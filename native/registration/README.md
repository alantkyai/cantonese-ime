# Windows x64 registration and lifecycle

Cantonese IME **1.0.5** uses the standard Windows installer to place its private
runtime under `C:\Program Files\CantoneseIME`, register protected machine COM/TSF
definitions and configure the original ordinary user's input source. The upgrade
completed on the Windows 10 x64 test PC; installed files, both profile identities,
four category memberships, current-user settings and engine readiness passed
read-back checks. See the [release notes](../../docs/RELEASE_NOTES_1.0.5.md) and
[validation record](../../docs/release-1.0.5-validation.json).

Users should follow the [installer guide](../../installer/GETTING_STARTED.txt).
Run Setup normally and approve its administrator prompt so the ordinary-user
activation step runs in the intended account. The package includes its own Python
runtime. Upgrades and uninstall preserve personal learning outside Program Files.
Clean-machine, Windows 11, sign-in startup and full uninstall acceptance remain
separate checks. These Windows tools do not install or validate the macOS port.

## Registration model

The project owns one service CLSID and one profile GUID:

```text
CLSID  {67718E6F-49A1-4F54-88D6-30578FC70C5D}
Profile {A7136205-2245-45CC-A6AA-702B3F2E8D42}
```

The machine definition contains `0C04` (Hong Kong Traditional Chinese) and `0409`
(legacy English-slot Cantonese) profiles. The five categories are keyboard,
display-attribute provider, candidate UI element, system-tray support and
immersive support (`GUID_TFCAT_TIPCAP_IMMERSIVESUPPORT`). Without the immersive
category Windows hides the input source in some packaged hosts, for example the
Microsoft Store WhatsApp client. `refresh-registration` adds it to an existing
four-category installation; removal follows persisted membership.

The separate, non-elevated user step adds the owned Hong Kong TIP to the existing
language list, or appends a Hong Kong language entry if needed. It proves that
source ready before disabling only the owned legacy `0409` TIP. An explicit
default override targeting that legacy entry keeps it enabled. English US,
unrelated keyboards, language order/properties and explicit UI/default overrides
are preserved. No Windows display-language pack is downloaded.

The low-level helper uses `EnableLanguageProfile` and `InstallLayoutOrTip` for
user enabling. The installer migration uses the typed Windows user-language-list
API for the language container. Neither workflow calls a default-setting API.
Windows can choose a fallback when a previously default profile is disabled;
observed default-profile tuples are retained separately from explicit overrides.

## Helper and branding resources

`machine.cpp` builds `CantoneseMachineRegistration.exe`. Its default action is a
read-only dry run. Machine mutations require an already elevated token; user
actions require the intended non-elevated account. The helper does not request
UAC, copy package files, launch the text service or activate a profile.

The COM server remains `native\CantoneseIME.dll`. Modern profile branding uses
resource 101 in the separate, protected
`native\CantoneseMachineRegistration.exe`, registered as signed location `-101`
(`DWORD 4294967195`). Start-menu and uninstall icons use that EXE's ordinal 0.
Mode icons remain in the service DLL.

This separation handles a demonstrated upgrade condition: Explorer retained an
older executable mapping of the service DLL with no branding resource, and
resource-load calls reused that image despite newer bytes on disk. A separate
EXE resource container loaded successfully in the same Explorer. Actual picker
appearance is a separate visual acceptance check.

Before an actual install/refresh write, the helper verifies its fixed executing
path, protected owner/DACL, resolved non-reparse directory/file paths, AMD64 EXE
format and all required branding icon sizes. Old installations remain inspectable
and removable through read-only/removal actions. A refresh restores prior icon
path, raw index and enabled flags on failure.

The installer backs up and retires both the service DLL and helper EXE before
replacement. This permits existing mappings to remain alive. Durable rollback
intents precede either rename; rollback handles a partial move, skips already
correct old files and retires a differing mapped replacement before restoring
protected backups. No application or Explorer process is forcibly closed.

## Low-level build

From the repository root with the retained LLVM-MinGW AMD64 toolchain:

```powershell
& .\native\registration\build.ps1 `
  -Compiler 'C:\path\to\llvm-mingw\bin\x86_64-w64-mingw32-clang++.exe' `
  -OutputDirectory .\.local\native\build-x64
```

`llvm-rc.exe` must be beside the compiler. The build links `branding.rc`, which
embeds the existing brand ICO. Keep the helper's artifact hash, argument-guard
report and source/resource test pins together. A successful build or dry run
alone does not establish installation or native typing.

## Pinned machine plan

The helper accepts a flat UTF-8 file **without a BOM**, with exactly these six
fields and a separately reviewed SHA-256 supplied on the command line:

```text
CANTONESE_IME_MACHINE_V1
clsid={67718E6F-49A1-4F54-88D6-30578FC70C5D}
profile={A7136205-2245-45CC-A6AA-702B3F2E8D42}
languages=0409,0c04
dll_source=C:\Program Files\CantoneseIME\native\CantoneseIME.dll
dll_target=C:\Program Files\CantoneseIME\native\CantoneseIME.dll
dll_sha256=<reviewed DLL SHA-256>
```

