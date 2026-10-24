# Cantonese IME 1.0.8 for Windows x64

The user requested publication of the frozen 1.0.8 build after the expanded
phrase review. This is an ordinary public release with known limitations; it
does not establish a general fix for long sentences. The
[review results](LONG_PHRASE_RELEASE_REVIEW.md) and original
[quality decision](long-phrase-release-decision.json) remain unchanged historical
evidence. The later instruction and publication exception are recorded in the
[publication record](RELEASE_PUBLICATION_1.0.8.md).

Version 1.0.8 is the next public release after 1.0.5. It combines the
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

The broader authored review returned the exact expected text in the first nine
choices for **66 of 89 ordinary phrases** with fresh history and compact plain
Yale input; **83 of 89** appeared within the first 90. The **9–12-character
group returned 18 of 30** in the first nine. Short and heavy synthetic
preferences each returned 67 of 89 in the first nine. These results fail the
previously recorded sentence-quality thresholds.

The user's habitual `ng` spelling for 唔 remains unreliable. In 29 ordinary
phrases using this separately labeled input form, fresh history returned
**0 of 29** exact targets within the first 90. Short synthetic preferences
returned **17 of 29** in the first nine and 23 within 90; heavy preferences
returned 16 and 23 respectively. Primary plain Yale for syllabic `m4` remains
`m`; the user-habit form was evaluated separately.

An external HKCanCor replay of speech spans of four or more characters returned
**84 of 217** exact texts in the first nine with fresh history and compact plain
Yale, and 85 of 217 with synthetic history. Its regression comparison passed,
but the absolute results show that sentence ranking still needs substantial
work. The authored cases are project-created development material; external
annotations have upstream dictionary overlap and spelling limitations. Neither
is a held-out accuracy claim or human typing acceptance. Alternate orthography
was not counted as an exact success.

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

Passing runtime tests does not override the broader sentence-quality failures.
Work after this release will continue with contextual scoring, consistent
habitual-input handling and additional frozen regression cases.

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

The exact packaged x64 typing DLL also passed an isolated COM smoke test:
class factory and service construction, seven interface identities and clean
unload. This did not activate TSF, register the IME or type into an application.

The frozen installer is `CantoneseIME-1.0.8-windows-x64-setup.exe`, containing
128 payload files and the 1.0.8.0 typing DLL.

Installer SHA-256:

```text
89643de3f872210a3ee2994af2d1df287ec277111cd3b0615cdc4b226e31e52e
```

The attached `SHA256SUMS.txt` covers the installer and `package-manifest.json`;
the manifest lists individual payload hashes.

**Installed 1.0.8 acceptance is unverified.** The first standard Setup attempt
was canceled with exit code 2 before the protected payload update and produced
no Setup log. The recorded local installation remains 1.0.7. Installed 1.0.8
file verification and actual personalized-broker acceptance have not been
completed. This publication does not convert that attempt into a successful
installation test. Users of local 1.0.6 or 1.0.7 builds can use Setup's standard
upgrade path, with this validation limitation.

Retained local 1.0.6 frontend/font/appearance validation remains unchanged and
scoped to that checkpoint; it does not establish installed 1.0.8 acceptance.

Restart applications fully after an upgrade. Chrome can retain background
processes after its windows close; save unfinished forms and enter
`chrome://restart` to load the new typing DLL. Personal preferences remain local
in `%LOCALAPPDATA%\CantoneseIME\learning.json`; appearance settings are separate
in `%LOCALAPPDATA%\CantoneseIME\appearance.ini`.

This unsigned release is scoped to native x64 Windows desktop applications.
Live game-client, clean-machine and Windows 11 acceptance remain unverified.
32-bit applications, ARM64 Windows and secure/password fields remain outside
the supported scope. Native macOS validation also remains unverified.

The bundled font retains its complete OFL 1.1 license and original credits.
Dictionary adaptations retain CC BY-SA 4.0 and component notices; runtime
licenses remain separate. See packaged `RELEASE_NOTICES.txt` and
`data/THIRD_PARTY_NOTICES.md`. Original application code currently has no general
redistribution license declaration.

The [first public 1.0.5 release](GITHUB_RELEASE_1.0.5.md) retains its original
assets. The [local 1.0.6 checkpoint](RELEASE_NOTES_1.0.6.md) retains its own
installation history; it was not published as a GitHub release.
