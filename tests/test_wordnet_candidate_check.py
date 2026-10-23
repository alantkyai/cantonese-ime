"""New-source checks must retain old competing texts at the same Yale input."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.check_wordnet_candidate import affected_groups


class WordnetCandidateCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="wordnet-check-")
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "candidate.sqlite3"
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript("CREATE TABLE entries(text TEXT,reading TEXT,base_reading TEXT,weight REAL,source TEXT);")
            db.executemany("INSERT INTO entries VALUES (?,?,?,?,?)", [
                ("炬", "geoi6", "geoi", 99, "earlier"),
                ("舉", "geoi2", "geoi", 0, "wordnet:cantown"),
                ("舉", "geoi3", "geoi", 0, "wordnet:cantown"),
                ("火", "fo2", "fo", 99, "earlier")])
            db.commit()
        self.manifest = {"added_pairs": 2, "added_entries": [{"text": "舉", "reading": "geoi2"}, {"text": "舉", "reading": "geoi3"}]}

    def test_existing_homophone_is_required_and_tone_duplicates_stay_counted(self):
        catalog, groups = affected_groups(self.database, self.manifest)
        self.assertEqual(catalog.source_pairs, 4)
        self.assertEqual(len(groups), 1)
        self.assertEqual((groups[0].raw, groups[0].targets, groups[0].source_pairs), ("geui", ("炬", "舉"), 3))

    def test_missing_extra_or_weight_changed_cohort_is_rejected(self):
        bad = {"added_pairs": 1, "added_entries": self.manifest["added_entries"][:1]}
        with self.assertRaises(ValueError):
            affected_groups(self.database, bad)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE entries SET weight=1 WHERE source='wordnet:cantown'")
            db.commit()
        with self.assertRaises(ValueError):
            affected_groups(self.database, self.manifest)


if __name__ == "__main__":
    unittest.main()
