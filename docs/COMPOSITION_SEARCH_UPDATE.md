# Distinct composed-phrase search

The old composer could lose valid suggestions because several readings or word
segmentations of the same text consumed its path beam. A nine-prefix fixture
returned only eight outputs; another fixture with four distinct outputs returned
only one. Forward pruning also reversed a text-order tie when a suffix was
appended, changing the correct first suggestion under the existing score.

The replacement keeps the best 90 distinct suffix texts at each reachable
input position, merging sorted word/suffix streams lazily. It excludes whole
input word arcs before applying the composed-output budget; those words retain
their separate direct priority. This fixes search under the existing unigram
score without adding dictionary readings, changing weights or fitting a
language model. It also deliberately expands the old 32-path publication pool
to 90 distinct composed outputs.

The guarantee covers the retained word-arc graph. Phonetic frontier and per-end
word-arc limits still apply; the search does not recover arcs they discard.
The 100,000 heap-pop budget raises `CompositionCapacityError` instead of
publishing a silently incomplete result. CLI handling returns an error, and
Session preserves its previous composition. Tiny floating-point tie changes
from reversed addition order remain documented. See [engine details](ENGINE.md).

## Evidence

- [222 unit tests](unit-test-results.json) pass, including real counterexamples,
  tone constraints, stable composition pages, capacity handling and frontend
  state preservation.
- The [independent checker](composition-search-analysis.md) matches the new
  implementation against all 10 public synthetic fixtures and 100 seeded DAGs
  with 39,602 exhaustively enumerated paths. It uses no external corpus or live
  dictionary. The previous engine matches one of those 10 fixtures.
- All 1,440 mapping relations, 282 collisions and their numeric/paging controls
  still pass. Dictionary contents and source locks are unchanged.

## Corpus replay: gains and losses

The original [HKCanCor report](hkcancor-evaluation.json), source cases and
pre-score freeze remain unchanged. A [new replay](hkcancor-distinct-composition-replay.json)
uses the same 500 cases in both input forms, retaining all 1,000 requests.
This is a post-hoc development comparison of a previously inspected corpus,
with unresolved upstream overlap, rather than a new held-out quality result.
All individual threshold gains and losses are in
[composition-corpus-comparison.json](composition-corpus-comparison.json).

| Metric, all 1,000 requests | Previous | New |
| --- | ---: | ---: |
| Exact text top 1 | 487 | 487 |
| Exact text top 9 | 722 | 720 |
| Exact text top 90 | 778 | 810 |
| Exact text and reading top 1 | 475 | 476 |
| Exact text and reading top 9 | 691 | 686 |
| Exact text and reading top 90 | 736 | 762 |
| Errors / empty lists | 0 / 0 | 0 / 0 |

At the text top-90 threshold, 53 requests gain a hit and 21 lose one; at top 9,
two gain and four lose. The replay therefore supports better aggregate
first-90 coverage, not universal ranking improvement. Fully toned word top-9
coverage remains 232/250; fully toned spans change from 160/250 to 157/250,
and tone-free spans from 111/250 to 112/250. More complete search exposes the
limitations of the unigram model and source orthography; it does not establish
linguistic readiness.

## Completion and timing tradeoffs

The [long-input report](long-input-coverage.json) retains all 666 target-text
routes and exactly the same 335 exact-pair routes. Of those exact-pair routes,
95 are still within 90 and 240 now appear at ranks 91–92. No exact pair is lost,
but some completions need an additional candidate page because more composed
outputs precede them. All 222 entries retain a text route, 187 an exact-pair
route through at least one prefix form, and 35 remain alternate-reading-only.
The literal 64-character limit is unchanged.

The [same-workload timing comparison](TYPING_LATENCY.md) records a later-pass
Session changing-key p95 of 10.597 ms, versus 14.521 ms before. Current Session
maximum remains 97.666 ms and backend outliers reach 251.657 ms. These are
observed Python lookup/key-event timings; separate runs do not prove causality,
remove stalls or establish native UI responsiveness.

The [seven-reading evidence review](PRONUNCIATION_GAP_REVIEW.md) separately
documents lexical/contraction contexts, conflicting tones, a pronunciation
discussion and unresolved transcription. None is automatically imported.
Human pronunciation, spelling-profile and independently authored typing
acceptance remain outstanding. Native Windows installation and testing remain
deferred.
