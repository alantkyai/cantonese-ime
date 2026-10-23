# Cantonese typing engine

The x64 Windows IME is installed. The development revision described here adds
systematic Yale ASCII input, a 256-character buffer and a CC-Canto vocabulary
expansion; it has not yet replaced the installed numbered-candidate package
(`94c29cf8…`). See the [installed revision record](numbered-candidates-validation.json)
for that separate result. The Python engine supplies offline spelling, dictionary,
ranking and composition services to the native TSF frontend.

## Components

| Component | Responsibility |
| --- | --- |
| `cantonese_ime/dictionary.py` | Build indexed SQLite from explicit and complete generated readings, with source/review ledgers |
| `cantonese_ime/autoencode.py` | Bounded, attributed adaptation of librime phrase autoencoding |
| `cantonese_ime/mappings.py` | Versioned spelling policy and source-attested inventory exports |
| `cantonese_ime/supplements.py`, `wordshk.py`, `typeduck.py`, `unihan.py`, `cccanto.py` | Parse selected supplementary readings with separate source, license, normalization and quarantine policies; Unihan remains provisional character evidence |
| `cantonese_ime/engine.py` | Syllable matching, bounded word/composition search, candidate ranking, completions, and optional selection memory |
| `cantonese_ime/session.py` | Composition buffer, candidate selection, paging, commit, cancel, and mode changes |
| `cantonese_ime/__main__.py` | Local command-line lookup, key replay, and evaluation |
| `eval/core_cases.json` | Development seed inputs and target outputs |

The engine uses a read-only SQLite connection. The dictionary's metadata records
source revisions, source hashes, licensing, and import rules. Its build is
deterministic for the pinned source files. See [data documentation](../data/README.md).

## Spelling and decoding

`jyutping` mode uses canonical dictionary syllables. Tone digits 1–6 are optional
in the lookup API. Supplied tones constrain readings before candidate truncation
and text deduplication. A complete supported letter run followed by a numeric
tone is indivisible: `ngo5` cannot become untoned `ng` plus `o5`. Partially toned
`neihou2` still permits untoned `nei`; an explicit `ng'o5` requests that split.
Apostrophes, or spaces in a lookup request, prevent a
syllable from crossing that boundary.

`forgiving` adds systematic Yale ASCII spelling and the existing per-syllable
alternatives: n/l tolerance, omitted ng, common initial-letter spellings,
selected vowel alternatives, and explicit aliases such as `lay`, `ngoh`, `boh`,
and `sheung`. Plain letters are the intended everyday input; tones are optional.
For example, 火炬 `fo2 geoi6` accepts `fogeui`, and 香港 accepts `heunggong`.
The whole-final conversion preserves closed `aa`: `caa → cha`, `can → chan`,
and `caan → chaan` differ. The 878 observed bases have 778 ordinary table-backed
routes, 96 declared project extensions, and four explicit Jyutping fallbacks
(`hm`, `hng`, `ngm`, `soei`). Yale output is never recursively merged into the
legacy convenience rules. Diacritics and Yale low-register tonal `h` are outside
this profile. See [mapping provenance](../data/mappings/README.md).
These rules retain
canonical readings in the returned candidates. The narrow `shueng` alternative
does not imply general spelling correction. Standard mode does not use these rules.

A spelling trie generates possible syllables. Dictionary-prefix sets prune
impossible word paths. Exact stored entries compete using upstream frequency and
a cost for spelling alternatives. Legacy fuzzy matches are penalized, but a long list of
rare exact readings cannot entirely hide common tolerated readings.

A separate index of each full stored reading's Yale route supplies tone-free
dictionary matches independently of the bounded syllable-path frontier. This
avoids losing a stored word when ambiguous letter splits fill that frontier.
Optional apostrophes must align with actual syllable boundaries; numeric-tone
requests continue through the general decoder's tone-closure rules. The index
preserves spelling collisions and canonical readings. It changes search
reachability, not source readings or word weights, and does not guarantee a
particular word's first-page rank.

