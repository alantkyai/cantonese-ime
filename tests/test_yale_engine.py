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
