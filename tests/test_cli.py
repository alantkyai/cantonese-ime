"""CLI contracts tested with an isolated project-authored dictionary."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from cantonese_ime.__main__ import main


class CliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cantonese-cli-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.dictionary = self.directory / "dictionary.sqlite3"
        fixture = Path(__file__).parent / "fixtures" / "mini_dictionary.json"
        entries = json.loads(fixture.read_text(encoding="utf-8"))
        connection = sqlite3.connect(self.dictionary)
        try:
            connection.execute("CREATE TABLE entries (text TEXT, reading TEXT, base_reading TEXT, weight REAL)")
            connection.executemany(
                "INSERT INTO entries VALUES (?, ?, ?, ?)",
                [(entry["text"], entry["reading"], " ".join(syllable[:-1] for syllable in entry["reading"].split()), entry["weight"]) for entry in entries],
            )
            connection.commit()
        finally:
            connection.close()

    def run_cli(self, *arguments, dictionary=True):
        output, errors = io.StringIO(), io.StringIO()
        options = list(arguments)
        if dictionary:
            options += ["--dictionary", str(self.dictionary)]
        with redirect_stdout(output), redirect_stderr(errors):
            try:
                code = main(options)
            except SystemExit as error:
                code = error.code
        return code, output.getvalue(), errors.getvalue()

    def write_cases(self, cases):
        path = self.directory / "cases.json"
        path.write_text(json.dumps({"cases": cases}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_lookup_json_preserves_unicode_and_candidate_contract(self):
        code, output, errors = self.run_cli("lookup", "neihou", "--mode", "jyutping", "--limit", "1", "--json")
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("你好", output)
        report = json.loads(output)
        self.assertEqual(len(report["candidates"]), 1)
        candidate = report["candidates"][0]
        self.assertEqual((candidate["text"], candidate["reading"], candidate["consumed_input"]), ("你好", "nei5 hou2", 6))
        self.assertIn("score", candidate)
        self.assertFalse(report["learning_enabled"])
        self.assertGreaterEqual(report["startup_ms"], 0)

    def test_lookup_text_and_mode_override(self):
        code, output, errors = self.run_cli("lookup", "lay")
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("你\tnei5\tfuzzy", output)
        code, output, errors = self.run_cli("lookup", "lay", "--mode", "jyutping", "--json")
        self.assertEqual(code, 0)
        self.assertNotIn("你", [candidate["text"] for candidate in json.loads(output)["candidates"]])

    def test_lookup_can_page_beyond_90_stored_homophones(self):
        connection = sqlite3.connect(self.dictionary)
        try:
            connection.executemany("INSERT INTO entries VALUES (?, 'lei4', 'lei', ?)",
                                   [(f"homophone{index:03}", 1000-index) for index in range(125)])
            connection.commit()
        finally:
            connection.close()
        code, output, errors = self.run_cli("lookup", "lei4", "--mode", "jyutping", "--offset", "108", "--limit", "9", "--json")
        self.assertEqual((code, errors), (0, ""))
        report = json.loads(output)
        self.assertEqual((report["offset"], report["next_offset"]), (108, 117))
        self.assertEqual([candidate["text"] for candidate in report["candidates"]], [f"homophone{index:03}" for index in range(108, 117)])

    def test_missing_database_explains_build_step(self):
        code, output, errors = self.run_cli("lookup", "nei", "--dictionary", str(self.directory / "missing.sqlite3"), dictionary=False)
        self.assertEqual((code, output), (2, ""))
        self.assertIn("tools/build_dictionary.py", errors)
        self.assertNotIn("Traceback", errors)

    def test_invalid_cli_options_fail_before_engine_lookup(self):
        for arguments in (("lookup", "nei", "--limit", "0"), ("lookup", "nei", "--limit", "91"), ("lookup", "nei", "--offset", "-1"), ("lookup", "nei", "--offset", "10001"), ("lookup", "nei", "--mode", "unknown"), ("evaluate", "--repeat", "0"), ("evaluate", "--repeat", "21")):
            with self.subTest(arguments=arguments):
                code, output, errors = self.run_cli(*arguments)
                self.assertEqual((code, output), (2, ""))
                self.assertIn("error:", errors)

    def test_type_replays_characters_and_named_keys_with_trace(self):
        code, output, errors = self.run_cli("type", "neihou", "--keys", "Space", "--trace", "--json")
        self.assertEqual((code, errors), (0, ""))
        report = json.loads(output)
        self.assertEqual((report["committed"], report["preedit"], report["candidates"]), ("你好", "", []))
        self.assertEqual([event["key"] for event in report["trace"]], [*"neihou", "Space"])
        self.assertEqual(report["trace"][-1]["committed"], "你好")

    def test_type_retains_preedit_and_reports_unhandled_keys(self):
        code, output, errors = self.run_cli("type", "nei", "--keys", "Ctrl+A", "--json")
        report = json.loads(output)
        self.assertEqual((code, errors, report["preedit"]), (0, "", "nei"))
        self.assertEqual(report["unhandled_keys"], ["Ctrl+A"])
        self.assertNotIn("trace", report)

    def test_enter_and_escape_do_not_write_opt_in_learning(self):
        learning = self.directory / "learning.json"
        for key, committed in (("Enter", "Nei"), ("Escape", "")):
            with self.subTest(key=key):
                code, output, errors = self.run_cli("type", "Nei", "--keys", key, "--learning", str(learning), "--json")
                self.assertEqual((code, errors), (0, ""))
                self.assertEqual(json.loads(output)["committed"], committed)
                self.assertFalse(learning.exists())

    def test_type_learning_is_explicit_and_changes_only_requested_memory(self):
        before = set(self.directory.iterdir())
        code, output, errors = self.run_cli("type", "nei", "--keys", "Down", "Space", "--json")
        self.assertEqual((code, errors, json.loads(output)["committed"]), (0, "", "妳"))
        self.assertEqual(set(self.directory.iterdir()), before)
        learning = self.directory / "learning.json"
        code, output, errors = self.run_cli("type", "nei", "--keys", "Down", "Space", "--learning", str(learning), "--json")
        self.assertEqual((code, errors), (0, ""))
        self.assertTrue(learning.is_file())
        code, output, errors = self.run_cli("lookup", "nei", "--learning", str(learning), "--json")
        self.assertEqual(json.loads(output)["candidates"][0]["text"], "妳")
        code, output, errors = self.run_cli("lookup", "nei", "--json")
        self.assertEqual(json.loads(output)["candidates"][0]["text"], "你")

    def test_evaluate_reports_ranks_coverage_categories_and_repeated_latency(self):
        cases = self.write_cases([
            {"id": "first", "input": "nei", "mode": "jyutping", "expected": ["你"], "top_k": 1, "category": "character"},
            {"id": "second", "input": "nei", "mode": "jyutping", "expected": ["missing", "妳"], "top_k": 2, "category": "character"},
            {"id": "phrase", "input": "neihou", "mode": "jyutping", "expected": ["你好"], "top_k": 9, "category": "phrase"},
        ])
        destination = self.directory / "reports" / "coverage.json"
        code, output, errors = self.run_cli("evaluate", "--cases", str(cases), "--repeat", "3", "--output", str(destination), "--json")
        self.assertEqual((code, errors), (0, ""))
        report = json.loads(output)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), report)
        self.assertEqual(report["report_schema_version"], 1)
        self.assertEqual(report["engine_version"], "1.0.0")
        self.assertRegex(report["dictionary_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(report["dictionary_sha256"], hashlib.sha256(self.dictionary.read_bytes()).hexdigest())
        self.assertRegex(report["corpus_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(report["corpus_sha256"], hashlib.sha256(cases.read_bytes()).hexdigest())
        self.assertEqual(report["python_version"], sys.version.split()[0])
        self.assertEqual(report["sqlite_version"], sqlite3.sqlite_version)
        self.assertTrue(report["captured_at_utc"].endswith("+00:00"))
        self.assertEqual(report["evaluation_kind"], "seed_case_coverage")
        self.assertIn("not held-out accuracy", report["notice"])
        self.assertEqual(report["aggregate"]["cases"], 3)
        self.assertEqual((report["aggregate"]["top1_hits"], report["aggregate"]["top_k_hits"]), (2, 3))
        self.assertEqual(report["cases"][1]["rank"], 2)
        self.assertEqual(report["categories"]["character"]["top1_rate"], 0.5)
        self.assertEqual(report["latency_ms"]["samples"], 9)
        self.assertEqual(report["cases"][0]["latency_ms"]["samples"], 3)
        self.assertGreaterEqual(report["latency_ms"]["p95"], report["latency_ms"]["median"])
        self.assertTrue(report["all_passed"])

    def test_unmet_evaluation_target_returns_failure_for_ci(self):
        cases = self.write_cases([
            {"id": "too-low", "input": "nei", "expected": ["妳"], "top_k": 1},
            {"id": "missing", "input": "zzzz", "expected": ["不存在"], "top_k": 9},
        ])
        code, output, errors = self.run_cli("evaluate", "--cases", str(cases), "--json")
        self.assertEqual((code, errors), (1, ""))
        report = json.loads(output)
        self.assertFalse(report["all_passed"])
        self.assertEqual(report["cases"][0]["rank"], 2)
        self.assertIsNone(report["cases"][1]["rank"])
        self.assertEqual(report["aggregate"]["top_k_hits"], 0)

    def test_empty_or_invalid_corpus_cannot_produce_false_pass(self):
        path = self.directory / "invalid.json"
        for document in ({"cases": []}, {"cases": [{"id": "empty", "input": "nei", "expected": []}]}, {"cases": [{"id": "bad-k", "input": "nei", "expected": ["你"], "top_k": True}]}):
            with self.subTest(document=document):
                path.write_text(json.dumps(document), encoding="utf-8")
                code, output, errors = self.run_cli("evaluate", "--cases", str(path), "--json")
                self.assertEqual((code, output), (2, ""))
                self.assertIn("error:", errors)

    def test_evaluation_output_cannot_overwrite_inputs(self):
        cases = self.write_cases([{"id": "first", "input": "nei", "expected": ["你"]}])
        before = self.dictionary.read_bytes()
        code, output, errors = self.run_cli("evaluate", "--cases", str(cases), "--output", str(self.dictionary), "--json")
        self.assertEqual((code, output), (2, ""))
        self.assertIn("must differ", errors)
        self.assertEqual(self.dictionary.read_bytes(), before)

    def test_module_entry_point_runs_from_repository(self):
        process = subprocess.run(
            [sys.executable, "-m", "cantonese_ime", "lookup", "neihou", "--dictionary", str(self.dictionary), "--json"],
            cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual((process.returncode, process.stderr), (0, ""))
        self.assertEqual(json.loads(process.stdout)["candidates"][0]["text"], "你好")


if __name__ == "__main__":
    unittest.main()
