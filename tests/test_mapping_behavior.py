"""Self-tests ensure the mechanical checker can detect real decoder mistakes."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime import Engine as RealEngine
from tools.check_mapping_behavior import exercise, exercise_paging, observed_tones


def artifacts():
    inventory = {"syllables": [
        {"base": "bou", "observed_tones_by_source": {"synthetic_fixture": ["2"]}},
        {"base": "nei", "observed_tones_by_source": {"synthetic_fixture": ["5"]}},
    ]}
    spellings = {"aliases": [
        {"spelling": "bou", "canonical": "bou"},
        {"spelling": "bo", "canonical": "bou"},
        {"spelling": "nei", "canonical": "nei"},
    ]}
    return inventory, spellings


class MappingBehaviorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mapping-checker-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def test_strict_prefix_completion_is_not_mistaken_for_alias_leakage(self):
        result = exercise(*artifacts(), self.directory)
        self.assertEqual(result["counts"].get("failures", 0), 0)
        self.assertTrue(all(row["strict_direct_isolation"] for row in result["relations"]))

    def test_an_exported_relation_missing_from_the_decoder_is_detected(self):
        inventory, spellings = artifacts()
        spellings["aliases"].append({"spelling": "qoo", "canonical": "nei"})
        result = exercise(inventory, spellings, self.directory)
        row = next(row for row in result["relations"] if row["spelling"] == "qoo")
        self.assertFalse(row["forgiving_untoned"])
        self.assertFalse(row["forgiving_toned"])
        self.assertGreater(result["counts"]["failures"], 0)

    def test_a_wrong_tone_is_detected_even_if_page_and_legacy_agree(self):
        class WrongToneEngine(RealEngine):
            @staticmethod
            def corrupt(raw, candidate):
                return replace(candidate, reading="nei6") if raw == "nei5" and candidate.text == "⟦base:nei⟧" else candidate

            def lookup_page(self, raw, **kwargs):
                page = super().lookup_page(raw, **kwargs)
                return replace(page, candidates=tuple(self.corrupt(raw, candidate) for candidate in page.candidates))

            def lookup(self, raw, *args, **kwargs):
                return [self.corrupt(raw, candidate) for candidate in super().lookup(raw, *args, **kwargs)]

        with patch("tools.check_mapping_behavior.Engine", WrongToneEngine):
            result = exercise(*artifacts(), self.directory)
        self.assertTrue(any(row["kind"] == "numeric_closure_or_tone_violation" for row in result["failures"]))
        self.assertTrue(any(not row["strict_direct_isolation"] for row in result["relations"] if row["canonical"] == "nei"))

    def test_observed_tones_are_required_instead_of_inventing_all_six(self):
        with self.assertRaises(ValueError):
            observed_tones({"syllables": [{"base": "nei", "observed_tones_by_source": {}}]})
        with self.assertRaises(ValueError):
            observed_tones({"syllables": [{"base": "nei", "observed_tones_by_source": {"fixture": ["7"]}}]})

    def test_missing_identity_relation_is_rejected(self):
        inventory, spellings = artifacts()
        spellings["aliases"] = spellings["aliases"][:-1]
        with self.assertRaisesRegex(ValueError, "identity relation"):
            exercise(inventory, spellings, self.directory)

    def test_paging_control_reaches_all_257_unique_homophones(self):
        result = exercise_paging(self.directory)
        self.assertTrue(result["passed"])
        self.assertTrue(all(row.get("last_target_rank", 257) == 257 for row in result["cases"]))


if __name__ == "__main__":
    unittest.main()
