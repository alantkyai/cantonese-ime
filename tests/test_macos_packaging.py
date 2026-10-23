"""Portable bundle/build checks; no Apple tool, installer or user data is used."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from macos import build_release as build


class MacPackagingTests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[1] / ".local/macos-packaging-tests"
        work.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="fixture-", dir=work)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.macos = self.root / "macos"
        (self.macos / "engine").mkdir(parents=True)
        (self.macos / "engine/stdio_bridge.py").write_bytes(b"# independent bridge fixture\n")
        (self.macos / "installer").mkdir()
        (self.macos / "installer/preinstall").write_bytes(b"#!/bin/sh\nexit 0\n")
        (self.macos / "installer/postinstall").write_bytes(b"#!/bin/sh\nexit 0\n")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(build, "ROOT", self.root))
        self.stack.enter_context(patch.object(build, "MACOS", self.macos))

    def snapshot(self, *, kind=None, extra=None):
        source = self.root / "windows-package"
        source.mkdir()
        contents = {
            "cantonese_ime/engine.py": b"# shared engine fixture\n",
            "data/generated/lexicon.sqlite3": b"not SQLite: packaging-only fixture",
            "data/THIRD_PARTY_NOTICES.md": b"Original data notices\n",
            "data/licenses/fixture/LICENSE.txt": b"Full retained upstream license\n",
            "native/CantoneseIME.dll": b"Windows-only image fixture",
            "runtime/python.exe": b"Windows-only interpreter fixture",
        }
        contents.update(extra or {})
        records = []
        for name, data in contents.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            records.append({"path": name, "bytes": len(data), "sha256": build.digest(path)})
        value = {"schema_version": 1, "kind": kind or build.WINDOWS_KIND,
                 "dictionary_sha256": build.digest(source / "data/generated/lexicon.sqlite3"),
                 "files": records}
        return source, self.publish(source, value), value

    @staticmethod
    def publish(source, value):
        build.write_json(source / "package-manifest.json", value)
        return build.digest(source / "package-manifest.json")

    def test_manifest_requires_external_pin_and_unchanged_payload(self):
        source, pin, expected = self.snapshot()
        self.assertEqual(build.read_manifest(source, pin), expected)
        with self.assertRaises(ValueError):
            build.read_manifest(source, "0" * 64)
        (source / "data/THIRD_PARTY_NOTICES.md").write_bytes(b"altered notice\n")
        with self.assertRaisesRegex(ValueError, "file changed"):
            build.read_manifest(source, pin)

    def test_manifest_rejects_case_collisions_and_disagreeing_dictionary_pin(self):
        source, _, value = self.snapshot()
        duplicate = dict(value["files"][0], path="CANTONESE_IME/ENGINE.PY")
        value["files"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build.read_manifest(source, self.publish(source, value))
        value["files"].pop()
        value["dictionary_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "pins disagree"):
            build.read_manifest(source, self.publish(source, value))

    def test_paths_reject_escape_aliases_and_windows_stream_syntax(self):
        for relative in ("../escape", "/absolute", "C:/outside", "a\\b", "a//b", "./file", "a/../b", "a:stream", "a\x00b", ""):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                build.safe_file(self.root, relative)
        self.assertEqual(build.safe_file(self.root, "data/licenses/A.txt"), self.root / "data/licenses/A.txt")

    def test_stage_copies_engine_dictionary_and_notices_without_windows_runtime(self):
        source, pin, original = self.snapshot()
        target = self.root / "engine"
        result = build.stage_engine(source, pin, target)
        names = {item["path"] for item in result["files"]}
        self.assertEqual(names, {"cantonese_ime/engine.py", "data/generated/lexicon.sqlite3",
                                 "data/THIRD_PARTY_NOTICES.md", "data/licenses/fixture/LICENSE.txt", "stdio_bridge.py"})
        self.assertFalse((target / "runtime").exists())
        self.assertFalse((target / "native").exists())
        self.assertEqual(result["source_package_manifest_sha256"], pin)
        self.assertEqual(result["dictionary_sha256"], original["dictionary_sha256"])
        self.assertEqual(build.read_manifest(target, build.digest(target / "package-manifest.json")), result)
        with self.assertRaisesRegex(ValueError, "already exists"):
            build.stage_engine(source, pin, target)

    def test_shared_snapshot_preserves_its_own_pinned_bridge(self):
        source, pin, _ = self.snapshot(kind=build.ENGINE_KIND, extra={"stdio_bridge.py": b"# original pinned bridge\n"})
        target = self.root / "engine"
        build.stage_engine(source, pin, target)
        self.assertEqual((target / "stdio_bridge.py").read_bytes(), b"# original pinned bridge\n")

    def test_stage_detects_source_notice_mutation_after_copy(self):
        source, pin, _ = self.snapshot()
        original_copy = build.shutil.copyfile

        def mutate_after_copy(src, dst, *args, **kwargs):
            result = original_copy(src, dst, *args, **kwargs)
            if Path(src) == source / "data/THIRD_PARTY_NOTICES.md":
                Path(src).write_bytes(b"notice changed after the copy\n")
            return result

        with patch.object(build.shutil, "copyfile", side_effect=mutate_after_copy):
            with self.assertRaisesRegex(ValueError, "file changed"):
                build.stage_engine(source, pin, self.root / "engine")

    def test_dependency_rejects_stale_bytes_without_fetch_or_execution(self):
        pkg = self.root / "fixture.pkg"
        pkg.write_bytes(b"official fixture bytes")
        lock = {"python": {"filename": pkg.name, "bytes": pkg.stat().st_size, "sha256": build.digest(pkg)}}
        build.write_json(self.macos / "dependencies.lock.json", lock)
        with patch.object(build.urllib.request, "urlretrieve") as fetch:
            self.assertEqual(build.dependency(pkg, fetch=False), (pkg.resolve(), lock))
            pkg.write_bytes(b"tampered fixture bytes")
            with self.assertRaisesRegex(ValueError, "differs"):
                build.dependency(pkg, fetch=False)
            fetch.assert_not_called()

    def test_relocation_only_rewrites_the_exact_upstream_framework_tree(self):
        prefix = "/Library/Frameworks/Python.framework"
        cases = {
            prefix: "@rpath/Python.framework",
            prefix + "/Versions/3.13/Python": "@rpath/Python.framework/Versions/3.13/Python",
            prefix + "-other/Python": prefix + "-other/Python",
            "/usr/lib/libSystem.B.dylib": "/usr/lib/libSystem.B.dylib",
            "@loader_path/libssl.dylib": "@loader_path/libssl.dylib",
        }
        for original, expected in cases.items():
            with self.subTest(original=original):
                self.assertEqual(build.new_install_name(original, prefix), expected)

    def test_framework_payload_uses_package_identity_and_install_location(self):
        expanded = self.root / "expanded"
        for directory, identity, location in (("other", "org.python.Python.PythonApplications-3.13", "/Applications"),
                                                ("framework", "org.python.Python.PythonFramework-3.13", "/Library/Frameworks/Python.framework")):
            package = expanded / directory
            binary = package / "Payload/Versions/3.13/Python"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"fixture runtime")
            (package / "PackageInfo").write_text(f'<pkg-info identifier="{identity}" install-location="{location}"/>', encoding="utf-8")
        self.assertEqual(build.framework_payload(expanded, "3.13"), expanded / "framework/Payload")
        (expanded / "framework/PackageInfo").write_text('<pkg-info identifier="unrelated"/>', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "uniquely locate"):
            build.framework_payload(expanded, "3.13")

    def test_framework_payload_refuses_ambiguous_matching_packages(self):
        expanded = self.root / "expanded"
        for name in ("first", "second"):
            package = expanded / name
            binary = package / "Payload/Versions/3.13/Python"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"fixture runtime")
            (package / "PackageInfo").write_text('<pkg-info identifier="org.python.Python.PythonFramework-3.13" install-location="/Library/Frameworks/Python.framework"/>', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "uniquely locate"):
            build.framework_payload(expanded, "3.13")

    def test_distribution_has_system_volume_only_and_declared_minimum(self):
        value = ET.fromstring(build.make_distribution("1.0.0", "Cantonese&IME.pkg"))
        domains = value.find("domains")
        self.assertEqual(domains.attrib, {"enable_anywhere": "false", "enable_currentUserHome": "false", "enable_localSystem": "true"})
        self.assertEqual(value.find("allowed-os-versions/os-version").get("min"), "13.0")
        self.assertEqual(value.findall("pkg-ref")[-1].text, "Cantonese&IME.pkg")
        for version, name in (("1.0", "a.pkg"), ("1.0.0-beta", "a.pkg"), ("1.0.0", "../a.pkg")):
            with self.subTest(version=version, name=name), self.assertRaises(ValueError):
                build.make_distribution(version, name)

    def test_source_guard_covers_added_modified_deleted_sources_and_checker(self):
        checker = self.root / "tools/check_macos_engine.py"
        checker.parent.mkdir()
        checker.write_bytes(b"# transport proof fixture\n")
        baseline = build.source_snapshot()
        build.verify_sources(baseline)
        self.assertIn("tools/check_macos_engine.py", baseline)
        cache = self.macos / "__pycache__/ignored.pyc"
        cache.parent.mkdir()
        cache.write_bytes(b"cache")
        build.verify_sources(baseline)
        added = self.macos / "added.swift"
        added.write_bytes(b"// source\n")
        with self.assertRaisesRegex(ValueError, "source changed"):
            build.verify_sources(baseline)
        added.unlink()
        checker.write_bytes(b"# changed checker\n")
        with self.assertRaisesRegex(ValueError, "source changed"):
            build.verify_sources(baseline)
        checker.unlink()
        with self.assertRaisesRegex(ValueError, "source changed"):
            build.verify_sources(baseline)

    def test_source_zip_has_pinned_offline_inputs_and_no_native_success_claim(self):
        source, pin, _ = self.snapshot()
        pkg = self.root / "python-fixture.pkg"
        pkg.write_bytes(b"packaging fixture; never an executable input")
        lock = {"python": {"sha256": build.digest(pkg)}}
        output = self.root / "out"
        output.mkdir()
        pins = build.source_snapshot()
        with patch.object(build, "run", side_effect=AssertionError("No platform command permitted")):
            report = build.source_release(output, source, pin, pkg, lock, pins)
        self.assertEqual(report["artifact_kind"], "source_zip")
        for field in ("native_compiled", "native_tested", "signed", "notarized"):
            self.assertIs(report[field], False)
        self.assertEqual(report["sha256"], build.digest(output / report["filename"]))
        with zipfile.ZipFile(output / report["filename"]) as archive:
            prefix = f"CantoneseIME-{build.VERSION}-macos-source/"
            for name, expected in report["archive_members_sha256"].items():
                self.assertEqual(hashlib.sha256(archive.read(prefix + name)).hexdigest(), expected)
            mode = archive.getinfo(prefix + "macos/installer/preinstall").external_attr >> 16
            self.assertEqual(stat.S_IMODE(mode), 0o755)
            self.assertEqual(archive.getinfo(prefix + "dependencies/" + pkg.name).compress_type, zipfile.ZIP_STORED)
            self.assertIn(prefix + "engine/data/licenses/fixture/LICENSE.txt", archive.namelist())
            self.assertNotIn(prefix + "engine/native/CantoneseIME.dll", archive.namelist())


if __name__ == "__main__":
    unittest.main()
