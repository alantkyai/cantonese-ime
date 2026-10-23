"""Replay frozen authored phrases without changing their targets or dictionary.

This is a development quality review, not held-out accuracy or native UI proof.
Only disposable synthetic learning paths are opened. Output contains public
fixture inputs and candidates; no personal history or Windows settings are read.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cantonese_ime import Engine

DATABASE = ROOT / "data/generated/lexicon.sqlite3"
POLICY = ROOT / "eval/long_phrase_release_policy.json"
FIXTURE = ROOT / "eval/long_phrase_review_cases.json"
GRID = ROOT / "eval/yale_expected.json"
PROFILES = ("fresh", "short_preferences", "heavy_short_preferences")
SHORT = (("ng", "唔"), ("ji", "字"), ("di", "啲"), ("go", "個"), ("bin", "邊"))
HEAVY = SHORT + (("ngo", "我"), ("nei", "你"), ("hai", "係"),
                 ("gam", "咁"), ("seung", "想"), ("hou", "好"), ("heui", "去"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def band(length):
    return "1-3" if length < 4 else "4-5" if length <= 5 else "6-8" if length <= 8 else "9-12" if length <= 12 else "13+"


def yale_from_grid(base, grid):
    """Independent conversion of ordinary bases using the frozen factual grid."""
    if base in ("m", "ng"):
        return base
    onset = next((item for item in ("gw", "kw", "ng", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "w", "z", "c", "s", "j")
                  if base.startswith(item)), "")
    final = base[len(onset):]
    if final not in grid:
        raise ValueError(f"No independently frozen ordinary Yale final for {base}")
    converted = {"z": "j", "c": "ch", "j": "y"}.get(onset, onset)
    if converted == "y" and final in ("yu", "yun", "yut"):
        converted = ""
    return converted + grid[final]


def prepare_cases(fixture, connection):
    grid = dict(json.loads(GRID.read_text(encoding="utf-8"))["final_grid"])
    identifiers, prepared = set(), []
    for case in fixture["cases"]:
        identifier, text, reading = case["id"], case["text"], case["reading"]
        if identifier in identifiers:
            raise ValueError("Duplicate case id")
        identifiers.add(identifier)
        tokens = reading.split()
        if not text or not all(re.fullmatch(r"[a-z]+[1-6]", item) for item in tokens):
            raise ValueError(f"Invalid authored target/reading: {identifier}")
        if len(text) != len(tokens):
            raise ValueError(f"Review character/reading alignment before scoring: {identifier}")
        syllables = [yale_from_grid(item[:-1], grid) for item in tokens]
        if "".join(syllables) != case["input"]:
            raise ValueError(f"Independent Yale spelling mismatch: {identifier}")
        forms = [("plain_yale_compact", case["input"], "forgiving"),
                 ("plain_yale_apostrophes", "'".join(syllables), "forgiving"),
                 ("strict_jyutping_toned", "".join(tokens), "jyutping"),
                 ("strict_jyutping_tone_free", "".join(item[:-1] for item in tokens), "jyutping")]
        if case.get("user_input"):
            habitual = "".join("ng" if character == "唔" and token[:-1] == "m" else item
                               for character, token, item in zip(text, tokens, syllables))
            if habitual != case["user_input"]:
                raise ValueError(f"Habitual-ng spelling changes unrelated syllables: {identifier}")
            forms.append(("habitual_ng_compact", habitual, "forgiving"))
        stored_text = bool(connection.execute("SELECT 1 FROM entries WHERE text=? LIMIT 1", (text,)).fetchone())
        stored_pair = bool(connection.execute("SELECT 1 FROM entries WHERE text=? AND reading=? LIMIT 1", (text, reading)).fetchone())
        # Reading support is a dictionary fact, not an engine-rank filter.
        reachable, parts = {0}, {}
        for start in range(len(text)):
            if start not in reachable:
                continue
            for end in range(start + 1, len(text) + 1):
                if connection.execute("SELECT 1 FROM entries WHERE text=? AND reading=? LIMIT 1",
                                      (text[start:end], " ".join(tokens[start:end]))).fetchone():
                    reachable.add(end)
                    parts.setdefault(end, parts.get(start, []) + [text[start:end]])
        prepared.append({**case, "char_length": len(text), "length_band": band(len(text)),
                         "stored_text": stored_text, "stored_pair": stored_pair,
                         "dictionary_reading_partition_found": len(text) in reachable,
                         "dictionary_reading_partition": parts.get(len(text)), "forms": forms})
    return prepared


def metric(rows):
    count = len(rows)
    return {"requests": count, "top1": sum(row.get("text_rank") == 1 for row in rows),
            "top9": sum(row.get("text_rank") is not None and row["text_rank"] <= 9 for row in rows),
            "top90": sum(row.get("text_rank") is not None for row in rows),
            "pair_top90": sum(row.get("pair_rank") is not None for row in rows),
            "errors": sum("error" in row for row in rows),
            "constraint_failures": sum(len(row.get("violations", [])) for row in rows),
            "truncated": sum(row.get("truncated", False) for row in rows),
            "target_first_character_in_first9": sum(row.get("prefix1_available", False) for row in rows),
            "target_first_two_characters_in_first9": sum(row.get("prefix2_available", False) for row in rows)}


def quality_decision(rows, cases, policy):
    ordinary = [case for case in cases if case["case_role"] == "ordinary" and len(case["text"]) >= 4]
    coverage = policy["authored_coverage"]
    checks = {
        "ordinary_case_count": len(ordinary) >= coverage["minimum_ordinary_cases_4plus_chars"],
        "length_band_coverage": all(sum(case["length_band"] == value for case in ordinary) >= coverage["minimum_cases_per_length_band"] for value in coverage["length_bands"]),
        "topic_coverage": len({case["category"] for case in ordinary}) >= coverage["minimum_topic_categories"],
        "unstored_whole_text_coverage": bool(ordinary) and sum(not case["stored_text"] for case in ordinary) / len(ordinary) >= coverage["minimum_expected_text_absent_dictionary_fraction"],
        "habitual_ng_coverage": sum(bool(case.get("user_input")) for case in ordinary) >= coverage["minimum_ordinary_habitual_ng_cases"],
        "no_errors_or_constraints": not any("error" in row or row["violations"] for row in rows),
    }
    target = policy["authored_quality_required_for_each_profile"]
    for form in ("plain_yale_compact", "habitual_ng_compact"):
        group_target = target if form == "plain_yale_compact" else target["additional_required_input_group"]
        fresh = metric([row for row in rows if row["quality_case"] and row["profile"] == "fresh" and row["form"] == form])
        for profile in PROFILES:
            selected = [row for row in rows if row["quality_case"] and row["profile"] == profile and row["form"] == form]
            result = metric(selected)
            size = result["requests"]
            checks[f"{profile}:{form}:top9"] = bool(size) and result["top9"] / size >= group_target.get("minimum_top9_fraction_overall", group_target.get("minimum_top9_fraction"))
            checks[f"{profile}:{form}:top90"] = bool(size) and result["top90"] / size >= group_target.get("minimum_top90_fraction_overall", group_target.get("minimum_top90_fraction"))
            checks[f"{profile}:{form}:learning_decline"] = (bool(size) and size == fresh["requests"]
                and 100 * (fresh["top9"] - result["top9"]) / size <= group_target["maximum_top9_decline_from_fresh_percentage_points"])
            if form == "plain_yale_compact":
                for length_band in coverage["length_bands"]:
                    group = metric([row for row in selected if row["length_band"] == length_band])
                    checks[f"{profile}:{form}:{length_band}:top9"] = (bool(group["requests"])
                        and group["top9"] / group["requests"] >= target["minimum_top9_fraction_each_length_band"])
    return {"passed": all(checks.values()), "checks": checks,
            "scope": "Authored quality and coverage gates only. External replay, dedicated latency, robustness and installed x64 checks are separate release requirements."}


def run(args):
    paths = [args.fixture, POLICY, GRID, DATABASE, Path(__file__).resolve(),
             *(ROOT / "cantonese_ime" / item for item in ("engine.py", "mappings.py", "session.py", "__init__.py"))]
    pins = {path.relative_to(ROOT).as_posix(): sha(path) for path in paths}
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if pins["cantonese_ime/engine.py"] != policy["candidate_engine_sha256"]:
        raise ValueError("Engine differs from the candidate frozen by the policy")
    if args.output.exists() or args.output.resolve().is_relative_to(ROOT / "cantonese_ime"):
        raise ValueError("Choose a fresh report path outside production code")
    with closing(sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        cases = prepare_cases(fixture, connection)
    report = {"schema_version": 1, "kind": "authored_long_phrase_development_review",
              "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "input_sha256": pins,
              "scope": "Public authored phrases; no personal history, no installed broker/UI. Timing is contended and diagnostic only.",
              "held_out_accuracy_claim": False, "cases": cases, "profiles": {}, "rows": []}
    total = sum(len(case["forms"]) for case in cases) * len(PROFILES)
    with tempfile.TemporaryDirectory(prefix="cantonese-phrase-review-") as directory:
        for profile in PROFILES:
            memory = None if profile == "fresh" else Path(directory) / (profile + ".json")
            started = time.perf_counter()
            with Engine(DATABASE, learning_path=memory) as engine:
                initialization_ms = (time.perf_counter() - started) * 1000
                if profile != "fresh":
                    for raw, text in SHORT if profile == "short_preferences" else HEAVY:
                        choice = next((item for item in engine.lookup(raw, limit=90) if item.text == text), None)
                        if choice is None:
                            raise ValueError(f"Cannot select synthetic seed {raw}/{text}; do not forge history")
                        for _ in range(2 if profile == "short_preferences" else 30):
                            engine.record_selection(raw, choice)
                before = sha(memory) if memory is not None else None
                report["profiles"][profile] = {"initialization_ms": round(initialization_ms, 3), "synthetic_units": 0 if profile == "fresh" else len(SHORT if profile == "short_preferences" else HEAVY)}
                for case in cases:
                    for form, raw, mode in case["forms"]:
                        row = {"case_id": case["id"], "expected": case["text"], "reading": case["reading"],
                               "profile": profile, "form": form, "input": raw, "mode": mode,
                               "quality_case": case["case_role"] == "ordinary" and case["char_length"] >= 4,
                               "length_band": case["length_band"], "category": case["category"],
                               "stored_pair": case["stored_pair"], "stored_text": case["stored_text"], "violations": []}
                        started = time.perf_counter()
                        try:
                            page = engine.lookup_page(raw, page_size=90, mode=mode)
                            candidates = page.candidates
                            row.update(text_rank=next((i + 1 for i, item in enumerate(candidates) if item.text == case["text"]), None),
                                       pair_rank=next((i + 1 for i, item in enumerate(candidates) if item.text == case["text"] and item.reading == case["reading"]), None),
                                       truncated=page.completion_truncated,
                                       first9=[{"text": item.text, "reading": item.reading, "match_type": item.match_type} for item in candidates[:9]],
                                       candidate_count=len(candidates),
                                       prefix1_available=any(item.text.startswith(case["text"][:1]) for item in candidates[:9]),
                                       prefix2_available=any(item.text.startswith(case["text"][:2]) for item in candidates[:9]))
                            if len(candidates) > 90 or len({item.text for item in candidates}) != len(candidates):
                                row["violations"].append("candidate_count_or_duplicates")
                            for item in candidates:
                                if item.consumed_input != len(raw) or not item.text or not math.isfinite(item.score):
                                    row["violations"].append("consumption_or_empty_text_or_nonfinite_score")
                        except Exception as error:
                            row["error"] = f"{type(error).__name__}: {error}"
                        row["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
                        report["rows"].append(row)
                        if len(report["rows"]) % 100 == 0:
                            print(json.dumps({"progress": len(report["rows"]), "total": total}), flush=True)
                report["profiles"][profile]["lookup_history_unchanged"] = memory is None or before == sha(memory)
    after = {path.relative_to(ROOT).as_posix(): sha(path) for path in paths}
    report["inputs_unchanged"] = pins == after
    report["summary"] = {f"{profile}:{form}": metric([row for row in report["rows"] if row["quality_case"] and row["profile"] == profile and row["form"] == form])
                         for profile in PROFILES for form in sorted({row["form"] for row in report["rows"]})}
    report["authored_gate"] = quality_decision(report["rows"], cases, policy)
    report["run_completed_without_errors"] = report["inputs_unchanged"] and not any("error" in row or row["violations"] for row in report["rows"])
    write(args.output, report)
    print(json.dumps({"report": str(args.output), "summary": report["summary"], "authored_gate_passed": report["authored_gate"]["passed"],
                      "run_completed_without_errors": report["run_completed_without_errors"]}, indent=2), flush=True)
    return int(not report["run_completed_without_errors"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
