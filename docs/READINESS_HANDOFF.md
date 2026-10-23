# Dictionary and mapping readiness handoff

This records the five-source engine/dictionary snapshot on 22 October 2026.
The current audit passes all ten mechanical requirements. Pronunciation
review, independent held-out quality and spelling-behavior review remain
incomplete. The external conversational baseline also exposes a composition
and ranking gap. The original dictionary-quality acceptance remains outstanding;
a working decoder and complete source accounting do not close that review.

The current priority has since changed to building and testing the project's
real Windows x64 IME, with result correctness tuned later. This file preserves
the dictionary snapshot and outstanding quality work; that review does not
block native operation. The approved persistent installation now registers both
0x0409 and 0x0c04 profile definitions and keeps the AMD64 DLL protected under
Program Files. The non-administrator desktop account enabled 0x0409 without
changing its English default. Fresh ordinary x64 Notepad PID 82468 mapped that
installed DLL (PE 0x8664, SHA-256 f22d1c0f…eba0a2d). Ordinary Windows Ctrl+Shift
cycling and individual letter-key events produced `你好` after `neihou`/Space;
`b`/Escape left it unchanged, and Ctrl+Space then `n` produced `你好n`. No
process-local registration or `ActivateEx` was used. Exact Notepad preedit and
candidate values were not observed through accessibility, and pixel capture
timed out; popup appearance remains unverified. The earlier RichEdit TSF data
is historical evidence. Hong Kong activation, login startup, next-login and
removal behavior, other apps, x86 and Windows 11 remain future checks. See
[the current native status](NATIVE_X64_VALIDATION.md).

## Exact snapshot

The database contains 607,026 text/reading pairs: 137,439 original explicit
pairs, 57,272 supplementary pairs and 412,315 generated pairs. All live pairs
matched selected sources or complete encoding records in the saved audit;
there were no duplicate or unverified pairs. All supplementary winners retain
unknown-frequency weight zero. The observed inventory covers 878 bases and
2,977 toned forms, with 1,440 mapping records and 282 spelling collisions.

The 330,701 text-only Rime inputs are accounted for as 7,455 already explicit,
293,807 mechanically unique, 29,359 ambiguous and 80 path-limited rows. The
80 path-limited results stay quarantined. The selected source boundary and
unchanged human acceptance gates are in
[DICTIONARY_READINESS.md](DICTIONARY_READINESS.md).

SHA-256 values below identify this snapshot, rather than whichever file may
later occupy the same path. A separately invoked build at
`.local/repro-five-source/lexicon.sqlite3` matched both database bytes and
semantic rows. The semantic hash is
`4529344104080eb568410dd89842f2a3643e964dd4cb32226bd3231c8a2133ff`.

| Artifact | SHA-256 |
| --- | --- |
| [Dictionary](../data/generated/lexicon.sqlite3), 265,768,960 bytes | `4353328cb17f8c8f8cc5d78730e34c3aa26c6c8ea7d1a4f4a8f91fee5d900a6e` |
| [Dictionary manifest](../data/generated/lexicon.manifest.json) | `d1641d00f289a419e1f2b460dfc418b68c8dda3da8e842aa8c1e16c7e61f01c0` |
| [Mechanical audit](../data/generated/dictionary-audit.json), captured 19:26 Hong Kong time | `2759faa639f72c24013cfb0cbf4cbcb1b1ea6f0e95c2857451d0e20aa880a9ee` |
| [Observed syllables](../data/mappings/syllables.json) | `5254e4555c8e043367cb62ab9360fb3da85750464a613ec27326000b59ef0b92` |
| [Spelling mappings](../data/mappings/spellings.json) | `0b6fed4339f9a23c6711db0418eb46ed4995497f17359abb470d023ca0fa7c6c` |
| [Mapping manifest](../data/mappings/build.manifest.json) | `c445e2bf1c645245e6834065ce0e684700eb09862d803913f72ffdab6d0e2543` |
| [Current review manifest](../data/review-v2/manifest.json) | `b557acba6da48404ec20a5f85de4a26dbf76fefb88ffba094d80d62da7c36211` |
| [Development seed corpus](../eval/core_cases.json) | `0d705ac210278c498269397173c942863b8fdbb265a9f6d7b1328925395300ed` |
| [Seed evaluation](engine-evaluation.json) | `ef73ae4a69a1cfabf7297d4dcf3bc913545e746d63ddccd0de72110b97df97ea` |
| [Source-derived corpus](../eval/source_coverage_cases.json) | `8d9b2e765119d24a14a1ae6c7067d50b3faec08fd7a8d7d74e59770158c0118b` |
| [Source-derived lookup report](dictionary-lookup-coverage.json) | `73ec039dfcf0824774f6296df020e45889d43a57d5555619cfa36680f0f887a4` |
| [Paged Session replay](paged-typing-evidence.json) | `03671157205d51b0a416190d80c30fab1e759c0129d8414213776f89d31aa214` |
| [Saved unit-test report](unit-test-results.json), 222 tests passed | `f4916e05c3aa48d3cc680ac2134ecfee093bd98d7afef9299a27f001ced6a14f` |
| [Empty held-out template](../eval/heldout_cases.template.json) | `1f94fc539c0e041ebb4e2b35013caf33c3508dd57e23d93d29ff26a82ccbfd02` |

