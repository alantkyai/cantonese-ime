# Native x64 Cantonese IME validation

The project must demonstrate Cantonese composition through a native AMD64 TSF text service in a verified AMD64 Windows application. Browser input, a working conversion harness, and a 64-bit conversion server do not establish this result.

## Current result

**The compact popup with 1–9 candidate labels is installed.**
The approved update committed at `2026-10-22T16:33:47Z` (23 October in
Hong Kong) on Windows 10 Pro
22H2 AMD64 build 19045.6466. Its protected runtime is under
`C:\Program Files\CantoneseIME`. The `0x0409` profile remains enabled for the
desktop account, and the `0x0c04` machine definition remains registered. No login
startup was added. The updater made no registry writes or default-setting calls.
Separate default-profile queries reported Cantonese before the update and English
afterward; identical default preservation is not claimed, and no reset was made.

| Current revision check | Result |
| --- | --- |
| Installed package manifest SHA-256 | `94c29cf8e9e1e5c521368a38f109ea24aaa28cecf111cff0bc734085d29d6000` |
| Installed AMD64 DLL SHA-256 | `dfe90daff7339fc01437fef5c3bb28719f0c50db84789ac8e9cc403c4970e7e4` |
| Installed registration-plan SHA-256 | `bf6fbe19c3955d8ba6ed9360809f5601ea25f2dc22236a41857860dc36b59de6` |
| Engine verification | Engine unchanged; prior 312-test suite not rerun for the label-only change |
| Native build/layout geometry | Build passed; label-inclusive sizing, wrapping, DPI, selected-row viewport, label-area mouse selection and work-area clamps passed |
| Native learning IPC | Previous adaptive revision's short/long-input and restart checks retained; not rerun for labels |
| Fresh native load | New x64 probe PID 17848 loaded the updated DLL; this is load verification, not a typing test |
| Personal state | Personal learning-store SHA-256 unchanged; registration definitions retained |
| Current typing and visual checks | Assigned to the user by explicit request; no new Notepad/UI test claimed for this revision |

The [current numbered-popup validation](numbered-candidates-validation.json)
records this update. The [previous adaptive revision](adaptive-ime-validation.json) and
[engine checks](native-evidence/2026-10-22/adaptive-compact/engine-checks.json)
its saved checks remain historical engine evidence. The raw
[native learning run](native-evidence/2026-10-22/adaptive-compact/native-learning.json)
and [restart readback](native-evidence/2026-10-22/adaptive-compact/native-learning-after-restart.json)
explicitly distinguish IPC verification from TSF typing proof.

The popup now paints each candidate word beside its 1–9 selection number in a
compact measured row that wraps. Measurement and painting use the same label.
It omits the raw-input heading, readings and instructions. The earlier
words-only layout is historical.
Keyboard selection and paging remain. The editor's phonetic composition is
separate from the popup. Successful candidate commits queue best-effort local
learning outside the input thread, including learned phrases. The installed
broker enables the existing per-user learning file; isolated tests did not
populate the user's personal store.

Existing applications may continue executing the previous mapped DLL after this
in-place update. Restart an application before checking the new UI and learning.
An old process can retain the canonical module filename while that disk path now
contains the new DLL: hashing the canonical path alone does **not** establish
which revision that old process executes. Use a fresh process started after the
update, or independent mapped-image identity evidence.

At the user's request, actual typing, candidate appearance and caret-placement
checks of this revision are left to them. The historical Notepad pass below is
retained without treating it as a new-layout or adaptive-commit test. Login
startup, Hong Kong-language activation, other application/architecture support
and the full removal lifecycle remain separately unverified.

## Historical installed Notepad proof (previous DLL)

The previous installed DLL, `f22d1c0f…eba0a2d`, produced Cantonese typing in ordinary x64 Notepad. On 22 October 2026, the first approved administrator installation placed that runtime under `C:\Program Files\CantoneseIME`. Machine COM, both language-profile definitions (`0x0409` and `0x0c04`) and the project's TSF categories were registered. The intended non-administrator desktop account enabled `0x0409`; its existing English default remained unchanged.

Fresh Notepad PID 82468 loaded the protected installed DLL. Ordinary Windows Ctrl+Shift input-method cycling, followed by individual ASCII key events, produced Cantonese text, cancellation without extra committed text, and literal English input. This test used neither process-local registration nor `ActivateEx`. The [installed validation record](installed-ime-validation.json), [Notepad module inspection](native-evidence/2026-10-22/installed/notepad-modules-82468.json) and [actual key-event observations](native-evidence/2026-10-22/installed/notepad-key-events.json) preserve the result.

