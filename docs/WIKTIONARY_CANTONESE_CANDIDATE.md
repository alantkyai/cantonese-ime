# Wiktionary Cantonese candidate: bounded source research

Research date: **23 October 2026 (Hong Kong)**. Candidate research only; no dictionary, mapping rules, runtime, package or installed input method was changed. Comparisons used the read-only Wordnet canonical build, **739,128 pairs / 623,223 texts**, SHA-256 `d835b8c4487b90ef751c8c91f467b9245c8bd54ee5be8157531dd9530ac7667b`, checked before and after each probe. The older [additional-source survey](ADDITIONAL_CANTONESE_SOURCES.md) remains a historical pre-Wordnet comparison.

**Recommended next source:** the official **Yue Wiktionary 2026-10-01 XML dump**, using explicit own-headword pronunciation fields and an isolated append-only candidate. Its compressed archive is only 3.5 MB and has page/revision provenance. A narrow pass found **194 potentially new pairs / 110 entirely new texts**. These are mechanical overlap counts, not acceptance or completeness claims.

## Retained official snapshot and scope

The [official dated index](https://dumps.wikimedia.org/yuewiktionary/20261001/) supplies [pages-articles XML](https://dumps.wikimedia.org/yuewiktionary/20261001/yuewiktionary-20261001-pages-articles.xml.bz2) and [SHA-1 checksums](https://dumps.wikimedia.org/yuewiktionary/20261001/yuewiktionary-20261001-sha1sums.txt). The fetched archive is **3,510,364 bytes**, decompressing to 23,513,780 bytes. Its SHA-1 matches the official `78600a2b4cf61cc9157047bed02980e89c37fc80`; locally computed SHA-256 is `e09d60b43588bf5a860ce2dac2a865002e145579b4c3c7a3cc26743e5407d542`.

All retained downloads, HTTP headers, exact research scripts, source-template extracts, results and ledgers are under [.local/source-research/wiktionary-20261023](../.local/source-research/wiktionary-20261023/), bound by its [research manifest](../.local/source-research/wiktionary-20261023/research-manifest.json). Nothing was installed to parse them. The XML includes templates/modules and other languages; an edition written in Cantonese is not itself a guarantee that every entry is Cantonese. Wikimedia documents the [dump format](https://meta.wikimedia.org/wiki/Data_dumps/Dump_format).

The [exact Yue probe](../.local/source-research/wiktionary-20261023/probe_yue_dump.py) selects namespace 0, then only level-two `{{langue|yue}}` sections. Within those sections it accepts line-leading, flat `{{zh-pron|c=...}}` or `{{Yue-rom|...}}` first-positional fields. The original source templates are retained from the same dump: `模:Yue-rom` revision 10752, `模:zh-pron` revision 14605 and `模:粵拼` revision 9516. The English template [documentation](https://en.wiktionary.org/wiki/Template:zh-pron/documentation) distinguishes `c=` Cantonese Jyutping from Taishanese/Dongguan/Yangjiang parameters and marks tone changes separately.

The probe masks comments without shifting offsets, splits explicitly comma-separated alternatives, normalizes reading case/whitespace, and requires canonical tone digits 1–6, existing 878 bases and one Han codepoint per syllable. It does not expand templates, read definitions/examples, follow redirects, synthesize readings or convert marked tone changes. Repeated template occurrences remain separately located before exact-pair deduplication.

| Observed boundary | Count |
| --- | ---: |
| All XML pages, recorded in page ledger | 11,396 |
| Main-namespace pages | 9,608 |
| Explicit supported Yue language sections | 1,948 |
| Sections without a recognized pronunciation field | 221 |
| Recognized pronunciation template calls | 2,327 |
| Supported flat `Yue-rom` / `zh-pron` calls | 949 / 592 |
| Unsupported `粵拼` calls / nested or non-line-leading calls | 718 / 68 |
| `zh-pron` call without one unique `c=` field | 1 |
| Examined literal reading variants | 1,562 |
| Accepted variant occurrences / repeated accepted pairs | 1,474 / 437 |
| Excluded variants: non-Han / notation / unknown base / alignment | 45 / 38 / 4 / 1 |
| Unique admitted research pairs / texts | 1,037 / 987 |
| Existing exact pairs / potentially new pairs | 843 / **194** |
| Entirely new texts | **110** |

The [page ledger](../.local/source-research/wiktionary-20261023/yue-page-ledger.jsonl) locates every page by namespace, title, page ID, revision ID/time, revision URL and contributor-history URL. The [field ledger](../.local/source-research/wiktionary-20261023/yue-field-ledger.jsonl) records each recognized field or missing-field section with line/offset, template/variant ordinal, raw reading, normalized reading and outcome. [The result](../.local/source-research/wiktionary-20261023/yue-dump-probe.json) also counts every template name observed in selected sections. Unsupported structures are counted, not interpreted; **1,037 is not a count of all readings available in this dump**.

Examples of absent whole texts include 一棍打死成船人 (`jat1 gwan3 daa2 sei2 sing4 syun4 jan4`) and 中宵 (`zung1 siu1`). The source also supplies questionable-looking readings such as 三冬 `saan1 dung1`; a canonical spelling check cannot certify pronunciation. Unknown-base examples include `yan4`, `dur4` and `hoen2`. They stay excluded rather than being repaired to a familiar syllable.

## Kaikki/Wiktextract: complementary, broader extraction work

[Kaikki's raw-data page](https://kaikki.org/dictionary/rawdata.html) describes regular Wiktextract exports. The publisher's [README](https://github.com/tatuylonen/wiktextract) documents JSONL, pronunciation extraction and per-language/per-tag subsets. The extractor's MIT code license is separate from the Wiktionary data license; no extractor package or copied code was used here.

Selecting only `lang_code=yue` misses much of the desired Han vocabulary. The downloaded Chinese-edition `粵語` subset has 1,854 records, of which 1,785 are romanization entries and 64 are redirects. The current English [Cantonese index](https://kaikki.org/dictionary/Cantonese/index.html) likewise predominantly lists romanizations/characters. Own Han headwords with Cantonese readings commonly occur under `lang_code=zh` in the much larger [Chinese export](https://kaikki.org/dictionary/Chinese/index.html).

The downloaded current [Cantonese-tagged Chinese subset index](https://kaikki.org/dictionary/Chinese/tags/rY/Cantonese/index.html) identifies extraction on **2026-10-21**, from enwiktionary **2026-10-01**, with Wiktextract `c1bb342f3f3afb42e2200dea4dfc8bdc9fb0a4f4` and Wikitextprocessor `6f96ddf5f3466707f1869fe6618390fd77dfd109`. This differs from older search-cache page dates. Its advertised postprocessed file is **99,849,306 bytes** by HTTP Content-Range. It is marked deprecated and may merge other data; it is not a substitute for a pinned raw revision audit.

Only three 4,000,000-byte ranges starting at bytes 0, 40,000,000 and 80,000,000 were downloaded. All responses were HTTP 206 with matching ETag/Last-Modified and recorded Content-Range; partial boundary lines were discarded. The [sample probe](../.local/source-research/wiktionary-20261023/probe_kaikki_ranges.py) examines only the entry's own Han `word` and explicit Cantonese+Jyutping `sounds[].zh_pron`, rejects contradictory romanization/variety tags, converts only superscript digits 1–6 and applies syntax/base/alignment checks. It does not obtain readings from forms, glosses, translations or Mandarin.

Across **1,028 complete records**, this found **645 distinct candidate pairs / 598 texts**, including **119 new pairs / 80 new texts** against d835. Results are in [kaikki-range-probe.json](../.local/source-research/wiktionary-20261023/kaikki-range-probe.json). These byte windows are neither random nor complete, so no total-vocabulary extrapolation is justified. Their new-pair union with the narrow Yue-dump result is **312 pairs / 190 new texts**, with one overlapping new pair.

A bounded official [revisions API](https://www.mediawiki.org/wiki/API:Revisions) batch separately confirmed explicit own `zh-pron|c=` fields for six sampled new texts: 丈人佬, 一臺花, 三叉神經線, 五行欠抦, 出監 and 亂嗮大龍. The [raw response](../.local/source-research/wiktionary-20261023/en-wiktionary-revision-sample.json) retains page/revision IDs and wikitext. This spot check does not validate the other sampled pairs. A complete English-source importer should retain raw dated revisions/dump, extraction versions and unresolved metadata instead of trusting a tag name alone.

## License, attribution and next implementation boundary

The retained [Yue page footer](../.local/source-research/wiktionary-20261023/yue-page-licensing-sample.html) explicitly links **CC BY-SA 4.0**. Wikimedia's [Terms of Use, section 7](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content) permits attribution through source-page/history URLs, requires modification/license notices, and calls for preserving additional imported-source attribution where applicable. The full [terms snapshot](../.local/source-research/wiktionary-20261023/wikimedia-terms.html) is retained. Use the project's existing full CC BY-SA 4.0 text for the transformed dictionary notice, credit **Yue Wiktionary contributors** (and English Wiktionary/Kaikki/Wiktextract when applicable), retain revision/history links and explain the extraction/normalization/exclusions. No audio, image, example quotation or definition is selected for redistribution. This data selection does not change the application-code license.

The next concrete implementation can remain small and auditable:

1. Pin this dated archive, official checksum list, terms/footer, source-template evidence and the frozen 878-base admission inventory in a candidate lock. Bound compressed/decompressed size, XML depth/nodes and per-page text; reject DTD/entities and unsupported XML structure without executing templates or Lua.
2. Account for every XML page and main-page language section. Initially accept only the two flat literal fields above, in their own supported Yue section and own Han headword. Count missing fields and preserve every unsupported/ambiguous template, marked form and unknown base as source-located review events. `粵拼` positional superscripts can be a separately audited extension; they are not silently included in the 1,037-pair result.
3. Emit zero-frequency explicit pairs with complete page/revision/template/variant provenance; retain duplicates as occurrence accounting. Build an isolated append-only candidate **after** existing autoencoding: preserve earlier pairs, IDs, weights and origins, and keep new character readings out of the encoder.
4. Independently replay source/accounting and verify every changed plain-Yale input and its existing competing target texts through public paging. Only then decide default-source selection. Source correctness and user ranking remain separate from mechanical retrieval.

No full English/Chinese Wiktionary dump was downloaded. Total retained public download bytes are recorded in the research manifest and remain well below the 100 MB allowance. “All Chinese words” remains open-ended; these results identify measurable additional explicit readings rather than establish exhaustive vocabulary.
