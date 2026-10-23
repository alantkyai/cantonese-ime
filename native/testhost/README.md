# Native AMD64 TSF acceptance host

**Basic native TSF typing verified on AMD64 Windows 10.** The built host loaded the actual project's AMD64 DLL and observed real letter-key composition, candidates, Space commit, Escape cancellation and the IME's Ctrl+Space English mode. The successful profile was process-local under installed input language `0x0409`; persistent Hong Kong profile installation and popup pixel review remain incomplete. See [the exact evidence and scope](../../docs/NATIVE_X64_VALIDATION.md). The host itself is diagnostic; those results require the actual project DLL, not this executable alone.

The host uses Windows' Unicode RichEdit 4.1+ control (`Msftedit.dll`, `RICHEDIT50W`) with `SES_USECTF`. Microsoft documents TSF support and that edit style in [About Rich Edit Controls](https://learn.microsoft.com/en-us/windows/win32/controls/about-rich-edit-controls). This avoids introducing a custom `ITextStoreACP` implementation into the application being used to validate the IME. Its context status is recorded so an unexpected transitory context is visible.

The executable is AMD64-only: the source rejects other CPU targets, CMake requires a 64-bit Windows target, and startup checks the executable's PE Machine against `0x8664`. The separate [module inspector](../../tools/Inspect-NativeIme.ps1) remains necessary for DLL architecture, hash and signature evidence.

## Build and launch

Use an already authorized Windows C++17 toolchain and CMake. This directory contains no toolchain downloader or persistent registration tool. Example with Visual Studio's installed x64 compiler:

```powershell
cmake -S native/testhost -B .local/native-build/testhost -A x64
cmake --build .local/native-build/testhost --config Release
```

LLVM-MinGW can build the same target using an appropriate existing CMake toolchain configuration. It links only Windows libraries; no ATL, WRL, third-party GUI toolkit or custom text store is required. The C++ runtime is linked statically; Windows system/UCRT imports remain. The build path/executable location depends on the selected generator. This machine's verified build is `.local/native/build-x64/CantoneseImeNativeTestHost.exe`.

Supply an already registered project profile explicitly:

```powershell
& .local/native-build/testhost/Release/CantoneseImeNativeTestHost.exe `
  --clsid '{67718E6F-49A1-4F54-88D6-30578FC70C5D}' `
  --profile '{A7136205-2245-45CC-A6AA-702B3F2E8D42}' `
  --langid 0x0c04 `
  --log 'D:\IME_Project\.local\native-host-proof-01.jsonl' `
  --activate
