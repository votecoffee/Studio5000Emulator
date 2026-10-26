"""Offline SDK upload content receipts must prove values and actual source."""
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


if __name__=='__main__':unittest.main()
