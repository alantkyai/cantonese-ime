"""Conservative WN-LMF source parsing; no product dictionary/runtime changes."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cantonese_ime.wordnet import read_wordnet_entries, verify_wordnet_snapshot


LICENSE = "https://creativecommons.org/licenses/by/4.0/"
DTD = '<!DOCTYPE LexicalResource SYSTEM "http://globalwordnet.github.io/schemas/WN-LMF-1.0.dtd">'


def entry(identity, text, readings, extra=""):
    forms = "".join(f'<Form writtenForm="{reading}"/>' for reading in readings)
    return f'<LexicalEntry id="{identity}"><Lemma writtenForm="{text}" partOfSpeech="n"/>{forms}{extra}</LexicalEntry>'


def xml(entries, english="", doctype=DTD):
    sibling = (f'<Lexicon id="cantown-en" language="en" license="{LICENSE}" version="1.0">{english}</Lexicon>'
               if english else "")
    return (f'<?xml version="1.0" encoding="UTF-8"?>{doctype}<LexicalResource>'
            f'<Lexicon id="cantown-yue" language="yue" license="{LICENSE}" version="1.0">{entries}</Lexicon>'
            f'{sibling}</LexicalResource>')


class WordnetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cantonese-wordnet-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "cantown.xml"
        self.allowed = {"nei", "hou", "waa", "jan", "jat", "cin", "ngaa", "aa", "ei", "m", "ng"}

    def read(self, content, **options):
        self.path.write_text(content, encoding="utf-8")
        return list(read_wordnet_entries(self.path, allowed_bases=self.allowed, **options))

    def assert_accounting(self, stats):
        self.assertEqual(stats["lexical_entries_total"], stats["input_rows"] + stats["excluded_lexical_entries"])
        self.assertEqual(stats["forms_total"], stats["form_candidates"] + stats["excluded_forms"])
        self.assertEqual(stats["input_rows"], stats["accepted_rows"] + stats["quarantined_rows"])
        self.assertEqual(stats["form_candidates"], stats["blank_forms"] + stats["accepted_entries"]
                         + stats["duplicate_entries"] + stats["quarantined_forms"])
        self.assertEqual(stats["nonblank_forms"], stats["accepted_entries"] + stats["duplicate_entries"] + stats["quarantined_forms"])

    def test_each_form_uses_only_its_own_lemma_not_senses_or_synsets(self):
        content = xml(entry("a", "你", ["nei5"], '<Sense id="sense-a" synset="shared"/>')
                      + entry("b", "話", ["waa6"], '<Sense id="sense-b" synset="shared"/>')
                      + '<Synset id="shared"><Definition>秘密 definition nei2</Definition><Example>例子 hou2</Example></Synset>')
        rows = self.read(content)
        self.assertEqual([(row.text, row.reading) for row in rows], [("你", "nei5"), ("話", "waa6")])
        self.assertTrue(all(row.weight == 0 and row.source == "wordnet:cantown" for row in rows))
        self.assertEqual(rows[0].base_reading, "nei")
        rows = self.read(xml(entry("c", "你好", ["nei5 hou2"])))
        self.assertEqual((rows[0].base_reading, rows[0].compact, rows[0].syllable_count), ("nei hou", "neihou", 2))

    def test_english_sibling_is_excluded_even_with_valid_han_and_jyutping(self):
        stats, review = {}, []
        rows = self.read(xml(entry("a", "你", ["nei5"]), english=entry("en-a", "話", ["waa6", ""])),
                         stats=stats, review_rows=review)
        self.assertEqual([(row.text, row.reading) for row in rows], [("你", "nei5")])
        self.assertEqual((stats["excluded_lexical_entries"], stats["excluded_forms"], stats["excluded_blank_forms"]), (1, 2, 1))
        self.assertEqual({row["status"] for row in review}, {"excluded"})
        self.assertTrue(all(row["reason"] == "non_yue_lexicon" and row["lexicon_id"] == "cantown-en" for row in review))
        self.assert_accounting(stats)

    def test_case_whitespace_normalization_and_exact_pair_dedup_preserve_tones(self):
        stats = {}
        rows = self.read(xml(entry("a", "你好", ["  NEI5   HOU2  ", "nei5 hou2", "nei2 hou2"])
                             + entry("b", "你好", ["nei5 hou2"])), stats=stats)
        self.assertEqual([row.reading for row in rows], ["nei5 hou2", "nei2 hou2"])
        self.assertEqual((stats["accepted_entries"], stats["duplicate_entries"], stats["normalized_reading_forms"]), (2, 2, 1))
        self.assertEqual(stats["accepted_rows"], 2)
        self.assert_accounting(stats)

    def test_syntax_tone_variants_and_unknown_bases_are_quarantined_without_repairs(self):
        stats, review = {}, []
        rows = self.read(xml(entry("a", "你", ["nei7", "nei5-2", "nei5/2", "nei5hou2", "yat6"])),
                         stats=stats, review_rows=review)
        self.assertEqual(rows, [])
        self.assertEqual([row["raw_reading"] for row in review], ["nei7", "nei5-2", "nei5/2", "nei5hou2", "yat6"])
        self.assertEqual([row["reason"] for row in review], ["noncanonical_jyutping"] * 4 + ["unattested_syllables"])
        self.assertEqual(review[-1]["unknown_bases"], ["yat"])
        self.assert_accounting(stats)

    def test_alignment_and_non_han_text_are_separate_from_syntax(self):
        stats, review = {}, []
        rows = self.read(xml(entry("a", "瓩", ["cin1 ngaa5"])
                             + entry("b", "你A", ["nei5 ei1"])
                             + entry("c", "你好！", ["nei5 hou2 aa1"])), stats=stats, review_rows=review)
        self.assertEqual(rows, [])
        self.assertEqual([row["reason"] for row in review], ["codepoint_syllable_alignment", "non_han_text", "non_han_text"])
        self.assertEqual(review[0]["text_codepoints"], 1)
        self.assertEqual(review[0]["syllable_count"], 2)
        self.assert_accounting(stats)

    def test_blank_forms_and_entries_without_forms_are_accounted_separately(self):
        stats, review = {}, []
        rows = self.read(xml(entry("a", "你", ["", "  ", "nei5"])
                             + entry("b", "話", []) + entry("c", "人", [""])), stats=stats, review_rows=review)
        self.assertEqual(len(rows), 1)
        self.assertEqual((stats["blank_forms"], stats["entries_without_forms"], stats["accepted_rows"], stats["quarantined_rows"]), (3, 1, 1, 2))
        self.assertEqual({row["status"] for row in review}, {"missing_reading"})
        self.assertEqual(next(row for row in review if row["entry_id"] == "b")["form_ordinal"], None)
        self.assert_accounting(stats)

    def test_review_rows_bind_original_file_entry_and_form_without_definitions(self):
        stats, review = {}, []
        content = xml(entry("original-id", "你", ["nei5", "nei5-2", ""], '<Sense id="s" synset="x"/>')
                      + '<Synset id="x"><Definition>SECRET DEFINITION</Definition></Synset>')
        self.read(content, stats=stats, review_rows=review)
        self.assertEqual([row["form_ordinal"] for row in review], [2, 3])
        self.assertTrue(all(row["entry_id"] == "original-id" and row["source_sha256"] == hashlib.sha256(content.encode()).hexdigest() for row in review))
        self.assertEqual(stats["review_records"], len(review))
        self.assertNotIn("SECRET", json.dumps(review))

    def test_root_identity_license_version_and_structural_changes_fail_before_yielding(self):
        valid = xml(entry("a", "你", ["nei5"]))
        changes = [valid.replace("LexicalResource", "WrongRoot"),
                   valid.replace('language="yue"', 'language="zh"'),
                   valid.replace('id="cantown-yue"', 'id="other"'),
                   valid.replace(LICENSE, "https://example.com/license"),
                   valid.replace('version="1.0"><LexicalEntry', 'version="2.0"><LexicalEntry'),
                   valid.replace('<Lemma writtenForm="你" partOfSpeech="n"/>', ''),
                   valid.replace('<Form writtenForm="nei5"/>', '<Form/>'),
                   valid.replace('<Form writtenForm="nei5"/>', '<Form writtenForm="nei5"><Representation/></Form>'),
                   xml(entry("a", "你", ["nei5"]) + entry("a", "話", ["waa6"])),
                   xml(entry("a", "你", ["nei5"]) + '<LexicalEntry id="bad"><Form writtenForm="waa6"/></LexicalEntry>')]
        for content in changes:
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    next(read_wordnet_entries(self.path, allowed_bases=self.allowed))

    def test_nested_lexical_data_cannot_hide_in_semantic_metadata(self):
        bad = xml(entry("a", "你", ["nei5"], '<Sense id="s"><Form writtenForm="waa6"/></Sense>'))
        with self.assertRaisesRegex(ValueError, "nested"):
            self.read(bad)

    def test_known_ascii_tags_are_metadata_and_do_not_repair_ellipsis_forms(self):
        stats, review = {}, []
        entries = ('<LexicalEntry id="a"><Lemma writtenForm="你"/>'
                   '<Form writtenForm="nei5"><Tag category="transliteration">ascii</Tag></Form>'
                   '<Form writtenForm="nei5...hou2"><Tag category="transliteration">ascii</Tag></Form></LexicalEntry>')
        rows = self.read(xml(entries), stats=stats, review_rows=review)
        self.assertEqual([(row.text, row.reading) for row in rows], [("你", "nei5")])
        self.assertEqual(stats["ignored_form_tags"], 2)
        self.assertEqual(review[0]["raw_reading"], "nei5...hou2")
        self.assertEqual(review[0]["reason"], "noncanonical_jyutping")
        for bad in (entries.replace('category="transliteration"', 'category="pronunciation"'),
                    entries.replace('>ascii</Tag>', '>nei2</Tag>')):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "metadata"):
                self.read(xml(bad))

    def test_known_external_dtd_is_offline_and_other_dtd_or_entities_are_refused(self):
        self.assertEqual(len(self.read(xml(entry("a", "你", ["nei5"])))), 1)
        self.assertEqual(len(self.read(xml(entry("a", "你", ["nei5"]), doctype=""))), 1)
        for declaration in ('<!DOCTYPE LexicalResource SYSTEM "https://example.com/remote.dtd">',
                            '<!DOCTYPE LexicalResource [<!ENTITY local "nei5">]>',
                            '<!DOCTYPE LexicalResource [<!ENTITY secret SYSTEM "file:///private">]>'):
            with self.subTest(declaration=declaration), self.assertRaisesRegex(ValueError, "DTD|entity"):
                self.read(xml(entry("a", "你", ["nei5"]), doctype=declaration))
        with self.assertRaisesRegex(ValueError, "Malformed"):
            self.read(xml(entry("a", "你", ["&undefined;"])))

    def test_size_node_depth_and_inventory_bounds_are_explicit(self):
        content = xml(entry("a", "你", ["nei5"]))
        for name, value in (("MAX_SOURCE_BYTES", 20), ("MAX_XML_NODES", 2), ("MAX_XML_DEPTH", 2)):
            with self.subTest(name=name), patch("cantonese_ime.wordnet." + name, value), self.assertRaisesRegex(ValueError, "limit"):
                self.read(content)
        self.path.write_text(content, encoding="utf-8")
        for bases in (set(), {"nei5"}, "nei", {"UPPER"}):
            with self.subTest(bases=bases), self.assertRaises(ValueError):
                list(read_wordnet_entries(self.path, allowed_bases=bases))

    def snapshot_fixture(self):
        self.path.write_text(xml(entry("a", "你", ["nei5"])), encoding="utf-8")
        inventory = {"schema_version": 1, "bases": sorted(self.allowed), "baseline_database_sha256": "a" * 64}
        (self.root / "parser-attested-bases.json").write_text(json.dumps(inventory), encoding="utf-8")
        (self.root / "README.md").write_text("Creative Commons Attribution 4.0 International License", encoding="utf-8")
        (self.root / "LICENSE-CC-BY-4.0.txt").write_text("Attribution 4.0 International\nCreative Commons", encoding="utf-8")
        (self.root / "ATTRIBUTION.md").write_text("Fixture attribution", encoding="utf-8")
        records = [{"name": path.name, "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for path in self.root.iterdir() if path.is_file()]
        return {"files": records, "license": "CC-BY-4.0", "source_id": "wordnet:cantown", "data_file": "cantown.xml",
                "declaration_file": "README.md", "license_file": "LICENSE-CC-BY-4.0.txt",
                "parser_attestation": {"file": "parser-attested-bases.json", "base_count": len(self.allowed),
                    "sha256": hashlib.sha256((self.root / "parser-attested-bases.json").read_bytes()).hexdigest(),
                    "baseline_database_sha256": "a" * 64}}

    def test_snapshot_verification_and_default_frozen_inventory(self):
        lock = self.snapshot_fixture()
        verify_wordnet_snapshot(self.root, lock)
        self.assertEqual(len(list(read_wordnet_entries(self.path))), 1)
        for change in ("license", "inventory", "missing-notice", "duplicate-file"):
            bad = json.loads(json.dumps(lock))
            if change == "license":
                bad["license"] = "CC-BY-SA-4.0"
            elif change == "inventory":
                bad["parser_attestation"]["base_count"] += 1
            elif change == "missing-notice":
                bad["files"] = [row for row in bad["files"] if row["name"] != "ATTRIBUTION.md"]
            else:
                bad["files"].append(bad["files"][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_wordnet_snapshot(self.root, bad)
        self.path.write_text(self.path.read_text("utf-8") + "tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify_wordnet_snapshot(self.root, lock)

    def test_pinned_actual_snapshot_has_complete_form_and_entry_accounting(self):
        project = Path(__file__).resolve().parents[1]
        lock = json.loads((project / "data/supplements/wordnet.sources.lock.json").read_text(encoding="utf-8"))
        directory = project / lock["local_directory"]
        verify_wordnet_snapshot(directory, lock)
        stats, review = {}, []
        rows = list(read_wordnet_entries(directory / "cantown.xml", stats=stats, review_rows=review))
        self.assertEqual((stats["lexical_entries_total"], stats["input_rows"], stats["excluded_lexical_entries"]), (11672, 11667, 5))
        self.assertEqual((stats["forms_total"], stats["form_candidates"], stats["excluded_forms"]), (23738, 23733, 5))
        self.assertEqual((stats["blank_forms"], stats["nonblank_forms"]), (11660, 12073))
        self.assertEqual(stats["ignored_form_tags"], 7)
        self.assertEqual((stats["quarantined_forms"], stats["accepted_entries"], stats["duplicate_entries"]), (222, 10775, 1076))
        self.assertEqual({reason: stats.get("review_" + reason, 0) for reason in (
            "noncanonical_jyutping", "unattested_syllables", "codepoint_syllable_alignment", "non_han_text")},
            {"noncanonical_jyutping": 97, "unattested_syllables": 38, "codepoint_syllable_alignment": 86, "non_han_text": 1})
        normalized = [row for row in review if row["reason"] == "normalized_reading"]
        self.assertEqual((len(normalized), stats["normalized_reading_forms"]), (20, 20))
        # The selected raw rows contain repeated ASCII separators, not repaired
        # syllables. Removing only those extra separators reproduces the output.
        self.assertTrue(all("  " in row["raw_reading"] and " ".join(row["raw_reading"].split()) == row["reading"]
                            and row["status"] == "informational" for row in normalized))
        self.assertEqual(len(rows), len({(row.text, row.reading) for row in rows}))
        self.assertTrue(all(row.source == "wordnet:cantown" and row.weight == 0 for row in rows))
        self.assertEqual(stats["review_records"], len(review))
        self.assert_accounting(stats)


if __name__ == "__main__":
    unittest.main()
