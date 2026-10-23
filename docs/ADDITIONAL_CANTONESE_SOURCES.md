# Additional Cantonese source candidates

Research date: 23 October 2026, Hong Kong time. **Candidate analysis only:** nothing below has been imported, accepted as linguistically correct, or added to the staged native package. The comparison database remains SHA-256 `3fccc5bcf45cbb676b8a1a51e2030d418803af64b3cd5c0ae7d67cf90a4711bb` (736,570 pairs; 621,245 distinct texts).

## 1. Cantonese Wordnet: recommended next focused source audit

The authors' [repository README](https://github.com/lmorgadodacosta/CantoneseWN/blob/6434cbc1d692d3061266352aa223a8df4a9c883e/README.md) explicitly licenses the dataset under **CC BY 4.0**. The downloadable XML independently declares that license on its `Lexicon` element. This permits an attributed adaptation within our existing CC BY-SA 4.0 combined dictionary; preserve the source's own license and citation. It does not require changing the application-code license.

The [2019 construction paper](https://aclanthology.org/2019.gwc-1.26/) explains that candidate concepts/lemmas were developed through a Wordnet expansion process, then checked by a Cantonese-speaking linguist; the Jyutping readings were entered manually. This is a different collection process from merely rerunning our character encoder. The current README describes hand checking, pronunciation variants, changed tones and functional words. Those are source statements, not our independent approval of every row or proof that the source is independent of every existing lexicon.

Pinned, actually fetched files:

| Item | Value |
| --- | --- |
| [Commit](https://github.com/lmorgadodacosta/CantoneseWN/commit/6434cbc1d692d3061266352aa223a8df4a9c883e) | `6434cbc1d692d3061266352aa223a8df4a9c883e` (4 December 2023) |
| [Raw XML download](https://raw.githubusercontent.com/lmorgadodacosta/CantoneseWN/6434cbc1d692d3061266352aa223a8df4a9c883e/cantown.xml) | `cantown.xml`, 4,448,577 bytes |
| XML SHA-256 | `660debb24d51a439de758cfc80dd4d2bcfc9f2b5cad6d83f68c1206be48865d9` |
| [Raw declaration](https://raw.githubusercontent.com/lmorgadodacosta/CantoneseWN/6434cbc1d692d3061266352aa223a8df4a9c883e/README.md) | `README.md`, 3,711 bytes |
| README SHA-256 | `1d301f8931bf687e81f5b145a78170059d07a9849f7d20048a71587c68cca093` |

Use **XML**, not `cantown.tsv`: the authors explicitly say the legacy TSV omits Jyutping forms. Select exactly the `cantown-yue` lexicon with language `yue`; each selected `LexicalEntry` supplies its own `Lemma/@writtenForm` and `Form/@writtenForm` values. Empty forms occur frequently. Pair within the same lexical entry; do not join by synset or infer pronunciation from another lemma. The whole fetched snapshot contains 11,672 lexical entries and 10,412 distinct lemma strings. The target Yue lexicon contains **11,667 entries and 10,407 distinct lemmas**. A separate English lexicon contributes five entries with five empty forms and is excluded. The README's separate headline count is not substituted for observed file counts.

### Preliminary overlap, with a deliberately narrow counting boundary

The following was computed in memory from the pinned XML against a read-only immutable connection to the comparison DB. No raw candidate files were retained or product files written. A form counted toward the preliminary pair set only when its reading already matched lowercase, space-separated `[a-z]+[1-6]` syllables, every base was in the current stored inventory, the lemma had one Unicode codepoint per syllable, and every lemma codepoint was Han in the checked CJK ranges. No punctuation stripping, tone repair, `y`→`j` conversion, or expansion of variant notation was performed.

| Observation | Count |
| --- | ---: |
| Selected Yue `Form` nodes | 23,733 |
| Empty Yue forms | 11,660 |
| Nonempty forms | 12,073 |
| Excluded: reading syntax | 117 |
| Excluded next: base absent from current inventory | 38 |
| Excluded next: text/syllable count mismatch | 86 |
| Excluded next: non-Han text | 1 |
| Remaining form occurrences | 11,831 |
| Unique preliminary text/reading pairs | 10,757 |
| Exact pairs already present | 8,210 |
| Potential new pairs | **2,547** |
| Potential entirely new texts | **1,970** |

The four exclusion counts are sequential and mutually exclusive at the form-occurrence level; together they account for 242 nonempty forms. Repeated pairs across lexical entries/parts of speech are deduplicated only for the preliminary pair counts. No frequency is supplied by this analysis, and these counts are **not importer acceptance counts or quality scores**.

Examples absent as whole texts from the comparison DB include 㩒住 `gam6 zyu6`, 一啖 `jat1 daam6`, 一陣仔 `jat1 zan6 zai2`, 上油 `soeng5 jau4`, and 一劑藥 `jat1 zai1 joek6`. These are source-provided whole readings, not generated combinations. A substantial share of other additions are adjective phrases ending 嘅 or adverbial phrases ending 噉; that improves explicit phrase coverage but is not evidence of thousands of previously missing basic lexical roots. New readings for already stored words also include pronunciation variants, so they must not automatically replace existing readings or inherit whole-text frequencies.

Before an import, retain a source lock, raw XML, README and full CC BY 4.0 text; record lexical-entry IDs and every raw form. Quarantine or explicitly review marked forms such as `gam2 joeng6*2`, missing tones such as `si`, glued syllables such as `heng6 heng1gam2`, unaligned forms and unknown bases. The 38 unknown-base occurrences include both unusual-looking spellings and likely transcription issues; the preliminary audit did not repair or decide them. Passing these mechanical checks alone does not establish linguistic correctness. Start with zero unknown reading frequency, preserve authored alternatives and keep any new single-character readings out of phrase autoencoding until separately reviewed. Cite Sio and Morgado da Costa (2019), retain source attribution, and do not claim this source as an independent held-out evaluation corpus.

## 2. English Wiktionary: useful second candidate, larger extraction task

Wiktionary contains explicit word-level Cantonese readings. For example, [唔使客氣, revision 63033438](https://en.wiktionary.org/w/index.php?title=%E5%94%94%E4%BD%BF%E5%AE%A2%E6%B0%A3&oldid=63033438) labels the Guangzhou–Hong Kong Jyutping reading `m4 sai2 haak3 hei3`, separately from Taishanese and Hakka. This is evidence of the required source field, not an assertion that this example is new to our dictionary.

The [official Wikimedia download index](https://dumps.wikimedia.org/enwiktionary/latest/) actually lists a complete `enwiktionary-latest-pages-articles.xml.bz2` download (1,647,823,823 bytes in the index observed during this review), multistream alternatives, and checksum lists. These are source wikitext dumps, **not** a ready-made Cantonese pair table. No dump was downloaded, pinned or processed here, so net new vocabulary and extraction coverage remain unmeasured.

The entry's license link points to [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); Wikimedia's [Terms of Use, section 7](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content) describe text reuse, page/history attribution, imported-content notices and modification disclosure. This fits the combined dictionary's existing BY-SA 4.0 adaptation policy when the applicable attribution/notice requirements are retained. Do not assume that audio, images or all externally imported material have identical terms.

A future extractor must pin a dated dump and checksums, retain page/revision IDs and contributor-history links, and select only explicitly labelled target Cantonese/Jyutping pronunciation fields. A page can contain several languages and regional varieties; grabbing all romanization-looking strings would mix incompatible readings. Template expansion, alternate pronunciations, missing readings and character alignment need a full accounting. Do not synthesize Jyutping for entries without it. Expected value is colloquial words, variants and newer terms, but overlap with the existing seven source families and actual everyday-word gain must be measured before selection.

## Other leads checked, not recommended for immediate selection

- **Cifu:** its [primary repository](https://github.com/gwinterstein/Cifu/tree/896ba8c84dddc43071cf3060ad05251b414a867e) provides real word/Jyutping files under GPL-3.0. Its [construction paper, sections 5.1–5.2.3](https://aclanthology.org/2020.lrec-1.375.pdf) also documents HKCanCor among input corpora and automatically reconstructed pronunciations for entries absent from yeDict. It is not a clean source of uniformly authored whole-word readings, would require a separate data-license decision, and importing its corpus-derived vocabulary/frequencies risks contaminating our existing HKCanCor evaluation boundary.
- **KFCD:** the [pinned `yyzd` repository](https://github.com/kfcd/yyzd/tree/6cfb10f9ab8061b0357cf7b27c4333a275dacc28) openly supplies CC BY 3.0 character readings, including explicit Jyutping exports. Its example-word column does not supply aligned whole-word readings, so it cannot simply become a new word lexicon. The [publisher's larger word website](https://kaifangcidian.com/yue/) has a [CC BY 3.0 declaration](https://kaifangcidian.com/yue/cc/), but this bounded check did not establish a downloadable bulk word-plus-Jyutping export. Do not treat the site's word count as an available, audited pair dataset.

**Action:** audit Cantonese Wordnet first; keep Wiktionary as the next extraction project. Neither source establishes completeness for “all Chinese words.” The current dictionary, mapping files and package remain unchanged.
