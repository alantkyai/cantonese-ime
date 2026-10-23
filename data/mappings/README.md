# Cantonese syllable and spelling mappings

`python tools/build_mappings.py` verifies the pinned source files and rebuilds
`syllables.json`, `spellings.json`, and `build.manifest.json` without a network
connection. Build the full dictionary first. The mapping build covers its
complete dictionary-schema-2 inventory and independently compares the original pinned Rime
explicit readings, LSHK's character table, accepted words.hk pronunciations,
the TypeDuck principal export, provisional Unihan `kCantonese` readings, and
selected CC-Canto/CC-CEDICT Cantonese readings. The current Yale/vocabulary
revision is development work; the installed numbered-candidate package remains
separate until a verified update.

`syllables.json` distinguishes attestation in LSHK's list, attestation in the
original Rime source, the accepted words.hk wordlist, TypeDuck, Unihan, the
full generated dictionary, and compatibility with the official onset/final spelling
shape. These are different facts. The union is not a complete enumeration of
every legal syllable, and an absent or unusual reading is not automatically
invalid or a loanword. Descriptive readings and the table's multi-syllable JP
rows are counted separately and never silently converted into single-syllable
character readings. The scheme includes the finals `a` and `oet` added in 2018.

`spellings.json` enumerates every identity and input spelling produced by
the versioned `cantonese-yale-ascii-v3` policy (schema 3). Each spelling/canonical pair retains a
cost, kind, rule ID, source references, and derivation. Different canonical
readings of the same spelling remain eligible. Tone digits 1–6 are retained
unchanged by the single-syllable resolution API; that does not claim every
base/tone combination is linguistically attested.

Strict `jyutping` mode enables identities only. Forgiving mode enables an
independent whole-syllable Yale ASCII conversion plus the existing bounded
conveniences. Legacy conveniences permit at most two operations and one onset
rewrite. In particular `zaa → jaa → yaa` is excluded, while `caa → chaa → cha`
is retained. Yale output is computed from the original syllable and never fed
back into those convenience rules. The former spurious `yyu/yyun/yyut`
alternatives are corrected to `yu/yun/yut`. Costs are project ranking choices,
not pronunciation probabilities. Existing spelling/canonical costs are retained;
new Yale aliases cost 0.45.
The development Engine separately defaults to `prefer_yale=True`: complete Yale
words containing a spelling change from canonical Jyutping receive first-class
word priority. Identity spellings keep the existing weighted merger ranking;
strict Jyutping is unchanged. `prefer_yale=False` disables the ranking preference,
and saved personal selections can still override the default order. Mapping
costs and this whole-word preference are separate policy layers.
Google's documented examples and the reference website provide evidence for
specific behaviours; they do not establish a complete conversion table or
grant access to their dictionaries. Sidney Lau is not implemented as a complete
scheme.

The Yale ASCII route covers the dictionary through its canonical readings,
rather than adding aliases for selected words. For ordinary syllables it uses
`z/c/j → j/ch/y`, open `aa → a`, `oe → eu`, `eoi/eon/eot → eui/eun/eut`, and
`oeng/oek → eung/euk`. Closed finals retain their long vowel: `caa → cha`,
`can → chan`, and `caan → chaan` are separate conversions. `yu/yun/yut` keep
their `y`; canonical `jyu/jyun/jyut` become `yu/yun/yut`, without a duplicate
`y`. `kw` remains `kw`, and syllabic `m/ng` are unchanged. Thus 火炬
`fo2 geoi6` has the tone-free route `fogeui`, 香港 `hoeng1 gong2` has
`heunggong`, and 先生 `sin1 saang1` has `sinsaang`. The existing `sinsang`
route is a relaxed-vowel convenience, rather than the formal Yale conversion.

