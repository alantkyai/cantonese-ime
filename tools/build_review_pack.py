"""Build source-derived human review queues without granting approvals.

Generated columns are reproduced from pinned local inputs. Reviewer columns
are never consumed by the dictionary builder or engine. No network is used.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cantonese_ime.autoencode import ScriptAutoencoder
from cantonese_ime.dictionary import file_sha256, read_frequencies


PACK_VERSION = "cantonese-linguistic-review-v2"
LEGACY_PACK_VERSION = "cantonese-linguistic-review-v1"
LEGACY_INPUT_ROLES = {
    "data/generated/lexicon.sqlite3": "database",
    "data/mappings/spellings.json": "mapping_spellings",
    "data/mappings/syllables.json": "mapping_syllables",
    "data/mappings/build.manifest.json": "mapping_manifest",
    "cantonese_ime/autoencode.py": "autoencoder_source",
    "tools/build_review_pack.py": "generator_source",
    "data/sources.lock.json": "rime_lock",
    "data/supplements/wordshk.sources.lock.json": "wordshk_lock",
    "data/mappings/lshk.sources.lock.json": "lshk_lock",
    "data/vendor/rime-cantonese/259f0e48bba840c3a2e0d117539e96937f3d89bc/essay-cantonese.txt": "preset_frequencies",
}
INPUT_ROLES = frozenset(LEGACY_INPUT_ROLES.values()) | {"typeduck_lock", "unihan_lock"}
STATUSES = ("pending", "needs_evidence", "proposed_change", "confirmed", "exclude")
COMMON_REVIEW = ("review_status", "reviewer", "reviewed_at", "evidence", "review_notes")
PHRASE_REVIEW = ("proposed_preferred_reading", "proposed_other_accepted_readings") + COMMON_REVIEW
EXCEPTION_REVIEW = ("proposed_resolution", "proposed_text", "proposed_reading") + COMMON_REVIEW
SPELLING_REVIEW = ("proposed_policy", "proposed_retained_targets") + COMMON_REVIEW
PHRASE_GENERATED = (
    "record_id", "priority_rank", "selection_reason", "text", "source", "line",
    "ledger_status", "codes_json", "path_count", "candidate_code_count",
    "full_path_count", "path_limit_category", "frequency", "polyphonic_characters_json",
    "qualifying_character_codes_json", "heuristic_tags_json",
)
EXCEPTION_GENERATED = ("record_id", "source", "text", "source_status", "details_json", "existing_authored_readings_json")
SPELLING_GENERATED = ("record_id", "spelling", "canonical_targets_json", "target_count", "alias_records_json", "target_attestations_json", "profile_version")
TABLES = {
    "phrases.tsv": (PHRASE_GENERATED, PHRASE_REVIEW),
    "path_limited_phrases.tsv": (PHRASE_GENERATED, PHRASE_REVIEW),
    "source_exceptions.tsv": (EXCEPTION_GENERATED, EXCEPTION_REVIEW),
    "spelling_collisions.tsv": (SPELLING_GENERATED, SPELLING_REVIEW),
}
COLLOQUIAL_MARKERS = frozenset("唔嘅啲咁嚟喺佢哋冇乜噉嘢咗咩喎囉吖嘞")
NAME_MARKERS = ("阿", "麥當", "香港", "中國", "美國", "日本", "大學", "中學", "學校", "公司", "銀行", "政府", "醫院", "大廈", "街", "路")


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(compact_json(value).encode("utf-8")).hexdigest()


def record_id(kind: str, *identity: object) -> str:
    return kind + ":" + digest(identity)[:24]


def reviewer_defaults(columns: tuple[str, ...]) -> dict[str, str]:
    return {column: "pending" if column == "review_status" else "" for column in columns}


def encode_tsv(rows: list[dict], generated: tuple, reviewer: tuple) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=generated + reviewer, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, **reviewer_defaults(reviewer)})
    return stream.getvalue().encode("utf-8")


def immutable_digest(rows: list[dict], columns: tuple) -> str:
    # String coercion matches an ordinary UTF-8 TSV round trip.
    return digest([{key: str(row[key]) for key in columns} for row in rows])


def read_table(path: Path, generated: tuple, reviewer: tuple) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != list(generated + reviewer):
            raise ValueError(f"{path.name}: column names/order changed")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{path.name}: malformed TSV row")
    ids = [row["record_id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path.name}: duplicate record_id")
    return rows


def full_path_count(text: str, encoder: ScriptAutoencoder, lengths: tuple[int, ...] | None = None) -> int:
    """Count complete paths without imposing the emission cap or inventing codes.

    A path is an upstream DFS emission, not necessarily a distinct code. The
    dictionary's conservative 32-path classification is never changed here.
    """
    if lengths is None:
        lengths = tuple(sorted({len(token) for token, codes in encoder.translations.items() if codes}))
    paths = [0] * (len(text) + 1)
    paths[-1] = 1
    for start in range(len(text) - 1, -1, -1):
        for length in lengths:
            end = start + length
            if end <= len(text):
                paths[start] += len(encoder.translations.get(text[start:end], ())) * paths[end]
    return paths[0]


def collect(database: Path, mapping_dir: Path) -> tuple[dict[str, list[dict]], dict]:
    spellings = json.loads((mapping_dir / "spellings.json").read_text(encoding="utf-8"))
    syllables = json.loads((mapping_dir / "syllables.json").read_text(encoding="utf-8"))
    syllable_by_base = {row["base"]: row for row in syllables["syllables"]}
    source_lock = json.loads((PROJECT_ROOT / "data/sources.lock.json").read_text(encoding="utf-8"))
    frequency_path = PROJECT_ROOT / source_lock["local_directory"] / "essay-cantonese.txt"
    frequencies = read_frequencies(frequency_path)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        metadata = {row[0]: json.loads(row[1]) for row in connection.execute("SELECT key,value FROM metadata")}
        translation_policy = metadata.get("phrase_translation_policy", {})
        if not isinstance(translation_policy, dict):
            raise ValueError("phrase_translation_policy must have a machine-readable excluded_sources list")
        excluded = translation_policy.get("excluded_sources", [])
        if not isinstance(excluded, list) or any(not isinstance(source, str) for source in excluded):
            raise ValueError("phrase_translation_policy.excluded_sources must be a list of source names")
        authored = list(connection.execute("SELECT text,reading,weight,source FROM entries WHERE origin IN ('explicit','supplement') ORDER BY id"))
        if any(row["source"].startswith("unihan:") and row["source"] not in excluded for row in authored):
            raise ValueError("Unihan source is missing its explicit phrase-translation exclusion policy")
        encoder = ScriptAutoencoder(tuple(row)[:3] for row in authored if row["source"] not in excluded)
        translation_lengths = tuple(sorted({len(text) for text, codes in encoder.translations.items() if codes}))
        ambiguous = [dict(row) for row in connection.execute("SELECT * FROM phrase_encodings WHERE status='encoded_ambiguous' ORDER BY source,line")]
        limited = [dict(row) for row in connection.execute("SELECT * FROM phrase_encodings WHERE status='truncated' ORDER BY source,line")]
        exceptions = [dict(row) for row in connection.execute("SELECT * FROM supplement_review WHERE status!='normalized_variant' ORDER BY source,text,details_json")]
        for row in exceptions:
            row["authored_readings"] = [dict(found) for found in connection.execute(
                "SELECT reading,source,origin FROM entries WHERE text=? AND origin IN ('explicit','supplement') ORDER BY reading,source", (row["text"],))]
    for row in ambiguous + limited:
        row["polyphones"] = sorted({character for character in row["text"] if len(encoder.translations.get(character, ())) > 1})
        row["frequency"] = frequencies.get(row["text"], 0)
        row["tags"] = []
        if any(character in COLLOQUIAL_MARKERS for character in row["text"]):
            row["tags"].append("colloquial_marker")
        if any(marker in row["text"] for marker in NAME_MARKERS):
            row["tags"].append("name_or_institution_marker")
    order = lambda row: (-row["frequency"], row["source"], row["line"], row["text"])
    ranked = sorted(ambiguous, key=order)
    selected: list[tuple[dict, str]] = []
    seen: set[tuple] = set()
    covered: set[str] = set()

    def take(rows: list[dict], count: int, reason: str) -> None:
        added = 0
        for row in rows:
            identity = (row["source"], row["line"])
            if identity not in seen:
                selected.append((row, reason))
                seen.add(identity)
                covered.update(row["polyphones"])
                added += 1
                if added >= count:
                    break

    take(ranked, 100, "frequency_top100")
    take([row for row in ranked if "colloquial_marker" in row["tags"]], 25, "colloquial_marker_frequency_quota")
    take([row for row in ranked if "name_or_institution_marker" in row["tags"]], 25, "name_marker_frequency_quota")
    # Maximize previously unseen polyphonic characters, breaking ties by the
    # source frequency; these are queue priorities, not pronunciation claims.
    while len(selected) < min(200, len(ranked)):
        remaining = [row for row in ranked if (row["source"], row["line"]) not in seen]
        chosen = min(remaining, key=lambda row: (-len(set(row["polyphones"]) - covered), *order(row)))
        take([chosen], 1, "polyphonic_character_diversity_then_frequency")

    def phrase_row(row: dict, rank: int, reason: str) -> dict:
        codes = json.loads(row["codes_json"])
        complete_paths = full_path_count(row["text"], encoder, translation_lengths)
        boundary = ("exactly_32_paths" if complete_paths == 32 else "over_32_paths") if row["status"] == "truncated" and row["reason"] == "path_limit" else "complete"
        return {
            "record_id": record_id("phrase", row["source"], row["line"], row["text"]),
            "priority_rank": rank, "selection_reason": reason, "text": row["text"],
            "source": row["source"], "line": row["line"], "ledger_status": row["status"],
            "codes_json": compact_json(codes), "path_count": row["path_count"],
            "candidate_code_count": len(codes), "full_path_count": complete_paths,
            "path_limit_category": boundary, "frequency": row["frequency"],
            "polyphonic_characters_json": compact_json(row["polyphones"]),
            "qualifying_character_codes_json": compact_json({character: encoder.translations[character] for character in row["polyphones"]}),
            "heuristic_tags_json": compact_json(row["tags"]),
        }

    phrase_rows = [phrase_row(row, rank, reason) for rank, (row, reason) in enumerate(selected, 1)]
    limited_rows = [phrase_row(row, rank, "all_truncated_frequency_order") for rank, row in enumerate(sorted(limited, key=order), 1)]
    exception_rows = [{
        "record_id": record_id("exception", row["source"], row["text"], row["details_json"]),
        "source": row["source"], "text": row["text"], "source_status": row["status"],
        "details_json": compact_json(json.loads(row["details_json"])),
        "existing_authored_readings_json": compact_json(row["authored_readings"]),
    } for row in exceptions]
    groups: dict[str, list] = defaultdict(list)
    for row in spellings["aliases"]:
        groups[row["spelling"]].append(row)
    collision_rows = []
    for spelling, records in sorted(groups.items()):
        targets = sorted({row["canonical"] for row in records})
        if len(targets) < 2:
            continue
        collision_rows.append({
            "record_id": record_id("spelling", spellings["profile_version"], spelling),
            "spelling": spelling, "canonical_targets_json": compact_json(targets),
            "target_count": len(targets), "alias_records_json": compact_json(records),
            "target_attestations_json": compact_json({target: syllable_by_base[target] for target in targets}),
            "profile_version": spellings["profile_version"],
        })
    return {
        "phrases.tsv": phrase_rows, "path_limited_phrases.tsv": limited_rows,
        "source_exceptions.tsv": exception_rows, "spelling_collisions.tsv": collision_rows,
    }, {
        "database_schema_version": metadata["schema_version"],
        "database_semantic_sha256": metadata["semantic_sha256"],
        "database_sources": metadata["sources"],
        "database_source_metadata": metadata["source_metadata"],
        "supplement_weight_policy": metadata["supplement_weight_policy"],
        "queue_frequency_policy": "Exact-text essay-cantonese.txt count only for review priority, not a pronunciation probability or an assigned supplement weight. Missing count is 0.",
        "autoencoding_algorithm": metadata["autoencoding_algorithm"],
        "phrase_translation_policy": translation_policy,
        "mapping_profile_version": spellings["profile_version"],
        "mapping_policy": spellings["policy"],
        "mapping_rules": spellings["rules"],
        "mapping_sources": spellings["sources"],
        "queue_coverage": {
            "ambiguous_phrase_rows_total": len(ambiguous), "ambiguous_phrase_rows_queued": len(phrase_rows),
            "ambiguous_polyphonic_characters_total": len({char for row in ambiguous for char in row["polyphones"]}),
            "ambiguous_polyphonic_characters_queued": len(covered),
            "path_limited_rows_total": len(limited),
            "path_limit_categories": dict(Counter(row["path_limit_category"] for row in limited_rows)),
            "source_exception_statuses": dict(Counter(row["source_status"] for row in exception_rows)),
            "spelling_collision_rows_total": len(collision_rows),
            "phrase_selection_reasons": dict(Counter(reason for _, reason in selected)),
            "phrase_heuristic_tags": dict(Counter(tag for row, _ in selected for tag in row["tags"])),
        },
    }


def input_paths(database: Path, mapping_dir: Path) -> dict[str, Path]:
    paths = {"database": database, "mapping_spellings": mapping_dir / "spellings.json",
             "mapping_syllables": mapping_dir / "syllables.json", "mapping_manifest": mapping_dir / "build.manifest.json",
             "autoencoder_source": PROJECT_ROOT / "cantonese_ime/autoencode.py", "generator_source": Path(__file__).resolve(),
             "rime_lock": PROJECT_ROOT / "data/sources.lock.json"}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        source_metadata = json.loads(connection.execute("SELECT value FROM metadata WHERE key='source_metadata'").fetchone()[0])
    supplements = source_metadata.get("supplements", {})
    known = {"lshk": ("lshk_lock", "data/mappings/lshk.sources.lock.json"),
             "wordshk": ("wordshk_lock", "data/supplements/wordshk.sources.lock.json"),
             "typeduck": ("typeduck_lock", "data/supplements/typeduck.sources.lock.json"),
             "unihan": ("unihan_lock", "data/supplements/unihan.sources.lock.json")}
    for name in supplements:
        if name not in known:
            raise ValueError(f"Unsupported supplemental input role: {name}")
        role, filename = known[name]
        paths[role] = PROJECT_ROOT / filename
    source_lock = json.loads((PROJECT_ROOT / "data/sources.lock.json").read_text(encoding="utf-8"))
    paths["preset_frequencies"] = PROJECT_ROOT / source_lock["local_directory"] / "essay-cantonese.txt"
    return paths


def input_hashes(database: Path, mapping_dir: Path) -> dict:
    return {role: {"sha256": file_sha256(path), "size_bytes": path.stat().st_size}
            for role, path in input_paths(database, mapping_dir).items()}


def normalize_manifest_inputs(inputs: dict, *, legacy: bool) -> dict:
    """Map only known legacy keys; never open a path supplied by a manifest."""
    if not isinstance(inputs, dict):
        raise ValueError("Manifest inputs must be an object")
    normalized = {}
    for name, value in inputs.items():
        role = LEGACY_INPUT_ROLES.get(name, name) if legacy else name
        if role not in INPUT_ROLES:
            raise ValueError(f"Unknown manifest input role: {name}")
        if role in normalized:
            raise ValueError(f"Duplicate manifest input role: {role}")
        if (not isinstance(value, dict) or set(value) != {"sha256", "size_bytes"} or
                not isinstance(value["sha256"], str) or len(value["sha256"]) != 64 or
                any(character not in "0123456789abcdef" for character in value["sha256"]) or
                not isinstance(value["size_bytes"], int) or isinstance(value["size_bytes"], bool) or value["size_bytes"] < 0):
            raise ValueError(f"Malformed manifest input hash: {role}")
        normalized[role] = value
    return normalized


def validate_pack(output: Path, tables: dict, hashes: dict, *, for_regeneration: bool) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    legacy = manifest.get("pack_version") == LEGACY_PACK_VERSION
    if manifest.get("pack_version") not in (PACK_VERSION, LEGACY_PACK_VERSION):
        raise ValueError("pack version changed; use --new-output with a nonexistent directory")
    if legacy and for_regeneration:
        raise ValueError("v1 review snapshot is frozen; use --new-output and preserve its manifest and TSVs")
    recorded = normalize_manifest_inputs(manifest.get("inputs"), legacy=legacy)
    # Generator identity remains historical provenance; the present validator
    # proves actual generated content afresh. File location is not identity.
    recorded_data = {role: value for role, value in recorded.items() if role != "generator_source"}
    current_data = {role: value for role, value in hashes.items() if role != "generator_source"}
    if "generator_source" not in recorded or recorded_data != current_data:
        raise ValueError("input hashes changed; use --new-output to preserve the existing review snapshot")
    if for_regeneration and file_sha256(output / "README.md") != manifest["readme_sha256"]:
        raise ValueError("review README edits exist; use --new-output to preserve this snapshot")
    counts = Counter()
    for name, (generated, reviewer) in TABLES.items():
        rows = read_table(output / name, generated, reviewer)
        # Fresh derivation prevents editing both TSV and local manifest to hide
        # a generated-column change. It still cannot authenticate a reviewer.
        expected = immutable_digest(tables[name], generated)
        if immutable_digest(rows, generated) != expected:
            raise ValueError(f"{name}: generated columns differ from freshly derived source data")
        if manifest["tables"][name]["generated_sha256"] != expected:
            raise ValueError(f"{name}: manifest generated digest differs from source data")
        for row in rows:
            status = row["review_status"]
            if status not in STATUSES:
                raise ValueError(f"{name} {row['record_id']}: unsupported review_status {status!r}")
            counts[status] += 1
            if status == "confirmed" and not all(row[field].strip() for field in ("reviewer", "reviewed_at", "evidence")):
                raise ValueError(f"{name} {row['record_id']}: confirmed claim requires reviewer, reviewed_at, and evidence")
            if for_regeneration and any(row[key] != value for key, value in reviewer_defaults(reviewer).items()):
                raise ValueError(f"{name}: reviewer edits exist; use --new-output with a nonexistent directory; there is no --force")
    return {"generated_fields_match_current_inputs": True, "review_status_counts": dict(counts),
            "pack_version": manifest["pack_version"],
            "recorded_generator_sha256": recorded["generator_source"]["sha256"],
            "current_validator_sha256": file_sha256(Path(__file__)),
            "generator_hash_is_historical_provenance": True,
            "authenticated_human_approval": False, "readiness_approved": False,
            "warning": "Confirmed is an unauthenticated record claim until the project owner verifies trusted human approval of this exact snapshot."}


README = """# Linguistic review pack

