# Updating the installed x64 IME

`Update-NativeIme.ps1` replaces a reviewed package at the existing protected
`C:\Program Files\CantoneseIME` path. It does not register, unregister, enable,
disable or activate an input method, change defaults, request UAC, stop/start a
broker, close applications, or read/write LocalAppData. Fixed COM and profile
identities remain unchanged. Local selection memory remains at the runtime
controller's existing per-user location, outside the package.

The guarded mapped-DLL upgrade has completed on this machine. Crash recovery
and post-upgrade ordinary-application UI/learning behavior remain separate checks.
Earlier Notepad success applies to the baseline DLL; the user will test the
updated application behavior without further automated UI checking.

## Historical adaptive update on 2026-10-22

Administrator/UAC execution finished at `2026-10-22T14:59:44.3632356Z`;
the protected journal records `committed` at `14:59:44.3499030Z`. The current
package was `preview-20261022-adaptive-compact-install`, with manifest SHA-256
`514600bf31f5d8371d162d5205ce1f3a296bd210cb0a7ae584d0971db670348b`.
That revision's DLL was
`4a5e1138f77d45ed9c406e1f4cb4113531095c005f816accf06bd881d5c002cc`;
its registration-plan pin was
`6a42dabddeafa9f6d887cf34190f01b86d5aebab3e51b19b470b5f1b1cf7564a`.
These pins identify that historical update. Use the latest reviewed installed
receipt and validation report for subsequent verification/removal. The later
[numbered-candidate update](../docs/numbered-candidates-validation.json) and any
subsequent dictionary upgrade have separate package/plan pins.

The protected operation directory is
`C:\Program Files\CantoneseIME-Updates\20261022T145913Z-64569819256d4cdfb861803f474f1f6a`.
Its `backup`, `retired` and authoritative `journal.json` were retained. Mapped-DLL
mode left Explorer, Chrome, Codex and the existing Notepad process running with
their old images; no application was closed or killed. COM/profile definitions,
user enabling/defaults and the personal learning store were preserved. No test
preferences were copied into the real user's store.

Installed runtime integrity verification passed; broker PID 82448 was ready at
the recorded check, and a fresh x64 `LoadLibrary` probe PID 1140 loaded the new
DLL successfully. The installed helper read back `0409` enabled with the English
default unchanged. See [adaptive validation](../docs/adaptive-ime-validation.json)
and [raw evidence](../docs/native-evidence/2026-10-22/adaptive-compact).
These are installation/runtime checks, not a post-upgrade popup or typing test.
Reopen the application you want to test to load the new UI and selection-learning
frontend; existing processes may keep the previous DLL until it unloads.

This repository guide now includes the completed result. The installed/package
copy remains the frozen pre-update guide; it and its reviewed manifest were not
rewritten to add this note.

## Review and preflight

Build and stage a fresh package with `tools/package_native.py`. Keep the original
package and its explicit manifest pin. This updater permits reviewed frontend,
Python, protocol and associated package changes. It requires the same external
Python executable and reviewed registration helper. A helper or interpreter
change needs a separately reviewed workflow. A changed dictionary is refused
by default; it requires the explicit `-DictionarySha256` option described below.
The new production config must explicitly enable learning and use the normal
per-user store (`learning_file` null/absent). An isolated smoke-test store override,
disabled learning or a nonboolean setting is refused rather than installed.
The old baseline config predates these fields and remains accepted.

Run 64-bit PowerShell with all four reviewed values:

```powershell
& 'D:\IME_Project\native\Update-NativeIme.ps1' `
  -PackageRoot '<new-package-root>' `
  -ManifestSha256 '<new-package-manifest-sha256>' `
  -InstalledManifestSha256 '<current-installed-package-manifest-sha256>' `
  -RegistrationPlanSha256 '<current-installed-machine-registration-plan-sha256>' `
  -WhatIf
```

For a reviewed vocabulary upgrade, add the new dictionary file's explicit
64-hex-digit SHA-256 to both preflight and the actual command:

```powershell
& 'D:\IME_Project\native\Update-NativeIme.ps1' `
  -PackageRoot '<new-package-root>' `
  -ManifestSha256 '<new-package-manifest-sha256>' `
  -InstalledManifestSha256 '<current-installed-package-manifest-sha256>' `
  -RegistrationPlanSha256 '<current-installed-machine-registration-plan-sha256>' `
  -DictionarySha256 '<reviewed-new-lexicon.sqlite3-sha256>' `
  -WhatIf
