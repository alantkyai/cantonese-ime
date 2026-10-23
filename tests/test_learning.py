"""Selection-memory regressions using a small local SQLite fixture."""

from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from cantonese_ime import Engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_learning_fixture(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("""
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                reading TEXT NOT NULL,
                base_reading TEXT NOT NULL,
                compact TEXT NOT NULL,
                syllable_count INTEGER NOT NULL,
                weight REAL NOT NULL,
                source TEXT NOT NULL
            );
            CREATE INDEX entries_base_reading ON entries(base_reading);
        """)
        connection.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?)", [
            (1, "你", "nei5", "nei", "nei", 1, 1000.0, "learning-test"),
            (2, "妳", "nei5", "nei", "nei", 1, 100.0, "learning-test"),
            (3, "你好", "nei5 hou2", "nei hou", "neihou", 2, 500.0, "learning-test"),
            (4, "好", "hou2", "hou", "hou", 1, 500.0, "learning-test"),
            (5, "妳好", "nei5 hou2", "nei hou", "neihou", 2, 100.0, "learning-test"),
        ])
        connection.commit()


_SUBPROCESS_WRITER = r"""
from pathlib import Path
import sys,time
from cantonese_ime import Engine
database,memory,ready,gate,raw,repetitions=sys.argv[1:]
with Engine(database,learning_path=memory) as engine:
    candidate=engine.lookup(raw)[0]
    Path(ready).write_text('ready',encoding='utf-8')
    deadline=time.monotonic()+15
    while not Path(gate).exists():
        if time.monotonic()>deadline:
            raise TimeoutError('parent did not release writers')
        time.sleep(0.01)
    for _ in range(int(repetitions)):
        engine.record_selection(raw,candidate)
"""


class LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cantonese-learning-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.database = self.directory / "dictionary.sqlite3"
        self.memory = self.directory / "learning.json"
        create_learning_fixture(self.database)

    def saved(self) -> list[dict]:
        return json.loads(self.memory.read_text(encoding="utf-8"))["selections"]

    def test_preopened_instances_preserve_independent_selections(self) -> None:
        # Both instances see no file initially. The second writer must refresh
        # the disk state, not overwrite the first instance's subsequent update.
        with Engine(self.database, learning_path=self.memory) as first, Engine(
            self.database, learning_path=self.memory
        ) as second:
            one = first.lookup("nei")[0]
            two = second.lookup("neihou")[0]
            first.record_selection("nei", one)
            second.record_selection("neihou", two)
            first.record_selection("nei", one)
        records = {item["input"]: item for item in self.saved()}
        self.assertEqual(set(records), {"nei", "neihou"})
        self.assertEqual((records["nei"]["text"], records["nei"]["count"]), ("你", 2))
        self.assertEqual((records["neihou"]["text"], records["neihou"]["count"]), ("你好", 1))
        with Engine(self.database, learning_path=self.memory) as reopened:
            self.assertEqual(reopened.lookup("nei")[0].text, "你")

    def test_two_subprocess_writers_preserve_every_increment(self) -> None:
        gate = self.directory / "start"
        repetitions = 8
        processes: list[subprocess.Popen] = []
        ready_paths = []
        try:
            for index, raw in enumerate(("nei", "neihou")):
                ready = self.directory / f"writer-{index}.ready"
                ready_paths.append(ready)
                process = subprocess.Popen(
                    [sys.executable, "-c", _SUBPROCESS_WRITER, str(self.database),
                     str(self.memory), str(ready), str(gate), raw, str(repetitions)],
                    cwd=PROJECT_ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                processes.append(process)
            deadline = time.monotonic() + 15
            while not all(ready.exists() for ready in ready_paths):
                for process in processes:
                    if process.poll() is not None:
                        stdout, stderr = process.communicate()
                        self.fail(f"Writer exited before the shared barrier: {stdout}\n{stderr}")
                if time.monotonic() > deadline:
                    self.fail("Writer startup barrier timed out")
                time.sleep(0.01)
            gate.write_text("start", encoding="utf-8")
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, f"{stdout}\n{stderr}")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
        records = {item["input"]: item for item in self.saved()}
        self.assertEqual(set(records), {"nei", "neihou"})
        self.assertEqual({key: item["count"] for key, item in records.items()},
                         {"nei": repetitions, "neihou": repetitions})
        with Engine(self.database, learning_path=self.memory) as reopened:
            self.assertTrue(reopened.lookup("neihou"))

    def test_malformed_file_found_during_save_is_not_overwritten(self) -> None:
        with Engine(self.database, learning_path=self.memory) as engine:
            candidate = engine.lookup("nei")[0]
            engine.record_selection("nei", candidate)
            malformed = b'{"schema_version":1,"selections":['
            self.memory.write_bytes(malformed)
            with self.assertRaises(ValueError):
                engine.record_selection("nei", candidate)
            self.assertEqual(self.memory.read_bytes(), malformed)
        with self.assertRaises(ValueError):
            Engine(self.database, learning_path=self.memory)
        self.assertEqual(self.memory.read_bytes(), malformed)

    def test_serialized_byte_budget_evicts_records_and_remains_reloadable(self) -> None:
        budget = 900
        inputs = ["nei", "nei5", "nei'", "nei5'", "lay", "nay", "lei",
                  "neihou", "nei'hou", "nei5hou2", "nei5'hou2", "leihou",
                  "nayhou", "layhou", "nei'hou2"]
        with patch("cantonese_ime.engine._MAX_LEARNING_BYTES", budget):
            with Engine(self.database, learning_path=self.memory) as engine:
                for raw in inputs:
                    candidate = engine.lookup(raw)[0]
                    engine.record_selection(raw, candidate)
                    self.assertLessEqual(self.memory.stat().st_size, budget)
            records = self.saved()
            self.assertGreater(len(records), 0)
            self.assertLess(len(records), len(inputs), "The byte budget must actually trigger eviction")
            self.assertIn(inputs[-1], {item["input"] for item in records})
        # Restore the normal loader budget before checking a fresh instance.
        with Engine(self.database, learning_path=self.memory) as reopened:
            self.assertTrue(reopened.lookup(inputs[-1]))

    def test_oversized_single_selection_preserves_previous_bytes(self) -> None:
        # This valid existing file fits the smaller budget. Adding one selection
        # cannot fit, so exercise serialization failure rather than loader refusal.
        original = b'{"schema_version":1,"selections":[]}\n'
        self.memory.write_bytes(original)
        with Engine(self.database, learning_path=self.memory) as engine:
            candidate = engine.lookup("nei")[0]
            with patch("cantonese_ime.engine._MAX_LEARNING_BYTES", 100):
                with self.assertRaises(ValueError):
                    engine.record_selection("nei", candidate)
            self.assertEqual(self.memory.read_bytes(), original)
        with Engine(self.database, learning_path=self.memory) as reopened:
            self.assertEqual(reopened.lookup("nei")[0].text, "你")

    def test_legacy_count_migrates_and_four_new_choices_overtake_old_habit(self) -> None:
        self.memory.write_text(json.dumps({"schema_version": 1, "selections": [
            {"mode": "forgiving", "input": "nei", "text": "你", "reading": "nei5", "count": 1000000}
        ]}), encoding="utf-8")
        with Engine(self.database, learning_path=self.memory) as engine:
            self.assertEqual(engine.lookup("nei")[0].text, "你")
            new = next(candidate for candidate in engine.lookup("nei") if candidate.text == "妳")
            for _ in range(4):
                engine.record_selection("nei", new)
            self.assertEqual(engine.lookup("nei")[0].text, "妳")
        saved = json.loads(self.memory.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], 2)
        entries = {item["text"]: item for item in saved["selections"]}
        self.assertEqual(entries["你"]["count"], 1000000)
        self.assertEqual(entries["妳"]["count"], 4)
        self.assertAlmostEqual(entries["你"]["adaptive_weight"], 2.048)
        self.assertAlmostEqual(entries["妳"]["adaptive_weight"], 2.952)
        with Engine(self.database, learning_path=self.memory) as reopened:
            self.assertEqual(reopened.lookup("nei")[0].text, "妳")

    def test_composed_long_phrase_learning_keeps_shorter_inputs_independent(self) -> None:
        raw = "neihouneihou"
        with Engine(self.database, learning_path=self.memory) as engine:
            short = next(candidate for candidate in engine.lookup("nei") if candidate.text == "妳")
            engine.record_selection("nei", short)
            phrase = next(candidate for candidate in engine.lookup(raw) if candidate.text == "你好妳好")
            self.assertEqual(phrase.match_type, "composed")
            for _ in range(3):
                engine.record_selection(raw, phrase)
            self.assertEqual(engine.lookup(raw)[0].text, "你好妳好")
            self.assertEqual(engine.lookup("nei")[0].text, "妳")
            self.assertEqual(engine.lookup("neihou")[0].text, "你好")
        records = {(item["mode"], item["input"], item["text"]): item for item in self.saved()}
        self.assertEqual(records[("forgiving", "nei", "妳")]["adaptive_weight"], 1.0)
        self.assertEqual(records[("forgiving", raw, "你好妳好")]["count"], 3)
        with Engine(self.database, learning_path=self.memory) as reopened:
            self.assertEqual(reopened.lookup(raw)[0].text, "你好妳好")
            self.assertEqual(reopened.lookup("nei")[0].text, "妳")

    def test_decay_does_not_spill_into_other_mode_or_alias_input(self) -> None:
        with Engine(self.database, learning_path=self.memory) as engine:
            strict = engine.lookup("nei", mode="jyutping")[0]
            engine.record_selection("nei", strict, mode="jyutping")
            alias = engine.lookup("lei")[0]
            engine.record_selection("lei", alias)
            choice = next(candidate for candidate in engine.lookup("nei") if candidate.text == "妳")
            for _ in range(4):
                engine.record_selection("NEI", choice)
            self.assertEqual(engine.lookup("nei")[0].text, "妳")
            self.assertEqual(engine.lookup("nei", mode="jyutping")[0].text, "你")
            self.assertEqual(engine.lookup("lei")[0].text, "你")
        records = {(item["mode"], item["input"]): item for item in self.saved()}
        self.assertEqual(records[("jyutping", "nei")]["adaptive_weight"], 1.0)
        self.assertEqual(records[("forgiving", "lei")]["adaptive_weight"], 1.0)

    def test_invalid_schema2_weights_are_not_accepted_or_modified(self) -> None:
        for weight in (-0.1, 5.1, float("inf"), float("nan"), 10 ** 500, True, "1", None):
            with self.subTest(weight=weight):
                original = json.dumps({"schema_version": 2, "selections": [
                    {"mode": "forgiving", "input": "nei", "text": "你", "reading": "nei5", "count": 1,
                     "adaptive_weight": weight}
                ]}).encode("utf-8")
                self.memory.write_bytes(original)
                with self.assertRaises(ValueError):
                    Engine(self.database, learning_path=self.memory)
                self.assertEqual(self.memory.read_bytes(), original)

    def test_adaptive_weight_drives_eviction_instead_of_large_historical_count(self) -> None:
        self.memory.write_text(json.dumps({"schema_version": 2, "selections": [
            {"mode": "forgiving", "input": "nei", "text": "你", "reading": "nei5", "count": 1000000,
             "adaptive_weight": 0.0},
            {"mode": "forgiving", "input": "neihou", "text": "你好", "reading": "nei5 hou2", "count": 1,
             "adaptive_weight": 1.0},
        ]}), encoding="utf-8")
        with patch("cantonese_ime.engine._MAX_LEARNING_RECORDS", 2):
            with Engine(self.database, learning_path=self.memory) as engine:
                engine.record_selection("nei5", engine.lookup("nei5")[0])
        self.assertEqual({item["input"] for item in self.saved()}, {"neihou", "nei5"})

    def test_personal_composed_phrase_survives_later_static_search_pruning(self) -> None:
        raw = "neihouneihou"
        with Engine(self.database, learning_path=self.memory) as engine:
            phrase = next(candidate for candidate in engine.lookup(raw) if candidate.text == "你好妳好")
            self.assertEqual(phrase.match_type, "composed")
            engine.record_selection(raw, phrase)
        # A fresh non-learning engine demonstrates the changed search really
        # loses this whole phrase; the test must not pass through a stale cache.
        with Engine(self.database) as static_only, patch.object(static_only, "_compose_sentences", return_value=()):
            self.assertNotIn(phrase.text, {candidate.text for candidate in static_only.lookup(raw)})
        with Engine(self.database, learning_path=self.memory) as reopened, \
             patch.object(reopened, "_compose_sentences", return_value=()):
            retained = reopened.lookup(raw)[0]
            self.assertEqual((retained.text, retained.reading, retained.match_type),
                             (phrase.text, phrase.reading, "learned"))
            self.assertEqual(retained.consumed_input, len(raw))
            self.assertNotIn(phrase.text, {candidate.text for candidate in reopened.lookup("nei")})
            self.assertNotIn(phrase.text, {candidate.text for candidate in reopened.lookup(raw, mode="jyutping")})
            reopened.record_selection(raw, retained)
        self.assertEqual(self.saved()[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
