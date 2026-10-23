"""Append pinned explicit Yue Wiktionary pairs to a separate candidate only."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime.yue_wiktionary import SOURCE_ID, DATA_FILE, read_yue_wiktionary_entries, verify_yue_wiktionary_snapshot, _han
from tools.build_cccedict_candidate import _preserve_baseline

BASELINES = {
    "canonical": (".local/wordnet-canonical/lexicon.sqlite3", "d835b8c4487b90ef751c8c91f467b9245c8bd54ee5be8157531dd9530ac7667b"),
    "with-cccedict": (".local/cccedict-candidate/lexicon.sqlite3", "4931e9e25898b48dc663fadb0d6554bfdc920d0046aded4f8e6e1e811657b0ad"),
}
TABLES = {"pages": "yue_wiktionary_pages", "sections": "yue_wiktionary_sections",
          "fields": "yue_wiktionary_fields", "reviews": "yue_wiktionary_review"}
_CODE = re.compile(r"[a-z]{1,12}[1-6]\Z", re.ASCII)


def _hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_candidate(baseline: Path, output: Path, entries, *, expected_baseline_sha256: str,
                    evidence: dict, page_rows: list, section_rows: list, field_rows: list,
                    review_rows: list, validate_sources=None) -> dict:
    """Preserve all old IDs/fields/ledgers; append explicit zero-frequency pairs.

    Entries/ledgers must be the complete frozen reader result, not a hand-picked
    new-pair cohort. CLI source verification and before/after guards are retained
    in evidence. No source is added to an encoder or default build here.
    """
    baseline, output = Path(baseline).resolve(), Path(output).resolve()
    manifest, review_path = output.with_suffix(".manifest.json"), output.with_suffix(".review.json")
    if (output.suffix != ".sqlite3" or baseline == output
            or output == (ROOT / "data/generated/lexicon.sqlite3").resolve()
            or any(os.path.lexists(path) for path in (output, manifest, review_path))):
        raise ValueError("Yue candidate outputs must be new, separate files")
    if _hash(baseline) != expected_baseline_sha256:
        raise ValueError("Yue candidate baseline hash differs from its requested snapshot")
    if validate_sources is not None:
        validate_sources()
    unique = {}
    for entry in entries:
        tokens = entry.reading.split()
        base = " ".join(token[:-1] for token in tokens)
        if (entry.source != SOURCE_ID or isinstance(entry.weight, bool) or not math.isfinite(entry.weight)
                or entry.weight != 0 or not tokens or not _han(entry.text) or len(entry.text) != len(tokens)
                or any(not _CODE.fullmatch(token) for token in tokens) or " ".join(tokens) != entry.reading
                or (entry.base_reading, entry.compact, entry.syllable_count) != (base, base.replace(" ", ""), len(tokens))):
            raise ValueError("Yue candidate pairs must be explicit, aligned, canonical source readings with unknown-frequency zero")
        key = entry.text, entry.reading
        if key in unique:
            raise ValueError("Yue reader must account for duplicate occurrences before pair emission")
        unique[key] = entry
    stats = evidence.get("source_stats", {})
    if (not unique or not page_rows or not section_rows or not field_rows
            or stats.get("unique_pairs") != len(unique) or stats.get("all_xml_pages") != len(page_rows)
            or stats.get("section_records") != len(section_rows) or stats.get("field_records") != len(field_rows)
            or stats.get("review_records") != len(review_rows)):
        raise ValueError("Yue candidate requires complete nonempty source/ledger accounting")
    page_ids = [row.get("page_id") for row in page_rows]
    if len(page_ids) != len(set(page_ids)) or any(not value for value in page_ids):
        raise ValueError("Yue candidate page identities must be unique and present")
    page_id_set = set(page_ids)
    source_hash = evidence.get("source_sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", source_hash, re.ASCII):
        raise ValueError("Yue candidate source digest is missing")
    for row in [*page_rows, *section_rows, *field_rows, *review_rows]:
        if row.get("source") != SOURCE_ID or row.get("source_sha256") != source_hash or row.get("page_id") not in page_id_set:
            raise ValueError("Yue candidate ledger source/page correspondence differs")
    located_pairs = {(row.get("text"), row.get("normalized_reading")) for row in field_rows
                     if row.get("scope") == "variant" and row.get("status") == "admitted_pair"}
    if located_pairs != set(unique):
        raise ValueError("Yue candidate pairs lack complete accepted-field provenance")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporaries, published = [], []

    def temporary(suffix):
        descriptor, name = tempfile.mkstemp(prefix=output.stem + ".", suffix=suffix, dir=output.parent)
        os.close(descriptor)
        path = Path(name)
        temporaries.append(path)
        return path

    temporary_db = temporary(".sqlite3.tmp")
    try:
        with closing(sqlite3.connect(baseline.as_uri() + "?mode=ro", uri=True)) as source:
            source.execute("PRAGMA query_only=ON")
            with closing(sqlite3.connect(temporary_db.as_uri(), uri=True)) as target:
                source.backup(target)
                existing_tables = {row[0] for row in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if existing_tables & set(TABLES.values()):
                    raise ValueError("Baseline already contains a Yue candidate ledger")
                before = target.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
                bases = {row[0] for row in target.execute("SELECT base FROM syllables")}
                old_metadata = dict(target.execute("SELECT key,value FROM metadata"))
                next_id = target.execute("SELECT COALESCE(MAX(id),0)+1 FROM entries").fetchone()[0]
                added, new_texts = [], set()
                for pair, entry in sorted(unique.items()):
                    if set(entry.base_reading.split()) - bases:
                        raise ValueError("Yue source reading introduces an unattested baseline base")
                    if target.execute("SELECT 1 FROM entries WHERE text=? AND reading=?", pair).fetchone():
                        continue
                    if not source.execute("SELECT 1 FROM entries WHERE text=? LIMIT 1", (entry.text,)).fetchone():
                        new_texts.add(entry.text)
                    target.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)", (
                        next_id, entry.text, entry.reading, entry.base_reading, entry.compact,
                        entry.syllable_count, 0.0, SOURCE_ID, "supplement"))
                    next_id += 1
                    added.append({"text": entry.text, "reading": entry.reading})
                after = target.execute("SELECT COUNT(*),COUNT(DISTINCT text) FROM entries").fetchone()
                if after != (before[0] + len(added), before[1] + len(new_texts)):
                    raise ValueError("Yue candidate row/text accounting differs")
                target.executescript(f"""
                    CREATE TABLE {TABLES['pages']} (page_id TEXT PRIMARY KEY,revision_id TEXT,namespace TEXT NOT NULL,
                        text TEXT NOT NULL,status TEXT NOT NULL,details_json TEXT NOT NULL) WITHOUT ROWID;
                    CREATE TABLE {TABLES['sections']} (page_id TEXT NOT NULL,section_ordinal INTEGER NOT NULL,
                        details_json TEXT NOT NULL,PRIMARY KEY(page_id,section_ordinal)) WITHOUT ROWID;
                    CREATE TABLE {TABLES['fields']} (id INTEGER PRIMARY KEY,page_id TEXT NOT NULL,scope TEXT NOT NULL,
                        status TEXT NOT NULL,details_json TEXT NOT NULL);
                    CREATE TABLE {TABLES['reviews']} (id INTEGER PRIMARY KEY,page_id TEXT NOT NULL,scope TEXT NOT NULL,
                        details_json TEXT NOT NULL);
                """)
                target.executemany(f"INSERT INTO {TABLES['pages']} VALUES (?,?,?,?,?,?)", (
                    (row["page_id"], row.get("revision_id"), row["namespace"], row["text"], row["status"], _json(row)) for row in page_rows))
                target.executemany(f"INSERT INTO {TABLES['sections']} VALUES (?,?,?)", (
                    (row["page_id"], row["language_section_ordinal"], _json(row)) for row in section_rows))
                target.executemany(f"INSERT INTO {TABLES['fields']} VALUES (?,?,?,?,?)", (
                    (number, row["page_id"], row["scope"], row["status"], _json(row)) for number, row in enumerate(field_rows, 1)))
                target.executemany(f"INSERT INTO {TABLES['reviews']} VALUES (?,?,?,?)", (
                    (number, row["page_id"], row["scope"], _json(row)) for number, row in enumerate(review_rows, 1)))
                metadata = {"schema_version": 2, "entry_count": after[0], "distinct_texts": after[1],
                    "combined_data_license": "CC-BY-SA-4.0", "candidate_only": True,
                    "candidate_scope": "Separate append-only source-explicit Yue Wiktionary extension. Earlier entries, IDs, weights, "
                        "origins and ledgers preserved; no re-encoding, encoder input change, default publication or linguistic approval.",
                    "baseline_sha256": expected_baseline_sha256, "baseline_metadata": old_metadata,
                    "yue_wiktionary_evidence": evidence}
                target.execute("DELETE FROM metadata")
                target.executemany("INSERT INTO metadata VALUES (?,?)", ((key, _json(value)) for key, value in sorted(metadata.items())))
                target.commit()
                preservation = _preserve_baseline(target, baseline)
                if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("Yue candidate database integrity failed")
        if _hash(baseline) != expected_baseline_sha256:
            raise ValueError("Yue baseline changed during candidate construction")
        after_hashes = validate_sources() if validate_sources is not None else None
        temporary_review = temporary(".review.json.tmp")
        temporary_review.write_text(json.dumps({"candidate_only": True, "linguistic_approval": False,
            "source_evidence": evidence, "complete_ledger_tables": TABLES, "rows": review_rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = {**metadata, **preservation, "database_sha256": _hash(temporary_db), "baseline_pairs": before[0],
            "baseline_texts": before[1], "accepted_source_pairs": len(unique), "overlapping_pairs": len(unique) - len(added),
            "added_pairs": len(added), "new_texts": len(new_texts), "added_entries": added,
            "source_ledger_counts": {"pages": len(page_rows), "sections": len(section_rows), "fields": len(field_rows), "reviews": len(review_rows)},
            "review_sha256": _hash(temporary_review), "inputs_after_sha256": after_hashes,
            "inputs_unchanged": bool(after_hashes) and evidence.get("inputs_before_sha256") == after_hashes,
            "source_notices": evidence.get("source_notices", []), "native_or_installed_state_changed": False}
        temporary_manifest = temporary(".manifest.json.tmp")
        temporary_manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if validate_sources is not None:
            validate_sources()
        if _hash(baseline) != expected_baseline_sha256:
            raise ValueError("Yue baseline changed before publication")
        for staging, destination in ((temporary_review, review_path), (temporary_manifest, manifest), (temporary_db, output)):
            expected = _hash(staging)
            os.link(staging, destination)
            published.append((destination, expected))
            if _hash(destination) != expected:
                raise ValueError("Yue candidate artifact differs from its staged hash")
        return report
    except BaseException:
        for destination, expected in reversed(published):
            if destination.exists() and _hash(destination) == expected:
                destination.unlink()
        raise
    finally:
        for path in temporaries:
            if path.exists():
                path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-type", choices=sorted(BASELINES), default="canonical")
    parser.add_argument("--source-lock", type=Path, default=ROOT / "data/supplements/yue-wiktionary.sources.lock.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    baseline_relative, baseline_hash = BASELINES[args.baseline_type]
    baseline = (ROOT / baseline_relative).resolve()
    output_root = (ROOT / ".local/yue-wiktionary-candidate").resolve()
    output = (args.output or output_root / args.baseline_type / "lexicon.sqlite3").resolve()
    if not output.is_relative_to(output_root) or output.suffix != ".sqlite3":
        parser.error("Output must be a new SQLite file under .local/yue-wiktionary-candidate")
    lock = json.loads(args.source_lock.read_text("utf-8"))
    directory = (ROOT / lock["local_directory"]).resolve()
    verify_yue_wiktionary_snapshot(directory, lock)
    guarded = {"baseline": baseline, "baseline_manifest": baseline.with_suffix(".manifest.json"),
        "source_lock": args.source_lock.resolve(), "parser": ROOT / "cantonese_ime/yue_wiktionary.py",
        "builder": Path(__file__).resolve(), "preservation_helper": ROOT / "tools/build_cccedict_candidate.py",
        "mappings": ROOT / "cantonese_ime/mappings.py", "engine": ROOT / "cantonese_ime/engine.py"}
    guarded.update({"source:" + row["name"]: directory / row["name"] for row in lock["files"]})
    before = {key: _hash(path) for key, path in guarded.items()}
    if before["baseline"] != baseline_hash:
        raise ValueError("Requested Yue baseline is not the pinned source snapshot")

    def verify_inputs():
        current = {key: _hash(path) for key, path in guarded.items()}
        if current != before:
            raise ValueError("Yue candidate source, implementation or baseline changed during build")
        verify_yue_wiktionary_snapshot(directory, lock)
        return current

    stats, pages, sections, fields, reviews = {}, [], [], [], []
    entries = list(read_yue_wiktionary_entries(directory / DATA_FILE, stats=stats, page_rows=pages,
        section_rows=sections, field_rows=fields, review_rows=reviews))
    evidence = {"source_sha256": before["source:" + DATA_FILE], "source_lock": str(args.source_lock.resolve()),
        "source_snapshot": lock["snapshot_id"], "source_stats": stats, "source_license": lock["license"],
        "attribution": lock["attribution"], "template_revisions": lock["template_revisions"],
        "inputs_before_sha256": before, "linguistic_approval": False,
        "source_notices": [str(directory / name) for name in ("ATTRIBUTION.md", "LICENSE-CC-BY-SA-4.0.txt",
            "wikimedia-terms.html", "yue-page-licensing-sample.html")]}
    result = build_candidate(baseline, output, entries, expected_baseline_sha256=baseline_hash,
        evidence=evidence, page_rows=pages, section_rows=sections, field_rows=fields,
        review_rows=reviews, validate_sources=verify_inputs)
    print(json.dumps({key: value for key, value in result.items()
                     if key not in {"baseline_metadata", "added_entries", "yue_wiktionary_evidence"}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
