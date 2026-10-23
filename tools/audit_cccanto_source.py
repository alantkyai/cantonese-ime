"""Measure pinned CC-Canto lexical coverage without changing the dictionary."""
from __future__ import annotations
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime.cccanto import read_cccanto_entries, verify_cccanto_snapshot
from cantonese_ime.dictionary import file_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/cccanto-data-audit.json")
    parser.add_argument("--review-output", type=Path, default=ROOT / "data/review-cccanto/source_exceptions.json")
    args = parser.parse_args()
    lock_path = ROOT / "data/supplements/cccanto.sources.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    directory = ROOT / lock["local_directory"]
    verify_cccanto_snapshot(directory, lock)
    database = args.database.resolve()
    before = file_sha256(database)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        known = set(db.execute("SELECT text,reading FROM entries"))
    known_texts = {text for text, _ in known}
    sources, reviews, combined = {}, [], set()
    raw_pattern = re.compile(r"^(\S+)\s+(\S+)\s+\[[^\[\]]*\]\s+\{([^{}]*)\}(?:\s+/.*)?$")
    for filename in ("cccanto-webdist.txt", "cccedict-canto-readings-150923.txt"):
        stats, review = {}, []
        entries = list(read_cccanto_entries(directory / filename, stats=stats, review_rows=review))
        pairs = {(entry.text, entry.reading) for entry in entries}
        assert stats["input_rows"] == stats["accepted_rows"] + stats.get("quarantined_rows", 0)
        assert stats["form_candidates"] == len(pairs) + stats.get("duplicate_entries", 0) + stats.get("quarantined_forms", 0)
        traditional, simplified = set(), set()
        for raw in (directory / filename).read_text(encoding="utf-8-sig").splitlines():
            match = raw_pattern.fullmatch(raw)
            if match:
                trad, simp, reading = match.groups()
                reading = " ".join(reading.lower().split())
                if (trad, reading) in pairs:
                    traditional.add((trad, reading))
                if (simp, reading) in pairs:
                    simplified.add((simp, reading))
        new = pairs - known
        new_texts = {text for text, _ in pairs} - known_texts
        sources[filename] = {
            "sha256": file_sha256(directory / filename), "stats": stats,
            "distinct_pairs": len(pairs), "overlap_pairs": len(pairs & known),
            "new_pairs": len(new), "new_texts": len(new_texts),
            "traditional_field_new_pairs": len(traditional - known),
            "simplified_field_new_pairs": len(simplified - known),
            "traditional_new_pair_examples": [list(pair) for pair in sorted(traditional - known, key=lambda pair: (len(pair[0]), pair))[:30]],
        }
        reviews.extend(review)
        combined.update(pairs)
    report = {
        "schema_version": 1, "kind": "source-derived lexical admission and overlap audit; no linguistic approval",
        "baseline_database": {"path": str(database), "sha256": before, "pairs": len(known), "texts": len(known_texts)},
        "source_lock_sha256": file_sha256(lock_path),
        "parser_sha256": file_sha256(ROOT / "cantonese_ime/cccanto.py"),
        "audit_tool_sha256": file_sha256(Path(__file__)), "sources": sources,
        "combined": {"pairs": len(combined), "overlap_pairs": len(combined & known),
                     "new_pairs": len(combined - known), "new_texts": len({text for text, _ in combined} - known_texts),
                     "quarantine_records": len(reviews)},
        "license": "CC-BY-SA-3.0 originals; CC-BY-SA-4.0 combined transformed adaptation",
        "unknown_frequency_weight": 0, "linguistic_approval": False,
        "limits": ["No claim of all Chinese vocabulary", "Source-derived coverage is not independent held-out accuracy",
                   "Unknown bases and codepoint/syllable alignment exceptions require human review; no inferred repairs",
                   "Mandarin fields and definitions do not supply lookup readings"],
    }
    if file_sha256(database) != before:
        raise ValueError("Database changed during lexical coverage audit")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.review_output.write_text(json.dumps({"schema_version": 1, "source_lock_sha256": report["source_lock_sha256"],
                                           "parser_sha256": report["parser_sha256"], "linguistic_approval": False,
                                           "rows": reviews}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["combined"], sort_keys=True))


if __name__ == "__main__":
    main()
