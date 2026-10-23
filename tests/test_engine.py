"""Independent engine contract tests using a deliberately small dictionary.

The fixture contains ambiguous readings and lacks the whole sentence used by
the composition test. No network, downloaded dictionary, or Windows IME is
needed. Run with ``python -m unittest discover -s tests -v``.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from cantonese_ime import Candidate, Engine
from cantonese_ime.engine import CandidatePage, PaginationCapacityError


FIXTURE = Path(__file__).parent / "fixtures" / "mini_dictionary.json"


def create_fixture_database(path: Path) -> None:
    entries = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            BEGIN;
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                reading TEXT NOT NULL,
                base_reading TEXT NOT NULL,
                compact TEXT NOT NULL,
                syllable_count INTEGER NOT NULL,
                weight REAL NOT NULL,
                source TEXT NOT NULL,
                UNIQUE(text, reading)
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX entries_compact ON entries(compact);
            CREATE INDEX entries_base_reading ON entries(base_reading);
            CREATE INDEX entries_text ON entries(text);
            """
        )
        for item in entries:
            syllables = item["reading"].split()
            base = [syllable[:-1] for syllable in syllables]
            connection.execute(
                """INSERT INTO entries
                   (text, reading, base_reading, compact, syllable_count, weight, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["text"],
                    item["reading"],
                    " ".join(base),
                    "".join(base),
                    len(syllables),
                    item["weight"],
                    "project-authored-test-fixture",
                ),
            )
        connection.commit()


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cantonese-engine-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.database = self.directory / "dictionary.sqlite3"
        create_fixture_database(self.database)
        self.engine = Engine(self.database)
        close = getattr(self.engine, "close", None)
        if callable(close):
            self.addCleanup(close)

    def texts(self, raw: str, *, mode: str = "forgiving", limit: int = 9) -> list[str]:
        return [candidate.text for candidate in self.engine.lookup(raw, mode=mode, limit=limit)]

    def paging_engine(self, *, learning_path: Path | None = None, completions: bool = False) -> Engine:
        database = self.directory / "paging.sqlite3"
        create_fixture_database(database)
        rows = []
        for index in range(240):
            text = chr(0x6000 + index)
            reading = "zi4 hou2" if completions else "zi4"
            rows.append((text, reading, 240 - index))
            if not completions and index % 7 == 0:
                # Equal-score alternative pronunciations must not take visible
                # slots or change the public per-text tie winner across pages.
                rows.append((text, "zi6", 240 - index))
        if not completions:
            rows.extend((("飽和甲", "zi4", 1e100), ("飽和乙", "zi4", 1e200)))
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("BEGIN")
            for text, reading, weight in rows:
                bases = [part[:-1] for part in reading.split()]
                connection.execute(
                    """INSERT INTO entries
                       (text,reading,base_reading,compact,syllable_count,weight,source)
                       VALUES (?,?,?,?,?,?, 'synthetic-paging')""",
                    (text, reading, " ".join(bases), "".join(bases), len(bases), weight),
                )
            connection.commit()
        engine = Engine(database, learning_path=learning_path)
        self.addCleanup(engine.close)
        return engine

    def test_paging_reaches_all_stored_homophones_in_a_stable_order(self) -> None:
        engine = self.paging_engine()
        collected = []
        offset = 0
        while True:
            page = engine.lookup_page("zi", offset=offset, page_size=17, mode="jyutping")
            self.assertIsInstance(page, CandidatePage)
            self.assertEqual(page.offset, offset)
            self.assertFalse(page.completion_truncated)
            collected.extend(page.candidates)
            if page.next_offset is None:
                break
            self.assertEqual(page.next_offset, offset + len(page.candidates))
            offset = page.next_offset
        self.assertEqual(len(collected), 242)
        self.assertEqual(len({candidate.text for candidate in collected}), 242)
        self.assertEqual(collected[:90], engine.lookup("zi", limit=90, mode="jyutping"))
        self.assertEqual(collected[:9], engine.lookup("zi", mode="jyutping"))
        self.assertEqual(collected[180:199], list(engine.lookup_page("zi", offset=180, page_size=19, mode="jyutping").candidates))
        self.assertEqual(collected, sorted(collected, key=lambda item: (-item.score, item.text, item.reading)))
        self.assertEqual(engine.lookup_page("zi", offset=242, mode="jyutping").candidates, ())
        self.assertIsNone(engine.lookup_page("zi", offset=242, mode="jyutping").next_offset)

    def test_paging_preserves_pronunciation_ties_and_tone_filters(self) -> None:
        engine = self.paging_engine()
        first = chr(0x6000)
        untuned = next(candidate for candidate in engine.lookup_page("zi", page_size=90, mode="jyutping").candidates if candidate.text == first)
        self.assertEqual(untuned.reading, "zi6")
        toned = engine.lookup_page("zi4", page_size=90, mode="jyutping")
        self.assertTrue(all(candidate.reading == "zi4" for candidate in toned.candidates))
        self.assertEqual(next(candidate.reading for candidate in toned.candidates if candidate.text == first), "zi4")
        later = engine.lookup_page("zi6", offset=27, page_size=9, mode="jyutping")
        self.assertTrue(all(candidate.reading == "zi6" for candidate in later.candidates))
        self.assertIsNone(later.next_offset)

    def test_paging_score_saturation_uses_public_text_order(self) -> None:
        engine = self.paging_engine()
        actual = engine.lookup_page("zi4", page_size=2, mode="jyutping").candidates
        self.assertEqual([candidate.text for candidate in actual], sorted(("飽和甲", "飽和乙")))
        self.assertEqual(actual[0].score, actual[1].score)

    def test_paging_mode_override_and_original_input_length(self) -> None:
        for raw in ("lay5", " LAY5 "):
            page = self.engine.lookup_page(raw, mode="forgiving")
            self.assertIn("你", [candidate.text for candidate in page.candidates])
            self.assertTrue(all(candidate.consumed_input == len(raw) for candidate in page.candidates))
            self.assertEqual(list(page.candidates), self.engine.lookup(raw, mode="forgiving"))
            self.assertNotIn("你", [candidate.text for candidate in self.engine.lookup_page(raw, mode="jyutping").candidates])

    def test_paging_learning_promotes_a_later_homophone_and_persists(self) -> None:
        path = self.directory / "paging-learning.json"
        engine = self.paging_engine(learning_path=path)
        candidate = engine.lookup_page("zi4", offset=180, page_size=1, mode="jyutping").candidates[0]
        self.assertNotIn(candidate.text, [item.text for item in engine.lookup("zi4", limit=90, mode="jyutping")])
        engine.record_selection("zi4", candidate, mode="jyutping")
        self.assertEqual(engine.lookup_page("zi4", mode="jyutping").candidates[0].text, candidate.text)
        reopened = Engine(engine.path, learning_path=path)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.lookup("zi4", mode="jyutping")[0].text, candidate.text)

    def test_paging_learning_rejects_forged_or_wrong_tone_selection(self) -> None:
        engine = self.paging_engine(learning_path=self.directory / "selection.json")
        candidate = engine.lookup_page("zi4", offset=190, page_size=1, mode="jyutping").candidates[0]
        with self.assertRaises(ValueError):
            engine.record_selection("zi6", candidate, mode="jyutping")
        forged = Candidate("不存在的字詞", "zi4", candidate.score, "exact", 3)
        with self.assertRaises(ValueError):
            engine.record_selection("zi4", forged, mode="jyutping")
        self.assertFalse(engine.learning_path.exists())

    def test_paging_failed_learning_keeps_the_previous_ranked_snapshot(self) -> None:
        engine = self.paging_engine(learning_path=self.directory / "failing-learning.json")
        before = engine.lookup_page("zi4", offset=180, page_size=9, mode="jyutping")
        with patch("cantonese_ime.engine.os.replace", side_effect=OSError("simulated failed save")):
            with self.assertRaises(OSError):
                engine.record_selection("zi4", before.candidates[0], mode="jyutping")
        self.assertEqual(engine.lookup_page("zi4", offset=180, page_size=9, mode="jyutping"), before)
        self.assertFalse(engine.learning_path.exists())
        engine.record_selection("zi4", before.candidates[0], mode="jyutping")
        self.assertEqual(engine.lookup("zi4", mode="jyutping")[0].text, before.candidates[0].text)

    def test_paging_failed_read_does_not_replace_the_previous_snapshot(self) -> None:
        before = self.engine.lookup_page("nei5", mode="jyutping")
        with patch.object(self.engine, "_decode", side_effect=sqlite3.OperationalError("simulated read failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.engine.lookup_page("hou2", mode="jyutping")
            self.assertEqual(self.engine.lookup_page("nei5", mode="jyutping"), before)

    def test_paging_completion_capacity_is_explicit_and_bounded(self) -> None:
        engine = self.paging_engine(completions=True)
        first = engine.lookup_page("z", page_size=90, mode="jyutping")
        self.assertTrue(first.completion_truncated)
        self.assertEqual(first.next_offset, 90)
        self.assertEqual(list(first.candidates), engine.lookup("z", limit=90, mode="jyutping"))
        second = engine.lookup_page("z", offset=90, page_size=90, mode="jyutping")
        self.assertEqual(len(second.candidates), 38)
        self.assertEqual(second.next_offset, 128)
        with self.assertRaises(PaginationCapacityError):
            engine.lookup_page("z", offset=128, mode="jyutping")
        self.assertEqual(engine.lookup_page("z", page_size=90, mode="jyutping"), first)
        # Refining to the full stored reading makes every homophone available.
        refined = engine.lookup_page("zi4hou2", offset=230, page_size=90, mode="jyutping")
        self.assertEqual(len(refined.candidates), 10)
        self.assertIsNone(refined.next_offset)
        self.assertFalse(refined.completion_truncated)

    def test_paging_invalid_parameters_are_explicit(self) -> None:
        for offset in (-1, 10001, True, 0.5, "0"):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.engine.lookup_page("nei", offset=offset)
        for size in (0, -1, 91, True, 1.5, "9"):
            with self.subTest(page_size=size), self.assertRaises(ValueError):
                self.engine.lookup_page("nei", page_size=size)
        with self.assertRaises(ValueError):
            self.engine.lookup_page("nei", mode="unknown")
        empty = self.engine.lookup_page("🙂", offset=99)
        self.assertEqual(empty.candidates, ())
        self.assertIsNone(empty.next_offset)
        self.assertEqual(empty.offset, 99)

    def test_paging_results_are_immutable(self) -> None:
        page = self.engine.lookup_page("nei5")
        self.assertIsInstance(page.candidates, tuple)
        with self.assertRaises(AttributeError):
            page.next_offset = 123

    def tone_boundary_engine(self) -> Engine:
        """Include tempting, heavily weighted splits of whole toned syllables."""
        database = self.directory / "tone-boundaries.sqlite3"
        create_fixture_database(database)
        rows = (
            ("黃", "wong4", 10), ("水", "seoi6", 10), ("林", "lam4", 10),
            ("吾", "ng6", 1000000), ("哦", "o5", 1000000),
            ("和", "wo4", 1000000), ("些", "se2", 1000000), ("愛", "oi6", 1000000),
            ("拉", "la1", 1000000), ("姆", "m4", 1000000),
            ("花", "fa1", 1000000), ("衣", "i3", 1000000),
            ("分讀我", "ng6 o5", 1000000000),
            ("分讀黃", "wo4 ng4", 1000000000),
            ("分讀水", "se2 oi6", 1000000000),
            ("分讀林", "la1 m4", 1000000000),
            ("分讀快", "fa1 i3", 1000000000),
            ("我好", "ngo5 hou2", 50),
            ("分讀我好", "ng6 o5 hou2", 1000000000),
            ("好我", "hou2 ngo5", 50),
            ("好分讀我", "hou2 ng6 o5", 1000000000),
        )
        with closing(sqlite3.connect(database)) as connection:
            for text, reading, weight in rows:
                bases = [token[:-1] for token in reading.split()]
                connection.execute(
                    """INSERT INTO entries
                       (text, reading, base_reading, compact, syllable_count, weight, source)
                       VALUES (?, ?, ?, ?, ?, ?, 'synthetic-tone-boundary')""",
                    (text, reading, " ".join(bases), "".join(bases), len(bases), weight),
                )
            connection.commit()
        engine = Engine(database)
        self.addCleanup(engine.close)
        return engine

    def test_candidates_expose_the_public_contract(self) -> None:
        raw = "nei'hou"
        candidates = self.engine.lookup(raw, mode="jyutping")
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertIsInstance(candidate, Candidate)
            self.assertIsInstance(candidate.text, str)
            self.assertIsInstance(candidate.reading, str)
            self.assertIsInstance(candidate.score, (int, float))
            self.assertIn(candidate.match_type, {"exact", "fuzzy", "composed", "completion"})
            self.assertEqual(candidate.consumed_input, len(raw))

    def test_exact_phrase_and_tone_free_entry(self) -> None:
        for raw in ("neihou", "nei'hou", "nei hou"):
            with self.subTest(raw=raw):
                self.assertEqual(self.texts(raw, mode="jyutping")[0], "你好")

    def test_numeric_tones_select_matching_readings(self) -> None:
        for raw, text, reading in (
            ("nei5", "你", "nei5"),
            ("hou2", "好", "hou2"),
            ("hou3", "好", "hou3"),
            ("hou6", "號", "hou6"),
            ("nei5hou2", "你好", "nei5 hou2"),
        ):
            with self.subTest(raw=raw):
                matches = [candidate for candidate in self.engine.lookup(raw, mode="jyutping") if candidate.text == text]
                self.assertTrue(matches)
                self.assertEqual(matches[0].reading, reading)

    def test_tones_are_not_silently_discarded(self) -> None:
        self.assertNotIn("你好", self.texts("nei2hou2", mode="jyutping"))
        self.assertNotIn("你好", self.texts("nei5hou6", mode="jyutping"))
        self.assertNotIn("號", self.texts("hou2", mode="jyutping"))
        self.assertNotIn("你", self.texts("lei6"))

    def test_partial_tone_specification_is_respected(self) -> None:
        self.assertIn("你好", self.texts("nei5hou", mode="jyutping"))
        self.assertNotIn("你好", self.texts("nei2hou", mode="jyutping"))

    def test_numeric_tones_protect_supported_whole_syllables(self) -> None:
        engine = self.tone_boundary_engine()
        for mode in ("jyutping", "forgiving"):
            for raw, target, reading in (
                ("ngo5", "我", "ngo5"),
                ("wong4", "黃", "wong4"),
                ("seoi6", "水", "seoi6"),
                ("lam4", "林", "lam4"),
                ("hou2ngo5", "好我", "hou2 ngo5"),
            ):
                with self.subTest(raw=raw, mode=mode):
                    candidates = engine.lookup(raw, mode=mode, limit=90)
                    self.assertIn(target, [candidate.text for candidate in candidates])
                    expected = reading.split()
                    for candidate in candidates:
                        self.assertEqual(candidate.reading.split()[:len(expected)], expected)

    def test_numeric_tone_boundaries_apply_to_completions(self) -> None:
        engine = self.tone_boundary_engine()
        for mode in ("jyutping", "forgiving"):
            with self.subTest(mode=mode):
                candidates = engine.lookup("ngo5h", mode=mode, limit=90)
                self.assertIn("我好", [candidate.text for candidate in candidates])
                self.assertNotIn("分讀我好", [candidate.text for candidate in candidates])
                self.assertTrue(all(candidate.reading.split()[0] == "ngo5" for candidate in candidates))

    def test_numeric_tone_boundaries_respect_explicit_and_partial_spelling(self) -> None:
        engine = self.tone_boundary_engine()
        for mode in ("jyutping", "forgiving"):
            for raw in ("ng'o5", "ng o5"):
                with self.subTest(raw=raw, mode=mode):
                    candidates = engine.lookup(raw, mode=mode, limit=90)
                    self.assertIn("分讀我", [candidate.text for candidate in candidates])
                    self.assertNotIn("我", [candidate.text for candidate in candidates])
            with self.subTest(raw="neihou2", mode=mode):
                candidates = engine.lookup("neihou2", mode=mode)
                self.assertIn("你好", [candidate.text for candidate in candidates])
                self.assertEqual(next(candidate.reading for candidate in candidates if candidate.text == "你好"), "nei5 hou2")

    def test_numeric_tone_alias_protection_is_mode_specific(self) -> None:
        engine = self.tone_boundary_engine()
        # fai is a supported complete alias for faai only in forgiving mode.
        # In strict mode the same letters may still mean untoned fa + toned i3.
        strict = engine.lookup("fai3", mode="jyutping", limit=90)
        self.assertIn("分讀快", [candidate.text for candidate in strict])
        self.assertNotIn("快", [candidate.text for candidate in strict])
        forgiving = engine.lookup("fai3", mode="forgiving", limit=90)
        self.assertIn("快", [candidate.text for candidate in forgiving])
        self.assertNotIn("分讀快", [candidate.text for candidate in forgiving])
        self.assertTrue(all(candidate.reading.split()[0] == "faai3" for candidate in forgiving))

    def test_jyutping_mode_does_not_enable_forgiving_aliases(self) -> None:
        for raw, forbidden in (("lay", "你"), ("ngoh", "我"), ("boh", "保"), ("sheung", "想"), ("jau", "就")):
            with self.subTest(raw=raw):
                self.assertNotIn(forbidden, self.texts(raw, mode="jyutping"))

    def test_forgiving_aliases_return_canonical_readings(self) -> None:
        for raw, text, reading in (
            ("lay", "你", "nei5"),
            ("nay", "你", "nei5"),
            ("lei", "你", "nei5"),
            ("ngoh", "我", "ngo5"),
            ("boh", "保", "bou2"),
            ("jau", "就", "zau6"),
            ("chaa", "叉", "caa1"),
            ("sheung", "想", "soeng2"),
            ("shueng", "想", "soeng2"),
        ):
            with self.subTest(raw=raw):
                candidates = [candidate for candidate in self.engine.lookup(raw) if candidate.text == text]
                self.assertTrue(candidates)
                self.assertEqual(candidates[0].reading, reading)

    def test_aliases_keep_other_legitimate_readings(self) -> None:
        self.assertIn("理", self.texts("lei"))
        self.assertIn("你", self.texts("lei"))
        self.assertIn("有", self.texts("jau"))
        self.assertIn("就", self.texts("jau"))

    def test_yale_preference_and_mixed_spelling_priorities(self) -> None:
        candidates = self.texts("lei")
        self.assertLess(candidates.index("理"), candidates.index("你"))
        candidates = self.texts("jau")
        self.assertLess(candidates.index("就"), candidates.index("有"))
        with Engine(self.database, prefer_yale=False) as mixed:
            candidates = [candidate.text for candidate in mixed.lookup("jau")]
            self.assertLess(candidates.index("有"), candidates.index("就"))

    def test_crowded_exact_readings_do_not_hide_common_fuzzy_candidate(self) -> None:
        # Synthetic homophones exercise the real-dictionary failure without
        # copying its entries. They deliberately have negligible frequency.
        database = self.directory / "crowded.sqlite3"
        create_fixture_database(database)
        with closing(sqlite3.connect(database)) as connection:
            connection.executemany(
                """INSERT INTO entries
                   (text, reading, base_reading, compact, syllable_count, weight, source)
                   VALUES (?, 'lei5', 'lei', 'lei', 1, 0, 'synthetic-ranking-stress')""",
                ((chr(0x4E00 + index),) for index in range(120)),
            )
            connection.commit()
            self.assertGreater(connection.execute("SELECT COUNT(*) FROM entries WHERE compact = 'lei'").fetchone()[0], 100)
        engine = Engine(database)
        self.addCleanup(engine.close)
        candidates = [candidate.text for candidate in engine.lookup("lei", limit=9)]
        self.assertIn("你", candidates)
        self.assertLess(candidates.index("理"), candidates.index("你"))

    def test_fuzzy_tones_filter_before_text_deduplication(self) -> None:
        candidates = self.engine.lookup("jau6")
        self.assertIn("就", [candidate.text for candidate in candidates])
        self.assertNotIn("有", [candidate.text for candidate in candidates])
        self.assertEqual(next(candidate.reading for candidate in candidates if candidate.text == "就"), "zau6")

    def test_aliases_work_at_syllable_boundaries(self) -> None:
        for raw, target in (("leihou", "你好"), ("bohim", "保險"), ("chasiubao", "叉燒包")):
            with self.subTest(raw=raw):
                self.assertIn(target, self.texts(raw))

    def test_unstored_sentence_is_composed_from_dictionary_units(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM entries WHERE text = ?", ("我想食叉燒包",)).fetchone()[0], 0)
        candidates = self.engine.lookup("ngosoengsikcaasiubaau", mode="jyutping")
        matches = [candidate for candidate in candidates if candidate.text == "我想食叉燒包"]
        self.assertTrue(matches)
        self.assertEqual(matches[0].reading, "ngo5 soeng2 sik6 caa1 siu1 baau1")
        self.assertEqual(matches[0].match_type, "composed")

    def test_continuous_forgiving_sentence(self) -> None:
        for raw in ("ngosheungsikchasiubao", "ngoshuengsikchasiubao"):
            with self.subTest(raw=raw):
                self.assertIn("我想食叉燒包", self.texts(raw))

    def test_explicit_boundaries_exclude_an_unsplit_syllable(self) -> None:
        self.assertIn("狼", self.texts("long", mode="jyutping"))
        for raw in ("lo'ng", "lo ng"):
            with self.subTest(raw=raw):
                candidates = self.texts(raw, mode="jyutping")
                self.assertNotIn("狼", candidates)
                self.assertNotIn("朗", candidates)
                self.assertIn("囉吳", candidates)

    def test_frequency_orders_equally_matched_candidates(self) -> None:
        self.assertLess(self.texts("nei", mode="jyutping").index("你"), self.texts("nei", mode="jyutping").index("妳"))
        self.assertEqual(self.texts("hou", mode="jyutping")[0], "好")

    def test_direct_phrase_is_preferred_to_character_composition(self) -> None:
        self.assertEqual(self.texts("caasiubaau", mode="jyutping")[0], "叉燒包")
        self.assertEqual(self.texts("bouhim", mode="jyutping")[0], "保險")

    def test_candidate_texts_are_unique(self) -> None:
        candidates = self.texts("hou", mode="jyutping", limit=90)
        self.assertEqual(len(candidates), len(set(candidates)))

    def test_completion_can_recover_a_partial_last_syllable(self) -> None:
        self.assertIn("你好", self.texts("neih", mode="jyutping"))

    def test_tone_completion_filters_before_capping_dictionary_rows(self) -> None:
        database = self.directory / "tone-completion.sqlite3"
        create_fixture_database(database)
        with closing(sqlite3.connect(database)) as connection:
            # The only matching zi4 reading belongs to a longer word. Every
            # higher-weight row has the wrong first tone and must be filtered
            # before the prefix-candidate cap, rather than occupying its slots.
            connection.executemany(
                """INSERT INTO entries
                   (text, reading, base_reading, compact, syllable_count, weight, source)
                   VALUES (?, 'zi1 zi1 zam1', 'zi zi zam', 'zizizam', 3, 1000, 'synthetic-tone-stress')""",
                ((chr(0x4E00 + index) + "詞",) for index in range(140)),
            )
            connection.execute(
                """INSERT INTO entries
                   (text, reading, base_reading, compact, syllable_count, weight, source)
                   VALUES ('字字枕', 'zi4 zi4 zam4', 'zi zi zam', 'zizizam', 3, 0, 'synthetic-tone-target')"""
            )
            connection.commit()
        engine = Engine(database)
        self.addCleanup(engine.close)
        for raw in ("zi4", "zi4zi4"):
            with self.subTest(raw=raw):
                candidates = engine.lookup(raw, mode="jyutping", limit=9)
                target = next((candidate for candidate in candidates if candidate.text == "字字枕"), None)
                self.assertIsNotNone(target)
                self.assertEqual(target.reading, "zi4 zi4 zam4")
                self.assertEqual(target.match_type, "completion")
                self.assertTrue(all(candidate.reading.split()[0] == "zi4" for candidate in candidates))

    def test_long_stored_word_and_its_completion_reach_beyond_twelve_syllables(self) -> None:
        database = self.directory / "long-word.sqlite3"
        create_fixture_database(database)
        text = "你" * 13
        reading = " ".join(["nei5"] * 13)
        base = " ".join(["nei"] * 13)
        with closing(sqlite3.connect(database)) as connection:
            connection.executemany(
                """INSERT INTO entries
                   (text, reading, base_reading, compact, syllable_count, weight, source)
                   VALUES (?, ?, ?, ?, ?, 100, 'synthetic-long-word')""",
                (
                    (text, reading, base, "nei" * 13, 13),
                    (text + "好", reading + " hou2", base + " hou", "nei" * 13 + "hou", 14),
                ),
            )
            connection.commit()
        engine = Engine(database)
        self.addCleanup(engine.close)
        for raw in ("nei" * 13, "nei5" * 13):
            with self.subTest(raw=raw):
                self.assertLessEqual(len(raw), 64)
                target = next(candidate for candidate in engine.lookup(raw, mode="jyutping") if candidate.text == text)
                self.assertEqual(target.reading, reading)
                self.assertEqual(target.match_type, "exact")
        prefix = "nei" * 13 + "h"
        target = next(candidate for candidate in engine.lookup(prefix, mode="jyutping") if candidate.text == text + "好")
        self.assertEqual(target.match_type, "completion")

    def test_stored_completion_prefix_is_not_crowded_out_by_impossible_splits(self) -> None:
        database = self.directory / "completion-prefix-pruning.sqlite3"
        create_fixture_database(database)
        target_text = "廣" * 11
        target_reading = " ".join(["gwong2"] * 11)
        rows = ((target_text, target_reading, 0), ("廣", "gwong2", 1000),
                ("過", "gwo3", 1000), ("嗯", "ng6", 1000))
        with closing(sqlite3.connect(database)) as connection:
            for text, reading, weight in rows:
                bases = [syllable[:-1] for syllable in reading.split()]
                connection.execute(
                    """INSERT INTO entries
                       (text,reading,base_reading,compact,syllable_count,weight,source)
                       VALUES (?,?,?,?,?,?, 'synthetic-prefix-pruning')""",
                    (text, reading, " ".join(bases), "".join(bases), len(bases), weight),
                )
            connection.commit()
        engine = Engine(database)
        self.addCleanup(engine.close)
        # gwong can split into gwo+ng. Without stored-prefix pruning, the
        # completion query cap favors impossible paths with extra spaces and
        # drops the only real longer word. Numeric closure already prevents
        # those splits and supplies an independent positive control.
        self.assertGreater(len(target_reading.replace(" ", "")), 64)
        for mode in ("jyutping", "forgiving"):
            for raw in ("gwong" * 10, "'".join(["gwong"] * 10), "gwong2" * 10):
                with self.subTest(mode=mode, raw=raw):
                    self.assertLessEqual(len(raw), 64)
                    candidate = None
                    offset = 0
                    # The distinct composed pool can precede this completion.
                    # Verify that the real prefix is issued and the target is
                    # selectable through public pages, independently of rank.
                    with patch.object(engine, "_by_prefix", wraps=engine._by_prefix) as prefix_reader:
                        for _ in range(114):
                            page = engine.lookup_page(raw, offset=offset, page_size=90, mode=mode)
                            candidate = next((item for item in page.candidates if item.text == target_text), None)
                            if candidate is not None or page.next_offset is None:
                                break
                            offset = page.next_offset
                        self.assertIn(" ".join(["gwong"] * 10) + " ",
                                      [call.args[0] for call in prefix_reader.call_args_list])
                    self.assertIsNotNone(candidate)
                    self.assertEqual(candidate.reading, target_reading)
                    self.assertEqual(candidate.match_type, "completion")
                    self.assertEqual(candidate.consumed_input, len(raw))

    def test_query_mode_override_does_not_mutate_the_default(self) -> None:
        strict = Engine(self.database, mode="jyutping")
        close = getattr(strict, "close", None)
        if callable(close):
            self.addCleanup(close)
        self.assertIn("你", [candidate.text for candidate in strict.lookup("lay", mode="forgiving")])
        self.assertNotIn("你", [candidate.text for candidate in strict.lookup("lay")])

    def test_invalid_and_nonphonetic_inputs_return_no_candidates(self) -> None:
        for raw in ("", "   ", "你好", "🙂", "nei🙂", "nei!", "https://example.com", "nei0", "nei7", "nei9", "n" * 257):
            with self.subTest(raw=raw):
                self.assertEqual(self.engine.lookup(raw), [])

    def test_limit_is_enforced(self) -> None:
        candidates = self.engine.lookup("nei", limit=1)
        self.assertEqual(len(candidates), 1)

    def test_ambiguous_input_at_length_limit_remains_bounded(self) -> None:
        # Each "long" has both whole-syllable and lo+ng interpretations.
        # This detects exhaustive expansion while allowing ample CI headroom.
        started = time.perf_counter()
        candidates = self.engine.lookup("long" * 16, limit=9)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 2.0)
        self.assertLessEqual(len(candidates), 9)

    def test_invalid_options_are_reported(self) -> None:
        for limit in (0, -1, 91):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.engine.lookup("nei", limit=limit)
        with self.assertRaises(ValueError):
            self.engine.lookup("nei", mode="unknown")
        with self.assertRaises(ValueError):
            Engine(self.database, mode="unknown")

    def test_ranking_is_repeatable_without_learning(self) -> None:
        first = self.engine.lookup("lei")
        for _ in range(5):
            self.assertEqual(self.engine.lookup("lei"), first)

    def test_opt_in_learning_survives_engine_recreation(self) -> None:
        learning_path = self.directory / "learning.json"
        learning_engine = Engine(self.database, learning_path=learning_path)
        close = getattr(learning_engine, "close", None)
        if callable(close):
            self.addCleanup(close)
        selected = next(candidate for candidate in learning_engine.lookup("nei") if candidate.text == "妳")
        for _ in range(5):
            learning_engine.record_selection("nei", selected)
        self.assertTrue(learning_path.is_file())
        reloaded = Engine(self.database, learning_path=learning_path)
        close = getattr(reloaded, "close", None)
        if callable(close):
            self.addCleanup(close)
        self.assertEqual(reloaded.lookup("nei")[0].text, "妳")
        self.assertEqual(self.engine.lookup("nei")[0].text, "你")


if __name__ == "__main__":
    unittest.main()
