"""Build a separate append-only vocabulary candidate; never replace live data."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime.dictionary import file_sha256

SOURCE = "wordnet:cantown"
BASELINE_SHA256 = "3fccc5bcf45cbb676b8a1a51e2030d418803af64b3cd5c0ae7d67cf90a4711bb"
FIELDS = "text,reading,base_reading,compact,syllable_count,weight,source,origin"


def build_candidate(baseline: Path, output: Path, entries, *, expected_baseline_sha256: str, evidence: dict, review_rows: list, validate_sources=None) -> dict:
    baseline, output = baseline.resolve(), output.resolve()
    manifest = output.with_suffix(".manifest.json")
    review_path = output.with_suffix(".review.json")
    if baseline == output or any(path.exists() for path in (output, manifest, review_path)):
        raise ValueError("Candidate outputs must be new, separate files")
    baseline_hash = file_sha256(baseline)
    if baseline_hash != expected_baseline_sha256:
        raise ValueError("Candidate baseline hash differs from the requested snapshot")
    if validate_sources is not None:
        validate_sources()
    unique = {}
    for entry in entries:
        if entry.weight != 0 or entry.source != SOURCE:
            raise ValueError("Candidate entries must retain the Wordnet source and unknown-frequency zero weight")
        key = entry.text, entry.reading
        if key in unique:
            raise ValueError("Importer must explicitly account for duplicate pairs before candidate construction")
        unique[key] = entry
    if not unique:
        raise ValueError("No explicit Wordnet pairs to measure")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        with closing(sqlite3.connect(baseline.as_uri() + "?mode=ro", uri=True)) as source:
            source.execute("PRAGMA query_only=ON")
            with closing(sqlite3.connect(temporary)) as target:
                source.backup(target)
                before = target.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
                old_metadata = dict(target.execute("SELECT key,value FROM metadata"))
                bases = {row[0] for row in target.execute("SELECT base FROM syllables")}
                added, new_texts = [], set()
                for key, entry in sorted(unique.items()):
                    if set(entry.base_reading.split()) - bases:
                        raise ValueError("Candidate introduces a base outside the frozen baseline inventory")
                    if target.execute("SELECT 1 FROM entries WHERE text=? AND reading=?", key).fetchone():
                        continue
                    if not target.execute("SELECT 1 FROM entries WHERE text=? LIMIT 1", (entry.text,)).fetchone():
                        new_texts.add(entry.text)
                    target.execute(f"INSERT INTO entries({FIELDS}) VALUES (?,?,?,?,?,?,?,?)", (
                        entry.text, entry.reading, entry.base_reading, entry.compact,
                        entry.syllable_count, 0.0, SOURCE, "supplement"))
                    added.append({"text": entry.text, "reading": entry.reading})
                after = target.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
                if after != (before[0] + len(added), before[1] + len(new_texts)):
                    raise ValueError("Candidate row/text accounting differs")
                # Preserve original build metadata as a namespaced snapshot, so
                # its earlier counts are never mistaken for a fresh full build.
                metadata = {"schema_version": 2, "entry_count": after[0], "distinct_texts": after[1],
                    "combined_data_license": "CC-BY-SA-4.0",
                    "candidate_scope": "Separate append-only Wordnet extension; no re-encoding, existing-pair replacement, canonical build publication, installation or linguistic approval.",
                    "baseline_sha256": baseline_hash, "baseline_metadata": old_metadata,
                    "wordnet_evidence": evidence, "added_pairs": len(added), "new_texts": len(new_texts)}
                target.execute("DELETE FROM metadata")
                target.executemany("INSERT INTO metadata VALUES (?,?)", (
                    (key, json.dumps(value, ensure_ascii=False, sort_keys=True)) for key, value in sorted(metadata.items())))
                target.commit()
                if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("Candidate database integrity check failed")
                # Full field comparison catches replacement or weight changes,
                # including rows not represented in the new vocabulary cohort.
                source_rows = source.execute(f"SELECT {FIELDS} FROM entries ORDER BY text,reading")
                for row in source_rows:
                    actual = target.execute(f"SELECT {FIELDS} FROM entries WHERE text=? AND reading=?", row[:2]).fetchone()
                    if actual != row:
                        raise ValueError("Candidate changed an earlier stored pair")
        if file_sha256(baseline) != baseline_hash:
            raise ValueError("Baseline changed during candidate construction")
        if validate_sources is not None:
            validate_sources()
        report = {**metadata, "database_sha256": file_sha256(temporary),
                  "baseline_pairs": before[0], "baseline_texts": before[1],
                  "accepted_source_pairs": len(unique), "overlapping_pairs": len(unique) - len(added),
                  "baseline_pairs_preserved_with_fields": before[0],
                  "added_entries": added, "review_records": len(review_rows),
                  "data_notice": ["data/DATA_LICENSE.md", "data/THIRD_PARTY_NOTICES.md", *evidence.get("source_notices", [])],
                  "native_or_installed_state_changed": False}
        review_path.write_text(json.dumps({"candidate_only": True, "linguistic_approval": False,
            "source_evidence": evidence, "rows": review_rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)
        return report
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--baseline-sha256", default=BASELINE_SHA256)
    parser.add_argument("--source-lock", type=Path, default=ROOT / "data/supplements/wordnet.sources.lock.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/wordnet-candidate/lexicon.sqlite3")
    args = parser.parse_args()
    relative = args.output.resolve().relative_to(ROOT / ".local/wordnet-candidate")
    if not relative.parts or args.output.suffix != ".sqlite3":
        parser.error("Candidate output must be a new SQLite file under .local/wordnet-candidate")
    from cantonese_ime.wordnet import read_wordnet_entries, verify_wordnet_snapshot
    lock_hash = file_sha256(args.source_lock)
    lock = json.loads(args.source_lock.read_text("utf-8"))
    directory = ROOT / lock["local_directory"]
    verify_wordnet_snapshot(directory, lock)
    frozen = {"lock": lock_hash, "parser": file_sha256(ROOT / "cantonese_ime/wordnet.py"),
              "builder": file_sha256(Path(__file__))}

    def verify_inputs():
        current = {"lock": file_sha256(args.source_lock), "parser": file_sha256(ROOT / "cantonese_ime/wordnet.py"),
                   "builder": file_sha256(Path(__file__))}
        if current != frozen:
            raise ValueError("Wordnet source lock or implementation changed during candidate construction")
        verify_wordnet_snapshot(directory, lock)

    stats, review = {}, []
    entries = list(read_wordnet_entries(directory / "cantown.xml", stats=stats, review_rows=review))
    evidence = {"lock_sha256": lock_hash, "source_lock": str(args.source_lock), "source_commit": lock["commit"],
                "parser_sha256": frozen["parser"],
                "candidate_builder_sha256": frozen["builder"], "source_stats": stats,
                "source_notices": [lock["local_directory"] + "/" + name for name in
                                   ("ATTRIBUTION.md", "LICENSE-CC-BY-4.0.txt", "README.md")]}
    result = build_candidate(args.baseline, args.output, entries,
        expected_baseline_sha256=args.baseline_sha256, evidence=evidence, review_rows=review,
        validate_sources=verify_inputs)
    print(json.dumps({key: value for key, value in result.items() if key not in {"baseline_metadata", "added_entries"}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