| Observed check | Installed Notepad result |
| --- | --- |
| Host process | `C:\Windows\System32\notepad.exe`, PID 82468, PE `0x8664` |
| Actual loaded project DLL | `C:\Program Files\CantoneseIME\native\CantoneseIME.dll`, PE `0x8664`, SHA-256 `f22d1c0f376e1aa93908bdc7420374d36fe35ed78c6e018e0086fd34aeba0a2d` |
| Windows input-method selection | Ordinary Ctrl+Shift cycling before typing; no test-host activation or temporary profile |
| Input provenance | Individual Computer Use `press_key` events; no Chinese paste, `type_text`, value replacement or direct editor text injection |
| Commit | `n`, `e`, `i`, `h`, `o`, `u`, then Space produced `你好`, confirmed by refreshed Notepad accessibility text |
| Cancel | After `b`, Escape left committed text unchanged at `你好` |
| English mode | Ctrl+Space followed by `n` produced literal `你好n` |
| Notepad preedit and candidate contents | Not exposed by the captured Notepad accessibility observations; exact preedit and candidate-list values were not independently observed in this application |
| Candidate popup appearance | Unverified: pixel capture failed with `FrameArrived`/window-capture timeout |

The module inspection establishes the installed DLL's actual mapping into this x64 Notepad. It does not, by itself, establish composition state or popup visibility at that instant. The key-event trace independently establishes the observed document results. Earlier RichEdit TSF composition/candidate records remain historical evidence below; they are not substituted for missing Notepad UI observations.

The Hong Kong `0x0c04` profile definition was installed, but its activation was not tested. That baseline broker used the offline dictionary with learning disabled; the current revision above enables local learning. See [the installed runtime instructions](../native/INSTALLATION.md) for explicit start/stop and removal commands. Pronunciation and ranking refinement remain separate work.

## Historical process-local test-host proof

Before persistent installation, the project's AMD64 DLL passed actual TSF composition, candidate data, commit, cancel and English mode in its AMD64 RichEdit test host. The [original structured proof](native-evidence/2026-10-22/installed/earlier-process-local-proof.json) and [raw evidence](native-evidence/2026-10-22/) retain the exact build, host log, module inspection, IPC report and registration attempts.

| Observed check | Final result |
| --- | --- |
| Host process | PID 78660; RichEdit `RICHEDIT50W`, `SES_USECTF`, nontransitory TSF context; executable PE `0x8664` |
| Actual loaded project DLL | `CantoneseIME.dll`, PE `0x8664`, SHA-256 `f22d1c0f376e1aa93908bdc7420374d36fe35ed78c6e018e0086fd34aeba0a2d` |
| Input provenance | Individual Computer Use `press_key` events `n`, `e`, `i`, `h`, `o`, `u`; no Chinese paste, value replacement or editor text injection |
| Preedit and candidates | TSF composition `neihou`, owner `{67718E6F-49A1-4F54-88D6-30578FC70C5D}`; 9 TSF candidates, first `你好` |
| Commit | Space produced `你好` and zero remaining compositions |
| Cancel | Another `b` composition followed by Escape returned the document to `你好` |
| English mode | Ctrl+Space followed by the same `n` key produced literal `你好n`, key not consumed, zero compositions |
| Cleanup | Original profile restored, temporary profile unregistered, thread manager deactivated; all reported success |
| Focused Python verification | 44 protocol/lifecycle tests passed |
| Actual client/broker IPC | 58 requests without connection failure; 55 pages, 491 unique `lei` candidates; next request reported the explicit completion-capacity limit. Maximum observed request 7.503 ms, not a representative latency benchmark |

That earlier test used **process-local registration under the already installed English input language `0x0409`**. The profile GUID is `{A7136205-2245-45CC-A6AA-702B3F2E8D42}` and the service CLSID is `{67718E6F-49A1-4F54-88D6-30578FC70C5D}`. Its `0x0c04` activation attempt was unsuccessful. Non-elevated persistent registration also returned `0x80004005` at that stage. Those failures explain the later approved machine-install route; they are historical diagnostics, not a current installation blocker.

