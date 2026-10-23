"""Build versioned syllable/spelling artifacts from pinned local sources."""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cantonese_ime.dictionary import DICTIONARY_FILES, file_sha256, read_entries, verify_source_files
from cantonese_ime.mappings import PROFILE_VERSION, SCHEMA_VERSION, build_mapping_artifacts, read_lshk_table
from cantonese_ime import mappings as mapping_rules
from cantonese_ime.wordshk import read_wordshk_entries, verify_wordshk_snapshot
from cantonese_ime.typeduck import read_typeduck_entries, verify_typeduck_snapshot
from cantonese_ime.unihan import read_unihan_entries, verify_unihan_snapshot
from cantonese_ime.cccanto import read_cccanto_entries, verify_cccanto_snapshot
from cantonese_ime.wordnet import read_wordnet_entries, verify_wordnet_snapshot
from cantonese_ime.cccedict_headwords import DATA_FILE as CC_HEADWORDS_FILE, read_cccedict_headwords, verify_cccedict_headwords_snapshot
from cantonese_ime.yue_wiktionary import DATA_FILE as YUE_FILE, SOURCE_ID as YUE_SOURCE_ID, read_yue_wiktionary_entries, verify_yue_wiktionary_snapshot


WORDNET_ATTESTATION_KEY = "wordnet_dictionary"
CC_HEADWORDS_METADATA_KEY = "cccedict_headwords"
YUE_ATTESTATION_KEY = "yue_wiktionary"


def collect_kfcd_yale_source() -> dict | None:
    """Source-backed spelling evidence, distinct from authored word/tone sets."""
    alternates = getattr(mapping_rules, "YALE_ASCII_ALTERNATES", None)
    if not alternates:
        return None
    from cantonese_ime.yale_sources import verify_kfcd_yale_source
    metadata = verify_kfcd_yale_source(PROJECT_ROOT, PROJECT_ROOT / "data/mappings/kfcd.sources.lock.json",
                                     alternates=alternates)
    metadata.update(verifier_file="cantonese_ime/yale_sources.py",
                    verifier_sha256=file_sha256(PROJECT_ROOT / "cantonese_ime/yale_sources.py"))
    return metadata


def _metadata_path(path: Path) -> str:
    path = path.resolve()
    return path.relative_to(PROJECT_ROOT).as_posix() if path.is_relative_to(PROJECT_ROOT) else path.as_posix()


def _verify_wordnet_collection(lock_path: Path, metadata: dict) -> None:
    """Refuse a source/parser change between collection and publication."""
    parser_path = PROJECT_ROOT / "cantonese_ime" / "wordnet.py"
    if (file_sha256(lock_path) != metadata["source_lock_sha256"]
            or file_sha256(parser_path) != metadata["parser_sha256"]):
        raise ValueError("Wordnet mapping source lock/parser changed before publication.")
    verify_wordnet_snapshot(PROJECT_ROOT / metadata["local_directory"], metadata)


def collect_wordnet_source(lock_path: Path) -> tuple[set[str], dict[str, set[str]], dict]:
    """Collect accepted Wordnet evidence before dictionary winner deduplication.

    Blank, excluded and quarantined forms stay in import accounting, not in the
    observed base/tone union. Source acceptance is not linguistic approval.
    """
    lock_path = Path(lock_path)
    lock_bytes = lock_path.read_bytes()
    lock = json.loads(lock_bytes.decode("utf-8"))
    directory = PROJECT_ROOT / lock["local_directory"]
    verify_wordnet_snapshot(directory, lock)
    parser_path = PROJECT_ROOT / "cantonese_ime" / "wordnet.py"
    metadata = dict(lock,
        source_lock_file=_metadata_path(lock_path),
        source_lock_sha256=hashlib.sha256(lock_bytes).hexdigest(),
        parser_file="cantonese_ime/wordnet.py", parser_sha256=file_sha256(parser_path),
        build_selection_status="selected_default_post_autoencoding",
        insertion_phase="post_autoencoding",
        mapping_inventory_policy=("All accepted own-Lemma/own-Form Cantonese Wordnet readings are independently parsed before dictionary winner deduplication. Blank, malformed, unknown-base, unaligned, non-Han and English sibling forms are excluded from the base/tone union and retained in import accounting. The dictionary appends new zero-weight pairs after autoencoding; existing pairs and encoding inputs are preserved. Source attestation is not independent linguistic approval."))
    bases = set()
    tones = defaultdict(set)
    stats = {}
    for entry in read_wordnet_entries(directory / lock["data_file"], stats=stats):
        bases.update(entry.base_reading.split())
        for code in entry.reading.split():
            tones[code[:-1]].add(code[-1])
    metadata["import_stats"] = stats
    _verify_wordnet_collection(lock_path, metadata)
    return bases, dict(tones), metadata


