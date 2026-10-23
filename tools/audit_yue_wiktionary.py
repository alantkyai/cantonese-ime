"""Independent pinned Yue XML/literal-field audit; no production reader imports.

This establishes correspondence with the declared source-field policy and its
complete ledgers. It supplies no linguistic approval or vocabulary-completeness
claim. Source-derived output retains the Yue contributors' CC-BY-SA-4.0 notice.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import bz2
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import quote
import xml.etree.ElementTree as ET

SOURCE = "wiktionary:yue"
NS = "{http://www.mediawiki.org/xml/export-0.11/}"
DATA = "yuewiktionary-20261001-pages-articles.xml.bz2"
TEMPLATES = {"yue-rom": ("模:Yue-rom", "10752", "source-template-yue-rom.wikitext"),
             "zh-pron": ("模:zh-pron", "14605", "source-template-zh-pron.wikitext"),
             "粵拼": ("模:粵拼", "9516", "source-template-jyutping.wikitext")}
BASELINE = "d835b8c4487b90ef751c8c91f467b9245c8bd54ee5be8157531dd9530ac7667b"
CALL_START = re.compile(r"\{\{\s*(zh-pron|yue-rom|粵拼)(?=[|\s}])", re.I)
BLOCK_START = re.compile(r"<!--|<(nowiki|pre|source|syntaxhighlight|ref|blockquote|math|code)\b(?:[^>'\"]|'[^']*'|\"[^\"]*\")*>", re.I)
CODE = re.compile(r"[a-z]{1,12}[1-6]\Z", re.ASCII)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _value(node, tag):
    child = node.find(NS + tag)
    return child.text or "" if child is not None else ""


def _han(text):
    return bool(text) and all(char == "〇" or unicodedata.name(char, "").startswith(
        ("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-")) for char in text)


def _visibility(text):
    """Mask inert source regions, retaining original character/line positions."""
    intervals = []
    cursor = 0
    while match := BLOCK_START.search(text, cursor):
        start = match.start()
        if match.group(0) == "<!--":
            closing = text.find("-->", match.end())
            end, kind = (len(text) if closing < 0 else closing + 3), "comment"
        else:
            kind = match.group(1).lower()
            end = match.end()
            if not match.group(0).rstrip().endswith("/>"):
                depth = 1
                tags = re.compile(r"</?" + re.escape(kind) + r"\b(?:[^>'\"]|'[^']*'|\"[^\"]*\")*>", re.I)
                for tag in tags.finditer(text, match.end()):
                    if tag.group(0).startswith("</"):
                        depth -= 1
                    elif not tag.group(0).rstrip().endswith("/>"):
                        depth += 1
                    if not depth:
                        end = tag.end()
                        break
                else:
                    end = len(text)
        intervals.append((start, end, kind))
        cursor = end
    visible = list(text)
    for start, end, _ in intervals:
        for position in range(start, end):
            if visible[position] not in "\r\n":
                visible[position] = " "
    return "".join(visible), intervals


def _brace_spans(text):
    """Locate double-brace calls with a stack for both calls and parameters."""
    opens, result = [], {}
    position = 0
    while position < len(text):
        if text.startswith("{{{", position):
            opens.append((3, position, len(opens)))
            position += 3
        elif text.startswith("{{", position):
            opens.append((2, position, len(opens)))
            position += 2
        elif opens and text.startswith("}" * opens[-1][0], position):
            width, start, nesting = opens.pop()
            position += width
            if width == 2:
                result[start] = (position, nesting)
        else:
            position += 1
    return result


def _page_problem(page, revision):
    page_tags = {"title", "ns", "id", "redirect", "revision", "restrictions"}
    revision_tags = {"id", "parentid", "timestamp", "contributor", "minor", "comment", "origin", "model", "format", "text", "sha1"}
    if any(child.tag.removeprefix(NS) not in page_tags for child in page):
        return "unsupported_page_structure"
    if revision is None:
        return "unsupported_revision_count"
    if any(child.tag.removeprefix(NS) not in revision_tags for child in revision):
        return "unsupported_revision_structure"
    required = ("id", "text", "timestamp", "model", "format")
    identity = _value(revision, "id")
    if any(len(revision.findall(NS + key)) != 1 for key in required) or not identity.isascii() or not identity.isdecimal():
        return "unsupported_revision_metadata"
    if (_value(revision, "model") != "wikitext" or _value(revision, "format") != "text/x-wiki"
            or revision.find(NS + "text").get("deleted") is not None):
        return "unsupported_revision_content"
    try:
        if datetime.fromisoformat(_value(revision, "timestamp").replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
    except ValueError:
        return "unsupported_revision_timestamp"
    return None


def _arguments(name, arguments):
    """Read literal argument fields; this does not execute source templates."""
    extra_fields = []
    if name == "zh-pron":
        fields = [(index, value.split("=", 1)[1]) for index, value in enumerate(arguments, 1)
                  if "=" in value and value.split("=", 1)[0].strip() == "c"]
        if len(fields) != 1:
            return [], "unsupported_no_unique_c_parameter", fields
        index, value = fields[0]
        return [(variant, {"parameter_ordinal": index}) for variant in value.split(",")], None, extra_fields
    if name == "yue-rom":
        if not arguments or "=" in arguments[0] or any("=" not in value for value in arguments[1:]):
            return [], "unsupported_yue_rom_argument_shape", extra_fields
        if any(value.split("=", 1)[0].strip() != "count" for value in arguments[1:]):
            return [], "unsupported_yue_rom_named_parameter", extra_fields
        return [(variant, {"parameter_ordinal": 1}) for variant in arguments[0].split(",")], None, extra_fields
    if not 2 <= len(arguments) <= 32 or len(arguments) % 2 or any("=" in value for value in arguments):
        return [], "unsupported_paired_argument_shape", extra_fields
    syllables = []
    tone_digits = dict(zip("¹²³⁴⁵⁶", "123456"))
    for index in range(0, len(arguments), 2):
        base, display = arguments[index].strip().lower(), arguments[index + 1].strip().lower()
        code = "".join(tone_digits.get(char, char) for char in display)
        if not CODE.fullmatch(code) or base != code[:-1]:
            return [], "unverified_display_or_index_mismatch", extra_fields
        syllables.append(code)
    return [(" ".join(arguments[1::2]), {"canonical_pair_sequence": " ".join(syllables),
        "unicode_tone_conversion": any(char in tone_digits for value in arguments[1::2] for char in value)})], None, extra_fields


def _parse_pages(document, archive_hash, xml_hash, bases, template_valid):
    """Independently derive the complete source occurrence ledgers."""
    expected = {key: [] for key in ("pages", "sections", "fields", "review")}
    pairs = set()
    counts = Counter()
    heading_pattern = re.compile(r"^==([^=\n].*?)==[ \t]*\r?$", re.M)
    for page in document.findall(NS + "page"):
        title, page_id, namespace = (_value(page, name) for name in ("title", "id", "ns"))
        revisions = page.findall(NS + "revision")
        revision = revisions[0] if len(revisions) == 1 else None
        revision_id = _value(revision, "id") if revision is not None else None
        info = {"source": SOURCE, "source_file": DATA, "source_sha256": archive_hash, "xml_sha256": xml_hash,
            "text": title, "page_id": page_id, "namespace": namespace, "revision_id": revision_id,
            "revision_timestamp": _value(revision, "timestamp") if revision is not None else None,
            "page_url": "https://yue.wiktionary.org/wiki/" + quote(title),
            "revision_url": "https://yue.wiktionary.org/w/index.php?oldid=" + revision_id if revision_id else None,
            "history_url": "https://yue.wiktionary.org/w/index.php?title=" + quote(title) + "&action=history"}
        page_record = dict(info)
        expected["pages"].append(page_record)
        if namespace != "0":
            page_record["status"] = "excluded_non_main_namespace"
            continue
        problem = _page_problem(page, revision)
        if problem:
            page_record["status"] = problem
            expected["review"].append(dict(info, scope="page", status="quarantined", reason=problem,
                                           revision_ids=[_value(item, "id") for item in revisions]))
            continue
        if page.find(NS + "redirect") is not None:
            page_record["status"] = "excluded_redirect"
            continue
        text = _value(revision, "text")
        info["wikitext_sha256"] = _sha(text.encode("utf-8"))
        page_record["wikitext_sha256"] = info["wikitext_sha256"]
        visible, inert = _visibility(text)
        headings = list(heading_pattern.finditer(visible))
        sections = [(0, 0, headings[0].start() if headings else len(text), "", False)]
        for index, heading in enumerate(headings):
            raw_heading = text[heading.start(1):heading.end(1)]
            selected = re.fullmatch(r"\s*\{\{langue\|yue\}\}\s*", raw_heading, re.I) is not None
            sections.append((heading.start(), heading.end(), headings[index + 1].start() if index + 1 < len(headings) else len(text), raw_heading, selected))
        page_record.update(status="selected_yue_section" if any(row[4] for row in sections) else "excluded_no_supported_yue_section",
                           selected_yue_sections=sum(row[4] for row in sections), level2_sections=len(headings))
        spans = _brace_spans(visible)
        ordinals, active_calls = Counter(), Counter()
        section_index = 0
        for match in CALL_START.finditer(text):
            start, name = match.start(), match.group(1).lower()
            while section_index + 1 < len(sections) and sections[section_index + 1][0] <= start:
                section_index += 1
            _, body_start, section_end, _, selected = sections[section_index]
            ordinals[section_index] += 1
            event = dict(info, scope="call", language_section_ordinal=section_index,
                template_ordinal=ordinals[section_index], template=name, source_line=text.count("\n", 0, start) + 1,
                source_character_offset=start)
            region = next((row for row in inert if row[0] <= start < row[1]), None)
            if region:
                reason = "excluded_" + region[2]
                rejected = dict(event, status=reason, reason=reason)
                expected["fields"].append(rejected)
                expected["review"].append(dict(rejected))
                continue
            if not selected or start < body_start:
                expected["fields"].append(dict(event, status="excluded_non_yue_language_context", reason="excluded_non_yue_language_context"))
                continue
            active_calls[section_index] += 1
            end, depth = spans.get(start, (None, 0))
            reason = None
            if end is None or end > section_end:
                reason = "unsupported_unclosed_or_cross_section_template"
            elif end - start > 32000:
                reason = "unsupported_oversized_template"
            elif depth or not re.fullmatch(r"[ \t:]*", visible[visible.rfind("\n", 0, start) + 1:start]):
                reason = "unsupported_nested_or_non_line_leading_template"
            elif any(left < end and right > start for left, right, _ in inert):
                reason = "unsupported_comment_or_protected_content"
            elif any(char in "{}" for char in text[start + 2:end - 2]):
                reason = "unsupported_nested_or_non_line_leading_template"
            elif not template_valid[name]:
                reason = "unsupported_template_revision"
            if end is not None:
                event.update(source_end_character_offset=end, raw_call_sha256=_sha(text[start:end].encode("utf-8")))
            if reason:
                rejected = dict(event, status="quarantined", reason=reason)
                expected["fields"].append(rejected)
                expected["review"].append(dict(rejected))
                continue
            inner = text[start + 2:end - 2]
            arguments = inner.split("|", 1)[1].split("|") if "|" in inner else []
            event["raw_arguments"] = arguments
            variants, reason, repeated = _arguments(name, arguments)
            for index, raw in repeated:
                rejected = dict(event, scope="parameter", parameter_ordinal=index, raw_reading=raw,
                    status="quarantined", reason=reason)
                expected["fields"].append(rejected)
                expected["review"].append(dict(rejected))
            if reason:
                rejected = dict(event, status="quarantined", reason=reason)
                expected["fields"].append(rejected)
                expected["review"].append(dict(rejected))
                continue
            expected["fields"].append(dict(event, status="parsed_call", examined_variants=len(variants)))
            for ordinal, (raw, extra) in enumerate(variants, 1):
                reading = extra.get("canonical_pair_sequence", " ".join(raw.lower().split()))
                tokens = reading.split()
                unknown = sorted({token[:-1] for token in tokens} - bases)
                if not tokens or any(not CODE.fullmatch(token) for token in tokens):
                    reason = "syntax_or_marked_notation"
                elif unknown:
                    reason = "unknown_base"
                elif not _han(title):
                    reason = "non_han_headword"
                elif len(title) != len(tokens):
                    reason = "unaligned_headword"
                else:
                    reason = None
                variant = dict(event, scope="variant", variant_ordinal=ordinal, raw_reading=raw,
                               normalized_reading=reading, **extra)
                if reason:
                    variant.update(status="quarantined", reason=reason)
                    if reason == "unknown_base":
                        variant["unknown_bases"] = unknown
                    expected["fields"].append(variant)
                    expected["review"].append(dict(variant))
                else:
                    pair = title, reading
                    variant["status"] = "duplicate_pair" if pair in pairs else "admitted_pair"
                    expected["fields"].append(variant)
                    pairs.add(pair)
        for ordinal, (start, body_start, end, heading, selected) in enumerate(sections):
            section = dict(info, scope="section", language_section_ordinal=ordinal, raw_heading=heading,
                source_character_offset=start, body_character_offset=body_start, source_end_character_offset=end,
                source_line=text.count("\n", 0, start) + 1, kind="preamble" if not ordinal else "level2",
                selected_yue=selected, recognized_active_calls=active_calls[ordinal],
                status="selected_yue_section" if selected else "excluded_non_yue_language_section")
            expected["sections"].append(section)
            if selected and not active_calls[ordinal]:
                rejected = dict(section, status="quarantined", reason="missing_supported_pronunciation_field")
                expected["fields"].append(rejected)
                expected["review"].append(dict(rejected))
    for row in expected["fields"]:
        counts[row["scope"] + ":" + row["status"]] += 1
    return {"pairs": pairs, "ledgers": expected, "field_status_counts": dict(counts)}


def _read_locked_source(lock_audit):
    if not lock_audit or lock_audit.get("verified") is not True:
        raise ValueError("Yue source lock is not verified")
    directory = Path(lock_audit["source_directory"]).resolve()
    lock_path = Path(lock_audit["path"]).resolve()
    lock_bytes = lock_path.read_bytes()
    if _sha(lock_bytes) != lock_audit.get("sha256"):
        raise ValueError("Yue source lock changed")
    lock = json.loads(lock_bytes)
    if (lock.get("source_id") != SOURCE or lock.get("schema_version") != 1
            or lock.get("license") != "CC-BY-SA-4.0"
            or lock.get("license_url") != "https://creativecommons.org/licenses/by-sa/4.0/"
            or lock.get("data_file") != DATA
            or lock.get("wiki_database") != "yuewiktionary" or lock.get("wiki_language") != "yue"
            or lock.get("xml_export_version") != "0.11"):
        raise ValueError("Unexpected Yue lock identity/license/export policy")
    records = lock.get("files", [])
    by_name = {row["name"]: row for row in records}
    audited = {row["name"]: row for row in lock_audit.get("files", [])}
    if len(by_name) != len(records) or len(audited) != len(lock_audit.get("files", [])) or set(by_name) != set(audited):
        raise ValueError("Missing/duplicate retained source records")
    payloads = {}
    for name, record in by_name.items():
        path = directory / name
        if (not path.resolve().is_relative_to(directory) or Path(name).is_absolute()
                or audited[name].get("matches_lock") is not True or path.stat().st_size > 8_000_000):
            raise ValueError("Invalid bounded locked file: " + name)
        payload = path.read_bytes()
        if _sha(payload) != record.get("sha256") or len(payload) != record.get("size_bytes"):
            raise ValueError("Retained source bytes changed: " + name)
        payloads[name] = payload
    required = {DATA, "parser-attested-bases.json", "yue-20261001-sha1sums.txt", "LICENSE-CC-BY-SA-4.0.txt",
                "ATTRIBUTION.md", *(spec[2] for spec in TEMPLATES.values())}
    if not required <= payloads.keys():
        raise ValueError("Required retained source/license/template files are absent")
    archive = payloads[DATA]
    checksum_lines = [line.split() for line in payloads["yue-20261001-sha1sums.txt"].decode("ascii").splitlines()]
    checksums = [columns[0] for columns in checksum_lines if len(columns) == 2 and columns[1] == DATA]
    if len(checksums) != 1 or checksums[0] != lock.get("official_archive_sha1") or checksums[0] != hashlib.sha1(archive).hexdigest():
        raise ValueError("Official retained dump SHA1 does not match the archive")
    decoder = bz2.BZ2Decompressor()
    xml = decoder.decompress(archive, max_length=32_000_001)
    if len(xml) > 32_000_000 or not decoder.eof or decoder.unused_data:
        raise ValueError("Oversized/truncated/trailing-member bzip2 source")
    if _sha(xml) != lock.get("xml_sha256") or len(xml) != lock.get("xml_size_bytes"):
        raise ValueError("Decoded XML pin mismatch")
    text = xml.decode("utf-8-sig")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
        raise ValueError("DTD/entity declarations are not accepted")
    document = ET.fromstring(text)
    if (document.tag != NS + "mediawiki" or document.get("version") != "0.11"
            or document.get("{http://www.w3.org/XML/1998/namespace}lang") != "yue"
            or len(document.findall(NS + "siteinfo")) != 1
            or _value(document.find(NS + "siteinfo"), "dbname") != "yuewiktionary"):
        raise ValueError("Unexpected MediaWiki export/site identity")
    stack, node_count = [(document, 1)], 0
    while stack:
        node, depth = stack.pop()
        node_count += 1
        if depth > 16 or node_count > 300_000 or not isinstance(node.tag, str) or not node.tag.startswith(NS):
            raise ValueError("XML structure/namespace/depth bound failed")
        stack.extend((child, depth + 1) for child in node)
    if any(child.tag not in {NS + "siteinfo", NS + "page"} for child in document):
        raise ValueError("Unexpected XML root member")
    pages = document.findall(NS + "page")
    if not 1 <= len(pages) <= 20_000 or len(pages) != lock.get("page_count"):
        raise ValueError("Page collection is empty, oversized or differs from the lock")
    identities, titles = set(), set()
    for page in pages:
        identity, title = _value(page, "id"), _value(page, "title")
        if (any(len(page.findall(NS + key)) != 1 for key in ("id", "title", "ns"))
                or not identity.isascii() or not identity.isdecimal() or not title or identity in identities or title in titles):
            raise ValueError("Invalid/duplicate page identity")
        identities.add(identity)
        titles.add(title)
        for revision in page.findall(NS + "revision"):
            for node in revision.findall(NS + "text"):
                value = (node.text or "").encode("utf-8")
                if list(node) or len(value) > 2_000_000:
                    raise ValueError("Unexpected nested/oversized revision content")
                if node.get("bytes") is not None and (not node.get("bytes").isascii() or not node.get("bytes").isdecimal() or int(node.get("bytes")) != len(value)):
                    raise ValueError("Revision byte count mismatch")
                exported = _value(revision, "sha1")
                if exported and int(exported, 36) != int(hashlib.sha1(value).hexdigest(), 16):
                    raise ValueError("Revision text SHA1 mismatch")
    template_rows = lock.get("template_revisions", [])
    by_title = {_value(page, "title"): page for page in pages}
    valid = {}
    for name, (title, revision_id, filename) in TEMPLATES.items():
        specifications = [row for row in template_rows if row.get("title") == title]
        revisions = by_title[title].findall(NS + "revision") if title in by_title else []
        if len(specifications) != 1 or len(revisions) != 1:
            raise ValueError("Missing unique source-template revision")
        spec, revision = specifications[0], revisions[0]
        revision_text = _value(revision, "text").encode("utf-8")
        valid[name] = (str(spec.get("revision_id")) == revision_id == _value(revision, "id")
            and spec.get("name") == filename and _sha(payloads[filename]) == spec.get("sha256")
            and _sha(revision_text) == spec.get("revision_text_sha256")
            and payloads[filename].replace(b"\r\n", b"\n") == revision_text)
        if not valid[name]:
            raise ValueError("Template retained bytes/revision identity differ: " + name)
    inventory = json.loads(payloads["parser-attested-bases.json"])
    bases = inventory.get("bases", [])
    attestation = lock.get("parser_attestation", {})
    if (inventory.get("schema_version") != 1 or inventory.get("base_count") != 878
            or inventory.get("baseline_database_sha256") != BASELINE
            or len(bases) != 878 or len(set(bases)) != len(bases)
            or any(not isinstance(base, str) or not re.fullmatch(r"[a-z]{1,12}", base, re.ASCII) for base in bases)
            or attestation.get("base_count") != 878 or attestation.get("baseline_database_sha256") != BASELINE
            or attestation.get("sha256") != _sha(payloads["parser-attested-bases.json"])):
        raise ValueError("Frozen 878-base admission inventory/attestation mismatch")
    return document, set(bases), valid, _sha(archive), _sha(xml), lock_path, _sha(lock_bytes), directory, by_name


def audit_yue_wiktionary(connection: sqlite3.Connection, lock_audit: dict | None,
                         verified_ids: dict[str, set[int]]) -> dict:
    keys = ("source_files_audited explicit_pairs explicit_texts all_xml_pages recognized_main_calls "
            "reading_variant_occurrences accepted_variant_occurrences explicit_rows_present explicit_rows_missing "
            "source_weight_or_origin_invalid yue_source_rows_credited overlap_rows_present "
            "overlap_rows_previously_verified overlap_rows_not_previously_verified unattested_source_rows_unexpected "
            "source_snapshot_invalid").split()
    keys += [kind + "_records_" + suffix for kind in ("pages", "sections", "fields", "review")
             for suffix in ("required", "present", "missing", "unexpected", "invalid")]
    counts = Counter({key: 0 for key in keys})
    errors, mismatches, missing_pairs = [], [], []
    pending_ids = set()

    def result():
        failures = sum(value for key, value in counts.items() if key.endswith(("_missing", "_unexpected", "_invalid")))
        complete = bool(counts["source_files_audited"] and counts["explicit_pairs"] and not errors and not failures)
        # The caller's provenance set is authoritative. Publish new ownership
        # only after the complete ledger, reverse-source and final hash checks.
        if complete:
            verified_ids.setdefault("supplement", set()).update(pending_ids)
            counts["yue_source_rows_credited"] = len(pending_ids)
        return {"counts": dict(counts), "mechanical_complete": complete, "errors": errors,
            "missing_pair_samples": missing_pairs, "ledger_mismatch_samples": mismatches,
            "notice": "Independent pinned raw XML/literal-field and complete-ledger correspondence only. Overlap rows receive no new provenance credit. No linguistic approval, source-vocabulary completeness or native typing claim."}

    if lock_audit is None:
        return result()
    try:
        document, bases, valid, archive_hash, xml_hash, lock_path, lock_hash, directory, records = _read_locked_source(lock_audit)
        parsed = _parse_pages(document, archive_hash, xml_hash, bases, valid)
        counts["source_files_audited"] = 1
        pairs = parsed["pairs"]
        counts["explicit_pairs"] = len(pairs)
        counts["explicit_texts"] = len({text for text, _ in pairs})
        counts["all_xml_pages"] = len(parsed["ledgers"]["pages"])
        counts["recognized_main_calls"] = sum(row["scope"] == "call" for row in parsed["ledgers"]["fields"])
        counts["reading_variant_occurrences"] = sum(row["scope"] == "variant" for row in parsed["ledgers"]["fields"])
        counts["accepted_variant_occurrences"] = sum(row.get("status") in {"admitted_pair", "duplicate_pair"} for row in parsed["ledgers"]["fields"])
        for key, value in parsed["field_status_counts"].items():
            counts["source_field:" + key] = value
        for kind, expected in parsed["ledgers"].items():
            table = "yue_wiktionary_" + kind
            actual = []
            try:
                columns = [row[1] for row in connection.execute("PRAGMA table_info(" + table + ")")]
                if not columns:
                    raise ValueError("Missing ledger table: " + table)
                for row in connection.execute("SELECT * FROM " + table):
                    wrapper = dict(zip(columns, row))
                    detail = json.loads(wrapper["details_json"])
                    if not isinstance(detail, dict) or wrapper["page_id"] != detail.get("page_id"):
                        raise ValueError("Ledger wrapper page_id differs")
                    for column, field in (("revision_id", "revision_id"), ("namespace", "namespace"), ("text", "text"),
                                          ("status", "status"), ("scope", "scope"), ("section_ordinal", "language_section_ordinal")):
                        if column in wrapper and wrapper[column] != detail.get(field):
                            raise ValueError("Ledger wrapper differs: " + column)
                    actual.append(detail)
            except (ValueError, TypeError, KeyError, sqlite3.Error) as exception:
                counts[kind + "_records_invalid"] += 1
                errors.append(str(exception))
            expected_counter, actual_counter = Counter(map(_canonical, expected)), Counter(map(_canonical, actual))
            missing, unexpected = expected_counter - actual_counter, actual_counter - expected_counter
            counts[kind + "_records_required"] = len(expected)
            counts[kind + "_records_present"] = sum((expected_counter & actual_counter).values())
            counts[kind + "_records_missing"] = sum(missing.values())
            counts[kind + "_records_unexpected"] = sum(unexpected.values())
            for category, difference in (("missing", missing), ("unexpected", unexpected)):
                for serialized, multiplicity in difference.items():
                    if len(mismatches) >= 12:
                        break
                    row = json.loads(serialized)
                    mismatches.append({"ledger": kind, "difference": category, "count": multiplicity,
                        **{key: row.get(key) for key in ("page_id", "scope", "language_section_ordinal", "template_ordinal", "variant_ordinal", "source_character_offset", "status", "reason")}})
        # Presence and own-source ownership are separate. Earlier-source rows
        # must retain their existing proof/weight, never receive fake Yue credit.
        for text, reading in sorted(pairs):
            rows = connection.execute("SELECT id,base_reading,weight,source,origin FROM entries WHERE text=? AND reading=?", (text, reading)).fetchall()
            if len(rows) != 1:
                counts["explicit_rows_missing"] += 1
                if len(missing_pairs) < 12:
                    missing_pairs.append({"text": text, "reading": reading})
                continue
            identity, base_reading, weight, source, origin = rows[0]
            counts["explicit_rows_present"] += 1
            if source == SOURCE:
                if origin != "supplement" or not isinstance(weight, (int, float)) or weight != 0 or base_reading != " ".join(token[:-1] for token in reading.split()):
                    counts["source_weight_or_origin_invalid"] += 1
                else:
                    pending_ids.add(identity)
            else:
                counts["overlap_rows_present"] += 1
                counts["overlap_rows_previously_verified" if identity in verified_ids.get(origin, set()) else "overlap_rows_not_previously_verified"] += 1
        for identity, text, reading, weight, origin in connection.execute("SELECT id,text,reading,weight,origin FROM entries WHERE source=?", (SOURCE,)):
            if (text, reading) not in pairs:
                counts["unattested_source_rows_unexpected"] += 1
        if _sha(lock_path.read_bytes()) != lock_hash:
            raise ValueError("Yue lock changed during source audit")
        for name, record in records.items():
            if _sha((directory / name).read_bytes()) != record["sha256"]:
                raise ValueError("Yue retained source changed during audit: " + name)
    except (ValueError, TypeError, KeyError, OSError, EOFError, sqlite3.Error, ET.ParseError) as exception:
        counts["source_snapshot_invalid"] += 1
        errors.append(str(exception))
    return result()


def _self_test():
    """Small primary-format controls plus a damaged-ledger/crediting fixture."""
    import tempfile
    import unittest
    from unittest.mock import patch

    def page(text, title="字"):
        document = ET.Element(NS + "mediawiki")
        item = ET.SubElement(document, NS + "page")
        for name, value in (("title", title), ("id", "1"), ("ns", "0")):
            ET.SubElement(item, NS + name).text = value
        revision = ET.SubElement(item, NS + "revision")
        for name, value in (("id", "2"), ("timestamp", "2026-01-01T00:00:00Z"), ("model", "wikitext"), ("format", "text/x-wiki"), ("text", text)):
            ET.SubElement(revision, NS + name).text = value
        return document

    def parsed(text, title="字"):
        return _parse_pages(page(text, title), "archive", "xml", {"zi", "gaa"}, {name: True for name in TEMPLATES})

    class Controls(unittest.TestCase):
        def test_literal_source_field_forms(self):
            for call in ("{{zh-pron|c=zi6}}", "{{Yue-rom|zi6|count=1}}", "{{粵拼|zi|zi⁶}}"):
                with self.subTest(call=call):
                    self.assertEqual(parsed("=={{langue|yue}}==\n" + call)["pairs"], {("字", "zi6")})

        def test_display_index_and_unicode_scope(self):
            for call in ("{{粵拼|gaa|zi⁶}}", "{{Yue-rom|zi⁶}}", "{{zh-pron|c=zi6-2}}", "{{粵拼|zi|zi⁹}}"):
                self.assertFalse(parsed("=={{langue|yue}}==\n" + call)["pairs"])

        def test_inert_and_other_language_fields_cannot_supply_pairs(self):
            text = "=={{langue|yue}}==\n<!--{{zh-pron|c=zi6}}-->\n<ref><ref>{{Yue-rom|zi6}}</ref></ref>\n<nowiki>{{粵拼|zi|zi⁶}}</nowiki>"
            result = parsed(text)
            self.assertFalse(result["pairs"])
            self.assertEqual(len([r for r in result["ledgers"]["fields"] if r["scope"] == "call"]), 3)
            self.assertFalse(parsed("=={{langue|zh}}==\n{{zh-pron|c=zi6}}")["pairs"])

        def test_nesting_line_prefix_cross_section_and_unclosed_are_rejected(self):
            for call in ("text {{zh-pron|c=zi6}}", "{{outer|{{zh-pron|c=zi6}}}}", "{{zh-pron|c=zi6\n=={{langue|zh}}==\n}}", "{{zh-pron|c=zi6"):
                self.assertFalse(parsed("=={{langue|yue}}==\n" + call)["pairs"])

        def test_repeated_c_fields_and_other_yue_rom_parameters_are_rejected(self):
            result = parsed("=={{langue|yue}}==\n{{zh-pron|c=zi6|c=zi2}}")
            self.assertFalse(result["pairs"])
            self.assertEqual(sum(row["scope"] == "parameter" for row in result["ledgers"]["fields"]), 2)
            self.assertFalse(parsed("=={{langue|yue}}==\n{{Yue-rom|zi6|other=x}}")["pairs"])

        def test_unknown_han_and_alignment_are_distinct_rejections(self):
            cases = (("nope1", "字", "unknown_base"), ("zi6", "A", "non_han_headword"), ("zi6 gaa1", "字", "unaligned_headword"))
            for reading, title, reason in cases:
                result = parsed("=={{langue|yue}}==\n{{Yue-rom|" + reading + "}}", title)
                variants = [row for row in result["ledgers"]["fields"] if row["scope"] == "variant"]
                self.assertEqual(variants[0]["reason"], reason)

        def test_missing_ledgers_wrong_frequency_and_unattested_rows_block_pass(self):
            text = "=={{langue|yue}}==\n{{Yue-rom|zi6}}"
            document = page(text)
            expected = parsed(text)["ledgers"]
            connection = sqlite3.connect(":memory:")
            self.addCleanup(connection.close)
            connection.executescript("""
                CREATE TABLE entries(id INTEGER PRIMARY KEY,text,reading,base_reading,weight,source,origin);
                CREATE TABLE yue_wiktionary_pages(page_id,revision_id,namespace,text,status,details_json);
                CREATE TABLE yue_wiktionary_sections(page_id,section_ordinal,details_json);
                CREATE TABLE yue_wiktionary_fields(id INTEGER PRIMARY KEY,page_id,scope,status,details_json);
                CREATE TABLE yue_wiktionary_review(id INTEGER PRIMARY KEY,page_id,scope,details_json);
            """)
            for kind, records in expected.items():
                for row in records:
                    if kind == "pages":
                        connection.execute("INSERT INTO yue_wiktionary_pages VALUES(?,?,?,?,?,?)", (*[row[key] for key in ("page_id", "revision_id", "namespace", "text", "status")], _canonical(row)))
                    elif kind == "sections":
                        connection.execute("INSERT INTO yue_wiktionary_sections VALUES(?,?,?)", (row["page_id"], row["language_section_ordinal"], _canonical(row)))
                    elif kind == "fields":
                        connection.execute("INSERT INTO yue_wiktionary_fields(page_id,scope,status,details_json) VALUES(?,?,?,?)", (row["page_id"], row["scope"], row["status"], _canonical(row)))
                    else:
                        connection.execute("INSERT INTO yue_wiktionary_review(page_id,scope,details_json) VALUES(?,?,?)", (row["page_id"], row["scope"], _canonical(row)))
            connection.execute("INSERT INTO entries VALUES(1,'字','zi6','zi',0,?,'supplement')", (SOURCE,))
            with tempfile.TemporaryDirectory(prefix="yue-audit-controls-") as temporary:
                lock_path = Path(temporary) / "lock.json"
                lock_path.write_bytes(b"{}")
                loaded = (document, {"zi", "gaa"}, {name: True for name in TEMPLATES}, "archive", "xml", lock_path, _sha(b"{}"), Path(temporary), {})
                with patch(__name__ + "._read_locked_source", return_value=loaded):
                    verified = {"supplement": set()}
                    self.assertTrue(audit_yue_wiktionary(connection, {"verified": True}, verified)["mechanical_complete"])
                    self.assertEqual(verified["supplement"], {1})
                    connection.execute("UPDATE entries SET source='earlier',origin='generated',weight=200")
                    previous = {"generated": {1}, "supplement": set()}
                    overlap = audit_yue_wiktionary(connection, {}, previous)
                    self.assertTrue(overlap["mechanical_complete"])
                    self.assertEqual(overlap["counts"]["overlap_rows_previously_verified"], 1)
                    self.assertEqual(previous["supplement"], set())
                    self.assertEqual(audit_yue_wiktionary(connection, {}, {})["counts"]["overlap_rows_not_previously_verified"], 1)
                    connection.execute("UPDATE entries SET source=?,origin='supplement',weight=0", (SOURCE,))
                    connection.execute("UPDATE entries SET weight=99")
                    self.assertFalse(audit_yue_wiktionary(connection, {}, {})["mechanical_complete"])
                    connection.execute("UPDATE entries SET weight=0")
                    connection.execute("INSERT INTO entries VALUES(2,'假','gaa1','gaa',0,?,'supplement')", (SOURCE,))
                    rejected = {"supplement": {99}}
                    failure = audit_yue_wiktionary(connection, {}, rejected)
                    self.assertFalse(failure["mechanical_complete"])
                    self.assertEqual(failure["counts"]["yue_source_rows_credited"], 0)
                    self.assertEqual(rejected["supplement"], {99})
                    connection.execute("DELETE FROM entries WHERE id=2")
                    # Simulate a late hash failure after valid rows were seen.
                    lock_path.write_bytes(b'{"changed":true}')
                    rejected = {"supplement": {99}}
                    failure = audit_yue_wiktionary(connection, {}, rejected)
                    self.assertFalse(failure["mechanical_complete"])
                    self.assertEqual(failure["counts"]["source_snapshot_invalid"], 1)
                    self.assertEqual(failure["counts"]["yue_source_rows_credited"], 0)
                    self.assertEqual(rejected["supplement"], {99})
                    lock_path.write_bytes(b"{}")
                    connection.execute("DELETE FROM yue_wiktionary_fields WHERE scope='variant'")
                    rejected = {"supplement": {99}}
                    failure = audit_yue_wiktionary(connection, {}, rejected)
                    self.assertFalse(failure["mechanical_complete"])
                    self.assertGreater(failure["counts"]["fields_records_missing"], 0)
                    self.assertEqual(failure["counts"]["yue_source_rows_credited"], 0)
                    self.assertEqual(rejected["supplement"], {99})

        def test_duplicate_occurrences_and_absent_fields_remain_accounted(self):
            result = parsed("=={{langue|yue}}==\n{{Yue-rom|zi6, zi6}}")
            self.assertEqual(result["pairs"], {("字", "zi6")})
            self.assertEqual(result["field_status_counts"]["variant:admitted_pair"], 1)
            self.assertEqual(result["field_status_counts"]["variant:duplicate_pair"], 1)
            empty = parsed("=={{langue|yue}}==\n")
            self.assertEqual(empty["ledgers"]["review"][0]["reason"], "missing_supported_pronunciation_field")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main():
    import argparse
    from contextlib import closing
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path)
    parser.add_argument("--lock", type=Path, default=Path(__file__).resolve().parents[1] / "data/supplements/yue-wiktionary.sources.lock.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return 0 if _self_test() else 1
    if args.dictionary is None:
        parser.error("dictionary is required unless self-test")
    root = Path(__file__).resolve().parents[1]
    lock_bytes = args.lock.read_bytes()
    lock = json.loads(lock_bytes)
    directory = (root / lock["local_directory"]).resolve()
    if not directory.is_relative_to(root / "data/vendor/yue-wiktionary"):
        raise ValueError("Standalone audit expects the selected project Yue vendor directory")
    files = []
    for row in lock["files"]:
        retained = (directory / row["name"]).resolve()
        if not retained.is_relative_to(directory) or retained.stat().st_size > 8_000_000:
            raise ValueError("Invalid bounded retained source file")
        payload = retained.read_bytes()
        files.append({**row, "matches_lock": _sha(payload) == row["sha256"] and len(payload) == row["size_bytes"]})
    lock_audit = {"path": str(args.lock.resolve()), "sha256": _sha(lock_bytes), "source_directory": str(directory.resolve()),
                  "files": files, "verified": all(row["matches_lock"] for row in files)}
    database_hash = _sha(args.dictionary.read_bytes())
    code_hash = _sha(Path(__file__).read_bytes())
    with closing(sqlite3.connect(args.dictionary.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        report = audit_yue_wiktionary(connection, lock_audit, {})
    if _sha(args.dictionary.read_bytes()) != database_hash or _sha(Path(__file__).read_bytes()) != code_hash:
        raise ValueError("Dictionary or auditor changed while auditing")
    report.update(database_sha256=database_hash, auditor_sha256=code_hash, source_lock_sha256=_sha(lock_bytes))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = args.output.resolve()
        relative = target.relative_to(root)
        if not relative.parts or relative.parts[0] not in {".local", "docs"} or target.suffix != ".json" or target in {args.dictionary.resolve(), args.lock.resolve()}:
            raise ValueError("Output must be a separate JSON report under docs/.local")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["mechanical_complete"] else 1


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
