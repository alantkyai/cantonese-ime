"""Collect and score a pinned HKCanCor external-annotation baseline.

Evaluation only: no corpus reading or frequency is imported into the dictionary.
Source annotations are independent of this decoder, but upstream dictionary
overlap is unresolved. This is neither a clean held-out test nor natural typing.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import sys
import tempfile
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cantonese_ime import Engine
from cantonese_ime.dictionary import file_sha256


POLICY = {
    "version": "hkcancor-external-v1",
    "input_limit": 64,
    "units": ["word_type", "speech_span"],
    "selection": "Lowest SHA-256(unit NUL text NUL spaced_reading), equally allocated by unit; independent of dictionary contents/ranking.",
    "word_type": "Distinct eligible source text/reading pairs, including one-syllable words; all occurrences counted and first source occurrence retained.",
    "speech_span": "Distinct maximal consecutive eligible-token text/reading pairs within one source sent_tag; punctuation or any ineligible token ends a span; minimum two source tokens; no clipping of long spans.",
    "eligibility": "Chinese ideographs only and complete lowercase [a-z]+[1-6] source syllables; source POS w is punctuation. No dictionary-inventory filter, tone conversion, text normalization, guessed reading or bridging of unsupported tokens.",
    "length": "Exclude an entire unit if its fully toned compact input exceeds 64 raw characters; report all exclusions.",
    "scenarios": ["fully_toned", "tone_free"],
    "metric": "Exact source text at ranks 1/9/90; exact source text AND reading separately. No unreviewed orthographic alternatives accepted.",
    "quality_scope": "External corpus annotations, not clean held-out accuracy, casual spelling, human acceptance or native IME validation. Source/dictionary overlap is reported after selection and is not an eligibility filter.",
}
READING = re.compile(r"(?:[a-z]+[1-6])+")
SYLLABLE = re.compile(r"[a-z]+[1-6]")
SENT = re.compile(r"<sent>\s*(.*?)\s*</sent>", re.DOTALL)


def chinese_text(text: str) -> bool:
    """Eligibility is deliberately narrower than all possible Chinese text."""
    return bool(text) and all(
        0x3400 <= ord(char) <= 0x4DBF or 0x4E00 <= ord(char) <= 0x9FFF
        or 0xF900 <= ord(char) <= 0xFAFF or 0x20000 <= ord(char) <= 0x323AF
        for char in text
    )


def parse_transcript(content: str, source_file: str) -> list[dict]:
    """Read original fragment markup without interpreting transcript text as XML.

    The source is XML-like, not a single XML document. Only its known structural
    tags are recognized; source lines and slash notation are retained verbatim.
    Structural damage fails the collection rather than silently losing turns.
    """
    matches = list(SENT.finditer(content))
    if content.count("<sent>") != len(matches) or content.count("</sent>") != len(matches):
        raise ValueError(f"Unbalanced sent markup: {source_file}")
    if not matches:
        raise ValueError(f"No source utterances: {source_file}")
    for tag in ("sent_head", "sent_tag", "sent_tran"):
        if content.count(f"<{tag}>") != len(matches) or content.count(f"</{tag}>") != len(matches):
            raise ValueError(f"Unaccounted structural tag {tag}: {source_file}")
    turns = []
    for number, match in enumerate(matches, 1):
        body = match.group(1)
        if "<sent>" in body:
            raise ValueError(f"Nested sent markup: {source_file}:{number}")
        values = {}
        for tag in ("sent_head", "sent_tag", "sent_tran"):
            blocks = re.findall(fr"<{tag}>\s*(.*?)\s*</{tag}>", body, re.DOTALL)
            if len(blocks) != 1:
                raise ValueError(f"Expected one {tag}: {source_file}:{number}")
            values[tag] = blocks[0]
        tokens = []
        for index, line in enumerate(values["sent_tag"].splitlines(), 1):
            raw = line.strip()
            if not raw:
                continue
            fields = raw.rsplit("/", 3)
            token = {"raw": raw, "source_line_in_tag": index, "token_index": len(tokens)}
            if raw.endswith("/@"):
                token.update(status="unsupported_source_annotation", text=None, pos=None, raw_reading=None, reading=None)
            elif len(fields) != 4 or fields[-1] or not fields[0] or not fields[1]:
                token.update(status="malformed_annotation", text=None, pos=None, raw_reading=None, reading=None)
            else:
                text, pos, raw_reading, _ = fields
                reading = " ".join(SYLLABLE.findall(raw_reading)) if READING.fullmatch(raw_reading) else None
                status = ("punctuation" if pos == "w" else "non_ideographic_text" if not chinese_text(text)
                          else "unsupported_reading" if reading is None else "eligible")
                token.update(text=text, pos=pos, raw_reading=raw_reading, reading=reading, status=status)
            tokens.append(token)
        turns.append({"source_file": source_file, "turn": number,
                      "speaker": values["sent_head"].strip(), "tokens": tokens})
    return turns


def source_paths(lock_path: Path) -> tuple[dict, Path, dict[str, Path]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("source_id") != "hkcancor:original-utf8" or lock.get("license") != "CC-BY-4.0":
        raise ValueError("Unexpected HKCanCor source/permission boundary")
    root = (PROJECT_ROOT / lock["local_directory"]).resolve()
    paths = {}
    for item in lock["files"]:
        path = (root / item["name"]).resolve()
        if not path.is_relative_to(root) or item["name"] in paths:
            raise ValueError("Unsafe or duplicate locked path")
        if path.stat().st_size != item["size_bytes"] or file_sha256(path) != item["sha256"]:
            raise ValueError(f"Changed locked source: {item['name']}")
        paths[item["name"]] = path
    return lock, root, paths


def stable_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def collect_from_turns(turns: list[dict], sample_size: int) -> dict:
    if sample_size < 2 or sample_size % 2:
        raise ValueError("Sample size must be a positive even integer of at least two")
    counts: Counter = Counter()
    units: dict[str, dict[tuple[str, str], dict]] = {name: {} for name in POLICY["units"]}
    exclusion_examples: dict[str, list] = {}

    def add(unit: str, tokens: list[dict], turn: dict) -> None:
        counts[unit + ":source_occurrences"] += 1
        if unit == "speech_span" and len(tokens) < 2:
            counts[unit + ":excluded_single_token"] += 1
            return
        text = "".join(token["text"] for token in tokens)
        reading = " ".join(token["reading"] for token in tokens)
        if len(reading.replace(" ", "")) > POLICY["input_limit"]:
            counts[unit + ":excluded_over_input_limit"] += 1
            return
        counts[unit + ":eligible_occurrences"] += 1
        key = text, reading
        if key in units[unit]:
            units[unit][key]["source_occurrences"] += 1
            return
        selection_hash = hashlib.sha256((unit + "\0" + text + "\0" + reading).encode()).hexdigest()
        units[unit][key] = {
            "id": unit + ":" + selection_hash[:24], "unit": unit, "selection_hash": selection_hash,
            "text": text, "reading": reading, "source_occurrences": 1,
            "fully_toned_input": reading.replace(" ", ""),
            "tone_free_input": "".join(token[:-1] for token in reading.split()),
            "first_occurrence": {"file": turn["source_file"], "turn": turn["turn"],
                                 "speaker": turn["speaker"], "token_indices": [token["token_index"] for token in tokens],
                                 "raw_tokens": [token["raw"] for token in tokens]},
        }

    for turn in turns:
        counts["turns"] += 1
        run = []
        for token in turn["tokens"]:
            status = token["status"]
            counts["tokens"] += 1
            counts["token_status:" + status] += 1
            if status == "eligible":
                counts["syllables"] += len(token["reading"].split())
                if len(token["text"]) != len(token["reading"].split()):
                    counts["eligible_token_character_syllable_mismatches"] += 1
                add("word_type", [token], turn)
                run.append(token)
            else:
                if status != "punctuation" and len(exclusion_examples.setdefault(status, [])) < 30:
                    exclusion_examples[status].append({"file": turn["source_file"], "turn": turn["turn"], **token})
                if run:
                    add("speech_span", run, turn)
                    run = []
        if run:
            add("speech_span", run, turn)
    cases = []
    strata = {}
    for unit, records in units.items():
        quota = sample_size // 2
        selected = heapq.nsmallest(quota, records.values(), key=lambda row: row["selection_hash"])
        cases.extend(selected)
        strata[unit] = {"eligible_distinct_pairs": len(records), "requested": quota, "selected": len(selected)}
    cases.sort(key=lambda row: (row["unit"], row["selection_hash"]))
    selected_content: Counter = Counter((row["text"], row["reading"]) for row in cases)
    return {"accounting": dict(sorted(counts.items())), "exclusion_examples": exclusion_examples,
            "strata": strata, "case_count": len(cases),
            "selected_cross_unit_duplicate_pairs": sum(count > 1 for count in selected_content.values()), "cases": cases}


def collect(lock_path: Path, sample_size: int = 500) -> dict:
    lock_hash = file_sha256(lock_path)
    lock, _, paths = source_paths(lock_path)
    transcript_names = sorted(name for name in paths if name.startswith("data/utf8/"))
    if len(transcript_names) != 58:
        raise ValueError("Expected all 58 original UTF8 transcripts in the selected pin")
    turns = []
    for name in transcript_names:
        turns.extend(parse_transcript(paths[name].read_text(encoding="utf-8-sig"), name))
    result = {
        "schema_version": 1, "artifact_kind": "hkcancor_external_corpus",
        "purpose": "Frozen corpus-derived canonical-input external annotation baseline; no independent natural typing or clean held-out claim.",
        "source_id": lock["source_id"], "source_commit": lock["commit"],
        "source_lock_sha256": lock_hash, "license": lock["license"],
        "attribution": lock["attribution"], "citation": lock["citation"],
        "changes": "Original text/readings retained; eligible annotations joined into spaced readings and compact numeric/tone-free inputs, deduplicated and sampled under the recorded policy.",
        "selection_policy": POLICY, "selection_policy_sha256": stable_digest(POLICY),
        "transcript_count": len(transcript_names), "requested_cases": sample_size,
        **collect_from_turns(turns, sample_size),
    }
    source_paths(lock_path)
    if file_sha256(lock_path) != lock_hash:
        raise ValueError("Source lock changed during collection")
    return result


def metric(rows: list[dict]) -> dict:
    summary = {"requests": len(rows), "errors": sum("error" in row for row in rows),
               "empty_candidate_lists": sum(row.get("candidate_count") == 0 for row in rows)}
    for label, cap in (("top1", 1), ("top9", 9), ("top90", 90)):
        for field in ("text_rank", "pair_rank"):
            summary[field.replace("_rank", "") + "_" + label] = sum(row[field] is not None and row[field] <= cap for row in rows)
    samples = sorted(row["elapsed_ms"] for row in rows)
    if samples:
        summary["latency_ms"] = {"samples": len(samples), "median": round(statistics.median(samples), 3),
                                 "p95": samples[math.ceil(len(samples) * .95) - 1], "maximum": samples[-1]}
    return summary


def overlap(connection: sqlite3.Connection, case: dict) -> dict:
    exact = connection.execute("SELECT source,origin FROM entries WHERE text=? AND reading=?", (case["text"], case["reading"])).fetchone()
    any_text = connection.execute("SELECT 1 FROM entries WHERE text=? LIMIT 1", (case["text"],)).fetchone() is not None
    return {"stored_pair": exact is not None, "stored_text": any_text,
            "pair_source": exact[0] if exact else None, "pair_origin": exact[1] if exact else None}


def evaluate(database: Path, corpus_path: Path, lock_path: Path) -> dict:
    source_hashes = {name: file_sha256(PROJECT_ROOT / name) for name in
                     ("cantonese_ime/engine.py", "cantonese_ime/mappings.py", "tools/evaluate_hkcancor.py")}
    corpus_hash, database_hash, lock_hash = (file_sha256(path) for path in (corpus_path, database, lock_path))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if corpus.get("artifact_kind") != "hkcancor_external_corpus" or not corpus.get("cases"):
        raise ValueError("Expected a nonempty frozen external corpus")
    if corpus["source_lock_sha256"] != lock_hash or corpus["selection_policy"] != POLICY:
        raise ValueError("Corpus source or collection policy differs")
    # Rederive every label/provenance field before trusting this as source-based
    # evidence; JSON metadata alone cannot authenticate external annotations.
    if collect(lock_path, corpus["requested_cases"]) != corpus:
        raise ValueError("Frozen cases differ from a fresh source-only collection")
    results = []
    oracle = {}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        for case in corpus["cases"]:
            oracle[case["id"]] = overlap(connection, case)
    start = time.perf_counter()
    with Engine(database, mode="jyutping") as engine:
        startup_ms = (time.perf_counter() - start) * 1000
        for case in corpus["cases"]:
            for scenario in POLICY["scenarios"]:
                raw = case[scenario + "_input"]
                row = {"id": case["id"], "unit": case["unit"], "scenario": scenario,
                       "input": raw, "expected_text": case["text"], "expected_reading": case["reading"],
                       "text_rank": None, "pair_rank": None, "dictionary_overlap": oracle[case["id"]]}
                start = time.perf_counter()
                try:
                    candidates = engine.lookup(raw, limit=90, mode="jyutping")
                    row["candidate_count"] = len(candidates)
                    row["text_rank"] = next((i for i, c in enumerate(candidates, 1) if c.text == case["text"]), None)
                    row["pair_rank"] = next((i for i, c in enumerate(candidates, 1) if c.text == case["text"] and c.reading == case["reading"]), None)
                    row["top9"] = [{"text": c.text, "reading": c.reading, "match_type": c.match_type} for c in candidates[:9]]
                    row["consumed_input_mismatches"] = sum(c.consumed_input != len(raw) for c in candidates)
                except Exception as error:
                    row["error"] = f"{type(error).__name__}: {error}"
                row["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
                results.append(row)
            if len(results) % 100 == 0 or len(results) == 2 * len(corpus["cases"]):
                print(json.dumps({"progress": len(results), "total": 2 * len(corpus["cases"])}), file=sys.stderr, flush=True)
    if {name: file_sha256(PROJECT_ROOT / name) for name in source_hashes} != source_hashes:
        raise ValueError("Runtime or evaluator source changed during scoring")
    source_paths(lock_path)
    if any(file_sha256(path) != digest for path, digest in
           ((database, database_hash), (corpus_path, corpus_hash), (lock_path, lock_hash))):
        raise ValueError("Database, corpus or source lock changed during scoring")
    groups = {}
    for unit in POLICY["units"]:
        for scenario in POLICY["scenarios"]:
            rows = [row for row in results if row["unit"] == unit and row["scenario"] == scenario]
            groups[unit + ":" + scenario] = metric(rows)
            for label in ("stored_pair", "stored_text"):
                groups[unit + ":" + scenario][label + "_cohorts"] = {
                    str(value).lower(): metric([row for row in rows if row["dictionary_overlap"][label] == value])
                    for value in (True, False)}
    return {"schema_version": 1, "artifact_kind": "hkcancor_external_report",
            "purpose": corpus["purpose"], "interpretation": POLICY["quality_scope"],
            "database_sha256": database_hash, "corpus_sha256": corpus_hash,
            "source_lock_sha256": lock_hash, "runtime_source_sha256": source_hashes,
            "source_commit": corpus["source_commit"], "selection_policy_sha256": corpus["selection_policy_sha256"],
            "case_count": len(corpus["cases"]), "mode": "jyutping", "learning": False, "candidate_limit": 90,
            "engine_startup_ms": round(startup_ms, 3), "python_version": platform.python_version(),
            "platform": platform.platform(), "summary": metric(results), "strata": groups,
            "first90_policy": "Fixed first-90 metric; no later-page recovery relabeled as a first-90 hit. Text/reading and exact-text metrics are separate; completions must equal the full target text to count.",
            "timing_policy": "One lookup per case/scenario, not a repeated-same-query cached median. Duplicate inputs between source cases may still share the current engine snapshot. Not per-keystroke or native latency.",
            "corpus_accounting": corpus["accounting"], "selected_cross_unit_duplicate_pairs": corpus["selected_cross_unit_duplicate_pairs"],
            "selected_dictionary_overlap": {"stored_pairs": sum(row["stored_pair"] for row in oracle.values()),
                                            "stored_texts": sum(row["stored_text"] for row in oracle.values()),
                                            "interpretation": "Measured after source-only selection, never used to exclude cases. Absent whole-text pairs do not prove unseen constituents, frequencies or training provenance."},
            "results": results}


def write_json(path: Path, value: dict, *, protected: list[Path]) -> None:
    target = path.resolve()
    if any(target == item.resolve() or item.is_dir() and target.is_relative_to(item.resolve()) for item in protected):
        raise ValueError("Output would overwrite a source or frozen input")
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("artifact_kind") != value["artifact_kind"]:
            raise ValueError("Refusing to replace a different artifact")
        if value["artifact_kind"] == "hkcancor_external_corpus" and existing != value:
            raise ValueError("Frozen corpus differs; choose a new corpus path")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-lock", type=Path, default=PROJECT_ROOT / "eval/hkcancor.sources.lock.json")
    parser.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "eval/hkcancor_cases.json")
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data/generated/lexicon.sqlite3")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs/hkcancor-evaluation.json")
    parser.add_argument("--collect", action="store_true", help="Freeze source-only cases; do not score")
    parser.add_argument("--sample-size", type=int, default=500)
    args = parser.parse_args()
    _, retained_root, _ = source_paths(args.source_lock)
    protected = [args.source_lock, retained_root, PROJECT_ROOT / "eval/vendor", args.database,
                 PROJECT_ROOT / "cantonese_ime", PROJECT_ROOT / "data", PROJECT_ROOT / "tools", PROJECT_ROOT / "tests"]
    if args.collect:
        corpus = collect(args.source_lock, args.sample_size)
        write_json(args.corpus, corpus, protected=protected)
        print(json.dumps({key: corpus[key] for key in ("case_count", "strata", "accounting", "selection_policy_sha256")}, indent=2))
        return 0
    report = evaluate(args.database, args.corpus, args.source_lock)
    write_json(args.output, report, protected=protected + [args.corpus])
    print(json.dumps({"summary": report["summary"], "selected_dictionary_overlap": report["selected_dictionary_overlap"],
                      "strata": report["strata"]}, indent=2))
    return int(bool(report["summary"]["errors"]) or any(row.get("consumed_input_mismatches") for row in report["results"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(f"HKCanCor evaluation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
