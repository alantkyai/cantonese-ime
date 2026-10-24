"""Optional habitual ng input uses canonical readings and synthetic memory."""
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime import Engine
from cantonese_ime.mappings import spelling_variants, yale_ascii_variants


class HabitualNgInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="habitual-ng-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.database = self.folder / "dictionary.sqlite3"
        self.memory = self.folder / "synthetic-learning.json"
        self.rows = [
            ("唔", "m4", 6_000_000), ("唔", "ng4", 0),
            ("吳", "ng4", 100_000), ("五", "ng5", 10_000),
            ("好", "hou2", 100_000), ("係", "hai6", 90_000),
            ("咁", "gam3", 80_000), ("你", "nei5", 70_000),
            ("妳", "nei5", 700), ("我", "ngo5", 300_000),
            ("唔好", "m4 hou2", 20_000), ("唔係", "m4 hai6", 19_000),
            ("字", "zi6", 100_000), ("而", "ji4", 100_000),
            ("型", "jing4", 100_000), ("字型", "zi6 jing4", 30_000),
            ("唔唔唔唔", "m4 m4 m4 m4", 10),
        ]
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript("""
                CREATE TABLE entries(text TEXT, reading TEXT, base_reading TEXT, weight REAL);
                CREATE INDEX entries_base ON entries(base_reading);
            """)
            db.executemany("INSERT INTO entries VALUES(?,?,?,?)", [
                (text, reading, " ".join(token[:-1] for token in reading.split()), weight)
                for text, reading, weight in self.rows
            ])
            db.commit()

    def engine(self, **kwargs):
        engine = Engine(self.database, **kwargs)
        self.addCleanup(engine.close)
        return engine

    def find(self, engine, raw, text):
        return next(candidate for candidate in engine.lookup(raw, limit=90) if candidate.text == text)

    def test_whole_syllable_alias_matches_stored_words_and_mixed_inputs(self):
        engine = self.engine(syllabic_m_as_ng=True)
        for raw in ("nghou", "ng'hou", "ng4hou2", "ng4'hou2", "ngho"):
            with self.subTest(raw=raw):
                chosen = self.find(engine, raw, "唔好")
                self.assertEqual(chosen.reading, "m4 hou2")
                self.assertEqual(chosen.match_type, "fuzzy")
        for raw in ("ngngngng", "ngmngm", "ng'm'ng'm"):
            with self.subTest(raw=raw):
                chosen = self.find(engine, raw, "唔唔唔唔")
                self.assertEqual(chosen.reading, "m4 m4 m4 m4")
        reading = "m m m m"
        self.assertEqual(sum(reading in bucket for bucket in engine._habitual_ng_readings.values()), 1)

    def test_apostrophes_and_numeric_tones_constrain_the_alias(self):
        engine = self.engine(syllabic_m_as_ng=True)
        for raw in ("n'ghou", "ngh'ou", "n'g'hou"):
            with self.subTest(raw=raw):
                self.assertFalse(any(candidate.text == "唔好" and candidate.reading == "m4 hou2"
                                     for candidate in engine.lookup(raw, limit=90)))
        for raw in ("ng5hou2", "ng5'hou2"):
            with self.subTest(raw=raw):
                self.assertFalse(any(candidate.reading.startswith("m4")
                                     for candidate in engine.lookup(raw, limit=90)))
        self.assertEqual(self.find(engine, "ng4hou2", "唔好").reading, "m4 hou2")
        self.assertEqual(self.find(engine, "m4hou2", "唔好").reading, "m4 hou2")
        self.assertEqual(self.find(engine, "ngo5", "我").reading, "ngo5")
        # The digit closes ying as one supported syllable; yi+ng is not a
        # substitute parse of that explicitly toned syllable.
        self.assertEqual(engine.lookup("ying4")[0].text, "型")
        self.assertNotIn("而唔", [candidate.text for candidate in engine.lookup("ying4", limit=90)])

    def test_canonical_ng_alternatives_and_embedded_nasal_inputs_remain(self):
        engine = self.engine(syllabic_m_as_ng=True)
        rows = engine.lookup("ng4", limit=90)
        self.assertTrue(any(candidate.text == "吳" and candidate.reading == "ng4" for candidate in rows))
        self.assertTrue(any(candidate.text == "唔" and candidate.reading == "m4" for candidate in rows))
        self.assertEqual(self.find(engine, "neinghou", "你唔好").reading, "nei5 m4 hou2")
        self.assertEqual(self.find(engine, "ngonghaigam", "我唔係咁").reading, "ngo5 m4 hai6 gam3")
        self.assertEqual(engine.lookup("jiying")[0].text, "字型")

    def test_alias_cost_is_not_zeroed_by_yale_preference_or_exported_as_yale(self):
        original_spellings = spelling_variants("m")
        for prefer_yale in (False, True):
            with self.subTest(prefer_yale=prefer_yale):
                engine = self.engine(syllabic_m_as_ng=True, prefer_yale=prefer_yale)
                self.assertEqual(engine._input_spellings("m", "forgiving")["ng"], .8)
                self.assertEqual(engine._input_spellings("m", "jyutping"), {"m": 0.0})
                self.assertEqual(engine._effective_spelling_penalty("forgiving", "ng", "m", 0), .8)
                chosen = self.find(engine, "nghou", "唔好")
                self.assertAlmostEqual(chosen.score, 1000 - 6 * .8 + math.log1p(20_000))
                self.assertEqual(engine._yale_word_forms["m"], (("m", 0.0),))
        self.assertEqual(spelling_variants("m"), original_spellings)
        self.assertNotIn("ng", original_spellings)
        self.assertEqual(yale_ascii_variants("m"), ("m",))

    def test_default_disabled_and_strict_modes_keep_exact_candidate_pools(self):
        default = self.engine()
        disabled = self.engine(syllabic_m_as_ng=False)
        enabled = self.engine(syllabic_m_as_ng=True)
        for raw in ("ng", "nghou", "ng'haigam", "mhou", "ng4hou2", "ng5hou2", "ying", "ying4", "jiying", "ngo5"):
            for mode in ("forgiving", "jyutping"):
                with self.subTest(raw=raw, mode=mode):
                    before = default.lookup_page(raw, page_size=90, mode=mode)
                    self.assertEqual(disabled.lookup_page(raw, page_size=90, mode=mode), before)
                    if mode == "jyutping":
                        self.assertEqual(enabled.lookup_page(raw, page_size=90, mode=mode), before)
        self.assertNotIn(("m", .8), enabled._variants["jyutping"].get("ng", ()))

    def test_new_m_reading_selection_persists_and_reuses_an_unstored_phrase(self):
        engine = self.engine(syllabic_m_as_ng=True, learning_path=self.memory)
        selected = self.find(engine, "ngnei", "唔妳")
        self.assertEqual(selected.reading, "m4 nei5")
        self.assertNotEqual(engine.lookup("ngongnei")[0].text, "我唔妳")
        engine.record_selection("ngnei", selected)
        self.assertEqual(engine.lookup("ngnei")[0].text, "唔妳")
        self.assertEqual(engine.lookup("ngongnei")[0].text, "我唔妳")
        self.assertEqual(engine.lookup("ngneihou")[0].text, "唔妳好")
        stored = json.loads(self.memory.read_text(encoding="utf-8"))
        self.assertEqual(stored["schema_version"], 2)
        self.assertEqual([(row["input"], row["reading"]) for row in stored["selections"]], [("ngnei", "m4 nei5")])
        reopened = self.engine(syllabic_m_as_ng=True, learning_path=self.memory)
        self.assertEqual(reopened.lookup("ngongnei")[0].text, "我唔妳")
        self.assertEqual(reopened.lookup("ngneihou")[0].text, "唔妳好")

    def test_old_ng4_memory_keeps_its_reading_and_lookup_never_rewrites_history(self):
        legacy = self.engine(learning_path=self.memory)
        old = self.find(legacy, "ng", "唔")
        self.assertEqual(old.reading, "ng4")
        legacy.record_selection("ng", old)
        before = hashlib.sha256(self.memory.read_bytes()).hexdigest()
        enabled = self.engine(syllabic_m_as_ng=True, learning_path=self.memory)
        chosen = enabled.lookup("ng")[0]
        self.assertEqual((chosen.text, chosen.reading), ("唔", "ng4"))
        self.assertIn("你唔好", [candidate.text for candidate in enabled.lookup("neinghou")])
        self.assertEqual(hashlib.sha256(self.memory.read_bytes()).hexdigest(), before)

    def test_configuration_requires_a_boolean(self):
        for value in (None, 0, 1, "yes"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "syllabic_m_as_ng must be a boolean"):
                    Engine(self.database, syllabic_m_as_ng=value)


if __name__ == "__main__":
    unittest.main()
