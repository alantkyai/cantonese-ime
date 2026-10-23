# Cantonese dictionary snapshot

Build the offline lexicon with Python 3.11 or newer from the project root:

```powershell
python tools/build_dictionary.py
python tools/build_mappings.py
```

This uses retained source files; no network access, packages or installation are
needed. Source hashes and lengths are checked before parsing. SQLite is built in
a temporary file, checked, then replaces `generated/lexicon.sqlite3`. Its sibling
`lexicon.manifest.json` records sources, policies, counts and SHA-256. A build
failure before publication preserves the old database. Database and manifest are
separate file replacements; the auditor detects a mismatched pair after an
interrupted publication.

## Included data

This describes the development database, SHA-256
`bd312406a15162556ac58a257ede1514ad40890c793b6f8fa05084fda2d6241a`.
It is published in the project with the v3 Yale profile. All 567 Python tests and
31 staged native x64 cases passed. The final exhaustive scan passed for all
503,708 compact Yale input groups, representing 776,335 stored pairs: 503,925
public page calls and zero missing target memberships. The four workers took
51 minutes 1 second; the frozen replay reverified all 58 copied files and passed.
See [the aggregate](../docs/final-yale-catalog-coverage.json),
[frozen replay](../.local/yale-catalog/final-v3-frozen-runtime/replay-validation.json)
and [current staged validation](../docs/yale-expanded-v3-ime-validation.json).
This proves retrieval for the finite stored catalog, not pronunciation quality
or all Chinese vocabulary. The r2 package (`fde66d90…`) is now installed and
verified: all 86 payload files match, including this dictionary, and a fresh x64
DLL load passed. Personal-learning hashes remained unchanged and the broker is
ready with learning enabled. See [installed validation](../docs/yale-expanded-v3-installed-validation.json).
User application typing and visual acceptance remain separate; reopen the app
and select Cantonese IME with Win+Space before checking the new revision.

| Origin in the current database | Unique text/reading pairs |
| --- | ---: |
| Rime Cantonese explicit character and word readings | 137,439 |
| Additional LSHK readings | 7,859 |
| Additional words.hk wordlist readings after both earlier sources | 12,157 |
| Additional TypeDuck principal-table readings | 34,364 |
| Additional provisional Unihan character readings after earlier sources | 2,892 |
| Additional CC-Canto dictionary pairs after earlier explicit sources | 22,677 |
| Additional CC-CEDICT Cantonese reading pairs after CC-Canto | 106,990 |
| Generated complete phrase readings | 412,192 |
| Cantonese Wordnet pairs appended after phrase generation | 2,558 |
| CC-CEDICT written-headword pairs generated after Wordnet | 36,884 |
| Yue Wiktionary explicit pairs appended after headword encoding | 323 |
| Total | 776,335 |

The database contains 644,427 distinct texts. The final additions preserve all
739,128 preceding rows and IDs, adding 37,207 pairs and 21,204 texts. Two normal
default builds have identical database and manifest bytes; their streaming
comparison also matches every entry field and ledger against the isolated
combined candidate. See [the canonical comparison](../.local/final-source-canonical/comparison-report.json).

The historical Wordnet addition contributes
2,558 pairs and 1,978 new texts, preserving all earlier 736,570 rows, IDs,
readings and weights. Two independent clean builds match byte for byte; see
[the exact comparison](../docs/wordnet-dictionary-comparison.json).
The earlier CC-Canto expansion added 129,609 pairs and 125,924 texts; no previous text disappeared.
Sixty-five previously generated alternatives across 33 texts were superseded by
explicit whole-word source readings. Source import counts above are measured
before phrase generation, except Wordnet which is appended afterward, so they differ from additions against an earlier full
database. See the [exact comparison](../docs/yale-dictionary-comparison.json).

There are 878 observed tone-free bases, including source extensions and unusual
spellings. An observed inventory is not a claim that every form belongs to the
formal Jyutping scheme. See [mapping provenance](mappings/README.md).
The v3 profile has 778 ordinary-table routes, 98 explicitly classified extensions
and two Jyutping fallbacks (`ngm`, `soei`). KFCD attests the marginal `hm`/`hng`
extensions and six extra whole-syllable ASCII spellings: `deeu`, `eeu`, `meeu`,
`peeu`, `seeu`, `jeeu`. Primary `ew`-family routes remain available; alternatives
are not fed recursively through spelling rules. Formal Yale coverage and
project typing extensions remain separately labeled.

