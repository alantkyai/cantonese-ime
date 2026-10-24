# Surface-aware context: fresh development results

The [aggregate diagnostic](self-improvement-cycle5-surface-development-diagnostic.json) records the frozen inputs, gates and evidence hashes.

The fixed experiment passes all 18 preregistered fresh development gates. All
1,388 attempts (76 pilot + 1,312 development) complete without runtime errors,
capacity fallbacks or source changes. All 1,041 full-pool controls match exactly.
Protected validation is pending at this snapshot; these development requests
were previously exposed and do not establish heldout language accuracy.

| Proper compact input set | Baseline: first 9 / first 90 | Character 0.5 | Surface-aware |
| --- | --- | --- | --- |
| Old 89 ordinary phrases | 66 / 83 | 79 / 87 | 81 / 88 |
| New 30 development phrases | 14 / 22 | 17 / 26 | 17 / 26 |
| Combined 179 primary phrases | 111 / 150 | 136 / 166 | 139 / 168 |

Old 89 first 9 hits by length are 26/29, 29/30 and 26/30 for 4–5, 6–8 and 9–12
characters. Six distinct development phrases absent from both baseline and
zero-control first 90 pools are recovered across seven input forms. There are
zero new first 9 losses on the specified nasal controls against baseline, zero
or character 0.5, across all evaluated forms.

The character factor stays at 0.5. A second 0.5 factor discounts the existing
lexical cost only for observed known-word pairs, using positive association
lift multiplied by `out(previous)/(out(previous)+10)`. The discount is bounded
by that lexical cost. Initial, unknown and missing pairs receive no discount.
The word model uses `None` for initial/unigram backoff and contains no trained
BOS or EOS counts. The experiment reuses the frozen models and counts; it is
not a normalized joint language model, new training run or new word-frequency
estimate.

Every signed regression remains recorded. Against character 0.5 there are 65
text-rank gains and 21 losses, plus 47 reading-rank gains and 20 losses across
the 328 requests. Against baseline (and separately zero), text changes are 182
gains / 36 losses and reading changes 146 gains / 34 losses. Exact text-plus-reading
first 90 coverage drops 74→73 on old 89 and 142→141 on the combined 179 set.
The all 125 new forms also drop 77→76 on reading-pair first 9 coverage. These
declines are not converted into primary text successes or omitted from review.

The generic decoder passes 14,232 exact mechanical comparisons over 595 synthetic
graphs, including allocation/capacity checks. That proof does not establish
typing quality or native performance. The original all-history and habitual
input gates, HKCanCor500 regression replay, controlled performance, and native
application/installer checks remain unfinished. Lookup timing observations are
shared-process source measurements, not Windows TSF/game latency acceptance.

No production integration or installation was performed by this experiment.
The frozen v1.0.8 tag and release assets are unchanged. Only a separate fresh
protected-validation freeze and GO is supported by this development result.
