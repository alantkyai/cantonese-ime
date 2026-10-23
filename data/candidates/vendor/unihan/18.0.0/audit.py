"""Project-authored, offline comparison of a candidate Unihan snapshot.

This script is not part of the Unicode source distribution and never writes the
selected lexicon or mappings. Run from any directory with Python's stdlib.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MISSING_COMPONENTS = tuple("乄乊乛纟罓肀覀讠钅阝饣𠃍𠃑𧘇")
ORIGINAL_BASELINE_SHA256 = "aec269744279a5d85a9f5ca459b9a04f060ae53c29b975fd4aab132d90fab39d"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/generated/lexicon.sqlite3")
    args = parser.parse_args()
    database = args.database.resolve()
    before = sha256(database)
    if before != ORIGINAL_BASELINE_SHA256:
        raise ValueError(
            "This candidate audit preserves its original comparison baseline. "
            f"Supply --database with SHA-256 {ORIGINAL_BASELINE_SHA256}; audit outputs were not changed."
        )
    pairs: dict[tuple[str, str], dict] = {}
    properties = Counter()
    members = []
    with zipfile.ZipFile(HERE / "Unihan.zip") as archive:
        for name in archive.namelist():
            data = archive.read(name)
            members.append({"name": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
                if not line or line.startswith("#"):
                    continue
                code, prop, value = line.split("\t")
                properties[prop] += 1
                if prop != "kCantonese":
                    continue
                text = chr(int(code[2:], 16))
                for reading in value.split():
                    if not re.fullmatch(r"[a-z]{1,6}[1-6]", reading):
                        raise ValueError(f"{name}:{number}: unsupported kCantonese reading {reading!r}")
                    if (text, reading) in pairs:
                        raise ValueError(f"{name}:{number}: repeated character/reading pair")
                    pairs[(text, reading)] = {"member": name, "line": number, "codepoint": code}
        extracted = HERE / "Unihan_Readings.txt"
        if extracted.read_bytes() != archive.read("Unihan_Readings.txt"):
            raise ValueError("Retained readings file differs from the pinned archive member.")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        current = {(text, reading): origin for text, reading, origin in connection.execute(
            "SELECT text,reading,origin FROM entries WHERE length(text)=1"
        )}
        authored = {pair for pair, origin in current.items() if origin in ("explicit", "supplement")}
        all_bases = {base for reading, in connection.execute("SELECT DISTINCT base_reading FROM entries") for base in reading.split()}
        all_tones = {part for reading, in connection.execute("SELECT DISTINCT reading FROM entries") for part in reading.split()}
        row_count = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    if sha256(database) != before:
        raise ValueError("Baseline dictionary changed during candidate comparison.")
    current_texts = {text for text, reading in current}
    new = set(pairs) - set(current)
    source_bases = {reading[:-1] for text, reading in pairs}
    source_tones = {reading for text, reading in pairs}
    new_bases = sorted(source_bases - all_bases)
    new_tones = sorted(source_tones - all_tones)
    inventory = json.loads((ROOT / "data/mappings/syllables.json").read_text(encoding="utf-8"))
    scheme = inventory["scheme"]
    classified_bases = []
    for base in new_bases:
        onset = next((value for value in sorted(scheme["onsets"], key=lambda item: (-len(item), item)) if base.startswith(value)), "")
        final = base[len(onset):]
        classified_bases.append({
            "base": base, "onset": onset, "final": final,
            "scheme_shape": final in scheme["finals"],
            "source_tones": sorted(reading[-1] for text, reading in pairs if reading[:-1] == base),
            "exception_flags": ["new_to_selected_inventory", "provisional_source_property"],
            "interpretation": "Onset/final shape compatibility only; no exhaustive phonotactic or modern-use validation.",
        })
    components = [
        {"text": text, "codepoint": f"U+{ord(text):04X}",
         "kCantonese": [{"reading": reading, **detail} for (character, reading), detail in pairs.items() if character == text],
         "baseline_readings": sorted(reading for character, reading in current if character == text)}
        for text in MISSING_COMPONENTS
    ]
    with (ROOT / "data/review/path_limited_phrases.tsv").open(encoding="utf-8", newline="") as stream:
        phrases = list(csv.DictReader(stream, delimiter="\t"))
    with (HERE / "new-pairs.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("text", "codepoint", "reading", "comparison", "property", "archive_member", "source_line"))
        for text, reading in sorted(new):
            detail = pairs[(text, reading)]
            writer.writerow((text, detail["codepoint"], reading,
                             "new_reading_existing_text" if text in current_texts else "new_text",
                             "kCantonese", detail["member"], detail["line"]))
    report = {
        "schema_version": 1,
        "candidate_status": "audit_only_not_selected",
        "unicode_version": "18.0.0",
        "property": "kCantonese",
        "property_status": "Provisional",
        "baseline": {"path": str(database), "sha256": before, "pairs": row_count,
                     "single_character_pairs": len(current), "authored_single_character_pairs": len(authored),
                     "bases": len(all_bases), "toned_forms": len(all_tones)},
        "counts": {"source_character_texts": len({text for text, reading in pairs}),
                   "source_pairs": len(pairs), "source_bases": len(source_bases), "source_toned_forms": len(source_tones),
                   "overlapping_baseline_pairs": len(set(pairs) & set(current)),
                   "new_pairs_vs_baseline": len(new), "new_pairs_vs_authored": len(set(pairs) - authored),
                   "new_texts": len({text for text, reading in new if text not in current_texts}),
                   "new_readings_existing_texts": sum(text in current_texts for text, reading in new),
                   "missing_components_with_direct_kCantonese": sum(bool(item["kCantonese"]) for item in components),
                   "missing_components_still_without_kCantonese": sum(not item["kCantonese"] for item in components),
                   "path_limited_phrase_rows": len(phrases),
                   "path_limited_exact_wholeword_matches": sum(any(text == row["text"] for text, reading in pairs) for row in phrases)},
        "new_bases": new_bases,
        "new_base_classification": classified_bases,
        "new_toned_forms": new_tones,
        "new_base_examples": {base: [{"text": text, "reading": reading, **pairs[(text, reading)]}
                                     for text, reading in sorted(pairs) if reading[:-1] == base] for base in new_bases},
        "missing_components": components,
        "archive_members": members,
        "derived_files": {"new-pairs.tsv": {"sha256": sha256(HERE / "new-pairs.tsv"), "rows": len(new)}},
        "interpretation": "Exact textual pair delta only. No pronunciation/frequency quality claim, no variant inheritance, no word reading generation and no source selection change.",
    }
    (HERE / "audit.summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "new_bases": new_bases, "new_toned_forms": new_tones}, indent=2))


if __name__ == "__main__":
    main()
