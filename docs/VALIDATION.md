# Cantonese IME validation

Recorded on 22 October 2026, Hong Kong time.

## Current engine milestone

Windows integration is deferred at the user's request. The project now contains a
working Python typing engine, composition state machine, CLI, and generated
607,026-pair dictionary. [Engine design](ENGINE.md) describes the current
implementation; [engine-evaluation.json](engine-evaluation.json) records measured
seed coverage and timing. The browser observations and native matrix below
belong to the earlier research and later Windows work.

The complete suite passed 222 tests. It covers the engine, composition, mapping rules, source readers,
bounded phrase encoding and independent readiness audit. The seed evaluation found all
40 targets within the first nine candidates, including 34 at rank one. The saved
report includes dictionary/corpus SHA-256, engine/Python/SQLite versions, and the
measurement method. These development examples do not establish general typing
accuracy. A key-by-key CLI replay of `bohim` followed by Space committed 保險.
The [paged Session replay](paged-typing-evidence.json) selected a stored homophone
at rank 193 and verified promotion after reopening with temporary opt-in learning.
The [readiness requirements](DICTIONARY_READINESS.md) distinguish selected-source
accounting from independent linguistic review and broad held-out quality.

[Mapping controls](mapping-behavior-coverage.json)
cover all 1,440 exported relations and 282 collisions, with synthetic tone and
paging fixtures. [Long-input checks](long-input-coverage.json) cover 222 stored
entries in three shorter-prefix forms. The stored-prefix search fix brings
target-text reachability to 666/666 scenarios; exact stored readings reach
335/666 scenarios, or 187/222 entries through at least one form. With 90 distinct
composed outputs, 95 exact routes are within 90 and 240 are at ranks 91–92;
none is lost. All 263 literal
inputs exceeding 64 characters are rejected. These are mechanical checks, not
acceptance of the length limit or alternative suffix pronunciations.

The [HKCanCor external baseline](HKCANCOR_EVALUATION.md) adds 500 frozen
corpus-derived cases and 1,000 lookup requests with zero errors. Fully toned
top-9 text coverage is 232/250 word types and 160/250 speech spans; tone-free
coverage is 219/250 and 111/250. Overall request p95 is 30.958 ms; tone-free
spans reach 41.533 ms. These measurements expose composition/ranking and
workload limits. They are not per-key or native timings, a clean held-out
estimate, or fulfillment of the reviewed 200-case/500-task milestones below.

The [distinct-composition update](COMPOSITION_SEARCH_UPDATE.md) fixes duplicate
path crowding and forward pruning on independent exhaustive synthetic oracles.
Its subsequent replay of the same external corpus is development evidence:
text top-90 hits change from 778 to 810, top-9 from 722 to 720. The original
baseline is preserved. [Changing-key timing](TYPING_LATENCY.md) separates quiet
workload phases from identical snapshot hits; current later-pass Session p95
is 10.597 ms, with slow outliers retained. None of these passes the pending
human or native acceptance gates automatically.

## Completed checks

