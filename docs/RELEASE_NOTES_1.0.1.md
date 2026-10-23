# Cantonese IME 1.0.1 for Windows x64

The 1.0.0 upgrade could copy its files successfully, then roll back because its
category enumeration did not show a newly registered system-tray category.
The actual failure was reproduced in the retained Setup log. Registration API
calls succeeded, but the following count check rejected the result.

The corrected helper verifies the exact saved category memberships in both
directions, the two owned language profiles and their release name/icon.
Category enumeration is retained as a separate diagnostic. Removal uses the
same saved membership inventory, so it includes the system-tray category.
All registration changes still use Windows TSF APIs.

The installer also retains child-process diagnostics in the Setup log, records
completed rollback in its protected journal, and returns exit 11 for a failed
machine installation. Exit 10 means ordinary-user activation needs attention.
The dictionary, learning engine and IME DLL are unchanged from 1.0.0.

The final 1.0.1 installer was installed on this Windows x64 machine. Machine
registration and ordinary-user activation both reported exit 0. Read-only
verification passed all nine checks, including 120 payload files, private
64-bit Python, a ready engine, four saved category memberships, profile metadata,
shortcuts and the standard uninstall entry. Tests passed for 56 installer/package
cases, 15 native inventory fixtures and 18 registration guards.

The read-only default-profile query differed from its before snapshot; this is
recorded explicitly, without claiming global default settings stayed identical.
The learning file remains present and was updated after installation during
normal use; the delayed monitor snapshot cannot prove byte-for-byte preservation.
No personal learning contents were copied. Actual uninstallation, clean-machine
testing and Windows 11 acceptance remain pending. Typing and taskbar appearance
are checked by the user.

The user's subsequent screenshot identified a dark-taskbar icon problem and the
legacy English language container. The white alpha icons and Traditional Chinese
(Hong Kong) source migration are included in [1.0.3](RELEASE_NOTES_1.0.3.md).
The intermediate 1.0.2 activation rejected Windows' equivalent Hong Kong language
tags and is retained for diagnosis rather than distribution.

See [the exact installed validation](release-1.0.1-validation.json) and
[retained evidence](windows-installer-repair-evidence/2026-10-23/installed-1.0.1.json).
