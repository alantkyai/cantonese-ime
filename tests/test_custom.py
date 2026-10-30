"""Per-user custom phrases and spelling aliases against the mini fixture lexicon."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from cantonese_ime.custom import (
    MAX_CUSTOM_BYTES, MAX_RULES, parse_custom, parse_rule, preview_rule, read_custom, rule_spelling)
from cantonese_ime.engine import Engine
from tests.test_engine import create_fixture_database


class ParseCustomTests(unittest.TestCase):
    def test_phrases_aliases_comments_and_invalid_lines(self) -> None:
        entries = parse_custom(
            "﻿# comment\n\nhh 曈曈\nHH\t瞳瞳\nhh 曈曈\nlay = NEI\nmoon=mun\n"
            "h1 數字\nhh\n= mun\nmoon = mun5\nab " + "字" * 65 + "\nok a\x01b\n"
        )
        self.assertEqual(entries.phrases, {"hh": ("曈曈", "瞳瞳")})
        self.assertEqual(entries.aliases, (("lay", "nei"), ("moon", "mun")))
        self.assertEqual(entries.invalid_lines, 6)

    def test_rules_need_matching_wildcard_shapes(self) -> None:
        entries = parse_custom("k* = g*\n*OON = *un\n*oo* = *u*\nk* = *g\n*a = *a\noo = u\n*x = y\nk* = g*\n")
        self.assertEqual(entries.rules, (("initial", "k", "g"), ("final", "oon", "un"), ("inside", "oo", "u")))
        self.assertEqual(entries.aliases, (("oo", "u"),))        # plain alias; the engine ignores target u
        self.assertEqual(entries.invalid_lines, 3)              # mismatched, identical and half-starred
        self.assertIsNone(parse_rule("toolongx*", "g*"))
        many = "".join(f"*{chr(97 + i // 26)}{chr(97 + i % 26)} = *u\n" for i in range(MAX_RULES + 3))
        self.assertEqual(len(parse_custom(many).rules), MAX_RULES)

    def test_rule_spelling_matches_whole_initials_and_finals(self) -> None:
        self.assertEqual(rule_spelling(("initial", "k", "g"), "g", "au"), "kau")
        self.assertIsNone(rule_spelling(("initial", "k", "g"), "gw", "ong"))    # gw is its own initial
        self.assertEqual(rule_spelling(("final", "oon", "un"), "m", "un"), "moon")
        self.assertIsNone(rule_spelling(("final", "oon", "un"), "j", "yun"))
        self.assertEqual(rule_spelling(("inside", "oo", "u"), "g", "au"), "gaoo")  # inside rules reach glides
        self.assertIsNone(rule_spelling(("inside", "oo", "u"), "g", "o"))
        self.assertIsNone(rule_spelling(("final", "x" * 12, "un"), "m", "un"))    # longer than the trie allows

    def test_missing_file_is_empty_and_oversized_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.txt"
            self.assertEqual(read_custom(path).phrases, {})
            path.write_bytes(b"a " + b"x" * MAX_CUSTOM_BYTES)
            with self.assertRaises(ValueError):
                read_custom(path)


class EngineCustomTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="cantonese-custom-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.database = self.directory / "lexicon.sqlite3"
        create_fixture_database(self.database)
        self.custom = self.directory / "custom.txt"

    def engine(self, learning: bool = False) -> Engine:
        engine = Engine(self.database, custom_path=self.custom,
                        learning_path=self.directory / "learning.json" if learning else None)
        self.addCleanup(engine.close)
        return engine

    def write(self, text: str) -> None:
        self.custom.write_text(text, encoding="utf-8")
        # Some filesystems have coarse mtimes; force a distinct stamp.
        stamp = self.custom.stat().st_mtime_ns + 1_000_000_000 * (getattr(self, "_writes", 0) + 1)
        self._writes = getattr(self, "_writes", 0) + 1
        os.utime(self.custom, ns=(stamp, stamp))

    def texts(self, engine: Engine, raw: str) -> list[str]:
        return [candidate.text for candidate in engine.lookup(raw)]

    def test_custom_phrases_lead_for_exact_input_only(self) -> None:
        self.write("hh 曈曈\nhh 瞳瞳\nneihou 你好嗎\n")
        engine = self.engine()
        self.assertEqual(self.texts(engine, "hh")[:2], ["曈曈", "瞳瞳"])
        self.assertEqual(self.texts(engine, "neihou")[0], "你好嗎")
        self.assertIn("你好", self.texts(engine, "neihou"))
        self.assertNotIn("曈曈", self.texts(engine, "h"))
        candidate = engine.lookup("hh")[0]
        self.assertEqual((candidate.reading, candidate.match_type), ("", "custom"))

    def test_alias_is_forgiving_only_and_reloads_without_restart(self) -> None:
        engine = self.engine()
        self.assertNotIn("你", self.texts(engine, "nee"))
        self.write("nee = nei\nzz = notasyllable\n")
        self.assertEqual(self.texts(engine, "nee")[0], "你")
        self.assertEqual(engine.lookup("nee")[0].match_type, "exact")
        self.assertEqual(self.texts(engine, "neehou")[0], "你好")
        self.assertEqual(engine.lookup("nee", mode="jyutping"), [])
        self.assertEqual(self.texts(engine, "zz"), [])
        self.write("hh 曈曈\n")
        self.assertNotIn("你", self.texts(engine, "nee"))
        self.assertEqual(self.texts(engine, "hh"), ["曈曈"])
        self.custom.unlink()
        self.assertEqual(self.texts(engine, "hh"), [])

    def test_alias_target_may_be_a_known_spelling_but_never_another_alias(self) -> None:
        engine = self.engine()
        # lay is a built-in forgiving spelling of nei; nee then reaches 你.
        self.write("nee = lay\nnnn = nee\n")
        self.assertEqual(self.texts(engine, "nee")[0], "你")
        self.assertEqual(engine.lookup("nee")[0].match_type, "fuzzy")
        self.assertEqual(self.texts(engine, "nnn"), [])

    def test_rules_add_spellings_for_every_matching_syllable(self) -> None:
        self.write("x* = h*\n*ee* = *ei*\n")
        engine = self.engine()
        self.assertEqual(self.texts(engine, "xou")[0], "好")          # initial rule
        self.assertIn("好樂", self.texts(engine, "xoulok"))           # rule spellings compose
        self.assertEqual(self.texts(engine, "nee")[0], "你")          # inside rule
        self.assertEqual(engine.lookup("nee", mode="jyutping"), [])
        self.write("")
        self.assertNotIn("好", self.texts(engine, "xou"))           # removing the rule removes the spellings

    def test_a_colliding_rule_spelling_ranks_below_the_real_reading(self) -> None:
        # *ou = *aau turns baau (包) into "bou", which already spells 保/煲.
        self.write("*ou = *aau\n")
        texts = self.texts(self.engine(), "bou")
        self.assertIn("包", texts)
        self.assertLess(min(texts.index("保"), texts.index("煲")), texts.index("包"))

    def test_preview_lists_affected_syllables_and_collisions(self) -> None:
        result = preview_rule(self.database, "*ou = *aau")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"], [{"syllable": "baau", "spelling": "bou", "example": "包", "collides": True}])
        fresh = preview_rule(self.database, "x* = h*")
        self.assertEqual({row["syllable"] for row in fresh["rows"]}, {"him", "hoeng", "hou"})
        self.assertEqual(fresh["collisions"], 0)
        with self.assertRaises(ValueError):
            preview_rule(self.database, "oo = u")

    def test_unreadable_file_keeps_last_entries_and_lookups_continue(self) -> None:
        self.write("hh 曈曈\n")
        engine = self.engine()
        self.custom.write_bytes(b"hh \xff\xfe\n")
        os.utime(self.custom, ns=(1, 1))
        self.assertEqual(self.texts(engine, "hh"), ["曈曈"])
        self.assertIsNotNone(engine.custom_error)
        self.assertIn("你好", self.texts(engine, "neihou"))

    def test_custom_phrase_is_not_written_to_learning_memory(self) -> None:
        self.write("hh 曈曈\n")
        engine = self.engine(learning=True)
        engine.record_selection("hh", engine.lookup("hh")[0])
        self.assertNotIn("曈曈", (self.directory / "learning.json").read_text(encoding="utf-8")
                         if (self.directory / "learning.json").exists() else "")


if __name__ == "__main__":
    unittest.main()
