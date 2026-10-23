# Review of the four remaining Yale fallbacks

Research snapshot: 23 October 2026, Hong Kong time. This is a source review, not an approved pronunciation correction or a change to the mappings. The current database contains 736,570 text/reading pairs and 621,245 distinct texts; the four fallback bases occur in **12 pairs across seven texts**. Every pair already has a working canonical input route. Complete formal Yale coverage remains unestablished.

The reviewed database SHA-256 is `3fccc5bcf45cbb676b8a1a51e2030d418803af64b3cd5c0ae7d67cf90a4711bb`. Its manifest, mapping inventory and the exact pair list are recorded in [yale-fallback-review.json](yale-fallback-review.json). No dictionary, mapping, runtime or package file was changed for this review.

| Base | Stored pairs containing the base | Evidence and provisional recommendation |
| --- | --- | --- |
| `hm` | 哼 `hm1`, 哼 `hm6`, 啈 `hm6`, 噷 `hm1` | Several retained sources attest the base. CUHK explicitly places 噷 at initial `h` plus syllabic final `m`. Plain `hm` is a defensible **documented compositional Yale extension**, pending the mapping review; its letters would remain unchanged. This does not independently validate every character/tone pairing. |
| `hng` | 哼 `hng1`, 哼 `hng6`, 啈 `hng6`, 嗯哼 `ng6 hng6` | Several retained sources attest the base. CUHK explicitly places 哼 at `h` plus syllabic `ng`; its pronunciation index lists 哼 under `hng6`. Plain `hng` is likewise a defensible compositional extension, pending review. |
| `ngm` | 呣 `ngm2`, 呣 `ngm6`, 唔 `ngm4` | Attested in the retained LSHK table only. Those rows also occur in the repository's 2004 and 2023 exports. This establishes source lineage, **not** independent phonetic confirmation. Keep the literal fallback and seek an explanation of the `ng` + `m` analysis from the source editors or a phonetic reference. Do not replace it with `m` or `ng`. |
| `soei` | 穗 `soei2` | Attested in the retained LSHK table only, including its 2004 and 2023 exports. The row explicitly separates initial `s`, final `oei` and tone `2`; the same table separately retains 穗 `seoi6`. No verified primary Yale correspondence for whole final `oei` was found in this bounded review. Keep `soei`; do not silently transpose it to `seoi` or advertise guessed `seui` as verified. |

“Several sources” means separate retained source files, not proven independent linguistic research. Deduplication leaves one winning source label per stored pair; the mapping inventory also retains attestations from overlapping source files. Zero supplement weight means frequency is unknown.

## What the primary references establish

CUHK's [Table of Cantonese Syllables](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-can/syllables.htm) uses the LSHK transcription system. Its final two rows explicitly contain `h` + `m` (噷) and `h` + `ng` (哼). Its [syllabic-ng pronunciation index](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-can/pho-rel.php?s2=ng) additionally lists `hng6` with 哼. These are primary lexical/phonological attestations for the two shapes; they are not Yale word spellings and do not approve all twelve stored pairs.

The [EdUHK Yale teaching chart](https://www.eduhk.hk/cle/resources/cep/cantonese-survival-package/Appendix%20I.html) provides initial `h` and syllabic `m`/`ng`. CUHK's [comparison of romanized finals](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-mf/finals.php) gives Yale `m`/`ng` and the ordinary Jyutping `eoi` → Yale `eui` correspondence. The latter page distinguishes its devised extensions from sounds present in original schemes. Neither chart verifies a whole `oei` correspondence. These facts support the **extension** recommendation for `hm`/`hng`; they do not establish direct formal Yale attestations for the four rare whole syllables.

[PyCantonese 4.3.0's own parser](https://docs.pycantonese.org/v4.3.0/_modules/pycantonese/jyutping/parse_jyutping.html) explicitly discusses parsing `hng6` as initial `h` and nucleus `ng`. Its [Yale converter](https://docs.pycantonese.org/v4.3.0/_modules/pycantonese/jyutping/yale.html) maps those components compositionally. Reading that implementation supports plain `hm`/`hng` operationally. Its permissive component grammar is not independent proof that every admitted syllable, such as `ngm` or `soei`, is linguistically valid. A mechanical `oe` + `i` conversion also cannot establish an authoritative Yale spelling for rare `oei`.

## Source lineage and unresolved checks

The pinned [LSHK repository README](https://github.com/lshk-org/jyutping-table/blob/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3/README.md) describes its current workgroup table and the extraction lineage of the historical data. All four `ngm`/`soei` pairs occur verbatim in [the 2004 export](https://github.com/lshk-org/jyutping-table/blob/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3/versions/list-20040907.tsv), [the 2023 export](https://github.com/lshk-org/jyutping-table/blob/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3/versions/list-20230104.tsv) and the pinned current `list.tsv`. Thus they were not introduced by this project's importer. Those exports share source lineage; repeating them does not multiply independent evidence. The original scanned table was not independently visually verified in this review. No conclusion that either spelling is an editorial error is justified here.

The next useful linguistic checks are narrow: confirm what the original table intends by `ngm`, and obtain a primary explanation or audio/phonetic account for 穗 `soei2`, including whether its vowel differs from `seoi`. No additional broad dictionary download was needed to establish these gaps. Vocabulary completeness remains open ended and separate from a mapping's coverage of the current stored dictionary.

## Reuse and review boundary

The LSHK data are already retained with their CC BY 4.0 attribution. Other stored-source licenses and the combined database's CC BY-SA 4.0 adaptation policy remain documented in `data/DATA_LICENSE.md` and `THIRD_PARTY_NOTICES.md`; this report grants no new license to outside material. The CUHK and EdUHK pages were consulted and cited, not harvested into the dictionary or reproduced as complete charts. EdUHK explicitly reserves reproduction rights. PyCantonese was inspected as a primary implementation reference; no code was copied or executed for this review.

All recommendations remain **pending human linguistic/mapping review**. There are no approval records, pronunciation repairs, new dictionary rows or claims of exhaustive formal Yale coverage in this report.
