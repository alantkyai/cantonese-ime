"""Check every new Wordnet input and its competing stored texts via public lookup."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime import Engine
from cantonese_ime.mappings import yale_ascii
from tools.check_yale_catalog import NOTICE, build_catalog, file_digest, input_hashes, output_path, probe_group


def affected_groups(database: Path, manifest: dict):
    """Include existing homophones at every changed input, not only new words."""
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = list(db.execute("SELECT text,reading,base_reading,weight FROM entries WHERE source='wordnet:cantown' ORDER BY text,reading"))
    expected = {(row["text"], row["reading"]) for row in manifest["added_entries"]}
    if (not rows or len(rows) != manifest["added_pairs"] or len(expected) != len(rows)
            or {(text, reading) for text, reading, _, _ in rows} != expected
            or any(weight != 0 for _, _, _, weight in rows)):
        raise ValueError("Actual new-source cohort differs from the candidate manifest")
    inputs = {"".join(yale_ascii(base) for base in base_reading.split()) for _, _, base_reading, _ in rows}
    catalog = build_catalog(database)
    selected = tuple(group for group in catalog.groups if group.raw in inputs)
    if {group.raw for group in selected} != inputs:
        raise ValueError("New Yale input cohort is incomplete")
    return catalog, selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, default=ROOT / ".local/wordnet-candidate/lexicon.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/wordnet-candidate-yale.json")
    args = parser.parse_args()
    manifest_path = args.dictionary.with_suffix(".manifest.json")
    fixture = ROOT / "eval/yale_expected.json"
    lock_path = ROOT / "data/supplements/wordnet.sources.lock.json"
    target = output_path(args.output, suffix=".json", protected=(args.dictionary, manifest_path, fixture, lock_path))
    manifest = json.loads(manifest_path.read_text("utf-8"))

    def guarded():
        values = input_hashes(args.dictionary, fixture)
        values.update(candidate_manifest=file_digest(manifest_path), source_lock=file_digest(lock_path),
                      parser=file_digest(ROOT / "cantonese_ime/wordnet.py"),
                      candidate_builder=file_digest(ROOT / "tools/build_wordnet_candidate.py"),
                      candidate_checker=file_digest(Path(__file__)))
        return values

    hashes = guarded()
    evidence = manifest["wordnet_evidence"]
    if (hashes["dictionary"] != manifest["database_sha256"] or hashes["source_lock"] != evidence["lock_sha256"]
            or hashes["parser"] != evidence["parser_sha256"] or hashes["candidate_builder"] != evidence["candidate_builder_sha256"]):
        raise ValueError("Candidate database, source lock or implementation differs from its build evidence")
    from cantonese_ime.wordnet import verify_wordnet_snapshot
    lock = json.loads(lock_path.read_text("utf-8"))
    verify_wordnet_snapshot(ROOT / lock["local_directory"], lock)
    catalog, groups = affected_groups(args.dictionary, manifest)
    results = []
    with Engine(args.dictionary, learning_path=None, prefer_yale=True) as engine:
        for index, group in enumerate(groups, 1):
            results.append({"input": group.raw, "targets": list(group.targets),
                            "source_pairs": group.source_pairs, **probe_group(engine, group, max_pages=128)})
            if index % 250 == 0:
                print(json.dumps({"checked_groups": index, "total_groups": len(groups),
                                  "outcomes": dict(Counter(row["status"] for row in results))}), flush=True)
    if guarded() != hashes:
        raise ValueError("Candidate audit inputs changed during lookup")
    verify_wordnet_snapshot(ROOT / lock["local_directory"], lock)
    outcomes = Counter(row["status"] for row in results)
    passed = bool(groups) and outcomes["all_found"] == len(groups)
    report = {"schema_version": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_only": True, "status": "passed" if passed else "failed", "notice": NOTICE,
        "inputs_sha256": hashes, "candidate_catalog_sha256": catalog.sha256,
        "candidate_total_pairs": catalog.source_pairs, "affected_groups": len(groups),
        "required_input_text_memberships": sum(len(group.targets) for group in groups),
        "new_pairs": manifest["added_pairs"], "new_texts": manifest["new_texts"],
        "outcomes": dict(outcomes), "all_affected_target_texts_reached": passed,
        "complete_catalog_retrieval_verified": False,
        "scope": "Every newly added Wordnet pair's compact Yale input, including all candidate-database texts competing at those inputs. Other inputs are outside this cohort; full baseline audit remains separate. No linguistic, native typing, installation or all-Chinese claim.",
        "public_page_calls": sum(row["public_page_calls"] for row in results), "results": results}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
