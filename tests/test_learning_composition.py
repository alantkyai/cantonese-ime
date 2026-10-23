"""Constituent preferences transfer to longer inputs using synthetic data only."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from cantonese_ime import Engine


def create_fixture(path: Path) -> None:
    # More than 90 ng homophones force the selected zero-weight character past
    # both the dictionary row cap and the old generated-sentence cap. 唔好 is
    # stored with m, while the user-selected standalone reading is ng4.
    rows = [(chr(0x5000 + index), "ng5", 100000.0 - index) for index in range(110)]
    rows += [("唔", "ng4", 0.0), ("唔", "m4", 6000000.0),
             ("好", "hou2", 100000.0), ("係", "hai6", 90000.0),
             ("咁", "gam3", 80000.0), ("你", "nei5", 70000.0),
             ("妳", "nei5", 700.0), ("唔好", "m4 hou2", 20000.0),
             ("你好", "nei5 hou2", 1000.0), ("妳好", "nei5 hou2", 100.0)]
    rows += [(f"全詞{index}", "ng5 hou2", 1000.0) for index in range(6)]
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("""
            CREATE TABLE entries(text TEXT,reading TEXT,base_reading TEXT,weight REAL);
            CREATE INDEX entries_base_reading ON entries(base_reading);
        """)
        connection.executemany("INSERT INTO entries VALUES(?,?,?,?)", [
            (text, reading, " ".join(token[:-1] for token in reading.split()), weight)
            for text, reading, weight in rows
        ])
        connection.commit()


class ConstituentLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cantonese-span-learning-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.database = self.folder / "dictionary.sqlite3"
        self.memory = self.folder / "synthetic-learning.json"
        create_fixture(self.database)

    def learn_negative(self, engine: Engine, repetitions: int = 1):
        page = engine.lookup_page("ng", offset=90, page_size=90)
        selected = next(item for item in page.candidates if item.text == "唔")
        self.assertEqual(selected.reading, "ng4")
        for _ in range(repetitions):
            engine.record_selection("ng", selected)

    def test_low_frequency_selection_survives_graph_pruning_in_new_phrases(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            self.assertNotIn("唔好", {item.text for item in engine.lookup("ngho", limit=90)})
            self.assertNotIn("唔係咁", {item.text for item in engine.lookup("nghaigam", limit=90)})
            self.learn_negative(engine)
            rows = engine.lookup("ngho")
            self.assertIn("唔好", {item.text for item in rows})
            self.assertEqual(next(item for item in rows if item.text == "唔好").reading, "ng4 hou2")
            self.assertEqual(engine.lookup("nghaigam")[0].text, "唔係咁")
            # The mechanism also applies to another suffix and inside an input;
            # there is no word-specific ng->m alias or phrase replacement.
            self.assertEqual(engine.lookup("ngnei")[0].text, "唔你")
            self.assertEqual(engine.lookup("neingho")[0].text, "你唔好")
            self.assertEqual(engine.lookup("ng")[0].text, "唔")

    def test_persistence_uses_existing_schema_and_exact_long_choice_wins(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            self.learn_negative(engine, repetitions=6)
            # A specific longer spelling may mean a different phrase. Its own
            # selection remains stronger than a reused shorter preference.
            other = engine.lookup("nghaigam", limit=90)[1]
            self.assertNotEqual(other.text, "唔係咁")
            engine.record_selection("nghaigam", other)
            self.assertEqual(engine.lookup("nghaigam")[0].text, other.text)
            self.assertEqual(engine.lookup("ng")[0].text, "唔")
        stored = json.loads(self.memory.read_text(encoding="utf-8"))
        self.assertEqual(stored["schema_version"], 2)
        self.assertEqual({row["input"] for row in stored["selections"]}, {"ng", "nghaigam"})
        with Engine(self.database, learning_path=self.memory) as reopened:
            self.assertEqual(reopened.lookup("ng")[0].text, "唔")
            self.assertIn("唔好", {item.text for item in reopened.lookup("ngho")})
            self.assertEqual(reopened.lookup("nghaigam")[0].text, other.text)
            self.assertEqual(reopened.lookup("ngnei")[0].text, "唔你")

    def test_modes_and_tone_closure_do_not_cross_pollinate(self):
        with Engine(self.database) as static:
            strict = static.lookup("nghou", mode="jyutping", limit=90)
            toned = static.lookup("ng5hou2", limit=90)
        with Engine(self.database, learning_path=self.memory) as engine:
            self.learn_negative(engine)
            self.assertEqual(engine.lookup("nghou", mode="jyutping", limit=90), strict)
            self.assertEqual(engine.lookup("ng5hou2", limit=90), toned)
            self.assertIn("唔好", {item.text for item in engine.lookup("ng'ho")})
            self.assertNotIn("唔好", {item.text for item in engine.lookup("ng5'ho", limit=90)})

    def test_another_selected_word_transfers_without_changing_stored_phrase_priority(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            selected = next(item for item in engine.lookup("nei") if item.text == "妳")
            engine.record_selection("nei", selected)
            self.assertEqual(engine.lookup("neing")[0].text[:1], "妳")
            self.assertEqual(engine.lookup("neihou")[0].text, "你好")

    def test_complete_learned_phrase_can_be_a_constituent(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            self.learn_negative(engine)
            phrase = engine.lookup("nghaigam")[0]
            engine.record_selection("nghaigam", phrase)
            self.assertEqual(engine.lookup("neinghaigam")[0].text, "你唔係咁")

    def test_prefix_completions_do_not_become_implicit_abbreviations(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            completion = next(item for item in engine.lookup("ne") if item.text == "你")
            self.assertEqual(completion.match_type, "completion")
            engine.record_selection("ne", completion)
            self.assertEqual(engine.lookup("ne")[0].text, "你")
            self.assertNotIn("你好", {item.text for item in engine.lookup("neho", limit=90)})

    def test_no_memory_and_zero_weight_memory_preserve_every_candidate(self):
        inputs = ("ng", "ngho", "nghaigam", "ng5hou2", "ng'ho", "neingho")
        with Engine(self.database) as static:
            baseline = {raw: static.lookup_page(raw, page_size=90) for raw in inputs}
        with Engine(self.database, learning_path=self.memory) as empty:
            self.assertEqual({raw: empty.lookup_page(raw, page_size=90) for raw in inputs}, baseline)
        self.memory.write_text(json.dumps({"schema_version": 2, "selections": [
            {"mode": "forgiving", "input": "ng", "text": "唔", "reading": "ng4", "count": 100,
             "adaptive_weight": 0.0}
        ]}), encoding="utf-8")
        with Engine(self.database, learning_path=self.memory) as zero:
            # Whole-input record retention is an existing behavior; compare the
            # longer inputs where the new constituent path must stay inactive.
            self.assertEqual({raw: zero.lookup_page(raw, page_size=90) for raw in inputs[1:]},
                             {raw: baseline[raw] for raw in inputs[1:]})

    def test_matching_budget_is_explicit_and_preserves_available_candidates(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            self.learn_negative(engine)
            started = time.perf_counter()
            with patch("cantonese_ime.engine._SPAN_LEARNING_WORK_LIMIT", 1):
                page = engine.lookup_page("ngho", page_size=9)
            self.assertTrue(page.candidates)
            self.assertTrue(page.completion_truncated)
            self.assertLess(time.perf_counter() - started, 0.5)


if __name__ == "__main__":
    unittest.main()
