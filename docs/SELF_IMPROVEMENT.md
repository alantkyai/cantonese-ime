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

## Cycle 3: real-graph capacity failures and a sparse conversational model

The [retained language diagnostics](self-improvement-cycle3-diagnostic.json)
record two fresh-profile pilots on the same 19 already exposed requests. The
first eager context adapter completed no context searches: every request hit
its preparation or retained-arc bound. One stored dictionary word remained
available after a caught composition error; its truncated page is a capacity
failure, not a successful context result. The revised evaluator checks saved
capacity diagnostics and truncation even when a direct word is returned.

An isolated lazy A* replacement removes only paths without a complete
continuation and stores unfinished paths as backpointers. Its
[independent mechanical proof](self-improvement-cycle3-lazy-mechanical.json)
passes 3,456 exact comparisons over 384 graphs. The
[standalone decoder and replay](../tools/experiments/context_search_lazy/README.md)
preserve the frozen source bytes and document allocation/work units separately
from the earlier eager decoder. These are integer retained-graph proofs, not
native latency or language-quality acceptance.

On the real dictionary, the lazy zero-weight control completed 16/19 requests
and the weighted lexical-context model completed 5/19. Every remaining failure
hit the 32,768-hypothesis bound; the large waiting frontier is now the measured
bottleneck. Both pilots fail the runtime gate. All saved ranks, signed changes,
fallbacks and source guards remain in the diagnostic; incomplete runs provide
no aggregate accuracy improvement claim. Development and protected validation
have not been queried. Further exact search work must precede either stage.

The next [lexicographic search revision](../tools/experiments/context_search_lazy2/README.md)
adds a cached one-step context bound and a written-text lower bound. It stops
after every path capable of matching the Kth `(cost, text)` pair is processed,
rather than expanding every text tied on cost. Its
[independent mechanical proof](self-improvement-cycle3-lexicographic-mechanical.json)
passes 4,644 comparisons over 387 graphs, including 100,000 equally costly
complete paths. Numerical resource limits were not increased; string generation
and cached scalar bounds have explicit allocation units.

Its [real-graph pilot](self-improvement-cycle3-lexicographic-diagnostic.json)
still fails: the zero-weight arm completes 11/19 requests and the weighted arm
8/19. Hypothesis-limit failures are gone, but work and cached-state limits now
stop the remaining inputs. It recovers three weighted requests while losing
five zero-weight completions. All 35 comparisons completed by both revisions
match full candidate pools, float-hex scores, pages and ranks exactly, including
the 19-request baseline repeat guard. Every crossing and failure is retained.
No corpus-model, development or protected-validation queries follow this failed
pilot. A zero-cost model should avoid context work, and a tighter exact scalar
suffix bound is the next isolated search experiment.

Separately, a [frozen conversational-count model](self-improvement-cycle3-corpus-inventory.json)
uses 39 recording groups from the retained HKCanCor source: 128,253 training
characters and 30,579 bigram types. It counts actual segment occurrences,
preserves utterance and exclusion boundaries, and blends their conditional
counts with the fixed expanded lexical prior. Its 7,620-character fitted
vocabulary is the lexical vocabulary union training characters, with one UNK
bucket. No development or reserved occurrence counts enter training.

Independent checks reconstructed the source segments, exclusions, training
counts, binary tables and probability normalization. All corpus groups already
had prior project exposure through the old 500-case corpus set; retained overlap
with old development is disclosed, not presented as untouched evaluation.
Protected new targets are excluded through an opaque matching list. Model,
reader, source-policy and attribution hashes are retained. The corpus adapter
has passed synthetic checks only: no actual dictionary rankings have been
queried with it. Neither context model is enabled in production or installed.

Two further isolated search revisions retain the failed pilots above. The
[static/context revision](../tools/experiments/context_search_lazy3/README.md)
specializes the exact integer-zero model with a position-only suffix merge and
uses lazy exact scalar suffix costs for nonzero context. Its
[mechanical proof](self-improvement-cycle3-static-context-mechanical.json)
passes 9,288 exact comparisons across 387 synthetic graphs. Its
[57-attempt dictionary diagnostic](self-improvement-cycle3-static-context-diagnostic.json)
completes all 19 zero-control requests and 11 of 19 weighted requests. The eight
remaining weighted requests reach the unchanged 100,000-work limit. All 97
saved-pool comparisons completed by both this and earlier revisions are exact.

