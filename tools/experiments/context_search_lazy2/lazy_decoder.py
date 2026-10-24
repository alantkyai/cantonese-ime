"""Exact bounded lexicographic A* with cached one-step context bounds.

This experimental search has no eager suffix/context table and no prefix
dominance pruning. Paths stay as backpointers until completion. The caller's
retained DAG is the search boundary; this does not recover discarded arcs.
"""
from dataclasses import dataclass
import hashlib
import heapq
import importlib.util
from pathlib import Path
import sys
from types import MappingProxyType

HERE = Path(__file__).resolve().parent
TYPES_SHA256 = "7c355e1ff76e501ec908c4c0493eefd87a2325affbdc010c2451c546a9bb96ac"
if hashlib.sha256((HERE / "mechanical_types.py").read_bytes()).hexdigest() != TYPES_SHA256:
    raise ValueError("Mechanical type source changed")
spec = importlib.util.spec_from_file_location("_context_cycle3_lazy_types", HERE / "mechanical_types.py")
types = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = types
spec.loader.exec_module(types)
Arc, Hypothesis, Limits = types.Arc, types.Hypothesis, types.Limits
CharacterModel, CapacityError = types.CharacterModel, types.CapacityError


@dataclass(frozen=True)
class Result:
    candidates: tuple[Hypothesis, ...]
    counters: object
    statistics: object
    complete_within_retained_graph: bool = True


@dataclass(frozen=True, slots=True)
class _Node:
    position: int
    previous: str | None
    cost: int
    lexical: int
    context: int
    parent: object
    arc: Arc | None
    words: int
    chars: int
    reading_chars: int
    text_bytes: int
    reading_bytes: int
    prefix: str


