# Surface context with learned preferences

An isolated development adapter now connects the fixed surface-context decoder
to the existing selection memory. Production context scoring remains disabled;
the published v1.0.8 installer is unchanged.

The adapter reuses calibrated constituent rewards, applying them to the combined
lexical/spelling cost before the unchanged context scorer and its single lexical
quantization. Exact full-input preferences stay separate from reusable word and
phrase preferences. It retains schema2 persistence, original bounds and the
baseline selection API. A remembered full input remains available on declared
composition capacity, with failed search diagnostics and truncated paging kept
visible.

Thirty-three component checks pass, including 240 zero-reward preparation
comparisons against the frozen fresh implementation. Thirty-three runtime checks
pass using authored tiny SQLite dictionaries and toy providers, including two
overlapping child-process writers. A separate outer lock covers the unchanged
selection API through the adapter's successful reseal. This coordinates writers
using this adapter; direct baseline or external writers can still leave an
instance stale and requiring reopen. The guards are cooperative consistency
checks, not an adversarial filesystem transaction or fsync durability guarantee.

A subsequent primary-dictionary/model smoke run passes all 26 checks. Its 43
explicit candidate calls include 30 fresh calls forming 15 complete pool
comparisons across three scorer variants; every comparison matches text,
reading, score, kind, input consumption and paging exactly. The run also makes
eight selection API calls and constructs 15 engines. Two stale-history lookups,
one read-only write and one injected pre-replace write failure are expected
rejections. Restart, old `ng4` memory and new `m4` selection checks pass.

An independent saved-evidence audit passes 22 checks and rechecks all 74 pinned
input hashes. It directly reconstructs the pool and restart comparisons. Five
internal persistence predicates remain executed source assertions rather than
independently reconstructed state snapshots; one unchanged-file predicate also
lacks serialized before/after bytes. The audit makes no new engine queries.
See the [aggregate record](self-improvement-cycle5-learning-smoke.json).

Internal selection validation may decode again; the explicit API counts do not
claim zero internal work. Shared smoke timings are not performance acceptance.
All histories are new synthetic files; no personal learning or native
registration was accessed or changed.

## Original phrase profiles

The subsequent campaign completes all 4,824 lookups: 402 original input forms
across four engines and three histories. SHORT uses five units twice each;
HEAVY uses twelve units thirty times each. The masters were created through
the original selection API, and each engine receives identical history bytes.
All twelve runtime cells complete without errors, partial consumption, capacity
failure, source/history drift or shutdown failure. No query is retried.

The fixed surface-context candidate produces these intended-text counts:

| History | Proper first 9 / 90, of 89 | Habitual `ng` first 9 / 90, of 29 |
| --- | --- | --- |
| Fresh | 81 / 88 | 26 / 27 |
| SHORT | 82 / 88 | 27 / 29 |
| HEAVY | 82 / 88 | 27 / 29 |

All original proper-input gates pass for this candidate, including the length
bands and learning-decline limits. Both learned habitual groups pass. Fresh
habitual results fail two unchanged gates: at least 27 first-nine and 28
first-90 hits are required. The candidate therefore remains ineligible for
release; text improvements do not erase these misses.

Expected-reading coverage also needs care. Habitual first-nine text/reading-pair
hits fall from 23 fresh to 5 SHORT and 4 HEAVY; first-90 pairs fall from 24 to 6
and 5. The original `ng4` history keys remain intact, and no expected reading is
relabelled to turn those losses into successes.

An independent saved audit reconstructs all 4,824 pools, ranks, paging and
per-row diagnostics and retains 1,620 signed rank-change records. Full
constructor metadata was not serialized; its strict checks remain source-bound
initialization witnesses. The [aggregate record](self-improvement-cycle5-original-profiles.json)
includes every engine's gates, control results, topic/length/form/history counts,
prefix diversity and signed gains and losses. Full-detail descriptive evidence
retains all 840 strata locally under its published hash.

Next work is the remaining fresh habitual-input boundary/ranking problem.
External500 replay, controlled serial latency, production integration and
native acceptance remain unfinished. These shared-process source timings do
not establish controlled or native performance. Production context scoring and
the published v1.0.8 installer remain unchanged.
