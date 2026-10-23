"""Verify a self-contained release with native clients and isolated learning.

No registration, input-language changes, keyboard injection or installed broker
control. Run as the sandbox account, whose session pipe must initially be free.
All control state and learned test selections stay inside the output directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
import subprocess
import time
import traceback


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_package(root: Path, pin: str):
    path = root / "package-manifest.json"
    require(digest(path) == pin, "Release manifest changed")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    require(manifest["kind"] == "Cantonese IME native AMD64 release runtime package", "Not a release package")
    require(manifest["version"] == "1.0.0", "Unexpected release version")
    seen = {"package-manifest.json"}
    for row in manifest["files"]:
        relative = row["path"]
        parts = PurePosixPath(relative)
        require(not parts.is_absolute() and ".." not in parts.parts and ":" not in relative
                and "\\" not in relative and relative not in seen, "Invalid payload path")
        path = (root / relative).resolve()
        require(path.is_relative_to(root) and path.is_file(), "Missing or nonlocal payload")
        require(path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], f"Changed payload: {relative}")
        seen.add(relative)
    require(seen == {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()},
            "Unlisted or missing release files")
    require(digest(root / "data/generated/lexicon.sqlite3") == manifest["dictionary_sha256"], "Dictionary pin differs")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--learning-client", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(os.name == "nt" and struct.calcsize("P") == 8, "Run on Windows x64")
    root, output = args.package.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    local = output / "localappdata"
    local.mkdir()
    env = dict(os.environ, LOCALAPPDATA=str(local))
    # The bundled interpreter is always named explicitly. No PATH/system Python
    # lookup or user-site packages participate in a release-runtime check.
    python = root / "runtime/python/python.exe"
    controller = root / "native/runtime/control.py"
    config = output / "test-runtime-config.json"
    report = {"schema_version": 1, "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "package": str(root), "manifest_sha256": args.manifest_sha256, "passed": False,
              "registry_actions": 0, "keyboard_actions": 0, "installed_state_changed": False,
              "personal_learning_opened": False, "private_test_learning": str(output / "test-learning.json"),
              "commands": [], "inputs": {}}
    active = False

    def command(argv, name, *, timeout=120):
        started = time.perf_counter()
        result = subprocess.run([str(part) for part in argv], cwd=output, env=env,
                                capture_output=True, timeout=timeout, creationflags=0x08000000)
        (output / f"{name}.stdout.txt").write_bytes(result.stdout)
        (output / f"{name}.stderr.txt").write_bytes(result.stderr)
        row = {"name": name, "argv": [str(part) for part in argv], "exit_code": result.returncode,
               "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
        report["commands"].append(row)
        require(result.returncode == 0, f"{name} failed: see preserved output")
        return result

    def control(action, label, *extra):
        result = command([python, "-B", "-I", controller, action, "--config", config, *extra], label)
        return json.loads(result.stdout.decode("utf-8-sig"))

    try:
        manifest = verify_package(root, args.manifest_sha256)
        for path in (args.cases.resolve(), args.client.resolve(), args.learning_client.resolve(), Path(__file__).resolve()):
            report["inputs"][str(path)] = digest(path)
        report["payload_count"] = len(manifest["files"])
        report["dictionary_sha256"] = manifest["dictionary_sha256"]
        report["interpreter"] = json.loads(command([python, "-B", "-I", "-c",
            "import sys,struct,json,sqlite3,ctypes;print(json.dumps({'path':sys.executable,'version':sys.version,'bits':struct.calcsize('P')*8,'sqlite':sqlite3.sqlite_version}))"],
            "bundled-python").stdout)
        require(report["interpreter"]["bits"] == 64 and Path(report["interpreter"]["path"]).resolve() == python,
                "Not the bundled x64 interpreter")
        report["configured"] = control("configure", "configure", "--install-root", root, "--python", python,
                                      "--learning-file", output / "test-learning.json")
        report["verified"] = control("verify", "verify")
        report["before"] = control("status", "status-before")
        require(report["before"]["status"] == "stopped", "Session already has a broker; refusing to touch it")
        # Reproduce the user's short-selection/long-phrase report on the real
        # release dictionary. Only this private test file is opened for learning.
        transfer = command([python, "-B", "-I", "-c", "\n".join((
            "from cantonese_ime import Engine",
            "import json,sys",
            "checks=[('ng','\\u5514'),('ngho','\\u5514\\u597d'),('nghaigam','\\u5514\\u4fc2\\u5481')]",
            "with Engine(sys.argv[1],learning_path=sys.argv[2]) as engine:",
            "    target=next(c for c in engine.lookup('ng',limit=90) if c.text=='\\u5514')",
            "    for _ in range(6): engine.record_selection('ng',target)",
            "with Engine(sys.argv[1],learning_path=sys.argv[2]) as engine:",
            "    rows=[{'input':raw,'target':text,'choices':[c.text for c in engine.lookup(raw)]} for raw,text in checks]",
            "    print(json.dumps(rows,ensure_ascii=True))",
            "    assert all(row['target'] in row['choices'] for row in rows), 'Learned short input did not transfer into phrases'",
        )), root / "data/generated/lexicon.sqlite3", output / "test-learning.json"], "learned-ng-phrases")
        report["learned_ng_phrase_retrieval"] = json.loads(transfer.stdout)
        report["ready"] = control("start", "start")
        active = True
        require(report["ready"]["status"] == "ready", "Test broker not ready")
        pid = report["ready"]["pid"]
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        argv = [args.client, output / "native-smoke.json", pid]
        for row in cases[6:]:
            argv.extend((row["flag"], row["id"], row["input"], row["text"]))
        command(argv, "native-lookup")
        native = json.loads((output / "native-smoke.json").read_text(encoding="utf-8"))
        require(native["passed"] and len(native["cases"]) == len(cases), "Native cohort failed/incomplete")
        require([(row["id"], row["input"], row["expected_text"]) for row in native["cases"]]
                == [(row["id"], row["input"], row["text"]) for row in cases], "Wrong native cohort")
        require(native["expected_broker_pid"] == native["observed_broker_pid_before"]
                == native["observed_broker_pid_after"] == pid, "Wrong native pipe peer")
        report["native_lookup"] = {"passed": True, "cases": len(cases),
                                    "sha256": digest(output / "native-smoke.json")}
        marker = output / "learning-marker.txt"
        command([args.learning_client, "learn", output / "native-learn.json", pid, marker], "native-learn")
        report["stopped_before_restart"] = control("stop", "stop-before-restart")
        active = False
        report["restarted"] = control("start", "restart")
        active = True
        command([args.learning_client, "verify", output / "native-learn-restored.json",
                 report["restarted"]["pid"], marker], "native-learn-restored")
        report["adaptive_learning_persists_across_restart"] = True
        report["checks_passed"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        (output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        if active:
            try:
                report["stopped"] = control("stop", "stop-final")
                require(report["stopped"]["status"] == "stopped", "Test broker did not stop")
            except Exception as error:
                report["cleanup_error"] = str(error)
        try:
            verify_package(root, args.manifest_sha256)
            require(all(digest(Path(path)) == checksum for path, checksum in report["inputs"].items()),
                    "Check inputs changed while running")
            report["payload_and_inputs_unchanged"] = True
        except Exception as error:
            report["recheck_error"] = str(error)
        report["passed"] = bool(report.get("checks_passed") and report.get("payload_and_inputs_unchanged")
                                and not report.get("cleanup_error") and not report.get("recheck_error"))
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write(output / "report.json", report)
    print(json.dumps({"passed": report["passed"], "output": str(output), "error": report.get("error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
