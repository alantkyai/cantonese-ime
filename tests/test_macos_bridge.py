"""Mac stdio transport tests; run locally without pretending to test AppKit."""
from contextlib import closing, redirect_stderr
import io
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime import Engine
from cantonese_ime.native_protocol import (LearningRequest, LookupRequest, MAX_FRAME_BYTES,
    Status, decode_response, encode_learning_request, encode_request)
from macos.engine import stdio_bridge as bridge
from tools import check_macos_engine as checker


ROOT = Path(__file__).resolve().parents[1]


def framed(body):
    return struct.pack("<I", len(body)) + body


def responses(value):
    result = []
    stream = io.BytesIO(value)
    while prefix := stream.read(4):
        size = struct.unpack("<I", prefix)[0]
        body = stream.read(size)
        if len(body) != size:
            raise AssertionError("Bridge produced a partial response")
        result.append(decode_response(body))
    return result


def fixture(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY,text TEXT,reading TEXT,base_reading TEXT,compact TEXT,syllable_count INTEGER,weight REAL,source TEXT)")
        rows = [("五", "ng5", "ng", 100.0), ("唔", "ng4", "ng", 0.0),
                ("唔", "m4", "m", 10000.0), ("好", "hou2", "hou", 100.0),
                ("唔好", "m4 hou2", "m hou", 1000.0), ("係", "hai6", "hai", 100.0),
                ("咁", "gam3", "gam", 100.0)]
        connection.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?)", [
            (index, text, reading, base, base.replace(" ", ""), len(reading.split()), weight, "synthetic-mac-bridge")
            for index, (text, reading, base, weight) in enumerate(rows, 1)])
        connection.commit()


class Fragmented(io.BytesIO):
    def read(self, size=-1):
        return super().read(min(size, 3) if size >= 0 else 3)


class MacBridgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cantonese-mac-bridge-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "dictionary.sqlite3"
        self.memory = self.root / "learning.json"
        fixture(self.database)

    def exchange(self, payload, *, memory=False, fragmented=False):
        destination = io.BytesIO()
        with Engine(self.database, learning_path=self.memory if memory else None) as engine:
            count = bridge.serve(engine, Fragmented(payload) if fragmented else io.BytesIO(payload), destination)
        return count, responses(destination.getvalue())

    def test_fragmented_concatenated_binary_frames_preserve_unicode_and_ids(self):
        body = b"".join(framed(encode_request(LookupRequest(index, 0, 0, 9, raw)))
                        for index, raw in ((7, "ng"), (9, "mhou")))
        count, result = self.exchange(body, fragmented=True)
        self.assertEqual(count, 2)
        self.assertEqual([row.request_id for row in result], [7, 9])
        self.assertIn("唔", {row.text for row in result[0].candidates})
        self.assertEqual(result[1].candidates[0].text, "唔好")
        self.assertFalse(self.memory.exists())

    def test_boundary_eof_is_clean_and_never_emits_unframed_output(self):
        self.assertEqual(self.exchange(b""), (0, []))

    def test_bridge_default_and_opt_out_preserve_canonical_nasal_readings(self):
        with bridge.open_engine(self.database, None) as engine:
            destination = io.BytesIO()
            bridge.serve(engine, io.BytesIO(framed(encode_request(LookupRequest(15, 0, 0, 9, "nghou")))), destination)
            result = responses(destination.getvalue())[0]
            self.assertEqual((result.candidates[0].text, result.candidates[0].reading), ("唔好", "m4 hou2"))
            self.assertNotIn("m4 hou2", {row.reading for row in engine.lookup("nghou", mode="jyutping")})
        with bridge.open_engine(self.database, None, syllabic_m_as_ng=False) as engine:
            self.assertFalse(engine.syllabic_m_as_ng)
            self.assertNotIn("m4 hou2", {row.reading for row in engine.lookup("nghou")})

    def test_legacy_constructor_negotiates_auto_and_explicit_opt_out(self):
        calls = []

        class LegacyEngine:
            def __init__(self, dictionary, learning_path=None):
                calls.append((dictionary, learning_path))
                self.learning_path = learning_path

        with patch.object(bridge, "Engine", LegacyEngine):
            self.assertFalse(bridge.supports_habitual_ng())
            auto = bridge.open_engine(self.database, self.memory)
            disabled = bridge.open_engine(self.database, None, syllabic_m_as_ng=False)
            self.assertEqual(bridge.habitual_ng_status(auto), "unavailable")
            self.assertEqual(bridge.habitual_ng_status(disabled), "unavailable")
            with self.assertRaisesRegex(ValueError, "does not support.*ng-for-m"):
                bridge.open_engine(self.database, None, syllabic_m_as_ng=True)
        self.assertEqual(calls, [(self.database, self.memory), (self.database, None)])

    def test_kwargs_alone_is_not_an_explicit_engine_capability(self):
        class LegacyWrapper:
            def __init__(self, dictionary, **kwargs):
                self.options = kwargs

        with patch.object(bridge, "Engine", LegacyWrapper):
            result = bridge.open_engine(self.database, None)
            self.assertEqual(result.options, {"learning_path": None})
            with self.assertRaises(bridge.EngineCapabilityError):
                bridge.open_engine(self.database, None, syllabic_m_as_ng=True)

    def test_legacy_learning_fallback_retains_the_same_negotiated_options(self):
        calls = []

        class LegacyEngine:
            def __init__(self, dictionary, learning_path=None):
                calls.append((dictionary, learning_path))
                if learning_path is not None:
                    raise ValueError("Cannot read learning data: isolated corrupt fixture")
                self.learning_path = None

        with patch.object(bridge, "Engine", LegacyEngine), redirect_stderr(io.StringIO()):
            result = bridge.open_engine(self.database, self.memory)
        self.assertIsNone(result.learning_path)
        self.assertEqual(calls, [(self.database, self.memory), (self.database, None)])

    def test_checker_pins_the_package_used_by_a_staged_bridge(self):
        staged = self.root / "stage"
        (staged / "cantonese_ime").mkdir(parents=True)
        (staged / "cantonese_ime/engine.py").write_bytes(b"# separately pinned engine\n")
        script = staged / "stdio_bridge.py"
        script.write_bytes(b"# bridge fixture\n")
        self.assertEqual(checker.child_engine_root(script), staged)
        self.assertEqual(checker.child_engine_root(ROOT / "macos/engine/stdio_bridge.py"), ROOT)

    def test_invalid_lengths_and_truncation_are_fatal_without_partial_response(self):
        for data in (b"\x01", struct.pack("<I", 0), struct.pack("<I", MAX_FRAME_BYTES + 1), struct.pack("<I", 4) + b"a"):
            with self.subTest(data=data), Engine(self.database) as engine:
                output = io.BytesIO()
                with self.assertRaises(bridge.FramingError):
                    bridge.serve(engine, io.BytesIO(data), output)
                self.assertEqual(output.getvalue(), b"")

    def test_bad_payload_does_not_poison_the_next_complete_frame(self):
        count, result = self.exchange(framed(b"invalid") + framed(encode_request(LookupRequest(18, 0, 0, 9, "ng"))))
        self.assertEqual(count, 2)
        self.assertEqual(result[0].status, Status.INVALID)
        self.assertEqual(result[1].request_id, 18)
        self.assertEqual(result[1].status, Status.OK)

    def test_only_explicit_valid_selection_writes_and_transfers_to_compounds(self):
        lookup = framed(encode_request(LookupRequest(1, 0, 0, 9, "ng")))
        learn = framed(encode_learning_request(LearningRequest(2, 0, "ng", "唔", "ng4")))
        count, result = self.exchange(lookup + learn, memory=True)
        self.assertEqual(count, 2)
        self.assertEqual(result[-1].status, Status.OK)
        self.assertEqual(json.loads(self.memory.read_text(encoding="utf-8"))["schema_version"], 2)
        _, reopened = self.exchange(framed(encode_request(LookupRequest(3, 0, 0, 9, "nghaigam"))), memory=True)
        self.assertIn("唔係咁", {row.text for row in reopened[0].candidates})

    def test_forged_learning_and_disabled_memory_do_not_create_a_store(self):
        payload = framed(encode_learning_request(LearningRequest(2, 0, "ng", "火炬", "fo2 geoi6")))
        _, result = self.exchange(payload, memory=True)
        self.assertEqual(result[0].status, Status.INVALID)
        self.assertFalse(self.memory.exists())
        _, result = self.exchange(payload, memory=False)
        self.assertEqual(result[0].status, Status.INTERNAL)
        self.assertFalse(self.memory.exists())

    def test_corrupt_learning_is_preserved_with_conversion_only_fallback(self):
        original = b"{private-invalid-selection-memory"
        self.memory.write_bytes(original)
        log = io.StringIO()
        with redirect_stderr(log), bridge.open_engine(self.database, self.memory) as engine:
            self.assertIsNone(engine.learning_path)
            self.assertTrue(engine.syllabic_m_as_ng)
            self.assertTrue(engine.lookup("ng"))
        self.assertEqual(self.memory.read_bytes(), original)
        self.assertNotIn(str(self.memory), log.getvalue())
        self.assertNotIn("private-invalid", log.getvalue())

    def test_dictionary_failure_does_not_become_a_learning_fallback(self):
        with patch.object(bridge, "Engine", side_effect=ValueError("Unsupported dictionary schema")) as constructor:
            with self.assertRaisesRegex(ValueError, "dictionary"):
                bridge.open_engine(self.database, self.memory)
            constructor.assert_called_once()

    def test_default_store_is_mac_application_support_and_other_hosts_require_explicit_choice(self):
        with patch.object(bridge.sys, "platform", "darwin"), patch.object(bridge.Path, "home", return_value=self.root):
            self.assertEqual(bridge.default_learning_file(), self.root / "Library/Application Support/CantoneseIME/learning.json")
        with patch.object(bridge.sys, "platform", "win32"):
            with self.assertRaises(ValueError):
                bridge.default_learning_file()

    def child(self, payload, *extra):
        return subprocess.run([sys.executable, "-B", "-I", str(ROOT / "macos/engine/stdio_bridge.py"),
                               "--dictionary", str(self.database), *map(str, extra)], input=payload,
                              capture_output=True, cwd=self.root, timeout=15)

    def test_real_child_handles_learning_restart_without_stdout_diagnostics(self):
        value = framed(encode_learning_request(LearningRequest(1, 0, "ng", "唔", "ng4")))
        # Create a real legacy ng4 selection through the opt-out, then reopen
        # the same store with the new default. No fabricated history records.
        first = self.child(value, "--learning-file", self.memory, "--no-syllabic-m-as-ng")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn(b"ng-for-m=off", first.stderr)
        self.assertEqual(responses(first.stdout)[0].status, Status.OK)
        second = self.child(framed(encode_request(LookupRequest(2, 0, 0, 9, "ngho"))), "--learning-file", self.memory)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn(b"ng-for-m=on", second.stderr)
        self.assertIn("唔好", {row.text for row in responses(second.stdout)[0].candidates})
        self.assertEqual(responses(second.stdout)[0].candidates[0].reading, "m4 hou2")
        self.assertEqual(json.loads(self.memory.read_text(encoding="utf-8"))["selections"][0]["reading"], "ng4")
        self.assertNotIn("ngho", second.stderr.decode())
        self.assertNotIn(str(self.memory), second.stderr.decode())

    def test_real_child_rejects_dictionary_pin_and_truncated_frame(self):
        wrong = self.child(b"", "--disable-learning", "--expected-dictionary-sha256", "0" * 64)
        self.assertEqual(wrong.returncode, 2)
        self.assertEqual(wrong.stdout, b"")
        truncated = self.child(b"\x03", "--disable-learning")
        self.assertEqual(truncated.returncode, 2)
        self.assertEqual(truncated.stdout, b"")
        self.assertNotIn(str(self.database), truncated.stderr.decode())


if __name__ == "__main__":
    unittest.main()
