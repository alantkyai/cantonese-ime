# HKCanCor baseline error analysis

The frozen baseline has **222/1,000 exact-text misses at rank 90**. Of those, 194 have a theoretical segmentation through existing dictionary text/reading pairs; the other 28 requests represent 14 cases without such a source-aligned path. This points to composition, ranking and transcription policy as substantial remaining work alongside pronunciation coverage. A stored-pair graph path does **not** prove that the bounded decoder retains it or ranks it within 90.

This is read-only analysis of [the frozen external baseline](hkcancor-evaluation.json) and [500 frozen cases](../eval/hkcancor_cases.json). The [machine-readable analysis](hkcancor-error-analysis.json) retains every case's source tokens, dictionary coverage, segmentation witness and original result labels. No corpus readings were imported, rules fitted, labels corrected or baseline scores changed.

## Scope and unchanged scores

The source is K. K. Luke and May L. Y. Wong's *Hong Kong Cantonese Corpus* (2015), original transcriptions hosted by Francis Bond, pinned at [`39aeadf920e0b5ca93d0ad7792c59e740e7bdd65`](https://github.com/fcbond/hkcancor/tree/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65). It is used under [CC BY 4.0](../eval/vendor/hkcancor/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65/data/LICENSE). Changes here are selection, input derivation and analytical annotations; original text/readings remain identifiable. See the [source lock](../eval/hkcancor.sources.lock.json) for attribution, paper citation and individual file hashes.

Selection used the lowest hashes of source text/reading pairs, independently of dictionary membership or ranking: 250 distinct word types and 250 distinct maximal speech spans, each queried fully toned and tone-free. The selected groups share no exact text/reading pairs. Unknown upstream corpus/dictionary overlap remains, so these are external annotation results, **not clean held-out accuracy, human-approved linguistic labels or natural typing accuracy**.

| Exact match | Rank 1 | Rank 9 | Rank 90 | Denominator |
|---|---:|---:|---:|---:|
| Source text | 487 | 722 | 778 | 1,000 requests |
| Source text and reading | 475 | 691 | 736 | 1,000 requests |

There were no errors or empty candidate lists. These first-90 scores remain unchanged by the separate page probes below.

Full-source accounting is 160,836 tokens: 128,134 eligible, 29,904 punctuation, 2,768 non-ideographic and 30 unsupported special annotations. Of 30,427 maximal eligible runs, 23,604 qualify as speech-span occurrences, 714 exceed the 64-character input limit and 6,109 contain only one source token. There are 6,564 eligible distinct word pairs and 19,578 span pairs before sampling. Long spans were excluded whole, never clipped. One eligible source word has unequal character/syllable counts; it is not among the selected 500, all of which align within every source word token.

## Coverage separates the problems

For each selected case, a graph tests whether exact contiguous text substrings and their corresponding source syllables exist as dictionary pairs. It permits segmentation across source token boundaries and records a shortest witness. It assumes the source's one-character/one-syllable alignment; it does not establish linguistic correctness or model decoder search.

| Dictionary relationship | Cases | Requests | Text misses at 90 | Pair misses at 90 |
|---|---:|---:|---:|---:|
| Exact whole source pair stored | 218 | 436 | 0 | 12 |
| Whole pair absent; stored-pair graph path exists | 268 | 536 | 194 | 224 |
| No exact source-aligned graph path | 14 | 28 | 28 | 28 |
| Total | 500 | 1,000 | 222 | 264 |

The 218 stored-pair cases comprise 208 word types and 10 spans. The 268 composable cases comprise 39 word types and 229 spans; the remaining 14 comprise 3 word types and 11 spans. All 218 stored whole pairs return their target **text** within 90 for both inputs. This sample therefore exposes no stored-whole-pair text lookup loss. Its 12 tone-free pair misses return that text with another reading.

Across selected-case occurrences, 1,526/1,596 source word-token pairs are stored; the 70 missing occurrences represent 61 distinct pairs. All word-token pairs are present in 431/500 cases. Character coverage is 2,237/2,256 aligned occurrences; 19 missing occurrences represent seven pairs, and 481/500 cases have all character pairs. These are sample occurrence counts, not full-corpus frequencies. Missing a character pair alone does not make a case infeasible: a longer stored word can supply it.

## Actionable categories

**Source-aligned pronunciation gaps:** the seven missing character pairs are 哩 `ni1` (13 selected occurrences), 窿 `lung2`, 肆 `si5`, 沸 `fat6`, 蚚 `sik1`, 跤 `gaau3` and 三 `saa1` (one each). Examples without a graph path include 蚚蜴 `sik1 jik6`, 脫跤 `tyut3 gaau3` and 佢就鼎沸 `keoi5 zau6 ding2 fat6`. These require source and linguistic review before any dictionary change; contextual readings, transcription conventions and annotation errors are possible. The evaluation source is not an automatic enrichment feed.

**Composition and ranking with existing constituents:** 194 text misses have a graph path. For example, 慧琪 `wai6 kei4` has both character readings but returns 位其 first; 少娟 `siu3 gyun1` returns 笑捐. In 俾返我個 `bei2 faan1 ngo5 go3`, stored pairs 俾返 + 我個 form a witness, yet 畀番我個 ranks first and the source text is absent from 90. 即刻誇咗 similarly has 即刻 + 誇 + 咗 but returns 即喀喎咗 first. These demonstrate a gap between available constituents and published candidates, without isolating beam pruning, scoring, tokenization or another mechanism as the cause.

**Source orthography and reading ambiguity:** outputs such as 好慘架喎 for source 好慘𡃉喎, or 但係嚟緊喎 for source 但係來𡁵喎, have the same annotated reading in these cases. They remain exact-text misses. No spelling alternative is accepted automatically. Separately, 42 requests return the target text within 90 with a different reading, explaining the gap between 222 text misses and 264 pair misses. These need a reviewed task policy before reporting any alternative-aware metric.

## Lookup and pool evidence

Most text misses do not have 90 published candidates: 142/222 have 32, and only two have 90. This is not evidence that raising the display limit alone will solve them. Additional public-page probes inspected 子由 `zijau` through 138 candidates and 南哥 `naamgo` through 146; both reached explicit completion-capacity errors without the target. Neither source whole pair is stored. 午夜 `mje` exhausted 30 candidates without its text; 午夜 is stored with other readings, while its source pair `m5 je6` is absent and its constituent pairs are present.

These probes preserve first-90 scores. They establish bounded search outcomes, not that either missing composed target sits beyond a SQL row cap. Further work should distinguish composition retention from ranking on separately frozen diagnostic cases, and review orthographic/pronunciation policy before any fitting. No change was implemented in this analysis.

## Frozen inputs

All 63 retained source files were rechecked against the source lock. The companion JSON records these hashes and runtime engine, mappings and evaluator hashes.

| Input | SHA-256 |
|---|---|
| Dictionary | `4353328cb17f8c8f8cc5d78730e34c3aa26c6c8ea7d1a4f4a8f91fee5d900a6e` |
| Cases | `410f4b612ca14e5e60da0b147f7bf9fb4b4a1e25c125053e00596981b72ef085` |
| Baseline report | `d6f44b92d3287da9cafa80693d32de689a972ddeee65920406c9666251ce67b8` |
| Source lock | `e020995669488936880d4ef9dd55290cb86a23d22476c576d705e87145fbb060` |

