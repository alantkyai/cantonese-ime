# Long-phrase release review

This records the quality review and its original decision to withhold. The
maintainer subsequently requested publication of 1.0.8 with these known limits;
see [the publication record](RELEASE_PUBLICATION_1.0.8.md). The measurements,
frozen policy and failed quality gates remain unchanged.

The expanded phrase testing is complete. The candidate remains held because
its sentence-quality gates failed. This review responds to failures across
many longer sentences, beyond the original 字型 example.
The [release policy](../eval/long_phrase_release_policy.json) records the
coverage, ranking, learning, correctness and latency gates before scoring the
new authored fixture. Thresholds are product targets; they do not establish
statistical confidence or general language accuracy.

The campaign combines independently authored everyday phrases, a replay of the
500 frozen HKCanCor annotation cases, synthetic short-word learning histories,
and session/boundary/stress checks. Full targets, failures and input variants
are retained. External annotation and dictionary overlap limit interpretation;
neither the corpus replay nor authored phrases are a clean held-out benchmark.

The primary user-facing measure is whether the complete expected phrase appears
in the first nine choices from compact plain Yale input. Apostrophes, tones and
later pages are diagnostics, not substitutes for that measure. Learning must
not recreate the widespread loss seen with the earlier reward policy.

Installation and publication remain on hold until required checks support the
release decision. A completed test run can still result in withholding the
version when its quality is inadequate. The current 1.0.8 build is a development
candidate; its earlier 195 passing runtime tests do not establish sentence
quality or installed x64 typing acceptance.

The expanded review fails the sentence-quality gates. **Do not install or
publish the 1.0.8 candidate as an accepted update.** The engine remains at
SHA-256 `a4e2d07c98adbb78b8a6978892827bd907a68cd658f06229d6493fbc05e3e141`;
this campaign changes evaluation material, not engine ranking or dictionary data.

The [93-case authored fixture](../eval/long_phrase_review_cases.json) contains
89 ordinary phrases, the reported 換咗啲字型 example and three short controls.
Only the 89 ordinary phrases enter the main quality denominator. They span ten
topics with 29/30/30 cases at 4–5, 6–8 and 9–12 characters. Of those, 83 are
absent as complete dictionary texts. All readings have dictionary-supported
character paths. Targets and readings were written without engine ranking;
two contextual 開會 tone errors were corrected and recorded before scoring.
The [freeze record](long-phrase-fixture-freeze.json) binds the reviewed fixture,
policy and runner. No native-speaker or audio acceptance is claimed.

All **1,206 authored lookups** completed without exceptions, partial-input
consumption, duplicate candidates or nonfinite scores. Guarded inputs and
disposable learning histories stayed unchanged during lookup. Correct execution
does not establish correct sentence ranking:

| History | Plain Yale first | First 9 | First 90 | Habitual `ng` first 9 / 90 |
| --- | ---: | ---: | ---: | ---: |
| Fresh | 32/89 | 66/89 | 83/89 | 0/29 / 0/29 |
| Five short preferences, selected twice | 32/89 | 67/89 | 83/89 | 17/29 / 23/29 |
| Twelve short preferences, selected 30 times | 32/89 | 67/89 | 84/89 | 16/29 / 23/29 |

Primary input is plain Yale without tones. The additional `ng` group changes
only the syllabic `m` for 唔 to match the user's habit; it is not presented as
standard Yale spelling. Those outputs can use a valid `ng4` reading while the
fixture records canonical `m4`. Their exact text/reading-pair mismatch is not
evidence of a wrong pronunciation; exact full-text retrieval is the quality
measure. Learning improves this group but does not make it reliable.

| Characters | Fresh first 9 | Fresh first 90 |
| --- | ---: | ---: |
| 4–5 | 24/29 | 28/29 |
| 6–8 | 24/30 | 29/30 |
| 9–12 | 18/30 | 26/30 |

The pre-recorded targets require 90% overall first-9, 80% in each length band
and 95% first-90 for every history, with a separate habitual-`ng` gate. The
overall and longest-phrase gates fail. Apostrophes improve fresh first-9 from
66 to 67; strict tone-free Jyutping reaches 68. Supplying all canonical tones
reaches 81/89 first-9 and 86/89 first-90. These diagnostics do not replace the
user’s normal tone-free typing result. All original expected spellings and
failures remain in the [authored results](long-phrase-authored-evaluation.json).
Eight of the 66 fresh first-9 text hits use a reading different from the fixed
gold reading; 13 of the 83 first-90 hits do. Text coverage is not pronunciation
accuracy. The [authored failure triage](long-phrase-authored-failure-triage.json)
retains all 23 first-page misses. Tones rescue 18 of those into the first nine;
apostrophes rescue one. Alternate written forms are noted without counting
them as exact-text successes.

