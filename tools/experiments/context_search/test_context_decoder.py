"""Mechanical synthetic fixtures. No IME, dictionary, or quality-label imports."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import itertools
import random
import unittest

from context_decoder import Arc, CapacityError, CharacterModel, Limits, decode


ORACLE_COMPARISONS = 0


def exhaustive(arcs, end, costs, default=0, *, incoming=None, k=9, max_paths=100000):
    """Independent path enumeration, then score the complete written string.

    It does not use decoder state discovery, model.consume, hypothesis joins,
    heap ordering, dedup, or candidate-cost accumulation. Small integer costs
    keep the comparison exact rather than relying on float tolerances.
    """
    outputs = []

    def visit(position, pieces, readings, lexical):
        if position == end:
            if len(outputs) >= max_paths:
                raise RuntimeError("Oracle path bound")
            text = "".join(pieces)
            context = 0
            previous = incoming
            for letter in text:
                context += costs.get((previous, letter), default)
                previous = letter
            outputs.append((text, " ".join(readings), lexical + context, lexical, context))
            return
        for arc in arcs:
            if arc.start == position:
                visit(arc.end, pieces + [arc.text], readings + [arc.reading], lexical + arc.cost)

    visit(0, [], [], 0)
    unique = {}
    for row in outputs:
        previous = unique.get(row[0])
        if previous is None or row[2] < previous[2] or (row[2] == previous[2] and row[1] > previous[1]):
            unique[row[0]] = row
    return sorted(unique.values(), key=lambda row: (row[2], row[0]))[:k]


def actual_rows(result):
    return [(p.text, p.reading, p.cost, p.lexical_cost, p.context_cost) for p in result.candidates]


class ContextDecoderTests(unittest.TestCase):
    def compare(self, arcs, end, costs, default=0, incoming=None, k=9):
        global ORACLE_COMPARISONS
        expected = exhaustive(arcs, end, costs, default, incoming=incoming, k=k)
        actual = decode(arcs, end, CharacterModel(costs, default=default), incoming=incoming, k=k)
        self.assertEqual(actual_rows(actual), expected)
        self.assertTrue(actual.complete_within_retained_graph)
        ORACLE_COMPARISONS += 1
        return actual

    def test_naive_suffix_top1_reranker_loses_true_top1(self):
        arcs = [Arc(0, 1, "x", "x", 0), Arc(1, 2, "a", "a", 1),
                Arc(1, 2, "b", "b", 2), Arc(0, 2, "z", "z", 3)]
        costs = {("x", "a"): 4}
        # A context-free top-1 suffix discards b because a costs1 < b costs2.
        # Reranking its surviving xa and the other z stream returns z at3.
        naive_retained = [("xa", 1 + 4), ("z", 3)]
        self.assertEqual(min(naive_retained, key=lambda row: (row[1], row[0]))[0], "z")
        actual = self.compare(arcs, 2, costs, k=1)
        self.assertEqual((actual.candidates[0].text, actual.candidates[0].cost), ("xb", 2))
        self.assertGreaterEqual(actual.counters["states"], 4)

    def test_two_incoming_contexts_need_different_suffixes(self):
        arcs = [Arc(0, 1, "x", "x", 0), Arc(0, 1, "y", "y", 0),
                Arc(1, 2, "a", "a", 1), Arc(1, 2, "b", "b", 2)]
        costs = {("x", "a"): 5, ("y", "b"): 5}
        actual = self.compare(arcs, 2, costs, k=4)
        self.assertEqual([p.text for p in actual.candidates], ["ya", "xb", "xa", "yb"])
        self.compare([Arc(0, 1, "a", "a", 1), Arc(0, 1, "b", "b", 2)], 1, costs, incoming="x", k=1)
        self.compare([Arc(0, 1, "a", "a", 1), Arc(0, 1, "b", "b", 2)], 1, costs, incoming="y", k=1)

    def test_character_cost_is_segmentation_invariant(self):
        costs = {(None, "a"): 1, ("a", "b"): 2, ("b", "c"): 3, ("q", "a"): 7}
        partitions = [[Arc(0, 3, "abc", "z", 3)],
                      [Arc(0, 1, "a", "a", 1), Arc(1, 3, "bc", "b", 2)],
                      [Arc(0, 2, "ab", "a", 2), Arc(2, 3, "c", "b", 1)]]
        for incoming, expected in [(None, 6), ("q", 12)]:
            for arcs in partitions:
                result = self.compare(arcs, 3, costs, incoming=incoming)
                self.assertEqual(result.candidates[0].context_cost, expected)
                self.assertEqual(result.candidates[0].cost, expected + 3)
        combined = self.compare(list(itertools.chain.from_iterable(partitions)), 3, costs)
        self.assertEqual(combined.candidates[0].reading, "z")

    def test_equal_cost_reading_ties_finish_after_last_text_cutoff(self):
        arcs = [Arc(0, 2, "ab", reading, 0) for reading in ("a", "z", "zz", "y")]
        arcs += [Arc(0, 1, "a", "q", 0), Arc(1, 2, "b", "z", 0), Arc(0, 2, "ac", "other", 0)]
        result = self.compare(arcs, 2, {}, k=1)
        self.assertEqual((result.candidates[0].text, result.candidates[0].reading), ("ab", "zz"))

    def test_dedup_across_many_paths_does_not_consume_distinct_budget(self):
        arcs = [Arc(0, 2, "ab", f"r{i:03d}", 0) for i in range(200)]
        arcs += [Arc(0, 1, "a", "a", 0), Arc(1, 2, "b", "b", 0),
                 Arc(0, 2, "ac", "c", 1), Arc(0, 2, "ad", "d", 2)]
        result = self.compare(arcs, 2, {}, k=3)
        self.assertEqual([p.text for p in result.candidates], ["ab", "ac", "ad"])
        self.assertEqual(result.candidates[0].reading, "r199")

    def test_more_than_ninety_outputs_and_unicode_ties(self):
        arcs = [Arc(0, 1, chr(0x4e00 + i), str(i), i % 3) for i in range(220)]
        result = self.compare(arcs, 1, {}, k=90)
        self.assertEqual(len(result.candidates), 90)
        self.assertEqual(len({p.text for p in result.candidates}), 90)

    def test_prefix_text_lexical_ties_and_zero_cost_paths(self):
        arcs = [Arc(0, 1, "a", "a", 0), Arc(0, 1, "aa", "b", 0),
                Arc(1, 2, "a", "c", 0), Arc(1, 2, "z", "d", 0)]
        result = self.compare(arcs, 2, {}, k=4)
        self.assertEqual([p.text for p in result.candidates], ["aa", "aaa", "aaz", "az"])

    def test_unreachable_and_dead_end_edges(self):
        self.assertEqual(self.compare([Arc(0, 1, "a", "a", 0)], 2, {}).candidates, ())
        self.compare([Arc(0, 2, "a", "a", 1), Arc(1, 2, "x", "x", 0)], 2, {})

    def test_random_integer_graphs_against_exhaustive_oracle(self):
        generator = random.Random(20261024)
        alphabet = "abc"
        for graph_id in range(320):
            end = generator.randrange(2, 6)
            arcs = []
            for start in range(end):
                for _ in range(generator.randrange(1, 4)):
                    stop = generator.randrange(start + 1, end + 1)
                    text = "".join(generator.choices(alphabet, k=generator.randrange(1, 4)))
                    reading = generator.choice(["a", "aa", "b", "b a", "z"])
                    arcs.append(Arc(start, stop, text, reading, generator.randrange(5)))
            costs = {(previous, letter): generator.randrange(5) for previous in [None, *alphabet] for letter in alphabet}
            for incoming in (None, "a", "c"):
                for k in (1, 3, 5):
                    with self.subTest(graph=graph_id, incoming=incoming, k=k):
                        self.compare(arcs, end, costs, incoming=incoming, k=k)

    def test_limits_are_explicit_before_reservation_overrun(self):
        arcs = [Arc(0, 1, "甲", "gaa1", 1), Arc(0, 1, "乙", "jyut3", 2),
                Arc(1, 2, "丙", "bing2", 1), Arc(1, 2, "丁", "ding1", 2)]
        baseline = decode(arcs, 2, CharacterModel({}), k=4)
        for resource, used in baseline.counters.items():
            self.assertGreater(used, 1)
            with self.subTest(resource=resource):
                limits = replace(Limits(), **{resource: used - 1})
                with self.assertRaises(CapacityError) as caught:
                    decode(arcs, 2, CharacterModel({}), k=4, limits=limits)
                failure = caught.exception
                self.assertEqual(failure.resource, resource)
                self.assertLessEqual(failure.used, failure.limit)
                self.assertGreater(failure.used + failure.requested, failure.limit)
                self.assertLessEqual(failure.counters[resource], failure.limit)
                with self.assertRaises(TypeError):
                    failure.counters[resource] = 999
        # Exactly observed cumulative work/memory reservations must succeed.
        exact = replace(Limits(), **dict(baseline.counters))
        self.assertEqual(actual_rows(decode(arcs, 2, CharacterModel({}), k=4, limits=exact)), actual_rows(baseline))

    def test_output_length_and_reading_allocation_limits(self):
        arcs = [Arc(0, 1, "甲乙", "a b", 0), Arc(1, 2, "丙丁", "c d", 0)]
        for resource, limit in [("output_chars", 3), ("reading_chars", 6)]:
            with self.subTest(resource=resource), self.assertRaises(CapacityError) as caught:
                decode(arcs, 2, CharacterModel({}), limits=replace(Limits(), **{resource: limit}))
            self.assertEqual(caught.exception.resource, resource)
            self.assertEqual(caught.exception.counters["pushes"], 1)
        # First candidate's concatenated UTF-8 text cannot fit. No push/path
        # reservation occurs, and there is no partial successful result.
        with self.assertRaises(CapacityError) as caught:
            decode([Arc(0, 1, "甲", "a", 0)], 1, CharacterModel({}), limits=replace(Limits(), text_bytes=2))
        self.assertEqual(caught.exception.counters["pushes"], 0)
        self.assertEqual(caught.exception.counters["text_bytes"], 0)

    def test_input_graph_model_and_integer_parameter_validation(self):
        normal = Arc(0, 1, "a", "a", 0)
        bad_arcs = [replace(normal, start=-1), replace(normal, end=0), replace(normal, end=2),
                    replace(normal, text=""), replace(normal, reading=""), replace(normal, text="\ud800"),
                    replace(normal, cost=-1), replace(normal, cost=float("inf")), replace(normal, cost=float("nan")),
                    replace(normal, cost=True)]
        for arc in bad_arcs:
            with self.subTest(arc=repr(arc)), self.assertRaises(ValueError):
                decode([arc], 1, CharacterModel({}))
        for k in [0, 91, True, 1.5]:
            with self.assertRaises(ValueError):
                decode([normal], 1, CharacterModel({}), k=k)
        for end in [0, 257, True, 1.5]:
            with self.assertRaises(ValueError):
                decode([normal], end, CharacterModel({}))
        for incoming in ["", "ab", 1]:
            with self.assertRaises(ValueError):
                decode([normal], 1, CharacterModel({}), incoming=incoming)
        for value in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError):
                decode([normal], 1, CharacterModel({}), limits=replace(Limits(), states=value))
        for costs in [{("ab", "c"): 1}, {("a", ""): 1}, {("a", "b"): -1}, {("a", "b"): float("nan")}]:
            with self.assertRaises(ValueError):
                CharacterModel(costs)
        with self.assertRaises(ValueError):
            decode([normal, normal], 1, CharacterModel({}), limits=replace(Limits(), arcs=1))

    def test_result_and_model_are_immutable(self):
        costs = {(None, "a"): 1}
        model = CharacterModel(costs)
        costs[(None, "a")] = 999
        result = decode([Arc(0, 1, "a", "a", 1)], 1, model)
        self.assertEqual(result.candidates[0].cost, 2)
        self.assertIsInstance(result.candidates, tuple)
        with self.assertRaises(TypeError):
            result.counters["pushes"] = 999
        with self.assertRaises(TypeError):
            model.costs[(None, "a")] = 999
        with self.assertRaises(FrozenInstanceError):
            model.default = 999
        with self.assertRaises(FrozenInstanceError):
            result.candidates = ()


if __name__ == "__main__":
    unittest.main(verbosity=2)