Rime Cantonese is pinned to `259f0e48bba840c3a2e0d117539e96937f3d89bc` in
[sources.lock.json](sources.lock.json). The LSHK table is pinned to
`dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3` in
[its lock](mappings/lshk.sources.lock.json). The words.hk wordlist snapshot was
retrieved on 22 October 2026; [its lock](supplements/wordshk.sources.lock.json)
retains the JSON and the exact public-domain declaration page. That declaration
is scoped to wordlist/pronunciations. Definitions, examples and other API datasets
are excluded. Full applicable licenses, upstream READMEs and attribution are
retained under `vendor/` and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The TypeDuck principal table is pinned to
`7f9d90d4185eca293576de5b5dddaaf1d265f3c9`, with its explicit CC BY 4.0 scope
and exclusions in [the lock](supplements/typeduck.sources.lock.json). The
[historical provenance audit](../docs/typeduck-data-audit.md) distinguishes
physical explicit rows from independent human phrase review. Unicode 18.0.0
Unihan is pinned by archive/member hashes and a retained Unicode License V3
notice in [its lock](supplements/unihan.sources.lock.json). Only direct
`kCantonese` character values are used, with provisional status retained.

The added [CC-Canto snapshot](supplements/cccanto.sources.lock.json) retains
explicit brace-delimited Cantonese readings for aligned traditional and simplified
headwords. Mandarin Pinyin and definitions do not become lookup data. Original
sources retain CC BY-SA 3.0 notices; the combined transformed data is offered
under [CC BY-SA 4.0](DATA_LICENSE.md). The [source audit](../docs/cccanto-data-audit.md)
accounts for rejected and partly accepted records without guessed repairs.

[Cantonese Wordnet](supplements/wordnet.sources.lock.json), under CC BY 4.0,
supplies 10,775 accepted own-Lemma/own-Form pairs before overlap removal.
Only the Cantonese lexicon is selected. All 11,907 blank, excluded, quarantined
and normalized source events are accounted for in the
[independent source audit](../docs/wordnet-source-audit.json). Its 2,558 new
zero-weight pairs are appended after autoencoding and do not supply encoder
inputs or replace earlier rows. The raw source lock retains its original
candidate-preparation wording; build metadata separately records selection.

[CC-CEDICT written headwords](supplements/cccedict-headwords.sources.lock.json)
supply only traditional and simplified written forms. The bounded Cantonese
encoder uses the fixed earlier permitted character cohort; Mandarin Pinyin and
definitions supply no codes. Its 250,590 source-form occurrences and 21,142 absent
headwords are fully ledgered: 21,038 texts receive 36,884 complete zero-weight
generated pairs, while 34 path-limited and 70 unencodable texts stay quarantined.
The new rows never become translator inputs. See [selection and evidence](../docs/CCCEDICT_HEADWORD_CANDIDATE.md).

[Yue Wiktionary](supplements/yue-wiktionary.sources.lock.json) supplies 1,486
explicit own-headword pairs from pinned literal pronunciation fields. Of these,
323 pairs and 166 texts are new after earlier sources; overlaps retain their
earlier provenance and weight. No template expansion, guessed repairs or
definitions are imported. All 11,396 pages, 19,804 section/preamble records,
5,366 fields and 647 review events are retained and independently matched to
the raw export. The new zero-weight readings are appended after both encoding
passes and never feed them. Original revision/contributor attribution and
CC BY-SA 4.0 notices remain with the source.

LSHK contributes only explicit `JP` readings: 38,191 single-syllable and three
multisyllable rows before overlap removal. Its 112 blank-`JP` description rows
are review records; description pronunciations are never repurposed as character
readings. words.hk supplies 66,370 accepted readings before overlap removal.
Exactly one documented trailing variant `*` is normalized with 2,225 informational
records retaining raw text and readings. The 383 quarantined words.hk rows contain
non-Jyutping notation or ellipsis templates, preserved intact for review.
TypeDuck contributes 155,509 valid explicit pairs before overlap removal; its
two tilde-marked phonetic annotations stay quarantined with raw lines. Its
percentage ranking values, including values over 100%, are not imported as
frequencies or probabilities. All 29,936 direct Unihan pairs are present after
overlap removal, without overriding earlier readings or inheriting variants.

