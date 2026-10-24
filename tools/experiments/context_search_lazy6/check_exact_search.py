"""Independent exhaustive integer path oracle; imports no language fixtures.

The candidate module is loaded only after its exact source pin is supplied.
The oracle scores whole emitted strings directly, rather than reproducing
state search, heuristics, streams, context preparation, or candidate joining.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys
import time
from types import MappingProxyType


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def enumerate_paths(rows, end):
    # Build every complete path with a simple independent recursion. No search
    # pruning, cost dominance, incoming context, or bounded-k suffix table.
    adjacency = {position: [] for position in range(end)}
    for row in rows:
        adjacency[row[0]].append(row)

    def visit(position, path):
        if position == end:
            yield tuple(path)
        else:
            for row in adjacency[position]:
                path.append(row)
                yield from visit(row[1], path)
                path.pop()

    return list(visit(0, []))


def expected(paths, costs, incoming):
    best = {}
    for path in paths:
        text = "".join(row[2] for row in path)
        reading = " ".join(row[3] for row in path)
        lexical = sum(row[4] for row in path)
        previous = incoming
        context = 0
        for letter in text:
            context += costs.get((previous, letter), 0)
            previous = letter
        item = (lexical + context, text, reading, lexical, context)
        prior = best.get(text)
        if prior is None or item[0] < prior[0] or (item[0] == prior[0] and reading > prior[2]):
            best[text] = item
    return sorted(best.values(), key=lambda item: (item[0], item[1]))


def cases():
    # Duplicate written strings, reading strings that prefix one another,
    # alternate word splits, unreachable/dead arcs, Unicode and zero-cost ties.
    yield "hidden_context_successor", 2, [
        (0, 1, "甲", "x", 0), (1, 2, "乙", "a", 1),
        (1, 2, "丙", "b", 2), (0, 2, "丁", "z", 3),
    ], {(None, "甲"): 0, ("甲", "乙"): 4, ("甲", "丙"): 0}
    yield "reading_and_segmentation_ties", 3, [
        (0, 1, "甲", "a", 0), (0, 1, "甲", "a b", 0),
        (1, 2, "乙", "z", 0), (1, 2, "乙", "zz", 0),
        (2, 3, "丙", "q", 0), (0, 2, "甲乙", "a zz", 0),
        (0, 3, "甲乙丙", "a b zz q", 0),
        (0, 3, "甲乙丁", "zzzz", 0),
    ], {}
    yield "dead_continuations", 5, [
        (0, 1, "甲", "a", 0), (1, 5, "乙", "b", 2),
        (0, 2, "甲乙", "z", 0), (2, 3, "丙", "q", 0),
        (4, 5, "丁", "x", 0),
    ], {("甲", "乙"): 1}
    yield "unicode_distinct", 2, [
        (0, 1, "\U00020000", "ngo5", 1), (1, 2, "甲", "z", 0),
        (0, 2, "\U00020000甲", "a", 2), (0, 2, "甲\U00020000", "q", 0),
    ], {(None, "\U00020000"): 2, ("\U00020000", "甲"): 3}
    rng = random.Random(20261024031)
    alphabet = ("甲", "乙", "丙", "丁", "甲乙", "乙甲", "\U00020000")
    readings = ("a", "a b", "aa", "z", "z a", "ngo5", "ng5 o5")
    chars = ("甲", "乙", "丙", "丁", "\U00020000")
    for index in range(320):
        end = rng.randint(2, 5)
        rows = []
        for start in range(end):
            for stop in range(start + 1, end + 1):
                for _ in range(rng.randrange(3)):
                    rows.append((start, stop, rng.choice(alphabet), rng.choice(readings), rng.randrange(5)))
        # Some graphs intentionally have no complete path.
        costs = {(left, right): rng.randrange(5)
                 for left, right in itertools.product((None,) + chars, chars)}
        yield f"random_{index:03d}", end, rows, costs
    for index in range(60):
        end = 6
        rows = []
        for start in range(end):
            for stop in range(start + 1, min(end, start + 3) + 1):
                for _ in range(2 if stop == start + 1 else 1):
                    rows.append((start, stop, rng.choice(alphabet), rng.choice(readings), rng.randrange(3)))
        costs = {(left, right): rng.randrange(3)
                 for left, right in itertools.product((None,) + chars, chars)}
        yield f"dense_{index:03d}", end, rows, costs
    yield "cost_tie_frontier_100000_paths", 5, [
        (start, start + 1, letter, "q" + letter, 0)
        for start in range(5) for letter in "ABCDEFGHIJ"
    ], {}
    prefix_rows = [
        (start, start + 1, word, "q" + word, 0)
        for start in range(5) for word in ("A", "AA", "B", "BA", "C", "CA", "D", "DA")
    ]
    prefix_rows.append((0, 1, "A", "zz", 0))
    yield "prefix_strings_and_reading_tie_frontier", 5, prefix_rows, {}
    yield "lexical_and_cost_bounds_from_different_paths", 3, [
        (0, 1, "A", "a", 10), (0, 1, "B", "b", 0),
        (1, 2, "A", "q", 3), (1, 2, "AA", "qq", 0),
        (2, 3, "A", "r", 0), (2, 3, "B", "rr", 1),
        (0, 3, "A", "z", 11),
    ], {("B", "A"): 3, ("A", "A"): 1}
    left = [chr(0x4E00 + i) for i in range(120)]
    right = [chr(0x5000 + i) for i in range(60)]
    rows = [(0, 1, char, "r" + str(i), i % 3) for i, char in enumerate(left)]
    rows += [(1, 2, char, "v" + str(i), i % 2) for i, char in enumerate(right)]
    costs = {(a, b): (i * 7 + j * 3) % 7
             for i, a in enumerate(left) for j, b in enumerate(right)}
    costs.update({(None, char): (i * 5) % 4 for i, char in enumerate(left)})
    yield "many_incoming_contexts_shared_outgoing_groups", 2, rows, costs


    # Independent complete-path oracles stress actual T ordering rather than
    # reproducing a scalar/group cache. Most lexical minima have expensive
    # future context; the one useful group comes late in lexical order.
    left = [chr(0x5300 + i) for i in range(90)]
    groups = [chr(0x5400 + i) for i in range(80)]
    ending = chr(0x5500)
    rows = [(0, 1, char, 'left' + str(i), i % 4)
            for i, char in enumerate(left)]
    rows += [(1, 2, char, 'group' + str(i), int(i == 79))
             for i, char in enumerate(groups)]
    rows += [(2, 3, ending, 'end', 0)]
    costs = {(char, ending): (0 if i == 79 else 100 + i % 5)
             for i, char in enumerate(groups)}
    costs.update({(a, b): (i * 3 + j) % 7
                  for i, a in enumerate(left) for j, b in enumerate(groups)})
    yield 'late_group_with_cheap_exact_future', 3, rows, costs

    # Identical head costs and written lower bounds must retain alternative
    # readings and later group outputs even when the scalar minimum is tied.
    rows = [(0, 1, 'A', 'r', 0), (0, 1, 'A', 'r zz', 0),
            (1, 2, 'AB', 'a', 0), (1, 2, 'A', 'zz', 0),
            (1, 2, 'B', 'b', 0), (1, 3, 'ABA', 'a b', 1),
            (2, 3, 'A', 'z', 0), (2, 3, 'BA', 'z z', 0),
            (2, 3, 'A', 'zzzz', 0)]
    costs = {('A', 'A'): 1, ('A', 'B'): 0, ('B', 'A'): 0,
             (None, 'A'): 0, ('B', 'B'): 1}
    yield 'exact_group_head_cost_text_reading_ties', 3, rows, costs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to replace existing proof")
    module_path = args.module.resolve()
    initial_sha = digest(module_path)
    if initial_sha != args.expected_sha256:
        raise SystemExit("Candidate source differs from supplied pin")
    name = "_independent_cycle3_candidate"
    specification = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)

    class CallbackModel(module.CharacterModel):
        # Like a packed-prior provider, this model's public preparation table is
        # empty while consume supplies nonzero costs. Zero specialization must
        # never infer callback behavior from that empty table.
        def __init__(self, table):
            super().__init__({})
            object.__setattr__(self, "_actual_table", MappingProxyType(dict(table)))

        def consume(self, incoming, text):
            previous, total = incoming, 0
            for letter in text:
                total += self._actual_table.get((previous, letter), 0)
                previous = letter
            return total, previous

    report = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "synthetic integer retained-DAG search only; no engine, model training or language fixture queries",
              "checker_sha256": digest(__file__), "candidate_sha256": initial_sha,
              "model_flavors": ["explicit_table", "callback_hidden_table"],
              "graphs": 0, "comparisons": 0, "complete_paths_enumerated": 0,
              "failures": [], "passed": False}
    start_time = time.monotonic()
    for case_id, end, rows, costs in cases():
        paths = enumerate_paths(rows, end)
        if len(paths) > 100000:
            raise AssertionError("Independent graph generation exceeded enumerator bound")
        report["graphs"] += 1
        report["complete_paths_enumerated"] += len(paths)
        arcs = tuple(module.Arc(*row) for row in rows)
        models = (("explicit_table", module.CharacterModel(costs)),
                  ("callback_hidden_table", CallbackModel(costs)))
        for flavor, model in models:
            for incoming in (None, "甲", "丁"):
                wanted_all = expected(paths, costs, incoming)
                for k in (1, 2, 5, 90):
                    report["comparisons"] += 1
                    wanted = wanted_all[:k]
                    try:
                        result = module.decode(arcs, end, model, k=k, incoming=incoming)
                        got = [(row.cost, row.text, row.reading, row.lexical_cost, row.context_cost)
                               for row in result.candidates]
                    except Exception as error:
                        got = {"exception": type(error).__name__, "message": str(error)}
                    if got != wanted:
                        report["failures"].append({"case_id": case_id, "incoming": incoming, "k": k,
                                                   "model_flavor": flavor, "rows": rows,
                                                   "costs": [[a, b, c] for (a, b), c in costs.items()],
                                                   "expected": wanted, "actual": got})
    # These independent complete-path cases need many logical contexts but
    # only three simultaneous recursive/outgoing records. The constructor hook
    # counts actual slot allocations, without trusting a reported cache counter.
    report["bounded_slot_comparisons"] = 0
    report["expected_state_capacity_failures"] = 0
    report["bounded_slot_observations"] = []
    for duplicates in (False, True):
        letters = [chr(0x5800 + i) for i in range(80)]
        rows = [(0, 1, "A", "root", 0)]
        rows += [(1, 2, char, "group" + str(i), 0)
                 for i, char in enumerate(letters)]
        rows += [(2, 3, "Z", "a", 0)]
        if duplicates:
            rows += [(2, 3, "Z", "zzzz", 0)]
            rows += [(1, 3, char + "Z", "zzzz", 0) for char in letters]
        costs = {(char, "Z"): 1 + (i * 7 + 3) % 11
                 for i, char in enumerate(letters)}
        costs.update({("A", char): i % 3 for i, char in enumerate(letters)})
        paths = enumerate_paths(rows, 3)
        report["graphs"] += 1
        report["complete_paths_enumerated"] += len(paths)
        arcs = tuple(module.Arc(*row) for row in rows)
        for flavor, model in (("explicit_table", module.CharacterModel(costs)),
                              ("callback_hidden_table", CallbackModel(costs))):
            for incoming in (None, "甲", "丁"):
                wanted = expected(paths, costs, incoming)[:1]
                for state_cap in (2, 3):
                    created = []
                    constructor = module._Context
                    def counted_constructor(*args, **kwargs):
                        slot = constructor(*args, **kwargs)
                        created.append(slot)
                        return slot
                    module._Context = counted_constructor
                    report["comparisons"] += 1
                    report["bounded_slot_comparisons"] += 1
                    observation = {"duplicates": duplicates, "model_flavor": flavor,
                                   "incoming": incoming, "state_cap": state_cap}
                    try:
                        result = module.decode(arcs, 3, model, k=1, incoming=incoming,
                                               limits=module.Limits(states=state_cap))
                        got = [(row.cost, row.text, row.reading, row.lexical_cost, row.context_cost)
                               for row in result.candidates]
                        observation.update({"status": "completed", "actual_allocations": len(created),
                                            "counters": dict(result.counters),
                                            "statistics": dict(result.statistics)})
                        valid = (state_cap == 3 and got == wanted and len(created) <= state_cap
                                 and result.counters["states"] == len(created))
                    except module.CapacityError as error:
                        observation.update({"status": "capacity", "resource": error.resource,
                                            "actual_allocations": len(created),
                                            "counters": dict(error.counters)})
                        valid = (state_cap == 2 and error.resource == "states"
                                 and len(created) == error.counters["states"] == state_cap
                                 and error.used == state_cap and error.requested == 1
                                 and error.limit == state_cap)
                        if valid:
                            report["expected_state_capacity_failures"] += 1
                    except Exception as error:
                        observation.update({"status": "unexpected_exception",
                                            "exception": type(error).__name__, "message": str(error)})
                        valid = False
                    finally:
                        module._Context = constructor
                    observation["passed"] = valid
                    report["bounded_slot_observations"].append(observation)
                    if not valid:
                        report["failures"].append({"case_id": "bounded_slot_reuse", **observation})
    report["source_unchanged"] = digest(module_path) == initial_sha
    report["wall_seconds"] = time.monotonic() - start_time
    report["passed"] = not report["failures"] and report["source_unchanged"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "graphs", "comparisons", "complete_paths_enumerated", "wall_seconds")}, ensure_ascii=False))
    if not report["passed"]:
        print(json.dumps({"failures": len(report["failures"]), "first": report["failures"][:1]}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
