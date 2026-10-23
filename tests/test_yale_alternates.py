"""Project-authored isolated regression/complexity fixtures, not language QA."""
from contextlib import closing
import json
from itertools import product
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cantonese_ime import Engine
from cantonese_ime.engine import _match_yale_word
from cantonese_ime.mappings import build_mapping_artifacts, spelling_variants, yale_ascii, yale_ascii_mapping, yale_ascii_variants


EXPECTED = (("deu", "dew", "deeu", "掉", "6"), ("eu", "ew", "eeu", "歐", "1"),
            ("meu", "mew", "meeu", "貓", "1"), ("peu", "pew", "peeu", "飄", "1"),
            ("seu", "sew", "seeu", "小", "1"), ("zeu", "jew", "jeeu", "蕉", "1"))


class YaleAlternateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="isolated-yale-alternates-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "synthetic.sqlite3"
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript("""
                CREATE TABLE entries(id INTEGER PRIMARY KEY,text TEXT,reading TEXT,base_reading TEXT,weight REAL,
                                     UNIQUE(text,reading));
                CREATE INDEX entries_base_reading ON entries(base_reading);
            """)
            rows = [(text, base + tone, 20) for base, _, _, text, tone in EXPECTED]
            rows += [("吊", "deu6", 1), ("掉低", "deu6 dai1", 100), ("低", "dai1", 10),
                     ("好", "hou2", 10), ("你", "nei5", 10),
                     ("三音", "e1 e1 u1", 20), ("三音掉", "e1 e1 u1 deu6", 20),
                     ("歐掉", "eu1 deu6", 20),
                     ("假音", "de1 e1 u6", 999999),
                     ("古橋", "geu1 hou2", 20)]
            # A stored mixed word tests alternate/primary combinations without
            # relying on the ordinary syllable frontier discovering the path.
            rows += [("混合", "deu6 eu1 meu1 peu1 seu1 zeu1 nei5 hou2", 20)]
            rows += [("長" * 32, " ".join(["deu6"] * 32), 20),
                     ("長" * 31 + "短", " ".join(["deu6"] * 32), 1)]
            for text, reading, weight in rows:
                base = " ".join(token[:-1] for token in reading.split())
                db.execute("INSERT INTO entries(text,reading,base_reading,weight) VALUES (?,?,?,?)", (text, reading, base, weight))
            db.commit()

    def engine(self, **options):
        engine = Engine(self.database, **options)
        self.addCleanup(engine.close)
        return engine

    def candidates(self, engine, raw, *, mode="forgiving"):
        return {(row.text, row.reading): row for row in engine.lookup(raw, limit=90, mode=mode)}

    def test_all_six_primary_and_source_alternates_are_whole_syllables_with_same_tones(self):
        engine = self.engine()
        for base, primary, alternate, text, tone in EXPECTED:
            with self.subTest(base=base):
                self.assertEqual(yale_ascii(base), primary)
                self.assertEqual(yale_ascii_variants(base), (primary, alternate))
                self.assertIn(alternate, spelling_variants(base))
                self.assertEqual(spelling_variants(base, "jyutping"), {base: 0.0})
                for raw in (primary, alternate, primary + tone, alternate + tone):
                    self.assertIn((text, base + tone), self.candidates(engine, raw))
                wrong = str(int(tone) % 6 + 1)
                self.assertNotIn((text, base + tone), self.candidates(engine, alternate + wrong))
                self.assertNotIn((text, base + tone), self.candidates(engine, alternate + tone, mode="jyutping"))

    def test_numeric_closure_rejects_a_high_weight_internal_split_and_keeps_partial_tones(self):
        engine = self.engine()
        self.assertNotIn(("假音", "de1 e1 u6"), self.candidates(engine, "deeu6"))
        for raw in ("deeudai1", "deeu6dai1", "deeu6'dai1"):
            self.assertIn(("掉低", "deu6 dai1"), self.candidates(engine, raw))

    def test_exported_alternate_records_have_source_and_rule_metadata(self):
        _, artifact = build_mapping_artifacts([], [row[0] for row in EXPECTED])
        rules = {rule["rule_id"] for rule in artifact["rules"]}
        for base, _, alternate, _, _ in EXPECTED:
            row = next(record for record in artifact["aliases"]
                       if (record["canonical"], record["spelling"]) == (base, alternate))
            self.assertIn(row["rule_id"], rules)
            self.assertEqual(row["source"], ("yale_kfcd_numeric",))
            self.assertIn(alternate, artifact["yale_ascii"]["alternate_spellings"][base])
        self.assertEqual(artifact["sources"]["yale_kfcd_numeric"]["license"], "CC-BY-3.0")

    def test_published_nasals_are_attested_extensions_without_new_spellings(self):
        for base in ("hm", "hng"):
            route = yale_ascii_mapping(base)
            self.assertEqual((route.spelling, route.status, route.source), (base, "extension", ("yale_kfcd_numeric",)))
            self.assertEqual(spelling_variants(base)[base], 0.0)
            self.assertEqual(spelling_variants(base, "jyutping"), {base: 0.0})
        for base in ("ngm", "soei"):
            self.assertEqual(yale_ascii_mapping(base).status, "jyutping_fallback")

    def test_all_compact_and_boundary_mixtures_match_stored_words(self):
        engine = self.engine()
        reading = "deu6 eu1 meu1 peu1 seu1 zeu1 nei5 hou2"
        for raw in ("deeu" + "ew" + "meeu" + "pew" + "seeu" + "jew" + "neihou",
                    "dew'eeu'mew'peeu'sew'jeeu'nei'hou",
                    "deeu6'ew1'meeu1'pew1'seeu1'jew1'nei5'hou2"):
            with self.subTest(raw=raw):
                self.assertIn(("混合", reading), self.candidates(engine, raw))

    def test_literal_old_index_collision_and_cross_boundary_normalization_are_retained(self):
        engine = self.engine()
        rows = self.candidates(engine, "eeu")
        self.assertIn(("三音", "e1 e1 u1"), rows)
        self.assertIn(("歐", "eu1"), rows)
        # The existing literal primary key eeudew itself normalizes; keeping
        # only query normalization against the old index would lose this word.
        rows = self.candidates(engine, "eeudeeu")
        self.assertIn(("三音掉", "e1 e1 u1 deu6"), rows)
        self.assertIn(("歐掉", "eu1 deu6"), rows)
        rows = self.candidates(engine, "e'e'u'deeu")
        self.assertIn(("三音掉", "e1 e1 u1 deu6"), rows)
        self.assertNotIn(("歐掉", "eu1 deu6"), rows)

    def test_coarse_key_cannot_add_an_unattested_whole_syllable_alias(self):
        engine = self.engine()
        self.assertIn(("古橋", "geu1 hou2"), self.candidates(engine, "gewhou"))
        self.assertNotIn("geeu", spelling_variants("geu"))
        self.assertNotIn(("古橋", "geu1 hou2"), self.candidates(engine, "geeuhou"))
        self.assertNotIn(("掉", "deu6"), self.candidates(engine, "de'eu"))

    def test_long_repeated_32_variants_use_full_word_index_and_original_consumption(self):
        engine = self.engine()
        reading = " ".join(["deu6"] * 32)
        for raw in ("deeu" * 32, "'".join(["deeu"] * 32), "deeu6" * 32,
                    "dew" * 16 + "deeu" * 16):
            with self.subTest(length=len(raw)):
                rows = self.candidates(engine, raw)
                self.assertIn(("長" * 32, reading), rows)
                self.assertEqual(rows[("長" * 32, reading)].consumed_input, len(raw))
        raw = "  " + "deeu" * 32 + "  "
        self.assertEqual(self.candidates(engine, raw)[("長" * 32, reading)].consumed_input, len(raw))

    def test_word_verification_collapses_combinations_instead_of_expanding_two_to_32(self):
        forms = tuple((("ew", .45), ("eeu", .45)) for _ in range(32))
        work = [0]
        result = _match_yale_word("eeu" * 32, forms, work=work)
        self.assertAlmostEqual(result, .45 * 32)
        self.assertLessEqual(work[0], 64)
        self.assertIsNone(_match_yale_word("e'eu" * 32, forms))

    def test_every_apostrophe_placement_matches_an_independent_fixed_word_oracle(self):
        # A natural literal e+e+u collision must remain distinct from eu, even
        # though both use the same coarse eeu/ew preselection bucket.
        for syllables in ((("e",), ("e",), ("u",), ("dew", "deeu")),
                          (("ew", "eeu"), ("dew", "deeu"))):
            allowed, compacts = set(), set()
            for sequence in product(*syllables):
                compacts.add("".join(sequence))
                for boundaries in product((False, True), repeat=len(sequence) - 1):
                    allowed.add(sequence[0] + "".join(("'" if mark else "") + word
                                                       for mark, word in zip(boundaries, sequence[1:])))
            forms = tuple(tuple((spelling, .45) for spelling in choices) for choices in syllables)
            for compact in compacts:
                for boundaries in product((False, True), repeat=len(compact) - 1):
                    raw = compact[0] + "".join(("'" if mark else "") + letter
                                                for mark, letter in zip(boundaries, compact[1:]))
                    self.assertEqual(_match_yale_word(raw, forms) is not None, raw in allowed,
                                     (syllables, raw))

    def test_full_raw_learning_keys_and_primary_spellings_stay_isolated_across_reopen(self):
        memory = self.root / "learning.json"
        with Engine(self.database, learning_path=memory) as engine:
            before = [candidate.text for candidate in engine.lookup("dew")]
            selected = next(row for row in engine.lookup("deeu") if row.text == "吊")
            engine.record_selection("deeu", selected)
            self.assertEqual(engine.lookup("deeu")[0].text, "吊")
            self.assertEqual([candidate.text for candidate in engine.lookup("dew")], before)
            long_raw = "deeu" * 32
            selected = next(row for row in engine.lookup(long_raw) if row.text.endswith("短"))
            engine.record_selection(long_raw, selected)
        saved = json.loads(memory.read_text(encoding="utf-8"))["selections"]
        self.assertEqual({row["input"] for row in saved}, {"deeu", "deeu" * 32})
        self.assertFalse(any(row["input"] in {"dew", "dew" * 32} for row in saved))
        with Engine(self.database, learning_path=memory) as engine:
            self.assertEqual(engine.lookup("deeu")[0].text, "吊")
            self.assertEqual(engine.lookup("deeu" * 32)[0].text, "長" * 31 + "短")
            self.assertEqual(engine.lookup("dew")[0].text, "掉")
            self.assertEqual(engine.lookup("dew" * 32)[0].text, "長" * 32)
            self.assertFalse(any(row.text == "吊" for row in engine.lookup("deeu", mode="jyutping")))

    def test_learning_the_same_canonical_raw_input_is_isolated_by_mode(self):
        memory = self.root / "mode-learning.json"
        with Engine(self.database, learning_path=memory) as engine:
            standard_before = [row.text for row in engine.lookup("deu", mode="jyutping")]
            chosen = next(row for row in engine.lookup("deu", mode="forgiving") if row.text == "吊")
            engine.record_selection("deu", chosen, mode="forgiving")
            self.assertEqual(engine.lookup("deu", mode="forgiving")[0].text, "吊")
            self.assertEqual([row.text for row in engine.lookup("deu", mode="jyutping")], standard_before)
        with Engine(self.database, learning_path=memory) as engine:
            self.assertEqual(engine.lookup("deu", mode="forgiving")[0].text, "吊")
            self.assertEqual(engine.lookup("deu", mode="jyutping")[0].text, "掉")

    def test_homophone_pages_beyond_90_are_stable_for_alternate_inputs(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.executemany("INSERT INTO entries(text,reading,base_reading,weight) VALUES (?,?,?,?)",
                [("詞" + chr(0x6000 + number), "deu6", "deu", 0) for number in range(210)])
            db.commit()
        engine = self.engine()
        expected = {"詞" + chr(0x6000 + number) for number in range(210)}
        seen, offset = [], 0
        for _ in range(30):
            page = engine.lookup_page("deeu", offset=offset, page_size=9)
            seen.extend(row.text for row in page.candidates)
            if expected <= set(seen):
                break
            self.assertIsNotNone(page.next_offset)
            offset = page.next_offset
        self.assertTrue(expected <= set(seen))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(seen[:9], [row.text for row in engine.lookup("deeu")])


if __name__ == "__main__":
    unittest.main()
