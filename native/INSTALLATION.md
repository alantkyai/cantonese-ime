# Persistent Windows installation

The AMD64 IME is installed at `C:\Program Files\CantoneseIME` on this Windows 10
machine. Its compact candidate UI with 1–9 labels beside candidate words was
successfully installed through the guarded mapped-DLL update; UAC execution
finished at `2026-10-22T16:33:47.6214641Z` (00:33:47 on 23 October, Hong Kong time). The protected
journal records `committed`. Existing applications were allowed to retain the
old DLL; no application was closed or killed for this update.

The installed runtime passed integrity verification and its broker was ready as
PID 68980 at the recorded check. A fresh x64 `LoadLibrary` probe, PID 17848,
successfully loaded the replacement. The installed helper independently read
back `0409` enabled before and after the update. Its default-profile query returned
Cantonese before the update and English afterward. The updater called no default
setter and no reset was performed; identical default preservation is not claimed.
These checks establish installation/runtime readiness, not the new
popup's appearance or learning behavior in an ordinary application.

**Reopen the application you want to test so it loads the new UI and selection
learning.** Existing processes may continue using the previous DLL until it
unloads. No automated post-upgrade UI check was performed, at the user's request;
the user will test the updated behavior. The existing personal learning store
was unchanged across the update; no synthetic preferences were installed.

The [numbered-candidate installation record](../docs/numbered-candidates-validation.json) and
[raw evidence directory](../docs/native-evidence/2026-10-23/numbered-choices)
retain the new package/runtime checks. Both `0409` and `0C04` machine profile
definitions and all three TSF categories remain installed. `0C04` has not been
separately enabled or tested. No language pack or login startup was installed.
The [earlier adaptive revision](../docs/adaptive-ime-validation.json) retains its
312-test Python result and learning IPC checks; those were not rerun for labels.

## Historical ordinary-app proof

The original installed DLL `f22d1c0f…eba0a2d` passed **x64 Windows Notepad typing**,
using normal Windows Ctrl+Shift input-method
cycling, individual `neihou` key events and Space to commit `你好`. Escape cancelled
a new composition; Ctrl+Space followed by `n` produced `你好n`. No process-local
profile or manual service activation was used. Popup appearance and the visible
input-selector label still await visual confirmation because screen capture
times out.

The historical [installed validation record](../docs/installed-ime-validation.json),
[key/UIA trace](../docs/native-evidence/2026-10-22/installed/notepad-key-events.json)
and [module inspection](../docs/native-evidence/2026-10-22/installed/notepad-modules-82468.json)
retain the ordinary-app evidence. The host was actual
`C:\Windows\System32\notepad.exe`, PID 82468, with both its PE header and the mapped
protected IME DLL identified as AMD64 (`0x8664`). The DLL hash was the installed
`f22d1c0f…eba0a2d`. A refreshed accessibility read confirmed exact committed text
at `2026-10-22T14:08:13.750Z`; the first immediate reads were stale. This is a
functional typing check, not a measurement of commit latency. The earlier
process-local diagnostic-host proof remains separate evidence. This historical
Notepad result is not a post-upgrade UI/learning acceptance result.

The original administrator installation completed at
`2026-10-22T13:57:53.7959235Z`. Its evidence is retained in
`C:\Program Files\CantoneseIME\machine-install.jsonl` and `installation.json`.
Every machine registration stage returned `S_OK`, including protected-path/ACL
checks, both `RegisterProfile` calls and their discovery queries. The
[non-admin enabling journal](../.local/native/installed-enable-user-0409.jsonl)
records `EnableLanguageProfile`, `InstallLayoutOrTip(flags=0)`, enabled-state
readback and the unchanged English default. The installation receipt was written
before user enabling, so its `user_enabling_complete=false` field is an initial
receipt rather than the later user-state result.

Historically, non-elevated legacy `Register` and persistent `RegisterProfile`
probes returned `0x80004005` for both input languages, leaving no project TIP
definition in either hive. A read-only check denied creating a subkey under
the machine CTF TIP root. The approved administrator installation has now
resolved that persistent-registration blocker.

