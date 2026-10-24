"""Exact bounded static suffix merge or scalar-context lexicographic A*.

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


@dataclass(slots=True)
class _Group:
    first: str
    rows: list
    unseen: int = 0
    pending: object = None
    emitted: object = None


@dataclass(slots=True)
class _Context:
    position: int
    previous: str | None
    cost: int | None = None
    unseen: int = 0
    pending: object = None
    emitted: object = None
    advance: object = None


@dataclass(slots=True)
class _Position:
    groups: list
    unseen: int = 0
    pending: object = None
    emitted: object = None


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
    static_zero = type(model) is CharacterModel and not model.costs and type(model.default) is int and model.default == 0
    statistics = {"work": 0, "input_arcs": len(arcs), "productive_arcs": 0, "dead_arcs_pruned": 0,
                  "context_suffix_tables": 0, "transition_cache_hits": 0, "transition_requests": 0,
                  "heuristic_character_visits": 0, "edge_expansions": 0, "complete_paths": 0,
                  "peak_frontier": 0, "cutoff_cost": None, "cutoff_text": None,
                  "hstar_requests": 0, "hstar_cache_hits": 0, "hstar_arc_scans": 0,
                  "static_suffix_tables": 0, "factored_groups": 0,
                  "t_requests": 0, "t_cache_hits": 0, "t_arc_scans": 0,
                  "outgoing_requests": 0, "outgoing_cache_hits": 0,
                  "outgoing_group_scans": 0, "continuation_pushes": 0, "continuation_pops": 0,
                  "position_min_streams": 0, "position_min_requests": 0,
                  "position_min_cache_hits": 0, "position_min_refinements": 0}

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
            if not static_zero and arc.text not in internals:
                internal = 0
                for index in range(1, len(arc.text)):
                    statistics["heuristic_character_visits"] += 1
                    internal += transition(arc.text[index - 1], arc.text[index])
                internals[arc.text] = internal
            internal = 0 if static_zero else internals[arc.text]
            candidate = arc.cost + internal + heuristic[arc.end]
            best = candidate if best is None else min(best, candidate)
            if not static_zero:
                text_length = len(arc.text) + len(minimum_text[arc.end])
                if text_length > limits.output_chars:
                    fail("output_chars", 0, text_length, limits.output_chars)
                generated_bytes = byte_count + minimum_bytes[arc.end]
                work()  # One bounded concat; byte generation reserved separately.
                reserve(text_bytes=generated_bytes)
                candidate_text = arc.text + minimum_text[arc.end]
                if lexical_minimum is None or candidate_text < lexical_minimum:
                    lexical_minimum = candidate_text
                    lexical_minimum_bytes = generated_bytes
            rows.append((arc, byte_count, reading_bytes, internal, candidate) if static_zero else
                        (arc, byte_count, reading_bytes, internal, candidate, candidate_text, generated_bytes))
            statistics["productive_arcs"] += 1
        work(len(rows))  # Bound key evaluation before the finite-row sort.
        rows.sort(key=lambda row: (row[4], row[5]) if not static_zero else (row[4],))
        graph[start] = rows
        if best is not None:
            heuristic[start] = best
            if not static_zero:
                minimum_text[start] = lexical_minimum
                minimum_bytes[start] = lexical_minimum_bytes

    if static_zero:
        # Fixed text/reading prefixes preserve the sorted suffix-stream order.
        # Any (k+1)th distinct suffix has k distinct predecessors within its own
        # stream, so it cannot belong to the parent's distinct-text topK. All
        # same(cost,text) items are exhausted before choosing greatest reading.
        # This branch is legal ONLY for the exact immutable empty-zero class:
        # callback subclasses may have empty .costs but emit nonzero context.
        suffixes = {}
        reserve(states=1, hypotheses=1)
        suffixes[end] = (Hypothesis("", "", 0, 0, 0, 0, 0, 0),)
        statistics["static_suffix_tables"] += 1
        for start in sorted(graph, reverse=True):
            reserve(states=1)
            statistics["static_suffix_tables"] += 1
            heap, streams, sequence = [], [], 0

            def static_push(stream_index, tail_index):
                nonlocal sequence
                arc, byte_count, reading_bytes, tails = streams[stream_index]
                if tail_index >= len(tails):
                    return
                work()
                statistics["edge_expansions"] += 1
                tail = tails[tail_index]
                chars = len(arc.text) + len(tail.text)
                rchars = len(arc.reading) + bool(tail.reading) + len(tail.reading)
                if chars > limits.output_chars:
                    fail("output_chars", 0, chars, limits.output_chars)
                if rchars > limits.reading_chars:
                    fail("reading_chars", 0, rchars, limits.reading_chars)
                tbytes = byte_count + tail.text_bytes
                rbytes = reading_bytes + bool(tail.reading) + tail.reading_bytes
                reserve(pushes=1, hypotheses=1, text_bytes=tbytes, reading_bytes=rbytes)
                text = arc.text + tail.text
                reading = " ".join((arc.reading, tail.reading)) if tail.reading else arc.reading
                cost = arc.cost + tail.cost
                candidate = Hypothesis(text, reading, cost, cost, 0, tail.words + 1, tbytes, rbytes)
                heapq.heappush(heap, (cost, text, sequence, stream_index, tail_index, candidate))
                sequence += 1
                statistics["peak_frontier"] = max(statistics["peak_frontier"], len(heap))

            for arc, byte_count, reading_bytes, _, _ in graph[start]:
                work()
                streams.append((arc, byte_count, reading_bytes, suffixes[arc.end]))
                static_push(len(streams) - 1, 0)
            output, seen = [], set()
            while heap and len(output) < k:
                pair = heap[0][:2]
                winner = None
                while heap and heap[0][:2] == pair:
                    work()
                    reserve(pops=1)
                    _, _, _, stream_index, tail_index, candidate = heapq.heappop(heap)
                    statistics["complete_paths"] += 1
                    if winner is None or candidate.reading > winner.reading:
                        winner = candidate
                    static_push(stream_index, tail_index + 1)
                if winner.text not in seen:
                    seen.add(winner.text)
                    output.append(winner)
            suffixes[start] = tuple(output)
        output = suffixes[0]
        if len(output) == k:
            statistics["cutoff_cost"] = output[-1].cost
            statistics["cutoff_text"] = output[-1].text
        return Result(output, MappingProxyType(dict(budget.counts)), MappingProxyType(dict(statistics)))

    # Group records are structurally bounded by arcs and additionally charged
    # to the shared hypotheses budget before their lists/cache publication.
    groups = {}
    for position, rows in graph.items():
        buckets = {}
        for row in rows:
            work()
            first = row[0].text[0]
            if first not in buckets:
                reserve(hypotheses=1)
                buckets[first] = _Group(first, [], pending=[], emitted=[])
                statistics["factored_groups"] += 1
            buckets[first].rows.append(row)  # Total row references <= arcs.
        work(len(buckets))
        groups[position] = sorted(buckets.values(), key=lambda group: (group.rows[0][4], group.rows[0][5]))
    contexts, positions = {}, {}

    def context(position, previous):
        key = position, previous
        state = contexts.get(key)
        if state is None:
            reserve(states=1)
            state = _Context(position, previous, pending=[], emitted=[])
            contexts[key] = state
        return state

    def group_item(group, index):
        # T(pos,first) and the entire sorted outgoing arc stream are shared
        # across every incoming context. Each arc's child H* is refined once.
        work()
        statistics["t_requests"] += 1
        if index < len(group.emitted):
            statistics["t_cache_hits"] += 1
            return group.emitted[index]
        while len(group.emitted) <= index:
            while group.unseen < len(group.rows):
                row = group.rows[group.unseen]
                lower = row[4], row[5]
                if group.pending and group.pending[0][:2] <= lower:
                    break
                work()
                statistics["t_arc_scans"] += 1
                arc, _, _, internal, _, text_key, _ = row
                total = arc.cost + internal + hstar(arc.end, arc.text[-1])
                reserve(hypotheses=1, pushes=1)
                # One immutable cached row/heap item, reused after popping.
                heapq.heappush(group.pending, (total, text_key, group.unseen, row))
                group.unseen += 1
                statistics["peak_frontier"] = max(statistics["peak_frontier"], len(group.pending))
            if not group.pending:
                return None
            work()
            reserve(pops=1)
            group.emitted.append(heapq.heappop(group.pending))
        return group.emitted[index]

    def position_item(position, index, cutoff=None):
        # Shared group HEAD bounds, not an arc/argmin filter. Cost-only scalar
        # cutoffs are resumable; outgoing callers use no cutoff and retain all
        # groups plus every alternative in the separate full group arc stream.
        work()
        statistics["position_min_requests"] += 1
        stream = positions.get(position)
        if stream is None:
            reserve(hypotheses=1)
            stream = _Position(groups[position], pending=[], emitted=[])
            positions[position] = stream
            statistics["position_min_streams"] += 1
        if index < len(stream.emitted):
            statistics["position_min_cache_hits"] += 1
            item = stream.emitted[index]
            return None if cutoff is not None and item[0] >= cutoff else item
        while len(stream.emitted) <= index:
            while stream.unseen < len(stream.groups):
                group = stream.groups[stream.unseen]
                lower = group.rows[0][4], group.rows[0][5]
                pending_pair = stream.pending[0][:2] if stream.pending else None
                if cutoff is not None and lower[0] >= cutoff and (pending_pair is None or pending_pair[0] >= cutoff):
                    return None  # No state lost; a later larger cutoff resumes.
                if pending_pair is not None and pending_pair <= lower:
                    break
                work()
                statistics["position_min_refinements"] += 1
                item = group_item(group, 0)
                reserve(hypotheses=1, pushes=1)
                heapq.heappush(stream.pending, (item[0], item[1], group.first, group))
                stream.unseen += 1
                statistics["peak_frontier"] = max(statistics["peak_frontier"], len(stream.pending))
            if not stream.pending or (cutoff is not None and stream.pending[0][0] >= cutoff):
                return None
            work()
            reserve(pops=1)
            stream.emitted.append(heapq.heappop(stream.pending))
        return stream.emitted[index]

    def hstar(position, previous):
        work()
        statistics["hstar_requests"] += 1
        if position == end:
            return 0
        state = context(position, previous)
        if state.cost is not None:
            statistics["hstar_cache_hits"] += 1
            return state.cost
        best, index = None, 0
        while True:
            item = position_item(position, index, best)
            if item is None:
                break
            work()
            statistics["hstar_arc_scans"] += 1
            minimum, _, _, group = item
            boundary = transition(previous, group.first)
            value = boundary + minimum
            best = value if best is None else min(best, value)
            index += 1
        if best is None:
            raise AssertionError("Productive position had no continuation")
        state.cost = best
        return best

    def outgoing_item(state, index):
        # Every prefix owns its own index into this immutable realized stream.
        # Realizing one prefix does not consume another prefix's alternatives.
        work()
        statistics["outgoing_requests"] += 1
        if index < len(state.emitted):
            statistics["outgoing_cache_hits"] += 1
            return state.emitted[index]

        def insert(group, item_index, boundary):
            item = group_item(group, item_index)
            if item is None:
                return
            reserve(hypotheses=1, pushes=1)
            total, text_key, row_index, row = item
            # This immutable merge item is retained as an emitted descriptor.
            heapq.heappush(state.pending, (boundary + total, text_key,
                                         group.first, item_index, boundary, group, row))
            statistics["peak_frontier"] = max(statistics["peak_frontier"], len(state.pending))

        while len(state.emitted) <= index:
            if state.advance is not None:
                old = state.advance
                state.advance = None
                insert(old[5], old[3] + 1, old[4])
            while True:
                head = position_item(state.position, state.unseen)
                if head is None:
                    break
                lower = head[:2]
                if state.pending and state.pending[0][:2] <= lower:
                    break
                work()
                statistics["outgoing_group_scans"] += 1
                group = head[3]
                boundary = transition(state.previous, group.first)
                insert(group, 0, boundary)
                state.unseen += 1
            if not state.pending:
                return None
            work()
            reserve(pops=1)
            item = heapq.heappop(state.pending)
            state.emitted.append(item)
            state.advance = item  # Reuse it for deferred next-group-item work.
        return state.emitted[index]

    heap, sequence = [], 0

    def schedule(parent, index, cutoff):
        nonlocal sequence
        state = context(parent.position, parent.previous)
        item = outgoing_item(state, index)
        if item is None:
            return
        total, _, _, _, _, _, row = item
        lower_cost = parent.cost + total
        if cutoff is not None and lower_cost > cutoff[0]:
            return
        key_chars = parent.chars + len(row[5])
        if key_chars > limits.output_chars:
            fail("output_chars", 0, key_chars, limits.output_chars)
        work()
        key_bytes = parent.text_bytes + row[6]
        reserve(text_bytes=key_bytes)
        key_text = parent.prefix + row[5]
        if cutoff is not None and (lower_cost, key_text) > cutoff:
            return
        reserve(hypotheses=1, pushes=1)
        heapq.heappush(heap, (lower_cost, key_text, sequence, parent, index, item))
        sequence += 1
        statistics["continuation_pushes"] += 1
        statistics["peak_frontier"] = max(statistics["peak_frontier"], len(heap))

    # H* is evaluated lazily by the same factored groups later used by outgoing
    # streams. At most three recursive helper frames are added per advancing
    # position; the full256-position chain is a synthetic regression control.
    hstar(0, incoming)
    reserve(hypotheses=1)
    root = _Node(0, incoming, 0, 0, 0, None, None, 0, 0, 0, 0, 0, "")
    schedule(root, 0, None)
    winners, cutoff = {}, None
    while heap:
        if cutoff is not None and heap[0][:2] > cutoff:
            break
        reserve(pops=1)
        _, _, _, parent, index, item = heapq.heappop(heap)
        statistics["continuation_pops"] += 1
        work()
        statistics["edge_expansions"] += 1
        _, _, _, _, boundary, _, row = item
        arc, byte_count, reading_bytes, internal, _, _, _ = row
        chars = parent.chars + len(arc.text)
        rchars = parent.reading_chars + bool(parent.words) + len(arc.reading)
        if chars > limits.output_chars:
            fail("output_chars", 0, chars, limits.output_chars)
        if rchars > limits.reading_chars:
            fail("reading_chars", 0, rchars, limits.reading_chars)
        tbytes = parent.text_bytes + byte_count
        rbytes = parent.reading_bytes + bool(parent.words) + reading_bytes
        reserve(hypotheses=1, text_bytes=tbytes)
        prefix = parent.prefix + arc.text
        lexical, extra = parent.lexical + arc.cost, parent.context + internal + boundary
        node = _Node(arc.end, arc.text[-1], lexical + extra, lexical, extra,
                     parent, arc, parent.words + 1, chars, rchars, tbytes, rbytes, prefix)
        if arc.end == end:
            statistics["complete_paths"] += 1
            work(node.words)
            reserve(hypotheses=1, reading_bytes=node.reading_bytes)
            readings, cursor = [], node
            while cursor.arc is not None:
                readings.append(cursor.arc.reading)
                cursor = cursor.parent
            reading = " ".join(reversed(readings))
            path = Hypothesis(node.prefix, reading, node.cost, node.lexical, node.context,
                              node.words, node.text_bytes, node.reading_bytes)
            old = winners.get(path.text)
            if old is None or path.cost < old.cost or (path.cost == old.cost and path.reading > old.reading):
                winners[path.text] = path
            if cutoff is None and len(winners) >= k:
                cutoff = path.cost, path.text
                statistics["cutoff_cost"], statistics["cutoff_text"] = cutoff
        else:
            schedule(node, 0, cutoff)
        # Reinsert the exact next sibling before applying the global cutoff.
        # The unexpanded tail remains represented by this one continuation.
        schedule(parent, index + 1, cutoff)
    output = tuple(sorted(winners.values(), key=lambda path: (path.cost, path.text))[:k])
    return Result(output, MappingProxyType(dict(budget.counts)), MappingProxyType(dict(statistics)))