The [factored revision](../tools/experiments/context_search_lazy4/README.md)
shares first-character groups and outgoing streams across incoming contexts,
with a separate continuation for each written prefix. Its
[mechanical proof](self-improvement-cycle3-factored-mechanical.json) passes
9,312 exact comparisons over 388 graphs, including explicit cost tables,
callback models and a shared-outgoing stress case. Its
[57-attempt diagnostic](self-improvement-cycle3-factored-diagnostic.json)
keeps the zero control at 19 of 19 and completes 16 of 19 weighted requests.
Three weighted requests still reach the same work limit. No earlier completed
request is lost; all 146 comparisons completed by both revisions match full
saved pools, float-hex scores, pages and ranks exactly.

Both revisions fail the strict runtime-completion gate. Every attempted rank,
failure, counter and elapsed time is retained; no accuracy acceptance is inferred
from completed requests. The timings measure fresh first-90 source queries on
Windows, separately from initialization. Some samples exceed 250 ms. They do
not establish native TSF latency, game acceptance or a speedup, and successful
resource completion would not by itself satisfy a latency gate. No corpus-model,
broader development or protected-validation queries followed these pilots.

The [context and personal-preference design note](CONTEXT_SCORING_DESIGN.md)
clarifies that the existing bounded lexical reward can remain an additive
discount alongside a nonnegative context cost. Context reanchoring is not
inherently required for that objective. The search must use the same discounted
objective in edges, bounds and caches. The fresh-only guard remains until actual
personalization, cache-generation, exact-memory and capacity tests pass; this
design clarification does not replace those tests or alter historical results.

The next [ordered-group revision](../tools/experiments/context_search_lazy5/README.md)
shares each position's exact group-minimum order between scalar suffix bounds
and outgoing streams. Its [mechanical proof](self-improvement-cycle3-ordered-groups-mechanical.json)
passes 9,360 exact comparisons over 390 synthetic graphs. The
[all-attempt diagnostic](self-improvement-cycle3-ordered-groups-diagnostic.json)
retains the same 57 attempts: zero control completes 19 of 19 and weighted
context 17 of 19. Two weighted requests reach the unchanged 1,024-state limit,
so the runtime gate still fails. The work-limit failures are gone in this pilot.
All 200 comparisons completed by both this and earlier pilots match full saved
pools, float-hex scores, pages and ranks exactly; no prior completion is lost.
Every rank, failure and elapsed time remains recorded. This is fresh source
evidence on exposed controls, without accuracy, native latency or personalized
learning acceptance. No broader development, corpus-model or protected-validation
query follows from this result.

The [bounded scalar-slot revision](../tools/experiments/context_search_lazy6/README.md)
reuses eligible completed scalar records in place and pins recursive or active
outgoing records. Its [mechanical proof](self-improvement-cycle3-slot-reuse-mechanical.json)
passes 9,384 exact comparisons and retains constructor-observed tiny-capacity
tests. The [lexical pilot](self-improvement-cycle3-slot-reuse-diagnostic.json)
and [corpus pilot](self-improvement-cycle3-corpus-pilot-diagnostic.json) each
complete all 57 attempts. All 255 earlier completed lexical pool comparisons
and 38 baseline/zero model-control comparisons match exactly. Corpus-weighted
costs change some rankings; every gain and loss remains diagnostic.

The [development record](self-improvement-cycle3-development-diagnostic.json)
contains aggregates and anonymous ranks for all 1,968 attempts. New development
text, readings, typed spellings and ordinal-to-case mappings remain private.
Both weight-0.25 models complete the resource checks but fail the unchanged
old-89 fresh quality gates: lexical first-page hits are 77/89 and corpus 73/89,
below 90%. Their 9–12-character counts are 23/30 and 20/30, below 80%. Their
86/89 and 87/89 first-90 counts pass that separate 95% threshold; this does not
override the failed gates. Short/heavy learning and protected validation have
not been tested for these candidates, and neither is accepted for release.

The [latency scope audit](CONTEXT_LATENCY_SCOPE.md) corrects the interpretation
of historical `elapsed_ms`: it includes evaluator validation, target rank scans
and pool hashing as well as lookup. It is evaluation-row duration, not
engine-only or native TSF/game latency. Existing frozen measurements remain
unchanged. A fixed development-only weight grid was recorded before further
coefficient queries; it retains the quality gates and does not authorize
protected validation or imply a model choice.

