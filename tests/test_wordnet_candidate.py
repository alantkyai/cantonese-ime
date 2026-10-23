"""Candidate extensions preserve existing readings, weights and source fields."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime import Engine
from cantonese_ime.dictionary import DictionaryEntry, file_sha256
from tools.build_wordnet_candidate import build_candidate


def entry(text, reading, weight=0, source="wordnet:cantown"):
    bases = [token[:-1] for token in reading.split()]
    return DictionaryEntry(text, reading, " ".join(bases), "".join(bases), len(bases), weight, source)


class WordnetCandidateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="wordnet-candidate-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.baseline = self.root / "baseline.sqlite3"
        self.output = self.root / "candidate.sqlite3"
        with closing(sqlite3.connect(self.baseline)) as db:
            db.executescript("CREATE TABLE entries(id INTEGER PRIMARY KEY,text TEXT,reading TEXT,base_reading TEXT,compact TEXT,syllable_count INTEGER,weight REAL,source TEXT,origin TEXT,UNIQUE(text,reading)); CREATE INDEX bases ON entries(base_reading); CREATE TABLE syllables(base TEXT PRIMARY KEY); CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);")
            db.execute("INSERT INTO entries VALUES (1,'炬','geoi6','geoi','geoi',1,99,'earlier','explicit')")
            db.executemany("INSERT INTO syllables VALUES (?)", [("geoi",), ("fo",)])
            db.execute("INSERT INTO metadata VALUES ('entry_count','1')")
            db.commit()
        self.sha = file_sha256(self.baseline)

    def build(self, entries):
        return build_candidate(self.baseline, self.output, entries,
            expected_baseline_sha256=self.sha, evidence={"candidate_only": True}, review_rows=[])

    def test_append_preserves_existing_pair_and_weight_and_supports_public_yale(self):
        report = self.build([entry("炬", "geoi6"), entry("火炬", "fo2 geoi6")])
        self.assertEqual((report["added_pairs"], report["new_texts"], report["overlapping_pairs"]), (1, 1, 1))
        self.assertEqual(file_sha256(self.baseline), self.sha)
        with closing(sqlite3.connect(self.output)) as db:
            self.assertEqual(db.execute("SELECT weight,source,origin FROM entries WHERE text='炬'").fetchone(), (99, "earlier", "explicit"))
            self.assertEqual(db.execute("SELECT weight,source FROM entries WHERE text='火炬'").fetchone(), (0, "wordnet:cantown"))
        with Engine(self.output, learning_path=None) as engine:
            self.assertEqual(engine.lookup("fogeui")[0].text, "火炬")

    def test_nonzero_weights_duplicates_and_unknown_bases_cannot_publish(self):
        for entries in ([entry("火炬", "fo2 geoi6", 100)], [entry("炬", "geoi6"), entry("炬", "geoi6")], [entry("尖", "zim1")]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.build(entries)
            self.assertFalse(self.output.exists())
            self.assertEqual(file_sha256(self.baseline), self.sha)

    def test_stale_baseline_and_existing_output_are_rejected(self):
        with closing(sqlite3.connect(self.baseline)) as db:
            db.execute("UPDATE entries SET weight=1")
            db.commit()
        with self.assertRaisesRegex(ValueError, "hash"):
            self.build([entry("火炬", "fo2 geoi6")])
        self.output.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "new, separate"):
            self.build([entry("火炬", "fo2 geoi6")])
        self.assertEqual(self.output.read_text("utf-8"), "preserve")

    def test_changed_sources_prevent_candidate_publication(self):
        checks = 0

        def verify():
            nonlocal checks
            checks += 1
            if checks == 2:
                raise ValueError("source changed")

        with self.assertRaisesRegex(ValueError, "source changed"):
            build_candidate(self.baseline, self.output, [entry("火炬", "fo2 geoi6")],
                expected_baseline_sha256=self.sha, evidence={}, review_rows=[], validate_sources=verify)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_suffix(".manifest.json").exists())
        self.assertEqual(file_sha256(self.baseline), self.sha)


if __name__ == "__main__":
    unittest.main()
