"""Per-user custom phrases and spelling aliases from a small UTF-8 text file.

Each non-blank line not starting with ``#`` is one of:

    hh 曈曈          a phrase: typing exactly ``hh`` offers 曈曈 first
    moon = mun       a spelling: ``moon`` is read as the syllable ``mun``

Phrase keys and spellings are 1-32 ASCII letters (case-insensitive). Phrase
text is the rest of the line, up to 64 characters. A key may repeat; its
phrases are offered in file order. Alias targets must be toneless syllables of
the loaded lexicon; the engine ignores unknown targets. Invalid lines are
counted and skipped so one typo never disables the whole file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


MAX_CUSTOM_BYTES = 256 * 1024
MAX_CUSTOM_LINES = 5000
MAX_PHRASE_LENGTH = 64
_KEY = re.compile(r"[a-z]{1,32}\Z")
_SYLLABLE = re.compile(r"[a-z]{1,12}\Z")


@dataclass(frozen=True, slots=True)
class CustomEntries:
    phrases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    aliases: tuple[tuple[str, str], ...] = ()
    invalid_lines: int = 0


def parse_custom(text: str) -> CustomEntries:
    phrases: dict[str, list[str]] = {}
    aliases: dict[tuple[str, str], None] = {}
    invalid = 0
    if text.startswith("﻿"):
        text = text[1:]
    for number, line in enumerate(text.splitlines(), start=1):
        if number > MAX_CUSTOM_LINES:
            invalid += 1
            continue
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            spelling, _, base = (part.strip().lower() for part in line.partition("="))
            if _KEY.fullmatch(spelling) and _SYLLABLE.fullmatch(base):
                aliases[(spelling, base)] = None
            else:
                invalid += 1
            continue
        key, phrase = (line.split(None, 1) + [""])[:2]
        key, phrase = key.lower(), phrase.strip()
        if (not _KEY.fullmatch(key) or not phrase or len(phrase) > MAX_PHRASE_LENGTH
                or any(ord(c) < 32 or ord(c) == 127 for c in phrase)):
            invalid += 1
            continue
        values = phrases.setdefault(key, [])
        if phrase not in values:
            values.append(phrase)
    return CustomEntries({key: tuple(values) for key, values in phrases.items()}, tuple(aliases), invalid)


def read_custom(path: Path) -> CustomEntries:
    """A missing file is empty. An oversized or undecodable file raises."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return CustomEntries()
    if len(data) > MAX_CUSTOM_BYTES:
        raise ValueError("Custom entries file exceeds its size limit.")
    return parse_custom(data.decode("utf-8-sig"))
