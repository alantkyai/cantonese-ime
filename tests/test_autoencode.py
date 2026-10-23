"""Independent small examples for source-compatible phrase autoencoding."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace
import unittest

from cantonese_ime.autoencode import ScriptAutoencoder


class AutoencodeTests(unittest.TestCase):
    def test_unique_codes_use_explicit_single_syllable_entries(self) -> None:
        encoder = ScriptAutoencoder([("你", "nei5", 100), ("好", "hou2", 100)])
        result = encoder.encode("你好")
        self.assertEqual((result.codes, result.status, result.path_count),
                         (("nei5 hou2",), "encoded_unique", 1))

    def test_objects_and_non_bmp_characters_are_supported(self) -> None:
        encoder = ScriptAutoencoder([SimpleNamespace(text="𠮷", reading="gat1", weight=1)])
        self.assertEqual(encoder.encode("𠮷").codes, ("gat1",))
        self.assertEqual(encoder.encode("𠮷" * 32).status, "encoded_unique")
        self.assertEqual(encoder.encode("𠮷" * 33).status, "too_long")

    def test_multisyllable_words_do_not_become_translation_tokens(self) -> None:
        encoder = ScriptAutoencoder([("你好", "nei5 hou2", 10000),
                                      ("你", "nei5", 1), ("好", "hou3", 1)])
        self.assertEqual(encoder.encode("你好").codes, ("nei5 hou3",))
        self.assertEqual(ScriptAutoencoder([("你好", "nei5 hou2", 100)]).encode("你好").status,
                         "unencodable")

    def test_threshold_is_five_percent_of_total_not_of_maximum(self) -> None:
        encoder = ScriptAutoencoder([("字", "zi1", 95), ("字", "zi2", 5), ("字", "zi3", 1)])
        # 5 is below 5% of101, although it exceeds 5% of95.
        self.assertEqual(encoder.encode("字").codes, ("zi1",))
        exact_boundary = ScriptAutoencoder([("字", "zi1", 95), ("字", "zi2", 5)])
        self.assertEqual(exact_boundary.encode("字").codes, ("zi1", "zi2"))

    def test_zero_total_keeps_all_readings_and_reports_ambiguity(self) -> None:
        encoder = ScriptAutoencoder([("字", "zi6", 0), ("字", "zi1", 0)])
        result = encoder.encode("字")
        self.assertEqual(result.codes, ("zi1", "zi6"))
        self.assertEqual(result.status, "encoded_ambiguous")

    def test_reading_sort_is_lexical_and_duplicate_first_weight_wins(self) -> None:
        encoder = ScriptAutoencoder([("字", "zi6", 95), ("字", "zi2", 1),
                                      ("字", "zi2", 1000), ("字", "zi1", 5)])
        self.assertEqual(encoder.encode("字").codes, ("zi6",))
        self.assertEqual(encoder.metadata()["duplicate_single_rows"], 1)

    def test_longest_matching_text_token_is_visited_first(self) -> None:
        encoder = ScriptAutoencoder([("甲乙", "gaa1", 1), ("甲", "gaap3", 1),
                                      ("乙", "jyut3", 1), ("丙", "bing2", 1)])
        result = encoder.encode("甲乙丙")
        self.assertEqual(result.codes, ("gaa1 bing2", "gaap3 jyut3 bing2"))
        self.assertEqual(result.status, "encoded_ambiguous")

    def test_all_paths_follow_longest_token_then_lexical_code_order(self) -> None:
        encoder = ScriptAutoencoder([("甲", "gaap3", 1), ("甲", "gaa1", 1),
                                      ("乙", "jyut6", 1), ("乙", "jyut3", 1)])
        expected = tuple(" ".join(parts) for parts in product(("gaa1", "gaap3"), ("jyut3", "jyut6")))
        self.assertEqual(encoder.encode("甲乙").codes, expected)

    def test_exactly_32_complete_paths_are_conservatively_truncated(self) -> None:
        encoder = ScriptAutoencoder([("甲", "gaa1", 1), ("甲", "gaap3", 1)])
        result = encoder.encode("甲" * 5)
        self.assertEqual((len(result.codes), result.path_count, result.status, result.reason),
                         (32, 32, "truncated", "path_limit"))

    def test_more_than_32_paths_preserves_first_32_rime_emissions(self) -> None:
        encoder = ScriptAutoencoder([("甲", "gaa1", 1), ("甲", "gaap3", 1)])
        expected = tuple(" ".join(parts) for parts in product(("gaa1", "gaap3"), repeat=6))[:32]
        result = encoder.encode("甲" * 6)
        self.assertEqual(result.codes, expected)
        self.assertEqual(result.status, "truncated")

    def test_unencodable_suffix_does_not_blow_up_the_search(self) -> None:
        encoder = ScriptAutoencoder([("甲", "gaa1", 1), ("甲", "gaap3", 1)])
        result = encoder.encode("甲" * 31 + "?")
        self.assertEqual(result.status, "unencodable")
        self.assertEqual(result.codes, ())
        self.assertLessEqual(result.work_count, 32)

    def test_work_guard_never_labels_partial_results_unique(self) -> None:
        encoder = ScriptAutoencoder([("甲", "gaa1", 1)], max_work=1)
        result = encoder.encode("甲乙")
        self.assertEqual((result.status, result.reason, result.codes),
                         ("truncated", "work_limit", ()))

    def test_invalid_data_and_invalid_phrases_are_rejected(self) -> None:
        for row in [("", "zi1", 1), ("字", "zi", 1), ("字", "zi1", -1),
                    ("字", "zi1", float("nan")), ("字", "zi1", float("inf"))]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                ScriptAutoencoder([row])
        encoder = ScriptAutoencoder([("字", "zi1", 1)])
        for phrase in ("", None, "\ud800"):
            with self.subTest(phrase=repr(phrase)), self.assertRaises(ValueError):
                encoder.encode(phrase)

    def test_metadata_records_revision_policy_and_license(self) -> None:
        metadata = ScriptAutoencoder([("字", "zi1", 1)]).metadata()
        self.assertEqual(metadata["license"], "BSD-3-Clause")
        self.assertEqual(len(metadata["commit"]), 40)
        self.assertEqual((metadata["max_phrase_codepoints"], metadata["max_encoder_paths"]), (32, 32))


if __name__ == "__main__":
    unittest.main()
