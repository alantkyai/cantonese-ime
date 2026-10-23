"""Counterexamples to path beams, using project-authored miniature dictionaries."""

from contextlib import closing, redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime import CompositionCapacityError, Engine
from cantonese_ime.__main__ import main
from cantonese_ime.engine import _Arc, _Entry
from cantonese_ime.session import Session


class CompositionSearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cantonese-composition-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.counter = 0

    def engine(self, rows):
        self.counter += 1
        database = self.directory / f"dictionary-{self.counter}.sqlite3"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE TABLE entries(text TEXT,reading TEXT,base_reading TEXT,weight REAL)")
            connection.executemany("INSERT INTO entries VALUES (?,?,?,?)", [
                (text, reading, " ".join(part[:-1] for part in reading.split()), weight)
                for text, reading, weight in rows
            ])
            connection.commit()
        engine = Engine(database, mode="jyutping")
        self.addCleanup(engine.close)
        return engine

    def test_ninth_distinct_prefix_survives_composition(self):
        prefixes = [(f"P{i}", "nei5", 1000-i*10) for i in range(9)]
        engine = self.engine(prefixes + [("A", "hou2", 1000)])
        candidates = engine.lookup("nei5hou2", limit=90)
        self.assertEqual([candidate.text for candidate in candidates], [f"P{i}A" for i in range(9)])

    def test_duplicate_reading_paths_do_not_spend_unique_output_slots(self):
        engine = self.engine([
            *[("P", f"nei{tone}", 1000) for tone in range(1, 7)],
            ("Q", "nei5", 900),
            *[("A", f"hou{tone}", 1000) for tone in range(1, 7)],
            ("B", "hou2", 900),
        ])
        candidates = engine.lookup("neihou", limit=90)
        self.assertEqual({candidate.text for candidate in candidates}, {"PA", "PB", "QA", "QB"})
        self.assertEqual(next(candidate.reading for candidate in candidates if candidate.text == "PA"), "nei6 hou6")
        toned = engine.lookup("nei5hou2", limit=90)
        self.assertEqual({candidate.text for candidate in toned}, {"PA", "PB", "QA", "QB"})
        self.assertTrue(all(candidate.reading == "nei5 hou2" for candidate in toned))

    def test_suffix_text_order_avoids_forward_append_tie_reversal(self):
        engine = self.engine([*(('A'*i, "nei5", 1000) for i in range(1, 10)), ("B", "hou2", 1000)])
        candidates = engine.lookup("nei5hou2", limit=90)
        self.assertEqual([candidate.text for candidate in candidates], sorted('A'*i+'B' for i in range(1, 10)))
        self.assertEqual(candidates[0].text, "AAAAAAAAAB")

    def test_direct_word_arcs_do_not_fill_composition_budget(self):
        engine = self.engine([("P", "nei5", 1000), ("A", "hou2", 1000)])
        direct = tuple(_Arc(2, _Entry(f"D{i}", "nei5 hou2", "nei hou", 1000), 0) for i in range(100))
        graph = {0: direct + (_Arc(1, _Entry("P", "nei5", "nei", 1), 0),),
                 1: (_Arc(2, _Entry("A", "hou2", "hou", 1), 0),)}
        paths = engine._compose_sentences(graph.__getitem__, 2)
        self.assertEqual([path.text for path in paths], ["PA"])
        self.assertTrue(all(path.words > 1 for path in paths))

    def test_best_90_unique_compositions_have_stable_public_pages(self):
        engine = self.engine([
            *[(f"P{i:02}", "nei5", 1000) for i in range(12)],
            *[(f"A{i:02}", "hou2", 1000) for i in range(12)],
        ])
        expected = sorted(f"P{i:02}A{j:02}" for i in range(12) for j in range(12))[:90]
        candidates = engine.lookup("nei5hou2", limit=90)
        self.assertEqual([candidate.text for candidate in candidates], expected)
        first = engine.lookup_page("nei5hou2", page_size=9)
        last = engine.lookup_page("nei5hou2", offset=81, page_size=9)
        self.assertEqual([candidate.text for candidate in first.candidates], expected[:9])
        self.assertEqual([candidate.text for candidate in last.candidates], expected[81:90])

    def test_work_limit_raises_instead_of_publishing_incomplete_results(self):
        engine = self.engine([("P", "nei5", 1000), ("A", "hou2", 1000)])
        graph = {0: (_Arc(1, _Entry("P", "nei5", "nei", 1), 0),),
                 1: (_Arc(2, _Entry("A", "hou2", "hou", 1), 0),)}
        with self.assertRaises(CompositionCapacityError):
            engine._compose_sentences(graph.__getitem__, 2, work_limit=1)

    def test_capacity_error_preserves_session_and_cli_handles_it(self):
        engine = self.engine([("P", "nei5", 1000), ("A", "hou2", 1000)])
        session = Session(engine, mode="jyutping")
        for key in "nei":
            session.handle_key(key)
        original = session.buffer, session.candidates, session.page
        with patch.object(engine, "_compose_sentences", side_effect=CompositionCapacityError("capacity")):
            with self.assertRaises(CompositionCapacityError):
                session.handle_key("h")
        self.assertEqual((session.buffer, session.candidates, session.page), original)
        output, error = io.StringIO(), io.StringIO()
        with patch.object(Engine, "_compose_sentences", side_effect=CompositionCapacityError("capacity")):
            with redirect_stdout(output), redirect_stderr(error):
                code = main(["lookup", "neihou", "--dictionary", str(engine.path), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("capacity", error.getvalue())


if __name__ == "__main__":
    unittest.main()
