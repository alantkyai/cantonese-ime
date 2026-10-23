"""Pure-Python wire contracts; no broker, Windows API, or production DB use."""

from dataclasses import replace
import random
from types import SimpleNamespace
import unittest

from cantonese_ime.engine import CompositionCapacityError, PaginationCapacityError
from cantonese_ime.native_protocol import (
    MAGIC, MAX_CANDIDATE_UTF16_UNITS, MAX_ERROR_BYTES, MAX_FRAME_BYTES,
    REQUEST_HEADER, RESPONSE_HEADER, U32, LookupRequest, LookupResponse,
    ProtocolError, Status, WireCandidate, decode_frame_length, decode_request,
    decode_response, dispatch, encode_request, encode_response, frame,
)


class FakeEngine:
    """Only the dispatch dependency; no file handles, IPC, or learning state."""

    def __init__(self, page=None, error=None):
        self.page = page or SimpleNamespace(
            candidates=(WireCandidate("你好𠮷", "nei5 hou2 gat1"),),
            next_offset=None, completion_truncated=False,
        )
        self.error = error
        self.calls = []

    def lookup_page(self, raw, **options):
        self.calls.append((raw, options))
        if self.error is not None:
            raise self.error
        return self.page

    def record_selection(self, *args, **kwargs):
        raise AssertionError("Native lookup must never enable learning.")


class NativeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.request = LookupRequest(0x01020304, 1, 90, 9, "Nei'Ho")
        self.response = LookupResponse(
            0x01020304, Status.OK, 9, True,
            (WireCandidate("你", "nei5"), WireCandidate("𠮷", "gat1")),
        )

    def response_header(self, **changes):
        fields = dict(magic=MAGIC, request_id=7, status=0, next_offset=-1,
                      truncated=0, count=0, error_length=0)
        fields.update(changes)
        return RESPONSE_HEADER.pack(*fields.values())

    def test_request_exact_little_endian_layout_and_frame(self):
        expected = bytes.fromhex(
            "494d4531 04030201 01000000 5a000000 09000000 06000000"
        ) + b"Nei'Ho"
        self.assertEqual(REQUEST_HEADER.size, 24)
        self.assertEqual(encode_request(self.request), expected)
        self.assertEqual(decode_request(expected), self.request)
        self.assertEqual(frame(expected), b"\x1e\0\0\0" + expected)

    def test_response_exact_unicode_byte_lengths_and_sentinel(self):
        expected = bytes.fromhex(
            "494d4531 04030201 00000000 09000000 01000000 02000000 00000000 "
            "03000000 e4bda0 04000000 6e656935 "
            "04000000 f0a0aeb7 04000000 67617431"
        )
        self.assertEqual(RESPONSE_HEADER.size, 28)
        self.assertEqual(encode_response(self.response), expected)
        self.assertEqual(decode_response(expected, expected_request_id=0x01020304), self.response)
        terminal = encode_response(LookupResponse(7, Status.OK))
        self.assertEqual(terminal[12:16], b"\xff\xff\xff\xff")
        self.assertIsNone(decode_response(terminal).next_offset)

    def test_request_numeric_and_input_boundaries_round_trip(self):
        for raw in ("", "A" * 64, "A" * 256, "nei5 hou2", "ng'o5", "  '"):
            for mode in (0, 1):
                for request_id in (0, 0xFFFFFFFF):
                    request = LookupRequest(request_id, mode, 10000, 1, raw)
                    with self.subTest(request=request):
                        self.assertEqual(decode_request(encode_request(request)), request)

    def test_invalid_request_object_fields_are_protocol_errors(self):
        invalid = {
            "request_id": (-1, 0x100000000, True, 1.0, "1"),
            "mode": (-1, 2, False, 0.0, "0"),
            "offset": (-1, 10001, True, 1.0, None),
            "limit": (0, 10, True, 1.0, None),
            "raw": (None, b"nei", "a" * 257, "你", "é", "nei0", "nei7", "nei9", "nei\n", "nei\0", "a\t"),
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ProtocolError):
                    encode_request(replace(self.request, **{field: value}))
        with self.assertRaises(ProtocolError):
            encode_request(None)

    def test_request_wire_header_corruption(self):
        fields = [MAGIC, 7, 0, 0, 9, 3]
        for index, value in ((0, 0), (2, 2), (3, 10001), (4, 0), (4, 10), (5, 0), (5, 4), (5, 0xFFFFFFFF)):
            changed = fields.copy()
            changed[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ProtocolError):
                decode_request(REQUEST_HEADER.pack(*changed) + b"nei")
        for raw in (b"\xff", b"\xc0\xaf", b"\xed\xa0\x80", b"\xf4\x90\x80\x80", "你".encode()):
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                decode_request(REQUEST_HEADER.pack(MAGIC, 7, 0, 0, 9, len(raw)) + raw)

    def test_request_truncation_and_trailing_bytes(self):
        payload = encode_request(self.request)
        for size in range(len(payload)):
            with self.subTest(size=size), self.assertRaises(ProtocolError):
                decode_request(payload[:size])
        with self.assertRaises(ProtocolError):
            decode_request(payload + b"x")

    def test_frame_length_boundaries(self):
        for length in (1, MAX_FRAME_BYTES):
            payload = b"x" * length
            encoded = frame(payload)
            self.assertEqual(decode_frame_length(encoded[:4]), length)
            self.assertEqual(encoded[4:], payload)
        for payload in (b"", b"x" * (MAX_FRAME_BYTES + 1)):
            with self.subTest(size=len(payload)), self.assertRaises(ProtocolError):
                frame(payload)
        for header in (b"", b"\0" * 3, b"\0" * 5, U32.pack(0), U32.pack(MAX_FRAME_BYTES + 1)):
            with self.subTest(header=header), self.assertRaises(ProtocolError):
                decode_frame_length(header)

    def test_nonbyte_payloads_are_rejected_and_bytearrays_work(self):
        for value in (None, "bytes", 42, [1, 2, 3], memoryview(b"abc")):
            for decoder in (decode_request, decode_response, decode_frame_length, frame):
                with self.subTest(value=type(value).__name__, decoder=decoder.__name__), self.assertRaises(ProtocolError):
                    decoder(value)
        self.assertEqual(decode_request(bytearray(encode_request(self.request))), self.request)
        self.assertEqual(decode_response(bytearray(encode_response(self.response))), self.response)
        self.assertEqual(decode_frame_length(bytearray(U32.pack(7))), 7)
        self.assertEqual(frame(bytearray(b"abc")), U32.pack(3) + b"abc")

    def test_response_rejects_stale_ids_and_invalid_expected_id(self):
        payload = encode_response(self.response)
        for request_id in (0, 0xFFFFFFFF, 0x01020303):
            with self.subTest(request_id=request_id), self.assertRaisesRegex(ProtocolError, "mismatched"):
                decode_response(payload, expected_request_id=request_id)
        id_one = encode_response(LookupResponse(1, Status.OK))
        for request_id in (True, 1.0, -1, 0x100000000, "1"):
            with self.subTest(request_id=request_id), self.assertRaises(ProtocolError):
                decode_response(id_one, expected_request_id=request_id)

    def test_response_error_unicode_and_all_statuses(self):
        for status in (Status.INVALID, Status.CAPACITY, Status.INTERNAL):
            response = LookupResponse(7, status, error="輸入未完成𠮷")
            with self.subTest(status=status):
                self.assertEqual(decode_response(encode_response(response)), response)
        for candidates in ((), (WireCandidate("廣東話", "gwong2 dung1 waa2"),) * 9):
            response = LookupResponse(0xFFFFFFFF, Status.OK, candidates=candidates)
            self.assertEqual(decode_response(encode_response(response)), response)

    def test_response_validation_covers_python_types_and_bounds(self):
        invalid = {
            "request_id": (-1, 0x100000000, True, 1.0),
            "status": (-1, 4, True, 0.0, "0", None),
            "next_offset": (-2, 10001, True, 1.0),
            "completion_truncated": (0, 1, None, "yes"),
            "candidates": (None, 1, "x", (WireCandidate("字", "zi6"),) * 10, (None,), (object(),)),
            "error": (None, 1, b"error", "\ud800", "x" * (MAX_ERROR_BYTES + 1)),
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=type(value).__name__), self.assertRaises(ProtocolError):
                    encode_response(replace(self.response, **{field: value}))
        with self.assertRaises(ProtocolError):
            encode_response(None)

    def test_candidate_text_validation_matches_native_utf16_units(self):
        for text in ("字" * MAX_CANDIDATE_UTF16_UNITS, "𠮷" * (MAX_CANDIDATE_UTF16_UNITS // 2)):
            response = LookupResponse(1, Status.OK, candidates=(WireCandidate(text, "zi6"),))
            self.assertEqual(decode_response(encode_response(response)), response)
        for candidate in (
            WireCandidate("", "zi6"), WireCandidate(None, "zi6"),
            WireCandidate("字", None), WireCandidate("\ud800", "zi6"), WireCandidate("字", "\ud800"),
            WireCandidate("字" * (MAX_CANDIDATE_UTF16_UNITS + 1), "zi6"),
            WireCandidate("𠮷" * (MAX_CANDIDATE_UTF16_UNITS // 2 + 1), "zi6"),
            WireCandidate("字", "a" * (MAX_CANDIDATE_UTF16_UNITS + 1)),
        ):
            with self.subTest(text_type=type(candidate.text).__name__), self.assertRaises(ProtocolError):
                encode_response(LookupResponse(1, Status.OK, candidates=(candidate,)))
        # The C++ consumer permits an empty reading; preserve that wire contract.
        response = LookupResponse(1, Status.OK, candidates=(WireCandidate("字", ""),))
        self.assertEqual(decode_response(encode_response(response)), response)

    def test_error_messages_use_byte_not_character_bound(self):
        for error in ("x" * MAX_ERROR_BYTES, "漢" * (MAX_ERROR_BYTES // 3)):
            response = LookupResponse(7, Status.CAPACITY, error=error)
            self.assertEqual(decode_response(encode_response(response)), response)
        with self.assertRaises(ProtocolError):
            encode_response(LookupResponse(7, Status.CAPACITY, error="漢" * (MAX_ERROR_BYTES // 3 + 1)))

    def test_error_pages_cannot_publish_candidates_or_continuation(self):
        for status in (Status.INVALID, Status.CAPACITY, Status.INTERNAL):
            for changes in ({"candidates": (WireCandidate("字", "zi6"),)}, {"next_offset": 9}, {"completion_truncated": True}):
                with self.subTest(status=status, changes=changes), self.assertRaises(ProtocolError):
                    encode_response(LookupResponse(7, status, **changes))
        with self.assertRaises(ProtocolError):
            encode_response(LookupResponse(7, Status.OK, next_offset=9))

    def test_response_header_corruption(self):
        for changes in ({"magic": 0}, {"status": 4}, {"next_offset": -2},
                        {"next_offset": 10001}, {"truncated": 2}, {"count": 10},
                        {"error_length": MAX_ERROR_BYTES + 1}, {"error_length": 1}):
            with self.subTest(changes=changes), self.assertRaises(ProtocolError):
                decode_response(self.response_header(**changes))
        for changes in ({"status": 1, "truncated": 1}, {"next_offset": 1}):
            with self.subTest(changes=changes), self.assertRaises(ProtocolError):
                decode_response(self.response_header(**changes))

    def test_response_truncation_and_trailing_bytes(self):
        payload = encode_response(self.response)
        for size in range(len(payload)):
            with self.subTest(size=size), self.assertRaises(ProtocolError):
                decode_response(payload[:size])
        with self.assertRaises(ProtocolError):
            decode_response(payload + b"x")

    def test_response_text_length_and_utf8_corruption(self):
        cases = (
            self.response_header(count=1),  # missing field length
            self.response_header(count=1) + b"\0\0",  # partial length
            self.response_header(count=1) + U32.pack(0xFFFFFFFF),
            self.response_header(count=1) + U32.pack(0) + U32.pack(0),  # empty candidate
            self.response_header(count=1) + U32.pack(1) + b"x" + U32.pack(5) + b"y",
            self.response_header(status=1, count=1) + U32.pack(1) + b"x" + U32.pack(0),
        )
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ProtocolError):
                decode_response(payload)
        for bad in (b"\xff", b"\xc0\xaf", b"\xed\xa0\x80", b"\xf4\x90\x80\x80"):
            payloads = (
                self.response_header(status=1, error_length=len(bad)) + bad,
                self.response_header(count=1) + U32.pack(len(bad)) + bad + U32.pack(0),
                self.response_header(count=1) + U32.pack(1) + b"x" + U32.pack(len(bad)) + bad,
            )
            for payload in payloads:
                with self.subTest(bad=bad), self.assertRaises(ProtocolError):
                    decode_response(payload)

    def test_large_incoming_payloads_are_rejected(self):
        payload = b"x" * (MAX_FRAME_BYTES + 1)
        for decoder in (decode_request, decode_response):
            with self.subTest(decoder=decoder.__name__), self.assertRaises(ProtocolError):
                decoder(payload)

    def test_dispatch_forwards_modes_raw_case_and_paging_without_learning(self):
        for mode, name in ((0, "forgiving"), (1, "jyutping")):
            engine = FakeEngine(SimpleNamespace(
                candidates=(WireCandidate("你好𠮷", "nei5 hou2 gat1"),),
                next_offset=91, completion_truncated=True,
            ))
            request = replace(self.request, mode=mode, limit=1)
            response = dispatch(engine, encode_request(request))
            with self.subTest(mode=mode):
                self.assertEqual(response.status, Status.OK)
                self.assertEqual(response.request_id, request.request_id)
                self.assertEqual(response.next_offset, 91)
                self.assertTrue(response.completion_truncated)
                self.assertEqual(response.candidates[0].text, "你好𠮷")
                self.assertEqual(engine.calls, [("Nei'Ho", {"offset": 90, "page_size": 1, "mode": name})])
                self.assertEqual(decode_response(encode_response(response)), response)

    def test_dispatch_invalid_payload_never_calls_backend_and_recovers_id(self):
        payload = encode_request(self.request)
        for malformed, request_id in ((b"bad", 0), (None, 0), (payload + b"x", self.request.request_id),
                                      (b"nope" + payload[4:], self.request.request_id)):
            engine = FakeEngine()
            response = dispatch(engine, malformed)
            with self.subTest(request_id=request_id):
                self.assertEqual(response.status, Status.INVALID)
                self.assertEqual(response.request_id, request_id)
                self.assertEqual(engine.calls, [])
                self.assertEqual(response.candidates, ())
                self.assertIsNone(response.next_offset)
                self.assertEqual(decode_response(encode_response(response)), response)

    def test_dispatch_capacity_and_validation_errors_are_distinct(self):
        for error, status in ((PaginationCapacityError("Refine the input."), Status.CAPACITY),
                              (CompositionCapacityError("Composition work limit."), Status.CAPACITY),
                              (ValueError("Invalid mode."), Status.INVALID)):
            response = dispatch(FakeEngine(error=error), encode_request(self.request))
            with self.subTest(error=type(error).__name__):
                self.assertEqual(response.status, status)
                self.assertEqual(response.error, str(error))
                self.assertEqual(response.candidates, ())
                self.assertFalse(response.completion_truncated)
                self.assertEqual(decode_response(encode_response(response)), response)

    def test_dispatch_bounds_multibyte_and_invalid_unicode_exception_messages(self):
        for error in (ValueError("漢" * 5000), PaginationCapacityError("漢" * 5000),
                      CompositionCapacityError("bad\ud800message")):
            response = dispatch(FakeEngine(error=error), encode_request(self.request))
            with self.subTest(error=type(error).__name__):
                self.assertLessEqual(len(response.error.encode("utf-8")), MAX_ERROR_BYTES)
                self.assertNotEqual(response.status, Status.OK)
                self.assertEqual(decode_response(encode_response(response)), response)

    def test_dispatch_internal_errors_do_not_expose_paths_or_tracebacks(self):
        response = dispatch(FakeEngine(error=RuntimeError("secret C:\\private\\dictionary.db Traceback")),
                            encode_request(self.request))
        self.assertEqual(response.status, Status.INTERNAL)
        self.assertNotIn("private", response.error)
        self.assertNotIn("Traceback", response.error)
        self.assertEqual(decode_response(encode_response(response)), response)

    def test_dispatch_malformed_backend_pages_become_encodable_internal_errors(self):
        pages = (
            SimpleNamespace(candidates=(WireCandidate("", "zi6"),), next_offset=None, completion_truncated=False),
            SimpleNamespace(candidates=(WireCandidate("字", "zi6"),), next_offset=10001, completion_truncated=False),
            SimpleNamespace(candidates=(WireCandidate("字", "zi6"),), next_offset=92, completion_truncated=False),
            SimpleNamespace(candidates=(WireCandidate("字", "zi6"),) * 10, next_offset=None, completion_truncated=False),
            SimpleNamespace(candidates=(), next_offset=9, completion_truncated=False),
            SimpleNamespace(candidates=(WireCandidate("字", "zi6"),), next_offset=None, completion_truncated=1),
            SimpleNamespace(candidates=(object(),), next_offset=None, completion_truncated=False),
        )
        for page in pages:
            with self.subTest(page=page):
                response = dispatch(FakeEngine(page), encode_request(self.request))
                self.assertEqual(response.status, Status.INTERNAL)
                self.assertEqual(response.candidates, ())
                self.assertEqual(decode_response(encode_response(response)), response)

    def test_dispatch_does_not_exceed_requested_page_size(self):
        page = SimpleNamespace(candidates=(WireCandidate("字", "zi6"),) * 2,
                               next_offset=None, completion_truncated=False)
        request = replace(self.request, limit=1)
        response = dispatch(FakeEngine(page), encode_request(request))
        self.assertEqual(response.status, Status.INTERNAL)
        self.assertEqual(decode_response(encode_response(response)), response)

    def test_deterministic_small_payload_fuzz_has_only_protocol_failures_or_round_trips(self):
        generator = random.Random(0x494D4531)
        payloads = [generator.randbytes(generator.randrange(160)) for _ in range(500)]
        for valid in (encode_request(self.request), encode_response(self.response)):
            for _ in range(250):
                mutated = bytearray(valid)
                for _ in range(generator.randrange(1, 5)):
                    mutated[generator.randrange(len(mutated))] = generator.randrange(256)
                payloads.append(bytes(mutated))
        for index, payload in enumerate(payloads):
            for decoder, encoder in ((decode_request, encode_request), (decode_response, encode_response)):
                with self.subTest(index=index, decoder=decoder.__name__):
                    try:
                        decoded = decoder(payload)
                    except ProtocolError:
                        pass
                    else:
                        self.assertEqual(encoder(decoded), payload)
            engine = FakeEngine()
            response = dispatch(engine, payload)
            self.assertEqual(decode_response(encode_response(response)), response)
            self.assertEqual(response.status, Status.OK if engine.calls else Status.INVALID)


if __name__ == "__main__":
    unittest.main()
