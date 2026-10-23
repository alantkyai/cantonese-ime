# Remaining dictionary review work

Read-only analysis of the schema2 database built on 22 October 2026, Hong Kong
time. Analyzed database SHA-256:
`4353328cb17f8c8f8cc5d78730e34c3aa26c6c8ea7d1a4f4a8f91fee5d900a6e`.
The counts below apply to this snapshot. Newly added supplementary reading
weights remain zero because their sources supply no pronunciation frequencies;
zero is an unknown-frequency sentinel, not a measured absence of use.

## Full phrase accounting and linguistic ambiguity

Every one of the 330,701 source phrase rows has a ledger record:

| Status | Phrase rows | Meaning |
| --- | ---: | --- |
| `already_explicit` | 7,455 | An explicit whole-word reading exists in the imported source data. |
| `encoded_unique` | 293,807 | The compatible mechanical encoder found one complete code. |
| `encoded_ambiguous` | 29,359 | Multiple complete codes were retained; the right pronunciation is not selected by this process. |
| `truncated` | 80 | Rime's 32-complete-path cap was reached; none of these has been imported as a complete reading set. |
| `unencodable` | 0 | No phrase lacks a complete translation path. |
| `too_long` or work-limit failure | 0 | Neither guard blocked this snapshot. |

The initial missing-character coverage problem has been removed for this phrase
list. Every Chinese character appearing in it has a qualifying translation.
Only the individual Latin letters `g`, `i`, `p`, `r`, `s` lack standalone
translations; known multi-character loanword tokens provide complete paths for
the phrases containing them. There is no evidence-based reason to fabricate
pronunciations for those isolated letters.

Full mechanical accounting does **not** mean that all 293,807 unique codes are
linguistically correct. Changed tones, names, and polyphonic context still need
authored phrase-level evidence. At least **29,359 explicitly ambiguous phrases**
remain a separate linguistic review population. The build metadata field
`unresolved_phrase_rows=80` measures enumeration failures only and must not be
presented as the total number of pronunciation decisions still requiring review.

The ambiguous cases are often small sets: 12,395 phrases have two paths, 4,032
have three, 3,729 have four, and 7,215 have five. High-frequency examples make
the distinction practical:

| Source text | Existing text frequency | Reached alternatives, abbreviated |
| --- | ---: | --- |
| 麥當奴 | 15,483 | `mak6 dong1 nou4`, `mak6 dong3 nou4` |
| 阿詩 | 13,703 | `aa3 si1`, `o1 si1` |
| 嚟到 | 12,369 | `lai4 dou2`, `lai4 dou3` |
| 阿龍 | 12,369 | `aa3 lung4`, `o1 lung4` |

These alternatives are products of source character readings and the published
5%-of-total threshold. They are not claims that every combination is natural in
the displayed phrase. Whole-text counts cannot be copied independently onto
new supplement pronunciations: that would invent reading-frequency evidence
and distort the threshold. Supplementary `住 zi6` and `唔 m6` remain authored
dictionary entries with unknown frequency, while existing positive Rime weights
govern their token's autoencoder eligibility. The corrected weight policy
reduces mechanical ambiguity; that reduction is not human linguistic review.

TypeDuck contributes explicit whole-word rows such as `返到 faan1 dou3` and
`先會 sin1 wui5`; these texts now use source-explicit entries rather than our
character-derived alternatives. An explicit exported row is not independent
proof of human contextual review. Unihan's provisional character readings are
retained for direct lookup and explicitly excluded from phrase translation.
The recorded policy preserves that boundary in both build and review derivation.

## The 80 path-limit cases

A separate finite dynamic-programming count of all successful paths over the
same 191,819 phrase-eligible source-explicit entries found (excluding Unihan):

- **7 phrases have exactly 32 paths.** The conservative encoder marks them
  truncated because it stops when it emits path 32, even when no further path
  exists. Their sets are mechanically complete but remain ambiguous.
- **73 phrases have more than 32 paths.** Their recorded sets are incomplete.
- The largest complete path count is **125**. No work-limit failure occurred.

The current 32-path conservative policy is intentionally retained. Reclassifying
the exactly 32 cases would be an accounting refinement, not linguistic resolution.
Increasing the cap or arbitrarily choosing the first path would not solve the
pronunciation problem or establish parity with Rime's published output cap.

