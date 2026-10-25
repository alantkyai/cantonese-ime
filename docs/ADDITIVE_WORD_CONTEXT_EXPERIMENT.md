# Additive word context: fresh and saved-preference gates passed

Independent saved audits confirm all 14 original fresh gates and all 27 candidate gates across the original three preference profiles passed. All twelve comparison cells are complete and runtime-clean. The candidate is eligible for separately authorized later checks only. No model selection, production enable, native or release acceptance follows. C8 and C9 remain rejected and stopped.

C10 adds new word-adjacency evidence to the original conversational word counts. It retains every one of the existing 5,591 word surfaces and IDs, with one unobserved unknown bucket. The character factor is exactly C8, including its lexical marginal for initial `None`; C9's initial-character change is not used. Character/word-association weights remain 0.5/0.5, alias cost 0.8, quantization scale 1,000,000, and the existing clipping, dictionary, learning behavior, direct tiers, retained paths, tie rules and query caps stay fixed. Word costs remain unclipped.

The new source is the admitted original TRAIN split of [CTCPC BASE](https://huggingface.co/datasets/raptorkwok/cantonese-chinese-parallel-corpus-base/blob/5e047fe1764e50868b22ae6f1c191ede448f4f26/README.md). Its pinned first-party card declares CC0; the original [HKCanCor](https://github.com/fcbond/hkcancor) attribution and CC-BY-4.0 notices remain with the derived artifact. These declarations do not establish individual sentence ownership or linguistic correctness. Empty Cantonese strings are excluded before exact whole-sentence deduplication, without stripping or normalization. Every remaining maximal run in the fixed Han ranges is an instance, including repeated runs in different retained sentences. The existing opaque exclusion applies only to exact complete runs.

Offline forward-longest matching uses the complete fixed word vocabulary, without a word-length cutoff or new vocabulary. Each unmatched scalar is privately ledgered as an unknown event and breaks word adjacency. It contributes no observed unknown unigram or pair. Known tokens and adjacent known-token pairs are counted within uninterrupted chains; punctuation, unknown events, runs and sentences are never bridged. New integer counts are added once to the original counts, with no rescaling. Original transcribed-word events and curated sentence-type matching events have different units and domains: their sum is an explicit engineering mixture, not natural usage frequency or validated linguistic segmentation. Runtime decoding still preserves its retained alternative segmentations.

| Derived word artifact | Verified aggregate |
| --- | ---: |
| Positive word IDs / unknown buckets | 5,591 / 1 |
| Combined word-token count | 1,057,037 |
| Combined positive adjacent-pair types | 216,294 |
| Payload bytes | 2,699,360, approximately 2.7MB |

Independent count replay compared the original IDs, every sentence/run/token/fallback decision, all original/new/combined raw count tables, the private ledger and full header/payload identity. Separate bounded numerical checks verified the normalized smoothing arithmetic, exact initial/zero-outgoing backoff, unclipped word costs, immutable metadata and byte-verified cache/tamper behavior. Count agreement and numerical correctness establish neither language quality nor the success of the data hypothesis. The count-audit aggregate is `d69cf8a63cc5b8687acc1b5e467602272db0b9b61d41511280969a1ddef51adf`; the numeric aggregate is `173d9a10f3837ecfca6b006bc20e3533849d3396d7c9c5a35934935b6e4634b8`.

Data-total assertions were updated explicitly for the fixed additive recipe. The 16MiB word artifact limit, 16KiB header limit, integer state bound and per-query allocation/work limits were preserved. The independently bounded source build used a private compact decision ledger; no source subset, shorter matching, pair pruning, count truncation or cap increase was used. An initial source-assembly attempt stopped on an exact CRLF/LF placeholder mismatch before entry writing or any model parsing or quality call. Its partial evidence was preserved; a separately authorized corrective assembly succeeded. That setup correction was not a quality-query retry.

The 38-call, two-constructor pilot used the original 19 requests in each arm. Its zero arm matched all 19 original C5 full first-90 floathex pool/page controls exactly. Candidate written-text and exact-reading-pair coverage each reached 17/19 first-nine and 18/19 first-90. Relative to C8's saved candidate, each rank kind had four gains, one loss and 14 ties. Full pools and signed records remain private. The pilot report is `d6f49a96b4ab71755ce096e6b9f22a6e0019dba6e561526de5fe2aeecb14076c`; its independent audit is `cc6346ccc6a18445b96550b6784b9f395e9028d4e5cd74d91a31543bded1eeb5`.

| Original 402-form fresh group | Denominator | Written first 1 / 9 / 90 | Exact-reading pair first 9 / 90 |
| --- | ---: | --- | --- |
| Ordinary proper inputs | 89 | 55 / 86 / 89 | 71 / 73 |
| Proper 4–5 characters | 29 | 21 / 27 / 29 | 26 / 28 |
| Proper 6–8 characters | 30 | 20 / 30 / 30 | 24 / 24 |
| Proper 9–12 characters | 30 | 14 / 29 / 30 | 21 / 21 |
| Ordinary habitual inputs | 29 | 15 / 27 / 28 | 24 / 25 |

The terminal fresh report is `cc43a4020e1539f95e204776b9cc53b9b6b12f6620460777c2bdc40951812882`. It records all 402 original forms complete under one constructor with clean runtime and all 14 gates passed. Independent saved audit `57b322b7d721781a609b4ac6e2fb43030eebe805a74fd5aa7d75d0216f2d5923` confirms the results. Across all 402 forms against C8, written ranks have 57 gains, 17 losses and 328 ties; reading-pair ranks have 51 gains, 17 losses and 334 ties. All 804 signed records, including every one of the 17 written-rank losses and 17 reading-pair-rank losses, remain private. The full inventory is 93 cases, 89 ordinary proper inputs, 29 ordinary habitual inputs plus its additional control, and the original length bands; no successful subset replaces those denominators.

The original saved-preference comparison is now complete. The two original API-produced synthetic histories were imported byte for byte, preserving their readings, counts and adaptive weights. No new seeding, selection write or dictionary-membership query occurred. SHORT retains five units selected twice; HEAVY retains twelve units selected thirty times. Those historical selections are preparation provenance, not new C10 calls.

| Candidate profile | Proper written first 1 / 9 / 90, out of 89 | Proper reading-pair first 9 / 90 | Habitual written first 1 / 9 / 90, out of 29 | Habitual reading-pair first 9 / 90 |
| --- | --- | --- | --- | --- |
| Fresh | 55 / 86 / 89 | 71 / 73 | 15 / 27 / 28 | 24 / 25 |
| SHORT | 57 / 87 / 89 | 72 / 73 | 17 / 27 / 28 | 6 / 6 |
| HEAVY | 56 / 87 / 89 | 72 / 73 | 17 / 27 / 28 | 5 / 5 |

The reading-pair regression is material: habitual first-nine falls from 24/29 to 6/29 and 5/29 while written first-nine stays 27/29. The original synthetic histories retain their alternative readings, including `ng4`; the aggregate alone does not establish the cause of every reading change. Every signed text/pair change remains available privately. Reading diagnostics are not substituted for the original written-text gates, and the gates were not changed after seeing these results.

The campaign executed eleven new cells with **4,422 calls and eleven top-level constructors**, importing the already completed fresh candidate cell exactly once. Its complete twelve-cell join has 4,824 rows and twelve constructor records. All three candidate profiles pass the original absolute, length-band and two-percentage-point first-nine decline rules. The decline comparison is separately against matching fresh proper and habitual written first-nine; no new first-90 or reading-pair decline gate was introduced. Baseline, zero and character-only controls fail quality requirements, with their results retained; all twelve runtime cells are clean. Independent audit reconstructs all pools, ranks, source/history metadata, actual call sequences, original gates and all 6,432 signed learned-versus-fresh records.

The terminal profile report is `506535368aad130e1566532d6f75454c8ff2c7372d71fca513a54def30e3195d`; the independent aggregate is `61fc94491f147ddaddcf85098c9e008c137ac09f3b0c827099fc281da78efea7`. Across pilot, fresh and the new profile cells, C10 has executed **4,862 calls and fourteen top-level constructors**, without a quality-query retry. Broader phrase replay, controlled latency, whole-text learning/persistence, dense/paging/session correctness and native integration obligations remain pending. Profile passage permits separately authorized later checks only.

Exposed project cases are development evidence, not new blind, source-disjoint or representative accuracy evidence. The bounded hybrid score is not a normalized independent joint language model. Shared-process/source timing does not establish controlled latency or native typing. All original learning, external, performance, integration and native obligations remain unchanged. The v1.0.8 release and installation remain unchanged. UI layout development is separate. This experimental model has not been enabled, installed or released.

A pilot-auditor source search accidentally included live pilot output before its terminal report. The exposure is recorded; unchanged pool/rank audit routines were retained, and no blinding is claimed. The audit scope receipt is `f465cff7c2b11e33ce6e1e1dc932cb025aae4fae1318aab205893fa4e2f7d7e7`; the full fresh prerequisite receipt is `288969a55e9686d49ef4bce2044c7c758b2abf01743a590b19adc1ec2a11d4fe`.

See the [aggregate diagnostic](self-improvement-cycle10-word-diagnostic.json).
