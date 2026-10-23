"""Source attestation/binding checks, distinct from linguistic evaluation."""

from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools import build_mappings as mapping
from cantonese_ime.dictionary import YUE_WIKTIONARY_TABLES


class YueMappingBindingTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);"
                              "CREATE TABLE entries(text TEXT,reading TEXT,weight REAL,origin TEXT,source TEXT);")
        self.pairs = {("甲", "gaap3"), ("乙", "jyut6")}
        self.metadata = {
            "source_lock_sha256": "locked", "parser_sha256": "reader",
            "insertion_phase": "post_autoencoding_post_wordnet_post_cccedict_headwords",
            "import_stats": {"all_xml_pages": 1, "section_records": 1, "field_records": 2,
                             "review_records": 1, "unique_pairs": 2},
            "files": [{"name": mapping.YUE_FILE, "sha256": "archive"}],
            "accepted_pairs_sha256": mapping._pair_digest(self.pairs)}
        self.selected = dict(self.metadata, source_explicit_cantonese_readings=True,
            independent_linguistic_approval=False, build_selection_status="selected_default_explicit_post_cccedict")
        self.stats = {"insertion_phase": self.metadata["insertion_phase"],
            "ledger_counts": {"pages": 1, "sections": 1, "fields": 2, "reviews": 1},
            "accepted_source_pairs": 2, "added_pairs": 1, "overlapping_pairs": 1}
        self.write_metadata()
        for table in YUE_WIKTIONARY_TABLES.values():
            self.db.execute(f"CREATE TABLE {table}(details_json TEXT)")
        shared = {"source": mapping.YUE_SOURCE_ID, "source_file": mapping.YUE_FILE,
                  "source_sha256": "archive"}
        for role in ("pages", "sections", "reviews"):
            self.db.execute(f"INSERT INTO {YUE_WIKTIONARY_TABLES[role]} VALUES (?)", (json.dumps(shared),))
        for text, reading in sorted(self.pairs):
            details = dict(shared, scope="variant", status="admitted_pair", text=text, normalized_reading=reading)
            self.db.execute(f"INSERT INTO {YUE_WIKTIONARY_TABLES['fields']} VALUES (?)", (json.dumps(details),))
        self.db.executemany("INSERT INTO entries VALUES (?,?,?,?,?)", [
            ("甲", "gaap3", 99, "explicit", "rime:chars"),
            ("乙", "jyut6", 0, "supplement", mapping.YUE_SOURCE_ID)])

    def write_metadata(self):
        self.db.executemany("INSERT OR REPLACE INTO metadata VALUES (?,?)", [
            ("source_metadata", json.dumps({"supplements": {"yue_wiktionary": self.selected}})),
            ("yue_wiktionary", json.dumps(self.stats))])

    def test_binds_all_raw_pairs_including_prior_source_winner(self):
        mapping._bind_yue_wiktionary_dictionary(self.db, self.metadata)
        self.assertEqual(self.metadata["dictionary_selection"], self.stats)
        self.assertEqual(self.metadata["build_selection_status"], "selected_default_explicit_post_cccedict")

    def test_missing_accepted_pair_fails(self):
        self.db.execute("DELETE FROM entries WHERE text='甲'")
        with self.assertRaisesRegex(ValueError, "pair is missing"):
            mapping._bind_yue_wiktionary_dictionary(self.db, self.metadata)

    def test_own_rows_cannot_invent_frequency_or_generated_origin(self):
        for assignment in ("weight=1", "origin='generated'"):
            with self.subTest(assignment=assignment):
                self.db.execute("UPDATE entries SET weight=0,origin='supplement' WHERE source=?", (mapping.YUE_SOURCE_ID,))
                self.db.execute(f"UPDATE entries SET {assignment} WHERE source=?", (mapping.YUE_SOURCE_ID,))
                with self.assertRaisesRegex(ValueError, "zero supplement provenance"):
                    mapping._bind_yue_wiktionary_dictionary(self.db, self.metadata)

    def test_exact_four_ledger_counts_and_raw_source_hash_required(self):
        table = YUE_WIKTIONARY_TABLES["reviews"]
        self.db.execute(f"UPDATE {table} SET details_json=?", (json.dumps({"source": mapping.YUE_SOURCE_ID,
            "source_file": mapping.YUE_FILE, "source_sha256": "other"}),))
        with self.assertRaisesRegex(ValueError, "source correspondence"):
            mapping._bind_yue_wiktionary_dictionary(self.db, self.metadata)
        self.db.execute(f"DELETE FROM {table}")
        with self.assertRaisesRegex(ValueError, "ledger counts"):
            mapping._bind_yue_wiktionary_dictionary(self.db, self.metadata)

    def test_stale_selected_reader_or_phase_fails(self):
        self.selected["parser_sha256"] = "stale"
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, "provenance differs"):
            mapping._bind_yue_wiktionary_dictionary(self.db, self.metadata)

    def test_pair_digest_does_not_accept_same_count_wrong_reading(self):
        table = YUE_WIKTIONARY_TABLES["fields"]
        row = json.loads(self.db.execute(f"SELECT details_json FROM {table} LIMIT 1").fetchone()[0])
        row["normalized_reading"] = "gaap6"
        self.db.execute(f"UPDATE {table} SET details_json=? WHERE rowid=1", (json.dumps(row),))
        with self.assertRaisesRegex(ValueError, "pair set differs"):
            mapping._bind_yue_wiktionary_dictionary(self.db, self.metadata)