Microsoft documents machine TSF definitions and separate user enabling. See
[custom IME installation guidance](https://learn.microsoft.com/en-us/windows/apps/develop/input/input-method-editor-requirements#ime-installation)
and [64-bit TSF registration](https://learn.microsoft.com/en-us/windows/win32/tsf/64-bit-platform-considerations).
There is no claim that a full Hong Kong display-language pack is necessary.
No direct, undocumented TIP registry-writing fallback is used.

## Installed package and pinned identities

The current installed files came from this retained staged package:

`D:\IME_Project\.local\native\packages\preview-20261023-numbered-choices`

Its `package-manifest.json` SHA-256 is:

`94c29cf8e9e1e5c521368a38f109ea24aaa28cecf111cff0bc734085d29d6000`

It contains 56 files / 270,402,848 payload bytes, including the existing
dictionary, engine, AMD64 DLL, runtime controller, registration helper,
installation/removal/update scripts and retained notices. The existing external
AMD64 Python is explicitly required; no compiler or Python distribution is
included. The current native DLL SHA-256 is:

`dfe90daff7339fc01437fef5c3bb28719f0c50db84789ac8e9cc403c4970e7e4`

The unchanged reviewed helper is `81c5ea2d…a5bfc987`. The dictionary and external
interpreter were preserved. Full hashes are in the package manifest and numbered
validation record. The retained original package
`preview-20261022-persistent-final` has manifest
`8d7af8fda6021d6d131eabfe5b5f4310f0b570490d9186e8369aa5fcc426c5f7`;
its earlier [persistent-integration evidence](../docs/persistent-ime-progress.json)
remains historical.

For that original package, 69 focused protocol/broker/controller tests passed.
The unchanged helper passed 18
read-only guard checks. Its desktop-account dry run and the installer `-WhatIf`
passed without machine writes. The staged runtime completed 58 actual native
client requests, repeated start reused its verified PID, and nonce-scoped stop
ended the broker cleanly. Protected installation, user enabling and ordinary
Notepad typing have since succeeded as recorded above. These earlier broker
checks remain distinct from the actual application test.

The installed registration-plan SHA-256 is:

`bf6fbe19c3955d8ba6ed9360809f5601ea25f2dc22236a41857860dc36b59de6`

The update refreshed this plan's verification hash without changing COM/profile
bindings, user enabling or LocalAppData. No default setter was called, but the
separate before/after default queries differed as recorded above. The protected backup/journal
and completed-update details are documented in [UPGRADING.md](UPGRADING.md).

## Original administrator step (historical)

The destination is `C:\Program Files\CantoneseIME`. The installer
copies only manifest-checked package files and invokes the helper to register
the fixed project CLSID, English/Hong Kong profile definitions and TSF
categories. It does not enable the IME for other accounts, change the default
keyboard, install a language pack or enable login startup.

Before the original installation, the desktop account removed its verified
preview-only HKCU COM override so it could not shadow the protected machine DLL:

```powershell
python D:\IME_Project\native\manage.py unregister-com-only
```

This was a completed preparation step. The command verifies the project's own
binding; do not recreate the HKCU COM override for the installed runtime.

The following historical command reproduces the original install in **64-bit administrator
PowerShell** on a machine without this destination. It has already run here;
rerunning it against the existing installation deliberately refuses overwrite:

```powershell
& 'D:\IME_Project\native\Install-NativeIme.ps1' `
  -PackageRoot 'D:\IME_Project\.local\native\packages\preview-20261022-persistent-final' `
  -ManifestSha256 8d7af8fda6021d6d131eabfe5b5f4310f0b570490d9186e8369aa5fcc426c5f7
```

Adding `-WhatIf` performs only the package/destination review and does not
require an elevated token. The script does not request or automate UAC. A
failed registration retains diagnostics and DLL files if rollback is uncertain;
inspect its journal before retrying or removing anything.

## Current-user verification, runtime and application test

The `0409` profile is already enabled for the intended **non-administrator
desktop account**. Query its current state with the installed helper. The plan refers
only to the protected installed DLL, so future removal does not depend on the
staging directory remaining present.

```powershell
& 'C:\Program Files\CantoneseIME\native\CantoneseMachineRegistration.exe' `
  --action inspect-user --language 0409 `
  --manifest 'C:\Program Files\CantoneseIME\machine-registration.plan' `
  --manifest-sha256 bf6fbe19c3955d8ba6ed9360809f5601ea25f2dc22236a41857860dc36b59de6

python 'C:\Program Files\CantoneseIME\native\runtime\control.py' start `
  --config 'C:\Program Files\CantoneseIME\runtime-config.json'
```

The helper uses documented user-enable APIs, including `InstallLayoutOrTip`,
without a default-setting flag. To reproduce the completed enabling step, use
the same helper/plan arguments with `--action enable-user --language 0409`.
The English-language profile supports the already installed input language;
`--language 0c04` is a separate supported enablement to test for Hong Kong language
availability. User actions reject an elevated token.

For the user's manual post-upgrade check, close/reopen the testing app or open a
fresh x64 Notepad, select the IME through
Windows (Ctrl+Shift cycling worked in the recorded test), and type `neihou`,
then Space. Confirm `你好`, cancel a new composition with Escape, and toggle
English with Ctrl+Space. The historical saved test used actual individual key events rather
than Chinese paste or direct document-value setting. A refreshed accessibility
read verified the committed text, and independent module inspection verified the
protected baseline x64 DLL in Notepad. The updated popup and selection-learning
behavior are left for the user's testing; no new automated UI check is claimed.
Historical visual confirmation of the popup and selector label
is still pending; the functional result does not establish their appearance or
compatibility with every application.

Login startup is not installed. `control.py print-login-command` emits a command
for separate review; explicit broker start is required until startup is enabled.

## Removal

In the non-admin account, use the same installed helper/plan arguments with
`--action disable-user` for each enabled language, then run the controller's
`stop` command and close applications using the DLL. In administrator
PowerShell, this command removes only verified project machine COM/TSF definitions:

```powershell
& 'C:\Program Files\CantoneseIME\native\Remove-NativeIme.ps1' `
  -RegistrationPlanSha256 bf6fbe19c3955d8ba6ed9360809f5601ea25f2dc22236a41857860dc36b59de6
```

Add `-WhatIf` to review without changes. Runtime files are retained so no loaded
DLL or unrelated file is removed automatically. Machine installation, user
enabling and ordinary Notepad use have been exercised; the complete removal
lifecycle remains unverified. Disabling a profile the user made their default may cause
Windows to select a fallback; the helper never requests a default-setting API.
