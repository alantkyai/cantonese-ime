"""Text-only source correspondence and loss-accounting tests."""
from dataclasses import FrozenInstanceError, fields
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime import cccedict_headwords as reader


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "data/supplements/cccedict-headwords.sources.lock.json"
REAL_DIRECTORY = ROOT / "data/vendor/cc-cedict/2026-10-21-f6b2248b589a"


def source_bytes(rows, *, changes=None, bom=False):
    header = {"version": "1", "format": "ts", "charset": "UTF-8",
              "entries": str(len(rows)), "publisher": "MDBG", "license": reader.LICENSE_URL,
              "date": "2026-10-21T05:46:59Z"}
    header.update(changes or {})
    text = ("# CC-CEDICT\n# Published by MDBG\n# " + reader.LICENSE_DECLARATION
            + "\n# " + reader.LICENSE_URL + "\n"
            + "".join(f"#! {key}={value}\n" for key, value in header.items())
            + "\n".join(rows) + "\n")
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


class HeadwordReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / reader.DATA_FILE

    def read(self, rows, **options):
        self.path.write_bytes(source_bytes(rows, **options))
        stats, reviews = {}, []
        records = list(reader.read_cccedict_headwords(self.path, stats=stats, review_rows=reviews))
        return records, stats, reviews

    def assert_source_rejected(self, payload):
        self.path.write_bytes(payload)
        stats, reviews = {"sentinel": 7}, [{"sentinel": True}]
        iterator = reader.read_cccedict_headwords(self.path, stats=stats, review_rows=reviews)
        with self.assertRaises(ValueError):
            next(iterator)
        self.assertEqual(stats, {"sentinel": 7})
        self.assertEqual(reviews, [{"sentinel": True}])

    def test_occurrences_scripts_hashes_and_immutable_text_only_records(self):
        raw = "漢語 汉语 [han4 yu3] /Mandarin definition must never become a reading/"
        records, stats, reviews = self.read([raw, "你好 你好 [ni3 hao3] /hello/", raw], bom=True)
        self.assertEqual([entry.text for entry in records], ["漢語", "汉语", "你好", "你好", "漢語", "汉语"])
        self.assertEqual([entry.script for entry in records], ["traditional", "simplified"] * 3)
        self.assertLess(records[0].line, records[2].line)
        self.assertEqual(records[0].raw_line_sha256, hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(records[0].raw_line_sha256, records[1].raw_line_sha256)
        self.assertEqual(records[0].source, reader.SOURCE_ID)
        self.assertEqual({field.name for field in fields(reader.HeadwordRecord)},
                         {"text", "line", "script", "raw_line_sha256", "source"})
        self.assertFalse(hasattr(records[0], "reading"))
        with self.assertRaises(FrozenInstanceError):
            records[0].text = "改"
        self.assertEqual(stats["form_candidates"], 6)
        self.assertEqual(stats["accepted_occurrences"], 6)
        self.assertEqual(stats["unique_han_forms"], 3)
        self.assertEqual(stats["identical_form_rows"], 1)
        self.assertEqual(reviews, [])

    def test_foreign_forms_quarantined_per_occurrence_without_repair_or_definition(self):
        records, stats, reviews = self.read([
            "ABC 你好 [A B C] /private ignored definition/",
            "你好! 你好! [ni3 hao3] /another definition/",
            "〇𰀀 〇𰀀 [ling2] /no syllable alignment inference/",
        ])
        self.assertEqual([entry.text for entry in records], ["你好", "〇𰀀", "〇𰀀"])
        self.assertEqual([row["text"] for row in reviews], ["ABC", "你好!", "你好!"])
        self.assertEqual(stats["source_rows"] * 2, stats["accepted_occurrences"] + stats["quarantined_forms"])
        self.assertEqual(stats["review_records"], 3)
        self.assertEqual(stats["unique_non_han_forms"], 2)
        source_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        for row in reviews:
            self.assertEqual(row["reason"], "non_han_headword")
            self.assertEqual(row["status"], "quarantined")
            self.assertEqual(row["scope"], "headword")
            self.assertEqual(row["source_file"], reader.DATA_FILE)
            self.assertEqual(row["source_sha256"], source_hash)
            self.assertIn(row["script"], ("traditional", "simplified"))
            self.assertEqual(len(row["raw_line_sha256"]), 64)
        encoded = json.dumps(reviews)
        self.assertNotIn("private", encoded)
        self.assertNotIn("ni3", encoded)
        self.assertNotIn("reading", encoded)

    def test_late_malformed_record_never_publishes_earlier_valid_record(self):
        self.assert_source_rejected(source_bytes(["你好 你好 [ni3 hao3] /hello/", "malformed row"]))

    def test_bad_structure_count_utf8_and_empty_source_rejected(self):
        valid = ["你好 你好 [ni3 hao3] /hello/"]
        invalid = [
            b"", source_bytes([]), source_bytes(valid, changes={"entries": "2"}),
            source_bytes(valid, changes={"entries": "01"}),
            source_bytes(["你好 你好 ni3 hao3 /missing brackets/"]),
            source_bytes(["你好 你好 [ni3 [hao3]] /nested brackets/"]),
            source_bytes(["你好 你好 [ni3 hao3] missing definition delimiters"]),
            source_bytes(valid) + b"\xff", source_bytes(valid).replace(b"/hello/", b"/hel\x00lo/"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload[-70:]):
                self.assert_source_rejected(payload)

    def test_wrong_header_license_and_attribution_rejected(self):
        valid = ["你好 你好 [ni3 hao3] /hello/"]
        for key, value in [("version", "2"), ("format", "st"), ("charset", "GB2312"),
                           ("license", "https://creativecommons.org/publicdomain/zero/1.0/"),
                           ("publisher", "other"), ("date", "2026-10-21")]:
            with self.subTest(key=key):
                self.assert_source_rejected(source_bytes(valid, changes={key: value}))
        self.assert_source_rejected(source_bytes(valid).replace(b"# Published by MDBG", b"# anonymous"))
        self.assert_source_rejected(source_bytes(valid).replace(reader.LICENSE_DECLARATION.encode(), b"wrong terms"))

    def test_duplicate_or_late_header_directive_rejected(self):
        valid = source_bytes(["你好 你好 [ni3 hao3] /hello/"])
        self.assert_source_rejected(valid.replace(b"#! version=1", b"#! version=1\n#! version=1"))
        self.assert_source_rejected(valid + b"#! entries=1\n")

    def test_source_row_line_and_size_limits_fail_before_publication(self):
        valid = source_bytes(["你好 你好 [ni3 hao3] /hello/", "你好 你好 [ni3 hao3] /hello/"])
        for constant, limit in [("MAX_SOURCE_BYTES", 100), ("MAX_LINE_BYTES", 8),
                                ("MAX_LINES", 3), ("MAX_ROWS", 1)]:
            with self.subTest(constant=constant), patch.object(reader, constant, limit):
                self.assert_source_rejected(valid)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        payload = source_bytes(["漢語 汉语 [han4 yu3] /ignored/"])
        fixtures = {
            reader.DATA_FILE: payload,
            reader.ARCHIVE_FILE: gzip.compress(payload, mtime=0),
            "download-page.html": (reader.LICENSE_DECLARATION + " " + reader.LICENSE_URL).encode(),
            "LICENSE-CC-BY-SA-4.0.txt": (REAL_DIRECTORY / "LICENSE-CC-BY-SA-4.0.txt").read_bytes(),
            "ATTRIBUTION.md": b"CC-CEDICT MDBG Paul Andrew Denisowski; Mandarin ignored, Cantonese never inferred.",
        }
        self.lock = {"schema_version": 1, "source_id": reader.SOURCE_ID, "license": "CC-BY-SA-4.0",
                     "license_declaration": reader.LICENSE_DECLARATION,
                     "source_release_header": {"version": "1", "format": "ts", "charset": "UTF-8",
                                               "entries": 1, "date": "2026-10-21T05:46:59Z"}, "files": []}
        for name, content in fixtures.items():
            (self.directory / name).write_bytes(content)
            self.lock["files"].append({"name": name, "sha256": hashlib.sha256(content).hexdigest(),
                                       "size_bytes": len(content)})

    def verify(self):
        reader.verify_cccedict_headwords_snapshot(self.directory, self.lock)

    def replace_and_relock(self, name, payload):
        (self.directory / name).write_bytes(payload)
        record = next(item for item in self.lock["files"] if item["name"] == name)
        record.update(sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload))

    def test_valid_snapshot_and_real_snapshot(self):
        self.verify()
        lock = json.loads(LOCK_PATH.read_text("utf-8"))
        reader.verify_cccedict_headwords_snapshot(ROOT / lock["local_directory"], lock)

    def test_real_source_full_occurrence_and_loss_accounting(self):
        stats, reviews = {}, []
        records = list(reader.read_cccedict_headwords(REAL_DIRECTORY / reader.DATA_FILE,
                                                    stats=stats, review_rows=reviews))
        self.assertEqual(stats["source_rows"], 125295)
        self.assertEqual(stats["form_candidates"], 250590)
        self.assertEqual(len(records), 248980)
        self.assertEqual(stats["unique_han_forms"], 197075)
        self.assertEqual(len(reviews), 1610)
        self.assertEqual(stats["form_candidates"], len(records) + len(reviews))
        self.assertTrue(records)

    def test_same_size_hash_drift_and_missing_file_rejected(self):
        path = self.directory / "ATTRIBUTION.md"
        path.write_bytes(path.read_bytes().replace(b"MDBG", b"xxxx"))
        with self.assertRaises(ValueError):
            self.verify()
        path.unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_valid_gzip_with_different_content_is_not_correspondence(self):
        self.replace_and_relock(reader.ARCHIVE_FILE, gzip.compress(b"other source", mtime=0))
        with self.assertRaisesRegex(ValueError, "gzip content differs"):
            self.verify()

    def test_malformed_gzip_rejected_even_if_hash_relocked(self):
        self.replace_and_relock(reader.ARCHIVE_FILE, b"not gzip")
        with self.assertRaises(ValueError):
            self.verify()
        corrupted = bytearray(gzip.compress(b"source payload", mtime=0))
        corrupted[10] = (corrupted[10] & 0xF8) | 7  # forbidden DEFLATE block type
        self.replace_and_relock(reader.ARCHIVE_FILE, bytes(corrupted))
        with self.assertRaisesRegex(ValueError, "Malformed CC-CEDICT gzip"):
            self.verify()

    def test_truncated_license_or_wrong_page_declaration_rejected(self):
        self.replace_and_relock("LICENSE-CC-BY-SA-4.0.txt", b"Attribution-ShareAlike 4.0 International")
        with self.assertRaisesRegex(ValueError, "full license"):
            self.verify()
        self.replace_and_relock("LICENSE-CC-BY-SA-4.0.txt", (REAL_DIRECTORY / "LICENSE-CC-BY-SA-4.0.txt").read_bytes())
        self.replace_and_relock("download-page.html", b"Creative Commons Attribution 4.0")
        with self.assertRaisesRegex(ValueError, "download page"):
            self.verify()

    def test_bad_lock_identity_header_or_size_rejected(self):
        original = copy.deepcopy(self.lock)
        for key, value in [("source_id", "cccedict:pronunciations"), ("license", "CC-BY-4.0"),
                           ("schema_version", 2), ("license_declaration", "other")]:
            with self.subTest(key=key):
                self.lock = copy.deepcopy(original)
                self.lock[key] = value
                with self.assertRaises(ValueError):
                    self.verify()
        self.lock = copy.deepcopy(original)
        self.lock["source_release_header"]["entries"] = 2
        with self.assertRaises(ValueError):
            self.verify()
        self.lock = copy.deepcopy(original)
        self.lock["files"][0]["size_bytes"] = True
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_notice_duplicate_and_unsafe_paths_rejected(self):
        original = copy.deepcopy(self.lock)
        self.lock["files"] = self.lock["files"][:-1]
        with self.assertRaises(ValueError):
            self.verify()
        for name in ("../cedict_ts.u8", "C:/cedict_ts.u8", "\\\\server\\share", "folder/../cedict_ts.u8",
                     "cedict_ts.u8.", "./cedict_ts.u8"):
            with self.subTest(name=name):
                self.lock = copy.deepcopy(original)
                self.lock["files"][0]["name"] = name
                with self.assertRaises(ValueError):
                    self.verify()
        self.lock = copy.deepcopy(original)
        self.lock["files"].append(copy.deepcopy(self.lock["files"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
