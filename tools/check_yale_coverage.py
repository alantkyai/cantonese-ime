"""Read-only Yale input coverage audit, independent of the converter's tables.

All dictionary text/reading pairs are accounted mechanically. Deterministic
dictionary-derived lookup samples measure visible retrieval separately; neither
count is held-out linguistic accuracy or a native Windows typing result.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import heapq
import json
from pathlib import Path
import platform
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime import CompositionCapacityError, Engine, PaginationCapacityError
from cantonese_ime import mappings

TOKEN = re.compile(r"([a-z]+)([1-6])\Z", re.ASCII)
STATUSES = {"table", "extension", "jyutping_fallback"}
GUARDED = ("cantonese_ime/engine.py", "cantonese_ime/mappings.py", "cantonese_ime/__init__.py",
           "tools/check_yale_coverage.py", "eval/yale_expected.json")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def report_output(path: Path, database: Path, fixture: Path) -> Path:
    target = path.resolve()
    relative = target.relative_to(ROOT)
    if (not relative.parts or relative.parts[0] not in {"docs", ".local"} or target.suffix.lower() != ".json"
            or target in {database.resolve(), fixture.resolve()}):
        raise ValueError("Output must be a separate JSON report under docs or .local")
    return target


def reference_rows(fixture: dict):
    for group in ("final_grid", "onset_grid", "compound_grid", "extension_grid"):
        for base, spelling in fixture[group]:
            yield {"group": group, "canonical": base, "spelling": spelling,
                   "status": "extension" if group == "extension_grid" else "table"}
    for base in fixture["fallback_grid"]:
        yield {"group": "fallback_grid", "canonical": base, "spelling": base, "status": "jyutping_fallback"}


def mapping_probe(base: str, api=mappings) -> dict:
    """Exercise public conversion, aliases, strict identity and inverse APIs."""
    route = api.yale_ascii_mapping(base)
    spelling = api.yale_ascii(base)
    errors = []
    if route.canonical != base or route.spelling != spelling or route.status not in STATUSES:
        errors.append("converter_metadata_disagrees")
    if not isinstance(spelling, str) or not re.fullmatch("[a-z]+", spelling, re.ASCII):
        errors.append("non_ascii_or_empty_spelling")
    if spelling not in api.spelling_variants(base, mode="forgiving"):
        errors.append("missing_public_forgiving_alias")
    if api.spelling_variants(base, mode="jyutping") != {base: 0.0}:
        errors.append("strict_identity_changed")
    resolved = api.resolve_syllable(spelling, [base], mode="forgiving")
    if not any(item.canonical == base and item.tone is None for item in resolved):
        errors.append("untoned_inverse_lost")
    if spelling != base and any(item.canonical == base for item in api.resolve_syllable(spelling, [base], mode="jyutping")):
        errors.append("strict_mode_accepts_yale_alias")
    return {"canonical": base, "spelling": spelling, "status": route.status,
            "reason": getattr(route, "reason", None), "source": getattr(route, "source", None), "errors": errors}


def audit_reference(fixture: dict, api=mappings) -> dict:
    results = []
    for expected in reference_rows(fixture):
        actual = mapping_probe(expected["canonical"], api)
        errors = list(actual["errors"])
        if actual["spelling"] != expected["spelling"]:
            errors.append("independent_expected_spelling_mismatch")
        if actual["status"] != expected["status"]:
            errors.append("independent_expected_status_mismatch")
        results.append({"expected": expected, "actual": actual, "passed": not errors, "errors": errors})
    return {"checks": len(results), "passed": bool(results) and all(row["passed"] for row in results), "results": results}


def _length_bucket(count: int) -> str:
    return "1" if count == 1 else "2" if count == 2 else "3-4" if count <= 4 else "5-8" if count <= 8 else "9+"


def audit_dictionary(connection: sqlite3.Connection, *, sample_size: int, input_limit: int, api=mappings) -> dict:
    """Stream every pair; bound the sample heap rather than materialize the DB."""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(entries)")}
    origin_sql = "origin" if "origin" in columns else "'unspecified'"
    probes, tones, occurrences = {}, defaultdict(set), Counter()
    counts, routes, lengths = Counter(), Counter(), Counter()
    pair_errors, invalid_rows, heaps = [], [], defaultdict(list)
    max_lengths = {"compact": 0, "apostrophe": 0, "numeric_tones": 0}
    for text, reading, source, origin in connection.execute(f"SELECT text,reading,source,{origin_sql} FROM entries ORDER BY text,reading"):
        counts["dictionary_pairs"] += 1
        parsed = [TOKEN.fullmatch(token) for token in reading.split()]
        if not parsed or any(item is None for item in parsed):
            counts["invalid_reading_pairs"] += 1
            if len(invalid_rows) < 30:
                invalid_rows.append({"text": text, "reading": reading})
            continue
        components, statuses, failed = [], [], False
        for item in parsed:
            base, tone = item.groups()
            if base not in probes:
                probes[base] = mapping_probe(base, api)
                probes[base]["numeric_tone_errors"] = []
            probe = probes[base]
            if tone not in tones[base]:
                inverse = api.resolve_syllable(probe["spelling"] + tone, [base], mode="forgiving")
                if not any(match.canonical == base and match.tone == tone for match in inverse):
                    probe["numeric_tone_errors"].append(tone)
                tones[base].add(tone)
            components.append(probe["spelling"])
            statuses.append(probe["status"])
            occurrences[base] += 1
            failed |= bool(probe["errors"]) or tone in probe["numeric_tone_errors"]
        counts["reading_syllable_occurrences"] += len(parsed)
        if failed:
            counts["pairs_with_public_mapping_failure"] += 1
            if len(pair_errors) < 30:
                pair_errors.append({"text": text, "reading": reading})
        else:
            counts["pairs_with_lossless_input_route"] += 1
        route = ("invalid" if any(status not in STATUSES for status in statuses) else
                 "jyutping_fallback" if "jyutping_fallback" in statuses else "extension" if "extension" in statuses else "table")
        routes[route] += 1
        compact, boundary = "".join(components), "'".join(components)
        for form, length in (("compact", len(compact)), ("apostrophe", len(boundary)), ("numeric_tones", len(compact) + len(parsed))):
            max_lengths[form] = max(max_lengths[form], length)
            lengths[form + ("_within_limit" if length <= input_limit else "_over_limit")] += 1
        if len(compact) > input_limit:
            counts["sample_pairs_excluded_by_input_limit"] += 1
            continue
        if sample_size:
            identity = hashlib.sha256((text + "\t" + reading).encode()).hexdigest()
            case = {"id": identity[:20], "text": text, "reading": reading, "source": source, "origin": origin,
                    "route": route, "compact": compact, "apostrophe": boundary, "selection_hash": identity}
            group = (source, origin, _length_bucket(len(parsed)))
            entry = (-int(identity, 16), text, reading, case)
            pool = heaps[group]
            if len(pool) < sample_size:
                heapq.heappush(pool, entry)
            elif entry[:3] > pool[0][:3]:
                heapq.heapreplace(pool, entry)
    pools = {group: [entry[3] for entry in sorted(pool, key=lambda entry: -entry[0])]
             for group, pool in heaps.items()}
    selected = []
    while len(selected) < sample_size:
        changed = False
        for group in sorted(pools):
            if pools[group] and len(selected) < sample_size:
                selected.append(pools[group].pop(0)); changed = True
        if not changed:
            break
    collisions = []
    by_spelling = defaultdict(list)
    for base, probe in probes.items():
        by_spelling[probe["spelling"]].append(base)
    collision_failures = []
    for spelling, bases in sorted(by_spelling.items()):
        if len(bases) > 1:
            resolved = {match.canonical for match in api.resolve_syllable(spelling, sorted(probes), mode="forgiving")}
            missing = sorted(set(bases) - resolved)
            collisions.append({"spelling": spelling, "canonical_targets": sorted(bases), "missing": missing})
            collision_failures.extend({"spelling": spelling, "canonical": base} for base in missing)
    base_rows = [dict(probe, observed_tones=sorted(tones[base]), dictionary_syllable_occurrences=occurrences[base])
                 for base, probe in sorted(probes.items())]
    counts["distinct_dictionary_bases"] = len(probes)
    counts["distinct_dictionary_toned_syllables"] = sum(map(len, tones.values()))
    counts["bases_with_public_mapping_failure"] = sum(bool(row["errors"] or row["numeric_tone_errors"]) for row in base_rows)
    for key in ("dictionary_pairs", "invalid_reading_pairs", "pairs_with_public_mapping_failure", "pairs_with_lossless_input_route",
                "reading_syllable_occurrences", "sample_pairs_excluded_by_input_limit"):
        counts.setdefault(key, 0)
    for form in ("compact", "apostrophe", "numeric_tones"):
        for limit in ("within_limit", "over_limit"):
            lengths.setdefault(form + "_" + limit, 0)
    for status in sorted(STATUSES):
        routes.setdefault(status, 0)
    return {"counts": dict(counts), "pairs_by_spelling_route": dict(routes), "input_lengths": dict(lengths),
            "maximum_input_lengths": max_lengths, "input_limit": input_limit,
            "base_route_counts": dict(Counter(row["status"] for row in base_rows)),
            "all_public_routes_lossless": bool(counts["dictionary_pairs"]) and not counts["invalid_reading_pairs"] and not counts["pairs_with_public_mapping_failure"] and not collision_failures,
            "all_pairs_have_table_backed_yale": bool(counts["dictionary_pairs"]) and routes["table"] == counts["dictionary_pairs"],
            "unverified_yale_fallbacks": [row for row in base_rows if row["status"] == "jyutping_fallback"],
            "supplementary_extensions": [row for row in base_rows if row["status"] == "extension"],
            "base_results": base_rows, "invalid_reading_examples": invalid_rows, "mapping_failure_examples": pair_errors,
            "same_yale_spelling_collisions": collisions, "collision_failures": collision_failures,
            "sample_selection": {"method": "SHA256(text TAB reading), round-robin across source/origin/syllable-length strata; selected before engine scoring, no ranking-driven filter.",
                "requested": sample_size, "selected": len(selected), "sha256": json_digest(selected), "cases": selected}}


def probe_lookup(engine, raw: str, text: str, *, mode: str = "forgiving", max_pages: int = 128) -> dict:
    if len(raw) > engine.MAX_INPUT_LENGTH:
        return {"status": "input_limit_excluded", "input": raw, "input_length": len(raw), "input_limit": engine.MAX_INPUT_LENGTH}
    offset, seen, pages = 0, set(), 0
    while pages < max_pages:
        try:
            page = engine.lookup_page(raw, offset=offset, page_size=90, mode=mode)
        except (PaginationCapacityError, CompositionCapacityError) as error:
            return {"status": "capacity_limited", "input": raw, "visible_candidates": len(seen), "pages": pages,
                    "error_type": type(error).__name__, "error": str(error)}
        texts = [candidate.text for candidate in page.candidates]
        if (page.offset != offset or len(texts) != len(set(texts)) or any(text in seen for text in texts)
                or any(candidate.consumed_input != len(raw) for candidate in page.candidates)):
            raise ValueError("Inconsistent pager offset or duplicate text")
        pages += 1
        for index, candidate in enumerate(page.candidates):
            seen.add(candidate.text)
            if candidate.text == text:
                rank = offset + index + 1
                return {"status": "found", "input": raw, "rank": rank, "within_top9": rank <= 9, "within_top90": rank <= 90,
                        "reading": candidate.reading, "match_type": candidate.match_type, "consumed_input": candidate.consumed_input,
                        "candidate_pool_truncated": page.completion_truncated, "pages": pages}
        if page.next_offset is None:
            return {"status": "absent_from_returned_pool", "input": raw, "visible_candidates": len(seen), "pages": pages}
        if page.next_offset <= offset or page.next_offset != offset + len(page.candidates):
            raise ValueError("Pager did not make exact visible progress")
        if page.next_offset > engine.MAX_OFFSET:
            return {"status": "offset_limit", "input": raw, "visible_candidates": len(seen), "pages": pages}
        offset = page.next_offset
    return {"status": "audit_page_budget", "input": raw, "visible_candidates": len(seen), "pages": pages}


def exercise_lookups(engine, selection: list[dict], word_cases: list[dict], *, max_pages: int) -> dict:
    results = []
    for case in selection:
        for form in ("compact", "apostrophe"):
            outcome = probe_lookup(engine, case[form], case["text"], max_pages=max_pages)
            results.append({"case": case, "form": form, "outcome": outcome,
                            "visible_reading_equals_source": outcome.get("reading") == case["reading"] if outcome["status"] == "found" else None})
    examples = []
    for case in word_cases:
        raw = "".join(case["input"].split())
        examples.append({"case": case, "outcome": probe_lookup(engine, raw, case["text"], max_pages=max_pages)})
    summary = Counter()
    for row in results:
        outcome = row["outcome"]
        summary[row["form"] + ":" + outcome["status"]] += 1
        if outcome["status"] == "found":
            summary[row["form"] + ":top9"] += outcome["within_top9"]
            summary[row["form"] + ":top90"] += outcome["within_top90"]
            summary[row["form"] + ":later_page"] += not outcome["within_top90"]
    return {"configuration": {"mode": "forgiving", "prefer_yale": engine.prefer_yale,
                              "learning_enabled": engine.learning_path is not None},
            "summary": dict(summary), "dictionary_sample_results": results, "fixed_word_examples": examples,
            "fixed_word_examples_all_retrieved": all(row["outcome"]["status"] == "found" for row in examples),
            "scope": "Dictionary-derived diagnostics, not independent linguistic accuracy. Text dedup can choose a different legitimate reading; exact source reading visibility is recorded separately."}


def run(database: Path, fixture_path: Path, *, sample_size: int = 200, max_pages: int = 128) -> dict:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    before = {name: digest(ROOT / name) for name in GUARDED}
    before["dictionary"] = digest(database)
    before["selected_fixture"] = digest(fixture_path)
    reference = audit_reference(fixture)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        coverage = audit_dictionary(connection, sample_size=sample_size, input_limit=Engine.MAX_INPUT_LENGTH)
    frozen_at = datetime.now(timezone.utc).isoformat()
    with Engine(database, learning_path=None) as engine:
        lookups = exercise_lookups(engine, coverage["sample_selection"]["cases"], fixture["word_cases"], max_pages=max_pages)
    after = {name: digest(ROOT / name) for name in GUARDED}
    after["dictionary"] = digest(database)
    after["selected_fixture"] = digest(fixture_path)
    if before != after:
        raise RuntimeError("Dictionary, fixture or implementation changed during audit; report is not current evidence")
    return {"schema_version": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "passed_mechanical_mapping": reference["passed"] and coverage["all_public_routes_lossless"],
            "all_dictionary_pairs_formal_yale": coverage["all_pairs_have_table_backed_yale"],
            "full_typing_or_linguistic_acceptance": False, "implementation_sha256": before,
            "python_version": platform.python_version(), "sqlite_version": sqlite3.sqlite_version,
            "reference": reference, "dictionary_coverage": coverage, "real_engine_lookups": lookups,
            "sample_frozen_before_engine_queries_at_utc": frozen_at, "sources": fixture["sources"],
            "limitations": ["ASCII aliases omit Yale tonal diacritics and low-register h; they are an input convention.",
                "Table-backed spellings, supplementary extensions and canonical Jyutping fallbacks are separate counts.",
                "Per-syllable route coverage does not prove every concatenated word appears within a bounded ranked candidate pool.",
                "Input limits, ambiguous segmentations, text/reading dedup and explicit capacity outcomes are reported separately.",
                "No learning writes, dictionary edits, linguistic review or native Windows typing tests are performed."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, default=ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "eval/yale_expected.json")
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--max-pages", type=int, default=128)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 0 <= args.sample_size <= 1000 or not 1 <= args.max_pages <= 128:
        parser.error("sample-size must be 0..1000 and max-pages 1..128")
    target = report_output(args.output, args.dictionary, args.fixtures) if args.output else None
    report = run(args.dictionary, args.fixtures, sample_size=args.sample_size, max_pages=args.max_pages)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(json.dumps({"output": str(target), "passed_mechanical_mapping": report["passed_mechanical_mapping"],
            "all_dictionary_pairs_formal_yale": report["all_dictionary_pairs_formal_yale"],
            "dictionary_pairs": report["dictionary_coverage"]["counts"]["dictionary_pairs"],
            "sample_lookup_summary": report["real_engine_lookups"]["summary"]}, indent=2))
    else:
        print(text, end="")
    return 0 if report["passed_mechanical_mapping"] else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
