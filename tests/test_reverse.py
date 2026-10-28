"""Reverse lookup against the mini fixture lexicon; read-only."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from cantonese_ime.__main__ import main
from cantonese_ime.reverse import reverse_lookup, tsv_lines, typing_hints
from tests.test_engine import create_fixture_database


class TypingHintTests(unittest.TestCase):
    def test_single_syllable_hints_follow_engine_costs(self) -> None:
        # Yale counts as free, like the engine's prefer_yale; costly aliases are omitted.
        self.assertEqual(typing_hints("soeng2"), ("soeng", "seung", "seong", "sheung"))
        self.assertEqual(typing_hints("nei5"), ("nei", "nay"))
        self.assertNotIn("lay", typing_hints("nei5"))
        self.assertEqual(typing_hints("tung4"), ("tung",))

    def test_word_hints_join_toneless_and_yale_forms(self) -> None:
        self.assertEqual(typing_hints("nei5 hou2"), ("neihou",))
        self.assertEqual(typing_hints("ceot1 heoi3"), ("ceotheoi", "cheutheui"))
        self.assertEqual(typing_hints(""), ())


class ReverseLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="cantonese-reverse-test-")
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "lexicon.sqlite3"
        create_fixture_database(self.database)

    def test_character_readings_are_ordered_by_weight(self) -> None:
        result = reverse_lookup(self.database, " 好 ")
        self.assertEqual(result["text"], "好")
        self.assertEqual([item["reading"] for item in result["readings"]], ["hou2", "hou3"])
        self.assertEqual(result["characters"], [])

    def test_word_lists_whole_reading_then_each_distinct_character(self) -> None:
        result = reverse_lookup(self.database, "你好")
        self.assertEqual([item["reading"] for item in result["readings"]], ["nei5 hou2"])
        self.assertEqual([c["text"] for c in result["characters"]], ["你", "好"])
        self.assertEqual(reverse_lookup(self.database, "你你")["characters"][0]["text"], "你")
        self.assertEqual(len(reverse_lookup(self.database, "你你")["characters"]), 1)
        self.assertEqual(tsv_lines(result)[0], "word\t你好\tnei5 hou2\t3000\tneihou")

    def test_unknown_text_has_no_readings_and_invalid_text_raises(self) -> None:
        self.assertEqual(reverse_lookup(self.database, "曈")["readings"], [])
        for bad in ("", "   ", "字" * 33, "a\x01"):
            with self.assertRaises(ValueError):
                reverse_lookup(self.database, bad)
        with self.assertRaises(FileNotFoundError):
            reverse_lookup(self.database.with_name("missing.sqlite3"), "你")

    def test_cli_tsv_output_and_error_status(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["reverse", "你", "--tsv", "--dictionary", str(self.database)]), 0)
        rows = [line.split("\t") for line in output.getvalue().splitlines()]
        self.assertEqual(rows[0][:3], ["word", "你", "nei5"])
        self.assertIn("nei", rows[0][4].split(","))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["reverse", "", "--dictionary", str(self.database)]), 2)


if __name__ == "__main__":
    unittest.main()