For this user's plain-letter Yale input, `Engine(..., prefer_yale=True)` is the
default in forgiving mode. A complete indexed Yale word with at least one
syllable spelled differently from its canonical Jyutping form receives a
first-class base score of 1,100 plus its capped log-frequency term, instead of
being treated as a penalized typo. Thus 尖 `zim1` entered as `jim` now ranks
first in the recorded example rather than 87th. Words whose Yale and Jyutping
spellings are identical keep the existing weighted merger behavior, including
n/l alternatives. Strict Jyutping is unchanged; `prefer_yale=False` opts out of
this ranking preference without removing Yale spellings. Personal selection
memory can still promote the user's chosen candidate above this default.

For a complete tone-free indexed Yale word longer than 64 letters, a fast path
returns all stored matches and exact-input saved phrases while omitting optional
composition and prefix expansion. Its `completion_truncated` flag is true; paging
past the known set raises an explicit capacity error. The threshold selects a
search strategy, rather than lowering the 256-character input limit. Short input
and unknown long compositions retain bounded search. This avoids the measured
expensive optional search for known long words, but is not a latency guarantee:
native IPC and actual incremental keystrokes still need verification.

Continuous sentence input combines dictionary words using additive unigram
frequency costs. A backward dynamic program keeps the best 90 distinct output
texts at each input position. It merges sorted suffix streams lazily with a heap
and deduplicates written text before applying that limit, so duplicate
pronunciation paths cannot spend all the output slots. Equal-cost paths for one
text retain the lexicographically greatest complete reading, matching public
candidate deduplication. Direct whole-input word arcs have their own ranking
branch and do not consume the composition budget.

This replaces the former forward path beam and expands its final composed pool
from at most 32 paths to at most 90 distinct texts. It fixes demonstrated search
loss under the existing objective; it does not add sentence context or change
word weights. The saved development examples still place 我相識叉燒包 ahead of
the intended 我想食叉燒包. A word-transition or contextual ranking model remains
future work. The [independent composition analysis](composition-search-analysis.md)
and [exhaustive synthetic checks](composition-search-analysis.json) separate
search correctness from language-model quality.

Prefix completions supply candidates before the final syllable is finished.
These have lower base priority than full dictionary matches and ordinary
composed outputs. Candidate text is deduplicated after tone filtering.
The completion search discards committed canonical syllable paths that cannot
prefix any stored reading before spending its bounded frontier and query pools.
This prevents impossible internal splits such as repeated `gwong` → `gwo` + `ng`
from crowding out the actual stored-word prefix. The filter applies to stored-word
completion; it does not change ordinary sentence composition, spelling rules,
numeric-tone closure or the search budgets.

The larger composed pool can place a lower-scored completion after the first
90 candidates. Such a completion remains reachable through paging when present
in the retained pool. Ordinary direct, composed and completion score formulas
retain their existing base priorities; changed-syllable full Yale words have the
separate preference described above. Backward rather than forward cost addition can
also change floating-point scores by an ulp; it is not a new ranking feature.

## Public API

```python
from cantonese_ime import Engine
from cantonese_ime.session import Session

with Engine("data/generated/lexicon.sqlite3", mode="forgiving") as engine:
    candidates = engine.lookup("bohim", limit=9)
    assert candidates[0].text == "保險"

    session = Session(engine)
    for letter in "bohim":
        session.handle_key(letter)
    result = session.handle_key("Space")
    assert result.committed == "保險"
```

Each immutable `Candidate` contains `text`, canonical `reading`, numeric `score`,
`match_type`, and `consumed_input`. Match types are `exact`, `fuzzy`, `composed`,
`completion`, or `learned` for a restored personal phrase. All current candidates consume the whole input buffer, including
completions that predict additional text. Scores order candidates within this
prototype; they are not probabilities or confidence percentages.

