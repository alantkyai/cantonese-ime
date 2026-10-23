"""Isolated Wordnet source attestation; no production mapping regeneration."""
from contextlib import closing, ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime.dictionary import file_sha256
from cantonese_ime.mappings import SOURCES, build_mapping_artifacts
from tools import build_mappings as mapping_cli


PROJECT = Path(__file__).resolve().parents[1]
WORDNET_SOURCE = {
    "title": "Cantonese Wordnet explicit Cantonese Lemma/Form readings",
    "url": "https://github.com/lmorgadodacosta/CantoneseWN/tree/6434cbc1d692d3061266352aa223a8df4a9c883e",
    "license": "CC-BY-4.0",
    "scope": "Accepted own-Lemma/own-Form Cantonese readings, independently parsed before winner deduplication; source acceptance is not independent linguistic approval.",
}


def word(identity, text, readings):
    return (f'<LexicalEntry id="{identity}"><Lemma writtenForm="{text}"/>'
            + "".join(f'<Form writtenForm="{reading}"/>' for reading in readings) + '</LexicalEntry>')


class WordnetMappingCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="wordnet-mapping-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vendor = self.root / "vendor" / "wordnet"
        self.vendor.mkdir(parents=True)
        self.xml = self.vendor / "cantown.xml"
        self.xml.write_text('<LexicalResource><Lexicon id="cantown-yue" language="yue" version="1.0" '
            'license="https://creativecommons.org/licenses/by/4.0/">'
            + word("you", "你", ["nei5", "nei2", ""])
            + word("phrase", "你好", ["nei5 hou2", "nei5  hou2"])
            + word("talk", "話", ["waa6"])
            + word("unknown", "日", ["yat6"])
            + '</Lexicon><Lexicon id="cantown-en" language="en" version="1.0" '
            'license="https://creativecommons.org/licenses/by/4.0/">'
            + word("english", "you", [""]) + '</Lexicon></LexicalResource>', encoding="utf-8")
        inventory = {"schema_version": 1, "bases": ["nei", "hou", "waa"],
                     "baseline_database_sha256": "a" * 64}
        (self.vendor / "parser-attested-bases.json").write_text(json.dumps(inventory), encoding="utf-8")
        (self.vendor / "README.md").write_text("Fixture Creative Commons Attribution 4.0 International", encoding="utf-8")
        (self.vendor / "LICENSE-CC-BY-4.0.txt").write_text("Fixture Creative Commons Attribution 4.0 International", encoding="utf-8")
        (self.vendor / "ATTRIBUTION.md").write_text("Project-authored synthetic fixture, not retained source data.", encoding="utf-8")
        self.lock = self.root / "data" / "supplements" / "wordnet.sources.lock.json"
        self.lock.parent.mkdir(parents=True)
        self.lock_value = {
            "format_version": 1, "source_id": "wordnet:cantown", "license": "CC-BY-4.0",
            "repository": "https://example.invalid/synthetic-wordnet", "commit": "f" * 40,
            "local_directory": "vendor/wordnet", "data_file": "cantown.xml",
            "declaration_file": "README.md", "license_file": "LICENSE-CC-BY-4.0.txt",
            "selection_status": "Synthetic candidate preparation only",
            "parser_attestation": {"file": "parser-attested-bases.json", "base_count": 3,
                "baseline_database_sha256": "a" * 64,
                "sha256": file_sha256(self.vendor / "parser-attested-bases.json")},
            "files": [{"name": path.name, "sha256": file_sha256(path), "size_bytes": path.stat().st_size}
                      for path in sorted(self.vendor.iterdir())],
        }
        self.lock.write_text(json.dumps(self.lock_value), encoding="utf-8")
        self.parser = self.root / "cantonese_ime" / "wordnet.py"
        self.parser.parent.mkdir()
        # A copied parser file supplies a real hash without editing the loaded
        # implementation or any current production source/artifact.
        self.parser.write_bytes((PROJECT / "cantonese_ime/wordnet.py").read_bytes())
        for name in ("dictionary", "mappings", "wordshk", "typeduck", "unihan", "cccanto"):
            (self.parser.parent / (name + ".py")).write_text("# synthetic parser pin\n", encoding="utf-8")
        self.root_patch = patch.object(mapping_cli, "PROJECT_ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def prepare_cli(self):
        locks = (
            ("data/mappings/lshk.sources.lock.json", "lshk"),
            ("data/sources.lock.json", "rime"),
            ("data/supplements/wordshk.sources.lock.json", "wordshk"),
            ("data/supplements/typeduck.sources.lock.json", "typeduck"),
            ("data/supplements/unihan.sources.lock.json", "unihan"),
            ("data/supplements/cccanto.sources.lock.json", "cccanto"),
        )
        for relative, kind in locks:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"local_directory": "vendor/" + kind, "repository": "fixture",
                                       "commit": "f" * 40, "license": "fixture", "attribution": "fixture", "files": []}), encoding="utf-8")
        database = self.root / "lexicon.sqlite3"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE TABLE entries (base_reading TEXT, source TEXT, origin TEXT)")
            connection.execute("PRAGMA user_version=2")
            connection.executemany("INSERT INTO entries VALUES (?,?,?)", [
                ("nei", "rime:explicit", "explicit"), ("hou", "rime:explicit", "explicit")])
            connection.commit()
        self.output = self.root / "output"
        return database

    def cli_context(self, database, *extra):
        stack = ExitStack()
        stack.enter_context(patch.object(sys, "argv", ["build_mappings.py", "--database", str(database),
                                                      "--output-dir", str(self.output), *extra]))
        for name in ("verify_source_files", "verify_wordshk_snapshot", "verify_typeduck_snapshot",
                     "verify_unihan_snapshot", "verify_cccanto_snapshot"):
            stack.enter_context(patch.object(mapping_cli, name))
        for name in ("read_entries", "read_wordshk_entries", "read_typeduck_entries", "read_unihan_entries",
                     "read_cccanto_entries", "read_lshk_table"):
            stack.enter_context(patch.object(mapping_cli, name, return_value=[]))
        # This fixture isolates Wordnet attestation; its synthetic project root
        # deliberately contains no KFCD spelling source or verifier snapshot.
        stack.enter_context(patch.object(mapping_cli, "collect_kfcd_yale_source", return_value=None))
        # The live module stays frozen until root applies its separate metadata
        # patch. This scoped in-memory declaration tests the future build path.
        stack.enter_context(patch.dict(SOURCES, {mapping_cli.WORDNET_ATTESTATION_KEY: WORDNET_SOURCE}))
        stack.enter_context(redirect_stdout(io.StringIO()))
        return stack

    def test_collector_retains_all_accepted_tones_and_truthful_exclusion_counts(self):
        bases, tones, metadata = mapping_cli.collect_wordnet_source(self.lock)
        self.assertEqual(bases, {"nei", "hou", "waa"})
        self.assertEqual(tones, {"nei": {"2", "5"}, "hou": {"2"}, "waa": {"6"}})
        stats = metadata["import_stats"]
        self.assertEqual((stats["accepted_entries"], stats["duplicate_entries"], stats["blank_forms"],
                          stats["quarantined_forms"], stats["excluded_forms"]), (4, 1, 1, 1, 1))
        self.assertEqual(stats["normalized_reading_forms"], 1)
        self.assertEqual(stats["review_unattested_syllables"], 1)
        self.assertEqual(metadata["selection_status"], self.lock_value["selection_status"])
        self.assertEqual(metadata["build_selection_status"], "selected_default_post_autoencoding")
        self.assertEqual(metadata["insertion_phase"], "post_autoencoding")
        self.assertEqual(metadata["source_lock_sha256"], file_sha256(self.lock))
        self.assertEqual(metadata["parser_sha256"], file_sha256(self.parser))
        for key, value in self.lock_value.items():
            self.assertEqual(metadata[key], value)
        self.assertEqual(self.lock.read_text(encoding="utf-8"), json.dumps(self.lock_value))

    def test_tampered_snapshot_is_rejected_before_collecting_any_inventory(self):
        self.xml.write_bytes(self.xml.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            mapping_cli.collect_wordnet_source(self.lock)

    def test_wrong_source_identity_is_rejected(self):
        value = dict(self.lock_value, source_id="unrelated:source")
        self.lock.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source lock/license"):
            mapping_cli.collect_wordnet_source(self.lock)

    def test_source_lock_change_during_collection_is_rejected(self):
        original = mapping_cli.read_wordnet_entries

        def changing_reader(*args, **kwargs):
            yield from original(*args, **kwargs)
            self.lock.write_bytes(self.lock.read_bytes() + b" ")

        with patch.object(mapping_cli, "read_wordnet_entries", side_effect=changing_reader), \
                self.assertRaisesRegex(ValueError, "lock/parser changed"):
            mapping_cli.collect_wordnet_source(self.lock)

    def test_parser_pin_change_during_collection_is_rejected(self):
        original = mapping_cli.read_wordnet_entries

        def changing_reader(*args, **kwargs):
            yield from original(*args, **kwargs)
            self.parser.write_bytes(self.parser.read_bytes() + b"\n")

        with patch.object(mapping_cli, "read_wordnet_entries", side_effect=changing_reader), \
                self.assertRaisesRegex(ValueError, "lock/parser changed"):
            mapping_cli.collect_wordnet_source(self.lock)

    def test_default_cli_preserves_wordnet_overlap_attestation_and_full_provenance(self):
        database = self.prepare_cli()
        with self.cli_context(database):
            self.assertEqual(mapping_cli.main(), 0)
        inventory = json.loads((self.output / "syllables.json").read_text(encoding="utf-8"))
        mappings = json.loads((self.output / "spellings.json").read_text(encoding="utf-8"))
        by_base = {row["base"]: row for row in inventory["syllables"]}
        self.assertEqual(by_base["nei"]["retained_dictionary_sources"], ["rime:explicit"])
        self.assertEqual(by_base["nei"]["source_attestations"], ["wordnet_dictionary"])
        self.assertEqual(by_base["nei"]["observed_tones_by_source"], {"wordnet_dictionary": ["2", "5"]})
        self.assertFalse(by_base["waa"]["dictionary_observed"])
        self.assertEqual(by_base["waa"]["source_attestations"], ["wordnet_dictionary"])
        self.assertNotIn("yat", by_base)
        self.assertEqual(inventory["source_inventory_counts"]["wordnet_dictionary"], 3)
        self.assertEqual(inventory["source_observed_toned_form_counts"]["wordnet_dictionary"], 4)
        metadata = inventory["source_metadata"]["wordnet_dictionary"]
        self.assertEqual(metadata, mappings["source_metadata"]["wordnet_dictionary"])
        self.assertEqual(metadata["source_lock_file"], "data/supplements/wordnet.sources.lock.json")
        self.assertEqual(metadata["files"], self.lock_value["files"])
        self.assertEqual(metadata["selection_status"], self.lock_value["selection_status"])
        self.assertEqual(inventory["source_metadata"]["parser_sha256"]["wordnet"], file_sha256(self.parser))
        self.assertEqual(metadata["source_lock_sha256"], file_sha256(self.lock))
        manifest = json.loads((self.output / "build.manifest.json").read_text(encoding="utf-8"))
        for filename, digest in manifest["files"].items():
            self.assertEqual(digest, file_sha256(self.output / filename))

    def test_explicit_wordnet_lock_cli_argument_is_recorded(self):
        database = self.prepare_cli()
        alternative = self.root / "explicit-wordnet-lock.json"
        alternative.write_bytes(self.lock.read_bytes())
        with self.cli_context(database, "--wordnet-lock", str(alternative)):
            self.assertEqual(mapping_cli.main(), 0)
        metadata = json.loads((self.output / "syllables.json").read_text(encoding="utf-8"))["source_metadata"]["wordnet_dictionary"]
        self.assertEqual(metadata["source_lock_file"], "explicit-wordnet-lock.json")
        self.assertEqual(metadata["source_lock_sha256"], file_sha256(alternative))

    def test_snapshot_change_after_mapping_computation_preserves_existing_outputs(self):
        database = self.prepare_cli()
        self.output.mkdir()
        before = {filename: ("previous:" + filename).encode() for filename in
                  ("syllables.json", "spellings.json", "build.manifest.json")}
        for filename, payload in before.items():
            (self.output / filename).write_bytes(payload)

        def changed_source(*args, **kwargs):
            result = build_mapping_artifacts(*args, **kwargs)
            self.xml.write_bytes(self.xml.read_bytes() + b" ")
            return result

        with self.cli_context(database), patch.object(mapping_cli, "build_mapping_artifacts", side_effect=changed_source), \
                self.assertRaises(ValueError):
            mapping_cli.main()
        self.assertEqual({path.name: path.read_bytes() for path in self.output.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
