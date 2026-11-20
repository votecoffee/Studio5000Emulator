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

    def test_aoi_draft_keeps_live_instance_state_and_replans_inout_from_live_values(self):
        self.app.command('demo', {'sample': 'AOILab'})
        xml = ET.parse(self.app.engine.project.path)
        tags = xml.find('./Controller/Tags')
        pool = ET.SubElement(tags, 'Tag', Name='SharedPool', TagType='Base', DataType='DINT', Dimensions='2')
        array = ET.SubElement(ET.SubElement(pool, 'Data', Format='Decorated'), 'Array', DataType='DINT', Dimensions='2')
        for index, value in enumerate(('30', '40')):
            ET.SubElement(array, 'Element', Index=f'[{index}]', Value=value)
        for name, value in (('RouteIndex', '0'), ('SavedOutOfRange', '2')):
            tag = ET.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType='DINT')
            ET.SubElement(ET.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value=value)
        original = ET.tostring(xml.getroot(), encoding='utf-8')
        state = self.app.command('load', {'name': 'AOIRebind.L5X', 'content': base64.b64encode(original).decode()})
        self.assertTrue(state['routine_edits']['draft_apply_available'])
        self.assertEqual(state['blockers'], [])
        engine = self.app.engine
        self.app.command('step', {'dt': 10})
        self.assertEqual(engine.memory.read('AccumulatorA.Count'), 2)
        self.assertEqual(engine.memory.read('SharedA'), 12)
        self.app.command('write', {'tag': 'RouteIndex', 'value': 2})
        self.app.command('write', {'tag': 'SavedOutOfRange', 'value': 1})
        routine = next(routine for routine in state['routines'] if routine['key'] == 'MainProgram/MainRoutine')
        rows = [{key: row[key] for key in ('number', 'comment', 'text')} for row in routine['rungs']]
        draft = {'format': 'logixlab-rll-draft', 'version': 1, 'routine': routine['key'],
                 'source_sha256': state['source_sha256'], 'base_revision': 0, 'rungs': rows}
        request = {'project_generation': state['project_generation'], 'draft': draft}

        def use_inout(index):
            rows[0]['text'] = f'XIC(EnableA)LabAccumulator(AccumulatorA,5,TotalA,SharedPool[{index}])OTE(AReady);'

        before = copy.deepcopy(self.app.state())
        use_inout('RouteIndex')
        self.assertEqual(self.app.command('ladder-draft-validate', request), {'valid': True, 'diagnostics': []})
        with self.assertRaisesRegex(ModelError, 'Candidate routine execution is blocked'):
            self.app.command('ladder-draft-apply', request)
        use_inout('SavedOutOfRange')
        with self.assertRaisesRegex(ModelError, 'Edited L5X execution is blocked'):
            self.app.command('ladder-draft-apply', request)
        self.assertIs(self.app.engine, engine)
        self.assertEqual(self.app.state(), before)

        self.app.command('write', {'tag': 'RouteIndex', 'value': 1})
        before = copy.deepcopy(self.app.state())
        use_inout('RouteIndex')
        applied = self.app.command('ladder-draft-apply', request)
        self.assertEqual(applied['aoi_bindings']['AccumulatorA']['shared'], 'SharedPool[1]')
        self.assertEqual(applied['aoi_instances'], before['aoi_instances'])
        self.assertEqual(applied['tags'], before['tags'])
        self.assertEqual(applied['scan'], before['scan'])
        self.assertEqual(self.app.engine.memory.read('AccumulatorA.Count'), 2)
        self.app.command('step', {'dt': 10})
        self.assertEqual(self.app.engine.memory.read('AccumulatorA.Count'), 7)
        self.assertEqual(self.app.engine.memory.read('SharedPool[1]'), 45)
        self.assertEqual(self.app.engine.memory.read('SharedA'), 12)

        result = self.app.command('export-edited-l5x', {})
        exported = ET.fromstring(result['content'])
        for name in ('AddOnInstructionDefinitions', 'Tags'):
            element = f'./Controller/{name}'
            self.assertEqual(ET.tostring(exported.find(element)), ET.tostring(xml.find(element)))
        self.assertEqual(engine.project.path.read_bytes(), original)
        self.app.command('load', {'name': result['filename'], 'content': base64.b64encode(result['content'].encode()).decode()})
        self.assertEqual(self.app.engine.memory.read('TotalA'), 99)
        self.assertEqual(self.app.engine.memory.read('RouteIndex'), 0)
        self.assertEqual(self.app.state()['aoi_bindings']['AccumulatorA']['shared'], 'SharedPool[0]')
        self.app.command('step', {'dt': 10})
        self.assertEqual(self.app.engine.memory.read('AccumulatorA.Count'), 5)
        self.assertEqual(self.app.engine.memory.read('SharedPool[0]'), 35)

    def test_draft_can_switch_to_an_unused_aoi_instance_before_run_prescan(self):
        self.app.command('demo', {'sample': 'AOILab'})
        xml = ET.parse(self.app.engine.project.path)
        tags = xml.find('./Controller/Tags')
        spare = copy.deepcopy(tags.find("Tag[@Name='AccumulatorA']"))
        spare.set('Name', 'SpareAccumulator')
        tags.append(spare)
        loaded = self.app.command('load', {'name': 'SpareAOI.L5X',
            'content': base64.b64encode(ET.tostring(xml.getroot(), encoding='utf-8')).decode()})
        first_scan = self.app.command('step', {'dt': 10})
        routine = next(row for row in loaded['routines'] if row['key'] == 'MainProgram/MainRoutine')
        rows = [{key: row[key] for key in ('number', 'comment', 'text')} for row in routine['rungs']]
        rows[0]['text'] = rows[0]['text'].replace('AccumulatorA,', 'SpareAccumulator,')
        draft = {'format': 'logixlab-rll-draft', 'version': 1, 'routine': routine['key'],
                 'source_sha256': loaded['source_sha256'], 'base_revision': 0, 'rungs': rows}
        applied = self.app.command('ladder-draft-apply', {'project_generation': loaded['project_generation'], 'draft': draft})
        self.assertEqual(applied['tags'], first_scan['tags'])
        self.assertNotIn('AccumulatorA', applied['aoi_instances'])
        self.assertIn('SpareAccumulator', applied['aoi_instances'])

        self.app.engine.enter_run()
        self.app.command('step', {'dt': 10})
        self.assertEqual(self.app.engine.memory.read('SpareAccumulator.Count'), 2)
        self.assertEqual(self.app.engine.memory.read('AccumulatorA.Count'), 2)

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

    def test_duplicate_rungs_with_shared_preset_keep_live_and_imported_values(self):
        xml = ET.parse(self.app.engine.project.path)
        location = ".//Routine[@Name='MainRoutine']/RLLContent"
        rungs = xml.findall(location + '/Rung')
        index = next(i for i, rung in enumerate(rungs) if 'TON(StartDelay' in rung.findtext('Text', ''))
        source_rung = rungs[index]
        source_rung.set('SourceMetadata', 'OriginalOnly')
        source_rung.find('Text').text = 'XIC(RunLatch)TON(StartDelay,321,0);'
        original = ET.tostring(xml.getroot(), encoding='utf-8')
        state = self.app.command('load', {'name': 'DuplicateTimer.L5X',
            'content': base64.b64encode(original).decode()})
        routine = next(row for row in state['routines'] if row['key'] == 'MainProgram/MainRoutine')
        rows = [{'base_index': i, 'text': rung['text'], 'comment': rung['comment']}
                for i, rung in enumerate(routine['rungs'])]
        copied = {**rows[index], 'base_index': None}
        rows[index + 1:index + 1] = [copied, copied.copy()]
        draft = {'format': 'logixlab-rll-draft', 'version': 3, 'routine': routine['key'],
                 'source_sha256': state['source_sha256'], 'base_revision': 0, 'rungs': rows}
        request = {'project_generation': state['project_generation'], 'draft': draft}
        self.app.command('write', {'tag': 'StartDelay.PRE', 'value': 1234})
        self.assertEqual(self.app.command('ladder-draft-validate', request), {'valid': True, 'diagnostics': []})
        after = self.app.command('ladder-draft-apply', request)
        active = next(row for row in after['routines'] if row['key'] == routine['key'])
        for row in active['rungs'][index:index + 3]:
            self.assertEqual(row['nodes'][-1]['args'], ['StartDelay', '?', '?'])
            self.assertEqual(row['nodes'][-1]['source_args'], ['StartDelay', '321', '0'])
        self.assertEqual(self.app.engine.memory.read('StartDelay.PRE'), 1234)
        exported = self.app.command('export-edited-l5x', {})
        rungs = ET.fromstring(exported['content']).findall(location + '/Rung')[index:index + 3]
        self.assertEqual([rung.get('SourceMetadata') for rung in rungs], ['OriginalOnly', None, None])
        self.assertEqual([rung.findtext('Text') for rung in rungs], [copied['text']] * 3)
        self.assertEqual([rung.findtext('Comment') for rung in rungs], [copied['comment']] * 3)
        self.assertEqual(self.app.engine.project.path.read_bytes(), original)
        self.app.command('load', {'name': exported['filename'],
            'content': base64.b64encode(exported['content'].encode()).decode()})
        self.assertEqual(self.app.engine.memory.read('StartDelay.PRE'), 321)

    def test_copied_preset_is_checked_against_the_destination_program_saved_tags(self):
        xml = ET.parse(self.app.engine.project.path)
        controller = xml.find('./Controller')
        main = controller.find(".//Routine[@Name='MainRoutine']/RLLContent")
        source = next(rung for rung in main if 'TON(StartDelay' in rung.findtext('Text', ''))
        source.find('Text').text = 'XIC(RunLatch)TON(StartDelay,321,0);'
        alternate = ET.SubElement(controller.find('Programs'), 'Program', Name='Alternate',
                                  MainRoutineName='Worker', Class='Standard')
        local = copy.deepcopy(controller.find("./Tags/Tag[@Name='StartDelay']"))
        local.find(".//DataValueMember[@Name='PRE']").set('Value', '113')
        ET.SubElement(alternate, 'Tags').append(local)
        worker = ET.SubElement(ET.SubElement(alternate, 'Routines'), 'Routine', Name='Worker', Type='RLL')
        rung = ET.SubElement(ET.SubElement(worker, 'RLLContent'), 'Rung', Number='0', Type='N')
        ET.SubElement(rung, 'Text').text = 'NOP();'
        state = self.app.command('load', {'name': 'CopiedPreset.L5X',
            'content': base64.b64encode(ET.tostring(xml.getroot(), encoding='utf-8')).decode()})
        self.assertEqual(state['blockers'], [])
        source = next(row for row in state['routines'] if row['key'] == 'MainProgram/MainRoutine')['rungs'][1]

        def pasted_draft(key, text):
            routine = next(row for row in state['routines'] if row['key'] == key)
            rows = [{'base_index': i, 'text': rung['text'], 'comment': rung['comment']}
                    for i, rung in enumerate(routine['rungs'])]
            rows.append({'base_index': None, 'text': text, 'comment': source['comment']})
            return {'project_generation': state['project_generation'],
                    'draft': {'format': 'logixlab-rll-draft', 'version': 3, 'routine': key,
                              'source_sha256': state['source_sha256'], 'base_revision': 0, 'rungs': rows}}

        wrong_scope = pasted_draft('Alternate/Worker', source['text'])
        result = self.app.command('ladder-draft-validate', wrong_scope)
        self.assertFalse(result['valid'])
        self.assertIn('would change imported tag initial values for StartDelay.PRE', result['diagnostics'][0])
        with self.assertRaisesRegex(ModelError, 'Alternate/Worker: Rung 1'):
            self.app.command('ladder-draft-apply', wrong_scope)
        fixed_scope = pasted_draft('Alternate/Worker', source['text'].replace(',321,', ',113,'))
        self.assertTrue(self.app.command('ladder-draft-validate', fixed_scope)['valid'])
        self.assertEqual(self.app.state(), state)

        same_program = pasted_draft('MainProgram/Reporting', source['text'])
        self.assertTrue(self.app.command('ladder-draft-validate', same_program)['valid'])
        applied = self.app.command('ladder-draft-apply', same_program)
        self.assertEqual(applied['routine_edits']['edited_routines'], ['mainprogram/reporting'])
        model = self.app.engine.project.routines['mainprogram/reporting'].rungs[-1]
        self.assertEqual(model['nodes'][-1].args, ['StartDelay', '?', '?'])
        exported = self.app.command('export-edited-l5x', {})
        self.app.command('load', {'name': exported['filename'],
            'content': base64.b64encode(exported['content'].encode()).decode()})
        self.assertEqual(self.app.engine.memory.read('StartDelay.PRE'), 321)
        self.assertEqual(self.app.engine.memory.read('StartDelay.PRE', 'Alternate'), 113)

    def test_reordered_draft_changes_scan_order_and_keeps_source_rung_metadata(self):
        xml = ET.parse(self.app.engine.project.path)
        location = ".//Routine[@Name='MainRoutine']/RLLContent"
        content = xml.find(location)
        original_rungs = content.findall('Rung')
        for rung, name, value in ((original_rungs[0], 'First', 11), (original_rungs[-1], 'Last', 22)):
            rung.set('SourceMetadata', name)
            rung.find('Text').text = f'MOV({value},SpeedSetpoint);'
            rung.find('Comment').text = name + ' assignment'
        content.insert(1, ET.Element('Extension', Name='KeepFirstSlot'))
        original = ET.tostring(xml.getroot(), encoding='utf-8')
        initial = self.app.command('load', {'name': 'ReorderDraft.L5X',
            'content': base64.b64encode(original).decode()})
        state = self.app.command('step', {'dt': 10})
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'), 22)
        key = 'MainProgram/MainRoutine'

        def request_for(current):
            rungs = next(row['rungs'] for row in current['routines'] if row['key'] == key)
            draft = {'format': 'logixlab-rll-draft', 'version': 3, 'routine': key,
                     'source_sha256': current['source_sha256'], 'base_revision': current['routine_edits']['revision'],
                     'base_logic_sha256': current['routine_edits']['logic_sha256'],
                     'rungs': [{'base_index': i, 'comment': rung['comment'], 'text': rung['text']}
                               for i, rung in enumerate(rungs)]}
            return {'project_generation': current['project_generation'], 'draft': draft}

        request = request_for(state)
        rows = request['draft']['rungs']
        rows.insert(0, rows.pop())
        with self.assertRaisesRegex(ModelError, 'indices in order'):
            self.app.command('ladder-draft-open', {**request, 'draft': {**request['draft'], 'version': 2}})
        duplicate = [{**rows[0]}, *rows]
        with self.assertRaisesRegex(ModelError, 'unique base indices'):
            self.app.command('ladder-draft-open', {**request, 'draft': {**request['draft'], 'rungs': duplicate}})
        opened = self.app.command('ladder-draft-open', request)['rungs']
        self.assertEqual([rung['base_index'] for rung in opened], [len(rows) - 1, *range(len(rows) - 1)])
        self.assertEqual(opened[0]['comment'], 'Last assignment')
        self.assertEqual(self.app.state(), state)
        self.assertTrue(self.app.command('ladder-draft-validate', request)['valid'])
        applied = self.app.command('ladder-draft-apply', request)
        self.assertEqual(applied['tags'], state['tags'])
        self.app.command('step', {'dt': 10})
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'), 11)
        first = self.app.command('export-edited-l5x', {})
        moved = ET.fromstring(first['content']).find(location)
        self.assertEqual(moved[0].get('SourceMetadata'), 'Last')
        self.assertEqual(moved[1].get('Name'), 'KeepFirstSlot')
        self.assertEqual(moved[2].get('SourceMetadata'), 'First')
        self.assertEqual(moved[0].findtext('Comment'), 'Last assignment')

        second = request_for(applied)
        second['draft']['rungs'].append(second['draft']['rungs'].pop(0))
        self.app.command('ladder-draft-apply', second)
        result = self.app.command('export-edited-l5x', {})
        restored = ET.fromstring(result['content']).find(location)
        self.assertEqual(restored[0].get('SourceMetadata'), 'First')
        self.assertEqual(restored[-1].get('SourceMetadata'), 'Last')
        self.assertEqual(self.app.engine.project.path.read_bytes(), original)

        loaded = self.app.command('load', {'name': first['filename'],
            'content': base64.b64encode(first['content'].encode()).decode()})
        self.assertEqual(loaded['routine_edits']['revision'], initial['routine_edits']['revision'])
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'), 50)
        self.app.command('step', {'dt': 10})
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'), 11)


if __name__=='__main__':unittest.main()
