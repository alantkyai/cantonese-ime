# Cantonese IME 1.0.5

The first public release of Cantonese IME provides offline Cantonese input for
native Windows x64 desktop applications.

## Download and install

Download **CantoneseIME-1.0.5-windows-x64-setup.exe** from this release, run Setup
and approve the administrator prompt. The installer contains its own Python
runtime and dictionary; installation does not need system Python or Internet
access. The package is unsigned, so Windows may show an unknown-publisher or
SmartScreen notice.

Press **Win+Space** and choose **Cantonese IME** under **Chinese (Traditional,
Hong Kong SAR)**. Type `fogeui` for 火炬 or `neihou` for 你好. Space commits the
highlighted word, 1–9 select numbered choices, Escape cancels, and Ctrl+Space
switches Cantonese/English mode.

After an upgrade, restart applications fully so they load the new IME DLL.
For Chrome, save unfinished forms and enter `chrome://restart` in the address
bar. Closing browser windows can leave its background process running.

## Included

- Plain Yale-style and Jyutping letter input.
- Compact numbered candidates and personal word/phrase learning.
- Offline dictionary with 776,335 text/pronunciation pairs across 644,427 texts.
- Native Windows TSF integration and Cantonese/English mode controls.
- Standard installer, Start menu controls and Windows uninstall entry.
- Upgrades and uninstall preserve personal learning.

Version 1.0.5 stores the branding icon separately from the typing DLL so an older
DLL mapping cannot shadow its replacement icon resource. Upgrade and rollback
also handle mapped registration-helper executables. The native typing component
retains its existing 1.0.2 file version; the installer/package version is 1.0.5.

## Verification and scope

The exact installer completed successfully on the Windows 10 x64 development
PC. All 121 installed payload hashes and nine installation checks passed.
The 44 focused installer/package tests passed, including two actual Windows
resource-mapped upgrade/rollback cases. Native checks covered both profile icon
references, 12 resource matches, 15 category fixtures and 18 registration guards.
The user confirmed working Chrome input after a full browser restart.

Support is scoped to native 64-bit desktop applications on Windows x64. Windows
11 and clean-machine acceptance, sign-in startup and end-to-end uninstall remain
pending. 32-bit applications, ARM64 and secure/password fields are outside this
release. Picker pixels have not been independently captured after the update.

The repository also contains the macOS InputMethodKit port and build
instructions. Native Mac compilation, installation and typing checks remain
pending; this release does not include a ready-to-install Mac package.

## Integrity and licensing

Installer SHA-256:

```text
e23a936f5c5bcf38ff74f1874ad3143b63ada893cc1cc151188e63a6c5e23c58
```

`SHA256SUMS.txt` covers the installer and `package-manifest.json`. The latter
lists all installed payload hashes. The published installer is the already
tested artifact, rather than a new build for this upload.

Dictionary material retains its original component notices and licenses; the
combined transformed dictionary adaptation is distributed under CC BY-SA 4.0.
See `data/DATA_LICENSE.md`, `data/THIRD_PARTY_NOTICES.md` and the retained license
texts. Original application code has no general redistribution license
declaration; public source availability does not assign it a new license.

Local compiler caches, generated databases, personal learning and machine-specific
verification logs are excluded from Git. Retained dictionary source snapshots,
source locks, attribution, engine tests and build scripts are included.
