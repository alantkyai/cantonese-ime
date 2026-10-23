"""Build the offline, self-contained Windows x64 Cantonese IME installer.

The compiler is unpacked only into .local/release-tools in official portable
mode. This command never runs the generated installer or registers an IME.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from package_native import _InputPins, _candidate_font_inputs, amd64, digest, stage


def validate_version(version: str) -> str:
    if (not isinstance(version, str)
            or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version)
            or any(int(part) > 65535 for part in version.split("."))):
        raise ValueError("A stable Windows release requires three numeric version components from 0 to 65535, without leading zeros.")
    return version


def project_version() -> str:
    return validate_version(tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])


def default_output() -> Path:
    return ROOT / "dist" / ("CantoneseIME-" + project_version() + "-x64")


def write_json(path: Path, value: dict):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def download(path: Path, source: dict, *, allow_fetch: bool):
    if not path.is_file():
        if not allow_fetch:
            raise ValueError(f"Missing {path.name}; rerun with --fetch-tools to download the pinned official dependency.")
        temporary = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(source["url"], temporary)
        if digest(temporary) != source["sha256"]:
            temporary.unlink()
            raise ValueError("Downloaded dependency differs from its official SHA256: " + path.name)
        temporary.replace(path)
    if digest(path) != source["sha256"]:
        raise ValueError("Cached dependency differs from its official SHA256: " + path.name)


def verify_authenticode(path: Path):
    """Verify the already SHA256-pinned official file with Windows trust APIs."""
    class FileInfo(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("path", w.LPCWSTR), ("file", w.HANDLE), ("subject", ctypes.c_void_p)]
    class TrustData(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("policy", ctypes.c_void_p), ("sip", ctypes.c_void_p),
                    ("ui", w.DWORD), ("revocation", w.DWORD), ("choice", w.DWORD),
                    ("file", ctypes.POINTER(FileInfo)), ("state_action", w.DWORD), ("state", w.HANDLE),
                    ("url", w.LPCWSTR), ("flags", w.DWORD), ("context", w.DWORD), ("settings", ctypes.c_void_p)]
    file = FileInfo(ctypes.sizeof(FileInfo), str(path), None, None)
    data = TrustData()
    data.size, data.ui, data.choice, data.file = ctypes.sizeof(TrustData), 2, 1, ctypes.pointer(file)
    data.flags = 0x1000  # Cache-only URL retrieval; no online build dependency.
    action = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID("00aac56b-cd44-11d0-8cc2-00c04fc295ee").bytes_le)
    trust = ctypes.WinDLL("wintrust")
    trust.WinVerifyTrust.argtypes = [w.HWND, ctypes.c_void_p, ctypes.POINTER(TrustData)]
    trust.WinVerifyTrust.restype = ctypes.c_long
    result = trust.WinVerifyTrust(w.HWND(-1), ctypes.byref(action), ctypes.byref(data))
    if result:
        raise ValueError(f"The official installer compiler's Authenticode signature did not verify: 0x{result & 0xffffffff:08x}")


def tools(allow_fetch: bool) -> tuple[Path, Path, dict]:
    lock = json.loads((ROOT / "installer/dependencies.lock.json").read_text(encoding="utf-8"))
    local = ROOT / ".local/release-tools"
    cache = local / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    python_zip = cache / Path(lock["python"]["url"]).name
    inno_setup = cache / Path(lock["inno_setup"]["url"]).name
    for path, source in ((python_zip, lock["python"]), (inno_setup, lock["inno_setup"])):
        download(path, source, allow_fetch=allow_fetch)
    python = local / ("python-" + lock["python"]["version"])
    expected = {}
    with zipfile.ZipFile(python_zip) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            if Path(item.filename).is_absolute() or ".." in Path(item.filename).parts:
                raise ValueError("Unexpected upstream runtime archive path.")
            payload = archive.read(item)
            if item.filename == "python313._pth":
                payload = lock["python"]["pth_contents"].encode("ascii")
            expected[item.filename] = hashlib.sha256(payload).hexdigest()
            target = python / item.filename
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            elif digest(target) != expected[item.filename]:
                raise ValueError("The private runtime staging input changed: " + item.filename)
    actual = {path.relative_to(python).as_posix() for path in python.rglob("*") if path.is_file()}
    if actual != set(expected):
        raise ValueError("The private runtime staging tree has unexpected files.")
    # Extract a fresh portable compiler from the pinned signed installer on
    # every build. An unverified old compiler cache cannot bless new releases.
    compiler = local / ("inno-" + lock["inno_setup"]["version"] + "-build-" + uuid.uuid4().hex) / "ISCC.exe"
    if not compiler.exists():
        verify_authenticode(inno_setup)
        subprocess.run([str(inno_setup), "/PORTABLE=1", "/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES",
                        "/NORESTART", "/NOICONS", "/DIR=" + str(compiler.parent)], check=True, timeout=120)
    if not amd64(compiler) or not amd64(python / "python.exe"):
        raise ValueError("The release requires native AMD64 build tools and runtime.")
    return python, compiler, lock


def verify_payload(payload: Path, manifest: dict):
    records = {record["path"]: record for record in manifest["files"]}
    actual = {path.relative_to(payload).as_posix() for path in payload.rglob("*") if path.is_file()}
    if actual != set(records) | {"package-manifest.json"}:
        raise ValueError("Release payload has an unexpected or missing file.")
    for relative, item in records.items():
        path = payload / relative
        if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
            raise ValueError("Release payload changed: " + relative)


def build(output: Path, *, allow_fetch: bool, compile_setup: bool) -> dict:
    if output.exists():
        raise ValueError("Release output already exists; choose a new directory.")
    build_sources = ["tools/build_release.py", "tools/package_native.py", "installer/CantoneseIME.iss",
                     "installer/dependencies.lock.json", "pyproject.toml", "native/tsf/icons/cantonese.ico",
                     "installer/lifecycle.py", "installer/Set-UserInputSource.ps1", "installer/GETTING_STARTED.txt", "installer/RELEASE_NOTICES.txt"]
    build_source_pins = {name: digest(ROOT / name) for name in build_sources}
    font_pins = _InputPins()
    font_inputs = _candidate_font_inputs(pins=font_pins)
    font_source_pins = {name: font_pins.expected[path.resolve()] for name, path in font_inputs.items()}
    version = project_version()
    python, compiler, lock = tools(allow_fetch)
    compiler_files = {path.relative_to(compiler.parent).as_posix(): digest(path)
                      for path in compiler.parent.rglob("*") if path.is_file()}
    actual_version = subprocess.run([str(compiler), "--version"], check=True, capture_output=True,
                                    text=True, timeout=20).stdout.strip()
    if lock["inno_setup"]["version"] not in actual_version:
        raise ValueError("The fresh compiler reports an unexpected version.")
    output.mkdir(parents=True)
    payload = output / "package"
    manifest = stage(payload, python / "python.exe", bundled_runtime=python, release=True)
    staged_files = {item["path"]: item for item in manifest["files"]}
    if any(staged_files.get(name, {}).get("sha256") != expected
           for name, expected in font_source_pins.items()):
        raise ValueError("Staged candidate font assets differ from the original release input pins.")
    manifest["version"] = version
    manifest["supported_platform"] = "Windows 10/11 native AMD64; x64 desktop text applications"
    manifest["release_channel"] = "stable"
    manifest["signed"] = False
    manifest["runtime_source"] = lock["python"]
    additional = {
        "installer/lifecycle.py": ROOT / "installer/lifecycle.py",
        "installer/Set-UserInputSource.ps1": ROOT / "installer/Set-UserInputSource.ps1",
        "GETTING_STARTED.txt": ROOT / "installer/GETTING_STARTED.txt",
        "RELEASE_NOTICES.txt": ROOT / "installer/RELEASE_NOTICES.txt",
        "licenses/INNO-SETUP-LICENSE.txt": compiler.parent / "license.txt",
    }
    source_pins = {name: digest(source) for name, source in additional.items()}
    for name, source in additional.items():
        target = payload / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(target) != source_pins[name] or digest(source) != source_pins[name]:
            raise ValueError("A release support input changed while staging.")
        manifest["files"].append({"path": name, "bytes": target.stat().st_size, "sha256": source_pins[name]})
    manifest["files"].sort(key=lambda item: item["path"])
    manifest["total_payload_bytes"] = sum(item["bytes"] for item in manifest["files"])
    write_json(payload / "package-manifest.json", manifest)
    manifest_hash = digest(payload / "package-manifest.json")
    verify_payload(payload, manifest)
    report = {"schema_version": 1, "version": version, "architecture": "AMD64", "signed": False,
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "package_manifest_sha256": manifest_hash,
              "payload_file_count": len(manifest["files"]), "payload_bytes": manifest["total_payload_bytes"],
              "compiler": {"version": lock["inno_setup"]["version"], "reported_version": actual_version,
                           "sha256": digest(compiler), "fresh_portable_extraction": True,
                           "files_sha256": compiler_files}, "build_sources_sha256": build_source_pins,
              "candidate_font_sources_sha256": font_source_pins,
              "private_python": lock["python"], "source_pins": source_pins,
              "installation_performed": False}
    if compile_setup:
        icon = ROOT / "native/tsf/icons/cantonese.ico"
        command = [str(compiler), "/Qp", "/DPayloadRoot=" + str(payload), "/DOutputRoot=" + str(output),
                   "/DReleaseVersion=" + version, "/DManifestSha256=" + manifest_hash,
                   "/DSetupIconFile=" + str(icon), str(ROOT / "installer/CantoneseIME.iss")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        (output / "compiler.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("Inno Setup compilation failed; inspect " + str(output / "compiler.log"))
        setup = output / f"CantoneseIME-{version}-windows-x64-setup.exe"
        if not setup.is_file() or not amd64(setup):
            raise ValueError("The setup executable is missing or is not AMD64.")
        report["setup"] = {"filename": setup.name, "bytes": setup.stat().st_size, "sha256": digest(setup)}
        (output / "SHA256SUMS.txt").write_text(report["setup"]["sha256"] + "  " + setup.name + "\n" +
            manifest_hash + "  package/package-manifest.json\n", encoding="ascii")
    verify_payload(payload, manifest)
    if digest(payload / "package-manifest.json") != manifest_hash:
        raise ValueError("The package manifest changed during compilation.")
    if any(digest(ROOT / name) != pin for name, pin in build_source_pins.items()):
        raise ValueError("A release build source changed during compilation; choose a fresh output and rebuild.")
    font_pins.verify()
    if any(digest(compiler.parent / name) != pin for name, pin in compiler_files.items()):
        raise ValueError("An extracted compiler file changed during compilation.")
    write_json(output / "release-build.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output())
    parser.add_argument("--fetch-tools", action="store_true")
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve(), allow_fetch=args.fetch_tools, compile_setup=not args.stage_only), indent=2))


if __name__ == "__main__":
    main()
