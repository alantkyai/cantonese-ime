"""Learning protocol and local-file behavior; no Win32 APIs or native process."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from cantonese_ime import Engine
from cantonese_ime.native_protocol import (
    LEARNING_HEADER, LEARNING_MAGIC, LearningRequest, LookupRequest, ProtocolError, Status,
    decode_learning_request, decode_response, dispatch, encode_learning_request, encode_request, encode_response,
)
from native.backend import server


class NativeLearningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "dictionary.sqlite3"
        self.memory = self.root / "user/learning.json"
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("CREATE TABLE entries(text TEXT,reading TEXT,base_reading TEXT,weight REAL)")
            db.executemany("INSERT INTO entries VALUES(?,?,?,?)", [
                ("你", "nei5", "nei", 1000), ("妳", "nei5", "nei", 100),
                ("尼", "nei4", "nei", 10), ("好", "hou2", "hou", 300),
                ("你好", "nei5 hou2", "nei hou", 500), ("妳好", "nei5 hou2", "nei hou", 100),
            ])
            db.commit()
        self.request = LearningRequest(0x01020304, 0, "nei", "妳", "nei5")

    def send(self, engine, request=None):
        response = dispatch(engine, encode_learning_request(request or self.request))
        self.assertEqual(decode_response(encode_response(response), expected_request_id=response.request_id), response)
        self.assertEqual(response.candidates, ())
        self.assertIsNone(response.next_offset)
        self.assertFalse(response.completion_truncated)
        return response

    def records(self):
        return json.loads(self.memory.read_text(encoding="utf-8"))["selections"]

    def test_wire_layout_exact_and_round_trip(self):
        text = "妳".encode("utf-8")
        expected = LEARNING_HEADER.pack(LEARNING_MAGIC, 0x01020304, 0, 3, len(text), 4) + b"nei" + text + b"nei5"
        self.assertEqual(encode_learning_request(self.request), expected)
        self.assertEqual(decode_learning_request(expected), self.request)
        boundary = LearningRequest(0xFFFFFFFF, 1, "n" * 256, "𠮷" * 256, "abcdefghijkl6 " * 255 + "abcdefghijkl6")
        self.assertEqual(decode_learning_request(encode_learning_request(boundary)), boundary)

    def test_invalid_fields_are_rejected_without_writing(self):
        invalid = {
            "request_id": (-1, True, 0x100000000), "mode": (2, False),
            "raw": ("", " ", "n" * 257, "你", "nei7", "nei\0"),
            "text": ("", "妳" * 257, "\ud800", None),
            "reading": ("", "NEI5", "nei", "nei7", "nei5  hou2", "nei5\n", "nei5\thou2",
                        "abcdefghijklmnop1", "nei5 " * 256 + "nei5", None),
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ProtocolError):
                    encode_learning_request(replace(self.request, **{field: value}))
        self.assertFalse(self.memory.exists())

    def test_malformed_length_utf8_magic_and_trailing_data_are_invalid(self):
        payload = encode_learning_request(self.request)
        for end in range(len(payload)):
            with self.subTest(end=end), self.assertRaises(ProtocolError):
                decode_learning_request(payload[:end])
        variants = [payload + b"x", b"NONE" + payload[4:],
                    LEARNING_HEADER.pack(LEARNING_MAGIC, 7, 0, 0xFFFFFFFF, 1, 1),
                    LEARNING_HEADER.pack(LEARNING_MAGIC, 7, 0, 3, 1, 4) + b"nei\xffnei5"]
        for broken in variants:
            with self.subTest(payload=broken), self.assertRaises(ProtocolError):
                decode_learning_request(broken)

    def test_valid_selection_promotes_and_persists_after_engine_restart(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            self.assertEqual(engine.lookup("nei")[0].text, "你")
            response = self.send(engine)
            self.assertEqual((response.request_id, response.status), (self.request.request_id, Status.OK))
            self.assertEqual(engine.lookup("nei")[0].text, "妳")
        self.assertEqual(self.records()[0]["count"], 1)
        self.assertEqual(self.records()[0]["adaptive_weight"], 1.0)
        with Engine(self.database, learning_path=self.memory) as reopened:
            self.assertEqual(reopened.lookup("nei")[0].text, "妳")

    def test_preferences_are_full_input_and_mode_specific(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            self.assertEqual(self.send(engine).status, Status.OK)
            self.assertEqual(engine.lookup("nei")[0].text, "妳")
            self.assertEqual(engine.lookup("nei", mode="jyutping")[0].text, "你")
            self.assertEqual(engine.lookup("lei")[0].text, "你")
            self.assertEqual(engine.lookup("neihou")[0].text, "你好")
            long_request = replace(self.request, raw="neihou", text="妳好", reading="nei5 hou2")
            self.assertEqual(self.send(engine, long_request).status, Status.OK)
            self.assertEqual(engine.lookup("neihou")[0].text, "妳好")
            self.assertEqual(engine.lookup("nei")[0].text, "妳")

    def test_forged_text_reading_or_strict_alias_cannot_create_memory(self):
        forged = (replace(self.request, text="虛構"), replace(self.request, reading="nei4"),
                  replace(self.request, mode=1, raw="lei"))
        with Engine(self.database, learning_path=self.memory) as engine:
            for request in forged:
                with self.subTest(request=request):
                    response = self.send(engine, request)
                    self.assertEqual(response.status, Status.INVALID)
                    self.assertNotIn(request.text, response.error)
                    self.assertNotIn(str(self.memory), response.error)
                    self.assertFalse(self.memory.exists())
            self.assertEqual(engine.lookup("nei")[0].text, "你")

    def test_lookup_requests_never_create_or_update_learning_file(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            request = encode_request(LookupRequest(1, 0, 0, 9, "nei"))
            self.assertEqual(dispatch(engine, request).status, Status.OK)
            self.assertFalse(self.memory.exists())
            self.send(engine)
            previous = self.memory.read_bytes()
            for _ in range(3):
                self.assertEqual(dispatch(engine, request).status, Status.OK)
            self.assertEqual(self.memory.read_bytes(), previous)

    def test_disabled_learning_does_not_silently_acknowledge_save(self):
        with Engine(self.database) as engine:
            self.assertEqual(self.send(engine).status, Status.INTERNAL)
            self.assertEqual(engine.lookup("nei")[0].text, "你")
        self.assertFalse(self.memory.exists())

    def test_corrupt_startup_memory_is_preserved_and_conversion_falls_back(self):
        self.memory.parent.mkdir()
        original = b'{"schema_version":2,"selections":['
        self.memory.write_bytes(original)
        events = []
        with server._conversion_engine(self.database, self.memory, lambda event, **fields: events.append((event, fields))) as engine:
            self.assertIsNone(engine.learning_path)
            self.assertEqual(engine.lookup("nei")[0].text, "你")
            self.assertEqual(self.send(engine).status, Status.INTERNAL)
        self.assertEqual(self.memory.read_bytes(), original)
        self.assertEqual(events, [("learning_unavailable", {"stage": "startup"})])

    def test_broker_default_convention_survives_learning_fallback_and_can_be_disabled(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.executemany("INSERT INTO entries VALUES(?,?,?,?)", [
                ("唔", "m4", "m", 10000), ("唔好", "m4 hou2", "m hou", 1000),
            ])
            db.commit()
        events = []
        log = lambda event, **fields: events.append((event, fields))
        with server._conversion_engine(self.database, self.memory, log) as engine:
            request = LookupRequest(10, 0, 0, 9, "nghou")
            response = dispatch(engine, encode_request(request))
            self.assertEqual((response.candidates[0].text, response.candidates[0].reading), ("唔好", "m4 hou2"))
            selected = LearningRequest(11, 0, "nghou", "唔好", "m4 hou2")
            self.assertEqual(self.send(engine, selected).status, Status.OK)
        self.assertEqual(self.records()[0]["input"], "nghou")
        with server._conversion_engine(self.database, None, log, syllabic_m_as_ng=False) as engine:
            self.assertNotIn("唔好", {row.text for row in engine.lookup("nghou")})
        self.memory.write_bytes(b"invalid synthetic history")
        with server._conversion_engine(self.database, self.memory, log) as engine:
            self.assertIsNone(engine.learning_path)
            self.assertEqual(engine.lookup("nghou")[0].reading, "m4 hou2")
        self.assertEqual(self.memory.read_bytes(), b"invalid synthetic history")

    def test_corruption_during_save_does_not_break_conversion_or_overwrite_file(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            self.assertEqual(self.send(engine).status, Status.OK)
            original = b"malformed memory; preserve evidence"
            self.memory.write_bytes(original)
            self.assertEqual(self.send(engine).status, Status.INVALID)
            self.assertEqual(engine.lookup("nei")[0].text, "妳")
            self.assertEqual(self.memory.read_bytes(), original)

    def test_unwritable_save_keeps_previous_memory_and_conversion(self):
        with Engine(self.database, learning_path=self.memory) as engine:
            self.send(engine)
            previous = self.memory.read_bytes()
            with mock.patch("cantonese_ime.engine.os.replace", side_effect=PermissionError("secret private path")):
                response = self.send(engine, replace(self.request, text="你"))
            self.assertEqual(response.status, Status.INTERNAL)
            self.assertNotIn("secret", response.error)
            self.assertEqual(self.memory.read_bytes(), previous)
            self.assertEqual(engine.lookup("nei")[0].text, "妳")
            self.assertFalse(list(self.memory.parent.glob(".learning-*.json")))

    def test_unreadable_memory_fallback_does_not_hide_a_bad_dictionary(self):
        with self.assertRaises(ValueError):
            # File exists but has no dictionary schema, so both openings fail.
            bad = self.root / "bad.sqlite3"
            with closing(sqlite3.connect(bad)):
                pass
            with server._conversion_engine(bad, self.memory, lambda *_args, **_kwargs: None):
                self.fail("Bad dictionary must not be accepted by learning fallback")


if __name__ == "__main__":
    unittest.main()