def _verify_cccedict_headword_collection(lock_path: Path, metadata: dict) -> None:
    """Retain source and parser bindings without inventing tone attestation."""
    if (file_sha256(lock_path) != metadata["source_lock_sha256"]
            or file_sha256(PROJECT_ROOT / metadata["parser_file"]) != metadata["parser_sha256"]
            or file_sha256(PROJECT_ROOT / metadata["encoder_file"]) != metadata["encoder_sha256"]):
        raise ValueError("CC-CEDICT headword mapping source lock/parser/encoder changed before publication.")
    verify_cccedict_headwords_snapshot(PROJECT_ROOT / metadata["local_directory"], metadata)


def collect_cccedict_headword_source(lock_path: Path) -> dict:
    """Parse every written-form occurrence; no source base/tone set is returned.

    CC-CEDICT is text evidence for mechanically generated Cantonese entries,
    not direct attestation of any Cantonese pronunciation. The generated bases
    are already covered by the full dictionary inventory and retained origins.
    """
    lock_path = Path(lock_path)
    payload = lock_path.read_bytes()
    lock = json.loads(payload.decode("utf-8"))
    directory = PROJECT_ROOT / lock["local_directory"]
    verify_cccedict_headwords_snapshot(directory, lock)
    metadata = dict(lock,
        source_lock_file=_metadata_path(lock_path), source_lock_sha256=hashlib.sha256(payload).hexdigest(),
        parser_file="cantonese_ime/cccedict_headwords.py",
        parser_sha256=file_sha256(PROJECT_ROOT / "cantonese_ime/cccedict_headwords.py"),
        encoder_file="cantonese_ime/autoencode.py",
        encoder_sha256=file_sha256(PROJECT_ROOT / "cantonese_ime/autoencode.py"),
        insertion_phase="post_autoencoding_post_wordnet",
        build_selection_status="selected_source_provenance",
        authored_cantonese_readings=False,
        mapping_inventory_policy="Source headwords only: no Mandarin Pinyin or definitions are imported, and no CC-CEDICT base/tone source-attestation set is created. Complete mechanical Cantonese readings of previously absent texts use the earlier eligible translator after Wordnet insertion. Generated entries retain their source/origin and are represented by dictionary coverage, not authored pronunciation evidence.")
    stats = {}
    count = sum(1 for _ in read_cccedict_headwords(directory / CC_HEADWORDS_FILE, stats=stats))
    if count != stats["accepted_occurrences"]:
        raise ValueError("CC-CEDICT mapping source-form accounting disagrees.")
    metadata["import_stats"] = stats
    _verify_cccedict_headword_collection(lock_path, metadata)
    return metadata


