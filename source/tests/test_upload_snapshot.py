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

    def test_online_aggregate_receipt_requires_exact_unique_scoped_paths_and_all_bytes(self):
        paths=["Controller/Tags/Tag[@Name='Record']","Controller/Programs/Program[@Name='Aux']/Tags/Tag[@Name='Record']"]
        tags=[dict(xpath=p,typeCode=c,constant=False,dimensions=d,expectedHex=raw)
            for p,c,d,raw in zip(paths,(0x8F00,0x20C4),([0,0,0],[3,0,0]),('01000000ffff0000','0000000001000000ffffffff'))]
        rows=[dict(xpath=t['xpath'],actualHex=t['expectedHex']) for t in tags]
        expected=dict(tags=tags);receipt=dict(onlineAggregateMaximumBytes=128,onlineAggregateChecks=rows)
        self.assertEqual(snapshot.online_aggregates(expected,receipt),
            dict(verified=True,tags=2,value_bytes=20,maximum_bytes=128,excluded_tags=0))
        self.assertTrue(snapshot.online_aggregates(expected,dict(receipt,onlineAggregateChecks=list(reversed(rows))))['verified'])
        for changed in ([],rows[:1],rows*2,[rows[0]]*2,[dict(rows[0],actualHex='01000000'),rows[1]],
                        [rows[0],dict(rows[1],actualHex=rows[1]['actualHex']+'00')],
                        [dict(rows[0],extra=True),rows[1]],[dict(rows[0],xpath=paths[1]),rows[1]],None):
            self.assertFalse(snapshot.online_aggregates(expected,dict(receipt,onlineAggregateChecks=changed))['verified'])
        for changed in ({},dict(receipt,onlineAggregateMaximumBytes=64),dict(receipt,onlineAggregateMaximumBytes=None)):
            self.assertFalse(snapshot.online_aggregates(expected,changed)['verified'])
        self.assertFalse(snapshot.online_aggregates(dict(tags=tags+[tags[0]]),receipt)['verified'])

    def test_online_aggregate_coverage_includes_short_roots_and_reports_large_roots_outside_its_bound(self):
        def tag(name,code,size,dims,constant=False):
            return dict(xpath="Controller/Tags/Tag[@Name='"+name+"']",typeCode=code,constant=constant,
                expectedHex='00'*size,dimensions=dims)
        eligible=[tag('OneWord',0x8F00,4,[0,0,0]),tag('AtLimit',0x20C4,128,[32,0,0]),tag('Packed',0x20D3,8,[2,0,0]),
                  tag('Odd',0x20C3,6,[3,0,0]),tag('Byte',0x20C2,1,[1,0,0])]
        excluded=[tag('OverLimit',0x20C4,132,[33,0,0])]
        ignored=[tag('Scalar',0xC4,4,[0,0,0]),tag('Constant',0x8F00,4,[0,0,0],True)]
        receipt=dict(onlineAggregateMaximumBytes=128,onlineAggregateChecks=[dict(xpath=t['xpath'],actualHex=t['expectedHex']) for t in eligible])
        result=snapshot.online_aggregates(dict(tags=eligible+excluded+ignored),receipt)
        self.assertEqual(result,dict(verified=True,tags=5,value_bytes=147,maximum_bytes=128,excluded_tags=1))
        empty=dict(onlineAggregateMaximumBytes=128,onlineAggregateChecks=[])
        self.assertEqual(snapshot.online_aggregates(dict(tags=excluded+ignored),empty),
            dict(verified=True,tags=0,value_bytes=0,maximum_bytes=128,excluded_tags=1))

    def test_snapshot_requires_online_aggregate_coverage_independently_of_file_hashes_and_flags(self):
        _,baseline,_=self.inputs();expected=self.plan();receipt=self.artifacts(baseline)
        result=snapshot.verify(self.folder,expected,self.types,baseline,receipt)
        self.assertEqual(result['online_aggregate_checks'],
            dict(verified=True,tags=2,value_bytes=24,maximum_bytes=128,excluded_tags=0))
        for key,value in (('onlineAggregateChecks',[]),('onlineAggregateMaximumBytes',64)):
            self.assertFalse(snapshot.verify(self.folder,expected,self.types,baseline,dict(receipt,**{key:value}))['verified'])

    def test_online_real_receipt_requires_exact_bytes_and_complete_scoped_coverage(self):
        paths=["Controller/Tags/Tag[@Name='Analog']","Controller/Programs/Program[@Name='Main']/Tags/Tag[@Name='Analog']"]
        tags=[dict(xpath=path,typeCode=0xCA,constant=False,expectedHex=value,dimensions=[0,0,0])
            for path,value in zip(paths,('0000a03f','000020c0'))]
        expected=dict(tags=tags);receipt=dict(onlineRealChecks=[dict(xpath=t['xpath'],actualHex=t['expectedHex']) for t in tags])
        self.assertEqual(snapshot.online_reals(expected,receipt),dict(verified=True,tags=2))
        for rows in ([],receipt['onlineRealChecks'][:1],receipt['onlineRealChecks']*2,
                     [receipt['onlineRealChecks'][0]]*2,
                     [dict(xpath=paths[0],actualHex='000020c0'),receipt['onlineRealChecks'][1]],
                     [dict(xpath=paths[0],actualHex='0000a03f',extra=True),receipt['onlineRealChecks'][1]]):
            self.assertFalse(snapshot.online_reals(expected,dict(onlineRealChecks=rows))['verified'])
        self.assertFalse(snapshot.online_reals(expected,{})['verified'])
        self.assertEqual(snapshot.online_reals(dict(tags=[]),{}),dict(verified=True,tags=0))
        for changed in (dict(tags[0],constant=True),dict(tags[0],dimensions=[2,0,0]),dict(tags[0],typeCode=0xC4)):
            self.assertEqual(snapshot.online_reals(dict(tags=[changed]),{}),dict(verified=True,tags=0))

    def test_small_integer_online_receipts_require_exact_signed_bytes_and_scoped_coverage(self):
        paths=["Controller/Tags/Tag[@Name='Byte']","Controller/Programs/Program[@Name='Aux']/Tags/Tag[@Name='Word']"]
        tags=[dict(xpath=path,typeCode=code,constant=False,expectedHex=raw,dimensions=[0,0,0])
            for path,code,raw in zip(paths,(0xC2,0xC3),('80','ff7f'))]
        expected=dict(tags=tags);rows=[dict(xpath=t['xpath'],actualHex=t['expectedHex']) for t in tags]
        self.assertEqual(snapshot.online_small_integers(expected,dict(onlineIntegerChecks=rows)),dict(verified=True,tags=2))
        for changed in ([],rows[:1],rows*2,[rows[0]]*2,[dict(rows[0],actualHex='7f'),rows[1]],
                        [rows[0],dict(rows[1],actualHex='ff7f0000')],[dict(rows[0],extra=True),rows[1]]):
            self.assertFalse(snapshot.online_small_integers(expected,dict(onlineIntegerChecks=changed))['verified'])
        self.assertFalse(snapshot.online_small_integers(expected,{})['verified'])
        self.assertEqual(snapshot.online_small_integers(dict(tags=[]),{}),dict(verified=True,tags=0))
        for changed in (dict(tags[0],constant=True),dict(tags[0],dimensions=[2,0,0]),dict(tags[0],typeCode=0xC4)):
            self.assertEqual(snapshot.online_small_integers(dict(tags=[changed]),{}),dict(verified=True,tags=0))

    def test_lint_online_receipts_require_full_eight_bytes_and_every_scoped_path(self):
        paths=["Controller/Tags/Tag[@Name='Long']","Controller/Programs/Program[@Name='Main']/Tags/Tag[@Name='Long']"]
        tags=[dict(xpath=path,typeCode=0xC5,constant=False,expectedHex=raw,dimensions=[0,0,0])
            for path,raw in zip(paths,('0000000000000080','ffffffffffffff7f'))]
        rows=[dict(xpath=t['xpath'],actualHex=t['expectedHex']) for t in tags];expected=dict(tags=tags)
        self.assertEqual(snapshot.online_lints(expected,dict(onlineLintChecks=rows)),dict(verified=True,tags=2))
        for changed in ([],rows[:1],rows*2,[rows[0]]*2,[dict(rows[0],actualHex='00000000'),rows[1]],
                        [rows[0],dict(rows[1],actualHex='0000000000000080')],[dict(rows[0],extra=True),rows[1]]):
            self.assertFalse(snapshot.online_lints(expected,dict(onlineLintChecks=changed))['verified'])
        self.assertFalse(snapshot.online_lints(expected,{})['verified'])
        self.assertEqual(snapshot.online_lints(dict(tags=[]),{}),dict(verified=True,tags=0))
        for changed in (dict(tags[0],constant=True),dict(tags[0],dimensions=[2,0,0]),dict(tags[0],typeCode=0xC4)):
            self.assertEqual(snapshot.online_lints(dict(tags=[changed]),{}),dict(verified=True,tags=0))

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
            reopenedOnline=True,baselineSha256=digest(baseline),acdSha256=digest(acd),reopenedL5xSha256=digest(xml),
            onlineAggregateMaximumBytes=128,onlineAggregateChecks=[dict(xpath=t['xpath'],actualHex=t['expectedHex'])
                for t in self.plan()['tags'] if t['typeCode']&0x8000 or any(t['dimensions'])])

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
