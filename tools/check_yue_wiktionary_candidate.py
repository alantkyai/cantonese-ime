"""Probe all changed Yale inputs and all stored competing texts in a candidate."""
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
from cantonese_ime.yue_wiktionary import SOURCE_ID, verify_yue_wiktionary_snapshot
from tools.build_yue_wiktionary_candidate import BASELINES
from tools.check_yale_catalog import NOTICE, build_catalog, file_digest, input_hashes, output_path, probe_group


def affected_groups(database: Path, manifest: dict):
    """Derive inputs from real new rows and include every stored homophone text."""
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        rows = list(db.execute("SELECT text,reading,base_reading,weight,origin FROM entries WHERE source=? ORDER BY text,reading", (SOURCE_ID,)))
    expected = {(row["text"], row["reading"]) for row in manifest["added_entries"]}
    if (not rows or len(rows) != manifest["added_pairs"] or len(expected) != len(rows)
            or {(row[0], row[1]) for row in rows} != expected
            or any(weight != 0 or origin != "supplement" for _, _, _, weight, origin in rows)):
        raise ValueError("Actual explicit Yue cohort differs from candidate evidence")
    inputs = {"".join(yale_ascii(base) for base in bases.split()) for _, _, bases, _, _ in rows}
    catalog = build_catalog(database)
    selected = tuple(group for group in catalog.groups if group.raw in inputs)
    if {group.raw for group in selected} != inputs:
        raise ValueError("Yue affected-input cohort is incomplete")
    return catalog, selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-type", choices=sorted(BASELINES), default="canonical")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    database = ROOT / ".local/yue-wiktionary-candidate" / args.baseline_type / "lexicon.sqlite3"
    manifest_path = database.with_suffix(".manifest.json")
    lock_path = ROOT / "data/supplements/yue-wiktionary.sources.lock.json"
    fixture = ROOT / "eval/yale_expected.json"
    target = output_path(args.output or ROOT / f"docs/yue-wiktionary-candidate-{args.baseline_type}-yale.json",
                         suffix=".json", protected=(database, manifest_path, lock_path, fixture))
    if target.exists():
        raise ValueError("Preserve the earlier candidate lookup report; select a new output")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    evidence = manifest["yue_wiktionary_evidence"]
    lock = json.loads(lock_path.read_text("utf-8"))
    directory = ROOT / lock["local_directory"]
    baseline_relative, baseline_hash = BASELINES[args.baseline_type]
    paths = {"source_lock": lock_path, "parser": ROOT / "cantonese_ime/yue_wiktionary.py",
        "builder": ROOT / "tools/build_yue_wiktionary_candidate.py",
        "preservation_helper": ROOT / "tools/build_cccedict_candidate.py",
        "mappings": ROOT / "cantonese_ime/mappings.py", "engine": ROOT / "cantonese_ime/engine.py",
        "baseline": ROOT / baseline_relative, "baseline_manifest": (ROOT / baseline_relative).with_suffix(".manifest.json")}
    paths.update({"source:" + row["name"]: directory / row["name"] for row in lock["files"]})

    def guarded():
        values = input_hashes(database, fixture)
        values.update({key: file_digest(path) for key, path in paths.items()})
        values.update(candidate_manifest=file_digest(manifest_path), candidate_checker=file_digest(Path(__file__)))
        return values

    hashes = guarded()
    if (hashes["dictionary"] != manifest["database_sha256"] or hashes["baseline"] != baseline_hash
            or manifest["baseline_sha256"] != baseline_hash
            or any(hashes.get(key) != digest for key, digest in evidence["inputs_before_sha256"].items())
            or manifest.get("inputs_after_sha256") != evidence["inputs_before_sha256"]):
        raise ValueError("Yue candidate source, implementation or baseline differs from build evidence")
    verify_yue_wiktionary_snapshot(directory, lock)
    catalog, groups = affected_groups(database, manifest)
    results = []
    with Engine(database, learning_path=None, prefer_yale=True) as engine:
        for index, group in enumerate(groups, 1):
            results.append({"input": group.raw, "targets": list(group.targets), "source_pairs": group.source_pairs,
                            **probe_group(engine, group, max_pages=128)})
            if index % 50 == 0 or index == len(groups):
                print(json.dumps({"checked_groups": index, "total_groups": len(groups),
                                  "outcomes": dict(Counter(row["status"] for row in results))}), flush=True)
    if guarded() != hashes:
        raise ValueError("Yue candidate inputs changed during public lookup")
    verify_yue_wiktionary_snapshot(directory, lock)
    outcomes = Counter(row["status"] for row in results)
    passed = bool(groups) and outcomes["all_found"] == len(groups)
    report = {"schema_version": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_only": True, "status": "passed" if passed else "failed", "notice": NOTICE,
        "inputs_sha256": hashes, "inputs_unchanged": True, "candidate_catalog_sha256": catalog.sha256,
        "candidate_total_pairs": catalog.source_pairs, "affected_groups": len(groups),
        "required_input_text_memberships": sum(len(group.targets) for group in groups),
        "new_pairs": manifest["added_pairs"], "new_texts": manifest["new_texts"],
        "outcomes": dict(outcomes), "all_affected_target_texts_reached": passed,
        "complete_catalog_retrieval_verified": False, "linguistic_approval": False,
        "scope": "Every new explicit Yue pair's compact Yale input and all candidate-database texts competing at those inputs. "
                 "Text reachability, not proof every pronunciation is correct or every stored reading is separately displayed. "
                 "Unchanged inputs, native typing, installation and all-Chinese coverage are outside this cohort.",
        "public_page_calls": sum(row["public_page_calls"] for row in results), "results": results}
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
