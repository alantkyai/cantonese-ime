"""Read-only dry-run guard checks. Never invokes install/remove/enable/disable."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(helper: Path, plan: Path, checksum: str, extra: list[str] | None = None) -> dict:
    command = [str(helper), "--action", "dry-run", "--manifest", str(plan),
               "--manifest-sha256", checksum, *(extra or [])]
    result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=10)
    records = [json.loads(line) for line in result.stdout.splitlines() if line]
    forbidden = ("RegisterProfile_", "RegisterCategory_", "HKLM_COM_create", "remove_profile_",
                 "user_EnableLanguageProfile", "user_InstallLayoutOrTip", "rollback_",
                 "refresh_RegisterProfile_", "refresh_RegisterCategory_", "refresh_preserve_enabled_",
                 "refresh_rollback_")
    if any(row["stage"].startswith(forbidden) for row in records):
        raise AssertionError("Dry run reached a mutating stage")
    return {"exit_code": result.returncode, "stages": records, "stderr": result.stderr}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    helper, manifest = args.helper.resolve(), args.manifest.resolve()
    helper_hash = digest(helper.read_bytes())
    original = manifest.read_bytes()
    text = original.decode("utf-8")
    rows: list[dict] = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="registration-guards-", dir=args.output.parent) as folder:
        fixtures = Path(folder).resolve()
        malformed = fixtures / "not-a-dll.bin"
        malformed.write_bytes(b"MZ" + b"\0" * 126)
        fields = dict(line.split("=", 1) for line in text.splitlines()[1:])
        cases: list[tuple[str, bytes, list[str], str | None]] = [
            ("valid_preinstall_dry_run", original, [], None),
            ("manifest_digest_mismatch", original, [], "0" * 64),
            ("wrong_clsid", text.replace(fields["clsid"], "{00000000-0000-0000-0000-000000000000}").encode(), [], None),
            ("wrong_profile", text.replace(fields["profile"], "{00000000-0000-0000-0000-000000000000}").encode(), [], None),
            ("unexpected_language", text.replace("languages=0409,0c04", "languages=0409,0411").encode(), [], None),
            ("workspace_target", text.replace(fields["dll_target"], str(fixtures / "CantoneseIME.dll")).encode(), [], None),
            ("target_dot_traversal", text.replace(fields["dll_target"], fields["dll_target"].replace("\\native\\", "\\native\\..\\native\\")).encode(), [], None),
            ("relative_source", text.replace(fields["dll_source"], "CantoneseIME.dll").encode(), [], None),
            ("wrong_dll_digest", text.replace(fields["dll_sha256"], "0" * 64).encode(), [], None),
            ("invalid_pe_source", text.replace(fields["dll_source"], str(malformed)).replace(fields["dll_sha256"], digest(malformed.read_bytes())).encode(), [], None),
            ("unknown_field", original + b"arbitrary_registry_key=HKLM\\Software\\Other\n", [], None),
            ("duplicate_field", original + f"clsid={fields['clsid']}\n".encode(), [], None),
            ("nul_in_manifest", original + b"extra=hello\0world\n", [], None),
            ("invalid_utf8", original + b"extra=\xff\n", [], None),
            ("unexpected_bom", b"\xef\xbb\xbf" + original, [], None),
            ("oversized_manifest", original + b"x" * 65536, [], None),
            ("duplicate_action_argument", original, ["--action", "dry-run"], None),
            ("unexpected_machine_language_argument", original, ["--language", "0409"], None),
        ]
        for index, (name, data, extra, override) in enumerate(cases):
            path = fixtures / f"case-{index}.plan"
            path.write_bytes(data)
            result = run(helper, path, override or digest(data), extra)
            expected = 0 if index == 0 else 2
            if index == 0 and result["exit_code"] == 2:
                # An already-installed development machine is a valid place to
                # test guards. Fresh install must refuse the existing namespace.
                stages = result["stages"]
                existing = any(row["stage"] in ("HKLM_COM", "HKLM_TIP") and row["detail"] == "present" for row in stages)
                refused_existing = any(row["stage"] == "failed" and row["hresult"] == "0x800700b7" for row in stages)
                if existing and refused_existing:
                    expected = 2
                    result["existing_install_refused"] = True
            result.update(name=name, expected_exit_code=expected, passed=result["exit_code"] == expected)
            rows.append(result)
    if digest(helper.read_bytes()) != helper_hash:
        raise AssertionError("Helper changed during checks")
    report = {"scope": "synthetic manifest/argument guards; dry-run only in sandbox; not desktop registration or protected-copy proof",
              "helper": str(helper), "helper_sha256": helper_hash,
              "manifest": str(manifest), "manifest_sha256": digest(original),
              "checks": rows, "passed": all(row["passed"] for row in rows)}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(rows), "helper_sha256": helper_hash,
                      "output": str(args.output.resolve())}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
