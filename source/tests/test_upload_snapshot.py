"""Value snapshots require complete content and unchanged saved correlation."""
import copy
import hashlib
import unittest
from xml.etree import ElementTree as ET

from tools import upload_snapshot as snapshot
import test_upload_content as content_tests
from test_native_project import container,FIELDS


class UploadSnapshotTests(unittest.TestCase):
    setUp=content_tests.UploadContentTests.setUp
    plan=content_tests.UploadContentTests.plan

    def inputs(self):
        original=self.folder/'source.ACD';baseline=self.folder/'baseline.ACD'
        original.write_bytes(container(fields={**FIELDS,10:0,11:0}))
        baseline.write_bytes(container(fields={**FIELDS,11:0}))
        state=copy.deepcopy(self.state);state['connectivity']['native_download']=dict(installed=True,source_equivalent=True)
        return original,baseline,state

    def artifacts(self,baseline):
        acd=self.folder/'snapshot.ACD';xml=self.folder/'snapshot.L5X'
        acd.write_bytes(baseline.read_bytes());xml.write_bytes(self.project.path.read_bytes())
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        return dict(sourceEquivalentValueSnapshot=True,baselineLogicVerified=True,nativeAcdReopened=True,
            reopenedOnline=True,baselineSha256=digest(baseline),acdSha256=digest(acd),reopenedL5xSha256=digest(xml))

    def test_snapshot_requires_explicit_source_check_matching_target_and_existing_upload(self):
        snapshot.validate_options('upload',True,'source.L5X','saved.ACD')
        for operation in ('connection','download','modes','edits'):
            snapshot.validate_options(operation,False,None,None)
            with self.assertRaises(ValueError):snapshot.validate_options(operation,True,'source.L5X','saved.ACD')
        for values in ((None,'saved.ACD',False,False),('source.L5X',None,False,False),
                       ('source.L5X','saved.ACD',True,False),('source.L5X','saved.ACD',False,True)):
            with self.assertRaises(ValueError):snapshot.validate_options('upload',True,*values)
        for value in (None,1,'true',[]):
            with self.assertRaises(ValueError):snapshot.validate_options('upload',value,'source.L5X','saved.ACD')

    def test_online_baseline_check_has_the_same_strict_profile_without_enabling_a_snapshot(self):
        option='--verify-upload-baseline-online'
        snapshot.validate_options('upload',True,'source.L5X','saved.ACD',option=option)
        for operation,source,target,save,new in (('connection','source.L5X','saved.ACD',False,False),
                ('upload',None,'saved.ACD',False,False),('upload','source.L5X',None,False,False),
                ('upload','source.L5X','saved.ACD',True,False),('upload','source.L5X','saved.ACD',False,True)):
            with self.assertRaisesRegex(ValueError,option):snapshot.validate_options(operation,True,source,target,save,new,option=option)

    def test_baseline_online_receipt_requires_all_ordered_native_steps(self):
        methods=('GoOnlineAsync:verify-upload-baseline','Verify upload baseline Online',
                 'GoOfflineAsync:verify-upload-baseline','Require upload baseline Offline before upload')
        receipt=dict(uploadBaselineOnlineVerified=True,steps=[dict(method=name,status='succeeded') for name in methods])
        self.assertTrue(snapshot.baseline_online_verified(receipt))
        for flag in (False,None,1):
            self.assertFalse(snapshot.baseline_online_verified(dict(receipt,uploadBaselineOnlineVerified=flag)))
        for variant in (receipt['steps'][:-1],list(reversed(receipt['steps'])),receipt['steps']+[receipt['steps'][0]],
                        [dict(row,status='failed') if i==1 else row for i,row in enumerate(receipt['steps'])]):
            self.assertFalse(snapshot.baseline_online_verified(dict(receipt,steps=variant)))
        self.assertFalse(snapshot.baseline_online_verified(None))

    def test_only_unedited_saved_download_identity_is_admitted_without_rewriting_it(self):
        original,baseline,state=self.inputs();before=baseline.read_bytes()
        result=snapshot.prepare(original,baseline,state)
        self.assertEqual(result['download_uid'],FIELDS[10]);self.assertEqual(baseline.read_bytes(),before)
        for change in ({10:0},{8:1},{9:1},{3:1},{11:1},{12:4}):
            baseline.write_bytes(container(fields={**FIELDS,11:0,**change}))
            with self.subTest(change=change),self.assertRaises(ValueError):snapshot.prepare(original,baseline,state)
        baseline.write_bytes(before)
        for field,value in (('installed',False),('source_equivalent',False)):
            changed=copy.deepcopy(state);changed['connectivity']['native_download'][field]=value
            with self.assertRaises(ValueError):snapshot.prepare(original,baseline,changed)
        changed=copy.deepcopy(state);changed['routine_edits']['revision']=1
        with self.assertRaises(ValueError):snapshot.prepare(original,baseline,changed)

    def test_complete_saved_content_retained_identity_and_native_online_receipt_all_required(self):
        _,baseline,_=self.inputs();expected=self.plan();receipt=self.artifacts(baseline)
        result=snapshot.verify(self.folder,expected,self.types,baseline,receipt)
        self.assertTrue(result['verified']);self.assertTrue(result['correlation_preserved'])
        self.assertEqual(result['content']['value_bytes'],45);self.assertEqual(result['content']['rungs'],10)
        for key in ('sourceEquivalentValueSnapshot','baselineLogicVerified','nativeAcdReopened','reopenedOnline'):
            with self.subTest(key=key):
                self.assertFalse(snapshot.verify(self.folder,expected,self.types,baseline,dict(receipt,**{key:False}))['verified'])
        self.assertFalse(snapshot.verify(self.folder,expected,self.types,baseline,None)['verified'])

    def test_changed_identity_malformed_acd_or_wrong_artifact_hash_cannot_claim_snapshot(self):
        _,baseline,_=self.inputs();expected=self.plan()
        for case in ('identity','malformed','acd-hash','xml-hash','baseline-hash'):
            with self.subTest(case=case):
                receipt=self.artifacts(baseline);acd=self.folder/'snapshot.ACD'
                if case=='identity':acd.write_bytes(container(fields={**FIELDS,11:0,10:123}))
                if case=='malformed':acd.write_bytes(b'malformed acd bytes')
                if case in ('identity','malformed'):receipt['acdSha256']=hashlib.sha256(acd.read_bytes()).hexdigest()
                if case=='acd-hash':receipt['acdSha256']='0'*64
                if case=='xml-hash':receipt['reopenedL5xSha256']='0'*64
                if case=='baseline-hash':receipt['baselineSha256']='0'*64
                self.assertFalse(snapshot.verify(self.folder,expected,self.types,baseline,receipt)['verified'])

    def test_matching_hashes_and_online_flags_do_not_hide_changed_values_logic_or_partial_xml(self):
        _,baseline,_=self.inputs();expected=self.plan()
        for case in ('value','logic','partial'):
            receipt=self.artifacts(baseline);path=self.folder/'snapshot.L5X';root=ET.fromstring(path.read_bytes())
            if case=='value':root.find('.//Tag[@Name="SpeedSetpoint"]/Data[@Format="Decorated"]/DataValue').set('Value','87')
            if case=='logic':root.find('.//Routine/RLLContent/Rung/Text').text='NOP();'
            if case=='partial':root.set('TargetType','Program')
            raw=ET.tostring(root);path.write_bytes(raw);receipt['reopenedL5xSha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(case=case):self.assertFalse(snapshot.verify(self.folder,expected,self.types,baseline,receipt)['verified'])
