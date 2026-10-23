# CC-Canto lexical expansion audit

The selected official CC-Canto 2017-02-02 and CC-CEDICT Cantonese Readings
2015-09-23 snapshots contribute **213,321 distinct admitted Cantonese text/reading
pairs** before overlap removal. Against the preserved `4353328c…` database
(607,026 pairs, 495,321 texts), their union adds **129,609 pairs and 125,924
texts**. These are source-derived lexical coverage counts, not independent
pronunciation accuracy or a claim of all Chinese words.

| Source | Physical data rows | Admitted distinct pairs | New pairs versus baseline | Fully quarantined rows |
| --- | ---: | ---: | ---: | ---: |
| CC-Canto | 34,335 | 50,274 | 22,626 | 362 |
| CC-CEDICT Cantonese Readings | 105,862 | 171,145 | 108,376 | 450 |

The two new-pair columns overlap, so they must not be summed into the union.
Traditional and simplified headwords are both explicitly present in each source
row. The admitted traditional-field pairs add 7,745 and 43,072 pairs respectively;
the simplified-field values add 17,990 and 79,555. Some forms occur in both fields.
No OpenCC conversion or variant inference supplies additional text forms.

The [official download page](https://www.cc-canto.org/download.html) declares
the two datasets CC BY-SA 3.0 and identifies brace fields as Jyutping after
bracketed Pinyin. The [about page](https://www.cc-canto.org/about.html) describes
human editorial work and checked Cantonese readings, while acknowledging beta
quality and lexical noise. This is useful lexical evidence, not independent
human approval of our resulting database. Original headers, pages, archives,
extracted member bytes and full licenses are retained in the
[source lock](../data/supplements/cccanto.sources.lock.json).

The importer accepts only explicit brace-delimited canonical toned readings.
Bracketed Mandarin, definitions and unrelated source fields never become lookup
codes. It normalizes reading case/spacing, retains original text/tone digits,
requires one codepoint per syllable for each distinct headword form, removes
duplicate pairs, and gives every new pair unknown frequency weight zero. Earlier
source pairs and their weights remain unchanged.

Additional CC-Canto character readings are retained for direct lookup and are
excluded from Rime's mechanical phrase translation pool, alongside provisional
Unihan character readings. This prevents unmeasured zero-weight alternatives
from widening unrelated phrase pronunciations. Accepted explicit CC-Canto
whole-word readings remain live; they use the existing `already_explicit` policy
rather than combining them with unreviewed mechanical alternatives.

Fourteen newly encountered bases—`es fim moi om p r seo w wa yat ye yo yuk yut`—
are quarantined against the frozen 878-base parser admission inventory. That
inventory is explicitly marked project-generated validation metadata, with its
baseline database hash. Absence is not a declaration of linguistic invalidity.
We do not change `yat` into `jat`, pronounce foreign letters automatically, strip
punctuation, repair tone notation, or infer missing syllables. Examples requiring
review include `成日 {seng4 yat6}`, the foreign-letter notation in `夠ｐｏｗｅｒ`,
a malformed brace in `陳慧琳`, and one-character/multiple-syllable `瓩 {cin1 ngaa5}`.
The last example can be a genuine compound character; alignment quarantine is a
software admission policy rather than a finding that its reading is wrong.

All exceptions are accounted for in **891 review records**: 437 from CC-Canto and
454 from the separate readings file. A rejected source row produces one record;
an unaligned traditional or simplified form produces its own record, including
within a partly accepted row. The ledger retains source, physical line, raw
pronunciation, reason, scope, raw prefix and full-line hash. Definitions remain
only in the unmodified vendor source. No record is automatically approved or
repaired. See the [full ledger](../data/review-cccanto/source_exceptions.json) and
[accounting/provenance report](cccanto-data-audit.json).

CC BY-SA 3.0 legal-code [section 4(b)(ii)](https://creativecommons.org/licenses/by-sa/3.0/legalcode.en#s4b)
expressly permits adaptations under a later version with the same license
elements. This project's combined transformed data adaptation is offered under
**CC BY-SA 4.0**, with original component licenses, attribution and change notices
retained. This does not assign that data license to independent program code.
The [data notice](../data/DATA_LICENSE.md) and
[third-party notices](../data/THIRD_PARTY_NOTICES.md) accompany redistribution.

The current Rime and CanCLID upstream API heads were rechecked and match the
already retained revisions `259f0e48…` and `4cb67a48…`; refreshing them adds no
new source words. CantoDict's own copyright notice does not offer a public-domain
or equivalent bulk reuse grant, so it was excluded. HKCanCor evaluation material
was not imported. Current coverage remains bounded by the named source editions,
review exceptions and the open-ended nature of names, terminology and new words.

`python tools/audit_cccanto_source.py --database <preserved-baseline>` reproduces
the source admission/overlap report without modifying a dictionary. The saved
JSON pins the baseline, source lock, parser and audit tool. Running against a
later expanded database measures a different overlap and must be identified as
such; it does not replace this historical baseline result.

## Expansion safeguard

The first expanded build (`ea62ca78…`) admitted CC-Canto single-character
readings to phrase autoencoding. A full comparison with the preserved baseline
found 115 removed old generated pairs and two missing texts. The two texts,
`嗱嗱啉` and `無嗱嗱多噠疤`, each previously had 25 complete mechanical readings.
Two added zero-weight readings of `嗱`, `naa2` and `naa5`, expanded its five
eligible codes to seven. The repeated character then produced 49 combinations,
so the conservative 32-path guard correctly quarantined both phrases and removed
their 50 old live codes. This was a data-policy regression rather than permission
to publish a partial subset of the enlarged encoding space.

The builder now keeps both CC-Canto source IDs out of the phrase translation
pool while retaining their direct character and explicit word lookup. The
regression fixture independently demonstrates a 32-path overflow if unknown
zero-weight character alternatives are mixed, and verifies that both source
kinds preserve original phrase generation and explicit whole words under the
new policy. The main build must verify restoration of the two texts and no
increase in the original path-limit quarantine.

The remaining 65 removed old pairs concern 33 texts newly supplied with authored
whole-word readings, so they did not lose word coverage. For example, `唔使多謝`
retains explicit `m4 sai2 do1 ze6` instead of the old mechanically generated
`m4 si2 do1 ze6`; `喺呢度` retains explicit `hai2 ni1 dou6` instead of generated
`hai2 ne1 dou6`. This records the source/derivation distinction; it does not
declare every source choice correct or every old alternative wrong. All 115
pre-safeguard removed pairs, retained alternatives, ledgers, changed-character
evidence and exact database hashes are preserved in the
[pre-policy diff](cccanto-pre-policy-diff.json).
