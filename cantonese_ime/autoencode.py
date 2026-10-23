"""Auditable offline compatibility implementation of Rime ScriptEncoder.

Algorithm adapted from librime, Copyright RIME Developers, BSD-3-Clause.
Full notice: data/licenses/librime-BSD-3-Clause.txt. Pinned source references
are in ALGORITHM_PROVENANCE below. Generated codes are mechanically derived;
they are not newly authored or independently verified phrase pronunciations.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import math
import re
from typing import Iterable


LIBRIME_COMMIT = "1b3417d2b6a11b5e50e0e1fa9dc396056aa11dce"
MAX_PHRASE_CODEPOINTS = 32
MAX_ENCODER_PATHS = 32
MIN_READING_WEIGHT_SHARE = 0.05
ALGORITHM_PROVENANCE = {
    "name": "librime ScriptEncoder + EntryCollector.TranslateWord",
    "repository": "https://github.com/rime/librime",
    "commit": LIBRIME_COMMIT,
    "encoder_url": f"https://github.com/rime/librime/blob/{LIBRIME_COMMIT}/src/rime/algo/encoder.cc",
    "collector_url": f"https://github.com/rime/librime/blob/{LIBRIME_COMMIT}/src/rime/dict/entry_collector.cc",
    "license": "BSD-3-Clause",
    "local_license": "data/licenses/librime-BSD-3-Clause.txt",
    "adaptations": [
        "Valid Unicode text boundaries only; invalid UTF-8 substring probes cannot match valid source text.",
        "Suffix reachability avoids dead DFS branches without changing the order of successful paths.",
        "A finite work guard reports truncated instead of silently selecting a reading.",
        "Reaching the 32-path limit is conservatively marked truncated, even if exactly 32 paths exist.",
        "Returned codes are deduplicated in first-emission order; path_count retains duplicate DFS paths.",
    ],
}
_READING = re.compile(r"[a-z]+[1-6]\Z")


@dataclass(frozen=True, slots=True)
class AutoencodeResult:
    text: str
    codes: tuple[str, ...]
    status: str
    path_count: int
    work_count: int
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ScriptAutoencoder:
    """Generate all reached Rime codes, with ambiguity and truncation explicit.

    Input entries may expose ``text``, ``reading``, ``weight`` attributes, or be
    three-item ``(text, reading, weight)`` sequences. Only one-syllable entries
    populate Rime's translation map, including any multi-character texts with
    one code. Duplicate text/code pairs keep the first weight as EntryCollector
    does. Retained codes have weight >= 5% of the sum for that text; if the sum
    is zero, all codes satisfy the threshold. No frequency smoothing is added.

    ``encode`` follows longest matching text first and lexical reading order.
    It emits at most 32 complete DFS paths for at most 32 Unicode codepoints.
    The work guard includes prefix viability checks and explored code edges.
    A result labelled unique is complete; hitting either bound is truncated.
    """

    def __init__(self, entries: Iterable, *, max_work: int = 100_000) -> None:
        if isinstance(max_work, bool) or not isinstance(max_work, int) or max_work < 1:
            raise ValueError("max_work must be a positive integer")
        self.max_work = max_work
        weights: dict[str, dict[str, float]] = defaultdict(dict)
        explicit_rows = 0
        ignored_multisyllable_rows = 0
        duplicate_single_rows = 0
        for entry in entries:
            if hasattr(entry, "text"):
                text, reading, weight = entry.text, entry.reading, entry.weight
            else:
                try:
                    text, reading, weight = entry
                except (TypeError, ValueError) as error:
                    raise ValueError("entries must provide text, reading and weight") from error
            if not isinstance(text, str) or not text or any(0xD800 <= ord(c) <= 0xDFFF for c in text):
                raise ValueError("entry text must be valid nonempty Unicode")
            if not isinstance(reading, str):
                raise ValueError("entry reading must be canonical toned Jyutping")
            syllables = reading.split()
            if not syllables or any(not _READING.fullmatch(code) for code in syllables):
                raise ValueError("entry reading must be canonical toned Jyutping")
            if isinstance(weight, bool):
                raise ValueError("entry weight must be finite and nonnegative")
            try:
                numeric_weight = float(weight)
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError("entry weight must be finite and nonnegative") from error
            if not math.isfinite(numeric_weight) or numeric_weight < 0:
                raise ValueError("entry weight must be finite and nonnegative")
            explicit_rows += 1
            if len(syllables) != 1:
                ignored_multisyllable_rows += 1
                continue
            code = syllables[0]
            if code in weights[text]:
                duplicate_single_rows += 1
                continue
            weights[text][code] = numeric_weight
        self.translations: dict[str, tuple[str, ...]] = {}
        for text, alternatives in weights.items():
            total = sum(alternatives.values())
            if not math.isfinite(total):
                raise ValueError("sum of entry weights overflowed")
            minimum = total * MIN_READING_WEIGHT_SHARE
            self.translations[text] = tuple(sorted(code for code, weight in alternatives.items()
                                                   if weight >= minimum))
        self._lengths = tuple(sorted({len(text) for text, codes in self.translations.items() if codes}, reverse=True))
        self._counts = {
            "explicit_rows": explicit_rows,
            "ignored_multisyllable_rows": ignored_multisyllable_rows,
            "duplicate_single_rows": duplicate_single_rows,
            "translation_texts": len(self.translations),
            "qualifying_readings": sum(map(len, self.translations.values())),
        }

    def metadata(self) -> dict:
        return dict(ALGORITHM_PROVENANCE, max_phrase_codepoints=MAX_PHRASE_CODEPOINTS,
                    max_encoder_paths=MAX_ENCODER_PATHS, min_reading_weight_share=MIN_READING_WEIGHT_SHARE,
                    max_work=self.max_work, **self._counts)

    def encode(self, text: str) -> AutoencodeResult:
        if not isinstance(text, str) or not text:
            raise ValueError("phrase must be nonempty Unicode text")
        if any(0xD800 <= ord(char) <= 0xDFFF for char in text):
            raise ValueError("phrase contains an invalid Unicode surrogate")
        length = len(text)
        if length > MAX_PHRASE_CODEPOINTS:
            return AutoencodeResult(text, (), "too_long", 0, 0,
                                    "Rime ScriptEncoder accepts at most 32 Unicode codepoints")

        work = 0
        matches: list[list[tuple[int, tuple[str, ...]]]] = [[] for _ in range(length)]
        reachable = [False] * length + [True]
        # A phrase-code choice cannot change later text segmentation. Pruning a
        # suffix with no encoding therefore preserves every successful DFS path.
        for start in range(length - 1, -1, -1):
            for token_length in self._lengths:
                if start + token_length > length:
                    continue
                work += 1
                if work > self.max_work:
                    return AutoencodeResult(text, (), "truncated", 0, self.max_work,
                                            "work_limit")
                end = start + token_length
                codes = self.translations.get(text[start:end], ())
                if codes and reachable[end]:
                    matches[start].append((end, codes))
                    reachable[start] = True
        if not reachable[0]:
            return AutoencodeResult(text, (), "unencodable", 0, work,
                                    "no complete path through qualifying single-syllable translations")

        output: list[str] = []
        seen: set[str] = set()
        path: list[str] = []
        path_count = 0
        stopped: str | None = None

        def visit(start: int) -> None:
            nonlocal work, path_count, stopped
            if stopped is not None:
                return
            if start == length:
                code = " ".join(path)
                path_count += 1
                if code not in seen:
                    seen.add(code)
                    output.append(code)
                if path_count >= MAX_ENCODER_PATHS:
                    stopped = "path_limit"
                return
            for end, alternatives in matches[start]:
                for code in alternatives:
                    if work >= self.max_work:
                        stopped = "work_limit"
                        return
                    work += 1
                    path.append(code)
                    visit(end)
                    path.pop()
                    if stopped is not None:
                        return

        visit(0)
        status = "truncated" if stopped else "encoded_unique" if len(output) == 1 else "encoded_ambiguous"
        return AutoencodeResult(text, tuple(output), status, path_count, work, stopped)
