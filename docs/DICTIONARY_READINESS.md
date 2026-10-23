# Dictionary and mapping readiness

The x64 Windows IME is installed; the current development work expands its Yale
ASCII input and vocabulary. The installed numbered-candidate package remains
`94c29cf8…` until a separately verified update. A usable engine or a green seed
evaluation does not establish a complete dictionary. "All Chinese" is an
open-ended target covering names, new words, regional usage and arbitrary text;
coverage here is measured against named source editions and explicit policies.

The selected source boundary is the pinned Rime Cantonese character, word and
phrase tables, their frequency data, the pinned LSHK table, the words.hk
wordlist/pronunciation snapshot, the TypeDuck principal table, Unicode
18.0.0's direct `kCantonese` character readings, CC-Canto 2017-02-02, and
CC-CEDICT Cantonese Readings 2015-09-23.
The words.hk declaration is scoped to that wordlist; definitions, examples,
media and other API datasets are excluded. TypeDuck selection uses the pinned
README's principal-data CC BY 4.0 declaration; reverse lookups, rich translation
data and `essay.txt` are excluded. Unicode's provisional property is retained
as direct character fallback under the full Unicode License V3 notice, with
no variant inheritance or phrase-autoencoder use. Preserve the
original source files, revisions, hashes, licenses, authorship and modification
notices. Dedicated Rime maps and lettered tables remain excluded; Google and web-input
service dictionaries are not collected. Changing the selected boundary requires
a documented decision, rather than removing a difficult source to obtain a pass.
An explicit export reading does not establish independently reviewed human
authorship or contextual phrase correctness. TypeDuck ranking percentages are
validated but do not become imported frequency values.

CC-Canto selection imports explicit brace-delimited Cantonese readings and
aligned traditional/simplified headwords. Mandarin codes, definitions, inferred
variants and repaired unknown syllables are excluded. The
[source audit](cccanto-data-audit.md) admits 213,321 distinct source pairs and
measures 129,609 new pairs/125,924 new texts against the preserved 607,026-pair
baseline. The settled development build contains **736,570 pairs across 621,245
texts**, database SHA-256
`3fccc5bcf45cbb676b8a1a51e2030d418803af64b3cd5c0ae7d67cf90a4711bb`;
an independent clean rebuild matches its bytes. All 129,609 new pairs are
accounted for. Sixty-five old generated alternatives across 33 texts are
superseded by explicit CC-Canto whole-word readings, rather than silently lost
words; no earlier text is lost. The 80 path-limited encoding records remain
quarantined. The current full suite passes 354 tests; the final mechanical audit
passes its ten automated gates. Pronunciation review, held-out quality and human
mapping review remain incomplete. The [staged validation](yale-ime-validation.json)
records the tested hashes and distinguishes this build from the installed version.
Fourteen source bases remain
quarantined against the declared 878-base admission inventory; absence there does
not establish linguistic invalidity. Review exceptions are retained separately
in [the CC-Canto ledger](../data/review-cccanto/source_exceptions.json).
The [quarantined-form presence check](cccanto-quarantine-coverage.json) separately
accounts for 1,375 distinct parseable forms in those exception records: 512 texts
already occur in the database through other accepted readings, while 863 exact
forms are absent. These include punctuation and lettered forms, not just Chinese
words. One malformed record has no parseable form. Text presence does not accept
the rejected pronunciation; absence of an exact stored phrase does not establish
that the engine cannot compose it. The exception ledger and database are unchanged.

Expansion must also account for the previous dictionary's pairs, texts,
source-specific weights and encoding/review ledgers. A larger total does not
excuse an unexplained earlier-text loss or a change to the autoencoder's source
policy. Compare the settled build with its preserved baseline and resolve such
differences through explicit policy and evidence. Do not overwrite or reinterpret
the frozen v2 review pack as approval of newly generated readings.

The combined transformed data adaptation selects CC BY-SA 4.0, while the original
Pleco sources retain CC BY-SA 3.0 and all earlier component notices remain.
See [the selected source lock](../data/supplements/cccanto.sources.lock.json),
[data license](../data/DATA_LICENSE.md) and
[third-party notices](../data/THIRD_PARTY_NOTICES.md). The data license does not
relicense the independent engine or native frontend code.

