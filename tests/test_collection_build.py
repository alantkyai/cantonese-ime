"""Collection integration: explicit, generated and unresolved data stay distinct."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime.dictionary import build_dictionary


HEADER = "---\nname: collection_fixture\n...\n"


class CollectionBuildTests(unittest.TestCase):
    def test_full_phrase_accounting_does_not_publish_partial_or_missing_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jyut6ping3.chars.dict.yaml").write_text(
                HEADER + "你\tnei5\t10\n我\tngo5\t10\n好\thou2\t10\n好\thou3\t10\n", encoding="utf-8")
            (root / "jyut6ping3.words.dict.yaml").write_text(HEADER + "你好\tnei5 hou2\t1\n", encoding="utf-8")
            phrases = ["你好", "你我", "好好", "好" * 6, "你嗎", "我" * 33]
            (root / "jyut6ping3.phrase.dict.yaml").write_text(HEADER + "\n".join(phrases) + "\n", encoding="utf-8")
            output = root / "out.sqlite3"
            manifest = build_dictionary(root, output, autoencode_phrases=True)
            with closing(sqlite3.connect(output)) as connection:
                records = connection.execute("SELECT text,status,codes_json FROM phrase_encodings").fetchall()
                states = {text: state for text, state, _ in records}
                self.assertEqual(states, {
                    "你好": "already_explicit", "你我": "encoded_unique", "好好": "encoded_ambiguous",
                    "好" * 6: "truncated", "你嗎": "unencodable", "我" * 33: "too_long",
                })
                self.assertEqual(manifest["autoencoding"]["input_rows"], len(phrases))
                self.assertEqual(manifest["source_stats"]["jyut6ping3.phrase.dict.yaml"]["unencoded_input_rows"], len(phrases))
                self.assertNotIn("skipped_missing_reading", manifest["source_stats"]["jyut6ping3.phrase.dict.yaml"])
                self.assertEqual(manifest["unresolved_phrase_rows"], 3)
                for text in ("好" * 6, "你嗎", "我" * 33):
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM entries WHERE text=?", (text,)).fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT origin FROM entries WHERE text='你我'").fetchone()[0], "generated")
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM entries WHERE text='好好'").fetchone()[0], 4)
                self.assertEqual(connection.execute("SELECT origin FROM entries WHERE text='你好'").fetchone()[0], "explicit")
                self.assertEqual(len(json.loads(next(codes for text, _, codes in records if text == "好" * 6))), 32)

    def test_supplemental_pronunciations_and_description_rows_are_auditable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jyut6ping3.chars.dict.yaml").write_text(HEADER + "你\tnei5\t10\n", encoding="utf-8")
            lshk = root / "list.tsv"
            lshk.write_text("CH\tUCODE\tJP\tINIT\tFINL\tTONE\tDESC\tDESC_JP\n"
                            "你\tU+4F60\tnei5\tn\tei\t5\t\tnei5\n"
                            "好\tU+597D\thou2\th\tou\t2\t\thou2\n"
                            "㓁\tU+34C1\t\t\t\t\t禿頭穴\ttuk1 tau4 jyut6\n", encoding="utf-8")
            output = root / "out.sqlite3"
            manifest = build_dictionary(root, output, supplements={"lshk": lshk})
            self.assertEqual(manifest["supplement_stats"]["lshk"]["added_pairs"], 1)
            self.assertEqual(manifest["supplement_stats"]["lshk"]["overlapping_pairs"], 1)
            self.assertEqual(manifest["supplement_review_count"], 1)
            with closing(sqlite3.connect(output)) as connection:
                self.assertEqual(connection.execute("SELECT origin,weight FROM entries WHERE text='好'").fetchone(), ("supplement", 0))
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM entries WHERE text='㓁'").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT status FROM supplement_review").fetchone()[0], "description_only")

    def test_generated_builds_have_repeatable_semantic_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jyut6ping3.chars.dict.yaml").write_text(HEADER + "你\tnei5\t10\n我\tngo5\t10\n", encoding="utf-8")
            (root / "jyut6ping3.phrase.dict.yaml").write_text(HEADER + "你我\n", encoding="utf-8")
            first = build_dictionary(root, root / "first.sqlite3", autoencode_phrases=True)
            second = build_dictionary(root, root / "second.sqlite3", autoencode_phrases=True)
            self.assertEqual(first["semantic_sha256"], second["semantic_sha256"])
            self.assertEqual(first["database_sha256"], second["database_sha256"])

    def test_text_frequency_does_not_promote_unknown_supplement_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jyut6ping3.chars.dict.yaml").write_text(HEADER + "住\tzyu6\t100%\n你\tnei5\t100%\n", encoding="utf-8")
            (root / "essay-cantonese.txt").write_text("住\t1000000\n你\t1000000\n", encoding="utf-8")
            (root / "jyut6ping3.phrase.dict.yaml").write_text(HEADER + "住你\n", encoding="utf-8")
            wordshk = root / "wordslist.json"
            wordshk.write_text(json.dumps({"住": ["zi6"]}, ensure_ascii=False), encoding="utf-8")
            output = root / "out.sqlite3"
            manifest = build_dictionary(root, output, supplements={"wordshk": wordshk}, autoencode_phrases=True)
            with closing(sqlite3.connect(output)) as connection:
                self.assertEqual(connection.execute("SELECT weight,origin FROM entries WHERE text='住' AND reading='zi6'").fetchone(), (0, "supplement"))
                self.assertEqual(connection.execute("SELECT reading FROM entries WHERE text='住你'").fetchall(), [("zyu6 nei5",)])
            self.assertEqual(manifest["autoencoding"]["encoded_unique"], 1)

    def test_phrase_attestation_and_provisional_character_fallback_have_distinct_roles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jyut6ping3.chars.dict.yaml").write_text(HEADER + "返\tfaan2\t10\n到\tdou2\t10\n你\tnei5\t10\n", encoding="utf-8")
            (root / "jyut6ping3.phrase.dict.yaml").write_text(HEADER + "返到\n你水\n", encoding="utf-8")
            typeduck = root / "typeduck.dict.yaml"
            typeduck.write_text("---\nname: jyut6ping3\n...\n返到\tfaan1 dou3\t785.1%\n你哋\tnei5 dei6\t100%\n", encoding="utf-8")
            wordshk = root / "wordslist.json"
            wordshk.write_text(json.dumps({"你哋": ["nei5 dei6"]}, ensure_ascii=False), encoding="utf-8")
            unihan = root / "Unihan_Readings.txt"
            unihan.write_text("U+6C34\tkCantonese\tseoi2\n", encoding="utf-8")
            output = root / "out.sqlite3"
            manifest = build_dictionary(root, output, supplements={
                "unihan": unihan, "typeduck": typeduck, "wordshk": wordshk,
            }, autoencode_phrases=True)
            self.assertEqual(manifest["supplement_order"], ["wordshk", "typeduck", "unihan"])
            with closing(sqlite3.connect(output)) as connection:
                self.assertEqual(connection.execute("SELECT reading,source,weight FROM entries WHERE text='返到'").fetchall(), [("faan1 dou3", "typeduck:principal", 0)])
                self.assertEqual(connection.execute("SELECT source FROM entries WHERE text='你哋'").fetchone()[0], "words.hk:wordlist")
                self.assertEqual(connection.execute("SELECT reading,source FROM entries WHERE text='水'").fetchone(), ("seoi2", "unihan:kCantonese"))
                self.assertEqual(dict(connection.execute("SELECT text,status FROM phrase_encodings")), {"返到": "already_explicit", "你水": "unencodable"})
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM entries WHERE text='你水'").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
