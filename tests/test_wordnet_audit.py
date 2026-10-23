"""Independent audit failures tested with hand-authored source and ledger data."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.audit_wordnet_source import audit_wordnet


SOURCE = "wordnet:cantown"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"


class WordnetAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="wordnet-independent-audit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE entries(id INTEGER PRIMARY KEY,text TEXT,reading TEXT,source TEXT,weight REAL,origin TEXT);
            CREATE TABLE supplement_review(source TEXT,text TEXT,status TEXT,details_json TEXT);
            INSERT INTO entries VALUES(1,'你好','nei5 hou2','rime',100,'explicit');
            INSERT INTO entries VALUES(2,'話','waa6','wordnet:cantown',0,'supplement');
        """)
        self.xml = (f'<LexicalResource><Lexicon id="cantown-yue" language="yue" version="1.0" license="{LICENSE}">'
                    '<LexicalEntry id="a"><Lemma writtenForm="你好"/>'
                    '<Form writtenForm="nei5 hou2"><Tag category="transliteration">ascii</Tag></Form>'
                    '<Form writtenForm=""/><Form writtenForm="NEI5  HOU2"/></LexicalEntry>'
                    '<LexicalEntry id="b"><Lemma writtenForm="話"/><Form writtenForm="waa6"/>'
                    '<Form writtenForm="waa6*2"/><Form writtenForm="yat6"/></LexicalEntry>'
                    '<LexicalEntry id="c"><Lemma writtenForm="你"/><Form writtenForm="nei5 hou2"/></LexicalEntry>'
                    '<LexicalEntry id="d"><Lemma writtenForm="A"/><Form writtenForm="aa1"/></LexicalEntry>'
                    '<LexicalEntry id="e"><Lemma writtenForm="人"/></LexicalEntry>'
                    '<Synset id="not-a-word"><Definition>SECRET text</Definition></Synset></Lexicon>'
                    f'<Lexicon id="cantown-en" language="en" version="1.0" license="{LICENSE}">'
                    '<LexicalEntry id="en"><Lemma writtenForm="好"/><Form writtenForm="hou2"/><Form writtenForm=""/>'
                    '</LexicalEntry></Lexicon></LexicalResource>')
        (self.root / "cantown.xml").write_bytes(self.xml.encode())
        inventory = {"schema_version": 1, "baseline_database_sha256": "a" * 64,
                     "bases": ["aa", "hou", "nei", "waa"]}
        (self.root / "parser-attested-bases.json").write_text(json.dumps(inventory), encoding="utf-8")
        self.lock = {"verified": True, "source_directory": str(self.root), "files": []}
        self.refresh_lock()
        self.reviews = [
            self.event("a", 2, "你好", "", "blank_form", "missing_reading"),
            self.event("a", 3, "你好", "NEI5  HOU2", "normalized_reading", "informational", reading="nei5 hou2"),
            self.event("b", 2, "話", "waa6*2", "noncanonical_jyutping"),
            self.event("b", 3, "話", "yat6", "unattested_syllables", unknown_bases=["yat"]),
            self.event("c", 1, "你", "nei5 hou2", "codepoint_syllable_alignment", text_codepoints=1, syllable_count=2),
            self.event("d", 1, "A", "aa1", "non_han_text"),
            self.event("e", None, "人", "", "missing_forms", "missing_reading"),
            self.event("en", 1, "好", "hou2", "non_yue_lexicon", "excluded", lexicon="cantown-en"),
            self.event("en", 2, "好", "", "non_yue_lexicon", "excluded", lexicon="cantown-en"),
        ]
        self.persist()

    def refresh_lock(self):
        self.lock["files"] = [{"name": name, "matches_lock": True,
                               "size_bytes": (self.root / name).stat().st_size,
                               "sha256": hashlib.sha256((self.root / name).read_bytes()).hexdigest()}
                              for name in ("cantown.xml", "parser-attested-bases.json")]

    def event(self, entry, ordinal, text, raw, reason, status="quarantined", lexicon="cantown-yue", **fields):
        return {"source": SOURCE, "source_file": "cantown.xml",
                "source_sha256": hashlib.sha256((self.root / "cantown.xml").read_bytes()).hexdigest(),
                "lexicon_id": lexicon, "entry_id": entry, "form_ordinal": ordinal,
                "scope": "entry" if ordinal is None else "form", "text": text,
                "raw_reading": raw, "reason": reason, "status": status, **fields}

    def persist(self):
        self.db.execute("DELETE FROM supplement_review")
        self.db.executemany("INSERT INTO supplement_review VALUES(?,?,?,?)",
                            [(row["source"], row["text"], row["status"], json.dumps(row)) for row in self.reviews])

    def run_audit(self, **options):
        self.verified = {}
        return audit_wordnet(self.db, self.lock, self.verified, **options)

    def test_complete_own_pair_and_every_ledger_status(self):
        report = self.run_audit()
        self.assertTrue(report["mechanical_complete"], report)
        counts = report["counts"]
        self.assertEqual((counts["explicit_pairs"], counts["duplicate_entries"]), (2, 1))
        self.assertEqual((counts["review_records_required"], counts["review_records_present"]), (9, 9))
        self.assertEqual((counts["input_rows"], counts["excluded_lexical_entries"]), (5, 1))
        self.assertEqual(counts["ignored_form_tags"], 1)
        self.assertEqual(self.verified, {"supplement": {2}})
        self.assertEqual(counts["wordnet_source_rows_credited"], 1)
        self.assertEqual(counts["overlap_rows_not_previously_verified"], 1)
        self.assertNotIn("SECRET", json.dumps(report))
        # English 好/hou2 is explicitly excluded despite a valid-looking code.
        self.assertEqual(counts["explicit_rows_missing"], 0)

    def test_missing_or_wrong_pair_cannot_pass(self):
        for replacement in (None, "waa2"):
            with self.subTest(replacement=replacement):
                self.db.execute("DELETE FROM entries WHERE id=2")
                if replacement:
                    self.db.execute("INSERT INTO entries VALUES(2,'話',?,'wordnet:cantown',0,'supplement')", (replacement,))
                report = self.run_audit()
                self.assertFalse(report["mechanical_complete"])
                self.assertEqual(report["counts"]["explicit_rows_missing"], 1)
                self.assertNotIn(2, self.verified.get("supplement", set()))

    def test_deleted_blank_quarantine_normalization_and_excluded_records_fail(self):
        for index in range(len(self.reviews)):
            with self.subTest(event=self.reviews[index]["reason"], ordinal=self.reviews[index]["form_ordinal"]):
                report = self.run_audit(review_rows=self.reviews[:index] + self.reviews[index + 1:])
                self.assertFalse(report["mechanical_complete"])
                self.assertEqual(report["counts"]["review_records_missing"], 1)

    def test_stale_hash_wrong_ordinal_raw_and_diagnostic_fields_fail(self):
        for index, field, value in ((0, "source_sha256", "f" * 64), (0, "form_ordinal", 1),
                                    (1, "raw_reading", "nei5 hou2"), (1, "reading", "nei2 hou2"),
                                    (3, "unknown_bases", ["jat"]), (4, "syllable_count", 1)):
            with self.subTest(field=field):
                rows = copy.deepcopy(self.reviews)
                rows[index][field] = value
                report = self.run_audit(review_rows=rows)
                self.assertFalse(report["mechanical_complete"])
                self.assertEqual(report["counts"]["review_records_missing"], 1)

    def test_sql_ledger_disagreement_and_duplicate_events_fail(self):
        self.db.execute("UPDATE supplement_review SET status='confirmed' WHERE text='人'")
        report = self.run_audit()
        self.assertFalse(report["mechanical_complete"])
        self.assertEqual(report["counts"]["review_records_invalid"], 1)
        report = self.run_audit(review_rows=self.reviews + [self.reviews[0]])
        self.assertFalse(report["mechanical_complete"])
        self.assertEqual(report["counts"]["review_records_unexpected"], 1)

    def test_positive_new_weight_or_wrong_origin_fails_but_old_source_weight_is_preserved(self):
        self.assertTrue(self.run_audit()["mechanical_complete"])
        self.db.execute("UPDATE entries SET weight=100 WHERE id=2")
        report = self.run_audit()
        self.assertFalse(report["mechanical_complete"])
        self.assertEqual(report["counts"]["source_weight_or_origin_errors"], 1)
        self.assertNotIn(2, self.verified.get("supplement", set()))
        self.db.execute("UPDATE entries SET weight=0,origin='generated' WHERE id=2")
        self.assertFalse(self.run_audit()["mechanical_complete"])

    def test_other_source_overlap_does_not_grant_or_replace_provenance(self):
        earlier = {"explicit": {1}}
        report = audit_wordnet(self.db, self.lock, earlier)
        self.assertTrue(report["mechanical_complete"])
        self.assertEqual(earlier, {"explicit": {1}, "supplement": {2}})
        self.assertEqual(report["counts"]["overlap_rows_previously_verified"], 1)
        self.db.execute("UPDATE entries SET source='unattested:forged',weight=500,origin='generated' WHERE id=2")
        report = self.run_audit()
        # Pair presence is true, but this helper cannot authenticate another
        # source's attribution. The parent's provenance coverage must fail.
        self.assertTrue(report["mechanical_complete"])
        self.assertEqual(self.verified, {})
        self.assertEqual(report["counts"]["wordnet_source_rows_credited"], 0)
        self.assertEqual(report["counts"]["overlap_rows_not_previously_verified"], 2)

    def test_changed_raw_source_lock_cannot_reuse_previous_verified_hash(self):
        inventory = json.loads((self.root / "parser-attested-bases.json").read_text("utf-8"))
        digest = next(row["sha256"] for row in self.lock["files"] if row["name"] == "parser-attested-bases.json")
        raw = {"license": "CC-BY-4.0", "parser_attestation": {
            "file": "parser-attested-bases.json", "sha256": digest,
            "base_count": len(inventory["bases"]), "baseline_database_sha256": "a" * 64}}
        path = self.root / "source-lock.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        self.lock.update(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(self.run_audit()["mechanical_complete"])
        raw["license"] = "changed-after-verification"
        path.write_text(json.dumps(raw), encoding="utf-8")
        report = self.run_audit()
        self.assertFalse(report["mechanical_complete"])
        self.assertEqual(report["counts"]["invalid_locked_source"], 1)

    def test_lock_change_during_pair_queries_prevents_complete_result(self):
        inventory = json.loads((self.root / "parser-attested-bases.json").read_text("utf-8"))
        digest = next(row["sha256"] for row in self.lock["files"] if row["name"] == "parser-attested-bases.json")
        raw = {"parser_attestation": {"file": "parser-attested-bases.json", "sha256": digest,
                                      "base_count": len(inventory["bases"]), "baseline_database_sha256": "a" * 64}}
        path = self.root / "source-lock.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        self.lock.update(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())

        def change_after_source_read(sql):
            if sql.startswith("SELECT rowid"):
                path.write_text(json.dumps({**raw, "changed_during_audit": True}), encoding="utf-8")

        self.db.set_trace_callback(change_after_source_read)
        self.addCleanup(self.db.set_trace_callback, None)
        report = self.run_audit()
        self.assertEqual(report["counts"]["explicit_rows_present"], 2)
        self.assertFalse(report["mechanical_complete"])
        self.assertEqual(report["counts"]["invalid_locked_source"], 1)

    def test_missing_or_stale_locked_source_and_inventory_fail(self):
        original = copy.deepcopy(self.lock)
        for name in ("cantown.xml", "parser-attested-bases.json"):
            with self.subTest(name=name):
                self.lock = copy.deepcopy(original)
                self.lock["files"] = [row for row in self.lock["files"] if row["name"] != name]
                self.assertFalse(self.run_audit()["mechanical_complete"])
        self.lock = original
        path = self.root / "cantown.xml"
        payload = path.read_bytes()
        path.write_bytes(payload.replace(b"nei5 hou2", b"nei2 hou2", 1))
        report = self.run_audit()
        self.assertFalse(report["mechanical_complete"])
        self.assertEqual(report["counts"]["invalid_locked_source"], 1)

    def test_foreign_or_inherited_lexical_forms_cannot_supply_cantonese_pairs(self):
        for xml in (self.xml.replace('language="yue"', 'language="en"'),
                    self.xml.replace('<Form writtenForm="waa6"/>', '<Sense><Form writtenForm="waa6"/></Sense>')):
            with self.subTest(xml=xml):
                (self.root / "cantown.xml").write_bytes(xml.encode())
                self.refresh_lock()
                report = self.run_audit()
                self.assertFalse(report["mechanical_complete"])
                self.assertEqual(report["counts"]["structural_errors"], 1)

    def test_empty_selected_lexicon_and_missing_lock_never_pass_vacuously(self):
        self.assertFalse(audit_wordnet(self.db, None, {})["mechanical_complete"])
        xml = f'<LexicalResource><Lexicon id="cantown-yue" language="yue" version="1.0" license="{LICENSE}"/></LexicalResource>'
        (self.root / "cantown.xml").write_bytes(xml.encode())
        self.refresh_lock()
        report = self.run_audit(review_rows=[])
        self.assertFalse(report["mechanical_complete"])
        self.assertEqual(report["counts"]["explicit_pairs"], 0)

    def test_candidate_override_does_not_depend_on_existing_sql_review_table(self):
        self.db.execute("DROP TABLE supplement_review")
        self.assertTrue(self.run_audit(review_rows=self.reviews)["mechanical_complete"])
        self.assertFalse(self.run_audit()["mechanical_complete"])


if __name__ == "__main__":
    unittest.main()
