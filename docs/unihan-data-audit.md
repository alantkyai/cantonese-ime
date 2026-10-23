# Unihan kCantonese candidate audit

The official Unicode 18.0.0 `kCantonese` snapshot is a relevant **candidate character supplement**: it supplies direct readings for 11 of the 14 currently unread component characters and 2,899 character/reading pairs absent from the frozen lexicon. It supplies no authored whole-word readings for the 80 path-limited phrases. Nothing from this candidate has been added to the selected dictionary or spelling maps.

The comparison baseline is `data/generated/lexicon.sqlite3`, SHA-256 `aec269744279a5d85a9f5ca459b9a04f060ae53c29b975fd4aab132d90fab39d`, with 576,125 pairs, 873 tone-free bases and 2,950 observed toned forms. This is an exact textual data comparison, not human pronunciation validation or an accuracy evaluation.

## Official source, version and license

The [versioned UCD ReadMe](https://www.unicode.org/Public/18.0.0/ucd/ReadMe.txt) explicitly identifies final Unicode 18.0.0 data; the [latest UCD ReadMe](https://www.unicode.org/Public/UCD/latest/ReadMe.txt) points to the same version at retrieval on 22 October 2026. The retained readings header identifies Unicode 18.0.0 and data date 31 July 2026. [UAX #38 revision 41](https://www.unicode.org/reports/tr38/tr38-41.html) is the stable documentation for this release. The version landing page still carries draft boilerplate, so the final-data ReadMe, versioned archive and stable annex are the version evidence used here.

The retained archive is [the official versioned Unihan.zip](https://www.unicode.org/Public/18.0.0/ucd/Unihan.zip), 8,340,649 bytes, SHA-256 `4c93ea9c1f636451729a840978f1667a53886af37ba854fdcce109721c63d43e`. Its eight members are fingerprinted in the candidate lock. The extracted `Unihan_Readings.txt` is verified byte-for-byte against the archive member.

The [Unicode License V3](https://www.unicode.org/license.txt), SPDX `Unicode-3.0`, permits using, modifying and distributing covered data, including commercial distribution, provided the copyright and permission notice accompanies the copies or associated documentation. The exact notice is retained as `LICENSE.txt` with SHA-256 `e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96`. That license URL is mutable; its retrieved bytes are pinned separately. Unicode distinguishes licensed data/software from its publications, glyphs and fonts in its [licensing policy](https://www.unicode.org/policies/licensing_policy.html). This audit does not retain or redistribute code-chart glyphs or fonts.

## What the property establishes

[UAX #38's kCantonese definition](https://www.unicode.org/reports/tr38/tr38-41.html#kCantonese) classifies it as **Provisional**, with ASCII lower-case Jyutping and tone digits 1–6. It describes a customary reading intended for CLDR collation and transliteration; stability requirements mean that a value can differ from a dictionary's preferred pronunciation. The annex also explains that pronunciation varies by region, word and context. Consequently, this is source attestation, not a normative Cantonese pronunciation decision or a complete alternative-reading inventory.

The snapshot contains 29,936 code points, each with one `kCantonese` reading: 29,936 unique pairs, 659 bases and 1,869 toned forms. Every value passes the published property syntax. This only validates its format. No reading was inherited through character variants or compatibility mappings, and no descriptive label was converted to a pronunciation.

## Exact delta

| Comparison | Count |
| --- | ---: |
| Candidate pairs already present in the baseline | 27,037 |
| Candidate pairs absent from the baseline | 2,899 |
| New character texts | 2,789 |
| New readings of already represented character texts | 110 |
| New tone-free forms relative to the selected inventory | 4 |
| New toned forms relative to the selected inventory | 14 |

The baseline has 42,677 single-character pairs, all with `explicit` or `supplement` origin. Thus the new-pair delta against source-authored baseline pairs and against the whole generated database is identical. The 110 differences are additional claims requiring comparison; they are not automatically corrections to the current readings. Some characters already have multi-syllable unit readings: for example, Unihan's `䇆 sap6` differs from the retained `sap6 sing1`.

The four new forms all fit the onset/final component inventory shown in the [official LSHK scheme](https://lshk.org/jyutping-scheme/):

| Form | Source reading | Source code point | Onset | Final | Scheme component shape |
| --- | --- | --- | --- | --- | --- |
| `bap` | `bap6` | U+2BAC8 | `b` | `ap` | compatible |
| `dun` | `dun1` | U+204CE | `d` | `un` | compatible |
| `eot` | `eot1` | U+20C32 | zero | `eot` | compatible |
| `kwaat` | `kwaat1` | U+21078 | `kw` | `aat` | compatible |

This component check is not a complete phonotactic validator. All four remain flagged `new_to_selected_inventory` and `provisional_source_property`; absence from the current dictionary or LSHK observed-character table does not prove invalidity. The candidate has not expanded the shipped identity or forgiving-alias maps.

The 14 new toned forms are `aap6 bap6 caa6 dun1 eot1 ju4 kek3 koeng6 kui1 kwaat1 meng5 nip3 paang6 zeot6`.

## The 14 component gaps

These are direct `kCantonese` values attached to the actual code point, independent of LSHK's `DESC_JP` descriptions. They establish a useful candidate source for review, while the property remains provisional.

| Character | Code point | Candidate reading |
| --- | --- | --- |
| 乄 | U+4E44 | `ngau1` |
| 乊 | U+4E4A | `fu4` |
| 乛 | U+4E5B | `waang4` |
| 纟 | U+7E9F | `mik6` |
| 罓 | U+7F53 | no `kCantonese` value |
| 肀 | U+8080 | no `kCantonese` value |
| 覀 | U+8980 | `sai1` |
| 讠 | U+8BA0 | `jin4` |
| 钅 | U+9485 | `gam1` |
| 阝 | U+961D | `fau6` |
| 饣 | U+9963 | `sik6` |
| 𠃍 | U+200CD | `waang4` |
| 𠃑 | U+200D1 | `saam1` |
| 𧘇 | U+27607 | no `kCantonese` value |

The other three gaps remain uncovered by this property. There is no automatic inference from a related character. None of these 14 characters blocks an existing phrase in the encoding ledger.

## Phrase limitations and possible selection policy

There are zero exact whole-word matches between this single-character property and the 80 quarantined path-limited phrases. Those cases already have character encodings; their problem is enumeration limits and context-dependent choices. Adding character readings does not establish a preferred phrase reading and can increase the number of possible combinations. This candidate likewise supplies no phrase frequencies.

If the source is selected later, a narrow integration would add missing direct pairs under a distinct `unihan:kCantonese` provenance, retain the Unicode version and provisional status, assign **unknown weight 0**, preserve existing pairs and weights, and retain the notice. The 110 additional reading claims and four inventory additions should remain individually reviewable. This recommendation does not authorize overriding current pronunciations, propagating variants, inferring word readings, or treating the source as exhaustive.

## Retained evidence and reproduction

- Candidate source lock: [unihan.sources.lock.json](../data/candidates/unihan.sources.lock.json).
- Official archive, extracted readings, ReadMe and notice: [candidate vendor directory](../data/candidates/vendor/unihan/18.0.0/).
- Complete 2,899-pair delta with code points and source line numbers: [new-pairs.tsv](../data/candidates/vendor/unihan/18.0.0/new-pairs.tsv).
- Machine-readable counts, all 14 gap comparisons, new-form classifications and member hashes: [audit.summary.json](../data/candidates/vendor/unihan/18.0.0/audit.summary.json).
- Offline stdlib comparison: `python data/candidates/vendor/unihan/18.0.0/audit.py --database PATH_TO_ORIGINAL_BASELINE`. It requires the original `aec269…` baseline and checks that its hash did not change during the comparison. It refuses to overwrite this candidate comparison using a later expanded dictionary. The project-authored audit script is separate from the upstream Unicode files.

The default source locks, dictionary, mappings and evaluation corpus remain unchanged by this audit.
