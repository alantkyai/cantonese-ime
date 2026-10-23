"""Database-derived decoder reachability smoke test, not held-out accuracy.

Sample authored and generated rows deterministically, then replay their stored
readings through Engine. The corpus is an oracle for reachable stored entries,
not evidence that the entries' pronunciations are linguistically correct.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import hashlib
import heapq
import json
import math
import os
import platform
from pathlib import Path
import re
import sqlite3
import statistics
import sys
import tempfile
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cantonese_ime import Engine, PaginationCapacityError
from cantonese_ime.dictionary import file_sha256


RUNTIME_SOURCE_HASHES = {
    name: file_sha256(PROJECT_ROOT / name)
    for name in ("cantonese_ime/engine.py", "cantonese_ime/mappings.py", "tools/check_dictionary_lookup.py")
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def collect_cases(database: Path, sample_size: int = 500) -> dict:
    if sample_size < 1:
        raise ValueError("sample size must be positive")
    explicit = round(sample_size * 0.4)
    supplement = round(sample_size * 0.2)
    quotas = {"explicit": explicit, "supplement": supplement,
              "generated": sample_size - explicit - supplement}
    eligibility = {}
    selected = []
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        for origin, quota in quotas.items():
            counts: Counter = Counter()

            def rows():
                for text, reading, source, weight in connection.execute(
                    "SELECT text,reading,source,weight FROM entries WHERE origin=?", (origin,)
                ):
                    counts["input_rows"] += 1
                    syllables = reading.split()
                    if not syllables or any(not re.fullmatch(r"[a-z]+[1-6]", token) for token in syllables):
                        counts["excluded_invalid_reading"] += 1
                        continue
                    fully_toned = "".join(syllables)
                    if len(fully_toned) > Engine.MAX_INPUT_LENGTH:
                        counts["excluded_over_input_limit"] += 1
                        continue
                    counts["eligible_rows"] += 1
                    key = hashlib.sha256((origin + "\0" + text + "\0" + reading).encode("utf-8")).hexdigest()
                    yield {"id": key[:20], "selection_hash": key, "origin": origin,
                           "source": source, "text": text, "reading": reading,
                           "weight": weight, "fully_toned_input": fully_toned,
                           "tone_free_input": "".join(token[:-1] for token in syllables)}

            chosen = heapq.nsmallest(quota, rows(), key=lambda row: row["selection_hash"])
            selected.extend(chosen)
            eligibility[origin] = dict(counts, requested=quota, sampled=len(chosen))
    selected.sort(key=lambda row: (row["origin"], row["selection_hash"]))
    for index, case in enumerate(selected):
        case["include_tone_free"] = index % 5 == 0
    return {
        "schema_version": 1,
        "purpose": "Database-derived decoder reachability smoke corpus; NOT independent held-out linguistic evaluation.",
        "database_sha256": file_sha256(database),
        "selection_method": "Lowest SHA-256(origin NUL text NUL reading) within each origin; no frequency weighting or manual target selection.",
        "strata": eligibility,
        "requested_cases": sample_size,
        "case_count": len(selected),
        "tone_free_policy": "Every fifth selected case also tested without tones; all cases tested fully toned in strict Jyutping mode.",
        "cases": selected,
    }


def summarize(results: list[dict]) -> dict:
    result = {"scenarios": len(results)}
    for label, cap in (("top1", 1), ("top9", 9), ("top90", 90)):
        result[label] = sum(row["rank"] is not None and row["rank"] <= cap for row in results)
    result["missing_top90"] = sum(row["rank"] is None for row in results)
    result["constraint_failure_scenarios"] = sum(bool(row["constraint_failures"]) for row in results)
    result["errors"] = sum("error" in row for row in results)
    elapsed = sorted(row["elapsed_ms"] for row in results)
    if elapsed:
        result["median_ms"] = round(statistics.median(elapsed), 3)
        result["p95_ms"] = round(elapsed[max(0, math.ceil(len(elapsed) * 0.95) - 1)], 3)
        result["maximum_ms"] = round(elapsed[-1], 3)
    return result


def check_candidates(row: dict, candidates, *, offset: int = 0) -> None:
    requested = row["expected_reading"].split()
    for index, candidate in enumerate(candidates, offset + 1):
        if candidate.consumed_input != len(row["input"]):
            row["constraint_failures"].append({"rank": index, "reason": "consumed_input", "text": candidate.text})
        if row["variant"] == "fully_toned" and candidate.reading.split()[:len(requested)] != requested:
            row["constraint_failures"].append({"rank": index, "reason": "fully_toned_reading_prefix", "text": candidate.text,
                                               "actual_reading": candidate.reading})


def page_recovery(engine: Engine, row: dict) -> dict:
    """Walk public pages, preserving the original first-90 ranking metrics."""
    started = time.perf_counter()
    offset = 0
    requested_offsets = []
    seen_candidates = 0
    truncated = False
    outcome = {}
    # The API has an explicit maximum offset; a second finite guard makes
    # checker termination independent of a malformed/nonadvancing response.
    for _ in range(114):
        requested_offsets.append(offset)
        try:
            page = engine.lookup_page(row["input"], offset=offset, page_size=90, mode="jyutping")
        except PaginationCapacityError as error:
            outcome = {"status": "capacity_limited", "reason": str(error)}
            break
        except Exception as error:
            outcome = {"status": "error", "error": f"{type(error).__name__}: {error}"}
            break
        truncated |= page.completion_truncated
        check_candidates(row, page.candidates, offset=offset)
        seen_candidates += len(page.candidates)
        matches = [offset + index for index, candidate in enumerate(page.candidates, 1)
                   if candidate.text == row["expected_text"] and
                   (row["variant"] == "tone_free" or candidate.reading == row["expected_reading"])]
        if matches:
            outcome = {"status": "found", "rank": matches[0], "after_first90": matches[0] > 90}
            break
        if page.next_offset is None:
            outcome = {"status": "exhausted", "reason": "Public pagination reported no further candidates."}
            break
        if page.next_offset <= offset:
            outcome = {"status": "error", "error": "Nonadvancing next_offset from lookup_page."}
            break
        offset = page.next_offset
    else:
        outcome = {"status": "error", "error": "Checker's finite 114-request pagination guard was reached."}
    return {**outcome, "requested_offsets": requested_offsets, "candidates_inspected": seen_candidates,
            "completion_pool_truncated": truncated,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}


def evaluate_scenario(engine: Engine, case: dict, variant: str) -> dict:
    raw = case[variant + "_input"]
    row = {"case_id": case["id"], "origin": case["origin"], "variant": variant,
           "input": raw, "expected_text": case["text"], "expected_reading": case["reading"],
           "rank": None, "text_rank": None, "constraint_failures": []}
    started = time.perf_counter()
    try:
        candidates = engine.lookup(raw, limit=90, mode="jyutping")
        row["candidate_count"] = len(candidates)
        for rank, candidate in enumerate(candidates, 1):
            if candidate.text == case["text"]:
                if row["text_rank"] is None:
                    row["text_rank"] = rank
                if row["rank"] is None and (variant == "tone_free" or candidate.reading == case["reading"]):
                    row["rank"] = rank
        check_candidates(row, candidates)
        row["first9"] = [{"text": c.text, "reading": c.reading, "match_type": c.match_type} for c in candidates[:9]]
    except Exception as error:
        row["error"] = f"{type(error).__name__}: {error}"
    row["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    if row["rank"] is None and "error" not in row:
        row["page_recovery"] = page_recovery(engine, row)
        if row["page_recovery"]["status"] == "error":
            row["error"] = row["page_recovery"]["error"]
    return row


def crowded_regression_cases(database: Path) -> list[tuple[dict, str]]:
    """Known historical pool misses, separate from the hash-sampled corpus."""
    targets = (("賁", "fan", "tone_free"), ("粪", "fan", "tone_free"),
               ("褛", "lau", "tone_free"), ("铌", "lei4", "fully_toned"), ("铌", "lei", "tone_free"))
    cases = []
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        for text, raw, variant in targets:
            base = re.sub("[1-6]", "", raw)
            found = connection.execute(
                "SELECT reading,origin,source FROM entries WHERE text=? AND base_reading=? ORDER BY weight DESC,reading LIMIT 1",
                (text, base)).fetchone()
            if found is None:
                raise ValueError(f"Known crowded regression target {text!r}/{raw!r} is missing from the current dictionary")
            reading, origin, source = found
            if variant == "fully_toned" and "".join(reading.split()) != raw:
                raise ValueError("Known fully toned regression no longer has the requested reading")
            cases.append(({"id": "historical-crowding-" + hashlib.sha256((text + "\0" + raw).encode()).hexdigest()[:16],
                           "text": text, "reading": reading, "origin": origin, "source": source,
                           variant + "_input": raw}, variant))
    return cases


def recovery_summary(results: list[dict]) -> dict:
    recovered = [row["page_recovery"] for row in results if "page_recovery" in row]
    return {"first90_misses_probed": len(recovered),
            "recovered_on_later_pages": sum(row["status"] == "found" and row["after_first90"] for row in recovered),
            "capacity_limited": sum(row["status"] == "capacity_limited" for row in recovered),
            "exhausted_without_target": sum(row["status"] == "exhausted" for row in recovered),
            "errors": sum(row["status"] == "error" for row in recovered)}


def selected_source_regression_cases(database: Path) -> tuple[list[dict], list[str]]:
    """Freeze concrete new-source lookups separately from the hash sample."""
    targets = [("返到", "faan1 dou3", "typeduck:principal")]
    targets.extend((text, reading, "unihan:kCantonese") for text, reading in (
        ("乄", "ngau1"), ("乊", "fu4"), ("乛", "waang4"), ("纟", "mik6"),
        ("覀", "sai1"), ("讠", "jin4"), ("钅", "gam1"), ("阝", "fau6"),
        ("饣", "sik6"), ("𠃍", "waang4"), ("𠃑", "saam1")))
    cases = []
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        sources = {row[0] for row in connection.execute("SELECT DISTINCT source FROM entries")}
        unavailable = sorted({source for _, _, source in targets} - sources)
        for text, reading, source in targets:
            if source not in sources:
                continue
            found = connection.execute("SELECT origin,source FROM entries WHERE text=? AND reading=?", (text, reading)).fetchone()
            cases.append({"id": "selected-source-" + hashlib.sha256((source + "\0" + text + "\0" + reading).encode()).hexdigest()[:16],
                          "text": text, "reading": reading, "origin": found[0] if found else "supplement",
                          "source": source, "stored_pair_exists": found is not None,
                          "actual_stored_source": found[1] if found else None,
                          "fully_toned_input": "".join(reading.split()),
                          "source_provisional": source == "unihan:kCantonese"})
    return cases, unavailable


def evaluate(database: Path, corpus_path: Path) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    corpus_hash = file_sha256(corpus_path)
    database_hash = file_sha256(database)
    if corpus["database_sha256"] != database_hash:
        raise ValueError("Corpus database hash differs; collect again with --refresh-corpus")
    total = sum(1 + bool(case["include_tone_free"]) for case in corpus["cases"])
    results = []
    regression_results = []
    selected_source_results = []
    start = time.perf_counter()
    with Engine(database, mode="jyutping") as engine:
        startup_ms = (time.perf_counter() - start) * 1000
        for case in corpus["cases"]:
            for variant in (["fully_toned", "tone_free"] if case["include_tone_free"] else ["fully_toned"]):
                results.append(evaluate_scenario(engine, case, variant))
                if len(results) % 100 == 0 or len(results) == total:
                    print(json.dumps({"progress": len(results), "total": total}), file=sys.stderr, flush=True)
        for case, variant in crowded_regression_cases(database):
            row = evaluate_scenario(engine, case, variant)
            row["regression_purpose"] = "Historical fixed-pool miss retained independently of the current hash sample; database-derived, not held-out."
            regression_results.append(row)
        selected_cases, unavailable_sources = selected_source_regression_cases(database)
        for case in selected_cases:
            row = evaluate_scenario(engine, case, "fully_toned")
            row.update({"source": case["source"], "source_provisional": case["source_provisional"],
                        "actual_stored_source": case["actual_stored_source"],
                        "regression_purpose": "Selected source pair reachability, not independently reviewed pronunciation; provisional Unihan is direct-character lookup only and excluded from phrase translation."})
            if not case["stored_pair_exists"]:
                row["error"] = "Selected source regression pair is absent from the current dictionary."
            selected_source_results.append(row)
    # Explain misses against the underlying oracle without pretending a fixed
    # publication pool is a missing dictionary entry or a linguistic judgment.
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        for row in results + regression_results + selected_source_results:
            if row["rank"] is not None:
                continue
            base = " ".join(token[:-1] for token in row["expected_reading"].split())
            pool = connection.execute(
                "SELECT text,reading,weight FROM entries WHERE base_reading=? ORDER BY weight DESC,text,reading", (base,)
            ).fetchall()
            if row["variant"] == "fully_toned":
                pool = [entry for entry in pool if entry[1] == row["expected_reading"]]
            expected_rank = next((index for index, entry in enumerate(pool, 1)
                                  if entry[0] == row["expected_text"]), None)
            row["oracle_pool"] = {
                "matching_dictionary_pairs": len(pool),
                "expected_text_pair_rank_by_frequency": expected_rank,
                "candidate_limit": 90,
                "diagnosis": "frequency_order_beyond_candidate_pool" if expected_rank and expected_rank > 90
                             else "requires_decoder_review",
            }
    observed_hashes = {name: file_sha256(PROJECT_ROOT / name) for name in RUNTIME_SOURCE_HASHES}
    if observed_hashes != RUNTIME_SOURCE_HASHES:
        raise ValueError("Engine, mapping or check-tool source changed during this run; rerun against a stable revision")
    if file_sha256(database) != database_hash or file_sha256(corpus_path) != corpus_hash:
        raise ValueError("Database or corpus changed during this run; rerun against stable artifacts")
    groups = {}
    for origin in ("explicit", "supplement", "generated"):
        for variant in ("fully_toned", "tone_free"):
            group = [row for row in results if row["origin"] == origin and row["variant"] == variant]
            groups[origin + ":" + variant] = summarize(group)
    return {
        "schema_version": 2,
        "purpose": corpus["purpose"],
        "interpretation": "Stored-entry reachability and ranking against the same source database. Success does not verify pronunciations; failures may reflect finite candidate pools or decoder pruning. Not a held-out accuracy estimate.",
        "database_sha256": database_hash,
        "corpus_sha256": corpus_hash,
        "runtime_source_sha256": RUNTIME_SOURCE_HASHES,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "case_count": corpus["case_count"],
        "mode": "jyutping", "candidate_limit": 90, "learning": False,
        "rank_policy": "Fully toned requires expected text AND exact stored reading; tone-free requires expected text and permits its other readings.",
        "constraint_policy": "Every fully toned candidate must start with the requested canonical syllables/tones; completions may append syllables. All candidates consume the complete raw input.",
        "engine_startup_ms": round(startup_ms, 3),
        "summary": summarize(results),
        "pagination_recovery": recovery_summary(results),
        "pagination_policy": "First-90 rankings are unchanged by later-page probes. Missing targets are sought through lookup_page(page_size=90) until found, explicitly capacity-limited, or exhausted; a finite checker guard prevents a nonadvancing loop. Page reachability is not pronunciation accuracy.",
        "crowded_homophone_regressions": {"summary": summarize(regression_results),
                                          "pagination_recovery": recovery_summary(regression_results),
                                          "results": regression_results},
        "selected_source_regressions": {"summary": summarize(selected_source_results),
                                         "pagination_recovery": recovery_summary(selected_source_results),
                                         "unavailable_sources": unavailable_sources,
                                         "results": selected_source_results},
        "strata": groups,
        "failures": [row for row in results if row["rank"] is None or row["constraint_failures"] or "error" in row],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "eval/source_coverage_cases.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs/dictionary-lookup-coverage.json")
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--refresh-corpus", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_corpus or not args.corpus.is_file():
        corpus = collect_cases(args.database, args.sample_size)
        write_json(args.corpus, corpus)
    if args.collect_only:
        corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
        print(json.dumps({"case_count": corpus["case_count"], "database_sha256": corpus["database_sha256"], "strata": corpus["strata"]}, indent=2))
        return 0
    report = evaluate(args.database, args.corpus)
    write_json(args.output, report)
    print(json.dumps({"database_sha256": report["database_sha256"], "corpus_sha256": report["corpus_sha256"],
                      "summary": report["summary"], "strata": report["strata"],
                      "pagination_recovery": report["pagination_recovery"],
                      "crowded_homophone_regressions": {key: value for key, value in report["crowded_homophone_regressions"].items() if key != "results"},
                      "selected_source_regressions": {key: value for key, value in report["selected_source_regressions"].items() if key != "results"}}, ensure_ascii=False, indent=2, sort_keys=True))
    # The report records misses honestly; source-derived ranking misses are not
    # asserted to be process/test failures. Exceptions and constraint violations are.
    regression_summary = report["crowded_homophone_regressions"]["summary"]
    selected_summary = report["selected_source_regressions"]["summary"]
    return 1 if (report["summary"]["errors"] or report["summary"]["constraint_failure_scenarios"] or
                 regression_summary["errors"] or regression_summary["constraint_failure_scenarios"] or
                 selected_summary["errors"] or selected_summary["constraint_failure_scenarios"]) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Dictionary lookup check failed: {error}", file=sys.stderr)
        raise SystemExit(1)
