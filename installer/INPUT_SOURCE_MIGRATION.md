# Cantonese input language activation

The 1.0.2 user phase enables Cantonese IME under Traditional Chinese (Hong Kong,
LANGID `0c04`). Machine registration continues to own both historical profiles
so existing installations can be upgraded safely.

`Set-UserInputSource.ps1` runs as the ordinary setup user, after the protected
installed payload has been verified. It reads the current typed language list,
appends `zh-HK` if needed, and adds only this product's Hong Kong TIP. Existing
language objects retain their order, other keyboards, handwriting and spelling
properties. It invokes no language-package installation or download command.

Before removing the product's historical English-slot TIP, it verifies both the
exact Hong Kong entry in `Get-WinUserLanguageList` and the native TSF enabled
flag. The US keyboard and every unrelated TIP remain. If the explicit default
override names the old product TIP, that TIP remains enabled. The script does
not set the display language, culture, or default input override.

The script records language/profile settings and rollback facts in
`%LOCALAPPDATA%\CantoneseIME\Installer\input-source-migration.json`. It never
reads personal learning. On failure, it restores the in-process original typed
list and owned enabled flags only when current settings still differ solely by
the migration. Detected unrelated or environment changes prevent that rollback
from overwriting another choice. Windows provides no atomic compare-and-set for
this list, so concurrent external writers cannot be made race-free. If an
existing engine was ready before setup, lifecycle attempts to restart the new
verified engine after activation failure while retaining the activation error.

Windows may normalize the new language tag `zh-HK` to `zh-Hant-HK`. Comparison
snapshots treat only these two Hong Kong aliases as equivalent, while receipts
retain raw expected and observed tags for diagnosis. Rollback restores the owned
profile flags before writing the original typed language list, because native
TIP enable/disable operations can recreate a language container. The original
list write has a fresh unrelated-settings and environment guard.
When exact list membership and TSF enabled state are already correct, repeated
activation avoids redundant language-list and native enable/disable writes.

Microsoft documents `InstallLayoutOrTip` as enabling a specified keyboard or
TIP; it does not promise to update the user's ordered language list. That list
is managed by `Set-WinUserLanguageList`. `EnumEnabledLayoutOrTip` alone is not
proof of an enabled Chinese IME because it can enumerate all IMEs for a Chinese
language. The migration therefore checks exact list membership and TSF state.

References:

- [InstallLayoutOrTip](https://learn.microsoft.com/en-us/windows/win32/tsf/installlayoutortip)
- [Set-WinUserLanguageList](https://learn.microsoft.com/en-us/powershell/module/international/set-winuserlanguagelist)
- [New-WinUserLanguageList](https://learn.microsoft.com/en-us/powershell/module/international/new-winuserlanguagelist)
- [EnumEnabledLayoutOrTip](https://learn.microsoft.com/en-us/windows/win32/tsf/enumenabledlayoutortip)
- [Get-WinDefaultInputMethodOverride](https://learn.microsoft.com/en-us/powershell/module/international/get-windefaultinputmethodoverride)
- [Get-WinUILanguageOverride](https://learn.microsoft.com/en-us/powershell/module/international/get-winuilanguageoverride)
