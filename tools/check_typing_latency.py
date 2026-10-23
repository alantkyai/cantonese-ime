"""Measure existing development seeds through changing queries and Session.

No native UI, external corpus, learning, dictionary mutation or fitting. Run
without concurrent project benchmarks. Timings describe this run, not bounds.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime import Engine
from cantonese_ime.session import Session

CASES = ROOT / "eval/core_cases.json"
DATABASE = ROOT / "data/generated/lexicon.sqlite3"
MODULES = ("engine.py", "mappings.py", "session.py", "__init__.py")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprints() -> dict[str, str]:
    paths = (DATABASE, CASES, Path(__file__).resolve(), *(ROOT / "cantonese_ime" / name for name in MODULES))
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in paths}


def distribution(values: list[float]) -> dict:
    if not values:
        return {"samples": 0, "median_ms": None, "p95_ms": None, "maximum_ms": None}
    ordered = sorted(values)
    return {"samples": len(values), "minimum_ms": ordered[0],
            "median_ms": statistics.median(values),
            "p95_ms": ordered[math.ceil(.95 * len(ordered)) - 1],
            "maximum_ms": ordered[-1]}


def summary(rows: list[dict]) -> dict:
    successful = [row for row in rows if row.get("error") is None]
    groups = {"all": successful,
              "first_pass": [row for row in successful if row["pass"] == 0],
              "later_passes": [row for row in successful if row["pass"] > 0]}
    result = {name: distribution([row["elapsed_ms"] for row in group]) for name, group in groups.items()}
    result["errors"] = len(rows) - len(successful)
    result["by_mode"] = {mode: distribution([row["elapsed_ms"] for row in successful if row["mode"] == mode]) for mode in sorted({row["mode"] for row in rows})}
    result["slowest_20"] = sorted(successful, key=lambda row: row["elapsed_ms"], reverse=True)[:20]
    result["case_summaries"] = {identifier: distribution([row["elapsed_ms"] for row in successful if row["case_id"] == identifier]) for identifier in sorted({row["case_id"] for row in rows})}
    return result


def run(passes: int = 3, snapshot_repeats: int = 20) -> dict:
    before = fingerprints()
    corpus = json.loads(CASES.read_text(encoding="utf-8"))
    cases = corpus["cases"]
    if len(cases) != 40 or len({case["id"] for case in cases}) != 40:
        raise ValueError("This harness is scoped to the 40 existing development seeds.")
    for case in cases:
        if not isinstance(case["input"], str) or not case["input"] or case["mode"] not in {"jyutping", "forgiving"}:
            raise ValueError("Invalid development seed fields.")
    applicable, exclusions = [], []
    for case in cases:
        unsupported = sorted({key for key in case["input"] if not ("a" <= key <= "z" or "A" <= key <= "Z" or key == "'")})
        if unsupported:
            exclusions.append({"case_id": case["id"], "input": case["input"], "mode": case["mode"], "unsupported_characters": unsupported,
                               "reason": "Session reserves digits for selection; this phase accepts only letters/apostrophes and does not reinterpret tone digits."})
        elif len(case["input"]) > 64:
            exclusions.append({"case_id": case["id"], "input": case["input"], "mode": case["mode"], "reason": "Entire seed exceeds Session's declared 64-character input bound; not clipped."})
        else:
            applicable.append(case)

    report = {"schema_version": 1, "kind": "development_seed_changing_query_latency",
              "captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "python_version": platform.python_version(), "sqlite_version": sqlite3.sqlite_version,
              "platform": {"system": platform.system(), "version": platform.version(), "machine": platform.machine()},
              "input_sha256_before": before, "learning_enabled": False,
              "passes": passes, "snapshot_repeats_per_case": snapshot_repeats,
              "corpus_cases": len(cases), "session_cases": len(applicable), "session_exclusions": exclusions,
              "startup_samples": [], "phases": {}, "valid_input_snapshot": False,
              "method": {
                  "clock": "perf_counter_ns, elapsed milliseconds, p95 nearest-rank; source/data hashing and JSON/statistics work are outside timers",
                  "startup": "Fresh Engine construction per phase; no learning path. Filesystem cache is uncontrolled and fingerprint reads precede construction, so these are not cold-disk measurements.",
                  "changing_queries": "Corpus order is fixed. Each seed starts at its first character; every prefix is a distinct query from the immediately preceding (input, mode). One Engine stays alive within each phase and all passes; later passes reuse base/prefix caches but not the identical-query ranked snapshot.",
                  "session": "One character per Session.handle_key call, including apostrophes. Time ends when SessionResult and visible first page (up to9) are available. Reset between seeds is outside timing. No commit, selection, rendering, keystroke pacing, IPC or native host is measured.",
                  "backend": "Separate fresh Engine phases for lookup limits9 and90 prevent cross-phase snapshot reuse. Numeric-tone seeds are included here. Timed calls are sequential, without artificial cache clearing or timed instrumentation callbacks.",
                  "snapshot": "Each full-input query is primed outside repeated-hit timers, then exactly repeated. These cache-hit timings do not represent changing input.",
                  "limits": "Existing40 development seeds only, not a representative or held-out workload. Shared-machine scheduling/OS cache are uncontrolled. Native candidate-update target cannot be assessed by this harness. Errors remain in traces and invalidate successful-run status."
              }}

    def start_engine(phase):
        if fingerprints() != before:
            raise RuntimeError("Inputs changed before phase " + phase)
        started = perf_counter_ns()
        engine = Engine(DATABASE, mode="forgiving", learning_path=None)
        elapsed = (perf_counter_ns() - started) / 1_000_000
        report["startup_samples"].append({"phase": phase, "elapsed_ms": elapsed})
        return engine

    def trace_case(engine, case, pass_index, session=None, limit=9):
        rows = []
        previous = None
        if session is not None:
            session.set_mode(case["mode"])
        for key_index, key in enumerate(case["input"]):
            prefix = case["input"][:key_index + 1]
            if previous == prefix:
                raise AssertionError("Changing-query phase repeated its query.")
            previous = prefix
            row = {"case_id": case["id"], "category": case.get("category"), "input": case["input"], "mode": case["mode"],
                   "pass": pass_index, "key_index": key_index, "key": key, "prefix": prefix}
            started = perf_counter_ns()
            try:
                if session is not None:
                    result = session.handle_key(key)
                else:
                    candidates = engine.lookup(prefix, limit=limit, mode=case["mode"])
                elapsed = (perf_counter_ns() - started) / 1_000_000
                if session is not None:
                    if not result.handled or result.preedit != prefix or result.committed or result.page != 0 or len(result.candidates) > 9:
                        raise ValueError("Session did not preserve expected preedit/visible-page state.")
                    candidates = result.candidates
                    row["completion_truncated"] = result.completion_truncated
                    row["has_more"] = result.has_more
                row.update(elapsed_ms=elapsed, candidate_count=len(candidates), error=None)
            except Exception as error:
                elapsed = (perf_counter_ns() - started) / 1_000_000
                row.update(elapsed_ms=elapsed, candidate_count=None, error=type(error).__name__ + ": " + str(error))
                rows.append(row)
                break
            rows.append(row)
        return rows

    for phase, limit in (("session_visible_first_page", None), ("backend_limit9", 9), ("backend_limit90", 90)):
        engine = start_engine(phase)
        rows = []
        selected = applicable if limit is None else cases
        try:
            session = Session(engine, learn=False, page_size=9) if limit is None else None
            for pass_index in range(passes):
                for case in selected:
                    rows.extend(trace_case(engine, case, pass_index, session=session, limit=limit or 9))
            report["phases"][phase] = {"case_count": len(selected), "rows": rows, "summary": summary(rows)}
        finally:
            engine.close()
            del engine
            gc.collect()

    phase = "identical_full_input_snapshot_hits"
    engine = start_engine(phase)
    rows, priming = [], []
    try:
        for case in cases:
            started = perf_counter_ns()
            candidates = engine.lookup(case["input"], limit=9, mode=case["mode"])
            priming.append({"case_id": case["id"], "elapsed_ms": (perf_counter_ns() - started) / 1_000_000})
            for repeat in range(snapshot_repeats):
                started = perf_counter_ns()
                repeated = engine.lookup(case["input"], limit=9, mode=case["mode"])
                elapsed = (perf_counter_ns() - started) / 1_000_000
                rows.append({"case_id": case["id"], "input": case["input"], "prefix": case["input"], "mode": case["mode"], "pass": repeat,
                             "elapsed_ms": elapsed, "candidate_count": len(repeated), "error": None if repeated == candidates else "Same-query snapshot results changed"})
        report["phases"][phase] = {"case_count": len(cases), "priming_queries": priming, "rows": rows, "summary": summary(rows)}
    finally:
        engine.close()
        del engine
        gc.collect()
    report["startup_ms"] = distribution([row["elapsed_ms"] for row in report["startup_samples"]])
    report["input_sha256_after"] = fingerprints()
    report["valid_input_snapshot"] = report["input_sha256_after"] == before
    report["error_count"] = sum(phase["summary"]["errors"] for phase in report["phases"].values())
    report["completed_successfully"] = report["valid_input_snapshot"] and report["error_count"] == 0
    report["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passes", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--snapshot-repeats", type=int, default=20, choices=range(1, 101))
    parser.add_argument("--output", type=Path, default=ROOT / "docs/typing-latency.json")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "docs").resolve()) or output.suffix != ".json":
        parser.error("Output must be a .json report inside project docs.")
    report = run(args.passes, args.snapshot_repeats)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "completed_successfully": report["completed_successfully"],
                      "startup_ms": report["startup_ms"], "session_cases": report["session_cases"],
                      "phase_summaries": {name: {key: value for key, value in phase["summary"].items() if key in ("all", "first_pass", "later_passes", "errors")} for name, phase in report["phases"].items()}}, ensure_ascii=True, indent=2))
    return 0 if report["completed_successfully"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