The `cantonese-yale-ascii-v2` development mapping computes a plain-letter route
for every admitted base: 778 ordinary table-backed correspondences, 96 declared
extensions, and four explicit Jyutping fallbacks (`hm`, `hng`, `ngm`, `soei`).
This is not a claim that every observed form is formal Yale. Whole-word Yale
matching uses stored canonical readings; it does not infer new pronunciations.
It exports 1,514 spelling relations and retains 298 spelling collisions. Numeric
tone filters are optional, and strict Jyutping remains identity-only. The default
forgiving preference promotes complete Yale words with a changed syllable spelling;
identical Yale/Jyutping forms retain the prior weighted merger behavior. An explicit
`prefer_yale=False` disables that ranking preference, and personal choices can
still override it. The [independent Yale report](yale-coverage.json) covers every
stored pair's route and retrieves all 400 requests in its 200-pair sample, with
later-page retrieval distinguished from first-page ranking. Actual typing and
human spelling review remain separate from these mechanical checks and the
frozen pre-Yale spelling review.

## Acceptance requirements

| Requirement | Concrete evidence needed |
| --- | --- |
| Provenance and reuse | Every selected input matches its immutable source lock. Full licenses and attribution accompany data and generated outputs. Retained third-party notices describe transformations and exclusions. |
| Full selected-source accounting | Every explicit source text/reading pair is retained or has a reviewed exclusion. Every text-only phrase has a complete encoding record or a reasoned quarantine. The initial 330,701 missing-reading rows must not simply disappear from accounting. Supplementary blank and exceptional rows also need an explicit policy and counts. |
| Pronunciation integrity | Explicit readings retain tones and ambiguity. Generated readings identify their source and algorithm. New supplementary pairs retain unknown-frequency weight zero; an exact-text count must not be presented as a reading-specific count. Complete polyphonic alternatives are retained; truncated or unencodable results are quarantined rather than published as a confident single reading. Contextual correctness needs independent linguistic review. |
| Canonical and spelling mappings | Inventory coverage is measured against named sources. Observed syllables are distinct from a claim about all legal onset/final/tone combinations. Source forms absent from LSHK are recorded for review, not automatically called invalid. Forgiving aliases retain all legitimate canonical targets; collision handling, tone constraints and standard-mode separation are tested. |
| Deterministic build | Two independent clean builds from the same lock and configuration produce matching logical rows and database bytes. Preserve the commands, hashes and builder version. Identical copied files alone are not independent-build evidence. |
| Broad held-out quality | Freeze an independently authored and reviewed corpus plus quality acceptance criteria before running it. Cover common and rare characters, colloquial phrases, names, polyphony, tones, boundaries, long input, spelling alternatives and collisions, negative inputs and quarantine cases. Preserve dataset provenance and split discipline. |
| Current executable evidence | Build, unit-test, mapping-generation, audit, lookup, typing-replay and evaluation commands succeed against the current artifact hashes. Stale saved reports or a previous process's success do not prove the current build. |

The existing 40 development seed cases are development coverage. Their top-1
and top-k counts must remain labeled as such, even when every target is found.
No numerical quality threshold is invented here. The original research plan's
larger corpus milestones remain planning requirements; neither test count nor
automatic generation makes a corpus independent or linguistically reviewed.

## Independent mechanical audit

`tools/audit_dictionary.py` uses Python 3.11 and the standard library. It opens
SQLite in read-only mode, independently scans the retained source rows and
database fields, verifies source/manifest hashes and checks any phrase-encoding
ledger. It never builds or repairs a dictionary, installs software or changes
Windows configuration. An explicitly supplied `--output` saves a JSON report;
otherwise the report goes only to stdout.

```powershell
python tools/build_dictionary.py
python tools/build_mappings.py
python -m unittest discover -s tests -v
python -m cantonese_ime lookup "nei5'hou2" --mode jyutping --json
python -m cantonese_ime lookup ngosheungsikchasiubao --mode forgiving --json
python -m cantonese_ime type bohim --keys Down Space --trace --json
python -m cantonese_ime evaluate --repeat 3 --output docs/engine-evaluation.json --json
python tools/audit_dictionary.py --evaluation docs/engine-evaluation.json --output data/generated/dictionary-audit.json
```

To collect independent rebuild evidence, build again into another file and
compare without changing either database:

```powershell
python tools/build_dictionary.py --output .local/rebuild/lexicon.sqlite3
python tools/audit_dictionary.py --compare-database .local/rebuild/lexicon.sqlite3 --evaluation docs/engine-evaluation.json --output data/generated/dictionary-audit.json
```

The audit returns 0 after producing a report, 2 when it cannot inspect the
requested inputs, and 1 with `--require-ready` while requirements are incomplete.
Every requirement reports `pass` or `incomplete` with its actual evidence.
`fully_ready` remains false: the tool deliberately cannot certify independent
linguistic review, held-out quality or product completeness from mechanical
counts. A human readiness decision must review those remaining requirements.

