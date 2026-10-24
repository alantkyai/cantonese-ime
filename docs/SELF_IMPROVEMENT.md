# Engine improvement record

The frozen [1.0.8 release](RELEASE_PUBLICATION_1.0.8.md) is published. Further
engine changes are development work, separate from its tag and installer.
The failed [sentence-quality gates](LONG_PHRASE_RELEASE_REVIEW.md) remain failed;
an incremental feature pass does not replace them.

## Cycle 1: habitual ng input for syllabic m

The dictionary has canonical `m4` readings and weighted compounds for 唔. Its
attested `ng4` variant has much less coverage. Teaching the exact short input
`ng` cannot manufacture missing whole-word `ng` readings for longer input.
The engine now offers a whole-syllable input convention at cost 0.8, allowing
typed `ng` to reach those existing `m` readings. It does not rewrite input,
dictionary readings, frequencies or saved learning keys. Other `ng` paths,
tones and explicit apostrophe boundaries remain eligible.

The library option is `Engine(..., syllabic_m_as_ng=True)`, defaulting to False
for compatibility. The development CLI, Windows broker and Mac stdio bridge
enable it explicitly and accept `--no-syllabic-m-as-ng`. The exported v3
spelling map is unchanged; this separate input convention must be recorded in
evaluation configuration. New selections still save the original raw input and
actual canonical reading. Existing `ng4` learning records remain valid.

### Independent frozen comparison

The candidate and cost were frozen before its author could view a new
[60-phrase fixture](../eval/self_improvement_cycle_1_cases.json). A separate
reviewer authored and checked its readings; this is project review, not a
native-speaker/audio study. It contains 20 negative phrases, 20 nasal controls
and 20 ordinary controls, with a stable 30/30 development/validation split.
Fifty-seven full target texts are absent from the dictionary. No phrase-specific
ranking rules or target corrections were added.

The comparison made 1,560 paired requests and 260 disabled-option checks. Each
synthetic history was created once through the frozen baseline's real selection
API, then copied identically to both models. The short history uses five
selections twice each, including the old `ng4` selection for 唔; the heavy history
uses twelve selections 30 times each. Lookups left all histories unchanged.

| Validation input / history | Baseline first 9 | Candidate first 9 | Baseline first 90 | Candidate first 90 |
| --- | ---: | ---: | ---: | ---: |
| Habitual ng, fresh | 0/10 | 2/10 | 0/10 | 6/10 |
| Habitual ng, short preferences | 3/10 | 4/10 | 5/10 | 6/10 |
| Habitual ng, heavy preferences | 3/10 | 4/10 | 5/10 | 6/10 |
| Proper plain Yale, each history | 14/30 | 14/30 | 22/30 | 22/30 |

These are exact-text retrieval counts, not correct-reading counts or a
representative accuracy estimate. The declared incremental gates passed.
All 360 strict-Jyutping first-90 pools and paging metadata were identical, as
were all 260 disabled-option checks. There were no new first-page losses,
exceptions, nonfinite scores, duplicate outputs or consumption/metadata errors.
The only two rank worsenings were the same development phrase 五蚊一個, compact
and apostrophe input, from rank 5 to 6. They remain part of the retained result.

Quality-run timings include checks and result hashing, with other work sharing
the machine. Enabled startup was 5.14–5.55 seconds, versus 4.92–5.03 seconds for
baseline. Both models had approximately half-second outliers. These are not
native IPC deadlines or application typing acceptance measurements.

### Context experiments

Ordinary long-phrase quality is still limited. The following experiments use a
small character-context prior and a decoder that retains incoming context as
part of its search state. Adding context scores to the current suffix merge
without changing that state can lose the true best candidate. Mechanical
correctness against exhaustive small graphs precedes any integration of a
context-aware search.
Context scoring must cover the whole output independently of word splitting,
remain bounded, and preserve calibrated learning and full-input preferences.
Licensed word-type evidence will be labeled as such, rather than presented as
measured conversational frequencies. Further validation targets must be frozen
before tuning can inspect them.

### Retained evidence and replay

The [public cycle 1 report](self-improvement-cycle1-evaluation.json) retains all
1,820 saved requests, first-nine candidates, first-90 pool digests, split/group/
length summaries and signed rank losses. Synthetic learning-store contents,
history filenames and private source paths are excluded. The
[feature acceptance policy](self-improvement-cycle1-feature-policy.json) is the
unchanged policy written before the original seed and evaluation lookups.

