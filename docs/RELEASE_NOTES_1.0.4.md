# Cantonese IME 1.0.4 for Windows x64

The Windows input switcher listed Cantonese IME under Chinese (Traditional,
Hong Kong SAR), but its branding-icon area was blank. This update registers the
branding icon by its explicit resource ID, following Microsoft's current TSF
sample, instead of the first-icon ordinal used by the earlier registration.

The modern `RegisterProfile` call now receives the signed resource reference
`-101`, encoded as the unsigned DWORD `0xFFFFFF9B`. Fresh registration,
metadata refresh and read-back use the same value. A failed refresh retains the
exact prior icon location and enabled state for rollback. Shell shortcuts still
use their documented ordinal index, which is a separate consumer.

The installed icon file was checked before making this change. All three Windows
icon extraction APIs returned a visible ç²µ icon for both ordinal `0` and resource
reference `-101`, with identical rendered pixels. Loading resource ID `101`
directly succeeded; resource ID `0` did not exist. Those results rule out a blank
icon resource but do not alone identify the switcher's loading path or establish
the cause of its blank display.

The package keeps the white outlined mode icons, the Hong Kong input source,
and the tested migration and rollback corrections from the previous release.
The English US keyboard remains available separately. Reopen typing applications
after updating, then press **Win+Space** to choose **Cantonese IME**.

The standard 1.0.4 upgrade completed with exit 0. All 121 installed files and
nine read-only installation checks passed, including the explicit icon location.
The user then reopened the picker and confirmed that the icon remained blank.
This release therefore did not resolve the visible branding issue.

A subsequent controlled probe inside the running Explorer process found an older
Cantonese DLL still mapped in memory, without resource 101. Windows resource-load
calls for the canonical DLL path returned that old mapping. A separate prototype
EXE resource container loaded the icon successfully in the same Explorer process.
A follow-up container fix is being prepared.

This unsigned release supports native x64 desktop applications. Clean-machine
and Windows 11 acceptance, actual uninstall and sign-in startup remain pending.

Implementation references: [Microsoft SampleIME icon definition](https://github.com/microsoft/Windows-classic-samples/blob/main/Samples/IME/cpp/SampleIME/Define.h),
[profile registration](https://github.com/microsoft/Windows-classic-samples/blob/main/Samples/IME/cpp/SampleIME/Register.cpp)
and [IME branding requirements](https://learn.microsoft.com/en-us/windows/apps/develop/input/input-method-editor-requirements).

See [installed validation and failed visual acceptance](release-1.0.4-validation.json).
