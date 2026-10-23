"""Combined proof requires the complete current partition, not matching totals."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime import Engine
from tools.check_yale_catalog import Checkpoint, build_catalog, input_hashes, make_header, probe_group, select_shard, summarize
from tools.merge_yale_catalog import merge_catalog


class YaleCatalogMergeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="yale-merge-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "dictionary.sqlite3"
        self.fixture = self.root / "reference.json"
        self.fixture.write_text("{}\n", encoding="utf-8")
        rows = [("甲", "aa1"), ("尖", "zim1"), ("染", "jim5"), ("火炬", "fo2 geoi6"),
                ("香港", "hoeng1 gong2"), ("月", "jyut6"), ("出發", "ceot1 faat3")]
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript("CREATE TABLE entries(text TEXT,reading TEXT,base_reading TEXT,weight REAL); CREATE INDEX bases ON entries(base_reading);")
            db.executemany("INSERT INTO entries VALUES(?,?,?,0)", [(text, reading, " ".join(token[:-1] for token in reading.split())) for text, reading in rows])
            db.commit()

    def checkpoints(self, incomplete=False):
        catalog = build_catalog(self.database)
        hashes = input_hashes(self.database, self.fixture)
        paths = []
        with Engine(self.database, learning_path=None) as engine:
            for index in range(2):
                groups = select_shard(catalog, 2, index)
                self.assertTrue(groups)
                path = self.root / f"shard-{index}.jsonl"
                checkpoint = Checkpoint(path, make_header(catalog, groups, hashes, shards=2, shard_index=index, max_pages=128), groups, resume=False)
                try:
                    selected = groups[:-1] if incomplete and index == 0 else groups
                    for group in selected:
                        checkpoint.append(probe_group(engine, group, max_pages=128))
                    checkpoint.commit_verified()
                finally:
                    checkpoint.close()
                paths.append(path)
        return paths

    def test_complete_current_shards_prove_actual_public_text_retrieval(self):
        paths = self.checkpoints()
        before = [path.read_bytes() for path in paths]
        report = merge_catalog(self.database, self.fixture, list(reversed(paths)))
        self.assertTrue(report["complete_catalog_retrieval_verified"])
        self.assertEqual((report["processed_groups"], report["source_pairs_checked"]), (7, 7))
        self.assertEqual(report["missing_target_memberships"], 0)
        self.assertEqual(before, [path.read_bytes() for path in paths])

    def test_missing_and_duplicate_shards_are_rejected(self):
        paths = self.checkpoints()
        for selected in (paths[:1], [paths[0], paths[0]], []):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                merge_catalog(self.database, self.fixture, selected)

    def test_valid_incomplete_partition_does_not_pass(self):
        paths = self.checkpoints(incomplete=True)
        report = merge_catalog(self.database, self.fixture, paths)
        self.assertFalse(report["complete_catalog_retrieval_verified"])
        self.assertEqual(report["status"], "in_progress")
        self.assertEqual(report["remaining_groups"], 1)

    def test_stale_dictionary_checkpoint_cannot_be_reused(self):
        paths = self.checkpoints()
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE entries SET weight=1 WHERE text='甲'")
            db.commit()
        with self.assertRaisesRegex(ValueError, "identity"):
            merge_catalog(self.database, self.fixture, paths)

    def test_earlier_shard_stays_leased_until_later_shard_is_verified(self):
        paths = self.checkpoints()
        catalog = build_catalog(self.database)
        header = json.loads(paths[0].read_text("utf-8").splitlines()[0])
        groups = select_shard(catalog, 2, 0)
        calls = 0

        def observe(checkpoint, **options):
            nonlocal calls
            calls += 1
            if calls == 2:
                try:
                    writer = Checkpoint(paths[0], header, groups, resume=True)
                except ValueError as error:
                    self.assertIn("writer", str(error))
                else:
                    writer.close()
                    self.fail("Earlier shard was released during aggregate verification")
            return summarize(checkpoint, **options)

        with patch("tools.merge_yale_catalog.summarize", side_effect=observe):
            self.assertTrue(merge_catalog(self.database, self.fixture, paths)["complete_catalog_retrieval_verified"])
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
