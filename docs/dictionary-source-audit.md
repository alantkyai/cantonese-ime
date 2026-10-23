# Cantonese dictionary and pronunciation source audit

Evidence recorded on 22 October 2026, Hong Kong time. Windows/native testing is
deferred. This audit covers source permissions, explicit pronunciations and the
remaining text-only phrase gap; it does not claim that a dictionary's size proves
typing accuracy or that mechanically generated readings are independently reviewed.

## What the existing snapshot contains

The initial pinned Rime snapshot has **137,439 explicit text/reading pairs**:
34,362 character-table rows and 103,077 word-table rows. Its phrase table has
**330,701 text-only rows**, requiring an automatic encoder. The preset frequency
table supplies weights, not phrase pronunciation. The source revision is
[`259f0e48bba840c3a2e0d117539e96937f3d89bc`](https://github.com/rime/rime-cantonese/tree/259f0e48bba840c3a2e0d117539e96937f3d89bc).
Exact source hashes and attribution are in [the main data lock](../data/sources.lock.json).
These are the baseline counts before supplementary import and autoencoding;
the generated database manifest records the actual current build.

Downloading the newer-looking CSV filenames from the same upstream does not
automatically add a separate phrase corpus. Rime's pinned
[`scripts/fetch_upstream.py`](https://github.com/rime/rime-cantonese/blob/259f0e48bba840c3a2e0d117539e96937f3d89bc/scripts/fetch_upstream.py)
already merges every upstream CSV containing both `char` and `jyutping` into
`jyut6ping3.words.dict.yaml`, including fixed expressions and phrase fragments.
That transformation also expands supported bracket/variant notation. Importing
those CSVs again without a delta check would mostly duplicate existing readings.

## Source inventory

| Source | Revision and exact structure | Permission and intended use |
| --- | --- | --- |
| [Rime Cantonese](https://github.com/rime/rime-cantonese/tree/259f0e48bba840c3a2e0d117539e96937f3d89bc) | Pinned revision above. Default Rime table columns: text, optional toned reading, optional numeric/percentage weight. `essay-cantonese.txt`: text and frequency. | [CC BY 4.0 main data declaration](https://github.com/rime/rime-cantonese/blob/259f0e48bba840c3a2e0d117539e96937f3d89bc/README-en.md); full local license retained. The separate ODbL map dataset is excluded. |
| [CanCLID upstream](https://github.com/CanCLID/rime-cantonese-upstream/tree/4cb67a486312e5f0f13cc842433617104d75de87) | Current inspected commit `4cb67a486312e5f0f13cc842433617104d75de87`, 10 August 2026. Structured CSV readings and editorial pronunciation classifications. | [CC BY 4.0 LICENSE](https://github.com/CanCLID/rime-cantonese-upstream/blob/4cb67a486312e5f0f13cc842433617104d75de87/LICENSE). Principal source of already imported explicit Rime tables; use for editorial provenance and future diffs. |
| [LSHK character pronunciation list](https://github.com/lshk-org/jyutping-table/tree/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3) | Commit `dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3`, 11 January 2024. `list.tsv` has 38,306 reading rows for 29,144 distinct character texts. | [CC BY 4.0](https://github.com/lshk-org/jyutping-table/blob/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3/README.md). Authoritative character-reading comparison source, already a principal CanCLID input. Differences require editorial review rather than unconditional overrides. |
| [words.hk official wordlist](https://words.hk/faiman/analysis/wordslist/) | Snapshotted JSON object mapping text to a list of explicit readings. Displayed update: 8 October 2026 14:24:41, timezone not stated. Retrieved 22 October 2026 14:44:39 +08:00. | The specific wordlist/pronunciation page declares **public domain** and requests credit. This does not apply that declaration to definitions, examples or media. Snapshot, parser and review accounting implemented below. |
| [TypeDuck schema](https://github.com/TypeDuck-HK/schema/tree/7f9d90d4185eca293576de5b5dddaaf1d265f3c9) | Inspected commit `7f9d90d4185eca293576de5b5dddaaf1d265f3c9`, 4 September 2026. Monolithic `jyut6ping3.dict.yaml`; separate frequency/rich annotation files excluded. | [README scope](https://github.com/TypeDuck-HK/schema/blob/7f9d90d4185eca293576de5b5dddaaf1d265f3c9/README.md): principal dictionary/schema CC BY 4.0, reverse lookup files separately licensed. All 155,509 canonical pairs are selected; 34,364 add pairs over earlier sources, with unknown frequency zero. The [preserved pre-import audit](typeduck-data-audit.md) records 314 ambiguous-text overlaps. Exported-row authorship and historical row lineage remain separate from the declared license. |
| [Unicode Unihan](https://www.unicode.org/reports/tr38/#kCantonese) | `U+codepoint<TAB>property<TAB>value`; `kCantonese` values are space-separated Jyutping codes. Character property, not annotated phrase corpus. Versioned source/member hashes retained in the [selected lock](../data/supplements/unihan.sources.lock.json). | [Unicode License V3](https://www.unicode.org/license.txt) permits redistribution/modification with its notice. Selected for direct character lookup only; 2,892 pairs add over earlier sources. Provisional readings are explicitly excluded from automatic phrase translation. |
| [CC-Canto and Cantonese readings for CC-CEDICT](https://cantonese.org/download.html) | CC-CEDICT-style entries with Cantonese readings in braces after Mandarin readings. Separate explicit word data may help later. | Publisher declares CC BY-SA 3.0. Keep the source's attribution/share-alike requirements and dataset identity separate; do not relabel this data CC BY 4.0. Not downloaded or imported here. |

Unihan's own specification labels `kCantonese` provisional and primarily targets
stable collation/transliteration. It can identify character gaps but cannot prove
the right reading of a polyphonic character inside a phrase. Adding its character
coverage therefore does not settle the 330,701 phrase pronunciations.

No permission to redistribute Google's complete engine/dictionary or
cantoneseinput.com's data has been established. They remain behavior references.
The OpenStreetMap-derived Rime map names remain excluded under their separate ODbL
terms. No scraper is used to gather dictionary definitions.

## CanCLID CSV schemas and direct paths

All links in this table use the same pinned CanCLID commit. Source sizes are from
GitHub's repository API; row counts below were measured from fetched text.

| File | Columns | Observed scope |
| --- | --- | --- |
| [`char.csv`](https://raw.githubusercontent.com/CanCLID/rime-cantonese-upstream/4cb67a486312e5f0f13cc842433617104d75de87/char.csv) | `char,jyutping,pron_rank,tone_var,literary_vernacular,comment` | 34,362 data rows; pronunciation rank supplies the percentage categories used by Rime. |
| [`word.csv`](https://raw.githubusercontent.com/CanCLID/rime-cantonese-upstream/4cb67a486312e5f0f13cc842433617104d75de87/word.csv) | Contains `char,jyutping`; default common-word table | 2,276,881 bytes; already consumed by Rime's pinned importer. Direct connector read exceeded its supported payload; no new standalone snapshot imported. |
| [`fixed_expressions.csv`](https://raw.githubusercontent.com/CanCLID/rime-cantonese-upstream/4cb67a486312e5f0f13cc842433617104d75de87/fixed_expressions.csv) | `char,jyutping` | 937 data rows, including punctuation-bearing expressions. |
| [`phrase_fragment.csv`](https://raw.githubusercontent.com/CanCLID/rime-cantonese-upstream/4cb67a486312e5f0f13cc842433617104d75de87/phrase_fragment.csv) | `char,jyutping` | 7,275 data rows; these explicit phrase fragments are already part of the 103,077 compiled word rows. |
| [`trending.csv`](https://raw.githubusercontent.com/CanCLID/rime-cantonese-upstream/4cb67a486312e5f0f13cc842433617104d75de87/trending.csv) | `char,jyutping` | Header only at inspected revision. |
| [`proper_nouns.csv`](https://raw.githubusercontent.com/CanCLID/rime-cantonese-upstream/4cb67a486312e5f0f13cc842433617104d75de87/proper_nouns.csv) | `category,char,jyutping` | 67 data rows. |
| [`onomatopoeia.csv`](https://raw.githubusercontent.com/CanCLID/rime-cantonese-upstream/4cb67a486312e5f0f13cc842433617104d75de87/onomatopoeia.csv) | `type,jyutping,char` | 52 data rows; column names matter because text/reading order differs. |

The LSHK [`list.tsv`](https://raw.githubusercontent.com/lshk-org/jyutping-table/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3/list.tsv)
columns are `CH,UCODE,JP,INIT,FINL,TONE,DESC,DESC_JP`. `CH` is the character
text, and `JP` is its explicit toned pronunciation. Other fields provide source
descriptions and phonetic parts; none is a popularity frequency.

## Implemented words.hk supplement

The vendor snapshot contains only the official
[`wordslist.json`](https://words.hk/faiman/analysis/wordslist.json) and the full
wordlist licensing-declaration HTML. Exact URLs, source update text, explicit
timezone uncertainty, retrieval timestamp, byte lengths and SHA-256 hashes are
recorded in [wordshk.sources.lock.json](../data/supplements/wordshk.sources.lock.json).

The retained declaration is: “Data License: public domain. Credits to words.hk
appreciated.” Credit to words.hk contributors remains in provenance.

[`wordshk.py`](../cantonese_ime/wordshk.py) imports explicit lowercase toned
readings with weight zero because this endpoint supplies no frequencies.
The full builder preserves zero for every newly added words.hk/LSHK pair as an
unknown-frequency sentinel, rather than a claim that its occurrence count is
zero. A whole-text essay count must not be assigned independently to each new
pronunciation: that would invent a reading-frequency distribution and alter
Rime's 5% translation threshold. Original Rime weights remain unchanged.
Exact-text frequencies can separately prioritize human review.
All source readings remain accounted for:

| Snapshot category | Reading rows |
| --- | ---: |
| Raw source keys | 62,635 text keys |
| Raw text/reading rows | 66,753 |
| Accepted explicit rows | 66,370 |
| Quarantined non-Jyutping notation | 282 |
| Quarantined ellipsis/template text | 101 |
| Total quarantined | 383 |
| Documented variant-marker normalization, included in accepted rows | 2,225 |

Exactly one trailing `*` is the source's documented variant annotation. It is
removed from output text with a `normalized_variant` provenance row retaining
`raw_text`, `normalized_text`, raw reading and `source_flag=variant`. Middle or
multiple asterisks are quarantined. English/multilingual notation such as `!zhi1`
is preserved in quarantine rather than rewritten into guessed Jyutping.
Templates containing ellipses remain review items.

Against the initial 137,439-entry Rime database, this snapshot adds **12,347
text/reading pairs**. It also supplies explicit readings for **314 distinct
texts** appearing in the text-only Rime phrase file. These are measured deltas,
not a claim that every new term is frequent or that every unresolved phrase is
now covered. Whole-word authored readings take precedence over autoencoding.

## Rime-compatible automatic phrase encoding

The compatibility implementation is [autoencode.py](../cantonese_ime/autoencode.py).
It follows librime commit
[`1b3417d2b6a11b5e50e0e1fa9dc396056aa11dce`](https://github.com/rime/librime/tree/1b3417d2b6a11b5e50e0e1fa9dc396056aa11dce),
specifically [ScriptEncoder](https://github.com/rime/librime/blob/1b3417d2b6a11b5e50e0e1fa9dc396056aa11dce/src/rime/algo/encoder.cc)
and [EntryCollector](https://github.com/rime/librime/blob/1b3417d2b6a11b5e50e0e1fa9dc396056aa11dce/src/rime/dict/entry_collector.cc).
The adapted algorithm's BSD 3-Clause notice is retained in
[data/licenses](../data/licenses/librime-BSD-3-Clause.txt), separately from the
dictionary's CC BY 4.0 license.

Its relevant rules are:

1. Only explicit entries with exactly one code syllable populate the translation
   map. A multi-character spelling with one syllable can be a token; ordinary
   multi-syllable words do not become translation tokens.
2. Duplicate text/code definitions keep the first weight. For each text, retain
   codes with weight at least 5% of the sum of its code weights. If the sum is
   zero, all zero-weight codes meet that threshold, which can increase ambiguity.
3. Traverse longest matching text substrings first, then lexical code order.
   Follow the successful DFS emission order, up to 32 complete paths and 32
   Unicode codepoints. This is not a one-best-pronunciation guess.
4. Record all reached codes and a status: `encoded_unique`,
   `encoded_ambiguous`, `truncated`, `unencodable`, or `too_long`. Exactly reaching
   the 32-path bound remains conservatively `truncated`. A separate finite work
   guard also produces `truncated`, never false certainty.
5. Pruning unreachable suffixes and skipping invalid UTF-8 substring probes
   preserve the order of successful paths for valid Unicode source text. These
   implementation adaptations are disclosed in algorithm metadata.

The independent tests cover explicit-only tokens, the exact 5%-of-total rule,
zero-weight ambiguity, lexical/longest-first traversal, Unicode limits, complete
path truncation and finite-work failure. A successful unique mechanical encoding
means only that this algorithm found one complete code; it does not establish
linguistic correctness, resolve changed tones or prove names' preferred readings.
Native compiled-librime comparison remains a separate validation item.

## Remaining readiness work

The build must account for every original phrase as already explicitly covered,
uniquely generated, ambiguous, truncated, unencodable or too long. Keep original
source text and every reached reading for review. Generated and authored readings
must retain different origins. Unresolved counts cannot be renamed a quality pass.

Prioritize authored whole-word supplements and human review for high-frequency
ambiguous phrases, polyphonic characters, place/person names and changed-tone
words. Track the remaining uncovered texts and pronunciation conflicts. Character
sources can improve coverage, but blindly adding every reading often expands
ambiguity. A compiled-librime parity check and a held-out phrase-quality review
are distinct gates from full source-row accounting.
# Additional selected CC-Canto lexical sources

The 23 October 2026 vocabulary expansion selects the official CC-Canto and
CC-CEDICT Cantonese reading exports under their retained CC BY-SA 3.0 declaration.
Their admitted union has 213,321 explicit text/readings before overlap removal,
with 891 exception records; no Mandarin fallback or dictionary-definition data
is used for lookup. The combined transformed data adaptation is CC BY-SA 4.0,
with original notices preserved. See the [complete source audit](cccanto-data-audit.md),
[immutable source lock](../data/supplements/cccanto.sources.lock.json) and
[data-license notice](../data/DATA_LICENSE.md). Counts in earlier sections refer
to the earlier pinned source set and must not be used as the new build's totals.
