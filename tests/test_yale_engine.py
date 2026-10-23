"""Whole-word Yale retrieval, collisions, paging and native length contracts."""

from contextlib import closing
from itertools import product
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime import CompositionCapacityError, Engine, PaginationCapacityError
from cantonese_ime.native_protocol import (
    LearningRequest, LookupRequest, decode_learning_request, decode_request,
    encode_learning_request, encode_request,
)
from cantonese_ime.session import Session


class YaleEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="yale-engine-")
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "dictionary.sqlite3"
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript("""
                CREATE TABLE entries (
                    text TEXT NOT NULL, reading TEXT NOT NULL,
                    base_reading TEXT NOT NULL, weight REAL NOT NULL,
                    UNIQUE(text,reading)
                );
                CREATE INDEX base_lookup ON entries(base_reading);
            """)

    def engine(self, rows, *, learning=False):
        with closing(sqlite3.connect(self.database)) as db:
            db.executemany(
                "INSERT INTO entries VALUES (?,?,?,?)",
                [(text, reading, " ".join(t[:-1] for t in reading.split()), weight)
                 for text, reading, weight in rows],
            )
            db.commit()
        engine = Engine(self.database, learning_path=(
            self.database.with_suffix(".learning.json") if learning else None))
        self.addCleanup(engine.close)
        return engine

    def test_plain_yale_words_and_valid_boundaries_commit(self):
        engine = self.engine([
            ("火炬", "fo2 geoi6", 100), ("張文", "zoeng1 man4", 90),
            ("出發", "ceot1 faat3", 80), ("香港", "hoeng1 gong2", 70),
            ("月", "jyut6", 60), ("車", "ce1", 50),
        ])
        for raw, text in (("fogeui", "火炬"), ("fo'geui", "火炬"),
                          ("jeungman", "張文"), ("cheutfaat", "出發"),
                          ("heunggong", "香港"), ("yut", "月"), ("che", "車")):
            with self.subTest(raw=raw):
                session = Session(engine)
                for key in raw:
                    session.handle_key(key)
                self.assertEqual(session.candidates[0].text, text)
                self.assertEqual(session.handle_key("1").committed, text)
        for raw in ("fog'eui", "f'ogeui"):
            self.assertNotIn("火炬", [c.text for c in engine.lookup(raw)])
        self.assertNotIn("火炬", [c.text for c in engine.lookup("fogeui", mode="jyutping")])
        self.assertEqual(engine.lookup("fogeoi", mode="jyutping")[0].text, "火炬")

    def test_full_stored_yale_word_survives_ambiguous_frontier(self):
        # Each preceding jau can be canonical jau or zau. More than 96 live
        # stored-prefix paths compete before the final syllable; the target's
        # Yale reading must still be retrieved despite its larger alias cost.
        rows = []
        for index, bases in enumerate(product(("jau", "zau"), repeat=9)):
            rows.append((chr(0x4E00 + index), " ".join(b + "1" for b in bases) + " hou2", 0))
        target = rows[-1][0]
        engine = self.engine(rows)
        raw = "jau" * 9 + "hou"
        all_texts = set()
        offset = 0
        while True:
            page = engine.lookup_page(raw, offset=offset, page_size=90)
            all_texts.update(c.text for c in page.candidates)
            if page.next_offset is None:
                break
            offset = page.next_offset
        self.assertIn(target, all_texts)
        # Yale y- for canonical j- remains distinct from Yale j- for z-.
        self.assertEqual(engine.lookup("yau" * 9 + "hou")[0].text, rows[0][0])

    def test_yale_homophones_remain_selectable_on_later_pages(self):
        rows = [(chr(0x5000 + i), "geoi6", i) for i in range(125)]
        engine = self.engine(rows)
        actual = set()
        offset = 0
        while True:
            page = engine.lookup_page("geui", offset=offset, page_size=9)
            actual.update(c.text for c in page.candidates)
            if page.next_offset is None:
                break
            offset = page.next_offset
        self.assertEqual(actual, {row[0] for row in rows})

    def test_yale_words_take_priority_over_conflicting_jyutping_spellings(self):
        engine = self.engine([("尖", "zim1", 0), ("染", "jim5", 1_000_000)], learning=True)
        self.assertEqual(engine.lookup("jim")[0].text, "尖")
        self.assertEqual(engine.lookup("jim", mode="jyutping")[0].text, "染")
        # This is a preference, not deletion of the other spelling convention.
        alternate = next(c for c in engine.lookup("jim") if c.text == "染")
        engine.record_selection("jim", alternate)
        self.assertEqual(engine.lookup("jim")[0].text, "染")
        with Engine(self.database, prefer_yale=False) as mixed:
            self.assertEqual(mixed.lookup("jim")[0].text, "染")

    def composition_rows(self):
        # A known word must retain its Yale interpretation when it becomes a
        # constituent, even though no complete phrase is stored. Frequent
        # literal Jyutping ji/jo competitors previously won after a prefix.
        return [
            ("基準", "aa1", 300_000_000),
            ("啲", "di1", 2_103_563), ("字型", "zi6 jing4", 1601),
            ("而", "ji4", 490407), ("以", "ji5", 180000),
            ("依", "ji1", 170000), ("二", "ji6", 160000),
            ("凝", "jing4", 121200), ("影", "jing2", 41022),
            ("型", "jing4", 29365), ("應", "jing1", 23937),
            ("換", "wun6", 100000), ("碗", "wun2", 98000),
            ("玩", "wun6", 96000), ("喲", "jo1", 10000),
            ("咗", "zo2", 60000), ("左", "zo2", 50000),
            ("改變", "goi2 bin3", 1000), ("火炬", "fo2 geoi6", 100),
            ("掉", "deu6", 1000), ("你", "nei5", 100),
        ]

    def test_yale_word_remains_first_page_constituent_in_unstored_phrases(self):
        engine = self.engine(self.composition_rows())
        self.assertEqual(engine.lookup("jiying")[0].text, "字型")
        self.assertEqual(engine.lookup("dijiying")[0].text, "啲字型")
        for raw, text in (("wunjodijiying", "換咗啲字型"),
                          ("goibinjiying", "改變字型"),
                          ("dideeu", "啲掉")):
            with self.subTest(raw=raw):
                page = engine.lookup_page(raw, page_size=9)
                self.assertIn(text, [candidate.text for candidate in page.candidates])
                target = next(candidate for candidate in page.candidates if candidate.text == text)
                self.assertEqual(target.match_type, "composed")

    def test_yale_constituent_cost_preserves_strict_and_mixed_modes(self):
        engine = self.engine(self.composition_rows())
        with Engine(self.database, prefer_yale=False) as mixed:
            # Strict canonical spelling and scores remain independent of the
            # optional Yale preference, including complete tone requests.
            for raw in ("dizijing", "wunzodizijing", "di1zi6jing4"):
                self.assertEqual(engine.lookup(raw, mode="jyutping", limit=90),
                                 mixed.lookup(raw, mode="jyutping", limit=90))
            preferred = next(c for c in engine.lookup("dijiying", limit=90) if c.text == "啲字型")
            legacy = next(c for c in mixed.lookup("dijiying", limit=90) if c.text == "啲字型")
            self.assertAlmostEqual(preferred.score - legacy.score, 6 * (0.8 + 0.45))
            self.assertNotEqual(mixed.lookup("dijiying")[0].text, "啲字型")
            # Arbitrary forgiving aliases still incur their original costs:
            # nei -> lei is not the validated Yale spelling of nei.
            preferred_other = next(c for c in engine.lookup("dilei", limit=90) if c.text == "啲你")
            legacy_other = next(c for c in mixed.lookup("dilei", limit=90) if c.text == "啲你")
            self.assertEqual(preferred_other.score, legacy_other.score)

    def test_yale_constituent_tones_boundaries_and_partial_completions(self):
        engine = self.engine(self.composition_rows())
        for raw in ("di'ji'ying", "di1ji6ying4", "di1'ji6'ying4"):
            with self.subTest(raw=raw):
                self.assertIn("啲字型", [c.text for c in engine.lookup(raw)])
        for raw in ("di1ji4ying4", "di1ji6ying2", "di'j'iying"):
            with self.subTest(raw=raw):
                self.assertNotIn("啲字型", [c.text for c in engine.lookup(raw, limit=90)])
        # Keep original alias metadata: prefix preselection uses it to find
        # incomplete aliases, even when complete Yale edges have zero cost.
        for raw, text in (("jiy", "字型"), ("fogeu", "火炬")):
            with self.subTest(raw=raw):
                match = next(c for c in engine.lookup(raw, limit=90) if c.text == text)
                self.assertEqual(match.match_type, "completion")
                with Engine(self.database, prefer_yale=False) as mixed:
                    legacy = next(c for c in mixed.lookup(raw, limit=90) if c.text == text)
                    self.assertEqual(legacy.match_type, "completion")

    def test_full_input_choice_still_overrides_yale_constituent_preference(self):
        engine = self.engine(self.composition_rows(), learning=True)
        self.assertEqual(engine.lookup("dijiying")[0].text, "啲字型")
        alternate = next(c for c in engine.lookup("dijiying", limit=90) if c.text == "啲而凝")
        engine.record_selection("dijiying", alternate)
        self.assertEqual(engine.lookup("dijiying")[0].text, "啲而凝")
        self.assertEqual(engine.lookup("jiying")[0].text, "字型")
        self.assertEqual(engine.lookup("goibinjiying")[0].text, "改變字型")

    def test_learned_only_yale_constituent_uses_same_cost_after_row_cap(self):
        # The zero-weight target is beyond the per-reading 90-row bound.
        # Only the learned-span index can restore it in this new combination;
        # an ordinary dictionary arc cannot mask a wrong restored-span cost.
        rows = [(chr(0x5000 + i), "zi6", 100000 - i) for i in range(100)]
        rows += [("字", "zi6", 0), ("啲", "di1", 1000)]
        engine = self.engine(rows, learning=True)
        self.assertNotIn("啲字", [c.text for c in engine.lookup("diji", limit=90)])
        chosen = next(c for c in engine.lookup_page("ji", offset=90, page_size=90).candidates
                      if c.text == "字")
        engine.record_selection("ji", chosen)
        preferred = next(c for c in engine.lookup("diji") if c.text == "啲字")
        with Engine(self.database, learning_path=self.database.with_suffix(".learning.json"),
                    prefer_yale=False) as mixed:
            legacy = next(c for c in mixed.lookup("diji") if c.text == "啲字")
            self.assertAlmostEqual(preferred.score - legacy.score, 6 * 0.8)
        self.assertNotIn("啲字", [c.text for c in engine.lookup("di1ji4", limit=90)])

    def test_long_word_yale_input_and_learning_exceed_old_cap(self):
        text = "香港" * 10
        reading = " ".join(["hoeng1 gong2"] * 10)
        raw = "heunggong" * 10
        self.assertGreater(len(raw), 64)
        engine = self.engine([(text, reading, 100)], learning=True)
        candidate = engine.lookup(raw)[0]
        self.assertEqual(candidate.text, text)
        engine.record_selection(raw, candidate)
        self.assertEqual(engine.lookup(raw)[0].text, text)
        request = LookupRequest(17, 0, 0, 9, raw)
        self.assertEqual(decode_request(encode_request(request)), request)
        learning = LearningRequest(18, 0, raw, text, reading)
        self.assertEqual(decode_learning_request(encode_learning_request(learning)), learning)
        session = Session(engine)
        for key in raw:
            session.handle_key(key)
        self.assertEqual(session.handle_key("1").committed, text)

    def test_stored_word_survives_large_composition_with_explicit_tail_limit(self):
        # Multiple equal-cost tone paths duplicate each composed output. The
        # optional 220-position composition exhausts its work limit, while an
        # independently stored full-input word is already a valid candidate.
        rows = [(text, "a" + str(tone), 0) for text in ("甲", "乙") for tone in range(1, 7)]
        rows.append(("已存長詞", " ".join(["a1"] * 220), 1000))
        engine = self.engine(rows)
        raw = "a" * 220
        page = engine.lookup_page(raw)
        self.assertIn("已存長詞", [candidate.text for candidate in page.candidates])
        self.assertTrue(page.completion_truncated)
        self.assertIsNotNone(page.next_offset)
        with self.assertRaises(PaginationCapacityError):
            engine.lookup_page(raw, offset=page.next_offset)

    def test_large_composition_without_stored_word_keeps_capacity_error(self):
        rows = [(text, "a" + str(tone), 0) for text in ("甲", "乙") for tone in range(1, 7)]
        engine = self.engine(rows)
        with self.assertRaises(CompositionCapacityError):
            engine.lookup("a" * 220)


if __name__ == "__main__":
    unittest.main()
