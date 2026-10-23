"""Conservative, source-pinned Yue Wiktionary pronunciation candidate reader.

Only explicit own-headword fields are read. No wikitext/Lua executes, no
pronunciation is inherited or inferred, and no default-source selection occurs.
Source text is CC BY-SA 4.0; this independently authored parser is application code.
"""
from __future__ import annotations

from bisect import bisect_right
import bz2
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Collection, Iterator, MutableMapping, MutableSequence
from urllib.parse import quote
import xml.etree.ElementTree as ET

from .dictionary import DictionaryEntry

SOURCE_ID = "wiktionary:yue"
DATA_FILE = "yuewiktionary-20261001-pages-articles.xml.bz2"
INVENTORY_FILE = "parser-attested-bases.json"
XML_NAMESPACE = "http://www.mediawiki.org/xml/export-0.11/"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
MAX_ARCHIVE_BYTES = 8_000_000
MAX_XML_BYTES = 32_000_000
MAX_XML_NODES = 300_000
MAX_XML_DEPTH = 16
MAX_PAGES = 20_000
MAX_TEXT_BYTES = 2_000_000
MAX_CALL_CHARACTERS = 32_000
MAX_FIELD_RECORDS = 100_000
_HASH = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_BASE = re.compile(r"[a-z]{1,12}\Z", re.ASCII)
_CODE = re.compile(r"[a-z]{1,12}[1-6]\Z", re.ASCII)
_HEADINGS = re.compile(r"(?m)^==([^=\n].*?)==[ \t]*\r?$")
_YUE_HEADING = re.compile(r"\s*\{\{langue\|yue\}\}\s*\Z", re.I)
_START = re.compile(r"\{\{\s*(zh-pron|yue-rom|粵拼)(?=[|\s}])", re.I)
_PROTECTED = re.compile(r"<!--|<(nowiki|pre|source|syntaxhighlight|ref|blockquote|math|code)\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.I)
_SUPERSCRIPTS = str.maketrans("¹²³⁴⁵⁶", "123456")
# These are original source revision fields, not an implementation of the templates.
_TEMPLATE_SPECS = {
    "yue-rom": ("模:Yue-rom", 10752, "source-template-yue-rom.wikitext", "95be4bc85b521bc627d10daf3d09daed07e86389cb3674195d838a731647cdc3"),
    "zh-pron": ("模:zh-pron", 14605, "source-template-zh-pron.wikitext", "6b4f266fc564f8ede70ab7cb5bfe23d913af1a6865c8cd00382d07fd0ffe2b94"),
    "粵拼": ("模:粵拼", 9516, "source-template-jyutping.wikitext", "acc5f0c81b006e4db2412b66ade34cda6659f47f3e5f317d2b96469da9b27f17"),
}
_TEMPLATE_REVISION_HASHES = {
    "yue-rom": "95be4bc85b521bc627d10daf3d09daed07e86389cb3674195d838a731647cdc3",
    "zh-pron": "e7b11777a13633d646c5e40f57220af3510be2c064f81d3322af07bd998b1847",
    "粵拼": "381d7c98e48df6c8aee225bcea3522600f8ccc25707cf0fbcd9da6e2e3a8eaf5",
}


@dataclass(frozen=True, slots=True)
class _Document:
    root: ET.Element
    source_sha256: str
    xml_sha256: str
    xml_size_bytes: int
    template_valid: dict[str, bool]


def _bounded(path: Path, limit: int) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError("Yue Wiktionary retained source exceeds its size bound")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Yue Wiktionary retained source exceeds its size bound")
    return data


def _child(element, tag):
    return element.find("{" + XML_NAMESPACE + "}" + tag)


def _children(element, tag):
    return element.findall("{" + XML_NAMESPACE + "}" + tag)


def _text(element, tag, default=""):
    node = _child(element, tag)
    return (node.text or "") if node is not None else default


def _load_document(path: Path) -> _Document:
    compressed = _bounded(path, MAX_ARCHIVE_BYTES)
    if not re.match(b"BZh[1-9]", compressed):
        raise ValueError("Expected the pinned bzip2 Yue Wiktionary archive")
    try:
        decompressor = bz2.BZ2Decompressor()
        xml = decompressor.decompress(compressed, max_length=MAX_XML_BYTES + 1)
    except (OSError, EOFError) as error:
        raise ValueError("Malformed Yue Wiktionary bzip2 archive") from error
    if len(xml) > MAX_XML_BYTES or not decompressor.eof or decompressor.unused_data:
        raise ValueError("Truncated, oversized or trailing-member Yue Wiktionary archive")
    try:
        document = xml.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Yue Wiktionary XML must be UTF-8") from error
    if re.search(r"<!DOCTYPE|<!ENTITY", document, re.I):
        raise ValueError("Yue Wiktionary XML DTD/entities are forbidden")
    try:
        root = ET.fromstring(document)
    except ET.ParseError as error:
        raise ValueError("Malformed Yue Wiktionary XML") from error
    if (root.tag != "{" + XML_NAMESPACE + "}mediawiki" or root.get("version") != "0.11"
            or root.get("{http://www.w3.org/XML/1998/namespace}lang") != "yue"):
        raise ValueError("Unexpected Yue Wiktionary XML export header")
    siteinfo = _children(root, "siteinfo")
    if len(siteinfo) != 1 or _text(siteinfo[0], "dbname") != "yuewiktionary":
        raise ValueError("Yue Wiktionary XML site identity is missing or wrong")
    stack, nodes = [(root, 1)], 0
    while stack:
        element, depth = stack.pop()
        nodes += 1
        if nodes > MAX_XML_NODES or depth > MAX_XML_DEPTH:
            raise ValueError("Yue Wiktionary XML node/depth bound exceeded")
        if not isinstance(element.tag, str) or not element.tag.startswith("{" + XML_NAMESPACE + "}"):
            raise ValueError("Unsupported Yue Wiktionary XML namespace")
        stack.extend((child, depth + 1) for child in element)
    if any(child.tag not in {"{" + XML_NAMESPACE + "}siteinfo", "{" + XML_NAMESPACE + "}page"} for child in root):
        raise ValueError("Unsupported Yue Wiktionary XML root structure")
    pages = _children(root, "page")
    if not 1 <= len(pages) <= MAX_PAGES:
        raise ValueError("Yue Wiktionary XML must contain a bounded nonempty page collection")
    page_ids, titles = set(), set()
    for page in pages:
        identity, title = _text(page, "id"), _text(page, "title")
        if (len(_children(page, "id")) != 1 or not identity.isascii() or not identity.isdecimal()
                or len(_children(page, "title")) != 1 or not title or identity in page_ids or title in titles
                or len(_children(page, "ns")) != 1):
            raise ValueError("Missing/duplicate Yue Wiktionary page identity")
        page_ids.add(identity)
        titles.add(title)
        for revision in _children(page, "revision"):
            for node in _children(revision, "text"):
                if list(node):
                    raise ValueError("Unsupported nested XML in revision text")
                value = (node.text or "").encode("utf-8")
                if len(value) > MAX_TEXT_BYTES:
                    raise ValueError("Yue Wiktionary per-page text bound exceeded")
                if node.get("bytes") is not None and (not node.get("bytes").isascii()
                        or not node.get("bytes").isdecimal() or int(node.get("bytes")) != len(value)):
                    raise ValueError("Yue Wiktionary revision byte-count integrity mismatch")
                # Export sha1 is a base36 encoding of the SHA1 integer, not hex.
                exported = _text(revision, "sha1")
                if exported:
                    try:
                        matches = int(exported, 36) == int(hashlib.sha1(value).hexdigest(), 16)
                    except ValueError:
                        matches = False
                    if not matches:
                        raise ValueError("Yue Wiktionary revision SHA1 integrity mismatch")
    valid = {}
    by_title = {_text(page, "title"): page for page in pages}
    for name, (title, revision_id, _, digest) in _TEMPLATE_SPECS.items():
        revisions = _children(by_title[title], "revision") if title in by_title else []
        valid[name] = (len(revisions) == 1 and _text(revisions[0], "id") == str(revision_id)
                       and hashlib.sha256(_text(revisions[0], "text").encode()).hexdigest() == _TEMPLATE_REVISION_HASHES[name])
    return _Document(root, hashlib.sha256(compressed).hexdigest(), hashlib.sha256(xml).hexdigest(), len(xml), valid)


def _inventory(path: Path) -> tuple[frozenset[str], dict]:
    value = json.loads(_bounded(path, 100_000).decode("utf-8"))
    bases = value.get("bases") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(bases, list)
            or not 1 <= len(bases) <= 2000
            or any(not isinstance(base, str) or not _BASE.fullmatch(base) for base in bases)
            or len(set(bases)) != len(bases)):
        raise ValueError("Invalid Yue Wiktionary frozen admission inventory")
    return frozenset(bases), value


