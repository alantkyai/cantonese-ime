# Windows x64 TSF frontend

These project-authored C++17 sources implement Cantonese IME's in-process Windows
Text Services Framework (TSF) frontend. The DLL uses the offline Python engine
through the [native protocol](../PROTOCOL.md). It has no network dependency or
third-party C++ library dependency.

The **1.0.5 Windows x64 release** provides a standard installer with a private
Python runtime, protected machine registration and ordinary-user Hong Kong input
source setup. See the [release notes](../../docs/RELEASE_NOTES_1.0.5.md),
[validation record](../../docs/release-1.0.5-validation.json) and
[installer guide](../../installer/GETTING_STARTED.txt).

Installation, profile discovery, payload integrity and broker readiness have
been checked on Windows 10 Pro 22H2 x64. Historical native composition and ordinary
Notepad typing evidence is retained separately. Current visual acceptance,
clean-machine installation, Windows 11 and the full uninstall/sign-in lifecycle
remain separate checks. x86, ARM64, elevated/secure contexts and AppContainer
compatibility are outside the verified desktop scope. The macOS source port
requires its own native build and validation.

## Source layout

- `tsf.cpp`: COM lifetime, `ITfTextInputProcessorEx`, keyboard handling, edit
  sessions, composition, display attributes, focus/layout handling and the
  nonactivating candidate window. `ITfCandidateListUIElementBehavior` exposes the
  loaded page to a host that renders candidates itself.
- `candidate_layout.h`: measured, DPI-aware candidate sizing, wrapping, work-area
  placement and mouse hit rectangles.
- `input_mode_button.h`: the TSF input-mode button with Cantonese **粵** and
  English **英** states, click handling and change notifications.
- `ipc.cpp` / `ipc.h`: bounded framing, strict UTF-8 checks, matching request IDs,
  same-user server verification and overlapped named-pipe I/O.
- `registration.cpp`: legacy `DllRegisterServer` / `DllUnregisterServer`
  development exports. The standard installer uses the separate
  [machine registration helper](../registration/README.md).
- `ime_ids.h`: stable project CLSID, profile, display and candidate GUIDs.
- `CantoneseIME.rc`, `resource.h` and `icons/`: DLL resources and version metadata.

Document changes occur only in granted TSF edit sessions. Lookup finishes before
requesting the document write session. Disabled/read-only contexts and an
explicit password input scope are checked before sending a request; host-specific
security and input-scope behavior still needs compatibility testing.

## Typing and learning

Plain Yale or Jyutping letters begin a forgiving composition. Apostrophes mark
syllable boundaries; Backspace edits the buffer, up to 256 ASCII characters.
The compact popup shows numbered candidate words, without readings, a raw-input
heading or instructions. It wraps within the available work area and hides when
there are no candidates. The editor's phonetic preedit remains separate.

| Key | Action |
| --- | --- |
| Space | Commit the highlighted candidate |
| 1–9 | Commit the corresponding visible candidate |
| Up / Down | Move the highlight |
| PageUp / PageDown | Navigate candidate pages |
| Enter | Commit the literal Latin buffer |
| Escape | Cancel the composition |
| Ctrl+Space or the mode button | Switch Cantonese / direct English input |

Switching mode completes an active raw Latin buffer first. Shift/Caps Lock
uppercase, Ctrl/Alt/Windows shortcuts and unsupported keys pass through. The
Windows input selector can switch to another keyboard. Digit keys select
candidates; numeric-tone lookup is available through the engine/protocol API.
The frontend currently uses forgiving mode; strict Jyutping is supported by the
protocol for future settings integration.

The installed broker enables local selection and phrase learning at
`%LOCALAPPDATA%\CantoneseIME\learning.json`. Successful selected-candidate commits
queue best-effort notifications on a bounded FIFO worker outside the TSF input
thread. Literal commits, cancellation and focus-departure completion do not learn.
A failed save does not undo committed text. The engine can reuse learned
constituents in longer compositions while preserving full-input phrase choices.
Upgrades and uninstall retain the separate personal store.