The fixed, preregistered context-weight grid is complete. Its
[anonymous all-attempt record](self-improvement-cycle3-weight-grid-diagnostic.json)
retains 2,196 new attempts, including every capacity failure,
plus the existing weight-0.25 references. All 1,464 baseline/zero saved-pool
comparisons match exactly. Both weight-1 pilots hit the unchanged work limit,
so their development stages were skipped rather than evaluated over successful
requests only.

No point qualifies under the unchanged selection rules. Lexical weight 0.5 is
closest on the old 89-case set, with 79 first-page hits where 81 are required.
Corpus weight 0.5 reaches 75/89 and also fails the longest-band and new
development first-page gain requirements. The weight 0.25 failures remain
recorded. No development quality counts are inferred for the failed weight-1
pilots. The eligible set is
empty, so no model is selected and protected validation remains unqueried.
Learning, latency and native acceptance are separate unfinished obligations.

The new lookup wall/CPU fields stop before evaluator checks; the historical
elapsed field remains evaluation-row duration. All are shared-process source
observations, not a controlled native benchmark or a speedup claim. New
development text, readings, typed spellings and ordinal mappings remain private.

Saved old-case analysis separates ranking from resource failures: eight of the
lexical weight-0.5 model's ten remaining old-89 first-page misses already occur
at ranks 10–90. Missing a first-90 result does not prove that its text is absent
from the dictionary or retained graph. This motivated an isolated word-context
experiment using the licensed training partition's original word tokens,
frozen smoothing and unknown-word rules.

The [word-context experiment](WORD_CONTEXT_EXPERIMENT.md) is now complete.
Its bounded search passes 12,288 independent mechanical comparisons; original
word counts, normalized probabilities and immutable model loading were checked
separately. All 1,041 pilot/development attempts complete without runtime
failures, and all 694 baseline/zero full-pool controls match exactly.

The fixed word model improves old-89 first-page hits from 66 to 70, below the
required 81 and the earlier character model's 79. Its 84 first-90 hits miss the
required 85; two length bands and individual nasal-control requests also fail.
Exact text-plus-reading first-90 coverage on the old cases falls from 70 to 68.
The [aggregate record](self-improvement-cycle4-word-diagnostic.json) preserves
these failures and signed gain/loss counts. No model is selected, protected
validation remains unqueried, and production context scoring remains disabled.
Actual learning histories, controlled latency and native acceptance remain
unfinished.


### Surface context: fresh development

The surface-aware context experiment passes all 18 fresh development gates.
Its aggregate record covers 1,388 attempts and 1,041 exact full-pool controls.
Old 89 text hits improve to 81/89 first 9 and 88/89 first 90, compared with 66/83
for baseline and 79/87 for character 0.5. The new 30 set reaches 17/26, equal to
character 0.5 and above baseline 14/22; the combined 179 reaches 139/168.

All signed regressions remain recorded, including 21 text-rank and 20 reading-rank
losses against character 0.5. Reading-pair first 90 declines 74→73 on old 89 and
142→141 on the combined set. These exposed development results support a
separate protected-validation freeze and GO; validation is pending at this
snapshot. All-history learning, external replay, controlled performance and
native acceptance remain unfinished. Production and the v1.0.8 release are
unchanged. See the [surface experiment note](SURFACE_CONTEXT_EXPERIMENT.md) and [aggregate diagnostic](self-improvement-cycle5-surface-development-diagnostic.json).


### Surface context: fixed fresh validation

The subsequent [fixed validation](SURFACE_CONTEXT_VALIDATION.md) completes all
500 attempts and passes all 13 incremental fresh gates. On 30 previously
reserved phrases, intended-text first-nine/first-90 hits rise from 12/21 for
baseline to 15/23 for both character and surface context. Across all 125 input
forms, surface context reaches 80/104 versus baseline 66/98 and character
79/104. Three distinct missing phrases are recovered, with no individual nasal
first-page loss against any control. All 295 signed text/reading changes remain
recorded, including 11 text and 11 reading rank losses against character context.

Only half of the proper inputs reach the first page; the longest band reaches
4/11. These incremental results leave substantial sentence-quality limits.
The [aggregate record](self-improvement-cycle5-surface-validation-diagnostic.json)
is project-authored within-cycle evidence, not representative language accuracy.
This reserved set is now exposed and cannot support another untouched claim
after tuning. Original SHORT (five units twice each), HEAVY (twelve units thirty
times each), habitual-input, external replay, controlled performance and native
checks remain unfinished. No context model was integrated or installed, and the
published v1.0.8 tag and installers remain unchanged.

