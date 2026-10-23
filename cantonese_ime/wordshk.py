"""Read the official public-domain words.hk wordlist snapshot.

This consumes only the wordlist/pronunciation endpoint, never definitions.
The scope of the declaration is recorded with the snapshot's full HTML page.
Questionable source notation is retained in review rows instead of rewritten.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterator, MutableMapping, MutableSequence

from .dictionary import DictionaryEntry, verify_source_files


SOURCE_NAME = "words.hk:wordlist"
MAX_SNAPSHOT_BYTES = 32_000_000
_CODE = re.compile(r"[a-z]+[1-6]\Z")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON wordlist key: {key!r}")
        result[key] = value
    return result


def verify_wordshk_snapshot(source_dir: str | Path, lock: dict) -> None:
    """Check locked bytes and the narrowly scoped public-domain declaration."""
    source_dir = Path(source_dir)
    verify_source_files(source_dir, lock)
    declaration = (source_dir / "license-declaration.html").read_text(encoding="utf-8")
    if "Data License: public domain. Credits to words.hk appreciated." not in declaration:
        raise ValueError("words.hk snapshot is missing the expected wordlist public-domain declaration")


def read_wordshk_entries(
    path: str | Path,
    *,
    stats: MutableMapping[str, int] | None = None,
    review_rows: MutableSequence[dict] | None = None,
) -> Iterator[DictionaryEntry]:
    """Yield explicit well-formed toned word readings with no invented frequency.

    JSON schema: ``{written_text: [reading, ...], ...}``. Readings use space-
    separated lowercase letter syllables ending in1–6. Multilingual notation
    such as ``!zhi1`` is quarantined intact. One trailing source ``*`` marker
    is removed according to the source's documented variant annotation, while
    a ``normalized_variant`` review record retains the raw spelling and flag.
    Malformed markers and ellipsis templates are quarantined. Spaces in valid
    readings are normalized.

    Accepted rows have weight0. The caller may attach a separately attributed
    frequency by exact text. ``accepted_entries + quarantined_rows +
    duplicate_entries == source_reading_rows`` after consuming the iterator.
    Malformed top-level structures and duplicate JSON keys raise ValueError.
    """
    path = Path(path)
    if path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError("words.hk snapshot exceeds the data size limit")
    with path.open(encoding="utf-8-sig") as stream:
        data = json.load(stream, object_pairs_hook=_unique_object)
    if not isinstance(data, dict):
        raise ValueError("words.hk wordlist must be a JSON object")
    counts = stats if stats is not None else {}

    def count(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    def quarantine(text: str, reading: object, index: int, reason: str) -> None:
        count("quarantined_rows")
        count("quarantined_" + reason)
        if review_rows is not None:
            review_rows.append({"text": text, "raw_reading": reading,
                                "reading_index": index, "reason": reason, "source": SOURCE_NAME,
                                "status": "quarantined", "source_flag": None})

    seen: set[tuple[str, str]] = set()
    for text, readings in data.items():
        count("source_text_keys")
        if not isinstance(readings, list):
            raise ValueError(f"words.hk readings for {text!r} must be a list")
        if not readings:
            count("empty_reading_lists")
        for index, raw_reading in enumerate(readings):
            count("source_reading_rows")
            if (not text or text != text.strip() or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in text)):
                quarantine(text, raw_reading, index, "invalid_text")
                continue
            if not isinstance(raw_reading, str) or not raw_reading.split() or any(
                not _CODE.fullmatch(code) for code in raw_reading.split()
            ):
                quarantine(text, raw_reading, index, "non_jyutping_reading")
                continue
            normalized_text = text
            variant = False
            if "*" in text:
                if text.endswith("*") and text.count("*") == 1 and len(text) > 1:
                    normalized_text = text[:-1]
                    variant = True
                    if normalized_text != normalized_text.strip():
                        quarantine(text, raw_reading, index, "invalid_text")
                        continue
                else:
                    quarantine(text, raw_reading, index, "malformed_variant_annotation")
                    continue
            if "⋯" in text or "…" in text or "..." in text:
                quarantine(text, raw_reading, index, "template_annotation")
                continue
            syllables = raw_reading.split()
            reading = " ".join(syllables)
            duplicate = (normalized_text, reading) in seen
            if variant:
                count("normalized_variant_rows")
                if review_rows is not None:
                    review_rows.append({"text": normalized_text, "raw_text": text,
                                        "raw_reading": raw_reading, "reading": reading,
                                        "normalized_text": normalized_text,
                                        "normalization": "removed exactly one documented trailing variant marker",
                                        "reading_index": index, "source": SOURCE_NAME,
                                        "status": "normalized_variant", "source_flag": "variant",
                                        "imported": not duplicate})
            if duplicate:
                count("duplicate_entries")
                continue
            seen.add((normalized_text, reading))
            base = [code[:-1] for code in syllables]
            count("accepted_entries")
            yield DictionaryEntry(normalized_text, reading, " ".join(base), "".join(base),
                                  len(syllables), 0.0, SOURCE_NAME)