Input is limited to 256 raw characters and each lookup/page to 1–90 candidates.
Unknown modes and invalid limits raise `ValueError`; unsupported phonetic strings
return no candidates. Word depth follows the dictionary's longest stored entry,
bounded by the input limit. Word-arc discovery retains at most 90 matching rows
per applicable base and ending group, and at most 96 phonetic paths while
extending a stored word. The best-90 composed-text search is exact on that
retained acyclic arc graph; it cannot recover a path discarded during arc
discovery. Completion frontiers and queries have separate bounds. All stored
entries matching a complete decoded input are ranked before text deduplication
and paging; they are not cut off at 90 homophones. SQLite lookup caches are bounded.

Composition has a global 100,000 heap-pop work budget. When it is exhausted
without a complete dictionary match, `CompositionCapacityError` preserves the
last successful engine snapshot; the CLI reports it on stderr with exit status 2.
If full stored words were already found, those words remain available while the
optional composed alternatives are omitted. The returned truncation flag is true,
and paging to the unresolved tail raises an explicit capacity error instead of
claiming that the search was exhaustive. `Session` resolves a prospective buffer or page before
changing its state, so a failed lookup preserves the previous buffer, candidates,
page and selection; the caller can refine, retry or cancel composition.

`Engine.lookup_page(raw, offset=0, page_size=9, mode=None)` returns an immutable
`CandidatePage(candidates, offset, next_offset, completion_truncated)`. Pages
slice one shared ranked snapshot, so their order matches `lookup` and does not
change when another page is requested. At most one query snapshot is retained;
successful learning invalidates it. Offsets are bounded at 10,000 with an explicit
error beyond capacity. All matching direct stored homophones are enumerated;
the composed pool, word-arc discovery and spelling-path frontiers remain bounded.

Prefix completion retains up to 128 matching entries per bounded query, with an
extra probe to detect a truncated tail. It does not load every word beginning
with a single letter. `completion_truncated` exposes that scope and also signals
the composition fallback described above. If paging
reaches the unresolved completion tail, `PaginationCapacityError` asks the caller
to refine input; it does not falsely report that the dictionary has ended.

`Session` fetches pages only when navigation needs them and caches them for
backtracking. A page-fetch failure preserves the buffer, candidates and selection.
Later-page selections can be learned and promoted. Older lookup-only engines
remain supported with a fixed 90-candidate fallback. `SessionResult.has_more`
and `completion_truncated` let a frontend present continuation state.
Page and selected-slot indexes are
zero based. It preserves the original Latin buffer for Enter, cancels on reset or
mode changes, and leaves unsupported key events unhandled. Numeric tones belong
to the lookup API for now; digits in an active session select candidates.

## Optional learning

The reference Engine creates no learning file by default. An explicit
`learning_path` enables local candidate-selection memory; a Session must also
have `learn=True` to record it. The native runtime now explicitly supplies a
per-user store, and its frontend notifies only successful candidate selection.
Enter, cancellation, ordinary lookups and focus-departure literal completion do
not record selections.

The development engine, session and native lookup wire accept 256 ASCII input
characters. Selection notifications accept up to 256 canonical reading tokens
(3,583 ASCII bytes). These bounds are separate from the 256-codepoint selected
text limit and from the frame-size limit; raising input length does not remove
search budgets or make arbitrary sentence input exhaustive.

Preferences are keyed by mode, the exact normalized full input, text and reading.
On a saved selection, competing weights for only that input/mode are multiplied
by 0.8 and the selected weight gains 1, bounded at 5. Ranking uses that adaptive
weight; lifetime count remains informational. Four repeated new choices can
overtake an old saturated preference without matching its lifetime count. A
selected long phrase does not alter any shorter input's preferences. These
constants are project policy, not measured language probabilities.

Learning uses a JSON file and a one-byte sidecar lock. A local process lock and
an operating-system file lock serialize disk read/merge/replace, so separate
writers preserve each other's records. Writes use an atomic replacement.
Malformed data is reported rather than silently replaced. Record and byte limits
bound the file; lower-adaptive-weight records can be evicted when it is full,
with count used as a tie-breaker. The newest
selection is retained. An already running instance refreshes other writers'
changes when it next saves; reopening loads all saved selections for lookup.

