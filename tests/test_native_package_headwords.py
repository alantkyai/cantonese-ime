import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from tests import test_native_package as fixture
from tools import package_native as package

PROJECT = Path(__file__).resolve().parents[1]


class NativeHeadwordPackageTests(unittest.TestCase):
    setUp = fixture.NativePackageTests.setUp
    write = fixture.NativePackageTests.write
    json = fixture.NativePackageTests.json
    fake_configure = fixture.NativePackageTests.fake_configure
    stage = fixture.NativePackageTests.stage
    assert_rejected_before_staging = fixture.NativePackageTests.assert_rejected_before_staging

    def select_headwords(self):
        relative = 'data/supplements/cccedict-headwords.sources.lock.json'
        self.write(relative,(PROJECT/relative).read_bytes())
        lock = json.loads((self.root/relative).read_text('utf-8'))
        self.headword_vendor = lock['local_directory']
        shutil.copytree(PROJECT/self.headword_vendor,self.root/self.headword_vendor)
        selected = dict(lock,source_lock_file=relative,source_lock_sha256=package.digest(self.root/relative),
                        insertion_phase='post_autoencoding_post_wordnet',
                        build_selection_status='selected_opt_in_post_wordnet_autoencoding',
                        authored_cantonese_readings=False)
        for role,relative in (('parser','cantonese_ime/cccedict_headwords.py'),
                              ('encoder','cantonese_ime/autoencode.py'),
                              ('builder','cantonese_ime/dictionary.py'),
                              ('build_script','tools/build_dictionary.py')):
            path = self.write(relative,(PROJECT/relative).read_bytes())
            selected[role+'_file'] = relative
            selected[role+'_sha256'] = package.digest(path)
        self.selected_headwords = selected
        self.dictionary_metadata['source_metadata']['supplements']['cccedict_headwords']=selected
        fixture.NativePackageTests.save_source_manifest(self)

    def test_selected_headwords_retain_full_notices_without_markdown_links_or_raw_table(self):
        self.select_headwords()
        manifest = self.stage()
        paths = {row['path'] for row in manifest['files']}
        self.assertIn('data/supplements/cccedict-headwords.sources.lock.json',paths)
        for name in ('ATTRIBUTION.md','LICENSE-CC-BY-SA-4.0.txt','download-page.html'):
            self.assertIn(self.headword_vendor+'/'+name,paths)
        self.assertNotIn(self.headword_vendor+'/cedict_ts.u8',paths)
        self.assertNotIn(self.headword_vendor+'/cedict_1_0_ts_utf-8_mdbg.txt.gz',paths)

    def test_written_forms_cannot_be_mislabeled_as_authored_cantonese(self):
        self.select_headwords()
        self.selected_headwords['authored_cantonese_readings']=True
        fixture.NativePackageTests.save_source_manifest(self)
        self.assert_rejected_before_staging('generated-reading policy')

    def test_selected_headword_builder_and_source_changes_are_rejected(self):
        self.select_headwords()
        path = self.root/'cantonese_ime/dictionary.py'
        original = path.read_bytes()
        path.write_bytes(original+b'changed')
        self.assert_rejected_before_staging('builder changed')
        path.write_bytes(original)
        path = self.root/self.headword_vendor/'cedict_ts.u8'
        path.write_bytes(path.read_bytes()+b'changed')
        self.assert_rejected_before_staging('differs from its source lock')

    def test_original_source_candidate_status_cannot_be_rewritten_by_selected_build(self):
        self.select_headwords()
        self.selected_headwords['selection_status']='rewritten original source claim'
        fixture.NativePackageTests.save_source_manifest(self)
        self.assert_rejected_before_staging('differs from its original lock')

    def test_selected_markers_cannot_survive_an_omitted_source_block(self):
        self.dictionary_metadata['headword_encoding']={'new_generated_pairs':36884}
        fixture.NativePackageTests.save_source_manifest(self)
        self.assert_rejected_before_staging('source block is missing')

    def test_notice_edit_after_validation_cannot_become_a_fresh_package_pin(self):
        self.select_headwords()
        notice = self.root/self.headword_vendor/'LICENSE-CC-BY-SA-4.0.txt'
        guard = package._cccedict_headword_notice_inputs

        def edit_after_validation(metadata, **options):
            result = guard(metadata, **options)
            notice.write_bytes(notice.read_bytes()+b'changed after validation')
            return result

        with patch.object(package, '_cccedict_headword_notice_inputs', side_effect=edit_after_validation), \
                patch.object(package.subprocess, 'run', side_effect=self.fake_configure) as launch, \
                self.assertRaisesRegex(ValueError, 'Validated package input changed'):
            package.stage(self.output, self.python)
        self.assertFalse(self.output.exists())
        launch.assert_not_called()

    def test_restoring_source_after_copy_cannot_bless_an_unpinned_notice(self):
        self.select_headwords()
        notice = self.root/self.headword_vendor/'LICENSE-CC-BY-SA-4.0.txt'
        original_bytes = notice.read_bytes()
        guard = package._cccedict_headword_notice_inputs
        copy_file = package.shutil.copyfile

        def edit_after_validation(metadata, **options):
            result = guard(metadata, **options)
            notice.write_bytes(original_bytes+b'changed before generic capture')
            return result

        def restore_after_later_copy(source, target, **options):
            result = copy_file(source, target, **options)
            if Path(target).name == 'download-page.html':
                notice.write_bytes(original_bytes)
            return result

        try:
            with patch.object(package, '_cccedict_headword_notice_inputs', side_effect=edit_after_validation), \
                    patch.object(package.shutil, 'copyfile', side_effect=restore_after_later_copy), \
                    patch.object(package.subprocess, 'run', side_effect=self.fake_configure) as launch, \
                    self.assertRaisesRegex(ValueError, 'Validated package input changed'):
                package.stage(self.output, self.python)
            self.assertFalse(self.output.exists())
            launch.assert_not_called()
        finally:
            notice.write_bytes(original_bytes)

    def test_staged_notice_edit_after_configuration_prevents_manifest_publication(self):
        self.select_headwords()
        relative = self.headword_vendor+'/LICENSE-CC-BY-SA-4.0.txt'

        def change_staged_notice(args, **options):
            self.fake_configure(args, **options)
            path = self.output/relative
            path.write_bytes(path.read_bytes()+b'late staged edit')

        with patch.object(package.subprocess, 'run', side_effect=change_staged_notice), \
                self.assertRaisesRegex(RuntimeError, 'staged file changed before publication'):
            package.stage(self.output, self.python)
        self.assertFalse((self.output/'package-manifest.json').exists())


