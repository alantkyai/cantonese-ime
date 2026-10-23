# Cantonese IME 1.0.3 for Windows x64

The mode icons now use white 粵 / 英 glyphs with dark outlines, so they remain
readable on dark taskbars. Native resource checks rendered all 24 icon variants
on both dark and white backgrounds. Actual taskbar appearance is checked by the
user after reopening typing applications so they load the new DLL.

Cantonese IME is activated under **Chinese (Traditional, Hong Kong SAR)** rather
than the historical English container. English US remains a separate keyboard.
Press **Win+Space** to choose Cantonese IME; **ENG** is expected when the English
source is selected. The Windows display language and explicit default input
override are preserved.

The 1.0.2 migration rejected Windows' normalization of `zh-HK` to `zh-Hant-HK`.
This release accepts only those equivalent Hong Kong tags and retains both raw
forms in diagnostic receipts. Rollback restores owned profile flags before the
original language list, with a fresh check for unrelated changes. Repeated
activation skips redundant writes when the source is already ready. A patch
upgrade also backs up the native DLL before renaming it when its bytes are
unchanged, allowing rollback after cancellation before file copying.

The exact packaged migration was run twice as this machine's ordinary Windows
user before packaging. The first run enabled the Hong Kong source and removed
only this product's old English TIP. English, existing language properties,
display language, culture and explicit default override were preserved. The
second run left recorded preferences and enable/disable helper log timestamps
unchanged. The 45 focused migration, lifecycle and builder tests passed.

The final standard installer is built and all 121 payload files match its pinned
manifest. Windows closed the final Setup before installation (exit 2, no Setup
log). The installed 1.0.2 payload, including the white-icon DLL, remains intact;
the corrected Hong Kong source is active and the engine is ready. A fresh
read-only verification passed all nine checks. The personal learning file's hash,
size and timestamp remained unchanged during this attempt, and no contents were
copied. Completing the protected 1.0.3 package update still requires the normal
Windows administrator approval.

The dictionary and learning engine are unchanged from 1.0.0. This unsigned release
supports native x64 desktop applications. Clean-machine and Windows 11 tests,
actual uninstall, sign-in startup and the complete live cancellation matrix
remain pending. User typing and taskbar checks are separate from automated
resource and registration verification.

Download the [standard installer](../dist/CantoneseIME-1.0.3-x64/CantoneseIME-1.0.3-windows-x64-setup.exe)
and [SHA-256 checksums](../dist/CantoneseIME-1.0.3-x64/SHA256SUMS.txt).

See [hash-bound validation](release-1.0.3-validation.json) and
[setup completion facts](windows-installer-repair-evidence/2026-10-23/setup-1.0.3-attempt-1.json).
