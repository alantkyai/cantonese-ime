import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from cantonese_ime.yale_sources import verify_kfcd_yale_source
from tests import test_native_package as fixture
from tools import package_native as package

PROJECT = Path(__file__).resolve().parents[1]
ALTERNATES = {'deu':['deeu'],'eu':['eeu'],'meu':['meeu'],'peu':['peeu'],'seu':['seeu'],'zeu':['jeeu']}


class NativeYaleSourcePackageTests(unittest.TestCase):
    """Selected-source guards use real source bytes in a synthetic package."""
    # Reuse setup helpers without discovering or inheriting the earlier suite.
    setUp = fixture.NativePackageTests.setUp
    write = fixture.NativePackageTests.write
    json = fixture.NativePackageTests.json
    fake_configure = fixture.NativePackageTests.fake_configure
    stage = fixture.NativePackageTests.stage
    assert_rejected_before_staging = fixture.NativePackageTests.assert_rejected_before_staging

    def select_kfcd(self):
        relative = 'data/mappings/kfcd.sources.lock.json'
        self.write(relative,(PROJECT/relative).read_bytes())
        self.kfcd_lock = json.loads((self.root/relative).read_text('utf-8'))
        self.kfcd_vendor = self.kfcd_lock['local_directory']
        shutil.copytree(PROJECT/self.kfcd_vendor,self.root/self.kfcd_vendor)
        self.verifier = self.write('cantonese_ime/yale_sources.py',(PROJECT/'cantonese_ime/yale_sources.py').read_bytes())
        source = verify_kfcd_yale_source(self.root,self.root/relative,alternates=ALTERNATES)
        source.update(verifier_file='cantonese_ime/yale_sources.py',verifier_sha256=package.digest(self.verifier))
        self.kfcd_source = source
        for name in self.mapping_names:
            value = json.loads((self.root/'data/mappings'/name).read_text('utf-8'))
            value['source_metadata']['yale_kfcd_numeric'] = source
            self.json('data/mappings/'+name,value)
        self.rehash_mappings()

    def rehash_mappings(self):
        self.mapping_manifest['profile_version']='cantonese-yale-ascii-v3'
        self.mapping_manifest['files']={name:package.digest(self.root/'data/mappings'/name) for name in self.mapping_names}
        self.json('data/mappings/build.manifest.json',self.mapping_manifest)

    def test_selected_kfcd_retains_original_notices_even_without_markdown_links(self):
        self.select_kfcd()
        manifest = self.stage()
        paths = {row['path'] for row in manifest['files']}
        for name in ('README.md','LICENSE','LICENSE-CC-BY-3.0.txt','ATTRIBUTION.md'):
            self.assertIn(self.kfcd_vendor+'/'+name,paths)
        self.assertIn('data/mappings/kfcd.sources.lock.json',paths)
        self.assertIn('cantonese_ime/yale_sources.py',paths)
        self.assertNotIn(self.kfcd_vendor+'/pingyambiu',paths)

    def test_selected_kfcd_table_and_verifier_changes_are_rejected(self):
        self.select_kfcd()
        path = self.root/self.kfcd_vendor/'pingyambiu'
        original = path.read_bytes()
        path.write_bytes(original+b'changed')
        self.assert_rejected_before_staging('differs from its lock')
        path.write_bytes(original)
        self.verifier.write_bytes(self.verifier.read_bytes()+b'changed')
        self.assert_rejected_before_staging('verifier changed')

    def test_selected_kfcd_evidence_must_agree_between_artifacts(self):
        self.select_kfcd()
        name = 'spellings.json'
        value = json.loads((self.root/'data/mappings'/name).read_text('utf-8'))
        del value['source_metadata']['yale_kfcd_numeric']
        self.json('data/mappings/'+name,value)
        self.rehash_mappings()
        self.assert_rejected_before_staging('disagree on selected KFCD')

    def test_yale_v3_cannot_omit_all_selected_source_evidence(self):
        self.rehash_mappings()
        self.assert_rejected_before_staging('lacks its KFCD source evidence')

    def test_kfcd_notice_edit_after_validation_cannot_replace_its_mapping_pin(self):
        self.select_kfcd()
        guard = package._kfcd_notice_inputs
        notice = self.root/self.kfcd_vendor/'LICENSE-CC-BY-3.0.txt'

        def edit_after_validation(**options):
            result = guard(**options)
            notice.write_bytes(notice.read_bytes()+b'changed after validation')
            return result

        with patch.object(package, '_kfcd_notice_inputs', side_effect=edit_after_validation), \
                patch.object(package.subprocess, 'run', side_effect=self.fake_configure) as launch, \
                self.assertRaisesRegex(ValueError, 'Validated package input changed'):
            package.stage(self.output, self.python)
        self.assertFalse(self.output.exists())
        launch.assert_not_called()

    def test_raw_kfcd_source_change_after_copy_is_rejected_without_bundling_it(self):
        self.select_kfcd()

        def edit_excluded_raw_table(args, **options):
            self.fake_configure(args, **options)
            table = self.root/self.kfcd_vendor/'pingyambiu'
            table.write_bytes(table.read_bytes()+b'changed after copy')

        with patch.object(package.subprocess, 'run', side_effect=edit_excluded_raw_table), \
                self.assertRaisesRegex(ValueError, 'Validated package input changed'):
            package.stage(self.output, self.python)
        self.assertFalse((self.output/'package-manifest.json').exists())
        self.assertFalse((self.output/self.kfcd_vendor/'pingyambiu').exists())

    def test_temporary_mapping_edit_cannot_hide_source_evidence_before_copy(self):
        self.select_kfcd()
        guard = package._kfcd_notice_inputs
        paths = [self.root/'data/mappings'/name for name in (*self.mapping_names, 'build.manifest.json')]
        originals = {path: path.read_bytes() for path in paths}

        def transient_source_removal(**options):
            for path in paths[:2]:
                value = json.loads(path.read_text('utf-8'))
                del value['source_metadata']['yale_kfcd_numeric']
                path.write_text(json.dumps(value), encoding='utf-8')
            value = json.loads(paths[2].read_text('utf-8'))
            value['profile_version'] = 'cantonese-yale-ascii-v2'
            paths[2].write_text(json.dumps(value), encoding='utf-8')
            try:
                return guard(**options)
            finally:
                for path, payload in originals.items():
                    path.write_bytes(payload)

        with patch.object(package, '_kfcd_notice_inputs', side_effect=transient_source_removal):
            manifest = self.stage()
        copied = {record['path'] for record in manifest['files']}
        self.assertIn('data/mappings/kfcd.sources.lock.json', copied)
        self.assertIn(self.kfcd_vendor+'/LICENSE-CC-BY-3.0.txt', copied)
