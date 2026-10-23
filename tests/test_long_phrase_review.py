"""Check that the quality-review harness cannot hide hard cases or spelling errors."""
import json
import sqlite3
import unittest

from tools.evaluate_long_phrases import GRID, band, metric, prepare_cases, yale_from_grid


class LongPhraseReviewTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)
        self.connection.execute("CREATE TABLE entries(text TEXT, reading TEXT)")

    def case(self, **changes):
        value = {"id": "unseen", "text": "唔好", "reading": "m4 hou2",
                 "input": "mhou", "user_input": "nghou", "case_role": "control",
                 "category": "negative"}
        value.update(changes)
        return {"cases": [value]}

    def test_unknown_dictionary_phrase_is_retained_without_rank_or_coverage_filter(self):
        cases = prepare_cases(self.case(), self.connection)
        self.assertEqual(len(cases), 1)
        self.assertFalse(cases[0]["stored_text"])
        self.assertFalse(cases[0]["dictionary_reading_partition_found"])
        self.assertEqual(cases[0]["length_band"], "1-3")
        self.assertIn(("habitual_ng_compact", "nghou", "forgiving"), cases[0]["forms"])

    def test_static_reading_partition_does_not_require_whole_phrase_row(self):
        self.connection.executemany("INSERT INTO entries VALUES (?,?)", [("唔", "m4"), ("好", "hou2")])
        case = prepare_cases(self.case(), self.connection)[0]
        self.assertTrue(case["dictionary_reading_partition_found"])
        self.assertFalse(case["stored_pair"])
        self.assertEqual(case["dictionary_reading_partition"], ["唔", "好"])

    def test_spelling_mismatch_is_not_silently_replaced_by_converter(self):
        with self.assertRaisesRegex(ValueError, "Yale spelling mismatch"):
            prepare_cases(self.case(input="nghou"), self.connection)

    def test_habitual_ng_cannot_modify_unrelated_letters(self):
        with self.assertRaisesRegex(ValueError, "unrelated syllables"):
            prepare_cases(self.case(user_input="ngho"), self.connection)

    def test_independent_grid_handles_yale_collisions_and_rejects_unknown_final(self):
        grid = dict(json.loads(GRID.read_text(encoding="utf-8"))["final_grid"])
        for base, expected in (("zi", "ji"), ("jing", "ying"), ("jyu", "yu"), ("zyu", "jyu"),
                               ("heoi", "heui"), ("ngo", "ngo"), ("m", "m")):
            self.assertEqual(yale_from_grid(base, grid), expected)
        with self.assertRaises(ValueError):
            yale_from_grid("qx", grid)

    def test_first90_and_partial_prefix_are_not_relabelled_as_first9(self):
        rows = [{"text_rank": 11, "pair_rank": None, "prefix1_available": True},
                {"text_rank": None, "error": "miss", "prefix1_available": True}]
        result = metric(rows)
        self.assertEqual(result["requests"], 2)
        self.assertEqual(result["top9"], 0)
        self.assertEqual(result["top90"], 1)
        self.assertEqual(result["pair_top90"], 0)
        self.assertEqual(result["target_first_character_in_first9"], 2)
        self.assertEqual(result["errors"], 1)
        self.assertEqual([band(value) for value in (3, 4, 6, 9, 13)], ["1-3", "4-5", "6-8", "9-12", "13+"])


if __name__ == "__main__":
    unittest.main()
