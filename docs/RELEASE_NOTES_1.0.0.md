# Cantonese IME 1.0.0

The distributable is built and its automated checks passed. The local Windows administrator prompt was canceled before installation; the prior IME is still running and personal learning is unchanged. Run the final setup and approve its Windows prompt to install this release.

[Windows x64 setup](../dist/CantoneseIME-1.0.0-x64/CantoneseIME-1.0.0-windows-x64-setup.exe)
· [SHA-256 checksums](../dist/CantoneseIME-1.0.0-x64/SHA256SUMS.txt)
· [Validation record](release-1.0.0-validation.json)

The single offline installer is 84,531,930 bytes (about 81 MiB). Its SHA-256 is
`4910f193e8850b8923816d11a3cebb5afc2c88d1efef7ff02c2e377a11c025e2`.
It is unsigned; Windows can show an unknown-publisher or SmartScreen warning.

## Changes

- Replaced Preview branding with Cantonese IME 1.0.0 and embedded native icons.
- Added a native **粵 / 英** mode button. Click it or use Ctrl+Space to switch.
- Kept the compact candidate popup with numbers 1–9 beside the words.
- Added learned constituents to longer composition before candidate pruning.
  Selecting `ng` → 唔 now helps find 唔好 for `ngho` and 唔係咁 for `nghaigam`.
  The mechanism also works with other complete selected words and phrases;
  choices for a full input retain their separate stronger preference.
- Added an application-local Python 3.13.17 runtime, standard setup/uninstall,
  Start menu controls and optional per-user startup at sign-in.

The dictionary and spelling-map bytes are unchanged: 776,335 text/pronunciation
pairs across 644,427 texts. Existing personal learning uses the same file and
schema. No synthetic test preferences were copied into the user's store.

## Install and use

Run Setup normally, approve its Windows administrator prompt, and choose
whether the engine should start at sign-in. Then use Win+Space to select
**Cantonese IME**. Reopen existing applications after upgrading so they load the
new DLL. Some Windows shell icon caches can require sign-out/sign-in.

Use Start menu > Cantonese IME to enable or stop the engine. Use Windows
Settings > Apps to uninstall. Learning remains at
`%LOCALAPPDATA%\CantoneseIME\learning.json`; uninstall keeps it. The uninstaller
removes exact owned startup commands from loaded user hives; a startup value in
an unloaded user profile may remain. Other active engine sessions must be
stopped or signed out before replacing or uninstalling their runtime files.

## Verification and remaining checks

Passed: **592 Python tests** with no failures, errors or skips; 14 targeted tests
against the final installer lifecycle; **34 real native x64 lookup cases**,
including the learned `ng` phrases; native learning/restart; fresh x64 DLL load;
COM mode button, notifications, teardown and eight icon sizes; 18 registration
manifest guard cases; and 84 old/new no-learning candidate comparisons.
All 120 final payload files are pinned and rechecked. Test learning is isolated.

Windows taskbar appearance and ordinary application typing remain assigned to
the user. A clean Windows VM, a Windows 11 machine, live end-to-end uninstall,
sign-in startup and alternate administrator credentials have not been tested.
The implemented platform scope is Windows x64 with native 64-bit desktop text
applications; 32-bit applications, ARM64 and secure/password fields are excluded.
The offline bundle is self-contained, but that is not presented as a clean-VM
installation result.

The previous exhaustive finite-catalog scan remains a
[historical proof](final-yale-catalog-coverage.json) for its exact engine bytes.
The new personalized decoder was not subjected to a new full-catalog scan.
Pronunciation, segmentation and general language-model quality remain ongoing
work; generated readings are identified in the dictionary provenance.

The initial runtime-path candidate was rejected before installation. The
Windows-native path policy was independently checked, the setup was rebuilt,
and the corrected bundle passed native checks. Failed bytes and evidence are
retained separately, not distributed as the final release.

Dictionary licenses, full component notices and attribution are included;
see [data licensing](../data/DATA_LICENSE.md) and
[release notices](../installer/RELEASE_NOTICES.txt).
