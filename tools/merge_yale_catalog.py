"""Verify all catalog shard checkpoints before claiming complete text retrieval.

The source-derived aggregate carries the data notices in check_yale_catalog.
No engine queries, learning, dictionary writes or installation actions occur.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_yale_catalog import (
    Checkpoint, NOTICE, build_catalog, file_digest, input_hashes, make_header,
    output_path, select_shard, summarize,
)


def merge_catalog(database: Path, fixture: Path, paths: list[Path]) -> dict:
    if not paths or len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("Provide each shard checkpoint exactly once")
    original_hashes = input_hashes(database, fixture)
    merger_hash = file_digest(Path(__file__))
    shards = len(paths)
    indexed = {}
    for path in paths:
        with path.open("rb") as stream:
            first = stream.readline()
        if not first.endswith(b"\n"):
            raise ValueError("Incomplete checkpoint header")
        identity = json.loads(first)["identity"]
        index = identity["shard_index"]
        if (type(index) is not int or not 0 <= index < shards
                or identity["shards"] != shards or index in indexed):
            raise ValueError("Missing, duplicate or incompatible shard indices")
        indexed[index] = (path, identity["configuration"]["max_pages"])
    if set(indexed) != set(range(shards)) or len({item[1] for item in indexed.values()}) != 1:
        raise ValueError("Shard partition or paging configuration differs")

    catalog = build_catalog(database)
    summaries = []
    covered_ordinals = set()
    outcomes = Counter()
    source_pairs = processed = missing = page_calls = 0
    leases = []
    checkpoint_hashes = {}
    try:
        for index in range(shards):
            path, max_pages = indexed[index]
            groups = select_shard(catalog, shards, index)
            expected = make_header(catalog, groups, original_hashes, shards=shards,
                                   shard_index=index, max_pages=max_pages)
            checkpoint_hashes[path] = file_digest(path)
            checkpoint = Checkpoint(path, expected, groups, resume=True)
            leases.append(checkpoint)
            summary = summarize(checkpoint, new_groups=0, startup_ms=None, run_seconds=0)
            summaries.append(summary)
            outcomes.update(checkpoint.counts)
            source_pairs += checkpoint.source_pairs_checked
            processed += checkpoint.processed
            missing += checkpoint.missing_target_memberships
            page_calls += checkpoint.public_page_calls
            ordinals = {group.ordinal for group in groups}
            if covered_ordinals & ordinals:
                raise ValueError("Shard groups overlap")
            covered_ordinals.update(ordinals)
        if covered_ordinals != set(range(len(catalog.groups))):
            raise ValueError("Shards do not partition the entire current catalog")
        if input_hashes(database, fixture) != original_hashes or file_digest(Path(__file__)) != merger_hash:
            raise ValueError("Inputs changed during aggregate verification")
        if any(file_digest(path) != value for path, value in checkpoint_hashes.items()):
            raise ValueError("Checkpoint changed during aggregate verification")
        complete = bool(catalog.groups) and processed == len(catalog.groups)
        passed = (complete and source_pairs == catalog.source_pairs
                  and outcomes["all_found"] == len(catalog.groups) and not missing)
        return {"schema_version": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "completed" if passed else "completed_with_failures" if complete else "in_progress",
            "notice": NOTICE, "inputs_sha256": original_hashes,
            "merger_source_sha256": merger_hash, "catalog_sha256": catalog.sha256,
            "shards": shards, "catalog_groups": len(catalog.groups),
            "processed_groups": processed, "remaining_groups": len(catalog.groups) - processed,
            "source_pairs": catalog.source_pairs, "source_pairs_checked": source_pairs,
            "outcomes": dict(outcomes), "missing_target_memberships": missing,
            "public_page_calls": page_calls, "all_shard_checkpoints_validated": True,
            "complete_catalog_retrieval_verified": passed,
            "scope": "All stored target texts per compact plain-Yale input. Source-reading alternatives that collapse to the same text/input are represented once. Not all Chinese vocabulary, pronunciation quality, ranking acceptance, native timeout or typing proof.",
                "checkpoint_summaries": summaries}
    finally:
        for checkpoint in reversed(leases):
            checkpoint.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, default=ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--reference-fixture", type=Path, default=ROOT / "eval/yale_expected.json")
    parser.add_argument("--checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = output_path(args.output, suffix=".json", protected=(args.dictionary, args.reference_fixture, *args.checkpoint))
    report = merge_catalog(args.dictionary, args.reference_fixture, args.checkpoint)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "checkpoint_summaries"}, ensure_ascii=False))
    return 0 if report["complete_catalog_retrieval_verified"] else 1 if report["status"] == "completed_with_failures" else 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
