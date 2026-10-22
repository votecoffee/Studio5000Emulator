"""Separate upload cache targets preserve both originals and emulator binding."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.probe_native_sdk import digest,input_evidence,run,upload_input
import test_native_sdk_probe as native_tests


class UploadMergeTargetTests(unittest.TestCase):
    def test_merge_target_is_optional_upload_only_and_bounded_acd(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'original.ACD';source.write_bytes(b'original-source')
            target=Path(folder)/'target.ACD';target.write_bytes(b'other-baseline')
            self.assertEqual(upload_input(source,'upload'),source)
            self.assertEqual(upload_input(source,'upload',target),target.resolve())
            for operation in ('connection','download','modes','edits'):
                with self.assertRaises(ValueError):upload_input(source,operation,target)
            for name,data in (('wrong.L5X',b'not-an-acd'),('short.ACD',b'tiny')):
                bad=Path(folder)/name;bad.write_bytes(data)
                with self.assertRaises(ValueError):upload_input(source,'upload',bad)
            directory=Path(folder)/'directory.ACD';directory.mkdir()
            with self.assertRaises(ValueError):upload_input(source,'upload',directory)
            with self.assertRaises(OSError):upload_input(source,'upload',Path(folder)/'missing.ACD')

    def test_private_upload_changes_are_separate_from_both_preserved_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.ACD';source.write_bytes(b'original-source')
            target=Path(folder)/'target.ACD';target.write_bytes(b'original-target')
            working=Path(folder)/'input.ACD';working.write_bytes(b'uploaded-private-working-project')
            source_hash=digest(source);target_hash=digest(target)
            state=input_evidence(source,source_hash,target,target_hash,working,'upload')
            self.assertTrue(state['source_unchanged']);self.assertTrue(state['upload_target_original_unchanged'])
            self.assertFalse(state['working_copy_unchanged']);self.assertTrue(state['working_copy_changes_permitted'])
            self.assertEqual(state['working_copy_sha256'],digest(working))
            for operation in ('connection','download','modes','edits'):
                state=input_evidence(source,source_hash,target,target_hash,working,operation)
                self.assertFalse(state['source_unchanged']);self.assertFalse(state['working_copy_changes_permitted'])
            target.write_bytes(b'changed-target-original')
            self.assertFalse(input_evidence(source,source_hash,target,target_hash,working,'upload')['source_unchanged'])
            target.write_bytes(b'original-target');source.write_bytes(b'changed-source-original')
            self.assertFalse(input_evidence(source,source_hash,target,target_hash,working,'upload')['source_unchanged'])

    def test_missing_or_inaccessible_files_retain_failure_evidence_without_suppressing_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input.ACD';p.write_bytes(b'original-source');value=digest(p)
            missing=Path(folder)/'missing.ACD'
            state=input_evidence(p,value,p,value,missing,'upload')
            self.assertTrue(state['source_unchanged']);self.assertFalse(state['working_copy_present'])
            self.assertIsNone(state['working_copy_sha256'])
            state=input_evidence(missing,value,p,value,p,'upload');self.assertFalse(state['source_unchanged'])
            with patch('tools.probe_native_sdk.digest',side_effect=PermissionError('denied')):
                state=input_evidence(p,value,p,value,p,'upload')
                self.assertFalse(state['source_unchanged']);self.assertFalse(state['working_copy_present'])

    def simulated_run(self,folder,*,missing_copy=False,change_original=False,wrong_receipt=False,change_model=False,wrong_controller=False):
        root=Path(folder);source=root/'original.ACD';source.write_bytes(b'owned-controller-source')
        target=root/'baseline.ACD';target.write_bytes(b'owned-different-merge-baseline')
        output=root/'report';state=native_tests.NativeSdkProbeTests.state(self)
        state.update(app_version='test',tags=[],scan=0,ms=0,changes=[],mode='test')
        state.update(routines=[{'key':'MainProgram/Run','rungs':[]}],tasks=[],entry_routines=['MainProgram/Run'])
        final=copy.deepcopy(state)
        if change_model:final['routines'][0]['rungs']=[{'unexpected':True}]
        state['connectivity']['native_correlation']['source_acd_sha256']=digest(source)
        final['connectivity']['native_correlation']['source_acd_sha256']=digest(source)
        args=SimpleNamespace(project=str(source),upload_target=str(target),url='http://127.0.0.1:8786',
            path=r'TestDriver\192.0.2.8\Backplane\0',operation='upload',tag=[],output=str(output),sdk_feed=None)
        trace={'events':[],'counts':{'native_verified':0}}
        def process(command,**kwargs):
            if command[0]=='dotnet':
                (output/'bin').mkdir();(output/'bin/NativeSdkProbe.exe').write_bytes(b'fake-apphost')
                (output/'bin/NativeSdkProbe.dll').write_bytes(b'fake-code')
                return subprocess.CompletedProcess(command,0)
            config=json.loads((output/'request.json').read_text())
            self.assertEqual(config['SourceSha256'],digest(target))
            self.assertEqual(config['ControllerSourceSha256'],digest(source))
            self.assertEqual(Path(config['Project']).read_bytes(),target.read_bytes())
            if missing_copy:Path(config['Project']).unlink()
            else:Path(config['Project']).write_bytes(b'new-private-uploaded-project')
            if change_original:target.write_bytes(b'original-target-unexpectedly-changed')
            Path(command[2]).write_text(json.dumps({'status':'succeeded','steps':[],
                'serverFaulted':False,'sdkOfflineConfirmed':True,'sourceUnchanged':False,
                'workingProjectSha256':None if missing_copy or wrong_receipt=='missing' else ('a'*64 if wrong_receipt else digest(Path(config['Project']))),
                'controllerSourceSha256':'a'*64 if wrong_controller else digest(source)}))
            return subprocess.CompletedProcess(command,0)
        with patch('tools.probe_native_sdk.sys.platform','win32'), \
                patch('tools.probe_native_sdk.require_sdk_service'), \
                patch('tools.probe_native_sdk.background_options',return_value={}), \
                patch('tools.probe_native_sdk.subprocess.run',side_effect=process), \
                patch('tools.probe_native_sdk.api',side_effect=(state,state,trace,final,trace)), \
                patch('tools.probe_native_sdk.wait_for_cleanup',return_value=final) as cleanup,patch('builtins.print'):
            code=run(args)
        cleanup.assert_called_once()
        return code,json.loads((output/'summary.json').read_text()),source,target

    def test_full_probe_keeps_controller_pin_and_hashes_both_originals_while_upload_changes_its_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            code,report,source,target=self.simulated_run(folder)
            self.assertEqual(code,0);self.assertEqual(report['status'],'succeeded')
            self.assertEqual(report['source_sha256'],digest(source));self.assertEqual(report['sdk_input_sha256'],digest(target))
            self.assertTrue(report['separate_upload_target']);self.assertTrue(report['source_unchanged'])
            self.assertTrue(report['cleanup_confirmed']);self.assertFalse(report['working_copy_unchanged'])
            self.assertTrue(report['working_copy_matches_sdk']);self.assertTrue(report['sdk_controller_source_matches'])
            self.assertEqual(source.read_bytes(),b'owned-controller-source')
            self.assertEqual(target.read_bytes(),b'owned-different-merge-baseline')

    def test_disappearing_private_copy_fails_but_still_checks_native_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            code,report,_,_=self.simulated_run(folder,missing_copy=True)
            self.assertEqual(code,1);self.assertEqual(report['status'],'failed')
            self.assertTrue(report['cleanup_confirmed']);self.assertFalse(report['working_copy_present'])

    def test_changed_original_target_fails_even_when_native_api_reports_success(self):
        with tempfile.TemporaryDirectory() as folder:
            code,report,_,_=self.simulated_run(folder,change_original=True)
            self.assertEqual(code,1);self.assertEqual(report['status'],'failed')
            self.assertTrue(report['cleanup_confirmed']);self.assertFalse(report['source_unchanged'])

    def test_mismatched_sdk_artifact_receipt_fails_after_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            code,report,_,_=self.simulated_run(folder,wrong_receipt=True)
            self.assertEqual(code,1);self.assertFalse(report['working_copy_matches_sdk'])
            self.assertTrue(report['source_unchanged']);self.assertTrue(report['cleanup_confirmed'])

    def test_transfer_checks_detect_a_changed_routine_even_when_tags_and_clock_are_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            code,report,_,_=self.simulated_run(folder,change_model=True)
            self.assertEqual(code,1);self.assertFalse(report['model_unchanged'])
            self.assertIn('routines',report['model_fields_checked']);self.assertTrue(report['cleanup_confirmed'])

    def test_missing_artifact_receipt_cannot_establish_successful_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            code,report,_,_=self.simulated_run(folder,wrong_receipt='missing')
            self.assertEqual(code,1);self.assertIsNone(report['working_copy_matches_sdk'])
            self.assertTrue(report['source_unchanged']);self.assertTrue(report['cleanup_confirmed'])

    def test_wrong_controller_source_receipt_cannot_establish_successful_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            code,report,_,_=self.simulated_run(folder,wrong_controller=True)
            self.assertEqual(code,1);self.assertFalse(report['sdk_controller_source_matches'])
            self.assertTrue(report['source_unchanged']);self.assertTrue(report['cleanup_confirmed'])


if __name__=='__main__':unittest.main()
