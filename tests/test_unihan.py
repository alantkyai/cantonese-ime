"""Independent fixture tests for direct, provisional Unihan character data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from cantonese_ime.unihan import read_unihan_entries, verify_unihan_snapshot


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "data/vendor/unihan/18.0.0"


class UnihanTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="cantonese-unihan-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "Unihan_Readings.txt"

    def write(self, body: str, version: str = "18.0.0") -> Path:
        self.path.write_text(f"# Unihan_Readings.txt\n# Unicode Version {version}\n{body}", encoding="utf-8")
        return self.path

    def snapshot(self, *, member: bytes | None = None) -> dict:
        if not self.path.exists():
            self.write("U+4F60\tkCantonese\tnei5\n")
        with zipfile.ZipFile(self.directory / "Unihan.zip", "w") as archive:
            archive.writestr("Unihan_Readings.txt", self.path.read_bytes() if member is None else member)
        (self.directory / "LICENSE.txt").write_bytes((VENDOR / "LICENSE.txt").read_bytes())
        (self.directory / "ReadMe.txt").write_text("Fixture: Unicode 18.0.0 final data.\n", encoding="utf-8")
        return {
            "license": "Unicode-3.0", "unicode_version": "18.0.0",
            "property": "kCantonese", "property_status": "Provisional",
            "license_notice": {"text": (self.directory / "LICENSE.txt").read_text(encoding="utf-8")},
            "files": [{"name": name, "size_bytes": (self.directory / name).stat().st_size,
                       "sha256": hashlib.sha256((self.directory / name).read_bytes()).hexdigest()}
                      for name in ("Unihan.zip", "Unihan_Readings.txt", "LICENSE.txt", "ReadMe.txt")],
        }

    def test_direct_readings_have_no_invented_frequency(self) -> None:
        entries = list(read_unihan_entries(self.write("U+4F60\tkCantonese\tnei5\nU+200CD\tkCantonese\twaang4\n")))
        self.assertEqual([(entry.text, entry.reading) for entry in entries], [("你", "nei5"), ("𠃍", "waang4")])
        for entry in entries:
            self.assertEqual(entry.weight, 0.0)
            self.assertEqual(entry.source, "unihan:kCantonese")
            self.assertEqual(entry.syllable_count, 1)
            self.assertEqual(entry.base_reading, entry.reading[:-1])
            self.assertEqual(entry.compact, entry.base_reading)

    def test_multiple_values_are_alternative_character_readings(self) -> None:
        entries = list(read_unihan_entries(self.write("U+597D\tkCantonese\thou2  hou3\n")))
        self.assertEqual([(entry.text, entry.reading, entry.syllable_count) for entry in entries], [("好", "hou2", 1), ("好", "hou3", 1)])

    def test_unrelated_properties_cannot_invent_readings(self) -> None:
        path = self.write("U+597D\tkDefinition\tgood; love\nU+597D\tkMandarin\thao3\nU+597D\tkCantonese\thou2 hou3\n")
        stats, review = {}, []
        entries = list(read_unihan_entries(path, stats=stats, review_rows=review))
        self.assertEqual([entry.reading for entry in entries], ["hou2", "hou3"])
        self.assertEqual(stats, {"scanned_data_rows": 3, "ignored_other_property_rows": 2,
                                 "input_rows": 1, "alternative_reading_rows": 1, "accepted_entries": 2})
        self.assertEqual(review, [])

    def test_empty_and_comment_only_data_is_not_an_inferred_dictionary(self) -> None:
        self.assertEqual(list(read_unihan_entries(self.write("\n# no direct readings\n"))), [])

    def test_bad_columns_fail_with_source_line(self) -> None:
        for row in ("U+4F60\tkCantonese", "U+4F60\tkCantonese\tnei5\textra"):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, r"Unihan_Readings\.txt:3:"):
                list(read_unihan_entries(self.write(row + "\n")))

    def test_bad_unicode_scalars_are_rejected(self) -> None:
        for value in ("U+110000", "U+D800", "U+DCFF", "U+ZZZZ", "4F60", "U+0000001"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "invalid Unicode scalar"):
                list(read_unihan_entries(self.write(f"{value}\tkCantonese\tnei5\n")))

    def test_malformed_readings_are_rejected_without_repair(self) -> None:
        for value in ("", "nei", "NEI5", "nei0", "nei7", "nei5*", "!nei5", "neiiiiii5", "nei⁵"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "malformed direct kCantonese"):
                list(read_unihan_entries(self.write(f"U+4F60\tkCantonese\t{value}\n")))

    def test_duplicate_property_rows_and_values_are_rejected(self) -> None:
        for rows in ("U+597D\tkCantonese\thou2\nU+597D\tkCantonese\thou3\n",
                     "U+597D\tkCantonese\thou2 hou2\n"):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "duplicate kCantonese"):
                list(read_unihan_entries(self.write(rows)))

    def test_snapshot_checks_pinned_files_and_member_bytes(self) -> None:
        verify_unihan_snapshot(self.directory, self.snapshot())
        mismatched = self.snapshot(member=b"# different archive member\n")
        with self.assertRaisesRegex(ValueError, "differ from the pinned archive member"):
            verify_unihan_snapshot(self.directory, mismatched)

    def test_snapshot_tampering_is_rejected(self) -> None:
        lock = self.snapshot()
        self.path.write_text(self.path.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_unihan_snapshot(self.directory, lock)

    def test_snapshot_version_is_verified_independently_of_hashes(self) -> None:
        self.write("U+4F60\tkCantonese\tnei5\n", version="17.0.0")
        with self.assertRaisesRegex(ValueError, "header disagrees"):
            verify_unihan_snapshot(self.directory, self.snapshot())

    def test_snapshot_license_and_provisional_status_are_required(self) -> None:
        lock = self.snapshot()
        for field, value in (("license", "unknown"), ("property_status", "Normative"), ("property", "kMandarin")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_unihan_snapshot(self.directory, {**lock, field: value})
        with self.assertRaisesRegex(ValueError, "full Unicode License V3 notice"):
            verify_unihan_snapshot(self.directory, {**lock, "license_notice": {}})

    def test_data_size_is_bounded_before_reading(self) -> None:
        self.write("U+4F60\tkCantonese\tnei5\n")
        with patch("cantonese_ime.unihan.MAX_READINGS_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "size limit"):
                list(read_unihan_entries(self.path))

    def test_selected_official_snapshot_retains_all_direct_pairs(self) -> None:
        lock = json.loads((ROOT / "data/supplements/unihan.sources.lock.json").read_text(encoding="utf-8"))
        verify_unihan_snapshot(VENDOR, lock)
        stats = {}
        entries = list(read_unihan_entries(VENDOR / "Unihan_Readings.txt", stats=stats))
        pairs = {(entry.text, entry.reading) for entry in entries}
        self.assertEqual(len(pairs), 29936)
        self.assertEqual(len(entries), 29936)
        self.assertEqual(stats["input_rows"], 29936)
        self.assertEqual(stats["accepted_entries"], 29936)
        self.assertIn(("乄", "ngau1"), pairs)
        self.assertIn(("𠃍", "waang4"), pairs)
        self.assertFalse(any(text in ("罓", "肀", "𧘇") for text, reading in pairs))


if __name__ == "__main__":
    unittest.main()