The independent replay re-derived all 58 retained HKCanCor transcripts to the
unchanged 500-case fixture, then tested four forms on the current and retained
1.0.6 engines with the same current dictionary/maps, fresh and with five
synthetic preferences. All **8,000 lookups** completed without errors or partial
input. All 92 guarded inputs stayed unchanged. For the 217 speech spans with
four or more characters:

| Input | 1.0.6 fresh first 9 | Current fresh first 9 | Current fresh first 90 |
| --- | ---: | ---: | ---: |
| Strict Jyutping, tones | 128/217 | 128/217 | 154/217 |
| Strict Jyutping, tone-free | 86/217 | 86/217 | 111/217 |
| Plain Yale, compact | 67/217 | 84/217 | 106/217 |
| Plain Yale, apostrophes | 69/217 | 86/217 | 106/217 |

The 2-percentage-point regression gate passes for every form overall and for
4+ speech spans against matching baseline history. Current synthetic-history
compact Yale reaches 85/217 first-9, compared with 32/217 under the older
reward policy. This supports the calibration fix, while leaving substantial
sentence-quality limits. These external annotations and mechanically derived
inputs have source-overlap and orthographic limitations; they are development
diagnostics, not clean held-out accuracy or observed human typing.

Of 111 compact-Yale targets outside the first 90, 100 have exact annotated
readings supported by a stored-word partition. Forty-eight are found within
90 when all source tones are supplied. Extra vocabulary alone will not solve
most of these misses. SQL support does not distinguish bounded-search loss
from scoring competition. The [external results](long-phrase-external-evaluation.json)
retain all request ranks, signed gains/losses, length groups and failure triage.
HKCanCor attribution and licenses remain in the source lock and existing
[corpus documentation](HKCANCOR_EVALUATION.md).

Robustness checks used 15 public-dictionary phrases at 3–17 characters,
362 per-keystroke session states, paging/commit/reopen, tone and boundary
controls, protocol dispatch and synthetic phrase reuse. They found no errors
or capacity failures. All six dense 255/256-character stress children returned
bounded outputs without a crash or watchdog timeout. One took about 905 ms:
the native 250 ms request cancellation policy is not a hard wall-clock bound,
and these engine tests do not establish native UI latency. See the
[robustness evidence](long-phrase-robustness-evaluation.json).

One inspected miss, 我想試下用呢個字型, survives the retained arc graph but falls
below the final 90-result cutoff by about 0.35 score points. The 吓 variant
ranks 10 and the fully toned 下 target ranks 7. This demonstrates weighting and
orthographic competition in that case; it does not diagnose every missed
sentence as the same problem.

Dedicated serial latency passed the recorded engine-only targets across 708
changing-query lookups after other project query workers stopped:

| History | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: |
| Fresh | 28.70 ms | 155.40 ms | 195.03 ms |
| Heavy synthetic learning | 28.19 ms | 161.21 ms | 180.61 ms |

No ordinary timed lookup exceeded 200 ms or returned errors, metadata constraint
failures or truncation flags. Each history also completed 362 session-prefix
states; their 56 bounded completion flags per history remain recorded. A guard
avoided timing repeated one-entry snapshot hits. Constructor startup was
separately about 4.9–5.2 seconds, with imported modules and existing filesystem
caches; it is not a cold-disk startup measurement. This Windows 10 x64 run
does not measure IPC, TSF, game rendering or a hard native latency deadline.
The [latency results](long-phrase-latency-evaluation.json) retain all timings,
machine/runtime scope and cache controls.

Passing mechanics, latency and baseline-regression checks does not override
the failed quality gates. The [release decision](long-phrase-release-decision.json)
records the checked artifacts and the decision to withhold. No new setup was
launched, installed, tagged or published during this expanded campaign.

The next engine work should address
contextual word choice, ambiguity and orthographic competition, plus robust
support for the user's `ng` habit. Any tuning against these cases makes them
development data; subsequent confidence requires additional untouched cases
and the same frozen regression checks. No phrase-specific dictionary patches
were made in this review.
