"""Post-autoencoding Wordnet append semantics; only isolated tiny fixtures."""
from contextlib import closing, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime.dictionary import build_dictionary, file_sha256
from tools import build_dictionary as build_cli


def word(identity, text, readings):
    return (f'<LexicalEntry id="{identity}"><Lemma writtenForm="{text}"/>'
            + "".join(f'<Form writtenForm="{reading}"/>' for reading in readings) + '</LexicalEntry>')


class DictionaryWordnetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dictionary-wordnet-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "rime"
        self.source.mkdir()
        (self.source / "jyut6ping3.chars.dict.yaml").write_text(
            "---\nname: fixture\n...\n三\tsaam1\t100\n話\twaa6\t77\n", encoding="utf-8")
        (self.source / "jyut6ping3.phrase.dict.yaml").write_text(
            "---\nname: fixture\n...\n三三\n話話\n", encoding="utf-8")
        (self.source / "essay-cantonese.txt").write_text("三三\t40\n話話\t7\n", encoding="utf-8")
        self.vendor = self.root / "wordnet"
        self.vendor.mkdir()
        self.xml = self.vendor / "cantown.xml"
        (self.vendor / "parser-attested-bases.json").write_text(json.dumps({
            "schema_version": 1, "bases": ["saam", "waa", "nei", "hou"],
            "baseline_database_sha256": "a" * 64,
        }), encoding="utf-8")

    def write_wordnet(self, entries, english=""):
        sibling = ('<Lexicon id="cantown-en" language="en" version="1.0" '
                   'license="https://creativecommons.org/licenses/by/4.0/">' + english + '</Lexicon>') if english else ""
        self.xml.write_text('<LexicalResource><Lexicon id="cantown-yue" language="yue" version="1.0" '
                            'license="https://creativecommons.org/licenses/by/4.0/">' + entries
                            + '</Lexicon>' + sibling + '</LexicalResource>', encoding="utf-8")

    def build(self, name, *, wordnet=False, **options):
        output = self.root / (name + ".sqlite3")
        stats = build_dictionary(self.source, output, autoencode_phrases=True,
                                 supplements={"wordnet": self.xml} if wordnet else None, **options)
        return output, stats

    def rows(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return dict(((row[1], row[2]), row) for row in connection.execute(
                "SELECT id,text,reading,base_reading,compact,syllable_count,weight,source,origin FROM entries"))

    def phrase_rows(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("SELECT * FROM phrase_encodings ORDER BY source,line").fetchall()

    def test_existing_pairs_ids_fields_weights_and_phrase_ledgers_are_unchanged(self):
        baseline, before_stats = self.build("baseline")
        self.write_wordnet(word("new-char", "三", ["saam3"])
                           + word("new-word", "三三", ["saam3 saam3", "saam1 saam1"])
                           + word("overlap", "話", ["waa6", "waa2"])
                           + word("other-word", "話話", ["waa2 waa2", "waa6 waa6"]))
        expanded, stats = self.build("expanded", wordnet=True)
        before, after = self.rows(baseline), self.rows(expanded)
        self.assertTrue(before.keys() <= after.keys())
        for pair, old in before.items():
            self.assertEqual(after[pair], old, pair)
        self.assertEqual(self.phrase_rows(expanded), self.phrase_rows(baseline))
        self.assertEqual(stats["autoencoding"], before_stats["autoencoding"])
        self.assertEqual(stats["post_autoencoding_supplements"], ["wordnet"])
        self.assertEqual(stats["supplement_stats"]["wordnet"]["added_pairs"], 4)
        self.assertEqual(stats["supplement_stats"]["wordnet"]["overlapping_pairs"], 3)
        new_rows = [after[pair] for pair in after.keys() - before.keys()]
        self.assertTrue(all(row[6:] == (0.0, "wordnet:cantown", "supplement") for row in new_rows))
        self.assertTrue(all(row[0] > max(old[0] for old in before.values()) for row in new_rows))
        # A zero-weight authored overlap cannot relabel or reweight a generated
        # 40-count baseline pair, or an explicit 77-count character pair.
        self.assertEqual(after[("三三", "saam1 saam1")][6:], (40.0, "jyut6ping3.phrase.dict.yaml:autoencoded", "generated"))
        self.assertEqual(after[("話", "waa6")][6:], (77.0, "jyut6ping3.chars.dict.yaml", "explicit"))

    def test_new_char_readings_neither_feed_encoder_nor_mark_old_phrases_explicit(self):
        self.write_wordnet(word("a", "三", ["saam3"]) + word("b", "三三", ["saam3 saam3"]))
        output, stats = self.build("encoding", wordnet=True)
        rows = self.rows(output)
        # Feeding this character into the encoder would introduce mixed-tone
        # saam1/saam3 alternatives. Only the preserved baseline + authored pair exist.
        self.assertEqual({reading for text, reading in rows if text == "三三"}, {"saam1 saam1", "saam3 saam3"})
        with closing(sqlite3.connect(output)) as connection:
            status, codes, paths = connection.execute(
                "SELECT status,codes_json,path_count FROM phrase_encodings WHERE text='三三'").fetchone()
        self.assertEqual((status, json.loads(codes), paths), ("encoded_unique", ["saam1 saam1"], 1))
        self.assertIn("wordnet:cantown", stats["phrase_translation_policy"]["excluded_sources"])
        self.assertEqual(rows[("三三", "saam3 saam3")][7:], ("wordnet:cantown", "supplement"))

    def test_form_blank_normalization_exclusion_and_review_accounting_survive_build(self):
        self.write_wordnet(word("a", "話", ["waa6", "  WAA6  ", "waa2", "", "waa7", "yat6", "nei5 hou2"]),
                           english=word("en-a", "hello", [""]))
        output, stats = self.build("accounting", wordnet=True)
        source = stats["supplement_stats"]["wordnet"]
        self.assertEqual((source["accepted_entries"], source["added_pairs"], source["overlapping_pairs"]), (2, 1, 1))
        self.assertEqual(source["form_candidates"], source["accepted_entries"] + source["duplicate_entries"]
                         + source["blank_forms"] + source["quarantined_forms"])
        self.assertEqual(source["lexical_entries_total"], source["input_rows"] + source["excluded_lexical_entries"])
        self.assertEqual((source["blank_forms"], source["normalized_reading_forms"], source["excluded_forms"]), (1, 1, 1))
        self.assertEqual(source["insertion_phase"], "post_autoencoding")
        with closing(sqlite3.connect(output)) as connection:
            review = [json.loads(row[0]) for row in connection.execute("SELECT details_json FROM supplement_review ORDER BY id")]
            self.assertEqual(json.loads(connection.execute("SELECT value FROM metadata WHERE key='supplement_stats'").fetchone()[0])["wordnet"], source)
        self.assertEqual(len(review), source["review_records"])
        self.assertEqual(stats["supplement_review_count"], len(review))
        self.assertEqual({row["status"] for row in review}, {"quarantined", "missing_reading", "informational", "excluded"})
        self.assertTrue(all(row["source_sha256"] == file_sha256(self.xml) and row["entry_id"] and row["form_ordinal"] for row in review))

    def test_diagnostic_no_autoencoding_still_adds_only_admitted_explicit_pairs(self):
        self.write_wordnet(word("a", "你好", ["nei5 hou2"]) + word("bad", "日", ["yat6"]))
        output = self.root / "no-auto.sqlite3"
        stats = build_dictionary(self.source, output, supplements={"wordnet": self.xml}, autoencode_phrases=False)
        rows = self.rows(output)
        self.assertIn(("你好", "nei5 hou2"), rows)
        self.assertNotIn(("日", "yat6"), rows)
        self.assertFalse(any(row[-1] == "generated" for row in rows.values()))
        with closing(sqlite3.connect(output)) as connection:
            syllables = {row[0] for row in connection.execute("SELECT base FROM syllables")}
        self.assertEqual(syllables, {"saam", "waa", "nei", "hou"})
        self.assertEqual(stats["syllable_count"], len(syllables))
        self.assertEqual(stats["schema_version"], 2)

    def test_two_clean_fixture_builds_have_identical_bytes_semantics_and_ids(self):
        self.write_wordnet(word("z", "話話", ["waa2 waa2"])
                           + word("a", "三三", ["saam3 saam3"]) + word("m", "話", ["waa2"]))
        first, first_stats = self.build("first", wordnet=True)
        second, second_stats = self.build("second", wordnet=True)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first_stats, second_stats)
        self.assertEqual(self.rows(first), self.rows(second))
        self.assertEqual(first_stats["database_sha256"], hashlib.sha256(first.read_bytes()).hexdigest())

    def test_prepublication_failure_preserves_database_and_manifest(self):
        output, _ = self.build("protected")
        manifest = output.with_suffix(".manifest.json")
        original, original_manifest = output.read_bytes(), manifest.read_bytes()
        self.write_wordnet(word("new", "話", ["waa2"]))
        calls = []

        def refuse():
            calls.append(True)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(manifest.read_bytes(), original_manifest)
            raise ValueError("Source changed before publication")

        with self.assertRaisesRegex(ValueError, "Source changed"):
            build_dictionary(self.source, output, supplements={"wordnet": self.xml}, autoencode_phrases=True,
                             verify_before_publish=refuse)
        self.assertEqual(calls, [True])
        self.assertEqual((output.read_bytes(), manifest.read_bytes()), (original, original_manifest))
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_default_cli_selects_and_pins_wordnet_and_rechecks_before_publication(self):
        captured = {}

        def fake_build(*args, **options):
            captured.update(options)
            options["verify_before_publish"]()
            return {"fixture": True}

        output = self.root / "not-built.sqlite3"
        with patch.object(sys, "argv", ["build_dictionary.py", "--output", str(output)]), \
                patch.object(build_cli, "build_dictionary", side_effect=fake_build), \
                patch.object(build_cli, "verify_source_files") as primary_verify, \
                patch.object(build_cli, "_verify_supplement_snapshot") as supplement_verify, redirect_stdout(io.StringIO()):
            self.assertEqual(build_cli.main(), 0)
        self.assertIn("wordnet", captured["supplements"])
        metadata = captured["source_metadata"]["supplements"]["wordnet"]
        project = Path(__file__).resolve().parents[1]
        self.assertEqual(metadata["source_lock_sha256"], file_sha256(project / "data/supplements/wordnet.sources.lock.json"))
        self.assertEqual(metadata["parser_sha256"], file_sha256(project / "cantonese_ime/wordnet.py"))
        self.assertEqual((metadata["source_id"], metadata["license"], metadata["insertion_phase"]),
                         ("wordnet:cantown", "CC-BY-4.0", "post_autoencoding"))
        self.assertEqual(metadata["build_selection_status"], "selected_default_post_autoencoding")
        self.assertEqual(metadata["selection_status"], json.loads(
            (project / "data/supplements/wordnet.sources.lock.json").read_text(encoding="utf-8"))["selection_status"])
        self.assertEqual(primary_verify.call_count, 2)
        self.assertEqual([call.args[0] for call in supplement_verify.call_args_list].count("wordnet"), 2)
        self.assertFalse(output.exists())

    def test_cli_source_lock_change_is_rejected_by_prepublication_callback(self):
        project = Path(__file__).resolve().parents[1]
        copy = self.root / "source-lock.json"
        copy.write_bytes((project / "data/sources.lock.json").read_bytes())

        def fake_build(*args, **options):
            copy.write_bytes(copy.read_bytes() + b" ")
            options["verify_before_publish"]()
            self.fail("Changed source lock should refuse publication")

        with patch.object(sys, "argv", ["build_dictionary.py", "--lock", str(copy), "--output", str(self.root / "not-built.sqlite3")]), \
                patch.object(build_cli, "build_dictionary", side_effect=fake_build), \
                patch.object(build_cli, "verify_source_files"), patch.object(build_cli, "_verify_supplement_snapshot"), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "changed before publication"):
            build_cli.main()


if __name__ == "__main__":
    unittest.main()
