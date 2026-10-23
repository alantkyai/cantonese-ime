"""Patch release version rules and real Inno exit/capture behavior.

The tiny Inno fixture uses lowest privileges, no payload/app directory,
registration, uninstall metadata, shortcuts, user activation or UAC.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import build_release as build


class ReleaseBuilderTests(unittest.TestCase):
    def test_patch_versions_are_supported(self):
        for version in ("0.0.0", "1.0.0", "1.0.1", "2.12.30", "65535.65535.65535"):
            with self.subTest(version=version):
                self.assertEqual(build.validate_version(version), version)

    def test_noncanonical_or_unrepresentable_windows_versions_are_rejected(self):
        for version in ("1.0", "1.0.1.0", "1.0.1-beta", "01.0.1", "1.00.1", "-1.0.1", "65536.0.0", "1.0.1\n", 101, None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                build.validate_version(version)

    def test_default_output_follows_the_project_patch_version(self):
        with patch.object(build, "project_version", return_value="1.0.1"):
            self.assertEqual(build.default_output(), build.ROOT / "dist/CantoneseIME-1.0.1-x64")

    def test_bad_project_version_is_rejected_before_output_selection(self):
        work = build.ROOT / ".local/release-builder-tests"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text('[project]\nversion="1.0.1-preview"\n', encoding="utf-8")
            with patch.object(build, "ROOT", root), self.assertRaises(ValueError):
                build.default_output()


class InnoOutcomeTests(unittest.TestCase):
    def test_actual_inno_returns_nonzero_for_failed_machine_or_user_phases_and_captures_diagnostics(self):
        compiler = build.ROOT / ".local/release-tools/inno-7.1.0/ISCC.exe"
        if not compiler.is_file():
            self.skipTest("Project-local Inno compiler is not available.")
        work = build.ROOT / ".local/release-builder-tests"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="inno-outcome-", dir=work) as directory:
            root = Path(directory)
            source = (build.ROOT / "installer/CantoneseIME.iss").read_text(encoding="utf-8")
            start = source.index("function GetCustomSetupExitCode: Integer;")
            finish = source.index("function InitializeUninstall: Boolean;", start)
            outcome = source[start:finish]
            for prepared, committed, activated, expected in ((True, False, False, 11), (True, True, False, 10), (True, True, True, 0)):
                name = f"outcome-{expected}"
                script = root / (name + ".iss")
                script.write_text(f'''[Setup]
AppName=Cantonese IME inert installer test
AppVersion=0.0.0
AppId=CantoneseIMEInertTest
DefaultDirName={{tmp}}\\CantoneseIMEInertTest
PrivilegesRequired=lowest
CreateAppDir=no
Uninstallable=no
CreateUninstallRegKey=no
UsePreviousAppDir=no
UsePreviousGroup=no
UsePreviousTasks=no
UsePreviousLanguage=no
DisableDirPage=yes
DisableProgramGroupPage=yes
CloseApplications=no
OutputDir={root}
OutputBaseFilename={name}
[Code]
var MachinePrepared, MachineCommitted, UserActivated: Boolean;
{outcome}
procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer;
begin
  if CurStep = ssPostInstall then begin
    MachinePrepared := {str(prepared)};
    MachineCommitted := {str(committed)};
    UserActivated := {str(activated)};
    ExecAndLogOutput(ExpandConstant('{{sys}}\\cmd.exe'), '/d /c echo CANTONESE_TEST_DIAGNOSTIC', '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code, nil);
  end;
end;
''', encoding="utf-8")
                compiled = subprocess.run([str(compiler), "/Q", str(script)], capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                log = root / (name + ".log")
                executed = subprocess.run([str(root / (name + ".exe")), "/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=" + str(log)], capture_output=True, timeout=30)
                self.assertEqual(executed.returncode, expected)
                self.assertIn("CANTONESE_TEST_DIAGNOSTIC", log.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
