"""CC-Canto source parsing and tiny-build integration; no network/live DB writes."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime.cccanto import read_attested_bases, read_cccanto_entries, verify_cccanto_snapshot
from cantonese_ime.dictionary import build_dictionary


class CCCantoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "cccanto-webdist.txt"
        self.allowed = {"nei", "hou", "jan", "saam", "jat", "jau", "cin", "ngaa", "zi", "waa"}

    def read(self, content, **kwargs):
        self.path.write_text(content, encoding="utf-8")
        return list(read_cccanto_entries(self.path, allowed_bases=self.allowed, **kwargs))

    def test_explicit_traditional_and_simplified_forms_keep_reading_not_pinyin(self):
        rows = self.read("# fixture\n話 话 [hua4] {waa6} /speech/\n你好 你好 [ni3 hao3] {nei5 hou2} /hello/\n")
        self.assertEqual([(row.text, row.reading) for row in rows], [("話", "waa6"), ("话", "waa6"), ("你好", "nei5 hou2")])
        self.assertTrue(all(row.weight == 0 for row in rows))
        self.assertTrue(all(row.source == "cccanto:dictionary" for row in rows))
        self.assertEqual(rows[2].base_reading, "nei hou")
        self.assertEqual(rows[2].compact, "neihou")

    def test_second_export_has_distinct_source_and_no_definitions_required(self):
        self.path = self.root / "cccedict-canto-readings-150923.txt"
        rows = self.read("話 话 [hua4] {waa6}\n")
        self.assertEqual({row.source for row in rows}, {"cccanto:cedict-readings"})

    def test_bom_case_whitespace_normalization_and_pair_dedup(self):
        stats = {}
        rows = self.read("\ufeff# source\n你好 你好 [ni3 hao3] {NEI5   HOU2}\n你好 你好 [ni3hao3] {nei5 hou2}\n", stats=stats)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].reading, "nei5 hou2")
        self.assertEqual(stats["normalized_reading_rows"], 1)
        self.assertEqual(stats["accepted_rows"], 2)
        self.assertEqual(stats["duplicate_entries"], 1)

    def test_missing_or_malformed_braces_never_fall_back_to_mandarin(self):
        review = []
        rows = self.read("你好 你好 [ni3 hao3] /hello/\n陳慧琳 陈慧琳 [chen2 hui4 lin2] {can4 wai6} lam4} /secret definition/\n", review_rows=review)
        self.assertEqual(rows, [])
        self.assertEqual([row["reason"] for row in review], ["malformed_record", "malformed_record"])
        self.assertNotIn("secret definition", json.dumps(review))
        self.assertTrue(all(len(row["raw_line_sha256"]) == 64 for row in review))

    def test_noncanonical_notation_and_unknown_spellings_are_not_repaired(self):
        stats, review = {}, []
        rows = self.read("你好 你好 [ni3hao3] {nei5 hou7}\n你好 你好 [ni3hao3] {nei5 hou2/3}\n日 日 [ri4] {yat6}\n", stats=stats, review_rows=review)
        self.assertEqual(rows, [])
        self.assertEqual(stats["quarantined_rows"], 3)
        self.assertEqual(review[-1]["unknown_bases"], ["yat"])
        self.assertEqual(review[-1]["raw_reading"], "yat6")

    def test_unaligned_or_punctuated_forms_are_quarantined_without_stripping(self):
        stats, review = {}, []
        rows = self.read("人蔘 人参 [ren2shen1] {jan4}\n一人，一人 一人，一人 [a] {jat1 jan4 jat1 jan4}\n瓩 瓩 [qian1 wa3] {cin1 ngaa5}\n", stats=stats, review_rows=review)
        self.assertEqual(rows, [])
        self.assertEqual(stats["quarantined_rows"], 3)
        self.assertEqual(stats["quarantined_forms"], 4)
        self.assertTrue(all(row["reason"] == "codepoint_syllable_alignment" for row in review))
        self.assertEqual(review[-1]["text"], "瓩")

    def test_each_text_variant_is_validated_separately(self):
        stats, review = {}, []
        rows = self.read("人蔘 人 [ren2] {jan4}\n", stats=stats, review_rows=review)
        self.assertEqual([(row.text, row.reading) for row in rows], [("人", "jan4")])
        self.assertEqual(stats["accepted_rows"], 1)
        self.assertEqual(stats["quarantined_forms"], 1)
        self.assertEqual(review[0]["text"], "人蔘")

    def test_accounting_invariants_include_duplicates_and_partial_rows(self):
        stats, review = {}, []
        rows = self.read("話 话 [hua4] {waa6}\n話 话 [hua4] {waa6}\n人蔘 人 [ren2] {jan4}\nbroken\n日 日 [ri4] {yat6}\n", stats=stats, review_rows=review)
        self.assertEqual(stats["input_rows"], stats["accepted_rows"] + stats["quarantined_rows"])
        self.assertEqual(stats["form_candidates"], stats["accepted_entries"] + stats["duplicate_entries"] + stats["quarantined_forms"])
        self.assertEqual(stats["accepted_entries"], len(rows))
        self.assertEqual(stats["review_records"], len(review))

    def test_source_size_inventory_shape_and_unknown_kind_are_rejected(self):
        inventory = self.root / "parser-attested-bases.json"
        for value in ([], {"schema_version": 1, "bases": ["nei", "nei"]}, {"schema_version": 1, "bases": ["bad5"]}):
            inventory.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_attested_bases(inventory)
        self.path = self.root / "unknown.txt"
        with self.assertRaisesRegex(ValueError, "source kind"):
            self.read("話 话 [hua4] {waa6}\n")

    def test_tiny_build_preserves_earlier_weights_and_marks_combined_data_license(self):
        (self.root / "jyut6ping3.chars.dict.yaml").write_text("---\nname: fixture\n...\n話\twaa6\t99\n", encoding="utf-8")
        self.path.write_text("話 话 [hua4] {waa6}\n", encoding="utf-8")
        (self.root / "parser-attested-bases.json").write_text(json.dumps({"schema_version": 1, "bases": sorted(self.allowed)}), encoding="utf-8")
        output = self.root / "fixture.sqlite3"
        stats = build_dictionary(self.root, output, supplements={"cccanto": self.path})
        self.assertEqual(stats["combined_data_license"], "CC-BY-SA-4.0")
        self.assertEqual(stats["supplement_stats"]["cccanto"]["added_pairs"], 1)
        with closing(sqlite3.connect(output)) as db:
            rows = {text: (weight, source, origin) for text, weight, source, origin in db.execute("SELECT text,weight,source,origin FROM entries")}
        self.assertEqual(rows["話"], (99, "jyut6ping3.chars.dict.yaml", "explicit"))
        self.assertEqual(rows["话"], (0, "cccanto:dictionary", "supplement"))

    def test_selected_real_snapshot_verifies_and_full_parser_counts_are_accounted(self):
        root = Path(__file__).resolve().parents[1]
        lock = json.loads((root / "data/supplements/cccanto.sources.lock.json").read_text(encoding="utf-8"))
        directory = root / lock["local_directory"]
        verify_cccanto_snapshot(directory, lock)
        for filename in ("cccanto-webdist.txt", "cccedict-canto-readings-150923.txt"):
            stats, review = {}, []
            rows = list(read_cccanto_entries(directory / filename, stats=stats, review_rows=review))
            self.assertGreater(len(rows), 10000)
            self.assertEqual(stats["input_rows"], stats["accepted_rows"] + stats["quarantined_rows"])
            self.assertEqual(stats["form_candidates"], stats["accepted_entries"] + stats["duplicate_entries"] + stats["quarantined_forms"])
            self.assertEqual(len(rows), len({(row.text, row.reading) for row in rows}))
            self.assertTrue(all(row.weight == 0 for row in rows))
            self.assertEqual(len(review), stats["review_records"])

    def test_new_cc_character_readings_do_not_broaden_rime_phrase_autoencoding(self):
        from cantonese_ime.autoencode import ScriptAutoencoder
        phrase = "三" * 5
        # Control: mixing two unknown-frequency character alternatives really
        # hits the conservative32-path limit, instead of publishing partialcodes.
        self.assertEqual(ScriptAutoencoder([("三", "saam1", 0), ("三", "saam3", 0)]).encode(phrase).status,
                         "truncated")
        (self.root / "jyut6ping3.chars.dict.yaml").write_text(
            "---\nname: fixture\n...\n三\tsaam1\t0\n話\twaa6\t0\n", encoding="utf-8")
        (self.root / "jyut6ping3.phrase.dict.yaml").write_text(
            "---\nname: fixture\n...\n" + phrase + "\n話話\n", encoding="utf-8")
        (self.root / "parser-attested-bases.json").write_text(
            json.dumps({"schema_version": 1, "bases": sorted(self.allowed)}), encoding="utf-8")
        for kind, filename, source in (
            ("cccanto", "cccanto-webdist.txt", "cccanto:dictionary"),
            ("cccedict_cantonese", "cccedict-canto-readings-150923.txt", "cccanto:cedict-readings"),
        ):
            with self.subTest(kind=kind):
                path = self.root / filename
                path.write_text("三 三 [san1] {saam3}\n話話 话话 [hua4hua4] {waa2 waa2}\n", encoding="utf-8")
                output = self.root / (kind + ".sqlite3")
                stats = build_dictionary(self.root, output, supplements={kind: path}, autoencode_phrases=True)
                self.assertIn(source, stats["phrase_translation_policy"]["excluded_sources"])
                with closing(sqlite3.connect(output)) as db:
                    char_readings = set(db.execute("SELECT reading,source FROM entries WHERE text='三'"))
                    self.assertIn(("saam3", source), char_readings)
                    self.assertEqual(db.execute("SELECT status,path_count FROM phrase_encodings WHERE text=?", (phrase,)).fetchone(),
                                     ("encoded_unique", 1))
                    self.assertEqual(db.execute("SELECT reading FROM entries WHERE text=?", (phrase,)).fetchall(),
                                     [("saam1 saam1 saam1 saam1 saam1",)])
                    # An authored whole-word reading is retained even though its
                    # source's isolated characters cannot expand the encoder.
                    self.assertEqual(db.execute("SELECT status FROM phrase_encodings WHERE text='話話'").fetchone(),
                                     ("already_explicit",))
                    self.assertEqual(db.execute("SELECT reading,source FROM entries WHERE text='話話'").fetchall(),
                                     [("waa2 waa2", source)])


if __name__ == "__main__":
    unittest.main()
