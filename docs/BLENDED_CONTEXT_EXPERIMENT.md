# Blended character context: rejected experiment

The fixed corpus-blended character factor failed four original fresh quality
gates when combined with the existing bounded word discount. The candidate was
rejected after the pilot and original fresh campaign, with no later learned,
external, controlled-latency or native stage and no parameter retuning.

This experiment reused the frozen character model and its reader; it created
no new counts, training or downloads. The character conditional backs admitted
TRAIN bigrams with a lexical conditional. All 7,620 lexical/TRAIN union classes,
including the 13 TRAIN-only classes, remain known; one unknown class covers
other codepoints. The state radix is 7,621 so every existing class is represented.
This changes identifiers without enlarging the 1,024 allocated-state budget or
other search caps. The 3,017,352-byte character payload has SHA256
`524589c75bc0ac0717ecc2f0cfa74b4d3974a3b12b42ad97afef44abe836df8f`.

Character and word weights stayed at 0.5 each, the habitual alias cost at 0.8,
and learning, dictionary, search, smoothing, clipping, quantization, targets and
thresholds stayed fixed. The adapter preserves the reader's initial/unknown
arithmetic. Its unweighted costs use this experiment's explicit 0.5 character
coefficient; the historical model header was not rewritten. Character and word
factors share TRAIN evidence, so the combined objective is not an independent
normalized joint language model.

The 19-request pilot completed 38 calls across two constructors. All 19
quantized-zero full first-90 pools, floathex scores and page metadata matched
the saved cycle5 controls exactly. The candidate reached 13/19 intended texts
in the first nine and 18/19 in the first 90; exact-reading pairs reached 13/19
and 17/19. Against the saved surface candidate, text ranks had three gains,
seven losses and nine ties; reading ranks had three gains, six losses and ten
ties. Clean mechanics permitted the separately authorized fresh campaign;
these pilot observations did not establish quality acceptance.

All 402 original forms then completed under one fresh constructor: 93 cases,
including 89 ordinary proper inputs, 29 ordinary habitual inputs and the
additional habitual short control. Runtime checks passed, but quality failed.

| Fresh group | New text first 9 | New text first 90 | Previous surface text first 9 / 90 | New exact-reading pair first 9 / 90 |
| --- | ---: | ---: | ---: | ---: |
| Proper inputs | 76/89 | 88/89 | 81/89, 88/89 | 65/89, 73/89 |
| Habitual inputs | 26/29 | 27/29 | 26/29, 27/29 | 23/29, 24/29 |

Written-text coverage does not imply exact-reading coverage. Proper first-page
hits by length were 26/29 for 4–5 characters, 28/30 for 6–8 characters and
22/30 for 9–12 characters.

| Failed original gate | Observed hits | Required hits |
| --- | ---: | ---: |
| Proper first 9 | 76/89 | 81/89 |
| 9–12-character first 9 | 22/30 | 24/30 |
| Habitual first 9 | 26/29 | 27/29 |
| Habitual first 90 | 27/29 | 28/29 |

Across all 402 forms, text ranks had 43 gains, 92 losses and 267 ties;
exact-reading ranks had 26 gains, 73 losses and 303 ties. All 804 signed
records, complete pools and failures remain in private evidence. No successful
subset replaced the full denominators. The earlier occurrence-only candidate
remains rejected, and the original surface candidate's two fresh habitual
failures remain unresolved.

Both stages total 440 explicit lookup calls and three constructors, with no
runtime exceptions, capacity failures, selection writes or query retries.
Normal internal model and SQL work was unmeasured, not zero. Source/shared-process
timings include engine-owned guards and a small call counter; they do not
establish controlled or native latency. The 27 evaluator and 17 runtime-adapter
synthetic checks establish scoped mechanics, not installed-IME acceptance.

Independent saved audits reconstructed all pools, ranks, signed comparisons,
raw constraints and metadata. The first saved auditor failed on a missing key:
it requested `expected_metadata_sha256` instead of the binding's mandatory
`expected_variant_metadata_sha256`. A one-key correction in both auditors
preserved the exact metadata check. The earlier source and failure remain
archived; the same completed results were audited without an Engine rerun.
Actual payload byte-guard and lifecycle assertions remain source-bound
producer witnesses rather than independent auditor payload snapshots.

These are exposed development cases with historical training overlap, not new
held-out or representative language accuracy. This fixed interaction's outcome
does not identify a source-level cause for any individual failure. See the
[numeric diagnostic](self-improvement-cycle7-blended-diagnostic.json).
Production context scoring is disabled; no model was selected or installed.
The horizontal/vertical candidate layout remains a development change with
installation pending. Published v1.0.8 tags and installer assets remain unchanged.
