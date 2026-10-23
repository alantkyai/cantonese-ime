"""Project-authored fixtures exercise external-corpus accounting and freezing."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import evaluate_hkcancor as evaluation


def transcript(lines: list[str]) -> str:
    return "<info>fixture</info><sent><sent_head>A:</sent_head><sent_tag>\n" + "\n".join(lines) + "\n</sent_tag><sent_tran></sent_tran></sent>"


class HKCanCorEvaluationTests(unittest.TestCase):
    def parse(self, lines: list[str]) -> list[dict]:
        return evaluation.parse_transcript(transcript(lines), "fixture")

    def test_markup_damage_fails_instead_of_silently_losing_turns(self) -> None:
        good = transcript(["你/r/nei5/"])
        for bad in (good + "<sent>", good.replace("</sent>", ""),
                    good.replace("</sent_tag>", ""), good.replace("<sent_head>A:</sent_head>", "")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                evaluation.parse_transcript(bad, "broken")

    def test_unsupported_source_notation_is_not_repaired_or_bridged(self) -> None:
        turns = self.parse(["你/r/nei5/", "○/q/lam6/@", "好/a/hou2/", "。/w/VQ1/",
                            "英語/x/english0/", "嗎/y/maa3/"])
        result = evaluation.collect_from_turns(turns, 10)
        self.assertEqual([token["status"] for token in turns[0]["tokens"]],
                         ["eligible", "unsupported_source_annotation", "eligible", "punctuation", "unsupported_reading", "eligible"])
        self.assertEqual(result["accounting"]["tokens"], 6)
        self.assertEqual(result["strata"]["speech_span"]["eligible_distinct_pairs"], 0)
        self.assertEqual({case["text"] for case in result["cases"]}, {"你", "好", "嗎"})
        self.assertEqual(result["exclusion_examples"]["unsupported_source_annotation"][0]["raw"], "○/q/lam6/@")

    def test_source_pos_punctuation_is_respected_even_for_canonical_han(self) -> None:
        turns = self.parse(["你/r/nei5/", "我哋/w/ngo5dei6/", "好/a/hou2/"])
        result = evaluation.collect_from_turns(turns, 10)
        self.assertEqual(turns[0]["tokens"][1]["status"], "punctuation")
        self.assertFalse(any(case["unit"] == "speech_span" for case in result["cases"]))

    def test_unknown_canonical_syllables_and_count_mismatch_are_retained(self) -> None:
        # Shape-valid syllables must not be filtered by the engine's inventory.
        turns = self.parse(["字/n/xyz1/", "兩字/n/ji6/"])
        result = evaluation.collect_from_turns(turns, 6)
        self.assertEqual(result["accounting"]["eligible_token_character_syllable_mismatches"], 1)
        self.assertIn(("字", "xyz1"), {(case["text"], case["reading"]) for case in result["cases"]})
        self.assertIn(("字兩字", "xyz1 ji6"), {(case["text"], case["reading"]) for case in result["cases"]})

    def test_long_span_is_rejected_whole_instead_of_clipped(self) -> None:
        turns = self.parse(["你/r/nei5/"] * 17)
        result = evaluation.collect_from_turns(turns, 6)
        self.assertEqual(result["accounting"]["speech_span:excluded_over_input_limit"], 1)
        self.assertEqual(result["strata"]["speech_span"]["eligible_distinct_pairs"], 0)
        self.assertEqual(result["cases"][0]["source_occurrences"], 17)

    def test_selection_uses_source_types_not_frequency_or_dictionary(self) -> None:
        turns = self.parse(["你/r/nei5/", "好/a/hou2/", "。/w/VQ1/", "字/n/zi6/"])
        with patch.object(evaluation, "Engine", side_effect=AssertionError("No engine may be opened")):
            result = evaluation.collect_from_turns(turns, 2)
            repeated = evaluation.collect_from_turns(turns * 4, 2)
        self.assertEqual([case["id"] for case in result["cases"]], [case["id"] for case in repeated["cases"]])
        self.assertEqual([case["source_occurrences"] for case in repeated["cases"]], [4, 4])
        self.assertEqual(result["cases"][0]["first_occurrence"]["raw_tokens"], ["你/r/nei5/", "好/a/hou2/"])

    def test_exact_text_and_exact_pair_metrics_are_separate(self) -> None:
        rows = [{"text_rank": 1, "pair_rank": None, "candidate_count": 90, "elapsed_ms": 2},
                {"text_rank": 10, "pair_rank": 10, "candidate_count": 90, "elapsed_ms": 3}]
        report = evaluation.metric(rows)
        self.assertEqual((report["text_top1"], report["pair_top1"]), (1, 0))
        self.assertEqual((report["text_top9"], report["pair_top9"]), (1, 0))
        self.assertEqual((report["text_top90"], report["pair_top90"]), (2, 1))

    def test_corpus_freezing_and_source_output_protection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            corpus = {"artifact_kind": "hkcancor_external_corpus", "cases": ["first"]}
            evaluation.write_json(path, corpus, protected=[])
            evaluation.write_json(path, corpus, protected=[])
            changed = copy.deepcopy(corpus)
            changed["cases"].append("second")
            with self.assertRaises(ValueError):
                evaluation.write_json(path, changed, protected=[])
            self.assertEqual(json.loads(path.read_text()), corpus)
            with self.assertRaises(ValueError):
                evaluation.write_json(path, corpus, protected=[Path(directory)])


if __name__ == "__main__":
    unittest.main()
