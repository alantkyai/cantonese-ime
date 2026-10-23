# Cantonese IME 1.0.6 for Windows x64

The numbered candidate panel now uses **LXGW WenKai TC Regular (霞鶩文楷 TC)**
at 20 logical pixels, scaled for the host window's DPI. The installer bundles
the original, unmodified font. Candidate numbering, keyboard selection and
compact word-only layout are retained.

## Appearance for each application

Right-click the candidate panel or the native **粵 / 英** mode button to open
**Candidate appearance for this app**:

- **Background:** Dark, Light or Windows system colors.
- **Panel opacity:** 100%, 95%, 90% or 85%.
- **Reset appearance for this app:** remove that application's override.

The default is **Dark at 95% opacity**. Opacity affects the entire panel,
including candidate text and selection highlighting. Select 100% for an opaque
panel. Windows High Contrast always uses Windows colors at 100% opacity.
Hosts that render their own TSF candidate list control their list's appearance.

Preferences are saved separately for each application in
`%LOCALAPPDATA%\CantoneseIME\appearance.ini`. The file is separate from personal
selection learning and survives upgrades and uninstall. The dictionary and
word/phrase learning mechanism retain their existing behavior.

## Bundled font and licensing

The IME reads the font from its own installation and loads a private in-memory
GDI resource for the candidate panel. It makes no Windows-wide font installation
and does not change the receiving application's font for committed text. If
the bundled file is missing or cannot be loaded, candidate rendering falls back
through Microsoft JhengHei UI, Microsoft JhengHei and Segoe UI, with the existing
Windows GUI font as the final fallback.

The font is distributed under the **SIL Open Font License 1.1**. Its original
font file, complete copyright and license, authors, contributors and upstream
acknowledgements are retained in
[assets/fonts/lxgw-wenkai-tc](../assets/fonts/lxgw-wenkai-tc/NOTICE.md), together
with a pinned source lock. No font modification or renaming was made. Dictionary,
runtime and application licensing remain separately documented in the
[release notices](../installer/RELEASE_NOTICES.txt).

## Upgrading

Install the 1.0.6 Windows x64 setup normally and approve its administrator
prompt. Restart applications fully afterward so they load the updated typing
DLL. Chrome can retain background processes after its windows close; save
unfinished forms and enter `chrome://restart` to restart it fully.

The Hong Kong input-source registration and separate branding-icon container
introduced by earlier releases are retained. English US and other input sources
remain subject to the installer's existing preservation checks. Personal
learning stays in `%LOCALAPPDATA%\CantoneseIME\learning.json`.

## Verification and scope

Native x64 Windows GDI checks passed for the bundled font at 96, 120, 144 and
192 DPI: 15 font cases and nine offscreen popup renders, representative Cantonese
glyphs, missing-font fallback, multiple resource owners and cleanup. An
independent child process could not see the private font. The original font
asset could be renamed and replaced while rendering from its copied memory
resource. Invalid or redirected font-file fixtures were rejected. Existing
geometry checks and font-integration compilation checks passed.

The exact standard installer completed with exit code 0 on the Windows 10 x64
development PC. All 128 installed payload hashes, the seven font bundle files
and native DLL version 1.0.6.0 passed read-back. The engine reports ready, and
personal learning and Windows input-source preferences were preserved. The
56 focused package/builder tests and native DLL COM loading checks passed.
The [verification record](release-1.0.6-validation.json) separates installed
checks from appearance acceptance. Live game-client, clean-machine and
Windows 11 acceptance remain pending. This unsigned release is scoped to
native x64 desktop applications; 32-bit applications, ARM64 Windows and
secure/password fields remain outside its supported scope. Native macOS
compilation, installation and typing validation also remain pending.

The [first public 1.0.5 release](GITHUB_RELEASE_1.0.5.md) and its
[technical notes](RELEASE_NOTES_1.0.5.md) retain their original history and
version-specific validation.
