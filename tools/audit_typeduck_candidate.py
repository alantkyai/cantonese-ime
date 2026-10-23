"""Read-only delta audit of the isolated, pinned TypeDuck candidate table.

This does not import data, authenticate row authorship, or approve licensing.
It preserves raw percentages without treating them as measured frequencies.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cantonese_ime.dictionary import file_sha256, read_frequencies


def audit(database: Path, lock_path: Path) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    directory = PROJECT_ROOT / lock["local_directory"]
    for record in lock["files"]:
        path = directory / record["name"]
        if path.stat().st_size != record["size_bytes"] or file_sha256(path) != record["sha256"]:
            raise ValueError(f"Candidate source hash mismatch: {path.name}")
        payload = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
        if blob != record["git_blob_sha1"]:
            raise ValueError(f"Candidate Git blob mismatch: {path.name}")
    source = directory / "jyut6ping3.dict.yaml"
    rows = []
    excluded = []
    header = []
    started = False
    for line_number, raw in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not started:
            header.append(raw)
            if raw == "...":
                started = True
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        columns = raw.split("\t")
        if len(columns) != 3 or not columns[0]:
            raise ValueError(f"Unexpected TypeDuck row shape at {line_number}")
        text, raw_reading, raw_weight = columns
        if not raw_weight.endswith("%"):
            raise ValueError(f"Unexpected non-percentage weight at {line_number}")
        percentage = float(raw_weight[:-1])
        if not math.isfinite(percentage) or percentage < 0:
            raise ValueError(f"Invalid percentage weight at {line_number}")
        reading = " ".join(raw_reading.lower().split())
        record = {"line": line_number, "text": text, "raw_reading": raw_reading,
                  "reading": reading, "raw_weight": raw_weight, "percentage": percentage}
        if not all(re.fullmatch(r"[a-z]+[1-6]", token) for token in reading.split()):
            excluded.append({**record, "reason": "Noncanonical reading syntax; source markers retained, not stripped."})
        else:
            rows.append(record)
    if not started:
        raise ValueError("Missing dictionary header terminator")
    bytext = defaultdict(list)
    for row in rows:
        bytext[row["text"]].append(row)
    pairs = {(row["text"], row["reading"]) for row in rows}
    if len(pairs) != len(rows):
        raise ValueError("Duplicate candidate pairs require an explicit audit policy")
    database_hash = file_sha256(database)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        authored = set(connection.execute("SELECT text,reading FROM entries WHERE origin IN ('explicit','supplement')"))
        live = set(connection.execute("SELECT text,reading FROM entries"))
        ledgers = list(connection.execute("SELECT source,line,text,status,codes_json FROM phrase_encodings"))
        missing_components = [row[0] for row in connection.execute(
            "SELECT DISTINCT text FROM supplement_review WHERE status='description_only' AND NOT EXISTS "
            "(SELECT 1 FROM entries WHERE entries.text=supplement_review.text AND origin IN ('explicit','supplement')) ORDER BY text")]
    rime_lock = json.loads((PROJECT_ROOT / "data/sources.lock.json").read_text(encoding="utf-8"))
    frequency_path = PROJECT_ROOT / rime_lock["local_directory"] / "essay-cantonese.txt"
    frequencies = read_frequencies(frequency_path)
    coverage = defaultdict(Counter)
    ambiguous_matches = []
    for source_name, line, text, status, codes_json in ledgers:
        coverage[status]["source_phrase_rows"] += 1
        if text not in bytext:
            continue
        codes = json.loads(codes_json)
        candidates = bytext[text]
        coverage[status]["matched_text_rows"] += 1
        coverage[status]["candidate_pairs"] += len(candidates)
        coverage[status]["same_as_recorded_generated_codes"] += sum(row["reading"] in codes for row in candidates)
        coverage[status]["outside_recorded_codes"] += sum(row["reading"] not in codes for row in candidates)
        coverage[status]["zero_percentage_candidate_pairs"] += sum(row["percentage"] == 0 for row in candidates)
        if status == "encoded_ambiguous":
            ambiguous_matches.append({"source": source_name, "line": line, "text": text,
                                      "current_ledger_codes": codes,
                                      "existing_text_frequency_for_review_priority": frequencies.get(text, 0),
                                      "typeduck_candidate_rows": candidates})
    new_pairs = pairs - live
    new_rows = [row for row in rows if (row["text"], row["reading"]) in new_pairs]
    buckets = Counter(("single_codepoint_text" if len(row["text"]) == 1 else "multiple_codepoint_text",
                       "zero_percent" if row["percentage"] == 0 else "positive_percent") for row in new_rows)
    report = {
        "schema_version": 1,
        "purpose": "Isolated candidate delta only. Explicit file rows are not independently proven human-authored or contextually correct.",
        "approved_for_live_import": False,
        "database_sha256": database_hash,
        "candidate_lock_sha256": file_sha256(lock_path),
        "audit_tool_sha256": file_sha256(Path(__file__)),
        "source_sha256": file_sha256(source),
        "review_priority_frequency_sha256": file_sha256(frequency_path),
        "header": header,
        "counts": {
            "raw_data_rows": len(rows) + len(excluded), "canonical_pairs": len(pairs),
            "unique_texts": len(bytext), "excluded_noncanonical_rows": len(excluded),
            "overlap_current_authored_pairs": len(pairs & authored),
            "absent_from_current_authored_pairs": len(pairs - authored),
            "overlap_current_live_pairs": len(pairs & live), "absent_from_current_live_pairs": len(new_pairs),
            "new_texts_vs_current_live": len(set(bytext) - {text for text, _ in live}),
            "zero_percentage_rows": sum(row["percentage"] == 0 for row in rows),
            "maximum_percentage": max(row["percentage"] for row in rows),
            "new_pair_categories": {kind + ":" + weight: count for (kind, weight), count in sorted(buckets.items())},
        },
        "phrase_ledger_coverage": {status: dict(counts) for status, counts in sorted(coverage.items())},
        "description_components_without_authored_readings": missing_components,
        "description_component_matches": {text: bytext[text] for text in missing_components if text in bytext},
        "excluded_rows": excluded,
        "ambiguous_phrase_matches": sorted(ambiguous_matches, key=lambda row: (-row["existing_text_frequency_for_review_priority"], row["text"])),
        "interpretation_limits": [
            "All three downloaded files remain unmodified candidates; no current entries or review decisions are changed.",
            "Explicit table notation differs from independently audited authorship. Export/generation and per-row source lineage remain unresolved.",
            "The repository README declares principal data CC BY 4.0, but has no per-row origin manifest. No categorical assertion of ODbL presence or absence is made.",
            "Percentages are source ranking values, some above 100; they are not imported or treated as measured reading frequencies or probabilities.",
            "Overlap with generated readings is shared output, not an independent held-out correctness result or an automatic phrase resolution.",
        ],
    }
    if file_sha256(database) != database_hash:
        raise ValueError("Database changed during candidate audit")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--lock", type=Path, default=PROJECT_ROOT / "data/candidates/typeduck.sources.lock.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/candidates/typeduck.audit.json")
    args = parser.parse_args()
    report = audit(args.database, args.lock)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output.exists() and args.output.read_text(encoding="utf-8") != payload:
        raise ValueError("Existing candidate audit is a historical snapshot; choose a new --output path to preserve it")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists():
        args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"database_sha256": report["database_sha256"], "counts": report["counts"],
                      "phrase_ledger_coverage": report["phrase_ledger_coverage"],
                      "description_component_matches": report["description_component_matches"],
                      "approved_for_live_import": False}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
