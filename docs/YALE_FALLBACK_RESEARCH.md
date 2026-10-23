# Published Yale usage and the remaining source readings

Research snapshot: 23 October 2026, Hong Kong time. **Published Yale conversion data directly support `hm` and `hng`; the original LSHK scan deliberately records `ngm`, while `soei2` is also genuinely printed but remains linguistically unresolved.** A second finding is six published alternate Yale spellings which the present public decoder does not recognize as the intended syllables. This report proposes reviewable mapping additions; it changes no dictionary, mapping, runtime, installed IME or package.

This supplements, and does not rewrite, [the earlier fallback review](YALE_FALLBACK_REVIEW.md). Source presence, published conversion usage and decoder reachability are separate evidence. None is an independent human pronunciation approval or proof of vocabulary completeness.

## Snapshot and the twelve stored pairs

The read-only snapshot is `.local/wordnet-canonical/lexicon.sqlite3`: **739,128 pairs**, SHA-256 `d835b8c4487b90ef751c8c91f467b9245c8bd54ee5be8157531dd9530ac7667b`. The four fallback bases still affect **12 pairs across seven distinct texts**. Winning database source labels below do not imply that overlapping upstream sources are independent research.

| Base | Text | Exact stored reading | Winning source |
| --- | --- | --- | --- |
| `hm` | 哼 | `hm1` | `words.hk:wordlist` |
| `hm` | 哼 | `hm6` | `lshk:list.tsv` |
| `hm` | 啈 | `hm6` | `lshk:list.tsv` |
| `hm` | 噷 | `hm1` | `jyut6ping3.chars.dict.yaml` |
| `hng` | 哼 | `hng1` | `jyut6ping3.chars.dict.yaml` |
| `hng` | 哼 | `hng6` | `jyut6ping3.chars.dict.yaml` |
| `hng` | 啈 | `hng6` | `jyut6ping3.chars.dict.yaml` |
| `hng` | 嗯哼 | `ng6 hng6` | `jyut6ping3.words.dict.yaml` |
| `ngm` | 呣 | `ngm2` | `lshk:list.tsv` |
| `ngm` | 呣 | `ngm6` | `lshk:list.tsv` |
| `ngm` | 唔 | `ngm4` | `lshk:list.tsv` |
| `soei` | 穗 | `soei2` | `lshk:list.tsv` |

All twelve retain their existing canonical input route. The question here is the evidence for Yale classification and additional spellings, not whether the stored rows should be silently deleted or repaired.

## Original LSHK scan: these are not extraction artifacts

