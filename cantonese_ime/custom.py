"""Per-user custom phrases and spelling aliases from a small UTF-8 text file.

Each non-blank line not starting with ``#`` is one of:

    hh 曈曈          a phrase: typing exactly ``hh`` offers 曈曈 first
    moon = mun       a spelling: ``moon`` is read as the syllable ``mun``
    k* = g*          a rule on initials: any syllable with initial g may start with k
    *oon = *un       a rule on finals: any syllable with final un may end in oon
    *oo* = *u*       a rule inside finals: u in a final may be typed oo

Rules apply to every syllable of the loaded lexicon (see ``rule_spelling``).
Phrase keys and spellings are 1-32 ASCII letters (case-insensitive). Phrase
text is the rest of the line, up to 64 characters. A key may repeat; its
phrases are offered in file order. An alias target is a toneless Jyutping
syllable (``mun``) or any spelling the IME already accepts (``cheut``, which
means ceot/coet); the engine ignores targets it cannot resolve. Invalid lines are
counted and skipped so one typo never disables the whole file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from .mappings import FINALS, ONSETS


MAX_CUSTOM_BYTES = 256 * 1024
MAX_CUSTOM_LINES = 5000
MAX_PHRASE_LENGTH = 64
MAX_RULES = 50
MAX_SPELLING_LENGTH = 12  # The engine's syllable trie matches at most 12 letters.
_KEY = re.compile(r"[a-z]{1,32}\Z")
_SYLLABLE = re.compile(r"[a-z]{1,12}\Z")
_RULE_SHAPES = (
    ("initial", re.compile(r"([a-z]{1,6})\*\Z")),
    ("final", re.compile(r"\*([a-z]{1,6})\Z")),
    ("inside", re.compile(r"\*([a-z]{1,6})\*\Z")),
)


@dataclass(frozen=True, slots=True)
class CustomEntries:
    phrases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    aliases: tuple[tuple[str, str], ...] = ()
    invalid_lines: int = 0
    # (kind, typed, canonical): kind is "initial", "final" or "inside".
    rules: tuple[tuple[str, str, str], ...] = ()


def parse_rule(spelling: str, base: str) -> tuple[str, str, str] | None:
    """A rule when both sides have the same wildcard shape, else None."""
    for kind, shape in _RULE_SHAPES:
        typed, canonical = shape.fullmatch(spelling), shape.fullmatch(base)
        if typed and canonical and typed.group(1) != canonical.group(1):
            return kind, typed.group(1), canonical.group(1)
    return None


def rule_spelling(rule: tuple[str, str, str], initial: str, final: str) -> str | None:
    """The spelling a rule gives a syllable split as initial + final, or None.

    A side that is a real initial or final matches it whole (k* = g* leaves gw
    alone; *oon = *un leaves jyun alone). Any other letters match the start or
    end of the spelling instead (ch* = zy* turns zyu into chu, across the
    z + yu boundary). An inside rule replaces within the final only, never the
    initial, so it also reaches finals like au or yu that merely contain it.
    """
    kind, typed, canonical = rule
    base = initial + final
    if kind == "initial":
        if canonical in ONSETS:
            spelling = typed + final if initial == canonical else None
        else:
            spelling = typed + base[len(canonical):] if base.startswith(canonical) and base != canonical else None
    elif kind == "final":
        if canonical in FINALS:
            spelling = initial + typed if final == canonical else None
        else:
            spelling = base[:-len(canonical)] + typed if base.endswith(canonical) and base != canonical else None
    else:
        spelling = initial + final.replace(canonical, typed) if canonical in final else None
    if spelling is None or spelling == initial + final or not _SYLLABLE.fullmatch(spelling):
        return None
    return spelling


def parse_custom(text: str) -> CustomEntries:
    phrases: dict[str, list[str]] = {}
    aliases: dict[tuple[str, str], None] = {}
    rules: dict[tuple[str, str, str], None] = {}
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
            rule = parse_rule(spelling, base) if "*" in spelling or "*" in base else None
            if rule is not None and (rule in rules or len(rules) < MAX_RULES):
                rules[rule] = None
            elif rule is None and _KEY.fullmatch(spelling) and _SYLLABLE.fullmatch(base):
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
    return CustomEntries({key: tuple(values) for key, values in phrases.items()}, tuple(aliases), invalid, tuple(rules))


def preview_rule(db_path: str | Path, line: str, *, limit: int = 200) -> dict:
    """What one rule line would add, without changing anything.

    Lists each affected lexicon syllable with its new spelling, the most
    common single character read that way, and whether the spelling collides
    with one the IME already accepts (where the engine charges more).
    """
    import sqlite3
    from contextlib import closing
    from .mappings import scheme_parts, spelling_variants

    spelling, _, base = (part.strip().lower() for part in line.partition("="))
    rule = parse_rule(spelling, base) if "=" in line else None
    if rule is None:
        raise ValueError("A rule has the same wildcard shape on both sides, e.g. k* = g*, *oon = *un or *oo* = *u*.")
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Dictionary not found: {path}")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        bases = sorted({token for (reading,) in connection.execute("SELECT DISTINCT base_reading FROM entries")
                        for token in reading.split()})
        examples: dict[str, tuple[str, float]] = {}
        for base_reading, text, weight in connection.execute(
                "SELECT base_reading, text, weight FROM entries WHERE base_reading NOT LIKE '% %' AND length(text) = 1"):
            if base_reading not in examples or weight > examples[base_reading][1]:
                examples[base_reading] = (text, float(weight))
    existing = {variant for base_syllable in bases for variant in spelling_variants(base_syllable)}
    rows = []
    for syllable in bases:
        initial, final, _ = scheme_parts(syllable)
        new = rule_spelling(rule, initial, final)
        if new is not None:
            example, weight = examples.get(syllable, ("", 0.0))
            rows.append({"syllable": syllable, "spelling": new, "example": example,
                         "collides": new in existing, "weight": weight})
    rows.sort(key=lambda row: (-row["weight"], row["syllable"]))
    return {"rule": {"kind": rule[0], "typed": rule[1], "canonical": rule[2]}, "count": len(rows),
            "collisions": sum(row["collides"] for row in rows),
            "rows": [{key: row[key] for key in ("syllable", "spelling", "example", "collides")} for row in rows[:limit]]}


def read_custom(path: Path) -> CustomEntries:
    """A missing file is empty. An oversized or undecodable file raises."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return CustomEntries()
    if len(data) > MAX_CUSTOM_BYTES:
        raise ValueError("Custom entries file exceeds its size limit.")
    return parse_custom(data.decode("utf-8-sig"))
