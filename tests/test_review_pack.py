"""Snapshot-preservation tests use tiny, project-authored review fixtures."""

from __future__ import annotations

import csv
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tools import build_review_pack as review


class ReviewPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cantonese-review-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(review, "PROJECT_ROOT", self.root).start()
        self.database = self.root / "data/generated/lexicon.sqlite3"
        self.database.parent.mkdir(parents=True)
        self.mappings = self.root / "data/mappings"
        self.mappings.mkdir(parents=True)
        self.pack = self.root / "review"
        source_directory = "data/vendor/rime-cantonese/259f0e48bba840c3a2e0d117539e96937f3d89bc"
        (self.root / source_directory).mkdir(parents=True)
        (self.root / source_directory / "essay-cantonese.txt").write_text("行行\t10\n", encoding="utf-8")
        (self.root / "data/sources.lock.json").write_text(json.dumps({"local_directory": source_directory}), encoding="utf-8")
        (self.root / "data/supplements").mkdir()
        (self.root / "data/supplements/wordshk.sources.lock.json").write_text("{}", encoding="utf-8")
        (self.mappings / "lshk.sources.lock.json").write_text("{}", encoding="utf-8")
        (self.root / "cantonese_ime").mkdir()
        (self.root / "cantonese_ime/autoencode.py").write_text("fixture algorithm identity", encoding="utf-8")
        (self.mappings / "syllables.json").write_text(json.dumps({"syllables": [{"base": "haang"}, {"base": "hong"}]}), encoding="utf-8")
        (self.mappings / "spellings.json").write_text(json.dumps({
            "aliases": [{"spelling": "h", "canonical": "haang"}, {"spelling": "h", "canonical": "hong"}],
            "profile_version": "fixture", "policy": {}, "rules": [], "sources": []}), encoding="utf-8")
        (self.mappings / "build.manifest.json").write_text("{}", encoding="utf-8")
        metadata = {"schema_version": 2, "semantic_sha256": "fixture", "sources": [],
                    "source_metadata": {"supplements": {"lshk": {}, "wordshk": {}}},
                    "supplement_weight_policy": "unknown0", "autoencoding_algorithm": {}}
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.executescript("""
                CREATE TABLE entries(id INTEGER PRIMARY KEY,text TEXT,reading TEXT,weight REAL,source TEXT,origin TEXT);
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE phrase_encodings(source TEXT,line INTEGER,text TEXT,status TEXT,codes_json TEXT,path_count INTEGER,work_count INTEGER,reason TEXT);
                CREATE TABLE supplement_review(id INTEGER PRIMARY KEY,source TEXT,text TEXT,status TEXT,details_json TEXT);
            """)
            connection.executemany("INSERT INTO entries VALUES(?,?,?,?,?,?)", [
                (1, "行", "haang4", 0, "fixture", "explicit"), (2, "行", "hong4", 0, "fixture", "explicit")])
            connection.executemany("INSERT INTO metadata VALUES(?,?)", [(key, json.dumps(value)) for key, value in metadata.items()])
            connection.execute("INSERT INTO phrase_encodings VALUES(?,?,?,?,?,?,?,?)", (
                "fixture", 1, "行行", "encoded_ambiguous", json.dumps(["haang4 haang4", "haang4 hong4", "hong4 haang4", "hong4 hong4"]), 4, 10, None))
            connection.execute("INSERT INTO supplement_review VALUES(1,?,?,?,?)", (
                "typeduck:principal", "🦆", "quarantined", json.dumps({"raw_reading": "~daa2 ~dak1", "reason": "phonetic_annotation"})))

    def make_pack(self, *, legacy: bool = False) -> tuple[dict, dict]:
        tables, provenance = review.collect(self.database, self.mappings)
        hashes = review.input_hashes(self.database, self.mappings)
        inputs = hashes
        if legacy:
            reverse = {role: name for name, role in review.LEGACY_INPUT_ROLES.items()}
            inputs = {reverse[role]: value for role, value in hashes.items()}
            inputs["tools/build_review_pack.py"] = {"sha256": "0" * 64, "size_bytes": 123}
        self.pack.mkdir()
        for name, rows in tables.items():
            (self.pack / name).write_bytes(review.encode_tsv(rows, *review.TABLES[name]))
        instructions = review.readme_for(tables, provenance).encode()
        (self.pack / "README.md").write_bytes(instructions)
        manifest = {"pack_version": review.LEGACY_PACK_VERSION if legacy else review.PACK_VERSION,
                    "inputs": inputs, "tables": {name: {"generated_sha256": review.immutable_digest(rows, review.TABLES[name][0])} for name, rows in tables.items()},
                    "readme_sha256": hashlib.sha256(instructions).hexdigest()}
        self.write_manifest(manifest)
        return tables, hashes

    def write_manifest(self, manifest: dict) -> None:
        (self.pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def edit_phrase(self, **changes) -> list[dict]:
        path = self.pack / "phrases.tsv"
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            fields = reader.fieldnames
            rows = list(reader)
        rows[0].update(changes)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return rows

    def test_v1_snapshot_migrates_to_frozen_paths_and_new_validator_without_rewrite(self) -> None:
        self.make_pack(legacy=True)
        self.edit_phrase(reviewer="fixture reviewer", review_notes="Preserve this work")
        before = {path.name: path.read_bytes() for path in self.pack.iterdir()}
        frozen = self.root / "frozen"
        frozen.mkdir()
        frozen_database = frozen / "lexicon.sqlite3"
        shutil.copyfile(self.database, frozen_database)
        for filename in ("spellings.json", "syllables.json", "build.manifest.json"):
            shutil.copyfile(self.mappings / filename, frozen / filename)
        tables, _ = review.collect(frozen_database, frozen)
        hashes = review.input_hashes(frozen_database, frozen)
        result = review.validate_pack(self.pack, tables, hashes, for_regeneration=False)
        self.assertEqual(result["recorded_generator_sha256"], "0" * 64)
        self.assertNotEqual(result["recorded_generator_sha256"], result["current_validator_sha256"])
        self.assertFalse(result["authenticated_human_approval"])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.pack.iterdir()})
        with self.assertRaisesRegex(ValueError, "frozen"):
            review.validate_pack(self.pack, tables, hashes, for_regeneration=True)

    def test_generated_tsv_and_manifest_digest_tampering_cannot_defeat_fresh_derivation(self) -> None:
        tables, hashes = self.make_pack(legacy=True)
        rows = self.edit_phrase(text="changed text")
        manifest = json.loads((self.pack / "manifest.json").read_text(encoding="utf-8"))
        manifest["tables"]["phrases.tsv"]["generated_sha256"] = review.immutable_digest(rows, review.PHRASE_GENERATED)
        self.write_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "freshly derived"):
            review.validate_pack(self.pack, tables, hashes, for_regeneration=False)

    def test_unknown_and_duplicate_legacy_roles_rejected_without_opening_paths(self) -> None:
        tables, hashes = self.make_pack(legacy=True)
        path = self.pack / "manifest.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for added, message in (("C:/not-a-source/arbitrary-path", "Unknown"), ("database", "Duplicate")):
            manifest = json.loads(json.dumps(original))
            manifest["inputs"][added] = hashes["database"]
            self.write_manifest(manifest)
            with self.assertRaisesRegex(ValueError, message):
                review.validate_pack(self.pack, tables, hashes, for_regeneration=False)

    def test_v2_reviewer_or_readme_edits_block_regeneration(self) -> None:
        tables, hashes = self.make_pack()
        review.validate_pack(self.pack, tables, hashes, for_regeneration=True)
        self.edit_phrase(review_notes="Do not overwrite")
        with self.assertRaisesRegex(ValueError, "reviewer edits"):
            review.validate_pack(self.pack, tables, hashes, for_regeneration=True)
        self.edit_phrase(review_notes="")
        (self.pack / "README.md").write_text("edited instructions", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "README edits"):
            review.validate_pack(self.pack, tables, hashes, for_regeneration=True)

    def test_confirmation_claim_needs_fields_but_never_authenticates_human(self) -> None:
        tables, hashes = self.make_pack()
        self.edit_phrase(review_status="confirmed")
        with self.assertRaisesRegex(ValueError, "requires reviewer"):
            review.validate_pack(self.pack, tables, hashes, for_regeneration=False)
        self.edit_phrase(reviewer="fixture identity", reviewed_at="2026-10-22", evidence="fixture evidence")
        result = review.validate_pack(self.pack, tables, hashes, for_regeneration=False)
        self.assertFalse(result["authenticated_human_approval"])
        self.assertFalse(result["readiness_approved"])

    def test_translation_policy_excludes_provisional_unihan_codes_from_path_count(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("INSERT INTO entries VALUES(3,'行','hang6',0,'unihan:kCantonese','supplement')")
            connection.execute("INSERT INTO metadata VALUES('phrase_translation_policy',?)", (json.dumps({"excluded_sources": ["unihan:kCantonese"]}),))
        tables, provenance = review.collect(self.database, self.mappings)
        self.assertEqual(tables["phrases.tsv"][0]["full_path_count"], 4)
        self.assertNotIn("hang6", tables["phrases.tsv"][0]["qualifying_character_codes_json"])
        self.assertEqual(provenance["phrase_translation_policy"]["excluded_sources"], ["unihan:kCantonese"])

    def test_provisional_unihan_without_explicit_exclusion_is_rejected(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("INSERT INTO entries VALUES(3,'行','hang6',0,'unihan:kCantonese','supplement')")
        with self.assertRaisesRegex(ValueError, "Unihan source is missing"):
            review.collect(self.database, self.mappings)

    def test_source_exception_readme_counts_are_dynamic(self) -> None:
        tables, provenance = review.collect(self.database, self.mappings)
        text = review.readme_for(tables, provenance)
        self.assertIn("`typeduck:principal` / `quarantined`: 1.", text)
        self.assertNotIn("495", text)
        self.assertNotIn("@EXCEPTION_BREAKDOWN@", text)


if __name__ == "__main__":
    unittest.main()
