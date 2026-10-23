from pathlib import Path
import tempfile
import unittest

from cantonese_ime.supplements import read_lshk_entries


HEADER = "CH\tUCODE\tJP\tINIT\tFINL\tTONE\tDESC\tDESC_JP\n"


class SupplementTests(unittest.TestCase):
    def test_explicit_single_and_multisyllable_readings_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "list.tsv"
            path.write_text(HEADER + "你\tU+4F60\tnei5\tn\tei\t5\t\tnei5\n"
                            + "𠯢\tU+20BE2\tsaa1 aa6\t\t\t\t\tsaa1 aa6\n", encoding="utf-8")
            stats = {}
            entries = list(read_lshk_entries(path, stats=stats))
            self.assertEqual([(e.text, e.reading) for e in entries], [("你", "nei5"), ("𠯢", "saa1 aa6")])
            self.assertEqual(stats["explicit_rows"], 2)
            self.assertEqual(stats["multisyllable_rows"], 1)
            self.assertTrue(all(e.weight == 0 for e in entries))

    def test_description_pronunciation_is_not_mislabelled_as_character_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "list.tsv"
            path.write_text(HEADER + "㓁\tU+34C1\t\t\t\t\t禿頭穴\ttuk1 tau4 jyut6\n", encoding="utf-8")
            stats, review = {}, []
            self.assertEqual(list(read_lshk_entries(path, stats=stats, review_rows=review)), [])
            self.assertEqual(stats["description_only_rows"], 1)
            self.assertEqual(review[0]["status"], "description_only")

    def test_unicode_identity_and_bad_readings_fail(self):
        for row in ("你\tU+4F61\tnei5\tn\tei\t5\t\tnei5\n",
                    "你\tU+4F60\tnei7\tn\tei\t7\t\tnei7\n"):
            with self.subTest(row=row), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "list.tsv"
                path.write_text(HEADER + row, encoding="utf-8")
                with self.assertRaises(ValueError):
                    list(read_lshk_entries(path))


if __name__ == "__main__":
    unittest.main()
