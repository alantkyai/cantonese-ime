"""Tests for Rime parsing, trustworthy weighting, and SQLite construction."""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime.dictionary import DictionaryEntry, build_dictionary, read_entries, verify_source_files


FIXTURE = Path(__file__).parent / "fixtures" / "rime_valid.dict.yaml"
HEADER = '---\nname: test_fixture\nversion: "1"\nsort: by_weight\n...\n'


class DictionaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cantonese-dictionary-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def write_source(self, filename: str, rows: str, *, header: str = HEADER) -> Path:
        path = self.directory / filename
        path.write_text(header + rows, encoding="utf-8")
        return path

    def test_parser_normalizes_readings_and_derived_lookup_keys(self) -> None:
        entries = list(read_entries(FIXTURE, frequencies={"你好": 100, "妳": 25}))
        self.assertEqual(len(entries), 4)
        self.assertTrue(all(isinstance(entry, DictionaryEntry) for entry in entries))
        phrase = next(entry for entry in entries if entry.text == "你好")
        self.assertEqual(phrase.reading, "nei5 hou2")
        self.assertEqual(phrase.base_reading, "nei hou")
        self.assertEqual(phrase.compact, "neihou")
        self.assertEqual(phrase.syllable_count, 2)
        self.assertEqual(phrase.weight, 2)
        self.assertEqual(next(entry.reading for entry in entries if entry.text == "妳"), "nei5")

    def test_missing_percent_and_explicit_weights_follow_frequency_semantics(self) -> None:
        path = self.write_source("weights.dict.yaml", "字\tzi6\n字\tzi2\t3%\n字\tzi1\t5\n未知\tmei6 zi1\n")
        entries = list(read_entries(path, frequencies={"字": 100}))
        weights = {entry.reading: entry.weight for entry in entries}
        self.assertEqual(weights, {"zi6": 100, "zi2": 3, "zi1": 5, "mei6 zi1": 0})
        without_essay = list(read_entries(path))
        self.assertEqual(next(entry.weight for entry in without_essay if entry.reading == "zi2"), 0)

    def test_zero_weight_is_preserved(self) -> None:
        entries = list(read_entries(FIXTURE, frequencies={"好": 1000}))
        self.assertEqual(next(entry.weight for entry in entries if entry.text == "好"), 0)

    def test_comments_blank_lines_and_utf8_bom_are_supported(self) -> None:
        path = self.write_source("bom.dict.yaml", "\n# comment\n你\tnei5\t1\n", header="\ufeff" + HEADER)
        entries = list(read_entries(path))
        self.assertEqual([(entry.text, entry.reading) for entry in entries], [("你", "nei5")])

    def test_missing_readings_are_skipped_and_counted(self) -> None:
        path = self.write_source("missing.dict.yaml", "未標音短語\n你\tnei5\t1\n")
        stats: dict[str, int] = {}
        entries = list(read_entries(path, stats=stats))
        self.assertEqual([entry.text for entry in entries], ["你"])
        self.assertEqual(stats.get("skipped_missing_reading"), 1)

    def test_supplied_invalid_readings_are_rejected_with_location(self) -> None:
        for reading in ("nei", "nei0", "nei7", "nei55", "nei5 hou", "你好", "nei5🙂"):
            with self.subTest(reading=reading):
                path = self.write_source("bad-reading.dict.yaml", f"你\t{reading}\t1\n")
                with self.assertRaises(ValueError) as error:
                    list(read_entries(path))
                self.assertIn(str(path), str(error.exception))
                self.assertRegex(str(error.exception), r":\d+\b")

    def test_invalid_weights_cannot_contaminate_ranking(self) -> None:
        for weight in ("-1", "nan", "inf", "-inf", "not-a-number", "-3%"):
            with self.subTest(weight=weight):
                path = self.write_source("bad-weight.dict.yaml", f"你\tnei5\t{weight}\n")
                with self.assertRaises(ValueError) as error:
                    list(read_entries(path))
                self.assertIn(str(path), str(error.exception))

    def test_rime_header_is_required(self) -> None:
        for header in ("", "name: missing-start\n...\n", "---\nname: missing-end\n"):
            with self.subTest(header=header):
                path = self.write_source("bad-header.dict.yaml", "你\tnei5\t1\n", header=header)
                with self.assertRaises(ValueError):
                    list(read_entries(path))

    def make_build_inputs(self) -> None:
        self.write_source("jyut6ping3.chars.dict.yaml", "你\tnei5\t10\n好\thou2\t1\n")
        self.write_source("jyut6ping3.words.dict.yaml", "你好\tnei5 hou2\t2%\n你\tnei5\t20\n")
        self.write_source("jyut6ping3.phrase.dict.yaml", "我想食叉燒包\n香港\thoeng1 gong2\t1\n")
        (self.directory / "essay-cantonese.txt").write_text("你好\t1000\n你\t100\n", encoding="utf-8")

    def test_build_deduplicates_by_text_and_reading_using_maximum_weight(self) -> None:
        self.make_build_inputs()
        output = self.directory / "dictionary.sqlite3"
        stats = build_dictionary(self.directory, output)
        self.assertIsInstance(stats, dict)
        self.assertEqual(stats["entry_count"], 4)
        with closing(sqlite3.connect(output)) as connection:
            entries = connection.execute("SELECT text, reading, weight FROM entries ORDER BY text, reading").fetchall()
        self.assertEqual(len(entries), 4)
        self.assertEqual(next(weight for text, reading, weight in entries if text == "你"), 20)
        self.assertEqual(next(weight for text, reading, weight in entries if text == "你好"), 20)
        self.assertTrue(all(math.isfinite(weight) and weight >= 0 for _, _, weight in entries))

    def test_build_does_not_invent_readings_for_unencoded_phrases(self) -> None:
        self.make_build_inputs()
        output = self.directory / "dictionary.sqlite3"
        stats = build_dictionary(self.directory, output)
        self.assertEqual(stats.get("skipped_missing_reading"), 1)
        with closing(sqlite3.connect(output)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM entries WHERE text = ?", ("我想食叉燒包",)).fetchone()[0], 0)

    def test_build_keeps_multiple_real_readings_of_the_same_text(self) -> None:
        self.make_build_inputs()
        with (self.directory / "jyut6ping3.chars.dict.yaml").open("a", encoding="utf-8") as stream:
            stream.write("好\thou3\t2\n")
        output = self.directory / "dictionary.sqlite3"
        build_dictionary(self.directory, output)
        with closing(sqlite3.connect(output)) as connection:
            readings = connection.execute("SELECT reading FROM entries WHERE text = ? ORDER BY reading", ("好",)).fetchall()
        self.assertEqual(readings, [("hou2",), ("hou3",)])

    def test_build_produces_search_indexes_and_json_metadata(self) -> None:
        self.make_build_inputs()
        output = self.directory / "dictionary.sqlite3"
        build_dictionary(self.directory, output)
        with closing(sqlite3.connect(output)) as connection:
            indexes = connection.execute("PRAGMA index_list(entries)").fetchall()
            indexed_columns = set()
            for index in indexes:
                safe_name = index[1].replace('"', '""')
                indexed_columns.update(row[2] for row in connection.execute(f'PRAGMA index_info("{safe_name}")'))
            metadata = connection.execute("SELECT key, value FROM metadata").fetchall()
        self.assertTrue({"compact", "base_reading", "text"}.issubset(indexed_columns))
        self.assertTrue(metadata)
        for key, value in metadata:
            with self.subTest(key=key):
                json.loads(value)

    def test_rebuild_has_stable_dictionary_rows(self) -> None:
        self.make_build_inputs()
        rows = []
        for filename in ("first.sqlite3", "second.sqlite3"):
            output = self.directory / filename
            build_dictionary(self.directory, output)
            with closing(sqlite3.connect(output)) as connection:
                rows.append(connection.execute("SELECT id, text, reading, base_reading, compact, syllable_count, weight FROM entries ORDER BY id").fetchall())
        self.assertEqual(rows[0], rows[1])

    def test_build_rejects_directory_without_recognized_sources(self) -> None:
        self.write_source("unrelated.dict.yaml", "你\tnei5\t1\n")
        with self.assertRaises((ValueError, FileNotFoundError)):
            build_dictionary(self.directory, self.directory / "missing.sqlite3")

    def test_failed_rebuild_preserves_existing_database_and_manifest(self) -> None:
        self.make_build_inputs()
        output = self.directory / "dictionary.sqlite3"
        build_dictionary(self.directory, output)
        manifest = output.with_suffix(".manifest.json")
        database_before, manifest_before = output.read_bytes(), manifest.read_bytes()
        self.write_source("jyut6ping3.words.dict.yaml", "你\tnei7\t20\n")
        with self.assertRaises(ValueError):
            build_dictionary(self.directory, output)
        self.assertEqual(output.read_bytes(), database_before)
        self.assertEqual(manifest.read_bytes(), manifest_before)

    def test_source_lock_detects_content_changes_even_when_size_matches(self) -> None:
        source = self.write_source("jyut6ping3.chars.dict.yaml", "你\tnei5\t1\n")
        content = source.read_bytes()
        lock = {"files": [{"name": source.name, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}]}
        verify_source_files(self.directory, lock)
        source.write_bytes(content.replace(b"nei5", b"nei6"))
        self.assertEqual(source.stat().st_size, len(content))
        with self.assertRaises(ValueError):
            verify_source_files(self.directory, lock)


if __name__ == "__main__":
    unittest.main()
