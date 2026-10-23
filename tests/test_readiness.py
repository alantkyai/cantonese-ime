"""Readiness evidence must remain independent of development seed success."""

from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

from tools.audit_dictionary import IMPLEMENTATION_MODULES, TYPEDUCK_DECLARATION, _evaluation_audit, audit_dictionary, main, sha256


class DictionaryReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cantonese-readiness-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.vendor = self.directory / "vendor"
        self.vendor.mkdir()
        self.dictionary_source = self.vendor / "jyut6ping3.words.dict.yaml"
        self.dictionary_source.write_text("---\nname: fixture\n...\n你好\tnei5 hou2\t10\n你好嗎\n", encoding="utf-8")
        (self.vendor / "LICENSE").write_text("Fixture license retained for provenance testing.\n", encoding="utf-8")
        (self.vendor / "README.md").write_text("Project-authored test data; no real licensing assertion.\n", encoding="utf-8")
        (self.vendor / "list.tsv").write_text("CH\tJP\n你\tnei5\n", encoding="utf-8")
        self.lock = self.write_lock("sources.lock.json", [self.dictionary_source.name, "LICENSE", "README.md"])
        self.mapping_lock = self.write_lock("mapping.lock.json", ["list.tsv", "LICENSE", "README.md"])
        self.notices = self.directory / "NOTICES.md"
        self.notices.write_text("Project-authored fixture notice.\n", encoding="utf-8")
        self.inventory = self.directory / "syllables.json"
        self.inventory.write_text(json.dumps({"syllables": [{"base": "nei", "lshk_tones": [5]}, {"base": "hou", "lshk_tones": [2]}, {"base": "maa", "lshk_tones": [3]}]}), encoding="utf-8")
        self.spellings = self.directory / "spellings.json"
        self.spellings.write_text(json.dumps({"aliases": [{"spelling": "lay", "canonical": "nei", "penalty": 1.0}]}), encoding="utf-8")
        self.database = self.directory / "lexicon.sqlite3"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript("""
                CREATE TABLE entries(text TEXT, reading TEXT, base_reading TEXT, compact TEXT,
                                     syllable_count INTEGER, weight REAL, source TEXT, origin TEXT,
                                     UNIQUE(text,reading));
                CREATE INDEX entries_text ON entries(text);
                CREATE TABLE syllables(base TEXT PRIMARY KEY);
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
                INSERT INTO entries VALUES('你好','nei5 hou2','nei hou','neihou',2,10,'jyut6ping3.words.dict.yaml','explicit');
                INSERT INTO entries VALUES('你','nei5','nei','nei',1,5,'list.tsv','supplement');
                INSERT INTO syllables VALUES('nei'),('hou');
            """)
        self.manifest = self.database.with_suffix(".manifest.json")
        self.refresh_manifest()

    def write_lock(self, name, filenames):
        path = self.directory / name
        path.write_text(json.dumps({
            "repository": "https://example.invalid/fixture", "commit": "a" * 40,
            "license": "fixture-only", "attribution": "Project test author",
            "local_directory": str(self.vendor),
            "files": [{"name": filename, "size_bytes": (self.vendor / filename).stat().st_size, "sha256": sha256(self.vendor / filename)} for filename in filenames],
        }), encoding="utf-8")
        return path

    def refresh_manifest(self):
        with closing(sqlite3.connect(self.database)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        self.manifest.write_text(json.dumps({"database_sha256": sha256(self.database), "entry_count": count}), encoding="utf-8")

    def add_ledger(self, status="generated_unique", codes=None, generated=True, reason="complete"):
        codes = ["nei5 hou2 maa3"] if codes is None else codes
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE phrase_encodings(text TEXT PRIMARY KEY,status TEXT,codes_json TEXT,path_count INTEGER,work_count INTEGER,reason TEXT)")
            connection.execute("INSERT INTO phrase_encodings VALUES(?,?,?,?,?,?)", ("你好嗎", status, json.dumps(codes), len(codes), 3, reason))
            if generated:
                connection.execute("INSERT INTO entries VALUES('你好嗎','nei5 hou2 maa3','nei hou maa','neihoumaa',3,1,'jyut6ping3.phrase.dict.yaml','generated')")
                connection.execute("INSERT INTO syllables VALUES('maa')")
            connection.commit()
        self.refresh_manifest()

    def audit(self, **kwargs):
        return audit_dictionary(self.database, self.lock, mapping_lock_path=self.mapping_lock, inventory_path=self.inventory, spellings_path=self.spellings, notices_path=self.notices, manifest_path=self.manifest, **kwargs)

    @staticmethod
    def gate(report, identifier):
        return next(item for item in report["requirements"] if item["id"] == identifier)

    def test_unaccounted_text_only_rows_prevent_source_coverage_pass(self):
        report = self.audit()
        self.assertEqual(report["database"]["counts"]["entries"], 2)
        self.assertEqual(report["rime_source_rows"]["counts"]["text_only_without_encoding_ledger"], 1)
        self.assertEqual(self.gate(report, "selected_source_accounting")["status"], "incomplete")
        self.assertFalse(report["fully_ready"])

    def test_selected_missing_wordnet_lock_prevents_source_and_accounting_pass(self):
        self.add_ledger()
        report = self.audit(wordnet_lock_path=self.directory / "missing-wordnet.lock.json")
        self.assertEqual(self.gate(report, "source_provenance")["status"], "incomplete")
        self.assertEqual(self.gate(report, "supplement_accounting")["status"], "incomplete")

    def test_wordnet_unknown_frequency_must_remain_zero(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE entries SET source='wordnet:cantown' WHERE text='你'")
            connection.commit()
        report = self.audit()
        frequency = self.gate(report, "supplement_frequency_integrity")
        self.assertEqual(frequency["status"], "incomplete")
        self.assertEqual(frequency["evidence"]["nonzero_rows_by_source"]["wordnet:cantown"], 1)

    def test_wordnet_source_file_count_cannot_override_failed_child_accounting(self):
        self.add_ledger()
        wordnet_lock = self.directory / "wordnet.lock.json"
        wordnet_lock.write_text("{}", encoding="utf-8")
        import tools.audit_dictionary as auditor
        original = auditor._lock_audit

        def locked(path, **options):
            return {"verified": True} if path == wordnet_lock else original(path, **options)

        stub = types.ModuleType("tools.audit_wordnet_source")
        for flag in (False, None, "true"):
            stub.audit_wordnet = lambda *args, **kwargs: {"mechanical_complete": flag, "counts": {"source_files_audited": 1}}
            with self.subTest(flag=flag), patch("tools.audit_dictionary._lock_audit", side_effect=locked), patch.dict("sys.modules", {"tools.audit_wordnet_source": stub}):
                report = self.audit(wordnet_lock_path=wordnet_lock)
            self.assertEqual(self.gate(report, "supplement_accounting")["status"], "incomplete")

    def test_complete_ledger_passes_accounting_but_not_linguistic_readiness(self):
        self.add_ledger()
        before = sha256(self.database)
        report = self.audit()
        self.assertEqual(self.gate(report, "source_provenance")["status"], "pass")
        self.assertEqual(self.gate(report, "selected_source_accounting")["status"], "pass")
        self.assertEqual(self.gate(report, "database_integrity")["status"], "pass")
        self.assertEqual(self.gate(report, "pronunciation_review")["status"], "incomplete")
        self.assertEqual(self.gate(report, "held_out_quality")["status"], "incomplete")
        self.assertEqual(self.gate(report, "evaluation_evidence_current")["status"], "incomplete")
        self.assertFalse(report["fully_ready"])
        self.assertEqual(sha256(self.database), before)
        self.assertTrue(report["database"]["stable_during_audit"])

    def test_quarantine_is_accounted_without_importing_a_guess(self):
        self.add_ledger(status="unencodable", codes=[], generated=False, reason="No reading evidence")
        report = self.audit()
        self.assertEqual(report["rime_source_rows"]["counts"]["quarantined_source_rows"], 1)
        self.assertEqual(self.gate(report, "selected_source_accounting")["status"], "pass")
        self.assertFalse(report["fully_ready"])

    def test_quarantined_generated_entries_are_a_mechanical_failure(self):
        self.add_ledger(status="truncated", codes=[], generated=True, reason="Work bound reached")
        report = self.audit()
        self.assertEqual(report["rime_source_rows"]["counts"]["quarantined_generated_entries"], 1)
        self.assertEqual(self.gate(report, "selected_source_accounting")["status"], "incomplete")

    def test_invalid_generated_readings_do_not_pass_ledger_validation(self):
        self.add_ledger(codes=["nei9 hou2"])
        report = self.audit()
        self.assertEqual(report["rime_source_rows"]["counts"]["invalid_encoding_ledger"], 1)
        self.assertEqual(self.gate(report, "selected_source_accounting")["status"], "incomplete")

    def test_source_hash_and_current_manifest_are_checked_independently(self):
        self.dictionary_source.write_text(self.dictionary_source.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        self.manifest.write_text(json.dumps({"database_sha256": "0" * 64, "entry_count": 2}), encoding="utf-8")
        report = self.audit()
        self.assertEqual(self.gate(report, "source_provenance")["status"], "incomplete")
        self.assertEqual(self.gate(report, "manifest_current")["status"], "incomplete")

    def test_seed_success_is_never_held_out_accuracy(self):
        evaluation = self.directory / "seed-evaluation.json"
        evaluation.write_text(json.dumps({"evaluation_kind": "seed_case_coverage", "dictionary_sha256": sha256(self.database), "aggregate": {"cases": 40, "top_k_hits": 40}, "notice": "Not held-out accuracy"}), encoding="utf-8")
        report = self.audit(evaluation_path=evaluation)
        self.assertTrue(report["evaluation"]["matches_dictionary"])
        self.assertEqual(self.gate(report, "held_out_quality")["status"], "incomplete")
        self.assertFalse(report["fully_ready"])

    def test_artifact_equality_does_not_certify_a_clean_build_or_full_readiness(self):
        comparison = self.directory / "comparison.sqlite3"
        shutil.copyfile(self.database, comparison)
        report = self.audit(compare_database=comparison)
        self.assertEqual(self.gate(report, "deterministic_artifact_comparison")["status"], "pass")
        self.assertIn("invocation", report["comparison"]["notice"])
        self.assertFalse(report["fully_ready"])
        with self.assertRaises(ValueError):
            self.audit(compare_database=self.database)

    def test_inventory_absence_is_reported_without_labeling_forms_invalid(self):
        self.inventory.write_text(json.dumps({"syllables": [{"base": "nei", "lshk_tones": [5]}]}), encoding="utf-8")
        report = self.audit()
        self.assertEqual(report["mapping_inventory"]["dictionary_bases_not_in_inventory"], ["hou"])
        self.assertIn("rather than automatic rejection", report["mapping_inventory"]["notice"])

    def test_alias_collisions_remain_visible_and_duplicate_pairs_are_rejected(self):
        aliases = [{"spelling": "lay", "canonical": "nei", "penalty": 1}, {"spelling": "lay", "canonical": "hou", "penalty": 2}]
        self.spellings.write_text(json.dumps({"aliases": aliases}), encoding="utf-8")
        report = self.audit()
        self.assertEqual(report["spelling_map"]["collision_spellings"], 1)
        self.assertEqual(self.gate(report, "spelling_map_integrity")["status"], "pass")
        self.spellings.write_text(json.dumps({"aliases": aliases + aliases[:1]}), encoding="utf-8")
        self.assertEqual(self.gate(self.audit(), "spelling_map_integrity")["status"], "incomplete")

    def test_lshk_description_and_explicit_multisyllable_rows_are_accounted(self):
        (self.vendor / "list.tsv").write_text("CH\tJP\n你\tnei5\n嗎\t\n吖\taa1 aa1\n", encoding="utf-8")
        self.mapping_lock = self.write_lock("mapping.lock.json", ["list.tsv", "LICENSE", "README.md"])
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE supplement_review(source TEXT,text TEXT,status TEXT,details_json TEXT)")
            connection.execute("INSERT INTO supplement_review VALUES(?,?,?,?)", ("lshk:list.tsv", "嗎", "description_only", json.dumps({"line": 3, "reason": "JP is blank"})))
            connection.execute("INSERT INTO entries VALUES('吖','aa1 aa1','aa aa','aaaa',2,0,'lshk:list.tsv','supplement')")
            connection.execute("INSERT INTO syllables VALUES('aa')")
            connection.commit()
        self.refresh_manifest()
        report = self.audit()
        self.assertEqual(report["supplement_rows"]["counts"]["description_only_rows"], 1)
        self.assertEqual(report["supplement_rows"]["counts"]["multisyllable_rows"], 1)
        self.assertEqual(self.gate(report, "supplement_accounting")["status"], "pass")

    def test_website_snapshot_license_and_variant_records_are_verified(self):
        words = self.vendor / "wordslist.json"
        words.write_text(json.dumps({"你好": ["nei5 hou2", "!nei5 hou2"], "你好*": ["nei5 hou2"]}), encoding="utf-8")
        declaration = self.vendor / "license-declaration.html"
        statement = "Project-authored fixture declaration only."
        declaration.write_text("<p>" + statement + "</p>", encoding="utf-8")
        web_lock = self.directory / "web.lock.json"
        web_lock.write_text(json.dumps({
            "data_url": "https://example.invalid/words", "snapshot_id": "fixture",
            "snapshot_retrieved_at": "2026-10-22T00:00:00+00:00", "license": "fixture-only",
            "attribution": "Project test author", "license_declaration": statement,
            "local_directory": str(self.vendor),
            "files": [{"name": path.name, "size_bytes": path.stat().st_size, "sha256": sha256(path)} for path in (words, declaration)],
        }), encoding="utf-8")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE supplement_review(source TEXT,text TEXT,status TEXT,details_json TEXT)")
            connection.execute("INSERT INTO supplement_review VALUES(?,?,?,?)", ("words.hk:wordlist", "你好", "quarantined", json.dumps({"reading_index": 1, "raw_reading": "!nei5 hou2", "reason": "non-Jyutping"})))
            connection.execute("INSERT INTO supplement_review VALUES(?,?,?,?)", ("words.hk:wordlist", "你好", "normalized_variant", json.dumps({"reading_index": 0, "raw_reading": "nei5 hou2", "raw_text": "你好*"})))
            connection.commit()
        self.refresh_manifest()
        report = self.audit(wordshk_lock_path=web_lock)
        self.assertTrue(report["source_locks"][-1]["verified"])
        self.assertTrue(report["source_locks"][-1]["website_license_declaration_matches"])
        self.assertEqual(report["source_locks"][-1]["pin_type"], "retrieved_content_hash_snapshot")
        self.assertEqual(report["wordshk_rows"]["counts"]["normalized_variant_rows"], 1)
        self.assertEqual(report["wordshk_rows"]["counts"]["quarantined_source_rows"], 1)
        self.assertEqual(self.gate(report, "supplement_accounting")["status"], "pass")
        lock = json.loads(web_lock.read_text(encoding="utf-8"))
        lock["license_declaration"] = "Missing declaration text"
        web_lock.write_text(json.dumps(lock), encoding="utf-8")
        self.assertEqual(self.gate(self.audit(wordshk_lock_path=web_lock), "source_provenance")["status"], "incomplete")

    def test_cli_readiness_exit_and_default_manifest_overwrite_protection(self):
        arguments = ["--database", str(self.database), "--lock", str(self.lock), "--mapping-lock", str(self.mapping_lock), "--wordshk-lock", str(self.directory / "not-selected.lock.json"), "--inventory", str(self.inventory), "--spellings", str(self.spellings), "--notices", str(self.notices)]
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(arguments + ["--require-ready"])
        self.assertEqual((code, errors.getvalue()), (1, ""))
        self.assertFalse(json.loads(output.getvalue())["fully_ready"])
        before = self.manifest.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = main(arguments + ["--output", str(self.manifest)])
        self.assertEqual(code, 2)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_source_inclusion_does_not_claim_over_cap_readings_are_typable(self):
        reading = " ".join(["nei5"] * 23)
        base = " ".join(["nei"] * 23)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?)", ("長" * 23, reading, base, base.replace(" ", ""), 23, 0, self.dictionary_source.name, "explicit"))
            connection.commit()
        self.refresh_manifest()
        report = self.audit()
        coverage = report["database"]["input_length_coverage"]
        self.assertEqual(coverage["max_tone_free_letters"], 69)
        self.assertEqual(coverage["max_fully_toned_letters_and_digits"], 92)
        self.assertEqual(coverage["entries_tone_free_over_64"], 1)
        self.assertEqual(coverage["entries_fully_toned_over_64"], 1)
        self.assertIn("not direct full-reading retrievability", coverage["notice"])
        self.assertEqual(report["entry_provenance"]["explicit"]["unverified_entries"], 1)
        self.assertEqual(self.gate(report, "source_provenance")["status"], "incomplete")

    def test_supplement_reading_frequency_cannot_be_invented_from_text_count(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE entries SET source='words.hk:wordlist' WHERE origin='supplement'")
            connection.commit()
        self.refresh_manifest()
        report = self.audit()
        evidence = report["database"]["supplement_frequency_integrity"]
        self.assertEqual(evidence["counts"]["selected_source_nonzero_rows"], 1)
        self.assertEqual(self.gate(report, "supplement_frequency_integrity")["status"], "incomplete")
        self.assertEqual(evidence["nonzero_samples"][0]["weight"], 5)

    def test_new_selected_sources_also_require_unknown_frequency_zero(self):
        for source in ("typeduck:principal", "unihan:kCantonese"):
            with self.subTest(source=source):
                with closing(sqlite3.connect(self.database)) as connection:
                    connection.execute("UPDATE entries SET source=? WHERE origin='supplement'", (source,))
                    connection.commit()
                self.refresh_manifest()
                report = self.audit()
                self.assertEqual(self.gate(report, "supplement_frequency_integrity")["status"], "incomplete")
                self.assertEqual(report["database"]["supplement_frequency_integrity"]["nonzero_samples"][0]["source"], source)

    def test_typeduck_rows_and_exact_raw_quarantine_are_independently_accounted(self):
        principal = self.vendor / "jyut6ping3.dict.yaml"
        raw_marker = "🦆\t~daa2~dak1\t100.0%"
        principal.write_text("---\nname: jyut6ping3\n...\n你好\tNEI5  HOU2\t150%\n" + raw_marker + "\n", encoding="utf-8")
        (self.vendor / "README.md").write_text(TYPEDUCK_DECLARATION, encoding="utf-8")
        # The same retained README is also part of the fixture's Rime/LSHK locks.
        self.lock = self.write_lock("sources.lock.json", [self.dictionary_source.name, "LICENSE", "README.md"])
        self.mapping_lock = self.write_lock("mapping.lock.json", ["list.tsv", "LICENSE", "README.md"])
        lock = self.write_lock("typeduck.lock.json", [principal.name, "LICENSE", "README.md"])
        document = json.loads(lock.read_text(encoding="utf-8"))
        document["source_id"] = "typeduck:principal"
        lock.write_text(json.dumps(document), encoding="utf-8")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE supplement_review(source TEXT,text TEXT,status TEXT,details_json TEXT)")
            details = {"line": 5, "raw_text": "🦆", "raw_reading": "~daa2~dak1", "raw_weight": "100.0%", "raw_line": raw_marker, "reason": "phonetic_annotation"}
            connection.execute("INSERT INTO supplement_review VALUES(?,?,?,?)", ("typeduck:principal", "🦆", "quarantined", json.dumps(details)))
            connection.commit()
        self.refresh_manifest()
        report = self.audit(typeduck_lock_path=lock)
        counts = report["typeduck_rows"]["counts"]
        self.assertEqual((counts["input_rows"], counts["accepted_source_rows"], counts["quarantined_source_rows"]), (2, 1, 1))
        self.assertEqual(counts["normalized_reading_rows"], 1)
        self.assertEqual(self.gate(report, "supplement_accounting")["status"], "pass")
        self.assertTrue(report["source_locks"][-1]["principal_license_declaration_matches"])
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DELETE FROM supplement_review")
            connection.commit()
        self.refresh_manifest()
        self.assertEqual(self.gate(self.audit(typeduck_lock_path=lock), "supplement_accounting")["status"], "incomplete")
        (self.vendor / "README.md").write_text("The scope declaration is absent.", encoding="utf-8")
        document["files"][-1] = {"name": "README.md", "size_bytes": (self.vendor / "README.md").stat().st_size, "sha256": sha256(self.vendor / "README.md")}
        lock.write_text(json.dumps(document), encoding="utf-8")
        self.assertFalse(self.audit(typeduck_lock_path=lock)["source_locks"][-1]["verified"])
        document.pop("source_id")
        lock.write_text(json.dumps(document), encoding="utf-8")
        self.assertFalse(self.audit(typeduck_lock_path=lock)["source_locks"][-1]["verified"])

    def write_unihan_lock(self):
        directory = self.directory / "unihan"
        directory.mkdir()
        readings = "# Unicode Version 18.0.0\nU+4F60\tkDefinition\tyou\nU+4F60\tkCantonese\tnei5 nei4\n"
        (directory / "Unihan_Readings.txt").write_text(readings, encoding="utf-8")
        with zipfile.ZipFile(directory / "Unihan.zip", "w") as archive:
            archive.writestr("Unihan_Readings.txt", (directory / "Unihan_Readings.txt").read_bytes())
        (directory / "ReadMe.txt").write_text("This directory contains final data files for version 18.0.0 of the Unicode Character Database.", encoding="utf-8")
        # Project-authored test notice exercises exact retention, not real rights.
        notice = "UNICODE LICENSE V3\nFixture-only full notice for retention testing.\n"
        (directory / "LICENSE.txt").write_text(notice, encoding="utf-8")
        lock = self.directory / "unihan.lock.json"
        lock.write_text(json.dumps({"source_id": "unihan:kCantonese", "unicode_version": "18.0.0", "archive_url": "https://www.unicode.org/Public/18.0.0/ucd/Unihan.zip", "license": "Unicode-3.0", "attribution": "Project fixture author", "property": "kCantonese", "property_status": "Provisional", "local_directory": str(directory), "license_notice": {"file": "LICENSE.txt", "sha256": sha256(directory / "LICENSE.txt"), "text": notice}, "files": [{"name": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size} for path in directory.iterdir()]}), encoding="utf-8")
        return lock, directory

    def test_unihan_alternatives_are_character_pairs_and_release_evidence_is_checked(self):
        lock, directory = self.write_unihan_lock()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("INSERT INTO entries VALUES('你','nei4','nei','nei',1,0,'unihan:kCantonese','supplement')")
            connection.commit()
        self.refresh_manifest()
        report = self.audit(unihan_lock_path=lock)
        counts = report["unihan_rows"]["counts"]
        self.assertEqual((counts["input_rows"], counts["accepted_source_pairs"], counts["ignored_other_property_rows"]), (1, 2, 1))
        self.assertEqual(counts["alternative_reading_rows"], 1)
        self.assertTrue(report["source_locks"][-1]["verified"])
        self.assertEqual(report["source_locks"][-1]["pin_type"], "versioned_unicode_distribution")
        self.assertEqual(report["entry_provenance"]["supplement"]["unverified_entries"], 0)
        self.assertEqual(self.gate(report, "supplement_accounting")["status"], "pass")
        with zipfile.ZipFile(directory / "Unihan.zip", "w") as archive:
            archive.writestr("Unihan_Readings.txt", "different locked archive data")
        document = json.loads(lock.read_text(encoding="utf-8"))
        document["files"] = [{"name": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size} for path in directory.iterdir()]
        lock.write_text(json.dumps(document), encoding="utf-8")
        report = self.audit(unihan_lock_path=lock)
        self.assertFalse(report["source_locks"][-1]["unicode_release_evidence"]["archive_extraction_matches"])
        self.assertEqual(self.gate(report, "source_provenance")["status"], "incomplete")

    def test_unihan_malformed_or_repeated_properties_cannot_pass_source_accounting(self):
        lock, directory = self.write_unihan_lock()
        source = directory / "Unihan_Readings.txt"
        source.write_text(source.read_text(encoding="utf-8") + "U+4F60\tkCantonese\tnei5\nU+D800\tkCantonese\tnei5\n", encoding="utf-8")
        document = json.loads(lock.read_text(encoding="utf-8"))
        document["files"] = [{"name": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size} for path in directory.iterdir()]
        lock.write_text(json.dumps(document), encoding="utf-8")
        report = self.audit(unihan_lock_path=lock)
        self.assertEqual(report["unihan_rows"]["counts"]["invalid_source_reading"], 2)
        self.assertEqual(self.gate(report, "supplement_accounting")["status"], "incomplete")

    def test_evaluation_requires_current_fixed_module_and_corpus_hashes(self):
        modules = self.directory / "implementation"
        modules.mkdir()
        for name in IMPLEMENTATION_MODULES:
            (modules / name).write_text("fixture module " + name, encoding="utf-8")
        corpus = self.directory / "eval-cases.json"
        corpus.write_text('{"cases":[]}', encoding="utf-8")
        path = self.directory / "evaluation.json"
        document = {"dictionary_sha256": sha256(self.database), "corpus_sha256": sha256(corpus), "implementation_sha256": {name: sha256(modules / name) for name in IMPLEMENTATION_MODULES}, "evaluation_kind": "seed_case_coverage"}
        path.write_text(json.dumps(document), encoding="utf-8")
        report = _evaluation_audit(path, sha256(self.database), corpus, modules)
        self.assertTrue(report["current_evidence"])
        self.assertIn("not who ran or approved", report["authenticity_notice"])
        (modules / "engine.py").write_text("changed implementation", encoding="utf-8")
        report = _evaluation_audit(path, sha256(self.database), corpus, modules)
        self.assertFalse(report["current_evidence"])
        self.assertFalse(report["implementation_matches_current_sources"])

    def test_malformed_report_hash_fields_never_become_filesystem_paths(self):
        modules = self.directory / "implementation"
        modules.mkdir()
        for name in IMPLEMENTATION_MODULES:
            (modules / name).write_text("fixture " + name, encoding="utf-8")
        corpus = self.directory / "eval-cases.json"
        corpus.write_text("{}", encoding="utf-8")
        correct = {name: sha256(modules / name) for name in IMPLEMENTATION_MODULES}
        path = self.directory / "evaluation.json"
        for field in (None, [], {}, {**correct, "../../outside.py": "0" * 64}, {**correct, "engine.py": ["invalid"]}, {**correct, "engine.py": "z" * 64}):
            with self.subTest(field=field):
                path.write_text(json.dumps({"dictionary_sha256": sha256(self.database), "corpus_sha256": sha256(corpus), "implementation_sha256": field}), encoding="utf-8")
                report = _evaluation_audit(path, sha256(self.database), corpus, modules)
                self.assertFalse(report["current_evidence"])
                self.assertFalse(report["implementation_field_valid"])

    def test_forged_human_review_claims_do_not_approve_readiness(self):
        from tools.build_review_pack import PACK_VERSION, TABLES, encode_tsv, immutable_digest, read_table, validate_pack

        output = self.directory / "review"
        output.mkdir()
        (output / "README.md").write_text("Project-authored review fixture.\n", encoding="utf-8")
        tables = {name: [{column: "fixture" for column in generated}] for name, (generated, reviewer) in TABLES.items()}
        manifest = {"pack_version": PACK_VERSION, "inputs": {"generator_source": {"sha256": "0" * 64, "size_bytes": 0}}, "readme_sha256": sha256(output / "README.md"), "human_approval_authenticated": True, "readiness_approved": True, "tables": {name: {"generated_sha256": immutable_digest(rows, TABLES[name][0])} for name, rows in tables.items()}}
        for name, rows in tables.items():
            (output / name).write_bytes(encode_tsv(rows, *TABLES[name]))
        (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        name = "phrases.tsv"
        generated, reviewer = TABLES[name]
        rows = read_table(output / name, generated, reviewer)
        rows[0].update(review_status="confirmed", reviewer="Unauthenticated fixture claim", reviewed_at="2026-10-22T00:00:00+00:00", evidence="Fabricated fixture evidence, not human approval")
        import csv
        with (output / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=generated + reviewer, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        result = validate_pack(output, tables, {}, for_regeneration=False)
        self.assertEqual(result["review_status_counts"]["confirmed"], 1)
        self.assertFalse(result["authenticated_human_approval"])
        self.assertFalse(result["readiness_approved"])
        with self.assertRaises(ValueError):
            validate_pack(output, tables, {}, for_regeneration=True)


if __name__ == "__main__":
    unittest.main()
