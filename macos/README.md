# Cantonese IME for macOS

The Mac version uses an InputMethodKit app with the same offline engine, dictionary, numbered candidates, and local phrase learning as the Windows version. It targets **macOS 13 or later**, with native Apple Silicon and Intel slices in one universal2 app.

The source archive can be prepared on Windows. A runnable `.app` and an Installer `.pkg` must be built and checked on a Mac with the macOS SDK. A source ZIP is not a Mac installer, and a successful Windows engine test does not confirm native Mac input behavior.

## Installing a built package

Open `CantoneseIME-1.0.0-macos-universal2.pkg` and follow the standard macOS Installer. It installs only `/Library/Input Methods/CantoneseIME.app`, including a private Python runtime. The receiving Mac needs no Python installation, Homebrew, or developer tools.

Then open **System Settings → Keyboard → Text Input → Edit**, add **Cantonese IME**, and select it from the input menu. If it is not listed, sign out and sign in before trying again. Activation belongs to your account; the installer does not change input sources, the default keyboard, or login items as root.

Type `fogeui` for 火炬. Use the numbers beside candidates to choose them. Choosing `ng` as 唔 also helps combinations such as `ngho` as 唔好 and `nghaigam` as 唔係咁. Whole-phrase choices are remembered separately, so shorter and longer inputs can have different preferred choices.

Personal learning stays at `~/Library/Application Support/CantoneseIME/learning.json`. The installer and build scripts do not read, copy, reset, or remove that file.

Before upgrading, switch to another input source and quit Cantonese IME. Other signed-in users must do the same or sign out. The installer refuses to replace a running IMK server or its engine and does not force applications to quit.

For removal, first remove Cantonese IME from your Keyboard input sources, switch to another input source, and quit the IME or sign out. An administrator can then remove **only** `/Library/Input Methods/CantoneseIME.app` in Finder. Learning is retained. Package receipts may remain in macOS; deleting a receipt is not an application uninstall.

## Building on a Mac

Building needs **Python 3.11+ and Xcode 15.3+ command-line tools**, including Swift 5.10 or later. These are build-machine requirements. The app includes its own runtime for users.

The source archive contains the pinned shared engine under `engine/`, the official Python universal2 package under `dependencies/`, and all Mac source under `macos/`. The Python package is an offline build input: the builder extracts its framework with `pkgutil` and never runs the Python installer or installs a system framework.

From the extracted source archive:

```sh
python3 macos/build_release.py --output dist/macos-local
```

This creates an ad hoc signed app and an unsigned local testing PKG. It is **not a notarized public distribution**. Do not disable Gatekeeper or remove quarantine attributes to make a release appear approved.

For a public release, supply your own installed Apple signing identities and a previously configured notarytool keychain profile:

```sh
python3 macos/build_release.py \
  --output dist/macos-release \
  --application-identity 'Developer ID Application: Your identity' \
  --installer-identity 'Developer ID Installer: Your identity' \
  --notary-profile 'your-existing-keychain-profile'
```

The builder signs nested code from the inside out, signs the app with Developer ID Application, signs the package with Developer ID Installer, submits it with `notarytool`, requires an Accepted result, staples the ticket, and checks the package with Gatekeeper. It never creates certificates, stores account passwords, or invents a signing identity. Signing and notarization can require network access and access to your own keychain.

Always test the resulting package on a separate Mac/account without a developer Python installation, including Apple Silicon and Intel, typing in ordinary native apps, input-menu switching, learning across restarts, upgrades, and removal. Build hashes and native compilation are recorded in `macos-build.json`; visual typing acceptance is separate.

## Preparing the source archive from this repository

The default input is the existing validated Windows release payload. Only its shared Python engine, dictionary/mappings, and upstream data notices are copied. Windows executables, runtime, registry tools, and installers are omitted. Their original manifest hashes are verified; no Windows PE compiler or registration helper is run for this source staging.

```powershell
python macos/build_release.py --source-only --fetch-runtime --output dist/CantoneseIME-1.0.0-macos
```

If using another engine snapshot, supply `--engine-package` and its original `--engine-manifest-sha256`. `--python-pkg` can name the already downloaded official universal2 package. No network is needed when that pinned input is present.

The source ZIP contains the full offline dictionary and Python build input. Every archived file is checked against its original staged hash after writing, and `SHA256SUMS.txt` identifies the archive to copy to the Mac.

## Private runtime layout and provenance

The native launcher is `Contents/MacOS/CantoneseIMEEngine`. It uses CPython's isolated initialization API with explicit paths to `Contents/Frameworks/Python.framework`, ignores environment and user site packages, and disables bytecode writes. The Swift IMK frontend owns a private length-framed stdin/stdout child process; it does not create a global service or socket. The dictionary hash is pinned in the app's Info.plist.

The original Python framework contains absolute `/Library/Frameworks` load paths. The Mac build rewrites every bundled Mach-O dependency to the private framework, adds a relative loader search path, requires both architecture slices, and signs the modified code afterward. Copying the original Python executable alone would not provide a self-contained runtime.

The builder retains the original Python license material and all dictionary attributions. See `macos/installer/License.txt` and `engine/data/THIRD_PARTY_NOTICES.md`. No new redistribution license for the project's original application code is imposed.

Primary references: [Python universal2 distribution](https://docs.python.org/3.13/using/mac.html), [isolated embedding](https://docs.python.org/3.13/c-api/init_config.html), [Apple nested code signing](https://developer.apple.com/library/archive/technotes/tn2206/_index.html), [Developer ID and notarization](https://developer.apple.com/developer-id/), and [Installer Distribution XML](https://developer.apple.com/library/archive/documentation/DeveloperTools/Reference/DistributionDefinitionRef/Chapters/Distribution_XML_Ref.html).
