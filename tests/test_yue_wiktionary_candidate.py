"""Explicit source candidates preserve both canonical and earlier candidate data."""
from contextlib import closing
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime.dictionary import DictionaryEntry
from tools.build_yue_wiktionary_candidate import SOURCE_ID, TABLES, build_candidate


def entry(text, reading, weight=0, source=SOURCE_ID):
    tokens = reading.split()
    base = " ".join(token[:-1] for token in tokens)
    return DictionaryEntry(text, reading, base, base.replace(" ", ""), len(tokens), weight, source)


class YueCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="yue-candidate-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline, self.output = self.root / "baseline.sqlite3", self.root / "candidate.sqlite3"
        with closing(sqlite3.connect(self.baseline)) as db:
            db.executescript("""
                CREATE TABLE entries(id INTEGER PRIMARY KEY,text TEXT,reading TEXT,base_reading TEXT,compact TEXT,
                    syllable_count INTEGER,weight REAL,source TEXT,origin TEXT,UNIQUE(text,reading));
                CREATE TABLE syllables(base TEXT PRIMARY KEY);
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE phrase_encodings(source TEXT PRIMARY KEY,details TEXT);
                CREATE TABLE supplement_review(id INTEGER PRIMARY KEY,details_json TEXT);
                CREATE TABLE cccedict_headword_forms(line INTEGER PRIMARY KEY,text TEXT,status TEXT);
            """)
            db.execute("INSERT INTO entries VALUES(1,'你','nei5','nei','nei',1,99,'earlier','explicit')")
            db.execute("INSERT INTO entries VALUES(3,'好','hou2','hou','hou',1,88,'earlier','explicit')")
            db.executemany("INSERT INTO syllables VALUES (?)", [("nei",), ("hou",)])
            db.execute("INSERT INTO metadata VALUES ('earlier','\"keep\"')")
            db.execute("INSERT INTO phrase_encodings VALUES ('earlier','unchanged')")
            db.execute("INSERT INTO supplement_review VALUES (5,'{\"keep\":1}')")
            db.execute("INSERT INTO cccedict_headword_forms VALUES (9,'你好','encoded_unique')")
            db.commit()
        self.sha = hashlib.sha256(self.baseline.read_bytes()).hexdigest()
        self.entries = [entry("你", "nei5"), entry("你", "nei4"), entry("你好", "nei5 hou2")]
        source_hash = "a" * 64

        def record(page, **extra):
            return {"source": SOURCE_ID, "source_sha256": source_hash, "page_id": page, **extra}

        self.pages = [record("1", revision_id="10", namespace="0", text="你", status="selected_yue_section"),
                      record("2", revision_id="20", namespace="0", text="你好", status="selected_yue_section")]
        self.sections = [record("1", language_section_ordinal=1), record("2", language_section_ordinal=1)]
        self.fields = [record("1" if value.text == "你" else "2", scope="variant", status="admitted_pair",
                              text=value.text, normalized_reading=value.reading, raw_reading=value.reading,
                              source_line=3, source_character_offset=20) for value in self.entries]
        self.reviews = []
        self.evidence = {"source_sha256": source_hash, "source_stats": {"unique_pairs": 3, "all_xml_pages": 2,
                          "section_records": 2, "field_records": 3, "review_records": 0}}

    def build(self, **changes):
        options = {"expected_baseline_sha256": self.sha, "evidence": self.evidence, "page_rows": self.pages,
                   "section_rows": self.sections, "field_rows": self.fields, "review_rows": self.reviews}
        options.update(changes)
        return build_candidate(self.baseline, self.output, self.entries, **options)

    def assert_unpublished(self):
        for path in (self.output, self.output.with_suffix(".manifest.json"), self.output.with_suffix(".review.json")):
            self.assertFalse(path.exists())

    def test_append_explicit_zero_preserves_old_ids_weights_and_all_earlier_ledgers(self):
        with patch("cantonese_ime.autoencode.ScriptAutoencoder", side_effect=AssertionError("must not encode")):
            report = self.build()
        self.assertEqual((report["added_pairs"], report["new_texts"], report["overlapping_pairs"]), (2, 1, 1))
        self.assertEqual(report["earlier_tables_preserved"], {
            "cccedict_headword_forms": 1, "phrase_encodings": 1, "supplement_review": 1, "syllables": 2})
        self.assertTrue(report["all_nine_entry_fields_preserved"])
        self.assertEqual(hashlib.sha256(self.baseline.read_bytes()).hexdigest(), self.sha)
        with closing(sqlite3.connect(self.output)) as db:
            self.assertEqual(db.execute("SELECT id,weight,source,origin FROM entries WHERE id=1").fetchone(),
                             (1, 99, "earlier", "explicit"))
            self.assertEqual(db.execute("SELECT id,text,reading,weight,source,origin FROM entries WHERE id>3 ORDER BY id").fetchall(),
                [(4, "你", "nei4", 0, SOURCE_ID, "supplement"), (5, "你好", "nei5 hou2", 0, SOURCE_ID, "supplement")])
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {TABLES['pages']}").fetchone(), (2,))
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {TABLES['fields']}").fetchone(), (3,))
            self.assertEqual(db.execute("SELECT details_json FROM supplement_review").fetchone(), ('{"keep":1}',))
            metadata = dict(db.execute("SELECT key,value FROM metadata"))
            self.assertEqual(json.loads(metadata["baseline_metadata"])["earlier"], '"keep"')
            fields = [json.loads(row[0]) for row in db.execute(f"SELECT details_json FROM {TABLES['fields']} ORDER BY id")]
            self.assertEqual(fields, self.fields)
        saved = json.loads(self.output.with_suffix(".manifest.json").read_text("utf-8"))
        self.assertEqual(saved["database_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(saved["review_sha256"], hashlib.sha256(self.output.with_suffix(".review.json").read_bytes()).hexdigest())

    def test_nonzero_forged_noncanonical_duplicate_and_unknown_base_cannot_publish(self):
        original = self.entries
        for bad in (replace(original[0], weight=99), replace(original[0], source="other"),
                    entry("你", "nei7"), entry("你", "yan4")):
            with self.subTest(bad=bad):
                self.entries = [bad, *original[1:]]
                with self.assertRaises(ValueError):
                    self.build()
                self.assert_unpublished()
        self.entries = [*original, original[0]]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.build()
        self.assert_unpublished()

    def test_missing_ledger_pair_or_source_correspondence_cannot_publish(self):
        for changes in ({"field_rows": self.fields[:-1]}, {"section_rows": []}, {"page_rows": []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.build(**changes)
        bad_fields = copy.deepcopy(self.fields)
        bad_fields[0]["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "correspondence"):
            self.build(field_rows=bad_fields)
        bad_fields = copy.deepcopy(self.fields)
        bad_fields[0]["normalized_reading"] = "nei3"
        with self.assertRaisesRegex(ValueError, "accepted-field provenance"):
            self.build(field_rows=bad_fields)
        self.assert_unpublished()

    def test_changed_sources_stale_baseline_and_existing_outputs_are_preserved(self):
        checks = 0

        def verify():
            nonlocal checks
            checks += 1
            if checks == 2:
                raise ValueError("source changed")

        with self.assertRaisesRegex(ValueError, "source changed"):
            self.build(validate_sources=verify)
        self.assert_unpublished()
        self.assertFalse(list(self.root.glob("*.tmp")))
        with self.assertRaisesRegex(ValueError, "baseline hash"):
            self.build(expected_baseline_sha256="0" * 64)
        self.output.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "new, separate"):
            self.build()
        self.assertEqual(self.output.read_text("utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
