"""Build the local Cantonese lexicon using stdlib only.

This is a deliberately small Rime *text-table* reader, not a YAML interpreter or
a general Rime dictionary compiler. The full build adapts Rime's bounded phrase
autoencoder, retaining a ledger and keeping partial results out of live entries.
Missing and percentage weights use the preset vocabulary; an absent preset
frequency is zero, matching librime's entry collector.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Callable, Iterator, Mapping, MutableMapping


DICTIONARY_FILES = (
    "jyut6ping3.chars.dict.yaml",
    "jyut6ping3.words.dict.yaml",
    "jyut6ping3.phrase.dict.yaml",
)
FREQUENCY_FILE = "essay-cantonese.txt"
NOTICE_FILES = ("LICENSE-CC-BY", "README-en.md")
SCHEMA_VERSION = 2
SUPPLEMENT_ORDER = ("lshk", "wordshk", "typeduck", "unihan", "cccanto", "cccedict_cantonese", "wordnet", "cccedict_headwords", "yue_wiktionary")
HEADWORD_GENERATED_SOURCE = "cccedict:headwords:autoencoded"
HEADWORD_FORMS_TABLE = "cccedict_headword_forms"
HEADWORD_ENCODINGS_TABLE = "cccedict_headword_encodings"
YUE_WIKTIONARY_TABLES = {"pages": "yue_wiktionary_pages", "sections": "yue_wiktionary_sections",
                         "fields": "yue_wiktionary_fields", "reviews": "yue_wiktionary_review"}
_SYLLABLE = re.compile(r"[a-z]+[1-6]\Z")


@dataclass(frozen=True)
class DictionaryEntry:
    text: str
    reading: str
    base_reading: str
    compact: str
    syllable_count: int
    weight: float
    source: str


def _error(path: Path, line: int, message: str) -> ValueError:
    return ValueError(f"{path}:{line}: {message}")


def _number(value: str, path: Path, line: int) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise _error(path, line, f"invalid weight {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise _error(path, line, "weight must be finite and nonnegative")
    return number


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_frequencies(
    path: str | Path, *, stats: MutableMapping[str, int] | None = None
) -> dict[str, float]:
    """Read preset frequencies; later duplicate keys win as in Rime TextDb."""
    path = Path(path)
    frequencies: dict[str, float] = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, raw in enumerate(stream, 1):
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            columns = line.split("\t")
            if len(columns) != 2 or not columns[0]:
                raise _error(path, line_number, "expected text<TAB>frequency")
            text, value = columns
            if text in frequencies and stats is not None:
                stats["duplicate_frequency_rows"] = stats.get("duplicate_frequency_rows", 0) + 1
            frequencies[text] = _number(value, path, line_number)
    return frequencies


def read_entries(
    path: str | Path,
    *,
    frequencies: Mapping[str, float] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> Iterator[DictionaryEntry]:
    """Read explicit tab-separated Rime text/code/weight rows.

    Metadata must be bounded by ``---`` and ``...``. Only the upstream default
    text/code/weight column order is accepted; custom ``columns:`` declarations
    fail rather than being misread. Text-only rows are counted as
    ``skipped_missing_reading`` because their pronunciation is not explicit.
    ``stats`` is optional and accumulates counts while the iterator is consumed.
    """
    path = Path(path)
    frequencies = frequencies or {}
    counts = stats if stats is not None else Counter()
    state = "preamble"
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, raw in enumerate(stream, 1):
            line = raw.rstrip("\r\n")
            stripped = line.strip()
            if state != "body":
                if not stripped or stripped.startswith("#"):
                    continue
                if state == "preamble":
                    if stripped != "---":
                        raise _error(path, line_number, "missing Rime header start ---")
                    state = "header"
                    continue
                if stripped == "...":
                    state = "body"
                elif re.match(r"columns\s*:", stripped):
                    raise _error(path, line_number, "custom column order is unsupported")
                continue
            if not stripped or stripped.startswith("#"):
                continue
            counts["input_rows"] = counts.get("input_rows", 0) + 1
            columns = line.split("\t")
            if len(columns) > 3:
                raise _error(path, line_number, "expected at most text, code and weight columns")
            text = columns[0]
            if not text or text != text.strip() or any(ord(c) < 32 for c in text):
                raise _error(path, line_number, "empty, padded or control-containing entry text")
            if len(columns) < 2 or not columns[1].strip():
                counts["skipped_missing_reading"] = counts.get("skipped_missing_reading", 0) + 1
                continue
            syllables = columns[1].lower().split()
            if not syllables or any(not _SYLLABLE.fullmatch(s) for s in syllables):
                raise _error(path, line_number, f"invalid toned Jyutping reading {columns[1]!r}")
            weight_string = columns[2].strip() if len(columns) == 3 else ""
            preset = float(frequencies.get(text, 0.0))
            if not math.isfinite(preset) or preset < 0:
                raise _error(path, line_number, "preset frequency must be finite and nonnegative")
            if weight_string.endswith("%"):
                percentage = _number(weight_string[:-1], path, line_number)
                weight = preset * percentage / 100.0
                counts["percentage_weight_rows"] = counts.get("percentage_weight_rows", 0) + 1
            elif weight_string:
                weight = _number(weight_string, path, line_number)
                counts["absolute_weight_rows"] = counts.get("absolute_weight_rows", 0) + 1
            else:
                weight = preset
                counts["preset_weight_rows"] = counts.get("preset_weight_rows", 0) + 1
            if not math.isfinite(weight):
                raise _error(path, line_number, "resolved weight overflow")
            base = [syllable[:-1] for syllable in syllables]
            counts["explicit_rows"] = counts.get("explicit_rows", 0) + 1
            yield DictionaryEntry(text, " ".join(syllables), " ".join(base),
                                  "".join(base), len(syllables), weight, path.name)
    if state != "body":
        raise _error(path, 0, "missing Rime header terminator ...")


def verify_source_files(source_dir: str | Path, lock: Mapping) -> None:
    """Verify a downloaded source snapshot against the committed SHA-256 lock."""
    source_dir = Path(source_dir)
    for item in lock["files"]:
        name = item["name"]
        if Path(name).name != name or name in (".", ".."):
            raise ValueError(f"unsafe locked source filename: {name!r}")
        path = source_dir / name
        if not path.is_file():
            raise ValueError(f"missing locked source file: {path}")
        if path.stat().st_size != item["size_bytes"] or file_sha256(path) != item["sha256"]:
            raise ValueError(f"source integrity mismatch: {path}")
        if item.get("git_blob_sha1"):
            payload = path.read_bytes()
            blob = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
            if hashlib.sha1(blob).hexdigest() != item["git_blob_sha1"]:
                raise ValueError(f"upstream Git blob mismatch: {path}")


def _append_cccedict_headwords(
    connection: sqlite3.Connection,
    records: list,
    review_rows: list[dict],
    source_path: Path,
    source_stats: Mapping,
    excluded_sources: set[str],
    progress: Callable[[str], None] | None,
) -> dict:
    """Append complete absent-text encodings from a fixed pre-append snapshot.

    Written forms supply no codes. The translator is the same source-explicit,
    one-syllable SQL cohort used by the isolated candidate; neither generated
    phrases nor Wordnet/CC-Canto/provisional character rows can enter it.
    Every source field and incomplete encoding remains in a separate ledger.
    """
    from .autoencode import ScriptAutoencoder
    from .cccedict_headwords import DATA_FILE, SOURCE_ID

    complete = {"encoded_unique", "encoded_ambiguous"}
    incomplete = {"truncated", "unencodable", "too_long"}

    def canonical_json(value) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    existing_texts = {row[0] for row in connection.execute("SELECT DISTINCT text FROM entries")}
    baseline_pairs = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    boundary = connection.execute("SELECT COALESCE(MAX(id),0) FROM entries").fetchone()[0]
    bases = {base for (reading,) in connection.execute("SELECT DISTINCT base_reading FROM entries")
             for base in reading.split()}
    translator_rows = [row for row in connection.execute(
        "SELECT id,text,reading,weight,source,origin FROM entries WHERE id<=? "
        "AND origin IN ('explicit','supplement') AND syllable_count=1 ORDER BY text,reading", (boundary,))
        if row[4] not in excluded_sources]
    translations = [row[1:4] for row in translator_rows]
    translator_hash = hashlib.sha256()
    for row in translator_rows:
        translator_hash.update((canonical_json(row) + "\n").encode("utf-8"))
    if not bases or not translations:
        raise ValueError("CC-CEDICT headwords require eligible Cantonese character translations")
    if source_stats["accepted_occurrences"] != len(records):
        raise ValueError("CC-CEDICT accepted-form accounting disagrees")
    encoder = ScriptAutoencoder(translations)
    references: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if record.text not in existing_texts:
            references[record.text].append({"line": record.line, "script": record.script,
                                            "raw_line_sha256": record.raw_line_sha256})
    encoded, added = {}, []
    encoding_counts: Counter = Counter()
    for number, text in enumerate(sorted(references), 1):
        result = encoder.encode(text)
        if result.text != text or result.status not in complete | incomplete:
            raise ValueError("Unexpected CC-CEDICT Cantonese autoencoder result")
        if result.status in complete:
            if (not result.codes or len(result.codes) != len(set(result.codes))
                    or (result.status == "encoded_unique") != (len(result.codes) == 1)):
                raise ValueError("Complete CC-CEDICT encoding has inconsistent codes")
            for reading in sorted(result.codes):
                tokens = reading.split()
                if (not tokens or " ".join(tokens) != reading
                        or any(not _SYLLABLE.fullmatch(code) or code[:-1] not in bases for code in tokens)):
                    raise ValueError("CC-CEDICT generated code is outside the pre-append Cantonese inventory")
                added.append((text, reading))
        encoded[text] = result.to_dict()
        encoding_counts[result.status] += 1
        if progress is not None and (number % 2500 == 0 or number == len(references)):
            progress(f"Accounted for {number:,} of {len(references):,} missing CC-CEDICT headwords")

    connection.executescript(f"""
        CREATE TABLE {HEADWORD_FORMS_TABLE} (
            line INTEGER NOT NULL,script TEXT NOT NULL,text TEXT NOT NULL,
            raw_line_sha256 TEXT NOT NULL,source TEXT NOT NULL,source_file TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,status TEXT NOT NULL,reason TEXT,
            PRIMARY KEY(line,script)) WITHOUT ROWID;
        CREATE TABLE {HEADWORD_ENCODINGS_TABLE} (
            text TEXT PRIMARY KEY,status TEXT NOT NULL,codes_json TEXT NOT NULL,
            path_count INTEGER NOT NULL,work_count INTEGER NOT NULL,reason TEXT,
            source_refs_json TEXT NOT NULL) WITHOUT ROWID;
    """)
    connection.executemany(f"INSERT INTO {HEADWORD_ENCODINGS_TABLE} VALUES (?,?,?,?,?,?,?)", (
        (text, value["status"], canonical_json(value["codes"]), value["path_count"], value["work_count"],
         value["reason"], canonical_json(references[text])) for text, value in sorted(encoded.items())))
    source_hash = file_sha256(source_path)
    form_counts: Counter = Counter()

    def form_rows():
        for record in records:
            status = "already_present" if record.text in existing_texts else encoded[record.text]["status"]
            reason = None if status == "already_present" else encoded[record.text]["reason"]
            form_counts[status] += 1
            yield (record.line, record.script, record.text, record.raw_line_sha256, SOURCE_ID,
                   DATA_FILE, source_hash, status, reason)
        for row in review_rows:
            form_counts["source_quarantined"] += 1
            yield (row["line"], row["script"], row["text"], row["raw_line_sha256"], SOURCE_ID,
                   DATA_FILE, source_hash, "source_quarantined", row["reason"])

    connection.executemany(f"INSERT INTO {HEADWORD_FORMS_TABLE} VALUES (?,?,?,?,?,?,?,?,?)", form_rows())
    for text, reading in added:
        tokens = reading.split()
        base = " ".join(token[:-1] for token in tokens)
        connection.execute("INSERT INTO entries(text,reading,base_reading,compact,syllable_count,weight,source,origin) "
                           "VALUES (?,?,?,?,?,?,?,?)", (
                               text, reading, base, base.replace(" ", ""), len(tokens),
                               0.0, HEADWORD_GENERATED_SOURCE, "generated"))
    complete_texts = encoding_counts["encoded_unique"] + encoding_counts["encoded_ambiguous"]
    final_pairs, final_texts = connection.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
    if (final_pairs, final_texts) != (baseline_pairs + len(added), len(existing_texts) + complete_texts):
        raise ValueError("CC-CEDICT append pair/text accounting disagrees")
    if (sum(form_counts.values()) != source_stats["form_candidates"]
            or connection.execute(f"SELECT COUNT(*) FROM {HEADWORD_ENCODINGS_TABLE}").fetchone()[0] != len(references)):
        raise ValueError("CC-CEDICT source/encoding ledger is incomplete")
    return {
        "insertion_phase": "post_autoencoding_post_wordnet",
        "generated_source": HEADWORD_GENERATED_SOURCE,
        "source_reading_policy": "Han headwords only. Mandarin Pinyin and definitions never supply codes. "
            "Only complete mechanical Cantonese encodings of absent texts are added; existing texts, "
            "pairs, IDs and all earlier ledgers remain unchanged. Incomplete alternatives stay quarantined.",
        "linguistic_approval": False,
        "pre_headword_max_entry_id": boundary,
        "baseline_entry_count": baseline_pairs, "baseline_distinct_texts": len(existing_texts),
        "translator_input_sha256": translator_hash.hexdigest(),
        "translator_input_hash_policy": {
            "fields": ["id", "text", "reading", "weight", "source", "origin"],
            "where": "id <= pre_headword_max_entry_id AND origin IN ('explicit','supplement') AND syllable_count=1 AND source NOT IN excluded_encoder_sources",
            "order": ["text", "reading"],
            "serialization": "UTF-8 JSON arrays; ensure_ascii=False; separators=(',',':'); newline after each row",
        },
        "encoder": encoder.metadata(), "excluded_encoder_sources": sorted(excluded_sources),
        "translation_rows": len(translations),
        "encoding_counts": dict(sorted(encoding_counts.items())),
        "missing_texts": len(references), "complete_new_texts": complete_texts,
        "new_generated_pairs": len(added), "added_pairs": len(added),
        "already_present_source_texts": source_stats["unique_han_forms"] - len(references),
        "form_status_counts": dict(sorted(form_counts.items())),
        "source_form_ledger_rows": sum(form_counts.values()), "encoding_ledger_rows": len(references),
        "weight_policy": "Zero means unknown pronunciation frequency; no Mandarin code, definition or source rank is imported.",
    }


def _append_yue_wiktionary(
    connection: sqlite3.Connection,
    entries: list[DictionaryEntry],
    pages: list[dict],
    sections: list[dict],
    fields: list[dict],
    reviews: list[dict],
    source_path: Path,
    source_stats: Mapping,
) -> dict:
    """Append explicit pairs only after all generation and keep complete ledgers.

    Earlier source winners, entry IDs and all earlier review/generation tables
    are untouched. The pending Wiktionary readings never reach either encoder.
    """
    from .yue_wiktionary import SOURCE_ID

    if (not entries or source_stats.get("unique_pairs") != len(entries)
            or source_stats.get("all_xml_pages") != len(pages) or not pages
            or source_stats.get("section_records") != len(sections)
            or source_stats.get("field_records") != len(fields)
            or source_stats.get("review_records") != len(reviews)):
        raise ValueError("Yue Wiktionary source/ledger accounting is incomplete")
    source_hash = file_sha256(source_path)
    if any(row.get("source") != SOURCE_ID or row.get("source_sha256") != source_hash
           for row in [*pages, *sections, *fields, *reviews]):
        raise ValueError("Yue Wiktionary ledger source correspondence differs")
    located_pairs = {(row.get("text"), row.get("normalized_reading")) for row in fields
                     if row.get("scope") == "variant" and row.get("status") == "admitted_pair"}
    unique = {(entry.text, entry.reading) for entry in entries}
    if len(unique) != len(entries) or located_pairs != unique:
        raise ValueError("Yue Wiktionary accepted-pair provenance differs")
    before_pairs, before_texts = connection.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
    boundary = connection.execute("SELECT COALESCE(MAX(id),0) FROM entries").fetchone()[0]
    existing_texts = {row[0] for row in connection.execute("SELECT DISTINCT text FROM entries")}
    existing_bases = {base for (reading,) in connection.execute("SELECT DISTINCT base_reading FROM entries") for base in reading.split()}
    added, overlap, new_texts = 0, 0, set()
    for entry in sorted(entries, key=lambda value: (value.text, value.reading)):
        tokens = entry.reading.split()
        base = " ".join(token[:-1] for token in tokens)
        if (entry.source != SOURCE_ID or entry.weight != 0 or not tokens
                or any(not _SYLLABLE.fullmatch(token) or token[:-1] not in existing_bases for token in tokens)
                or " ".join(tokens) != entry.reading
                or (entry.base_reading, entry.compact, entry.syllable_count) != (base, base.replace(" ", ""), len(tokens))):
            raise ValueError("Yue Wiktionary entries must retain canonical source readings and unknown-frequency zero")
        result = connection.execute(
            "INSERT OR IGNORE INTO entries(text,reading,base_reading,compact,syllable_count,weight,source,origin) VALUES (?,?,?,?,?,?,?,?)",
            (entry.text, entry.reading, entry.base_reading, entry.compact, entry.syllable_count, 0.0, SOURCE_ID, "supplement"))
        if result.rowcount:
            added += 1
            if entry.text not in existing_texts:
                new_texts.add(entry.text)
        else:
            overlap += 1
    tables = YUE_WIKTIONARY_TABLES
    connection.executescript(f"""
        CREATE TABLE {tables['pages']} (page_id TEXT PRIMARY KEY,revision_id TEXT,namespace TEXT NOT NULL,
            text TEXT NOT NULL,status TEXT NOT NULL,details_json TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE {tables['sections']} (page_id TEXT NOT NULL,section_ordinal INTEGER NOT NULL,
            details_json TEXT NOT NULL,PRIMARY KEY(page_id,section_ordinal)) WITHOUT ROWID;
        CREATE TABLE {tables['fields']} (id INTEGER PRIMARY KEY,page_id TEXT NOT NULL,scope TEXT NOT NULL,
            status TEXT NOT NULL,details_json TEXT NOT NULL);
        CREATE TABLE {tables['reviews']} (id INTEGER PRIMARY KEY,page_id TEXT NOT NULL,scope TEXT NOT NULL,
            details_json TEXT NOT NULL);
    """)

    def canonical(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    connection.executemany(f"INSERT INTO {tables['pages']} VALUES (?,?,?,?,?,?)", (
        (row["page_id"], row.get("revision_id"), row["namespace"], row["text"], row["status"], canonical(row)) for row in pages))
    connection.executemany(f"INSERT INTO {tables['sections']} VALUES (?,?,?)", (
        (row["page_id"], row["language_section_ordinal"], canonical(row)) for row in sections))
    connection.executemany(f"INSERT INTO {tables['fields']} VALUES (?,?,?,?,?)", (
        (number, row["page_id"], row["scope"], row["status"], canonical(row)) for number, row in enumerate(fields, 1)))
    connection.executemany(f"INSERT INTO {tables['reviews']} VALUES (?,?,?,?)", (
        (number, row["page_id"], row["scope"], canonical(row)) for number, row in enumerate(reviews, 1)))
    after_pairs, after_texts = connection.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
    if (after_pairs, after_texts) != (before_pairs + added, before_texts + len(new_texts)):
        raise ValueError("Yue Wiktionary append row/text accounting differs")
    return {"insertion_phase": "post_autoencoding_post_wordnet_post_cccedict_headwords",
            "source": SOURCE_ID, "linguistic_approval": False, "pre_wiktionary_max_entry_id": boundary,
            "baseline_entry_count": before_pairs, "baseline_distinct_texts": before_texts,
            "accepted_source_pairs": len(entries), "added_pairs": added, "overlapping_pairs": overlap,
            "new_texts": len(new_texts), "ledger_counts": {"pages": len(pages), "sections": len(sections),
                                                         "fields": len(fields), "reviews": len(reviews)},
            "reading_policy": "Only source-explicit own-headword Yue fields; no inferred words or template expansion. "
                "Earlier pairs win exact overlaps. Appended character readings never supply encoder translations.",
            "weight_policy": "Zero is unknown pronunciation frequency; no source rank or corpus count is invented."}


def build_dictionary(
    source_dir: str | Path,
    output_path: str | Path,
    *,
    source_metadata: Mapping | None = None,
    supplements: Mapping[str, str | Path] | None = None,
    autoencode_phrases: bool = False,
    progress: Callable[[str], None] | None = None,
    verify_before_publish: Callable[[], None] | None = None,
) -> dict:
    """Build SQLite and a JSON manifest, replacing the database only on success.

    At least one known dictionary file must exist. This also supports small
    local fixtures without a download lock; the CLI verifies the real snapshot.
    Optional supplements retain source-authored readings. Phrase generation is
    opt-in at the library boundary and default in the full build CLI; generated
    readings retain their origin and unresolved rows remain in a review table.
    Stable Unicode sorting assigns deterministic IDs and breaks duplicate ties.
    Wordnet is validated into a pending list, then appended only after phrase
    autoencoding. It cannot change encoder inputs or already_explicit decisions.
    Optional CC-CEDICT Han headwords are encoded only after Wordnet, against a
    fixed earlier translator, and never replace an existing text or input code.
    An optional verification callback runs before either output is published.
    """
    source_dir, output_path = Path(source_dir), Path(output_path)
    if "cccedict_headwords" in (supplements or {}) and not autoencode_phrases:
        raise ValueError("CC-CEDICT headword selection requires autoencode_phrases=True")
    files = [source_dir / name for name in DICTIONARY_FILES if (source_dir / name).is_file()]
    if not files:
        raise ValueError(f"no supported dictionary files in {source_dir}")
    frequency_path = source_dir / FREQUENCY_FILE
    frequency_stats: Counter = Counter()
    frequencies = read_frequencies(frequency_path, stats=frequency_stats) if frequency_path.is_file() else {}
    entries: dict[tuple[str, str], DictionaryEntry] = {}
    origins: dict[tuple[str, str], str] = {}
    counts: Counter = Counter()
    source_stats = {}
    for path in files:
        per_source: Counter = Counter()
        for entry in read_entries(path, frequencies=frequencies, stats=per_source):
            key = (entry.text, entry.reading)
            previous = entries.get(key)
            if previous is not None:
                counts["duplicate_count"] += 1
            if previous is None or entry.weight > previous.weight:
                entries[key] = entry
                origins[key] = "explicit"
        counts.update(per_source)
        source_stats[path.name] = dict(sorted(per_source.items()))
    supplement_review: list[dict] = []
    supplement_stats = {}
    post_autoencoding: dict[str, list[DictionaryEntry]] = {}
    pending_headwords = None
    pending_yue_wiktionary = None
    supplement_order = sorted(supplements or {}, key=lambda kind: (
        SUPPLEMENT_ORDER.index(kind) if kind in SUPPLEMENT_ORDER else len(SUPPLEMENT_ORDER), kind))
    for kind in supplement_order:
        supplement = (supplements or {})[kind]
        supplement = Path(supplement)
        local_stats: dict[str, int] = {}
        if kind == "lshk":
            from .supplements import read_lshk_entries
            imported = read_lshk_entries(supplement, stats=local_stats, review_rows=supplement_review)
        elif kind == "wordshk":
            from .wordshk import read_wordshk_entries
            imported = read_wordshk_entries(supplement, stats=local_stats, review_rows=supplement_review)
        elif kind == "typeduck":
            from .typeduck import read_typeduck_entries
            imported = read_typeduck_entries(supplement, stats=local_stats, review_rows=supplement_review)
        elif kind == "unihan":
            from .unihan import read_unihan_entries
            imported = read_unihan_entries(supplement, stats=local_stats)
        elif kind in ("cccanto", "cccedict_cantonese"):
            from .cccanto import read_cccanto_entries
            source_id = "cccanto:dictionary" if kind == "cccanto" else "cccanto:cedict-readings"
            imported = read_cccanto_entries(supplement, source_id=source_id, stats=local_stats,
                                           review_rows=supplement_review)
        elif kind == "wordnet":
            from .wordnet import read_wordnet_entries
            # Validate early, but keep every Wordnet pair out of entries,
            # ordered, known_by_text and the encoder until generation finishes.
            pending = list(read_wordnet_entries(supplement, stats=local_stats, review_rows=supplement_review))
            if any(entry.source != "wordnet:cantown" or entry.weight != 0 for entry in pending):
                raise ValueError("Wordnet post-encoding entries must retain their source and unknown-frequency zero")
            post_autoencoding[kind] = sorted(pending, key=lambda entry: (entry.text, entry.reading))
            supplement_stats[kind] = dict(sorted(local_stats.items()), added_pairs=0, overlapping_pairs=0,
                                          sha256=file_sha256(supplement), filename=supplement.name,
                                          insertion_phase="post_autoencoding")
            continue
        elif kind == "cccedict_headwords":
            from .cccedict_headwords import read_cccedict_headwords
            # This source contains no Cantonese pronunciations. Keep its Han
            # occurrences and separate quarantine ledger outside entries and
            # supplement_review until all old generation and Wordnet finish.
            headword_reviews: list[dict] = []
            records = list(read_cccedict_headwords(supplement, stats=local_stats,
                                                  review_rows=headword_reviews))
            pending_headwords = (records, headword_reviews, supplement, dict(local_stats))
            supplement_stats[kind] = dict(sorted(local_stats.items()),
                sha256=file_sha256(supplement), filename=supplement.name,
                insertion_phase="post_autoencoding_post_wordnet")
            continue
        elif kind == "yue_wiktionary":
            from .yue_wiktionary import read_yue_wiktionary_entries
            # Parse and account now, but do not let a newly explicit reading
            # affect earlier word generation, headword encoding or source IDs.
            pages, sections, fields, reviews = [], [], [], []
            pending = list(read_yue_wiktionary_entries(supplement, stats=local_stats,
                page_rows=pages, section_rows=sections, field_rows=fields, review_rows=reviews))
            pending_yue_wiktionary = (pending, pages, sections, fields, reviews, supplement, dict(local_stats))
            supplement_stats[kind] = dict(sorted(local_stats.items()), sha256=file_sha256(supplement),
                filename=supplement.name, insertion_phase="post_autoencoding_post_wordnet_post_cccedict_headwords")
            continue
        else:
            raise ValueError(f"unsupported dictionary supplement: {kind}")
        added = 0
        overlap = 0
        for entry in imported:
            key = (entry.text, entry.reading)
            if key in entries:
                overlap += 1
                continue
            # Supplemental sources publish pronunciations, not measured
            # reading frequencies. Preserve their zero sentinel. Assigning a
            # whole-text preset count to every new reading would invent its
            # share of that token's frequency and alter autoencoder selection.
            entries[key] = entry
            origins[key] = "supplement"
            added += 1
        supplement_stats[kind] = dict(sorted(local_stats.items()), added_pairs=added,
                                       overlapping_pairs=overlap,
                                       sha256=file_sha256(supplement), filename=supplement.name)
    if not entries:
        raise ValueError("no explicit dictionary readings were imported")
    ordered = [entries[key] for key in sorted(entries)]
    syllables = sorted({base for entry in ordered for base in entry.base_reading.split()})
    input_paths = list(files) + ([frequency_path] if frequency_path.is_file() else [])
    input_paths.extend(source_dir / name for name in NOTICE_FILES if (source_dir / name).is_file())
    input_paths.extend(Path((supplements or {})[kind]) for kind in supplement_order)
    sources = [{"name": p.name, "size_bytes": p.stat().st_size, "sha256": file_sha256(p)}
               for p in input_paths]
    stats = {
        "schema_version": SCHEMA_VERSION,
        "entry_count": len(ordered),
        "syllable_count": len(syllables),
        "frequency_entry_count": len(frequencies),
        "duplicate_frequency_rows": frequency_stats["duplicate_frequency_rows"],
        "duplicate_count": counts["duplicate_count"],
        "explicit_count": counts["explicit_rows"],
        "skipped_missing_reading": counts["skipped_missing_reading"],
        "zero_weight_entries": sum(entry.weight == 0 for entry in ordered),
        "source_stats": source_stats,
        "sources": sources,
        "source_metadata": dict(source_metadata or {}),
        "supplement_stats": supplement_stats,
        "supplement_order": supplement_order,
        "post_autoencoding_supplements": sorted(post_autoencoding),
        "supplement_weight_policy": "All newly added supplement pairs retain weight 0 (frequency unknown, not a claim of nonoccurrence). Whole-text essay counts and TypeDuck percentage scores are never assigned as pronunciation-specific supplement frequencies. Original Rime weights remain unchanged.",
        "phrase_translation_policy": {
            "excluded_sources": ["unihan:kCantonese", "cccanto:dictionary", "cccanto:cedict-readings", "wordnet:cantown"],
            "description": "Rime, LSHK, words.hk and TypeDuck source-explicit one-syllable readings feed mechanical phrase encoding. Provisional Unihan and additional CC-Canto character readings remain direct-lookup-only. Existing explicit CC-Canto whole-word readings take the already_explicit path. Wordnet pairs are appended after all generation, changing neither encoder inputs nor already_explicit decisions; earlier pairs, weights, sources and origins win exact overlaps.",
        },
        "index_policy": "Compact, base and text indexes plus a covering base/weight/text/reading index reduce ranked lookup table reads.",
        "weight_policy": "Explicit numeric weights retained; missing weights use essay text frequency or 0; percentage weights multiply that frequency. No invented frequencies.",
        "reading_policy": ("Explicit source-authored readings plus audited Rime-compatible mechanical phrase encodings with origin flags; incomplete encodings quarantined."
                           if autoencode_phrases else "Explicit upstream toned readings only; text-only rows skipped. Essay supplies weights, never new entries."),
    }
    if any(kind in supplement_order for kind in ("cccanto", "cccedict_cantonese")):
        stats["combined_data_license"] = "CC-BY-SA-4.0"
        stats["combined_data_license_policy"] = (
            "Combined transformed database adaptation includes CC-Canto/CC-CEDICT Cantonese readings under "
            "CC-BY-SA-3.0; section4(b)(ii) permits a later license version with the same elements. "
            "The combined adaptation is offered under CC-BY-SA-4.0; original components retain their "
            "licenses/attribution. Application code is separate. See data/DATA_LICENSE.md and THIRD_PARTY_NOTICES.md."
        )
    if pending_headwords is not None:
        stats["phrase_translation_policy"]["excluded_sources"].append(HEADWORD_GENERATED_SOURCE)
        stats["phrase_translation_policy"]["description"] += (
            " CC-CEDICT Han headwords are encoded after Wordnet against the fixed earlier eligible "
            "single-syllable translation cohort. Generated headwords never supply new translations; "
            "no Mandarin readings or definitions enter the Cantonese data.")
        stats["combined_data_license"] = "CC-BY-SA-4.0"
        headword_license = ("CC-CEDICT headwords retain CC-BY-SA-4.0 attribution and notices; only their "
                            "written forms are used for mechanical Cantonese encoding.")
        stats["combined_data_license_policy"] = (stats.get("combined_data_license_policy", "")
                                                   + " " + headword_license).strip()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=output_path.name + ".", suffix=".tmp", dir=output_path.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_temporary: Path | None = None
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            connection.executescript("""
                PRAGMA journal_mode=DELETE;
                PRAGMA user_version=2;
                CREATE TABLE entries (
                    id INTEGER PRIMARY KEY,
                    text TEXT NOT NULL,
                    reading TEXT NOT NULL,
                    base_reading TEXT NOT NULL,
                    compact TEXT NOT NULL,
                    syllable_count INTEGER NOT NULL CHECK(syllable_count > 0),
                    weight REAL NOT NULL CHECK(weight >= 0),
                    source TEXT NOT NULL,
                    origin TEXT NOT NULL CHECK(origin IN ('explicit','supplement','generated')),
                    UNIQUE(text, reading)
                );
                CREATE TABLE syllables (base TEXT PRIMARY KEY) WITHOUT ROWID;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
                CREATE TABLE phrase_encodings (
                    source TEXT NOT NULL, line INTEGER NOT NULL, text TEXT NOT NULL,
                    status TEXT NOT NULL, codes_json TEXT NOT NULL,
                    path_count INTEGER NOT NULL, work_count INTEGER NOT NULL, reason TEXT,
                    PRIMARY KEY(source,line)
                ) WITHOUT ROWID;
                CREATE TABLE supplement_review (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL, text TEXT NOT NULL,
                    status TEXT NOT NULL, details_json TEXT NOT NULL
                );
            """)
            connection.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)", (
                (i, e.text, e.reading, e.base_reading, e.compact, e.syllable_count, e.weight, e.source, origins[(e.text,e.reading)])
                for i, e in enumerate(ordered, 1)
            ))
            connection.executemany("INSERT INTO supplement_review(source,text,status,details_json) VALUES (?,?,?,?)", (
                (row.get("source", "supplement"), row.get("text", ""), row["status"],
                 json.dumps(row, ensure_ascii=False, sort_keys=True)) for row in supplement_review
            ))
            if autoencode_phrases:
                from .autoencode import ScriptAutoencoder
                excluded_sources = set(stats["phrase_translation_policy"]["excluded_sources"])
                encoder = ScriptAutoencoder([entry for entry in ordered if entry.source not in excluded_sources])
                auto_stats: Counter = Counter()
                known_by_text: dict[str, list[str]] = {}
                for entry in ordered:
                    known_by_text.setdefault(entry.text, []).append(entry.reading)
                for path in files:
                    for line, text, weight in _unencoded_rows(path, frequencies):
                        if text in known_by_text:
                            status = "already_explicit"
                            codes = tuple(sorted(set(known_by_text[text])))
                            path_count, work_count, reason = 0, 0, None
                        else:
                            encoded = encoder.encode(text)
                            status, codes = encoded.status, encoded.codes
                            path_count, work_count, reason = encoded.path_count, encoded.work_count, encoded.reason
                        auto_stats[status] += 1
                        auto_stats["input_rows"] += 1
                        connection.execute("INSERT INTO phrase_encodings VALUES (?,?,?,?,?,?,?,?)", (
                            path.name, line, text, status, json.dumps(codes, ensure_ascii=False),
                            path_count, work_count, reason,
                        ))
                        if status in ("encoded_unique", "encoded_ambiguous"):
                            for reading in codes:
                                bases = [syllable[:-1] for syllable in reading.split()]
                                result = connection.execute(
                                    "INSERT OR IGNORE INTO entries(text,reading,base_reading,compact,syllable_count,weight,source,origin) VALUES (?,?,?,?,?,?,?,?)",
                                    (text, reading, " ".join(bases), "".join(bases), len(bases), weight,
                                     path.name + ":autoencoded", "generated"),
                                )
                                auto_stats["added_pairs"] += result.rowcount
                        if progress is not None and auto_stats["input_rows"] % 25000 == 0:
                            progress(f"Accounted for {auto_stats['input_rows']:,} phrase rows")
                stats["autoencoding"] = dict(sorted(auto_stats.items()))
                stats["autoencoding_algorithm"] = encoder.metadata()
                stats["unresolved_phrase_rows"] = sum(auto_stats[kind] for kind in ("unencodable", "truncated", "too_long"))
                # The explicit-row parser does not encode missing readings.
                # In a full build those same rows are subsequently accounted
                # for in the ledger, so do not describe them as skipped.
                for per_source in source_stats.values():
                    if "skipped_missing_reading" in per_source:
                        per_source["unencoded_input_rows"] = per_source.pop("skipped_missing_reading")
                stats["skipped_missing_reading"] = 0
            # Append-only means that even a different Wordnet whole-word
            # reading cannot suppress a previously generated alternative.
            final_syllables = set(syllables)
            for kind, pending in sorted(post_autoencoding.items()):
                added = overlap = 0
                for entry in pending:
                    result = connection.execute(
                        "INSERT OR IGNORE INTO entries(text,reading,base_reading,compact,syllable_count,weight,source,origin) VALUES (?,?,?,?,?,?,?,?)",
                        (entry.text, entry.reading, entry.base_reading, entry.compact, entry.syllable_count,
                         0.0, entry.source, "supplement"),
                    )
                    if result.rowcount:
                        added += 1
                        final_syllables.update(entry.base_reading.split())
                    else:
                        overlap += 1
                supplement_stats[kind]["added_pairs"] = added
                supplement_stats[kind]["overlapping_pairs"] = overlap
            if pending_headwords is not None:
                records, headword_reviews, headword_path, headword_source_stats = pending_headwords
                headword_stats = _append_cccedict_headwords(
                    connection, records, headword_reviews, headword_path, headword_source_stats,
                    set(stats["phrase_translation_policy"]["excluded_sources"]), progress)
                supplement_stats["cccedict_headwords"].update(headword_stats)
                stats["headword_encoding"] = headword_stats
            if pending_yue_wiktionary is not None:
                wiki_stats = _append_yue_wiktionary(connection, *pending_yue_wiktionary)
                supplement_stats["yue_wiktionary"].update(wiki_stats)
                stats["yue_wiktionary"] = wiki_stats
                # Record the future exclusion only after the fixed CC cohort
                # has been encoded, so its exact evidence remains unchanged.
                stats["phrase_translation_policy"]["excluded_sources"].append("wiktionary:yue")
                stats["phrase_translation_policy"]["description"] += (
                    " Explicit Yue Wiktionary pairs are appended last, after CC-CEDICT headword encoding, "
                    "and never supply translations or suppress earlier generated alternatives.")
                stats["combined_data_license"] = "CC-BY-SA-4.0"
                stats["combined_data_license_policy"] = (stats.get("combined_data_license_policy", "")
                    + " Yue Wiktionary explicit pronunciation fields retain contributor/revision/history attribution "
                    "and CC-BY-SA-4.0 source notices; no definitions/examples/audio are selected.").strip()
            syllables = sorted(final_syllables)
            stats["entry_count"] = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            stats["zero_weight_entries"] = connection.execute("SELECT COUNT(*) FROM entries WHERE weight=0").fetchone()[0]
            stats["syllable_count"] = len(syllables)
            stats["origin_counts"] = dict(connection.execute("SELECT origin,COUNT(*) FROM entries GROUP BY origin ORDER BY origin"))
            stats["supplement_review_count"] = len(supplement_review)
            semantic = hashlib.sha256()
            for row in connection.execute("SELECT text,reading,base_reading,compact,syllable_count,weight,source,origin FROM entries ORDER BY text,reading"):
                semantic.update((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            stats["semantic_sha256"] = semantic.hexdigest()
            connection.executemany("INSERT INTO syllables VALUES (?)", ((s,) for s in syllables))
            connection.executemany("INSERT INTO metadata VALUES (?,?)", (
                (key, json.dumps(value, ensure_ascii=False, sort_keys=True))
                for key, value in sorted(stats.items())
            ))
            connection.executescript("""
                CREATE INDEX idx_entries_compact ON entries(compact);
                CREATE INDEX idx_entries_base_reading ON entries(base_reading);
                CREATE INDEX idx_entries_base_rank ON entries(base_reading,weight DESC,text,reading);
                CREATE INDEX idx_entries_text ON entries(text);
                CREATE INDEX idx_phrase_status ON phrase_encodings(status);
                CREATE INDEX idx_phrase_text ON phrase_encodings(text);
            """)
            connection.commit()
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("generated SQLite database failed integrity check")
        finally:
            connection.close()
        manifest = dict(stats, database_sha256=file_sha256(temporary_path))
        descriptor, manifest_name = tempfile.mkstemp(prefix=manifest_path.name + ".", suffix=".tmp", dir=output_path.parent)
        manifest_temporary = Path(manifest_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        if verify_before_publish is not None:
            verify_before_publish()
        os.replace(temporary_path, output_path)
        os.replace(manifest_temporary, manifest_path)
        return manifest
    finally:
        temporary_path.unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)


def _unencoded_rows(path: Path, frequencies: Mapping[str, float]) -> Iterator[tuple[int, str, float]]:
    """Read already-validated rows with missing codes, retaining real weights."""
    body = False
    with path.open(encoding="utf-8-sig") as stream:
        for line, raw in enumerate(stream, 1):
            value = raw.rstrip("\r\n")
            if not body:
                body = value.strip() == "..."
                continue
            if not value.strip() or value.lstrip().startswith("#"):
                continue
            columns = value.split("\t")
            if len(columns) > 1 and columns[1].strip():
                continue
            text = columns[0]
            weight_string = columns[2].strip() if len(columns) > 2 else ""
            preset = frequencies.get(text, 0.0)
            weight = (_number(weight_string[:-1], path, line) * preset / 100
                      if weight_string.endswith("%") else
                      _number(weight_string, path, line) if weight_string else preset)
            if not math.isfinite(weight):
                raise _error(path, line, "resolved phrase weight overflow")
            yield line, text, weight