The evaluation records these exact implementation hashes:

| Module | SHA-256 |
| --- | --- |
| [engine.py](../cantonese_ime/engine.py) | `c2b67530f0fa42f14841f37e56369f776d023e4f63f67a4b92ad5085707e4d92` |
| [mappings.py](../cantonese_ime/mappings.py) | `39a19b8b9227153dfb16317b7ef5f223ce95fd005b68c61126248fec1a91872d` |
| [session.py](../cantonese_ime/session.py) | `736010659dd9b1d83472cd318303cf2bdf63c75ca854a2ce6b461fe07bb26c26` |
| [CLI](../cantonese_ime/__main__.py) | `8316f77e3c5086caf478c8664ab938f0464e9735729580f442ddec9164ef3f8a` |

The source locks retain the upstream pins, exact vendor-file hashes, licenses,
attribution, declared scope and exclusions:

| Source lock | SHA-256 |
| --- | --- |
| [Rime](../data/sources.lock.json) | `e33ae4ae7c4be7d7236f2566da2075ee6c96d9f53ebaac2d43f7dbac53254e88` |
| [LSHK](../data/mappings/lshk.sources.lock.json) | `4e8cdb775d3fa396187214f8813a248959aeb8838f704c41f09c481ad38714a1` |
| [words.hk](../data/supplements/wordshk.sources.lock.json) | `630bfd8dac948638537181b176d8a7a1743a054d19d51506574e3fc54eba94d2` |
| [TypeDuck principal](../data/supplements/typeduck.sources.lock.json) | `8aa2dcd72f4d453a0ae8d45f390b2bf2c9b3b8f0e8fa257e725156e2440aa51b` |
| [Unihan](../data/supplements/unihan.sources.lock.json) | `0f986fd73849025ffc9a72fbc686fe9aa5ce8540c995a8a15a23f850b8286505` |

The original 1,055-record review pack at `data/review` remains separate. Its
database, mappings, manifests, evaluation and audit are preserved under
`.local/frozen-aec269`. Its results cannot approve the later snapshot above.

## Human decisions still needed

| Existing incomplete gate | Decision/evidence needed |
| --- | --- |
| `pronunciation_review` | Cantonese judgments on whole-phrase readings, polyphonic alternatives, preferred readings and the quarantine policy. Declare how review covers the remaining generated population; completing a priority subset does not approve every other row. Source-explicit TypeDuck exports and provisional Unihan readings also do not establish independent contextual phrase review. |
| `mapping_behavior_review` | Accept or revise the documented spelling profile, canonical targets, collisions, costs, tones and separate standard/forgiving behavior for intended typing. Mechanical decoder coverage cannot decide whether an informal spelling or pronunciation merger is desirable. |
| `held_out_quality` | Independently authored intended typing tasks, reviewed targets/alternatives, provenance and permission, a frozen corpus and owner-approved criteria established before comparing results. No natural-typing corpus or owner acceptance judgment is supplied. The separate HKCanCor annotation baseline does not replace them. |

The owner can provide concrete decisions in this chat for the identified
snapshot. No extra identity-verification or cryptographic approval process is
required. Record the decision, scope and evidence; a self-reported TSV status
alone does not automatically change the dictionary or pass a readiness gate.
Do not manufacture speakers, preferred readings, reviews or accepted scores.

## Concrete review workflow

1. Use [data/review-v2](../data/review-v2/README.md), whose generated fields were
   independently rederived against this snapshot. It has 1,059 pending records:
   200 prioritized ambiguous phrases, all 80 path-limited phrases, 497 source
   exceptions and 282 spelling collisions. The phrase queue covers 82 of 103
   qualifying polyphonic characters from 29,359 ambiguous source rows; it is
   not full-population approval or a held-out corpus.
