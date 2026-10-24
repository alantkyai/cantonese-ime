# Cantonese IME 1.0.8 publication record

## User instruction and scope

The user directly instructed in the current chat on 2026-10-24 (Hong Kong):

> publish 1.0.8 to github and then continue the self improvement loop

This authorizes an ordinary public GitHub 1.0.8 release of the existing frozen
Windows x64 installer. It supersedes the earlier publication hold; it does not
change the measured quality results or establish native installation acceptance.
Subsequent engine improvements are separate revisions from the artifact pinned
here. The public 1.0.5 release, tag, notes and assets are to be retained.
Intermediate 1.0.6 and 1.0.7 builds remain local checkpoints.

## Frozen artifacts

These hashes were checked against current local files before this documentation
update. Publication does not rebuild or modify their contents.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `CantoneseIME-1.0.8-windows-x64-setup.exe` | 91,839,114 | `89643de3f872210a3ee2994af2d1df287ec277111cd3b0615cdc4b226e31e52e` |
| `package-manifest.json` | 24,397 | `77517c258452f1602880012fc3dc53e6db1f569fa443cce87a65bc41e6469205` |
| `cantonese_ime/engine.py` | 52,469 | `a4e2d07c98adbb78b8a6978892827bd907a68cd658f06229d6493fbc05e3e141` |
| `data/generated/lexicon.sqlite3` | 424,673,280 | `bd312406a15162556ac58a257ede1514ad40890c793b6f8fa05084fda2d6241a` |

The manifest lists 128 payload files and pins the 1.0.8.0 typing DLL at
SHA-256 `1ed29c7988322538b804f690db8c354dfa8c69d463d21c101b1e694f20a0f7ca`.
The flat `SHA256SUMS.txt` covers the installer basename and manifest basename.
The unmodified LXGW WenKai TC font, complete OFL 1.1 notice and private
font-loading policy remain part of the exact frozen package.

## Known quality exceptions

The [expanded review](LONG_PHRASE_RELEASE_REVIEW.md) completed before this
instruction. Its predeclared sentence-quality gates failed. Publishing 1.0.8
does not redefine those gates as passed or replace exact targets with alternate
orthography.

- Ordinary compact plain Yale with fresh history: **66/89** exact texts in the
  first nine and **83/89** within 90. The 9–12-character group reached **18/30**
  in the first nine; short and heavy synthetic histories each reached 67/89
  overall.
- Habitual ng-for-唔 forms: **0/29** exact targets within 90 with fresh history;
  short synthetic preferences reached **17/29** within nine and 23/29 within 90;
  heavy preferences reached 16/29 and 23/29. This separately labeled user habit
  is not treated as standard Yale for syllabic `m4`.
- External HKCanCor speech spans of four or more characters: **84/217** exact
  texts within nine for fresh compact plain Yale, and 85/217 with synthetic
  preferences. The external regression comparison passed but absolute sentence
  quality remains limited.

These are project-development and retained-corpus observations, not a held-out
accuracy rate or human/audio typing acceptance. The frozen engine's 32 focused
checks and 195-test runtime suite passed; mechanics checks do not override the
ranking failures.

The historical [release-decision JSON](long-phrase-release-decision.json),
[quality policy](../eval/long_phrase_release_policy.json) and
[authored fixture](../eval/long_phrase_review_cases.json) remain untouched.
Their retained SHA-256 values are respectively:

```text
e4194ebaf815bf8e66a4ddad719e4aa6a8d14a0f8e513d0b9889047d7756e049
5ab132691d4d987290de2afc03db49e6ee688a19082960a1e5d540c10fb499f0
bfb0eb8cf0ca77633394c3aad450d403603800e9a8108c01817bdb85d1d814c6
```

## Native verification scope

The first standard 1.0.8 Setup attempt was canceled with exit code 2 before the
protected payload update and produced no Setup log. The recorded local
installation remains 1.0.7. Installed 1.0.8 file verification and actual
personalized-broker acceptance have not been completed. No native 1.0.8 pass is
claimed by this publication.

Retained local 1.0.6 frontend/font/appearance verification remains unchanged and
scoped to that checkpoint. Live game-client, clean-machine, Windows 11 and native
macOS acceptance are unverified. The unsigned package targets native x64
Windows desktop text applications; 32-bit applications, ARM64 Windows and
secure/password fields remain outside its supported scope.

The exact packaged x64 typing DLL also passed an isolated COM smoke test:
class factory and service construction, seven interface identities and clean
unload. This did not activate TSF, register the IME or type into an application.

## Improvement loop after publication

Continue with contextual sequence scoring and candidate-path coverage,
consistent bounded support for the user's ng-for-唔 habit while preserving true
ng/m readings, and written-form preferences. Preserve all current failures and
replay this campaign as development regression. Freeze additional untouched
cases before evaluating tuned revisions; do not patch only the reported
phrases. Check varied synthetic histories, learning persistence, valid
boundaries, session/paging behavior, latency and external regressions separately.
Native installation and application acceptance require their own evidence.

## Remote publication evidence

Remote publication has not yet been verified in this record. The publishing
agent will append the final source commit, public tag/release URL, asset IDs,
downloaded hash verification, Latest status and preservation checks for 1.0.5
after completing GitHub publication. No remote completion is claimed by this
documentation-only step.
