"""The independent source auditor must detect missing pairs and forged reviews."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.audit_dictionary import _cccanto_audit


class CCCantoAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cccanto-audit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        raw = ("火炬 火炬 [huo3 ju4] {fo2 geoi6} /fixture gloss/\n"
               "月 月 [yue4] {yut6} /unattested test spelling/\n"
               "長 长 [chang2] {coeng4} /fixture gloss/\n")
        (self.root / "cccanto-webdist.txt").write_text(raw, encoding="utf-8")
        (self.root / "parser-attested-bases.json").write_text(json.dumps({"bases": ["fo", "geoi", "coeng"]}), encoding="utf-8")
        self.lock = {"source_directory": str(self.root), "files": [
            {"name": name, "matches_lock": True}
            for name in ("cccanto-webdist.txt", "parser-attested-bases.json")]}
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE entries(text,reading,origin);
            CREATE TABLE supplement_review(source,text,status,details_json);
        """)
        self.db.executemany("INSERT INTO entries VALUES (?,?,'supplement')", [
            ("火炬", "fo2 geoi6"), ("長", "coeng4"), ("长", "coeng4")])
        details = {"line": 2, "reason": "unattested_syllables", "scope": "row",
                   "raw_line_sha256": hashlib.sha256(raw.splitlines()[1].encode()).hexdigest()}
        self.db.execute("INSERT INTO supplement_review VALUES ('cccanto:dictionary','月','quarantined',?)", (json.dumps(details),))

    def audit(self):
        verified = {"supplement": set()}
        report = _cccanto_audit(self.db, self.lock, verified)
        return report["counts"], verified

    def test_all_aligned_forms_and_exact_quarantine_are_accounted(self):
        counts, verified = self.audit()
        self.assertEqual(counts["explicit_rows_present"], 3)
        self.assertEqual(len(verified["supplement"]), 3)
        self.assertEqual(counts.get("explicit_rows_missing", 0), 0)
        self.assertEqual(counts.get("quarantine_review_missing", 0), 0)

    def test_missing_simplified_pair_cannot_pass(self):
        self.db.execute("DELETE FROM entries WHERE text='长'")
        counts, _ = self.audit()
        self.assertEqual(counts["explicit_rows_missing"], 1)

    def test_review_needs_exact_source_line_and_hash(self):
        self.db.execute("UPDATE supplement_review SET details_json=?", (json.dumps({
            "line": 2, "reason": "unattested_syllables", "scope": "row", "raw_line_sha256": "0" * 64}),))
        counts, _ = self.audit()
        self.assertEqual(counts["quarantine_review_missing"], 1)

    def test_unverified_source_file_never_attests_live_entries(self):
        self.lock["files"][0]["matches_lock"] = False
        counts, verified = self.audit()
        self.assertEqual(verified["supplement"], set())
        self.assertEqual(counts.get("source_files_audited", 0), 0)


if __name__ == "__main__":
    unittest.main()
