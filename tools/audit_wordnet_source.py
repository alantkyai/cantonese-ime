"""Independent raw-XML/accounting audit for the Cantonese Wordnet source.

This module deliberately does not import the production Wordnet reader. A pass
establishes source/ledger consistency, never linguistic approval or completeness.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET


SOURCE = "wordnet:cantown"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
DTD = "http://globalwordnet.github.io/schemas/WN-LMF-1.0.dtd"
_KEYS = (
    "source_files_audited selected_lexicons lexicons_total lexical_entries_total "
    "input_rows excluded_lexical_entries forms_total form_candidates excluded_forms "
    "excluded_blank_forms blank_forms nonblank_forms accepted_rows quarantined_rows "
    "entries_without_forms accepted_entries duplicate_entries quarantined_forms "
    "normalized_reading_forms ignored_synsets ignored_form_tags explicit_pairs "
    "explicit_rows_present explicit_rows_missing review_records_required "
    "review_records_present review_records_missing review_records_unexpected "
    "review_records_invalid invalid_locked_source invalid_attestation_inventory "
    "structural_errors source_weight_or_origin_errors wordnet_source_rows_credited "
    "overlap_rows_present overlap_rows_previously_verified overlap_rows_not_previously_verified"
).split()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _han(character: str) -> bool:
    # Independent Unicode-name classification rather than the importer's ranges.
    name = unicodedata.name(character, "")
    return character == "〇" or name.startswith(("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-"))


def audit_wordnet(connection: sqlite3.Connection, lock_audit: dict | None,
                  verified_ids: dict[str, set[int]], review_rows: list[dict] | None = None) -> dict:
    """Check locked source pairs and every required source-review event.

    ``review_rows`` is the candidate sidecar's rows, when provided. Otherwise the
    persisted supplement_review table is authoritative. No database writes occur.
    """
    counts = Counter({key: 0 for key in _KEYS})
    errors: list[str] = []
    missing_pairs: list[dict] = []
    missing_reviews: list[dict] = []

    def result() -> dict:
        complete = (lock_audit is not None and not errors
                    and counts["source_files_audited"] == 1
                    and counts["selected_lexicons"] == 1
                    and counts["input_rows"] > 0 and counts["explicit_pairs"] > 0
                    and not any(counts[key] for key in (
                        "explicit_rows_missing", "review_records_missing", "review_records_unexpected",
                        "review_records_invalid", "invalid_locked_source", "invalid_attestation_inventory",
                        "structural_errors", "source_weight_or_origin_errors")))
        return {"counts": dict(counts), "mechanical_complete": bool(complete),
                "errors": errors, "missing_pair_samples": missing_pairs,
                "missing_review_samples": missing_reviews,
                "notice": "Independent locked XML pair and review-event accounting only; no linguistic approval, held-out evaluation or vocabulary-completeness claim."}

    if lock_audit is None:
        return result()
    if lock_audit.get("verified") is not True:
        counts["invalid_locked_source"] += 1
        errors.append("Wordnet source lock is not verified")
        return result()

    try:
        directory = Path(lock_audit["source_directory"]).resolve()
        records = lock_audit.get("files", [])
        by_name = {row["name"]: row for row in records}
        if len(by_name) != len(records):
            raise ValueError("Duplicate locked source names")

        def locked_bytes(name: str, maximum: int) -> bytes:
            record = by_name.get(name)
            if not record or record.get("matches_lock") is not True:
                raise ValueError("Missing verified locked file: " + name)
            path = directory / name
            if not path.resolve().is_relative_to(directory) or path.stat().st_size > maximum:
                raise ValueError("Invalid locked source path or size: " + name)
            payload = path.read_bytes()
            if (_sha(payload) != record.get("sha256")
                    or len(payload) != record.get("size_bytes")):
                raise ValueError("Locked source changed: " + name)
            return payload

        raw_lock = None
        raw_lock_path = Path(lock_audit["path"]) if lock_audit.get("path") else None
        if raw_lock_path is not None:
            raw_lock_bytes = raw_lock_path.read_bytes()
            if _sha(raw_lock_bytes) != lock_audit.get("sha256"):
                raise ValueError("Wordnet source lock changed after verification")
            raw_lock = json.loads(raw_lock_bytes)
            if not isinstance(raw_lock, dict):
                raise ValueError("Malformed Wordnet source lock")
        payload = locked_bytes("cantown.xml", 16_000_000)
        inventory_bytes = locked_bytes("parser-attested-bases.json", 100_000)
    except (OSError, ValueError, TypeError, KeyError) as error:
        counts["invalid_locked_source"] += 1
        errors.append(str(error))
        return result()

    try:
        inventory = json.loads(inventory_bytes)
        bases = inventory.get("bases")
        if (inventory.get("schema_version") != 1 or not isinstance(bases, list)
                or not 1 <= len(bases) <= 2000 or len(set(bases)) != len(bases)
                or any(not isinstance(base, str) or not re.fullmatch("[a-z]{1,12}", base) for base in bases)
                or not re.fullmatch("[a-f0-9]{64}", inventory.get("baseline_database_sha256", ""))):
            raise ValueError("Malformed frozen Wordnet admission inventory")
        if raw_lock is not None:
            attestation = raw_lock.get("parser_attestation", {})
            if (attestation.get("file") != "parser-attested-bases.json"
                    or attestation.get("sha256") != _sha(inventory_bytes)
                    or attestation.get("base_count") != len(bases)
                    or attestation.get("baseline_database_sha256") != inventory["baseline_database_sha256"]):
                raise ValueError("Admission inventory differs from its source lock")
        allowed = set(bases)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        counts["invalid_attestation_inventory"] += 1
        errors.append(str(error))
        return result()

    try:
        document = payload.decode("utf-8-sig")
        if re.search(r"<!ENTITY", document, re.I):
            raise ValueError("Entity declaration in Wordnet XML")
        declaration = re.compile(r"<!DOCTYPE\s+LexicalResource\s+SYSTEM\s+(['\"])([^'\"]+)\1\s*>")
        matches = list(declaration.finditer(document))
        if len(matches) > 1 or any(match.group(2) != DTD for match in matches):
            raise ValueError("Unexpected Wordnet DTD")
        document = declaration.sub("", document)
        if re.search(r"<!DOCTYPE", document, re.I):
            raise ValueError("Unsupported Wordnet DTD")
        root = ET.fromstring(document)
        if root.tag != "LexicalResource" or any(child.tag != "Lexicon" for child in root):
            raise ValueError("Unexpected Wordnet XML root/lexicon structure")
        lexicons = list(root)
        if len({lex.get("id") for lex in lexicons}) != len(lexicons):
            raise ValueError("Duplicate Wordnet lexicon identity")
        selected = [lex for lex in lexicons if lex.get("id") == "cantown-yue" and lex.get("language") == "yue"]
        if len(selected) != 1:
            raise ValueError("Exactly one own Cantonese lexicon is required")
        ids: set[str] = set()
        for lexicon in lexicons:
            if (lexicon.get("id"), lexicon.get("language")) not in {("cantown-yue", "yue"), ("cantown-en", "en")}:
                raise ValueError("Unexpected Wordnet lexicon identity/language")
            if lexicon.get("version") != "1.0" or lexicon.get("license") != LICENSE:
                raise ValueError("Unexpected Wordnet version/license")
            for entry in lexicon.findall("LexicalEntry"):
                identity = entry.get("id")
                if not identity or identity in ids:
                    raise ValueError("Missing or repeated lexical entry ID")
                ids.add(identity)
                lemmas = entry.findall("Lemma")
                if len(lemmas) != 1 or "writtenForm" not in lemmas[0].attrib:
                    raise ValueError("Entry requires exactly one own written lemma")
                if any("writtenForm" not in form.attrib for form in entry.findall("Form")):
                    raise ValueError("Form has no explicit reading attribute")
        # Reject hidden inherited lexical objects, while ignoring semantic data.
        for parent in root.iter():
            for child in parent:
                expected = {"Lexicon": "LexicalResource", "LexicalEntry": "Lexicon",
                            "Lemma": "LexicalEntry", "Form": "LexicalEntry", "Tag": "Form"}
                if child.tag in expected and parent.tag != expected[child.tag]:
                    raise ValueError("Nested/inherited lexical object")
                if child.tag == "Tag" and (child.attrib != {"category": "transliteration"}
                                           or (child.text or "").strip() != "ascii"):
                    raise ValueError("Unexpected Form metadata")
    except (UnicodeError, ET.ParseError, ValueError) as error:
        counts["structural_errors"] += 1
        errors.append(str(error))
        return result()

    source_hash = _sha(payload)
    expected_reviews: list[dict] = []
    seen: set[tuple[str, str]] = set()
    origin_present = any(row[1] == "origin" for row in connection.execute("PRAGMA table_info(entries)"))
    entry_columns = {row[1] for row in connection.execute("PRAGMA table_info(entries)")}

    def review(lexicon: str, identity: str, ordinal: int | None, text: str, raw: str,
               reason: str, status: str = "quarantined", **extra) -> None:
        expected_reviews.append({"source": SOURCE, "source_file": "cantown.xml", "source_sha256": source_hash,
                                 "lexicon_id": lexicon, "entry_id": identity, "form_ordinal": ordinal,
                                 "scope": "entry" if ordinal is None else "form", "text": text,
                                 "raw_reading": raw, "reason": reason, "status": status, **extra})
        counts["review_" + reason] += 1

    for lexicon in lexicons:
        lexicon_id = lexicon.get("id")
        target = lexicon_id == "cantown-yue"
        counts["lexicons_total"] += 1
        counts["selected_lexicons"] += int(target)
        counts["ignored_synsets"] += len(lexicon.findall("Synset"))
        for entry in lexicon.findall("LexicalEntry"):
            counts["lexical_entries_total"] += 1
            identity = entry.get("id")
            text = entry.find("Lemma").get("writtenForm")
            forms = entry.findall("Form")
            counts["forms_total"] += len(forms)
            counts["ignored_form_tags"] += sum(len(form.findall("Tag")) for form in forms)
            if not target:
                counts["excluded_lexical_entries"] += 1
                counts["excluded_forms"] += len(forms)
                if not forms:
                    review(lexicon_id, identity, None, text, "", "non_yue_lexicon", "excluded")
                for ordinal, form in enumerate(forms, 1):
                    raw = form.get("writtenForm")
                    counts["excluded_blank_forms"] += int(not raw.strip())
                    review(lexicon_id, identity, ordinal, text, raw, "non_yue_lexicon", "excluded")
                continue
            counts["input_rows"] += 1
            counts["form_candidates"] += len(forms)
            valid = 0
            if not forms:
                counts["entries_without_forms"] += 1
                review(lexicon_id, identity, None, text, "", "missing_forms", "missing_reading")
            for ordinal, form in enumerate(forms, 1):
                raw = form.get("writtenForm")
                if not raw.strip():
                    counts["blank_forms"] += 1
                    review(lexicon_id, identity, ordinal, text, raw, "blank_form", "missing_reading")
                    continue
                counts["nonblank_forms"] += 1
                codes = raw.lower().split()
                reason, extra = None, {}
                if any(not re.fullmatch(r"[a-z]{1,12}[1-6]", code) for code in codes):
                    reason = "noncanonical_jyutping"
                elif (unknown := sorted({code[:-1] for code in codes} - allowed)):
                    reason, extra = "unattested_syllables", {"unknown_bases": unknown}
                elif len(text) != len(codes):
                    reason, extra = "codepoint_syllable_alignment", {"text_codepoints": len(text), "syllable_count": len(codes)}
                elif not text or not all(_han(char) for char in text):
                    reason = "non_han_text"
                if reason:
                    counts["quarantined_forms"] += 1
                    review(lexicon_id, identity, ordinal, text, raw, reason, **extra)
                    continue
                valid += 1
                reading = " ".join(codes)
                if reading != raw:
                    counts["normalized_reading_forms"] += 1
                    review(lexicon_id, identity, ordinal, text, raw, "normalized_reading", "informational", reading=reading)
                if (text, reading) in seen:
                    counts["duplicate_entries"] += 1
                    continue
                seen.add((text, reading))
                counts["accepted_entries"] += 1
                counts["explicit_pairs"] += 1
                columns = ["rowid"] + [name for name in ("origin", "source", "weight") if name in entry_columns]
                found = connection.execute("SELECT " + ",".join(columns)
                                           + " FROM entries WHERE text=? AND reading=? LIMIT 1", (text, reading)).fetchone()
                counts["explicit_rows_present" if found else "explicit_rows_missing"] += 1
                if found:
                    values = dict(zip(columns, found))
                    origin = values.get("origin", "legacy_unspecified")
                    if values.get("source") == SOURCE:
                        if values.get("weight") != 0 or (origin_present and origin != "supplement"):
                            counts["source_weight_or_origin_errors"] += 1
                        else:
                            verified_ids.setdefault(origin, set()).add(values["rowid"])
                            counts["wordnet_source_rows_credited"] += 1
                    else:
                        # A pair can overlap another source, but Wordnet cannot
                        # authenticate that row's winning-source attribution.
                        counts["overlap_rows_present"] += 1
                        key = ("overlap_rows_previously_verified" if values["rowid"] in verified_ids.get(origin, set())
                               else "overlap_rows_not_previously_verified")
                        counts[key] += 1
                elif len(missing_pairs) < 8:
                    missing_pairs.append({"text": text, "reading": reading})
            counts["accepted_rows" if valid else "quarantined_rows"] += 1

    counts["source_files_audited"] = 1
    actual_reviews: list[dict] = []
    if review_rows is not None:
        for row in review_rows:
            if not isinstance(row, dict):
                counts["review_records_invalid"] += 1
            elif row.get("source") == SOURCE:
                actual_reviews.append(row)
    else:
        try:
            for source, text, status, details in connection.execute(
                    "SELECT source,text,status,details_json FROM supplement_review WHERE source=?", (SOURCE,)):
                try:
                    row = json.loads(details)
                    if not isinstance(row, dict) or (row.get("source"), row.get("text"), row.get("status")) != (source, text, status):
                        raise ValueError("Review detail/SQL columns disagree")
                    actual_reviews.append(row)
                except (ValueError, TypeError):
                    counts["review_records_invalid"] += 1
        except sqlite3.OperationalError:
            errors.append("Wordnet persisted review table is absent")

    identity_fields = ("lexicon_id", "entry_id", "form_ordinal", "reason", "status")
    lookup = defaultdict(list)
    for number, row in enumerate(actual_reviews):
        lookup[tuple(row.get(field) for field in identity_fields)].append((number, row))
    used: set[int] = set()
    for expected in expected_reviews:
        key = tuple(expected[field] for field in identity_fields)
        match = next((number for number, row in lookup.get(key, ()) if number not in used
                      and all(row.get(field) == value for field, value in expected.items())), None)
        if match is None:
            counts["review_records_missing"] += 1
            if len(missing_reviews) < 8:
                missing_reviews.append({field: expected[field] for field in identity_fields})
        else:
            used.add(match)
    counts["review_records_required"] = len(expected_reviews)
    counts["review_records_present"] = len(used)
    counts["review_records_unexpected"] = len(actual_reviews) - len(used)
    try:
        locked_bytes("cantown.xml", 16_000_000)
        locked_bytes("parser-attested-bases.json", 100_000)
        if raw_lock_path is not None and _sha(raw_lock_path.read_bytes()) != lock_audit.get("sha256"):
            raise ValueError("Wordnet source lock changed during audit")
    except (OSError, ValueError, TypeError) as error:
        counts["invalid_locked_source"] += 1
        errors.append(str(error))
    return result()
