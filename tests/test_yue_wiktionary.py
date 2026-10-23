"""Pinned literal fields, source integrity and complete exclusion accounting."""
import bz2
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from cantonese_ime import yue_wiktionary as reader

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "data/supplements/yue-wiktionary.sources.lock.json"
VENDOR = ROOT / "data/vendor/yue-wiktionary/2026-10-01-e09d60b43588"
ALLOWED = {"nei", "hou", "gwong", "tai", "sung", "sik", "faan", "ng", "saam"}


def tag(name):
    return "{" + reader.XML_NAMESPACE + "}" + name


def base36(integer):
    result = ""
    while integer:
        integer, remainder = divmod(integer, 36)
        result = "0123456789abcdefghijklmnopqrstuvwxyz"[remainder] + result
    return result or "0"


def page(title, text, identity=1, *, namespace=0, revision_id=None, redirect=False):
    item = ET.Element(tag("page"))
    for name, value in (("title", title), ("ns", str(namespace)), ("id", str(identity))):
        ET.SubElement(item, tag(name)).text = value
    if redirect:
        ET.SubElement(item, tag("redirect"), title="other")
    revision = ET.SubElement(item, tag("revision"))
    for name, value in (("id", str(revision_id or 1000 + identity)), ("timestamp", "2026-09-30T12:00:00Z"),
                        ("model", "wikitext"), ("format", "text/x-wiki")):
        ET.SubElement(revision, tag(name)).text = value
    ET.SubElement(revision, tag("text"), bytes=str(len(text.encode("utf-8")))).text = text
    ET.SubElement(revision, tag("sha1")).text = base36(int(hashlib.sha1(text.encode()).hexdigest(), 16))
    return item


def document(pages, *, template_revision_override=None):
    root = ET.Element(tag("mediawiki"), version="0.11", attrib={"{http://www.w3.org/XML/1998/namespace}lang": "yue"})
    site = ET.SubElement(root, tag("siteinfo"))
    ET.SubElement(site, tag("dbname")).text = "yuewiktionary"
    for ordinal, (_, (title, revision_id, file, _)) in enumerate(reader._TEMPLATE_SPECS.items(), 100):
        chosen = (template_revision_override or {}).get(title, revision_id)
        root.append(page(title, (VENDOR / file).read_text("utf-8"), ordinal,
                         namespace=10, revision_id=chosen))
    root.extend(pages)
    return ET.tostring(root, encoding="utf-8")


class LiteralReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="yue-wiktionary-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / reader.DATA_FILE

    def read(self, pages, **options):
        self.path.write_bytes(bz2.compress(document(pages, **options)))
        stats, reviews, pages_out, sections, fields = {}, [], [], [], []
        entries = list(reader.read_yue_wiktionary_entries(self.path, allowed_bases=ALLOWED,
            stats=stats, review_rows=reviews, page_rows=pages_out, section_rows=sections, field_rows=fields))
        return entries, stats, reviews, pages_out, sections, fields

    def reject_xml(self, xml, *, compressed=None):
        self.path.write_bytes(compressed if compressed is not None else bz2.compress(xml))
        stats, reviews = {"sentinel": 1}, [{"sentinel": True}]
        iterator = reader.read_yue_wiktionary_entries(self.path, allowed_bases=ALLOWED,
                                                    stats=stats, review_rows=reviews)
        with self.assertRaises(ValueError):
            next(iterator)
        self.assertEqual(stats, {"sentinel": 1})
        self.assertEqual(reviews, [{"sentinel": True}])

    def test_literal_own_fields_variants_duplicates_zero_and_source_locations(self):
        text = "prefix\n=={{langue|yue}}==\n===發音===\n: {{zh-pron|m=Mandarin|c= NEI5  HOU2,nei4 hou2}}\n{{Yue-rom|nei5 hou2}}"
        entries, counts, reviews, pages, sections, fields = self.read([page("你好", text)])
        self.assertEqual([value.reading for value in entries], ["nei4 hou2", "nei5 hou2"])
        self.assertTrue(all(value.weight == 0 and value.source == reader.SOURCE_ID for value in entries))
        self.assertEqual((counts["accepted_variant_occurrences"], counts["duplicate_pair_occurrences"]), (3, 1))
        self.assertEqual((len(pages), len(sections)), (4, 2))
        variants = [row for row in fields if row["scope"] == "variant"]
        self.assertEqual(len(variants), 3)
        self.assertEqual(reviews, [])
        first = variants[0]
        self.assertEqual(first["source_line"], 4)
        self.assertEqual(first["source_character_offset"], text.index("{{zh-pron"))
        self.assertEqual(first["wikitext_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(first["page_id"], "1")
        self.assertEqual(first["revision_id"], "1001")
        self.assertIn("oldid=1001", first["revision_url"])
        self.assertIn("action=history", first["history_url"])
        self.assertNotIn("Mandarin", " ".join(value.reading for value in entries))

    def test_documented_paired_superscripts_and_full_phrase(self):
        one = page("廣", "=={{langue|yue}}==\n{{粵拼|GWONG|GWONG²}}")
        phrase = page("睇餸食飯", "=={{langue|yue}}==\n{{粵拼|tai|tai²|sung|sung³|sik|sik⁶|faan|faan⁶}}", 2)
        entries, _, reviews, _, _, fields = self.read([one, phrase])
        self.assertEqual({(row.text, row.reading) for row in entries}, {("廣", "gwong2"), ("睇餸食飯", "tai2 sung3 sik6 faan6")})
        self.assertEqual(reviews, [])
        self.assertTrue(all(row["unicode_tone_conversion"] for row in fields if row["scope"] == "variant"))
        self.assertIn("GWONG²", next(row["raw_reading"] for row in fields if row["scope"] == "variant"))

    def test_marked_tone_change_is_not_repaired_and_other_variant_retained(self):
        entries, counts, reviews, *_ = self.read([page("你好", "=={{langue|yue}}==\n{{zh-pron|c=nei5-2 hou2,nei5 hou2}}")])
        self.assertEqual([value.reading for value in entries], ["nei5 hou2"])
        self.assertEqual(counts["excluded_syntax_or_marked_notation"], 1)
        self.assertEqual(reviews[0]["raw_reading"], "nei5-2 hou2")

    def test_comments_protected_nested_and_unclosed_blocks_cannot_supply_readings(self):
        text = ("=={{langue|yue}}==\n<!--\n{{Yue-rom|nei5 hou2}}\n-->\n"
                "<pre><pre>\n{{Yue-rom|nei5 hou2}}\n</pre>\n{{Yue-rom|nei5 hou2}}\n</pre>\n"
                "<nowiki>\n{{zh-pron|c=nei5 hou2}}\n</nowiki>\n"
                "<source>\n{{Yue-rom|nei5 hou2}}")
        entries, counts, reviews, _, _, fields = self.read([page("你好", text)])
        self.assertEqual(entries, [])
        self.assertEqual(counts["excluded_comment"], 1)
        self.assertEqual(counts["excluded_protected_text"], 4)
        self.assertEqual(counts["sections_without_recognized_pronunciation_field"], 1)
        self.assertEqual(len([row for row in fields if row["scope"] == "call"]), 5)
        self.assertEqual(len(reviews), 6)

    def test_nested_and_non_line_leading_calls_and_inline_comments_are_reviewed(self):
        text = ("=={{langue|yue}}==\n{{wrapper|\n{{Yue-rom|nei5 hou2}}\n}}\n"
                "*{{Yue-rom|nei5 hou2}}\n{{zh-pron|c={{other|nei5 hou2}}}}\n"
                "{{Yue-rom|nei5 <!-- editorial --> hou2}}")
        entries, counts, reviews, *_ = self.read([page("你好", text)])
        self.assertEqual(entries, [])
        self.assertEqual(counts["unsupported_nested_or_non_line_leading_template"], 3)
        self.assertEqual(counts["unsupported_comment_or_protected_content"], 1)
        self.assertEqual(len(reviews), 4)

    def test_multiple_c_fields_are_all_located_and_neither_first_nor_last_wins(self):
        entries, counts, reviews, _, _, fields = self.read([page("你好",
            "=={{langue|yue}}==\n{{zh-pron|c=nei5 hou2|c=nei4 hou2}}\n{{zh-pron|m=ni3 hao3}}")])
        self.assertEqual(entries, [])
        parameters = [row for row in fields if row["scope"] == "parameter"]
        self.assertEqual([row["raw_reading"] for row in parameters], ["nei5 hou2", "nei4 hou2"])
        self.assertEqual(counts["unsupported_no_unique_c_parameter"], 2)
        self.assertEqual(len(reviews), 4)  # two fields plus their two parent calls

    def test_nonhan_unknown_and_alignment_exclusions_keep_raw_source_fields(self):
        entries, counts, reviews, *_ = self.read([
            page("你A", "=={{langue|yue}}==\n{{Yue-rom|nei5 hou2}}"),
            page("你好", "=={{langue|yue}}==\n{{Yue-rom|yan4 hou2}}", 2),
            page("你", "=={{langue|yue}}==\n{{Yue-rom|nei5 hou2}}", 3)])
        self.assertEqual(entries, [])
        self.assertEqual({row["reason"] for row in reviews}, {"non_han_headword", "unknown_base", "unaligned_headword"})
        self.assertEqual(next(row["unknown_bases"] for row in reviews if row["reason"] == "unknown_base"), ["yan"])
        self.assertEqual(counts["quarantined_variant_occurrences"], 3)

    def test_paired_argument_mismatch_odd_named_and_html_tone_are_not_repaired(self):
        text = ("=={{langue|yue}}==\n{{粵拼|guong|gwong²}}\n{{粵拼|gwong}}\n"
                "{{粵拼|1=gwong|2=gwong²}}\n{{粵拼|gwong|gwong<sup>2</sup>}}")
        entries, counts, reviews, *_ = self.read([page("廣", text)])
        self.assertEqual(entries, [])
        self.assertEqual(counts["unsupported_paired_argument_shape"], 2)
        self.assertEqual(counts["unverified_display_or_index_mismatch"], 2)
        self.assertEqual(len(reviews), 4)

    def test_all_pages_sections_redirects_other_languages_and_missing_fields_accounted(self):
        entries, counts, reviews, pages, sections, fields = self.read([
            page("你好", "=={{langue|cmn}}==\n{{zh-pron|c=nei5 hou2}}\n=={{langue|yue}}==\nno explicit field"),
            page("你", "=={{langue|yue}}==\n{{Yue-rom|nei5}}", 2, redirect=True),
            page("模:Other", "=={{langue|yue}}==\n{{Yue-rom|nei5}}", 3, namespace=10)])
        self.assertEqual(entries, [])
        self.assertEqual(len(pages), 6)
        self.assertEqual(counts["main_namespace_pages"], 2)
        self.assertEqual(len(sections), 3)
        self.assertEqual(counts["excluded_non_yue_language_context"], 1)
        self.assertEqual(counts["sections_without_recognized_pronunciation_field"], 1)
        self.assertEqual([row["status"] for row in pages if row["namespace"] == "0"],
                         ["selected_yue_section", "excluded_redirect"])
        self.assertEqual(reviews[0]["reason"], "missing_supported_pronunciation_field")

    def test_unsupported_main_revision_and_changed_template_revision_not_admitted(self):
        item = page("你好", "=={{langue|yue}}==\n{{Yue-rom|nei5 hou2}}")
        item.append(copy.deepcopy(item.find(tag("revision"))))
        entries, counts, reviews, *_ = self.read([item])
        self.assertEqual(entries, [])
        self.assertEqual(counts["unsupported_revision_count"], 1)
        self.assertEqual(reviews[0]["revision_ids"], ["1001", "1001"])
        entries, counts, reviews, *_ = self.read([page("你好", "=={{langue|yue}}==\n{{Yue-rom|nei5 hou2}}")],
            template_revision_override={"模:Yue-rom": 10753})
        self.assertEqual(entries, [])
        self.assertEqual(counts["unsupported_template_revision"], 1)
        self.assertEqual(reviews[0]["reason"], "unsupported_template_revision")

    def test_archive_xml_header_entities_and_late_integrity_fail_before_publication(self):
        xml = document([page("你好", "=={{langue|yue}}==\n{{Yue-rom|nei5 hou2}}")])
        for bad in (b"not xml", b"\xff", xml.replace(b'version="0.11"', b'version="0.10"'),
                    xml.replace(b"yuewiktionary", b"enwiktionary"),
                    b'<!DOCTYPE mediawiki [<!ENTITY leak SYSTEM "file:///secret">]>' + xml,
                    xml.replace(b'bytes="55"', b'bytes="999"') if b'bytes="55"' in xml else xml.replace(b"nei5", b"nei4")):
            with self.subTest(prefix=bad[:50]):
                self.reject_xml(bad)
        for compressed in (b"broken", gzip.compress(xml), bz2.compress(xml)[:-4], bz2.compress(xml) + b"trailing"):
            with self.subTest(archive=compressed[:10]):
                self.reject_xml(xml, compressed=compressed)
        empty = ET.Element(tag("mediawiki"), version="0.11", attrib={"{http://www.w3.org/XML/1998/namespace}lang": "yue"})
        ET.SubElement(ET.SubElement(empty, tag("siteinfo")), tag("dbname")).text = "yuewiktionary"
        self.reject_xml(ET.tostring(empty))

    def test_declared_bounds_do_not_produce_partial_entries(self):
        xml = document([page("你好", "=={{langue|yue}}==\n{{Yue-rom|nei5 hou2}}")])
        for name, limit in (("MAX_ARCHIVE_BYTES", 100), ("MAX_XML_BYTES", 100),
                            ("MAX_XML_NODES", 5), ("MAX_XML_DEPTH", 2), ("MAX_PAGES", 1), ("MAX_TEXT_BYTES", 5),
                            ("MAX_FIELD_RECORDS", 1)):
            with self.subTest(name=name), patch.object(reader, name, limit):
                self.reject_xml(xml)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="yue-snapshot-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.lock = json.loads(LOCK.read_text("utf-8"))
        for item in self.lock["files"]:
            shutil.copyfile(VENDOR / item["name"], self.directory / item["name"])

    def verify(self):
        reader.verify_yue_wiktionary_snapshot(self.directory, self.lock)

    def relock(self, name, content):
        (self.directory / name).write_bytes(content)
        item = next(row for row in self.lock["files"] if row["name"] == name)
        item.update(size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())

    def test_actual_snapshot_and_conservative_union_counts(self):
        self.verify()
        counts, pages, sections, fields, reviews = {}, [], [], [], []
        entries = list(reader.read_yue_wiktionary_entries(self.directory / reader.DATA_FILE,
            stats=counts, page_rows=pages, section_rows=sections, field_rows=fields, review_rows=reviews))
        self.assertEqual((len(entries), counts["unique_texts"]), (1486, 1391))
        self.assertEqual((counts["accepted_variant_occurrences"], counts["duplicate_pair_occurrences"]), (1925, 439))
        self.assertEqual((len(pages), len(sections), len(fields), len(reviews)), (11396, 19804, 5366, 647))
        self.assertEqual(counts["recognized_main_pronunciation_calls"], 3101)
        self.assertEqual(counts["recognized_yue_pronunciation_calls"], 2327)
        self.assertEqual(len([row for row in fields if row["scope"] == "call"]), 3101)
        self.assertEqual(Counter(row["status"] for row in fields if row["scope"] == "variant")["admitted_pair"], 1486)

    def test_locked_bytes_safe_paths_and_notice_integrity(self):
        original = copy.deepcopy(self.lock)
        for name in ("../escape", "C:/escape", "folder/../escape", "source."):
            with self.subTest(name=name):
                self.lock = copy.deepcopy(original)
                self.lock["files"][0]["name"] = name
                with self.assertRaises(ValueError):
                    self.verify()
        self.lock = copy.deepcopy(original)
        self.lock["files"].append(copy.deepcopy(self.lock["files"][0]))
        with self.assertRaises(ValueError):
            self.verify()
        self.lock = copy.deepcopy(original)
        path = self.directory / "ATTRIBUTION.md"
        path.write_bytes(path.read_bytes().replace(b"Yue", b"Bad", 1))
        with self.assertRaisesRegex(ValueError, "differs from its lock"):
            self.verify()

    def test_wrong_source_license_full_terms_and_official_checksum_rejected(self):
        original = copy.deepcopy(self.lock)
        self.lock["license"] = "CC-BY-4.0"
        with self.assertRaises(ValueError):
            self.verify()
        self.lock = copy.deepcopy(original)
        self.relock("LICENSE-CC-BY-SA-4.0.txt", b"Attribution-ShareAlike 4.0 International")
        with self.assertRaisesRegex(ValueError, "full license"):
            self.verify()
        self.relock("LICENSE-CC-BY-SA-4.0.txt", (VENDOR / "LICENSE-CC-BY-SA-4.0.txt").read_bytes())
        self.relock("yue-20261001-sha1sums.txt", ("0" * 40 + "  " + reader.DATA_FILE).encode())
        with self.assertRaisesRegex(ValueError, "official checksum"):
            self.verify()

    def test_template_revision_source_and_inventory_cannot_drift(self):
        original = copy.deepcopy(self.lock)
        self.lock["template_revisions"][0]["revision_id"] += 1
        with self.assertRaisesRegex(ValueError, "template evidence"):
            self.verify()
        self.lock = copy.deepcopy(original)
        name = "source-template-jyutping.wikitext"
        self.relock(name, (self.directory / name).read_bytes().replace(b"32", b"64"))
        with self.assertRaisesRegex(ValueError, "template evidence"):
            self.verify()
        self.relock(name, (VENDOR / name).read_bytes())
        self.lock["parser_attestation"]["base_count"] = 877
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