## Preserved five-source snapshot before Yale and CC-Canto expansion

The [saved mechanical audit](../.local/frozen-before-yale-expansion/dictionary-audit.json), captured
on 22 October 2026 at 19:26 Hong Kong time, inspected database SHA256
`4353328cb17f8c8f8cc5d78730e34c3aa26c6c8ea7d1a4f4a8f91fee5d900a6e`.
The dictionary stayed unchanged during that audit, and a separately invoked rebuild matched
database bytes and semantic SHA256
`4529344104080eb568410dd89842f2a3643e964dd4cb32226bd3231c8a2133ff`.

| Checked evidence | Result |
| --- | --- |
| Actual dictionary | 607,026 pairs across 495,321 texts; zero duplicate pairs |
| Reverse provenance | All 137,439 explicit, 57,272 supplementary and 412,315 generated entries matched selected source pairs or complete ledger records; zero unverified entries |
| Forward supplementary coverage | All 38,194 LSHK, 66,370 accepted words.hk, 155,509 accepted TypeDuck and 29,936 direct Unihan source pairs retained; overlapping sources can attest the same live pair |
| Supplementary weights | Every new supplementary winner retained unknown-frequency zero: 7,859 LSHK, 12,157 words.hk, 34,364 TypeDuck and 2,892 Unihan entries |
| Text-only accounting | 293,807 mechanically unique, 29,359 ambiguous, 7,455 already explicit and 80 truncated rows account for all 330,701 inputs; zero generated quarantine leakage |
| Observed mappings | All 878 bases and 2,977 toned forms covered; 1,440 unique mapping records and 282 visible spelling collisions |
| Source exceptions | Exact records for 112 LSHK descriptions, 383 words.hk exceptions and two TypeDuck annotated emoji readings; 2,225 accepted words.hk variant records stay informational |
| Unihan scope | All 29,936 direct `kCantonese` rows retained; 261,323 other-property rows ignored. The versioned archive, extracted readings, final-release header/README and full notice matched retained evidence |
| Input limits | 41 entries exceeded 64 tone-free letters, 222 exceeded 64 fully toned letters/digits and 199 exceeded 64 letters with boundaries; maxima remained 79 and 102 |
| Evaluation evidence | Current dictionary, corpus and all four implementation hashes matched; 40/40 seed targets were within nine candidates and 34 ranked first |

All ten mechanical gates passed. Pronunciation review, independently reviewed
held-out quality and spelling-behavior review remain incomplete, so
`fully_ready` remains false. Source-explicit readings and fewer generated rows
do not establish contextual correctness or independent human review.

The offline suite at that composition milestone passed 222 tests. The completion-prefix search was
fixed without changing dictionary data or spelling policy. All 1,440 synthetic
mapping relations and 282 collisions pass; the long-input check reaches all
222 target texts from each of three shorter-prefix forms. Exact suffix readings
remain ambiguous for 35 entries across those forms, and literal input longer
than 64 characters is still rejected. See [ENGINE.md](ENGINE.md) for the precise
mechanical scope and [saved baseline reports](baselines/before-stored-prefix-filter/README.md).

The separate [external annotation baseline](HKCANCOR_EVALUATION.md) uses 500
fixed HKCanCor cases without importing them or fitting the engine. Fully toned
top-9 coverage is 232/250 word types and 160/250 speech spans; tone-free spans
reach 111/250. Measured lexical/frequency overlap and unresolved upstream lineage
prevent a clean held-out claim. These results expose a conversational quality
gap and do not satisfy any of the three incomplete human gates.

The newer [distinct-composition search](COMPOSITION_SEARCH_UPDATE.md) fixes
duplicate-path crowding under the existing unigram score. Its replay of those
same inspected cases is development evidence: text top-90 changes from 778 to
810 out of 1,000 requests, while top-9 changes from 722 to 720. All earlier
long-input exact-pair routes remain available, although 240 now require ranks
91–92. Independent synthetic graph checks prove the search change's mechanical
scope; they do not approve this ranking/paging tradeoff or the spelling profile.

The separate [seven-reading evidence pack](PRONUNCIATION_GAP_REVIEW.md) narrows
apparent missing-character issues to lexical/contraction contexts, conflicting
tones, a pronunciation discussion and unresolved transcription. All seven stay
pending, with no dictionary import, source-label repair or automated approval.

