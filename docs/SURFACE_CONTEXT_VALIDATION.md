# Surface context: fixed fresh validation

The fixed surface-aware candidate passes all 13 preregistered fresh validation
gates. All 500 attempts complete without runtime errors, capacity/truncation
records, invalid metadata or source changes. These are 125 input-form requests
per arm across four arms, covering 30 distinct phrases: four forms for each
phrase plus five habitual-ng requests. Forms are not additional independent
phrases. The [aggregate record](self-improvement-cycle5-surface-validation-diagnostic.json) retains the metrics,
gates and evidence hashes.

| Input set | Baseline: first 9 / first 90 | Character 0.5 | Surface-aware |
| --- | --- | --- | --- |
| Proper compact input, 30 phrases | 12 / 21 | 15 / 23 | 15 / 23 |
| All 125 input-form requests | 66 / 98 | 79 / 104 | 80 / 104 |

The zero control has the same hit counts as baseline. Three distinct written
phrases absent from both baseline and zero first-90 pools are recovered on
eligible inputs. No individual nasal-control first-nine loss occurs against
baseline, zero or character 0.5 in any evaluated form.

The limits remain substantial: only 15 of 30 proper inputs place the intended
phrase in the first nine, and only 4 of 11 inputs in the 9–12-character band
do so. Proper first-nine and first-90 coverage equals the character-only arm.
The baseline gains therefore must not be attributed to the word discount
alone. Passing these incremental gates does not establish satisfactory general
long-sentence typing.

All signed regressions remain recorded privately. Across the 125 requests,
surface-aware scoring has 25 text-rank gains and 11 losses against character
0.5, and 16 reading-rank gains and 11 losses. Against baseline, and separately
zero, the counts are 48 text-rank gains / 16 losses and 39 reading-rank gains /
13 losses. Two saved-only assessors reconcile all 500 attempts, all 13 gates,
and all 295 signed text/reading change records. Equal hit totals do not erase
individual ranking losses.

This project-curated, within-cycle validation is not representative Cantonese
accuracy. The candidate, models, coefficients and limits were fixed before this
run. The formerly reserved set is now exposed evaluation evidence and must not
be used to retune this candidate or presented as untouched in later tuning.
Raw phrases, input strings, readings, case identifiers and ledgers remain local.

The original all-history gates remain unfinished: SHORT uses five units selected
twice each; HEAVY uses twelve units selected thirty times each. The original
habitual-input group, dynamic constituent reuse and independent short/full-input
preferences, persistence/cache/capacity behavior, HKCanCor500 regression replay,
controlled performance and native Windows x64/application checks remain required.
The original quality thresholds and performance limits are unchanged. This
fresh experiment does not validate personalization or native latency.

No production context scoring was enabled and nothing was installed by this
experiment. The published v1.0.8 tag and installer assets are unchanged. The
result supports only a separately frozen next stage toward the full goal;
it does not select or approve a release.
