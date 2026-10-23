"""Resumable, exhaustive stored-text retrieval through public Engine.lookup_page.

Catalog keys and target texts are dictionary-derived data under CC-BY-SA-4.0;
retain data/DATA_LICENSE.md and data/THIRD_PARTY_NOTICES.md with shared reports.
This measures this finite catalog, not all Chinese or pronunciation correctness.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime import CompositionCapacityError, Engine, PaginationCapacityError
from cantonese_ime.mappings import yale_ascii

GUARDED = ("cantonese_ime/__init__.py", "cantonese_ime/engine.py", "cantonese_ime/mappings.py",
           "tools/check_yale_catalog.py")
TOKEN = re.compile(r"([a-z]+)[1-6]\Z", re.ASCII)
STATUSES = {"all_found", "exhausted_missing", "capacity_limited", "engine_error",
            "offset_limit", "page_budget", "input_limit_excluded"}
NOTICE = {"derived_data_license": "CC-BY-SA-4.0",
          "attribution": ["data/DATA_LICENSE.md", "data/THIRD_PARTY_NOTICES.md"],
          "scope": "Finite stored-text retrieval; dictionary-derived keys are not held-out linguistic labels, native typing or all-Chinese coverage."}


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True, slots=True)
class Group:
    ordinal: int
    raw: str
    targets: tuple[str, ...]
    source_pairs: int

    @property
    def identity(self):
        return digest([self.ordinal, self.raw, self.targets, self.source_pairs])


@dataclass(frozen=True, slots=True)
class Catalog:
    groups: tuple[Group, ...]
    source_pairs: int
    sha256: str


def build_catalog(database: Path, converter=yale_ascii) -> Catalog:
    """Read every row; unsupported/malformed rows fail rather than disappear."""
    grouped = {}
    base_spellings = {}
    rows = 0
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        for text, reading, base_reading in connection.execute("SELECT text,reading,base_reading FROM entries"):
            if not isinstance(text, str) or not text or not isinstance(reading, str):
                raise ValueError("Empty or non-text dictionary target/reading")
            bases = []
            for token in reading.split():
                match = TOKEN.fullmatch(token)
                if not match:
                    raise ValueError(f"Noncanonical dictionary reading: {reading!r}")
                bases.append(match.group(1))
            if not bases or " ".join(bases) != base_reading:
                raise ValueError(f"Dictionary base/reading mismatch: {reading!r}")
            spellings = []
            for base in bases:
                if base not in base_spellings:
                    spelling = converter(base)
                    if not isinstance(spelling, str) or not re.fullmatch(r"[a-z]+", spelling, re.ASCII):
                        raise ValueError(f"Invalid public Yale route for {base!r}")
                    base_spellings[base] = spelling
                spellings.append(base_spellings[base])
            raw = "".join(spellings)
            if raw not in grouped:
                grouped[raw] = [set(), 0]
            grouped[raw][0].add(text)
            grouped[raw][1] += 1
            rows += 1
    groups = []
    hasher = hashlib.sha256()
    for ordinal, raw in enumerate(sorted(grouped)):
        targets, source_pairs = grouped.pop(raw)
        group = Group(ordinal, raw, tuple(sorted(targets)), source_pairs)
        groups.append(group)
        hasher.update(encoded([ordinal, raw, group.targets, source_pairs]) + b"\n")
    return Catalog(tuple(groups), rows, hasher.hexdigest())


def select_shard(catalog: Catalog, shards: int, shard_index: int) -> tuple[Group, ...]:
    if type(shards) is not int or type(shard_index) is not int or not 1 <= shards <= 1024 or not 0 <= shard_index < shards:
        raise ValueError("shards must be1..1024 and shard-index0..shards-1")
    selected = []
    for group in catalog.groups:
        key = hashlib.sha256(group.raw.encode("ascii")).digest()
        if int.from_bytes(key, "big") % shards == shard_index:
            selected.append((key, group))
    return tuple(group for _, group in sorted(selected, key=lambda pair: pair[0]))


def probe_group(engine, group: Group, *, max_pages: int) -> dict:
    required = set(group.targets)
    found = {}
    seen = set()
    page_count = 0
    lookup_calls = 0
    offset = 0
    pool_truncated = False
    first_ms = None
    max_ms = 0.0
    started = time.perf_counter()
    status = "input_limit_excluded" if len(group.raw) > engine.MAX_INPUT_LENGTH else None
    error = ""
    while status is None:
        if page_count >= max_pages:
            status = "page_budget"
            break
        call_started = time.perf_counter()
        lookup_calls += 1
        try:
            page = engine.lookup_page(group.raw, offset=offset, page_size=90, mode="forgiving")
        except (CompositionCapacityError, PaginationCapacityError) as exception:
            status, error = "capacity_limited", str(exception)
        except Exception as exception:
            status, error = "engine_error", type(exception).__name__ + ": " + str(exception)
        elapsed = (time.perf_counter() - call_started) * 1000
        max_ms = max(max_ms, elapsed)
        if first_ms is None:
            first_ms = elapsed
        if status is not None:
            break
        page_count += 1
        try:
            if page.offset != offset:
                raise ValueError("Public pager returned the wrong offset")
            if len(page.candidates) > 90 or (page.next_offset is not None and
                    (type(page.next_offset) is not int or page.next_offset != offset + len(page.candidates)
                     or page.next_offset <= offset)):
                raise ValueError("Public pager returned invalid cursor/count metadata")
            pool_truncated = pool_truncated or page.completion_truncated
            for candidate in page.candidates:
                if candidate.text in seen or candidate.consumed_input != len(group.raw):
                    raise ValueError("Public pager repeated a text or consumed the wrong input")
                seen.add(candidate.text)
                if candidate.text in required:
                    found[candidate.text] = {"text": candidate.text, "reading": candidate.reading, "rank": len(seen)}
            if required <= found.keys():
                status = "all_found"
            elif page.next_offset is None:
                status = "exhausted_missing"
            elif page.next_offset > engine.MAX_OFFSET:
                status = "offset_limit"
            else:
                offset = page.next_offset
        except Exception as exception:
            status, error = "engine_error", type(exception).__name__ + ": " + str(exception)
    return {"status": status, "found_targets": [found[text] for text in sorted(found)],
            "missing_targets": sorted(required - found.keys()), "pages": page_count, "public_page_calls": lookup_calls,
            "visible_candidates": len(seen), "pool_truncated_seen": bool(pool_truncated), "error": error,
            "lookup_ms": (time.perf_counter() - started) * 1000,
            "first_request_ms": first_ms, "max_request_ms": max_ms}


def input_hashes(database: Path, fixture: Path) -> dict:
    result = {name: file_digest(ROOT / name) for name in GUARDED}
    result.update(dictionary=file_digest(database), reference_fixture=file_digest(fixture))
    return result


def make_header(catalog: Catalog, groups: tuple[Group, ...], hashes: dict, *, shards: int, shard_index: int, max_pages: int) -> dict:
    identity = {"inputs_sha256": hashes, "catalog_sha256": catalog.sha256,
                "source_pairs": catalog.source_pairs, "catalog_groups": len(catalog.groups),
                "selected_groups": len(groups), "selection_sha256": digest([group.identity for group in groups]),
                "shards": shards, "shard_index": shard_index,
                "shard_method": "sha256(ascii_input) modulo shards; visit in ascending SHA256 order",
                "configuration": {"mode": "forgiving", "prefer_yale": True, "learning_enabled": False,
                    "page_size": 90, "max_pages": max_pages, "input_limit": Engine.MAX_INPUT_LENGTH,
                    "max_offset": Engine.MAX_OFFSET},
                "python_version": platform.python_version(), "sqlite_version": sqlite3.sqlite_version}
    header = {"type": "header", "schema_version": 1, "identity": identity,
              "snapshot_id": digest(identity), "notice": NOTICE}
    return {**header, "header_sha256": digest(header)}


def validate_result(result: dict, group: Group) -> None:
    if set(result) != {"status", "found_targets", "missing_targets", "pages", "public_page_calls", "visible_candidates", "pool_truncated_seen",
                       "error", "lookup_ms", "first_request_ms", "max_request_ms"} or result["status"] not in STATUSES:
        raise ValueError("Invalid checkpoint result schema/status")
    found_rows = result["found_targets"]
    if not isinstance(found_rows, list) or not isinstance(result["missing_targets"], list):
        raise ValueError("Invalid checkpoint target lists")
    found = []
    ranks = []
    for row in found_rows:
        if set(row) != {"text", "reading", "rank"} or not isinstance(row["reading"], str) or type(row["rank"]) is not int or row["rank"] < 1:
            raise ValueError("Invalid found-target checkpoint record")
        found.append(row["text"])
        ranks.append(row["rank"])
    missing = result["missing_targets"]
    if found != sorted(set(found)) or missing != sorted(set(missing)) or set(found) & set(missing) or set(found) | set(missing) != set(group.targets):
        raise ValueError("Checkpoint targets do not exactly partition the catalog group")
    if result["status"] == "all_found" and (missing or result["error"] or result["pages"] < 1):
        raise ValueError("Checkpoint success contradicts missing targets")
    if (any(type(result[key]) is not int or result[key] < 0 for key in ("pages", "public_page_calls", "visible_candidates"))
            or type(result["pool_truncated_seen"]) is not bool or not isinstance(result["error"], str)
            or len(ranks) != len(set(ranks)) or any(rank > result["visible_candidates"] for rank in ranks)
            or not result["pages"] <= result["public_page_calls"] <= result["pages"] + 1
            or result["visible_candidates"] > result["pages"] * 90):
        raise ValueError("Invalid checkpoint counts/ranks")
    for key in ("lookup_ms", "first_request_ms", "max_request_ms"):
        value = result[key]
        if value is None and key == "first_request_ms":
            continue
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid checkpoint latency")
    if result["status"] == "input_limit_excluded" and (len(group.raw) <= Engine.MAX_INPUT_LENGTH or found or result["pages"]):
        raise ValueError("Checkpoint input exclusion contradicts the actual bound")


class Checkpoint:
    """Single-writer hash chain; only source-verified committed batches are trusted."""
    def __init__(self, path: Path, header: dict, groups: tuple[Group, ...], *, resume: bool, discard_uncommitted: bool = False):
        self.path, self.header, self.groups = path, header, groups
        self.processed = 0
        self.counts = Counter()
        self.source_pairs_checked = 0
        self.missing_target_memberships = 0
        self.lookup_seconds = 0.0
        self.public_page_calls = 0
        self.last_hash = header["header_sha256"]
        self.pending = []
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lease = path.with_suffix(path.suffix + ".lock").open("a+b")
        if self.lease.seek(0, os.SEEK_END) == 0:
            self.lease.write(b"0")
            self.lease.flush()
        self.lease.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lease.close()
            raise ValueError("Another writer holds this checkpoint lease") from None
        try:
            self._load(resume=resume, discard_uncommitted=discard_uncommitted)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.lease.closed:
            return
        self.lease.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.lease.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.lease.fileno(), fcntl.LOCK_UN)
        self.lease.close()

    def _load(self, *, resume, discard_uncommitted):
        path, header, groups = self.path, self.header, self.groups
        if resume:
            with path.open("rb") as stream:
                first = stream.readline()
                if not first.endswith(b"\n") or encoded(json.loads(first)) != encoded(header):
                    raise ValueError("Checkpoint header/snapshot identity mismatch")
                committed_offset, committed_hash = stream.tell(), self.last_hash
                incomplete_tail = False
                for raw in stream:
                    if not raw.endswith(b"\n"):
                        incomplete_tail = True
                        break
                    record = json.loads(raw)
                    checksum = record.pop("record_sha256", None)
                    if (record.get("snapshot_id") != header["snapshot_id"]
                            or record["previous_sha256"] != self.last_hash or checksum != digest(record)):
                        raise ValueError("Checkpoint record identity/hash-chain mismatch")
                    if record.get("type") == "invalid":
                        raise ValueError("Checkpoint was invalidated by a source/dictionary change")
                    if record.get("type") == "commit":
                        if (set(record) != {"type", "snapshot_id", "processed_groups", "previous_sha256"}
                                or type(record["processed_groups"]) is not int
                                or record["processed_groups"] != self.processed + len(self.pending)):
                            raise ValueError("Invalid checkpoint commit boundary")
                        for group, result in self.pending:
                            self._accept(result, group)
                        self.pending.clear()
                        self.last_hash = checksum
                        committed_offset, committed_hash = stream.tell(), checksum
                        continue
                    position = self.processed + len(self.pending)
                    if position >= len(groups) or set(record) != {"type", "snapshot_id", "group_position", "group_id", "ordinal", "input", "result", "previous_sha256"} or record["type"] != "group":
                        raise ValueError("Invalid checkpoint group schema")
                    group = groups[position]
                    if (type(record["group_position"]) is not int or type(record["ordinal"]) is not int
                            or record["group_position"] != position or record["group_id"] != group.identity
                            or record["ordinal"] != group.ordinal or record["input"] != group.raw):
                        raise ValueError("Checkpoint skipped/duplicated/mismatched catalog group")
                    validate_result(record["result"], group)
                    self.pending.append((group, record["result"]))
                    self.last_hash = checksum
            if self.pending or incomplete_tail:
                if not discard_uncommitted:
                    raise ValueError("Unverified checkpoint tail; use --discard-uncommitted-tail to archive it and retry its groups")
                with path.open("rb") as stream:
                    stream.seek(committed_offset)
                    tail = stream.read()
                recovered = path.with_name(path.name + ".unverified-" + uuid.uuid4().hex)
                with recovered.open("xb") as stream:
                    stream.write(tail)
                with path.open("r+b") as stream:
                    stream.truncate(committed_offset)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.pending.clear()
                self.last_hash = committed_hash
        else:
            with path.open("xb") as stream:
                stream.write(encoded(header) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        self.expected_size = path.stat().st_size

    def _accept(self, result: dict, group: Group) -> None:
        self.processed += 1
        self.counts[result["status"]] += 1
        self.source_pairs_checked += group.source_pairs
        self.missing_target_memberships += len(result["missing_targets"])
        self.lookup_seconds += result["lookup_ms"] / 1000
        self.public_page_calls += result["public_page_calls"]

    def _write_record(self, record):
        if self.path.stat().st_size != self.expected_size:
            raise ValueError("Checkpoint changed outside this writer")
        checksum = digest(record)
        data = encoded({**record, "record_sha256": checksum}) + b"\n"
        with self.path.open("ab") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        self.expected_size += len(data)
        self.last_hash = checksum

    def append(self, result: dict) -> None:
        position = self.processed + len(self.pending)
        group = self.groups[position]
        validate_result(result, group)
        record = {"type": "group", "snapshot_id": self.header["snapshot_id"], "group_position": position,
                  "group_id": group.identity, "ordinal": group.ordinal, "input": group.raw,
                  "result": result, "previous_sha256": self.last_hash}
        self._write_record(record)
        self.pending.append((group, result))

    def commit_verified(self):
        self._write_record({"type": "commit", "snapshot_id": self.header["snapshot_id"],
            "processed_groups": self.processed + len(self.pending), "previous_sha256": self.last_hash})
        for group, result in self.pending:
            self._accept(result, group)
        self.pending.clear()

    def invalidate(self):
        self._write_record({"type": "invalid", "snapshot_id": self.header["snapshot_id"],
            "previous_sha256": self.last_hash})


def summarize(checkpoint: Checkpoint, *, new_groups: int, startup_ms: float | None, run_seconds: float) -> dict:
    if checkpoint.pending:
        raise ValueError("Cannot summarize unverified checkpoint records")
    total = len(checkpoint.groups)
    processed = checkpoint.processed
    counts = checkpoint.counts
    all_processed = processed == total and total > 0
    all_reachable = all_processed and counts["all_found"] == total
    identity = checkpoint.header["identity"]
    return {"schema_version": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": checkpoint.header["snapshot_id"], "identity": identity, "notice": NOTICE,
            "status": "completed" if all_reachable else ("completed_with_failures" if all_processed else "in_progress"),
            "selected_groups": total, "processed_groups": processed, "remaining_groups": total - processed,
            "new_groups_this_run": new_groups, "outcomes": dict(counts),
            "source_pairs_checked": checkpoint.source_pairs_checked,
            "missing_target_memberships": checkpoint.missing_target_memberships,
            "input_limit_excluded_groups": counts["input_limit_excluded"],
            "all_selected_groups_processed": all_processed, "all_selected_target_texts_reached": all_reachable,
            "complete_catalog_retrieval_verified": all_reachable and identity["shards"] == 1,
            "engine_startup_ms_this_run": startup_ms, "wall_seconds_this_run": run_seconds,
            "lookup_seconds_all_checkpoint_records": checkpoint.lookup_seconds,
            "public_page_calls_all_checkpoint_records": checkpoint.public_page_calls,
            "checkpoint": str(checkpoint.path), "checkpoint_sha256": file_digest(checkpoint.path),
            "checkpoint_last_record_sha256": checkpoint.last_hash,
            "failures_retained_in_checkpoint": counts.total() - counts["all_found"]}


def output_path(path: Path, *, suffix: str, protected: tuple[Path, ...]) -> Path:
    target = path.resolve()
    relative = target.relative_to(ROOT)
    if (not relative.parts or relative.parts[0] not in {".local", "docs"} or target.suffix != suffix
            or target in {p.resolve() for p in protected}):
        raise ValueError("Audit outputs must be separate project docs/.local files with the required extension")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, default=ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--reference-fixture", type=Path, default=ROOT / "eval/yale_expected.json")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--discard-uncommitted-tail", action="store_true",
                        help="On resume archive an interrupted unverified tail, then recheck those groups")
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--limit", type=int, help="Maximum NEW groups this run; omitted means all remaining groups")
    parser.add_argument("--max-pages", type=int, default=128)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--verify-every", type=int, default=1000, help="Full source/DB hashes and durable batch commit interval")
    args = parser.parse_args()
    if ((args.limit is not None and args.limit < 0) or not 1 <= args.max_pages <= 10000
            or not 1 <= args.progress_every <= 10000 or not 1 <= args.verify_every <= 10000):
        parser.error("limit must be nonnegative; max-pages/progress-every/verify-every1..10000")
    if args.discard_uncommitted_tail and not args.resume:
        parser.error("discard-uncommitted-tail requires resume")
    checkpoint_path = output_path(args.checkpoint, suffix=".jsonl", protected=(args.dictionary, args.reference_fixture))
    report_path = output_path(args.output, suffix=".json", protected=(args.dictionary, args.reference_fixture, checkpoint_path)) if args.output else None
    started = time.perf_counter()
    hashes = input_hashes(args.dictionary, args.reference_fixture)
    database_stat = args.dictionary.stat()
    database_fingerprint = (database_stat.st_size, database_stat.st_mtime_ns, database_stat.st_dev, database_stat.st_ino)
    catalog = build_catalog(args.dictionary)
    groups = select_shard(catalog, args.shards, args.shard_index)
    header = make_header(catalog, groups, hashes, shards=args.shards, shard_index=args.shard_index, max_pages=args.max_pages)
    checkpoint = Checkpoint(checkpoint_path, header, groups, resume=args.resume,
                            discard_uncommitted=args.discard_uncommitted_tail)
    print(json.dumps({"type": "catalog_ready", "snapshot_id": header["snapshot_id"],
        "catalog_groups": len(catalog.groups), "source_pairs": catalog.source_pairs,
        "selected_groups": len(groups), "resumed_groups": checkpoint.processed,
        "catalog_and_resume_seconds": time.perf_counter() - started}), flush=True)
    new_groups = 0
    startup_ms = None
    remaining_budget = len(groups) if args.limit is None else args.limit
    try:
        if remaining_budget and checkpoint.processed < len(groups):
            engine_started = time.perf_counter()
            with Engine(args.dictionary, mode="forgiving", learning_path=None, prefer_yale=True) as engine:
                startup_ms = (time.perf_counter() - engine_started) * 1000
                while checkpoint.processed + len(checkpoint.pending) < len(groups) and new_groups < remaining_budget:
                    group = groups[checkpoint.processed + len(checkpoint.pending)]
                    checkpoint.append(probe_group(engine, group, max_pages=args.max_pages))
                    new_groups += 1
                    if new_groups % args.progress_every == 0:
                        source_hashes = {name: file_digest(ROOT / name) for name in GUARDED}
                        source_hashes["reference_fixture"] = file_digest(args.reference_fixture)
                        current_stat = args.dictionary.stat()
                        current_fingerprint = (current_stat.st_size, current_stat.st_mtime_ns, current_stat.st_dev, current_stat.st_ino)
                        if (any(value != hashes[name] for name, value in source_hashes.items())
                                or current_fingerprint != database_fingerprint):
                            checkpoint.invalidate()
                            raise RuntimeError("Source/dictionary changed; checkpoint is invalidated")
                        print(json.dumps({"type": "progress", "committed_groups": checkpoint.processed,
                            "unverified_groups": len(checkpoint.pending), "new_groups": new_groups,
                            "remaining_groups": len(groups) - checkpoint.processed - len(checkpoint.pending),
                            "committed_outcomes": dict(checkpoint.counts),
                            "wall_seconds": time.perf_counter() - started}), flush=True)
                    if new_groups % args.verify_every == 0:
                        if input_hashes(args.dictionary, args.reference_fixture) != hashes:
                            checkpoint.invalidate()
                            raise RuntimeError("Source/dictionary changed; checkpoint is invalidated")
                        checkpoint.commit_verified()
        if input_hashes(args.dictionary, args.reference_fixture) != hashes:
            checkpoint.invalidate()
            raise RuntimeError("Source/dictionary changed; checkpoint is invalidated")
        if checkpoint.pending:
            checkpoint.commit_verified()
        report = summarize(checkpoint, new_groups=new_groups, startup_ms=startup_ms, run_seconds=time.perf_counter() - started)
    finally:
        checkpoint.close()
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = report_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, report_path)
    print(json.dumps({"type": "summary", **report}, ensure_ascii=False), flush=True)
    return 1 if report["failures_retained_in_checkpoint"] else (0 if report["all_selected_groups_processed"] else 2)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