The preserved [v2 review manifest](../data/review-v2/manifest.json) identifies this
snapshot. Independent validation rederived its generated fields and found
all 1,059 rows pending, with no approval/readiness claim accepted. Validate it
against its frozen inputs:

```powershell
python tools/build_review_pack.py --database .local/frozen-before-yale-expansion/lexicon.sqlite3 --mappings .local/frozen-before-yale-expansion --output data/review-v2 --validate-only
```

Its 200 prioritized ambiguous phrases, 80 path-limited phrases, 497 source
exceptions and 282 spelling collisions are described below. Keep the original
v1 queue and its frozen inputs intact.

## Pinned review snapshot before source expansion

The [review manifest](../data/review/manifest.json) identifies database SHA256
`aec269744279a5d85a9f5ca459b9a04f060ae53c29b975fd4aab132d90fab39d`.
Its 1,055 rows are initially pending. The original database, mappings, manifest,
evaluation and [mechanical audit](../.local/frozen-aec269/dictionary-audit.json)
are preserved in `.local/frozen-aec269` for this queue. Its snapshot predates
the TypeDuck/Unihan expansion and covering-index change. Use a saved audit only
when its database, mapping and implementation hashes match the artifacts being reviewed.
An older report remains historical evidence rather than a pass for changed data.

Validate that original queue against its preserved inputs rather than the
expanded default dictionary:

```powershell
python tools/build_review_pack.py --database .local/frozen-aec269/lexicon.sqlite3 --mappings .local/frozen-aec269 --output data/review --validate-only
```

This historical audit was captured on 22 October 2026 at 18:00 Hong Kong
time. The database remained unchanged during inspection, and the independent
rebuild matched both database bytes and semantic hash
`21663a67ae0e42fdf8221fd74c009521dc626d31ad7b24bd26c38ae3da78c23c`.

| Checked evidence | Result |
| --- | --- |
| Actual live dictionary | 576,125 text/reading pairs across 470,308 texts; zero duplicate pairs |
| Reverse entry provenance | Every 137,439 explicit, 20,016 supplementary and 418,670 generated entry matched selected source pairs or complete ledger records; zero unverified entries |
| Supplementary reading weights | All 20,016 new supplementary pairs retained unknown-frequency weight zero |
| Text-only source accounting | 300,694 mechanically unique, 29,537 ambiguous, 390 already explicit and 80 truncated rows account for all 330,701 inputs; no quarantine leakage |
| Observed mappings | All 873 bases and 2,950 toned forms covered; 1,432 unique mapping records and 280 visible spelling collisions |
| Input-length limitations | 41 readings exceeded 64 tone-free letters; 214 exceeded 64 fully toned letters/digits and 191 exceeded 64 letters with boundaries; maxima were 79 and 102 |
| Current evaluation evidence | Database, corpus and all four fixed implementation-module hashes matched; the seed run found 40/40 targets within nine candidates and 34 ranked first |
| Independent audit tests | 18 passed, including source tampering, frequency policy, malformed/stale evaluation hashes, forged review flags, quarantine and input limits |

All ten mechanical requirements passed for that frozen snapshot. Pronunciation review, independently
reviewed held-out quality and spelling-behavior review remain incomplete, so
overall `fully_ready` remains false. A direct stored homophone can now be
reached through later candidate pages; sentence and prefix-completion searches
retain bounded pools. A reported completion capacity limit is not proof that
the dictionary has no further matching entries.

An earlier iteration copied whole-text frequencies onto new words.hk readings.
That could change the encoder's five-percent reading-selection threshold
without evidence of pronunciation frequency. The corrected build keeps those
new supplementary weights at zero as an unknown-frequency sentinel. Fewer
ambiguous or truncated codes after this policy correction do not establish
better linguistic accuracy.

## Review acceptance checklist

The frozen v2 [review instructions](../data/review-v2/README.md) explain the designated
reviewer columns. These checks turn a returned work queue into a reviewable
change proposal; they do not grant approval automatically.

1. **Identify the exact snapshot.** Retain the original manifest and immutable
   IDs. Run `python tools/build_review_pack.py --validate-only` with the
   snapshot's explicit `--database`, `--mappings` and `--output` arguments to
   rederive generated fields from its named inputs. Preserve reviewer work when inputs
   change by using a new output directory. Do not repair mismatches by editing
   generated text, codes or source hashes.
2. **Record the human review decision.** A concrete review instruction from
   the user in this chat can authorize a decision for the identified snapshot;
   no additional identity or cryptographic verification is required. Record
   that decision and its evidence. A `confirmed` cell, name, timestamp or URL
   inside a returned TSV alone does not instruct the engine or builder to
   apply a change automatically.
