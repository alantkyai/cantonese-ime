# Curated sentence-type context: rejected experiment

The fixed C8 candidate failed one original fresh quality gate: ordinary habitual-input first-nine coverage was 26/29, below the required 27/29. The candidate was rejected after the original pilot and full fresh campaign. No learned-profile, external, controlled-latency, integration or native stage followed, and no parameter retuning occurred.

This experiment newly fitted character counts from the original TRAIN split of [CTCPC BASE](https://huggingface.co/datasets/raptorkwok/cantonese-chinese-parallel-corpus-base/blob/5e047fe1764e50868b22ae6f1c191ede448f4f26/README.md). Its pinned first-party card declares CC0 1.0; the declaration does not establish original row ownership or linguistic correctness. Existing [lexical notices](../data/THIRD_PARTY_NOTICES.md) remain applicable. Empty Cantonese strings were excluded before exact sentence deduplication, without stripping or Unicode normalization. Fixed Han ranges split maximal runs; two exact complete runs matched the existing opaque exclusion list. This tests the fixed sentence-type-weighted data recipe, not a pure corpus-size effect or natural usage frequency.

| Count unit | Verified total |
| --- | ---: |
| Original TRAIN rows | 109,942 |
| Empty strings / nonempty duplicate occurrences excluded | 5 / 6,964 |
| Unique exact nonempty sentence types | 102,973 |
| Maximal Han runs / retained runs | 196,049 / 196,047 |
| Character occurrences / adjacent-pair occurrences | 1,379,235 / 1,183,188 |
| TRAIN character types / pair types | 6,165 / 254,031 |

The new character counts replace the old conversational counts while retaining lexical backoff. The 4,820,448-byte model has 8,353 positive classes: 7,607 with lexical mass and 746 with only curated TRAIN support, plus one unknown bucket. Radix 8,354 does not enlarge the 1,024 allocated-state budget. The C5 word prior, character/word-association weights 0.5/0.5, alias cost 0.8, quantization, clipping, learning, dictionary, direct tiers and caps stay fixed; initial None and unknown arithmetic remain distinct. Independent count replay matched every decision, table, ID, header and payload byte. Numeric checks covered 58,478 pairs in seven complete previous-context rows with zero mismatches. The 38-call/two-constructor pilot matched all 19 saved quantized-zero first-90 floathex pool/page controls; candidate text and reading pairs both reached 16/19 first-nine and 18/19 first-90. Pilot text ranks had five gains, eight losses and six ties; reading ranks had five gains, seven losses and seven ties against the saved surface candidate.

All 402 original forms completed under one fresh constructor, covering 93 cases, 89 ordinary proper inputs, 29 ordinary habitual inputs and the additional habitual control. Runtime mechanics passed; 13 of 14 gates passed. Proper written first-nine coverage by length was 27/29 for 4–5 characters, 30/30 for 6–8 and 28/30 for 9–12; first-90 coverage was 29/29, 30/30 and 29/30. Written-text coverage does not imply exact-reading coverage. All 804 signed text/reading records and complete pools remain in private evidence; no successful subset replaces the full denominators.

| Fresh group | New text first 9 / 90 | Previous surface text first 9 / 90 | New exact-reading pair first 9 / 90 |
| --- | ---: | ---: | ---: |
| Proper inputs | 85/89, 88/89 | 81/89, 88/89 | 70/89, 73/89 |
| Habitual inputs | 26/29, 28/29 | 26/29, 27/29 | 23/29, 25/29 |

| All 402 forms: rank changes against saved surface results | Gains | Losses | Ties |
| --- | ---: | ---: | ---: |
| Written text | 80 | 62 | 260 |
| Exact-reading pair | 56 | 56 | 290 |

Both quality stages total 440 explicit lookup calls and three constructors, with no runtime errors, capacity failures, selection writes or query retries. Normal internal model/SQL work is unmeasured, not zero; source/shared-process timing does not establish controlled latency. These curated rows and exposed project cases are not source-disjoint or new held-out accuracy evidence, and the outcome does not identify a cause for any individual ranking change. The engineered bounded score is not a normalized independent joint model. No model was selected, production-enabled, installed or released; published v1.0.8 remains unchanged. See the [numeric diagnostic](self-improvement-cycle8-curated-diagnostic.json) and [previous blended experiment](BLENDED_CONTEXT_EXPERIMENT.md).
