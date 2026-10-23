"""Check stored long-phrase reachability from bounded source-derived inputs.

Completion reachability is distinct from fully typing an over-cap reading and
from linguistic accuracy. This opens the dictionary read-only and uses public
Engine lookup/pagination APIs without learning or source modifications.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import platform
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


VERSION = "long-input-source-coverage-v1"
PAGE_SIZE = 90
MAX_PAGE_REQUESTS = 114


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def collect_entries(database: Path, cap: int) -> list[dict]:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(
            "SELECT id,text,reading,base_reading,origin,source,weight FROM entries "
            "WHERE length(replace(reading,' ',''))>? OR length(replace(base_reading,' ',''))>? ORDER BY text,reading", (cap, cap))]
    for row in rows:
        syllables = row["reading"].split()
        if not syllables or any(not re.fullmatch(r"[a-z]+[1-6]", token) for token in syllables):
            raise ValueError("Stored long entry has an unsupported canonical reading")
        bases = [token[:-1] for token in syllables]
        if row["base_reading"] != " ".join(bases):
            raise ValueError("Stored base reading disagrees with toned reading")
        row["case_id"] = hashlib.sha256((row["text"] + "\0" + row["reading"]).encode("utf-8")).hexdigest()[:24]
        row["fully_toned_length"] = len("".join(syllables))
        row["tone_free_length"] = len("".join(bases))
        row["syllable_count"] = len(syllables)
    return rows


def make_query(entry: dict, variant: str, cap: int) -> dict:
    toned = variant == "fully_toned_compact"
    boundary = variant == "tone_free_boundary"
    tokens = entry["reading"].split()
    if not toned:
        tokens = [token[:-1] for token in tokens]
    separator = "'" if boundary else ""
    count = 0
    for length in range(1, len(tokens) + 1):
        if len(separator.join(tokens[:length])) > cap:
            break
        count = length
    raw = separator.join(tokens[:count])
    if not raw:
        raise ValueError("No complete canonical syllable fits the input limit")
    return {"variant": variant, "input": raw, "input_length": len(raw),
            "full_variant_length": len(separator.join(tokens)), "prefix_syllables": count,
            "prefix_reading": " ".join(entry["reading"].split()[:count]),
            "completion_required": count < len(tokens),
            "input_policy": "Longest whole-syllable prefix fitting the cap; use the full reading when this variant fits."}


def inspect_candidates(row: dict, candidates, *, offset: int = 0) -> None:
    expected = row["prefix_reading"].split()
    bases = [token[:-1] for token in expected]
    for index, candidate in enumerate(candidates, offset + 1):
        if candidate.text == row["expected_text"]:
            if row["text_rank"] is None:
                row["text_rank"] = index
                row["returned_reading_for_target_text"] = candidate.reading
                actual = candidate.reading.split()
                target = row["expected_reading"].split()
                difference = next((position for position, (left, right) in enumerate(zip(target, actual)) if left != right), None)
                if difference is not None:
                    length_to_difference = len("".join(target[:difference + 1]))
                    row["target_reading_difference"] = {
                        "first_different_syllable": difference + 1,
                        "target_syllable": target[difference], "returned_syllable": actual[difference],
                        "canonical_toned_length_through_difference": length_to_difference,
                        "difference_after_supplied_syllable_prefix": difference >= row["prefix_syllables"],
                        "canonical_toned_difference_beyond_input_cap": length_to_difference > Engine.MAX_INPUT_LENGTH,
                    }
            if candidate.reading == row["expected_reading"] and row["pair_rank"] is None:
                row["pair_rank"] = index
        reasons = []
        readings = candidate.reading.split()
        candidate_bases = [token[:-1] for token in readings]
        if candidate.consumed_input != row["input_length"]:
            reasons.append("consumed_input")
        if row["variant"] == "fully_toned_compact":
            if readings[:len(expected)] != expected:
                reasons.append("fully_toned_prefix_mismatch")
        elif row["variant"] == "tone_free_boundary":
            # The current grammar allows multiple untoned syllables inside one
            # chunk. A boundary must be a candidate syllable end, but need not
            # make the whole preceding chunk an indivisible syllable.
            endings = set()
            length = 0
            for base in candidate_bases:
                length += len(base)
                endings.add(length)
            boundaries = set()
            length = 0
            for chunk in row["input"].split("'")[:-1]:
                length += len(chunk)
                boundaries.add(length)
            if not "".join(candidate_bases).startswith(row["input"].replace("'", "")) or not boundaries <= endings:
                reasons.append("explicit_boundary_prefix_mismatch")
        elif not "".join(candidate_bases).startswith(row["input"]):
            reasons.append("tone_free_compact_prefix_mismatch")
        for reason in reasons:
            row["constraint_failure_count"] += 1
            if len(row["constraint_failures"]) < 25:
                row["constraint_failures"].append({"rank": index, "reason": reason,
                                                   "text": candidate.text, "reading": candidate.reading})


def evaluate_query(engine: Engine, entry: dict, query: dict, mode: str) -> dict:
    row = {**query, "case_id": entry["case_id"], "origin": entry["origin"], "source": entry["source"],
           "expected_text": entry["text"], "expected_reading": entry["reading"],
           "pair_rank": None, "text_rank": None, "returned_reading_for_target_text": None,
           "constraint_failure_count": 0, "constraint_failures": [], "requested_offsets": [],
           "completion_pool_truncated": None, "page_candidates_inspected": 0}
    started = time.perf_counter()
    try:
        initial = engine.lookup(row["input"], limit=90, mode=mode)
        row["first90_candidate_count"] = len(initial)
        inspect_candidates(row, initial)
        row["first90_pair_rank"] = row["pair_rank"]
        row["first90_text_rank"] = row["text_rank"]
        row["first9"] = [{"text": candidate.text, "reading": candidate.reading,
                           "match_type": candidate.match_type} for candidate in initial[:9]]
    except Exception as error:
        row["error"] = f"{type(error).__name__}: {error}"
        row["status"] = "lookup_error"
    row["initial_elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    page_started = time.perf_counter()
    if "error" not in row:
        if row["pair_rank"] is not None:
            row["status"] = "found_first90"
        else:
            offset = 0
            for _ in range(MAX_PAGE_REQUESTS):
                row["requested_offsets"].append(offset)
                try:
                    page = engine.lookup_page(row["input"], offset=offset, page_size=PAGE_SIZE, mode=mode)
                except PaginationCapacityError as error:
                    row["status"] = "capacity_limited"
                    row["capacity_error"] = str(error)
                    break
                except Exception as error:
                    row["status"] = "pagination_error"
                    row["error"] = f"{type(error).__name__}: {error}"
                    break
                if offset == 0 and list(page.candidates) != initial:
                    row["status"] = "pagination_error"
                    row["error"] = "Public page0 differs from the legacy first90 lookup."
                    break
                row["completion_pool_truncated"] = bool(row["completion_pool_truncated"] or page.completion_truncated)
                row["page_candidates_inspected"] += len(page.candidates)
                inspect_candidates(row, page.candidates, offset=offset)
                if row["pair_rank"] is not None:
                    row["status"] = "found_later_page"
                    break
                if page.next_offset is None:
                    row["status"] = "exhausted"
                    break
                if page.next_offset <= offset:
                    row["status"] = "pagination_error"
                    row["error"] = "Nonadvancing public pagination offset."
                    break
                offset = page.next_offset
            else:
                row["status"] = "pagination_error"
                row["error"] = "Finite checker pagination guard reached."
    row["page_probe_elapsed_ms"] = round((time.perf_counter() - page_started) * 1000, 3)
    row["target_text_accessible"] = row["text_rank"] is not None
    row["exact_stored_pair_accessible"] = row["pair_rank"] is not None
    row["text_only_different_reading"] = row["text_rank"] is not None and row["pair_rank"] is None
    return row


def oracle_diagnostic(connection: sqlite3.Connection, row: dict) -> dict:
    tokens = row["prefix_reading"].split()
    base = " ".join(token[:-1] for token in tokens)
    if row["completion_required"]:
        prefix = base + " "
        pool = connection.execute(
            "SELECT text,reading,weight FROM entries WHERE base_reading>=? AND base_reading<? ORDER BY weight DESC,text,reading",
            (prefix, prefix + "{"))
    else:
        pool = connection.execute(
            "SELECT text,reading,weight FROM entries WHERE base_reading=? ORDER BY weight DESC,text,reading", (base,))
    matching = []
    for text, reading, weight in pool:
        if row["variant"] != "fully_toned_compact" or reading.split()[:len(tokens)] == tokens:
            matching.append((text, reading, weight))
    rank = next((index for index, (text, reading, _) in enumerate(matching, 1)
                 if text == row["expected_text"] and reading == row["expected_reading"]), None)
    if row["pair_rank"] is not None:
        diagnosis = "reachable_via_completion" if row["completion_required"] else "full_tone_free_input_fits"
    elif row["text_only_different_reading"]:
        diagnosis = "target_text_returned_with_another_reading; displayed_text_dedup_can_hide_other_stored_readings"
    elif row["status"] == "capacity_limited":
        diagnosis = "public_api_advertises_bounded_completion_tail; target_not_reached_before_capacity_error"
    elif "error" in row:
        diagnosis = "unexpected_api_error_requires_review"
    else:
        diagnosis = "stored_canonical_prefix_matches_but_decoder_or_completion_pool_did_not_surface_target"
    return {"canonical_base_prefix": base, "matching_stored_pairs": len(matching),
            "exact_target_pair_rank_by_weight_text_reading": rank,
            "target_is_stored_canonical_prefix_match": rank is not None,
            "rank_exceeds_128_prefix_rows": rank is not None and rank > 128 and row["completion_required"],
            "diagnosis": diagnosis,
            "limit": "This SQL oracle describes the canonical source segmentation, not every ambiguous segmentation or actual decoder query; it does not prove a unique pruning cause."}


def summarize(rows: list[dict]) -> dict:
    elapsed = sorted(row["initial_elapsed_ms"] for row in rows)
    return {"scenarios": len(rows), "exact_pair_first90": sum(row.get("first90_pair_rank") is not None for row in rows),
            "exact_pair_later_page": sum(row["pair_rank"] is not None and row.get("first90_pair_rank") is None for row in rows),
            "target_text_accessible": sum(row["target_text_accessible"] for row in rows),
            "text_only_different_reading": sum(row["text_only_different_reading"] for row in rows),
            "unreached_exact_pairs": sum(row["pair_rank"] is None for row in rows),
            "capacity_limited": sum(row["status"] == "capacity_limited" for row in rows),
            "exhausted": sum(row["status"] == "exhausted" for row in rows),
            "unexpected_errors": sum("error" in row for row in rows),
            "constraint_failure_scenarios": sum(row["constraint_failure_count"] > 0 for row in rows),
            "median_initial_ms": round(statistics.median(elapsed), 3) if elapsed else None,
            "p95_initial_ms": round(elapsed[max(0, math.ceil(len(elapsed) * .95) - 1)], 3) if elapsed else None,
            "maximum_initial_ms": round(max(elapsed), 3) if elapsed else None}


def evaluate(database: Path, mode: str) -> dict:
    cap = Engine.MAX_INPUT_LENGTH
    source_hashes = {name: file_sha256(PROJECT_ROOT / name) for name in (
        "cantonese_ime/engine.py", "cantonese_ime/mappings.py", "tools/check_long_inputs.py")}
    database_hash = file_sha256(database)
    entries = collect_entries(database, cap)
    results = []
    probes = []
    variants = ("fully_toned_compact", "tone_free_compact", "tone_free_boundary")
    total = len(entries) * len(variants)
    with Engine(database, mode=mode) as engine:
        for entry in entries:
            for variant, raw in (("fully_toned_compact", entry["reading"].replace(" ", "")),
                                 ("tone_free_compact", entry["base_reading"].replace(" ", ""))):
                if len(raw) <= cap:
                    continue
                probe = {"case_id": entry["case_id"], "variant": variant, "input_length": len(raw)}
                try:
                    candidates = engine.lookup(raw, limit=90, mode=mode)
                    probe.update({"candidate_count": len(candidates), "over_cap_rejected": not candidates})
                except Exception as error:
                    probe.update({"over_cap_rejected": True, "rejection_exception": f"{type(error).__name__}: {error}"})
                probes.append(probe)
            for variant in variants:
                row = evaluate_query(engine, entry, make_query(entry, variant, cap), mode)
                results.append(row)
                if len(results) % 50 == 0 or len(results) == total:
                    print(json.dumps({"progress": len(results), "total": total}), file=sys.stderr, flush=True)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        for row in results:
            if row["pair_rank"] is None or row["pair_rank"] > 90:
                row["oracle_prefix_pool"] = oracle_diagnostic(connection, row)
    if file_sha256(database) != database_hash or any(file_sha256(PROJECT_ROOT / name) != value for name, value in source_hashes.items()):
        raise ValueError("Database or relevant source changed during the long-input run")
    case_results = []
    for entry in entries:
        rows = [row for row in results if row["case_id"] == entry["case_id"]]
        case_results.append({**entry, "any_exact_pair_accessible": any(row["pair_rank"] is not None for row in rows),
                             "any_target_text_accessible": any(row["text_rank"] is not None for row in rows),
                             "exact_pair_accessible_by_completion": any(row["pair_rank"] is not None and row["completion_required"] for row in rows)})
    tone_free_long_ids = {entry["case_id"] for entry in entries if entry["tone_free_length"] > cap}
    return {"schema_version": 1, "tool_version": VERSION,
            "purpose": "Exhaustive source-derived over-cap stored-entry reachability from bounded prefixes; not independent linguistic accuracy or proof of fully typed over-cap support.",
            "database_sha256": database_hash, "runtime_source_sha256": source_hashes,
            "python_version": platform.python_version(), "platform": platform.platform(), "mode": mode,
            "input_cap": cap, "page_size": PAGE_SIZE, "learning": False,
            "prefix_policy": "Whole canonical syllables only. Three variants: fully toned compact; tone-free compact; tone-free apostrophe boundaries. Use full input if it fits, otherwise the longest whole-syllable prefix <=cap.",
            "rank_policy": "Exact pair requires expected text AND full stored reading; text-only reachability is reported separately. First90 and later pages remain separate.",
            "constraint_policy": "All candidates consume the full bounded input; fully toned readings retain the exact supplied syllable/tone prefix; tone-free candidates retain typed letters. Apostrophe character offsets must coincide with candidate syllable ends; internal untoned splits and final completion remain allowed by the current grammar.",
            "counts": {"over_cap_entries": len(entries), "fully_toned_over_cap": sum(row["fully_toned_length"] > cap for row in entries),
                       "tone_free_over_cap": sum(row["tone_free_length"] > cap for row in entries),
                       "origins": dict(Counter(row["origin"] for row in entries)),
                       "any_exact_pair_accessible": sum(row["any_exact_pair_accessible"] for row in case_results),
                       "any_target_text_accessible": sum(row["any_target_text_accessible"] for row in case_results),
                       "exact_pair_accessible_by_completion": sum(row["exact_pair_accessible_by_completion"] for row in case_results),
                       "neither_pair_nor_text_accessible": sum(not row["any_target_text_accessible"] for row in case_results)},
            "summary": summarize(results),
            "variants": {variant: summarize([row for row in results if row["variant"] == variant]) for variant in variants},
            "tone_free_over_cap_subgroup": {"entries": len(tone_free_long_ids),
                                             "any_exact_pair_accessible": sum(row["any_exact_pair_accessible"] for row in case_results if row["case_id"] in tone_free_long_ids),
                                             "any_target_text_accessible": sum(row["any_target_text_accessible"] for row in case_results if row["case_id"] in tone_free_long_ids),
                                             "variants": {variant: summarize([row for row in results if row["variant"] == variant and row["case_id"] in tone_free_long_ids]) for variant in variants}},
            "literal_over_cap_probe_summary": {"probes": len(probes),
                                                "rejected_with_no_candidates": sum(row.get("candidate_count") == 0 for row in probes),
                                                "rejected_by_exception": sum("rejection_exception" in row for row in probes),
                                                "unexpected_candidate_results": sum(not row["over_cap_rejected"] for row in probes)},
            "literal_over_cap_probes": probes,
            "unresolved": [row for row in results if row["pair_rank"] is None],
            "unresolved_cases": [row for row in case_results if not row["any_exact_pair_accessible"]],
            "cases": case_results, "results": results,
            "limits": ["An accepted shorter input that suggests a long phrase does not allow fully typing an over-cap literal reading.",
                       "Tone-free queries can display the target text with another stored reading; that is not exact-reading recovery.",
                       "A null completion_pool_truncated value means no public page probe was needed, so no pagination flag was observed.",
                       "No capacity/beam limits, frequencies, sources, dictionaries or engine code are changed by this checker."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs/long-input-coverage.json")
    parser.add_argument("--mode", choices=("jyutping", "forgiving"), default="jyutping")
    args = parser.parse_args()
    report = evaluate(args.database, args.mode)
    write_json(args.output, report)
    print(json.dumps({"database_sha256": report["database_sha256"], "counts": report["counts"],
                      "summary": report["summary"], "variants": report["variants"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["summary"]["unexpected_errors"] or report["summary"]["constraint_failure_scenarios"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Long-input check failed: {error}", file=sys.stderr)
        raise SystemExit(1)
