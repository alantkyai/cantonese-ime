"""Canonical explicit Yue insertion occurs after both existing generation phases."""
import bz2
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from cantonese_ime import cccedict_headwords as headwords
from cantonese_ime import yue_wiktionary as yue
from cantonese_ime.dictionary import build_dictionary, file_sha256, YUE_WIKTIONARY_TABLES
from tools import build_dictionary as build_cli

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "data/vendor/yue-wiktionary/2026-10-01-e09d60b43588"


def tag(name):
    return "{" + yue.XML_NAMESPACE + "}" + name


class CanonicalYueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="canonical-yue-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.rime = self.root / "rime"
        self.rime.mkdir()
        # Both character weights are zero, so an incorrectly early Wiki
        # alternative would qualify and change both generation phases.
        (self.rime / "jyut6ping3.chars.dict.yaml").write_text(
            "---\nname: fixture\n...\n你\tnei5\t0\n好\thou2\t0\n", encoding="utf-8")
        (self.rime / "jyut6ping3.words.dict.yaml").write_text(
            "---\nname: fixture\n...\n你好\tnei5 hou2\t99\n", encoding="utf-8")
        (self.rime / "jyut6ping3.phrase.dict.yaml").write_text(
            "---\nname: fixture\n...\n你好好\n", encoding="utf-8")
        self.cc = self.root / headwords.DATA_FILE
        self.cc.write_text("# CC-CEDICT\n# Published by MDBG\n# " + headwords.LICENSE_DECLARATION
            + "\n# " + headwords.LICENSE_URL + "\n#! version=1\n#! format=ts\n#! charset=UTF-8\n"
            + "#! entries=1\n#! publisher=MDBG\n#! license=" + headwords.LICENSE_URL
            + "\n#! date=2026-10-21T05:46:59Z\n你你好 你你好 [ignored Mandarin] /not a reading/\n", encoding="utf-8")
        self.yue_dir = self.root / "yue"
        self.yue_dir.mkdir()
        (self.yue_dir / yue.INVENTORY_FILE).write_text(json.dumps({"schema_version": 1,
            "bases": ["nei", "hou"], "baseline_database_sha256": "a" * 64}), encoding="utf-8")
        document = ET.Element(tag("mediawiki"), version="0.11",
            attrib={"{http://www.w3.org/XML/1998/namespace}lang": "yue"})
        ET.SubElement(ET.SubElement(document, tag("siteinfo")), tag("dbname")).text = "yuewiktionary"

        def page(identity, title, text, *, namespace=0, revision_id=None):
            item = ET.SubElement(document, tag("page"))
            for name, value in (("title", title), ("ns", str(namespace)), ("id", str(identity))):
                ET.SubElement(item, tag(name)).text = value
            revision = ET.SubElement(item, tag("revision"))
            for name, value in (("id", str(revision_id or identity + 1000)), ("timestamp", "2026-09-30T12:00:00Z"),
                                ("model", "wikitext"), ("format", "text/x-wiki")):
                ET.SubElement(revision, tag(name)).text = value
            ET.SubElement(revision, tag("text"), bytes=str(len(text.encode("utf-8")))).text = text

        for ordinal, (title, revision_id, name, _) in enumerate(yue._TEMPLATE_SPECS.values(), 100):
            page(ordinal, title, (VENDOR / name).read_text("utf-8"), namespace=10, revision_id=revision_id)
        for identity, (text, reading) in enumerate((("你", "nei4"), ("你好", "nei5 hou2"),
                                                    ("你好好", "nei4 hou2 hou2"), ("好你", "hou2 nei5")), 1):
            value = "=={{langue|yue}}==\n{{Yue-rom|" + reading + "}}"
            if identity == 1:
                value += "\n{{Yue-rom|nei5-2}}"
            page(identity, text, value)
        self.archive = self.yue_dir / yue.DATA_FILE
        self.archive.write_bytes(bz2.compress(ET.tostring(document, encoding="utf-8")))

    def build(self, name, *, wiki=False, cc=True, **options):
        supplements = {}
        # Deliberately reverse caller order; the canonical insertion order wins.
        if wiki:
            supplements["yue_wiktionary"] = self.archive
        if cc:
            supplements["cccedict_headwords"] = self.cc
        output = self.root / (name + ".sqlite3")
        stats = build_dictionary(self.rime, output, autoencode_phrases=True, supplements=supplements, **options)
        return output, stats

    def table(self, path, name):
        with closing(sqlite3.connect(path)) as connection:
            columns = connection.execute(f'PRAGMA table_info("{name}")').fetchall()
            order = "1,2" if len(columns) > 1 else "1"
            return connection.execute(f'SELECT * FROM "{name}" ORDER BY {order}').fetchall()

    def test_explicit_append_preserves_all_old_fields_ids_and_generation_review_ledgers(self):
        before, old_stats = self.build("baseline")
        after, stats = self.build("with-yue", wiki=True)
        old_entries = self.table(before, "entries")
        new_entries = self.table(after, "entries")
        self.assertEqual(new_entries[:len(old_entries)], old_entries)
        for name in ("phrase_encodings", "supplement_review", "cccedict_headword_forms", "cccedict_headword_encodings", "syllables"):
            self.assertEqual(self.table(before, name), self.table(after, name), name)
        additions = new_entries[len(old_entries):]
        self.assertEqual(len(additions), 3)
        self.assertTrue(all(row[6:] == (0.0, yue.SOURCE_ID, "supplement") for row in additions))
        self.assertEqual(stats["headword_encoding"], old_stats["headword_encoding"])
        self.assertEqual(stats["yue_wiktionary"]["pre_wiktionary_max_entry_id"], old_entries[-1][0])
        self.assertEqual(stats["yue_wiktionary"]["added_pairs"], 3)
        self.assertEqual(stats["yue_wiktionary"]["new_texts"], 1)
        with closing(sqlite3.connect(after)) as db:
            self.assertEqual(db.execute("SELECT weight,source,origin FROM entries WHERE text='你好'").fetchone(),
                             (99, "jyut6ping3.words.dict.yaml", "explicit"))
            self.assertEqual(db.execute("SELECT reading FROM entries WHERE text='你你好'").fetchall(), [("nei5 nei5 hou2",)])
            self.assertEqual(set(db.execute("SELECT reading FROM entries WHERE text='你好好'")),
                             {("nei5 hou2 hou2",), ("nei4 hou2 hou2",)})
        self.assertNotIn(yue.SOURCE_ID, stats["headword_encoding"]["excluded_encoder_sources"])
        self.assertIn(yue.SOURCE_ID, stats["phrase_translation_policy"]["excluded_sources"])

    def test_complete_raw_reader_ledgers_are_persisted_without_old_review_insertions(self):
        output, stats = self.build("ledgers", wiki=True)
        pages, sections, fields, reviews, counts = [], [], [], [], {}
        expected = list(yue.read_yue_wiktionary_entries(self.archive, stats=counts, page_rows=pages,
            section_rows=sections, field_rows=fields, review_rows=reviews))
        self.assertEqual(len(expected), 4)
        with closing(sqlite3.connect(output)) as db:
            actual_pages = {row[0]: json.loads(row[1]) for row in db.execute(f"SELECT page_id,details_json FROM {YUE_WIKTIONARY_TABLES['pages']}")}
            self.assertEqual(actual_pages, {row["page_id"]: row for row in pages})
            actual_sections = {(row[0], row[1]): json.loads(row[2]) for row in db.execute(f"SELECT page_id,section_ordinal,details_json FROM {YUE_WIKTIONARY_TABLES['sections']}")}
            self.assertEqual(actual_sections, {(row["page_id"], row["language_section_ordinal"]): row for row in sections})
            for role, expected_rows in (("fields", fields), ("reviews", reviews)):
                values = [json.loads(row[0]) for row in db.execute(f"SELECT details_json FROM {YUE_WIKTIONARY_TABLES[role]} ORDER BY id")]
                self.assertEqual(values, expected_rows)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM supplement_review").fetchone(), (0,))
        self.assertEqual(stats["yue_wiktionary"]["ledger_counts"]["reviews"], 1)
        self.assertFalse(stats["yue_wiktionary"]["linguistic_approval"])

    def test_unselected_bytes_unchanged_and_selected_builds_reproduce(self):
        one, old = self.build("old-one")
        two, old_again = self.build("old-two")
        self.assertEqual(one.read_bytes(), two.read_bytes())
        self.assertEqual(old, old_again)
        self.assertNotIn("yue_wiktionary", old)
        self.assertNotIn(yue.SOURCE_ID, old["phrase_translation_policy"]["excluded_sources"])
        with closing(sqlite3.connect(one)) as db:
            self.assertFalse(set(YUE_WIKTIONARY_TABLES.values()) & {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        selected, first = self.build("selected-one", wiki=True)
        repeated, second = self.build("selected-two", wiki=True)
        self.assertEqual(selected.read_bytes(), repeated.read_bytes())
        self.assertEqual(first, second)

    def test_prepublication_failure_preserves_previous_database_and_manifest(self):
        output, _ = self.build("protected")
        manifest = output.with_suffix(".manifest.json")
        original = (output.read_bytes(), manifest.read_bytes())

        def reject():
            self.assertEqual((output.read_bytes(), manifest.read_bytes()), original)
            raise ValueError("source changed")

        with self.assertRaisesRegex(ValueError, "source changed"):
            build_dictionary(self.rime, output, autoencode_phrases=True,
                supplements={"cccedict_headwords": self.cc, "yue_wiktionary": self.archive}, verify_before_publish=reject)
        self.assertEqual((output.read_bytes(), manifest.read_bytes()), original)

    def test_cli_optin_cannot_be_combined_with_no_supplements(self):
        with patch.object(sys, "argv", ["build_dictionary.py", "--no-supplements", "--yue-wiktionary-lock", "unused"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                build_cli.main()
        self.assertEqual(error.exception.code, 2)


class CliSourceSelectionTests(unittest.TestCase):
    def call(self, arguments):
        captured = {}

        def capture(*args, **options):
            captured.update(options)
            options["verify_before_publish"]()
            return {"fixture": True}

        with patch.object(sys, "argv", ["build_dictionary.py", *arguments]), \
                patch.object(build_cli, "build_dictionary", side_effect=capture), \
                patch.object(build_cli, "verify_source_files"), \
                patch.object(build_cli, "_verify_supplement_snapshot"), redirect_stdout(io.StringIO()):
            self.assertEqual(build_cli.main(), 0)
        return captured

    def test_cli_defaults_select_both_reviewed_sources_without_changing_raw_lock_status(self):
        options = self.call([])
        selected = options["source_metadata"]["supplements"]
        self.assertIn("cccedict_headwords", options["supplements"])
        self.assertIn("yue_wiktionary", options["supplements"])
        self.assertEqual(selected["cccedict_headwords"]["build_selection_status"], "selected_default_post_wordnet_autoencoding")
        self.assertEqual(selected["yue_wiktionary"]["build_selection_status"], "selected_default_explicit_post_cccedict")
        self.assertFalse(selected["cccedict_headwords"]["authored_cantonese_readings"])
        self.assertTrue(selected["yue_wiktionary"]["source_explicit_cantonese_readings"])
        self.assertFalse(selected["yue_wiktionary"]["independent_linguistic_approval"])
        self.assertIn("Candidate source preparation", selected["yue_wiktionary"]["selection_status"])
        self.assertEqual(selected["yue_wiktionary"]["source_lock_sha256"],
                         file_sha256(ROOT / "data/supplements/yue-wiktionary.sources.lock.json"))

    def test_cli_diagnostics_omit_only_requested_default_sources(self):
        for arguments, cc, wiki in ((["--no-cccedict-headwords"], False, True),
                (["--no-yue-wiktionary"], True, False),
                (["--no-cccedict-headwords", "--no-yue-wiktionary"], False, False),
                (["--no-supplements"], False, False), (["--no-autoencode"], False, True)):
            with self.subTest(arguments=arguments):
                options = self.call(arguments)
                self.assertEqual("cccedict_headwords" in options["supplements"], cc)
                self.assertEqual("yue_wiktionary" in options["supplements"], wiki)
                if arguments == ["--no-supplements"]:
                    self.assertEqual(options["supplements"], {})
                if arguments == ["--no-autoencode"]:
                    self.assertFalse(options["autoencode_phrases"])

    def test_explicit_lock_selection_and_diagnostic_conflicts_are_distinct(self):
        cc_lock = str(ROOT / "data/supplements/cccedict-headwords.sources.lock.json")
        wiki_lock = str(ROOT / "data/supplements/yue-wiktionary.sources.lock.json")
        options = self.call(["--cccedict-headwords-lock", cc_lock, "--yue-wiktionary-lock", wiki_lock])
        selected = options["source_metadata"]["supplements"]
        self.assertEqual(selected["cccedict_headwords"]["build_selection_status"], "selected_opt_in_post_wordnet_autoencoding")
        self.assertEqual(selected["yue_wiktionary"]["build_selection_status"], "selected_opt_in_explicit_post_cccedict")
        options = self.call(["--no-autoencode", "--yue-wiktionary-lock", wiki_lock])
        self.assertNotIn("cccedict_headwords", options["supplements"])
        self.assertEqual(options["source_metadata"]["supplements"]["yue_wiktionary"]["build_selection_status"],
                         "selected_opt_in_explicit_post_cccedict")
        for args in (["--no-autoencode", "--cccedict-headwords-lock", cc_lock],
                     ["--no-cccedict-headwords", "--cccedict-headwords-lock", cc_lock],
                     ["--no-yue-wiktionary", "--yue-wiktionary-lock", wiki_lock]):
            with self.subTest(arguments=args), patch.object(sys, "argv", ["build_dictionary.py", *args]), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                build_cli.main()
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
