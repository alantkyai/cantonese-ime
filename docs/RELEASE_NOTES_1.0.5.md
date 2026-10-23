# Cantonese IME 1.0.5 for Windows x64

Explorer could keep an older Cantonese typing DLL loaded after an upgrade. That
older image had no branding icon, although the newly installed file did. Inside
the running Explorer process, resource-load calls for the canonical DLL path
returned the older mapping and could not find icon 101. This explains a concrete
failure that the earlier fresh-process extraction checks did not reproduce.

The branding icon is now stored in the existing registration helper EXE,
separately from the typing DLL. Both owned TSF profiles reference that fixed,
protected EXE and resource `-101`. A prototype container loaded icon 101 in the
same Explorer process while its old typing module remained loaded. These were
controlled resource-load probes, rather than a trace of a naturally issued
switcher request; final switcher appearance is checked separately.

Before changing registration, the helper verifies its protected fixed path,
resolved file identity, AMD64 executable format and required icon resources.
Rollback preserves each profile's previous icon path, index and enabled state.
The COM service binding continues to use the typing DLL.

The installer backs up and retires both mapped native files before copying an
upgrade. Real Windows resource mappings demonstrated why this is necessary:
in-place overwriting failed, while rename and replacement succeeded. Rollback
also handles partial preparation and mapped replacement files. The 44 focused
installer and packaging tests passed, including two real mapped-helper cases.

Native checks passed for both captured profiles, 12 resource matches at six icon
sizes, five rejection cases, 15 category fixtures and 18 manifest guards. The
typing DLL, dictionary, learning engine and Hong Kong source migration are
unchanged. The fresh installation comparison confirmed that the English keyboard,
the user's newly added Array input method and full language preferences were
preserved. Personal learning hash, size and timestamp were unchanged during Setup.

The standard 1.0.5 upgrade completed with exit code 0 on the Windows 10 x64 test
PC. All 121 installed payload files and all nine installed checks passed. Both
machine profiles reference the protected helper EXE and resource `-101`; the
private engine reports ready. A controlled probe in the same running Explorer
loaded the final installed helper's 16-pixel icon successfully while the old
service mapping still lacked icon 101. The probe released its temporary resource
handles and detached. Actual picker appearance awaits the user's visual check.
See [the validation record](release-1.0.5-validation.json).

Microsoft documents [reuse of already-loaded DLLs even for resource loads](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryexw)
and permits IME icons in a [DLL or EXE resource container](https://learn.microsoft.com/en-us/windows/apps/develop/input/input-method-editor-requirements).
Hong Kong Basic Typing and Traditional Chinese font metadata were already
present on the test machine; no language pack was downloaded for this fix.

This unsigned release supports native x64 desktop applications. Clean-machine
and Windows 11 acceptance, actual uninstall and sign-in startup remain pending.
