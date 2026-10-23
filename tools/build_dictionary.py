"""Build the pinned offline Cantonese lexicon; no network or installation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cantonese_ime.dictionary import build_dictionary, file_sha256, verify_source_files


def _verify_supplement_snapshot(kind: str, directory: Path, lock: dict) -> None:
    if kind == "wordshk":
        from cantonese_ime.wordshk import verify_wordshk_snapshot
        verify_wordshk_snapshot(directory, lock)
    elif kind == "typeduck":
        from cantonese_ime.typeduck import verify_typeduck_snapshot
        verify_typeduck_snapshot(directory, lock)
    elif kind == "unihan":
        from cantonese_ime.unihan import verify_unihan_snapshot
        verify_unihan_snapshot(directory, lock)
    elif kind in ("cccanto", "cccedict_cantonese"):
        from cantonese_ime.cccanto import verify_cccanto_snapshot
        verify_cccanto_snapshot(directory, lock)
    elif kind == "wordnet":
        from cantonese_ime.wordnet import verify_wordnet_snapshot
        verify_wordnet_snapshot(directory, lock)
    elif kind == "cccedict_headwords":
        from cantonese_ime.cccedict_headwords import verify_cccedict_headwords_snapshot
        verify_cccedict_headwords_snapshot(directory, lock)
    elif kind == "yue_wiktionary":
        from cantonese_ime.yue_wiktionary import verify_yue_wiktionary_snapshot
        verify_yue_wiktionary_snapshot(directory, lock)
    else:
        verify_source_files(directory, lock)


def main() -> int:
    if callable(getattr(sys.stdout, "reconfigure", None)):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=PROJECT_ROOT / "data" / "sources.lock.json")
    parser.add_argument("--source-dir", type=Path, help="Override the pinned snapshot location (hashes still checked)")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "generated" / "lexicon.sqlite3")
    parser.add_argument("--no-autoencode", action="store_true", help="Build only explicit readings (diagnostic baseline)")
    parser.add_argument("--no-supplements", action="store_true", help="Omit supplemental sources (diagnostic baseline)")
    parser.add_argument("--cccedict-headwords-lock", type=Path,
                        help="Override the default pinned Han-headword snapshot; explicit selection requires autoencoding")
    parser.add_argument("--yue-wiktionary-lock", type=Path,
                        help="Override the default pinned explicit Yue snapshot appended after all generation")
    parser.add_argument("--no-cccedict-headwords", action="store_true",
                        help="Diagnostic: omit default CC-CEDICT Han-headword generation")
    parser.add_argument("--no-yue-wiktionary", action="store_true",
                        help="Diagnostic: omit default explicit Yue Wiktionary pairs")
    parser.add_argument("--progress", action="store_true", help="Report phrase progress to stderr")
    args = parser.parse_args()
    if args.cccedict_headwords_lock is not None and (args.no_supplements or args.no_autoencode or args.no_cccedict_headwords):
        parser.error("--cccedict-headwords-lock requires supplements and autoencoding")
    if args.yue_wiktionary_lock is not None and (args.no_supplements or args.no_yue_wiktionary):
        parser.error("--yue-wiktionary-lock requires supplements")
    selected_headword_lock = args.cccedict_headwords_lock
    if selected_headword_lock is None and not (args.no_supplements or args.no_autoencode or args.no_cccedict_headwords):
        selected_headword_lock = PROJECT_ROOT / "data/supplements/cccedict-headwords.sources.lock.json"
    selected_yue_lock = args.yue_wiktionary_lock
    if selected_yue_lock is None and not (args.no_supplements or args.no_yue_wiktionary):
        selected_yue_lock = PROJECT_ROOT / "data/supplements/yue-wiktionary.sources.lock.json"
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    source_dir = args.source_dir or PROJECT_ROOT / lock["local_directory"]
    verify_source_files(source_dir, lock)
    guarded_files = {args.lock: file_sha256(args.lock)}
    selected_snapshots = []
    supplements = {}
    supplement_sources = {}
    if not args.no_supplements:
        for kind, lock_path, filename in (
            ("lshk", PROJECT_ROOT / "data/mappings/lshk.sources.lock.json", "list.tsv"),
            ("wordshk", PROJECT_ROOT / "data/supplements/wordshk.sources.lock.json", "wordslist.json"),
            ("typeduck", PROJECT_ROOT / "data/supplements/typeduck.sources.lock.json", "jyut6ping3.dict.yaml"),
            ("unihan", PROJECT_ROOT / "data/supplements/unihan.sources.lock.json", "Unihan_Readings.txt"),
            ("cccanto", PROJECT_ROOT / "data/supplements/cccanto.sources.lock.json", "cccanto-webdist.txt"),
            ("cccedict_cantonese", PROJECT_ROOT / "data/supplements/cccanto.sources.lock.json", "cccedict-canto-readings-150923.txt"),
            ("wordnet", PROJECT_ROOT / "data/supplements/wordnet.sources.lock.json", "cantown.xml"),
        ):
            supplementary_lock = json.loads(lock_path.read_text(encoding="utf-8"))
            directory = PROJECT_ROOT / supplementary_lock["local_directory"]
            _verify_supplement_snapshot(kind, directory, supplementary_lock)
            guarded_files[lock_path] = file_sha256(lock_path)
            selected_snapshots.append((kind, directory, supplementary_lock))
            supplements[kind] = directory / filename
            supplement_sources[kind] = supplementary_lock
            if kind == "wordnet":
                parser_path = PROJECT_ROOT / "cantonese_ime/wordnet.py"
                guarded_files[parser_path] = file_sha256(parser_path)
                supplement_sources[kind] = dict(supplementary_lock,
                    source_lock_file=lock_path.relative_to(PROJECT_ROOT).as_posix(),
                    source_lock_sha256=guarded_files[lock_path],
                    parser_file="cantonese_ime/wordnet.py", parser_sha256=guarded_files[parser_path],
                    insertion_phase="post_autoencoding",
                    build_selection_status="selected_default_post_autoencoding")
        if selected_headword_lock is not None:
            from cantonese_ime.cccedict_headwords import DATA_FILE
            lock_path = selected_headword_lock
            lock_bytes = lock_path.read_bytes()
            supplementary_lock = json.loads(lock_bytes.decode("utf-8"))
            directory = PROJECT_ROOT / supplementary_lock["local_directory"]
            _verify_supplement_snapshot("cccedict_headwords", directory, supplementary_lock)
            guarded_files[lock_path] = hashlib.sha256(lock_bytes).hexdigest()
            implementation = {
                "parser": PROJECT_ROOT / "cantonese_ime/cccedict_headwords.py",
                "encoder": PROJECT_ROOT / "cantonese_ime/autoencode.py",
                "builder": PROJECT_ROOT / "cantonese_ime/dictionary.py",
                "build_script": Path(__file__).resolve(),
            }
            for path in implementation.values():
                guarded_files[path] = file_sha256(path)
            selected_snapshots.append(("cccedict_headwords", directory, supplementary_lock))
            supplements["cccedict_headwords"] = directory / DATA_FILE
            supplement_sources["cccedict_headwords"] = dict(supplementary_lock,
                source_lock_file=(lock_path.resolve().relative_to(PROJECT_ROOT).as_posix()
                                  if lock_path.resolve().is_relative_to(PROJECT_ROOT) else lock_path.resolve().as_posix()),
                source_lock_sha256=guarded_files[lock_path],
                insertion_phase="post_autoencoding_post_wordnet",
                build_selection_status=("selected_opt_in_post_wordnet_autoencoding" if args.cccedict_headwords_lock is not None
                                        else "selected_default_post_wordnet_autoencoding"),
                authored_cantonese_readings=False,
                **{name + "_file": path.relative_to(PROJECT_ROOT).as_posix() for name, path in implementation.items()},
                **{name + "_sha256": guarded_files[path] for name, path in implementation.items()})
        if selected_yue_lock is not None:
            from cantonese_ime.yue_wiktionary import DATA_FILE
            lock_path = selected_yue_lock
            lock_bytes = lock_path.read_bytes()
            supplementary_lock = json.loads(lock_bytes.decode("utf-8"))
            directory = PROJECT_ROOT / supplementary_lock["local_directory"]
            _verify_supplement_snapshot("yue_wiktionary", directory, supplementary_lock)
            guarded_files[lock_path] = hashlib.sha256(lock_bytes).hexdigest()
            implementation = {"parser": PROJECT_ROOT / "cantonese_ime/yue_wiktionary.py",
                              "builder": PROJECT_ROOT / "cantonese_ime/dictionary.py",
                              "build_script": Path(__file__).resolve()}
            for path in implementation.values():
                guarded_files[path] = file_sha256(path)
            selected_snapshots.append(("yue_wiktionary", directory, supplementary_lock))
            supplements["yue_wiktionary"] = directory / DATA_FILE
            supplement_sources["yue_wiktionary"] = dict(supplementary_lock,
                source_lock_file=(lock_path.resolve().relative_to(PROJECT_ROOT).as_posix()
                                  if lock_path.resolve().is_relative_to(PROJECT_ROOT) else lock_path.resolve().as_posix()),
                source_lock_sha256=guarded_files[lock_path],
                insertion_phase="post_autoencoding_post_wordnet_post_cccedict_headwords",
                build_selection_status=("selected_opt_in_explicit_post_cccedict" if args.yue_wiktionary_lock is not None
                                        else "selected_default_explicit_post_cccedict"),
                source_explicit_cantonese_readings=True, independent_linguistic_approval=False,
                **{name + "_file": path.relative_to(PROJECT_ROOT).as_posix() for name, path in implementation.items()},
                **{name + "_sha256": guarded_files[path] for name, path in implementation.items()})

    def verify_before_publish() -> None:
        for path, expected in guarded_files.items():
            if file_sha256(path) != expected:
                raise ValueError(f"Build source lock/parser changed before publication: {path}")
        verify_source_files(source_dir, lock)
        for kind, directory, supplementary_lock in selected_snapshots:
            _verify_supplement_snapshot(kind, directory, supplementary_lock)

    stats = build_dictionary(source_dir, args.output, source_metadata={
        "repository": lock["repository"], "commit": lock["commit"],
        "license": lock["license"], "attribution": lock["attribution"],
        "supplements": supplement_sources,
    }, supplements=supplements, autoencode_phrases=not args.no_autoencode, verify_before_publish=verify_before_publish,
        progress=(lambda message: print(message, file=sys.stderr, flush=True)) if args.progress else None)
    print(json.dumps(dict(stats, database=str(args.output.resolve())), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Dictionary build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