def _bind_cccedict_headword_dictionary(connection: sqlite3.Connection, metadata: dict) -> None:
    """Require a selected canonical build of this exact source, not any old DB."""
    from cantonese_ime.dictionary import HEADWORD_ENCODINGS_TABLE, HEADWORD_FORMS_TABLE, HEADWORD_GENERATED_SOURCE
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {HEADWORD_ENCODINGS_TABLE, HEADWORD_FORMS_TABLE} <= tables:
        raise ValueError("The selected CC-CEDICT mapping source requires its dictionary ledgers.")
    values = dict(connection.execute("SELECT key,value FROM metadata WHERE key IN ('source_metadata','headword_encoding')"))
    selected = json.loads(values.get("source_metadata", "null"))
    stats = json.loads(values.get("headword_encoding", "null"))
    if (not isinstance(selected, dict) or not isinstance(selected.get("supplements"), dict)
            or not isinstance(selected["supplements"].get("cccedict_headwords"), dict)):
        raise ValueError("Missing CC-CEDICT selected dictionary source metadata.")
    selected = selected["supplements"]["cccedict_headwords"]
    if (selected.get("source_lock_sha256") != metadata["source_lock_sha256"]
            or selected.get("parser_sha256") != metadata["parser_sha256"]
            or selected.get("encoder_sha256") != metadata["encoder_sha256"]
            or selected.get("authored_cantonese_readings") is not False
            or not isinstance(stats, dict)):
        raise ValueError("CC-CEDICT dictionary/source provenance differs from selected mapping evidence.")
    forms = connection.execute(f"SELECT COUNT(*) FROM {HEADWORD_FORMS_TABLE}").fetchone()[0]
    encodings = connection.execute(f"SELECT COUNT(*) FROM {HEADWORD_ENCODINGS_TABLE}").fetchone()[0]
    generated, bad = connection.execute("SELECT COUNT(*),COALESCE(SUM(weight != 0 OR origin != 'generated'),0) "
                                       "FROM entries WHERE source=?", (HEADWORD_GENERATED_SOURCE,)).fetchone()
    source_hash = next(item["sha256"] for item in metadata["files"] if item["name"] == CC_HEADWORDS_FILE)
    inconsistent_form = connection.execute(f"SELECT 1 FROM {HEADWORD_FORMS_TABLE} "
        "WHERE source != ? OR source_file != ? OR source_sha256 != ? LIMIT 1",
        ("cccedict:headwords", CC_HEADWORDS_FILE, source_hash)).fetchone()
    if (forms != metadata["import_stats"]["form_candidates"]
            or forms != stats.get("source_form_ledger_rows")
            or encodings != stats.get("encoding_ledger_rows")
            or generated != stats.get("new_generated_pairs") or bad or inconsistent_form):
        raise ValueError("CC-CEDICT dictionary source/encoding counts or generated provenance disagree.")
    metadata["dictionary_encoding"] = stats
    metadata["build_selection_status"] = selected.get("build_selection_status", "selected_source_provenance")


def _verify_yue_wiktionary_collection(lock_path: Path, metadata: dict) -> None:
    if (file_sha256(lock_path) != metadata["source_lock_sha256"]
            or file_sha256(PROJECT_ROOT / metadata["parser_file"]) != metadata["parser_sha256"]):
        raise ValueError("Yue Wiktionary mapping source lock/parser changed before publication.")
    verify_yue_wiktionary_snapshot(PROJECT_ROOT / metadata["local_directory"], metadata)