## Phrase encoding and weights

Every one of the 330,701 Rime text-only phrase rows has a `phrase_encodings` record:

| Result | Source phrase rows |
| --- | ---: |
| Already has a source-explicit whole-word reading | 7,540 |
| Complete, one generated reading | 293,729 |
| Complete, multiple generated readings | 29,352 |
| Reaches the 32-path limit; quarantined | 80 |

The Python autoencoder adapts librime `ScriptEncoder` and `EntryCollector` at
`1b3417d2b6a11b5e50e0e1fa9dc396056aa11dce`. Only source entries with one code
syllable become translation tokens. Per-token readings retain at least 5% of
that token's summed weight; a zero total retains all readings. Traversal visits
longest matching text tokens first, then lexical codes. Limits are 32 Unicode
codepoints, 32 complete paths, and a finite work guard. Reaching exactly 32 is
conservatively classified as truncated. Partial codes remain in the ledger and
never enter the live lexicon. Source-explicit whole-word readings take priority.
Unihan collation/transliteration values and additional CC-Canto character
readings are excluded from the encoder's
translation tokens; they remain available as direct character lookups.

These are mechanical possibilities, not contextually verified pronunciations.
The 29,352 ambiguous source phrases need linguistic review even though their
enumeration is complete. The 80 bounded results are the manifest's
`unresolved_phrase_rows`; that count does not measure all linguistic uncertainty.
See [source audit](../docs/dictionary-source-audit.md) and
[readiness requirements](../docs/DICTIONARY_READINESS.md).

`essay-cantonese.txt` supplies existing text frequencies, never additional
entries. Omitted weights use the text's preset frequency; percentages multiply
it; explicit numbers are preserved. Missing frequencies are zero. Later duplicate
frequency keys win. All new supplemental pairs have zero weight, meaning
frequency unknown rather than nonoccurrence. Copying a whole-text frequency onto
each supplemental reading would assert a pronunciation share the source never
provided. Such counts are used separately for review priority only. Generated phrase readings
inherit the phrase's source-resolved weight. No new frequency measurements or
synthetic popularity counts are asserted.

The separate Rime `jyut6ping3.maps` data under ODbL and its lettered dictionary
are excluded. No Google or
cantoneseinput.com dictionary data is imported.

## SQLite contract

Schema version 2 adds `origin` to `entries`:

```text
id, text, reading, base_reading, compact, syllable_count, weight, source, origin
```

`origin` is `explicit`, `supplement` or `generated`. Toned readings and polyphony
are retained; derived fields remove tones and optionally spaces. `(text, reading)`
is unique. Explicit Rime readings win overlaps with supplements; duplicate Rime
pairs retain the maximum existing weight. IDs are deterministic for a fixed source
configuration: explicit/supplement entries are sorted, then generated entries
follow source/traversal order. Wordnet, complete CC-CEDICT headword encodings and
Yue Wiktionary rows then append in their recorded phases, preserving all IDs
from preceding phases.

`phrase_encodings(source,line,text,status,codes_json,path_count,work_count,reason)`
accounts for each text-only source row. `supplement_review` retains quarantines
and normalization metadata. `syllables(base)` is the observed inventory.
`metadata(key,value)` stores JSON build/provenance fields. Indexes support
base, compact, text and ledger queries. `semantic_sha256` hashes sorted live
entry content independently of physical SQLite layout.
`cccedict_headword_forms` and `cccedict_headword_encodings` retain the second
encoding pass. The `yue_wiktionary_pages`, `sections`, `fields` and `review`
tables preserve the complete source-accounting records for that export.

The parser validates finite nonnegative weights, UTF-8, reading syntax and source
shape. It does not execute YAML or support arbitrary Rime configuration. The
library API keeps automatic encoding and supplements opt-in for small fixtures;
the CLI enables both by default. `--no-autoencode` and `--no-supplements` are
diagnostic options, not the normal full build.

```python
from cantonese_ime.dictionary import build_dictionary, read_entries

# Direct callers can use small fixtures; the CLI verifies the real source locks.
stats = build_dictionary(source_directory, output_database)
entries = read_entries(dictionary_file, frequencies={"你好": 1000})
```