```

The option must match the new package's dictionary hash exactly. The updater
independently verifies the old dictionary against the pinned installed manifest;
the option does not authorize a mismatch in that old package. It then verifies
the new SQLite bytes, their package file record, the package dictionary hash,
`data/generated/lexicon.manifest.json`, and `runtime-config.json` agree.
These checks repeat on the protected staged copy before replacement. Wrong or
missing pins, tampered bytes, or inconsistent manifests/configuration stop the
operation. The helper's fixed reviewed hash, interpreter pin, protected paths,
file inventory, owner policy and rollback behavior still apply. A dictionary pin
does not accept an arbitrary package manifest or bypass another guard.

For the first update, the installed manifest pin is
`8d7af8fda6021d6d131eabfe5b5f4310f0b570490d9186e8369aa5fcc426c5f7`;
the original registration-plan pin is
`035f79a008f8ee77166981ab976729a61c9a2e1ed65db6fc341c762a74de92d4`.
Use the new receipt's pins for subsequent updates. Never substitute a freshly
computed installed hash for a previously reviewed pin merely to bypass refusal.

Preflight verifies complete old/new inventories, executable architecture,
runtime configuration hashes, unchanged helper, fixed IDs and installed COM
path/profile definitions. It refuses reparse points, unprotected installation
ACLs, Windows path aliases, and collisions with unmanaged files. Restart Manager
lists DLL owners separately from owners of every other installed file. By default,
any owner causes refusal. With the explicitly reviewed `-AllowMappedDll` switch,
DLL owners may remain; every non-DLL owner still blocks, including a process that
appears in both lists. Subsequent file locks remain decisive, so an empty owner
list is not treated as proof that a later file operation cannot fail.
`-WhatIf` writes no installation, backup, journal or user-state files and changes
no COM/profile/input settings. Restart Manager creates and closes a discovery
session with its own internal bookkeeping; it does not shut down or restart apps.

Before replacement, the operator must gracefully stop the known owned broker
using the existing controller in the ordinary desktop account. Without mapped-DLL
mode, also ask the user to save/close applications holding the IME DLL. The updater
never kills them. Do not restart the broker until replacement finishes. If a
non-DLL file is open or any required file cannot be locked, replacement refuses;
inspect the reported owners rather than removing permissions or forcing deletion.

`-AllowMappedDll` requires prior review that the new broker remains compatible
with the protocol used by existing frontend DLLs. The switch does not prove
compatibility automatically. The current replacement keeps legacy `IME1`
conversion and adds `IML1` selection learning; old frontends continue conversion
but cannot acquire the new UI/selection behavior until naturally reopened.
Use the switch on both the preflight and actual reviewed command. Existing apps
may keep their old image until it unloads; no reboot deletion is scheduled.

## Protected replacement and receipts

Run the same reviewed command without `-WhatIf` in administrator PowerShell after
the preflight blocking owners have cleared. The updater creates a unique protected
`C:\Program Files\CantoneseIME-Updates\<timestamp>-<uuid>` operation directory.
Its `backup` contains a byte-verified copy of every installed file, including
the old manifest, registration plan, installation receipt and diagnostics.
`stage` holds the verified new package; `retired` retains original withdrawn
files. No backup or retired file is deleted automatically.

The updater holds installation-directory handles and exclusive file handles,
rechecks the installed bytes, and renames files through their held handles.
In mapped-DLL mode only the old DLL uses `GENERIC_READ | DELETE` with
`FILE_SHARE_READ`, preserving its exact identity and denying other write/delete
opens while allowing existing mappings. It never requests old-image write access.
All other inputs and the staged new DLL keep exclusive handles.
It never truncates a loaded image. The old config and DLL are withdrawn first;
the new config and DLL are published last and remain locked until completion.
Other installed diagnostic files remain in place. Old package inputs omitted
from the new manifest are retained in the backup/retired copy rather than left
as stale importable modules in the active package.

The protected `machine-registration.plan` is regenerated with the new DLL hash
at exactly the same path, CLSID, profile GUID and language definitions. This is
a local verification-plan update; no registration helper action is invoked and
no registry binding is rewritten. Future user-inspection/removal commands must
use its new SHA256, recorded with the old pin in the update journal and receipt.

`journal.json` is the authoritative operation status and records both package,
dictionary, DLL and plan hashes, the explicit dictionary pin when supplied,
unchanged helper/IDs, baseline inventory and backup path.
`installation.json` keeps existing installation fields and adds upgrade metadata,
including the current and previous dictionary hash;
it does not claim user enablement, startup or a new app test. `last-upgrade.json`
points to the authoritative protected journal.

## Failure and recovery

Ordinary errors trigger rollback while the original file handles remain held:
newly published files return to staging and original files return to the fixed
installation path. The journal distinguishes `rolled_back` from
`rollback_incomplete`, retains errors, and keeps all evidence. A preflight error
does not initiate replacement. Empty directories created during an attempted
update may remain; the script performs no recursive deletion.

This is not a power-loss-atomic directory transaction. A terminated PowerShell,
machine restart, storage failure or another administrator's concurrent changes
may interrupt rollback. If the journal is not `committed` or `rolled_back`, keep
the broker stopped and apps closed. Review the protected backup inventory and
old/new hashes; restore only those exact package/control files to the fixed
installation path from the verified backup, then verify the complete old
manifest and original plan pin before restarting. Do not rerun the first-install
script, remove profiles, change defaults, copy over a mapped DLL, or delete the
operation directory as a recovery shortcut. Recovery must be reviewed against
the actual partial state; the updater does not guess which files survived an
abrupt interruption.

After `committed`, verify/start the installed runtime as the normal desktop
account. Repeat ordinary x64 Notepad commit, cancellation and English toggle;
use a fresh application process launched after commit and inspect its actual
mapped DLL against the new hash. Old processes can retain the original module
filename while its on-disk path now contains the replacement; hashing that path
alone does not prove which code an old process mapped. For learning changes, verify
an explicit selection is saved locally and recalled after an owned broker
restart. For UI changes, capture the displayed candidate/preedit behavior when
screen capture is available. Record the new package, DLL, plan, broker and app
evidence separately from historical baseline proof. Keep the protected baseline
backup until rollback is no longer needed; an application-data schema change
requires a separate compatibility/recovery decision because this script never
rolls back or deletes local learning.

## Source checks

`tools/Test-NativeUpdater.ps1` exercises validation and held-handle
copy/rename/rollback primitives only inside a new project-local fixture directory.
It does not run the updater's installation path, registration actions or runtime
controller. Fixture success does not establish the real upgrade lifecycle.
The current 18 checks pass in Windows PowerShell 5.1 and PowerShell 7. Dictionary
fixtures cover default refusal, a wrong or malformed pin, valid explicit opt-in,
unchanged interpreter enforcement, dictionary byte tampering, disagreement in
either runtime configuration or source manifest, and restoration of all three
coupled dictionary/configuration files after an injected publication error.
These use synthetic dictionary bytes to test the installer boundary; they do
not claim SQLite or linguistic validation of a new vocabulary dataset.

`tools/check_mapped_image_upgrade.py` loads workspace copies of the pinned old
and new DLLs in its own x64 child processes. It verifies read/delete image rename,
old mapped function-byte stability and successful export execution, fresh new
image loading, refusal to overwrite an existing target, and rollback through
the old held handle while its image remains mapped. All children exit normally.
The report is `.local/native/mapped-image-upgrade-proof.json`; no live installation,
broker, registry, UI or unrelated process is changed by this fixture.

The file sharing/rename behavior uses Microsoft's
[CreateFile sharing contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
and [FILE_RENAME_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info).
Read-only owner discovery uses
[Restart Manager resource registration](https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmregisterresources)
and [RmGetList](https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmgetlist);
no Restart Manager shutdown/restart call is made.
Microsoft's [DLL update guidance](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-updates)
also describes retaining an old renamed DLL while existing applications finish
using it, and requires attention to shared-state and protocol compatibility.
