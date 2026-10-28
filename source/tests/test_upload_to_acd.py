"""Upload/save orchestration gates, with synthetic stage files and no SDK calls."""
import copy
from contextlib import ExitStack,redirect_stdout
import io
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import upload_to_acd as flow
from tools import rebuild_uploaded_acd as rebuild
import test_uploaded_rebuild as fixtures
import test_upload_tag_definitions as tag_fixtures


class UploadToAcdTests(unittest.TestCase):
    setUp=fixtures.UploadedRebuildTests.setUp
    plan=fixtures.UploadedRebuildTests.plan
    receipt=fixtures.UploadedRebuildTests.receipt
    program_receipt=fixtures.UploadedRebuildTests.program_receipt
    inputs=fixtures.UploadedRebuildTests.inputs
    artifacts=fixtures.UploadedRebuildTests.artifacts

    def scenario(self,case='success'):
        source,files=self.inputs();before=files['before-state.json']
        tags=tag_fixtures.UploadedTagDefinitionTests.artifact(self)
        files['request.json'].update(ExportUploadedTags=True,VerifyUploadBaselineOnline=False)
        files['sdk-result.json']['uploadedContent']['controllerTags']=tags['controllerTags']
        for name in ('request.json','sdk-result.json'):(self.folder/name).write_text(json.dumps(files[name]))
        pins={source:rebuild.digest(source),self.project.path:rebuild.digest(self.project.path)}
        args=SimpleNamespace(project=str(source),source=str(self.project.path),upload_target=None,
            output=str(self.folder/'workflow'),url='http://127.0.0.1:8786',path=r'Emulator\192.0.2.8\Backplane\0',sdk_feed=None)
        admitted=(args.url,source,self.project.path,source,before,pins)
        inputs={p.name:p.read_bytes() for p in self.folder.iterdir() if p.is_file()}
        calls=[]

        def upload(request):
            calls.append('upload');out=Path(request.output);out.mkdir()
            self.assertTrue(request.verify_uploaded_tag_definitions and request.retain_transfer_trace)
            self.assertFalse(request.verify_upload_baseline_online)
            for name,raw in inputs.items():(out/name).write_bytes(raw)
            summary=copy.deepcopy(files['summary.json'])
            if case in ('upload-failed','upload-unknown','upload-fault'):
                summary['status']='failed'
                if case=='upload-unknown':summary['native_call_outcome']='unknown'
                if case=='upload-fault':summary['sdk_server_faulted']=True
            (out/'summary.json').write_text(json.dumps(summary))
            if case=='changed-upload-evidence':
                p=out/self.plan()['programs'][0]['fileName'];p.write_bytes(p.read_bytes()+b'changed')
            if case=='missing-requested-tag-check':
                request=copy.deepcopy(files['request.json']);request['ExportUploadedTags']=False
                (out/'request.json').write_text(json.dumps(request))
            return 1 if summary['status']=='failed' else 0

        def save(request):
            calls.append('rebuild');out=Path(request.output);out.mkdir()
            if case=='save-unknown':
                (out/'summary.json').write_text(json.dumps(dict(status='unknown')));return 1
            receipt=self.artifacts()
            if case=='wrong-saved-logic':
                p=self.folder/'rebuilt.L5X';p.write_bytes(p.read_bytes().replace(b'OTE(MotorRunning)',b'OTL(MotorRunning)'))
                receipt['l5xSha256']=rebuild.digest(p)
            for name in ('rebuilt.ACD','rebuilt.L5X'):shutil.copyfile(self.folder/name,out/name)
            (out/'native-result.json').write_text(json.dumps(receipt))
            (out/'summary.json').write_text(json.dumps(dict(status='succeeded')))
            if case=='changed-original':source.write_bytes(source.read_bytes()+b'changed')
            return 0

        final=copy.deepcopy(before)
        if case=='changed-model':final['tags'][0]['value']=not final['tags'][0]['value']
        if case=='changed-model-mode':final['mode']='routine'
        with ExitStack() as stack:
            stack.enter_context(patch.object(flow,'admit',return_value=admitted))
            stack.enter_context(patch.object(flow.probe,'run',side_effect=upload))
            stack.enter_context(patch.object(flow.rebuild,'run',side_effect=save))
            stack.enter_context(patch.object(flow.probe,'api',return_value=final))
            stack.enter_context(patch.object(flow.probe,'validate_target'))
            stack.enter_context(patch.object(flow.probe,'validate_idle'))
            stack.enter_context(patch.object(rebuild.NativeTypes,'from_acd',return_value=self.types))
            with redirect_stdout(io.StringIO()):code=flow.run(args)
        report=json.loads((Path(args.output)/'summary.json').read_text())
        return code,report,calls,Path(args.output)

    def test_success_keeps_separate_stage_evidence_and_rechecks_actual_saved_content(self):
        code,report,calls,out=self.scenario()
        self.assertEqual(code,0);self.assertEqual(calls,['upload','rebuild'])
        self.assertEqual(report['status'],'succeeded')
        self.assertTrue(report['verification']['verified'] and report['inputs_preserved'] and report['model_unchanged'])
        self.assertTrue(report['requires_download']);self.assertFalse(report['online_verified'])
        self.assertFalse(report['direct_uploaded_project_save'] or report['automatic_retry'])
        self.assertEqual(report['acd_sha256'],rebuild.digest(out/report['acd_path']))
        self.assertTrue((out/'upload/summary.json').is_file() and (out/'rebuilt/summary.json').is_file())

    def test_failed_uncertain_or_faulted_upload_never_starts_native_save(self):
        for case in ('upload-failed','upload-unknown','upload-fault'):
            # A fresh folder preserves each outcome without replay or overwrite.
            with self.subTest(case=case):
                self.setUp()
                code,report,calls,out=self.scenario(case)
                self.assertEqual(code,1);self.assertEqual(calls,['upload'])
                self.assertEqual(report['native_rebuild_status'],'not_started')
                self.assertFalse((out/'rebuilt').exists())
                self.assertEqual(report['status'],'unknown' if case=='upload-unknown' else 'failed')

    def test_upload_success_flag_cannot_bypass_actual_program_artifact_gate(self):
        code,report,calls,_=self.scenario('changed-upload-evidence')
        self.assertEqual(code,1);self.assertEqual(calls,['upload'])
        self.assertEqual(report['native_upload_status'],'succeeded');self.assertEqual(report['status'],'failed')

    def test_missing_requested_tag_check_cannot_use_the_legacy_receipt_path(self):
        code,report,calls,_=self.scenario('missing-requested-tag-check')
        self.assertEqual(code,1);self.assertEqual(calls,['upload'])
        self.assertEqual(report['native_rebuild_status'],'not_started')

    def test_unknown_save_is_preserved_without_repeating_either_stage(self):
        code,report,calls,out=self.scenario('save-unknown')
        self.assertEqual(code,1);self.assertEqual(calls,['upload','rebuild'])
        self.assertEqual(report['status'],'unknown');self.assertEqual(report['native_rebuild_status'],'unknown')
        self.assertNotIn('acd_path',report);self.assertTrue((out/'upload/summary.json').is_file())

    def test_changed_saved_logic_rejects_even_when_native_success_and_hash_match(self):
        code,report,calls,_=self.scenario('wrong-saved-logic')
        self.assertEqual(code,1);self.assertEqual(calls,['upload','rebuild'])
        self.assertFalse(report['verification']['verified']);self.assertNotIn('acd_path',report)

    def test_original_change_after_native_save_cannot_be_reported_as_preserved(self):
        code,report,_,_=self.scenario('changed-original')
        self.assertEqual(code,1);self.assertEqual(report['status'],'failed');self.assertFalse(report['inputs_preserved'])

    def test_runtime_change_after_upload_is_not_claimed_as_an_unchanged_workflow(self):
        code,report,_,_=self.scenario('changed-model')
        self.assertEqual(code,1);self.assertEqual(report['status'],'failed');self.assertFalse(report['model_unchanged'])

    def test_harness_selection_change_is_also_part_of_the_final_model_check(self):
        code,report,_,_=self.scenario('changed-model-mode')
        self.assertEqual(code,1);self.assertFalse(report['model_unchanged'])

    def test_existing_output_is_not_reused_and_no_native_call_occurs(self):
        source,files=self.inputs();output=self.folder/'existing';output.mkdir();(output/'keep').write_text('retain')
        args=SimpleNamespace(output=str(output))
        admitted=('url',source,self.project.path,source,files['before-state.json'],{})
        with patch.object(flow,'admit',return_value=admitted),patch.object(flow.probe,'run') as upload:
            with self.assertRaises(FileExistsError):flow.run(args)
        upload.assert_not_called();self.assertEqual((output/'keep').read_text(),'retain')

    def test_admission_requires_an_unchanged_installed_source_before_any_native_stage(self):
        source,files=self.inputs();state=files['before-state.json']
        args=SimpleNamespace(project=str(source),source=str(self.project.path),upload_target=None,
            url='http://127.0.0.1:8786',path=r'Emulator\192.0.2.8\Backplane\0')
        with patch.object(flow.sys,'platform','win32'),patch.object(flow.probe,'api',return_value=state),\
                patch.object(flow.probe,'validate_target'),patch.object(flow.probe,'validate_idle'),\
                patch.object(flow.upload_content.NativeTypes,'from_acd',return_value=self.types):
            admitted=flow.admit(args)
            self.assertEqual(admitted[1:4],(source,self.project.path,source))
            self.assertEqual(admitted[5][source],rebuild.digest(source))
            state['connectivity']['native_download']['source_equivalent']=False
            with self.assertRaisesRegex(ValueError,'source-equivalent'):flow.admit(args)


if __name__=='__main__':unittest.main()