def _pair_digest(pairs) -> str:
    digest = hashlib.sha256()
    for pair in sorted(pairs):
        digest.update((json.dumps(pair, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    return digest.hexdigest()


def collect_yue_wiktionary_source(lock_path: Path) -> tuple[set[str], dict[str, set[str]], dict]:
    """Read all accepted raw source pairs before selected-dictionary deduplication.

    Explicit fields supply base/tone evidence, unlike text-only CC headwords.
    This source parsing is independent of winner labels, not independent human
    linguistic validation. The separate source auditor replays raw evidence.
    """
    lock_path = Path(lock_path)
    payload = lock_path.read_bytes()
    lock = json.loads(payload.decode("utf-8"))
    directory = PROJECT_ROOT / lock["local_directory"]
    verify_yue_wiktionary_snapshot(directory, lock)
    stats, bases, tones, pairs = {}, set(), defaultdict(set), set()
    for entry in read_yue_wiktionary_entries(directory / YUE_FILE, stats=stats):
        if entry.source != YUE_SOURCE_ID or entry.weight != 0:
            raise ValueError("Yue mapping readings must retain their explicit source and unknown frequency.")
        pairs.add((entry.text, entry.reading))
        bases.update(entry.base_reading.split())
        for code in entry.reading.split():
            tones[code[:-1]].add(code[-1])
    if not pairs or len(pairs) != stats["unique_pairs"]:
        raise ValueError("Yue mapping accepted-pair accounting differs.")
    metadata = dict(lock, source_lock_file=_metadata_path(lock_path),
        source_lock_sha256=hashlib.sha256(payload).hexdigest(),
        parser_file="cantonese_ime/yue_wiktionary.py", parser_sha256=file_sha256(PROJECT_ROOT / "cantonese_ime/yue_wiktionary.py"),
        insertion_phase="post_autoencoding_post_wordnet_post_cccedict_headwords",
        build_selection_status="selected_source_provenance", source_explicit_cantonese_readings=True,
        independent_linguistic_approval=False, import_stats=stats, accepted_pairs_sha256=_pair_digest(pairs),
        accepted_base_count=len(bases), accepted_toned_form_count=sum(len(value) for value in tones.values()),
        mapping_inventory_policy="All accepted own-headword literal Yue pronunciation fields are parsed from the pinned dump before dictionary winner deduplication. Unsupported structures, marked notation, non-Han/unknown/unaligned forms remain excluded. Explicit source attestation does not establish independent linguistic approval; no generated CC headword reading becomes this source's tone evidence.")
    _verify_yue_wiktionary_collection(lock_path, metadata)
    return bases, dict(tones), metadata


def _bind_yue_wiktionary_dictionary(connection: sqlite3.Connection, metadata: dict) -> None:
    from cantonese_ime.dictionary import YUE_WIKTIONARY_TABLES
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(YUE_WIKTIONARY_TABLES.values()) <= tables:
        raise ValueError("The selected Yue Wiktionary mapping source requires all four dictionary ledgers.")
    values = dict(connection.execute("SELECT key,value FROM metadata WHERE key IN ('source_metadata','yue_wiktionary')"))
    source_metadata = json.loads(values.get("source_metadata", "null"))
    stats = json.loads(values.get("yue_wiktionary", "null"))
    selected = (source_metadata.get("supplements", {}).get("yue_wiktionary")
                if isinstance(source_metadata, dict) and isinstance(source_metadata.get("supplements"), dict) else None)
    if (not isinstance(selected, dict) or not isinstance(stats, dict)
            or selected.get("source_lock_sha256") != metadata["source_lock_sha256"]
            or selected.get("parser_sha256") != metadata["parser_sha256"]
            or selected.get("source_explicit_cantonese_readings") is not True
            or selected.get("independent_linguistic_approval") is not False
            or selected.get("insertion_phase") != metadata["insertion_phase"]
            or stats.get("insertion_phase") != metadata["insertion_phase"]):
        raise ValueError("Yue Wiktionary selected dictionary/source provenance differs.")
    expected_counts = {"pages": metadata["import_stats"]["all_xml_pages"],
                       "sections": metadata["import_stats"]["section_records"],
                       "fields": metadata["import_stats"]["field_records"],
                       "reviews": metadata["import_stats"]["review_records"]}
    source_hash = next(row["sha256"] for row in metadata["files"] if row["name"] == YUE_FILE)
    pairs = set()
    for role, table in YUE_WIKTIONARY_TABLES.items():
        actual = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if actual != expected_counts[role] or actual != stats.get("ledger_counts", {}).get(role):
            raise ValueError("Yue Wiktionary dictionary ledger counts differ from the complete source.")
        for (raw,) in connection.execute(f"SELECT details_json FROM {table}"):
            row = json.loads(raw)
            if (row.get("source") != YUE_SOURCE_ID or row.get("source_file") != YUE_FILE
                    or row.get("source_sha256") != source_hash):
                raise ValueError("Yue Wiktionary dictionary ledger source correspondence differs.")
            if role == "fields" and row.get("scope") == "variant" and row.get("status") == "admitted_pair":
                pairs.add((row.get("text"), row.get("normalized_reading")))
    if (len(pairs) != metadata["import_stats"]["unique_pairs"]
            or len(pairs) != stats.get("accepted_source_pairs") or _pair_digest(pairs) != metadata["accepted_pairs_sha256"]):
        raise ValueError("Yue Wiktionary accepted-field pair set differs from the raw source.")
    if any(not connection.execute("SELECT 1 FROM entries WHERE text=? AND reading=?", pair).fetchone() for pair in pairs):
        raise ValueError("Yue Wiktionary explicit source pair is missing from the dictionary.")
    own_rows = connection.execute("SELECT text,reading,weight,origin FROM entries WHERE source=?", (YUE_SOURCE_ID,)).fetchall()
    if (len(own_rows) != stats.get("added_pairs") or stats.get("added_pairs", -1) + stats.get("overlapping_pairs", -1) != len(pairs)
            or any(weight != 0 or origin != "supplement" or (text, reading) not in pairs for text, reading, weight, origin in own_rows)):
        raise ValueError("Yue Wiktionary selected source rows must retain zero supplement provenance.")
    metadata["dictionary_selection"] = stats
    metadata["build_selection_status"] = selected.get("build_selection_status", "selected_source_provenance")


def _selected_snapshot_lock(connection: sqlite3.Connection, kind: str, explicit: Path | None,
                            default: Path, ledger_names: set[str], marker: str) -> Path | None:
    """Old databases omit new collectors; damaged/explicit selections must bind."""
    if explicit is not None:
        return Path(explicit)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # Older schema2 consumers may retain only entries. Absence is optional only
    # when nothing identifies either newly selected source; malformed existing
    # metadata still raises rather than being treated as an old database.
    values = (dict(connection.execute("SELECT key,value FROM metadata "
              "WHERE key IN ('source_metadata','supplement_stats','supplement_order',?)", (marker,)))
              if "metadata" in tables else {})
    selected = json.loads(values.get("source_metadata", "null"))
    if selected is not None and not isinstance(selected, dict):
        raise ValueError("Malformed dictionary selected-source metadata.")
    supplements = selected.get("supplements", {}) if selected else {}
    if not isinstance(supplements, dict):
        raise ValueError("Malformed dictionary supplement metadata.")
    source = supplements.get(kind)
    if source is not None and not isinstance(source, dict):
        raise ValueError("Malformed dictionary source selection.")
    stats = json.loads(values.get("supplement_stats", "{}"))
    order = json.loads(values.get("supplement_order", "[]"))
    if not isinstance(stats, dict) or not isinstance(order, list):
        raise ValueError("Malformed dictionary supplement selection markers.")
    entry_source = {"cccedict_headwords": "cccedict:headwords:autoencoded",
                    "yue_wiktionary": YUE_SOURCE_ID}[kind]
    entry_selected = False
    if "entries" in tables and "source" in {row[1] for row in connection.execute("PRAGMA table_info(entries)")}:
        entry_selected = connection.execute("SELECT 1 FROM entries WHERE source=? LIMIT 1", (entry_source,)).fetchone() is not None
    if source is not None or ledger_names & tables or marker in values or kind in stats or kind in order or entry_selected:
        if "metadata" not in tables:
            raise ValueError("Selected dictionary source requires its metadata table.")
        retained = source.get("source_lock_file") if source else None
        return PROJECT_ROOT / retained if isinstance(retained, str) and retained else default
    return None


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lshk-lock", type=Path, default=PROJECT_ROOT / "data" / "mappings" / "lshk.sources.lock.json")
    parser.add_argument("--rime-lock", type=Path, default=PROJECT_ROOT / "data" / "sources.lock.json")
    parser.add_argument("--wordshk-lock", type=Path, default=PROJECT_ROOT / "data" / "supplements" / "wordshk.sources.lock.json")
    parser.add_argument("--typeduck-lock", type=Path, default=PROJECT_ROOT / "data" / "supplements" / "typeduck.sources.lock.json")
    parser.add_argument("--unihan-lock", type=Path, default=PROJECT_ROOT / "data" / "supplements" / "unihan.sources.lock.json")
    parser.add_argument("--cccanto-lock", type=Path, default=PROJECT_ROOT / "data" / "supplements" / "cccanto.sources.lock.json")
    parser.add_argument("--wordnet-lock", type=Path, default=PROJECT_ROOT / "data" / "supplements" / "wordnet.sources.lock.json")
    parser.add_argument("--cccedict-headwords-lock", type=Path,
                        help="Retain selected text-only headword provenance; never adds direct Cantonese tone attestation")
    parser.add_argument("--yue-wiktionary-lock", type=Path,
                        help="Bind explicit Yue source evidence to the selected dictionary; selected sources are otherwise detected automatically")
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data" / "generated" / "lexicon.sqlite3")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data" / "mappings")
    args = parser.parse_args()
    lshk = json.loads(args.lshk_lock.read_text(encoding="utf-8"))
    rime = json.loads(args.rime_lock.read_text(encoding="utf-8"))
    wordshk = json.loads(args.wordshk_lock.read_text(encoding="utf-8"))
    typeduck = json.loads(args.typeduck_lock.read_text(encoding="utf-8"))
    unihan = json.loads(args.unihan_lock.read_text(encoding="utf-8"))
    cccanto = json.loads(args.cccanto_lock.read_text(encoding="utf-8"))
    lshk_dir, rime_dir = PROJECT_ROOT / lshk["local_directory"], PROJECT_ROOT / rime["local_directory"]
    wordshk_dir = PROJECT_ROOT / wordshk["local_directory"]
    typeduck_dir = PROJECT_ROOT / typeduck["local_directory"]
    unihan_dir = PROJECT_ROOT / unihan["local_directory"]
    cccanto_dir = PROJECT_ROOT / cccanto["local_directory"]
    verify_source_files(lshk_dir, lshk)
    verify_source_files(rime_dir, rime)
    verify_wordshk_snapshot(wordshk_dir, wordshk)
    verify_typeduck_snapshot(typeduck_dir, typeduck)
    verify_unihan_snapshot(unihan_dir, unihan)
    verify_cccanto_snapshot(cccanto_dir, cccanto)
    # Read the original pinned Rime table, independently of a generated database
    # that may already include LSHK supplements. This keeps the source comparison
    # meaningful and reproducible when additional dictionaries are integrated.
    rime_bases = set()
    rime_tones = defaultdict(set)
    for filename in DICTIONARY_FILES:
        for entry in read_entries(rime_dir / filename):
            rime_bases.update(entry.base_reading.split())
            for code in entry.reading.split():
                rime_tones[code[:-1]].add(code[-1])
    wordshk_bases = set()
    wordshk_tones = defaultdict(set)
    wordshk_stats = {}
    for entry in read_wordshk_entries(wordshk_dir / "wordslist.json", stats=wordshk_stats):
        wordshk_bases.update(entry.base_reading.split())
        for code in entry.reading.split():
            wordshk_tones[code[:-1]].add(code[-1])
    typeduck_bases = set()
    typeduck_tones = defaultdict(set)
    typeduck_stats = {}
    for entry in read_typeduck_entries(typeduck_dir / "jyut6ping3.dict.yaml", stats=typeduck_stats):
        typeduck_bases.update(entry.base_reading.split())
        for code in entry.reading.split():
            typeduck_tones[code[:-1]].add(code[-1])
    unihan_bases = set()
    unihan_tones = defaultdict(set)
    unihan_stats = {}
    for entry in read_unihan_entries(unihan_dir / "Unihan_Readings.txt", stats=unihan_stats):
        unihan_bases.update(entry.base_reading.split())
        for code in entry.reading.split():
            unihan_tones[code[:-1]].add(code[-1])
    cccanto_bases, cccanto_tones, cccanto_stats = {}, {}, {}
    for source, filename in (
        ("cccanto_dictionary", "cccanto-webdist.txt"),
        ("cccanto_cedict_readings", "cccedict-canto-readings-150923.txt"),
    ):
        cccanto_bases[source] = set()
        cccanto_tones[source] = defaultdict(set)
        cccanto_stats[source] = {}
        for entry in read_cccanto_entries(cccanto_dir / filename, stats=cccanto_stats[source]):
            cccanto_bases[source].update(entry.base_reading.split())
            for code in entry.reading.split():
                cccanto_tones[source][code[:-1]].add(code[-1])
    wordnet_bases, wordnet_tones, wordnet_metadata = collect_wordnet_source(args.wordnet_lock)
    headword_metadata = None
    yue_metadata = None
    yue_bases, yue_tones = set(), {}
    database_path = args.database.resolve()
    if not database_path.is_file():
        raise ValueError("Build the full multi-source dictionary before building mappings.")
    database_sha256 = file_sha256(database_path)
    dictionary_bases = set()
    retained_sources = defaultdict(set)
    retained_origins = defaultdict(set)
    with closing(sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True)) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(entries)")}
        if not {"base_reading", "source", "origin"}.issubset(columns):
            raise ValueError("Mapping coverage requires dictionary schema2 with source/origin columns.")
        database_schema = connection.execute("PRAGMA user_version").fetchone()[0]
        from cantonese_ime.dictionary import HEADWORD_ENCODINGS_TABLE, HEADWORD_FORMS_TABLE, YUE_WIKTIONARY_TABLES
        headword_lock = _selected_snapshot_lock(
            connection, "cccedict_headwords", args.cccedict_headwords_lock,
            PROJECT_ROOT / "data/supplements/cccedict-headwords.sources.lock.json",
            {HEADWORD_ENCODINGS_TABLE, HEADWORD_FORMS_TABLE}, "headword_encoding")
        yue_lock = _selected_snapshot_lock(
            connection, "yue_wiktionary", args.yue_wiktionary_lock,
            PROJECT_ROOT / "data/supplements/yue-wiktionary.sources.lock.json",
            set(YUE_WIKTIONARY_TABLES.values()), "yue_wiktionary")
        if headword_lock is not None:
            headword_metadata = collect_cccedict_headword_source(headword_lock)
            _bind_cccedict_headword_dictionary(connection, headword_metadata)
        if yue_lock is not None:
            yue_bases, yue_tones, yue_metadata = collect_yue_wiktionary_source(yue_lock)
            _bind_yue_wiktionary_dictionary(connection, yue_metadata)
        for reading, source, origin in connection.execute("SELECT DISTINCT base_reading,source,origin FROM entries"):
            for base in reading.split():
                dictionary_bases.add(base)
                retained_sources[base].add(source)
                retained_origins[base].add(origin)
    metadata = {
        "lshk": lshk,
        "rime": {key: rime[key] for key in ("repository", "commit", "license", "attribution", "files")},
        "wordshk": wordshk,
        "wordshk_import_stats": wordshk_stats,
        "typeduck": typeduck, "typeduck_import_stats": typeduck_stats,
        "unihan": unihan, "unihan_import_stats": unihan_stats,
        "cccanto": cccanto, "cccanto_import_stats": cccanto_stats,
        WORDNET_ATTESTATION_KEY: wordnet_metadata,
        "database": {"path": database_path.relative_to(PROJECT_ROOT).as_posix() if database_path.is_relative_to(PROJECT_ROOT) else database_path.as_posix(), "schema_version": database_schema, "sha256": database_sha256},
        "dictionary_inventory_policy": "Full generated dictionary coverage, with independently parsed original Rime/LSHK/accepted words.hk/TypeDuck/provisional Unihan/CC-Canto/CC-CEDICT Cantonese/accepted Cantonese Wordnet attestations preserved before winner deduplication. Wordnet is appended after autoencoding without supplying encoder inputs or replacing existing pairs. Retained database source/origin labels describe selected output rows only. Provisional character evidence is distinct from authored whole-word judgement; source acceptance is not independent linguistic approval.",
        "parser_sha256": {name: file_sha256(PROJECT_ROOT / "cantonese_ime" / (name + ".py")) for name in ("dictionary", "mappings", "wordshk", "typeduck", "unihan", "cccanto", "wordnet")},
    }
    if headword_metadata is not None:
        metadata[CC_HEADWORDS_METADATA_KEY] = headword_metadata
        metadata["parser_sha256"]["cccedict_headwords"] = headword_metadata["parser_sha256"]
        metadata["dictionary_inventory_policy"] += (
            " Selected CC-CEDICT contributes Han headwords only; its mechanically generated Cantonese "
            "readings are represented as dictionary coverage and generated provenance, never as direct source tone attestations.")
    if yue_metadata is not None:
        metadata[YUE_ATTESTATION_KEY] = yue_metadata
        metadata["parser_sha256"]["yue_wiktionary"] = yue_metadata["parser_sha256"]
        metadata["dictionary_inventory_policy"] += (
            " Selected Yue Wiktionary contributes independently parsed explicit own-headword readings before winner deduplication; "
            "it is appended after CC-CEDICT headword encoding and never supplies that encoder's translations.")
    kfcd_metadata = collect_kfcd_yale_source()
    if kfcd_metadata is not None:
        metadata["yale_kfcd_numeric"] = kfcd_metadata
        metadata["parser_sha256"]["yale_sources"] = kfcd_metadata["verifier_sha256"]
    inventory, mappings = build_mapping_artifacts(
        read_lshk_table(lshk_dir / "list.tsv"), dictionary_bases, source_metadata=metadata,
        source_inventories={"rime_dictionary": rime_bases, "wordshk_wordlist": wordshk_bases, "typeduck_principal": typeduck_bases, "unihan_kcantonese": unihan_bases, **cccanto_bases, WORDNET_ATTESTATION_KEY: wordnet_bases, **({YUE_ATTESTATION_KEY: yue_bases} if yue_metadata is not None else {})},
        source_tones={"rime_dictionary": rime_tones, "wordshk_wordlist": wordshk_tones, "typeduck_principal": typeduck_tones, "unihan_kcantonese": unihan_tones, **cccanto_tones, WORDNET_ATTESTATION_KEY: wordnet_tones, **({YUE_ATTESTATION_KEY: yue_tones} if yue_metadata is not None else {})},
        retained_sources=retained_sources, retained_origins=retained_origins,
    )
    _verify_wordnet_collection(args.wordnet_lock, wordnet_metadata)
    if headword_metadata is not None:
        _verify_cccedict_headword_collection(headword_lock, headword_metadata)
    if yue_metadata is not None:
        _verify_yue_wiktionary_collection(yue_lock, yue_metadata)
    if file_sha256(database_path) != database_sha256:
        raise ValueError("Selected dictionary changed before mapping publication.")
    if collect_kfcd_yale_source() != kfcd_metadata:
        raise ValueError("KFCD spelling source/verifier changed before mapping publication.")
    outputs = {"syllables.json": inventory, "spellings.json": mappings}
    for filename, value in outputs.items():
        write_json(args.output_dir / filename, value)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "profile_version": PROFILE_VERSION,
        "inventory_counts": inventory["counts"],
        "mapping_counts": mappings["counts"],
        "files": {name: hashlib.sha256((args.output_dir / name).read_bytes()).hexdigest() for name in outputs},
        "module_sha256": hashlib.sha256((PROJECT_ROOT / "cantonese_ime" / "mappings.py").read_bytes()).hexdigest(),
        "build_script_sha256": file_sha256(Path(__file__).resolve()),
    }
    write_json(args.output_dir / "build.manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"Mapping build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
