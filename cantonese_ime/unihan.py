"""Read directly supplied, provisional Unicode kCantonese character readings.

This is a character supplement, not a normative pronunciation dictionary or a
word autoencoder. No variants, descriptive labels, frequencies or other Unihan
properties are used to invent a reading.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Iterator, MutableMapping
import zipfile

from .dictionary import DictionaryEntry, verify_source_files


SOURCE_NAME = "unihan:kCantonese"
PROPERTY_STATUS = "Provisional"
MAX_READINGS_BYTES = 32_000_000
_CODEPOINT = re.compile(r"U\+([0-9A-Fa-f]{4,6})\Z")
_READING = re.compile(r"[a-z]{1,6}[1-6]\Z", re.ASCII)
_VERSION = re.compile(r"\d+\.\d+\.\d+\Z", re.ASCII)


def verify_unihan_snapshot(source_dir: str | Path, lock: dict) -> None:
    """Verify pinned raw bytes, the retained full notice and archive extraction."""
    source_dir = Path(source_dir)
    verify_source_files(source_dir, lock)
    if lock.get("license") != "Unicode-3.0" or lock.get("property_status") != PROPERTY_STATUS or lock.get("property") != "kCantonese":
        raise ValueError("Unihan lock must retain Unicode-3.0 licensing and provisional property status")
    notice = (source_dir / "LICENSE.txt").read_text(encoding="utf-8")
    expected_notice = lock.get("license_notice", {}).get("text")
    if not notice.startswith("UNICODE LICENSE V3\n") or notice != expected_notice:
        raise ValueError("Unihan snapshot is missing the expected full Unicode License V3 notice")
    version = lock.get("unicode_version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise ValueError("Unihan lock is missing its Unicode release version")
    readings_path = source_dir / "Unihan_Readings.txt"
    if readings_path.stat().st_size > MAX_READINGS_BYTES:
        raise ValueError("Unihan readings snapshot exceeds the data size limit")
    data = readings_path.read_bytes()
    if f"# Unicode Version {version}" not in data.decode("utf-8").splitlines():
        raise ValueError("Unihan readings header disagrees with the locked Unicode version")
    with zipfile.ZipFile(source_dir / "Unihan.zip") as archive:
        member = archive.getinfo("Unihan_Readings.txt")
        if member.file_size > MAX_READINGS_BYTES:
            raise ValueError("Unihan archive readings member exceeds the data size limit")
        if archive.read(member) != data:
            raise ValueError("Retained Unihan readings differ from the pinned archive member")


def read_unihan_entries(
    path: str | Path, *, stats: MutableMapping[str, int] | None = None,
    review_rows: list[dict] | None = None,
) -> Iterator[DictionaryEntry]:
    """Yield direct character/reading alternatives with unknown frequency zero.

    Unihan property rows contain codepoint, property name and property value.
    Values separated by spaces are alternative readings for the same character,
    not the syllables of a word. Only kCantonese is consumed. Its published lower
    case ASCII syntax is checked without normalization or variant inheritance.
    Repeated kCantonese property rows and repeated values are rejected.
    ``review_rows`` is accepted for the supplemental-reader call convention;
    valid direct rows need no quarantine. Provisional status belongs to the
    selected source metadata, not a fabricated per-row human-review decision.
    """
    path = Path(path)
    if path.stat().st_size > MAX_READINGS_BYTES:
        raise ValueError(f"{path}: Unihan readings snapshot exceeds the data size limit")
    counts = stats if stats is not None else {}
    seen_codepoints: set[int] = set()

    def count(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    with path.open(encoding="utf-8-sig") as stream:
        for number, raw in enumerate(stream, 1):
            line = raw.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            count("scanned_data_rows")
            columns = line.split("\t")
            if len(columns) != 3:
                raise ValueError(f"{path}:{number}: expected codepoint<TAB>property<TAB>value")
            codepoint, prop, value = columns
            if prop != "kCantonese":
                count("ignored_other_property_rows")
                continue
            count("input_rows")
            matched = _CODEPOINT.fullmatch(codepoint)
            scalar = int(matched.group(1), 16) if matched else -1
            if not 0 <= scalar <= 0x10FFFF or 0xD800 <= scalar <= 0xDFFF:
                raise ValueError(f"{path}:{number}: invalid Unicode scalar value")
            if scalar in seen_codepoints:
                raise ValueError(f"{path}:{number}: duplicate kCantonese property row")
            readings = value.split()
            if not readings or any(not _READING.fullmatch(reading) for reading in readings):
                raise ValueError(f"{path}:{number}: malformed direct kCantonese reading")
            if len(set(readings)) != len(readings):
                raise ValueError(f"{path}:{number}: duplicate kCantonese reading value")
            seen_codepoints.add(scalar)
            if len(readings) > 1:
                count("alternative_reading_rows")
            for reading in readings:
                count("accepted_entries")
                base = reading[:-1]
                yield DictionaryEntry(chr(scalar), reading, base, base, 1, 0.0, SOURCE_NAME)
