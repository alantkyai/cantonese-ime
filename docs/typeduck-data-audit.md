# TypeDuck candidate dictionary audit

This is the preserved **pre-import comparison** against the `aec269` baseline.
After that comparison, the project selected the expressly CC BY 4.0 principal
data as a default additional source. The selected [source lock](../data/supplements/typeduck.sources.lock.json)
and [parser](../cantonese_ime/typeduck.py) retain all 155,509 canonical pairs,
quarantine the two marked emoji readings, assign unknown frequency zero, and
preserve earlier sources on overlaps. The current database adds 34,364
TypeDuck pairs over earlier authored sources. The isolated candidate report
below remains unchanged historical evidence; its baseline comparison counts
are not current post-import missing-entry counts. No independent human
linguistic approval or categorical ODbL-lineage exclusion is inferred.

The pinned TypeDuck table can supply useful **explicit source rows for 314 of
the baseline's 29,537 ambiguous phrase texts**, including a reading absent from
our generated alternatives for `返到`. It matches none of the 80 path-limited
phrases and none of the 14 LSHK components still lacking authored readings.
The source's principal-data license is expressly **CC BY 4.0**. The main
remaining distinction is between explicit rows in an exported dictionary and
independently established human-authored whole-phrase judgements.

The audit itself left the then-live database, review queues and engine unchanged.
Its isolated source snapshot and report remain retained alongside the later
selected-source snapshot.
The comparison uses database SHA-256
`aec269744279a5d85a9f5ca459b9a04f060ae53c29b975fd4aab132d90fab39d`.

## Pinned files and permission scope

