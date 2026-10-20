"""Edited L5X copies preserve source data and reload the active routine logic."""
import base64
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine
from logixlab.server import Application
from logixlab.routine_edits import prepare
from logixlab.routine_source import decode
from test_routine_source import xml_source,container


class LogicExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
        self.app=Application(self.folder/'app');self.app.command('demo',{'sample':'ConveyorDemo'})

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def edit(self,name,texts):
        root=xml_source(name=name);content=root[0]
        for child in list(content):content.remove(child)
        for index,text in enumerate(texts):
            ET.SubElement(ET.SubElement(content,'Rung',Type='N',RegionId=str(index+1)),'TextIOI').text=text
        source=decode(container(ET.tostring(root)))
        engine=self.app.engine
        self.app.engine,_=prepare(engine,source,tuple(texts),'MainProgram',getattr(engine.project,'runtime_revision',0))

    def test_two_routine_export_reloads_logic_with_original_values_and_preserved_project_xml(self):
        original=self.app.engine.project.path.read_bytes();original_sha=self.app.engine.project.sha256
        main=[r['text'] for r in self.app.engine.project.routines['mainprogram/mainroutine'].rungs]
        self.edit('MainRoutine',['MOV(123,SpeedSetpoint);']+main)
        self.edit('Reporting',['MOV(456,Parts.PRE);','ADD(Parts.ACC,0,DisplayedPartCount);'])
        self.app.engine.memory.write('SpeedSetpoint',999);before=copy.deepcopy(self.app.state())
        result=self.app.command('export-edited-l5x',{})
        self.assertEqual(self.app.state(),before)
        self.assertEqual(result['logic_revision'],2);self.assertEqual(result['tag_values'],'original_import')
        self.assertFalse(result['native_acd_correlation']);self.assertEqual(result['native_studio_import'],'not_verified')
        self.assertEqual(result['base_l5x_sha256'],original_sha)
        payload=result['content'].encode('utf-8');self.assertEqual(hashlib.sha256(payload).hexdigest(),result['sha256'])
        source=ET.fromstring(original);exported=ET.fromstring(payload)
        for path in ('./Controller/Tags','./Controller/Tasks','./Controller/Modules','./Controller/DataTypes'):
            left=source.find(path);right=exported.find(path)
            self.assertEqual(ET.tostring(left) if left is not None else None,ET.tostring(right) if right is not None else None)
        path=self.folder/result['filename'];path.write_bytes(payload);project=Project(path);engine=Engine(project)
        self.assertNotEqual(project.sha256,original_sha)
        for key,routine in self.app.engine.project.routines.items():
            self.assertEqual([r['nodes'] for r in routine.rungs],[r['nodes'] for r in project.routines[key].rungs])
            self.assertEqual([r['comment'] for r in routine.rungs],[r['comment'] for r in project.routines[key].rungs])
        self.assertEqual(engine.memory.read('SpeedSetpoint'),50);engine.step(10)
        self.assertEqual(engine.memory.read('SpeedSetpoint'),123);self.assertEqual(engine.memory.read('Parts.PRE'),456)
        self.assertEqual(self.app.engine.project.path.read_bytes(),original)
        # Browser-style import starts a new artifact with no inherited native manifests.
        state=self.app.command('load',{'name':result['filename'],'content':base64.b64encode(payload).decode()})
        self.assertEqual(state['routine_edits']['revision'],0);self.assertIsNone(self.app.native_project_identity)
        self.assertIsNone(self.app.native_symbols);self.assertIsNone(self.app.native_types);self.assertIsNone(self.app.native_routines)

    def test_unmodified_running_busy_changed_source_and_unknown_target_exports_are_rejected(self):
        with self.assertRaises(ModelError):self.app.command('export-edited-l5x',{})
        self.edit('MainRoutine',['MOV(123,SpeedSetpoint);'])
        self.app.command('controller-mode',{'mode':'Run'})
        with self.assertRaises(ModelError):self.app.command('export-edited-l5x',{})
        self.app.command('controller-mode',{'mode':'Program'})
        project=self.app.engine.project
        changed=self.folder/'changed.L5X';changed.write_bytes(project.path.read_bytes()+b' ')
        with patch.object(project,'path',changed),self.assertRaisesRegex(ModelError,'changed'):
            self.app.command('export-edited-l5x',{})
        with patch.object(project,'runtime_edited_routines',('missing/routine',)),self.assertRaisesRegex(ModelError,'absent'):
            self.app.command('export-edited-l5x',{})
        self.app.busy=True
        with self.assertRaisesRegex(ModelError,'progress'):self.app.command('export-edited-l5x',{})
        self.app.busy=False


if __name__=='__main__':unittest.main()
