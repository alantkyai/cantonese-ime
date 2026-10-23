# Cantonese Wordnet vocabulary candidate

A separate candidate dictionary was built at
`.local/wordnet-candidate/lexicon.sqlite3`, SHA-256
`99f7fd4ec29692e5afe3a90a1ab7cd0d302937afbefa1d03b783958ff21dbdb2`.
It contains **739,128 text/reading pairs across 623,223 texts**. This is an
append-only extension of the frozen `3fccc5bc…` dictionary, adding **2,558 pairs
and 1,978 texts**. All 736,570 earlier pairs were compared field by field,
including weights and sources, and remain unchanged. This candidate does not
replace an installed dictionary or the earlier staged native package. The
append-only candidate itself is not a fresh full-source rebuild or a claim of
linguistic approval; the later clean builds and development publication are
described below.

The [candidate manifest](../.local/wordnet-candidate/lexicon.manifest.json) records
source, parser and builder hashes, exact additions and accounting. Its
[review ledger](../.local/wordnet-candidate/lexicon.review.json) retains 11,907
source-located records: blank readings, quarantines, normalization events and
the excluded English forms. Earlier full-build metadata is preserved in a
namespaced baseline snapshot rather than presented as current candidate counts.
No phrase re-encoding or inferred readings are performed.

The [source lock](../data/supplements/wordnet.sources.lock.json) pins Cantonese
Wordnet commit `6434cbc1d692d3061266352aa223a8df4a9c883e`. The exact `cantown-yue`
lexicon has 11,667 entries and 23,733 forms: 11,660 empty and 12,073 nonempty.
The five English entries and their empty forms are separately excluded.
Case/whitespace normalization admits 11,851 valid form occurrences, which
deduplicate to **10,775 explicit pairs**. Of these, 8,217 already exist in the
baseline and 2,558 are new. Twenty double-space readings receive explicit
normalization records; no pronunciation, tone or concatenated-syllable repair is
made. The earlier research's 10,757-pair count used a stricter single-space
grammar and remains preliminary evidence for that earlier boundary.

The 222 nonempty quarantines comprise 97 syntax, 38 unknown-base, 86 alignment
and one non-Han form. Unknown-base exclusion is against a frozen 878-base
inventory; it is not a finding that those pronunciations are linguistically
invalid. Known XML transliteration tags are counted but do not supply readings.
Definitions, relations and readings from other entries are never joined into
lookup pairs. New pairs retain weight zero as frequency unknown and do not
feed the phrase encoder.

The [parser](../cantonese_ime/wordnet.py) passes 14 focused tests. The separate
[candidate builder](../tools/build_wordnet_candidate.py) passes four tests for
preservation, zero weights, duplicate/unknown-base rejection, stale baselines
and source-change publication refusal. The
[candidate lookup checker](../tools/check_wordnet_candidate.py) passes two tests
that require existing competing texts and exact cohort accounting.
These are additional tooling checks; the staged product's 354-test result
remains tied to its recorded implementation.

Actual candidate lookup verification **passes all 2,497 affected input groups**:
5,491 required input/text memberships were reached through 2,509 public page
calls. It uses the public
`Engine.lookup_page` API for every newly introduced compact Yale input, requiring
all stored texts at each affected input, including earlier homophones. Its
output is [the candidate Yale report](wordnet-candidate-yale.json). This cohort check does not claim
complete lookup verification of the entire candidate catalog. The separate
[full baseline catalog audit](YALE_CATALOG_AUDIT.md) passed against
the unchanged `3fccc5bc…` database: every required stored text was reached at
all 488,219 compact input groups, representing 736,570 source pairs. That
exhaustive result belongs to the baseline; the expanded dataset's affected
cohort remains a separate check.

The source's unmodified XML, README, complete CC BY 4.0 terms and attribution
are retained in `data/vendor/cantonese-wordnet/6434cbc…`. Preserve the
[authors' citation and attribution](../data/vendor/cantonese-wordnet/6434cbc1d692d3061266352aa223a8df4a9c883e/ATTRIBUTION.md),
[component notice](../data/THIRD_PARTY_NOTICES.md) and
[combined adaptation license](../data/DATA_LICENSE.md) when sharing candidate
data. Application code is separate. The source is not an independent held-out
evaluation corpus and does not establish all-Chinese vocabulary completeness.

The default builder now selects Wordnet and appends its entries after phrase
generation. Two separate clean builds from the pinned sources produced the
same database bytes, SHA-256
`d835b8c4487b90ef751c8c91f467b9245c8bd54ee5be8157531dd9530ac7667b`.
The [complete comparison](wordnet-dictionary-comparison.json) confirms that
all 736,570 baseline entry IDs and fields, all 3,613 earlier review records and
all 330,701 phrase-generation ledger rows are unchanged. The canonical build's
739,128 entry rows also match the candidate field for field. The clean builds
remain separate artifacts in `.local/wordnet-canonical` and
`.local/wordnet-rebuild`. Their byte-identical database, manifest and audited
mapping artifacts were [published to the development defaults](wordnet-development-publication.json).

The [independent source audit](wordnet-source-audit.json) passes against the
canonical build: all 10,775 accepted pairs and all 11,907 required review events
are present, with no missing or unexpected events. Its 13 focused tests cover
false provenance credit and source-lock changes as well as source/ledger
accounting. Only valid newly inserted Wordnet rows receive Wordnet provenance;
earlier-source overlaps retain their earlier auditors' responsibility.

The [combined audit](wordnet-dictionary-audit.json) passes all ten mechanical
gates, including provenance for all 739,128 entries, mapping coverage and the
independent rebuild comparison. The three human quality gates remain incomplete.
All alias/rule/Yale records are [unchanged](wordnet-mapping-comparison.json).
The final canonical build [passes every affected input group](wordnet-canonical-yale.json),
and [all reading routes plus 400 samples](wordnet-yale-coverage.json).

The [current staged package](wordnet-ime-validation.json), manifest `cf81a6a8…`,
contains 69 hash-verified payload files. All 15 production x64 IPC cases pass,
including added vocabulary, strict-mode boundaries and long incremental input.
The maximum observed request is 189.1874 ms against a 250 ms client deadline;
this finite run is not a universal latency guarantee. A fresh x64 process also
loads the DLL and resolves its exports. The isolated broker used no learning
store and was stopped afterward. No keyboard/UI actions or new installed TSF
typing test were performed.

Installation awaits the user's readiness to retry the earlier canceled UAC
prompt. The older Yale-preferred package remains separately identified in
[its staged validation](yale-ime-validation.json); the installed numbered-choice
package is unchanged.
