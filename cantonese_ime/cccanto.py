"""Strict import of Pleco's CC-Canto and CC-CEDICT Cantonese reading exports.

Only explicitly supplied brace-delimited Jyutping is used. Bracketed Mandarin
Pinyin and definitions never supply lookup readings. See the retained CC-BY-SA
source notices; this module's code is separate from the licensed dictionary data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Collection, Iterator, MutableMapping, MutableSequence
import zipfile

from .dictionary import DictionaryEntry, verify_source_files

MAX_SOURCE_BYTES = 16_000_000
ATTESTATION_NAME = "parser-attested-bases.json"
SOURCE_FILES = {
    "cccanto-webdist.txt": "cccanto:dictionary",
    "cccedict-canto-readings-150923.txt": "cccanto:cedict-readings",
}
_ROW = re.compile(r"^(\S+)\s+(\S+)\s+\[[^\[\]]*\]\s+\{([^{}]*)\}(?:\s+/.*)?$")
_CODE = re.compile(r"[a-z]{1,12}[1-6]\Z")
_BASE = re.compile(r"[a-z]{1,12}\Z")


def read_attested_bases(path: str | Path) -> frozenset[str]:
    path = Path(path)
    if path.stat().st_size > 100_000:
        raise ValueError("CC-Canto parser attestation inventory is oversized")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Malformed CC-Canto parser attestation inventory")
    bases = value.get("bases")
    if (value.get("schema_version") != 1 or not isinstance(bases, list) or not 1 <= len(bases) <= 2000
            or any(not isinstance(base, str) or not _BASE.fullmatch(base) for base in bases)
            or len(set(bases)) != len(bases)):
        raise ValueError("Malformed CC-Canto parser attestation inventory")
    return frozenset(bases)


def verify_cccanto_snapshot(source_dir: str | Path, lock: dict) -> None:
    """Verify pinned raw archives/member bytes, declaration and parser inventory."""
    source_dir = Path(source_dir)
    verify_source_files(source_dir, lock)
    if lock.get("license") != "CC-BY-SA-3.0":
        raise ValueError("CC-Canto source license must retain its original CC-BY-SA-3.0 declaration")
    declaration = (source_dir / "download.html").read_text(encoding="utf-8")
    if ("Creative Commons Attribution-ShareAlike 3.0 license" not in declaration
            or "Jyutping readings after the Pinyin readings enclosed by {}" not in declaration):
        raise ValueError("CC-Canto declaration does not match the expected license/brace-reading scope")
    license_text = (source_dir / "LICENSE-CC-BY-SA-3.0.txt").read_text(encoding="utf-8")
    if "a later version of this License with" not in license_text:
        raise ValueError("CC-BY-SA-3.0 later-version adaptation clause is missing")
    for archive_name, member in (
        ("cccanto-170202.zip", "cccanto-webdist.txt"),
        ("cccedict-canto-readings-150923.zip", "cccedict-canto-readings-150923.txt"),
    ):
        with zipfile.ZipFile(source_dir / archive_name) as archive:
            if archive.namelist() != [member] or archive.getinfo(member).file_size > MAX_SOURCE_BYTES:
                raise ValueError("Unexpected CC-Canto archive members")
            if archive.read(member) != (source_dir / member).read_bytes():
                raise ValueError("CC-Canto retained text differs from its original archive member")
    bases = read_attested_bases(source_dir / ATTESTATION_NAME)
    if len(bases) != lock.get("parser_attestation", {}).get("base_count"):
        raise ValueError("CC-Canto parser inventory count disagrees with its lock")


def read_cccanto_entries(
    path: str | Path,
    *,
    source_id: str | None = None,
    allowed_bases: Collection[str] | None = None,
    stats: MutableMapping[str, int] | None = None,
    review_rows: MutableSequence[dict] | None = None,
) -> Iterator[DictionaryEntry]:
    """Yield aligned traditional/simplified forms with explicit Jyutping and weight0.

    Unknown bases are quarantined against a frozen, pinned baseline inventory;
    absence does not prove an upstream pronunciation wrong. No punctuation,
    variant, foreign-letter, tone or y/j correction is inferred. Each distinct
    text form must have one Unicode codepoint per supplied syllable. Legitimate
    punctuation and multisyllable characters may therefore need manual review.

    Source-row accounting: input_rows == accepted_rows + quarantined_rows.
    Each accepted row emits >=1 aligned form (or duplicate); rejected forms of
    a partly accepted row receive separate review records. Form accounting:
    form_candidates == accepted_entries + duplicate_entries + quarantined_forms.
    Definitions are omitted even from imported review rows; raw_record retains
    only the original prefix before the definition delimiter, with a full-line
    SHA256 and physical line reference to the unmodified retained source.
    """
    path = Path(path)
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("CC-Canto source exceeds the size limit")
    source_id = source_id or SOURCE_FILES.get(path.name)
    if source_id not in SOURCE_FILES.values():
        raise ValueError("Explicit CC-Canto source kind is required for an unfamiliar filename")
    bases = (frozenset(allowed_bases) if allowed_bases is not None
             else read_attested_bases(path.parent / ATTESTATION_NAME))
    if not bases or any(not isinstance(base, str) or not _BASE.fullmatch(base) for base in bases):
        raise ValueError("Invalid attested syllable set")
    counts = stats if stats is not None else {}

    def count(key, amount=1):
        counts[key] = counts.get(key, 0) + amount

    def review(number, raw, text, reading, reason, *, kind="row", **fields):
        count("review_records")
        count("rejected_" + reason)
        if review_rows is not None:
            review_rows.append({"source": source_id, "line": number, "text": text,
                                "raw_reading": reading, "raw_record": raw.partition(" /")[0],
                                "raw_line_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                                "status": "quarantined", "scope": kind, "reason": reason, **fields})

    seen = set()
    with path.open(encoding="utf-8-sig") as stream:
        for number, physical in enumerate(stream, 1):
            raw = physical.rstrip("\r\n")
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            count("input_rows")
            match = _ROW.fullmatch(raw)
            if not match:
                count("quarantined_rows")
                review(number, raw, raw.split(maxsplit=1)[0], "", "malformed_record")
                continue
            traditional, simplified, raw_reading = match.groups()
            fields = {"traditional": traditional, "simplified": simplified}
            codes = raw_reading.lower().split()
            if not codes or any(not _CODE.fullmatch(code) for code in codes):
                count("quarantined_rows")
                review(number, raw, traditional, raw_reading, "noncanonical_jyutping", **fields)
                continue
            unknown = sorted({code[:-1] for code in codes} - bases)
            if unknown:
                count("quarantined_rows")
                review(number, raw, traditional, raw_reading, "unattested_syllables", unknown_bases=unknown, **fields)
                continue
            reading = " ".join(codes)
            if reading != raw_reading:
                count("normalized_reading_rows")
            forms = list(dict.fromkeys((traditional, simplified)))
            valid_forms = 0
            for text in forms:
                count("form_candidates")
                if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in text):
                    count("quarantined_forms")
                    review(number, raw, text, raw_reading, "invalid_text", kind="form", **fields)
                    continue
                if len(text) != len(codes):
                    count("quarantined_forms")
                    review(number, raw, text, raw_reading, "codepoint_syllable_alignment", kind="form",
                           text_codepoints=len(text), syllable_count=len(codes), **fields)
                    continue
                valid_forms += 1
                pair = text, reading
                if pair in seen:
                    count("duplicate_entries")
                    continue
                seen.add(pair)
                count("accepted_entries")
                base_reading = " ".join(code[:-1] for code in codes)
                yield DictionaryEntry(text, reading, base_reading, base_reading.replace(" ", ""),
                                      len(codes), 0.0, source_id)
            count("accepted_rows" if valid_forms else "quarantined_rows")
