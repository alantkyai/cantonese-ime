"""Compare composition search with project-authored exhaustive DAG oracles.

The tiny lexicons and their weights are synthetic. This checks search/ranking
mechanics under the existing additive unigram objective; it does not measure
Cantonese quality, fit an external corpus, or claim that retained arc limits
enumerate every possible dictionary path. The selected live DB is never opened.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import heapq
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cantonese_ime import Engine, PaginationCapacityError


K = 90
FUZZY_COST = 6.0


@dataclass(frozen=True)
class Row:
    text: str
    reading: str
    weight: float


@dataclass(frozen=True)
class Unit:
    base: str
    tone: str | None = None
    spelling: str | None = None
    penalty: float = 0.0


@dataclass(frozen=True)
class Arc:
    end: int
    text: str
    reading: str
    cost: float
    penalty: float = 0.0


@dataclass(frozen=True)
class State:
    text: str
    reading: str
    costs: tuple[float, ...]
    penalties: tuple[float, ...]
    words: int

    @property
    def objective(self) -> float:
        return math.fsum(self.costs) + FUZZY_COST * math.fsum(self.penalties)

    @property
    def score(self) -> float:
        return 800.0 - self.objective


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def join_reading(first: str, second: str) -> str:
    return first + (" " + second if second else "")


def prepend(arc: Arc, suffix: State) -> State:
    return State(arc.text + suffix.text, join_reading(arc.reading, suffix.reading),
                 (arc.cost,) + suffix.costs, (arc.penalty,) + suffix.penalties, suffix.words + 1)


EMPTY = State("", "", (), (), 0)


def rank_unique(states: list[State], k: int = K) -> list[State]:
    """Public score/text order; best reading is lexicographically largest on ties."""
    winners: dict[str, State] = {}
    for item in states:
        previous = winners.get(item.text)
        if previous is None or (item.score, item.reading) > (previous.score, previous.reading):
            winners[item.text] = item
    return sorted(winners.values(), key=lambda item: (-item.score, item.text, item.reading))[:k]


def exhaustive(graph: dict[int, list[Arc]], end: int, max_paths: int = 1_000_000) -> tuple[list[State], int]:
    """Enumerate complete paths before any text deduplication or candidate cap."""
    complete: list[State] = []

    def visit(position: int, path: tuple[Arc, ...]) -> None:
        if position == end:
            if len(path) > 1:
                if len(complete) >= max_paths:
                    raise ValueError("Exhaustive synthetic path guard exceeded")
                complete.append(State("".join(arc.text for arc in path), " ".join(arc.reading for arc in path),
                                      tuple(arc.cost for arc in path), tuple(arc.penalty for arc in path), len(path)))
            return
        for arc in graph.get(position, ()):
            if not position < arc.end <= end:
                raise ValueError("Oracle requires a forward acyclic graph")
            visit(arc.end, path + (arc,))

    visit(0, ())
    return rank_unique(complete), len(complete)


class PrototypeCapacityError(RuntimeError):
    pass


def backward_lazy(graph: dict[int, list[Arc]], end: int, k: int = K, max_pops: int = 100_000) -> tuple[list[State], dict]:
    """Independent lazy stream merge over top-k distinct suffix output texts.

    Uses complete cost parts with math.fsum for the mechanical oracle. Runtime
    right-associated float addition may differ by an ulp; scores are compared
    with a tolerance, and synthetic equal-cost cases still check exact tie order.
    """
    suffixes: dict[int, list[State]] = {end: [EMPTY]}
    stats = {"heap_pops": 0, "heap_pushes": 0, "streams": 0, "states": 1, "max_heap": 0}
    for position in range(end - 1, -1, -1):
        streams: list[tuple[Arc, list[State]]] = []
        heap: list[tuple[float, str, int, int, State]] = []

        def push(stream: int, index: int) -> None:
            arc, tails = streams[stream]
            if index < len(tails):
                item = prepend(arc, tails[index])
                heapq.heappush(heap, (item.objective, item.text, stream, index, item))
                stats["heap_pushes"] += 1
                stats["max_heap"] = max(stats["max_heap"], len(heap))

        for arc in graph.get(position, ()):
            if position == 0 and arc.end == end:
                continue  # One-word direct matches have their own candidate tier.
            tails = suffixes.get(arc.end, [])
            if tails:
                streams.append((arc, tails))
                push(len(streams) - 1, 0)
        stats["streams"] += len(streams)
        result: list[State] = []
        seen: set[str] = set()
        while heap and len(result) < k:
            group_key = heap[0][:2]
            winner: State | None = None
            # A first-seen tie is insufficient: public text dedup chooses the
            # largest reading among every equal-score path for that same text.
            while heap and heap[0][:2] == group_key:
                _, _, stream, index, item = heapq.heappop(heap)
                stats["heap_pops"] += 1
                if stats["heap_pops"] > max_pops:
                    raise PrototypeCapacityError("Synthetic lazy merge exceeded its heap-pop budget")
                if winner is None or item.reading > winner.reading:
                    winner = item
                push(stream, index + 1)
            assert winner is not None
            if winner.text not in seen:
                seen.add(winner.text)
                result.append(winner)
        suffixes[position] = result
        stats["states"] += len(result)
    return suffixes.get(0, []), stats


def create_dictionary(path: Path, rows: list[Row]) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("""
            CREATE TABLE entries(id INTEGER PRIMARY KEY,text TEXT NOT NULL,reading TEXT NOT NULL,
              base_reading TEXT NOT NULL,compact TEXT NOT NULL,syllable_count INTEGER NOT NULL,
              weight REAL NOT NULL,source TEXT NOT NULL,UNIQUE(text,reading));
            CREATE INDEX entries_base_reading ON entries(base_reading);
        """)
        for row in rows:
            bases = [token[:-1] for token in row.reading.split()]
            connection.execute(
                "INSERT INTO entries(text,reading,base_reading,compact,syllable_count,weight,source) VALUES (?,?,?,?,?,?,?)",
                (row.text, row.reading, " ".join(bases), "".join(bases), len(bases), row.weight, "project:synthetic-composition-oracle"),
            )
        connection.commit()


def make_graph(rows: list[Row], units: tuple[Unit, ...], retained: bool = False) -> dict[int, list[Arc]]:
    """Independent token-level matching, with optional documented 90-arc cap.

    Primary fixtures use only nei/hou/sik, whose spellings cannot split into
    other bases present in those fixtures. This graph builder never calls the
    runtime tokenizer, trie, arc builder, or spelling-map implementation.
    """
    log_total = math.log(max(1.0, math.fsum(row.weight for row in rows) + len(rows)))
    graph: dict[int, list[Arc]] = defaultdict(list)
    for start in range(len(units)):
        for row in rows:
            tokens = row.reading.split()
            selected = units[start:start + len(tokens)]
            if len(selected) != len(tokens) or any(
                token[:-1] != unit.base or (unit.tone is not None and token[-1] != unit.tone)
                for token, unit in zip(tokens, selected)
            ):
                continue
            graph[start].append(Arc(start + len(tokens), row.text, row.reading,
                                    max(0.0, log_total - math.log1p(row.weight)),
                                    math.fsum(unit.penalty for unit in selected)))
        if retained:
            grouped: dict[int, list[Arc]] = defaultdict(list)
            for arc in graph[start]:
                grouped[arc.end].append(arc)
            graph[start] = [arc for end in sorted(grouped)
                            for arc in sorted(grouped[end], key=lambda a: (
                                a.cost + FUZZY_COST * a.penalty, a.penalty, a.text, a.reading))[:K]]
    return dict(graph)


def raw_input(units: tuple[Unit, ...], boundary: str = "") -> str:
    return boundary.join((unit.spelling or unit.base) + (unit.tone or "") for unit in units)


def public_pool(engine_type, database: Path, raw: str, mode: str) -> dict:
    candidates, offsets = [], []
    with engine_type(database, mode=mode) as engine:
        offset = 0
        while True:
            try:
                page = engine.lookup_page(raw, offset=offset, page_size=90)
            except PaginationCapacityError as error:
                return {"candidates": candidates, "offsets": offsets, "error": str(error)}
            offsets.append(offset)
            candidates.extend(page.candidates)
            if page.next_offset is None:
                break
            if page.next_offset <= offset:
                raise ValueError("Pagination failed to make progress")
            offset = page.next_offset
        if engine.lookup(raw, limit=90) != candidates[:90]:
            raise ValueError("lookup is not the prefix of the public page order")
    return {"candidates": candidates, "offsets": offsets, "error": None}


def compare(expected: list[State], candidates: list) -> dict:
    actual = [item for item in candidates if item.match_type == "composed"]
    actual_by_text = {item.text: item for item in actual}
    expected_texts = [item.text for item in expected]
    actual_texts = [item.text for item in actual]
    readings = [{"text": item.text, "expected": item.reading, "actual": actual_by_text[item.text].reading}
                for item in expected if item.text in actual_by_text and item.reading != actual_by_text[item.text].reading]
    max_delta = max((abs(item.score - actual_by_text[item.text].score)
                     for item in expected if item.text in actual_by_text), default=0.0)
    return {"oracle_top90_unique": len(expected), "composed_returned": len(actual),
            "public_total": len(candidates), "missing_oracle_top9": [text for text in expected_texts[:9] if text not in actual_by_text],
            "missing_oracle_top90": [text for text in expected_texts if text not in actual_by_text],
            "readings_differ": readings, "same_top90_text_order": expected_texts == actual_texts[:K],
            "max_score_delta": max_delta, "top9_expected": expected_texts[:9], "top9_actual": actual_texts[:9],
            "matches_oracle": expected_texts == actual_texts[:K] and not readings and max_delta < 1e-9}


def fixtures() -> list[dict]:
    toned = (Unit("nei", "5"), Unit("hou", "2"))
    untoned = (Unit("nei"), Unit("hou"))
    duplicates = ([Row("P", f"nei{tone}", 1000) for tone in range(1, 7)] + [Row("Q", "nei5", 900)] +
                  [Row("A", f"hou{tone}", 1000) for tone in range(1, 7)] + [Row("B", "hou2", 900)])
    arc_rows = [Row("P", " ".join(f"{base}{tone}" for base, tone in zip(("nei", "hou", "sik"), tones)), 1000)
                for tones in itertools.product(range(1, 7), repeat=3)]
    arc_rows += [Row("Q", "nei5 hou2 sik6", 900), Row("S", "hou2", 1000)]
    return [
        {"name": "ninth_unique_prefix", "rows": [Row(f"P{index:02}", "nei5", 1000-index*10) for index in range(9)] + [Row("S", "hou2", 1000)], "units": toned},
        {"name": "prefix_of_other_lexical_top1", "rows": [Row("A"*length, "nei5", 1000) for length in range(1, 10)] + [Row("B", "hou2", 1000)], "units": toned},
        {"name": "duplicate_tone_paths_final32", "rows": duplicates, "units": untoned},
        {"name": "duplicate_tone_paths_toned_control", "rows": duplicates, "units": toned},
        {"name": "duplicate_tone_paths_apostrophe", "rows": duplicates, "units": untoned, "boundary": "'"},
        {"name": "forgiving_alias_duplicate_paths", "rows": duplicates, "units": (Unit("nei", spelling="lei", penalty=0.8), Unit("hou")), "mode": "forgiving"},
        {"name": "duplicate_prefixes_intermediate8", "rows": [Row(text, f"nei{tone}", 1000) for text in ("P", "Q") for tone in range(1, 7)] + [Row("R", "nei5", 900), Row("A", "hou2", 1000)], "units": untoned},
        {"name": "sixty_four_distinct_compositions", "rows": [Row(f"P{index}", "nei5", 1000) for index in range(8)] + [Row(f"S{index}", "hou2", 1000) for index in range(8)], "units": toned},
        {"name": "root_direct_paths_must_not_spend_composed_budget", "rows": [Row(f"D{index:03}", "nei5 hou2", 1e9) for index in range(100)] + [Row("P", "nei5", 1000), Row("Q", "nei5", 900), Row("A", "hou2", 1000)], "units": toned},
        {"name": "retained_arc90_scope_control", "rows": arc_rows, "units": (Unit("nei"), Unit("hou"), Unit("sik"), Unit("hou")), "retained_scope": True},
    ]


def load_engine(path: Path, name: str):
    spec = importlib.util.spec_from_file_location("cantonese_ime." + name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load comparison engine source")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.Engine


def check_random_graphs(count: int) -> dict:
    randomizer = random.Random(20261022)
    failures, runtime_failures, max_paths, total_paths, heap_pops = [], [], 0, 0, 0
    runtime = Engine.__new__(Engine)
    runtime._log_total = 4.0
    runtime_helper_available = hasattr(runtime, "_compose_sentences")
    for case in range(count):
        end = randomizer.randint(3, 7)
        graph: dict[int, list[Arc]] = defaultdict(list)
        for position in range(end):
            for target in range(position + 1, min(end, position + 3) + 1):
                for _ in range(randomizer.randint(1, 3)):
                    # Binary-exact costs isolate the algorithm from floating
                    # association. Duplicate/prefix-related texts are deliberate.
                    graph[position].append(Arc(target, randomizer.choice(("A", "AA", "B", "AB", "BA")),
                                               f"nei{randomizer.randint(1, 6)}",
                                               randomizer.choice((0.0, 0.125, 0.75, 1.0, 3.0)),
                                               randomizer.choice((0.0, 0.125))))
        oracle, paths = exhaustive(graph, end)
        prototype, stats = backward_lazy(graph, end)
        total_paths += paths
        max_paths = max(max_paths, paths)
        heap_pops += stats["heap_pops"]
        if [(item.text, item.reading, item.objective) for item in oracle] != [(item.text, item.reading, item.objective) for item in prototype]:
            failures.append({"case": case, "paths": paths})
        if runtime_helper_available:
            # Feed the very same abstract DAG to the production search helper,
            # bypassing tokenizer/SQL. Invert its cost formula, checking that
            # the small binary-exact costs survive log/expm1 conversion.
            runtime_graph = {}
            for position, arcs in graph.items():
                converted = []
                for arc in arcs:
                    weight = math.expm1(4.0 - arc.cost)
                    if 4.0 - math.log1p(weight) != arc.cost:
                        raise AssertionError("Random oracle fixture cost did not roundtrip")
                    converted.append(SimpleNamespace(end=arc.end, penalty=arc.penalty,
                        entry=SimpleNamespace(text=arc.text, reading=arc.reading, weight=weight)))
                runtime_graph[position] = converted
            actual = runtime._compose_sentences(lambda position: runtime_graph.get(position, ()), end)
            observed = [(item.text, " ".join(item.readings), item.cost + FUZZY_COST * item.penalty) for item in actual]
            if [(item.text, item.reading, item.objective) for item in oracle] != observed:
                runtime_failures.append({"case": case, "paths": paths})
    return {"seed": 20261022, "cases": count, "complete_paths_enumerated": total_paths,
            "max_complete_paths_one_case": max_paths, "prototype_heap_pops": heap_pops, "failures": failures,
            "current_runtime_helper_exercised": runtime_helper_available,
            "current_runtime_helper_failures": runtime_failures}


def work_probe() -> dict:
    graph = {position: [Arc(position + 1, f"{position}:{index:02}/", "nei5", index / 8)
                        for index in range(30)] for position in range(6)}
    start = time.perf_counter()
    result, stats = backward_lazy(graph, 6)
    elapsed = (time.perf_counter() - start) * 1000
    guard_raised = False
    try:
        backward_lazy(graph, 6, max_pops=10)
    except PrototypeCapacityError:
        guard_raised = True
    return {"layered_nodes": 7, "arcs": 180, "possible_complete_paths": 30**6,
            "returned_unique": len(result), **stats, "elapsed_ms_single_observation": round(elapsed, 3),
            "low_budget_raises_before_returning_partial_pool": guard_raised,
            "timing_scope": "Synthetic Python prototype only; not a native IME latency measurement"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs/composition-search-analysis.json")
    parser.add_argument("--random-cases", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.random_cases <= 1000:
        parser.error("random-cases must be 1..1000")
    inputs = [PROJECT_ROOT / name for name in ("cantonese_ime/engine.py", "cantonese_ime/mappings.py", "cantonese_ime/__init__.py", "tools/check_composition_search.py")]
    if args.baseline_source:
        inputs.append(args.baseline_source.resolve())
    before = {path.relative_to(PROJECT_ROOT).as_posix(): digest(path) for path in inputs}
    engines = {"current": Engine}
    if args.baseline_source:
        engines["baseline"] = load_engine(args.baseline_source.resolve(), "_composition_baseline")
    rows = []
    with tempfile.TemporaryDirectory(prefix="composition-oracle-") as temporary:
        for fixture in fixtures():
            database = Path(temporary) / (fixture["name"] + ".sqlite3")
            create_dictionary(database, fixture["rows"])
            graph = make_graph(fixture["rows"], fixture["units"], retained=fixture.get("retained_scope", False))
            oracle, paths = exhaustive(graph, len(fixture["units"]))
            prototype, stats = backward_lazy(graph, len(fixture["units"]))
            if [(item.text, item.reading, item.objective) for item in oracle] != [(item.text, item.reading, item.objective) for item in prototype]:
                raise AssertionError("Independent prototype disagrees with exhaustive fixture oracle")
            raw = raw_input(fixture["units"], fixture.get("boundary", ""))
            result = {"name": fixture["name"], "raw": raw, "mode": fixture.get("mode", "jyutping"),
                      "source": "Project-authored synthetic words, readings and weights",
                      "rows": [asdict(row) for row in fixture["rows"]], "complete_composed_paths": paths,
                      "oracle_scope": "retained 90 arcs per ending" if fixture.get("retained_scope") else "entire independent fixture graph",
                      "prototype": {"matches_exhaustive_oracle": True, **stats}, "engines": {}}
            if fixture.get("retained_scope"):
                full, full_paths = exhaustive(make_graph(fixture["rows"], fixture["units"]), len(fixture["units"]))
                result["full_graph_control"] = {"complete_paths": full_paths, "unique_texts": [item.text for item in full],
                                                "lost_before_composition_search": [item.text for item in full if item.text not in {kept.text for kept in oracle}]}
            for name, engine_type in engines.items():
                pool = public_pool(engine_type, database, raw, result["mode"])
                result["engines"][name] = {**compare(oracle, pool["candidates"]), "offsets": pool["offsets"], "error": pool["error"]}
            rows.append(result)
    randomized = check_random_graphs(args.random_cases)
    work = work_probe()
    after = {path.relative_to(PROJECT_ROOT).as_posix(): digest(path) for path in inputs}
    if before != after:
        raise RuntimeError("Runtime/checker source changed during composition analysis; report not saved")
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Independent synthetic exhaustive search mechanics; no external corpus scoring or live lexicon access",
              "source_hashes": before, "source_guards_passed": True,
              "objective": "800 - sum(max(0, log(sum(weights)+entry_count)-log1p(word_weight))) - 6*sum(alias_penalties)",
              "tie_policy": "Per text choose max(score, full reading); final order (-score,text,reading)",
              "numeric_precision": "Oracle/prototype use math.fsum of arc cost parts. Runtime suffix addition may differ by an ulp; score tolerance 1e-9, exact text/reading ordering on these fixtures.",
              "fixtures": rows, "randomized_dag_oracles": randomized, "bounded_work_probe": work,
              "summary": {name: {"fixtures": len(rows), "oracle_matches": sum(row["engines"][name]["matches_oracle"] for row in rows),
                                 "missing_top9_cases": sum(bool(row["engines"][name]["missing_oracle_top9"]) for row in rows),
                                 "reading_tie_mismatch_cases": sum(bool(row["engines"][name]["readings_differ"]) for row in rows)} for name in engines},
              "limitations": ["Guarantee concerns only the retained acyclic word-arc graph; runtime per-base/per-ending arc90 and syllable-path96 bounds remain.",
                              "The composed pool remains at most90 distinct texts before learning. Learning outside that base pool is not exhaustive.",
                              "Prefix completion has separate limits and is not assessed by these composition-only oracles.",
                              "Synthetic word labels and weights say nothing about preferred Cantonese phrasing or real language ranking quality."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": report["summary"], "randomized_failures": len(randomized["failures"]),
                      "runtime_helper_failures": len(randomized["current_runtime_helper_failures"]), "work_probe": work}, ensure_ascii=True))
    return int(bool(randomized["failures"]) or bool(randomized["current_runtime_helper_failures"]) or
               report["summary"]["current"]["oracle_matches"] != len(rows) or
               not work["low_budget_raises_before_returning_partial_pool"])


if __name__ == "__main__":
    raise SystemExit(main())
