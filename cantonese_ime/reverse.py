"""Reverse lookup: the stored readings of a character or word, read-only.

For each reading this also lists spellings the forgiving mode accepts for it,
using the same rules as the engine: the toneless Jyutping, Yale (treated as a
first-class convention) and built-in casual aliases up to a modest cost. User
custom spellings are not included; they are what this lookup helps to write.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from .mappings import spelling_variants, yale_ascii_variants


MAX_TEXT_LENGTH = 32
MAX_HINT_PENALTY = 0.5
MAX_HINTS = 4


def typing_hints(reading: str) -> tuple[str, ...]:
    """Spellings to type for a toned reading such as 'zyun2' or 'nei5 hou2'."""
    bases = [syllable.rstrip("123456") for syllable in reading.split()]
    if not bases or not all(base.isascii() and base.isalpha() for base in bases):
        return ()
    if len(bases) > 1:
        # Words: the joined toneless Jyutping and the joined Yale form.
        forms = ["".join(bases), "".join(yale_ascii_variants(base)[0] for base in bases)]
        return tuple(dict.fromkeys(forms))
    base = bases[0]
    yale = set(yale_ascii_variants(base))
    ranked = sorted(
        ((0.0 if spelling in yale else penalty, spelling != base, spelling)
         for spelling, penalty in spelling_variants(base).items()),
    )
    return tuple(spelling for cost, _, spelling in ranked if cost <= MAX_HINT_PENALTY)[:MAX_HINTS]


def _readings(connection: sqlite3.Connection, text: str, limit: int) -> list[dict]:
    rows = connection.execute(
        "SELECT reading, weight FROM entries WHERE text=? ORDER BY weight DESC, reading LIMIT ?", (text, limit))
    return [{"reading": reading, "weight": float(weight), "spellings": list(typing_hints(reading))}
            for reading, weight in rows]


def reverse_lookup(db_path: str | Path, text: str, *, limit: int = 12) -> dict:
    """Readings of the whole text, then of each distinct character in it."""
    value = text.strip() if isinstance(text, str) else ""
    if not value or len(value) > MAX_TEXT_LENGTH or any(ord(c) < 32 for c in value):
        raise ValueError(f"Reverse lookup needs 1-{MAX_TEXT_LENGTH} characters of text.")
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Dictionary not found: {path}")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        result = {"text": value, "readings": _readings(connection, value, limit), "characters": []}
        if len(value) > 1:
            for character in dict.fromkeys(c for c in value if not c.isspace()):
                result["characters"].append({"text": character, "readings": _readings(connection, character, limit)})
    return result


def tsv_lines(result: dict) -> list[str]:
    """One line per reading: kind, text, reading, weight, comma-separated spellings."""
    lines = [f"word\t{result['text']}\t{item['reading']}\t{item['weight']:g}\t{','.join(item['spellings'])}"
             for item in result["readings"]]
    for character in result["characters"]:
        lines += [f"char\t{character['text']}\t{item['reading']}\t{item['weight']:g}\t{','.join(item['spellings'])}"
                  for item in character["readings"]]
    return lines