def verify_yue_wiktionary_snapshot(directory: str | Path, lock: dict) -> None:
    """Check all retained bytes, official checksum, XML/site and source semantics."""
    directory = Path(directory).resolve()
    required = {DATA_FILE, INVENTORY_FILE, "yue-20261001-sha1sums.txt", "yue-20261001-index.html",
                "yue-page-licensing-sample.html", "wikimedia-terms.html", "LICENSE-CC-BY-SA-4.0.txt",
                "ATTRIBUTION.md", "research-manifest.json", *(spec[2] for spec in _TEMPLATE_SPECS.values())}
    if (not isinstance(lock, dict) or lock.get("schema_version") != 1 or lock.get("source_id") != SOURCE_ID
            or lock.get("license") != "CC-BY-SA-4.0" or lock.get("license_url") != LICENSE_URL
            or lock.get("data_file") != DATA_FILE or lock.get("compression") != "bzip2"
            or lock.get("xml_export_version") != "0.11" or lock.get("wiki_database") != "yuewiktionary"
            or lock.get("wiki_language") != "yue"):
        raise ValueError("Unexpected Yue Wiktionary source lock/header/license")
    files = lock.get("files")
    if not isinstance(files, list) or not 12 <= len(files) <= 32 or any(not isinstance(row, dict) for row in files):
        raise ValueError("Missing Yue Wiktionary retained source notices")
    payloads, names = {}, set()
    for row in files:
        name = row.get("name")
        if (not isinstance(name, str) or not name or ":" in name or "\\" in name
                or PurePosixPath(name).is_absolute() or any(part in ("", ".", "..")
                    or part.endswith((".", " ")) for part in name.split("/")) or name.casefold() in names):
            raise ValueError("Unsafe/duplicate Yue Wiktionary retained filename")
        names.add(name.casefold())
        path = (directory / name).resolve()
        if not path.is_relative_to(directory):
            raise ValueError("Yue Wiktionary retained path escapes its directory")
        expected_size, expected_hash = row.get("size_bytes"), row.get("sha256")
        if (type(expected_size) is not int or not 0 < expected_size <= MAX_ARCHIVE_BYTES
                or not isinstance(expected_hash, str) or not _HASH.fullmatch(expected_hash)):
            raise ValueError("Invalid Yue Wiktionary source size/hash lock")
        data = _bounded(path, MAX_ARCHIVE_BYTES)
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError("Yue Wiktionary retained source differs from its lock")
        payloads[name] = data
    if not required <= payloads.keys():
        raise ValueError("Missing Yue Wiktionary source/license/template/inventory file")
    try:
        footer = payloads["yue-page-licensing-sample.html"].decode("utf-8")
        terms = payloads["wikimedia-terms.html"].decode("utf-8")
        legal = payloads["LICENSE-CC-BY-SA-4.0.txt"].decode("utf-8")
        attribution = payloads["ATTRIBUTION.md"].decode("utf-8")
        checksums = payloads["yue-20261001-sha1sums.txt"].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Yue Wiktionary retained notices must be UTF-8") from error
    if (LICENSE_URL not in footer or "creativecommons.org/licenses/by-sa/4.0/" not in terms
            or "Creative Commons Attribution-ShareAlike 4.0 International License" not in terms
            or len(legal) < 10_000 or "Attribution-ShareAlike 4.0 International" not in legal
            or any(f"Section {number} --" not in legal for number in range(1, 9))
            or any(word not in attribution for word in ("Yue Wiktionary contributors", "revision", "history", "CC BY-SA 4.0"))):
        raise ValueError("Yue Wiktionary attribution/full license declarations are incomplete")
    checksum_rows = [line.split() for line in checksums.splitlines() if line.split() and line.split()[-1] == DATA_FILE]
    actual_sha1 = hashlib.sha1(payloads[DATA_FILE]).hexdigest()
    if len(checksum_rows) != 1 or checksum_rows[0][0] != actual_sha1 or lock.get("official_archive_sha1") != actual_sha1:
        raise ValueError("Yue Wiktionary archive differs from its official checksum")
    document = _load_document(directory / DATA_FILE)
    if (lock.get("xml_sha256") != document.xml_sha256 or lock.get("xml_size_bytes") != document.xml_size_bytes
            or type(lock.get("page_count")) is not int or lock["page_count"] != len(_children(document.root, "page"))
            or not all(document.template_valid.values())):
        raise ValueError("Yue Wiktionary XML or pinned template revision differs")
    revisions = lock.get("template_revisions")
    if not isinstance(revisions, list) or len(revisions) != len(_TEMPLATE_SPECS):
        raise ValueError("Yue Wiktionary template evidence is incomplete")
    by_title = {_text(page, "title"): page for page in _children(document.root, "page")}
    for template, (title, revision_id, name, digest) in _TEMPLATE_SPECS.items():
        matching = [row for row in revisions if isinstance(row, dict) and row.get("title") == title]
        if (len(matching) != 1 or matching[0].get("revision_id") != revision_id or matching[0].get("name") != name
                or matching[0].get("sha256") != digest or hashlib.sha256(payloads[name]).hexdigest() != digest
                or matching[0].get("revision_text_sha256") != _TEMPLATE_REVISION_HASHES[template]
                or payloads[name].decode("utf-8").replace("\r\n", "\n")
                    != _text(_children(by_title[title], "revision")[0], "text")):
            raise ValueError("Yue Wiktionary retained template evidence differs from its source revision")
    if lock.get("research_manifest_sha256") != hashlib.sha256(payloads["research-manifest.json"]).hexdigest():
        raise ValueError("Yue Wiktionary retained research provenance differs")
    bases, inventory = _inventory(directory / INVENTORY_FILE)
    admission = lock.get("parser_attestation", {})
    if (admission.get("file") != INVENTORY_FILE or admission.get("base_count") != len(bases)
            or admission.get("sha256") != hashlib.sha256(payloads[INVENTORY_FILE]).hexdigest()
            or admission.get("baseline_database_sha256") != inventory.get("baseline_database_sha256")
            or not isinstance(admission.get("baseline_database_sha256"), str)
            or not _HASH.fullmatch(admission["baseline_database_sha256"])):
        raise ValueError("Yue Wiktionary admission inventory disagrees with its lock")


