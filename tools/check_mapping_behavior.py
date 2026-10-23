"""Exercise exported spelling relations through the decoder on synthetic data.

Source-observed base/tone sets seed uniquely labelled synthetic targets. This
checks software integration, not human pronunciation, preferred spelling,
ranking quality, a held-out accuracy estimate or native Windows behavior.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import sys
import tempfile
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cantonese_ime import Engine, PaginationCapacityError


RUNTIME_FILES = ("cantonese_ime/engine.py", "cantonese_ime/mappings.py", "cantonese_ime/__init__.py", "tools/check_mapping_behavior.py")
SYLLABLE = re.compile(r"[a-z]+[1-6]\Z", re.ASCII)
SPLITS = (
    ("ngo5", "ng6 o5", "ng'o5"), ("wong4", "wo4 ng4", "wo'ng4"),
    ("seoi6", "se2 oi6", "se'oi6"), ("lam4", "la1 m4", "la'm4"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target_text(base: str) -> str:
    return "⟦base:" + base + "⟧"


def create_dictionary(path: Path, rows: list[tuple[str, str, float]]) -> None:
    """Create a disposable fixture; the selected live lexicon is never opened."""
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("""
            BEGIN;
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY, text TEXT NOT NULL, reading TEXT NOT NULL,
                base_reading TEXT NOT NULL, compact TEXT NOT NULL,
                syllable_count INTEGER NOT NULL, weight REAL NOT NULL, source TEXT NOT NULL,
                UNIQUE(text,reading)
            );
            CREATE INDEX entries_base_reading ON entries(base_reading);
        """)
        for text, reading, weight in rows:
            tokens = reading.split()
            if not tokens or any(not SYLLABLE.fullmatch(token) for token in tokens):
                raise ValueError("Invalid synthetic fixture reading")
            bases = [token[:-1] for token in tokens]
            connection.execute(
                "INSERT OR REPLACE INTO entries(text,reading,base_reading,compact,syllable_count,weight,source) VALUES (?,?,?,?,?,?,?)",
                (text, reading, " ".join(bases), "".join(bases), len(tokens), weight, "project:synthetic-mapping-probe"),
            )
        connection.commit()


def collect(engine: Engine, raw: str, mode: str, page_size: int = 90) -> dict:
    """Inspect the entire public bounded pool, recording unresolved prefix tails."""
    candidates, offset, offsets = [], 0, []
    seen = set()
    truncated = False
    while True:
        try:
            page = engine.lookup_page(raw, offset=offset, page_size=page_size, mode=mode)
        except PaginationCapacityError as error:
            return {"candidates": candidates, "offsets": offsets, "capacity_error": str(error), "completion_truncated": truncated}
        if page.offset != offset or any(item.text in seen for item in page.candidates):
            raise ValueError("Pager returned an inconsistent offset or duplicate text")
        offsets.append(offset)
        seen.update(item.text for item in page.candidates)
        candidates.extend(page.candidates)
        truncated |= page.completion_truncated
        if page.next_offset is None:
            return {"candidates": candidates, "offsets": offsets, "capacity_error": None, "completion_truncated": truncated}
        if page.next_offset != offset + len(page.candidates) or page.next_offset <= offset:
            raise ValueError("Pager cursor did not make exact visible progress")
        offset = page.next_offset


def observed_tones(inventory: dict) -> dict[str, set[str]]:
    result = {}
    for row in inventory["syllables"]:
        tones = {tone for values in row.get("observed_tones_by_source", {}).values() for tone in values}
        if not tones or any(tone not in "123456" or len(tone) != 1 for tone in tones):
            raise ValueError(f"Missing or invalid source-observed tones for {row['base']}")
        result[row["base"]] = tones
    return result


def exercise(inventory: dict, spellings: dict, directory: Path) -> dict:
    tones = observed_tones(inventory)
    relations = spellings["aliases"]
    grouped = defaultdict(list)
    for relation in relations:
        if relation["canonical"] not in tones:
            raise ValueError("Exported relation targets a base absent from the source inventory")
        grouped[relation["spelling"]].append(relation)
    if len(relations) != len({(row["spelling"], row["canonical"]) for row in relations}):
        raise ValueError("Duplicate exported spelling/target relation")
    if not {(base, base) for base in tones}.issubset({(row["spelling"], row["canonical"]) for row in relations}):
        raise ValueError("Every source-observed canonical base needs an exported identity relation")
    fixture_rows = [(target_text(base), base + tone, 0.0) for base in sorted(tones) for tone in sorted(tones[base])]
    for index, (whole, split, boundary) in enumerate(SPLITS):
        fixture_rows.append((f"⟦split:{index}⟧", split, 1e12))
        fixture_rows.append((f"⟦whole:{index}⟧", whole, 1.0))
        fixture_rows.extend(("⟦component:" + reading + "⟧", reading, 1e6) for reading in split.split())
    fixture_rows.append(("⟦partial-tone⟧", "nei5 hou2", 1e8))
    database = directory / "mapping-fixture.sqlite3"
    create_dictionary(database, fixture_rows)
    failures, counts, relation_status, capacity_cases = [], Counter(), {}, []

    def fail(kind: str, raw: str, mode: str, **details) -> None:
        counts["failures"] += 1
        if len(failures) < 100:
            failures.append({"kind": kind, "raw": raw, "mode": mode, **details})

    with Engine(database) as engine:
        for spelling, targets in sorted(grouped.items()):
            canonical_targets = {row["canonical"] for row in targets}
            statuses = {base: {"spelling": spelling, "canonical": base,
                               "source_observed_tones": sorted(tones[base]),
                               "forgiving_untoned": True, "forgiving_toned": True,
                               "strict_direct_isolation": True} for base in canonical_targets}
            for mode in ("forgiving", "jyutping"):
                for tone in (None, "1", "2", "3", "4", "5", "6"):
                    raw = spelling + (tone or "")
                    counts["lookup_scenarios"] += 1
                    try:
                        pool = collect(engine, raw, mode)
                        candidates = pool["candidates"]
                        counts["candidate_pages"] += len(pool["offsets"])
                        counts["candidate_inspections"] += len(candidates)
                        counts["completion_capacity_scenarios"] += bool(pool["capacity_error"])
                        counts["completion_truncated_scenarios"] += pool["completion_truncated"]
                        if pool["capacity_error"]:
                            capacity_cases.append({"raw": raw, "mode": mode, "visible_candidates": len(candidates),
                                                   "capacity_error": pool["capacity_error"]})
                        if engine.lookup(raw, limit=90, mode=mode) != candidates[:90]:
                            fail("lookup_page_prefix_disagrees_with_lookup", raw, mode)
                    except Exception as error:
                        fail("lookup_exception", raw, mode, error=f"{type(error).__name__}: {error}")
                        for status in statuses.values():
                            key = ("forgiving_untoned" if tone is None else "forgiving_toned") if mode == "forgiving" else "strict_direct_isolation"
                            status[key] = False
                        continue
                    by_text = {candidate.text: candidate for candidate in candidates}
                    for base in canonical_targets:
                        status = statuses[base]
                        candidate = by_text.get(target_text(base))
                        if mode == "forgiving":
                            expected = tone is None or tone in tones[base]
                            counts["forgiving_target_checks"] += 1
                            if expected:
                                good = candidate is not None and candidate.match_type == ("exact" if base == spelling else "fuzzy")
                                good = good and candidate.consumed_input == len(raw)
                                good = good and candidate.reading in {base + value for value in tones[base]}
                                if tone is not None:
                                    good = good and candidate.reading == base + tone
                            else:
                                good = candidate is None
                            if not good:
                                status["forgiving_untoned" if tone is None else "forgiving_toned"] = False
                                fail("missing_or_wrong_forgiving_relation", raw, mode, canonical=base,
                                     expected_present=expected, candidate=asdict(candidate) if candidate else None)
                        else:
                            # Prefix completion is legitimate strict behavior.
                            # Only a direct exact/fuzzy interpretation is an alias leak.
                            direct = candidate is not None and candidate.match_type in ("exact", "fuzzy")
                            expected = base == spelling and (tone is None or tone in tones[base])
                            counts["strict_target_checks"] += 1
                            good = direct == expected
                            if direct:
                                good &= candidate.match_type == "exact" and candidate.consumed_input == len(raw)
                                good &= candidate.reading in {base + value for value in tones[base]}
                                good &= tone is None or candidate.reading == base + tone
                            if not good:
                                status["strict_direct_isolation"] = False
                                fail("strict_identity_or_alias_isolation", raw, mode, canonical=base,
                                     expected_direct=expected, candidate=asdict(candidate) if candidate else None)
                    # Every supported closed letter-run must consume exactly one
                    # requested syllable; completion may append a suffix.
                    accepted_bases = canonical_targets if mode == "forgiving" else ({spelling} if spelling in tones else set())
                    if tone is not None and accepted_bases:
                        counts["numeric_closure_scenarios"] += 1
                        for candidate in candidates:
                            tokens = candidate.reading.split()
                            good = bool(tokens) and tokens[0] in {base + tone for base in accepted_bases}
                            good = good and (len(tokens) == 1 or candidate.match_type == "completion")
                            good = good and candidate.consumed_input == len(raw)
                            if not good:
                                fail("numeric_closure_or_tone_violation", raw, mode, candidate=asdict(candidate))
            for base, status in statuses.items():
                relation_status[(spelling, base)] = status
        closure = []
        for index, (whole, split, boundary) in enumerate(SPLITS):
            for mode in ("jyutping", "forgiving"):
                closed = collect(engine, whole, mode)["candidates"]
                explicit = collect(engine, boundary, mode)["candidates"]
                good = not any(candidate.text == f"⟦split:{index}⟧" for candidate in closed)
                good &= any(candidate.text == f"⟦split:{index}⟧" and candidate.reading == split for candidate in explicit)
                closure.append({"raw": whole, "mode": mode, "forbidden_split_reading": split,
                                "explicit_boundary": boundary, "passed": good})
                if not good:
                    fail("adversarial_numeric_closure", whole, mode, split=split, explicit_boundary=boundary)
        for mode in ("jyutping", "forgiving"):
            candidates = collect(engine, "neihou2", mode)["candidates"]
            good = any(candidate.text == "⟦partial-tone⟧" and candidate.reading == "nei5 hou2" for candidate in candidates)
            closure.append({"raw": "neihou2", "mode": mode, "expected_reading": "nei5 hou2", "passed": good})
            if not good:
                fail("partial_tone_segmentation", "neihou2", mode)
    rows = [relation_status[key] for key in sorted(relation_status)]
    collisions = []
    for spelling, targets in sorted(grouped.items()):
        if len(targets) > 1:
            collisions.append({"spelling": spelling, "canonical_targets": sorted(row["canonical"] for row in targets),
                               "passed": all(relation_status[(spelling, row["canonical"])]["forgiving_untoned"] for row in targets)})
    return {"counts": dict(counts), "relations": rows, "collisions": collisions,
            "numeric_controls": closure, "failures": failures, "completion_capacity_queries": capacity_cases,
            "fixture": {"source_observed_base_tone_entries": sum(map(len, tones.values())),
                        "canonical_bases": len(tones), "unique_target_text_per_base": True,
                        "project_authored_control_rows": len(fixture_rows) - sum(map(len, tones.values())),
                        "target_weight": 0, "adversarial_split_weight": 1e12}}


def exercise_paging(directory: Path) -> dict:
    database = directory / "paging-fixture.sqlite3"
    rows = [(f"⟦page:{index:04}⟧", "zi4", 0.0) for index in range(257)]
    rows.extend((f"⟦page:{index:04}⟧", "zi6", 0.0) for index in range(0, 257, 7))
    create_dictionary(database, rows)
    cases = []
    with Engine(database) as engine:
        reference = None
        for raw, mode in (("zi4", "jyutping"), ("zi4", "forgiving"), ("ji4", "forgiving"), ("zi", "jyutping")):
            for size in (9, 17, 90):
                pool = collect(engine, raw, mode, size)
                values = pool["candidates"]
                texts = [candidate.text for candidate in values]
                good = len(values) == len(set(texts)) == 257 and pool["capacity_error"] is None
                good &= values[:90] == engine.lookup(raw, limit=90, mode=mode)
                good &= texts[-1] == "⟦page:0256⟧"
                good &= all(candidate.reading == ("zi6" if raw == "zi" and int(candidate.text[6:10]) % 7 == 0 else "zi4") for candidate in values)
                if reference is None:
                    reference = texts
                good &= texts == reference
                cases.append({"raw": raw, "mode": mode, "page_size": size, "unique_candidates": len(set(texts)),
                              "last_target_rank": texts.index("⟦page:0256⟧") + 1 if "⟦page:0256⟧" in texts else None,
                              "pages": len(pool["offsets"]), "passed": bool(good)})
        strict_alias = engine.lookup_page("ji4", mode="jyutping")
        cases.append({"raw": "ji4", "mode": "jyutping", "passed": not strict_alias.candidates,
                      "purpose": "Strict mode cannot directly use the z-to-j alias."})
    return {"synthetic_unique_homophones": 257, "synthetic_alternative_pronunciations": 37,
            "cases": cases, "passed": all(case["passed"] for case in cases)}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=PROJECT_ROOT / "data/mappings/syllables.json")
    parser.add_argument("--spellings", type=Path, default=PROJECT_ROOT / "data/mappings/spellings.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs/mapping-behavior-coverage.json")
    args = parser.parse_args()
    watched = {str(path.resolve()): digest(path) for path in (args.inventory, args.spellings, *(PROJECT_ROOT / name for name in RUNTIME_FILES))}
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    spellings = json.loads(args.spellings.read_text(encoding="utf-8"))
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="cantonese-mapping-behavior-") as temporary:
        result = exercise(inventory, spellings, Path(temporary))
        paging = exercise_paging(Path(temporary))
    changed = [path for path, before in watched.items() if digest(Path(path)) != before]
    if changed:
        raise ValueError("Inputs or runtime changed during the exercise: " + ", ".join(changed))
    relation_pass = lambda row: all(row[key] for key in ("forgiving_untoned", "forgiving_toned", "strict_direct_isolation"))
    result.update({
        "schema_version": 1, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Mechanical exported-map-to-decoder coverage on synthetic text; NOT human pronunciation review, held-out accuracy, ranking quality or native Windows validation.",
        "method": "Every exported relation; every unique spelling in both modes without tone and with each ASCII digit1..6. Synthetic target readings use source-observed tones, not every possible tone. Strict completion is permitted; direct alias interpretation is forbidden. Public paging enumerates each bounded candidate pool; capacity tails are recorded, not called exhaustive completion coverage.",
        "source_observation_basis": "Source-attested tone sets in the pinned inventory artifact. Synthetic target strings and adversarial controls are project-authored; actual live dictionary entries/weights are not used.",
        "human_mapping_review": "pending; this report does not change that gate",
        "profile_version": spellings.get("profile_version"),
        "input_and_runtime_sha256": watched,
        "artifact_dictionary_sha256": inventory.get("source_metadata", {}).get("database", {}).get("sha256"),
        "python": platform.python_version(), "elapsed_seconds": round(time.perf_counter() - started, 3),
        "paging": paging,
        "summary": {"exported_relations": len(result["relations"]),
                    "passing_relations": sum(relation_pass(row) for row in result["relations"]),
                    "collisions": len(result["collisions"]), "passing_collisions": sum(row["passed"] for row in result["collisions"]),
                    "numeric_controls": len(result["numeric_controls"]), "passing_numeric_controls": sum(row["passed"] for row in result["numeric_controls"]),
                    "failure_count": result["counts"].get("failures", 0), "paging_passed": paging["passed"]},
    })
    result["passed"] = result["summary"]["failure_count"] == 0 and paging["passed"]
    write_json(args.output, result)
    print(json.dumps({"passed": result["passed"], "summary": result["summary"], "counts": result["counts"], "elapsed_seconds": result["elapsed_seconds"]}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"Mapping behavior exercise failed: {error}", file=sys.stderr)
        raise SystemExit(1)