Qualifying polyphonic characters appearing in truncated phrases include `行`
in 63 texts, `上` in 14, `咯` in 12, `咪` in 11 and `會` in 7. Examples include
bank branch names with repeated `行` and longer colloquial sentences. The
`一行一行噉數` source text has 75 paths; `中國銀行澳門分行下環支行` has 125.

None of these 80 texts has a positive frequency in the preset table. A useful
review queue should still include proper names and common colloquial patterns,
rather than treating a missing frequency as proof that a phrase is unimportant.

## Supplement review rows

The 2,722 supplement review records do not all represent excluded or defective
data:

| Source/status | Rows | Disposition |
| --- | ---: | --- |
| words.hk `normalized_variant` | 2,225 | Accepted readings with the documented trailing `*` removed; raw text and variant flag retained. This is resolved source-format metadata. |
| words.hk non-Jyutping notation | 282 | Every row contains `!` notation for English or other non-Jyutping phonetics. Kept intact in quarantine. |
| words.hk template text | 101 | Ellipsis/slot expressions such as `⋯事小⋯事大`; cannot be committed as an ordinary filled-in word without a template feature. |
| LSHK `description_only` | 112 | `JP` is empty. `DESC_JP` pronounces a descriptive label, not necessarily the character itself. |
| TypeDuck phonetic annotation | 2 | Tilde-marked emoji readings remain intact with physical source line and raw percentage; markers are not stripped into ordinary Jyutping. |

The 282 `!` readings are not a parser accident or a missing-tone normalization.
Examples such as `!zhi1`, `!es1` and a lone `!` require a separately defined
mixed-phonetic input policy. Removing `!` would invent canonical Jyutping
readings. The 101 templates likewise remain distinct from ordinary entries.

Of the 112 LSHK description-only character texts, 109 now have separate explicit
readings from imported sources. The selected Unihan property supplies readings
for 11 formerly uncovered components, including `乄 ngau1`, `纟 mik6` and
`阝 fau6`. Their property is provisional and intended primarily for
collation/transliteration; these additions support direct character lookup,
not inferred whole-phrase pronunciations. They do not turn the LSHK descriptions
into character readings.

Three components still have no imported explicit reading: `罓 肀 𧘇`.
None blocks a phrase in the current ledger. Their readings are not guessed.

## Changes justified by this analysis

No parser or autoencoder mutation is warranted to make the unresolved counts
smaller. Source flags, non-Jyutping phonetics, descriptive labels, word templates
and linguistic polyphony are different categories and are retained separately.

Next work should prioritize authored phrase-level readings for frequent
ambiguous expressions, an explicit policy for presenting alternate readings,
and review of person/place names. Source-derived decoder smoke tests can check
that stored readings are reachable by the engine. They cannot replace a
held-out linguistic evaluation or establish that these generated readings are
correct.

## Concrete human review queues

[data/review-v2](../data/review-v2/README.md) contains a source-derived queue, not an
independent held-out corpus. Its 200 ambiguous phrases include 100 selected by
exact-text frequency, 25 additional colloquial-marker rows, 25 additional
name/institution-marker rows, and 50 selected for polyphonic-character diversity
before frequency. Together they cover 82 of the 103 qualifying polyphonic
characters found in the 29,359-row ambiguous population. Those marker tags are
sampling heuristics, not authoritative linguistic classifications.

Separate tables retain every one of the 80 path-limited phrases, all 497
unresolved source exceptions, and all 282 spellings that map to multiple
canonical bases. All 1,059 review records start pending with blank proposals,
reviewer identities and evidence. Codes, source rows, derivations, input hashes
and policy provenance remain generated fields. No preferred phrase reading or
approval has been invented.

The [review tool](../tools/build_review_pack.py) freshly derives immutable
columns during validation, rather than trusting only an editable local manifest.
It refuses regeneration over reviewer edits and requires a new nonexistent
output directory for a new snapshot. A self-reported `confirmed` record is
explicitly unauthenticated; the project owner must separately verify trusted
human decisions about the exact snapshot before applying them. This pack does
not make the dictionary ready for release.