### Surface context: learning integration mechanics

The [isolated history-aware adapter](SURFACE_CONTEXT_LEARNING.md) now passes
33 component and 33 tiny-dictionary runtime checks, including overlapping
child-process writes. Its primary-dictionary smoke passes 26 checks with 43
explicit candidate calls, eight selection API calls and 15 constructors. All 15
complete fresh pool comparisons are exact; restart and old/new saved-reading
checks pass. An independent saved audit reconciles the attempts and 74 input
hashes, with internal persistence assertions qualified in the aggregate.

These mechanical checks preceded the original phrase-profile campaign below.
Context scoring is still disabled in production, and v1.0.8 release assets
remain frozen.

### Surface context: original learned profiles

All 4,824 planned lookups complete across four engines and fresh, SHORT and
HEAVY histories, with twelve clean runtime cells and no history/source changes.
An independent saved audit reconstructs every pool, rank and per-row diagnostic.
The fixed surface candidate reaches 81/88 intended-text first-nine/first-90 hits
on the original 89 proper inputs when fresh, and 82/88 under either learned
history. All original proper-input gates pass for that candidate.

The 29 ordinary habitual-ng inputs reach 26/27 fresh and 27/29 under each learned
history. Fresh results miss the required 27 first-nine and 28 first-90 hits, so
quality eligibility fails. Expected-reading pairs also decline under preserved
old ng4 histories: first-nine hits fall from 23 to 5/4 and first-90 from 24 to
6/5. All 1,620 signed rank changes, control failures, spelling/topic/length/history
strata and prefix-diversity evidence remain recorded. See the
[learning results](SURFACE_CONTEXT_LEARNING.md) and
[aggregate record](self-improvement-cycle5-original-profiles.json).

The next engine change must address the remaining fresh habitual-input problem
without weakening the original targets or thresholds. External replay,
controlled serial performance and native acceptance remain unfinished; no new
context engine was installed or enabled in production.

### Surface context: retained-path diagnosis

A nine-call diagnostic retains all intended text and canonical-reading paths;
all six prebound original candidate pools match exactly. Passive hooks are
restored before 251 additional bounded provider computations. The minimum
target words, rewards and character costs match across proper, habitual and
apostrophe forms. Habitual spelling contributes 4.8 lexical-cost units per
substitution; apostrophes keep that cost while removing competing parses.
Two absent-first90 target costs exceed their composed cutoffs by 1.703919 and
0.226604. Matching observed span inventories do not prove exhaustive unpruned
dictionary coverage.

