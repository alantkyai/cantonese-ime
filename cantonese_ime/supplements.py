"""Import explicitly labelled pronunciations from supplementary text datasets."""

from __future__ import annotations

import csv
from pathlib import Path
import re
from typing import Iterator, MutableMapping

from .dictionary import DictionaryEntry


_SYLLABLE = re.compile(r"[a-z]+[1-6]\Z")
_COLUMNS = {"CH", "UCODE", "JP", "INIT", "FINL", "TONE", "DESC", "DESC_JP"}


def read_lshk_entries(
    path: str | Path,
    *,
    stats: MutableMapping[str, int] | None = None,
    review_rows: list[dict] | None = None,
) -> Iterator[DictionaryEntry]:
    """Use JP only; DESC_JP describes a glyph and is not its pronunciation.

    An explicit multisyllable JP is retained. Description-only rows are accounted
    separately rather than converted into invented character readings. The table
    supplies no usage frequency, so new readings have zero weight.
    """
    path = Path(path)
    counts = stats if stats is not None else {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None or set(reader.fieldnames) != _COLUMNS:
            raise ValueError(f"{path}: unsupported LSHK table columns")
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{number}: malformed TSV row")
            counts["input_rows"] = counts.get("input_rows", 0) + 1
            text = row["CH"]
            if len(text) != 1 or not row["UCODE"].startswith("U+"):
                raise ValueError(f"{path}:{number}: expected one character and Unicode code point")
            try:
                valid_codepoint = int(row["UCODE"][2:], 16) == ord(text)
            except ValueError:
                valid_codepoint = False
            if not valid_codepoint:
                raise ValueError(f"{path}:{number}: character and Unicode code point disagree")
            pronunciation = row["JP"].strip().lower()
            if not pronunciation:
                counts["description_only_rows"] = counts.get("description_only_rows", 0) + 1
                if review_rows is not None:
                    review_rows.append({
                        "source": "lshk:list.tsv", "line": number, "text": text,
                        "status": "description_only", "description": row["DESC"],
                        "description_reading": row["DESC_JP"],
                        "reason": "JP is empty; DESC_JP is not a character pronunciation.",
                    })
                continue
            syllables = pronunciation.split()
            if any(not _SYLLABLE.fullmatch(item) for item in syllables):
                raise ValueError(f"{path}:{number}: malformed explicit Jyutping pronunciation")
            category = "multisyllable_rows" if len(syllables) > 1 else "single_syllable_rows"
            counts[category] = counts.get(category, 0) + 1
            counts["explicit_rows"] = counts.get("explicit_rows", 0) + 1
            bases = [item[:-1] for item in syllables]
            yield DictionaryEntry(text, " ".join(syllables), " ".join(bases),
                                  "".join(bases), len(syllables), 0.0, "lshk:list.tsv")
