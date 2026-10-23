"""Independent reference-grid and auditor checks; no live corpus or learning writes."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from cantonese_ime import Candidate, CandidatePage, Engine, PaginationCapacityError
from cantonese_ime import mappings
from tools.check_yale_coverage import (
    audit_dictionary, audit_reference, exercise_lookups, mapping_probe, probe_lookup, reference_rows, report_output,
)


FIXTURE = Path(__file__).resolve().parents[1] / "eval/yale_expected.json"


def create_database(path: Path, rows):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("""
            CREATE TABLE entries(id INTEGER PRIMARY KEY,text TEXT,reading TEXT,base_reading TEXT,
                compact TEXT,syllable_count INTEGER,weight REAL,source TEXT,origin TEXT,UNIQUE(text,reading));
            CREATE INDEX entries_base_reading ON entries(base_reading);
        """)
        for text, reading in rows:
            tokens = reading.split(); bases = [token[:-1] for token in tokens]
            connection.execute("INSERT INTO entries(text,reading,base_reading,compact,syllable_count,weight,source,origin) VALUES (?,?,?,?,?,?,?,?)",
                (text, reading, " ".join(bases), "".join(bases), len(tokens), 1.0, "project:auditor-fixture", "explicit"))
        connection.commit()


class FakeApi:
    """Tiny independent oracle, deliberately incomplete outside its four keys."""
    expected = {"geoi": ("geui", "table"), "fo": ("fo", "table"),
                "hm": ("hm", "jyutping_fallback"), "aa": ("a", "table"), "a": ("a", "extension")}

    def yale_ascii(self, base):
        return self.expected[base][0]

    def yale_ascii_mapping(self, base):
        spelling, status = self.expected[base]
        return SimpleNamespace(canonical=base, spelling=spelling, status=status, reason="fixture", source=("fixture",))

    def spelling_variants(self, base, mode="forgiving"):
        return {base: 0.0} if mode == "jyutping" else {base: 0.0, self.yale_ascii(base): 0.45}

    def resolve_syllable(self, raw, bases, mode="forgiving"):
        tone = raw[-1] if raw[-1:] in "123456" else None
        spelling = raw[:-1] if tone else raw
        return [SimpleNamespace(canonical=base, tone=tone) for base in bases if spelling in self.spelling_variants(base, mode)]


class YaleCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cantonese-yale-audit-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_expected_fixture_covers_independent_tables_and_user_examples(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rows = list(reference_rows(fixture))
        expected = {(row["canonical"], row["spelling"]) for row in rows}
        for relation in (("geoi", "geui"), ("zeon", "jeun"), ("ceot", "cheut"), ("zoeng", "jeung"),
                         ("zoek", "jeuk"), ("jyut", "yut"), ("zim", "jim"), ("jim", "yim"), ("kwaa", "kwa"),
                         ("saang", "saang"), ("zyu", "jyu"), ("cyun", "chyun")):
            self.assertIn(relation, expected)
        self.assertGreaterEqual(len(fixture["final_grid"]), 53)
        self.assertEqual(len(fixture["onset_grid"]), 19)
        examples = {row["id"]: row for row in fixture["word_cases"]}
        self.assertEqual(examples["teacher_formal"]["input"], "sinsaang")
        self.assertEqual(examples["teacher_requested_casual"]["kind"], "project_alias")
        self.assertEqual(examples["torch"]["input"], "fogeui")

    def test_reference_detects_wrong_converter_even_if_its_inverse_agrees(self):
        fixture = {"final_grid": [["geoi", "geui"]], "onset_grid": [], "compound_grid": [], "extension_grid": [], "fallback_grid": []}
        self.assertTrue(audit_reference(fixture, FakeApi())["passed"])
        class ConsistentlyWrong(FakeApi):
            expected = dict(FakeApi.expected, geoi=("goi", "table"))
        bad = audit_reference(fixture, ConsistentlyWrong())
        self.assertFalse(bad["passed"])
        self.assertIn("independent_expected_spelling_mismatch", bad["results"][0]["errors"])

    def test_probe_detects_missing_alias_strict_leak_and_tone_loss(self):
        class Missing(FakeApi):
            def spelling_variants(self, base, mode="forgiving"):
                return {base: 0.0}
        self.assertIn("missing_public_forgiving_alias", mapping_probe("geoi", Missing())["errors"])
        class StrictLeak(FakeApi):
            def spelling_variants(self, base, mode="forgiving"):
                return super().spelling_variants(base, "forgiving")
        self.assertIn("strict_identity_changed", mapping_probe("geoi", StrictLeak())["errors"])
        class ToneLoss(FakeApi):
            def resolve_syllable(self, raw, bases, mode="forgiving"):
                values = super().resolve_syllable(raw, bases, mode)
                return [SimpleNamespace(canonical=row.canonical, tone=None) for row in values]
        database = self.root / "tone.sqlite3"
        create_database(database, [("炬", "geoi6")])
        with closing(sqlite3.connect(database)) as connection:
            report = audit_dictionary(connection, sample_size=0, input_limit=256, api=ToneLoss())
        self.assertFalse(report["all_public_routes_lossless"])
        self.assertEqual(report["counts"]["pairs_with_public_mapping_failure"], 1)

    def test_all_pairs_count_fallbacks_collisions_and_limits_without_false_formal_pass(self):
        database = self.root / "coverage.sqlite3"
        create_database(database, [("火炬", "fo2 geoi6"), ("炬", "geoi6"), ("鼻音", "hm6"),
                                   ("長串", "fo2 fo2 fo2 fo2"), ("長啊", "aa1"), ("短啊", "a1")])
        with closing(sqlite3.connect(database)) as connection:
            report = audit_dictionary(connection, sample_size=5, input_limit=7, api=FakeApi())
        self.assertEqual(report["counts"]["dictionary_pairs"], 6)
        self.assertEqual(report["counts"]["pairs_with_lossless_input_route"], 6)
        self.assertEqual(report["pairs_by_spelling_route"]["jyutping_fallback"], 1)
        self.assertEqual(report["pairs_by_spelling_route"]["extension"], 1)
        self.assertFalse(report["all_pairs_have_table_backed_yale"])
        self.assertTrue(report["all_public_routes_lossless"])
        self.assertEqual(report["input_lengths"]["compact_over_limit"], 1)
        self.assertEqual(report["same_yale_spelling_collisions"][0]["canonical_targets"], ["a", "aa"])
        self.assertEqual(report["same_yale_spelling_collisions"][0]["missing"], [])
        self.assertEqual(report["sample_selection"]["selected"], 5)

    def test_sample_selection_is_repeatable_and_includes_long_words_only_when_limit_allows(self):
        database = self.root / "selection.sqlite3"
        create_database(database, [(f"詞{i}", "fo2 geoi6" if i % 2 else "fo2") for i in range(30)])
        with closing(sqlite3.connect(database)) as connection:
            first = audit_dictionary(connection, sample_size=7, input_limit=256, api=FakeApi())
            second = audit_dictionary(connection, sample_size=7, input_limit=256, api=FakeApi())
        self.assertEqual(first["sample_selection"], second["sample_selection"])
        self.assertEqual(len({row["id"] for row in first["sample_selection"]["cases"]}), 7)

    def test_real_dictionary_is_opened_read_only_by_test_caller(self):
        database = self.root / "readonly.sqlite3"
        create_database(database, [("火炬", "fo2 geoi6")])
        before = database.read_bytes()
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            report = audit_dictionary(connection, sample_size=1, input_limit=256, api=FakeApi())
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM entries")
        self.assertTrue(report["all_public_routes_lossless"])
        self.assertEqual(database.read_bytes(), before)

    def test_probe_reads_later_pages_without_confusing_rank_with_mapping(self):
        class Pages:
            MAX_INPUT_LENGTH = 256
            MAX_OFFSET = 10000
            def lookup_page(self, raw, *, offset, page_size, mode):
                if offset == 0:
                    return CandidatePage(tuple(Candidate(str(i), "fo2", 1.0, "exact", len(raw)) for i in range(90)), 0, 90)
                return CandidatePage((Candidate("目標", "geoi6", 0.0, "fuzzy", len(raw)),), 90, None)
        outcome = probe_lookup(Pages(), "geui", "目標")
        self.assertEqual(outcome["rank"], 91)
        self.assertFalse(outcome["within_top90"])
        self.assertEqual(outcome["pages"], 2)

    def test_capacity_and_input_limit_are_explicit_not_false_exhaustion(self):
        class Limited:
            MAX_INPUT_LENGTH = 4
            MAX_OFFSET = 10000
            def lookup_page(self, *args, **kwargs):
                raise PaginationCapacityError("bounded completion tail")
        self.assertEqual(probe_lookup(Limited(), "geui", "炬")["status"], "capacity_limited")
        self.assertEqual(probe_lookup(Limited(), "fogeui", "火炬")["status"], "input_limit_excluded")

    def test_empty_dictionary_and_empty_reference_never_pass_vacuously(self):
        database = self.root / "empty.sqlite3"
        create_database(database, [])
        with closing(sqlite3.connect(database)) as connection:
            report = audit_dictionary(connection, sample_size=0, input_limit=256, api=FakeApi())
        self.assertFalse(report["all_public_routes_lossless"])
        self.assertFalse(report["all_pairs_have_table_backed_yale"])
        self.assertFalse(audit_reference({name: [] for name in ("final_grid", "onset_grid", "compound_grid", "extension_grid", "fallback_grid")})["passed"])

    def test_output_cannot_overwrite_dictionary_or_mapping_artifacts(self):
        project = FIXTURE.parents[1]
        self.assertEqual(report_output(project / "docs/yale-coverage.json", self.root / "db.sqlite3", FIXTURE),
                         project / "docs/yale-coverage.json")
        for output in (project / "data/generated/lexicon.manifest.json", FIXTURE, self.root / "outside.json"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                report_output(output, self.root / "db.sqlite3", FIXTURE)

    def test_real_api_reference_grid(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        report = audit_reference(fixture)
        failures = [row for row in report["results"] if not row["passed"]]
        self.assertEqual(failures, [])

    def test_real_engine_word_probe_has_no_learning_side_effect(self):
        database = self.root / "engine.sqlite3"
        create_database(database, [("火炬", "fo2 geoi6"), ("香港", "hoeng1 gong2"), ("中國", "zung1 gwok3"),
                                   ("出", "ceot1"), ("雨", "jyu5"), ("月", "jyut6"), ("全部", "cyun4 bou6")])
        before = database.read_bytes()
        with Engine(database, learning_path=None) as engine:
            for raw, expected in (("fogeui", "火炬"), ("heunggong", "香港"), ("junggwok", "中國"),
                                  ("cheut", "出"), ("yu", "雨"), ("yut", "月"), ("chyunbou", "全部")):
                with self.subTest(raw=raw):
                    self.assertEqual(probe_lookup(engine, raw, expected)["status"], "found")
            self.assertIsNone(engine.learning_path)
            report = exercise_lookups(engine, [], [], max_pages=1)
            self.assertEqual(report["configuration"], {
                "mode": "forgiving", "prefer_yale": True, "learning_enabled": False})
        with Engine(database, learning_path=None, prefer_yale=False) as mixed:
            report = exercise_lookups(mixed, [], [], max_pages=1)
            self.assertFalse(report["configuration"]["prefer_yale"])
        self.assertEqual(database.read_bytes(), before)
        self.assertFalse((self.root / "learning.json").exists())


if __name__ == "__main__":
    unittest.main()