The original [v1 pack](../data/review/README.md) remains a separate frozen
1,055-record baseline. Its preserved database and mappings are under
`.local/frozen-aec269`. The upgraded validator maps known legacy input keys to
logical roles, verifies the preserved data and freshly derives generated fields,
and reports its current hash separately from the original generator hash.
It never rewrites that pack or reads arbitrary paths from a manifest.

## Source-derived decoder reachability smoke

[check_dictionary_lookup.py](../tools/check_dictionary_lookup.py) selects the
lowest SHA-256 values within explicit/supplement/generated strata. The saved
[corpus](../eval/source_coverage_cases.json) contains 500 stored entries, tested
with their fully toned compact readings in strict mode; every fifth entry is
also tested without tones, for 600 requests. This is a database-derived oracle
test, **not an independent held-out pronunciation or user-accuracy evaluation**.

The current [lookup coverage report](dictionary-lookup-coverage.json) uses the
database hash above and engine SHA-256
`1dd3e62086d4c8491f3c7e4b81b50886dab3607878777b17269d4a90a9f25115`.
The corpus hash is
`8d9b2e765119d24a14a1ae6c7067d50b3faec08fd7a8d7d74e59770158c0118b`.
Mapping/check-tool hashes and Python/platform details are also recorded. The
tool rejects a run if its database, corpus or relevant sources change during it.

| Origin, fully toned | Cases | Top 1 | Top 9 | Top 90 |
| --- | ---: | ---: | ---: | ---: |
| Explicit Rime | 200 | 137 | 170 | 200 |
| Supplemental source-explicit readings | 100 | 69 | 82 | 100 |
| Generated readings | 200 | 195 | 200 | 200 |

Including the 100 tone-free checks, 474 of 600 targets ranked first, 538 appeared
in the first 9 and 597 in the first 90. There were no exceptions or candidate
tone/reading constraint violations in the final run. Fully toned targets require
both the expected text and exact stored reading; tone-free targets permit that
text's other readings. Completion candidates may append syllables but must
respect the requested fully toned prefix.

Numeric tones close supported full syllable spellings, so `ngo5` cannot be
split into an untoned `ng` and a toned `o5`. Explicit boundaries and partially
toned multi-syllable inputs retain separate grammar tests. The constraint
checks here verify returned reading prefixes and full raw-input consumption;
they do not validate a phrase's linguistic pronunciation.

All three sampled first-90 misses are explained by their positions outside the initial
publication page, with SQL oracle diagnostics retained. Public pagination now
retrieves each one without changing the first-90 metrics:

| Target/query | Matching dictionary pairs | Frequency-ordered pair rank | Public candidate rank |
| --- | ---: | ---: | ---: |
| 賁, tone-free `fan` | 215 | 109 | 101 |
| 泥, tone-free `lei` | 264 | 177 | 162 |
| 𩔗, tone-free `leoi` | 273 | 255 | 216 |

Pair ranks differ from public ranks because the engine deduplicates displayed
text and also considers composition/completions. The checker additionally
replays the same five historically crowded targets as a separate deterministic
regression group, so they remain covered if later hash samples omit them.
All five were recovered there too. The 600 sampled scenarios therefore all
reached their stored targets through the initial page or later pages; this is
API reachability against its own database, not linguistic accuracy.

A further separate source regression group tests `返到 faan1 dou3` from
TypeDuck and all 11 newly covered component readings from provisional Unihan.
The phrase ranks first; the 11 components rank 10–75, all within the first 90.
These 12 source-derived scenarios carry source/provisional labels and preserve
the direct-character-only policy. They do not establish a preferred spoken
reading or independent linguistic quality. Across the 600 sampled, five
historically crowded and 12 selected-source scenarios, no exceptions or
candidate constraint failures were observed.

The page probes stop at a found target, exhaustion or an explicit
`PaginationCapacityError`, with a finite checker request guard. No capacity
error was encountered in this run because every target was found first.
These queries still advertised bounded prefix-completion tails; the engine
does not promise unlimited completion enumeration or unlimited sentence beams.

No quality threshold has been invented to convert first-90 misses into a pass.
The local run's median initial lookup was 3.629 ms and p95 was 18.456 ms, with a
173.015 ms maximum. Page probes are timed separately in the report; their
snapshot reuse does not represent cold-query latency. These measurements
describe this run, not guaranteed performance bounds.
