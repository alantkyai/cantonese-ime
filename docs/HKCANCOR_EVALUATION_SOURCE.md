# HKCanCor external evaluation source

HKCanCor supplies independently provided conversational text, segmentation and
pronunciation annotations. It can support a frozen composition/phonetic
baseline without deriving the expected labels from this engine. It is **not
established as clean held-out data**: shared upstream dictionary or frequency
sources have not been ruled out, and its annotations are not natural IME
keystrokes or a new human acceptance decision for this project.

No HKCanCor text, readings or frequencies have been imported into the
dictionary or used to fit the engine for this baseline. Candidate results do
not determine source eligibility or case selection. Scoring belongs to the
separate evaluator/report; this document records source evidence and limits.

## Pinned original release and retained permission

The original [fcbond/hkcancor repository](https://github.com/fcbond/hkcancor)
was pinned at commit
`39aeadf920e0b5ca93d0ad7792c59e740e7bdd65`, dated 3 November 2025,
with Git tree `5adc953c291d015077d38f707c9f1e196652ae90`. The complete
recursive tree response was not truncated. The selected release is retained
under
`eval/vendor/hkcancor/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65`.

The [source lock](../eval/hkcancor.sources.lock.json) has SHA-256
`e020995669488936880d4ef9dd55290cb86a23d22476c576d705e87145fbb060`.
It records all 63 selected files, totaling 3,995,275 bytes: all 58 original
`data/utf8` transcripts, both READMEs, the root license pointer, the full
`data/LICENSE` and the one-page format specification. Every retained file
matched its pinned Git blob SHA-1 and byte length, and also has a SHA-256 in
the lock. Original bytes are unchanged. No packages were installed.

Audio, Big5/HKSCS duplicates, transcript ZIP duplicates, sample duplicates,
the HTML landing page and the article PDF are outside the retained evaluation
source selection. The authors' article was inspected separately as methods
evidence; it was not added as an evaluation case or dictionary source.

The pinned [repository README](https://github.com/fcbond/hkcancor/blob/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65/README.md)
and [data README](https://github.com/fcbond/hkcancor/blob/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65/data/README)
declare CC BY 4.0 for the transcriptions. The 12-byte root `LICENSE` is only a
pointer; the complete 15,037-byte license is retained at
[data/LICENSE](../eval/vendor/hkcancor/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65/data/LICENSE),
SHA-256 `ca2b19c8e224511f96187a44139da2d33a8cf9ff9d4695b584de7cc8c964638e`.
Keep attribution, the license and an account of extraction/normalization
changes with derived cases. Cite:

K. K. Luke and May L. Y. Wong (2015), *The Hong Kong Cantonese Corpus: Design
and Uses*, Journal of Chinese Linguistics Monograph Series 25, 312–333.

## Annotation provenance and its limits

The original project describes conversational and radio recordings, word
segmentation, POS annotation and LSHK pronunciation labels. Its broad README
description of about 230,000 words and 94 recordings is not the size of the
particular downloadable tree: the verified UTF-8 release here has 58 files,
10,801 utterance blocks and 160,836 nonempty tagged lines. Report observed
release counts rather than extrapolating the broader description.

The authors' [methods paper](https://github.com/fcbond/hkcancor/blob/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65/data/LukeWong_Hong-Kong-Cantonese-Corpus.pdf)
describes transcription work, an initially manual segmentation/POS sample and
subsequent semi-automatic segmentation/tagging (preprint pp. 8–10). It credits
transcriber training and final transcription checking (p. 15). This supports
using externally supplied annotations, not claiming every label was manually
verified for this IME. Per-token reviewer identities, confidence and
inter-annotator agreement are not supplied in these files.

[PyCantonese's corpus README](https://github.com/jacksonllee/pycantonese/blob/main/src/pycantonese/data/hkcancor/README.md)
links this original source and describes substantial conversion to CHAT,
including punctuation and participant metadata changes. It also states that
HKCanCor trains PyCantonese segmentation/POS models. We use the pinned
original UTF-8 annotations directly; PyCantonese and its trained models are
not installed or used to generate labels.

## Original file schema and source-only accounting

The retained [format specification](../eval/vendor/hkcancor/39aeadf920e0b5ca93d0ad7792c59e740e7bdd65/data/format_v.pdf)
has SHA-256 `8da07c93386aed4bc13c81624965765f1ea72b739bbbb54f197337375be86b42`.
Its one page was text-extracted and visually inspected. A file consists of an
`<info>` block followed by repeated `<sent>` fragments. These are multiple
top-level fragments, not a single well-formed XML document with one outer
root. Each `<sent>` is a speaker utterance and may contain more than one
punctuated sentence. It contains `<sent_head>`, `<sent_tag>` and
`<sent_tran>`; the latter is reserved for translations, not a pronunciation
label source. The information block identifies recording and speaker metadata.

Nonempty lines inside `<sent_tag>` normally have the form
`text/POS/compact-reading/`. For example, `旅行/vn/leoi5hang4/` supplies one
segmented word with two syllables. Tone digits delimit compact syllables.
POS `w` marks punctuation; forms such as `VQ1`, `VQ2`, `VQ6` and `VQ9` are
punctuation codes, not Jyutping tone alternatives.

An independent source-only parse, without importing or calling the engine,
found the same eligible token counts as the evaluator's collection step:

| Observed category | Count |
| --- | ---: |
| UTF-8 transcript files / information blocks | 58 / 58 |
| Utterances, each with exactly one `<sent_tag>` | 10,801 |
| Nonempty tagged lines | 160,836 |
| Eligible ideographic targets with complete lowercase `[a-z]+[1-6]` syllables and non-`w` POS | 128,134 |
| POS `w` barriers | 29,904 |
| Other non-ideographic targets | 2,768 |
| Unsupported `/@` source annotations | 30 |
| Distinct eligible `(text, reading)` word types | 6,564 |

The 2,768 non-ideographic rows include 2,326 with noncanonical readings
(typically English or `0` notation) and 442 with canonical readings but
non-ideographic targets, including private-use characters. No nonpunctuation
reading in this scan used digits 7–9. The 1,093 apparent `9` occurrences were
`VQ9` punctuation codes. These are exclusions under the declared baseline
policy, not evidence that English/code switching or private-use text is
incorrect in the corpus.

Preserve these particular annotation limits:

- All 30 unsupported lines end in `/@`: 26 `○/#/#/@`, one
  `○/a/jaap3/@`, one `○/q/lam6/@` and two `？幾/m/gei2/@`.
  The original short specification and methods text inspected do not define
  the suffix's semantics. Retain it as unsupported source annotation and a
  span barrier; do not call it source corruption or infer a repair.
- `我哋/w/ngo5dei6/` occurs in `data/utf8/FC-046_v2`, zero-based utterance
  51. The stated POS policy excludes it even though text/reading look
  canonical. Preserve the raw tag instead of silently changing `w`.
- `不明飛行物/n/bat1ming4fei1hang4mat6tai2/` occurs in
  `data/utf8/FC-042_v`, zero-based utterance 1, nonempty-token index 42.
  Its five characters have six annotated syllables. The baseline eligibility
  rule retains the word annotation; it does not add `體`, remove `tai2` or
  assert a one-character/one-syllable alignment. The character-overlap
  diagnostic below excludes this one word from positional alignment only.

## Frozen composition/phonetic baseline

The source-only selection policy was fixed before candidate scoring: 250
hash-selected distinct word types and 250 hash-selected distinct maximal
eligible speech spans. Eligibility uses the original ideographic text,
lowercase compact tones 1–6 and the source POS. Unsupported annotations,
punctuation and unsupported targets split runs; tokens are never joined
across these barriers or across utterances. Over-64-character fully toned
inputs are rejected as whole spans, not clipped. Selection does not consult
dictionary membership, candidate rank or returned output.

The collector found 19,578 eligible distinct speech-span types after
accounting for 714 over-cap spans and 6,109 single-token spans. The frozen
[500-case corpus](../eval/hkcancor_cases.json) has SHA-256
`410f4b612ca14e5e60da0b147f7bf9fb4b4a1e25c125053e00596981b72ef085`.
It preserves source file, utterance, speaker, token indices, raw tokens,
reading, occurrence count and selection hash; overlap between strata is
reported rather than silently hidden.

The [pre-score freeze](../eval/hkcancor.freeze.json), captured at
10:48:23 UTC on 22 October 2026, has SHA-256
`dc444760b7f236af5f00064ac8f9c0301ce6b185b81c2ff59fc023f68a1ca07b`.
It binds the corpus, source lock, evaluator, engine/mappings and dictionary
hashes. `/@` rows are classified as unsupported source annotation without
changing eligibility. This records a reproducible external baseline;
it does not create a reviewed 500-case natural-typing trial or approve the
existing linguistic quality gates.

## Lexical, component and frequency overlap

The independent diagnostic used SQLite read-only mode and no engine calls.
It compared corpus annotations with the current dictionary SHA-256
`4353328cb17f8c8f8cc5d78730e34c3aa26c6c8ea7d1a4f4a8f91fee5d900a6e`,
the original explicit Rime pairs at pinned commit
`259f0e48bba840c3a2e0d117539e96937f3d89bc`, and that source's
`essay-cantonese.txt` text keys. Input hashes and unchanged database bytes
were checked before/after. Compact reading comparisons remove separator
whitespace only; targets, syllables and tones are not rewritten.

| Corpus unit: distinct text/reading types | Types | Exact pair in current dictionary | Exact pair in original explicit Rime | Text key in Rime frequency file |
| --- | ---: | ---: | ---: | ---: |
| Eligible word types | 6,564 | 5,551 | 5,002 | 5,643 |
| Positionally aligned character/readings | 2,835 | 2,738 | 2,542 | 2,784 |
| Adjacent two-word combinations within eligible runs | 40,711 | 3,828 | 974 | 4,457 |
| Adjacent three-word combinations within eligible runs | 59,915 | 904 | 294 | 415 |

These counts go beyond exact whole selected-case membership. Of 128,134
eligible word occurrences, 124,739 have an exact current-dictionary pair and
118,700 an exact original-Rime pair. Positive Rime frequency entries cover
5,641 word-pair types and 117,788 occurrences. The frequency comparison is
by text key, not a claim that the frequency measures this particular corpus
pronunciation. Two-/three-word diagnostics retain original within-run
adjacency and do not bridge excluded annotations. Counts for frequency keys
are over text/reading types, so alternative readings can share a text key.

Exact overlap does not prove that HKCanCor was an upstream input: common
characters and vocabulary are expected to overlap. Conversely, absence of a
whole phrase from the dictionary cannot establish independence when its
components or frequency signal are shared.

The pinned Rime [generation script](https://github.com/rime/rime-cantonese/blob/259f0e48bba840c3a2e0d117539e96937f3d89bc/scripts/fetch_upstream.py)
builds character/word tables from CanCLID CSV data. The pinned Rime commit
identifies upstream revision
`4cb67a486312e5f0f13cc842433617104d75de87`. The current upstream
[source inventory](https://github.com/CanCLID/rime-cantonese-upstream#%E6%95%B8%E6%93%9A%E6%BA%90)
and Rime's [source wiki](https://github.com/rime/rime-cantonese/wiki/%E8%B3%87%E6%96%99%E4%BE%86%E6%BA%90)
name dictionaries and other linguistic resources but do not establish a
complete row-level or frequency-training lineage. The retained frequency
file has no per-row corpus-origin field. No evidence found in this scoped
inspection proves HKCanCor supplied the selected Rime frequencies; neither
does it rule that out. TypeDuck's historical row-level lineage also remains
incomplete in its separate source audit.

Use the label **external annotated baseline with measured lexical/frequency
overlap and unknown upstream training overlap**. Do not relabel it as strict
held-out accuracy, independently collected informal spellings, contemporary
daily typing or speaker approval of this engine. Preserve the frozen failures
and original labels; tuning on their results makes subsequent claims
development results and requires a separately frozen independent evaluation
for new generalization claims.