The primary spelling references are the
[CPIME parallel tables](https://www.cpime.hk/p/pingyam-table.html) and
[EdUHK comparison chart](https://www.eduhk.hk/cle/resources/cep/cantonese-survival-package/Appendix%20I.html).
These are spelling facts used by independently authored code; the charts and
their example dictionaries are not redistributed. The
[PyCantonese 4.3.0 implementation documentation](https://docs.pycantonese.org/v4.3.0/_modules/pycantonese/jyutping/yale.html)
provides supplementary evidence for open `aa`, avoiding `yyu`, and the marginal
`eu → ew` extension. Its `kw → k` spelling is not adopted because the primary
comparison tables retain `kw`; CPIME's abbreviated `yu` final display is
resolved using EdUHK's explicit `yu/yun/yut` entries. No PyCantonese dependency
or source code is copied.

The v3 profile also accepts the literal numeric-Yale alternatives published by
[KFCD's pinned table](https://github.com/kfcd/pingyam/blob/d0ceb32c2da07d156db99e50b192aaf45236ca95/pingyambiu):
`deu/eu/meu/peu/seu/zeu` have additional routes
`deeu/eeu/meeu/peeu/seeu/jeeu`. Existing `dew/ew/mew/pew/sew/jew` routes remain.
These are whole-syllable aliases with source and rule metadata. The runtime
matches mixed primary/alternate word spellings against each stored reading
without generating exponentially many word aliases or changing the raw input
used for personal learning. Explicit apostrophes remain syllable boundaries.
Strict Jyutping mode and numeric tone filtering keep their separate paths.
The table also explicitly preserves literal `hm/hng`, including their lexical
`h`; those two routes are supplementary source-backed extensions. Its published
possible tones do not become authored word-frequency or pronunciation evidence.
The [source lock](kfcd.sources.lock.json), original notices and full CC BY 3.0
terms are retained. Build tools bind the selected aliases to that exact source.

Each `syllables.json` base has a `yale_ascii` route with `table`, `extension`, or
`jyutping_fallback` status, source IDs and an explanation. `spellings.json`
retains the complete route list, onset/final tables, and coverage counts.
`table` means its spelling components are covered by the reference tables;
it does not prove that every onset/final combination is a standard syllable.
Project extensions cover the marginal finals `a`, `em/en/ep/et`, `om/op`,
`um/up` with the same final spelling, `oet → eut`, and `eu → ew`. They use
the nucleus/coda convention described by PyCantonese and retain the normal
onset conversion: `cet → chet`, `jen → yen`, `za → ja`, `zop → jop`, and
`zoet → jeut`. These are explicitly classified typing extensions, rather than
assertions that the ordinary Yale chart covers these forms. Rare forms with no
such verified or declared route—including `ngm` and `soei`—keep
their canonical Jyutping spelling as an explicit fallback. Every observed dictionary
base therefore has a documented typing route, while these fallbacks are not
presented as verified formal Yale. `yale_ascii(base)` returns the route string;
`yale_ascii_mapping(base)` also exposes its classification and provenance.

This profile omits Yale diacritics and low-register tonal `h`. Optional ASCII
digits 1–6 remain exact tone filters on the dictionary's Jyutping readings;
they are not rewritten into Yale tone marks. The inverse resolver retains all
canonical readings for a shared spelling. Full Yale tone-mark/tonal-`h` input
requires a separate normalization layer.

The LSHK source snapshot is in
`../vendor/lshk-jyutping-table/dad2dd6d6f02fc51138ecc6818f7b38eba5c2ad3`
and is released under CC BY 4.0. Attribution: Dr Cheung Kwan Hin, Prof Lu Qin,
the Jyutping Workgroup of the Linguistic Society of Hong Kong, and Nathan
Hammond. `lshk.sources.lock.json` records exact source hashes. The derived
observed inventory retains this attribution and marks the extraction and
classification changes. Rime source attribution and license information are
embedded in each artifact's source metadata and retained with the original
source snapshot.

Schema 3 preserves the earlier source attestation before dictionary deduplication. A base
can therefore remain marked as observed in words.hk even when the retained
database row has a Rime source label. `rime_observed` means the original Rime
source; `dictionary_observed` means the full generated database. Per-source
observed tones and retained database source/origin labels are separate fields.
`inventory_delta` lists additions beyond the original Rime/LSHK union. The
words.hk snapshot and narrowly scoped public-domain declaration are recorded
under `data/supplements/wordshk.sources.lock.json`; definitions and other
non-wordlist datasets are excluded.

The selected TypeDuck principal table is declared CC BY 4.0; exported explicit
rows are source evidence, not a claim of independent human whole-phrase review.
The Unicode 18.0.0 Unihan snapshot is retained under Unicode License V3
(`Unicode-3.0`). Its `kCantonese` property is provisional and targets customary
character readings for CLDR collation/transliteration. Per-base
`provisional_source_attestations` preserves that status. These sources are
independently parsed before winner deduplication, even when another source owns
the retained database row. Source percentages and character fallback readings
do not establish word pronunciation frequencies. Their selected locks and full
notices are under `data/supplements` and `data/vendor`; candidate audits retain
their original pre-selection baseline separately.

The preserved pre-Yale five-source build had 878 observed bases and 2,977
source-observed toned forms, with 1,440 mapping records and 282 spelling
collisions under `cantonese-safe-v1`. Those counts and review decisions must not
be silently reused for this new spelling profile. The five
bases added beyond the prior 873-base inventory are TypeDuck's `boeng` and
Unihan's `bap`, `dun`, `eot`, `kwaat`. All fit the scheme's onset/final component
shape; this does not independently validate every phonotactic combination or
claim normative pronunciation. The Yale development profile retains all 878
bases with 778 `table`, 98 `extension`, and two `jyutping_fallback` routes.
The rebuilt artifact has 1,514 spelling relations and 298 retained collisions.
The [independent Yale report](../../docs/yale-coverage.json) checks every stored
pair's public route, expected spellings and sampled decoder retrieval. These
mechanical checks remain separate from human typing review.

The selected [CC-Canto lock](../supplements/cccanto.sources.lock.json) retains
original CC BY-SA 3.0 notices. Its source-derived admission boundary preserves
the existing 878 bases and quarantines 14 newly encountered forms rather than
silently adding or repairing them. Independent source attestations use
`cccanto_dictionary` and `cccanto_cedict_readings`; overlapping pairs do not lose
those attestations when an earlier source retains the database row. New
supplementary readings keep unknown-frequency weight zero. The combined
transformed dictionary uses [CC BY-SA 4.0](../DATA_LICENSE.md), retaining the
original component terms. This source expansion changes vocabulary coverage,
not the definition of formal Yale or a claim that every Chinese word is present.
The settled combined build contains 736,570 pairs across 621,245 texts, and an
independent clean rebuild matches its bytes. It adds 129,609 previously absent
pairs and 125,924 texts; 65 earlier generated alternatives are superseded by
explicit CC-Canto readings, with no earlier text lost. The 80 path-limited
encoding records remain quarantined. See the
[source coverage audit](../../docs/cccanto-data-audit.md) and
[Yale checker](../../tools/check_yale_coverage.py). The final full suite passes
354 tests, and the mechanical audit passes ten automated gates with three human
quality gates incomplete. The [staged validation](../../docs/yale-ime-validation.json)
records those checks. Installation remains pending after the Windows UAC request
was canceled; the previous installed version is running.

Primary references:

- [LSHK scheme](https://lshk.org/jyutping-scheme/)
- [LSHK maintained character table](https://github.com/lshk-org/jyutping-table)
- [TypeDuck pinned principal source](https://github.com/TypeDuck-HK/schema/tree/7f9d90d4185eca293576de5b5dddaaf1d265f3c9)
- [Unihan 18.0.0 archive](https://www.unicode.org/Public/18.0.0/ucd/Unihan.zip)
- [UAX #38 kCantonese property](https://www.unicode.org/reports/tr38/tr38-41.html#kCantonese)
- [Google Cantonese input examples](https://www.google.com/intl/ka/inputtools/services/features/input-method.html)
- [Online Cantonese input guide](https://www.cantoneseinput.com/)

The mapping inventory is auditable source coverage. Typing quality still needs
independent reviewed examples, ranking evaluation, and user trials; it is not
established by enumerating all records in the map.