This explains retained-path ranking failures without repairing them. The two
original fresh habitual gates still fail at 26/29 first9 and 27/29 first90;
targets, alias cost, models, weights, caps and thresholds are unchanged. See the
[boundary analysis](SURFACE_CONTEXT_LEARNING.md#retained-path-boundary-diagnostic)
and [numeric record](self-improvement-cycle5-boundary-diagnostic.json). Independent
licensed conversational-data and model-alignment research is separate work.
No native, performance or release acceptance follows; production context
scoring and v1.0.8 remain unchanged.

### Occurrence character context: rejected data ablation

One fixed experiment replaced the character factor's type-derived counts and
vocabulary with admitted TRAIN occurrence counts, preserving 0.5 character/word
weights, the 0.8 alias cost and all targets, caps and thresholds. An independent
TRAIN replay matched all counts and class IDs. The model contains 2,295 positive
character types, 128,253 character occurrences and 110,076 bigram occurrences
from 18,177 segments across 39 groups and 48 files.

The pilot completes 38 calls with all 19 quantized-zero full-pool controls exact.
The separately authorized 402 fresh calls also complete cleanly. Proper text
first-nine/first-90 hits are 73/89 and 89/89, versus the previous surface
candidate's 81/89 and 88/89; habitual hits are 25/29 and 27/29, versus 26/29 and
27/29. Length-band first-page hits are 26/29, 25/30 and 22/30. Four unchanged
gates fail: proper first-page, longest-band first-page, and both habitual gates.
The full text coverage is not exact-reading coverage: proper reading-pair hits
are 62/89 and 73/89; habitual pairs are 22/29 and 24/29.

All 804 signed records are retained. Across 402 forms, text ranks have 48 gains,
139 losses and 215 ties; reading ranks have 30 gains, 117 losses and 255 ties.
The model is rejected and stops here, without retuning or later learning,
external, latency or native stages. The earlier cycle5 candidate's two fresh
habitual failures remain unresolved. These are exposed development results;
normal internal model/SQL work is unmeasured, and no native/performance or
release acceptance follows. Production and published v1.0.8 assets stay
unchanged. See the [experiment note](OCCURRENCE_CONTEXT_EXPERIMENT.md) and
[numeric evidence](self-improvement-cycle6-occurrence-diagnostic.json).

### Blended character context: rejected fixed interaction

One further fixed experiment reused the existing corpus-blended character
conditional with the bounded word discount. It retained all 7,620 lexical/TRAIN
union classes through radix 7,621, without changing the state-slot budget,
weights, alias cost, targets or thresholds. No new training or counts were made.

The 38-call pilot has all 19 quantized-zero pools exact. All 402 original fresh
calls then complete cleanly, but four original gates fail: proper text first9
is 76/89, the longest band's first9 is 22/30, and habitual first9/first90 is
26/29 and 27/29. Proper text first90 is 88/89; exact-reading pairs are only
65/89 first9 and 73/89 first90. Habitual reading pairs are 23/29 and 24/29.
Length-band first-page hits are 26/29, 28/30 and 22/30.

All 804 signed changes remain recorded: text ranks have 43 gains, 92 losses
and 267 ties; reading ranks have 26 gains, 73 losses and 303 ties. Independent
saved audits reconcile the full results after a preserved one-key metadata
lookup correction, with no Engine rerun. The candidate is rejected, with no
retuning or later learned, external, latency or native stage. The earlier
occurrence candidate remains rejected and the original surface candidate's
two fresh habitual failures remain unresolved. These exposed development
results and synthetic proofs do not establish native or release acceptance;
normal internal model/SQL work remains unmeasured. Production and v1.0.8
release assets are unchanged; the horizontal/vertical layout remains in
development. See the [experiment note](BLENDED_CONTEXT_EXPERIMENT.md) and
[numeric evidence](self-improvement-cycle7-blended-diagnostic.json).

### Curated sentence-type context: rejected fixed data recipe

A fixed C8 experiment replaces the old conversational character counts with
counts from the original CTCPC BASE TRAIN split while preserving lexical
backoff and the surface candidate's other scoring and resource settings.
Empty exclusion precedes exact nonempty sentence deduplication; admitted Han
runs produce 1,379,235 character and 1,183,188 adjacent-pair occurrences across
102,973 sentence types. This is sentence-type-weighted evidence, not natural
usage frequency. The first-party card declares CC0; row ownership, linguistic
quality and source-disjointness are not established.

An independent replay matches every count, class ID and payload byte.
Numerical checks compare 58,478 pairs with zero mismatches across seven complete
previous-context rows. The 38-call pilot preserves all 19 quantized-zero pools.
All 402 original fresh calls then complete with no runtime or capacity failure.
Proper text first-nine/first-90 hits are 85/89 and 88/89, versus the earlier
surface candidate's 81/89 and 88/89. Length-band first-nine hits are 27/29,
30/30 and 28/30. Proper exact-reading pairs reach 70/89 and 73/89.

Habitual text first-nine/first-90 hits are 26/29 and 28/29, versus the earlier
26/29 and 27/29; exact-reading pairs reach 23/29 and 25/29. One of the original
14 gates still fails: habitual first-nine requires 27/29. The candidate is
rejected and stops without retuning, learned-profile, external, controlled
latency, integration or native stages. Across all 402 forms, text ranks have
80 gains, 62 losses and 260 ties; reading ranks have 56 gains, 56 losses and
290 ties. Independent saved audits reconcile every result and all 804 signed
records, retaining all losses and complete denominators.

The two quality stages total 440 lookup calls and three constructors. These
exposed project results and numerical proofs do not establish representative
accuracy, controlled performance or release acceptance; normal internal
model/SQL work remains unmeasured. No context model is enabled or installed,
and published v1.0.8 remains unchanged. The horizontal/vertical layout remains
in the development build. See the [experiment note](CURATED_CONTEXT_EXPERIMENT.md)
and [numeric record](self-improvement-cycle8-curated-diagnostic.json).

### Initial-character marginal: rejected fixed ablation

A separate C9 experiment changes only the first emitted character's factor to
`(Cu + 10 * L) / (1379235 + 10)`, using the already audited curated unigram
counts and lexical backoff. Every non-initial conditional, including unknown
class 0, remains C8. Vocabulary, word discount, weights, alias cost, learning,
direct tiers and resource limits stay fixed. This is a composition-initial
marginal, not trained sentence-start evidence or natural usage frequency.

All 58,478 numeric probability/cost pairs agree with the independent count
oracle, and all seven tested full rows normalize. The 38-call pilot preserves
all 19 original quantized-zero controls. All 402 original fresh calls then
complete cleanly. Every reported proper, habitual and length-band first-one,
first-nine, first-90 and exact-reading coverage count is unchanged from C8:
proper text reaches 85/89 first-nine and 88/89 first-90; habitual text reaches
26/29 and 28/29. Habitual first-nine still misses the required 27/29, so one of
the original 14 gates fails and this fixed candidate is rejected.

Ranks do change despite unchanged coverage. Across all 402 forms, text ranks
have seven gains, four losses and 391 ties against C8; reading ranks have six
gains, four losses and 392 ties. Independent audits reconstruct every pool,
all 804 signed records and all original gates. The two quality stages total
440 calls and three constructors, without runtime or capacity failures.
No retuning or later learned-profile, external, controlled-latency, integration
or native stage follows. This exposed experiment does not establish broader
accuracy, causality for an individual failure, performance or release acceptance.
Production context scoring and published v1.0.8 remain unchanged. The layout
option remains in development. See the [experiment note](INITIAL_CONTEXT_EXPERIMENT.md)
and [numeric record](self-improvement-cycle9-initial-diagnostic.json).


### Additive word context: fresh and saved-preference gates passed

C10 keeps C8's character factor, including lexical initial backoff, and adds
fixed sentence-type word counts to the original conversational word counts.
Forward-longest matching preserves all 5,591 word IDs; each unknown scalar
breaks adjacency and contributes no observed unknown count. The combined
2,699,360-byte model has 1,057,037 word tokens and 216,294 positive pair types.
Different source/event units are an explicit mixture, not natural usage
frequency or validated linguistic segmentation. Weights and query limits stay fixed.

Independent count and numeric proofs pass. The 38-call pilot preserves all
19 original quantized-zero controls. All 402 original fresh calls then pass
all 14 unchanged gates: proper text first-nine/first-90 reaches 86/89 and 89/89;
habitual reaches 27/29 and 28/29. Proper reading pairs reach 71/89 and 73/89;
habitual pairs reach 24/29 and 25/29. Proper length-band first-nine counts are
27/29, 30/30 and 29/30. Saved audits reconstruct every row and all 804 signed
records. Across 402 forms against C8, text ranks have 57 gains, 17 losses and
328 ties; reading ranks have 51 gains, 17 losses and 334 ties. Every loss is retained.

The initial two stages total 440 calls and three constructors. A preserved CRLF/LF
setup failure was corrected before quality queries; it was not a quality retry.
The pilot auditor's live-output search exposure is recorded without a blinding
claim.

The complete original three-profile/four-arm comparison now adds eleven cells,
4,422 calls and eleven top-level constructors, reusing the existing fresh
candidate cell once. Independent audit reconciles all 4,824 joined rows and
6,432 signed records. All twelve runtime cells are clean; all 27 candidate
profile gates pass. Proper written first-nine increases from 86/89 fresh to
87/89 under both saved profiles; first-90 stays 89/89. Habitual written
first-nine/90 stays 27/29 and 28/29. The original histories are unchanged,
with no new seeding or selection writes. Controls' quality failures remain visible.

Habitual exact-reading coverage regresses: first-nine/90 changes from 24/25
fresh to 6/6 under SHORT and 5/5 under HEAVY, each out of 29. Alternative
historical readings are retained; these aggregate counts do not establish the
cause of every change. All losses remain private diagnostic evidence.

C10 quality work now totals 4,862 calls and fourteen top-level constructors.
These exposed project results permit separate later checks only. External
replay, controlled latency, whole-text learning/persistence, dense/paging/session
correctness and native integration remain pending; no model is selected or
enabled. C8/C9 remain rejected. Published v1.0.8
and installation remain unchanged; horizontal/vertical layout is separate
development work. See the [experiment note](ADDITIVE_WORD_CONTEXT_EXPERIMENT.md)
and [aggregate record](self-improvement-cycle10-word-diagnostic.json).