```

The log directory must exist. The log file must **not** exist: `CREATE_NEW` protects earlier evidence. Without `--activate`, use the host's **Activate target IME** action after focusing the large editor. Without GUID arguments, it can observe another profile selected through Windows, but cannot identify it as the project profile automatically.

Normal activation calls `ChangeCurrentLanguage` and [`ActivateProfile`](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfinputprocessorprofilemgr-activateprofile) with flags zero for the calling UI thread. It does not enable/register a persistent profile or select a default. The API can fail if the language/profile is unavailable; both HRESULTs and the actual active profile are logged. On exit it attempts to restore the original profile or original thread keyboard layout and records the outcome. This is a runtime attempt, not proof that every Windows configuration behaves identically.

### Explicit process-local fallback

When persistent TSF registration is unavailable without elevation, add **`--register-local-profile`** to the same GUID/activation arguments. The project COM CLSID must already resolve to the actual DLL, for example through a separately authorized HKCU COM registration. The host does not write that COM registration itself.

This option explicitly calls [`RegisterProfile`](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfinputprocessorprofilemgr-registerprofile) with `bEnabledByDefault=TRUE` and `TF_RP_LOCALPROCESS` (`0x4`), then activates with `TF_IPPMF_FORPROCESS` (`0x10000000`). It requests neither `FORSESSION` nor `ENABLEPROFILE`. On exit it restores the original profile, then calls [`UnregisterProfile`](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfinputprocessorprofilemgr-unregisterprofile) with `TF_URP_LOCALPROCESS` (`0x4`). Registration, activation and cleanup HRESULTs are all logged.

Any successful proof using this fallback is **native operation in this process only**. It does not prove a persistent Windows input-selector installation or availability in unrelated applications. The host marks this scope explicitly in the evidence log.

## Functional proof

1. Focus the large empty editor, activate the target, and save a snapshot. Check `host_start.pe_machine`, `editor_created.ses_usectf`, `thread_manager_active_flags`, `context_attached`, and the actual active CLSID/profile. An activation HRESULT alone is insufficient.
2. Through the approved external computer-use path, send individual ASCII letter-key events such as `n`, `e`, `i`, `h`, `o`, `u`. **Do not paste or set Chinese text.** The host generates no input and contains no expected Chinese output. Its status pane is updated programmatically; its input editor is never supplied target text by the host.
3. Capture the real preedit and native candidate window. The clickable snapshot action does not take focus from the editor. While composition is active, run the module inspector for the host's logged PID. Confirm the actual project TSF DLL path and AMD64 architecture, then hash that DLL.
4. Select a candidate using actual keys and capture the committed editor text. The host records read-only TSF composition ranges and document text in `tsf_end_edit`, plus `EN_CHANGE` and manual `document_snapshot` records.
5. Before the cancellation test, click **Mark cancel baseline**. Type another ASCII composition and press Escape. Capture the composition disappearance and compare the resulting document to that baseline. `composition_ended` deliberately does not decide commit versus cancel; key, composition and document evidence must agree.
6. Use **Switch to English**, which selects an existing English keyboard layout for this thread. Send the same kind of actual letter-key events and verify literal Latin text. No layout is downloaded or registered by this action.
7. Close the host, preserve its log, screenshots and the module-inspector result, and record any failures. No exit code or log record automatically marks the acceptance gate passed.

## Diagnostic records and limits

Logs are UTF-8 JSON Lines with increasing sequence numbers, UTC time, PID and TID. Important records are:

| Event | Evidence |
|---|---|
| `host_start` | Executable path, process identity, pointer width, actual PE Machine, requested profile |
| `thread_manager_active_flags` | [`GetActiveFlags`](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfthreadmgrex-getactiveflags) HRESULT and flags |
| `context_attached` | Text-edit sink HRESULT and static/dynamic context flags |
| `key_received`, `key_message` | Observed key messages before/after TSF processing, key codes and consumed status |
| `tsf_end_edit` | Read-only document and [`EnumCompositions`](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfcontextcomposition-enumcompositions) ranges with owner CLSIDs |
| `candidate_ui_*`, `candidate_list` | Candidate observations if the TIP implements TSF UIElement interfaces |
| `document_snapshot` | Control text, selection, baseline/manual stage and truncation flag |
| `editor_message` | Observed `WM_CHAR`, IMM composition, paste or text-setting messages |
| `loaded_module` | Paths actually mapped into this process at startup and requested snapshots |

[`OnEndEdit`](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itftexteditsink-onendedit) supplies the read-only edit cookie used for TSF range observations. The main loop follows the documented [`ITfMessagePump`](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfmessagepump-getmessagew) and [`ITfKeystrokeMgr`](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfkeystrokemgr-testkeyup) path. The host does not mutate a TSF range or synthesize keyboard events.

Candidate diagnostics keep the TIP's native UI visible (`pbShow=TRUE`); some TIPs expose a popup without UIElement support or omit updates while showing their own UI. Missing `candidate_list` events alone therefore do not establish missing candidates. Use visual evidence and the project's own service diagnostics. The application does not activate UI-less-only mode, which could exclude TIPs that lack that capability. See [Microsoft's UI-less overview](https://learn.microsoft.com/en-us/windows/win32/tsf/uiless-mode-overview).

Observations are bounded: 16 composition ranges, 4,095 UTF-16 units per composition, 8,191 TSF document units, 32,768 control-text units and 90 UIElement candidates. Relevant truncation flags/counts are logged. The acceptance smoke is far smaller than these bounds. Message logs cannot establish whether a key originated from a physical keyboard or external injection; the approved automation trace supplies that provenance. Module paths alone do not establish DLL hashes, signatures, or functional composition.
