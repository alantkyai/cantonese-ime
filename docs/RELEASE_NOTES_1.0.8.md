# Cantonese IME 1.0.8 for Windows x64

**Release withheld after expanded sentence testing.** The broader review is
complete and its sentence-quality gates failed. The
[review policy and results](LONG_PHRASE_RELEASE_REVIEW.md) take precedence over
the earlier plan to install after the focused checks. This remains a development
candidate.

**Final checks pending:** the engine is frozen and its runtime regressions have
passed. The first standard Setup attempt was canceled before the protected
payload update. The installed version remains 1.0.7; installed 1.0.8 broker
acceptance is pending.

Version 1.0.8 is the planned next public release after 1.0.5. It combines the
font and candidate-appearance controls tested in the local 1.0.6 installation
with fixes for plain Yale phrase composition and transferred learning.

## Learning across longer phrases

Selecting common characters could make many longer inputs rank worse. The
previous composition score subtracted a fixed learning reward for every chosen
piece. Several short learned pieces could accumulate enough reward to favor
an unintended split, such as reading `ying` as `yi` plus `ng`, and push other
complete phrases beyond the candidate pool. Good results with an empty learning
store did not establish behavior with the user's existing preferences.

The new calibration compares a learned unit with the best static candidate
covering the same typed span, including a cheapest static multiword subpath for
a newly learned phrase. It applies the discount before the 90-candidate pruning
step and keeps the combined arc cost nonnegative. This removes negative-cost
profit from adding more learned pieces. Different valid phonetic parses remain
available, including boundaries requested with apostrophes.

Exact full-input selection memory keeps its separate adaptive boost, and the
learning-file schema is unchanged. The plain Yale spelling fix is also carried
forward: recognized Yale constituents receive their supported-spelling cost
inside composed phrases while stored mapping metadata remains intact.

## Runtime and longer-phrase checks

The frozen 1.0.8 engine passed **32 focused checks** and an independent
**195-test runtime regression suite**, with zero failures, errors or skips.
These runtime results apply to the frozen 1.0.8 engine revision.

With synthetic common-character preferences, the frozen engine placed **16 of
19 expected phrases in the first nine choices and 18 within the first 90**.
The earlier reward policy placed three on the first page; the no-learning
baseline had 13. This project-authored public phrase cohort exercises the known
failure mode and is not a general Cantonese accuracy rate or a held-out
language benchmark.

Three development phrases remained outside the first page, including one
outside the first 90. Unigram-based ranking and the lack of preceding-document
context continue to limit sentence quality.

Regressions retained valid alternative boundaries, including `ngo` plus `ng`,
and preserved a deliberately selected nonminimal full-input reading. A newly
learned composed phrase transferred into a longer input and remained preferred
after its temporary store was reopened.

A lookup-only diagnostic using the frozen 1.0.8 engine and current personalized
profile returned all three reported target phrases first. This diagnostic
loaded existing learning internally; personal learning records are absent from
release material. Installed 1.0.8 broker checks remain pending.

## Candidate font and appearance

The installer includes the unmodified **LXGW WenKai TC Regular (霞鶩文楷 TC)**
font at 20 logical pixels with DPI scaling. It loads privately for the IME's
numbered candidate panel and keeps its original OFL 1.1 license and credits.
The font of committed text remains controlled by the receiving application.

Right-click the candidate panel or native **粵 / 英** mode button to choose
Dark, Light or Windows system colors and panel opacity of 100%, 95%, 90% or 85%.
The default is Dark at 95%. Opacity affects the whole panel, including text;
Windows High Contrast uses opaque Windows colors. Appearance is saved separately
for each application. Hosts drawing their own TSF candidate list control that
list's appearance.

## Upgrade and release checks

The frozen installer is `CantoneseIME-1.0.8-windows-x64-setup.exe`, containing
128 payload files and the 1.0.8.0 typing DLL.

Installer SHA-256:

```text
89643de3f872210a3ee2994af2d1df287ec277111cd3b0615cdc4b226e31e52e
```

The attached `SHA256SUMS.txt` covers the installer and `package-manifest.json`;
the manifest lists individual payload hashes.

**Installed verification pending:** the first standard Setup attempt ended with
exit code 2 before the protected payload update; no Setup log was produced.
The installed version remains 1.0.7 and learning metadata was unchanged.
Installed 1.0.8 file and personalized-broker acceptance checks remain pending.
Users of the local 1.0.6 or 1.0.7 builds can use Setup's normal upgrade path
once this release is ready.

Restart applications fully after an upgrade. Chrome can retain background
processes after its windows close; save unfinished forms and enter
`chrome://restart` to load the new typing DLL. Personal preferences remain local
in `%LOCALAPPDATA%\CantoneseIME\learning.json`; appearance settings are separate
in `%LOCALAPPDATA%\CantoneseIME\appearance.ini`.

This unsigned release is scoped to native x64 Windows desktop applications.
Live game-client, clean-machine and Windows 11 acceptance remain pending.
32-bit applications, ARM64 Windows and secure/password fields remain outside
the supported scope. Native macOS validation also remains pending.

The [first public 1.0.5 release](GITHUB_RELEASE_1.0.5.md) retains its original
assets. The [local 1.0.6 checkpoint](RELEASE_NOTES_1.0.6.md) retains its own
installation history; it was not published as a GitHub release.