| Check | Observed result | Evidence |
| --- | --- | --- |
| Project inspection | Initially empty; no source/build configuration or project instructions found | Local directory inspection |
| Windows version | Windows 10 Pro 22H2, build 19045.6466, x64 | [Environment snapshot](environment.json) |
| Development tools | Python, Node, Git and PowerShell available; no .NET SDK; standard VS C++ and Windows SDK installations not found | [Read-only probe](../tools/Test-DevEnvironment.ps1) |
| cantoneseinput.com | Typing `bohim` produced 保險 as candidate 1 | [Screenshot](evidence/cantoneseinput-bohim.png), [reference site](https://www.cantoneseinput.com/) |
| Google online Cantonese demo | Selecting Cantonese Traditional and typing `lay` produced 你 as candidate 1 | [Screenshot](evidence/google-lay.png), [reference demo](https://www.google.com/inputtools/try/) |

These earlier browser observations are not tests of an installed native IME.
The current engine harness has since been executed locally. Native registration,
signing, and host-application integration remain deferred.

The environment probe reports discovery scope. Absence from PATH and the standard installation roots does not prove that no portable or custom toolchain exists elsewhere. The saved JSON records command failures separately from confirmed results.

## Conversion acceptance cases

The executable seed corpus is now [core_cases.json](../eval/core_cases.json), with
actual results in the saved evaluation. The targets below also include future
coverage beyond that corpus. A desired phrase should appear in the first
candidate page unless a stricter rank is specified. A ranking target does not
assert the spelling has only one possible meaning.

| Input | Mode | Required behaviour |
| --- | --- | --- |
| `neihou` | Jyutping | Offer 你好 |
| `nei'hou` | Jyutping | Honour the explicit boundary and offer 你好 |
| `lay`, `nay`, `lei` | Forgiving | Include 你 among candidates; retain other legitimate readings |
| `leihou` | Forgiving | Offer 你好 using the enabled n/l tolerance |
| `bohim` | Forgiving | Offer 保險 |
| `bouhim` | Jyutping | Offer 保險 |
| `failok` | Forgiving | Offer 快樂 |
| `ngosheungsikchasiubao` | Forgiving | Offer 我想食叉燒包 through phrase composition |
| `ngosoengsikcaasiubaau` | Jyutping | Offer 我想食叉燒包 through phrase composition |
| `ngoshuengsikchasiubao` | Forgiving, exploratory | Google's documented `shueng` example; evaluate separately as an extra spelling or typo-tolerance case |
| `long` and `lo'ng` | Both | The explicit boundary constrains segmentation |
| Valid and invalid syllable fragments | Both | Offer useful completions or retain literal input without a crash |
| Literal English, punctuation, URLs and emoji | Both | Preserve text and documented mode/commit behaviour |
| Canonical spelling and nearby alternatives | Jyutping | Adding fuzzy mode does not change the standard mode's results |

Use a separate, held-out set for ranking evaluation. Split results by exact Jyutping, alias spellings, pronunciation mergers, colloquial vocabulary, and phrase length. Do not tune and report accuracy on the same sentences. Future evaluation records should include mode, keystrokes, target, accepted alternatives, rank, selected output, latency, engine/data revisions, and learning state.

Initial engineering targets, to revise after baseline measurements:

- At least 95% of a reviewed 200-case core phrase set appears in the top 9; this is a target, not a measured score.
- Report top-1 and top-9 results separately for exact and forgiving spellings, plus extra selections needed per phrase.
- Warm conversion p95 below 20 ms and end-to-end candidate update p95 below 50 ms on this machine. Report cold start separately and retain slow-input examples.
- No lost or duplicate commits, crashes, host freezes, or stale candidates during composition/focus stress testing.

## Windows integration matrix

Every row is pending. Record application version, process architecture, Windows build, expected output, actual output, and any unsupported case.

Native AMD64 validation is a required acceptance gate. Follow [the native x64 proof procedure](NATIVE_X64_VALIDATION.md): verify the editor's PE architecture, the actual loaded TSF DLL, and candidates plus commit from individual letter-key events. Browser demonstrations and a 64-bit backend alone do not pass this gate.

| Area | Required checks |
| --- | --- |
| Basic desktop | Notepad and small x86/x64 edit-control harnesses: activate, type, select, commit, cancel, backspace, move selection |
| Browsers | Edge and Chrome: input, textarea, contenteditable; scrolling, zoom, tab and window switches |
| Electron | VS Code and another available Electron app; shortcuts, composition updates, focus changes |
| Office | Word and other available text editors; range replacement and candidate placement |
| Windows surfaces | Search, Settings, Terminal, and an AppContainer text control where available |
| Permissions | Standard and elevated processes; backend connection/reconnection; disabled, password, readonly and noneditable contexts |
| Composition lifecycle | App closes mid-composition; IME switch; host terminates composition; backend crashes or responds late; failed edit-session requests |
| Presentation | DPI 100%, 150%, 200%; mixed-DPI monitors; caret near screen edges; host-rendered candidate UI; keyboard-only use and Narrator |
| Installation | Clean install, separate x86/x64 registration, upgrade with loaded DLLs, repair, uninstall, reinstall, preserved learning data |
| Other platforms | Dedicated Windows 11 validation; ARM64 only after architecture-specific builds and hardware tests |

## Safe development sequence

1. Run engine tests without system registration.
2. Build matching x86/x64 hosts and verify signing/loading prerequisites.
3. Use a test account or VM for the first native registration and uninstall cycle. Smoke-test AppContainer and elevated-host backend access before selecting the frontend architecture.
4. Keep a working English input method available and verify switching back before broader host tests.
5. Move to normal daily typing only after composition, recovery, and removal checks pass.

This Windows 10 machine can validate its own build and applications once the toolchain is ready. It cannot establish Windows 11 or ARM64 compatibility.
