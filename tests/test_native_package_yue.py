"""Selected Yue notices are pinned without distributing its raw XML source."""
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from tests import test_native_package as fixture
from tools import package_native as package

PROJECT = Path(__file__).resolve().parents[1]


class NativeYuePackageTests(unittest.TestCase):
    setUp = fixture.NativePackageTests.setUp
    write = fixture.NativePackageTests.write
    json = fixture.NativePackageTests.json
    fake_configure = fixture.NativePackageTests.fake_configure
    stage = fixture.NativePackageTests.stage
    assert_rejected_before_staging = fixture.NativePackageTests.assert_rejected_before_staging

    def select_yue(self):
        relative = 'data/supplements/yue-wiktionary.sources.lock.json'
        self.write(relative, (PROJECT/relative).read_bytes())
        lock = json.loads((self.root/relative).read_text('utf-8'))
        self.yue_vendor = lock['local_directory']
        shutil.copytree(PROJECT/self.yue_vendor, self.root/self.yue_vendor)
        source = dict(lock, source_lock_file=relative, source_lock_sha256=package.digest(self.root/relative),
            insertion_phase='post_autoencoding_post_wordnet_post_cccedict_headwords',
            build_selection_status='selected_default_explicit_post_cccedict',
            source_explicit_cantonese_readings=True, independent_linguistic_approval=False)
        for role, relative in (('parser', 'cantonese_ime/yue_wiktionary.py'),
                               ('builder', 'cantonese_ime/dictionary.py'),
                               ('build_script', 'tools/build_dictionary.py')):
            path = self.write(relative, (PROJECT/relative).read_bytes())
            source[role+'_file'] = relative
            source[role+'_sha256'] = package.digest(path)
        self.selected_yue = source
        self.dictionary_metadata['source_metadata']['supplements']['yue_wiktionary'] = source
        self.dictionary_metadata['yue_wiktionary'] = {'added_pairs': 323}
        fixture.NativePackageTests.save_source_manifest(self)

    def test_old_dictionary_has_no_new_yue_source_requirement(self):
        manifest = self.stage()
        self.assertNotIn('data/supplements/yue-wiktionary.sources.lock.json',
                         {record['path'] for record in manifest['files']})

    def test_selected_source_retains_licenses_history_attribution_and_parser_only(self):
        self.select_yue()
        manifest = self.stage()
        paths = {record['path'] for record in manifest['files']}
        self.assertIn('data/supplements/yue-wiktionary.sources.lock.json', paths)
        self.assertIn('cantonese_ime/yue_wiktionary.py', paths)
        for name in ('ATTRIBUTION.md', 'LICENSE-CC-BY-SA-4.0.txt',
                     'yue-page-licensing-sample.html', 'wikimedia-terms.html'):
            self.assertIn(self.yue_vendor+'/'+name, paths)
        for item in self.selected_yue['files']:
            if item['name'] not in {'ATTRIBUTION.md', 'LICENSE-CC-BY-SA-4.0.txt',
                                    'yue-page-licensing-sample.html', 'wikimedia-terms.html'}:
                self.assertNotIn(self.yue_vendor+'/'+item['name'], paths)
        retained = json.loads((self.output/'data/supplements/yue-wiktionary.sources.lock.json').read_text('utf-8'))
        self.assertEqual(retained['template_revisions'], self.selected_yue['template_revisions'])
        self.assertTrue(all(row['revision_url'] for row in retained['template_revisions']))

    def test_selected_markers_refuse_a_missing_source_block(self):
        self.dictionary_metadata['yue_wiktionary'] = {'added_pairs': 323}
        fixture.NativePackageTests.save_source_manifest(self)
        self.assert_rejected_before_staging('source block is missing')

    def test_original_preparation_status_cannot_be_rewritten(self):
        self.select_yue()
        self.selected_yue['selection_status'] = 'rewritten original status'
        fixture.NativePackageTests.save_source_manifest(self)
        self.assert_rejected_before_staging('differs from its original lock')

    def test_stale_footer_or_terms_cannot_be_staged(self):
        self.select_yue()
        for name in ('yue-page-licensing-sample.html', 'wikimedia-terms.html'):
            path = self.root/self.yue_vendor/name
            original = path.read_bytes()
            try:
                path.write_bytes(original+b'changed notice')
                self.assert_rejected_before_staging('differs from its lock')
            finally:
                path.write_bytes(original)

    def test_parser_builder_and_build_script_must_match_selected_source(self):
        self.select_yue()
        for role in ('parser', 'builder', 'build_script'):
            path = self.root/self.selected_yue[role+'_file']
            original = path.read_bytes()
            try:
                path.write_bytes(original+b'changed module')
                self.assert_rejected_before_staging(role+' changed')
            finally:
                path.write_bytes(original)

    def test_explicit_source_flag_and_unreviewed_status_remain_truthful(self):
        self.select_yue()
        for field, wrong in (('source_explicit_cantonese_readings', False),
                              ('independent_linguistic_approval', True)):
            original = self.selected_yue[field]
            try:
                self.selected_yue[field] = wrong
                fixture.NativePackageTests.save_source_manifest(self)
                self.assert_rejected_before_staging('reviewed explicit-source policy')
            finally:
                self.selected_yue[field] = original

    def test_notice_changed_after_validation_keeps_its_original_lock_pin(self):
        self.select_yue()
        guard = package._yue_wiktionary_notice_inputs
        notice = self.root/self.yue_vendor/'ATTRIBUTION.md'

        def edit_after_validation(metadata, **options):
            result = guard(metadata, **options)
            notice.write_bytes(notice.read_bytes()+b'changed after validation')
            return result

        with patch.object(package, '_yue_wiktionary_notice_inputs', side_effect=edit_after_validation), \
                patch.object(package.subprocess, 'run', side_effect=self.fake_configure) as launch, \
                self.assertRaisesRegex(ValueError, 'Validated package input changed'):
            package.stage(self.output, self.python)
        self.assertFalse(self.output.exists())
        launch.assert_not_called()
