"""Synthetic, bounded character-context k-best proof. Not product IME code.

The caller supplies a retained, advancing lexical DAG.  A state includes its
incoming character, so every fixed-arc suffix stream is sorted under the same
objective as its parent.  Limits count cumulative logical work/allocation;
they are not measurements of Python RSS or control of caller-owned inputs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import heapq
import math
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class Arc:
    start: int
    end: int
    text: str
    reading: str
    cost: int | float


@dataclass(frozen=True)
class Hypothesis:
    text: str
    reading: str
    cost: int | float
    lexical_cost: int | float
    context_cost: int | float
    words: int
    text_bytes: int
    reading_bytes: int


@dataclass(frozen=True)
class Limits:
    vertices: int = 257
    arcs: int = 4096
    states: int = 1024
    transitions: int = 32768
    pushes: int = 100000
    pops: int = 100000
    hypotheses: int = 32768
    text_bytes: int = 8 * 1024 * 1024
    reading_bytes: int = 16 * 1024 * 1024
    output_chars: int = 1024
    reading_chars: int = 8192
    k: int = 90
    model_pairs: int = 131072


class CapacityError(RuntimeError):
    def __init__(self, resource: str, used: int, requested: int, limit: int, counters: Mapping[str, int]):
        super().__init__(f"{resource}: {used} + {requested} exceeds {limit}")
        self.resource = resource
        self.used = used
        self.requested = requested
        self.limit = limit
        self.counters = MappingProxyType(dict(counters))


class _Budget:
    def __init__(self, limits: Limits):
        for name, value in asdict(limits).items():
            if type(value) is not int or value < 1:
                raise ValueError(f"Limit {name} must be a positive integer")
        self.limits = limits
        self.counts = {name: 0 for name in ("states", "transitions", "pushes", "pops", "hypotheses", "text_bytes", "reading_bytes")}

    def reserve(self, **changes: int) -> None:
        # Validate the whole reservation before changing counters or allocating
        # its state/transition/path/string/heap element.
        for resource, count in changes.items():
            used = self.counts[resource]
            limit = getattr(self.limits, resource)
            if used + count > limit:
                raise CapacityError(resource, used, count, limit, self.counts)
        for resource, count in changes.items():
            self.counts[resource] += count


def _valid_cost(value: int | float) -> bool:
    return type(value) in (int, float) and 0 <= value <= 1e12 and math.isfinite(value)


@dataclass(frozen=True, init=False)
class CharacterModel:
    """Immutable nonnegative character-bigram costs; None denotes BOS.

    There is no EOS cost in this proof. The caller owns model estimation and
    licensing. No supplied costs are derived from language-quality examples.
    """
    costs: Mapping[tuple[str | None, str], int | float]
    default: int | float

    def __init__(self, costs: Mapping[tuple[str | None, str], int | float], *, default: int | float = 0):
        if not _valid_cost(default):
            raise ValueError("Invalid default context cost")
        # Absolute preparation bound precedes copying a caller-owned mapping.
        if len(costs) > 131072:
            raise ValueError("Model exceeds preparation bound")
        for key, cost in costs.items():
            if (not isinstance(key, tuple) or len(key) != 2
                    or (key[0] is not None and (not isinstance(key[0], str) or len(key[0]) != 1))
                    or not isinstance(key[1], str) or len(key[1]) != 1 or not _valid_cost(cost)):
                raise ValueError("Invalid character transition")
        object.__setattr__(self, "costs", MappingProxyType(dict(costs)))
        object.__setattr__(self, "default", default)

    def consume(self, incoming: str | None, text: str) -> tuple[int | float, str]:
        total = 0
        previous = incoming
        for letter in text:
            total += self.costs.get((previous, letter), self.default)
            previous = letter
        assert previous is not None  # Arc text is validated nonempty.
        return total, previous


@dataclass(frozen=True)
class Result:
    candidates: tuple[Hypothesis, ...]
    counters: Mapping[str, int]
    complete_within_retained_graph: bool = True


def decode(arcs: tuple[Arc, ...] | list[Arc], end: int, model: CharacterModel, *,
           k: int = 9, incoming: str | None = None, limits: Limits | None = None) -> Result:
    """Exact top-k distinct written texts on a supplied finite retained DAG.

    Equal-cost pronunciations for one text choose the greatest reading string,
    matching the existing product's text-dedup policy. A capacity exception
    returns no partial Result. Integer-valued fixtures have exact arithmetic;
    floating-point addition retains the usual association/ULP limitations.
    """
    limits = limits or Limits()
    budget = _Budget(limits)
    if type(end) is not int or end < 1 or end + 1 > limits.vertices:
        raise ValueError("Invalid end/input-position bound")
    if type(k) is not int or not 1 <= k <= limits.k:
        raise ValueError("Invalid k")
    if incoming is not None and (not isinstance(incoming, str) or len(incoming) != 1):
        raise ValueError("Incoming context must be one character or None")
    if not isinstance(model, CharacterModel) or len(model.costs) > limits.model_pairs:
        raise ValueError("Invalid model/model-pair bound")
    if not isinstance(arcs, (tuple, list)) or len(arcs) > limits.arcs:
        raise ValueError("Invalid retained-arc bound")

    # Validate every arc before copying adjacency. Length checks precede UTF-8
    # encoding, and retained input has independent finite size bounds.
    for arc in arcs:
        if (not isinstance(arc, Arc) or type(arc.start) is not int or type(arc.end) is not int
                or not 0 <= arc.start < arc.end <= end
                or not isinstance(arc.text, str) or not 1 <= len(arc.text) <= limits.output_chars
                or not isinstance(arc.reading, str) or not 1 <= len(arc.reading) <= limits.reading_chars
                or arc.reading != arc.reading.strip() or not _valid_cost(arc.cost)):
            raise ValueError("Invalid retained arc")
        try:
            arc.text.encode("utf-8")
            arc.reading.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("Arc is not Unicode scalar text") from exc
    adjacency: dict[int, list[tuple[Arc, int, int]]] = {}
    for arc in arcs:
        adjacency.setdefault(arc.start, []).append((arc, len(arc.text.encode("utf-8")), len(arc.reading.encode("utf-8"))))

    # Discover the reachable context-conditioned DAG in forward order. Every
    # state and transition is reserved before its associated container append.
    initial = (0, incoming)
    budget.reserve(states=1)
    reachable = {initial}
    pending = [initial]
    graph: dict[tuple[int, str | None], list[tuple[Arc, int, int, int | float, tuple[int, str]]]] = {}
    while pending:
        state = pending.pop()
        position, previous = state
        rows = []
        if position != end:
            for arc, byte_count, reading_byte_count in adjacency.get(position, ()):
                # Count character-transition work rather than only whole arcs.
                budget.reserve(transitions=len(arc.text))
                extra, next_context = model.consume(previous, arc.text)
                next_state = (arc.end, next_context)
                if next_state not in reachable:
                    budget.reserve(states=1)
                    reachable.add(next_state)
                    pending.append(next_state)
                rows.append((arc, byte_count, reading_byte_count, extra, next_state))
        graph[state] = rows

    suffixes: dict[tuple[int, str | None], tuple[Hypothesis, ...]] = {}
    for state in sorted(reachable, key=lambda item: item[0], reverse=True):
        if state[0] == end:
            budget.reserve(hypotheses=1)
            suffixes[state] = (Hypothesis("", "", 0, 0, 0, 0, 0, 0),)
            continue
        streams = []
        heap = []

        def push(stream: int, index: int) -> None:
            arc, byte_count, reading_byte_count, extra, tails = streams[stream]
            tail = tails[index]
            char_count = len(arc.text) + len(tail.text)
            reading_count = len(arc.reading) + bool(tail.reading) + len(tail.reading)
            if char_count > limits.output_chars:
                raise CapacityError("output_chars", 0, char_count, limits.output_chars, budget.counts)
            if reading_count > limits.reading_chars:
                raise CapacityError("reading_chars", 0, reading_count, limits.reading_chars, budget.counts)
            combined_bytes = byte_count + tail.text_bytes
            combined_reading_bytes = reading_byte_count + bool(tail.reading) + tail.reading_bytes
            budget.reserve(hypotheses=1, text_bytes=combined_bytes,
                           reading_bytes=combined_reading_bytes, pushes=1)
            # Reservation and length checks happen before either concatenation.
            text = arc.text + tail.text
            reading = arc.reading + (" " + tail.reading if tail.reading else "")
            path = Hypothesis(text, reading, arc.cost + extra + tail.cost,
                              arc.cost + tail.lexical_cost, extra + tail.context_cost,
                              tail.words + 1, combined_bytes, combined_reading_bytes)
            heapq.heappush(heap, (path.cost, path.text, stream, index, path))

        for arc, byte_count, reading_byte_count, extra, target in graph[state]:
            tails = suffixes.get(target, ())
            if tails:
                streams.append((arc, byte_count, reading_byte_count, extra, tails))
                push(len(streams) - 1, 0)
        chosen = []
        seen = set()
        while heap and len(chosen) < k:
            group_key = heap[0][:2]
            winner = None
            # Finish the entire equal-cost/text group, including successors
            # just exposed by a pop, before publishing a pronunciation winner.
            while heap and heap[0][:2] == group_key:
                budget.reserve(pops=1)
                _, _, stream, index, path = heapq.heappop(heap)
                if winner is None or path.reading > winner.reading:
                    winner = path
                if index + 1 < len(streams[stream][4]):
                    push(stream, index + 1)
            assert winner is not None
            if winner.text not in seen:
                seen.add(winner.text)
                chosen.append(winner)
        suffixes[state] = tuple(chosen)
    return Result(suffixes.get(initial, ()), MappingProxyType(dict(budget.counts)))
