"""Exercise the Mac stdio engine on a real dictionary, without macOS UI claims."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT if (ROOT / "cantonese_ime").is_dir() else ROOT / "engine"
sys.path.insert(0, str(ENGINE_ROOT))
from cantonese_ime.native_protocol import (LookupRequest, LearningRequest, MAX_FRAME_BYTES, Status,
    decode_response, encode_request, encode_learning_request)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class Child:
    def __init__(self, python, bridge, dictionary, pin, memory, output, name):
        self.log = (output / (name + ".stderr.txt")).open("wb")
        self.process = subprocess.Popen([str(python), "-B", "-I", str(bridge), "--dictionary", str(dictionary),
            "--expected-dictionary-sha256", pin, "--learning-file", str(memory)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.log, cwd=output)
        self.responses = queue.Queue()
        self.sequence = 0
        self.timings = []
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read_exact(self, size):
        result = bytearray()
        while len(result) < size:
            part = self.process.stdout.read(size - len(result))
            if not part:
                raise EOFError("The private child closed its response pipe.")
            result.extend(part)
        return bytes(result)

    def read(self):
        try:
            while True:
                size = struct.unpack("<I", self.read_exact(4))[0]
                require(1 <= size <= MAX_FRAME_BYTES, "Bad child response size")
                self.responses.put(decode_response(self.read_exact(size)))
        except Exception as error:
            self.responses.put(error)

    def request(self, request):
        payload = encode_request(request) if isinstance(request, LookupRequest) else encode_learning_request(request)
        started = time.perf_counter()
        self.process.stdin.write(struct.pack("<I", len(payload)) + payload)
        self.process.stdin.flush()
        result = self.responses.get(timeout=45 if not self.timings else 5)
        self.timings.append((time.perf_counter() - started) * 1000)
        if isinstance(result, Exception):
            raise result
        require(result.request_id == request.request_id, "Mismatched child response ID")
        require(result.status == Status.OK, f"Engine returned protocol status {result.status}")
        return result

    def lookup(self, raw, *, mode="forgiving", offset=0):
        self.sequence += 1
        return self.request(LookupRequest(self.sequence, int(mode == "jyutping"), offset, 9, raw))

    def learn(self, raw, candidate):
        self.sequence += 1
        return self.request(LearningRequest(self.sequence, 0, raw, candidate.text, candidate.reading))

    def find(self, raw, text, mode="forgiving"):
        offset = 0
        while True:
            result = self.lookup(raw, mode=mode, offset=offset)
            for index, candidate in enumerate(result.candidates):
                if candidate.text == text:
                    return candidate, offset + index + 1
            if result.next_offset is None:
                return None, None
            require(result.next_offset > offset and result.next_offset <= 10000, "Nonadvancing page")
            offset = result.next_offset

    def close(self):
        self.process.stdin.close()
        code = self.process.wait(timeout=15)
        self.reader.join(timeout=2)
        self.process.stdout.close()
        self.log.close()
        require(code == 0, "Child failed during graceful EOF shutdown")

    def terminate_own_child(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=15)
        self.log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, default=ENGINE_ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--bridge", type=Path, default=(ROOT / "macos/engine/stdio_bridge.py"
        if ENGINE_ROOT == ROOT else ENGINE_ROOT / "stdio_bridge.py"))
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--cases", type=Path, default=ROOT / "macos/tests/engine-cases.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    memory = output / "synthetic-learning.json"
    paths = [args.dictionary.resolve(), args.bridge.resolve(), args.cases.resolve(), ENGINE_ROOT / "cantonese_ime/engine.py",
             ENGINE_ROOT / "cantonese_ime/mappings.py", ENGINE_ROOT / "cantonese_ime/native_protocol.py", Path(__file__).resolve()]
    pins = {str(path): sha(path) for path in paths}
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "passed": False,
              "platform": sys.platform, "native_mac_compile_or_inputmethodkit_proof": False,
              "personal_learning_opened": False, "test_store": str(memory), "source_pins": pins}
    child = None
    try:
        pin = pins[str(args.dictionary.resolve())]
        child = Child(args.python, args.bridge, args.dictionary.resolve(), pin, memory, output, "first")
        selected, rank = child.find("ng", "唔")
        require(selected is not None, "The user's standalone choice is missing")
        child.learn("ng", selected)
        rows = []
        for case in json.loads(args.cases.read_text(encoding="utf-8")):
            candidate, rank = child.find(case["input"], case["text"], case["mode"])
            present = candidate is not None
            passed = present == case["expect_present"]
            rows.append({"id": case["id"], "input": case["input"], "target": case["text"], "mode": case["mode"],
                         "passed": passed, "rank": rank, "reading": candidate.reading if candidate else None})
        report["cases"] = rows
        require(all(row["passed"] for row in rows), "Real-dictionary transport case failed")
        # A full phrase can intentionally prefer a different result from its
        # frequent first character. Its exact preference must remain separate.
        other = next(item for item in child.lookup("ngho").candidates if item.text != "唔好")
        child.learn("ngho", other)
        require(child.lookup("ngho").candidates[0] == other, "Full phrase preference did not take priority")
        require(child.lookup("ng").candidates[0].text == "唔", "Long choice changed the short input")
        report["full_phrase_preference_independent"] = True
        report["first_start_ms"] = child.timings[0]
        report["max_warm_request_ms"] = max(child.timings[1:])
        child.close()
        child = Child(args.python, args.bridge, args.dictionary.resolve(), pin, memory, output, "restarted")
        require(child.lookup("ng").candidates[0].text == "唔", "Short preference did not persist")
        require(child.lookup("ngho").candidates[0] == other, "Full phrase preference did not persist")
        require(any(item.text == "唔係咁" for item in child.lookup("nghaigam").candidates), "Constituent preference did not persist")
        child.close()
        child = None
        report["learning_restart_passed"] = True
        require(all(sha(Path(path)) == value for path, value in pins.items()), "Input changed during checks")
        report["source_hashes_unchanged"] = True
        report["passed"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if child:
            child.terminate_own_child()
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "error": report.get("error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
