from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest

from tests import test_dictionary_cccedict_headwords as fixture
from tools.audit_cccedict_headwords import audit_cccedict_headwords, sha

PROJECT = Path(__file__).resolve().parents[1]


class HeadwordSourceAuditTests(unittest.TestCase):
    write_headwords = fixture.CanonicalHeadwordTests.write_headwords
    selected_metadata = fixture.CanonicalHeadwordTests.selected_metadata
    build = fixture.CanonicalHeadwordTests.build

    def setUp(self):
        fixture.CanonicalHeadwordTests.setUp(self)
        self.database,_ = self.build('independent-audit',headwords=True)
        self.lock = json.loads(self.lock_path.read_text('utf-8'))
        selected = dict(self.lock,source_lock_sha256=sha(self.lock_path),
                        parser_file='cantonese_ime/cccedict_headwords.py',
                        parser_sha256=sha(PROJECT/'cantonese_ime/cccedict_headwords.py'),
                        encoder_file='cantonese_ime/autoencode.py',
                        encoder_sha256=sha(PROJECT/'cantonese_ime/autoencode.py'),
                        authored_cantonese_readings=False)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('UPDATE metadata SET value=? WHERE key=?',
                       (json.dumps({'supplements':{'cccedict_headwords':selected}}),'source_metadata'))
            db.commit()
        self.lock_audit = {'verified':True,'path':str(self.lock_path),'sha256':sha(self.lock_path),
                           'source_directory':str(self.vendor),
                           'files':[dict(row,matches_lock=True) for row in self.lock['files']]}

    def run_audit(self):
        verified = {'generated':{99999}}
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA query_only=ON')
            result = audit_cccedict_headwords(db,self.lock_audit,verified)
        return result,verified

    def mutate(self,sql,parameters=()):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute(sql,parameters)
            db.commit()

    def assert_rejected_without_credit(self):
        result,verified = self.run_audit()
        self.assertFalse(result['mechanical_complete'],result)
        self.assertTrue(result['errors'])
        self.assertEqual(verified,{'generated':{99999}})

    def test_every_occurrence_and_complete_encoding_are_verified_before_id_credit(self):
        result,verified = self.run_audit()
        self.assertTrue(result['mechanical_complete'],result)
        self.assertEqual(result['counts']['generated_rows_credited'],2)
        self.assertEqual(result['counts']['source_occurrences_verified'],14)
        self.assertEqual(len(verified['generated']),3)

    def test_wrong_generated_weight_cannot_be_credited(self):
        self.mutate("UPDATE entries SET weight=9 WHERE source='cccedict:headwords:autoencoded'")
        self.assert_rejected_without_credit()

    def test_quarantine_cannot_be_relabelled_complete(self):
        self.mutate("UPDATE cccedict_headword_encodings SET status='encoded_unique' WHERE status='truncated'")
        self.assert_rejected_without_credit()

    def test_changed_or_missing_source_occurrence_fails_closed(self):
        self.mutate('DELETE FROM cccedict_headword_forms WHERE line=(SELECT MIN(line) FROM cccedict_headword_forms)')
        self.assert_rejected_without_credit()

    def test_duplicate_ledger_rows_cannot_disappear_when_keys_are_collected(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript('''ALTER TABLE cccedict_headword_forms RENAME TO old_forms;
                CREATE TABLE cccedict_headword_forms AS SELECT * FROM old_forms;
                INSERT INTO cccedict_headword_forms SELECT * FROM old_forms LIMIT 1;
                DROP TABLE old_forms;''')
            db.commit()
        self.assert_rejected_without_credit()

    def test_fixed_boundary_survives_later_authored_source(self):
        self.mutate("INSERT INTO entries(text,reading,base_reading,compact,syllable_count,weight,source,origin) VALUES ('新','san1','san','san',1,0,'future:authored','supplement')")
        result,_ = self.run_audit()
        self.assertTrue(result['mechanical_complete'],result)

    def test_changed_fixed_translator_input_fails_even_with_valid_source(self):
        self.mutate("UPDATE entries SET weight=3 WHERE text='你' AND reading='nei5'")
        self.assert_rejected_without_credit()

    def test_raw_source_change_after_lock_audit_fails(self):
        path=self.vendor/'cedict_ts.u8'
        path.write_bytes(path.read_bytes()+b'changed')
        self.assert_rejected_without_credit()

    def test_missing_or_unverified_lock_cannot_credit_any_rows(self):
        self.lock_audit['verified']=False
        self.assert_rejected_without_credit()


if __name__=='__main__':
    unittest.main()
