# Linguistic review pack

This is a source-derived work queue, not an independent held-out accuracy
corpus. No row is linguistically approved by generation. The engine and
dictionary builder do not read reviewer columns. The initial state is pending.

`phrases.tsv` contains 200 of 29,359 mechanically ambiguous phrase rows.
The selection takes 100 highest source-frequency rows, 25 additional rows
with colloquial markers, 25 with name/institution markers, then prioritizes
new polyphonic characters before frequency until reaching 200. The markers
are transparent sampling heuristics, not authoritative linguistic labels.
Frequency is the dictionary's existing exact-text essay weight, with zero
where no frequency is supplied; it is not a pronunciation confidence score.
This small queue does not cover all remaining ambiguous phrases.

`path_limited_phrases.tsv` contains all 80 conservative path-limit rows.
`codes_json` retains the original capped codes in emission order. A separate
dynamic-programming count describes all possible complete paths through the
same qualifying translations: 7 rows have exactly 32 paths and 73 have more
than 32. The dictionary still labels both groups truncated. Full path counts
are not necessarily distinct code counts, and codes beyond the original cap
are not silently added. Character alternatives explain mechanical ambiguity;
they do not establish which readings apply to a whole phrase.

`source_exceptions.tsv` contains all 497 unresolved source rows.

- `lshk:list.tsv` / `description_only`: 112.
- `typeduck:principal` / `quarantined`: 2.
- `words.hk:wordlist` / `quarantined`: 383.

Existing authored readings are shown separately when available. An LSHK radical
description is not a character pronunciation. Accepted words.hk trailing-star
variant records remain traceable in the database; they are resolved source-format
normalization, not this queue. TypeDuck phonetic annotations retain their raw
line/reading/percentage and are never silently rewritten into ordinary codes.

`spelling_collisions.tsv` contains all 282 input spellings mapping to multiple
canonical bases under cantonese-safe-v1. It retains derivations, policy rules,
costs and target attestations. An identity and an alias can collide; a proposed
policy must consider all canonical targets and both input modes. Numeric
tones remain unchanged. Source documentation supports individual mappings,
not a claim of full Google/Yale/Sidney Lau compatibility.

## How to review and return records

Import TSV as UTF-8 text, preserving Unicode, IDs, JSON cells and tone digits.
Only edit columns listed in each manifest table's `reviewer_columns`; leave
every `generated_columns` value unchanged. Row order and record IDs are part
of the generated snapshot. Return the edited TSV files and the original
manifest together. Include external evidence (URL, publication/page, an
attributed speaker judgement with date, or another inspectable source) and
your reasoning; do not copy unrelated definitions or media into these files.

For phrases, leave `proposed_preferred_reading` blank until justified. Record
other accepted whole-phrase readings in `proposed_other_accepted_readings`.
Use complete lowercase, space-separated Jyutping with tone digits 1–6.
Multiple proposed readings can be separated by ` | `. Do not infer a preferred
whole-phrase reading from character frequency alone. If the appropriate code
is absent from the original capped set, record it with evidence in the editable
proposal fields; do not change `codes_json` or mark the cap issue resolved.

For source exceptions, describe a proposed resolution and, only with evidence,
the proposed text/reading. Non-Jyutping source notation and template slots
need source-aware handling. For spelling collisions, document the intended
policy and proposed retained targets; avoid silently dropping an attested
canonical spelling to favor an alias.

Allowed review statuses:

- `pending`: no completed review; default.
- `needs_evidence`: a reviewer identified an unresolved evidence gap.
- `proposed_change`: an evidence-backed proposal awaits project decision.
- `confirmed`: the named reviewer claims the recorded judgement is supported;
  reviewer identity, date and evidence are required, but remain unauthenticated.
- `exclude`: proposed exclusion with reasoning/evidence, awaiting project decision.

Enter `reviewer`, `reviewed_at` (ISO 8601 date/time with timezone when known),
`evidence`, and `review_notes`. Blank proposals and default pending statuses
are intentional. A name/date/evidence cell cannot authenticate a human.
The project owner must separately verify trusted human approval of the exact
snapshot before accepting decisions. Hashes establish local source/content
consistency, not independent authority, linguistic truth, or readiness.

## Validation and regeneration

Run `python tools/build_review_pack.py --validate-only` to compare generated
columns against fresh derivation from the current dictionary/mapping inputs
and check review field structure. It reports `authenticated_human_approval:
false` even when rows claim confirmation. It never applies proposed changes.
Input identity uses logical roles and bytes rather than the current filesystem
location. A v1 snapshot remains validatable against preserved DB/mapping files;
its original generator hash stays historical provenance, and the current
validator hash is reported separately. Unknown or duplicate legacy roles are
rejected. Manifest locations are never read as instructions or opened as paths.

Run `python tools/build_review_pack.py` to regenerate an untouched pack. It
refuses changed input hashes, changed generated fields, or any nondefault
review field. There is no force option. To build a new snapshot while keeping
work in progress, run `python tools/build_review_pack.py --new-output
data/review-next` with a directory that does not yet exist.
The original v1 pack is frozen and cannot be regenerated in place.

## Independent evaluation remains separate

Do not move these source-derived rows into a held-out evaluation and label
them independent. Prepare that corpus separately from real intended typing
tasks, keep source overlap/discovery provenance, record author/speaker and
licensing consent, cover Cantonese colloquial speech, names, mixed English,
tones and spelling habits, and freeze target judgements before comparing
engine changes. No new held-out examples or human judgements are invented here.

## Source attribution

Phrase text, explicit Rime readings and essay weights derive from Rime
Cantonese / CanCLID and contributors, CC BY 4.0; character-table attestations
derive from LSHK, CC BY 4.0. Accepted words.hk wordlist pronunciations are
declared public domain, with credit appreciated. Selected TypeDuck principal
data is declared CC BY 4.0; historical row lineage and independent human
authorship remain separate from that declaration. Unihan direct-character
attestations use the retained Unicode license; provisional kCantonese readings
are excluded from phrase translation according to the recorded policy.
ScriptEncoder compatibility
logic derives from librime, BSD-3-Clause. Project spelling conveniences have
separate source citations and project-policy costs. The manifest records
pinned source metadata, policy, algorithm provenance, input hashes and rules.
Full source notices remain in `../THIRD_PARTY_NOTICES.md` and `../licenses/`.
Do not broaden the wordlist permission to words.hk definitions/media, or
import excluded OpenStreetMap data. Changes to generated source material are
identified as mechanical derived code generation and review queue selection.
