"""Private InputMethodKit child process using the shared bounded IME1 wire.

Only its parent owns stdin/stdout. No socket, global broker, registration, input
injection, network access or typed-text logging is used by this transport.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import os
from pathlib import Path
import re
import struct
import sys
from typing import BinaryIO

# In an installed app this directory contains the sibling engine package.
# The second root supports running this source directly in the project.
HERE = Path(__file__).resolve().parent
for candidate in (HERE, HERE.parents[1]):
    if (candidate / "cantonese_ime/engine.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from cantonese_ime import Engine
from cantonese_ime.native_protocol import MAX_FRAME_BYTES, dispatch, encode_response

U32 = struct.Struct("<I")


class FramingError(ValueError):
    pass


class EngineCapabilityError(ValueError):
    pass


def read_exact(stream: BinaryIO, length: int, *, allow_eof: bool = False) -> bytes | None:
    result = bytearray()
    while len(result) < length:
        chunk = stream.read(length - len(result))
        if not chunk:
            if allow_eof and not result:
                return None
            raise FramingError("Incomplete input frame.")
        result.extend(chunk)
    return bytes(result)


def serve(engine: Engine, source: BinaryIO, destination: BinaryIO) -> int:
    """Dispatch complete bounded frames; clean boundary EOF shuts down normally."""
    requests = 0
    while True:
        header = read_exact(source, U32.size, allow_eof=True)
        if header is None:
            return requests
        length = U32.unpack(header)[0]
        if not 1 <= length <= MAX_FRAME_BYTES:
            raise FramingError("Input frame is outside the protocol size limit.")
        body = read_exact(source, length)
        response = encode_response(dispatch(engine, body))
        destination.write(U32.pack(len(response)))
        destination.write(response)
        destination.flush()
        requests += 1


def default_learning_file() -> Path:
    if sys.platform != "darwin":
        raise ValueError("Supply an explicit isolated learning file or disable learning outside macOS.")
    return Path.home() / "Library/Application Support/CantoneseIME/learning.json"


def supports_habitual_ng() -> bool:
    """Negotiate an explicit option; legacy **kwargs alone is not support."""
    try:
        parameter = inspect.signature(Engine).parameters.get("syllabic_m_as_ng")
    except (TypeError, ValueError):
        return False
    return parameter is not None and parameter.kind != inspect.Parameter.POSITIONAL_ONLY


def habitual_ng_status(engine: Engine) -> str:
    enabled = getattr(engine, "syllabic_m_as_ng", None)
    return "on" if enabled is True else "off" if enabled is False else "unavailable"


def open_engine(dictionary: Path, learning: Path | None, *, syllabic_m_as_ng: bool | None = None) -> Engine:
    if syllabic_m_as_ng is not None and not isinstance(syllabic_m_as_ng, bool):
        raise ValueError("syllabic_m_as_ng must be a boolean or None.")
    supported = supports_habitual_ng()
    if syllabic_m_as_ng is True and not supported:
        raise EngineCapabilityError("The bundled engine does not support the requested ng-for-m input convention.")
    options = ({"syllabic_m_as_ng": syllabic_m_as_ng is not False} if supported else {})
    try:
        return Engine(dictionary, learning_path=learning, **options)
    except ValueError as error:
        # Preserve the original file; never silently reset private selections.
        # Dictionary/schema errors must still stop startup, not masquerade as a
        # harmless personal-memory problem.
        if learning is None or not str(error).startswith("Cannot read learning data:"):
            raise
        sys.stderr.write("Cantonese IME: saved learning is unavailable; conversion remains enabled.\n")
        sys.stderr.flush()
        return Engine(dictionary, **options)


def verify_dictionary(dictionary: Path, expected: str | None):
    if expected is None:
        return
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Expected a lowercase SHA-256 dictionary pin.")
    value = hashlib.sha256()
    with dictionary.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    if value.hexdigest() != expected:
        raise ValueError("The bundled dictionary differs from its build pin.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, required=True)
    parser.add_argument("--expected-dictionary-sha256")
    parser.add_argument("--syllabic-m-as-ng", action=argparse.BooleanOptionalAction, default=None,
                        help="Accept whole-syllable ng for m in forgiving input (default: on when supported by the bundled engine).")
    memory = parser.add_mutually_exclusive_group()
    memory.add_argument("--learning-file", type=Path)
    memory.add_argument("--disable-learning", action="store_true")
    args = parser.parse_args(argv)
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    learning = None if args.disable_learning else (args.learning_file or default_learning_file())
    if learning is not None:
        learning = learning.expanduser().resolve()
        if learning == args.dictionary.expanduser().resolve():
            raise ValueError("Personal learning must be separate from the dictionary.")
    verify_dictionary(args.dictionary, args.expected_dictionary_sha256)
    with open_engine(args.dictionary, learning, syllabic_m_as_ng=args.syllabic_m_as_ng) as engine:
        sys.stderr.write("Cantonese IME: local engine ready; learning=" + ("on" if engine.learning_path else "off")
                         + "; ng-for-m=" + habitual_ng_status(engine) + ".\n")
        sys.stderr.flush()
        serve(engine, sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
    except EngineCapabilityError:
        # Fixed capability diagnostic, with no request or private path data.
        sys.stderr.write("Cantonese IME: requested ng-for-m input is unavailable in the bundled engine.\n")
        raise SystemExit(2)
    except (Exception, KeyboardInterrupt):
        # The parent gets EOF/exit status; logs contain no input, candidate,
        # local filesystem path, exception payload or document contents.
        sys.stderr.write("Cantonese IME: local engine stopped before completing a request.\n")
        raise SystemExit(2)