This is a source-derived work queue, not an independent held-out accuracy
corpus. No row is linguistically approved by generation. The engine and
dictionary builder do not read reviewer columns. The initial state is pending.

`phrases.tsv` contains @QUEUED_AMBIGUOUS@ of @TOTAL_AMBIGUOUS@ mechanically ambiguous phrase rows.
The selection takes 100 highest source-frequency rows, 25 additional rows
with colloquial markers, 25 with name/institution markers, then prioritizes
new polyphonic characters before frequency until reaching 200. The markers
are transparent sampling heuristics, not authoritative linguistic labels.
Frequency is the dictionary's existing exact-text essay weight, with zero
where no frequency is supplied; it is not a pronunciation confidence score.
This small queue does not cover all remaining ambiguous phrases.

`path_limited_phrases.tsv` contains all @TOTAL_LIMITED@ conservative path-limit rows.
`codes_json` retains the original capped codes in emission order. A separate
dynamic-programming count describes all possible complete paths through the
same qualifying translations: @EXACT32@ rows have exactly 32 paths and @OVER32@ have more
than 32. The dictionary still labels both groups truncated. Full path counts
are not necessarily distinct code counts, and codes beyond the original cap
are not silently added. Character alternatives explain mechanical ambiguity;
they do not establish which readings apply to a whole phrase.

