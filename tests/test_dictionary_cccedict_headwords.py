"""Canonical opt-in headwords must equal the isolated append-only candidate."""
from contextlib import closing, redirect_stdout
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime import cccedict_headwords as reader
from cantonese_ime.dictionary import (
    HEADWORD_ENCODINGS_TABLE, HEADWORD_FORMS_TABLE, HEADWORD_GENERATED_SOURCE,
    build_dictionary, file_sha256,
)
from tools import build_cccedict_candidate as candidate
from tools import build_dictionary as build_cli
from tools import build_mappings as mapping_cli


class CanonicalHeadwordTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canonical-headwords-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "rime"
        self.source.mkdir()
        (self.source / "jyut6ping3.chars.dict.yaml").write_text(
            "---\nname: fixture\n...\n你\tnei5\t91\n好\thou2\t82\n甲\tgaap3\t64\n甲\tgaap6\t64\n", encoding="utf-8")
        (self.source / "jyut6ping3.phrase.dict.yaml").write_text(
            "---\nname: fixture\n...\n你好\n", encoding="utf-8")
        (self.source / "essay-cantonese.txt").write_text("你好\t73\n", encoding="utf-8")
        self.wordnet = self.root / "wordnet"
        self.wordnet.mkdir()
        self.xml = self.wordnet / "cantown.xml"
        (self.wordnet / "parser-attested-bases.json").write_text(json.dumps({
            "schema_version": 1, "bases": ["nei", "hou", "gaap", "haa"],
            "baseline_database_sha256": "a" * 64}), encoding="utf-8")
        self.xml.write_text('<LexicalResource><Lexicon id="cantown-yue" language="yue" '
            'version="1.0" license="https://creativecommons.org/licenses/by/4.0/">'
            '<LexicalEntry id="a"><Lemma writtenForm="你"/><Form writtenForm="nei4"/></LexicalEntry>'
            '<LexicalEntry id="b"><Lemma writtenForm="你好"/><Form writtenForm="nei4 hou3"/></LexicalEntry>'
            '<LexicalEntry id="c"><Lemma writtenForm="哈"/><Form writtenForm="haa1"/></LexicalEntry>'
            '</Lexicon></LexicalResource>', encoding="utf-8")
        self.vendor = self.root / "headwords"
        self.vendor.mkdir()
        self.lock_path = self.root / "headwords.lock.json"
        self.write_headwords([
            "你好 你好 [THIS IS NOT CANTONESE] /ignored Mandarin definition/",
            "你好好 你好好 [wrong3 wrong2] /never supplies a Cantonese reading/",
            "你你 你你 [invented] /cannot use Wordnet's extra character code/",
            "哈哈 哈哈 [invented] /Wordnet characters are not translator input/",
            "甲甲甲甲甲 甲甲甲甲甲 [a1] /32 paths are incomplete/",
            ("你" * 33) + " " + ("你" * 33) + " [a1] /too long/",
            "ABC 你好好 [foreign] /field-specific quarantine/",
        ])

    def write_headwords(self, rows):
        payload = ("# CC-CEDICT\n# Published by MDBG\n# " + reader.LICENSE_DECLARATION
            + "\n# " + reader.LICENSE_URL + "\n#! version=1\n#! format=ts\n#! charset=UTF-8\n"
            + "#! publisher=MDBG\n#! entries=" + str(len(rows)) + "\n#! license=" + reader.LICENSE_URL
            + "\n#! date=2026-10-21T05:46:59Z\n" + "\n".join(rows) + "\n").encode("utf-8")
        project = Path(__file__).resolve().parents[1]
        payloads = {reader.DATA_FILE: payload, reader.ARCHIVE_FILE: gzip.compress(payload, mtime=0),
            "download-page.html": (reader.LICENSE_DECLARATION + reader.LICENSE_URL).encode(),
            "LICENSE-CC-BY-SA-4.0.txt": (project / "data/vendor/cc-cedict/2026-10-21-f6b2248b589a/LICENSE-CC-BY-SA-4.0.txt").read_bytes(),
            "ATTRIBUTION.md": b"CC-CEDICT MDBG Paul Andrew Denisowski; Mandarin ignored; Cantonese mechanically generated."}
        lock = {"schema_version": 1, "source_id": reader.SOURCE_ID, "license": "CC-BY-SA-4.0",
            "license_declaration": reader.LICENSE_DECLARATION, "local_directory": str(self.vendor),
            "selection_status": "candidate source preparation", "snapshot_id": "test-only",
            "source_release_header": {"version": "1", "format": "ts", "charset": "UTF-8",
                "entries": len(rows), "date": "2026-10-21T05:46:59Z"}, "files": []}
        for name, data in payloads.items():
            (self.vendor / name).write_bytes(data)
            lock["files"].append({"name": name, "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest()})
        self.lock_path.write_text(json.dumps(lock), encoding="utf-8")

    def selected_metadata(self):
        return {"supplements": {"cccedict_headwords": {
            "source_lock_sha256": file_sha256(self.lock_path),
            "parser_sha256": file_sha256(Path(reader.__file__)),
            "encoder_sha256": file_sha256(Path(__file__).resolve().parents[1] / "cantonese_ime/autoencode.py"),
            "authored_cantonese_readings": False}}}

    def build(self, name, *, headwords=False, **options):
        supplements = {"wordnet": self.xml}
        if headwords:
            supplements["cccedict_headwords"] = self.vendor / reader.DATA_FILE
        output = self.root / (name + ".sqlite3")
        stats = build_dictionary(self.source, output, supplements=supplements,
            autoencode_phrases=True, source_metadata=self.selected_metadata() if headwords else None, **options)
        return output, stats

    @staticmethod
    def table(path, name):
        with closing(sqlite3.connect(path)) as db:
            order = "1,2" if len(db.execute('PRAGMA table_info("' + name + '")').fetchall()) > 1 else "1"
            return db.execute('SELECT * FROM "' + name + '" ORDER BY ' + order).fetchall()

    def test_opt_in_matches_candidate_all_nine_fields_and_both_complete_ledgers(self):
        baseline, _ = self.build("baseline")
        separate = self.root / "separate.sqlite3"
        candidate.build_candidate(baseline, separate, source_lock=self.lock_path,
            expected_baseline_sha256=file_sha256(baseline))
        canonical, stats = self.build("canonical", headwords=True)
        for table in ("entries", "syllables", "phrase_encodings", "supplement_review",
                      HEADWORD_FORMS_TABLE, HEADWORD_ENCODINGS_TABLE):
            self.assertEqual(self.table(canonical, table), self.table(separate, table), table)
        before, after = self.table(baseline, "entries"), self.table(canonical, "entries")
        self.assertEqual(after[:len(before)], before)
        self.assertTrue(all(row[6:] == (0.0, HEADWORD_GENERATED_SOURCE, "generated") for row in after[len(before):]))
        self.assertEqual(stats["headword_encoding"]["new_generated_pairs"], 2)
        self.assertEqual(stats["headword_encoding"]["complete_new_texts"], 2)

    def test_wordnet_has_already_been_appended_but_never_supplies_translations(self):
        output, stats = self.build("phases", headwords=True)
        rows = self.table(output, "entries")
        by_text = {}
        for row in rows:
            by_text.setdefault(row[1], set()).add(row[2])
        self.assertEqual(by_text["你好"], {"nei5 hou2", "nei4 hou3"})
        self.assertEqual(by_text["你你"], {"nei5 nei5"})
        self.assertNotIn("哈哈", by_text)
        # A generated phrase remains generated even if Wordnet also publishes
        # another whole-word reading before the headword cohort is considered.
        with closing(sqlite3.connect(output)) as db:
            self.assertEqual(db.execute("SELECT status,codes_json FROM phrase_encodings").fetchone(),
                             ("encoded_unique", '["nei5 hou2"]'))
            self.assertEqual(db.execute(f"SELECT status FROM {HEADWORD_FORMS_TABLE} WHERE text='你好' LIMIT 1").fetchone(),
                             ("already_present",))
        self.assertIn(HEADWORD_GENERATED_SOURCE, stats["phrase_translation_policy"]["excluded_sources"])

    def test_translator_boundary_hash_can_be_reconstructed_after_future_sources_append(self):
        baseline, _ = self.build("boundary-baseline")
        output, stats = self.build("boundary-selected", headwords=True)
        info = stats["headword_encoding"]
        with closing(sqlite3.connect(baseline)) as old:
            expected_boundary = old.execute("SELECT MAX(id) FROM entries").fetchone()[0]
        self.assertEqual(info["pre_headword_max_entry_id"], expected_boundary)
        with closing(sqlite3.connect(output)) as db:
            db.execute("INSERT INTO entries(text,reading,base_reading,compact,syllable_count,weight,source,origin) "
                       "VALUES ('新','san1','san','san',1,99,'future:authored','supplement')")
            excluded = set(info["excluded_encoder_sources"])
            rows = [row for row in db.execute(
                "SELECT id,text,reading,weight,source,origin FROM entries WHERE id<=? "
                "AND origin IN ('explicit','supplement') AND syllable_count=1 ORDER BY text,reading",
                (expected_boundary,)) if row[4] not in excluded]
        self.assertEqual({row[2] for row in rows}, {"nei5", "hou2", "gaap3", "gaap6"})
        expected_hash = hashlib.sha256()
        for row in rows:
            expected_hash.update((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                                  + "\n").encode("utf-8"))
        self.assertEqual(info["translation_rows"], len(rows))
        self.assertEqual(info["translator_input_sha256"], expected_hash.hexdigest())

    def test_all_forms_and_incomplete_results_are_accounted_without_partial_imports(self):
        output, stats = self.build("accounting", headwords=True)
        info = stats["supplement_stats"]["cccedict_headwords"]
        self.assertEqual(info["form_candidates"], 14)
        self.assertEqual(info["source_form_ledger_rows"], 14)
        self.assertEqual(info["quarantined_forms"], 1)
        self.assertEqual(set(info["encoding_counts"]), {"encoded_unique", "unencodable", "truncated", "too_long"})
        self.assertEqual(info["insertion_phase"], "post_autoencoding_post_wordnet")
        self.assertFalse(info["linguistic_approval"])
        with closing(sqlite3.connect(output)) as db:
            status, codes, paths = db.execute(f"SELECT status,codes_json,path_count FROM {HEADWORD_ENCODINGS_TABLE} "
                "WHERE text='甲甲甲甲甲'").fetchone()
            self.assertEqual((status, len(json.loads(codes)), paths), ("truncated", 32, 32))
            self.assertIsNone(db.execute("SELECT 1 FROM entries WHERE text='甲甲甲甲甲'").fetchone())
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {HEADWORD_FORMS_TABLE} WHERE source_sha256=?",
                (file_sha256(self.vendor / reader.DATA_FILE),)).fetchone()[0], 14)
        for table in (HEADWORD_FORMS_TABLE, HEADWORD_ENCODINGS_TABLE):
            serialized = json.dumps(self.table(output, table), ensure_ascii=False)
            self.assertNotIn("wrong3", serialized)
            self.assertNotIn("definition", serialized)
            self.assertNotIn("THIS IS NOT", serialized)

    def test_unselected_path_retains_schema_metadata_and_deterministic_bytes(self):
        first, first_stats = self.build("first")
        second, second_stats = self.build("second")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first_stats, second_stats)
        self.assertNotIn("headword_encoding", first_stats)
        self.assertNotIn("cccedict_headwords", first_stats["supplement_order"])
        self.assertNotIn(HEADWORD_GENERATED_SOURCE, first_stats["phrase_translation_policy"]["excluded_sources"])
        with closing(sqlite3.connect(first)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse({HEADWORD_FORMS_TABLE, HEADWORD_ENCODINGS_TABLE} & tables)
        selected_a, stats_a = self.build("selected-a", headwords=True)
        selected_b, stats_b = self.build("selected-b", headwords=True)
        self.assertEqual(selected_a.read_bytes(), selected_b.read_bytes())
        self.assertEqual(stats_a, stats_b)

    def test_selection_requires_generation_and_failure_preserves_old_outputs(self):
        output, _ = self.build("protected")
        manifest = output.with_suffix(".manifest.json")
        expected = (output.read_bytes(), manifest.read_bytes())
        with self.assertRaisesRegex(ValueError, "requires autoencode"):
            build_dictionary(self.source, output, supplements={"cccedict_headwords": self.vendor / reader.DATA_FILE})
        self.assertEqual((output.read_bytes(), manifest.read_bytes()), expected)

        def changed():
            self.assertEqual((output.read_bytes(), manifest.read_bytes()), expected)
            raise ValueError("Source changed before publication")

        with self.assertRaisesRegex(ValueError, "Source changed"):
            build_dictionary(self.source, output,
                supplements={"wordnet": self.xml, "cccedict_headwords": self.vendor / reader.DATA_FILE},
                autoencode_phrases=True, verify_before_publish=changed)
        self.assertEqual((output.read_bytes(), manifest.read_bytes()), expected)
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_cli_is_opt_in_and_retains_source_lock_and_implementation_guards(self):
        captured = {}

        def capture(*args, **options):
            captured.update(options)
            options["verify_before_publish"]()
            return {"fixture": True}

        with patch.object(sys, "argv", ["build_dictionary.py", "--cccedict-headwords-lock", str(self.lock_path),
                "--output", str(self.root / "no-output.sqlite3")]), \
                patch.object(build_cli, "build_dictionary", side_effect=capture), \
                patch.object(build_cli, "verify_source_files"), \
                patch.object(build_cli, "_verify_supplement_snapshot") as verify, redirect_stdout(io.StringIO()):
            self.assertEqual(build_cli.main(), 0)
        selected = captured["source_metadata"]["supplements"]["cccedict_headwords"]
        self.assertFalse(selected["authored_cantonese_readings"])
        self.assertEqual(selected["selection_status"], "candidate source preparation")
        self.assertEqual(selected["build_selection_status"], "selected_opt_in_post_wordnet_autoencoding")
        self.assertEqual(selected["source_lock_sha256"], file_sha256(self.lock_path))
        self.assertEqual(selected["parser_sha256"], file_sha256(Path(reader.__file__)))
        self.assertEqual([call.args[0] for call in verify.call_args_list].count("cccedict_headwords"), 2)
        self.assertFalse((self.root / "no-output.sqlite3").exists())

    def test_cli_prepublication_guard_refuses_changed_headword_lock(self):
        def capture(*args, **options):
            self.lock_path.write_bytes(self.lock_path.read_bytes() + b" ")
            options["verify_before_publish"]()
            self.fail("Changed source lock should refuse publication")

        with patch.object(sys, "argv", ["build_dictionary.py", "--cccedict-headwords-lock", str(self.lock_path)]), \
                patch.object(build_cli, "build_dictionary", side_effect=capture), \
                patch.object(build_cli, "verify_source_files"), patch.object(build_cli, "_verify_supplement_snapshot"), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "changed before publication"):
            build_cli.main()

    def test_mapping_collection_is_headword_provenance_not_authored_tone_inventory(self):
        metadata = mapping_cli.collect_cccedict_headword_source(self.lock_path)
        self.assertFalse(metadata["authored_cantonese_readings"])
        self.assertEqual(metadata["import_stats"]["form_candidates"], 14)
        self.assertEqual(metadata["import_stats"]["quarantined_forms"], 1)
        self.assertNotIn("bases", metadata)
        self.assertNotIn("tones", metadata)
        output, _ = self.build("mapping-binding", headwords=True)
        with closing(sqlite3.connect(output)) as db:
            mapping_cli._bind_cccedict_headword_dictionary(db, metadata)
            self.assertEqual(metadata["dictionary_encoding"]["new_generated_pairs"], 2)
            db.execute("UPDATE entries SET weight=1 WHERE source=?", (HEADWORD_GENERATED_SOURCE,))
            with self.assertRaisesRegex(ValueError, "generated provenance"):
                mapping_cli._bind_cccedict_headword_dictionary(db, metadata)

    def test_mapping_collection_refuses_stale_lock_and_old_dictionary(self):
        metadata = mapping_cli.collect_cccedict_headword_source(self.lock_path)
        baseline, _ = self.build("old-mapping-binding")
        with closing(sqlite3.connect(baseline)) as db, self.assertRaisesRegex(ValueError, "requires its dictionary ledgers"):
            mapping_cli._bind_cccedict_headword_dictionary(db, metadata)
        self.lock_path.write_bytes(self.lock_path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "changed before publication"):
            mapping_cli._verify_cccedict_headword_collection(self.lock_path, metadata)


if __name__ == "__main__":
    unittest.main()
