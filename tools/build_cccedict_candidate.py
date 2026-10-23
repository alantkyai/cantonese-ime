"""Build a separate, append-only headword/autoencoding experiment.

CC-CEDICT supplies written forms only. Cantonese codes come exclusively from
the frozen baseline's permitted source-explicit one-syllable translations.
This tool never publishes a canonical dictionary or changes the installed IME.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime.autoencode import ScriptAutoencoder
from cantonese_ime.cccedict_headwords import (
    DATA_FILE, SOURCE_ID, read_cccedict_headwords, verify_cccedict_headwords_snapshot,
)

BASELINE_SHA256 = "d835b8c4487b90ef751c8c91f467b9245c8bd54ee5be8157531dd9530ac7667b"
GENERATED_SOURCE = "cccedict:headwords:autoencoded"
FIELDS = ("id", "text", "reading", "base_reading", "compact", "syllable_count", "weight", "source", "origin")
FORMS_TABLE = "cccedict_headword_forms"
ENCODINGS_TABLE = "cccedict_headword_encodings"
_CODE = re.compile(r"[a-z]+[1-6]\Z", re.ASCII)
_COMPLETE = frozenset({"encoded_unique", "encoded_ambiguous"})
_INCOMPLETE = frozenset({"truncated", "unencodable", "too_long"})


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _preserve_baseline(target: sqlite3.Connection, baseline: Path) -> dict:
    """Compare all nine old entry fields by ID, and every old nonmetadata table."""
    target.execute("ATTACH DATABASE ? AS baseline_ro", (baseline.as_uri() + "?mode=ro",))
    try:
        equal_fields = " AND ".join(f"old.{_identifier(name)} IS new.{_identifier(name)}" for name in FIELDS)
        bad = target.execute("SELECT old.id FROM baseline_ro.entries old LEFT JOIN main.entries new ON old.id=new.id "
                             f"WHERE NOT ({equal_fields}) LIMIT 1").fetchone()
        if bad:
            raise ValueError("Candidate changed an earlier entry field or ID")
        protected = {}
        tables = target.execute("SELECT name,sql FROM baseline_ro.sqlite_master "
                                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        for name, schema in tables:
            if name in {"entries", "metadata"}:
                continue
            quoted = _identifier(name)
            actual_schema = target.execute("SELECT sql FROM main.sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
            if actual_schema != (schema,):
                raise ValueError("Candidate changed an earlier table schema")
            old_count = target.execute(f"SELECT COUNT(*) FROM baseline_ro.{quoted}").fetchone()[0]
            new_count = target.execute(f"SELECT COUNT(*) FROM main.{quoted}").fetchone()[0]
            if old_count != new_count:
                raise ValueError("Candidate changed an earlier ledger/table count")
            columns = target.execute(f"PRAGMA baseline_ro.table_info({quoted})").fetchall()
            primary = sorted((column for column in columns if column[5]), key=lambda item: item[5])
            if primary:
                join = " AND ".join(f"old.{_identifier(column[1])} IS new.{_identifier(column[1])}" for column in primary)
                equality = " AND ".join(f"old.{_identifier(column[1])} IS new.{_identifier(column[1])}" for column in columns)
                changed = target.execute(f"SELECT 1 FROM baseline_ro.{quoted} old LEFT JOIN main.{quoted} new ON {join} "
                                         f"WHERE NOT ({equality}) LIMIT 1").fetchone()
            else:
                changed = target.execute(f"SELECT * FROM baseline_ro.{quoted} EXCEPT SELECT * FROM main.{quoted} LIMIT 1").fetchone()
                changed = changed or target.execute(f"SELECT * FROM main.{quoted} EXCEPT SELECT * FROM baseline_ro.{quoted} LIMIT 1").fetchone()
            if changed:
                raise ValueError("Candidate changed earlier ledger/table rows")
            protected[name] = old_count
        return {"all_nine_entry_fields_preserved": True, "earlier_tables_preserved": protected}
    finally:
        target.execute("DETACH DATABASE baseline_ro")


def build_candidate(
    baseline: Path,
    output: Path,
    *,
    source_lock: Path,
    expected_baseline_sha256: str = BASELINE_SHA256,
    baseline_manifest: Path | None = None,
    source_directory: Path | None = None,
    validate_inputs=None,
    progress=None,
) -> dict:
    """Append only complete encodings of absent Han texts to a fresh candidate.

    Existing texts never receive inferred variants. Incomplete results retain
    their reached codes in a separate ledger, without importing any partial
    alternatives. Tests may supply a different explicitly hashed mini baseline;
    the CLI is pinned to BASELINE_SHA256. No approval or frequency is inferred.
    """
    baseline, output, source_lock = Path(baseline).resolve(), Path(output).resolve(), Path(source_lock).resolve()
    manifest_path = output.with_suffix(".manifest.json")
    review_path = output.with_suffix(".review.json")
    outputs = (output, manifest_path, review_path)
    baseline_manifest = (Path(baseline_manifest) if baseline_manifest is not None else baseline.with_suffix(".manifest.json")).resolve()
    if (output.suffix != ".sqlite3" or baseline == output
            or output == (ROOT / "data/generated/lexicon.sqlite3").resolve()
            or any(os.path.lexists(path) for path in outputs)):
        raise ValueError("Candidate outputs must be new, separate SQLite/evidence files")
    if _hash(baseline) != expected_baseline_sha256:
        raise ValueError("Candidate baseline hash differs from the requested frozen snapshot")
    lock = json.loads(source_lock.read_text("utf-8"))
    directory = (Path(source_directory) if source_directory is not None else ROOT / lock["local_directory"]).resolve()
    implementation = {"parser": ROOT / "cantonese_ime/cccedict_headwords.py",
                      "builder": Path(__file__).resolve(), "autoencoder": ROOT / "cantonese_ime/autoencode.py",
                      "mappings": ROOT / "cantonese_ime/mappings.py"}
    guarded = {"baseline": baseline, "baseline_manifest": baseline_manifest, "source_lock": source_lock, **implementation}
    verify_cccedict_headwords_snapshot(directory, lock)
    guarded.update({"source:" + item["name"]: directory / item["name"] for item in lock["files"]})
    before_hashes = {key: _hash(path) for key, path in guarded.items()}
    if before_hashes["baseline"] != expected_baseline_sha256 or set(outputs) & set(guarded.values()):
        raise ValueError("Candidate inputs/outputs overlap or baseline changed")

    def verify_current_inputs():
        if validate_inputs is not None:
            validate_inputs()
        current = {key: _hash(path) for key, path in guarded.items()}
        if current != before_hashes:
            raise ValueError("Candidate source, implementation or baseline changed during construction")
        verify_cccedict_headwords_snapshot(directory, lock)
        return current

    verify_current_inputs()
    original_manifest = json.loads(baseline_manifest.read_text("utf-8"))
    policy = original_manifest.get("phrase_translation_policy")
    if (original_manifest.get("database_sha256") != expected_baseline_sha256
            or not isinstance(policy, dict) or not isinstance(policy.get("excluded_sources"), list)
            or any(not isinstance(item, str) or not item for item in policy["excluded_sources"])):
        raise ValueError("Frozen baseline manifest or encoder-exclusion policy is invalid")
    excluded = set(policy["excluded_sources"])
    source_stats, source_reviews = {}, []
    records = list(read_cccedict_headwords(directory / DATA_FILE, stats=source_stats, review_rows=source_reviews))
    if not records or source_stats["accepted_occurrences"] != len(records):
        raise ValueError("No nonempty accounted Han headword cohort")
    with closing(sqlite3.connect(baseline.as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("PRAGMA query_only=ON")
        columns = tuple(row[1] for row in source.execute("PRAGMA table_info(entries)"))
        if columns != FIELDS:
            raise ValueError("Unexpected frozen baseline entry schema")
        old_metadata = dict(source.execute("SELECT key,value FROM metadata"))
        if json.loads(old_metadata.get("phrase_translation_policy", "null")) != policy:
            raise ValueError("Baseline metadata and manifest disagree on translator exclusions")
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if {FORMS_TABLE, ENCODINGS_TABLE} & tables:
            raise ValueError("Baseline already contains a headword-candidate ledger")
        baseline_pairs, baseline_texts = source.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
        if original_manifest.get("entry_count") != baseline_pairs:
            raise ValueError("Baseline manifest entry accounting disagrees")
        existing_texts = {row[0] for row in source.execute("SELECT DISTINCT text FROM entries")}
        bases = {row[0] for row in source.execute("SELECT base FROM syllables")}
        translations = [row[:3] for row in source.execute(
            "SELECT text,reading,weight,source FROM entries WHERE origin IN ('explicit','supplement') "
            "AND syllable_count=1 ORDER BY text,reading") if row[3] not in excluded]
        if not bases or not translations:
            raise ValueError("Frozen baseline has no eligible Cantonese translations")
        encoder = ScriptAutoencoder(translations)
        references = defaultdict(list)
        for record in records:
            if record.text not in existing_texts:
                references[record.text].append({"line": record.line, "script": record.script,
                                                "raw_line_sha256": record.raw_line_sha256})
        if not references:
            raise ValueError("No absent Han headwords to measure")
        encoded, added = {}, []
        status_counts = Counter()
        for number, text in enumerate(sorted(references), 1):
            result = encoder.encode(text)
            if result.text != text or result.status not in _COMPLETE | _INCOMPLETE:
                raise ValueError("Unexpected Cantonese autoencoder result")
            if result.status in _COMPLETE:
                if not result.codes or len(result.codes) != len(set(result.codes)):
                    raise ValueError("Complete encoding must have nonempty, deduplicated codes")
                if (result.status == "encoded_unique") != (len(result.codes) == 1):
                    raise ValueError("Complete encoding ambiguity label disagrees with codes")
                for reading in sorted(result.codes):
                    tokens = reading.split()
                    if (" ".join(tokens) != reading or not tokens
                            or any(not _CODE.fullmatch(token) or token[:-1] not in bases for token in tokens)):
                        raise ValueError("Generated code is not canonical in the frozen baseline")
                    added.append({"text": text, "reading": reading})
            encoded[text] = result.to_dict()
            status_counts[result.status] += 1
            if progress is not None and (number % 2500 == 0 or number == len(references)):
                progress({"encoded_missing_texts": number, "missing_texts": len(references)})
        if not added:
            raise ValueError("No complete headword encoding can be measured")
        complete_texts = status_counts["encoded_unique"] + status_counts["encoded_ambiguous"]
        source_hash = before_hashes["source:" + DATA_FILE]
        source_notices = [str(directory / name) for name in
                          ("ATTRIBUTION.md", "LICENSE-CC-BY-SA-4.0.txt", "download-page.html", DATA_FILE)]
        evidence = {"candidate_only": True, "linguistic_approval": False, "source_id": SOURCE_ID,
                    "source_lock": str(source_lock), "source_directory": str(directory),
                    "snapshot_id": lock["snapshot_id"], "source_stats": source_stats,
                    "source_notices": source_notices, "source_release_header": lock["source_release_header"],
                    "source_license": lock["license"], "attribution": lock.get("attribution"),
                    "encoder": encoder.metadata(), "excluded_encoder_sources": sorted(excluded),
                    "translation_rows": len(translations), "encoding_counts": dict(sorted(status_counts.items())),
                    "missing_texts": len(references), "complete_new_texts": complete_texts,
                    "new_generated_pairs": len(added), "already_present_source_texts": source_stats["unique_han_forms"] - len(references),
                    "source_reading_policy": "Only source Han written forms; Mandarin Pinyin and definitions never supply codes. "
                        "New rows are generated, zero unknown frequency, and never become translator inputs."}
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_paths, published = [], []

        def temporary_path(suffix):
            descriptor, name = tempfile.mkstemp(prefix=output.stem + ".", suffix=suffix, dir=output.parent)
            os.close(descriptor)
            path = Path(name)
            temporary_paths.append(path)
            return path

        temporary_db = temporary_path(".sqlite3.tmp")
        try:
            with closing(sqlite3.connect(temporary_db.as_uri(), uri=True)) as target:
                source.backup(target)
                target.executescript(f"""
                    CREATE TABLE {FORMS_TABLE} (
                        line INTEGER NOT NULL,script TEXT NOT NULL,text TEXT NOT NULL,
                        raw_line_sha256 TEXT NOT NULL,source TEXT NOT NULL,source_file TEXT NOT NULL,
                        source_sha256 TEXT NOT NULL,status TEXT NOT NULL,reason TEXT,
                        PRIMARY KEY(line,script)) WITHOUT ROWID;
                    CREATE TABLE {ENCODINGS_TABLE} (
                        text TEXT PRIMARY KEY,status TEXT NOT NULL,codes_json TEXT NOT NULL,
                        path_count INTEGER NOT NULL,work_count INTEGER NOT NULL,reason TEXT,
                        source_refs_json TEXT NOT NULL) WITHOUT ROWID;
                """)
                target.executemany(f"INSERT INTO {ENCODINGS_TABLE} VALUES (?,?,?,?,?,?,?)", (
                    (text, value["status"], _json(value["codes"]), value["path_count"], value["work_count"],
                     value["reason"], _json(references[text])) for text, value in sorted(encoded.items())))
                form_statuses = Counter()

                def form_rows():
                    for record in records:
                        status = "already_present" if record.text in existing_texts else encoded[record.text]["status"]
                        reason = None if status == "already_present" else encoded[record.text]["reason"]
                        form_statuses[status] += 1
                        yield (record.line, record.script, record.text, record.raw_line_sha256, SOURCE_ID,
                               DATA_FILE, source_hash, status, reason)
                    for row in source_reviews:
                        form_statuses["source_quarantined"] += 1
                        yield (row["line"], row["script"], row["text"], row["raw_line_sha256"], SOURCE_ID,
                               DATA_FILE, source_hash, "source_quarantined", row["reason"])

                target.executemany(f"INSERT INTO {FORMS_TABLE} VALUES (?,?,?,?,?,?,?,?,?)", form_rows())
                next_id = source.execute("SELECT COALESCE(MAX(id),0)+1 FROM entries").fetchone()[0]
                for number, pair in enumerate(added, next_id):
                    tokens = pair["reading"].split()
                    base = " ".join(token[:-1] for token in tokens)
                    target.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)", (
                        number, pair["text"], pair["reading"], base, base.replace(" ", ""), len(tokens),
                        0.0, GENERATED_SOURCE, "generated"))
                final_pairs, final_texts = target.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
                if (final_pairs, final_texts) != (baseline_pairs + len(added), baseline_texts + complete_texts):
                    raise ValueError("Candidate append row/text accounting disagrees")
                if (sum(form_statuses.values()) != source_stats["form_candidates"]
                        or target.execute(f"SELECT COUNT(*) FROM {ENCODINGS_TABLE}").fetchone()[0] != len(references)):
                    raise ValueError("Candidate source/encoding ledger is incomplete")
                evidence["form_status_counts"] = dict(sorted(form_statuses.items()))
                metadata = {"schema_version": 2, "entry_count": final_pairs, "distinct_texts": final_texts,
                            "combined_data_license": "CC-BY-SA-4.0", "candidate_only": True,
                            "candidate_scope": "Append-only CC-CEDICT Han headwords with complete mechanical Cantonese encodings. "
                                "Existing texts/entries/IDs/ledgers remain unchanged; not a fresh canonical build or linguistic approval.",
                            "baseline_sha256": before_hashes["baseline"], "baseline_metadata": old_metadata,
                            "headword_evidence": evidence}
                target.execute("DELETE FROM metadata")
                target.executemany("INSERT INTO metadata VALUES (?,?)", ((key, _json(value)) for key, value in sorted(metadata.items())))
                target.commit()
                preservation = _preserve_baseline(target, baseline)
                if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("Candidate database integrity check failed")
            after_hashes = verify_current_inputs()
            review = {"candidate_only": True, "linguistic_approval": False, "source_evidence": evidence,
                      "source_quarantines": source_reviews,
                      "incomplete_encodings": [dict(value, source_references=references[text])
                                               for text, value in sorted(encoded.items()) if value["status"] not in _COMPLETE],
                      "full_occurrence_ledger": FORMS_TABLE, "full_encoding_ledger": ENCODINGS_TABLE}
            temporary_review = temporary_path(".review.json.tmp")
            temporary_review.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report = {**metadata, **preservation, "database_sha256": _hash(temporary_db),
                      "baseline_pairs": baseline_pairs, "baseline_texts": baseline_texts,
                      "added_pairs": len(added), "new_texts": complete_texts, "added_entries": added,
                      "source_form_ledger_rows": sum(form_statuses.values()), "encoding_ledger_rows": len(references),
                      "review_sha256": _hash(temporary_review), "inputs_before_sha256": before_hashes,
                      "inputs_after_sha256": after_hashes, "inputs_unchanged": before_hashes == after_hashes,
                      "data_notice": ["data/DATA_LICENSE.md", "data/THIRD_PARTY_NOTICES.md", *source_notices],
                      "native_or_installed_state_changed": False}
            temporary_manifest = temporary_path(".manifest.json.tmp")
            temporary_manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if (json.loads(temporary_manifest.read_text("utf-8"))["database_sha256"] != _hash(temporary_db)
                    or json.loads(temporary_manifest.read_text("utf-8"))["review_sha256"] != _hash(temporary_review)):
                raise ValueError("Candidate evidence does not match the staged artifact hashes")
            verify_current_inputs()
            # Hard links create each destination exclusively, including on
            # Windows; unlike replace(), an unexpected existing file survives.
            for staging, destination in ((temporary_review, review_path), (temporary_manifest, manifest_path), (temporary_db, output)):
                expected_hash = _hash(staging)
                os.link(staging, destination)
                published.append((destination, expected_hash))
                if _hash(destination) != expected_hash:
                    raise ValueError("Published candidate artifact differs from its staged hash")
            return report
        except BaseException:
            for destination, expected_hash in reversed(published):
                if destination.exists() and _hash(destination) == expected_hash:
                    destination.unlink()
            raise
        finally:
            for path in temporary_paths:
                if path.exists():
                    path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / ".local/wordnet-canonical/lexicon.sqlite3")
    parser.add_argument("--baseline-manifest", type=Path)
    parser.add_argument("--source-lock", type=Path, default=ROOT / "data/supplements/cccedict-headwords.sources.lock.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/cccedict-candidate/lexicon.sqlite3")
    args = parser.parse_args()
    try:
        relative = args.output.resolve().relative_to((ROOT / ".local/cccedict-candidate").resolve())
        if not relative.parts or args.output.suffix != ".sqlite3":
            raise ValueError
    except ValueError:
        parser.error("Output must be a new SQLite file under .local/cccedict-candidate")
    report = build_candidate(args.baseline, args.output, source_lock=args.source_lock,
                             baseline_manifest=args.baseline_manifest,
                             progress=lambda value: print(json.dumps(value), flush=True))
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {"baseline_metadata", "added_entries", "headword_evidence"}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