Schema 2 stores both `count` and `adaptive_weight`. Schema 1 remains readable;
its count is preserved and its initial adaptive weight is `min(count, 5)`. A
successful later save writes schema 2. Invalid or malformed data is never silently
overwritten. The native broker falls back to conversion-only on startup load
failure and contains later save errors. The raw Engine API reports these errors.

Learning retains a personal ranking override and exact-input phrase memory. A
selected composed phrase remains available for that same full input/mode if a
later bounded static search omits it, with match type `learned` when restored.

Version 1.0.0 also transfers complete selected words and phrases into longer
composition. A trie indexed by mode and normalized entered spelling finds saved
constituents at input positions. Their arcs enter before the 90-row pruning
step, so a selected zero-frequency character is not discarded before ranking.
Each constituent receives a bounded cost reduction (`min(32, 24 * weight)`);
the exact full-input preference remains much stronger. The existing learning
file is reused without a schema migration or a dictionary rewrite.

For example, the lexicon lists 唔 under `ng4`, but lists 唔好 under `m4 hou2`.
Learning `ng` → 唔 now helps compose 唔好 for `ngho` and 唔係咁 for `nghaigam`.
Choosing a full phrase then learns that full spelling separately. This mechanism
also works for other characters and selected phrases; it is not an `ng`/`m`
replacement rule. A learned prefix completion is excluded from constituent
transfer unless the entered spelling actually matches the complete reading.
Mode, explicit boundaries and numeric tone closure remain respected.

Constituent matching has a separate 100,000-step budget and reports truncation
if exhausted. Existing input, composition and paging limits still apply.
No preceding-document/bigram context is used. Ranking evaluations with learning
off retain their exact historical implementation hashes; the old exhaustive
catalog proof is not relabeled as a run of the new personalized decoder.

## Development vocabulary and verification scope

The settled development database has **736,570 text/reading pairs across 621,245
texts**, SHA-256
`3fccc5bcf45cbb676b8a1a51e2030d418803af64b3cd5c0ae7d67cf90a4711bb`.
A separately invoked clean rebuild matches its bytes. The selected
CC-Canto/CC-CEDICT Cantonese snapshots add explicit traditional
and simplified headwords, with no Mandarin lookup codes, definitions, inferred
variants or invented frequency weights. Their source audit admits 213,321
distinct pairs and measures a union delta of 129,609 pairs/125,924 texts against
the preserved 607,026-pair baseline. The final build has those 129,609 new pairs;
65 earlier generated alternatives across 33 texts are superseded by explicit
CC-Canto whole-word readings, giving a net increase of 129,544 pairs. No earlier
text is lost, and the 80 path-limited encoding records remain quarantined.
See the [source audit](cccanto-data-audit.md),
[data license](../data/DATA_LICENSE.md) and
[readiness requirements](DICTIONARY_READINESS.md). The combined transformed
database uses CC BY-SA 4.0 while retaining original component notices.

The independent [Yale coverage report](yale-coverage.json) checks all 736,570
stored pairs' lossless public per-syllable routes and 150 expected conversion
rows. Its 200-pair sample retrieves all 400 compact/apostrophe requests; each
form places 163 targets in the first nine, 186 in the first 90, and 14 on later
pages, with maximum rank 350. It records `prefer_yale=True` and learning off.
This is source-derived route/ranking evidence, not independent pronunciation
accuracy or human typing acceptance. The [checker](../tools/check_yale_coverage.py)
and [earlier mixed-priority baseline](baselines/yale-mixed-priority/yale-coverage.json)
keep those roles distinct. The final full suite passes 354 tests, and the
mechanical audit passes ten automated gates while leaving three human quality
gates incomplete. The [staged validation](yale-ime-validation.json) records the
tested hashes, native IPC checks and canceled installation attempt.
Earlier reports below identify their own
dictionary, mapping profile and runtime hashes. A saved `cantonese-safe-v1` or
64-character result remains historical evidence for that revision.