In that test host, the native candidate UI was requested visible and actual TSF candidate-list values were observed. Computer Use pixel capture failed with `FrameArrived`/window-capture timeouts. Neither the old host records nor the installed Notepad text results complete the outstanding popup-rendering, caret-placement and visual review.

The portable compiler archive matched the official pinned digest in `native/toolchain.lock.json`. LLVM-MinGW/Clang 23.1.4 built the DLL and host with static C++ runtimes and Windows/UCRT imports. Minimal ABI declarations cover newer TSF interfaces absent from the bundled MinGW headers. Native source and build hashes are recorded in the saved manifest. Acquisition, build, current-account testing and the subsequent administrator installation were explicitly approved.

A transient reconnect problem found in early burst tests was addressed by spending the client's remaining lookup deadline on pipe-busy retries and moving broker diagnostic writes off the transport path. The final source hashes and successful actual IPC run are preserved independently of the TSF typing evidence. The old `native/Start-NativeIme.ps1 -LocalProfile` path is a diagnostic-host workflow; the installed runtime instructions above describe ordinary application use.

## Historical upstream baseline

The earlier upstream TypeDuck baseline attempt ended before setup began (exit code 2); no installation log or expected x64 DLL was found. The following retained package metadata is historical baseline evidence, not evidence that the project's IME works:

| Package field | Observed value |
| --- | --- |
| Upstream release | [TypeDuck Windows v2.0.1](https://github.com/TypeDuck-HK/TypeDuck-Windows/releases/tag/v2.0.1) |
| Download | [Official release installer](https://github.com/TypeDuck-HK/TypeDuck-Windows/releases/download/v2.0.1/typeduck-windows-ime-setup-v2.0.1.exe) |
| Filename | `typeduck-windows-ime-setup-v2.0.1.exe` |
| Bytes | 32,474,372 |
| SHA-256 | `79254f454b78939464247c55d60ad07c50aee3ef52db8c144720314b9a9beb97` |
| Release digest match | Yes |
| Installer Authenticode | `NotSigned` |
| Installed x64 TSF DLL | Pending |
| Native typing observation | Pending |

The download's hash proves agreement with the published release digest. It does not establish a publisher certificate or that the installed text-service DLL is signed.

## Required proof

1. Record the installed IME version, source, DLL hash, COM class, and TSF language profile.
2. Launch a fresh native text editor and verify its executable PE Machine is `0x8664` (AMD64). Record the PID and executable path.
3. Select the registered Cantonese IME in that editor. Record the selected input indicator or input-selector evidence.
4. Send actual ASCII letter key events through the active IME. Do not paste Chinese text or set the editor's text value.
5. Capture the phonetic preedit and Cantonese candidate window before committing.
6. While composition is active, inspect that editor PID's loaded modules. Verify the actual text-service DLL is mapped into the x64 editor and has an AMD64 PE header. After an in-place update, use a process started after the update; a canonical-path disk hash can describe replacement bytes rather than an old process's mapped image. A separate server process alone is insufficient.
7. Select/commit a candidate and capture the resulting Cantonese text.
8. Start another composition and cancel it with Escape. Check there is no extra committed text. Switch to English and verify the same letter events can produce literal Latin text.
9. Save the result and any failures. Limit the conclusion to the exact package, host application, architecture, and Windows build tested.

## Project acceptance gate

The historical `f22d1c0f…` DLL established installed native x64 Cantonese typing,
cancellation and English mode in the recorded Notepad/Windows build. The current
`dfe90daf…` revision is installed and has passed its build, numbered-layout and
fresh-process load checks. The unchanged engine retains its earlier 312-test and
native-IPC evidence; those were not rerun for the labels. Current typing and
layout checks remain with the user. Earlier Notepad
preedit/candidate observations and popup visuals remain incomplete, as do the
listed future compatibility and lifecycle checks.

The read-only [module inspector](../tools/Inspect-NativeIme.ps1) records the target PID, executable architecture, and actual loaded IME module paths, architectures, hashes, and signature states. For this project pass `-ModulePattern '(?i)CantoneseIME\.dll$'`; its default upstream-name pattern does not match this DLL. Run it from x64 PowerShell while the editor is composing when that state can be established. Its architecture result must be combined with functional evidence; it is not a typing test by itself.

Windows 11, x86 applications, AppContainer hosts, elevated applications, and installer lifecycle are separate gates in [the validation matrix](VALIDATION.md).
