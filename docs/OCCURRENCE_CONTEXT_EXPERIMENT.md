# Occurrence character context: rejected experiment

The fixed occurrence-character model failed four original fresh quality gates.
It was not selected, installed or enabled in production. Testing this model
stopped after the pilot and original fresh campaign; no later learning,
external replay, controlled latency or native stage ran for it.

This single data ablation replaced the character factor's lexical-type counts
and vocabulary with admitted conversational TRAIN occurrences. The character
and word weights stayed at 0.5 each, the habitual-spelling alias cost at 0.8,
and smoothing, clipping, quantization, learning, dictionary, search, resource
caps, targets and quality thresholds stayed fixed. No parameter sweep followed.

The model contains 2,295 positive-count character types plus one unknown
bucket, 128,253 character occurrences, and 30,579 bigram types representing
110,076 occurrences. Counts come from 18,177 admitted segments across 39 TRAIN
groups and 48 files, preserving repeated occurrences and segment boundaries.
There are no observed beginning/end tokens. Probabilities normalize before
cost clipping; the combined surface objective is not a normalized joint
language model. The payload is 395,299 bytes, SHA256
`bd047ab07832c08744c73d88add646061c892cbaa1e4b103348b29410b6221a8`.

The 19-request pilot completed 38 calls across two constructors. All 19
quantized-zero full pools and page metadata matched the saved cycle5 control
exactly. The candidate reached 13/19 intended texts in the first nine and 19/19
in the first 90. Against the previous surface candidate, text ranks improved
on four requests, worsened on nine and stayed equal on six; exact-reading ranks
had three gains, nine losses and seven ties. These pilot observations permitted
the separately authorized fresh campaign, without accepting its quality.

All 402 original input forms then completed under one fresh constructor:
93 cases, including 89 ordinary proper inputs, 29 ordinary habitual inputs and
the additional habitual short control. Runtime checks passed, but quality did
not. The previous cycle5 results below use the same saved inputs and targets.

| Fresh group | New text first 9 | New text first 90 | Previous text first 9 / 90 | New exact-reading pair first 9 / 90 |
| --- | ---: | ---: | ---: | ---: |
| Proper inputs | 73/89 | 89/89 | 81/89, 88/89 | 62/89, 73/89 |
| Habitual inputs | 25/29 | 27/29 | 26/29, 27/29 | 22/29, 24/29 |

The 89/89 result is written-text coverage, not exact-reading coverage.
Proper first-page hits by length were 26/29 for 4–5 characters, 25/30 for
6–8 characters and 22/30 for 9–12 characters.

| Failed original gate | Observed hits | Required hits |
| --- | ---: | ---: |
| Proper first 9 | 73/89 | 81/89 |
| 9–12-character first 9 | 22/30 | 24/30 |
| Habitual first 9 | 25/29 | 27/29 |
| Habitual first 90 | 27/29 | 28/29 |

Every form and regression remains recorded. Across all 402 requests, text ranks
had 48 gains, 139 losses and 215 ties; exact-reading ranks had 30 gains,
117 losses and 255 ties. All 804 signed records remain in private evidence.
The one additional proper-text first-90 hit does not offset the failed gates.
The earlier cycle5 candidate's two fresh habitual failures also remain unresolved.

Across both stages, all 440 explicit lookup calls and three constructors
completed with no quality/runtime exceptions, capacity failures or selection
writes. Normal engine-internal model and SQL work was unmeasured, not zero.
Shared-process lookup timing does not establish controlled or native latency.

An independent TRAIN replay matched all character counts, outgoing counts,
bigram counts and class IDs; its normalization checks used count algebra, not
probability API calls. Independent saved audits reconstructed pools, ranks,
counter constraints and signed comparisons. Runtime lifecycle and source-byte
guard assertions remain tied to the pinned executed source and receipts.
The first source preparation failed before provider and runtime-entry generation; after a reviewed
file-stat guard correction, the second succeeded without changing the model
or scoring. Its exact earlier failing stat field was not captured.

These are exposed project-authored development cases, with historical training
overlap, not new held-out or representative language accuracy. The ablation
shows the outcome of replacing this factor's data and vocabulary; it does not
identify a source-level cause for any individual ranking failure. The
[numeric diagnostic](self-improvement-cycle6-occurrence-diagnostic.json) retains
the aggregate results and evidence hashes. Production context scoring and the
published v1.0.8 tag and installer assets remain unchanged.
