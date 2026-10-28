"""Native edit persistence needs actual save/reopen/Online steps and full content."""
import copy
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from tools import native_edit_save as tool
import test_upload_content as content_tests
from test_native_project import container,FIELDS


class NativeEditSaveTests(unittest.TestCase):
    setUp=content_tests.UploadContentTests.setUp
    edited_state=content_tests.UploadContentTests.edited_state

    def options(self,**changes):
        values=dict(operation='edits',enabled=True,apply=True,baseline='downloaded.ACD',reconnect=True,
                    second_code=None,import_option='AcceptEdits',neutral_save=False)
        values.update(changes);return values

    def test_option_is_limited_to_one_explicit_accepted_edit_with_a_matching_baseline(self):
        tool.validate_options(**self.options())
        for change in (dict(operation='upload'),dict(enabled=1),dict(apply=False),dict(baseline=None),
                       dict(reconnect=False),dict(second_code='NOP();'),dict(import_option='LeaveEdits'),
                       dict(import_option='FinalizeEdits'),dict(neutral_save=True)):
            with self.subTest(change=change),self.assertRaises(ValueError):tool.validate_options(**self.options(**change))
        tool.validate_options(**self.options(enabled=False,operation='connection',apply=False,baseline=None,reconnect=False))

    def artifacts(self):
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        self.original=self.folder/'source.ACD';self.baseline=self.folder/'baseline.ACD'
        self.original.write_bytes(container(fields={**FIELDS,10:0,11:0}))
        self.baseline.write_bytes(container(fields={**FIELDS,11:0}))
        self.acd=self.folder/'native-edited.ACD';self.xml=self.folder/'native-edited.L5X'
        self.acd.write_bytes(container(fields={**FIELDS,8:FIELDS[8]+1,11:0}))
        root=ET.fromstring(self.project.path.read_bytes())
        root.find(".//Program[@Name='MainProgram']/Routines/Routine[@Name='MainRoutine']/RLLContent/Rung/Text").text='MOV(123,SpeedSetpoint);'
        self.xml.write_bytes(ET.tostring(root));self.edited=self.edited_state()
        receipt=dict(directAcceptedEditSave=True,nativeAcdReopened=True,reopenedOnline=True,
                     noUploadCalled=True,noL5xImportCalled=True,baselineSha256=sha(self.baseline),
                     acdSha256=sha(self.acd),l5xSha256=sha(self.xml))
        return dict(status='succeeded',serverFaulted=False,sdkOfflineConfirmed=True,workingProjectUnchanged=True,
                    savedNativeEditedProject=receipt,steps=[dict(method=name,status='succeeded') for name in tool.METHODS])

    def verify(self,report,**changes):
        args=dict(folder=self.folder,source_l5x=self.project.path,source_acd=self.original,baseline=self.baseline,
                  state=self.edited,report=report,source_hash=self.project.sha256)
        args.update(changes)
        with patch.object(tool.NativeTypes,'from_acd',return_value=self.types):return tool.verify(**args)

    def test_complete_native_save_receipt_allows_copy_uid_change_but_preserves_other_anchors(self):
        report=self.artifacts();before=self.original.read_bytes(),self.baseline.read_bytes()
        result=self.verify(report)
        self.assertTrue(result['verified']);self.assertTrue(result['correlation_anchors_preserved'])
        self.assertTrue(result['copy_uid_changed']);self.assertTrue(result['reopened_online'])
        self.assertEqual(result['content']['tags'],14);self.assertEqual(result['content']['routines'],2)
        self.assertFalse(result['controller_upload_verified']);self.assertFalse(result['change_log_records_decoded'])
        self.assertEqual(before,(self.original.read_bytes(),self.baseline.read_bytes()))

    def test_missing_reordered_duplicate_or_failed_native_steps_cannot_prove_saved_online_state(self):
        good=self.artifacts()
        for change in ('missing','reversed','duplicate','failed','fault','cleanup','working-copy','not-direct','imported','upload'):
            report=copy.deepcopy(good)
            if change=='missing':report['steps'].pop()
            elif change=='reversed':report['steps'].reverse()
            elif change=='duplicate':report['steps'].append(copy.deepcopy(report['steps'][0]))
            elif change=='failed':report['steps'][0]['status']='failed'
            elif change=='fault':report['serverFaulted']=True
            elif change=='cleanup':report['sdkOfflineConfirmed']=False
            elif change=='working-copy':report['workingProjectUnchanged']=False
            elif change=='not-direct':report['savedNativeEditedProject']['directAcceptedEditSave']=False
            elif change=='imported':report['savedNativeEditedProject']['noL5xImportCalled']=False
            else:report['savedNativeEditedProject']['noUploadCalled']=False
            with self.subTest(change=change):self.assertFalse(self.verify(report)['verified'])

    def test_changed_correlation_content_hash_or_source_cannot_pass_with_success_flags(self):
        for change in ('download','generation','copy-zero','hash','logic','dimensions','source','revision'):
            report=self.artifacts();state=copy.deepcopy(self.edited);binding=self.project.sha256
            if change in ('download','generation','copy-zero'):
                fields={**FIELDS,8:FIELDS[8]+1,11:0}
                if change=='download':fields[10]+=1
                elif change=='generation':fields[12]+=1
                else:fields[8]=0
                self.acd.write_bytes(container(fields=fields))
                report['savedNativeEditedProject']['acdSha256']=hashlib.sha256(self.acd.read_bytes()).hexdigest()
            elif change=='hash':report['savedNativeEditedProject']['l5xSha256']='f'*64
            elif change in ('logic','dimensions'):
                root=ET.fromstring(self.xml.read_bytes())
                if change=='logic':root.find('.//Rung/Text').text='NOP();'
                else:root.find(".//Controller/Tags/Tag[@Name='SpeedSetpoint']").set('Dimensions','2')
                self.xml.write_bytes(ET.tostring(root));report['savedNativeEditedProject']['l5xSha256']=hashlib.sha256(self.xml.read_bytes()).hexdigest()
            elif change=='source':binding='f'*64
            else:state['routine_edits']['revision']=2
            with self.subTest(change=change):self.assertFalse(self.verify(report,state=state,source_hash=binding)['verified'])

    def test_prepare_rejects_source_or_revision_changes_before_native_work(self):
        self.artifacts()
        with patch.object(tool.NativeTypes,'from_acd',return_value=self.types):
            self.assertEqual(tool.prepare(self.project.path,self.original,self.state),self.project.sha256)
            for state in (self.edited,dict(self.state,connectivity=dict(source_l5x_sha256='f'*64))):
                with self.assertRaises(ValueError):tool.prepare(self.project.path,self.original,state)

    def test_invalid_save_combinations_stop_the_public_runner_before_backend_build_or_sdk_access(self):
        from tools import probe_native_sdk as probe
        self.artifacts()
        for operation,baseline in (('connection',str(self.baseline)),('edits',None)):
            args=SimpleNamespace(project=str(self.original),url='http://127.0.0.1:8786',
                path=r'TestDriver\192.0.2.8\Backplane\0',operation=operation,tag=[],
                connection_target=baseline,apply_supported_edits=operation=='edits',
                reconnect_edits=operation=='edits',save_native_edits_acd=str(self.project.path))
            with self.subTest(operation=operation),patch.object(probe.sys,'platform','win32'), \
                    patch.object(probe,'api') as backend,patch.object(probe,'require_sdk_service') as sdk, \
                    patch.object(probe.subprocess,'run') as build,self.assertRaises(ValueError):
                try:probe.run(args)
                finally:backend.assert_not_called();sdk.assert_not_called();build.assert_not_called()


if __name__=='__main__':unittest.main()