class NativeWordnetNoticeRaceTests(unittest.TestCase):
    setUp = fixture.NativePackageTests.setUp
    write = fixture.NativePackageTests.write
    json = fixture.NativePackageTests.json
    fake_configure = fixture.NativePackageTests.fake_configure

    def test_wordnet_notice_is_bound_to_the_original_lock_before_generic_capture(self):
        guard = package._wordnet_notice_inputs
        notice = self.root/self.vendor/'LICENSE-CC-BY-4.0.txt'

        def edit_after_validation(metadata, **options):
            result = guard(metadata, **options)
            notice.write_bytes(notice.read_bytes()+b'changed after validation')
            return result

        with patch.object(package, '_wordnet_notice_inputs', side_effect=edit_after_validation), \
                patch.object(package.subprocess, 'run', side_effect=self.fake_configure) as launch, \
                self.assertRaisesRegex(ValueError, 'Validated package input changed'):
            package.stage(self.output, self.python)
        self.assertFalse(self.output.exists())
        launch.assert_not_called()

    def test_wordnet_lock_change_after_copy_prevents_manifest_publication(self):
        def edit_after_copy(args, **options):
            self.fake_configure(args, **options)
            self.lock_path.write_bytes(self.lock_path.read_bytes()+b' ')

        with patch.object(package.subprocess, 'run', side_effect=edit_after_copy), \
                self.assertRaisesRegex(ValueError, 'Validated package input changed'):
            package.stage(self.output, self.python)
        self.assertFalse((self.output/'package-manifest.json').exists())
