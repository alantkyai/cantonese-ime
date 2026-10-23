"""Bounded syllable decoding over a read-only Cantonese lexicon.

This is a reference engine, independent of TSF and of librime's runtime. Its
dictionary importer reuses licensed language data. Candidate ranking is an
initial unigram model, not a claim of Google-equivalent prediction quality.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
import heapq
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
from typing import Iterable

from .mappings import spelling_variants, yale_ascii


MODES = ("jyutping", "forgiving")
MAX_INPUT_LENGTH = 256
MAX_CANDIDATES = 90
MAX_OFFSET = 10000
_COMPOSITION_WORK_LIMIT = 100000
_FUZZY_COST = 6.0
_MAX_LEARNING_BYTES = 4_000_000
_MAX_LEARNING_RECORDS = 10000
_LEARNING_DECAY = 0.8
_LEARNING_MAX_WEIGHT = 5.0
_LEARNING_WRITE_LOCK = threading.RLock()
_READING = re.compile(r"^([a-z]+)([1-6])$")
_INPUT = re.compile(r"^[a-z1-6' ]+$")
_TONED_RUN = re.compile(r"([a-z]+)([1-6])")


@dataclass(frozen=True, slots=True)
class Candidate:
    text: str
    reading: str
    score: float
    match_type: str
    consumed_input: int


@dataclass(frozen=True, slots=True)
class CandidatePage:
    """A stable slice of the engine's ranked candidate pool.

    Stored full-input homophones are not capped at 90. Sentence decoding and
    prefix completion retain their existing bounded search. When generated
    search exceeds its work/row budget, ``completion_truncated`` is true;
    continuing beyond the available pool raises ``PaginationCapacityError``
    instead of incorrectly reporting that no further matches exist. A composed
    search budget failure does not discard valid complete dictionary words.
    """

    candidates: tuple[Candidate, ...]
    offset: int
    next_offset: int | None
    completion_truncated: bool = False


class PaginationCapacityError(RuntimeError):
    """The bounded completion pool cannot supply the requested next page."""


class CompositionCapacityError(RuntimeError):
    """The bounded composed-phrase search cannot finish this input."""


@dataclass(frozen=True, slots=True)
class _PrefixEntries:
    entries: tuple[_Entry, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class _Snapshot:
    candidates: tuple[Candidate, ...]
    completion_truncated: bool


@dataclass(frozen=True, slots=True)
class _Entry:
    text: str
    reading: str
    base: str
    weight: float


@dataclass(slots=True)
class _Node:
    children: dict[str, _Node] = field(default_factory=dict)
    outputs: list[tuple[str, float]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Edge:
    end: int
    base: str
    tone: str | None
    penalty: float


@dataclass(frozen=True, slots=True)
class _Path:
    end: int
    bases: tuple[str, ...]
    tones: tuple[str | None, ...]
    penalty: float


@dataclass(frozen=True, slots=True)
class _Arc:
    end: int
    entry: _Entry
    penalty: float


@dataclass(frozen=True, slots=True)
class _Sentence:
    text: str
    readings: tuple[str, ...]
    cost: float
    penalty: float
    words: int


def _spellings(base: str) -> dict[str, float]:
    """Use the same versioned rules as the exported spelling-map artifact."""
    return spelling_variants(base, mode="forgiving")


@contextmanager
def _learning_file_lock(path: Path):
    """Serialize read/merge/replace across instances and local processes."""
    with _LEARNING_WRITE_LOCK:
        with path.with_name(path.name + ".lock").open("a+b") as stream:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                def acquire():
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)

                def release():
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                def acquire():
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                def release():
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    acquire()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Learning data is busy in another process.")
                    time.sleep(0.025)
            try:
                yield
            finally:
                release()


class Engine:
    """One local lexicon and optional, explicitly enabled selection memory.

    ``lookup`` accepts numeric tones. A frontend must choose how tone entry and
    numbered candidate selection share keys; the prototype Session reserves
    digits for candidate selection. No files are written unless learning_path
    is supplied and record_selection is called.
    """

    MAX_INPUT_LENGTH = MAX_INPUT_LENGTH
    MAX_OFFSET = MAX_OFFSET

    def __init__(
        self,
        db_path: str | Path,
        mode: str = "forgiving",
        learning_path: str | Path | None = None,
    ) -> None:
        self._check_mode(mode)
        self.mode = mode
        self.path = Path(db_path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Dictionary not found: {self.path}. Run tools/build_dictionary.py first.")
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, check_same_thread=False)
        try:
            columns = {row[1] for row in self._db.execute("PRAGMA table_info(entries)")}
            if not {"text", "reading", "base_reading", "weight"}.issubset(columns):
                raise ValueError("Dictionary has an unsupported entries schema.")
            self._known: set[str] = set()
            self._prefixes: set[str] = set()
            self._longer: set[str] = set()
            self._max_word_syllables = 1
            bases: set[str] = set()
            for (reading,) in self._db.execute("SELECT DISTINCT base_reading FROM entries"):
                tokens = reading.split()
                if not tokens:
                    continue
                self._max_word_syllables = max(self._max_word_syllables, len(tokens))
                bases.update(tokens)
                self._known.add(reading)
                for size in range(1, len(tokens) + 1):
                    prefix = " ".join(tokens[:size])
                    self._prefixes.add(prefix)
                    if size < len(tokens):
                        self._longer.add(prefix)
            self._roots = {name: _Node() for name in MODES}
            self._variants: dict[str, dict[str, list[tuple[str, float]]]] = {name: {} for name in MODES}
            for base in sorted(bases):
                if not base.isascii() or not base.isalpha():
                    raise ValueError("Dictionary contains a noncanonical base syllable.")
                self._insert("jyutping", base, base, 0.0)
                for spelling, penalty in _spellings(base).items():
                    self._insert("forgiving", spelling, base, penalty)
            # Index each complete stored reading independently of the bounded
            # syllable frontier. A valid Yale word must not disappear because
            # other possible syllable splits occupy that frontier first.
            yale_forms = {
                base: (yale_ascii(base), _spellings(base)[yale_ascii(base)])
                for base in bases
            }
            self._yale_readings: dict[str, list[tuple[str, float]]] = {}
            for reading in sorted(self._known):
                forms = [yale_forms[base] for base in reading.split()]
                compact = "".join(form for form, _ in forms)
                penalty = sum(cost for _, cost in forms)
                self._yale_readings.setdefault(compact, []).append((reading, penalty))
            total, count = self._db.execute("SELECT COALESCE(SUM(weight),0), COUNT(*) FROM entries").fetchone()
            self._log_total = math.log(max(1.0, float(total) + count))
            self._by_base = lru_cache(maxsize=8192)(self._read_base)
            self._by_prefix = lru_cache(maxsize=512)(self._read_prefix)
            self.learning_path = Path(learning_path).resolve() if learning_path is not None else None
            self._selections: dict[tuple[str, str, str, str], int] = {}
            self._adaptive_weights: dict[tuple[str, str, str, str], float] = {}
            self._load_learning()
            self._learning_generation = 0
            self._snapshot_key: tuple[str, int, str, int] | None = None
            self._snapshot_value: _Snapshot | None = None
        except Exception:
            self._db.close()
            raise

    @staticmethod
    def _check_mode(mode: str) -> None:
        if mode not in MODES:
            raise ValueError("Mode must be 'jyutping' or 'forgiving'.")

    def _insert(self, mode: str, spelling: str, base: str, penalty: float) -> None:
        node = self._roots[mode]
        for letter in spelling:
            node = node.children.setdefault(letter, _Node())
        node.outputs.append((base, penalty))
        self._variants[mode].setdefault(spelling, []).append((base, penalty))

    @staticmethod
    def _normalise(raw: str) -> str | None:
        if not isinstance(raw, str) or not raw or len(raw) > MAX_INPUT_LENGTH:
            return None
        value = raw.lower().strip(" ")
        if not value or not _INPUT.fullmatch(value):
            return None
        if value[0] in "123456' " or re.search(r"[1-6]{2}|[1-6](?=[' ]?[1-6])|[' ]{2}", value):
            return None
        return value.replace(" ", "'")

    def _read_base(self, base: str) -> tuple[_Entry, ...]:
        cursor = self._db.execute(
            "SELECT text, reading, weight FROM entries WHERE base_reading=? ORDER BY weight DESC,text,reading", (base,)
        )
        try:
            return tuple(_Entry(text, reading, base, float(weight)) for text, reading, weight in cursor)
        finally:
            cursor.close()

    def _read_prefix(
        self, prefix: str, tones: tuple[str | None, ...], excluded_bases: tuple[str, ...] = (),
    ) -> _PrefixEntries:
        sql = (
            "SELECT text,reading,base_reading,weight FROM entries "
            "WHERE base_reading>=? AND base_reading<?"
        )
        parameters = [prefix, prefix + "{"]
        if excluded_bases:
            sql += " AND base_reading NOT IN (" + ",".join("?" for _ in excluded_bases) + ")"
            parameters.extend(excluded_bases)
        sql += " ORDER BY weight DESC,text,reading"
        if not any(tones):
            sql += " LIMIT 129"
        result = []
        cursor = self._db.execute(sql, parameters)
        try:
            for text, reading, base, weight in cursor:
                if self._tones_match(reading, tones):
                    result.append(_Entry(text, reading, base, float(weight)))
                    if len(result) >= 129:
                        break
        finally:
            cursor.close()
        return _PrefixEntries(tuple(result[:128]), len(result) > 128)

    @staticmethod
    def _tones_match(reading: str, tones: Iterable[str | None]) -> bool:
        readings = reading.split()
        requested = tuple(tones)
        return len(readings) >= len(requested) and all(
            tone is None or readings[index].endswith(tone) for index, tone in enumerate(requested)
        )

    def lookup(self, raw: str, limit: int = 9, mode: str | None = None) -> list[Candidate]:
        selected_mode = self.mode if mode is None else mode
        self._check_mode(selected_mode)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_CANDIDATES:
            raise ValueError(f"limit must be an integer from 1 to {MAX_CANDIDATES}.")
        value = self._normalise(raw)
        if value is None:
            return []
        with self._lock:
            return list(self._snapshot(value, len(raw), selected_mode).candidates[:limit])

    def lookup_page(
        self, raw: str, *, offset: int = 0, page_size: int = 9, mode: str | None = None,
    ) -> CandidatePage:
        """Page stored homophones without changing the legacy lookup limit.

        Offsets address the same post-learning, per-text-deduplicated order as
        ``lookup``. A ``next_offset`` at a truncated completion pool boundary
        advertises an unresolved tail; requesting it raises a catchable capacity
        error. Refine the input in that case. Learned completions outside this
        bounded pool are not guaranteed to surface.
        """
        selected_mode = self.mode if mode is None else mode
        self._check_mode(selected_mode)
        if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= MAX_OFFSET:
            raise ValueError(f"offset must be an integer from 0 to {MAX_OFFSET}.")
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= MAX_CANDIDATES:
            raise ValueError(f"page_size must be an integer from 1 to {MAX_CANDIDATES}.")
        value = self._normalise(raw)
        if value is None:
            return CandidatePage((), offset, None)
        with self._lock:
            snapshot = self._snapshot(value, len(raw), selected_mode)
            total = len(snapshot.candidates)
            if offset >= total and snapshot.completion_truncated:
                raise PaginationCapacityError(
                    "Candidate search exceeds the bounded pool; refine the input to continue."
                )
            candidates = snapshot.candidates[offset:offset + page_size]
            end = offset + len(candidates)
            more = end < total or snapshot.completion_truncated
            # A limit is an explicit error, never an invented end of results.
            if more and end > MAX_OFFSET:
                raise PaginationCapacityError(f"Candidate pagination exceeds the maximum offset {MAX_OFFSET}.")
            return CandidatePage(candidates, offset, end if more else None, snapshot.completion_truncated)

    def _snapshot(self, value: str, consumed: int, mode: str) -> _Snapshot:
        key = (value, consumed, mode, self._learning_generation)
        if self._snapshot_key != key:
            snapshot = self._decode(value, consumed, mode)
            # A failed read/decode leaves the last successful snapshot intact.
            self._snapshot_value = snapshot
            self._snapshot_key = key
        assert self._snapshot_value is not None
        return self._snapshot_value

    def _stored_yale_arcs(self, value: str) -> Iterable[_Arc]:
        """All full stored readings for tone-free Yale, preserving collisions.

        Optional apostrophes must fall at actual syllable boundaries. Numeric
        tones continue through the general decoder with its closure rules.
        This index does not generate readings or alter dictionary provenance.
        """
        compact = value.replace("'", "")
        if not compact.isalpha():
            return
        for base_reading, penalty in self._yale_readings.get(compact, ()):
            position = 0
            for base in base_reading.split():
                spelling = yale_ascii(base)
                if not value.startswith(spelling, position):
                    break
                position += len(spelling)
                if position < len(value) and value[position] == "'":
                    position += 1
            else:
                if position == len(value):
                    for entry in self._by_base(base_reading):
                        yield _Arc(len(value), entry, penalty)

    def _decode(self, value: str, consumed: int, mode: str) -> _Snapshot:
        size = len(value)
        root = self._roots[mode]
        # A numeric tone closes an indivisible syllable when the entire letter
        # run since the preceding digit/boundary is a supported spelling. Thus
        # ngo5 cannot become untoned ng + o5. A run such as neihou2 remains
        # segmentable because neihou is not one supported syllable; ng'o5 also
        # retains its explicit boundary. The selected mode controls aliases.
        protected_spans: dict[int, int] = {}
        protected_interiors: set[int] = set()
        for match in _TONED_RUN.finditer(value):
            if match.group(1) not in self._variants[mode]:
                continue
            start, end = match.span()
            protected_interiors.update(range(start + 1, end))
            if end < size and value[end] == "'":
                end += 1
            protected_spans[start] = end

        @lru_cache(maxsize=MAX_INPUT_LENGTH + 1)
        def edges(start: int) -> tuple[_Edge, ...]:
            if start in protected_interiors:
                return ()
            node = root
            result: dict[tuple[int, str, str | None], _Edge] = {}
            protected_end = protected_spans.get(start)
            for position in range(start, min(size, start + 12)):
                letter = value[position]
                if not ("a" <= letter <= "z") or letter not in node.children:
                    break
                node = node.children[letter]
                end = position + 1
                tone = None
                if end < size and value[end] in "123456":
                    tone = value[end]
                    end += 1
                if end < size and value[end] == "'":
                    end += 1
                if protected_end is not None and end != protected_end:
                    continue
                if end in protected_interiors:
                    continue
                for base, penalty in node.outputs:
                    edge = _Edge(end, base, tone, penalty)
                    key = (end, base, tone)
                    if key not in result or penalty < result[key].penalty:
                        result[key] = edge
            return tuple(sorted(result.values(), key=lambda e: (e.penalty, -e.end, e.base)))

        direct_arcs: dict[tuple[str, str], _Arc] = {}

        @lru_cache(maxsize=MAX_INPUT_LENGTH + 1)
        def arcs(start: int) -> tuple[_Arc, ...]:
            frontier = [_Path(start, (), (), 0.0)]
            found: dict[tuple[int, str, str], _Arc] = {}
            for _ in range(min(MAX_INPUT_LENGTH, self._max_word_syllables)):
                following: dict[tuple[int, tuple[str, ...], tuple[str | None, ...]], _Path] = {}
                for path in frontier:
                    for edge in edges(path.end):
                        bases = path.bases + (edge.base,)
                        base = " ".join(bases)
                        if base not in self._prefixes:
                            continue
                        tones = path.tones + (edge.tone,)
                        penalty = path.penalty + edge.penalty
                        if base in self._known:
                            # Tone filtering precedes candidate truncation/deduplication.
                            matching = (entry for entry in self._by_base(base) if self._tones_match(entry.reading, tones))
                            for index, entry in enumerate(matching):
                                direct = start == 0 and edge.end == size
                                if index >= MAX_CANDIDATES and not direct:
                                    break
                                arc = _Arc(edge.end, entry, penalty)
                                if direct:
                                    direct_key = (entry.text, entry.reading)
                                    if direct_key not in direct_arcs or penalty < direct_arcs[direct_key].penalty:
                                        direct_arcs[direct_key] = arc
                                if index >= MAX_CANDIDATES:
                                    continue
                                key = (arc.end, entry.text, entry.reading)
                                if key not in found or penalty < found[key].penalty:
                                    found[key] = arc
                        if edge.end < size and base in self._longer:
                            key = (edge.end, bases, tones)
                            candidate = _Path(edge.end, bases, tones, penalty)
                            if key not in following or penalty < following[key].penalty:
                                following[key] = candidate
                frontier = sorted(following.values(), key=lambda p: (p.penalty, -p.end, p.bases))[:96]
                if not frontier:
                    break
            # Retain a bounded pool per ending position so a common one-syllable
            # reading cannot crowd out a longer word required for sentence decoding.
            grouped: dict[int, list[_Arc]] = defaultdict(list)
            for arc in found.values():
                grouped[arc.end].append(arc)
            return tuple(
                arc
                for end in sorted(grouped)
                for arc in sorted(grouped[end], key=lambda a: (_FUZZY_COST * a.penalty - math.log1p(a.entry.weight), a.penalty, a.entry.text, a.entry.reading))[:MAX_CANDIDATES]
            )

        candidates: list[Candidate] = []
        indexed_yale_arcs = tuple(self._stored_yale_arcs(value)) if mode == "forgiving" else ()
        for arc in indexed_yale_arcs:
            direct_arcs[(arc.entry.text, arc.entry.reading)] = arc
        # Long dictionary words used to exceed the frontend's 64-letter bound.
        # Serve their indexed full matches promptly, including exact personal
        # phrases, instead of spending the native 250ms deadline on optional
        # sentence alternatives. The omitted tail is explicitly reported.
        indexed_long_word = size > 64 and bool(indexed_yale_arcs)
        if not indexed_long_word:
            arcs(0)
        for arc in direct_arcs.values():
            kind = "exact" if arc.penalty == 0 else "fuzzy"
            score = 1000.0 - _FUZZY_COST * arc.penalty + min(50.0, math.log1p(arc.entry.weight))
            candidates.append(Candidate(arc.entry.text, arc.entry.reading, score, kind, consumed))

        composition_truncated = indexed_long_word
        try:
            sentences = () if indexed_long_word else self._compose_sentences(arcs, size)
        except CompositionCapacityError:
            if not direct_arcs:
                raise
            # Optional composed alternatives must not hide a dictionary word
            # already matched in full. The public truncation flag and a later
            # paging capacity error preserve the limit instead of claiming an
            # exhaustive candidate set.
            sentences = ()
            composition_truncated = True
        for hypothesis in sentences:
            score = 800.0 - hypothesis.cost - _FUZZY_COST * hypothesis.penalty
            candidates.append(Candidate(hypothesis.text, " ".join(hypothesis.readings), score, "composed", consumed))

        direct_bases = {arc.entry.base for arc in direct_arcs.values()}
        completions, completion_truncated = ([], False) if indexed_long_word else self._completions(value, consumed, mode, edges, direct_bases)
        candidates.extend(completions)
        # Personal phrase memory is limited to the exact normalized full input
        # and mode originally selected. It can retain a valid composed phrase
        # that a later bounded static search drops, without prefix prediction.
        existing_pairs = {(candidate.text, candidate.reading) for candidate in candidates}
        for learned_mode, learned_input, text, reading in self._selections:
            if (learned_mode == mode and learned_input == value
                    and (text, reading) not in existing_pairs):
                candidates.append(Candidate(text, reading, 800.0, "learned", consumed))
        unique: dict[str, Candidate] = {}
        for candidate in candidates:
            memory = self._adaptive_weights.get((mode, value, candidate.text, candidate.reading), 0.0)
            if memory:
                candidate = Candidate(candidate.text, candidate.reading, candidate.score + 10000 * memory, candidate.match_type, consumed)
            previous = unique.get(candidate.text)
            if previous is None or (candidate.score, candidate.reading) > (previous.score, previous.reading):
                unique[candidate.text] = candidate
        return _Snapshot(tuple(sorted(unique.values(), key=lambda c: (-c.score, c.text, c.reading))), completion_truncated or composition_truncated)

    def _compose_sentences(self, arcs, size: int, *, work_limit: int = _COMPOSITION_WORK_LIMIT) -> tuple[_Sentence, ...]:
        """Best 90 distinct composed texts on the retained dictionary-arc DAG.

        A suffix below the best 90 distinct suffix texts cannot contribute to
        the best 90 at its parent: prepending the same arc adds the same cost
        and preserves distinctness and text order. Merge each arc's sorted
        suffix stream lazily, rather than expanding their Cartesian product.
        Arc discovery still has its separate phonetic/row bounds. This is not
        an exhaustive search over dictionary paths discarded by those bounds.
        """
        graph = {}
        pending = [0]
        visited = {0}
        while pending:
            position = pending.pop()
            rows = []
            for arc in arcs(position):
                if not position < arc.end <= size:
                    raise ValueError("Composition arcs must advance through input.")
                # Stored full-input words already have their direct priority.
                # They must not take the composed-output budget before filtering.
                if position == 0 and arc.end == size:
                    continue
                rows.append((arc, max(0.0, self._log_total - math.log1p(arc.entry.weight))))
                if arc.end != size and arc.end not in visited:
                    visited.add(arc.end)
                    pending.append(arc.end)
            graph[position] = rows

        def rank(path):
            return path.cost + _FUZZY_COST * path.penalty, path.text

        states = {size: (_Sentence("", (), 0.0, 0.0, 0),)}
        work = 0
        for position in sorted(graph, reverse=True):
            streams = []
            heap = []

            def push(stream, index):
                arc, cost, tails = streams[stream]
                tail = tails[index]
                path = _Sentence(
                    arc.entry.text + tail.text,
                    (arc.entry.reading,) + tail.readings,
                    cost + tail.cost,
                    arc.penalty + tail.penalty,
                    tail.words + 1,
                )
                heapq.heappush(heap, (*rank(path), " ".join(path.readings), stream, index, path))

            for arc, cost in graph[position]:
                tails = states.get(arc.end, ())
                if tails:
                    streams.append((arc, cost, tails))
                    push(len(streams) - 1, 0)
            unique = {}
            cutoff = None
            while heap:
                # Finish ties for the last selected text so its greatest
                # equally scored reading wins, matching public text dedup.
                if cutoff is not None and heap[0][:2] > cutoff:
                    break
                work += 1
                if work > work_limit:
                    raise CompositionCapacityError(
                        "Composition exceeds the bounded search budget; add tones or syllable boundaries to refine the input."
                    )
                cost, text, reading, stream, index, path = heapq.heappop(heap)
                previous = unique.get(text)
                if previous is None or cost < rank(previous)[0] or (
                    cost == rank(previous)[0] and reading > " ".join(previous.readings)
                ):
                    unique[text] = path
                if len(unique) >= MAX_CANDIDATES:
                    cutoff = cost, text
                if index + 1 < len(streams[stream][2]):
                    push(stream, index + 1)
            states[position] = tuple(sorted(unique.values(), key=rank)[:MAX_CANDIDATES])
        return states.get(0, ())

    def _completions(self, value: str, consumed: int, mode: str, edges, direct_bases: set[str]) -> tuple[list[Candidate], bool]:
        size = len(value)
        frontier = [_Path(0, (), (), 0.0)]
        queries: dict[tuple[str, tuple[str | None, ...]], float] = {}
        visited: set[tuple[int, tuple[str, ...], tuple[str | None, ...]]] = set()
        for _ in range(MAX_INPUT_LENGTH):
            following: list[_Path] = []
            for path in frontier:
                remaining = value[path.end:]
                prefix = " ".join(path.bases)
                if not remaining:
                    if prefix:
                        queries[(prefix + " ", path.tones)] = path.penalty
                    continue
                if remaining.isascii() and remaining.isalpha():
                    query = (prefix + " " if prefix else "") + remaining
                    key = (query, path.tones)
                    queries[key] = min(path.penalty, queries.get(key, math.inf))
                    # Completion through aliases is bounded independently of the
                    # ordinary canonical prefix query.
                    alternatives = [
                        (base, path.penalty + penalty)
                        for spelling, outputs in self._variants[mode].items()
                        if spelling.startswith(remaining) and spelling != remaining
                        for base, penalty in outputs
                        if penalty > 0
                    ]
                    for base, penalty in sorted(alternatives, key=lambda pair: (pair[1], pair[0]))[:8]:
                        key = ((prefix + " " if prefix else "") + base, path.tones)
                        queries[key] = min(penalty, queries.get(key, math.inf))
                for edge in edges(path.end):
                    bases = path.bases + (edge.base,)
                    # A committed syllable path can complete a stored word only
                    # if it is a prefix of some stored reading. Discard impossible
                    # internal splits before they spend the frontier/query budget.
                    if " ".join(bases) not in self._prefixes:
                        continue
                    tones = path.tones + (edge.tone,)
                    key = (edge.end, bases, tones)
                    if key in visited or len(bases) > MAX_INPUT_LENGTH:
                        continue
                    visited.add(key)
                    following.append(_Path(edge.end, bases, tones, path.penalty + edge.penalty))
            frontier = sorted(following, key=lambda p: (p.penalty, -p.end, p.bases))[:32]
            if not frontier:
                break
        result: list[Candidate] = []
        truncated = False
        for (prefix, tones), penalty in sorted(queries.items(), key=lambda item: (item[1], -len(item[0][0]), item[0][0]))[:32]:
            # Full stored readings are already exhaustive in direct_arcs. Do
            # not let their duplicate rows occupy the prefix completion budget.
            excluded = tuple(sorted(base for base in direct_bases if base.startswith(prefix)))
            pool = self._by_prefix(prefix, tones, excluded)
            truncated = truncated or pool.truncated
            for entry in pool.entries:
                # Exact full readings are already supplied by dictionary arcs.
                score = 600.0 - penalty * _FUZZY_COST + min(50.0, math.log1p(entry.weight))
                result.append(Candidate(entry.text, entry.reading, score, "completion", consumed))
        return result, truncated

    def _load_learning(self) -> None:
        if self.learning_path is None or not self.learning_path.exists():
            return
        try:
            if self.learning_path.stat().st_size > _MAX_LEARNING_BYTES:
                raise ValueError("Learning file exceeds the size limit.")
            content = json.loads(self.learning_path.read_text(encoding="utf-8"))
            schema = content.get("schema_version")
            if type(schema) is not int or schema not in (1, 2) or not isinstance(content.get("selections"), list):
                raise ValueError("Unsupported learning schema.")
            if len(content["selections"]) > _MAX_LEARNING_RECORDS:
                raise ValueError("Learning file has too many records.")
            for item in content["selections"]:
                mode, raw, text, reading, count = (item[name] for name in ("mode", "input", "text", "reading", "count"))
                if mode not in MODES or not isinstance(raw, str) or self._normalise(raw) != raw or not isinstance(text, str) or not text or len(text) > 256:
                    raise ValueError("Invalid learning record.")
                text.encode("utf-8")
                if not isinstance(reading, str) or not reading or len(reading.split()) > MAX_INPUT_LENGTH or not all(_READING.fullmatch(token) for token in reading.split()):
                    raise ValueError("Invalid learning reading.")
                if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1000000:
                    raise ValueError("Invalid learning count.")
                adaptive_weight = min(float(count), _LEARNING_MAX_WEIGHT) if schema == 1 else item["adaptive_weight"]
                if (isinstance(adaptive_weight, bool) or not isinstance(adaptive_weight, (int, float))
                        or not 0 <= adaptive_weight <= _LEARNING_MAX_WEIGHT or not math.isfinite(adaptive_weight)):
                    raise ValueError("Invalid adaptive learning weight.")
                key = (mode, raw, text, reading)
                self._selections[key] = count
                self._adaptive_weights[key] = float(adaptive_weight)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise ValueError(f"Cannot read learning data: {error}") from error

    def record_selection(self, raw: str, candidate: Candidate, mode: str | None = None) -> None:
        if self.learning_path is None:
            return
        selected_mode = self.mode if mode is None else mode
        self._check_mode(selected_mode)
        value = self._normalise(raw)
        if value is None:
            raise ValueError("Cannot learn an invalid input.")
        with self._lock:
            available = self._snapshot(value, len(raw), selected_mode).candidates
            if not any(item.text == candidate.text and item.reading == candidate.reading for item in available):
                raise ValueError("Selection is not a candidate for this input.")
            key = (selected_mode, value, candidate.text, candidate.reading)
            self.learning_path.parent.mkdir(parents=True, exist_ok=True)
            with _learning_file_lock(self.learning_path):
                # Refresh under the lock so an instance opened earlier cannot
                # overwrite selections saved by a different engine/process.
                previous = self._selections
                previous_weights = self._adaptive_weights
                try:
                    self._selections = {}
                    self._adaptive_weights = {}
                    self._load_learning()
                    updated = dict(self._selections)
                    weights = dict(self._adaptive_weights)
                finally:
                    self._selections = previous
                    self._adaptive_weights = previous_weights
                if key not in updated and len(updated) >= _MAX_LEARNING_RECORDS:
                    oldest = min(updated, key=lambda entry: (weights[entry], updated[entry], entry))
                    del updated[oldest]
                    del weights[oldest]
                updated[key] = min(updated.get(key, 0) + 1, 1000000)
                # Adapt only competing choices for this exact mode/full input.
                # A long phrase never changes shorter-prefix preferences.
                for entry in weights:
                    if entry[:2] == key[:2]:
                        weights[entry] = round(weights[entry] * _LEARNING_DECAY, 12)
                weights[key] = min(_LEARNING_MAX_WEIGHT, round(weights.get(key, 0.0) + 1.0, 12))

                def encode() -> bytes:
                    payload = {"schema_version": 2, "selections": [
                        {"mode": m, "input": i, "text": t, "reading": r, "count": count,
                         "adaptive_weight": weights[(m, i, t, r)]}
                        for (m, i, t, r), count in sorted(updated.items())
                    ]}
                    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

                encoded = encode()
                eviction_order = iter(sorted((item for item in updated if item != key),
                                             key=lambda item: (weights[item], updated[item], item)))
                while len(encoded) > _MAX_LEARNING_BYTES:
                    for _ in range(max(1, len(updated) // 10)):
                        try:
                            evicted = next(eviction_order)
                            del updated[evicted]
                            del weights[evicted]
                        except StopIteration:
                            raise ValueError("Selection exceeds the learning data size limit.") from None
                    encoded = encode()
                descriptor, temporary = tempfile.mkstemp(prefix=".learning-", suffix=".json", dir=self.learning_path.parent)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(encoded)
                    os.replace(temporary, self.learning_path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                self._selections = updated
                self._adaptive_weights = weights
                self._learning_generation += 1
                self._snapshot_key = None
                self._snapshot_value = None

    def close(self) -> None:
        with self._lock:
            self._by_base.cache_clear()
            self._by_prefix.cache_clear()
            self._snapshot_key = None
            self._snapshot_value = None
            self._db.close()

    def __enter__(self) -> Engine:
        return self

    def __exit__(self, *_args) -> None:
        self.close()
