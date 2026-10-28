"""Offline SDK upload content receipts must prove values and actual source."""
import base64
import copy
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from logixlab.server import Application
from logixlab.model import ModelError
from logixlab.native_types import NativeTypes
from tools import upload_content as content
import test_download_values as layouts


class UploadContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.app=Application(self.folder/'state');self.addCleanup(self.app.close)
        self.app.command('demo',{'sample':'ConveyorDemo'});self.project=self.app.engine.project
        self.types=NativeTypes('a'*64,self.project.sha256,
            [layouts.builtins().types['timer'],layouts.builtins('COUNTER').types['counter']],{'timer':0xF83,'counter':0xF82})
        self.state=self.app.state();self.state['connectivity']['source_l5x_sha256']=self.project.sha256

    def plan(self):return content.plan(self.project,self.types,self.state)

    def program_receipt(self,expected):
        exports=[]
        for program in expected['programs']:
            root=ET.fromstring(self.project.path.read_bytes())
            root.set('TargetType','Program');root.set('TargetName',program['name'])
            path=self.folder/program['fileName'];path.write_bytes(ET.tostring(root))
            exports.append(dict(fileName=program['fileName'],sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        return dict(sourceL5xSha256=expected['sourceL5xSha256'],offlineOnly=True,programs=exports)

    def receipt(self,expected):
        exports=[]
        for routine in expected['routines']:
            root=ET.Element('RSLogix5000Content',TargetType='Routine',TargetName=routine['name'])
            program=ET.SubElement(ET.SubElement(ET.SubElement(root,'Controller'),'Programs'),'Program',Name=routine['program'])
            target=ET.SubElement(ET.SubElement(program,'Routines'),'Routine',Name=routine['name'],Type='RLL')
            rll=ET.SubElement(target,'RLLContent')
            for number,text in enumerate(routine['expectedRungs']):
                ET.SubElement(ET.SubElement(rll,'Rung',Number=str(number)),'Text').text='\n '+text+'\n'
            path=self.folder/routine['fileName'];path.write_bytes(ET.tostring(root))
            exports.append(dict(fileName=routine['fileName'],sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        return dict(sourceL5xSha256=expected['sourceL5xSha256'],offlineOnly=True,
            tags=[dict(name=t['name'],xpath=t['xpath'],actualHex=t['expectedHex']) for t in expected['tags']],routines=exports)

    def test_complete_current_values_and_every_source_routine_independently_match_native_receipt(self):
        for name,value in (('StartPB',True),('SpeedSetpoint',87),('StartDelay.ACC',123),('StartDelay.EN',True),('Parts.ACC',3)):
            next(r for r in self.state['tags'] if r['name']==name)['value']=value
        before=copy.deepcopy(self.app.engine.memory.values);expected=self.plan();tags={r['name']:r for r in expected['tags']}
        self.assertEqual(bytes.fromhex(tags['StartPB']['expectedHex']),b'\1')
        self.assertEqual(bytes.fromhex(tags['SpeedSetpoint']['expectedHex']),struct.pack('<i',87))
        self.assertEqual(bytes.fromhex(tags['StartDelay']['expectedHex']),struct.pack('<Iii',0x80000000,1000,123))
        actual=content.verify(self.folder,expected,self.receipt(expected))
        self.assertEqual(actual,dict(verified=True,offline_values_verified=True,routine_exports_verified=True,
            tags=14,value_bytes=45,routines=2,rungs=10))
        self.assertEqual(self.app.engine.memory.values,before)

    def test_missing_duplicate_changed_or_unknown_leaf_context_and_edited_logic_reject_before_native(self):
        variants=[]
        for field,value in (('unknown',True),('aoi_local',True),('problem','missing'),('type','SINT')):
            state=copy.deepcopy(self.state);state['tags'][0][field]=value;variants.append(state)
        state=copy.deepcopy(self.state);state['tags'].pop();variants.append(state)
        state=copy.deepcopy(self.state);state['tags'].append(state['tags'][0]);variants.append(state)
        state=copy.deepcopy(self.state);state['routines'].pop();variants.append(state)
        state=copy.deepcopy(self.state);state['routines'][0]['rungs'][0]['nodes']=[];variants.append(state)
        state=copy.deepcopy(self.state);state['routine_edits']['revision']=1;variants.append(state)
        state=copy.deepcopy(self.state);state['controller']['mode']='Run';variants.append(state)
        state=copy.deepcopy(self.state);state['connectivity']['source_l5x_sha256']='b'*64;variants.append(state)
        for state in variants:
            with self.subTest(state=state['tags'][0]),self.assertRaises((ValueError,ModelError)):
                content.plan(self.project,self.types,state)
        with patch.object(content,'MAX_TAGS',1),self.assertRaises(ValueError):self.plan()
        with patch.object(content,'MAX_ROUTINES',1),self.assertRaises(ValueError):self.plan()

    def test_false_incomplete_or_reordered_tag_receipts_cannot_claim_uploaded_values(self):
        expected=self.plan();good=self.receipt(expected)
        variants=[None,dict(good,offlineOnly=False),dict(good,sourceL5xSha256='b'*64),dict(good,tags=[]),dict(good,routines=[])]
        changed=copy.deepcopy(good);changed['tags'][0]['actualHex']='01';variants.append(changed)
        changed=copy.deepcopy(good);changed['tags'][0]['xpath']='Controller/Tags/Tag[@Name=\'Foreign\']';variants.append(changed)
        changed=copy.deepcopy(good);changed['tags'].reverse();variants.append(changed)
        for receipt in variants:
            with self.subTest(receipt=receipt):self.assertFalse(content.verify(self.folder,expected,receipt)['verified'])

    def test_forged_export_hash_changed_logic_wrong_target_or_missing_artifact_rejects(self):
        expected=self.plan()
        for case in ('hash','logic','target','program','missing','doctype','duplicated','malformed','wrong-type'):
            with self.subTest(case=case):
                receipt=self.receipt(expected);path=self.folder/expected['routines'][0]['fileName']
                raw=path.read_bytes();root=ET.fromstring(raw)
                if case=='hash':path.write_bytes(raw+b' ')
                elif case=='missing':path.unlink()
                else:
                    if case=='logic':root.find('.//Rung/Text').text='NOP();'
                    if case=='target':root.set('TargetName','Foreign')
                    if case=='program':root.find('.//Program').set('Name','Foreign')
                    if case=='wrong-type':root.find('.//Routine').set('Type','ST')
                    if case=='duplicated':root.find('.//Routines').append(copy.deepcopy(root.find('.//Routine')))
                    data=ET.tostring(root)
                    if case=='doctype':data=b'<!DOCTYPE x>'+data
                    if case=='malformed':data=b'<broken'
                    path.write_bytes(data);receipt['routines'][0]['sha256']=hashlib.sha256(data).hexdigest()
                self.assertFalse(content.verify(self.folder,expected,receipt)['verified'])

    def test_existing_project_upload_option_and_exact_source_are_required(self):
        self.assertIsNone(content.prepare('connection',False,None,None,{}))
        for operation,new in (('connection',False),('upload',True),('download',False)):
            with self.assertRaises(ValueError):content.prepare(operation,new,self.project.path,None,self.state)
        with patch.object(content.NativeTypes,'from_acd',return_value=self.types):
            self.assertEqual(content.prepare('upload',False,self.project.path,'source.ACD',self.state),self.plan())
        state=copy.deepcopy(self.state);state['connectivity']['source_l5x_sha256']='b'*64
        with patch.object(content.NativeTypes,'from_acd',return_value=self.types),self.assertRaises(ValueError):
            content.prepare('upload',False,self.project.path,'source.ACD',state)

    def test_reopened_full_export_must_preserve_every_current_value_and_executable_routine(self):
        expected=self.plan();acd=self.folder/'uploaded.ACD';xml=self.folder/'uploaded.L5X'
        acd.write_bytes(b'synthetic native file receipt only');xml.write_bytes(self.project.path.read_bytes())
        def receipt():return dict(nativeAcdReopened=True,offlineOnly=True,uploadResultSaved=True,
            acdSha256=hashlib.sha256(acd.read_bytes()).hexdigest(),reopenedL5xSha256=hashlib.sha256(xml.read_bytes()).hexdigest())
        result=content.verify_saved(self.folder,expected,self.types,receipt())
        self.assertTrue(result['verified']);self.assertTrue(result['native_acd_reopened']);self.assertEqual(result['value_bytes'],45)
        root=ET.fromstring(xml.read_bytes());root.find('.//Routine/RLLContent/Rung/Text').text='NOP();';xml.write_bytes(ET.tostring(root))
        result=content.verify_saved(self.folder,expected,self.types,receipt())
        self.assertTrue(result['serialized_values_verified']);self.assertFalse(result['verified'])
        xml.write_bytes(self.project.path.read_bytes());changed=copy.deepcopy(expected)
        next(t for t in changed['tags'] if t['name']=='SpeedSetpoint')['expectedHex']=struct.pack('<i',87).hex()
        self.assertFalse(content.verify_saved(self.folder,changed,self.types,receipt())['verified'])
        for field,value in (('controller','Foreign'),('processor','1756-L81E'),('entryRoutines',[]),('taskNames',[])):
            with self.subTest(field=field):self.assertFalse(content.verify_saved(self.folder,dict(expected,**{field:value}),self.types,receipt())['verified'])
        bad=receipt();bad['nativeAcdReopened']=False
        self.assertFalse(content.verify_saved(self.folder,expected,self.types,bad)['verified'])

    def test_serialized_content_check_does_not_invent_native_reopen_or_ignore_program_settings(self):
        expected=self.plan();path=self.folder/'full.L5X';path.write_bytes(self.project.path.read_bytes())
        result=content.verify_serialized(path,expected,self.types)
        self.assertTrue(result['verified']);self.assertNotIn('native_acd_reopened',result)
        changed=copy.deepcopy(expected);changed['programs'][0]['settings']['disabled']=True
        self.assertFalse(content.verify_serialized(path,changed,self.types)['verified'])
        root=ET.fromstring(path.read_bytes());root.set('TargetType','Program');path.write_bytes(ET.tostring(root))
        self.assertFalse(content.verify_serialized(path,expected,self.types)['verified'])

    def test_changed_array_declaration_cannot_hide_behind_unchanged_decorated_scalar(self):
        expected=self.plan();path=self.folder/'changed-dimensions.L5X'
        root=ET.fromstring(self.project.path.read_bytes())
        root.find("./Controller/Tags/Tag[@Name='SpeedSetpoint']").set('Dimensions','2')
        path.write_bytes(ET.tostring(root))
        # The value parser still returns scalar 50; that is insufficient proof
        # that the native file declares the expected scalar tag.
        changed=content.Project(path)
        self.assertEqual(changed.initial['speedsetpoint'],50)
        self.assertFalse(content.verify_serialized(path,expected,self.types)['verified'])
        state=copy.deepcopy(self.state);state['connectivity']['source_l5x_sha256']=changed.sha256
        with self.assertRaisesRegex(ValueError,'declared dimensions'):
            content.plan(changed,self.types,state)

    def test_full_export_checks_logical_bool_bits_separately_from_packed_words(self):
        root=ET.fromstring(self.project.path.read_bytes());parent=root.find('./Controller/Tags')
        node=ET.SubElement(parent,'Tag',Name='Bits',TagType='Base',DataType='BOOL',Dimensions='32',Constant='true')
        array=ET.SubElement(ET.SubElement(node,'Data',Format='Decorated'),'Array',DataType='BOOL',Dimensions='32')
        for i in range(32):ET.SubElement(array,'Element',Index=f'[{i}]',Value=str(int(i in (0,7,31))))
        path=self.folder/'bits.L5X';path.write_bytes(ET.tostring(root))
        self.app.command('load',dict(name=path.name,content=base64.b64encode(path.read_bytes()).decode()))
        self.project=self.app.engine.project;self.state=self.app.state()
        self.state['connectivity']['source_l5x_sha256']=self.project.sha256
        expected=self.plan();self.assertTrue(content.verify_serialized(path,expected,self.types)['verified'])
        root.find(".//Tag[@Name='Bits']").set('Dimensions','1');path.write_bytes(ET.tostring(root))
        self.assertFalse(content.verify_serialized(path,expected,self.types)['verified'])

    def test_native_program_package_checks_settings_full_routine_set_and_artifact_identity(self):
        expected=self.plan();receipt=self.program_receipt(expected)
        self.assertEqual(content.verify_programs(self.folder,expected,self.types,receipt),
            dict(verified=True,programs_verified=1,routines_verified=2,local_tags_verified=0))
        for case in ('hash','missing','target','extra-program','main','disabled','class','type','folder','routine','extra-routine','logic','doctype'):
            with self.subTest(case=case):
                receipt=self.program_receipt(expected);path=self.folder/expected['programs'][0]['fileName']
                root=ET.fromstring(path.read_bytes());program=root.find('./Controller/Programs/Program')
                if case=='hash':path.write_bytes(path.read_bytes()+b' ')
                elif case=='missing':path.unlink()
                else:
                    if case=='target':root.set('TargetName','Foreign')
                    if case=='extra-program':root.find('./Controller/Programs').append(copy.deepcopy(program))
                    if case=='main':program.set('MainRoutineName','Reporting')
                    if case=='disabled':program.set('Disabled','true')
                    if case=='class':program.set('Class','Safety')
                    if case=='type':program.set('Type','Phase')
                    if case=='folder':program.set('UseAsFolder','true')
                    if case=='routine':program.find('Routines').remove(program.find('./Routines/Routine'))
                    if case=='extra-routine':
                        extra=copy.deepcopy(program.find('./Routines/Routine'));extra.set('Name','Foreign');program.find('Routines').append(extra)
                    if case=='logic':program.find('.//Rung/Text').text='NOP();'
                    raw=ET.tostring(root)
                    if case=='doctype':raw=b'<!DOCTYPE x>'+raw
                    path.write_bytes(raw);receipt['programs'][0]['sha256']=hashlib.sha256(raw).hexdigest()
                self.assertFalse(content.verify_programs(self.folder,expected,self.types,receipt)['verified'])

    def test_program_local_values_types_and_coverage_are_independent_of_controller_context(self):
        root=ET.fromstring(self.project.path.read_bytes());program=root.find('./Controller/Programs/Program')
        tags=program.find('Tags')
        if tags is None:tags=ET.SubElement(program,'Tags')
        tag=ET.SubElement(tags,'Tag',Name='LocalValue',TagType='Base',DataType='DINT',Radix='Decimal',Constant='false',ExternalAccess='Read/Write')
        ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Radix='Decimal',Value='87')
        path=self.folder/'scoped.L5X';path.write_bytes(ET.tostring(root));self.project=content.Project(path)
        self.app.command('load',{'name':'scoped.L5X','content':base64.b64encode(path.read_bytes()).decode()})
        self.state=self.app.state();self.state['connectivity']['source_l5x_sha256']=self.project.sha256
        self.types=NativeTypes('a'*64,self.project.sha256,list(self.types.types.values()),dict(self.types.type_ids))
        expected=self.plan();receipt=self.program_receipt(expected)
        self.assertEqual(content.verify_programs(self.folder,expected,self.types,receipt)['local_tags_verified'],1)
        export=self.folder/expected['programs'][0]['fileName']
        for case in ('value','missing','type','constant','dimension'):
            receipt=self.program_receipt(expected);root=ET.fromstring(export.read_bytes());tags=root.find('./Controller/Programs/Program/Tags');tag=tags.find('Tag')
            if case=='value':tag.find('./Data/DataValue').set('Value','0')
            if case=='missing':tags.remove(tag)
            if case=='type':tag.set('DataType','REAL')
            if case=='constant':tag.set('Constant','true')
            if case=='dimension':tag.set('Dimensions','2')
            raw=ET.tostring(root);export.write_bytes(raw);receipt['programs'][0]['sha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(case=case):self.assertFalse(content.verify_programs(self.folder,expected,self.types,receipt)['verified'])

    def test_incomplete_foreign_or_reordered_program_receipts_do_not_pass(self):
        expected=self.plan();good=self.program_receipt(expected)
        for receipt in (None,dict(good,offlineOnly=False),dict(good,sourceL5xSha256='b'*64),dict(good,programs=[]),dict(good,programs=good['programs']*2)):
            self.assertFalse(content.verify_programs(self.folder,expected,self.types,receipt)['verified'])
        with patch.object(content,'MAX_PROGRAMS',0),self.assertRaises(ValueError):self.plan()


if __name__=='__main__':unittest.main()
