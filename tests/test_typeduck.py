"""TypeDuck import tests use small project-authored text fixtures only."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from cantonese_ime.typeduck import read_typeduck_entries, verify_typeduck_snapshot


HEADER = '---\nname: jyut6ping3\nversion: "fixture"\nuse_preset_vocabulary: true\n...\n'


class TypeDuckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cantonese-typeduck-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "jyut6ping3.dict.yaml"

    def write(self, body: str, header: str = HEADER) -> None:
        self.path.write_text(header + body, encoding="utf-8")

    def test_explicit_readings_preserve_text_tones_and_unknown_weight(self) -> None:
        self.write("你好\tNEI5  HOU2\t785.1%\n𠮷\tgat1\t0.0%\nＲ\taa1 lou4\t50.0%\n")
        stats = {}
        rows = list(read_typeduck_entries(self.path, stats=stats))
        self.assertEqual([(row.text, row.reading) for row in rows],
                         [("你好", "nei5 hou2"), ("𠮷", "gat1"), ("Ｒ", "aa1 lou4")])
        self.assertEqual((rows[0].base_reading, rows[0].compact, rows[0].syllable_count),
                         ("nei hou", "neihou", 2))
        self.assertTrue(all(row.weight == 0 and row.source == "typeduck:principal" for row in rows))
        self.assertEqual(stats["source_above_100_percentage_rows"], 1)
        self.assertEqual(stats["source_zero_percentage_rows"], 1)

    def test_all_explicit_polyphonic_pairs_retained_even_with_zero_source_percentage(self) -> None:
        self.write("好\thou2\t100.0%\n好\thou3\t0.0%\n")
        self.assertEqual([row.reading for row in read_typeduck_entries(self.path)], ["hou2", "hou3"])

    def test_annotations_quarantined_with_physical_line_and_unmodified_fields(self) -> None:
        body = "# comment\n🦆\t~daa2 ~dak1\t100.0%\n字\tzi6\t100.0%\n"
        self.write(body)
        reviews = []
        rows = list(read_typeduck_entries(self.path, review_rows=reviews))
        self.assertEqual([row.text for row in rows], ["字"])
        self.assertEqual(reviews, [{"source": "typeduck:principal", "line": 7, "text": "🦆", "raw_text": "🦆",
                                    "raw_reading": "~daa2 ~dak1", "raw_weight": "100.0%",
                                    "raw_line": "🦆\t~daa2 ~dak1\t100.0%", "status": "quarantined",
                                    "reason": "phonetic_annotation"}])

    def test_noncanonical_notation_is_not_silently_repaired(self) -> None:
        self.write("字\tzi\t100%\n字\tzi7\t100%\n字\t!zi1\t100%\n字\t\t100%\n")
        reviews = []
        self.assertEqual(list(read_typeduck_entries(self.path, review_rows=reviews)), [])
        self.assertEqual([row["raw_reading"] for row in reviews], ["zi", "zi7", "!zi1", ""])
        self.assertTrue(all(row["reason"] == "non_jyutping_reading" for row in reviews))

    def test_duplicate_accounting_balances_without_selecting_a_pronunciation(self) -> None:
        self.write("字\tzi6\t100%\n字\tzi6\t0%\n字\tzi2\t100%\n🦆\t~daa2 ~dak1\t100%\n")
        stats = {}
        rows = list(read_typeduck_entries(self.path, stats=stats))
        self.assertEqual(len(rows), 2)
        self.assertEqual(stats["duplicate_entries"], 1)
        self.assertEqual(stats["input_rows"], stats["accepted_entries"] + stats["duplicate_entries"] + stats["quarantined_rows"])

    def test_wrong_field_count_and_invalid_percentage_fail(self) -> None:
        for weight in ("100", "-1%", "NaN%", "inf%", "1e2%", "100%%", "100% "):
            with self.subTest(weight=weight):
                self.write("字\tzi6\t" + weight + "\n")
                with self.assertRaises(ValueError):
                    list(read_typeduck_entries(self.path))
        for body in ("字\tzi6\n", "字\tzi6\t100%\textra\n"):
            self.write(body)
            with self.assertRaises(ValueError):
                list(read_typeduck_entries(self.path))

    def test_bom_and_comments_supported_but_other_dictionary_headers_rejected(self) -> None:
        self.write("字\tzi6\t100%\n", "\ufeff# fixture\n" + HEADER)
        self.assertEqual(len(list(read_typeduck_entries(self.path))), 1)
        invalid_headers = ("name: jyut6ping3\n...\n", "---\nname: luna_pinyin\n...\n",
                           "---\nname: jyut6ping3\n", "---\nname: jyut6ping3\ncolumns:\n...\n",
                           "---\nname: jyut6ping3\nimport_tables:\n...\n")
        for header in invalid_headers:
            self.write("字\tzi6\t100%\n", header)
            with self.subTest(header=header), self.assertRaises(ValueError):
                list(read_typeduck_entries(self.path))

    def test_invalid_text_is_quarantined_without_changing_written_form(self) -> None:
        self.write(" 字\tzi6\t100%\n\tzi6\t100%\n字\x00\tzi6\t100%\n")
        reviews = []
        self.assertEqual(list(read_typeduck_entries(self.path, review_rows=reviews)), [])
        self.assertEqual([row["raw_text"] for row in reviews], [" 字", "", "字\x00"])

    def test_locked_source_hashes_and_principal_declaration_are_required(self) -> None:
        self.write("字\tzi6\t100%\n")
        readme = self.directory / "README.md"
        readme.write_text("Except for the reverse lookup data listed above, this repo, including the main TypeDuck dictionary and the `jyut6ping3` schema, is licensed under [CC BY 4.0]", encoding="utf-8")
        license_path = self.directory / "LICENSE"
        license_path.write_text("project-authored fixture, not actual license text", encoding="utf-8")

        def lock():
            return {"files": [{"name": p.name, "size_bytes": p.stat().st_size,
                               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                              for p in (self.path, readme, license_path)]}

        original_lock = lock()
        verify_typeduck_snapshot(self.directory, original_lock)
        self.path.write_bytes(self.path.read_bytes().replace(b"zi6", b"zi2"))
        with self.assertRaises(ValueError):
            verify_typeduck_snapshot(self.directory, original_lock)
        readme.write_text("No principal-data permission here", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "principal-data"):
            verify_typeduck_snapshot(self.directory, lock())


if __name__ == "__main__":
    unittest.main()
