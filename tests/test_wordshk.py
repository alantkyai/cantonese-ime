"""words.hk import tests use project-authored miniature JSON data only."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from cantonese_ime.wordshk import read_wordshk_entries


class WordsHkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cantonese-wordshk-test-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "wordslist.json"

    def write(self, data: object) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_explicit_readings_preserve_tones_source_and_zero_weight(self) -> None:
        self.write({"你好": ["nei5  hou2"], "𠮷": ["gat1"], "BB": ["bi4 bi1"]})
        rows = list(read_wordshk_entries(self.path))
        self.assertEqual([(r.text, r.reading) for r in rows],
                         [("你好", "nei5 hou2"), ("𠮷", "gat1"), ("BB", "bi4 bi1")])
        self.assertEqual((rows[0].base_reading, rows[0].compact, rows[0].syllable_count),
                         ("nei hou", "neihou", 2))
        self.assertTrue(all(r.weight == 0 and r.source == "words.hk:wordlist" for r in rows))

    def test_multiple_explicit_readings_are_retained_without_choosing_one(self) -> None:
        self.write({"好": ["hou2", "hou3"]})
        self.assertEqual([r.reading for r in read_wordshk_entries(self.path)], ["hou2", "hou3"])

    def test_multilingual_notation_and_missing_tones_are_quarantined_intact(self) -> None:
        invalid = ["si1 !zhi1", "!", "NEI5", "nei", "nei7", "nei55", None, 3]
        self.write({"字": invalid + ["zi6"]})
        reviews, stats = [], {}
        rows = list(read_wordshk_entries(self.path, stats=stats, review_rows=reviews))
        self.assertEqual([r.reading for r in rows], ["zi6"])
        self.assertEqual([r["raw_reading"] for r in reviews], invalid)
        self.assertTrue(all(r["reason"] == "non_jyutping_reading" for r in reviews))
        self.assertEqual(stats["source_reading_rows"], stats["accepted_entries"] + stats["quarantined_rows"])

    def test_malformed_variant_flags_and_templates_are_quarantined(self) -> None:
        self.write({"床**": ["cong4"], "⋯食⋯": ["sik6"], "食…": ["sik6"], "食...": ["sik6"]})
        reviews = []
        self.assertEqual(list(read_wordshk_entries(self.path, review_rows=reviews)), [])
        self.assertEqual([r["text"] for r in reviews], ["床**", "⋯食⋯", "食…", "食..."])
        self.assertEqual(reviews[0]["reason"], "malformed_variant_annotation")
        self.assertTrue(all(r["reason"] == "template_annotation" for r in reviews[1:]))

    def test_documented_trailing_variant_marker_is_normalized_with_provenance(self) -> None:
        self.write({"床*": ["cong4"], "床": ["cong4"], "床*具": ["cong4 geoi6"]})
        reviews, stats = [], {}
        rows = list(read_wordshk_entries(self.path, stats=stats, review_rows=reviews))
        self.assertEqual([(r.text, r.reading) for r in rows], [("床", "cong4")])
        normalized = next(r for r in reviews if r["status"] == "normalized_variant")
        self.assertEqual((normalized["raw_text"], normalized["normalized_text"], normalized["source_flag"]),
                         ("床*", "床", "variant"))
        self.assertEqual(stats["normalized_variant_rows"], 1)
        self.assertEqual(stats["duplicate_entries"], 1)
        self.assertEqual(stats["quarantined_rows"], 1)

    def test_duplicate_readings_are_counted_and_full_accounting_balances(self) -> None:
        self.write({"字": ["zi6", "zi6", "zi2", "!"]})
        stats = {}
        rows = list(read_wordshk_entries(self.path, stats=stats))
        self.assertEqual(len(rows), 2)
        self.assertEqual(stats["duplicate_entries"], 1)
        self.assertEqual(stats["source_reading_rows"],
                         stats["accepted_entries"] + stats["duplicate_entries"] + stats["quarantined_rows"])

    def test_duplicate_json_keys_and_wrong_shapes_fail(self) -> None:
        self.path.write_text('{"字":["zi6"],"字":["zi2"]}', encoding="utf-8")
        with self.assertRaises(ValueError):
            list(read_wordshk_entries(self.path))
        for wrong in (["zi6"], {"字": "zi6"}, {"字": None}):
            with self.subTest(wrong=wrong):
                self.write(wrong)
                with self.assertRaises(ValueError):
                    list(read_wordshk_entries(self.path))

    def test_invalid_text_is_quarantined_without_normalization(self) -> None:
        self.write({" 字": ["zi6"], "字\n": ["zi6"], "": ["zi6"]})
        reviews = []
        self.assertEqual(list(read_wordshk_entries(self.path, review_rows=reviews)), [])
        self.assertTrue(all(r["reason"] == "invalid_text" for r in reviews))


if __name__ == "__main__":
    unittest.main()
