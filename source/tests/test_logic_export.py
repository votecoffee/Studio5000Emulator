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

    def test_draft_copy_preserves_rung_metadata_and_existing_timer_initializer(self):
        xml = ET.parse(self.app.engine.project.path)
        timer = next(row for row in xml.findall('.//Program/Routines/Routine/RLLContent/Rung')
                     if 'TON(StartDelay' in row.findtext('Text', ''))
        timer.set('Number', '37')
        timer.set('CustomAttribute', 'keep')
        timer.find('Text').text = 'XIC(RunLatch)TON(StartDelay,321,0);'
        original = xml.getroot()
        loaded = self.app.command('load', {'name': 'InitializerDraft.L5X',
            'content': base64.b64encode(ET.tostring(original, encoding='utf-8')).decode()})
        engine = self.app.engine
        original_bytes = engine.project.path.read_bytes()
        routine = next(row for row in loaded['routines'] if row['key'] == 'MainProgram/MainRoutine')
        self.assertEqual(engine.memory.read('StartDelay.PRE'), 321)
        rows = [{key: row[key] for key in ('number', 'comment', 'text')} for row in routine['rungs']]
        index = next(i for i, row in enumerate(rows) if row['number'] == '37')
        self.assertEqual(routine['rungs'][index]['nodes'][-1]['args'], ['StartDelay', '?', '?'])
        self.assertEqual(routine['rungs'][index]['nodes'][-1]['source_args'], ['StartDelay', '321', '0'])
        draft = {'format': 'logixlab-rll-draft', 'version': 1, 'routine': routine['key'],
                 'source_sha256': loaded['source_sha256'], 'base_revision': 0, 'rungs': rows}
        request = {'project_generation': loaded['project_generation'], 'draft': draft}

        rows[index]['text'] = 'XIC(StartPB)TON(StartDelay,?,?);'
        with self.assertRaisesRegex(ModelError, 'change imported tag initial values'):
            self.app.command('ladder-draft-apply', request)
        self.assertIs(self.app.engine, engine)
        self.assertEqual(self.app.state(), loaded)

        rows[index]['text'] = 'XIC(StartPB)TON(StartDelay,321,0);'
        rows[index]['comment'] = 'Preserved initializer'
        self.app.command('ladder-draft-apply', request)
        exported = self.app.command('export-edited-l5x', {})
        result = ET.fromstring(exported['content'])
        rung = result.find(".//Routine[@Name='MainRoutine']/RLLContent/Rung[@Number='37']")
        self.assertEqual(rung.get('CustomAttribute'), 'keep')
        self.assertEqual(rung.findtext('Comment'), 'Preserved initializer')
        self.assertEqual(rung.findtext('Text'), rows[index]['text'])
        self.assertEqual(engine.project.path.read_bytes(), original_bytes)
        self.assertEqual(self.app.engine.memory.read('StartDelay.PRE'), 321)

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

    def test_rung_layout_draft_reopens_applies_and_preserves_surviving_l5x_metadata(self):
        xml = ET.parse(self.app.engine.project.path)
        content = xml.find(".//Routine[@Name='MainRoutine']/RLLContent")
        content[0].set('DeletedAttribute', 'discard')
        content[1].set('Number', '37')
        content[1].set('CustomAttribute', 'keep')
        ET.SubElement(content, 'Extension', Name='KeepSibling')
        original = ET.tostring(xml.getroot(), encoding='utf-8')
        state = self.app.command('load', {'name': 'LayoutDraft.L5X', 'content': base64.b64encode(original).decode()})
        key = 'MainProgram/MainRoutine'

        def layout_request(current):
            rows = next(row['rungs'] for row in current['routines'] if row['key'] == key)
            draft = {'format': 'logixlab-rll-draft', 'version': 2, 'routine': key,
                     'source_sha256': current['source_sha256'], 'base_revision': current['routine_edits']['revision'],
                     'base_logic_sha256': current['routine_edits']['logic_sha256'],
                     'rungs': [{'base_index': i, 'comment': row['comment'], 'text': row['text']}
                               for i, row in enumerate(rows)]}
            return {'project_generation': current['project_generation'], 'draft': draft}

        request = layout_request(state)
        rows = request['draft']['rungs']
        for indices in ([False], [len(rows)], [1, 1], [2, None, 1]):
            invalid = [{**rows[0], 'base_index': index} for index in indices]
            with self.subTest(indices=indices), self.assertRaisesRegex(ModelError, 'unique base indices in order'):
                self.app.command('ladder-draft-open', {**request, 'draft': {**request['draft'], 'rungs': invalid}})
        rows.pop(0)
        rows.append({'base_index': None, 'comment': 'Speed <limit>\nFor the demo', 'text': 'MOV(71,SpeedSetpoint);'})
        reopened = self.app.command('ladder-draft-open', request)['rungs']
        self.assertEqual(reopened[0]['base_index'], 1)
        self.assertEqual(reopened[0]['number'], '0')
        self.assertIsNone(reopened[-1]['base_index'])
        self.assertEqual(self.app.state(), state)
        self.assertEqual(self.app.command('ladder-draft-validate', request), {'valid': True, 'diagnostics': []})
        applied = self.app.command('ladder-draft-apply', request)
        self.assertEqual(self.app.command('step', {'dt': 10, 'count': 1})['scan'], 1)
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'), 71)

        # Reopen at the new revision and insert above the surviving original rung.
        second = layout_request(applied)
        second['draft']['rungs'].insert(0, {'base_index': None, 'comment': 'Added first', 'text': ';'})
        self.app.command('ladder-draft-apply', second)
        result = self.app.command('export-edited-l5x', {})
        self.assertEqual(result['logic_revision'], 2)
        exported = ET.fromstring(result['content']).find(".//Routine[@Name='MainRoutine']/RLLContent")
        rungs = exported.findall('Rung')
        self.assertEqual([rung.get('Number') for rung in rungs], [str(i) for i in range(len(rungs))])
        self.assertEqual(rungs[0].findtext('Text'), ';')
        self.assertEqual(rungs[1].get('CustomAttribute'), 'keep')
        self.assertTrue(all(rung.get('DeletedAttribute') is None for rung in rungs))
        self.assertEqual(rungs[-1].findtext('Comment'), rows[-1]['comment'])
        self.assertEqual(exported.find('Extension').get('Name'), 'KeepSibling')
        self.assertEqual(self.app.engine.project.path.read_bytes(), original)


if __name__=='__main__':unittest.main()