def _han(text: str) -> bool:
    ranges = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x2A6DF),
              (0x2A700, 0x2B73F), (0x2B740, 0x2B81F), (0x2B820, 0x2CEAF), (0x2CEB0, 0x2EBEF),
              (0x2EBF0, 0x2EE5F), (0x2F800, 0x2FA1F), (0x30000, 0x3134F), (0x31350, 0x3347F))
    return bool(text) and all(character == "〇" or any(a <= ord(character) <= b for a, b in ranges) for character in text)


def _mask(text: str) -> tuple[str, list[tuple[int, int, str]]]:
    regions, position = [], 0
    while match := _PROTECTED.search(text, position):
        start = match.start()
        if match[0] == "<!--":
            close = text.find("-->", match.end())
            end = len(text) if close < 0 else close + 3
            kind = "comment"
        elif match[0].rstrip().endswith("/>"):
            end, kind = match.end(), "protected_text"
        else:
            tag = match[1]
            token = re.compile(r"</?" + re.escape(tag) + r"\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.I)
            nesting, end = 1, len(text)
            for close in token.finditer(text, match.end()):
                if close[0].startswith("</"):
                    nesting -= 1
                elif not close[0].rstrip().endswith("/>"):
                    nesting += 1
                if nesting == 0:
                    end = close.end()
                    break
            kind = "protected_text"
        regions.append((start, end, kind))
        position = end
    visible = list(text)
    for start, end, _ in regions:
        visible[start:end] = ["\n" if char == "\n" else " " for char in text[start:end]]
    return "".join(visible), regions


def _calls(visible: str) -> dict[int, tuple[int | None, int]]:
    """Track brace nesting; an inner recognized call is never a flat field."""
    stack, found, position = [], {}, 0
    while position < len(visible):
        if visible.startswith("{{{", position):
            stack.append((3, position))
            position += 3
        elif visible.startswith("{{", position):
            if _START.match(visible, position):
                found[position] = (None, len(stack))
            stack.append((2, position))
            position += 2
        elif stack and stack[-1][0] == 3 and visible.startswith("}}}", position):
            stack.pop()
            position += 3
        elif stack and stack[-1][0] == 2 and visible.startswith("}}", position):
            _, start = stack.pop()
            if start in found:
                found[start] = (position + 2, found[start][1])
            position += 2
        else:
            position += 1
    return found


def read_yue_wiktionary_entries(
    path: str | Path,
    *,
    allowed_bases: Collection[str] | None = None,
    stats: MutableMapping[str, int] | None = None,
    review_rows: MutableSequence[dict] | None = None,
    page_rows: MutableSequence[dict] | None = None,
    section_rows: MutableSequence[dict] | None = None,
    field_rows: MutableSequence[dict] | None = None,
) -> Iterator[DictionaryEntry]:
    """Yield unique explicit pairs with weight0 and complete occurrence ledgers.

    All main-page recognized calls, including excluded contexts, have call
    records. Variants and unsupported repeated c= fields have separate located
    field records. Every XML page and every main-page level2 section/preamble
    is accounted. Protected/comment text cannot supply active fields; source
    locations are decoded revision-text codepoint offsets and physical lines.
    A complete source parse finishes before caller ledgers or entries publish.
    """
    path = Path(path)
    document = _load_document(path)
    if isinstance(allowed_bases, (str, bytes)):
        raise ValueError("Expected a collection of attested admission bases")
    bases = frozenset(allowed_bases) if allowed_bases is not None else _inventory(path.parent / INVENTORY_FILE)[0]
    if not bases or any(not isinstance(base, str) or not _BASE.fullmatch(base) for base in bases):
        raise ValueError("Invalid Yue Wiktionary admission bases")
    counts = Counter()
    pages, sections, fields, reviews, admitted = [], [], [], [], {}

    def field(value, *, review=False):
        fields.append(value)
        counts["field_records"] += 1
        if len(fields) > MAX_FIELD_RECORDS:
            raise ValueError("Yue Wiktionary field-ledger bound exceeded")
        if review:
            reviews.append(dict(value))

    for page in _children(document.root, "page"):
        counts["all_xml_pages"] += 1
        title, page_id, namespace = _text(page, "title"), _text(page, "id"), _text(page, "ns")
        revisions = _children(page, "revision")
        revision = revisions[0] if len(revisions) == 1 else None
        revision_id = _text(revision, "id") if revision is not None else None
        page_info = {"source": SOURCE_ID, "source_file": path.name, "source_sha256": document.source_sha256,
                     "xml_sha256": document.xml_sha256, "text": title, "page_id": page_id, "namespace": namespace,
                     "revision_id": revision_id, "revision_timestamp": _text(revision, "timestamp") if revision is not None else None,
                     "page_url": "https://yue.wiktionary.org/wiki/" + quote(title),
                     "revision_url": "https://yue.wiktionary.org/w/index.php?oldid=" + revision_id if revision_id else None,
                     "history_url": "https://yue.wiktionary.org/w/index.php?title=" + quote(title) + "&action=history"}
        page_record = dict(page_info)
        pages.append(page_record)
        counts["namespace_" + namespace + "_pages"] += 1
        if namespace != "0":
            page_record["status"] = "excluded_non_main_namespace"
            continue
        counts["main_namespace_pages"] += 1
        unsupported = None
        known_page_tags = {"title", "ns", "id", "redirect", "revision", "restrictions"}
        known_revision_tags = {"id", "parentid", "timestamp", "contributor", "minor", "comment", "origin",
                               "model", "format", "text", "sha1"}
        if any(child.tag.rsplit("}", 1)[-1] not in known_page_tags for child in page):
            unsupported = "unsupported_page_structure"
        elif revision is None:
            unsupported = "unsupported_revision_count"
        elif any(child.tag.rsplit("}", 1)[-1] not in known_revision_tags for child in revision):
            unsupported = "unsupported_revision_structure"
        elif (len(_children(revision, "id")) != 1 or not revision_id or not revision_id.isascii()
              or not revision_id.isdecimal() or len(_children(revision, "text")) != 1
              or len(_children(revision, "timestamp")) != 1 or len(_children(revision, "model")) != 1
              or len(_children(revision, "format")) != 1):
            unsupported = "unsupported_revision_metadata"
        elif (_text(revision, "model") != "wikitext" or _text(revision, "format") != "text/x-wiki"
              or _child(revision, "text").get("deleted") is not None):
            unsupported = "unsupported_revision_content"
        if unsupported is None:
            try:
                if datetime.fromisoformat(page_info["revision_timestamp"].replace("Z", "+00:00")).tzinfo is None:
                    raise ValueError
            except ValueError:
                unsupported = "unsupported_revision_timestamp"
        if unsupported:
            page_record["status"] = unsupported
            reviews.append(dict(page_info, scope="page", status="quarantined", reason=unsupported,
                                revision_ids=[_text(item, "id") for item in revisions]))
            counts[unsupported] += 1
            continue
        if _child(page, "redirect") is not None:
            page_record["status"] = "excluded_redirect"
            counts["redirect_pages"] += 1
            continue
        text = _text(revision, "text")
        page_info["wikitext_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        page_record["wikitext_sha256"] = page_info["wikitext_sha256"]
        visible, protected = _mask(text)
        headings = list(_HEADINGS.finditer(visible))
        ranges = [(0, 0, headings[0].start() if headings else len(text), "", False)]
        for ordinal, heading in enumerate(headings, 1):
            end = headings[ordinal].start() if ordinal < len(headings) else len(text)
            ranges.append((heading.start(), heading.end(), end, text[heading.start(1):heading.end(1)],
                           bool(_YUE_HEADING.fullmatch(heading[1]))))
        range_starts = [value[0] for value in ranges]
        active_calls = Counter()
        selected_sections = sum(value[4] for value in ranges)
        page_record.update(status="selected_yue_section" if selected_sections else "excluded_no_supported_yue_section",
                           selected_yue_sections=selected_sections, level2_sections=len(headings))
        counts["explicit_yue_language_sections"] += selected_sections
        counts["main_level2_sections"] += len(headings)
        counts["main_preambles"] += 1
        call_map, ordinals = _calls(visible), Counter()
        protected_starts = [value[0] for value in protected]
        for match in _START.finditer(text):
            start, name = match.start(), match[1].lower()
            section_index = max(0, bisect_right(range_starts, start) - 1)
            _, body_start, section_end, heading_text, selected = ranges[section_index]
            region_index = bisect_right(protected_starts, start) - 1
            in_protected = region_index >= 0 and start < protected[region_index][1]
            ordinals[section_index] += 1
            counts["recognized_main_pronunciation_calls"] += 1
            event = dict(page_info, scope="call", language_section_ordinal=section_index,
                         template_ordinal=ordinals[section_index], template=name,
                         source_line=text.count("\n", 0, start) + 1, source_character_offset=start)
            if in_protected:
                reason = "excluded_" + protected[region_index][2]
                field(dict(event, status=reason, reason=reason), review=True)
                counts[reason] += 1
                continue
            if not selected or start < body_start:
                reason = "excluded_non_yue_language_context"
                field(dict(event, status=reason, reason=reason), review=False)
                counts[reason] += 1
                continue
            active_calls[section_index] += 1
            counts["recognized_yue_pronunciation_calls"] += 1
            end, depth = call_map.get(start, (None, 0))
            reason = None
            if end is None or end > section_end:
                reason = "unsupported_unclosed_or_cross_section_template"
            elif end - start > MAX_CALL_CHARACTERS:
                reason = "unsupported_oversized_template"
            elif depth or not re.fullmatch(r"[ \t:]*", visible[visible.rfind("\n", 0, start) + 1:start]):
                reason = "unsupported_nested_or_non_line_leading_template"
            elif any(a < end and b > start for a, b, _ in protected):
                reason = "unsupported_comment_or_protected_content"
            elif "{" in text[start + 2:end - 2] or "}" in text[start + 2:end - 2]:
                reason = "unsupported_nested_or_non_line_leading_template"
            elif not document.template_valid.get(name):
                reason = "unsupported_template_revision"
            if end is not None:
                event.update(source_end_character_offset=end, raw_call_sha256=hashlib.sha256(text[start:end].encode()).hexdigest())
            if reason:
                field(dict(event, status="quarantined", reason=reason), review=True)
                counts[reason] += 1
                continue
            _, separator, body = text[start + 2:end - 2].partition("|")
            arguments = body.split("|") if separator else []
            event["raw_arguments"] = arguments
            raw_variants = []
            if name == "zh-pron":
                c_fields = [(index, part.partition("=")[2]) for index, part in enumerate(arguments, 1)
                            if "=" in part and part.partition("=")[0].strip() == "c"]
                if len(c_fields) != 1:
                    reason = "unsupported_no_unique_c_parameter"
                    for index, raw in c_fields:
                        field(dict(event, scope="parameter", parameter_ordinal=index, raw_reading=raw,
                                   status="quarantined", reason=reason), review=True)
                else:
                    raw_variants = [(value, {"parameter_ordinal": c_fields[0][0]}) for value in c_fields[0][1].split(",")]
            elif name == "yue-rom":
                if not arguments or "=" in arguments[0] or any("=" not in part for part in arguments[1:]):
                    reason = "unsupported_yue_rom_argument_shape"
                elif any(part.partition("=")[0].strip() != "count" for part in arguments[1:]):
                    reason = "unsupported_yue_rom_named_parameter"
                else:
                    raw_variants = [(value, {"parameter_ordinal": 1}) for value in arguments[0].split(",")]
            else:
                args = [part.strip().lower() for part in arguments]
                if not args or len(args) > 32 or len(args) % 2 or any("=" in part for part in args):
                    reason = "unsupported_paired_argument_shape"
                else:
                    tokens = []
                    for base, display in zip(args[::2], args[1::2]):
                        code = display.translate(_SUPERSCRIPTS)
                        if not _CODE.fullmatch(code) or base != code[:-1]:
                            reason = "unverified_display_or_index_mismatch"
                            break
                        tokens.append(code)
                    if reason is None:
                        raw_variants = [(" ".join(arguments[1::2]), {"canonical_pair_sequence": " ".join(tokens),
                            "unicode_tone_conversion": any(char in "¹²³⁴⁵⁶" for char in "".join(arguments[1::2]))})]
            if reason:
                field(dict(event, status="quarantined", reason=reason), review=True)
                counts[reason] += 1
                continue
            field(dict(event, status="parsed_call", examined_variants=len(raw_variants)))
            counts["supported_" + name + "_calls"] += 1
            for variant_ordinal, (raw, extra) in enumerate(raw_variants, 1):
                counts["reading_variant_occurrences"] += 1
                reading = extra.get("canonical_pair_sequence", " ".join(raw.lower().split()))
                tokens = reading.split()
                reason = None
                if not tokens or any(not _CODE.fullmatch(token) for token in tokens):
                    reason = "syntax_or_marked_notation"
                elif unknown := sorted({token[:-1] for token in tokens} - bases):
                    reason = "unknown_base"
                elif not _han(title):
                    reason = "non_han_headword"
                elif len(title) != len(tokens):
                    reason = "unaligned_headword"
                variant = dict(event, scope="variant", variant_ordinal=variant_ordinal,
                               raw_reading=raw, normalized_reading=reading, **extra)
                if reason:
                    if reason == "unknown_base":
                        variant["unknown_bases"] = unknown
                    field(dict(variant, status="quarantined", reason=reason), review=True)
                    counts["quarantined_variant_occurrences"] += 1
                    counts["excluded_" + reason] += 1
                else:
                    pair = title, reading
                    duplicate = pair in admitted
                    field(dict(variant, status="duplicate_pair" if duplicate else "admitted_pair"))
                    counts["accepted_variant_occurrences"] += 1
                    counts["duplicate_pair_occurrences"] += duplicate
                    base_reading = " ".join(token[:-1] for token in tokens)
                    admitted.setdefault(pair, DictionaryEntry(title, reading, base_reading, base_reading.replace(" ", ""),
                                                             len(tokens), 0.0, SOURCE_ID))
        for ordinal, (start, body_start, end, raw_heading, selected) in enumerate(ranges):
            section = dict(page_info, scope="section", language_section_ordinal=ordinal, raw_heading=raw_heading,
                           source_character_offset=start, body_character_offset=body_start,
                           source_end_character_offset=end, source_line=text.count("\n", 0, start) + 1,
                           kind="preamble" if ordinal == 0 else "level2", selected_yue=selected,
                           recognized_active_calls=active_calls[ordinal],
                           status="selected_yue_section" if selected else "excluded_non_yue_language_section")
            sections.append(section)
            if selected and not active_calls[ordinal]:
                counts["sections_without_recognized_pronunciation_field"] += 1
                field(dict(section, status="quarantined", reason="missing_supported_pronunciation_field"), review=True)
    counts["unique_pairs"] = len(admitted)
    counts["unique_texts"] = len({pair[0] for pair in admitted})
    counts["page_records"] = len(pages)
    counts["section_records"] = len(sections)
    counts["review_records"] = len(reviews)
    if (len(pages) != counts["all_xml_pages"] or counts["accepted_variant_occurrences"]
            != len(admitted) + counts["duplicate_pair_occurrences"]
            or counts["reading_variant_occurrences"] != counts["accepted_variant_occurrences"] + counts["quarantined_variant_occurrences"]):
        raise ValueError("Yue Wiktionary source accounting invariant failed")
    if stats is not None:
        for key, value in counts.items():
            stats[key] = stats.get(key, 0) + value
    for target, values in ((review_rows, reviews), (page_rows, pages), (section_rows, sections), (field_rows, fields)):
        if target is not None:
            target.extend(values)
    yield from (admitted[pair] for pair in sorted(admitted))
