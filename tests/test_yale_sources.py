from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from cantonese_ime.yale_sources import verify_kfcd_yale_source

ROOT = Path(__file__).resolve().parents[1]
LOCK = Path('data/mappings/kfcd.sources.lock.json')
ALTERNATES = {'deu':('deeu',),'eu':('eeu',),'meu':('meeu',),'peu':('peeu',),'seu':('seeu',),'zeu':('jeeu',)}


class YaleSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lock = json.loads((ROOT/LOCK).read_text('utf-8'))
        self.directory = self.root/self.lock['local_directory']
        shutil.copytree(ROOT/self.lock['local_directory'], self.directory)
        (self.root/LOCK).parent.mkdir(parents=True)
        self.save()

    def save(self):
        (self.root/LOCK).write_text(json.dumps(self.lock,ensure_ascii=False),encoding='utf-8')

    def verify(self, **options):
        return verify_kfcd_yale_source(self.root,self.root/LOCK,alternates=options.get('alternates',ALTERNATES))

    def test_original_all_rows_and_tones_supply_literal_aliases_and_nasals(self):
        report = self.verify()
        self.assertEqual((report['table_rows'],report['table_bases']),(3972,741))
        self.assertEqual(set(row['jyutping'][:-1] for row in report['selected_literal_rows']),set(ALTERNATES)|{'hm','hng'})
        self.assertFalse(report['independent_linguistic_approval'])

    def test_changed_table_is_rejected_even_with_a_rehashed_lock(self):
        path = self.directory/'pingyambiu'
        path.write_bytes(path.read_bytes().replace(b'deeu',b'deex'))
        record = next(row for row in self.lock['files'] if row['name']=='pingyambiu')
        record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        record['size_bytes'] = path.stat().st_size
        self.save()
        with self.assertRaisesRegex(ValueError,'upstream commit'):
            self.verify()

    def test_runtime_aliases_must_equal_the_pinned_selection(self):
        altered = deepcopy(ALTERNATES)
        altered['deu'] = ('deeu','deeeeeu')
        with self.assertRaisesRegex(ValueError,'spelling policy'):
            self.verify(alternates=altered)

    def test_missing_license_escaping_duplicate_and_changed_notice_are_rejected(self):
        for mutation in ('missing','escaping','duplicate','notice'):
            with self.subTest(mutation=mutation):
                original = deepcopy(self.lock)
                if mutation=='missing':
                    self.lock['files'].pop()
                elif mutation=='escaping':
                    self.lock['files'][0]['name']='../pingyambiu'
                elif mutation=='duplicate':
                    self.lock['files'][-1]=deepcopy(self.lock['files'][0])
                else:
                    self.lock['files'][-1]['sha256']='0'*64
                self.save()
                with self.assertRaises(ValueError):
                    self.verify()
                self.lock = original


if __name__=='__main__':
    unittest.main()