The release installer writes this protected installed plan and records its hash
in `installation.json`. A staged source path can be used for development
preflight; actual install/refresh requires the executing helper at its fixed
protected installed path. The plan does not accept an arbitrary branding path.
The source DLL is read and hashed, not copied or executed by the helper.

The target is limited to `CantoneseIME.dll` under the actual 64-bit Program Files
`CantoneseIME` directory or its `native` subdirectory. The installed target must
match its pinned AMD64 DLL digest. Product directories/files require a protected
owner (Administrators, SYSTEM or TrustedInstaller), no effective unprivileged
allow-write ACE and matching final paths. Junctions/reparse points and unknown
effective ACE types are refused. Verified handles remain open during mutations.
The helper does not set ACLs.

## Actions and inspection

| Action | Token and behavior |
| --- | --- |
| `dry-run` | Read-only plan/file checks; an absent pre-copy target can be reported as pending |
| `dry-run-refresh` | Read-only exact binding, persistent category and existing profile metadata checks |
| `dry-run-remove` | Read-only removal preflight |
| `install` | Elevated fresh registration; refuses existing machine COM/TIP namespaces |
| `refresh-registration` | Elevated update of the two exact profiles and owned categories; preserves current-token enabled flags |
| `remove` | Elevated removal of only the fixed profiles/categories; retains COM/files on unresolved failures |
| `inspect-user` | Non-elevated profile, enabled-state and default-metadata queries |
| `enable-user` / `disable-user` | Non-elevated owned-profile enabling/disabling and input-list update |

For example, after verifying the installed plan hash against the installation
receipt, inspect the Hong Kong profile without changing it:

```powershell
$helper = 'C:\Program Files\CantoneseIME\native\CantoneseMachineRegistration.exe'
$plan = 'C:\Program Files\CantoneseIME\machine-registration.plan'
$pin = '<verified registration_plan_sha256 from installation.json>'
& $helper --action inspect-user --language 0c04 --manifest $plan --manifest-sha256 $pin
& $helper --action dry-run-refresh --manifest $plan --manifest-sha256 $pin
```

`enable-user` and `disable-user` require `--language 0409` or `--language 0c04`.
They verify the protected DLL, exact machine COM binding and profile identity.
Normal HKCU TIP enablement preferences are supported; an HKCU COM override is
refused. A failed input-list operation attempts restoration of the prior enabled
flag and logs the result; it does not claim an atomic layout-list transaction.

Fresh registration calls `RegisterProfile(flags=0, bEnabledByDefault=FALSE)` and
category APIs, then checks both profile identities and icon metadata. Refresh
also verifies both directions of persistent category membership. Fresh COM
category enumeration is logged separately because a cached view previously
omitted a just-registered category. A failed fresh install removes the new COM
key only when rollback succeeds and the owned TIP namespace is confirmed absent.
Refresh rollback preserves original metadata. Every stage logs its raw HRESULT.
No direct CTF TIP registry-writing fallback is used.

Use the standard uninstaller for package removal. The low-level `remove` action
unregisters only fixed identities through TSF APIs, verifies the persistent
namespace is gone and then removes the exact COM binding. It never uses an
all-profiles removal flag or recursively deletes the TIP tree. File cleanup,
user startup cleanup and learning retention belong to the installer lifecycle.
Mapped files can require a later application exit or Windows restart. Exact
startup values in unloaded user profiles can remain; full live uninstall testing
is still pending.

## Historical development diagnostics

`diagnostic.cpp`, `DllRegisterServer` and the custom test host are development
probes, separate from the standard installer. Early non-elevated legacy
`Register` and persistent `RegisterProfile` attempts failed on the test PC;
subsequent machine registration and separate user enabling succeeded. The early
process-local `0409` typing proof and installed Notepad proof retain their
original versions and scope in the
[historical native evidence](../../docs/NATIVE_X64_VALIDATION.md).

The diagnostic executable never activates a service or opens UI. Its default
`inspect` action reads project-owned COM/TIP presence and profile-manager state.
Explicit `register-legacy` and `register-profile` actions reproduce the early
non-elevated probes, require an exact pre-existing current-user COM binding and
refuse existing project TIP definitions. They log attempted rollback and retain
the existing COM binding/files. They are unsuitable for upgrading an installed
release. The DLL's legacy registration export similarly uses a current-user COM
class and `AddLanguageProfile`; it is not the release registration entry point.

Historical inspection syntax:

```text
CantoneseRegistrationDiagnostic.exe --action inspect --langid 0x0c04
```

## Primary references

- [Custom IME installation](https://learn.microsoft.com/en-us/windows/apps/develop/input/input-method-editor-requirements#ime-installation)
- [RegisterProfile](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfinputprocessorprofilemgr-registerprofile)
- [InstallLayoutOrTip](https://learn.microsoft.com/en-us/windows/win32/tsf/installlayoutortip)
- [64-bit TSF registration](https://learn.microsoft.com/en-us/windows/win32/tsf/64-bit-platform-considerations)
- [Resource loading and existing executable mappings](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryexw)