2. A speaker/reviewer fills only the designated reviewer columns. Preserve
   generated IDs, raw source fields, proposed alternatives and uncertainty.
   Use evidence addressing the whole phrase and intended context. For source
   exceptions, keep 112 LSHK descriptions, 383 words.hk exceptions and two
   TypeDuck annotated emoji readings distinct; do not strip notation to guess
   a pronunciation. The 2,225 accepted variant annotations stay informational.
3. Validate the returned queue with the command below. Structural validity
   does not approve its linguistic decisions. The owner reviews a concrete
   change proposal and records which rows/policies and residual population the
   decision covers. The existing checklist supplies the required evidence;
   this handoff adds no new sample count or quality threshold.
4. Apply accepted changes as attributed source overrides or explicit policy
   revisions. Preserve the original review files and disagreements. Rebuild
   into a new snapshot, regenerate mappings, run affected regressions and
   refresh evaluation/audit evidence against new hashes. Do not edit the
   generated SQLite rows or overwrite a reviewed pack in place.

```powershell
python tools/build_review_pack.py --output data/review-v2 --validate-only
```

## Empty independent-corpus template

The existing [collection guide](../eval/HELDOUT_COLLECTION.md) and
[empty template](../eval/heldout_cases.template.json) are ready for real
contributions. `cases` is deliberately empty and the evaluator rejects it.
Copy it to a new corpus file when collecting tasks; do not replace it with
dictionary samples or invented Cantonese judgments.

```json
{
  "schema_version": 1,
  "purpose": "Empty collection template for independently authored Cantonese typing tasks; no accuracy evidence yet.",
  "status": "empty_not_frozen",
  "corpus_author": null,
  "reviewer": null,
  "reviewed_at": null,
  "discovery_and_source_overlap": null,
  "acceptance_criteria": {
    "owner_decision": null,
    "minimum_top1_rate": null,
    "minimum_top9_rate": null,
    "latency_measurement_and_target": null
  },
  "default_top_k": 9,
  "cases": []
}
```

Collect a speaker's intended text and natural input spelling before inspecting
engine suggestions. Preserve reviewed alternatives, author/reviewer, date,
permission and discovery/source-overlap notes. Cover the task categories
already listed in the collection guide and validation plan. Positive conversion
cases use the existing evaluator fields; negative/passthrough and key-sequence
tasks need their own expected behavior. Agree criteria, freeze the reviewed
file and record its hash before scoring. Cases used to tune the engine become
development cases and retain that history.

## Original milestones and Windows validation

The [original plan](RESEARCH_AND_PLAN.md) and [validation targets](VALIDATION.md)
remain the reference. Its runtime/frontend reuse proposal was later followed
by the authorized engine/dictionary-first Python reference implementation;
this is not evidence that a real-librime or native frontend build succeeded.

| Original item | Current evidence and remaining work |
| --- | --- |
| First 200 evaluation cases; reviewed 200-case core with an initial target of at least 95% in top 9 | There are 40 development seeds: 34 top-1 and 40 top-9. The 200 source-derived review-queue rows are a different artifact. A reviewed 200-case core and its target assessment remain outstanding; the target was described as initial and revisable after baseline measurements, not already achieved. |
| 500 or more held-out phrases and natural spelling variants, followed by a typing trial | The 500 stored-entry sample produces 600 source-derived requests. Its 597 first-90 hits and three later-page recoveries establish reachability against the dictionary's own contents, not 500 independent held-out phrases. Collection and independent review remain outstanding. |
| Warm conversion p95 below 20 ms; candidate-update p95 below 50 ms | The current seed first-sample p95 is 10.343 ms; source-derived requests have p95 8.759 ms and a 109.049 ms maximum. The separately measured later-pass Session changing-key p95 is 10.597 ms; Session and backend stalls remain. The original HKCanCor baseline has p95 30.958 ms; its development replay has 16.106 ms overall and 23.341 ms for tone-free spans. These are Python lookup/key-event diagnostics; they do not establish representative intended-task or native UI performance. Startup remains about 2.1–2.2 seconds. The 50 ms end-to-end native target remains untested. |
| Native x64/x86 conversion, installation and host compatibility | Persistent machine installation and ordinary x64 Notepad typing verified: protected installed DLL mapped into PID 82468 (both PE 0x8664); Windows Ctrl+Shift selection, individual `neihou`/Space → `你好`, `b`/Escape unchanged, Ctrl+Space/`n` → `你好n`. Both language profiles are defined; 0x0409 is enabled for the non-admin user with its English default unchanged. No process-local activation was used. Exact Notepad preedit/candidate contents and popup pixels remain unobserved. Hong Kong 0x0c04 activation, startup/next-login/removal, other apps, x86, restricted/elevated hosts and Windows 11 remain future checks. |
| Daily typing trial on Windows 10 and Windows 11 | Pending native integration; the local Windows 10 environment cannot establish Windows 11 results. |

