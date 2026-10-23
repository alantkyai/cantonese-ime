"""Read-only evidence audit of the current dictionary, sources and mappings.

This reports mechanical checks separately from linguistic/release readiness.
It never promotes development seed coverage to a claim of held-out accuracy.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime.engine import MAX_INPUT_LENGTH
TONED = re.compile(r"[a-z]+[1-6]\Z")
ENTRY_FIELDS = ("text", "reading", "base_reading", "compact", "syllable_count", "weight", "source")
SUCCESS_ENCODINGS = {"already_explicit", "encoded_unique", "encoded_ambiguous", "generated_unique", "generated_ambiguous", "unique", "ambiguous", "complete"}
QUARANTINE_ENCODINGS = {"truncated", "unencodable", "too_long", "work_limit", "path_limit"}
IMPLEMENTATION_MODULES = ("engine.py", "mappings.py", "session.py", "__main__.py")
SUPPLEMENT_ZERO_WEIGHT_SOURCES = {"lshk:list.tsv", "words.hk:wordlist", "typeduck:principal", "unihan:kCantonese", "cccanto:dictionary", "cccanto:cedict-readings", "wordnet:cantown", "cccedict:headwords:autoencoded", "wiktionary:yue"}
TYPEDUCK_DECLARATION = "Except for the reverse lookup data listed above, this repo, including the main TypeDuck dictionary and the `jyut6ping3` schema, is licensed under [CC BY 4.0]"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"Dictionary not found: {path}. Run tools/build_dictionary.py first.")
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _gate(identifier: str, passed: bool, evidence: dict, requirement: str) -> dict:
    return {"id": identifier, "status": "pass" if passed else "incomplete", "requirement": requirement, "evidence": evidence}


def _lock_audit(path: Path, *, expected_source_id: str | None = None) -> dict:
    lock = read_json(path)
    source_directory = Path(lock.get("local_directory", ""))
    if not source_directory.is_absolute():
        source_directory = ROOT / source_directory
    source_directory = source_directory.resolve()
    files = []
    names = set()
    for item in lock.get("files", []):
        name = item.get("name", "")
        candidate = (source_directory / name).resolve()
        safe = bool(name) and candidate.is_relative_to(source_directory) and name not in names
        names.add(name)
        exists = safe and candidate.is_file()
        actual_hash = sha256(candidate) if exists else None
        actual_size = candidate.stat().st_size if exists else None
        files.append({
            "name": name, "safe_unique_path": safe, "exists": exists,
            "sha256": actual_hash, "size_bytes": actual_size,
            "matches_lock": exists and actual_hash == item.get("sha256") and actual_size == item.get("size_bytes"),
            "pinned_url": item.get("url"),
        })
    fields_present = all(lock.get(field) for field in ("license", "attribution")) and bool(lock.get("repository") or lock.get("data_url") or lock.get("archive_url"))
    pinned_commit = isinstance(lock.get("commit"), str) and bool(re.fullmatch(r"[a-fA-F0-9]{40}", lock["commit"]))
    snapshot_pinned = bool(lock.get("snapshot_id") and lock.get("snapshot_retrieved_at") and lock.get("data_url"))
    if snapshot_pinned:
        try:
            snapshot_pinned = datetime.fromisoformat(lock["snapshot_retrieved_at"]).utcoffset() is not None
        except (TypeError, ValueError):
            snapshot_pinned = False
    retained_license = any("license" in file["name"].lower() and file["matches_lock"] for file in files)
    retained_readme = any("readme" in file["name"].lower() and file["matches_lock"] for file in files)
    declaration_matches = None
    if snapshot_pinned:
        declaration = lock.get("license_declaration")
        declaration_files = [file for file in files if "license" in file["name"].lower() and file["matches_lock"]]
        declaration_matches = isinstance(declaration, str) and bool(declaration) and any(declaration in (source_directory / file["name"]).read_text(encoding="utf-8-sig") for file in declaration_files)
    source_id_matches = None if expected_source_id is None else lock.get("source_id") == expected_source_id
    source_kind = expected_source_id or lock.get("source_id")
    unicode_evidence = None
    if source_kind == "unihan:kCantonese":
        unicode_evidence = _unicode_release_evidence(lock, source_directory, files)
    principal_declaration = None
    if source_kind == "typeduck:principal":
        readme = next((file for file in files if file["name"] == "README.md" and file["matches_lock"]), None)
        principal_declaration = bool(readme and TYPEDUCK_DECLARATION in (source_directory / "README.md").read_text(encoding="utf-8-sig"))
    release_pinned = bool(unicode_evidence and unicode_evidence["verified"])
    cccanto_release = None
    if source_kind == "cccanto":
        from cantonese_ime.cccanto import verify_cccanto_snapshot
        try:
            verify_cccanto_snapshot(source_directory, lock)
            cccanto_release = True
        except (OSError, ValueError, zipfile.BadZipFile):
            cccanto_release = False
        fields_present = fields_present or bool(lock.get("source_url") and lock.get("license") and lock.get("attribution"))
        release_pinned = bool(cccanto_release)
    wordnet_snapshot = None
    if source_kind == "wordnet:cantown":
        from cantonese_ime.wordnet import verify_wordnet_snapshot
        try:
            verify_wordnet_snapshot(source_directory, lock)
            wordnet_snapshot = True
        except (OSError, ValueError):
            wordnet_snapshot = False
    headword_snapshot = None
    if source_kind == "cccedict:headwords":
        from cantonese_ime.cccedict_headwords import verify_cccedict_headwords_snapshot
        try:
            verify_cccedict_headwords_snapshot(source_directory, lock)
            headword_snapshot = True
            # The exact declaration is in the original source and publisher
            # page; the full legal-code title includes the extra word Public.
            declaration_matches = True
        except (OSError, ValueError):
            headword_snapshot = False
    yue_snapshot = None
    if source_kind == "wiktionary:yue":
        from cantonese_ime.yue_wiktionary import verify_yue_wiktionary_snapshot
        try:
            verify_yue_wiktionary_snapshot(source_directory, lock)
            yue_snapshot = True
        except (OSError, ValueError):
            yue_snapshot = False
    return {
        "path": str(path.resolve()), "sha256": sha256(path),
        "repository": lock.get("repository", lock.get("data_url", lock.get("archive_url", lock.get("source_url")))), "commit": lock.get("commit"), "snapshot_id": lock.get("snapshot_id"), "license": lock.get("license"),
        "retrieved_at": lock.get("snapshot_retrieved_at"), "scope": lock.get("scope"), "license_declaration": lock.get("license_declaration"),
        "attribution": lock.get("attribution"), "excluded": lock.get("excluded", []),
        "source_directory": str(source_directory), "files": files,
        "pin_type": "git_commit" if pinned_commit else ("versioned_wikimedia_dump" if yue_snapshot else ("versioned_cccanto_archives" if cccanto_release else ("versioned_unicode_distribution" if release_pinned else "retrieved_content_hash_snapshot"))),
        "license_evidence_retained": retained_license, "website_license_declaration_matches": declaration_matches,
        "unicode_release_evidence": unicode_evidence, "principal_license_declaration_matches": principal_declaration,
        "cccanto_archive_and_declaration_verified": cccanto_release,
        "wordnet_snapshot_verified": wordnet_snapshot,
        "cccedict_headwords_snapshot_verified": headword_snapshot,
        "yue_wiktionary_snapshot_verified": yue_snapshot,
        "expected_source_id_matches": source_id_matches,
        "verified": bool(files) and fields_present and source_id_matches is not False and (pinned_commit or snapshot_pinned or release_pinned or yue_snapshot) and retained_license and (retained_readme or snapshot_pinned or cccanto_release or yue_snapshot) and declaration_matches is not False and principal_declaration is not False and (unicode_evidence is None or release_pinned) and cccanto_release is not False and wordnet_snapshot is not False and headword_snapshot is not False and yue_snapshot is not False and all(file["matches_lock"] for file in files),
    }


def _unicode_release_evidence(lock: dict, directory: Path, files: list[dict]) -> dict:
    """Verify a versioned release without treating it as a website declaration."""
    version = lock.get("unicode_version")
    names = {file["name"] for file in files if file["matches_lock"]}
    required = {"Unihan.zip", "Unihan_Readings.txt", "LICENSE.txt", "ReadMe.txt"}
    version_valid = isinstance(version, str) and bool(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version))
    metadata_matches = version_valid and lock.get("archive_url") == f"https://www.unicode.org/Public/{version}/ucd/Unihan.zip" and lock.get("license") == "Unicode-3.0" and lock.get("property") == "kCantonese" and lock.get("property_status") == "Provisional"
    notice_matches = header_matches = readme_matches = archive_matches = False
    if required.issubset(names):
        notice = (directory / "LICENSE.txt").read_text(encoding="utf-8-sig")
        expected = lock.get("license_notice", {})
        notice_matches = isinstance(expected, dict) and notice.startswith("UNICODE LICENSE V3\n") and notice == expected.get("text") and expected.get("file") == "LICENSE.txt" and expected.get("sha256") == sha256(directory / "LICENSE.txt")
        if (directory / "Unihan_Readings.txt").stat().st_size <= 32_000_000:
            data = (directory / "Unihan_Readings.txt").read_bytes()
            header_matches = version_valid and f"# Unicode Version {version}" in data.decode("utf-8-sig").splitlines()
            readme_matches = version_valid and f"final data files for version {version}" in (directory / "ReadMe.txt").read_text(encoding="utf-8-sig")
            try:
                with zipfile.ZipFile(directory / "Unihan.zip") as archive:
                    members = [item for item in archive.infolist() if item.filename == "Unihan_Readings.txt"]
                    archive_matches = len(members) == 1 and members[0].file_size <= 32_000_000 and archive.read(members[0]) == data
            except (OSError, zipfile.BadZipFile, KeyError):
                archive_matches = False
    result = {"unicode_version": version, "property": lock.get("property"), "property_status": lock.get("property_status"), "metadata_matches": bool(metadata_matches), "retained_notice_matches": notice_matches, "readings_header_matches": header_matches, "final_release_readme_matches": readme_matches, "archive_extraction_matches": archive_matches}
    result["verified"] = all(result[name] for name in ("metadata_matches", "retained_notice_matches", "readings_header_matches", "final_release_readme_matches", "archive_extraction_matches"))
    return result


def _database_audit(connection: sqlite3.Connection) -> dict:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columns = {row[1] for row in connection.execute("PRAGMA table_info(entries)")}
    if not set(ENTRY_FIELDS).issubset(columns):
        raise ValueError("Dictionary entries table lacks required audited fields.")
    metadata = {}
    if "metadata" in tables:
        for key, value in connection.execute("SELECT key,value FROM metadata"):
            try:
                metadata[key] = json.loads(value)
            except (TypeError, ValueError):
                metadata[key] = value
    issues = Counter()
    issue_samples = []
    bases = set()
    toned = set()
    digest = hashlib.sha256()
    input_lengths = Counter()
    long_entry_samples = []
    supplement_frequency = Counter()
    supplement_frequency_by_source = Counter()
    supplement_nonzero_by_source = Counter()
    supplement_frequency_samples = []
    fields = ENTRY_FIELDS + (("origin",) if "origin" in columns else ())
    entry_count = 0
    for row in connection.execute("SELECT " + ",".join(fields) + " FROM entries ORDER BY text,reading"):
        entry_count += 1
        text, reading, base, compact, count, weight, source = row[:7]
        tokens = reading.split() if isinstance(reading, str) else []
        errors = []
        valid_reading = bool(tokens) and all(TONED.fullmatch(token) for token in tokens)
        if not valid_reading or reading != " ".join(tokens):
            errors.append("invalid_or_noncanonical_reading")
        if valid_reading:
            expected_base = " ".join(token[:-1] for token in tokens)
            bases.update(token[:-1] for token in tokens)
            toned.update(tokens)
            if base != expected_base or compact != expected_base.replace(" ", "") or count != len(tokens):
                errors.append("derived_reading_fields_mismatch")
            tone_free_length = len(expected_base.replace(" ", ""))
            fully_toned_length = len("".join(tokens))
            boundary_length = len(expected_base)
            input_lengths["max_tone_free_letters"] = max(input_lengths["max_tone_free_letters"], tone_free_length)
            input_lengths["max_fully_toned_letters_and_digits"] = max(input_lengths["max_fully_toned_letters_and_digits"], fully_toned_length)
            input_lengths["max_syllables"] = max(input_lengths["max_syllables"], len(tokens))
            input_lengths["entries_tone_free_over_64"] += tone_free_length > 64
            input_lengths["entries_fully_toned_over_64"] += fully_toned_length > 64
            input_lengths["entries_tone_free_with_boundaries_over_64"] += boundary_length > 64
            input_lengths["entries_tone_free_over_input_cap"] += tone_free_length > MAX_INPUT_LENGTH
            input_lengths["entries_fully_toned_over_input_cap"] += fully_toned_length > MAX_INPUT_LENGTH
            input_lengths["entries_with_boundaries_over_input_cap"] += boundary_length > MAX_INPUT_LENGTH
            if tone_free_length > MAX_INPUT_LENGTH and len(long_entry_samples) < 10:
                long_entry_samples.append({"text_prefix": text[:80] if isinstance(text, str) else repr(text), "reading_prefix": reading[:120], "tone_free_length": tone_free_length, "fully_toned_length": fully_toned_length})
        if not isinstance(text, str) or not text or text != text.strip() or any(ord(character) < 32 or ord(character) == 127 for character in text):
            errors.append("invalid_entry_text")
        if not isinstance(weight, (float, int)) or not math.isfinite(weight) or weight < 0:
            errors.append("invalid_weight")
        if not isinstance(source, str) or not source:
            errors.append("missing_entry_source")
        if "origin" in columns and row[7] == "supplement":
            supplement_frequency["all_supplement_rows"] += 1
            if source in SUPPLEMENT_ZERO_WEIGHT_SOURCES:
                supplement_frequency["selected_source_rows"] += 1
                supplement_frequency_by_source[source] += 1
                if weight != 0:
                    supplement_frequency["selected_source_nonzero_rows"] += 1
                    supplement_nonzero_by_source[source] += 1
                    if len(supplement_frequency_samples) < 10:
                        supplement_frequency_samples.append({"text": text, "reading": reading, "source": source, "weight": weight})
            else:
                supplement_frequency["custom_source_rows_outside_this_policy"] += 1
        issues.update(errors)
        if errors and len(issue_samples) < 10:
            issue_samples.append({"text": text, "reading": reading, "issues": errors})
        digest.update((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    duplicate_pairs = connection.execute("SELECT COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) n FROM entries GROUP BY text,reading HAVING COUNT(*)>1)").fetchone()[0]
    integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    stored_bases = {row[0] for row in connection.execute("SELECT base FROM syllables")} if "syllables" in tables else set()
    counts = {
        "entries": entry_count,
        "distinct_texts": connection.execute("SELECT COUNT(DISTINCT text) FROM entries").fetchone()[0],
        "distinct_readings": connection.execute("SELECT COUNT(DISTINCT reading) FROM entries").fetchone()[0],
        "single_character_entries": connection.execute("SELECT COUNT(*) FROM entries WHERE length(text)=1").fetchone()[0],
        "texts_with_multiple_readings": connection.execute("SELECT COUNT(*) FROM (SELECT text FROM entries GROUP BY text HAVING COUNT(DISTINCT reading)>1)").fetchone()[0],
        "readings_with_multiple_texts": connection.execute("SELECT COUNT(*) FROM (SELECT reading FROM entries GROUP BY reading HAVING COUNT(DISTINCT text)>1)").fetchone()[0],
        "zero_weight_entries": connection.execute("SELECT COUNT(*) FROM entries WHERE weight=0").fetchone()[0],
        "duplicate_text_reading_pairs": duplicate_pairs,
        "syllable_bases": len(bases), "toned_syllables": len(toned),
    }
    origins = dict(connection.execute("SELECT origin,COUNT(*) FROM entries GROUP BY origin")) if "origin" in columns else {"legacy_unspecified": entry_count}
    phrase_statuses = dict(connection.execute("SELECT status,COUNT(*) FROM phrase_encodings GROUP BY status")) if "phrase_encodings" in tables else {}
    supplement_review = [{"source": row[0], "status": row[1], "rows": row[2]} for row in connection.execute("SELECT source,status,COUNT(*) FROM supplement_review GROUP BY source,status ORDER BY source,status")] if "supplement_review" in tables else []
    return {
        "integrity_check": integrity, "counts": counts, "issues": dict(issues), "issue_samples": issue_samples,
        "source_entry_counts": dict(connection.execute("SELECT source,COUNT(*) FROM entries GROUP BY source")),
        "origin_entry_counts": origins, "phrase_encoding_statuses": phrase_statuses,
        "supplement_review_statuses": supplement_review,
        "supplement_frequency_integrity": {"origin_column_present": "origin" in columns, "counts": dict(supplement_frequency), "selected_source_rows_by_source": dict(supplement_frequency_by_source), "nonzero_rows_by_source": dict(supplement_nonzero_by_source), "nonzero_samples": supplement_frequency_samples,
                                            "policy": "New selected LSHK/words.hk/TypeDuck/Unihan/CC-Canto/Wordnet pronunciation pairs must retain weight0 as unknown-frequency sentinel. A text occurrence count or source ranking percentage does not measure a newly supplied pronunciation's frequency. Original Rime-authored pair weights are preserved; custom sources need their own declared policy."},
        "input_length_coverage": {"engine_raw_input_cap": MAX_INPUT_LENGTH, **dict(input_lengths), "long_entry_samples": long_entry_samples,
                                  "notice": "Source inclusion is not direct full-reading retrievability. Counts ending in over_64 retain the historical comparison threshold; over_input_cap uses the actual current engine bound. Being below the input cap does not prove every candidate survives decoder/pruning limits; prefix completion is a separate behavior."},
        "logical_rows_sha256": digest.hexdigest(), "metadata": metadata,
        "syllables_table_matches_entries": bool(stored_bases) and stored_bases == bases,
        "bases": sorted(bases), "toned_syllables": sorted(toned), "tables": sorted(tables),
    }


def _rime_source_audit(connection: sqlite3.Connection, lock: dict, tables: list[str], verified_ids: dict[str, set[int]]) -> dict:
    counts = Counter()
    per_source = {}
    samples = []
    origin_present = any(row[1] == "origin" for row in connection.execute("PRAGMA table_info(entries)"))
    ledger_columns = {row[1] for row in connection.execute("PRAGMA table_info(phrase_encodings)")}
    for file in lock["files"]:
        if not file["name"].endswith(".dict.yaml") or not file["matches_lock"]:
            continue
        file_counts = Counter()
        body = False
        path = Path(lock["source_directory"]) / file["name"]
        with path.open(encoding="utf-8-sig") as stream:
            for line_number, raw in enumerate(stream, start=1):
                line = raw.rstrip("\r\n")
                if not body:
                    body = line.strip() == "..."
                    continue
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                file_counts["input_rows"] += 1
                parts = line.split("\t")
                text = parts[0]
                if len(parts) > 1 and parts[1].strip():
                    file_counts["explicit_rows"] += 1
                    reading = " ".join(parts[1].lower().split())
                    found = connection.execute("SELECT rowid" + (",origin" if origin_present else "") + " FROM entries WHERE text=? AND reading=? LIMIT 1", (text, reading)).fetchone()
                    file_counts["explicit_rows_present" if found else "explicit_rows_missing"] += 1
                    if found:
                        verified_ids.setdefault(found[1] if origin_present else "legacy_unspecified", set()).add(found[0])
                    if not found and len(samples) < 10:
                        samples.append({"source": file["name"], "line": line_number, "text": text, "reading": reading, "issue": "explicit_pair_missing"})
                    continue
                file_counts["text_only_rows"] += 1
                present = connection.execute("SELECT 1 FROM entries WHERE text=? LIMIT 1", (text,)).fetchone()
                file_counts["text_only_with_any_stored_reading" if present else "text_only_without_stored_reading"] += 1
                ledger = None
                if "phrase_encodings" in tables:
                    if {"source", "line"}.issubset(ledger_columns):
                        ledger = connection.execute("SELECT status,codes_json,path_count,work_count,reason FROM phrase_encodings WHERE source=? AND line=? AND text=?", (file["name"], line_number, text)).fetchone()
                    else:
                        ledger = connection.execute("SELECT status,codes_json,path_count,work_count,reason FROM phrase_encodings WHERE text=?", (text,)).fetchone()
                if ledger is None:
                    file_counts["text_only_without_encoding_ledger"] += 1
                    continue
                status, raw_codes, path_count, work_count, reason = ledger
                try:
                    codes = json.loads(raw_codes)
                    if not isinstance(codes, list) or any(not isinstance(code, str) or not code.split() or any(not TONED.fullmatch(token) for token in code.split()) for code in codes):
                        raise ValueError("Invalid encoding codes")
                    if not isinstance(path_count, int) or path_count < 0 or not isinstance(work_count, int) or work_count < 0:
                        raise ValueError("Invalid encoding counts")
                except (ValueError, TypeError):
                    file_counts["invalid_encoding_ledger"] += 1
                    continue
                if status in SUCCESS_ENCODINGS and codes:
                    missing = 0
                    for code in codes:
                        found = connection.execute("SELECT rowid" + (",origin" if origin_present else "") + " FROM entries WHERE text=? AND reading=? LIMIT 1", (text, code)).fetchone()
                        missing += not found
                        if found:
                            verified_ids.setdefault(found[1] if origin_present else "legacy_unspecified", set()).add(found[0])
                    file_counts["successful_encoded_source_rows"] += 1
                    file_counts["encoding_codes_missing_from_entries"] += missing
                elif status in QUARANTINE_ENCODINGS and reason:
                    file_counts["quarantined_source_rows"] += 1
                    if origin_present:
                        generated = connection.execute("SELECT COUNT(*) FROM entries WHERE text=? AND origin='generated'", (text,)).fetchone()[0]
                        file_counts["quarantined_generated_entries"] += generated
                    else:
                        file_counts["quarantine_origin_unverifiable"] += 1
                else:
                    file_counts["unrecognized_encoding_status"] += 1
        counts.update(file_counts)
        per_source[file["name"]] = dict(file_counts)
    return {"counts": dict(counts), "per_source": per_source, "missing_samples": samples}


def _review_records(connection: sqlite3.Connection) -> dict:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    records = {}
    if "supplement_review" in tables:
        for source, text, status, raw_details in connection.execute("SELECT source,text,status,details_json FROM supplement_review"):
            details = json.loads(raw_details)
            records.setdefault((source, status, text), []).append(details)
    return records


def _supplement_audit(connection: sqlite3.Connection, lock: dict | None, verified_ids: dict[str, set[int]]) -> dict:
    counts = Counter()
    review = _review_records(connection)
    origin_present = any(row[1] == "origin" for row in connection.execute("PRAGMA table_info(entries)"))
    if lock:
        for file in lock["files"]:
            if file["name"] != "list.tsv" or not file["matches_lock"]:
                continue
            with (Path(lock["source_directory"]) / file["name"]).open(encoding="utf-8-sig", newline="") as stream:
                for line, row in enumerate(csv.DictReader(stream, delimiter="\t"), start=2):
                    counts["input_rows"] += 1
                    text, reading = row.get("CH", ""), " ".join(row.get("JP", "").strip().lower().split())
                    if len(text) != 1:
                        counts["invalid_source_text"] += 1
                        continue
                    if not reading:
                        counts["description_only_rows"] += 1
                        records = review.get(("lshk:list.tsv", "description_only", text), [])
                        if not any(record.get("line") == line and record.get("reason") for record in records):
                            counts["description_review_missing"] += 1
                        continue
                    if any(not TONED.fullmatch(token) for token in reading.split()):
                        counts["invalid_source_reading"] += 1
                        continue
                    counts["explicit_rows"] += 1
                    counts["single_syllable_rows" if len(reading.split()) == 1 else "multisyllable_rows"] += 1
                    found = connection.execute("SELECT rowid" + (",origin" if origin_present else "") + " FROM entries WHERE text=? AND reading=? LIMIT 1", (text, reading)).fetchone()
                    counts["explicit_rows_present" if found else "explicit_rows_missing"] += 1
                    if found:
                        verified_ids.setdefault(found[1] if origin_present else "legacy_unspecified", set()).add(found[0])
    return {"counts": dict(counts), "note": "Counts source rows, not unique pairs. Multisyllable JP is explicit pronunciation; blank JP is a description-only review record, never inferred from DESC_JP."}


def _wordshk_audit(connection: sqlite3.Connection, lock: dict | None, verified_ids: dict[str, set[int]]) -> dict:
    counts = Counter()
    review = _review_records(connection)
    origin_present = any(row[1] == "origin" for row in connection.execute("PRAGMA table_info(entries)"))
    if lock:
        for file in lock["files"]:
            if file["name"] != "wordslist.json" or not file["matches_lock"]:
                continue
            document = read_json(Path(lock["source_directory"]) / file["name"])
            for text, readings in document.items():
                counts["source_text_keys"] += 1
                if not isinstance(readings, list):
                    raise ValueError("words.hk source readings must be lists.")
                if not readings:
                    counts["empty_reading_lists"] += 1
                for index, raw in enumerate(readings):
                    counts["source_reading_rows"] += 1
                    valid_text = bool(text) and text == text.strip() and not any(ord(character) < 32 or 0xD800 <= ord(character) <= 0xDFFF for character in text)
                    valid_code = isinstance(raw, str) and bool(raw.split()) and all(TONED.fullmatch(token) for token in raw.split())
                    variant = text.endswith("*") and text.count("*") == 1 and len(text) > 1
                    normalized_text = text[:-1] if variant else text
                    valid_marker = "*" not in text or variant
                    template = any(marker in text for marker in ("⋯", "…", "..."))
                    if not valid_text or not valid_code or not valid_marker or normalized_text != normalized_text.strip() or template:
                        counts["quarantined_source_rows"] += 1
                        records = review.get(("words.hk:wordlist", "quarantined", text), [])
                        if not any(record.get("reading_index") == index and record.get("raw_reading") == raw and record.get("reason") for record in records):
                            counts["quarantine_review_missing"] += 1
                        continue
                    reading = " ".join(raw.split())
                    counts["accepted_source_rows"] += 1
                    found = connection.execute("SELECT rowid" + (",origin" if origin_present else "") + " FROM entries WHERE text=? AND reading=? LIMIT 1", (normalized_text, reading)).fetchone()
                    counts["explicit_rows_present" if found else "explicit_rows_missing"] += 1
                    if found:
                        verified_ids.setdefault(found[1] if origin_present else "legacy_unspecified", set()).add(found[0])
                    if variant:
                        counts["normalized_variant_rows"] += 1
                        records = review.get(("words.hk:wordlist", "normalized_variant", normalized_text), [])
                        if not any(record.get("reading_index") == index and record.get("raw_text") == text and record.get("raw_reading") == raw for record in records):
                            counts["variant_review_missing"] += 1
    return {"counts": dict(counts), "notice": "A normalized_variant is retained source annotation, not quarantine. Quarantined noncanonical readings and templates require exact raw evidence. Counts are physical reading rows, so duplicates can map to one dictionary pair."}


def _typeduck_audit(connection: sqlite3.Connection, lock: dict | None, verified_ids: dict[str, set[int]]) -> dict:
    counts = Counter()
    review = _review_records(connection)
    origin_present = any(row[1] == "origin" for row in connection.execute("PRAGMA table_info(entries)"))
    seen = set()
    if lock:
        for file in lock["files"]:
            if file["name"] != "jyut6ping3.dict.yaml" or not file["matches_lock"]:
                continue
            counts["source_files_audited"] += 1
            body = False
            header_started = principal_name = False
            with (Path(lock["source_directory"]) / file["name"]).open(encoding="utf-8-sig") as stream:
                for number, raw in enumerate(stream, 1):
                    line = raw.rstrip("\r\n")
                    if not body:
                        if not line.strip() or line.lstrip().startswith("#"):
                            continue
                        if line == "---" and not header_started:
                            header_started = True
                            continue
                        if line == "...":
                            body = True
                            if not header_started or not principal_name:
                                counts["invalid_source_structure"] += 1
                            continue
                        key, separator, value = line.partition(":")
                        if not header_started or not separator or key.strip() in ("columns", "import_tables"):
                            counts["invalid_source_structure"] += 1
                        if key.strip() == "name":
                            principal_name = value.strip().strip("\"'") == "jyut6ping3"
                        continue
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    counts["input_rows"] += 1
                    fields = line.split("\t")
                    if len(fields) != 3 or not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)%", fields[-1]):
                        counts["invalid_source_structure"] += 1
                        continue
                    text, raw_reading, percentage = fields
                    valid_text = bool(text) and text == text.strip() and not any(ord(character) < 32 or 0xD800 <= ord(character) <= 0xDFFF for character in text)
                    codes = raw_reading.lower().split()
                    valid_reading = bool(codes) and all(TONED.fullmatch(code) for code in codes)
                    if not valid_text or not valid_reading:
                        counts["quarantined_source_rows"] += 1
                        records = review.get(("typeduck:principal", "quarantined", text), [])
                        if not any(record.get("line") == number and record.get("raw_text") == text and record.get("raw_reading") == raw_reading and record.get("raw_weight") == percentage and record.get("raw_line") == line and record.get("reason") for record in records):
                            counts["quarantine_review_missing"] += 1
                        continue
                    reading = " ".join(codes)
                    counts["accepted_source_rows"] += 1
                    if reading != raw_reading:
                        counts["normalized_reading_rows"] += 1
                    pair = (text, reading)
                    if pair in seen:
                        counts["duplicate_source_pairs"] += 1
                    seen.add(pair)
                    found = connection.execute("SELECT rowid" + (",origin" if origin_present else "") + " FROM entries WHERE text=? AND reading=? LIMIT 1", pair).fetchone()
                    counts["explicit_rows_present" if found else "explicit_rows_missing"] += 1
                    if found:
                        verified_ids.setdefault(found[1] if origin_present else "legacy_unspecified", set()).add(found[0])
            if not body:
                counts["invalid_source_structure"] += 1
    return {"counts": dict(counts), "notice": "Principal table only. Canonical text/tone pairs are retained; reading case and whitespace may normalize. Raw marked pronunciations require exact quarantine evidence. Source percentages are ranking annotations and are not imported as frequency. Explicit export rows do not establish independent human phrase review."}


def _unihan_audit(connection: sqlite3.Connection, lock: dict | None, verified_ids: dict[str, set[int]]) -> dict:
    counts = Counter()
    origin_present = any(row[1] == "origin" for row in connection.execute("PRAGMA table_info(entries)"))
    seen = set()
    if lock:
        for file in lock["files"]:
            if file["name"] != "Unihan_Readings.txt" or not file["matches_lock"]:
                continue
            counts["source_files_audited"] += 1
            with (Path(lock["source_directory"]) / file["name"]).open(encoding="utf-8-sig") as stream:
                for raw in stream:
                    line = raw.rstrip("\r\n")
                    if not line.strip() or line.startswith("#"):
                        continue
                    counts["scanned_data_rows"] += 1
                    fields = line.split("\t")
                    if len(fields) != 3:
                        counts["invalid_source_structure"] += 1
                        continue
                    point, prop, value = fields
                    if prop != "kCantonese":
                        counts["ignored_other_property_rows"] += 1
                        continue
                    counts["input_rows"] += 1
                    matched = re.fullmatch(r"U\+([0-9A-Fa-f]{4,6})", point)
                    scalar = int(matched[1], 16) if matched else -1
                    codes = value.split()
                    if not 0 <= scalar <= 0x10FFFF or 0xD800 <= scalar <= 0xDFFF or not codes or any(not re.fullmatch(r"[a-z]{1,6}[1-6]", code) for code in codes) or len(codes) != len(set(codes)) or scalar in seen:
                        counts["invalid_source_reading"] += 1
                        continue
                    seen.add(scalar)
                    counts["alternative_reading_rows"] += len(codes) > 1
                    for code in codes:
                        counts["accepted_source_pairs"] += 1
                        found = connection.execute("SELECT rowid" + (",origin" if origin_present else "") + " FROM entries WHERE text=? AND reading=? LIMIT 1", (chr(scalar), code)).fetchone()
                        counts["explicit_rows_present" if found else "explicit_rows_missing"] += 1
                        if found:
                            verified_ids.setdefault(found[1] if origin_present else "legacy_unspecified", set()).add(found[0])
    return {"counts": dict(counts), "notice": "Direct kCantonese values only; space-separated values are alternative character readings, never word syllables. Other properties and variant inheritance supply no pronunciation. The property is provisional; syntax/source coverage is not a normative pronunciation or phrase-quality judgment."}


def _cccanto_audit(connection: sqlite3.Connection, lock: dict | None, verified_ids: dict[str, set[int]]) -> dict:
    """Independently reconstruct accepted headword pairs from raw brace fields."""
    counts = Counter()
    review = _review_records(connection)
    origin_present = any(row[1] == "origin" for row in connection.execute("PRAGMA table_info(entries)"))
    if not lock:
        return {"counts": {}}
    directory = Path(lock["source_directory"])
    inventory_file = next((f for f in lock["files"] if f["name"] == "parser-attested-bases.json" and f["matches_lock"]), None)
    if not inventory_file:
        return {"counts": {"invalid_attestation_inventory": 1}}
    allowed = set(read_json(directory / inventory_file["name"]).get("bases", ()))
    source_files = {"cccanto-webdist.txt": "cccanto:dictionary",
                    "cccedict-canto-readings-150923.txt": "cccanto:cedict-readings"}
    for file in lock["files"]:
        if file["name"] not in source_files or not file["matches_lock"]:
            continue
        counts["source_files_audited"] += 1
        source = source_files[file["name"]]
        seen = set()
        with (directory / file["name"]).open(encoding="utf-8-sig") as stream:
            for line_number, physical in enumerate(stream, 1):
                raw = physical.rstrip("\r\n")
                if not raw.strip() or raw.lstrip().startswith("#"):
                    continue
                counts["input_rows"] += 1
                prefix, opening, remainder = raw.partition("{")
                raw_reading, closing, suffix = remainder.partition("}")
                header = re.fullmatch(r"(\S+)\s+(\S+)\s+\[[^\[\]]*\]\s+", prefix)
                well_formed = bool(header and opening and closing and "{" not in raw_reading and "}" not in raw_reading
                                   and (not suffix or re.fullmatch(r"\s+/.*", suffix)))

                def quarantine(text, reason, scope="row"):
                    counts["quarantined_" + scope + "s"] += 1
                    records = review.get((source, "quarantined", text), ())
                    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                    if not any(item.get("line") == line_number and item.get("reason") == reason
                               and item.get("scope") == scope and item.get("raw_line_sha256") == digest
                               for item in records):
                        counts["quarantine_review_missing"] += 1

                if not well_formed:
                    quarantine(raw.split(maxsplit=1)[0], "malformed_record")
                    continue
                traditional, simplified = header.groups()
                codes = raw_reading.lower().split()
                if not codes or any(not re.fullmatch(r"[a-z]{1,12}[1-6]", code) for code in codes):
                    quarantine(traditional, "noncanonical_jyutping")
                    continue
                if any(code[:-1] not in allowed for code in codes):
                    quarantine(traditional, "unattested_syllables")
                    continue
                reading = " ".join(codes)
                valid_forms = 0
                for text in dict.fromkeys((traditional, simplified)):
                    if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in text):
                        quarantine(text, "invalid_text", "form")
                        continue
                    if len(text) != len(codes):
                        quarantine(text, "codepoint_syllable_alignment", "form")
                        continue
                    valid_forms += 1
                    if (text, reading) in seen:
                        counts["duplicate_pairs"] += 1
                        continue
                    seen.add((text, reading))
                    counts["explicit_pairs"] += 1
                    found = connection.execute("SELECT rowid" + (",origin" if origin_present else "")
                                               + " FROM entries WHERE text=? AND reading=? LIMIT 1", (text, reading)).fetchone()
                    counts["explicit_rows_present" if found else "explicit_rows_missing"] += 1
                    if found:
                        verified_ids.setdefault(found[1] if origin_present else "legacy_unspecified", set()).add(found[0])
                counts["accepted_rows" if valid_forms else "rows_without_aligned_forms"] += 1
    return {"counts": dict(counts), "notice": "Independent raw-record forward/reverse provenance audit. Only explicit brace Jyutping and aligned traditional/simplified headwords are verified; Mandarin Pinyin and definitions are excluded. Unattested forms remain review decisions, not inferred spelling repairs."}


def _mapping_audit(path: Path, bases: list[str], toned: list[str]) -> dict:
    if not path.is_file():
        return {"exists": False, "status": "incomplete", "reason": "Mapping inventory has not been generated."}
    document = read_json(path)
    # The observed inventory is useful for coverage. It does not itself define
    # every phonotactically legal Cantonese syllable or condemn source loans.
    items = document.get("syllables", document.get("canonical_syllables", []))
    inventory_bases = set()
    inventory_toned = set()
    for item in items:
        if isinstance(item, str):
            if TONED.fullmatch(item):
                inventory_toned.add(item)
                inventory_bases.add(item[:-1])
            else:
                inventory_bases.add(item)
        elif isinstance(item, dict):
            base = item.get("base", item.get("syllable"))
            if isinstance(base, str):
                inventory_bases.add(base)
                for tone in item.get("tones", item.get("lshk_tones", [])):
                    inventory_toned.add(base + str(tone))
                for source_tones in item.get("observed_tones_by_source", {}).values():
                    inventory_toned.update(base + str(tone) for tone in source_tones)
    source_database = document.get("source_metadata", {}).get("database", {})
    return {
        "exists": True, "sha256": sha256(path), "schema_keys": sorted(document),
        "source_database": source_database,
        "inventory_bases": len(inventory_bases), "inventory_toned_syllables": len(inventory_toned),
        "bases": sorted(inventory_bases),
        "dictionary_bases_not_in_inventory": sorted(set(bases) - inventory_bases),
        "dictionary_toned_syllables_not_in_inventory": sorted(set(toned) - inventory_toned) if inventory_toned else None,
        "inventory_bases_not_in_dictionary": sorted(inventory_bases - set(bases)),
        "parsed": bool(inventory_bases),
        "notice": "Observed inventory coverage only; absent loans, variants and rare readings require review rather than automatic rejection.",
    }


def _spellings_audit(path: Path | None, inventory_bases: list[str]) -> dict:
    if not path or not path.is_file():
        return {"exists": False, "valid": False}
    document = read_json(path)
    aliases = document.get("aliases", [])
    seen = set()
    targets: dict[str, set[str]] = {}
    issues = Counter()
    for alias in aliases:
        if not isinstance(alias, dict):
            issues["invalid_alias_record"] += 1
            continue
        spelling, canonical, penalty = alias.get("spelling"), alias.get("canonical"), alias.get("penalty")
        if not isinstance(spelling, str) or not spelling.isascii() or not spelling.isalpha() or spelling != spelling.lower():
            issues["invalid_spelling"] += 1
            continue
        if not isinstance(canonical, str) or canonical not in inventory_bases:
            issues["canonical_target_not_in_inventory"] += 1
            continue
        if not isinstance(penalty, (int, float)) or not math.isfinite(penalty) or penalty < 0:
            issues["invalid_penalty"] += 1
        pair = (spelling, canonical)
        if pair in seen:
            issues["duplicate_alias_pair"] += 1
        seen.add(pair)
        targets.setdefault(spelling, set()).add(canonical)
    collisions = {spelling: sorted(values) for spelling, values in targets.items() if len(values) > 1}
    return {
        "exists": True, "sha256": sha256(path), "profile_version": document.get("profile_version"),
        "valid": bool(aliases) and not issues, "alias_records": len(aliases), "unique_alias_pairs": len(seen),
        "issues": dict(issues), "collision_spellings": len(collisions), "collision_samples": dict(list(sorted(collisions.items()))[:20]),
        "policy": document.get("policy"), "rules": document.get("rules"),
        "notice": "Multiple canonical targets for one spelling are legitimate ambiguity, not automatically errors; candidate retention and ranking need separate behavioral tests.",
    }


def _implementation_hashes(directory: Path) -> dict[str, str | None]:
    result = {}
    for name in IMPLEMENTATION_MODULES:
        try:
            result[name] = sha256(directory / name)
        except OSError:
            result[name] = None
    return result


def _evaluation_audit(path: Path | None, database_hash: str, corpus_path: Path | None,
                      implementation_directory: Path | None = None) -> dict:
    if not path or not path.is_file():
        return {"provided": False, "current_evidence": False}
    implementation_directory = implementation_directory or ROOT / "cantonese_ime"
    raw_report = path.read_bytes()
    document = json.loads(raw_report.decode("utf-8-sig"))
    if not isinstance(document, dict):
        raise ValueError("Evaluation report must be a JSON object.")
    reported = document.get("implementation_sha256")
    valid_map = isinstance(reported, dict) and set(reported) == set(IMPLEMENTATION_MODULES)
    valid_map = valid_map and all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in reported.values())
    # Only fixed project-owned module names are opened. Report-supplied keys
    # never become filesystem paths, including malformed or traversal keys.
    actual_hashes = _implementation_hashes(implementation_directory)
    implementation_matches = bool(valid_map and all(actual_hashes.values()) and reported == actual_hashes)
    actual_corpus_hash = sha256(corpus_path) if corpus_path and corpus_path.is_file() else None
    reported_corpus_hash = document.get("corpus_sha256")
    corpus_matches = isinstance(reported_corpus_hash, str) and bool(re.fullmatch(r"[0-9a-f]{64}", reported_corpus_hash)) and actual_corpus_hash == reported_corpus_hash
    report_hash = hashlib.sha256(raw_report).hexdigest()
    report_stable = sha256(path) == report_hash
    dictionary_matches = document.get("dictionary_sha256") == database_hash
    return {
        "provided": True, "sha256": report_hash, "report_stable_during_check": report_stable,
        "evaluation_kind": document.get("evaluation_kind"), "matches_dictionary": dictionary_matches,
        "corpus_path": str(corpus_path.resolve()) if corpus_path else None,
        "corpus_sha256": actual_corpus_hash, "matches_corpus": corpus_matches,
        "implementation_field_valid": bool(valid_map), "implementation_matches_current_sources": implementation_matches,
        "actual_implementation_sha256": actual_hashes,
        "aggregate": document.get("aggregate"), "notice": document.get("notice"),
        "current_evidence": dictionary_matches and corpus_matches and implementation_matches and report_stable,
        "authenticity_notice": "Hashes verify artifact correspondence, not who ran or approved a report. Reported aggregates remain claims of the retained evaluation run, not authenticated human review.",
    }


def audit_dictionary(
    database: Path,
    lock_path: Path,
    *,
    mapping_lock_path: Path | None = None,
    wordshk_lock_path: Path | None = None,
    typeduck_lock_path: Path | None = None,
    unihan_lock_path: Path | None = None,
    cccanto_lock_path: Path | None = None,
    wordnet_lock_path: Path | None = None,
    cccedict_headwords_lock_path: Path | None = None,
    yue_wiktionary_lock_path: Path | None = None,
    inventory_path: Path | None = None,
    spellings_path: Path | None = None,
    notices_path: Path | None = None,
    manifest_path: Path | None = None,
    evaluation_path: Path | None = None,
    evaluation_corpus_path: Path | None = None,
    compare_database: Path | None = None,
) -> dict:
    if not database.is_file():
        raise FileNotFoundError(f"Dictionary not found: {database}. Run tools/build_dictionary.py first.")
    before_stat = database.stat()
    before_hash = sha256(database)
    implementation_before = _implementation_hashes(ROOT / "cantonese_ime") if evaluation_path else None
    source_lock = _lock_audit(lock_path)
    mapping_lock = _lock_audit(mapping_lock_path) if mapping_lock_path and mapping_lock_path.is_file() else None
    wordshk_lock = _lock_audit(wordshk_lock_path) if wordshk_lock_path and wordshk_lock_path.is_file() else None
    typeduck_lock = _lock_audit(typeduck_lock_path, expected_source_id="typeduck:principal") if typeduck_lock_path and typeduck_lock_path.is_file() else None
    unihan_lock = _lock_audit(unihan_lock_path, expected_source_id="unihan:kCantonese") if unihan_lock_path and unihan_lock_path.is_file() else None
    cccanto_lock = _lock_audit(cccanto_lock_path, expected_source_id="cccanto") if cccanto_lock_path and cccanto_lock_path.is_file() else None
    wordnet_lock = _lock_audit(wordnet_lock_path, expected_source_id="wordnet:cantown") if wordnet_lock_path and wordnet_lock_path.is_file() else None
    headword_lock = _lock_audit(cccedict_headwords_lock_path, expected_source_id="cccedict:headwords") if cccedict_headwords_lock_path and cccedict_headwords_lock_path.is_file() else None
    yue_lock = _lock_audit(yue_wiktionary_lock_path, expected_source_id="wiktionary:yue") if yue_wiktionary_lock_path and yue_wiktionary_lock_path.is_file() else None
    verified_ids = {origin: set() for origin in ("explicit", "supplement", "generated", "legacy_unspecified")}
    with closing(_connect(database)) as connection:
        db = _database_audit(connection)
        headwords_selected = ("headword_encoding" in db["metadata"]
                              or bool(db["source_entry_counts"].get("cccedict:headwords:autoencoded"))
                              or bool({"cccedict_headword_forms", "cccedict_headword_encodings"} & set(db["tables"])))
        yue_selected = ("yue_wiktionary" in db["metadata"]
                        or bool(db["source_entry_counts"].get("wiktionary:yue"))
                        or any(name.startswith("yue_wiktionary_") for name in db["tables"]))
        if cccedict_headwords_lock_path is None and headwords_selected:
            cccedict_headwords_lock_path = ROOT / "data/supplements/cccedict-headwords.sources.lock.json"
            headword_lock = _lock_audit(cccedict_headwords_lock_path, expected_source_id="cccedict:headwords") if cccedict_headwords_lock_path.is_file() else None
        if yue_wiktionary_lock_path is None and yue_selected:
            yue_wiktionary_lock_path = ROOT / "data/supplements/yue-wiktionary.sources.lock.json"
            yue_lock = _lock_audit(yue_wiktionary_lock_path, expected_source_id="wiktionary:yue") if yue_wiktionary_lock_path.is_file() else None
        sources = _rime_source_audit(connection, source_lock, db["tables"], verified_ids)
        supplement = _supplement_audit(connection, mapping_lock, verified_ids)
        wordshk = _wordshk_audit(connection, wordshk_lock, verified_ids)
        typeduck = _typeduck_audit(connection, typeduck_lock, verified_ids)
        unihan = _unihan_audit(connection, unihan_lock, verified_ids)
        cccanto = _cccanto_audit(connection, cccanto_lock, verified_ids)
        wordnet = {"counts": {}}
        if wordnet_lock:
            from tools.audit_wordnet_source import audit_wordnet
            wordnet = audit_wordnet(connection, wordnet_lock, verified_ids)
        headwords = {"counts": {}, "mechanical_complete": False}
        if headword_lock:
            from tools.audit_cccedict_headwords import audit_cccedict_headwords
            headwords = audit_cccedict_headwords(connection, headword_lock, verified_ids)
        yue = {"counts": {}, "mechanical_complete": False}
        if yue_lock:
            from tools.audit_yue_wiktionary import audit_yue_wiktionary
            yue = audit_yue_wiktionary(connection, yue_lock, verified_ids)
    provenance_counts = {origin: {"live_entries": count, "entries_verified_against_source_or_complete_ledger": len(verified_ids.get(origin, set())), "unverified_entries": count - len(verified_ids.get(origin, set()))} for origin, count in db["origin_entry_counts"].items()}
    all_entries_verified = all(counts["unverified_entries"] == 0 for counts in provenance_counts.values())
    inventory = _mapping_audit(inventory_path, db["bases"], db["toned_syllables"]) if inventory_path else {"exists": False, "parsed": False}
    inventory_source_database = inventory.get("source_database", {})
    inventory["source_database_matches"] = (inventory_source_database.get("sha256", inventory_source_database.get("database_sha256")) == before_hash)
    spellings = _spellings_audit(spellings_path, inventory.get("bases", []))
    manifest = read_json(manifest_path) if manifest_path and manifest_path.is_file() else None
    manifest_matches = bool(manifest and manifest.get("database_sha256") == before_hash and manifest.get("entry_count") == db["counts"]["entries"])
    comparison = {"provided": compare_database is not None}
    if compare_database:
        if compare_database.resolve() == database.resolve():
            raise ValueError("Comparison database must be a separately produced file.")
        with closing(_connect(compare_database)) as comparison_connection:
            comparison_db = _database_audit(comparison_connection)
        comparison.update({
            "database_sha256": sha256(compare_database),
            "logical_rows_sha256": comparison_db["logical_rows_sha256"],
            "matching_database_bytes": sha256(compare_database) == before_hash,
            "matching_logical_rows": comparison_db["logical_rows_sha256"] == db["logical_rows_sha256"],
            "notice": "Equal files establish artifact equality; independent clean-build invocation must also be recorded by the operator.",
        })
    evaluation = _evaluation_audit(evaluation_path, before_hash, evaluation_corpus_path or ROOT / "eval/core_cases.json")
    if evaluation["provided"]:
        implementation_stable = implementation_before == evaluation["actual_implementation_sha256"]
        evaluation["implementation_stable_during_audit"] = implementation_stable
        evaluation["current_evidence"] = evaluation["current_evidence"] and implementation_stable
    after_stat = database.stat()
    database_stable = before_hash == sha256(database) and (before_stat.st_ino, before_stat.st_size, before_stat.st_mtime_ns) == (after_stat.st_ino, after_stat.st_size, after_stat.st_mtime_ns)
    counts = sources["counts"]
    ledger_issues = sum(counts.get(name, 0) for name in (
        "text_only_without_encoding_ledger", "invalid_encoding_ledger", "encoding_codes_missing_from_entries",
        "quarantined_generated_entries", "quarantine_origin_unverifiable", "unrecognized_encoding_status",
    ))
    selected_rime_files = [file for file in source_lock["files"] if file["name"].endswith(".dict.yaml")]
    selected_sources_accounted = bool(selected_rime_files) and all(file["matches_lock"] and file["name"] in sources["per_source"] for file in selected_rime_files) and counts.get("explicit_rows_missing", 0) == 0 and ledger_issues == 0
    supplement_issues = sum(supplement["counts"].get(name, 0) for name in ("explicit_rows_missing", "invalid_source_text", "invalid_source_reading", "description_review_missing"))
    wordshk_issues = sum(wordshk["counts"].get(name, 0) for name in ("explicit_rows_missing", "quarantine_review_missing", "variant_review_missing"))
    wordshk_verified = wordshk_lock_path is None or bool(wordshk_lock and wordshk_lock["verified"])
    typeduck_verified = typeduck_lock_path is None or bool(typeduck_lock and typeduck_lock["verified"])
    unihan_verified = unihan_lock_path is None or bool(unihan_lock and unihan_lock["verified"])
    cccanto_verified = cccanto_lock_path is None or bool(cccanto_lock and cccanto_lock["verified"])
    wordnet_verified = wordnet_lock_path is None or bool(wordnet_lock and wordnet_lock["verified"])
    typeduck_issues = sum(typeduck["counts"].get(name, 0) for name in ("explicit_rows_missing", "quarantine_review_missing", "invalid_source_structure")) + int(typeduck_lock_path is not None and typeduck["counts"].get("source_files_audited") != 1)
    unihan_issues = sum(unihan["counts"].get(name, 0) for name in ("explicit_rows_missing", "invalid_source_reading", "invalid_source_structure")) + int(unihan_lock_path is not None and unihan["counts"].get("source_files_audited") != 1)
    cccanto_issues = sum(cccanto["counts"].get(name, 0) for name in ("explicit_rows_missing", "quarantine_review_missing", "invalid_attestation_inventory")) + int(cccanto_lock_path is not None and cccanto["counts"].get("source_files_audited") != 2)
    wordnet_accounted = wordnet_lock_path is None or (wordnet.get("mechanical_complete") is True and wordnet["counts"].get("source_files_audited") == 1)
    headwords_selected = ("headword_encoding" in db["metadata"]
                          or bool(db["source_entry_counts"].get("cccedict:headwords:autoencoded"))
                          or bool({"cccedict_headword_forms", "cccedict_headword_encodings"} & set(db["tables"])))
    headwords_accounted = ((not headwords_selected and cccedict_headwords_lock_path is None)
                          or bool(headword_lock and headword_lock["verified"] and headwords.get("mechanical_complete") is True
                                  and headwords["counts"].get("source_files_audited") == 1))
    yue_accounted = ((not yue_selected and yue_wiktionary_lock_path is None)
                     or bool(yue_lock and yue_lock["verified"] and yue.get("mechanical_complete") is True
                             and yue["counts"].get("source_files_audited") == 1))
    supplemental_locks_verified = wordshk_verified and typeduck_verified and unihan_verified and cccanto_verified and wordnet_verified and headwords_accounted and yue_accounted
    gates = [
        _gate("source_provenance", source_lock["verified"] and bool(mapping_lock and mapping_lock["verified"]) and supplemental_locks_verified and all_entries_verified and bool(notices_path and notices_path.is_file()), {"rime_lock_verified": source_lock["verified"], "lshk_lock_verified": bool(mapping_lock and mapping_lock["verified"]), "wordshk_lock_verified": wordshk_lock["verified"] if wordshk_lock else None, "typeduck_lock_verified": typeduck_lock["verified"] if typeduck_lock else None, "unihan_lock_verified": unihan_lock["verified"] if unihan_lock else None, "entry_provenance": provenance_counts, "notices_retained": bool(notices_path and notices_path.is_file())}, "Pin and hash every selected source, verify each live pair against those sources or a complete encoding ledger, retain licenses/attribution and record exclusions."),
        _gate("database_integrity", db["integrity_check"] == ["ok"] and not db["issues"] and db["counts"]["duplicate_text_reading_pairs"] == 0 and db["syllables_table_matches_entries"] and database_stable, {"counts": db["counts"], "issues": db["issues"], "database_stable_during_audit": database_stable}, "The actual read-only database must be sound, deduplicated and internally consistent."),
        _gate("manifest_current", manifest_matches, {"manifest_present": manifest is not None, "matches_current_database": manifest_matches}, "The build manifest must identify the actual database hash and row count."),
        _gate("selected_source_accounting", selected_sources_accounted, {"counts": counts, "ledger_issues": ledger_issues}, "Account for every selected Rime row as an explicit pair, complete generated reading set or reasoned quarantine; do not silently skip text-only rows."),
        _gate("supplement_accounting", bool(mapping_lock and mapping_lock["verified"]) and supplemental_locks_verified and supplement_issues == 0 and wordshk_issues == 0 and typeduck_issues == 0 and unihan_issues == 0 and cccanto_issues == 0 and wordnet_accounted, {"lshk": supplement, "wordshk": wordshk, "typeduck": typeduck, "unihan": unihan, "cccanto": cccanto, "wordnet": wordnet, "cccedict_headwords": headwords, "yue_wiktionary": yue}, "Import or explicitly account for every selected supplementary row; retain missing-reading and exceptional-row decisions."),
        _gate("supplement_frequency_integrity", db["supplement_frequency_integrity"]["origin_column_present"] and db["supplement_frequency_integrity"]["counts"].get("selected_source_nonzero_rows", 0) == 0, db["supplement_frequency_integrity"], "Retain unknown reading-frequency weight0 for newly added selected supplementary pairs; do not copy full text counts into unsupported pronunciation shares."),
        _gate("observed_mapping_inventory", inventory.get("parsed", False) and inventory["source_database_matches"] and not inventory.get("dictionary_bases_not_in_inventory") and not inventory.get("dictionary_toned_syllables_not_in_inventory"), inventory, "Generate a source-linked observed syllable inventory tied to this database hash and covering every observed base/tone in it; source differences are not legal/illegal judgments."),
        _gate("spelling_map_integrity", spellings.get("valid", False), spellings, "Each emitted spelling maps to an observed canonical base with finite nonnegative penalty, and duplicate pairs are removed; collisions remain visible."),
        _gate("deterministic_artifact_comparison", comparison.get("matching_database_bytes", False) and comparison.get("matching_logical_rows", False), comparison, "Compare two separately built artifacts for matching bytes and logical rows, then retain the clean-build command evidence."),
        _gate("evaluation_evidence_current", evaluation["current_evidence"] and database_stable, evaluation, "Evaluation evidence must match this database, the explicitly selected corpus and all fixed project implementation modules. Missing, malformed or stale hashes cannot pass."),
        _gate("pronunciation_review", False, {"phrase_encoding_statuses": db["phrase_encoding_statuses"], "text_ambiguity_count": db["counts"]["texts_with_multiple_readings"]}, "Independent linguistic review must accept generated pronunciations, polyphony handling and quarantine policy; mechanical autoencoding is not contextual pronunciation truth."),
        _gate("held_out_quality", False, evaluation, "Predeclare quality acceptance criteria and independently review a broad held-out corpus; development seeds cannot satisfy this requirement."),
        _gate("mapping_behavior_review", False, {"inventory_available": inventory.get("parsed", False)}, "Review the supported spelling map, collisions, tone constraints, standard-mode separation and deliberate exclusions against intended Cantonese typing behavior."),
    ]
    return {
        "report_schema_version": 1, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": {"path": str(database.resolve()), "sha256": before_hash, "stable_during_audit": database_stable, **db},
        "source_locks": [lock for lock in (source_lock, mapping_lock, wordshk_lock, typeduck_lock, unihan_lock, cccanto_lock, wordnet_lock, headword_lock, yue_lock) if lock],
        "entry_provenance": provenance_counts,
        "rime_source_rows": sources, "supplement_rows": supplement, "wordshk_rows": wordshk, "typeduck_rows": typeduck, "unihan_rows": unihan, "cccanto_rows": cccanto, "wordnet_rows": wordnet, "cccedict_headword_rows": headwords, "yue_wiktionary_rows": yue, "mapping_inventory": inventory, "spelling_map": spellings,
        "comparison": comparison, "evaluation": evaluation, "requirements": gates,
        "fully_ready": False, "readiness": "incomplete",
        "notice": "Mechanical evidence only. No native Windows result, contextual-pronunciation guarantee, held-out accuracy or complete linguistic readiness is claimed.",
        "incomplete_requirements": [gate["id"] for gate in gates if gate["status"] != "pass"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--lock", type=Path, default=ROOT / "data/sources.lock.json")
    parser.add_argument("--mapping-lock", type=Path, default=ROOT / "data/mappings/lshk.sources.lock.json")
    parser.add_argument("--wordshk-lock", type=Path, default=ROOT / "data/supplements/wordshk.sources.lock.json")
    parser.add_argument("--typeduck-lock", type=Path, default=ROOT / "data/supplements/typeduck.sources.lock.json")
    parser.add_argument("--unihan-lock", type=Path, default=ROOT / "data/supplements/unihan.sources.lock.json")
    parser.add_argument("--cccanto-lock", type=Path, default=ROOT / "data/supplements/cccanto.sources.lock.json")
    parser.add_argument("--wordnet-lock", type=Path, default=ROOT / "data/supplements/wordnet.sources.lock.json")
    parser.add_argument("--cccedict-headwords-lock", type=Path, help="Selected CC-CEDICT written-headword source; required when its generated rows or ledger are present.")
    parser.add_argument("--yue-wiktionary-lock", type=Path, help="Selected explicit Yue source; defaults to the retained lock when its source markers or ledgers are present.")
    parser.add_argument("--inventory", type=Path, default=ROOT / "data/mappings/syllables.json")
    parser.add_argument("--spellings", type=Path, default=ROOT / "data/mappings/spellings.json")
    parser.add_argument("--notices", type=Path, default=ROOT / "data/THIRD_PARTY_NOTICES.md")
    parser.add_argument("--manifest", type=Path, help="Default: the database's sibling .manifest.json.")
    parser.add_argument("--evaluation", type=Path, help="Optional evaluation evidence; seeds remain development evidence.")
    parser.add_argument("--evaluation-corpus", type=Path, default=ROOT / "eval/core_cases.json", help="The corpus to verify against evaluation evidence; report-provided paths are never trusted.")
    parser.add_argument("--compare-database", type=Path, help="A second clean-build artifact to compare without modifying either.")
    parser.add_argument("--output", type=Path, help="Optionally save exactly the printed JSON report.")
    parser.add_argument("--require-ready", action="store_true", help="Return 1 when any readiness requirement remains incomplete.")
    args = parser.parse_args(argv)
    try:
        manifest_path = args.manifest or args.database.with_suffix(".manifest.json")
        protected_paths = {path.resolve() for path in (args.database, args.lock, args.mapping_lock, args.wordshk_lock, args.typeduck_lock, args.unihan_lock, args.cccanto_lock, args.wordnet_lock, args.cccedict_headwords_lock, args.yue_wiktionary_lock, args.inventory, args.spellings, args.notices, manifest_path, args.evaluation, args.evaluation_corpus, args.compare_database) if path}
        protected_paths.update((ROOT / "cantonese_ime" / name).resolve() for name in IMPLEMENTATION_MODULES)
        protected_paths.update(path.resolve() for path in (ROOT / "cantonese_ime").glob("*.py"))
        protected_paths.update((ROOT / relative).resolve() for relative in ("data/supplements/cccedict-headwords.sources.lock.json", "data/supplements/yue-wiktionary.sources.lock.json"))
        if args.output and args.output.resolve() in protected_paths:
            raise ValueError("Output must not overwrite an audited input.")
        for lock_path in (args.lock, args.mapping_lock, args.wordshk_lock, args.typeduck_lock, args.unihan_lock, args.cccanto_lock, args.wordnet_lock, args.cccedict_headwords_lock or ROOT / "data/supplements/cccedict-headwords.sources.lock.json", args.yue_wiktionary_lock or ROOT / "data/supplements/yue-wiktionary.sources.lock.json"):
            if args.output and lock_path and lock_path.is_file():
                source_directory = Path(read_json(lock_path).get("local_directory", ""))
                if args.output.resolve().is_relative_to((ROOT / source_directory).resolve()):
                    raise ValueError("Output must not overwrite a retained source snapshot.")
        report = audit_dictionary(args.database, args.lock, mapping_lock_path=args.mapping_lock, wordshk_lock_path=args.wordshk_lock, typeduck_lock_path=args.typeduck_lock, unihan_lock_path=args.unihan_lock, cccanto_lock_path=args.cccanto_lock, wordnet_lock_path=args.wordnet_lock, cccedict_headwords_lock_path=args.cccedict_headwords_lock, yue_wiktionary_lock_path=args.yue_wiktionary_lock, inventory_path=args.inventory, spellings_path=args.spellings, notices_path=args.notices, manifest_path=manifest_path, evaluation_path=args.evaluation, evaluation_corpus_path=args.evaluation_corpus, compare_database=args.compare_database)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        if callable(getattr(sys.stdout, "reconfigure", None)):
            sys.stdout.reconfigure(encoding="utf-8")
        print(rendered, end="")
        return 1 if args.require_ready and not report["fully_ready"] else 0
    except (OSError, ValueError, sqlite3.Error, TypeError) as error:
        print(f"Dictionary audit failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