def decode(arcs, end, model, *, k=9, incoming=None, limits=None, work_limit=100000):
    limits = limits or Limits()
    budget = types._Budget(limits)
    if type(end) is not int or not 1 <= end < limits.vertices:
        raise ValueError("Invalid input-position bound")
    if type(k) is not int or not 1 <= k <= limits.k:
        raise ValueError("Invalid K")
    if type(work_limit) is not int or not 1 <= work_limit <= 100000:
        raise ValueError("Work limit must be1..100000")
    if incoming is not None and (not isinstance(incoming, str) or len(incoming) != 1):
        raise ValueError("Invalid incoming character")
    if not isinstance(arcs, (list, tuple)) or len(arcs) > limits.arcs:
        raise ValueError("Retained arc bound")
    if not isinstance(model, CharacterModel) or len(model.costs) > limits.model_pairs:
        raise ValueError("Invalid transition model")
    statistics = {"work": 0, "input_arcs": len(arcs), "productive_arcs": 0, "dead_arcs_pruned": 0,
                  "context_suffix_tables": 0, "transition_cache_hits": 0, "transition_requests": 0,
                  "heuristic_character_visits": 0, "edge_expansions": 0, "complete_paths": 0,
                  "peak_frontier": 0, "cutoff_cost": None, "cutoff_text": None,
                  "h1_requests": 0, "h1_cache_hits": 0, "h1_arc_scans": 0}

    def fail(resource, used, requested, cap):
        error = CapacityError(resource, used, requested, cap, budget.counts)
        error.statistics = MappingProxyType(dict(statistics))
        raise error

    def reserve(**changes):
        try:
            budget.reserve(**changes)
        except CapacityError as error:
            error.statistics = MappingProxyType(dict(statistics))
            raise

    def work(count=1):
        if statistics["work"] + count > work_limit:
            fail("work", statistics["work"], count, work_limit)
        statistics["work"] += count

    adjacency = {}
    for arc in arcs:
        work()
        if (not isinstance(arc, Arc) or type(arc.start) is not int or type(arc.end) is not int
                or not 0 <= arc.start < arc.end <= end or type(arc.cost) is not int
                or not 0 <= arc.cost <= 10**12
                or not isinstance(arc.text, str) or not 1 <= len(arc.text) <= limits.output_chars
                or not isinstance(arc.reading, str) or not 1 <= len(arc.reading) <= limits.reading_chars
                or arc.reading != arc.reading.strip()):
            raise ValueError("Invalid integer-cost arc")
        try:
            byte_count = len(arc.text.encode("utf-8"))
            reading_bytes = len(arc.reading.encode("utf-8"))
        except UnicodeError as error:
            raise ValueError("Invalid Unicode scalar arc") from error
        if arc.start not in adjacency:
            adjacency[arc.start] = []
        adjacency[arc.start].append((arc, byte_count, reading_bytes))
    reachable, pending = {0}, [0]
    while pending:
        start = pending.pop()
        for arc, _, _ in adjacency.get(start, ()):
            work()
            if arc.end not in reachable:
                reachable.add(arc.end)
                pending.append(arc.end)
    productive = {end}
    for start in sorted(adjacency, reverse=True):
        for arc, _, _ in adjacency[start]:
            work()
            if arc.end in productive:
                productive.add(start)
                break
    if 0 not in productive:
        statistics["dead_arcs_pruned"] = len(arcs)
        return Result((), MappingProxyType(dict(budget.counts)), MappingProxyType(dict(statistics)))

    transition_cache = {}

    def transition(previous, current):
        work()
        statistics["transition_requests"] += 1
        key = previous, current
        if key in transition_cache:
            statistics["transition_cache_hits"] += 1
            return transition_cache[key]
        if len(transition_cache) >= limits.model_pairs:
            fail("model_pairs", len(transition_cache), 1, limits.model_pairs)
        reserve(transitions=1)  # Actual distinct model evaluations.
        value, last = model.consume(previous, current)
        if type(value) is not int or not 0 <= value <= 10**12 or last != current:
            raise ValueError("Model must emit nonnegative integer transition costs")
        transition_cache[key] = value
        return value

    # Internal character costs are independent of incoming context. Reuse one
    # calculation per distinct emitted word; the incoming boundary is deferred.
    internals, graph, heuristic = {}, {}, {end: 0}
    minimum_text, minimum_bytes = {end: ""}, {end: 0}
    for start in sorted(adjacency, reverse=True):
        if start not in reachable or start not in productive:
            statistics["dead_arcs_pruned"] += len(adjacency[start])
            continue
        rows = []
        best = None
        lexical_minimum = None
        lexical_minimum_bytes = 0
        for arc, byte_count, reading_bytes in adjacency[start]:
            work()
            if arc.end not in productive:
                statistics["dead_arcs_pruned"] += 1
                continue
            if arc.text not in internals:
                internal = 0
                for index in range(1, len(arc.text)):
                    statistics["heuristic_character_visits"] += 1
                    internal += transition(arc.text[index - 1], arc.text[index])
                internals[arc.text] = internal
            internal = internals[arc.text]
            candidate = arc.cost + internal + heuristic[arc.end]
            best = candidate if best is None else min(best, candidate)
            text_length = len(arc.text) + len(minimum_text[arc.end])
            if text_length > limits.output_chars:
                fail("output_chars", 0, text_length, limits.output_chars)
            generated_bytes = byte_count + minimum_bytes[arc.end]
            work()  # One bounded concat; byte generation is reserved separately.
            reserve(text_bytes=generated_bytes)
            candidate_text = arc.text + minimum_text[arc.end]
            if lexical_minimum is None or candidate_text < lexical_minimum:
                lexical_minimum = candidate_text
                lexical_minimum_bytes = generated_bytes
            rows.append((arc, byte_count, reading_bytes, internal, candidate))
            statistics["productive_arcs"] += 1
        work(len(rows))  # Bound key evaluation before the finite-row sort.
        rows.sort(key=lambda row: row[4])
        graph[start] = rows
        if best is not None:
            heuristic[start] = best
            minimum_text[start] = lexical_minimum
            minimum_bytes[start] = lexical_minimum_bytes

    h1_cache = {}

    def h1(position, previous):
        work()
        statistics["h1_requests"] += 1
        if position == end:
            return 0
        key = position, previous
        if key in h1_cache:
            statistics["h1_cache_hits"] += 1
            return h1_cache[key]
        reserve(states=1)  # One cached scalar bound per visited context state.
        best = None
        for arc, _, _, _, baseline in graph[position]:
            work()
            statistics["h1_arc_scans"] += 1
            if best is not None and baseline >= best:
                break  # All further baselines >= best; boundary costs >=0.
            value = baseline + transition(previous, arc.text[0])
            best = value if best is None else min(best, value)
        if best is None:
            raise AssertionError("Productive position had no continuation")
        h1_cache[key] = best
        return best

    heap, sequence = [], 0

    def push(position, previous, lexical, context, parent, arc, words, chars, rchars, text_bytes, reading_bytes, cutoff):
        nonlocal sequence
        if chars > limits.output_chars:
            fail("output_chars", 0, chars, limits.output_chars)
        if rchars > limits.reading_chars:
            fail("reading_chars", 0, rchars, limits.reading_chars)
        lower_cost = lexical + context + h1(position, previous)
        if cutoff is not None and lower_cost > cutoff[0]:
            return
        key_chars = chars + len(minimum_text[position])
        if key_chars > limits.output_chars:
            fail("output_chars", 0, key_chars, limits.output_chars)
        # Prefix and key creation are both charged before concatenation.
        # At the root reuse the precomputed suffix string with no copy.
        prefix_bytes = text_bytes if parent is not None else 0
        key_bytes = text_bytes + minimum_bytes[position] if parent is not None and minimum_text[position] else 0
        work(2 if parent is not None else 1)
        reserve(text_bytes=prefix_bytes + key_bytes)
        prefix = parent.prefix + arc.text if parent is not None else ""
        key_text = (minimum_text[position] if parent is None else
                    prefix + minimum_text[position] if minimum_text[position] else prefix)
        if cutoff is not None and (lower_cost, key_text) > cutoff:
            return  # Exact pair lower bound, never a beam or prefix rule.
        reserve(hypotheses=1, pushes=1)
        node = _Node(position, previous, lexical + context, lexical, context, parent, arc,
                     words, chars, rchars, text_bytes, reading_bytes, prefix)
        heapq.heappush(heap, (lower_cost, key_text, sequence, node))
        sequence += 1
        statistics["peak_frontier"] = max(statistics["peak_frontier"], len(heap))

    push(0, incoming, 0, 0, None, None, 0, 0, 0, 0, 0, None)
    winners, cutoff = {}, None
    while heap:
        if cutoff is not None and heap[0][:2] > cutoff:
            break
        reserve(pops=1)
        _, _, _, node = heapq.heappop(heap)
        if node.position == end:
            statistics["complete_paths"] += 1
            work(node.words)
            reserve(hypotheses=1, reading_bytes=node.reading_bytes)
            readings, cursor = [], node
            while cursor.arc is not None:
                readings.append(cursor.arc.reading)
                cursor = cursor.parent
            text, reading = node.prefix, " ".join(reversed(readings))
            path = Hypothesis(text, reading, node.cost, node.lexical, node.context,
                              node.words, node.text_bytes, node.reading_bytes)
            old = winners.get(text)
            if old is None or path.cost < old.cost or (path.cost == old.cost and path.reading > old.reading):
                winners[text] = path
            # Pair bounds are consistent in cost and written-text order. Finish
            # every path with lower bound <=(kth cost,kth written text), so the
            # greatest complete reading wins even with alternate segmentation.
            if cutoff is None and len(winners) >= k:
                cutoff = path.cost, path.text
                statistics["cutoff_cost"], statistics["cutoff_text"] = cutoff
            continue
        for arc, byte_count, reading_bytes, internal, _ in graph[node.position]:
            work()
            statistics["edge_expansions"] += 1
            boundary = transition(node.previous, arc.text[0])
            lexical = node.lexical + arc.cost
            context = node.context + internal + boundary
            lower_bound = lexical + context + heuristic[arc.end]
            if cutoff is not None and lower_bound > cutoff[0]:
                continue  # Exact cost bound, never a beam or output-prefix rule.
            push(arc.end, arc.text[-1], lexical, context, node, arc, node.words + 1,
                 node.chars + len(arc.text), node.reading_chars + bool(node.words) + len(arc.reading),
                 node.text_bytes + byte_count, node.reading_bytes + bool(node.words) + reading_bytes, cutoff)
    output = tuple(sorted(winners.values(), key=lambda path: (path.cost, path.text))[:k])
    return Result(output, MappingProxyType(dict(budget.counts)), MappingProxyType(dict(statistics)))