The source is [TypeDuck-HK/schema commit
7f9d90d4185eca293576de5b5dddaaf1d265f3c9](https://github.com/TypeDuck-HK/schema/tree/7f9d90d4185eca293576de5b5dddaaf1d265f3c9),
dated 4 September 2026. Its principal table blob last changed in
[a956ac6f](https://github.com/TypeDuck-HK/schema/commit/a956ac6fb983e80ee48fc89b55dbd08b9f04e2c1),
whose description concerns missing proper-name variants. The later pinned
commit updates reverse lookup dictionaries, without changing this table.

The [pinned README](https://github.com/TypeDuck-HK/schema/blob/7f9d90d4185eca293576de5b5dddaaf1d265f3c9/README.md)
identifies `jyut6ping3.dict.yaml` and `essay.txt` as candidate entries and
frequencies. It separately identifies `jyut6ping3_scolar.dict.yaml` as the rich
dictionary used by a lookup filter for translations and other annotations.
Its license section covers the non-reverse-lookup principal dictionary/schema
under CC BY 4.0. The listed reverse lookup files retain their own LGPL, MIT or
CC BY terms and are excluded from this candidate snapshot.

Three unmodified files are retained under
[the isolated candidate directory](../data/vendor/candidates/typeduck-schema/7f9d90d4185eca293576de5b5dddaaf1d265f3c9):

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `jyut6ping3.dict.yaml` | 4,479,053 | `e54eab6a3ef4328e0803e65fe4320f088329d1f0496cf7b1576dc1d0d2e28a6b` |
| `README.md` | 3,896 | `6776d56c458a585df64b8175534a6a15b9ae244fe41f97f8e22e626d996f9495` |
| `LICENSE` | 18,657 | `9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411` |

The [candidate source lock](../data/candidates/typeduck.sources.lock.json)
also records exact URLs, Git blob hashes, date, attribution and exclusions.
The full CC BY license and original attribution declaration accompany the data.
Credit remains to TypeDuck-HK and TypeDuck contributors. Downloaded files are
unmodified; this project's comparison normalizes reading case/spacing in memory,
excludes unsupported marked readings and produces source-derived delta counts.
The candidate analysis and selection changes are this project's responsibility;
no TypeDuck endorsement is implied. Preserve the source declaration, full
license, attribution and change notice with redistributed derivatives.

No rich translation table, TypeDuck frequency file, reverse lookup data,
OpenCC binaries, runtime, frontend or installer was downloaded for this audit.
The current build does not discover/import the candidate directory.

## What the table physically encodes

After its small Rime header, all 155,511 data lines have three tab-separated
fields: text, supplied reading and percentage weight. There are no text-only
phrase lines, per-row source tags or source-section comments. The audit keeps
155,509 unique syntactically canonical text/reading pairs for 143,735 texts.
It excludes two emoji rows whose readings carry TypeDuck's `~` markers:
`🦆 ~daa2 ~dak1` and `🐧 ~tai1 ~dak1`. Their raw fields and line numbers remain
in the audit output; the marker is not stripped into an invented ordinary code.

All weights are percentages; 4,667 canonical rows have zero percent and the
largest value is 785.1%. They are source ranking values, not a probability
distribution or measured pronunciation frequency. They have not been assigned
to current entries, multiplied by our essay counts or used to change the
autoencoder's 5% eligibility. Zero-percent source rows are counted in the raw
delta, with their status retained, rather than hidden in a headline total.

## Exact comparison with the pre-import baseline

The [reproducible audit report](../data/candidates/typeduck.audit.json) compares
exact `(text, canonical toned reading)` pairs against the baseline's 157,455
source-authored and 576,125 live pairs. It does not call a generated match an
independent correctness check.

| Comparison | TypeDuck pairs |
| --- | ---: |
| Already in current source-authored entries | 121,145 |
| Absent from current source-authored entries | 34,364 |
| Already present anywhere in the live dictionary | 127,659 |
| Absent from the live dictionary | 27,850 |
| Entirely new text values versus the live dictionary | 22,229 texts |

Of the 27,850 new live pairs, 1,961 have single-codepoint text: 823 carry a
positive source percentage and 1,138 carry zero. The remaining 25,889 have
multiple-codepoint text: 25,837 positive and 52 zero. These counts do not
validate unusual readings or prove every entry is useful for intended typing.

| Current phrase status | Source phrase rows | Texts with TypeDuck rows | TypeDuck pairs | Same recorded code | Outside recorded codes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ambiguous | 29,537 | 314 | 324 | 293 | 31 |
| Path-limited | 80 | 0 | 0 | 0 | 0 |
| Mechanically unique | 300,694 | 6,751 | 6,905 | 6,222 | 683 |
| Already has an authored reading | 390 | 65 | 108 | 91 | 17 |

Two of the 324 candidate pairs for ambiguous texts have zero source percentage.
The report retains **all 314 matched ambiguous texts**, each current source
line/codes, each TypeDuck source line/raw reading/raw percentage, and existing
exact-text frequency solely for review priority. High-frequency examples are:

| Text | Existing text frequency | TypeDuck explicit row | Relation to current generated alternatives |
| --- | ---: | --- | --- |
| 返到 | 51,167 | `faan1 dou3`, `100.0%` | Outside `faan2 dou2` / `faan2 dou3`; substantive reading gap to review. |
| 先會 | 18,420 | `sin1 wui5`, `100.0%` | One of four current alternatives. |
| 邊到 | 7,919 | `bin1 dou3`, `100.0%` | One of two current alternatives. |
| 聽下 | 2,135 | `teng1 haa5`, `100.0%` | Outside the current generated alternatives. |

A TypeDuck reading outside our generated alternatives can reflect whole-word
context, changed tones, a source extension or a disagreement needing review.
It must not be silently discarded merely because character-based generation
did not produce it. Conversely, a single exported TypeDuck reading does not
prove other contextual readings should be deleted. No phrase status or preferred
reading has been changed by this audit.

## Generation history and the map-data boundary

The current README's principal-data CC BY 4.0 declaration is affirmative
permission evidence. **No evidence found here establishes that the current
monolithic table contains ODbL-derived rows.** Road names and place-name commit
descriptions alone would not establish that claim.

There is concrete historical evidence to retain, with a replacement boundary:

1. The [first commit, 5050489f](https://github.com/TypeDuck-HK/schema/commit/5050489faa3f059eb39f9eaa56f214a9440494bd),
   6 February 2023, included a separate
   [maps table](https://github.com/TypeDuck-HK/schema/blob/5050489faa3f059eb39f9eaa56f214a9440494bd/jyut6ping3.maps.dict.yaml)
   explicitly attributed to OpenStreetMap under ODbL. Its old 19-line main
   dictionary imported that table alongside Rime character/word/phrase tables.
2. [f5c375fc, “Original”](https://github.com/TypeDuck-HK/schema/commit/f5c375fca1dc272b8c76fda59521b2c65d59d291),
   9 June 2023, **removed** that main import file and the maps, phrase and words
   tables. This is not a present-day import declaration.
3. The immediately following
   [2b4030c1, “Cantoboard Schema”](https://github.com/TypeDuck-HK/schema/commit/2b4030c11cda311b9c664b4626f32407b5e22f11)
   added the replacement monolithic principal and SCOLAR files. The inspected
   commit/tree does not specify each new row's origin or demonstrate whether
   old map names were independently replaced, retained or regenerated.
4. [c9a464a6](https://github.com/TypeDuck-HK/schema/commit/c9a464a6c7155e72bfc5fdc7a471d35d94e4e166),
   16 November 2023, describes an update using a generation script, but changes
   only the two dictionary exports; its inspected recursive tree contains no
   such script. The [2026 lexicon overhaul](https://github.com/TypeDuck-HK/schema/commit/3e3a5a8b74cdd5396e71deee8ae495e57655b9ef)
   also updates dictionary exports without a row-origin manifest. The later
   [vocabulary/Macau-place-name update](https://github.com/TypeDuck-HK/schema/commit/5ba60165fdaac1beb8d8fddf9ffeb672317be164)
   is evidence of editing, not proof of a particular upstream data source.

The pinned
[reverse-update workflow](https://github.com/TypeDuck-HK/schema/blob/7f9d90d4185eca293576de5b5dddaaf1d265f3c9/.github/workflows/update-dictionaries.yml)
refreshes reverse lookup files only. The
[build workflow](https://github.com/TypeDuck-HK/schema/blob/7f9d90d4185eca293576de5b5dddaaf1d265f3c9/.github/workflows/build.yml)
compiles checked-in principal tables using a downloaded TypeDuck librime;
neither workflow supplies the principal text table's generation recipe.
Their floating runtime/reverse-source URLs are excluded from this data-only
snapshot. No workflow or executable was run locally.

The supported conclusion is therefore **known declared CC BY 4.0 principal
data, with residual row lineage and authorship uncertainty**, rather than an
unknown license or a confirmed ODbL-contamination finding. Maintainer
clarification or an exposed export/source manifest could resolve the historical
lineage question. The current declaration supports considering reuse; this
audit does not impose a blanket prohibition based on a hypothetical source.

Explicit exported readings also do not establish independent human authorship.
The history proves dictionary generation/export occurred, but does not prove
that these particular readings were Rime-autoencoded, manually authored, copied
from an editorial wordlist or contextually reviewed. No independent linguistic
quality result is claimed.

## Recommended next decision and reproduction

Use the 314 matched ambiguous texts as additional source evidence for human
whole-phrase review, prioritizing the 31 readings outside our generated sets
and the high-frequency disagreements. Keep source percentages and line numbers
visible. A later import decision can explicitly choose the permitted principal
data scope and retain its separate provenance without overriding existing
authored readings or inventing frequencies. TypeDuck does not close the 80-row
enumeration gap or the 14-character description-only gap in this snapshot.

Reproduce the comparison offline from the project root:

```powershell
python tools/audit_typeduck_candidate.py --database .local/frozen-aec269/lexicon.sqlite3 --output data/candidates/typeduck.audit-reproduced.json
```

The [audit tool](../tools/audit_typeduck_candidate.py) verifies all three locked
file sizes, SHA-256 and Git blob hashes, opens SQLite read-only, preserves
excluded raw rows, and records its own code hash plus database/source hashes.
It writes only an isolated candidate report and refuses to overwrite a differing
existing audit snapshot. The original review pack remains
the frozen 1,055 pending records; data/review-v2 is a separate later snapshot.
No reviewer claims or source-derived rows
are relabelled as independent held-out data.
