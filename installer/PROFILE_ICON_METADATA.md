# Windows profile branding icon

The modern machine registrar identifies the branding icon by
negative resource ID `-101`, represented as unsigned `ULONG`/registry `DWORD`
`0xFFFFFF9B` (4294967195). Starting with 1.0.5, resource 101 is embedded in the
existing protected `native/CantoneseMachineRegistration.exe`. The separate
Cantonese/English mode icons remain in the IME service DLL.

Microsoft's SampleIME defines its profile icon index as a negative icon resource
ID and casts that value to an unsigned integer for `RegisterProfile`. Its
general API documentation calls the field an icon index without spelling out
that convention. The older `AddLanguageProfile` documentation describes a
zero-based index. The development DLL registration path therefore retains its
existing ordinal index; the standard installer uses the modern guarded helper.

Fresh machine registration, metadata refresh, and desired-state readback must
agree on the exact unsigned value. A refresh snapshots the previous path,
description, raw index and enabled state first. Failure restores those original
values through TSF, including a previous index of zero. The fixed profile IDs,
language entries, defaults, learning store and registration ownership guards
retain their existing behavior.

The Start-menu shortcut and uninstall display icons use that helper executable
with Shell ordinal zero.
Native probes found that Shell extraction at zero and at -101 produced the
same visible branding pixels. Successful extraction and correct registry
metadata are prerequisites; actual appearance in the Windows switcher still
requires observation after the registration change. They do not by themselves
prove a visual fix. Runtime inspection found Explorer could retain an older
service DLL mapping without icon resources even after the file on disk had
been replaced. Loading branding from the separate helper executable avoids
that stale service-code mapping. The native input engine and DLL remain intact.

Windows can also retain the helper executable as resource data. Each upgrade
backs up both the service DLL and helper, records both rename intents before
moving either file, and retires the old paths before copying replacements.
Cancellation and failed registration restore both canonical paths from the
protected backup; differing mapped replacements are retired first. A canonical
file already matching its protected old hash is left untouched. Rollback still
accepts older receipts without the new helper-rename fields. Retired files are
kept for existing mappings and included in uninstall cleanup.

The package builder accepts the rebuilt helper only with its matching passing
guard report, pins both before copying, and rechecks them before publication.
This update retains the 1.0.3 input-source migration. The lifecycle changes only
to support safe replacement and rollback of both mapped native artifacts.

References:

- [Microsoft SampleIME icon definition](https://raw.githubusercontent.com/microsoft/Windows-classic-samples/main/Samples/IME/cpp/SampleIME/Define.h)
- [Microsoft SampleIME registration](https://github.com/microsoft/Windows-classic-samples/blob/main/Samples/IME/cpp/SampleIME/Register.cpp)
- [RegisterProfile](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfinputprocessorprofilemgr-registerprofile)
- [AddLanguageProfile](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfinputprocessorprofiles-addlanguageprofile)
- [ExtractIconEx](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-extracticonexw)