No test count, coverage percentage, sampled rank or mechanical source label
substitutes for the outstanding human quality reviews. Those reviews are future
quality work, not prerequisites for the newly prioritized native prototype. The
native phase is not a reason to redo a settled dictionary audit without changed
inputs or a concrete contradiction.

## Additional evidence and remaining work

The [mapping-to-decoder check](mapping-behavior-coverage.json) passes all 1,440
relations, 282 collisions, numeric controls and synthetic paging controls.
Synthetic fixtures establish mechanical behavior; they cannot approve the
spelling profile on a speaker's behalf.

The [long-input assessment](long-input-coverage.json) exposed impossible
syllable splits consuming the completion budget. Filtering committed prefixes
against stored reading prefixes fixes that loss: all 666 shorter-prefix
scenarios now reach the target text, versus 452 before. Exact pairs reach
335/666 scenarios and 187/222 entries through at least one form; 35 entries
remain alternate-reading-only. With the new distinct composed-output pool,
95 exact routes stay within 90 and 240 now appear at ranks 91–92. No exact
route is lost, but some completions require a later page. All 263 literal
over-64 inputs are rejected.
The 64-character cap, future suffix-tone ambiguity, text deduplication and
bounded sentence/completion pools remain visible limitations. Pre-fix reports
are preserved in [baseline notes](baselines/before-stored-prefix-filter/README.md).

The [HKCanCor baseline](HKCANCOR_EVALUATION.md) freezes 250 word types and 250
speech spans before scoring. Fully toned top-9 text coverage is 232/250 and
160/250 respectively; tone-free coverage is 219/250 and 111/250. There are no
request errors. This is an external annotation baseline with measured lexical
and frequency overlap and unresolved upstream training overlap. It is not an
independent 500-task typing trial or a new pronunciation approval. Source labels
and failures are retained without dictionary import or model fitting.

The [distinct-composition update](COMPOSITION_SEARCH_UPDATE.md) corrects
duplicate paths consuming output slots and forward-pruning tie loss. Its
retained-graph search agrees with 10 public synthetic fixtures and 100 exhaustive
synthetic DAGs; the full suite passes 222 tests. All 90 distinct composed texts
are ranked using the existing unigram model, with an explicit work-limit error.
The deliberate pool expansion also moves some completions later. Original
reports are retained in [before-distinct-composition](baselines/before-distinct-composition/snapshot.manifest.json).

The new replay of the same inspected corpus is development evidence: exact-text
top-90 hits rise from 778 to 810, while top-9 falls from 722 to 720. Gains and
losses are both retained; this does not approve ranking quality. The separately
[contextualized seven-reading review](PRONUNCIATION_GAP_REVIEW.md) identifies
lexical/contraction contexts, conflicting tone evidence, a pronunciation
discussion and unresolved orthography. All seven remain pending, and the
original 1,059-row review pack is untouched.

Conversational composition/ranking needs further development, informed by
[coverage/search/source-annotation triage](HKCANCOR_ERROR_ANALYSIS.md) rather than silently accepting all
corpus labels or tuning and calling the same set held out. Any later use for
tuning must preserve this baseline and record its changed development role.
The [changing-query/per-keystroke replay](TYPING_LATENCY.md) now separates
startup, changing input, Session key events and identical snapshot hits.
Its observed p95 does not eliminate outliers or establish representative native
update latency. The separate native smoke now establishes basic TSF behavior,
with its installation and visual limits recorded explicitly.

Future human quality review includes reviewing the pinned queue/profile and
contributing or designating independently authored Cantonese typing tasks and
acceptance criteria. Repeated audits, automatic spelling rules and source
samples cannot supply those decisions. Keep the gates incomplete until actual
decisions and evidence arrive. These future quality reviews do not block the
newly prioritized native prototype.