Lookup failures leave composition recoverable through Enter or Escape; a failed
page fetch retains the current page and selection. Native I/O shares a 250 ms
request deadline, with cancellation drained before releasing its `OVERLAPPED`
state. This bound is not a guarantee of end-to-end typing latency. Focus departure
requests completion of the raw text and hides candidate UI.

## Build from source

Use an AMD64 Windows C++17 toolchain with Windows headers/import libraries. The
retained LLVM-MinGW build uses no ATL, WRL or MSVC-only language extensions. From
the repository root:

```powershell
& .\native\tsf\build.ps1 `
  -Compiler 'C:\path\to\llvm-mingw\bin\x86_64-w64-mingw32-clang++.exe' `
  -OutputDirectory .\.local\native\build-x64
```

The script compiles and links the icon/version resource. For the equivalent
manual build, run in `native/tsf` with the toolchain on PATH:

```text
llvm-rc /fo CantoneseIME.res /i C:\path\to\llvm-mingw\include CantoneseIME.rc
x86_64-w64-mingw32-clang++ -std=c++17 -O2 -Wall -Wextra -DUNICODE -D_UNICODE -DWIN32_LEAN_AND_MEAN -DNOMINMAX -D_WIN32_WINNT=0x0A00 -DWINVER=0x0A00 -shared -static -Wl,--no-undefined -Wl,--dynamicbase -Wl,--nxcompat tsf.cpp ipc.cpp registration.cpp tsf_guids.cpp CantoneseIME.def CantoneseIME.res -o CantoneseIME.dll -lole32 -loleaut32 -luuid -luser32 -lgdi32 -ladvapi32
```

The C++ runtime is linked statically; Windows APIs remain ordinary imports. The
current CMake target omits the `.rc` resource and is a development source build,
so use the resource-aware PowerShell workflow for release packaging. Retain PE
architecture, dependency and source/artifact hash checks with each build.
Building these sources does not register an IME or change input preferences.

The 1.0.5 bundle intentionally reuses the typing DLL whose embedded version is
1.0.2. Package/helper changes have their own release version. Existing processes
can retain an older mapped image after upgrade, even when its canonical disk
path now contains the latest DLL. Verify a fresh process or the mapped image's
identity when checking which code is running.

## Installation and development diagnostics

Run the standard installer normally and approve its administrator prompt. It
places the bundle under `C:\Program Files\CantoneseIME`, registers the machine COM
service and two fixed TSF profiles, then configures the intended ordinary user's
Hong Kong input source. The `0409` profile is retained as a legacy definition;
normal setup disables that product entry after proving `0C04` ready, unless an
explicit default override requires retaining it. English US and unrelated input
methods and settings are preserved.

The service DLL remains the COM server. In 1.0.5, branding comes from resource
101 in the protected registration helper EXE, using registered location `-101`.
This separates branding from an old service DLL image retained by a long-lived
host. Mode icons remain in the service DLL. Upgrade handling retires mapped DLL
and helper files without closing applications; application restart may still be
needed to use new frontend code.

`DllRegisterServer`, the diagnostic host and manual registration probes are
**development tools**. They do not replace the release installer or its guarded
upgrade/removal workflow. See [registration details](../registration/README.md).
The release is unsigned. Windows 11, AppContainer, other architectures and full
accessibility/lifecycle acceptance must be reported only after their own tests.

## Primary API references

- [TSF activation](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nn-msctf-itftextinputprocessorex)
- [Edit sessions](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfcontext-requesteditsession)
- [Composition](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfcontextcomposition-startcomposition)
- [Candidate UI](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nn-msctf-itfcandidatelistuielementbehavior)
- [Text bounds](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfcontextview-gettextext)
- [Custom IME requirements](https://learn.microsoft.com/en-us/windows/apps/develop/input/input-method-editor-requirements)
