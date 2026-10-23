"""Read source-located CC-CEDICT written forms, never Mandarin readings.

This is a text-only candidate reader. It neither generates Cantonese codes nor
selects data for the default dictionary. Source data retains CC BY-SA 4.0.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import gzip
import hashlib
import io
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Iterator, MutableMapping, MutableSequence
import zlib


SOURCE_ID = "cccedict:headwords"
DATA_FILE = "cedict_ts.u8"
ARCHIVE_FILE = "cedict_1_0_ts_utf-8_mdbg.txt.gz"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
LICENSE_DECLARATION = "Creative Commons Attribution-ShareAlike 4.0 International License"
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_LINES = 600_000
MAX_ROWS = 300_000
_HASH = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_ROW = re.compile(r"^(\S+)[ \t]+(\S+)[ \t]+\[[^\[\]\r\n]+\][ \t]+/.*\/$")
_REQUIRED_FILES = frozenset({DATA_FILE, ARCHIVE_FILE, "download-page.html",
                             "LICENSE-CC-BY-SA-4.0.txt", "ATTRIBUTION.md"})


@dataclass(frozen=True, slots=True)
class HeadwordRecord:
    """One physical headword-field occurrence; no pronunciation is supplied."""

    text: str
    line: int
    script: str
    raw_line_sha256: str
    source: str = SOURCE_ID


@dataclass(frozen=True, slots=True)
class _ParsedSource:
    header: dict[str, str]
    rows: tuple[tuple[int, str, str, str], ...]
    source_sha256: str
    comment_or_blank_lines: int


def _read_bounded(path: Path, limit: int = MAX_SOURCE_BYTES) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError("CC-CEDICT retained file exceeds the size limit")
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("CC-CEDICT retained file exceeds the size limit")
    return payload


def _parse_source(payload: bytes) -> _ParsedSource:
    if len(payload) > MAX_SOURCE_BYTES:
        raise ValueError("CC-CEDICT source exceeds the size limit")
    try:
        document = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CC-CEDICT source must be UTF-8") from error
    lines = document.split("\n")
    if len(lines) > MAX_LINES:
        raise ValueError("CC-CEDICT physical line limit exceeded")
    header: dict[str, str] = {}
    comments, rows = [], []
    ignored = 0
    for number, physical in enumerate(lines, 1):
        raw = physical.removesuffix("\r")
        if len(raw.encode("utf-8")) > MAX_LINE_BYTES:
            raise ValueError(f"CC-CEDICT line {number} exceeds the line limit")
        if any(ord(char) < 32 and char != "\t" for char in raw):
            raise ValueError(f"CC-CEDICT line {number} contains a control character")
        if not raw.strip() or raw.startswith("#"):
            ignored += 1
            if raw.startswith("#!"):
                if rows:
                    raise ValueError("CC-CEDICT directives must precede data")
                directive = raw[2:].strip()
                key, separator, value = directive.partition("=")
                if not separator or not key or not value or key in header:
                    raise ValueError("Malformed or duplicate CC-CEDICT header directive")
                header[key] = value
            elif not rows:
                comments.append(raw)
            continue
        match = _ROW.fullmatch(raw)
        if match is None:
            raise ValueError(f"Malformed CC-CEDICT structural record on line {number}")
        traditional, simplified = match.groups()
        rows.append((number, traditional, simplified,
                     hashlib.sha256(raw.encode("utf-8")).hexdigest()))
        if len(rows) > MAX_ROWS:
            raise ValueError("CC-CEDICT source row limit exceeded")
    expected = {"version": "1", "format": "ts", "charset": "UTF-8",
                "publisher": "MDBG", "license": LICENSE_URL}
    if any(header.get(key) != value for key, value in expected.items()):
        raise ValueError("Unexpected CC-CEDICT version/format/charset/publisher/license header")
    try:
        declared = header["entries"]
        if not re.fullmatch(r"[1-9][0-9]*", declared, re.ASCII):
            raise ValueError
        expected_rows = int(declared)
        date = datetime.fromisoformat(header["date"].replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError
    except (KeyError, ValueError, OverflowError) as error:
        raise ValueError("Invalid CC-CEDICT nonzero entry count or release date") from error
    if not rows or expected_rows != len(rows):
        raise ValueError("CC-CEDICT declared entry count disagrees with parsed rows")
    declaration = "\n".join(comments)
    if ("# CC-CEDICT" not in declaration or "Published by MDBG" not in declaration
            or LICENSE_DECLARATION not in declaration or LICENSE_URL not in declaration):
        raise ValueError("CC-CEDICT original source attribution/license declaration is missing")
    return _ParsedSource(header, tuple(rows), hashlib.sha256(payload).hexdigest(), ignored)


def _safe_file(directory: Path, name: object) -> Path:
    if not isinstance(name, str) or not name or len(name) > 240 or "\\" in name or ":" in name:
        raise ValueError("Unsafe CC-CEDICT retained filename")
    posix = PurePosixPath(name)
    if (posix.is_absolute() or PureWindowsPath(name).is_absolute()
            or any(part in ("", ".", "..") or part.endswith((".", " ")) for part in name.split("/"))):
        raise ValueError("Unsafe CC-CEDICT retained filename")
    target = (directory / name).resolve()
    try:
        target.relative_to(directory.resolve())
    except ValueError as error:
        raise ValueError("CC-CEDICT retained path escapes its directory") from error
    if not target.is_file():
        raise ValueError("Missing CC-CEDICT retained file")
    return target


def verify_cccedict_headwords_snapshot(directory: str | Path, lock: dict) -> None:
    """Verify pinned files, full notices, structural header and gzip/plain identity.

    Verification establishes local source correspondence, not publisher signature,
    pronunciation approval or selection for the product. Every listed path is
    checked, with Windows-equivalent duplicate names rejected.
    """
    if (not isinstance(lock, dict) or lock.get("schema_version") != 1
            or lock.get("source_id") != SOURCE_ID or lock.get("license") != "CC-BY-SA-4.0"
            or lock.get("license_declaration") != LICENSE_DECLARATION):
        raise ValueError("Unexpected CC-CEDICT source lock/license")
    files = lock.get("files")
    if (not isinstance(files, list) or not 5 <= len(files) <= 32
            or any(not isinstance(item, dict) for item in files)):
        raise ValueError("Missing CC-CEDICT retained files/notices")
    directory = Path(directory)
    payloads, names = {}, set()
    total = 0
    for item in files:
        name = item.get("name")
        path = _safe_file(directory, name)
        if name.casefold() in names:
            raise ValueError("Duplicate CC-CEDICT retained filename")
        names.add(name.casefold())
        expected_size, expected_hash = item.get("size_bytes"), item.get("sha256")
        if (type(expected_size) is not int or not 0 < expected_size <= MAX_SOURCE_BYTES
                or not isinstance(expected_hash, str) or not _HASH.fullmatch(expected_hash)):
            raise ValueError("Invalid CC-CEDICT retained file size/hash")
        total += expected_size
        if total > 96 * 1024 * 1024:
            raise ValueError("CC-CEDICT retained snapshot exceeds the total size limit")
        payload = _read_bounded(path)
        if len(payload) != expected_size or hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ValueError("CC-CEDICT retained file differs from its source lock")
        payloads[name] = payload
    if not _REQUIRED_FILES <= payloads.keys():
        raise ValueError("Missing CC-CEDICT source/archive/full notices")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payloads[ARCHIVE_FILE])) as archive:
            unpacked = archive.read(MAX_SOURCE_BYTES + 1)
    except (OSError, EOFError, zlib.error) as error:
        raise ValueError("Malformed CC-CEDICT gzip archive") from error
    if len(unpacked) > MAX_SOURCE_BYTES or unpacked != payloads[DATA_FILE]:
        raise ValueError("CC-CEDICT gzip content differs from bounded retained plain text")
    parsed = _parse_source(payloads[DATA_FILE])
    release = lock.get("source_release_header")
    if (not isinstance(release, dict)
            or any(release.get(key) != parsed.header.get(key) for key in ("date", "format", "version", "charset"))
            or type(release.get("entries")) is not int or release["entries"] != len(parsed.rows)):
        raise ValueError("CC-CEDICT source header differs from the locked release")
    try:
        page = payloads["download-page.html"].decode("utf-8")
        legal = payloads["LICENSE-CC-BY-SA-4.0.txt"].decode("utf-8")
        attribution = payloads["ATTRIBUTION.md"].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("CC-CEDICT retained notices must be UTF-8") from error
    if LICENSE_DECLARATION not in page or LICENSE_URL not in page:
        raise ValueError("CC-CEDICT retained download page lacks its license declaration")
    if (len(legal) < 10_000 or "Creative Commons" not in legal
            or "Attribution-ShareAlike 4.0 International" not in legal
            or any(f"Section {number} --" not in legal for number in range(1, 9))):
        raise ValueError("CC-CEDICT retained full license terms are missing/incomplete")
    if any(word not in attribution for word in ("CC-CEDICT", "MDBG", "Paul Andrew Denisowski", "Mandarin", "Cantonese")):
        raise ValueError("CC-CEDICT attribution/transformation notice is incomplete")


def _is_han(character: str) -> bool:
    point = ord(character)
    return point == 0x3007 or any(start <= point <= end for start, end in (
        (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
        (0x20000, 0x2A6DF), (0x2A700, 0x2B73F), (0x2B740, 0x2B81F),
        (0x2B820, 0x2CEAF), (0x2CEB0, 0x2EBEF), (0x2EBF0, 0x2EE5F),
        (0x2F800, 0x2FA1F), (0x30000, 0x3134F), (0x31350, 0x323AF),
        (0x323B0, 0x3347F),
    ))


def read_cccedict_headwords(
    path: str | Path,
    *,
    stats: MutableMapping[str, int] | None = None,
    review_rows: MutableSequence[dict] | None = None,
) -> Iterator[HeadwordRecord]:
    """Yield both Han-field occurrences, including identical traditional/simplified.

    The whole file's header, license, UTF-8, shape and exact row count validate
    before the first record or caller ledger is published. No Pinyin/definition
    field is returned, converted, normalized, inspected as Cantonese or copied
    to review rows. Raw line hashes exclude line terminators. Physical lines and
    script labels distinguish repeated source occurrences; the builder owns any
    later deduplication. Han bounds plus U+3007 are a declared admission rule,
    not a claim that all codepoints are assigned words.

    input_rows == source_rows; form_candidates == 2 * source_rows;
    form_candidates == accepted_occurrences + quarantined_forms.
    """
    path = Path(path)
    parsed = _parse_source(_read_bounded(path))
    counts = {"input_rows": len(parsed.rows), "source_rows": len(parsed.rows),
              "form_candidates": 2 * len(parsed.rows), "accepted_occurrences": 0,
              "quarantined_forms": 0, "review_records": 0,
              "identical_form_rows": 0, "comment_or_blank_lines": parsed.comment_or_blank_lines}
    records, reviews, accepted, rejected = [], [], set(), set()
    for number, traditional, simplified, line_hash in parsed.rows:
        counts["identical_form_rows"] += traditional == simplified
        for script, text in (("traditional", traditional), ("simplified", simplified)):
            if all(_is_han(character) for character in text):
                counts["accepted_occurrences"] += 1
                accepted.add(text)
                records.append(HeadwordRecord(text, number, script, line_hash))
            else:
                counts["quarantined_forms"] += 1
                counts["review_records"] += 1
                rejected.add(text)
                reviews.append({"source": SOURCE_ID, "source_file": path.name,
                                "source_sha256": parsed.source_sha256, "line": number,
                                "script": script, "text": text, "raw_line_sha256": line_hash,
                                "scope": "headword", "reason": "non_han_headword", "status": "quarantined"})
    counts["unique_han_forms"] = len(accepted)
    counts["unique_non_han_forms"] = len(rejected)
    if stats is not None:
        for key, value in counts.items():
            stats[key] = stats.get(key, 0) + value
    if review_rows is not None:
        review_rows.extend(reviews)
    yield from records
