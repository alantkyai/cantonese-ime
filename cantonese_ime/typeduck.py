"""Read the selected TypeDuck principal table without importing its weights.

The pinned repository expressly licenses principal data CC BY 4.0. Its reverse
lookups are outside this source. An explicit export row is not independent
evidence of human phrase review; retained provenance describes that distinction.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import re
from typing import Iterator, MutableMapping, MutableSequence

from .dictionary import DictionaryEntry, verify_source_files


SOURCE_NAME = "typeduck:principal"
DICTIONARY_FILE = "jyut6ping3.dict.yaml"
MAX_SNAPSHOT_BYTES = 32_000_000
_CODE = re.compile(r"[a-z]+[1-6]\Z")
_PERCENTAGE = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)%\Z")
_DECLARATION = (
    "Except for the reverse lookup data listed above, this repo, including "
    "the main TypeDuck dictionary and the `jyut6ping3` schema, is licensed "
    "under [CC BY 4.0]"
)


def verify_typeduck_snapshot(source_dir: str | Path, lock: dict) -> None:
    """Check exact locked files and the retained principal-data declaration."""
    source_dir = Path(source_dir)
    verify_source_files(source_dir, lock)
    declaration = (source_dir / "README.md").read_text(encoding="utf-8")
    if _DECLARATION not in declaration:
        raise ValueError("TypeDuck snapshot is missing the expected principal-data CC BY 4.0 declaration")


def read_typeduck_entries(
    path: str | Path,
    *,
    stats: MutableMapping[str, int] | None = None,
    review_rows: MutableSequence[dict] | None = None,
) -> Iterator[DictionaryEntry]:
    """Yield all well-formed explicit pairs with weight 0 (frequency unknown).

    This narrow parser expects the selected principal dictionary's three-field
    text/reading/percentage table, not arbitrary YAML or imported tables. Source
    percentages are validated but never converted to frequencies, probabilities
    or autoencoder weights. Values above 100% are valid source ranking values.
    Original bytes remain in the vendor snapshot. Reading case/spacing alone is
    normalized; text and tone digits are retained.

    Phonetic annotations such as the selected source's two tilde-marked emoji
    readings are quarantined with physical line, complete raw line and fields.
    Their markers are never stripped into an invented ordinary reading.
    Malformed row/header/weight structure raises ValueError; noncanonical
    pronunciation notation is quarantined. After consuming the iterator:
    input_rows == accepted_entries + duplicate_entries + quarantined_rows.
    Existing entries from earlier sources are preserved by the caller's merge.
    """
    path = Path(path)
    if path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError("TypeDuck snapshot exceeds the data size limit")
    counts = stats if stats is not None else {}

    def count(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    def quarantine(text: str, reading: str, weight: str, raw: str, line: int, reason: str) -> None:
        count("quarantined_rows")
        count("quarantined_" + reason)
        if review_rows is not None:
            review_rows.append({"source": SOURCE_NAME, "line": line, "text": text,
                                "raw_text": text, "raw_reading": reading, "raw_weight": weight,
                                "raw_line": raw, "status": "quarantined", "reason": reason})

    seen = set()
    header_started = False
    in_table = False
    principal_name = False
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, raw in enumerate(stream, 1):
            raw = raw.rstrip("\r\n")
            if not in_table:
                if not raw.strip() or raw.lstrip().startswith("#"):
                    continue
                if raw == "---" and not header_started:
                    header_started = True
                    continue
                if not header_started:
                    raise ValueError(f"{path}:{line_number}: missing TypeDuck header start")
                if raw == "...":
                    if not principal_name:
                        raise ValueError(f"{path}:{line_number}: expected principal dictionary name jyut6ping3")
                    in_table = True
                    continue
                key, separator, value = raw.partition(":")
                if not separator:
                    raise ValueError(f"{path}:{line_number}: unsupported TypeDuck header field")
                if key.strip() in ("columns", "import_tables"):
                    raise ValueError(f"{path}:{line_number}: alternate columns/imported tables are outside the principal parser")
                if key.strip() == "name":
                    principal_name = value.strip().strip("\"'") == "jyut6ping3"
                continue
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            columns = raw.split("\t")
            if len(columns) != 3:
                raise ValueError(f"{path}:{line_number}: expected text<TAB>reading<TAB>percentage")
            text, raw_reading, raw_weight = columns
            if not _PERCENTAGE.fullmatch(raw_weight):
                raise ValueError(f"{path}:{line_number}: invalid TypeDuck percentage weight {raw_weight!r}")
            # A decimal with hundreds of digits can overflow float despite its
            # syntax. We do not need a float to classify zero or >100 safely.
            percentage = Decimal(raw_weight[:-1])
            count("input_rows")
            if percentage == 0:
                count("source_zero_percentage_rows")
            elif percentage > 100:
                count("source_above_100_percentage_rows")
            if not text or text != text.strip() or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in text):
                quarantine(text, raw_reading, raw_weight, raw, line_number, "invalid_text")
                continue
            syllables = raw_reading.lower().split()
            if not syllables or any(not _CODE.fullmatch(code) for code in syllables):
                reason = "phonetic_annotation" if "~" in raw_reading else "non_jyutping_reading"
                quarantine(text, raw_reading, raw_weight, raw, line_number, reason)
                continue
            reading = " ".join(syllables)
            if reading != raw_reading:
                count("normalized_reading_rows")
            if (text, reading) in seen:
                count("duplicate_entries")
                continue
            seen.add((text, reading))
            base = [code[:-1] for code in syllables]
            count("accepted_entries")
            yield DictionaryEntry(text, reading, " ".join(base), "".join(base), len(syllables), 0.0, SOURCE_NAME)
    if not in_table:
        raise ValueError(f"{path}: missing TypeDuck header terminator")