The [original `JPTableFull.pdf`](https://github.com/lshk-org/jyutping-table/blob/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3/JPTableFull.pdf), pinned to LSHK commit `dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3`, was downloaded, text-extracted and visually inspected on printed/PDF pages 10, 12, 77, 79 and 168. The retained PDF has 274 pages, 15,158,625 bytes and SHA-256 `6a713034f8deb8bda73189fc8339919739c5bedbf658110831ff14429802486c`. The git-blob SHA-1 is `19f03c5478a730a979ec7c8543dfaea5f883b896`.

| Printed page | Direct observation | What it establishes |
| --- | --- | --- |
| 77 | 呣 has `m2`, `ngm2`, `m6`, `ngm6`; both `ngm` rows are alternate readings, subclass 1.3. | The source itself intends and categorizes the `ngm` spellings. |
| 79 | 唔 includes `m4`, `ngm4`, `ng4`; `ngm4` is alternate subclass 1.3. 哼 includes `hang1`, `hng6`, `hm6`; `hm6` is alternate subclass 1.6. | These readings were not introduced by a TSV-column join or this project's parser. |
| 168 | 穗 has ordinary `seoi6` and alternate `soei2`, subclass 2. | `soei2` is visibly present in the original source, not a current-export transposition. |
| 10 | §4.16.1.3 describes adding an `ng` onset to a zero-onset form; §4.16.1.6 describes `ng`/`m` variation. §4.16.2 is the broad category for partly systematic variation. | The `ngm` rows have an explicit source classification. The broad `2` on `soei2` does not identify a particular changed-tone or literary/colloquial subtype. |
| 12 | §§5.2.10–11 explain alternate-reading and subclass columns. | The category interpretation comes from the source's own key. |

Thus `ngm` is deliberate source notation, with an explanation of its component relationship. This is stronger than finding the same spelling in repeated exports, but still does not independently establish its phonetic realization. `soei2` may be a rare vowel variant or a source editorial error; the inspected material does not decide that. **There is no evidence here to silently replace `ngm` by `m`/`ng`, transpose `soei` to `seoi`, or quarantine those rows as proven errors.**

The current [LSHK `list.tsv`](https://github.com/lshk-org/jyutping-table/blob/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3/list.tsv) contains 穗 `soei2` at physical line 15651, 呣 `ngm2`/`ngm6` at 28686/28688, and 唔 `ngm4` at 29011. It explicitly splits `ngm` into onset `ng` and final `m`, and `soei` into onset `s` and final `oei`. The old scan supplies category information absent from those current export fields.

Local evidence: [retained PDF](D:/IME_Project/.local/yale-fallback-research/JPTableFull.dad2dd6.pdf), [text search](D:/IME_Project/.local/yale-fallback-research/pdf-text-search.json), and inspected page renders [10](D:/IME_Project/.local/yale-fallback-research/original-page-10.png), [12](D:/IME_Project/.local/yale-fallback-research/original-page-12.png), [77](D:/IME_Project/.local/yale-fallback-research/original-page-77.png), [79](D:/IME_Project/.local/yale-fallback-research/original-page-79.png), [168](D:/IME_Project/.local/yale-fallback-research/original-page-168.png).

## Direct published Yale evidence for `hm` and `hng`

開放詞典/KFCD's [conversion table](https://github.com/kfcd/pingyam/blob/d0ceb32c2da07d156db99e50b192aaf45236ca95/pingyambiu), at commit `d0ceb32c2da07d156db99e50b192aaf45236ca95` (15 November 2025 UTC), explicitly labels numeric Yale as column 1, diacritic Yale as column 2 and Jyutping as column 7 in its [README](https://github.com/kfcd/pingyam/blob/d0ceb32c2da07d156db99e50b192aaf45236ca95/README.md).

Physical lines 1481–1486 map Jyutping `hm1`–`hm6` to numeric Yale `hm1`–`hm6`; lines 1487–1492 similarly map `hng1`–`hng6` to `hng1`–`hng6`. Its diacritic forms include `hmh` and `hngh` for tone 6. The initial `h` is lexical; the final `h` in those diacritic low-register forms marks tone. For a plain profile derived from **numeric** Yale, strip only the terminal digit: **`hm` and `hng`**. Do not remove every `h` from accented Yale.

There is also actual lexical usage: KFCD's [original numeric-Yale dictionary](https://github.com/kfcd/yyzd/blob/6cfb10f9ab8061b0357cf7b27c4333a275dacc28/yyzd.txt#L2338), pinned to commit `6cfb10f9ab8061b0357cf7b27c4333a275dacc28`, lists 哼 `hng6`. Its [diacritic export](https://github.com/kfcd/yyzd/blob/6cfb10f9ab8061b0357cf7b27c4333a275dacc28/dist/tsv/%E7%B9%81%E9%AB%94/%E7%B2%B5%E8%AA%9E%E5%AD%97%E5%85%B8_(%E8%80%B6%E9%AD%AF_%E8%AA%BF%E7%AC%A6).txt#L2148) gives `hngh`. This is direct published usage, beyond combining unrelated chart cells.

The conversion README says it derives from KFCD's own dictionary data, has been used to display pronunciations since 2009, includes every possible tone and attempts to include syllables without characters. Therefore its systematic rows are **published conversion usage**, not proof that every listed tone is a manually attested word or independently validated linguistic judgment. It does not provide row-by-row authorship or validation. No exact Jyutping-column row for `ngm` or `soei` was found.

CUHK's [syllable table](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-can/syllables.htm) independently provides lexical examples for `h` plus syllabic `m` (噷) and `h` plus syllabic `ng` (哼). Its [pronunciation index](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-can/pho-rel.php?s2=ng) lists 哼 `hng6`. These support the shapes, without approving all stored character/tone pairs. A mapping classification such as **published Yale extension** for `hm`/`hng` is defensible; calling all four rare bases formally verified is not.

## Bounded conversion-table coverage of the current inventory

All 3,972 KFCD rows have the documented 11 columns; no numeric syntax or checked-tone-correspondence failure was found. The table has 741 distinct Jyutping bases. Coverage below strips only the numeric tone from the table's Yale and Jyutping columns, including the source's Yale 7/8/9 versus Jyutping 1/3/6 checked-tone correspondence. It measures base spellings, not independent word pronunciations or every observed tone.

| Current inventory category | Total bases | KFCD covered | Same plain spelling | Alternate plain spelling | Absent from KFCD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Current table mapping | 778 | 699 | 699 | 0 | 79 |
| Current extension | 96 | 28 | 22 | 6 | 68 |
| Current canonical fallback | 4 | 2 | 2 | 0 | 2 |
| **All current bases** | **878** | **729** | **723** | **6** | **149** |

The 22 matching extensions are `ben dep em en fen fet gep get kem ken kep lem men oet pen pet sen set wem wen wet zem`. Six more extensions have a directly published alternative, below. KFCD coverage adds evidence for 28 of the 96 current extensions, but its absence for the remaining 68 does not invalidate their other evidence. Likewise the 149 absent bases must not be removed merely because this table omits them. Exact per-base records and retained source hashes are in [kfcd-coverage.json](D:/IME_Project/.local/yale-fallback-research/kfcd-coverage.json).

## Six published alternatives expose a current input gap

KFCD uses `eeu` where the project's current policy uses `ew`. The existing `ew` policy follows a primary implementation convention documented in [PyCantonese's Yale converter](https://docs.pycantonese.org/v4.3.0/_modules/pycantonese/jyutping/yale.html); the direct KFCD table supports accepting additional spellings, rather than discarding the working current routes.

| Jyutping base | Current plain route | KFCD plain alternative | Stored affected pairs | Distinct affected texts |
| --- | --- | --- | ---: | ---: |
| `deu` | `dew` | `deeu` | 256 | 204 |
| `eu` | `ew` | `eeu` | 7 | 6 |
| `meu` | `mew` | `meeu` | 11 | 10 |
| `peu` | `pew` | `peeu` | 3 | 2 |
| `seu` | `sew` | `seeu` | 4 | 4 |
| `zeu` | `jew` | `jeeu` | 16 | 16 |

The union is **297 stored pairs across 242 texts**. Counts include generated phrases and loanwords; they are not 297 independently authored pronunciations. All six representative full-word targets below were selected from source-explicit records, preferring them over generated records.

Read-only public probes used `Engine(..., learning_path=None, prefer_yale=True)` and `lookup_page(..., page_size=90, mode='forgiving')`, following pages until the exact stored text/reading appeared, the public API exhausted, or a capacity limit occurred. Rank means exact text **and** reading; text-only rank is recorded separately. No capacity error occurred in these probes. All six alternate standalone forms exhausted without their intended one-syllable targets. `peu` has no one-syllable stored target, so standalone `peeu` is a no-oracle observation, not a failed lexical target.

| Exact stored target | Source reading | Alternate whole-word input | Alternate outcome | Current control | Exact control rank |
| --- | --- | --- | --- | --- | ---: |
| 掉低 | `deu6 dai1` | `deeudai` | Target text/pair absent; public results exhausted | `dewdai` | 1 |
| OL | `ou1 eu1` | `oueeu` | Target text/pair absent; public results exhausted | `ouew` | 1 |
| 喵喵喵 | `meu1 meu1 meu1` | `meeumeeumeeu` | Target text/pair absent; public results exhausted | `mewmewmew` | 1 |
| 輕飄飄 | `heng1 peu1 peu1` | `hengpeeupeeu` | Target text/pair absent; public results exhausted | `hengpewpew` | 1 |
| sales | `seu1 si2` | `seeusi` | Target text/pair absent; public results exhausted | `sewsi` | 1 |
| 噍低 | `zeu6 dai1` | `jeeudai` | Target text/pair absent; public results exhausted | `jewdai` | 1 |

掉低, 喵喵喵 and 噍低 have explicit Rime whole-word readings; OL, 輕飄飄 and sales have explicit words.hk readings. Unrecognized alternates are currently interpreted through other supported segmentations, such as `de` plus `eu`; this is an input-alias gap, not evidence that the target vocabulary is missing. The measured scope is source-derived decoder reachability, not held-out linguistic accuracy. Raw ranks, first-page candidates, capacity flags, provenance and unchanged-hash guards are retained in [kfcd-public-probes.json](D:/IME_Project/.local/yale-fallback-research/kfcd-public-probes.json), SHA-256 `21f635fea7159cc7f5fed6b089804017bec9d0dd8e837a812bd61fca764dd21f`.

## Recommendations and remaining uncertainty

1. **`hm`/`hng`:** a mapping update can legitimately cite direct KFCD Yale usage and keep the existing plain letters. Classify these conservatively as attested/published extensions unless a separate policy review establishes a stronger formal category. This does not approve each stored tone assignment.
2. **Six `eeu` alternatives:** add aliases `deeu/eeu/meeu/peeu/seeu/jeeu` while retaining `dew/ew/mew/pew/sew/jew`. Their provenance, collision behavior and full-word routes should enter the mapping tests and catalog audit before publication.
3. **`ngm`:** retain the source reading and explain the original scan's deliberate onset-addition category. A source-specific compositional extension remains possible, but no direct whole-syllable Yale row was found. Do not relabel source notation as an established phonetic transcription without further evidence.
4. **`soei`:** retain the source literal and unresolved status. CUHK's [finals comparison](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-mf/finals.php) and [PyCantonese's component converter](https://docs.pycantonese.org/v4.3.0/_modules/pycantonese/jyutping/yale.html) suggest a mechanically compositional `s` + `eu` + `i` spelling `seui`. That is an **inference**, not verified whole-final Yale attestation; ordinary `seoi` also maps to `seui`, so source-preserving disambiguation matters. Neither a guessed repair nor an unqualified formal mapping is justified by this review.

No recommendation is an approval record. The unresolved phonetic status of `ngm`/`soei`, the other extensions, and open-ended vocabulary coverage prevent a claim that every Chinese word now has independently verified formal Yale.

## Retained evidence, licenses and unchanged inputs

KFCD's pinned [README license declaration](https://github.com/kfcd/pingyam/blob/d0ceb32c2da07d156db99e50b192aaf45236ca95/README.md#%E7%89%88%E6%AC%8A) and [LICENSE](https://github.com/kfcd/pingyam/blob/d0ceb32c2da07d156db99e50b192aaf45236ca95/LICENSE) identify **CC BY 3.0**. Future reuse must credit 開放詞典/KFCD, link the source and license, and identify modifications. This review retains the original text table and notices for research; no conversion code was copied and no source was imported into the product. The existing combined-data licensing and LSHK CC BY 4.0 attribution remain as documented in the project. The cited CUHK/EdUHK teaching material was consulted, not harvested into the dictionary or reproduced as complete charts.

| Retained KFCD file | Bytes | SHA-256 |
| --- | ---: | --- |
| `pingyambiu` | 267,047 | `bfb4a10ff62238a27d087a9a82e64de9b3cf9d3fc2326097ef083a476103e3aa` |
| `README.md` | 3,090 | `72667a8ac72516528ffb527796646aef0382c3c6e8f0ba05140fdfcb8a5e1977` |
| `LICENSE` | 836 | `243ce65e3a5a24669b08b5b6d25e82e961dfc747f841f04f199126a218968100` |

Files reside under `.local/yale-fallback-research/kfcd-pingyam-d0ceb32c2da07d156db99e50b192aaf45236ca95/`. Probe before/after hashes agree for the database above; `cantonese_ime/engine.py` (`f45b0a29693e613ba9dd0633be7ca67e905ad3bbca17b95fc01aac36df823d5f`); `cantonese_ime/mappings.py` (`3eaee728fc7355d466dee722e1ee4f67e508eb9c362fd92762b8d0531e5e99fe`); `.local/wordnet-mappings/syllables.json` (`43fa147c5a852563e7b3d59280362d274984eeb53d4fd9c1b8bb5097539fe9a3`); and the pinned KFCD table. The historical review, current runtime, staged package and installed IME were left unchanged.
