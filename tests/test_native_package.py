"""Synthetic package staging only; no installed files or programs are used."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import package_native as package


def pe_bytes():
    header = bytearray(70)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 60, 64)
    header[64:70] = b"PE\0\0\x64\x86"
    return bytes(header)


class NativePackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-package-fixture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root_patch = patch.object(package, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.python = self.write("external-python.exe", pe_bytes())
        self.write("cantonese_ime/__init__.py", b"# fixture\n")
        self.mapping_module = self.write("cantonese_ime/mappings.py", b"# synthetic mapping implementation\n")
        self.wordnet_parser = self.write("cantonese_ime/wordnet.py", b"# synthetic Wordnet parser\n")
        database = self.write("data/generated/lexicon.sqlite3", b"synthetic dictionary, not a production DB\n")
        self.dictionary_hash = package.digest(database)
        self.vendor = "data/vendor/cantonese-wordnet/frozen-fixture"
        files = []
        for name, content in (
            ("README.md", "Synthetic upstream README and attribution"),
            ("ATTRIBUTION.md", "Synthetic transformation/citation notice"),
            ("LICENSE-CC-BY-4.0.txt", "Synthetic full-license placeholder"),
            ("cantown.xml", "<synthetic-raw-table-not-to-be-bundled/>"),
            ("parser-attested-bases.json", '{"synthetic":true}'),
        ):
            path = self.write(self.vendor + "/" + name, content.encode())
            files.append({"name": name, "sha256": package.digest(path), "size_bytes": path.stat().st_size})
        self.wordnet_lock = {
            "source_id": "wordnet:cantown", "license": "CC-BY-4.0",
            "local_directory": self.vendor, "files": files,
            "selection_status": "Original immutable synthetic candidate preparation status",
        }
        self.lock_path = self.json("data/supplements/wordnet.sources.lock.json", self.wordnet_lock)
        selected = dict(self.wordnet_lock,
            source_lock_file="data/supplements/wordnet.sources.lock.json",
            source_lock_sha256=package.digest(self.lock_path),
            parser_file="cantonese_ime/wordnet.py", parser_sha256=package.digest(self.wordnet_parser),
            insertion_phase="post_autoencoding", build_selection_status="selected_default_post_autoencoding")
        self.dictionary_metadata = {"database_sha256": self.dictionary_hash,
                                    "source_metadata": {"supplements": {"wordnet": selected}}}
        self.source_manifest = self.json("data/generated/lexicon.manifest.json", self.dictionary_metadata)
        self.mapping_names = ("syllables.json", "spellings.json")
        for name in self.mapping_names:
            self.json("data/mappings/" + name,
                      {"source_metadata": {"database": {"sha256": self.dictionary_hash}}})
        self.mapping_manifest = {"files": {name: package.digest(self.root / "data/mappings" / name)
                                           for name in self.mapping_names},
                                 "module_sha256": package.digest(self.mapping_module)}
        self.json("data/mappings/build.manifest.json", self.mapping_manifest)
        dll = self.write(".local/native/build-x64/CantoneseIME.dll", pe_bytes())
        native_source = self.write("native/tsf/synthetic-source.cpp", b"// synthetic native source\n")
        self.json(".local/native/build-x64/build-manifest.json", {
            "artifacts": [{"path": str(dll), "sha256": package.digest(dll)}],
            "sources": [{"path": str(native_source), "sha256": package.digest(native_source)}]})
        helper = self.write(".local/native/build-x64/CantoneseMachineRegistration.exe", pe_bytes())
        self.json(".local/native/machine-registration-guard-checks.json", {
            "passed": True, "checks": [{"passed": True}], "helper_sha256": package.digest(helper)})
        for name in ("native/backend/server.py", "native/runtime/control.py", "native/runtime/Start-Runtime.ps1",
                     "native/runtime/README.md", "native/Install-NativeIme.ps1", "native/Remove-NativeIme.ps1",
                     "native/Update-NativeIme.ps1", "native/UPGRADING.md"):
            self.write(name, b"# synthetic fixture\n")
        # No Markdown source links: selected source notices must be retained
        # through the dictionary manifest, not an incidental documentation link.
        self.write("data/THIRD_PARTY_NOTICES.md", b"Synthetic distribution notice.\n")
        self.json("native/toolchain.lock.json", {"local_directory": "toolchain-fixture"})
        self.write("toolchain-fixture/LICENSE.TXT", b"synthetic toolchain notice")
        self.write("toolchain-fixture/x86_64-w64-mingw32/share/mingw32/COPYING.fixture", b"synthetic runtime notice")
        self.output = self.root / "new-package"

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def json(self, relative, value):
        return self.write(relative, (json.dumps(value, indent=2) + "\n").encode())

    def save_source_manifest(self):
        self.json("data/generated/lexicon.manifest.json", self.dictionary_metadata)

    def fake_configure(self, args, **options):
        self.assertEqual(args[:2], [str(self.python), "-B"])
        self.assertEqual(options["timeout"], 45)
        Path(args[args.index("--config") + 1]).write_text('{"synthetic_config":true}\n', encoding="utf-8")

    def stage(self):
        with patch.object(package.subprocess, "run", side_effect=self.fake_configure) as launch:
            result = package.stage(self.output, self.python)
        self.assertEqual(launch.call_count, 1)
        return result

    def assert_rejected_before_staging(self, message):
        with patch.object(package.subprocess, "run") as launch, self.assertRaisesRegex(ValueError, message):
            package.stage(self.output, self.python)
        self.assertFalse(self.output.exists())
        launch.assert_not_called()

    def test_selected_wordnet_retains_runtime_module_and_all_notices_without_bundling_raw_source(self):
        manifest = self.stage()
        records = {record["path"]: record for record in manifest["files"]}
        required = {"cantonese_ime/wordnet.py", "data/supplements/wordnet.sources.lock.json",
                    self.vendor + "/README.md", self.vendor + "/ATTRIBUTION.md",
                    self.vendor + "/LICENSE-CC-BY-4.0.txt"}
        self.assertTrue(required <= records.keys())
        self.assertNotIn(self.vendor + "/cantown.xml", records)
        self.assertNotIn(self.vendor + "/parser-attested-bases.json", records)
        for name in required:
            self.assertEqual((self.output / name).read_bytes(), (self.root / name).read_bytes())
            self.assertEqual(records[name]["sha256"], package.digest(self.output / name))
        self.assertEqual(manifest["dictionary_sha256"], self.dictionary_hash)
        self.assertFalse(manifest["installed"])
        self.assertEqual(self.lock_path.read_bytes(), (self.output / "data/supplements/wordnet.sources.lock.json").read_bytes())

    def test_registration_helper_is_bound_to_its_successful_guard_report(self):
        manifest = self.stage()
        helper = self.output / "native/CantoneseMachineRegistration.exe"
        guards = json.loads((self.output / "native/registration-guard-checks.json").read_text())
        records = {row["path"]: row for row in manifest["files"]}
        self.assertTrue(guards["passed"])
        self.assertEqual(package.digest(helper), guards["helper_sha256"])
        self.assertEqual(records["native/CantoneseMachineRegistration.exe"]["sha256"], guards["helper_sha256"])

    def test_new_helper_with_stale_guard_report_is_rejected_before_staging(self):
        helper = self.root / ".local/native/build-x64/CantoneseMachineRegistration.exe"
        helper.write_bytes(helper.read_bytes() + b"different helper revision")
        self.assert_rejected_before_staging("differs from its reviewed guard-test artifact")

    def test_failing_or_incomplete_registration_guards_are_rejected(self):
        helper = self.root / ".local/native/build-x64/CantoneseMachineRegistration.exe"
        for report in (
                {"passed": False, "checks": [{"passed": True}]},
                {"passed": True, "checks": [{"passed": False}]},
                {"passed": True, "checks": []}):
            with self.subTest(report=report):
                self.json(".local/native/machine-registration-guard-checks.json",
                          dict(report, helper_sha256=package.digest(helper)))
                self.assert_rejected_before_staging("guard checks are incomplete or failing")

    def test_guard_report_change_after_configuration_prevents_publication(self):
        report = self.root / ".local/native/machine-registration-guard-checks.json"

        def changed_after_configure(args, **options):
            self.fake_configure(args, **options)
            report.write_bytes(report.read_bytes() + b" ")

        with patch.object(package.subprocess, "run", side_effect=changed_after_configure), \
                self.assertRaisesRegex(ValueError, "Validated package input changed"):
            package.stage(self.output, self.python)
        self.assertFalse((self.output / "package-manifest.json").exists())

    def test_old_dictionary_without_wordnet_has_no_new_notice_requirement(self):
        del self.dictionary_metadata["source_metadata"]["supplements"]["wordnet"]
        self.save_source_manifest()
        (self.root / self.vendor / "README.md").unlink()
        manifest = self.stage()
        self.assertNotIn(self.vendor + "/README.md", {record["path"] for record in manifest["files"]})

    def test_modified_selected_source_lock_is_rejected(self):
        self.lock_path.write_bytes(self.lock_path.read_bytes() + b" ")
        self.assert_rejected_before_staging("source lock changed")

    def test_modified_selected_notice_is_rejected(self):
        path = self.root / self.vendor / "README.md"
        path.write_bytes(path.read_bytes() + b"changed")
        self.assert_rejected_before_staging("notice differs")

    def test_missing_full_selected_license_is_rejected(self):
        (self.root / self.vendor / "LICENSE-CC-BY-4.0.txt").unlink()
        self.assert_rejected_before_staging("missing or outside")

    def test_parser_revision_must_match_selected_dictionary_source_metadata(self):
        self.wordnet_parser.write_bytes(self.wordnet_parser.read_bytes() + b"changed")
        self.assert_rejected_before_staging("parser changed")

    def test_embedded_lock_fields_must_preserve_original_source_selection_status(self):
        self.dictionary_metadata["source_metadata"]["supplements"]["wordnet"]["selection_status"] = "Changed raw source status"
        self.save_source_manifest()
        self.assert_rejected_before_staging("differs from its original lock")

    def test_selected_source_must_retain_post_autoencoding_policy(self):
        self.dictionary_metadata["source_metadata"]["supplements"]["wordnet"]["insertion_phase"] = "before_autoencoding"
        self.save_source_manifest()
        self.assert_rejected_before_staging("reviewed import policy")

    def test_self_consistent_mapping_artifacts_bound_to_old_dictionary_are_rejected(self):
        name = "spellings.json"
        self.json("data/mappings/" + name, {"source_metadata": {"database": {"sha256": "a" * 64}}})
        self.mapping_manifest["files"][name] = package.digest(self.root / "data/mappings" / name)
        self.json("data/mappings/build.manifest.json", self.mapping_manifest)
        self.assert_rejected_before_staging("bound to another dictionary")

    def test_mapping_artifact_or_implementation_changes_are_rejected(self):
        original = (self.root / "data/mappings/syllables.json").read_bytes()
        self.write("data/mappings/syllables.json", original + b" ")
        self.assert_rejected_before_staging("differs from its build manifest")
        self.write("data/mappings/syllables.json", original)
        self.mapping_module.write_bytes(self.mapping_module.read_bytes() + b"changed")
        self.assert_rejected_before_staging("Mapping implementation changed")


if __name__ == "__main__":
    unittest.main()
