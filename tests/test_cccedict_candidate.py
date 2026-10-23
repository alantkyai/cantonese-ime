"""The candidate cannot overwrite old words or promote partial encodings."""
from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime import cccedict_headwords as reader
from tools import build_cccedict_candidate as builder


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CcCedictCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cccedict-candidate-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline = self.root / "baseline.sqlite3"
        self.output = self.root / "candidate.sqlite3"
        self.vendor = self.root / "vendor"
        self.vendor.mkdir()
        self.lock_path = self.root / "source.lock.json"
        self.policy = {"excluded_sources": ["unihan:kCantonese"], "description": "provisional char readings excluded"}
        with closing(sqlite3.connect(self.baseline)) as db:
            db.executescript("""
                CREATE TABLE entries(id INTEGER PRIMARY KEY,text TEXT,reading TEXT,base_reading TEXT,
                    compact TEXT,syllable_count INTEGER,weight REAL,source TEXT,origin TEXT,UNIQUE(text,reading));
                CREATE INDEX bases ON entries(base_reading);
                CREATE TABLE syllables(base TEXT PRIMARY KEY);
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE phrase_encodings(source TEXT,line INTEGER,text TEXT,status TEXT,codes_json TEXT,
                    path_count INTEGER,work_count INTEGER,reason TEXT,PRIMARY KEY(source,line));
                CREATE TABLE supplement_review(id INTEGER PRIMARY KEY,source TEXT,text TEXT,status TEXT,details_json TEXT);
            """)
            pairs = [(1, "你", "nei5", 91, "earlier", "explicit"),
                     (4, "好", "hou2", 82, "earlier", "explicit"),
                     (8, "你好", "nei4 hou3", 73, "earlier", "explicit"),
                     (12, "甲", "gaap3", 64, "earlier", "explicit"),
                     (13, "甲", "gaap6", 64, "earlier", "explicit"),
                     (17, "缺", "kyut3", 0, "unihan:kCantonese", "supplement")]
            for identity, text, reading, weight, source, origin in pairs:
                tokens = reading.split()
                base = " ".join(token[:-1] for token in tokens)
                db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)", (
                    identity, text, reading, base, base.replace(" ", ""), len(tokens), weight, source, origin))
            db.executemany("INSERT INTO syllables VALUES (?)", [(base,) for base in ("nei", "hou", "gaap", "kyut")])
            db.executemany("INSERT INTO metadata VALUES (?,?)", [("entry_count", "6"),
                ("phrase_translation_policy", json.dumps(self.policy)), ("earlier_key", '"retain"')])
            db.execute("INSERT INTO phrase_encodings VALUES ('earlier',9,'甲甲','encoded_ambiguous','[\"gaap3 gaap3\"]',1,3,NULL)")
            db.execute("INSERT INTO supplement_review VALUES (7,'earlier','甲','pending','{\"keep\":true}')")
            db.commit()
        self.sha = digest(self.baseline)
        self.baseline_manifest = self.baseline.with_suffix(".manifest.json")
        self.baseline_manifest.write_text(json.dumps({"database_sha256": self.sha, "entry_count": 6,
            "phrase_translation_policy": self.policy}), encoding="utf-8")
        self.write_source([
            "你好 你好 [THIS IS NOT CANTONESE] /ignored Mandarin definition/",
            "你好好 你好好 [wrong3 wrong2] /never a source reading/",
            "缺好 缺好 [kyut3 hou2] /excluded provisional component/",
            "甲甲甲甲甲 甲甲甲甲甲 [a1] /exactly 32 paths, not importable/",
            "ABC 你好好 [foreign] /foreign headword gets a field ledger/",
        ])

    def write_source(self, rows):
        data = ("# CC-CEDICT\n# Published by MDBG\n# " + reader.LICENSE_DECLARATION + "\n# " + reader.LICENSE_URL + "\n"
                + "#! version=1\n#! format=ts\n#! charset=UTF-8\n#! publisher=MDBG\n"
                + f"#! entries={len(rows)}\n#! license={reader.LICENSE_URL}\n#! date=2026-10-21T05:46:59Z\n"
                + "\n".join(rows) + "\n").encode()
        payloads = {reader.DATA_FILE: data, reader.ARCHIVE_FILE: gzip.compress(data, mtime=0),
            "download-page.html": (reader.LICENSE_DECLARATION + reader.LICENSE_URL).encode(),
            "LICENSE-CC-BY-SA-4.0.txt": (reader.Path(__file__).resolve().parents[1]
                / "data/vendor/cc-cedict/2026-10-21-f6b2248b589a/LICENSE-CC-BY-SA-4.0.txt").read_bytes(),
            "ATTRIBUTION.md": b"CC-CEDICT MDBG Paul Andrew Denisowski; Mandarin ignored; Cantonese mechanically derived."}
        lock = {"schema_version": 1, "source_id": reader.SOURCE_ID, "license": "CC-BY-SA-4.0",
                "license_declaration": reader.LICENSE_DECLARATION, "local_directory": str(self.vendor),
                "snapshot_id": "test-only", "source_release_header": {"version": "1", "format": "ts",
                    "charset": "UTF-8", "entries": len(rows), "date": "2026-10-21T05:46:59Z"},
                "attribution": "CC-CEDICT contributors and MDBG", "files": []}
        for name, payload in payloads.items():
            (self.vendor / name).write_bytes(payload)
            lock["files"].append({"name": name, "size_bytes": len(payload),
                                  "sha256": hashlib.sha256(payload).hexdigest()})
        self.lock_path.write_text(json.dumps(lock), encoding="utf-8")

    def build(self, **options):
        return builder.build_candidate(self.baseline, self.output, source_lock=self.lock_path,
            expected_baseline_sha256=self.sha, **options)

    def assert_no_publication(self):
        for path in (self.output, self.output.with_suffix(".manifest.json"), self.output.with_suffix(".review.json")):
            self.assertFalse(path.exists(), path)

    def test_append_only_all_nine_fields_and_prior_ledgers_preserved(self):
        report = self.build()
        self.assertEqual((report["added_pairs"], report["new_texts"]), (1, 1))
        self.assertTrue(report["all_nine_entry_fields_preserved"])
        self.assertEqual(report["earlier_tables_preserved"], {"phrase_encodings": 1, "supplement_review": 1, "syllables": 4})
        self.assertEqual(digest(self.baseline), self.sha)
        with closing(sqlite3.connect(self.output)) as db:
            self.assertEqual(db.execute("SELECT id,text,reading,weight,source,origin FROM entries WHERE id>17").fetchall(),
                [(18, "你好好", "nei5 hou2 hou2", 0, builder.GENERATED_SOURCE, "generated")])
            self.assertEqual(db.execute("SELECT reading,weight,source FROM entries WHERE text='你好'").fetchall(),
                             [("nei4 hou3", 73, "earlier")])
            self.assertEqual(db.execute("SELECT details_json FROM supplement_review").fetchone(), ('{"keep":true}',))
            metadata = dict(db.execute("SELECT key,value FROM metadata"))
            self.assertEqual(json.loads(metadata["baseline_metadata"])["earlier_key"], '"retain"')
            self.assertNotIn("earlier_key", metadata)
        manifest = json.loads(self.output.with_suffix(".manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["database_sha256"], digest(self.output))
        self.assertEqual(manifest["review_sha256"], digest(self.output.with_suffix(".review.json")))
        self.assertEqual(manifest["inputs_before_sha256"], manifest["inputs_after_sha256"])

    def test_all_form_occurrences_and_encoding_ledgers_include_partial_quarantines(self):
        report = self.build()
        self.assertEqual(report["source_form_ledger_rows"], 10)
        self.assertEqual(report["encoding_ledger_rows"], 3)
        with closing(sqlite3.connect(self.output)) as db:
            forms = db.execute(f"SELECT text,status,COUNT(*) FROM {builder.FORMS_TABLE} GROUP BY text,status").fetchall()
            self.assertEqual(dict(((text, status), count) for text, status, count in forms), {
                ("你好", "already_present"): 2, ("你好好", "encoded_unique"): 3,
                ("缺好", "unencodable"): 2, ("甲甲甲甲甲", "truncated"): 2, ("ABC", "source_quarantined"): 1})
            status, codes, paths = db.execute(f"SELECT status,codes_json,path_count FROM {builder.ENCODINGS_TABLE} WHERE text='甲甲甲甲甲'").fetchone()
            self.assertEqual((status, paths, len(json.loads(codes))), ("truncated", 32, 32))
            self.assertFalse(db.execute("SELECT 1 FROM entries WHERE text='甲甲甲甲甲'").fetchone())
            self.assertFalse(db.execute("SELECT 1 FROM entries WHERE text='缺好'").fetchone())
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {builder.FORMS_TABLE} WHERE source_sha256=?",
                (digest(self.vendor / reader.DATA_FILE),)).fetchone(), (10,))
            refs = json.loads(db.execute(f"SELECT source_refs_json FROM {builder.ENCODINGS_TABLE} WHERE text='你好好'").fetchone()[0])
            self.assertEqual(len(refs), 3)
        self.assertEqual(report["headword_evidence"]["excluded_encoder_sources"], ["unihan:kCantonese"])

    def test_no_mandarin_or_definitions_in_code_or_review_and_no_existing_text_variants(self):
        self.build()
        with closing(sqlite3.connect(self.output)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM entries WHERE text='你好'").fetchone(), (1,))
            for table in (builder.FORMS_TABLE, builder.ENCODINGS_TABLE):
                serialized = json.dumps(db.execute(f"SELECT * FROM {table}").fetchall(), ensure_ascii=False)
                self.assertNotIn("THIS IS", serialized)
                self.assertNotIn("wrong3", serialized)
                self.assertNotIn("definition", serialized)
            self.assertEqual(db.execute("SELECT reading FROM entries WHERE source=?", (builder.GENERATED_SOURCE,)).fetchone(),
                             ("nei5 hou2 hou2",))

    def test_changed_source_during_build_prevents_all_publication(self):
        checks = 0

        def change_source():
            nonlocal checks
            checks += 1
            if checks == 2:
                path = self.vendor / "ATTRIBUTION.md"
                path.write_bytes(path.read_bytes().replace(b"MDBG", b"xxxx"))

        with self.assertRaisesRegex(ValueError, "changed during construction"):
            self.build(validate_inputs=change_source)
        self.assert_no_publication()
        self.assertEqual(digest(self.baseline), self.sha)
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_stale_baseline_and_existing_output_cannot_be_overwritten(self):
        with self.assertRaisesRegex(ValueError, "baseline hash"):
            builder.build_candidate(self.baseline, self.output, source_lock=self.lock_path,
                                    expected_baseline_sha256="0" * 64)
        self.output.write_bytes(b"preserve existing output")
        with self.assertRaisesRegex(ValueError, "new, separate"):
            self.build()
        self.assertEqual(self.output.read_bytes(), b"preserve existing output")

    def test_publication_race_keeps_foreign_artifact_and_cleans_own_files(self):
        checks = 0
        protected = self.output.with_suffix(".review.json")

        def collide():
            nonlocal checks
            checks += 1
            if checks == 3:
                protected.write_text("another writer", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            self.build(validate_inputs=collide)
        self.assertEqual(protected.read_text("utf-8"), "another writer")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_suffix(".manifest.json").exists())

    def test_no_absent_texts_and_inconsistent_baseline_policy_rejected(self):
        self.write_source(["你好 你好 [ni3 hao3] /existing/"])
        with self.assertRaisesRegex(ValueError, "No absent"):
            self.build()
        self.assert_no_publication()
        manifest = json.loads(self.baseline_manifest.read_text("utf-8"))
        manifest["phrase_translation_policy"]["excluded_sources"] = []
        self.baseline_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "metadata and manifest disagree"):
            self.build()
        self.assert_no_publication()

    def test_preservation_comparison_rejects_old_id_field_or_ledger_mutation(self):
        for query in ("UPDATE entries SET weight=999 WHERE id=1", "UPDATE entries SET id=2 WHERE id=1",
                      "UPDATE supplement_review SET details_json='changed'", "DELETE FROM phrase_encodings"):
            with self.subTest(query=query):
                path = self.root / "tampered.sqlite3"
                with closing(sqlite3.connect(self.baseline)) as source, closing(sqlite3.connect(path.as_uri(), uri=True)) as target:
                    source.backup(target)
                    target.execute(query)
                    target.commit()
                    with self.assertRaisesRegex(ValueError, "Candidate changed"):
                        builder._preserve_baseline(target, self.baseline.resolve())
                path.unlink()


if __name__ == "__main__":
    unittest.main()
