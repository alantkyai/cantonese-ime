# HKCanCor external annotation baseline

This checks the offline reference engine against independently provided corpus
annotations. It is an external baseline, with unresolved upstream dictionary
and frequency overlap. It does not certify a clean held-out test, natural
keyboard spelling, human acceptance, or a native Windows IME.

This document preserves the original `dd9e6c46` baseline. The later
[distinct-composition development replay](COMPOSITION_SEARCH_UPDATE.md) is
reported separately, with its gains and losses; it does not replace this file.

## Frozen inputs and source boundary

The original corpus is credited to K. K. Luke and May L. Y. Wong and retained
under CC BY 4.0, at
[fcbond/hkcancor revision 39aeadf](https://github.com/fcbond/hkcancor/tree/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65).
The [source audit](HKCANCOR_EVALUATION_SOURCE.md) describes provenance, annotation
limitations, licensing and measured lexical overlap. Its 58 original UTF8
transcripts contain 10,801 source utterances and 160,836 tagged lines. No corpus
reading or frequency is added to the dictionary or used to fit this engine.

The [500-case corpus](../eval/hkcancor_cases.json) was selected and its
[freeze record](../eval/hkcancor.freeze.json) saved before the first engine
scoring run. SHA-256 identifies the selected cases:
`410f4b612ca14e5e60da0b147f7bf9fb4b4a1e25c125053e00596981b72ef085`.
The policy hash is
`0147f0efb08e69d412c4d208ac66961233c1dd65860c267d377aeabf4ce06a80`.
The dictionary remains the five-source snapshot
`4353328cb17f8c8f8cc5d78730e34c3aa26c6c8ea7d1a4f4a8f91fee5d900a6e`.

There are two equally sampled strata: 250 distinct word/reading types from
6,564 eligible types, and 250 distinct speech spans from 19,578 eligible types.
Selection takes the lowest SHA-256 of unit, text and reading. Frequency,
dictionary membership and engine ranks do not influence eligibility or
selection. There are no selected cross-stratum duplicate text/reading pairs.
Source occurrence counts are retained but do not weight the type-level scores.

A speech span is a maximal consecutive sequence of eligible source tokens
within one utterance, with at least two tokens. Punctuation and every
unsupported annotation end a span; text on either side is never silently joined.
Only source Han targets with complete lowercase numeric Jyutping syllables
1–6 are eligible. No inventory membership filter, tone conversion, spelling
guess, orthographic normalization or character/syllable-count correction is made.
An entire span is excluded when its fully toned compact input exceeds 64 raw
characters; it is not clipped to an easier prefix.

All 160,836 tagged lines are accounted for: 128,134 eligible tokens, 29,904
source-POS punctuation tokens, 2,768 non-ideographic targets and 30 unsupported
`/@` annotations. Of 30,427 maximal eligible-token runs, 23,604 occurrences
qualify as spans, 714 exceed the input limit and 6,109 contain just one token.
Repeated eligible occurrences are deduplicated into the type populations above.
The source POS anomaly and character/syllable mismatch remain documented source
facts; neither is silently corrected. The initial unscored collection used a
less precise annotation-status label; it is preserved in
[eval/baselines](../eval/baselines/hkcancor-cases-initial-collection.json).
Only that label and structural/input-protection checks changed before freezing;
the 500 selected targets and inputs did not change.

## Scoring and interpretation

Each case is looked up once with all source tones and once with tones removed,
in strict Jyutping mode with learning disabled. These are mechanically derived
canonical inputs, not a speaker's observed typing. Report exact source-text
rank and exact source-text-plus-reading rank separately at 1, 9 and 90. A
completion counts only when its full output equals the target. No unreviewed
alternative orthography is accepted, and no later page is relabeled as a
first-90 success.

Whole-text and whole-pair dictionary overlap is measured after selection and
reported in separate cohorts. Absence of a whole utterance from the dictionary
does not establish unseen constituents or independent training/frequency
provenance. Source spelling conventions and annotation errors can affect exact
matching, so a miss needs inspection before being judged a wrong pronunciation.

The stored-prefix completion fix was identified using the dictionary-derived
long-input check and tested before this corpus was scored. The frozen record
binds the resulting engine revision. No failures from this external baseline
have been used to tune its ranking or dictionary. If that happens later, retain
the baseline and call subsequent use development, with that history recorded.

Results are saved in [hkcancor-evaluation.json](hkcancor-evaluation.json).
The original human pronunciation, spelling-profile and independently authored
typing gates remain incomplete. No acceptance percentage is set by this test.

## Observed baseline

The stable engine was `dd9e6c46a702a945098b0a1c4c8dc54fb9c82e1aeb763430897b207ea4157d7e`.
All 1,000 requests completed with nonempty candidate lists and no exceptions or
consumed-input mismatches. Exact source-text results were:

| Unit and input | Top 1 | Top 9 | Top 90 |
| --- | --- | --- | --- |
| 250 word types, fully toned | 183/250 (73.2%) | 232/250 (92.8%) | 241/250 (96.4%) |
| 250 word types, tone-free | 144/250 (57.6%) | 219/250 (87.6%) | 232/250 (92.8%) |
| 250 speech spans, fully toned | 114/250 (45.6%) | 160/250 (64.0%) | 177/250 (70.8%) |
| 250 speech spans, tone-free | 46/250 (18.4%) | 111/250 (44.4%) | 128/250 (51.2%) |

Fully toned exact-pair counts equal exact-text counts in these scenarios.
Tone-free exact-pair top-9 counts are lower: 205 word types and 94 spans. Text
deduplication can show the same written target with another reading; do not
present text success as pronunciation success. Of the 500 selected targets,
218 exact pairs and 221 texts are already stored in the dictionary. Cohort
scores are included in the JSON, with none removed from these denominators.

This exposes a substantial conversational composition/ranking gap even with
source tones. Passing development seeds and mapping controls does not close
that gap. Missing targets need coverage, search, ranking and source-annotation
triage before a linguistic judgment; automatic addition or ranking adjustment
against these labels would change their role to development data.
The [read-only error analysis](HKCANCOR_ERROR_ANALYSIS.md) separates missing
stored constituents from theoretically composable targets and bounded-search
or ranking limits; it does not change the baseline scores or source labels.

The request-level median was 4.645 ms, p95 30.958 ms and maximum 128.062 ms.
Tone-free spans were slower (p95 41.533 ms). These are sequential in-process
lookup diagnostics, with startup separate and without same-query repetition;
they are not per-key timing or native UI latency and do not establish the
original warm-conversion target on intended user tasks.

## Reproduction

No network, package installation or Windows registration is needed after the
pinned source files have been retained.

```powershell
python tools/evaluate_hkcancor.py --collect
python tools/evaluate_hkcancor.py --output docs/hkcancor-current-replay.json
```

Collection refuses to replace a different frozen corpus. Evaluation rederives
the complete source-only corpus and checks all locked source hashes, the
database, corpus and implementation hashes before publishing a report. Fixture
tests cover damaged structure, unsupported annotation barriers, source POS,
long-span exclusion, inventory-independent sampling, separate text/reading
metrics and frozen-input protection.
Use an explicit new report path when replaying a different engine; the tool's
historical default report path is the frozen baseline above. Running the current
engine cannot reproduce the old engine's ranks merely by retaining its corpus.