The [CLI replay harness](../tools/evaluate_self_improvement_cycle1.py) uses the
exact retained [candidate](../eval/experiments/cycle1/nasal-prototype-merge-cost.py)
and [baseline](../eval/experiments/cycle1/engine-a4e2-frozen.py) snapshots by
default. They keep their original bytes and sibling filenames because the
candidate imports `engine-a4e2-frozen.py` from its own directory. Optional path
overrides must preserve that relationship. Prepare the dictionary and mapping
artifacts using the repository setup instructions; the harness checks their
exact frozen hashes and rejects drift. From the repository root, choose a fresh
output directory:

```console
python tools/evaluate_self_improvement_cycle1.py --output review-output/cycle1-replay
```

The retained harness was parameterized after the original run; the report also
records the original executed-harness and immutable-report hashes. A later replay
uses already disclosed targets and is not a new blind validation. No benchmark
histories are shipped or loaded from a personal profile: each replay creates
fresh synthetic baseline histories in its output directory.

The subsequent [production integration parity report](self-improvement-cycle1-integrated-parity.json)
retains 780 enabled-option comparisons against the frozen candidate and 260
disabled-option comparisons against its fresh baseline. All first-90 pool
digests, paging metadata and target ranks matched exactly, with unchanged
source/history guards and no runtime violations. This source-engine check does
not establish installed broker, native application or broader sentence-quality
acceptance.

The [current runtime check](self-improvement-runtime-validation.json) passed all
236 tests with unchanged source guards. It includes engine search, learning,
sessions/paging, CLI, protocol/broker control flow and the real stdio child on
Windows. The Mac bridge negotiates the new option with older frozen engines:
the [compatibility check](self-improvement-mac-compatibility.json) ran the current
bridge against the actual released 1.0.8 engine, including 34 public dictionary
cases, learning/restart, explicit opt-out and corrupt-history fallback. It
reports the option unavailable on that legacy engine and rejects an explicit
enable request, preserving the source-kit build path. These are source/transport
checks on Windows, without native macOS or installed TSF acceptance.

## Cycle 2: context search proof and rejected prior experiments

The [synthetic decoder proof](self-improvement-cycle2-mechanical.json) passes
13 tests with 2,897 independent exhaustive comparisons. Its public
[prototype and tests](../tools/experiments/context_search/README.md) retain
incoming character context, text deduplication, reading ties and explicit
allocation/work limits. This proves the declared integer objective on a supplied
retained graph; it does not prove exact floating-point ordering or dictionary
search coverage.

The [first language diagnostic](self-improvement-cycle2-diagnostic.json) used
203 saved first-90 pools from all 153 already exposed phrases. It compared five
fixed coefficients and retained every gain and loss. At coefficient 0.25, a
108,525-word-type prior helped some sentences but moved 少啲糖唔該 from rank 8 to
11. The target-reading grid was not included in that pilot's original guards;
the independent audit discloses this and verifies every saved input against the
fixture literals. These are development results, not untouched validation.

The [expanded-prior experiment](self-improvement-cycle2-expanded-prior.json)
held the same pools, formula and coefficient 0.25 fixed, adding only unique
written types from the locked raw Rime phrase file. It used 438,831 written
types and made no new engine queries. First-page exact-text counts were:

| Exposed development cohort | Existing pool order | Narrow prior | Expanded prior |
| --- | ---: | ---: | ---: |
| Old primary set, including reported/short controls | 70/93 | 75/93 | 81/93 |
| Cycle 1 primary set | 31/60 | 38/60 | 37/60 |
| Old habitual-ng forms | 16/30 | 20/30 | 21/30 |
| Cycle 1 habitual-ng forms | 5/20 | 9/20 | 11/20 |

The expanded prior lost four existing first-page hits in the newer primary
set while gaining three, relative to the narrow prior. It remains rejected for
shipping. Word-type counts are not measured conversational frequencies, and a
first-90 reranker cannot recover any candidate absent from its original pool.
Both models remain outside the production engine. Context-aware retained-path
search, suitable corpus evidence, personalized span calibration, independent
validation and native performance remain separate unfinished work.