`source_exceptions.tsv` contains all @TOTAL_EXCEPTIONS@ unresolved source rows.
@EXCEPTION_BREAKDOWN@
Existing authored readings are shown separately when available. An LSHK radical
description is not a character pronunciation. Accepted words.hk trailing-star
variant records remain traceable in the database; they are resolved source-format
normalization, not this queue. TypeDuck phonetic annotations retain their raw
line/reading/percentage and are never silently rewritten into ordinary codes.

`spelling_collisions.tsv` contains all @TOTAL_COLLISIONS@ input spellings mapping to multiple
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
"""


def readme_for(tables: dict, provenance: dict) -> str:
    coverage = provenance["queue_coverage"]
    replacements = {
        "@QUEUED_AMBIGUOUS@": len(tables["phrases.tsv"]),
        "@TOTAL_AMBIGUOUS@": coverage["ambiguous_phrase_rows_total"],
        "@TOTAL_LIMITED@": len(tables["path_limited_phrases.tsv"]),
        "@EXACT32@": coverage["path_limit_categories"].get("exactly_32_paths", 0),
        "@OVER32@": coverage["path_limit_categories"].get("over_32_paths", 0),
        "@TOTAL_EXCEPTIONS@": len(tables["source_exceptions.tsv"]),
        "@TOTAL_COLLISIONS@": len(tables["spelling_collisions.tsv"]),
    }
    text = README
    for marker, value in replacements.items():
        text = text.replace(marker, f"{value:,}")
    exceptions = Counter((row["source"], row["source_status"]) for row in tables["source_exceptions.tsv"])
    breakdown = "\n".join(f"- `{source}` / `{status}`: {count:,}." for (source, status), count in sorted(exceptions.items()))
    text = text.replace("@EXCEPTION_BREAKDOWN@", "\n" + breakdown + "\n")
    return text


def atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--mappings", type=Path, default=PROJECT_ROOT / "data/mappings")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/review")
    parser.add_argument("--new-output", type=Path, help="New snapshot directory; must not already exist")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.new_output is not None and args.validate_only:
        parser.error("--new-output cannot be combined with --validate-only")
    output = (args.new_output or args.output).resolve()
    if args.new_output is not None and output.exists():
        parser.error("--new-output must name a nonexistent directory")
    hashes = input_hashes(args.database, args.mappings)
    tables, provenance = collect(args.database, args.mappings)
    if input_hashes(args.database, args.mappings) != hashes:
        raise ValueError("inputs changed while collecting review rows")
    if args.validate_only:
        print(json.dumps(validate_pack(output, tables, hashes, for_regeneration=False), ensure_ascii=False, sort_keys=True))
        return 0
    if output.exists():
        validate_pack(output, tables, hashes, for_regeneration=True)
    payloads = {name: encode_tsv(rows, *TABLES[name]) for name, rows in tables.items()}
    payloads["README.md"] = readme_for(tables, provenance).encode("utf-8")
    manifest = {
        "schema_version": 2, "pack_version": PACK_VERSION, "inputs": hashes,
        "recorded_input_locations": {role: str(path.resolve()) for role, path in input_paths(args.database, args.mappings).items()},
        "provenance": provenance,
        "sampling": "Source-derived review queues, not independent held-out evaluation; no approval inferred.",
        "reviewer_statuses": list(STATUSES), "initial_review_status": "pending",
        "human_approval_authenticated": False, "readiness_approved": False,
        "trust_limit": "Source consistency is freshly checked; local hashes and self-reported reviewer fields cannot authenticate a human or approve linguistic readiness.",
        "tables": {name: {
            "row_count": len(rows), "generated_columns": list(TABLES[name][0]),
            "reviewer_columns": list(TABLES[name][1]),
            "generated_sha256": immutable_digest(rows, TABLES[name][0]),
            "initial_file_sha256": hashlib.sha256(payloads[name]).hexdigest(),
        } for name, rows in tables.items()},
        "readme_sha256": hashlib.sha256(payloads["README.md"]).hexdigest(),
    }
    payloads["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        atomic_write(output / name, payload)
    print(json.dumps({"output": str(output), "rows": {name: len(rows) for name, rows in tables.items()},
                      "bytes": {name: len(payload) for name, payload in payloads.items()},
                      "authenticated_human_approval": False}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Review pack error: {error}", file=sys.stderr)
        raise SystemExit(1)