3. **Require inspectable decisions.** Record a real review date, preferably
   an ISO timestamp with timezone, evidence and reasoning for every proposed
   confirmation, change or exclusion. Evidence should address the whole phrase
   and intended Cantonese usage, including changed tones, colloquial context,
   names and accepted variants. An algorithm path or character frequency alone
   is insufficient. Preserve uncertainty as `needs_evidence` when appropriate.
4. **Validate proposals before applying them.** Check complete lowercase
   Jyutping tokens with tones 1–6, intended output text, accepted alternatives,
   source/permission details and exclusion rationale. The pack validator checks
   generated content and required fields; it does not authenticate people,
   parse all proposal semantics or enforce a complete date format. Its README
   is guidance, not an editable review record.
5. **Account for coverage honestly.** Completing a priority subset does not
   approve the remaining population. Agree and record the linguistic review
   policy and residual limitations with the owner. Do not introduce an
   arbitrary percentage or sample count as a substitute for that decision.
6. **Apply through a versioned change.** An approved proposal becomes an
   attributed source override or documented policy revision with its evidence,
   not an in-place edit to the generated database. Rebuild, rerun mappings,
   source accounting, regression/learning/paging tests and evaluation. Link
   resulting hashes back to the accepted proposal and retain disagreements.

| Review population | Required decision evidence |
| --- | --- |
| [200 prioritized ambiguous phrases](../data/review-v2/phrases.tsv), selected from 29,359 | Justify preferred whole-phrase readings and other accepted readings in context. The queue covers 82 of 103 qualifying polyphonic characters; it is a priority queue, not full population approval. The 293,807 mechanically unique rows also require a declared linguistic review policy. |
| [All 80 path-limited phrases](../data/review-v2/path_limited_phrases.tsv) | Distinguish seven cases with exactly 32 complete paths from 73 with more paths. Retain original capped codes and the cap disposition. A proposed preferred reading may be supported independently, but selecting it does not prove that the original capped set was complete. |
| [497 source exceptions](../data/review-v2/source_exceptions.tsv) | Keep 112 LSHK descriptions separate from character pronunciation; handle 282 non-Jyutping words.hk readings, 101 slot/ellipsis templates and two TypeDuck annotated emoji readings through an explicit source-aware policy. Do not strip notation or invent character/slot readings. The 2,225 accepted variant-marker records remain informational rather than quarantine. |
| [All 282 spelling collisions](../data/review-v2/spelling_collisions.tsv) | Consider every attested canonical target, identity-versus-alias behavior, rule derivation, cost and input mode. Justify any target suppression; preserve numeric-tone constraints and deliberate standard/forgiving separation. Test actual ambiguous candidates and page navigation after changes. |

The priority counts above are pinned to the v2 review manifest. Differences from
earlier snapshots reflect declared source and weight-policy changes, not
received human judgements.

Held-out evaluation remains a separate gate. Collect intended typing tasks
independently of these source-derived queues and dictionary-oracle smoke tests;
record authorship, consent/licensing, discovery/source overlap and target
judgements. Freeze the corpus and owner-approved acceptance criteria before
comparing engine changes, include difficult and negative cases, and keep all
failures in the report. The current seed and source-derived tests cannot be
relabelled as held-out human accuracy.

`phrase_encodings` is evaluated independently of the build manifest. A complete
encoded result must have valid toned codes and corresponding entries. A
quarantined result must give a reason and must not leak generated entries into
the live dictionary. Counting a text that happens to have some stored reading
is reported separately and does not establish its autoencoding provenance.

SQLite integrity, forward source coverage and reverse live-entry provenance,
duplicate pairs, ambiguous texts, zero
weights, derived reading fields, origins and encoding statuses are reported
from the actual database. Ambiguous readings and zero weights are observations,
not automatic defects. Source syntax validation does not replace pronunciation
review, and an observed syllable inventory is not a complete linguistic grammar.

The report also measures tone-free, fully toned and apostrophe-separated reading
lengths against the implementation's bound: 256 raw characters in the Yale
development revision, versus 64 in the saved earlier reports. Importing a long entry is
not proof that its full reading can be entered; a below-cap reading can also
still be affected by decoder candidate/pruning limits. Prefix completion is
different behavior and must be tested separately.

Hashes and a before/after file identity check detect a database replaced during
the audit. Rerun against a settled build if `stable_during_audit` is false.
Do not infer current process state, completed jobs or open file handles from
older reports; this auditor makes no process-state claim.
