"""Finite catalog accounting, public paging and resumable checkpoint integrity."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime import Candidate, CandidatePage, Engine, PaginationCapacityError
from tools.check_yale_catalog import (
    Catalog, Checkpoint, Group, build_catalog, digest, encoded, make_header,
    output_path, probe_group, select_shard, summarize,
)


def database(path, rows):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("CREATE TABLE entries(text TEXT,reading TEXT,base_reading TEXT,weight REAL,UNIQUE(text,reading)); CREATE INDEX base_lookup ON entries(base_reading);")
        connection.executemany("INSERT INTO entries VALUES(?,?,?,?)",
            [(text, reading, " ".join(token[:-1] for token in reading.split()), weight) for text, reading, weight in rows])
        connection.commit()


class FakeEngine:
    MAX_INPUT_LENGTH = 256
    MAX_OFFSET = 10000

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def lookup_page(self, raw, *, offset, page_size, mode):
        self.calls.append((raw, offset, page_size, mode))
        result = self.pages[offset]
        if isinstance(result, Exception):
            raise result
        return result


def candidate(text, raw="jim"):
    return Candidate(text, "zim1", 0.0, "fuzzy", len(raw))


def success(group):
    return {"status": "all_found", "found_targets": [{"text": text, "reading": "a1", "rank": i + 1} for i, text in enumerate(group.targets)],
            "missing_targets": [], "pages": 1, "public_page_calls": 1, "visible_candidates": len(group.targets),
            "pool_truncated_seen": False, "error": "", "lookup_ms": 1.0, "first_request_ms": 1.0, "max_request_ms": 1.0}


class YaleCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="yale-catalog-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def setup_checkpoint(self, groups=None):
        groups = groups or (Group(0, "a", ("甲",), 1), Group(1, "aa", ("乙",), 1))
        catalog = Catalog(groups, sum(g.source_pairs for g in groups), digest([g.identity for g in groups]))
        header = make_header(catalog, groups, {"dictionary": "a" * 64}, shards=1, shard_index=0, max_pages=128)
        path = self.root / "checkpoint.jsonl"
        return path, header, groups

    def checkpoint(self, path, header, groups, **options):
        checkpoint = Checkpoint(path, header, groups, **options)
        self.addCleanup(checkpoint.close)
        return checkpoint

    def test_catalog_groups_every_row_by_public_yale_and_deduplicates_text_only(self):
        path = self.root / "catalog.sqlite3"
        database(path, [("甲", "aa1", 0), ("甲", "aa2", 0), ("乙", "a1", 0), ("尖", "zim1", 0), ("染", "jim5", 0)])
        before = path.read_bytes()
        catalog = build_catalog(path)
        groups = {group.raw: group for group in catalog.groups}
        self.assertEqual(groups["a"].targets, ("乙", "甲"))
        self.assertEqual(groups["a"].source_pairs, 3)
        self.assertEqual(groups["jim"].targets, ("尖",))
        self.assertEqual(groups["yim"].targets, ("染",))
        self.assertEqual(catalog.source_pairs, 5)
        self.assertEqual(build_catalog(path), catalog)
        self.assertEqual(path.read_bytes(), before)

    def test_malformed_reading_fails_instead_of_silently_excluding_a_row(self):
        path = self.root / "bad.sqlite3"
        database(path, [("甲", "aa1", 0)])
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("UPDATE entries SET base_reading='different'")
            connection.commit()
        with self.assertRaisesRegex(ValueError, "mismatch"):
            build_catalog(path)

    def test_shards_partition_complete_catalog_with_stable_hash_spread(self):
        groups = tuple(Group(i, "a" + chr(97 + i), (str(i),), 1) for i in range(20))
        catalog = Catalog(groups, 20, "fixture")
        shards = [select_shard(catalog, 4, i) for i in range(4)]
        self.assertEqual(sorted(g.ordinal for shard in shards for g in shard), list(range(20)))
        self.assertEqual(shards[0], select_shard(catalog, 4, 0))
        self.assertNotEqual(select_shard(catalog, 1, 0), groups)

    def test_public_pages_continue_until_all_required_texts_including_rank91(self):
        page0 = tuple(candidate(str(i)) for i in range(90))
        engine = FakeEngine({0: CandidatePage(page0, 0, 90), 90: CandidatePage((candidate("尖"),), 90, None)})
        group = Group(0, "jim", ("尖", "5"), 2)
        result = probe_group(engine, group, max_pages=128)
        self.assertEqual(result["status"], "all_found")
        self.assertEqual(result["public_page_calls"], 2)
        self.assertEqual(next(row["rank"] for row in result["found_targets"] if row["text"] == "尖"), 91)
        self.assertEqual(engine.calls, [("jim", 0, 90, "forgiving"), ("jim", 90, 90, "forgiving")])

    def test_missing_capacity_page_budget_and_input_exclusions_never_pass(self):
        group = Group(0, "jim", ("尖", "甲"), 2)
        pages = {0: CandidatePage((candidate("尖"),), 0, 1, True), 1: PaginationCapacityError("bounded tail")}
        result = probe_group(FakeEngine(pages), group, max_pages=128)
        self.assertEqual((result["status"], result["missing_targets"], result["public_page_calls"]), ("capacity_limited", ["甲"], 2))
        self.assertTrue(result["pool_truncated_seen"])
        self.assertEqual(probe_group(FakeEngine(pages), group, max_pages=1)["status"], "page_budget")
        exhausted = FakeEngine({0: CandidatePage((), 0, None)})
        self.assertEqual(probe_group(exhausted, group, max_pages=128)["missing_targets"], ["尖", "甲"])
        excluded = FakeEngine({})
        long_group = Group(1, "a" * 257, ("甲",), 1)
        self.assertEqual(probe_group(excluded, long_group, max_pages=128)["status"], "input_limit_excluded")
        self.assertEqual(excluded.calls, [])

    def test_invalid_public_cursor_or_duplicate_is_error_even_when_target_found(self):
        group = Group(0, "jim", ("尖",), 1)
        for page in (CandidatePage((candidate("尖"),), 0, 0),
                     CandidatePage((candidate("尖"), candidate("尖")), 0, None),
                     CandidatePage((candidate("尖", "wrong"),), 0, None)):
            with self.subTest(page=page):
                self.assertEqual(probe_group(FakeEngine({0: page}), group, max_pages=128)["status"], "engine_error")

    def test_only_committed_rows_resume_and_partial_work_is_not_complete(self):
        path, header, groups = self.setup_checkpoint()
        first = self.checkpoint(path, header, groups, resume=False)
        first.append(success(groups[0]))
        with self.assertRaisesRegex(ValueError, "unverified"):
            summarize(first, new_groups=1, startup_ms=0, run_seconds=0)
        first.commit_verified()
        summary = summarize(first, new_groups=1, startup_ms=0, run_seconds=0)
        self.assertFalse(summary["complete_catalog_retrieval_verified"])
        self.assertEqual(summary["remaining_groups"], 1)
        first.close()
        resumed = self.checkpoint(path, header, groups, resume=True)
        self.assertEqual(resumed.processed, 1)
        resumed.append(success(groups[1]))
        resumed.commit_verified()
        self.assertTrue(summarize(resumed, new_groups=1, startup_ms=0, run_seconds=0)["complete_catalog_retrieval_verified"])

    def test_unverified_tail_requires_explicit_archived_discard_then_is_rechecked(self):
        path, header, groups = self.setup_checkpoint()
        writer = self.checkpoint(path, header, groups, resume=False)
        writer.append(success(groups[0]))
        writer.commit_verified()
        writer.append(success(groups[1]))
        writer.close()
        with self.assertRaisesRegex(ValueError, "Unverified"):
            Checkpoint(path, header, groups, resume=True)
        recovered = self.checkpoint(path, header, groups, resume=True, discard_uncommitted=True)
        self.assertEqual(recovered.processed, 1)
        self.assertEqual(len(list(self.root.glob("*.unverified-*"))), 1)
        recovered.append(success(groups[1]))
        recovered.commit_verified()
        self.assertEqual(recovered.processed, 2)

    def test_invalidated_checkpoint_cannot_resume_even_if_source_identity_restored(self):
        path, header, groups = self.setup_checkpoint()
        writer = self.checkpoint(path, header, groups, resume=False)
        writer.append(success(groups[0]))
        writer.invalidate()
        writer.close()
        with self.assertRaisesRegex(ValueError, "invalidated"):
            Checkpoint(path, header, groups, resume=True, discard_uncommitted=True)

    def test_writer_lease_and_external_append_are_rejected(self):
        path, header, groups = self.setup_checkpoint()
        writer = self.checkpoint(path, header, groups, resume=False)
        with self.assertRaisesRegex(ValueError, "writer"):
            Checkpoint(path, header, groups, resume=True)
        with path.open("ab") as stream:
            stream.write(b"extra\n")
        with self.assertRaisesRegex(ValueError, "outside"):
            writer.append(success(groups[0]))

    def test_resume_rejects_stale_identity_corruption_skips_and_false_success(self):
        path, header, groups = self.setup_checkpoint()
        writer = self.checkpoint(path, header, groups, resume=False)
        writer.append(success(groups[0]))
        writer.commit_verified()
        writer.close()
        original = path.read_bytes()
        stale = {**header, "snapshot_id": "changed"}
        with self.assertRaisesRegex(ValueError, "identity"):
            Checkpoint(path, stale, groups, resume=True)
        records = [json.loads(line) for line in original.splitlines()]
        for mutation in ("checksum", "skip", "target"):
            altered = json.loads(json.dumps(records))
            row = altered[1]
            if mutation == "checksum":
                row["result"]["lookup_ms"] += 1
            elif mutation == "skip":
                row["group_position"] = 1
            else:
                row["result"]["found_targets"] = []
            if mutation != "checksum":
                row.pop("record_sha256")
                row["record_sha256"] = digest(row)
            path.write_bytes(b"\n".join(encoded(row) for row in altered) + b"\n")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                Checkpoint(path, header, groups, resume=True)
        path.write_bytes(original)

    def test_empty_catalog_and_completed_shard_cannot_claim_complete_catalog(self):
        empty = Catalog((), 0, digest([]))
        empty_header = make_header(empty, (), {}, shards=1, shard_index=0, max_pages=128)
        checkpoint = self.checkpoint(self.root / "empty.jsonl", empty_header, (), resume=False)
        self.assertFalse(summarize(checkpoint, new_groups=0, startup_ms=None, run_seconds=0)["complete_catalog_retrieval_verified"])
        path, _, groups = self.setup_checkpoint((Group(0, "a", ("甲",), 1),))
        shard_header = make_header(Catalog(groups, 1, "x"), groups, {}, shards=4, shard_index=0, max_pages=128)
        shard = self.checkpoint(path, shard_header, groups, resume=False)
        shard.append(success(groups[0]))
        shard.commit_verified()
        summary = summarize(shard, new_groups=1, startup_ms=0, run_seconds=0)
        self.assertTrue(summary["all_selected_target_texts_reached"])
        self.assertFalse(summary["complete_catalog_retrieval_verified"])

    def test_actual_engine_public_catalog_retrieval_without_learning_or_db_mutation(self):
        path = self.root / "real.sqlite3"
        database(path, [("火炬", "fo2 geoi6", 50), ("香港", "hoeng1 gong2", 30),
                        ("尖", "zim1", 0), ("染", "jim5", 1000), ("甲", "aa1", 0), ("乙", "a1", 0)])
        before = path.read_bytes()
        with Engine(path, learning_path=None, prefer_yale=True) as engine:
            for group in build_catalog(path).groups:
                with self.subTest(raw=group.raw):
                    self.assertEqual(probe_group(engine, group, max_pages=128)["status"], "all_found")
            self.assertIsNone(engine.learning_path)
        self.assertEqual(path.read_bytes(), before)

    def test_output_guard_cannot_replace_dictionary_fixture_or_source(self):
        project = Path(__file__).resolve().parents[1]
        protected = (project / "data/generated/lexicon.sqlite3", project / "eval/yale_expected.json")
        self.assertEqual(output_path(project / ".local/catalog.jsonl", suffix=".jsonl", protected=protected), project / ".local/catalog.jsonl")
        for path in (*protected, project / "tools/check_yale_catalog.py", self.root / "outside.jsonl"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                output_path(path, suffix=".jsonl", protected=protected)


if __name__ == "__main__":
    unittest.main()