class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)")

    def select(self, kind="yue_wiktionary", explicit=None):
        return mapping._selected_snapshot_lock(self.db, kind, explicit, Path("default-lock.json"),
            set(YUE_WIKTIONARY_TABLES.values()) if kind == "yue_wiktionary" else {"cccedict_headword_forms"},
            "yue_wiktionary" if kind == "yue_wiktionary" else "headword_encoding")

    def test_old_database_automatically_skips_both_new_collectors(self):
        self.db.execute("INSERT INTO metadata VALUES ('source_metadata',?)", (json.dumps({"supplements": {"wordnet": {}}}),))
        self.assertIsNone(self.select())
        self.assertIsNone(self.select("cccedict_headwords"))

    def test_entries_only_legacy_database_skips_unselected_collectors(self):
        self.db.execute("DROP TABLE metadata")
        self.db.execute("CREATE TABLE entries(base_reading TEXT,source TEXT,origin TEXT)")
        self.db.execute("INSERT INTO entries VALUES ('nei','rime:chars','explicit')")
        self.assertIsNone(self.select())
        self.assertIsNone(self.select("cccedict_headwords"))

    def test_missing_metadata_cannot_hide_selected_source_rows(self):
        self.db.execute("DROP TABLE metadata")
        self.db.execute("CREATE TABLE entries(source TEXT)")
        for kind, source in (("yue_wiktionary", mapping.YUE_SOURCE_ID),
                             ("cccedict_headwords", "cccedict:headwords:autoencoded")):
            with self.subTest(kind=kind):
                self.db.execute("DELETE FROM entries")
                self.db.execute("INSERT INTO entries VALUES (?)", (source,))
                with self.assertRaisesRegex(ValueError, "requires its metadata table"):
                    self.select(kind)

    def test_missing_metadata_cannot_hide_partial_source_ledger(self):
        self.db.execute("DROP TABLE metadata")
        self.db.execute(f"CREATE TABLE {YUE_WIKTIONARY_TABLES['pages']}(details_json TEXT)")
        with self.assertRaisesRegex(ValueError, "requires its metadata table"):
            self.select()

    def test_selection_markers_require_binding_even_without_source_block(self):
        for key, value in (("yue_wiktionary", {}), ("supplement_stats", {"yue_wiktionary": {}}),
                           ("supplement_order", ["yue_wiktionary"])):
            with self.subTest(key=key):
                self.db.execute("DELETE FROM metadata")
                self.db.execute("INSERT INTO metadata VALUES (?,?)", (key, json.dumps(value)))
                self.assertEqual(self.select(), Path("default-lock.json"))
                with self.assertRaisesRegex(ValueError, "all four dictionary ledgers"):
                    mapping._bind_yue_wiktionary_dictionary(self.db, {})

    def test_malformed_existing_metadata_is_not_optional(self):
        self.db.execute("DROP TABLE metadata")
        self.db.execute("CREATE TABLE metadata(unrelated TEXT)")
        with self.assertRaises(sqlite3.OperationalError):
            self.select()

    def test_explicit_new_source_on_old_database_requires_binding_and_fails(self):
        self.assertEqual(self.select(explicit=Path("explicit.json")), Path("explicit.json"))
        with self.assertRaisesRegex(ValueError, "all four dictionary ledgers"):
            mapping._bind_yue_wiktionary_dictionary(self.db, {})
        with self.assertRaisesRegex(ValueError, "requires its dictionary ledgers"):
            mapping._bind_cccedict_headword_dictionary(self.db, {})

    def test_partial_ledger_does_not_silently_omit_selected_source(self):
        self.db.execute(f"CREATE TABLE {YUE_WIKTIONARY_TABLES['pages']}(details_json TEXT)")
        self.assertEqual(self.select(), Path("default-lock.json"))
        with self.assertRaisesRegex(ValueError, "all four dictionary ledgers"):
            mapping._bind_yue_wiktionary_dictionary(self.db, {})

    def test_retained_custom_lock_is_selected(self):
        self.db.execute("INSERT INTO metadata VALUES ('source_metadata',?)", (json.dumps({"supplements": {
            "yue_wiktionary": {"source_lock_file": "retained/custom.json"}}}),))
        self.assertEqual(self.select(), mapping.PROJECT_ROOT / "retained/custom.json")


class RetainedSourceCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = mapping.PROJECT_ROOT / "data/supplements/yue-wiktionary.sources.lock.json"
        cls.bases, cls.tones, cls.metadata = mapping.collect_yue_wiktionary_source(cls.lock)

    def test_raw_source_inventory_is_before_dictionary_winner_deduplication(self):
        self.assertEqual(self.metadata["import_stats"]["unique_pairs"], 1486)
        self.assertEqual(len(self.bases), 527)
        self.assertEqual(sum(map(len, self.tones.values())), 1108)
        self.assertTrue(self.metadata["source_explicit_cantonese_readings"])
        self.assertFalse(self.metadata["independent_linguistic_approval"])

    def test_changed_lock_is_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "lock.json"
            lock.write_bytes(self.lock.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "changed before publication"):
                mapping._verify_yue_wiktionary_collection(lock, self.metadata)

    def test_text_only_cc_headwords_never_create_authored_tone_inventory(self):
        metadata = mapping.collect_cccedict_headword_source(
            mapping.PROJECT_ROOT / "data/supplements/cccedict-headwords.sources.lock.json")
        self.assertFalse(metadata["authored_cantonese_readings"])
        self.assertNotIn("bases", metadata)
        self.assertNotIn("tones", metadata)
        self.assertEqual(metadata["import_stats"]["form_candidates"], 250590)


if __name__ == "__main__":
    unittest.main()