The independent tests use small dictionaries with ambiguous readings and missing
whole sentences. They cover strict/fuzzy separation, tone constraints, boundaries,
candidate limits, composition, safe dictionary rebuilds, source integrity, and
opt-in memory. Real-data evaluation is recorded in
[engine-evaluation.json](engine-evaluation.json). It measures 40 development seed
targets, not broad user accuracy.

The earlier [full-suite result](unit-test-results.json) records its own pinned
implementation hashes. The current revision's 354-test run is retained in
[the Yale evidence](native-evidence/2026-10-23/yale-preferred/python354-tests.txt).
A real-data Session replay selected 铌 at
rank 193, committed it, and found it first after reopening with the temporary
learning file; see [paging evidence](paged-typing-evidence.json). The temporary
learning file was removed after the test; ordinary learning remains disabled by default.

The preserved five-source baseline contains 607,026 pairs and 878 observed bases. The saved
seed evaluation reports ranking and latency with learning disabled, together
with its exact runtime hashes. Consecutive repetitions normally reuse the query
snapshot, so the aggregate median including cached repeats is not typing latency.
Broad one-letter queries and 64-character ambiguity stress remain slower; these
are reference-engine measurements, not native host responsiveness guarantees.

The [source-derived lookup report](dictionary-lookup-coverage.json) covers 500
stored entries and 600 requests, reporting top-90 ranking, later-page
reachability and hard tone/consumption checks separately. It checks stored-entry
reachability rather than independent pronunciation correctness or user accuracy.

The historical [synthetic mapping exercise](mapping-behavior-coverage.json) passes all 1,440
exported spelling/target relations and all 282 spelling collisions across 15,484
strict/forgiving and tone scenarios. Unique synthetic target texts use the
inventory's source-observed tones; separate controls test numeric closure,
explicit boundaries, partial tones and paging through 257 unique homophones.
Strict prefix completion is permitted and is distinguished from direct alias
interpretation. Two `m` prefix scenarios reach the explicit bounded-completion
capacity error after the direct targets are found. This is mechanical software
coverage, not human acceptance of every alias, pronunciation or ranking decision.

Under the historical decoder's 64-character buffer, some stored phrases could
not be entered in full:
41 stored pairs exceed 64 tone-free letters; 222 exceed 64 fully toned letters
and digits, even without separators. The [long-input report](long-input-coverage.json)
tests those 222 entries in three forms: a fully toned whole-syllable prefix,
tone-free compact input and tone-free apostrophe boundaries, each fitted to the
existing cap. All 666 requests reach the target text after stored-prefix pruning;
the pre-fix report reached 452. In particular, apostrophe forms improve from
33/222 to 222/222 target texts. That search change did not increase the input
limit; the present development revision separately raises it to 256.

Target text and exact stored reading remain distinct. Only 335/666 requests
return the exact source reading; 331 return the same text with another stored
reading. Across the three forms, 187/222 entries have their exact pair reachable
at least once. Unspecified suffix tones, alternate readings and per-text
deduplication remain relevant when a prefix predicts a longer word. These checks
do not establish full-buffer entry of every long reading or contextual correctness.
They are separate from the development seeds, synthetic mapping controls and
future independent quality evaluation. The [preserved pre-fix evidence](baselines/before-stored-prefix-filter/README.md)
records the original runtime and comparison reports.

Remaining quality work includes contextual ranking, an independently reviewed
phrase corpus, and linguistic review of source/generated readings and aliases.
The frozen five-source review pack and its 80 path-limited phrases remain tied
to their original hashes; a new vocabulary build needs its own accounting and
review evidence. Names, new terminology, regional usage and arbitrary Chinese
text are open-ended. Coverage of these named source editions does not establish
that "all Chinese" input is complete, and human typing/layout quality checks
remain separate from mechanical route coverage.
