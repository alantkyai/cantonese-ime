#!/usr/bin/env python3
"""Build the native macOS app/PKG on macOS, or a verified source ZIP anywhere.

No installer, system Python, input-source preference or user learning is changed.
The receiving Mac does not need Python. Building needs Python >=3.11 and Xcode
15.3+ command-line tools. All subprocess commands use argument arrays.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
MACOS = ROOT / "macos"
VERSION = "1.0.0"
BUNDLE_ID = "org.cantoneseime.inputmethod.CantoneseIME"
ENGINE_KIND = "Cantonese IME shared engine source snapshot"
WINDOWS_KIND = "Cantonese IME native AMD64 release runtime package"
MACHO = {bytes.fromhex(value) for value in ("feedface", "feedfacf", "cefaedfe", "cffaedfe", "cafebabe", "bebafeca", "cafebabf", "bfbafeca")}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))


def safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or any(char in relative for char in '\\:\x00'):
        raise ValueError("Invalid package path.")
    parts = relative.split("/")
    if PurePosixPath(relative).is_absolute() or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Package paths must stay inside their root.")
    result = root.joinpath(*parts)
    if result.is_symlink() or (result.exists() and not result.resolve().is_relative_to(root.resolve())):
        raise ValueError("Engine inputs must not contain symlinks or escape their root.")
    return result


def read_manifest(root: Path, expected: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Supply the original package manifest SHA256.")
    path = root / "package-manifest.json"
    if digest(path) != expected or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("The engine snapshot manifest changed.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("kind") not in (ENGINE_KIND, WINDOWS_KIND):
        raise ValueError("Expected a validated release engine snapshot.")
    seen = set()
    for item in value["files"]:
        path = safe_file(root, item["path"])
        if item["path"].casefold() in seen:
            raise ValueError("Duplicate engine snapshot path.")
        seen.add(item["path"].casefold())
        if not path.is_file() or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
            raise ValueError("Engine snapshot file changed: " + item["path"])
    dictionary = next(item for item in value["files"] if item["path"] == "data/generated/lexicon.sqlite3")
    if value["dictionary_sha256"] != dictionary["sha256"]:
        raise ValueError("Dictionary pins disagree.")
    return value


def selected_engine_path(relative: str) -> bool:
    return relative.startswith(("cantonese_ime/", "data/")) or relative == "stdio_bridge.py"


def stage_engine(source: Path, expected: str, output: Path) -> dict:
    original = read_manifest(source, expected)
    if output.exists():
        raise ValueError("Engine output already exists.")
    output.mkdir(parents=True)
    records = []
    for item in original["files"]:
        if not selected_engine_path(item["path"]):
            continue
        target = safe_file(output, item["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_file(source, item["path"]), target)
        if digest(target) != item["sha256"]:
            raise ValueError("Engine input changed while copying.")
        records.append(dict(item))
    if original["kind"] == WINDOWS_KIND:
        bridge = MACOS / "engine/stdio_bridge.py"
        pin = digest(bridge)
        shutil.copyfile(bridge, output / "stdio_bridge.py")
        if digest(bridge) != pin or digest(output / "stdio_bridge.py") != pin:
            raise ValueError("The macOS stdio bridge changed while staging.")
        records.append({"path": "stdio_bridge.py", "bytes": bridge.stat().st_size, "sha256": pin})
    required = {"stdio_bridge.py", "cantonese_ime/engine.py", "data/generated/lexicon.sqlite3", "data/THIRD_PARTY_NOTICES.md"}
    if not required.issubset({item["path"] for item in records}):
        raise ValueError("The shared engine snapshot is incomplete.")
    result = {"schema_version": 1, "kind": ENGINE_KIND, "version": VERSION,
              "source_package_manifest_sha256": expected, "dictionary_sha256": original["dictionary_sha256"],
              "files": sorted(records, key=lambda item: item["path"]),
              "total_payload_bytes": sum(item["bytes"] for item in records)}
    write_json(output / "package-manifest.json", result)
    read_manifest(source, expected)  # Original pins remain authoritative.
    read_manifest(output, digest(output / "package-manifest.json"))
    return result


def dependency(pkg: Path | None, *, fetch: bool) -> tuple[Path, dict]:
    lock = json.loads((MACOS / "dependencies.lock.json").read_text(encoding="utf-8"))
    source = lock["python"]
    path = pkg or ROOT / ".local/macos/dependencies" / source["filename"]
    if not path.exists():
        if not fetch:
            raise ValueError("Missing official Python package. Supply --python-pkg or allow --fetch-runtime.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(source["url"], temporary)
        if digest(temporary) != source["sha256"]:
            raise ValueError("Downloaded Python package has a different SHA256.")
        temporary.replace(path)
    if path.stat().st_size != source["bytes"] or digest(path) != source["sha256"]:
        raise ValueError("The official Python package differs from its retained release pin.")
    return path.resolve(), lock


def run(arguments: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run([str(value) for value in arguments], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError("Build command failed: " + str(arguments[0]) + "\n" + result.stdout[-3000:] + result.stderr[-3000:])
    return result


def is_macho(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(4) in MACHO


def macho_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if is_macho(path)]


def new_install_name(value: str, old_prefix: str) -> str:
    if value == old_prefix or value.startswith(old_prefix + "/"):
        return "@rpath/Python.framework" + value[len(old_prefix):]
    return value


def validate_symlinks(root: Path):
    for path in root.rglob("*"):
        if path.is_symlink() and (not path.exists() or os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError("A runtime symlink escapes the app: " + str(path))


def framework_payload(expanded: Path, version: str) -> Path:
    found = []
    for metadata in expanded.glob("**/PackageInfo"):
        info = ET.fromstring(metadata.read_bytes())
        if (info.get("identifier") == "org.python.Python.PythonFramework-" + version
                and info.get("install-location") == "/Library/Frameworks/Python.framework"):
            candidate = metadata.parent / "Payload"
            if (candidate / "Versions" / version / "Python").is_file():
                found.append(candidate)
    if len(found) != 1:
        raise ValueError("Cannot uniquely locate the regular Python.framework payload.")
    return found[0]


def prune_runtime(framework: Path, version: str):
    """Drop unused upstream launchers/GUI code; retain the core and licenses."""
    home = framework / "Versions" / version
    for relative in ("bin", "Resources/Python.app", "Frameworks", "lib/python3.13/tkinter"):
        target = home / relative
        if target.is_symlink() or not target.resolve().is_relative_to(framework.resolve()):
            raise ValueError("Unexpected link in a private-runtime pruning target.")
        if target.is_dir():
            shutil.rmtree(target)
    for target in (home / "lib/python3.13/lib-dynload").glob("_tkinter*.so"):
        target.unlink()
    # AppleDouble files are extended-attribute transport records, not sources.
    for target in framework.rglob("._*"):
        if target.is_file() and not target.is_symlink():
            target.unlink()
    # Remove only obsolete Finder/resource-fork transport metadata from this
    # fresh build copy. Quarantine and user/system files are not changed.
    for target in [framework, *framework.rglob("*")]:
        if not target.is_symlink():
            for name in os.listxattr(target):
                if name in ("com.apple.FinderInfo", "com.apple.ResourceFork"):
                    os.removexattr(target, name)


def app_inventory(app: Path) -> dict:
    return {path.relative_to(app).as_posix(): ({"symlink": os.readlink(path)} if path.is_symlink()
            else {"sha256": digest(path), "bytes": path.stat().st_size})
            for path in app.rglob("*") if path.is_file() or path.is_symlink()}


def relocate_framework(framework: Path, old_prefix: str) -> list[dict]:
    records = []
    container = framework.parent
    for path in macho_files(framework):
        run(["/usr/bin/lipo", "-verify_arch", "arm64", "x86_64", str(path)])
        run(["/usr/bin/codesign", "--remove-signature", str(path)], check=False)
        linked = run(["/usr/bin/otool", "-L", str(path)]).stdout
        names = {line.strip().split(" (", 1)[0] for line in linked.splitlines() if line[:1].isspace()}
        changes = []
        for name in names:
            changed = new_install_name(name, old_prefix)
            if changed != name:
                run(["/usr/bin/install_name_tool", "-change", name, changed, str(path)])
                changes.append([name, changed])
            elif name.startswith("/") and not name.startswith(("/usr/lib/", "/System/Library/", "/Library/Apple/System/Library/")):
                raise ValueError("The private runtime depends on an external library: " + name)
        identities = run(["/usr/bin/otool", "-D", str(path)], check=False).stdout.splitlines()
        for name in sorted({line.strip() for line in identities if line.strip().startswith(old_prefix)}):
            run(["/usr/bin/install_name_tool", "-id", new_install_name(name, old_prefix), str(path)])
        relative = os.path.relpath(container, path.parent)
        rpath = "@loader_path" if relative == "." else "@loader_path/" + relative
        loads = run(["/usr/bin/otool", "-l", str(path)]).stdout
        if not any(line.strip().startswith("path " + rpath + " (offset") for line in loads.splitlines()):
            run(["/usr/bin/install_name_tool", "-add_rpath", rpath, str(path)])
        after = run(["/usr/bin/otool", "-L", str(path)]).stdout
        if old_prefix in after:
            raise ValueError("An original framework dependency was not relocated.")
        records.append({"path": path.relative_to(framework).as_posix(), "dependency_changes": changes, "rpath": rpath})
    if not records:
        raise ValueError("The Python framework contains no Mach-O runtime.")
    return records


def make_distribution(version: str, component_name: str) -> str:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", version) or "/" in component_name or "\\" in component_name:
        raise ValueError("Invalid product metadata.")
    return f'''<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
  <title>Cantonese IME {escape(version)}</title>
  <welcome file="Welcome.txt" mime-type="text/plain"/>
  <license file="License.txt" mime-type="text/plain"/>
  <conclusion file="Conclusion.txt" mime-type="text/plain"/>
  <options customize="never" require-scripts="false"/>
  <domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
  <allowed-os-versions><os-version min="13.0"/></allowed-os-versions>
  <choices-outline><line choice="main"/></choices-outline>
  <choice id="main" visible="false"><pkg-ref id="{BUNDLE_ID}.pkg"/></choice>
  <pkg-ref id="{BUNDLE_ID}.pkg" version="{escape(version)}" onConclusion="none">{escape(component_name)}</pkg-ref>
</installer-gui-script>
'''


def component_policy() -> list[dict]:
    return [{"RootRelativeBundlePath": "Library/Input Methods/CantoneseIME.app",
             "BundleIsRelocatable": False, "BundleHasStrictIdentifier": True,
             "BundleIsVersionChecked": True, "BundleOverwriteAction": "upgrade"}]


def inspect_component_package(metadata: Path):
    info = ET.fromstring(metadata.read_bytes())
    if info.get("install-location") != "/" or info.get("relocatable") != "false":
        raise ValueError("The generated component is not fixed to the startup-volume system path.")
    if info.findall("./relocate/bundle"):
        raise ValueError("The generated component allows unexpected app relocation.")
    for bundle in info.findall("./bundle"):
        path = bundle.get("path", "").removeprefix("./")
        if path != "Library/Input Methods/CantoneseIME.app" and not path.startswith("Library/Input Methods/CantoneseIME.app/"):
            raise ValueError("The generated package owns an unexpected bundle path.")


def source_snapshot() -> dict[str, str]:
    files = [path for path in MACOS.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
    checker = ROOT / "tools/check_macos_engine.py"
    if checker.is_file():
        files.append(checker)
    return {path.relative_to(ROOT).as_posix(): digest(path) for path in files}


def verify_sources(pins: dict[str, str]):
    if source_snapshot() != pins:
        raise ValueError("A macOS source changed during the release build.")


def source_release(output: Path, source: Path, expected: str, pkg: Path, lock: dict, pins: dict[str, str]) -> dict:
    tree = output / f"CantoneseIME-{VERSION}-macos-source"
    tree.mkdir()
    for name, original_hash in pins.items():
        target = tree / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        if digest(target) != original_hash:
            raise ValueError("A macOS source changed while archiving.")
    stage_engine(source, expected, tree / "engine")
    target_pkg = tree / "dependencies" / pkg.name
    target_pkg.parent.mkdir()
    shutil.copyfile(pkg, target_pkg)
    if digest(target_pkg) != lock["python"]["sha256"]:
        raise ValueError("The offline Python build input changed while archiving.")
    write_json(tree / "source-release.json", {"schema_version": 1, "version": VERSION, "native_compiled": False,
        "artifact_kind": "macOS source and offline build inputs; not an installable PKG",
        "engine_manifest_sha256": digest(tree / "engine/package-manifest.json"), "sources_sha256": pins,
        "python_package_sha256": lock["python"]["sha256"]})
    (tree / "START_HERE.txt").write_bytes(("Cantonese IME 1.0.0 macOS source/build kit\n\n"
        "This ZIP is not an installable Mac app or PKG. Read macos/README.md.\n"
        "Build on a Mac with Python 3.11+ and Xcode 15.3+ tools:\n"
        "  python3 macos/build_release.py --output dist/macos-local\n"
        "The official Python universal2 package and full shared dictionary are included offline.\n").encode("utf-8"))
    archive = output / f"CantoneseIME-{VERSION}-macos-source.zip"
    members = {path.relative_to(tree).as_posix(): digest(path) for path in tree.rglob("*") if path.is_file()}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(tree.rglob("*")):
            if not path.is_file():
                continue
            name = tree.name + "/" + path.relative_to(tree).as_posix()
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            executable = path.name in ("preinstall", "postinstall")
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            info.compress_type = zipfile.ZIP_STORED if path.suffix == ".pkg" else zipfile.ZIP_DEFLATED
            with path.open("rb") as reader, zipped.open(info, "w", force_zip64=True) as writer:
                shutil.copyfileobj(reader, writer, 1024 * 1024)
    with zipfile.ZipFile(archive) as zipped:
        for name, checksum in members.items():
            value = hashlib.sha256()
            with zipped.open(tree.name + "/" + name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(block)
            if value.hexdigest() != checksum or digest(tree / name) != checksum:
                raise ValueError("Source ZIP content verification failed.")
    verify_sources(pins)
    return {"schema_version": 1, "version": VERSION, "artifact_kind": "source_zip", "native_compiled": False,
            "native_tested": False, "signed": False, "notarized": False, "filename": archive.name,
            "bytes": archive.stat().st_size, "sha256": digest(archive), "sources_sha256": pins,
            "engine_manifest_sha256": digest(tree / "engine/package-manifest.json"), "archive_members_sha256": members}


def sign_app(app: Path, identity: str | None) -> str:
    selected = identity or "-"
    flags = ["--force", "--sign", selected]
    if identity:
        flags += ["--timestamp", "--options", "runtime"]
    for path in sorted(macho_files(app), key=lambda value: len(value.parts), reverse=True):
        run(["/usr/bin/codesign", *flags, str(path)])
    nested = [path for path in app.rglob("*") if path.is_dir() and not path.is_symlink() and path.suffix in (".app", ".framework")]
    for path in sorted(nested, key=lambda value: len(value.parts), reverse=True):
        run(["/usr/bin/codesign", *flags, str(path)])
    run(["/usr/bin/codesign", *flags, str(app)])
    run(["/usr/bin/codesign", "--verify", "--strict", "--deep", "--verbose=2", str(app)])
    displayed = run(["/usr/bin/codesign", "--display", "--verbose=4", str(app)])
    details = displayed.stdout + displayed.stderr
    if identity and "Authority=Developer ID Application:" not in details:
        raise ValueError("The supplied application identity is not a Developer ID Application certificate.")
    return details


def native_release(output: Path, source: Path, expected: str, pkg: Path, lock: dict, pins: dict[str, str], args) -> dict:
    if sys.platform != "darwin":
        raise RuntimeError("Native app and PKG compilation requires macOS and its SDK. Use --source-only here.")
    swift_version = run(["/usr/bin/xcrun", "swiftc", "--version"]).stdout
    match = re.search(r"Swift version ([0-9]+)\.([0-9]+)", swift_version)
    if not match or tuple(map(int, match.groups())) < (5, 10):
        raise ValueError("Swift 5.10 or newer (Xcode 15.3+) is required.")
    expanded = output / "python-expanded"
    run(["/usr/sbin/pkgutil", "--check-signature", str(pkg)])
    run(["/usr/sbin/pkgutil", "--expand-full", str(pkg), str(expanded)])
    original_framework = framework_payload(expanded, lock["python"]["major_minor"])
    payload = output / "payload"
    app = payload / "Library/Input Methods/CantoneseIME.app"
    contents = app / "Contents"
    resources = contents / "Resources"
    executable = contents / "MacOS"
    executable.mkdir(parents=True)
    resources.mkdir()
    engine = stage_engine(source, expected, resources / "engine")
    framework = contents / "Frameworks/Python.framework"
    framework.parent.mkdir()
    shutil.copytree(original_framework, framework, symlinks=True)
    prune_runtime(framework, lock["python"]["major_minor"])
    validate_symlinks(app)
    relocation = relocate_framework(framework, lock["python"]["upstream_framework_prefix"])
    version_home = framework / "Versions" / lock["python"]["major_minor"]
    if not (version_home / "lib/python3.13/encodings/__init__.py").is_file():
        raise ValueError("The private framework is missing its standard library.")
    licenses = resources / "licenses/Python"
    licenses.mkdir(parents=True)
    license_sources = [path for path in expanded.rglob("*") if path.is_file() and path.name.lower() in ("license.rtf", "license.txt")]
    if not license_sources:
        raise ValueError("The original Python package's license was not retained.")
    for index, path in enumerate(license_sources):
        shutil.copyfile(path, licenses / f"{index}-{path.name}")
    shutil.copyfile(MACOS / "installer/License.txt", resources / "RELEASE_NOTICES.txt")
    info = plistlib.loads((MACOS / "Resources/Info.plist").read_bytes())
    if info["CFBundleIdentifier"] != BUNDLE_ID or info["CFBundleExecutable"] != "CantoneseIME":
        raise ValueError("The IMK bundle identity changed.")
    info["CantoneseIMEDictionarySHA256"] = engine["dictionary_sha256"]
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    icons = output / "generated-icons"
    icons.mkdir()
    run(["/usr/bin/xcrun", "swift", str(MACOS / "Tools/GenerateIcons.swift"), str(icons)])
    for name in ("CantoneseIME.icns", "MenuCantonese.pdf", "MenuEnglish.pdf"):
        shutil.copyfile(icons / name, resources / name)
    sources = sorted((MACOS / "Sources").glob("*.swift"))
    slices = []
    for architecture in ("arm64", "x86_64"):
        target = output / ("CantoneseIME-" + architecture)
        run(["/usr/bin/xcrun", "--sdk", "macosx", "swiftc", "-O", "-swift-version", "5", "-module-name", "CantoneseIME", "-target", architecture + "-apple-macos13.0",
             "-framework", "Cocoa", "-framework", "InputMethodKit", "-framework", "Carbon", *map(str, sources), "-o", str(target)])
        slices.append(str(target))
    run(["/usr/bin/lipo", "-create", *slices, "-output", str(executable / "CantoneseIME")])
    run(["/usr/bin/xcrun", "--sdk", "macosx", "clang", "-O2", "-arch", "arm64", "-arch", "x86_64",
         "-mmacosx-version-min=13.0", "-F" + str(framework.parent), "-framework", "Python",
         "-I" + str(version_home / "include/python3.13"), "-Wl,-rpath,@executable_path/../Frameworks",
         str(MACOS / "installer/python_launcher.c"), "-o", str(executable / "CantoneseIMEEngine")])
    launcher = executable / "CantoneseIMEEngine"
    validate_symlinks(app)
    for path in macho_files(app):
        run(["/usr/bin/lipo", "-verify_arch", "arm64", "x86_64", str(path)])
    signing_details = sign_app(app, args.application_identity)
    (output / "application-signature.txt").write_text(signing_details, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="cantonese-ime-runtime-") as external:
        probe = "import sys,pathlib,sqlite3,ssl,ctypes,json; p=pathlib.Path(sys.executable).resolve().parents[1]; assert sys.flags.isolated and sys.dont_write_bytecode; assert all(pathlib.Path(x).resolve().is_relative_to(p) for x in sys.path); files=[m.__file__ for m in sys.modules.values() if isinstance(getattr(m,'__file__',None),str) and not m.__file__.startswith('<')]; assert all(pathlib.Path(x).resolve().is_relative_to(p) for x in files); print(json.dumps({'isolated':True,'sys_path':sys.path,'sqlite':sqlite3.sqlite_version,'module_files_inside_bundle':True}))"
        runtime_check = run([str(launcher), "-I", "-B", "-c", probe], cwd=Path(external)).stdout
    run([sys.executable, "-B", str(MACOS / "Tools/run_native_tests.py"), "--output", str(output / "native-validation")])
    run([sys.executable, "-B", str(ROOT / "tools/check_macos_engine.py"), "--python", str(launcher),
         "--dictionary", str(resources / "engine/data/generated/lexicon.sqlite3"),
         "--bridge", str(resources / "engine/stdio_bridge.py"), "--output", str(output / "engine-validation")])
    sealed_inventory = app_inventory(app)
    run(["/usr/bin/codesign", "--verify", "--strict", "--deep", "--verbose=2", str(app)])
    # All installer-owned payload is root-owned via pkgbuild; learning remains
    # in each user's Application Support directory and is never in this tree.
    scripts = output / "installer-scripts"
    scripts.mkdir()
    for name in ("preinstall", "postinstall"):
        target = scripts / name
        shutil.copyfile(MACOS / "installer" / name, target)
        target.chmod(0o755)
    component = output / "CantoneseIME-component.pkg"
    policy = output / "component-policy.plist"
    policy.write_bytes(plistlib.dumps(component_policy()))
    run(["/usr/bin/pkgbuild", "--root", str(payload), "--identifier", BUNDLE_ID + ".pkg", "--version", VERSION,
         "--install-location", "/", "--ownership", "recommended", "--component-plist", str(policy),
         "--scripts", str(scripts), str(component)])
    expanded_component = output / "component-inspection"
    run(["/usr/sbin/pkgutil", "--expand", str(component), str(expanded_component)])
    inspect_component_package(expanded_component / "PackageInfo")
    distribution = output / "Distribution.xml"
    distribution.write_text(make_distribution(VERSION, component.name), encoding="utf-8")
    final = output / f"CantoneseIME-{VERSION}-macos-universal2.pkg"
    command = ["/usr/bin/productbuild", "--distribution", str(distribution), "--resources", str(MACOS / "installer"), "--package-path", str(output)]
    if args.installer_identity:
        command += ["--sign", args.installer_identity]
    run(command + [str(final)])
    package_signature = run(["/usr/sbin/pkgutil", "--check-signature", str(final)], check=bool(args.installer_identity))
    (output / "installer-signature.txt").write_text(package_signature.stdout + package_signature.stderr, encoding="utf-8")
    if args.installer_identity and "Developer ID Installer:" not in package_signature.stdout + package_signature.stderr:
        raise ValueError("The supplied installer identity is not a Developer ID Installer certificate.")
    notarized = False
    notary_issues = []
    if args.notary_profile:
        if not args.application_identity or not args.installer_identity:
            raise ValueError("Notarization requires Developer ID Application and Installer identities.")
        response = run(["/usr/bin/xcrun", "notarytool", "submit", str(final), "--keychain-profile", args.notary_profile,
                        "--wait", "--output-format", "json"]).stdout
        result = json.loads(response)
        write_json(output / "notarization.json", result)
        log_path = output / "notarization-log.json"
        run(["/usr/bin/xcrun", "notarytool", "log", result["id"], "--keychain-profile", args.notary_profile, str(log_path)])
        notary_issues = json.loads(log_path.read_text(encoding="utf-8")).get("issues", [])
        if result.get("status") != "Accepted":
            raise ValueError("Apple did not accept this package for notarization.")
        run(["/usr/bin/xcrun", "stapler", "staple", str(final)])
        run(["/usr/bin/xcrun", "stapler", "validate", str(final)])
        run(["/usr/sbin/spctl", "--assess", "--type", "install", "--verbose=2", str(final)])
        notarized = True
    verify_sources(pins)
    read_manifest(source, expected)
    if app_inventory(app) != sealed_inventory:
        raise ValueError("A signed app input changed while packaging or notarizing.")
    return {"schema_version": 1, "version": VERSION, "artifact_kind": "native_pkg", "native_compiled": True,
            "native_ui_tested": False, "architectures": ["arm64", "x86_64"], "minimum_macos": "13.0",
            "application_signature": "Developer ID" if args.application_identity else "ad_hoc_local_build",
            "installer_signed": bool(args.installer_identity), "notarized": notarized,
            "notarization_issues": notary_issues,
            "filename": final.name, "bytes": final.stat().st_size, "sha256": digest(final),
            "private_runtime_check": json.loads(runtime_check), "relocation": relocation, "sources_sha256": pins,
            "private_python_source": lock["python"], "app_files": sealed_inventory,
            "native_core_validation_sha256": digest(output / "native-validation/report.json"),
            "engine_validation_sha256": digest(output / "engine-validation/report.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    packaged = ROOT / "engine"
    parser.add_argument("--engine-package", type=Path, default=packaged if packaged.is_dir() else ROOT / "dist/CantoneseIME-1.0.0-x64/package")
    parser.add_argument("--engine-manifest-sha256")
    parser.add_argument("--python-pkg", type=Path)
    parser.add_argument("--fetch-runtime", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/CantoneseIME-1.0.0-macos")
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--application-identity")
    parser.add_argument("--installer-identity")
    parser.add_argument("--notary-profile")
    args = parser.parse_args()
    expected = args.engine_manifest_sha256
    if expected is None:
        receipt = args.engine_package.parent / ("source-release.json" if args.engine_package.name == "engine" else "release-build.json")
        if not receipt.is_file():
            parser.error("Supply --engine-manifest-sha256 from the retained source release/build receipt.")
        value = json.loads(receipt.read_text(encoding="utf-8"))
        expected = value.get("engine_manifest_sha256") if args.engine_package.name == "engine" else value.get("package_manifest_sha256")
    if args.notary_profile and (not args.application_identity or not args.installer_identity):
        parser.error("A notary profile also requires both signing identities.")
    output = args.output.resolve()
    if output.exists():
        parser.error("Output already exists; choose a fresh release directory.")
    if not args.source_only and sys.platform != "darwin":
        parser.error("A native app/PKG requires macOS. Use --source-only on this host.")
    pins = source_snapshot()
    source = args.engine_package.resolve()
    read_manifest(source, expected)
    offline_default = ROOT / "dependencies" / json.loads((MACOS / "dependencies.lock.json").read_text())["python"]["filename"]
    pkg, lock = dependency(args.python_pkg or (offline_default if offline_default.is_file() else None), fetch=args.fetch_runtime)
    output.mkdir(parents=True)
    report = source_release(output, source, expected, pkg, lock, pins) if args.source_only else native_release(output, source, expected, pkg, lock, pins, args)
    report["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "macos-build.json", report)
    (output / "SHA256SUMS.txt").write_text(report["sha256"] + "  " + report["filename"] + "\n", encoding="ascii")
    print(json.dumps({key: report[key] for key in ("artifact_kind", "filename", "bytes", "sha256", "native_compiled")}, indent=2))


if __name__ == "__main__":
    main()
