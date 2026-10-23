#!/usr/bin/env python3
"""Compile/run Swift core tests on the build Mac without activating an IME."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

MACOS = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Native Swift checks require a Mac and the macOS SDK.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [MACOS / "Sources" / name for name in ("WireProtocol.swift", "CompositionState.swift", "MainThread.swift")]
    sources.append(MACOS / "tests/NativeCoreTests.swift")
    pins = {str(path): sha(path) for path in sources}
    binary = output / "NativeCoreTests"
    result = subprocess.run(["/usr/bin/xcrun", "--sdk", "macosx", "swiftc", "-swift-version", "5", "-O",
        "-module-name", "CantoneseIMECoreTests", *map(str, sources), "-o", str(binary)], capture_output=True, text=True)
    (output / "compile.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "compile.stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("Swift core tests did not compile; inspect the retained compiler output.")
    tested = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
    (output / "tests.stdout.json").write_text(tested.stdout, encoding="utf-8")
    (output / "tests.stderr.txt").write_text(tested.stderr, encoding="utf-8")
    if tested.returncode:
        raise RuntimeError("A native Swift core test failed.")
    summary = json.loads(tested.stdout)
    if summary.get("passed") is not True and summary.get("status") != "passed":
        raise RuntimeError("Swift tests did not report a passing result.")
    if any(sha(Path(path)) != checksum for path, checksum in pins.items()):
        raise RuntimeError("A Swift test input changed while the tests ran.")
    report = {"passed": True, "platform": "darwin", "host_architecture": platform.machine(),
        "native_core_compiled": True, "inputmethodkit_ui_tested": False, "sources_sha256": pins,
        "test_binary_sha256": sha(binary), "summary": summary}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
