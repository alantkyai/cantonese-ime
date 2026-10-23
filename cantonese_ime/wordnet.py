"""Conservative Cantonese Wordnet WN-LMF pronunciation import.

Only a Lemma and its own LexicalEntry's Form attributes are paired. Synsets,
definitions, English sibling entries and examples never supply lookup data.
Raw source data remains CC BY 4.0; this independently authored parser is code.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Collection, Iterator, MutableMapping, MutableSequence
import xml.etree.ElementTree as ET

from .dictionary import DictionaryEntry, verify_source_files


SOURCE_ID = "wordnet:cantown"
DATA_FILE = "cantown.xml"
ATTESTATION_NAME = "parser-attested-bases.json"
MAX_SOURCE_BYTES = 16_000_000
MAX_XML_NODES = 500_000
MAX_XML_DEPTH = 32
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
KNOWN_DTD = "http://globalwordnet.github.io/schemas/WN-LMF-1.0.dtd"
_BASE = re.compile(r"[a-z]{1,12}\Z", re.ASCII)
_CODE = re.compile(r"[a-z]{1,12}[1-6]\Z", re.ASCII)
_HASH = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_DOCTYPE = re.compile(r"<!DOCTYPE\s+LexicalResource\s+SYSTEM\s+(['\"])([^'\"]+)\1\s*>")


def _attested_inventory(path: Path) -> tuple[frozenset[str], dict]:
    if path.stat().st_size > 100_000:
        raise ValueError("Wordnet parser attestation inventory is oversized")
    value = json.loads(path.read_text(encoding="utf-8"))
    bases = value.get("bases") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or value.get("schema_version") != 1
            or not isinstance(bases, list) or not 1 <= len(bases) <= 2000
            or any(not isinstance(base, str) or not _BASE.fullmatch(base) for base in bases)
            or len(set(bases)) != len(bases)):
        raise ValueError("Malformed Wordnet parser attestation inventory")
    return frozenset(bases), value


def _load_xml(path: Path) -> tuple[ET.Element, str]:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Wordnet XML exceeds the size limit")
    with path.open("rb") as stream:
        payload = stream.read(MAX_SOURCE_BYTES + 1)
    if len(payload) > MAX_SOURCE_BYTES:
        raise ValueError("Wordnet XML exceeds the size limit")
    try:
        document = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Wordnet XML must be UTF-8") from error
    # ElementTree is not asked to resolve any DTD. Remove only this pinned
    # external declaration; reject internal subsets and entity declarations
    # before parsing, including documents that otherwise use a familiar root.
    if re.search(r"<!ENTITY", document, re.IGNORECASE):
        raise ValueError("Wordnet XML entity declarations are forbidden")
    declarations = list(_DOCTYPE.finditer(document))
    if len(declarations) > 1 or any(match.group(2) != KNOWN_DTD for match in declarations):
        raise ValueError("Unsupported Wordnet XML DTD")
    document = _DOCTYPE.sub("", document)
    if re.search(r"<!DOCTYPE", document, re.IGNORECASE):
        raise ValueError("Unsupported Wordnet XML DTD or internal subset")
    try:
        root = ET.fromstring(document)
    except ET.ParseError as error:
        raise ValueError("Malformed Wordnet XML") from error
    if root.tag != "LexicalResource":
        raise ValueError("Unexpected Wordnet XML root")
    stack = [(root, None, 1)]
    nodes = 0
    while stack:
        element, parent, depth = stack.pop()
        nodes += 1
        if nodes > MAX_XML_NODES or depth > MAX_XML_DEPTH:
            raise ValueError("Wordnet XML node/depth limit exceeded")
        parent_tag = parent.tag if parent is not None else None
        expected_parents = {"Lexicon": "LexicalResource", "LexicalEntry": "Lexicon",
                            "Lemma": "LexicalEntry", "Form": "LexicalEntry", "Sense": "LexicalEntry",
                            "Synset": "Lexicon", "Tag": "Form"}
        if element.tag in expected_parents and parent_tag != expected_parents[element.tag]:
            raise ValueError("Unsupported nested Wordnet lexical structure")
        if element.tag == "LexicalResource" and parent is not None:
            raise ValueError("Unsupported nested Wordnet lexical resource")
        allowed_children = {"LexicalResource": {"Lexicon"},
                            "Lexicon": {"LexicalEntry", "Synset"},
                            "LexicalEntry": {"Lemma", "Form", "Sense"},
                            "Lemma": set(), "Form": {"Tag"}, "Tag": set()}
        if element.tag in allowed_children and any(child.tag not in allowed_children[element.tag] for child in element):
            raise ValueError("Unsupported Wordnet lexical structure")
        if element.tag in {"LexicalResource", "Lexicon", "LexicalEntry", "Lemma", "Form"} and element.text and element.text.strip():
            raise ValueError("Unexpected text in Wordnet lexical structure")
        if element.tag == "Tag" and (element.attrib != {"category": "transliteration"} or (element.text or "").strip() != "ascii"):
            raise ValueError("Unsupported Wordnet Form metadata")
        stack.extend((child, element, depth + 1) for child in element)
    lexicons = list(root)
    expected_languages = {"cantown-yue": "yue", "cantown-en": "en"}
    ids = [lexicon.get("id") for lexicon in lexicons]
    if len(ids) != len(set(ids)) or ids.count("cantown-yue") != 1:
        raise ValueError("Wordnet must contain exactly one Cantonese lexicon")
    entry_ids = set()
    for lexicon in lexicons:
        identity = lexicon.get("id")
        if (identity not in expected_languages or lexicon.get("language") != expected_languages[identity]
                or lexicon.get("version") != "1.0" or lexicon.get("license") != LICENSE_URL):
            raise ValueError("Unexpected Wordnet lexicon identity/language/version/license")
        for entry in lexicon.findall("LexicalEntry"):
            identity = entry.get("id")
            if not identity or identity in entry_ids:
                raise ValueError("Missing or duplicate Wordnet lexical entry ID")
            entry_ids.add(identity)
            lemmas = entry.findall("Lemma")
            if len(lemmas) != 1 or "writtenForm" not in lemmas[0].attrib:
                raise ValueError("A Wordnet entry must have exactly one written lemma")
            if any("writtenForm" not in form.attrib for form in entry.findall("Form")):
                raise ValueError("A Wordnet Form must explicitly declare writtenForm")
    return root, hashlib.sha256(payload).hexdigest()


def verify_wordnet_snapshot(source_dir: str | Path, lock: dict) -> None:
    """Verify every retained file, license declaration and admission inventory."""
    source_dir = Path(source_dir)
    required = {DATA_FILE, "README.md", "LICENSE-CC-BY-4.0.txt", "ATTRIBUTION.md", ATTESTATION_NAME}
    files = lock.get("files")
    if (lock.get("license") != "CC-BY-4.0" or lock.get("source_id") != SOURCE_ID
            or lock.get("data_file") != DATA_FILE or lock.get("declaration_file") != "README.md"
            or lock.get("license_file") != "LICENSE-CC-BY-4.0.txt"
            or not isinstance(files, list) or any(not isinstance(item, dict) for item in files)
            or not required <= {item.get("name") for item in files}
            or len(files) != len({item.get("name") for item in files})):
        raise ValueError("Unexpected Wordnet source lock/license or missing retained notice")
    verify_source_files(source_dir, lock)
    readme = (source_dir / "README.md").read_text(encoding="utf-8")
    license_text = (source_dir / "LICENSE-CC-BY-4.0.txt").read_text(encoding="utf-8")
    if ("Creative Commons Attribution 4.0 International" not in readme
            or "Attribution 4.0 International" not in license_text or "Creative Commons" not in license_text):
        raise ValueError("Wordnet retained license declarations disagree")
    bases, inventory = _attested_inventory(source_dir / ATTESTATION_NAME)
    attestation = lock.get("parser_attestation", {})
    baseline = attestation.get("baseline_database_sha256")
    if (attestation.get("file") != ATTESTATION_NAME or type(attestation.get("base_count")) is not int
            or len(bases) != attestation["base_count"] or not isinstance(baseline, str)
            or not _HASH.fullmatch(baseline) or inventory.get("baseline_database_sha256") != baseline
            or attestation.get("sha256") != hashlib.sha256((source_dir / ATTESTATION_NAME).read_bytes()).hexdigest()):
        raise ValueError("Wordnet parser inventory disagrees with its source lock")
    _load_xml(source_dir / DATA_FILE)


def _is_han(character: str) -> bool:
    point = ord(character)
    return point == 0x3007 or any(start <= point <= end for start, end in (
        (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
        (0x20000, 0x2A6DF), (0x2A700, 0x2B73F), (0x2B740, 0x2B81F),
        (0x2B820, 0x2CEAF), (0x2CEB0, 0x2EBEF), (0x2EBF0, 0x2EE5F),
        (0x2F800, 0x2FA1F), (0x30000, 0x3134F), (0x31350, 0x323AF),
    ))


def read_wordnet_entries(
    path: str | Path,
    *,
    allowed_bases: Collection[str] | None = None,
    stats: MutableMapping[str, int] | None = None,
    review_rows: MutableSequence[dict] | None = None,
) -> Iterator[DictionaryEntry]:
    """Yield explicit aligned Han/Cantonese pairs with unknown-frequency weight0.

    Case and whitespace normalize; concatenated syllables, tone variants and
    unknown bases are quarantined rather than repaired. Forms are counted before
    exact pair deduplication. All-source totals include the excluded English
    sibling; selected counters refer only to cantown-yue. Invariants:
      lexical_entries_total == input_rows + excluded_lexical_entries
      forms_total == form_candidates + excluded_forms
      input_rows == accepted_rows + quarantined_rows
      form_candidates == blank_forms + accepted_entries + duplicate_entries + quarantined_forms
    Blank forms have their own missing-reading ledger status and are not counted
    as malformed pronunciations. Source hash, entry ID and 1-based form ordinal
    locate each decoded attribute in the unmodified XML; no definition is copied.
    """
    path = Path(path)
    root, source_hash = _load_xml(path)
    if isinstance(allowed_bases, (str, bytes)):
        raise ValueError("Expected a collection of canonical Wordnet admission bases")
    bases = (frozenset(allowed_bases) if allowed_bases is not None
             else _attested_inventory(path.parent / ATTESTATION_NAME)[0])
    if not bases or any(not isinstance(base, str) or not _BASE.fullmatch(base) for base in bases):
        raise ValueError("Invalid Wordnet attested syllable set")
    counts = stats if stats is not None else {}
    for key in ("lexicons_total", "excluded_lexicons", "lexical_entries_total", "input_rows", "excluded_lexical_entries",
                "forms_total", "form_candidates", "excluded_forms", "excluded_blank_forms", "nonblank_forms", "blank_forms",
                "accepted_rows", "quarantined_rows", "accepted_entries", "duplicate_entries", "quarantined_forms",
                "entries_without_forms", "normalized_reading_forms", "review_records", "ignored_synsets", "ignored_form_tags"):
        counts.setdefault(key, 0)

    def count(key: str, amount: int = 1) -> None:
        counts[key] = counts.get(key, 0) + amount

    def review(lexicon_id: str, entry_id: str, ordinal: int | None, text: str, raw: str,
               reason: str, status: str = "quarantined", **fields) -> None:
        count("review_records")
        count("review_" + reason)
        if review_rows is not None:
            review_rows.append({"source": SOURCE_ID, "source_file": path.name, "source_sha256": source_hash,
                                "lexicon_id": lexicon_id, "entry_id": entry_id, "form_ordinal": ordinal,
                                "scope": "entry" if ordinal is None else "form", "text": text,
                                "raw_reading": raw, "reason": reason, "status": status, **fields})

    seen = set()
    for lexicon in root:
        count("lexicons_total")
        selected = lexicon.get("id") == "cantown-yue"
        if not selected:
            count("excluded_lexicons")
        count("ignored_synsets", len(lexicon.findall("Synset")))
        for entry in lexicon.findall("LexicalEntry"):
            count("lexical_entries_total")
            text = entry.find("Lemma").attrib["writtenForm"]
            forms = entry.findall("Form")
            count("forms_total", len(forms))
            count("ignored_form_tags", sum(len(form.findall("Tag")) for form in forms))
            identity = entry.attrib["id"]
            if not selected:
                count("excluded_lexical_entries")
                count("excluded_forms", len(forms))
                if not forms:
                    review(lexicon.attrib["id"], identity, None, text, "", "non_yue_lexicon", "excluded")
                for ordinal, form in enumerate(forms, 1):
                    raw = form.attrib["writtenForm"]
                    if not raw.strip():
                        count("excluded_blank_forms")
                    review(lexicon.attrib["id"], identity, ordinal, text, raw, "non_yue_lexicon", "excluded")
                continue
            count("input_rows")
            count("form_candidates", len(forms))
            valid = 0
            if not forms:
                count("entries_without_forms")
                review(lexicon.attrib["id"], identity, None, text, "", "missing_forms", "missing_reading")
            for ordinal, form in enumerate(forms, 1):
                raw = form.attrib["writtenForm"]
                if not raw.strip():
                    count("blank_forms")
                    review(lexicon.attrib["id"], identity, ordinal, text, raw, "blank_form", "missing_reading")
                    continue
                count("nonblank_forms")
                codes = raw.lower().split()
                if any(not _CODE.fullmatch(code) for code in codes):
                    count("quarantined_forms")
                    review(lexicon.attrib["id"], identity, ordinal, text, raw, "noncanonical_jyutping")
                    continue
                unknown = sorted({code[:-1] for code in codes} - bases)
                if unknown:
                    count("quarantined_forms")
                    review(lexicon.attrib["id"], identity, ordinal, text, raw, "unattested_syllables", unknown_bases=unknown)
                    continue
                if len(text) != len(codes):
                    count("quarantined_forms")
                    review(lexicon.attrib["id"], identity, ordinal, text, raw, "codepoint_syllable_alignment",
                           text_codepoints=len(text), syllable_count=len(codes))
                    continue
                if not text or not all(_is_han(character) for character in text):
                    count("quarantined_forms")
                    review(lexicon.attrib["id"], identity, ordinal, text, raw, "non_han_text")
                    continue
                valid += 1
                reading = " ".join(codes)
                if reading != raw:
                    count("normalized_reading_forms")
                    review(lexicon.attrib["id"], identity, ordinal, text, raw, "normalized_reading",
                           "informational", reading=reading)
                pair = text, reading
                if pair in seen:
                    count("duplicate_entries")
                    continue
                seen.add(pair)
                count("accepted_entries")
                base_reading = " ".join(code[:-1] for code in codes)
                yield DictionaryEntry(text, reading, base_reading, base_reading.replace(" ", ""),
                                      len(codes), 0.0, SOURCE_ID)
            count("accepted_rows" if valid else "quarantined_rows")
