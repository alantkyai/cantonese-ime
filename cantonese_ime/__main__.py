"""Local lookup, composition replay and seed-case evaluation commands."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
import sys
from time import perf_counter

from .engine import CompositionCapacityError, Engine, MODES, PaginationCapacityError
from .session import Session


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DICTIONARY = PROJECT_ROOT / "data" / "generated" / "lexicon.sqlite3"
DEFAULT_CASES = PROJECT_ROOT / "eval" / "core_cases.json"
SEED_COVERAGE_NOTICE = (
    "Development seed coverage only; not held-out accuracy or representative user performance."
)


def _bounded_integer(value: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if not minimum <= number <= maximum:
        raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
    return number


def _limit(value: str) -> int:
    return _bounded_integer(value, 1, 90)


def _repeat(value: str) -> int:
    return _bounded_integer(value, 1, 20)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cantonese_ime",
        description="Run the local Cantonese reference engine without a native IME or network service.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    lookup = subcommands.add_parser("lookup", help="Look up phonetic input, including optional numeric tones.")
    lookup.add_argument("input", metavar="INPUT")
    lookup.add_argument("--limit", type=_limit, default=9, help="Candidate limit, 1–90 (default: 9).")
    lookup.add_argument("--offset", type=lambda value: _bounded_integer(value, 0, 10000),
                        help="Fetch a candidate page at this zero-based offset (0–10000).")

    typing = subcommands.add_parser("type", help="Replay individual characters and composition keys.")
    typing.add_argument("input", metavar="INPUT")
    typing.add_argument(
        "--keys", nargs="*", default=[], metavar="KEY",
        help="Subsequent keys, e.g. Down Space. Digits select candidates; use lookup for tones.",
    )
    typing.add_argument("--trace", action="store_true", help="Include a state snapshot for each key.")

    evaluate = subcommands.add_parser("evaluate", help="Measure development seed coverage and lookup latency.")
    evaluate.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Seed-case JSON corpus.")
    evaluate.add_argument("--output", type=Path, help="Also save the JSON report to this path.")
    evaluate.add_argument("--repeat", type=_repeat, default=1, help="Lookup repetitions per case, 1–20 (default: 1).")

    for command in (lookup, typing, evaluate):
        command.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY, help="Read-only SQLite lexicon.")
        command.add_argument("--mode", choices=MODES, default="forgiving", help="Default spelling mode.")
        command.add_argument(
            "--syllabic-m-as-ng", action=argparse.BooleanOptionalAction, default=True,
            help="Accept whole-syllable ng for m in forgiving input (default: on); canonical readings stay unchanged.",
        )
        command.add_argument(
            "--learning", type=Path,
            help="Opt in to local selection memory at this path. Only type selections write it.",
        )
        command.add_argument("--json", action="store_true", help="Print UTF-8 JSON instead of a text summary.")
    return parser


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _latency(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "samples": len(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)],
    }


def _implementation_hashes() -> dict[str, str]:
    directory = Path(__file__).resolve().parent
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("engine.py", "mappings.py", "session.py", "__main__.py")}


def _open_engine(args: argparse.Namespace) -> tuple[Engine, float]:
    started = perf_counter()
    engine = Engine(args.dictionary, mode=args.mode, learning_path=args.learning,
                    syllabic_m_as_ng=args.syllabic_m_as_ng)
    return engine, (perf_counter() - started) * 1000


def _lookup(args: argparse.Namespace) -> dict:
    engine, startup_ms = _open_engine(args)
    paging = {}
    with engine:
        started = perf_counter()
        if args.offset is None:
            candidates = engine.lookup(args.input, limit=args.limit)
        else:
            page = engine.lookup_page(args.input, offset=args.offset, page_size=args.limit)
            candidates = page.candidates
            paging = {"offset": page.offset, "next_offset": page.next_offset,
                      "completion_truncated": page.completion_truncated}
        lookup_ms = (perf_counter() - started) * 1000
    return {
        "command": "lookup", "input": args.input, "mode": args.mode,
        "input_conventions": {"syllabic_m_as_ng": args.syllabic_m_as_ng},
        "learning_enabled": args.learning is not None,
        "candidates": [asdict(candidate) for candidate in candidates],
        "startup_ms": startup_ms, "lookup_ms": lookup_ms,
        **paging,
    }


def _type(args: argparse.Namespace) -> dict:
    engine, startup_ms = _open_engine(args)
    trace = []
    committed = []
    unhandled_keys = []
    with engine:
        session = Session(engine, mode=args.mode, learn=args.learning is not None)
        for key in [*args.input, *args.keys]:
            result = session.handle_key(key)
            if result.committed:
                committed.append(result.committed)
            if not result.handled:
                unhandled_keys.append(key)
            if args.trace:
                trace.append({"key": key, **asdict(result)})
        report = {
            "command": "type", "input": args.input, "mode": args.mode,
            "input_conventions": {"syllabic_m_as_ng": args.syllabic_m_as_ng},
            "learning_enabled": args.learning is not None,
            "committed": "".join(committed), "preedit": session.buffer,
            "candidates": [asdict(candidate) for candidate in session.candidates],
            "selected_index": session.selected_index, "page": session.page,
            "has_more": session.has_more,
            "completion_truncated": session.completion_truncated,
            "unhandled_keys": unhandled_keys, "startup_ms": startup_ms,
        }
    if args.trace:
        report["trace"] = trace
    return report


def _load_cases(path: Path, default_mode: str) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list) or not document["cases"]:
        raise ValueError("Evaluation corpus must be an object containing a nonempty 'cases' list.")
    default_top_k = document.get("default_top_k", 9)
    if isinstance(default_top_k, bool) or not isinstance(default_top_k, int) or not 1 <= default_top_k <= 90:
        raise ValueError("Evaluation default_top_k must be an integer from 1 to 90.")
    cases = []
    identifiers = set()
    for number, case in enumerate(document["cases"], start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Evaluation case {number} must be an object.")
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError(f"Evaluation case {number} must have a unique, nonempty string id.")
        identifiers.add(identifier)
        raw = case.get("input")
        expected = case.get("expected")
        mode = case.get("mode", default_mode)
        top_k = case.get("top_k", default_top_k)
        category = case.get("category", "uncategorized")
        if not isinstance(raw, str):
            raise ValueError(f"Evaluation case {identifier}: input must be a string.")
        if not isinstance(expected, list) or not expected or any(not isinstance(text, str) or not text for text in expected):
            raise ValueError(f"Evaluation case {identifier}: expected must be a nonempty list of nonempty strings.")
        if mode not in MODES:
            raise ValueError(f"Evaluation case {identifier}: mode must be 'jyutping' or 'forgiving'.")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 90:
            raise ValueError(f"Evaluation case {identifier}: top_k must be an integer from 1 to 90.")
        if not isinstance(category, str) or not category:
            raise ValueError(f"Evaluation case {identifier}: category must be a nonempty string.")
        cases.append({"id": identifier, "input": raw, "expected": expected, "mode": mode, "top_k": top_k, "category": category})
    return cases


def _coverage(cases: list[dict]) -> dict:
    total = len(cases)
    top1 = sum(case["top1_hit"] for case in cases)
    top_k = sum(case["top_k_hit"] for case in cases)
    return {
        "cases": total, "top1_hits": top1, "top_k_hits": top_k,
        "top1_rate": top1 / total, "top_k_rate": top_k / total,
    }


def _evaluate(args: argparse.Namespace) -> dict:
    cases = _load_cases(args.cases, args.mode)
    implementation_sha256 = _implementation_hashes()
    if args.output:
        protected_paths = {args.dictionary.resolve(), args.cases.resolve()}
        protected_paths.update(Path(__file__).resolve().parent / name for name in implementation_sha256)
        if args.learning:
            protected_paths.add(args.learning.resolve())
        if args.output.resolve() in protected_paths:
            raise ValueError("Evaluation output must differ from the dictionary, corpus and learning files.")
    # Reproducibility hashing is deliberately outside engine startup and lookup
    # timing, so dictionary size does not inflate the reported latency samples.
    if not args.dictionary.is_file():
        raise FileNotFoundError(f"Dictionary not found: {args.dictionary.resolve()}. Run tools/build_dictionary.py first.")
    with args.dictionary.open("rb") as dictionary_file:
        dictionary_sha256 = hashlib.file_digest(dictionary_file, "sha256").hexdigest()
    with args.cases.open("rb") as corpus_file:
        corpus_sha256 = hashlib.file_digest(corpus_file, "sha256").hexdigest()
    engine, startup_ms = _open_engine(args)
    results = []
    all_samples = []
    first_samples = []
    with engine:
        for case in cases:
            samples = []
            actual = None
            stable = True
            for _ in range(args.repeat):
                started = perf_counter()
                candidates = engine.lookup(case["input"], limit=90, mode=case["mode"])
                samples.append((perf_counter() - started) * 1000)
                texts = [candidate.text for candidate in candidates]
                if actual is None:
                    actual = texts
                elif actual != texts:
                    stable = False
            expected = set(case["expected"])
            rank = next((index for index, text in enumerate(actual, start=1) if text in expected), None)
            results.append({
                **case, "actual": actual, "rank": rank, "top1_hit": rank == 1,
                "top_k_hit": rank is not None and rank <= case["top_k"],
                "ranking_stable": stable, "latency_ms": _latency(samples),
                "first_lookup_ms": samples[0],
            })
            all_samples.extend(samples)
            first_samples.append(samples[0])
    categories = defaultdict(list)
    for result in results:
        categories[result["category"]].append(result)
    if _implementation_hashes() != implementation_sha256:
        raise ValueError("Engine source changed during evaluation; rerun against settled sources.")
    with args.dictionary.open("rb") as dictionary_file:
        if hashlib.file_digest(dictionary_file, "sha256").hexdigest() != dictionary_sha256:
            raise ValueError("Dictionary changed during evaluation; rerun against a settled build.")
    with args.cases.open("rb") as corpus_file:
        if hashlib.file_digest(corpus_file, "sha256").hexdigest() != corpus_sha256:
            raise ValueError("Corpus changed during evaluation; rerun against a settled corpus.")
    report = {
        "report_schema_version": 1, "engine_version": "1.0.0",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "dictionary_sha256": dictionary_sha256, "corpus_sha256": corpus_sha256,
        "implementation_sha256": implementation_sha256,
        "python_version": sys.version.split()[0], "sqlite_version": sqlite3.sqlite_version,
        "command": "evaluate", "evaluation_kind": "seed_case_coverage",
        "notice": SEED_COVERAGE_NOTICE, "learning_enabled": args.learning is not None,
        "input_conventions": {"syllabic_m_as_ng": args.syllabic_m_as_ng},
        "rank_search_limit": 90, "repeat": args.repeat,
        "startup_ms": startup_ms, "latency_ms": _latency(all_samples),
        "first_sample_latency_ms": _latency(first_samples),
        "latency_method": "Sequential in-process lookups with limit=90. Consecutive repeats of one input normally reuse its ranked snapshot; the aggregate includes first lookups and cached repeats. First samples per case are also reported, without claiming cache-free operation. Startup is separate; p95 uses nearest rank. This is not per-keystroke or native host latency.",
        "aggregate": _coverage(results),
        "categories": {category: _coverage(group) for category, group in sorted(categories.items())},
        "all_passed": all(case["top_k_hit"] and case["ranking_stable"] for case in results),
        "cases": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(_json(report) + "\n", encoding="utf-8")
    return report


def _print_candidates(candidates: list[dict]) -> None:
    if not candidates:
        print("No candidates.")
    for index, candidate in enumerate(candidates, start=1):
        print(f"{index}. {candidate['text']}\t{candidate['reading']}\t{candidate['match_type']}")


def _print_report(report: dict) -> None:
    if report["command"] == "lookup":
        _print_candidates(report["candidates"])
        if "offset" in report:
            print(f"Offset: {report['offset']}; next offset: {report['next_offset']}")
        print(f"Startup: {report['startup_ms']:.3f} ms; lookup: {report['lookup_ms']:.3f} ms")
    elif report["command"] == "type":
        print(f"Committed: {report['committed']}")
        print(f"Preedit: {report['preedit']}")
        print(f"Page: {report['page'] + 1}; selected slot: {report['selected_index'] + 1}")
        _print_candidates(report["candidates"])
        if report["unhandled_keys"]:
            print(f"Unhandled keys: {', '.join(repr(key) for key in report['unhandled_keys'])}")
        for event in report.get("trace", []):
            print(f"{event['key']!r}: handled={event['handled']}, committed={event['committed']!r}, preedit={event['preedit']!r}, page={event['page'] + 1}, slot={event['selected_index'] + 1}")
    else:
        print(report["notice"])
        aggregate = report["aggregate"]
        print(f"Top-1: {aggregate['top1_hits']}/{aggregate['cases']}; top-k: {aggregate['top_k_hits']}/{aggregate['cases']}")
        for category, coverage in report["categories"].items():
            print(f"{category}: top-1 {coverage['top1_hits']}/{coverage['cases']}; top-k {coverage['top_k_hits']}/{coverage['cases']}")
        print(f"Startup: {report['startup_ms']:.3f} ms; lookup median: {report['latency_ms']['median']:.3f} ms; p95: {report['latency_ms']['p95']:.3f} ms")
        print(report["latency_method"])
        for case in report["cases"]:
            if not case["top_k_hit"] or not case["ranking_stable"]:
                print(f"Unmet: {case['id']}; expected rank={case['rank']}; top_k={case['top_k']}; ranking_stable={case['ranking_stable']}")
        print(f"All seed targets met: {report['all_passed']}")


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    args = _parser().parse_args(argv)
    try:
        if args.command == "lookup":
            report = _lookup(args)
        elif args.command == "type":
            report = _type(args)
        else:
            report = _evaluate(args)
        if args.json:
            print(_json(report))
        else:
            _print_report(report)
        return 1 if args.command == "evaluate" and not report["all_passed"] else 0
    except (OSError, ValueError, sqlite3.Error, PaginationCapacityError, CompositionCapacityError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
