"""Changed Yale cohorts must include earlier homophones, not only new targets."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.check_yue_wiktionary_candidate import affected_groups, SOURCE_ID


class YueCohortTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="yue-cohort-")
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "candidate.sqlite3"
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("CREATE TABLE entries(text TEXT,reading TEXT,base_reading TEXT,weight REAL,source TEXT,origin TEXT)")
            db.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?)", [
                ("你", "nei5", "nei", 100, "earlier", "explicit"),
                ("妳", "nei5", "nei", 0, SOURCE_ID, "supplement"),
                ("好", "hou2", "hou", 99, "earlier", "explicit")])
            db.commit()
        self.manifest = {"added_pairs": 1, "added_entries": [{"text": "妳", "reading": "nei5"}]}

    def test_earlier_homophones_are_required_while_other_inputs_stay_outside_scope(self):
        catalog, groups = affected_groups(self.database, self.manifest)
        self.assertEqual(catalog.source_pairs, 3)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].raw, "nei")
        self.assertEqual(groups[0].targets, ("你", "妳"))
        self.assertEqual(groups[0].source_pairs, 2)

    def test_wrong_cohort_origin_weight_or_manifest_does_not_silently_shrink(self):
        for column, value in (("origin", "generated"), ("weight", 10), ("source", "other")):
            with self.subTest(column=column):
                with closing(sqlite3.connect(self.database)) as db:
                    db.execute(f"UPDATE entries SET {column}=? WHERE text='妳'", (value,))
                    db.commit()
                with self.assertRaises(ValueError):
                    affected_groups(self.database, self.manifest)
                with closing(sqlite3.connect(self.database)) as db:
                    db.execute("UPDATE entries SET source=?,weight=0,origin='supplement' WHERE text='妳'", (SOURCE_ID,))
                    db.commit()


if __name__ == "__main__":
    unittest.main()
