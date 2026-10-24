"""Replay a frozen incremental feature evaluation; synthetic history only.

Policy is written before every lookup, including seed selection. Do not use
these incremental gates as a replacement for the failed full-release policy.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
_parser = argparse.ArgumentParser(description="Replay the already evaluated cycle1 feature comparison. Supply trusted frozen candidate/baseline files; generated synthetic histories remain only under the fresh output directory.")
_parser.add_argument("--candidate", type=Path, default=ROOT / "eval/experiments/cycle1/nasal-prototype-merge-cost.py", help="Frozen candidate; its original sibling baseline filename is required")
_parser.add_argument("--baseline", type=Path, default=ROOT / "eval/experiments/cycle1/engine-a4e2-frozen.py", help="Must be the candidate sibling named engine-a4e2-frozen.py")
_parser.add_argument("--output", type=Path, required=True)
_parser.add_argument("--candidate-freeze", type=Path)
_args = _parser.parse_args()
OUT = _args.output.resolve()
FIXTURE = ROOT / "eval/self_improvement_cycle_1_cases.json"
DB = ROOT / "data/generated/lexicon.sqlite3"
CANDIDATE = _args.candidate.resolve()
BASELINE = _args.baseline.resolve()
if BASELINE != CANDIDATE.parent / "engine-a4e2-frozen.py":
    raise ValueError("The frozen candidate imports its co-located engine-a4e2-frozen.py; --baseline must name that exact sibling")
FREEZE = _args.candidate_freeze.resolve() if _args.candidate_freeze else None
for _path in (OUT,CANDIDATE,BASELINE):
    if not _path.is_relative_to(ROOT):
        raise ValueError("Replay paths must remain inside the project workspace")
if FREEZE is not None and not FREEZE.is_relative_to(ROOT):
    raise ValueError("Freeze proof must remain inside the project workspace")
EXPECTED_FIXTURE = "7b98789e1ea9c307f03a0f0c12dd13492be507500e38f15fdaa1efd158655d64"
EXPECTED_CANDIDATE = "37fbc0d115aad3ae9466a7737fc4a45c77cf0a2d67a720bb9a5eeacd6662451b"
EXPECTED_BASELINE = "a4e2d07c98adbb78b8a6978892827bd907a68cd658f06229d6493fbc05e3e141"
EXPECTED_REPLAY_INPUTS = {'data/generated/lexicon.sqlite3': 'bd312406a15162556ac58a257ede1514ad40890c793b6f8fa05084fda2d6241a', 'cantonese_ime/mappings.py': 'd61d6e7ab3b82bab7a31d42f7abfefb4f224eed5c9dbf505304eef2d940249e1', 'eval/yale_expected.json': '477f56a946625283e78417e75382d9682b68cbe877fb13e3a67d2bf5a0095745', 'data/mappings/syllables.json': '6ba71ec3b02e763be7f371b0c354945075bb974092454aaba4725d750b03ef02', 'data/mappings/spellings.json': '6726e07ec0751d8a2017d25eb494c416555c0bc70d744155e48cdd1b513abb60', 'data/mappings/build.manifest.json': '8a91d6f2ef6b0258edf63f82eb8fdbcffded0aca706a4456f359d2eab3016f39', 'tools/evaluate_long_phrases.py': '5a693edea8985581c45cbb75337e8357a233bb8c28756312509d8debdeee350a'}
PROFILES = ("fresh", "short_preferences", "heavy_short_preferences")
SHORT = (("ng", "唔"), ("ji", "字"), ("di", "啲"), ("go", "個"), ("bin", "邊"))
HEAVY = SHORT + (("ngo", "我"), ("nei", "你"), ("hai", "係"),
                 ("gam", "咁"), ("seung", "想"), ("hou", "好"), ("heui", "去"))
STRICT = ("strict_jyutping_toned", "strict_jyutping_tone_free")


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_state(path: Path | None) -> dict | None:
    if path is None:
        return None
    stat = path.stat()
    return {"sha256": sha(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def pool_data(candidates) -> list:
    # Class/module identity is intentionally excluded. float.hex retains the
    # exact finite binary float, including signed zero, rather than rounding.
    return [[c.text, c.reading, float(c.score).hex(), c.match_type, c.consumed_input]
            for c in candidates]


def hit(rank, cap=9) -> bool:
    return rank is not None and rank <= cap


def metrics(rows: list[dict]) -> dict:
    return {"requests": len(rows),
            "top1": sum(hit(r.get("text_rank"), 1) for r in rows),
            "top9": sum(hit(r.get("text_rank"), 9) for r in rows),
            "top90": sum(hit(r.get("text_rank"), 90) for r in rows),
            "pair_top90": sum(hit(r.get("pair_rank"), 90) for r in rows),
            "errors": sum("error" in r for r in rows),
            "violations": sum(len(r["violations"]) for r in rows),
            "completion_truncated": sum(bool(r.get("completion_truncated")) for r in rows)}


def lookup(engine, case: dict, form: str, raw: str, mode: str,
           model: str, profile: str, memory: Path | None,
           memory_before: dict | None) -> dict:
    row = {"model": model, "profile": profile, "case_id": case["id"],
           "split": case["split"], "group": case["group"],
           "category": case["category"], "length_band": case["length_band"],
           "expected": case["text"], "expected_reading": case["reading"],
           "form": form, "input": raw, "mode": mode,
           "text_rank": None, "pair_rank": None, "violations": []}
    begin = time.perf_counter()
    try:
        page = engine.lookup_page(raw, page_size=90, mode=mode)
        candidates = page.candidates
        if type(page.offset) is not int or page.offset != 0:
            row["violations"].append("invalid_page_offset")
        if page.next_offset is not None and (type(page.next_offset) is not int or page.next_offset != len(candidates)):
            row["violations"].append("invalid_next_offset")
        if type(page.completion_truncated) is not bool:
            row["violations"].append("invalid_truncation_flag")
        if len(candidates) > 90:
            row["violations"].append("more_than90_candidates")
        if len({c.text for c in candidates}) != len(candidates):
            row["violations"].append("duplicate_candidate_text")
        for c in candidates:
            if not isinstance(c.text, str) or not c.text:
                row["violations"].append("empty_or_nontext_candidate")
            if not isinstance(c.reading, str) or not c.reading or not all(re.fullmatch(r"[a-z]+[1-6]", t) for t in c.reading.split()):
                row["violations"].append("invalid_reading_metadata")
            if type(c.consumed_input) is not int or c.consumed_input != len(raw):
                row["violations"].append("input_consumption_mismatch")
            if not isinstance(c.score, (int, float)) or isinstance(c.score, bool) or not math.isfinite(c.score):
                row["violations"].append("nonfinite_or_invalid_score")
            if c.match_type not in ("exact", "fuzzy", "composed", "completion", "learned"):
                row["violations"].append("invalid_match_type")
        row.update(
            text_rank=next((i+1 for i,c in enumerate(candidates) if c.text == case["text"]), None),
            pair_rank=next((i+1 for i,c in enumerate(candidates) if c.text == case["text"] and c.reading == case["reading"]), None),
            candidate_count=len(candidates),
            page={"offset":page.offset, "next_offset":page.next_offset,
                  "completion_truncated":page.completion_truncated},
            completion_truncated=page.completion_truncated,
            first9=[{"text":c.text, "reading":c.reading, "score_hex":float(c.score).hex(),
                     "match_type":c.match_type, "consumed_input":c.consumed_input} for c in candidates[:9]],
            pool_sha256=digest(pool_data(candidates)),
        )
    except Exception as error:
        row["error"] = f"{type(error).__name__}: {error}"
    row["elapsed_ms"] = round((time.perf_counter()-begin)*1000, 4)
    row["lookup_history_unchanged"] = file_state(memory) == memory_before
    if not row["lookup_history_unchanged"]:
        row["violations"].append("history_changed_by_lookup")
    return row



def public_projection(report, raw_report_sha256=None, timing=None):
    """Retain public/synthetic results, excluding history contents/paths."""
    kept = {key:value for key,value in report.items()
            if key not in ("source_sha256_before","source_sha256_after",
                           "seed_source_pins","history_profiles")}
    prefixes=("cantonese_ime/","data/","eval/","tools/","docs/")
    for label in ("source_sha256_before","source_sha256_after"):
        kept[label]={name:value for name,value in report[label].items()
                     if name.startswith(prefixes)}
    kept["startup_ms"]={label:info["initialization_ms"]
                        for label,info in report["history_profiles"].items()}
    kept["history_guard_summary"]={
        label:{"lookup_history_unchanged":info["lookup_history_unchanged"],
               "same_initial_bytes_as_baseline_created_source":info["same_initial_bytes_as_baseline_created_source"]}
        for label,info in report["history_profiles"].items()}
    kept["frozen_feature_sources"]={
        "candidate_code_sha256":"37fbc0d115aad3ae9466a7737fc4a45c77cf0a2d67a720bb9a5eeacd6662451b",
        "baseline_engine_sha256":"a4e2d07c98adbb78b8a6978892827bd907a68cd658f06229d6493fbc05e3e141",
        "fixture_sha256":"7b98789e1ea9c307f03a0f0c12dd13492be507500e38f15fdaa1efd158655d64"}
    kept["retention"]={
        "immutable_original_report_sha256":raw_report_sha256,
        "original_execution_harness_sha256":report["source_sha256_before"].get(Path(__file__).resolve().relative_to(ROOT).as_posix()),
        "prior_frozen_review_harness_sha256":"73b942ee4e0035be7a1e37b6042f0a4e67d0a5e59609b3205157f22572fd83ff",
        "replay_harness":"../tools/evaluate_self_improvement_cycle1.py",
        "acceptance_policy":"self-improvement-cycle1-feature-policy.json",
        "harness_adaptation":"The retained CLI replay harness was parameterized after the original run. The immutable report pins the original executed harness; a later replay is not a new blind validation.",
        "privacy":"Learning-store contents, history filenames/mtimes and nonpublic source paths are excluded. All saved fixture inputs/candidates are public project-authored material.",
        "completed_run_source_guard_scope":"Before/after pins describe the completed frozen run. Later production integration does not overwrite that evidence."}
    if timing is not None:
        kept["timing_comparison"]=timing
    return kept


def main() -> None:
    assert sha(CANDIDATE) == EXPECTED_CANDIDATE
    assert sha(BASELINE) == EXPECTED_BASELINE
    assert sha(FIXTURE) == EXPECTED_FIXTURE
    if FREEZE is not None:
        freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
        assert freeze["candidate_code_sha256"] == EXPECTED_CANDIDATE
    for name, expected in EXPECTED_REPLAY_INPUTS.items():
        if sha(ROOT / name) != expected:
            raise ValueError("Replay input differs from frozen evidence: " + name)
    if any(OUT.is_relative_to(ROOT / name) for name in ("cantonese_ime", "data", "eval", "tools", "docs")):
        raise ValueError("Choose an output directory outside source/data/documentation trees")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=False)
    policy_path = OUT / "feature-acceptance-policy-before-lookups.json"
    policy = {
        "schema_version": 1, "recorded_at_utc": stamp(),
        "kind": "incremental_opt_in_nasal_input_feature_acceptance",
        "fixture_sha256": EXPECTED_FIXTURE, "candidate_sha256": EXPECTED_CANDIDATE,
        "baseline_sha256": EXPECTED_BASELINE,
        "feature": {"syllabic_m_as_ng": True, "alias_cost": 0.8, "default": False},
        "recorded_before_seed_and_evaluation_lookups": True,
        "validation_rules": {
            "proper_yale_compact_all30": "Zero new exact-text first9 losses against baseline, for each of three histories.",
            "nasal_and_ordinary_controls": "Zero new exact-text first9 losses on validation nasal/ordinary controls across all four primary/diagnostic forms, per history.",
            "habitual_ng_fresh10": "Candidate first9 hit count minus baseline first9 hit count at least2.",
            "habitual_ng_learned10": "Candidate first9 hit count at least baseline first9 count for each short/heavy history; all individual losses remain reported.",
        },
        "contract_rules": {
            "strict_modes": "Type-independent serialized first90 candidate pools and page metadata identical for both strict Jyutping forms, all60 cases and all histories.",
            "disabled_behavior": "Explicitly disabled candidate must match baseline pools/page metadata on all260 fresh requests.",
            "runtime": "Zero exceptions, invalid page/reading metadata, consumption mismatches, nonfinite scores, duplicate texts or lookup history mutations.",
            "source_guards": "Fixture, candidate, baseline, runtime/data, runner and this policy must retain their recorded SHA256 after the run.",
            "history_identity": "Create each learned history once through actual baseline record_selection, preserve old ng4 seed reading and clone identical bytes per model/profile. Never seed models independently.",
        },
        "histories": {"fresh": None, "short_preferences": {"units":5, "repetitions_each":2},
                      "heavy_short_preferences": {"units":12, "repetitions_each":30}},
        "scope": "Replay of previously evaluated cycle1 cases, not new blind validation or representative/held-out language accuracy. Incremental feature gates do not replace failed90% sentence release gates.",
        "full_release_quality_gates_replaced": False,
        "expected_evaluation_requests": 1820,
        "expected_paired_requests": 1560,
        "expected_disabled_requests": 260,
    }
    write_new(policy_path, policy)
    # This persisted policy precedes imports/initialization of any engine and
    # therefore precedes even seed lookup/selection.
    print(json.dumps({"phase":"policy_recorded_before_lookups", "policy_sha256":sha(policy_path)}), flush=True)
    paths = [FIXTURE, DB, CANDIDATE, BASELINE, Path(__file__), policy_path,
             ROOT / "tools/evaluate_long_phrases.py", ROOT / "eval/yale_expected.json",
             ROOT / "data/mappings/syllables.json", ROOT / "data/mappings/spellings.json",
             ROOT / "data/mappings/build.manifest.json", ROOT / "docs/long-phrase-release-decision.json",
             ROOT / "eval/long_phrase_release_policy.json", ROOT / "eval/long_phrase_review_cases.json"]
    if FREEZE is not None:
        paths.append(FREEZE)
    paths.extend(sorted((ROOT / "cantonese_ime").glob("*.py")))
    pins = {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}
    write_new(OUT / "inputs-before-queries.json", {"recorded_at_utc":stamp(),"source_sha256":pins})
    sys.path.insert(0, str(ROOT))
    helper = load("cycle1_frozen_review_helpers", ROOT / "tools/evaluate_long_phrases.py")
    candidate = load("cycle1_frozen_nasal_candidate", CANDIDATE)
    assert sha(Path(candidate.frozen.__file__)) == EXPECTED_BASELINE
    baseline_type = candidate.BaselineEngine
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True)) as con:
        con.execute("PRAGMA query_only=ON")
        cases = helper.prepare_cases(fixture, con)
    assert len(cases) == 60 and sum(len(c["forms"]) for c in cases) == 260
    write_new(OUT / "prepared-cases.json", {"fixture_sha256":sha(FIXTURE),"cases":cases})

    # Seed each profile ONCE with the baseline; do not forge schema/counts or
    # allow the candidate to choose a different reading for the same seed text.
    histories = {}
    source_states = {}
    seeds = {}
    for profile, units, repetitions in (("short_preferences",SHORT,2), ("heavy_short_preferences",HEAVY,30)):
        path = OUT / "histories" / (profile+"-source.json")
        path.parent.mkdir(parents=True,exist_ok=True)
        selected_records = []
        print(json.dumps({"phase":"create_baseline_history_once","profile":profile}),flush=True)
        with baseline_type(DB,learning_path=path,prefer_yale=True) as engine:
            for raw, text in units:
                available = engine.lookup(raw,limit=90,mode="forgiving")
                selection = next((c for c in available if c.text==text),None)
                if selection is None:
                    raise RuntimeError("Baseline synthetic seed unavailable: "+raw)
                if raw=="ng":
                    assert selection.reading=="ng4", "Keep baseline's old ng4 history; do not silently reseed to m4"
                selected_records.append({"input":raw,"text":text,"reading":selection.reading,
                                         "candidate_rank":available.index(selection)+1,
                                         "candidate_fields":pool_data([selection])[0],
                                         "pool_sha256_at_selection":digest(pool_data(available)),
                                         "record_selection_calls":repetitions})
                for _ in range(repetitions):
                    engine.record_selection(raw,selection,mode="forgiving")
        data = path.read_bytes()
        payload = json.loads(data)
        assert len(payload["selections"])==len(units)
        assert next(r for r in payload["selections"] if r["input"]=="ng")["reading"]=="ng4"
        histories[profile]=path
        source_states[profile]=file_state(path)
        seeds[profile]={"units":len(units),"repetitions":repetitions,
                        "source_path":path.relative_to(ROOT).as_posix(),
                        "source_state":source_states[profile],"selected_records":selected_records,
                        "initial_stored_records":payload}
    seed_path = OUT / "baseline-created-seed-records.json"
    write_new(seed_path,{"created_at_utc":stamp(),"provenance":"New synthetic actual baseline selections; never personal history.","histories":seeds})
    seed_pins = {seed_path.relative_to(ROOT).as_posix():sha(seed_path)}
    seed_pins.update({p.relative_to(ROOT).as_posix():sha(p) for p in histories.values()})
    write_new(OUT / "history-pins-before-evaluation.json",{"source_sha256":seed_pins,"source_states":source_states})

    rows = []
    profile_records = {}
    journal_path = OUT / "requests.jsonl"
    total=1820
    with journal_path.open("x",encoding="utf-8",newline="\n") as journal:
        for model in ("baseline","candidate","disabled"):
            for profile in (("fresh",) if model=="disabled" else PROFILES):
                memory = None
                if profile != "fresh":
                    source = histories[profile]
                    memory = OUT / "histories" / (model+"-"+profile+".json")
                    with memory.open("xb") as stream:
                        stream.write(source.read_bytes())
                    assert sha(memory)==source_states[profile]["sha256"]
                before=file_state(memory)
                engine_type = baseline_type if model=="baseline" else candidate.NasalInputEngine
                kwargs = {} if model=="baseline" else {"syllabic_m_as_ng":model=="candidate"}
                begin=time.perf_counter()
                with engine_type(DB,learning_path=memory,prefer_yale=True,**kwargs) as engine:
                    startup=(time.perf_counter()-begin)*1000
                    print(json.dumps({"phase":"evaluation_started","model":model,"profile":profile,"completed_requests":len(rows),"initialization_ms":round(startup,3)}),flush=True)
                    for case in cases:
                        for form,raw,mode in case["forms"]:
                            row=lookup(engine,case,form,raw,mode,model,profile,memory,before)
                            rows.append(row)
                            journal.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+"\n")
                            journal.flush()
                            if len(rows)%50==0:
                                print(json.dumps({"phase":"progress","completed":len(rows),"total":total,"model":model,"profile":profile}),flush=True)
                profile_records[model+":"+profile]={"initialization_ms":round(startup,4),
                    "history_path":memory.relative_to(ROOT).as_posix() if memory else None,
                    "history_before":before,"history_after":file_state(memory),
                    "lookup_history_unchanged":before==file_state(memory),
                    "same_initial_bytes_as_baseline_created_source":memory is None or before["sha256"]==source_states[profile]["sha256"]}
    assert len(rows)==1820
    index={(r["model"],r["profile"],r["case_id"],r["form"]):r for r in rows}
    comparisons=[]
    for old in (r for r in rows if r["model"]=="baseline"):
        new=index["candidate",old["profile"],old["case_id"],old["form"]]
        rank_old=old["text_rank"] if old["text_rank"] is not None else 91
        rank_new=new["text_rank"] if new["text_rank"] is not None else 91
        comparisons.append({k:old[k] for k in ("profile","case_id","split","group","category","length_band","form","input","expected")}|{
            "baseline_rank":old["text_rank"],"candidate_rank":new["text_rank"],
            "rank_delta_capped91":rank_old-rank_new,
            "rank_direction":"improved" if rank_new<rank_old else "worsened" if rank_new>rank_old else "unchanged",
            "new_top9_gain":not hit(old["text_rank"]) and hit(new["text_rank"]),
            "new_top9_loss":hit(old["text_rank"]) and not hit(new["text_rank"]),
            "new_top90_loss":hit(old["text_rank"],90) and not hit(new["text_rank"],90),
            "pool_identical":old.get("pool_sha256") is not None and old.get("pool_sha256")==new.get("pool_sha256") and old.get("page")==new.get("page")})
    disabled_mismatches=[]
    for disabled in (r for r in rows if r["model"]=="disabled"):
        old=index["baseline","fresh",disabled["case_id"],disabled["form"]]
        if not (old.get("pool_sha256") is not None and old.get("pool_sha256")==disabled.get("pool_sha256") and old.get("page")==disabled.get("page")):
            disabled_mismatches.append({"case_id":disabled["case_id"],"form":disabled["form"]})
    strict_mismatches=[r for r in comparisons if r["form"] in STRICT and not r["pool_identical"]]
    checks={}
    for profile in PROFILES:
        proper=[r for r in comparisons if r["profile"]==profile and r["split"]=="validation" and r["form"]=="plain_yale_compact"]
        controls=[r for r in comparisons if r["profile"]==profile and r["split"]=="validation" and r["group"] in ("nasal_control","ordinary_control")]
        assert len(proper)==30 and len(controls)==80
        checks[profile+":validation_proper_yale_no_new_top9_loss"]=not any(r["new_top9_loss"] for r in proper)
        checks[profile+":validation_controls_allforms_no_new_top9_loss"]=not any(r["new_top9_loss"] for r in controls)
        habitual=[r for r in comparisons if r["profile"]==profile and r["split"]=="validation" and r["form"]=="habitual_ng_compact"]
        assert len(habitual)==10
        delta=sum(hit(r["candidate_rank"]) for r in habitual)-sum(hit(r["baseline_rank"]) for r in habitual)
        checks[profile+":validation_habitual_ng_required_delta"]=delta >= (2 if profile=="fresh" else 0)
    after={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}
    source_unchanged=pins==after
    histories_unchanged=all(file_state(histories[p])==source_states[p] for p in histories)
    history_guard=all(r["lookup_history_unchanged"] for r in rows) and all(v["lookup_history_unchanged"] for v in profile_records.values()) and histories_unchanged
    seed_files_unchanged=all(sha(ROOT/name)==value for name,value in seed_pins.items())
    checks.update({"strict_first90_pool_and_page_identical":not strict_mismatches,
                   "disabled_fresh_all260_pool_and_page_identical":not disabled_mismatches,
                   "zero_runtime_metadata_consumption_finite_duplicate_errors":not any("error" in r or r["violations"] for r in rows),
                   "fixture_runtime_policy_source_guards_unchanged":source_unchanged,
                   "baseline_created_history_bytes_lookup_unchanged":history_guard and seed_files_unchanged,
                   "paired_model_initial_histories_identical":all(v["same_initial_bytes_as_baseline_created_source"] for v in profile_records.values())})
    paired=[r for r in rows if r["model"]!="disabled"]
    def stratify(fields):
        groups=defaultdict(list)
        for r in paired:
            groups[tuple(r[f] for f in fields)].append(r)
        return [{**dict(zip(fields,key)),**metrics(value)} for key,value in sorted(groups.items())]
    report={"schema_version":1,"kind":"cycle1_frozen_incremental_nasal_feature_replay",
            "started_policy_at_utc":policy["recorded_at_utc"],"completed_at_utc":stamp(),
            "scope":"Source-engine public/synthetic fixtures only; no personal history, installed broker/UI or performance acceptance. Replay of previously evaluated labels, not a new blind validation or representative/held-out language accuracy.",
            "feature_policy_sha256":sha(policy_path),"source_sha256_before":pins,"source_sha256_after":after,
            "source_files_unchanged":source_unchanged,"seed_source_pins":seed_pins,
            "history_provenance":"Each source created once by real frozen baseline selections, including ng4, then cloned byte-identically; never different per-model seed readings.",
            "history_profiles":profile_records,"history_sources_unchanged":histories_unchanged,
            "pool_serialization":"UTF8 canonical JSON ordered array of [text,reading,float(score).hex(),match_type,consumed_input]; dataclass/module identity excluded. Full first90 pools and page metadata compared.",
            "request_counts":{"paired":len(paired),"disabled":len(rows)-len(paired),"total":len(rows),"explicit_seed_lookup_requests":17,"record_selection_calls":370},
            "summary_by_model_profile_split_form":stratify(("model","profile","split","form")),
            "summary_by_model_profile_split_group_form":stratify(("model","profile","split","group","form")),
            "summary_by_model_profile_split_length_form":stratify(("model","profile","split","length_band","form")),
            "summary_by_model_profile_split_category_form":stratify(("model","profile","split","category","form")),
            "all_signed_rank_comparisons":comparisons,
            "all_signed_rank_losses":[r for r in comparisons if r["rank_direction"]=="worsened"],
            "all_new_top9_losses":[r for r in comparisons if r["new_top9_loss"]],
            "strict_first90_mismatches":strict_mismatches,
            "disabled_fresh_mismatches":disabled_mismatches,
            "incremental_feature_gate":{"passed":all(checks.values()),"checks":checks,
                "full_sentence_release_quality_gates_replaced":False,
                "interpretation":"A pass means only the preregistered opt-in feature comparison passed. The old overall90% sentence-quality gate remains failed and unchanged."},
            "rows":rows}
    write_new(OUT / "report.json",report)
    write_new(OUT / "public-report.json",public_projection(report,sha(OUT / "report.json")))
    write_new(OUT / "signed-losses.json",{"source_report_sha256":sha(OUT/"report.json"),
        "all_signed_rank_losses":report["all_signed_rank_losses"],"all_new_top9_losses":report["all_new_top9_losses"]})
    aggregate=[r for r in report["summary_by_model_profile_split_form"] if r["split"]=="validation" and r["form"] in ("plain_yale_compact","habitual_ng_compact")]
    print(json.dumps({"phase":"completed","report_sha256":sha(OUT/"report.json"),
                      "incremental_feature_gate":report["incremental_feature_gate"],
                      "validation_aggregates":aggregate,
                      "all_signed_rank_loss_count":len(report["all_signed_rank_losses"]),
                      "all_new_top9_loss_count":len(report["all_new_top9_losses"]),
                      "strict_pool_mismatch_count":len(strict_mismatches),
                      "disabled_pool_mismatch_count":len(disabled_mismatches)},ensure_ascii=False,indent=2),flush=True)


if __name__=="__main__":
    main()
