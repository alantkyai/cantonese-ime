"""Run bounded synthetic decoder checks; no language model or IME imports."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

import context_decoder
import test_context_decoder


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/context-search/mechanical.json")
    args = parser.parse_args()
    output = args.output.resolve()
    log = output.with_suffix(".tests.txt")
    if not output.is_relative_to(ROOT) or output.suffix != ".json":
        raise ValueError("Choose a fresh JSON output inside this repository")
    if output.exists() or log.exists():
        raise FileExistsError("Existing evidence is preserved; choose a fresh output")
    paths = [HERE / name for name in ("context_decoder.py", "test_context_decoder.py", "run_mechanical_checks.py", "README.md")]
    guards = [ROOT / "cantonese_ime/engine.py", ROOT / "cantonese_ime/mappings.py"]
    before = {path.relative_to(ROOT).as_posix(): sha(path) for path in paths + guards}
    stream = io.StringIO()
    started = time.perf_counter()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_context_decoder))
    elapsed = time.perf_counter() - started
    after = {path.relative_to(ROOT).as_posix(): sha(path) for path in paths + guards}
    imported_product = sorted(name for name in sys.modules if name == "cantonese_ime" or name.startswith("cantonese_ime."))
    output.parent.mkdir(parents=True, exist_ok=True)
    with log.open("x", encoding="utf-8", newline="\n") as target:
        target.write(stream.getvalue())
    passed = result.wasSuccessful() and before == after and not imported_product
    data = {
        "schema_version": 1,
        "kind": "synthetic_context_conditioned_kbest_mechanical_check",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "source_sha256_before": before, "source_sha256_after": after,
        "source_guards_unchanged": before == after,
        "tests": {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped), "elapsed_seconds": elapsed},
        "oracle_comparisons": test_context_decoder.ORACLE_COMPARISONS,
        "random_graphs": 320, "random_comparisons": 2880, "random_seed": 20261024,
        "objective": "Nonnegative integer lexical plus character-bigram cost; exact topK distinct written texts on the supplied retained DAG. Equal-score same-text pronunciations choose greatest reading string.",
        "state": "input_position,incoming_character",
        "checked_properties": ["exhaustive independent path enumeration agreement", "whole-output segmentation-invariant character cost",
                               "context-conditioned child stream ordering", "same-cost reading ties at the K cutoff",
                               "text dedup before K", "more than90 unique outputs", "zero-cost advancing paths",
                               "Unicode and lexical-prefix tie order", "explicit capacity failures with no partial Result",
                               "finite reservations before generated strings, state/transition publication and heap insertion",
                               "immutable model/results", "invalid graph/cost/budget parameters rejected"],
        "naive_suffix_reranker_counterexample": {"lexical_suffixes": {"a": 1, "b": 2},
                                                "prefix_x_total_cost": {"xa": 5, "xb": 2},
                                                "other_stream_z": 3, "naive_top1": "z", "correct_top1": "xb"},
        "default_limits": asdict(context_decoder.Limits()),
        "limits_are_logical_not_process_rss": True,
        "scope": {"synthetic_data_only": True, "product_modules_imported": imported_product,
                  "engine_queries": 0, "dictionary_opened": False, "history_opened": False,
                  "language_quality_claim": False, "production_enabled": False,
                  "floating_point_exact_order_proved": False,
                  "retained_graph_only": True,
                  "learned_profile_context_calibration_solved": False},
        "limitations": ["Cannot recover arcs discarded before the supplied DAG.",
                        "Integer costs prove the tested objective; floats retain ordinary association/ULP limits.",
                        "Budgets count cumulative logical work/UTF8 bytes, not Python RSS; caller-owned inputs have separate finite preparation bounds.",
                        "Fresh-only integration hook is design guidance in README, not a shipped feature or personalized-decoder proof."],
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "test_log": log.relative_to(ROOT).as_posix(), "test_log_sha256": sha(log),
    }
    with output.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(data, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write("\n")
    print(json.dumps({"status": data["status"], "tests": data["tests"], "oracle_comparisons": data["oracle_comparisons"],
                      "report": output.relative_to(ROOT).as_posix(), "sha256": sha(output)}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
