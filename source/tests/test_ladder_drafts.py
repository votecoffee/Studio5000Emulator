
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from logixlab.ladder_drafts import reopen, validate
from logixlab.model import ARITIES, ModelError, Project, Routine, parse_rung
from logixlab.routine_edits import record_revision
from logixlab.runtime import Engine
from logixlab.server import Application


class LadderDraftTests(unittest.TestCase):
    def test_revision_digest_distinguishes_identical_rungs_with_different_source_origins(self):
        routine = Routine('MainProgram', 'Main', 'RLL')
        routine.rungs = [{'number': str(index), 'comment': '', 'text': 'NOP();', 'nodes': parse_rung('NOP();')}
                         for index in range(2)]
        key = routine.key.lower()
        original = SimpleNamespace(routines={key: routine})
        same_order = SimpleNamespace(routines=original.routines)
        reversed_order = SimpleNamespace(routines=original.routines)
        record_revision(original, same_order, key, 0, rung_origins=(0, 1))
        record_revision(original, reversed_order, key, 0, rung_origins=(1, 0))
        self.assertNotEqual(same_order.runtime_logic_sha256, reversed_order.runtime_logic_sha256)

    def test_report_offers_only_ladder_instructions_and_the_loaded_project_aois(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Application(directory)
            self.addCleanup(app.close)
            app.command('demo', {'sample': 'ConveyorDemo'})
            report = app.command('report', {})
            catalog = report['ladder_instruction_catalog']
            self.assertEqual(set(catalog), set(ARITIES))
            self.assertEqual(catalog['NOT'], {'min_args': 2, 'max_args': 2, 'step': 1})
            self.assertEqual(catalog['JSR'], {'min_args': 2, 'max_args': 82, 'step': 1, 'defaults': ['?', '0']})
            self.assertEqual(catalog['SBR'], {'min_args': 0, 'max_args': 40, 'step': 1})
            self.assertEqual(catalog['ALMD'], {'min_args': 5, 'max_args': 7, 'step': 2})
            app.command('demo', {'sample': 'AOIConstantsLab'})
            aois = app.command('report', {})['ladder_instruction_catalog']
            self.assertEqual(aois['LABTYPEDINPUTS'],
                             {'min_args': 9, 'max_args': 9, 'step': 1, 'add_on': 'LabTypedInputs'})
            app.command('demo', {'sample': 'ConveyorDemo'})
            self.assertNotIn('LABTYPEDINPUTS', app.command('report', {})['ladder_instruction_catalog'])

    def test_reopen_checks_runtime_digest_even_at_the_same_revision(self):
        routine = Routine('MainProgram', 'Main', 'RLL')
        routine.rungs = [{'number': '0', 'comment': '', 'text': 'NOP();', 'nodes': parse_rung('NOP();')}]
        project = SimpleNamespace(sha256='a' * 64, runtime_revision=1, runtime_logic_sha256='b' * 64,
                                  routines={routine.key.lower(): routine})
        draft = {'format': 'logixlab-rll-draft', 'version': 1, 'source_sha256': project.sha256,
                 'base_revision': 1, 'routine': routine.key,
                 'rungs': [{'number': '0', 'comment': '', 'text': 'XIC(?);'}]}
        for stale in (draft, {**draft, 'base_logic_sha256': 'c' * 64}):
            with self.assertRaisesRegex(ModelError, 'matching base logic revision'):
                reopen(project, stale)
        restored = reopen(project, {**draft, 'base_logic_sha256': project.runtime_logic_sha256})
        self.assertEqual(restored[0]['nodes'], parse_rung('XIC(?);'))
        self.assertEqual(routine.rungs[0]['text'], 'NOP();')

    def test_validation_includes_an_unscheduled_draft_routine(self):
        sample = Path(__file__).resolve().parents[1] / 'samples' / 'ConveyorDemo.L5X'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'unscheduled.L5X'
            project_xml = ET.parse(sample)
            programs = project_xml.getroot().find('./Controller/Programs')
            program = ET.SubElement(programs, 'Program', Name='DraftSpare', Class='Standard', MainRoutineName='Main')
            ET.SubElement(program, 'Tags')
            routine = ET.SubElement(ET.SubElement(program, 'Routines'), 'Routine', Name='Main', Type='RLL')
            rung = ET.SubElement(ET.SubElement(routine, 'RLLContent'), 'Rung', Type='N', Number='7')
            ET.SubElement(rung, 'Text').text = 'NOP();'
            project_xml.write(path, encoding='utf-8', xml_declaration=True)
            project = Project(path)
            engine = Engine(project, defer_prescan=True)
            self.assertNotIn('draftspare/main', engine.active)
            self.assertEqual(engine.blockers, [])
            draft = {'format': 'logixlab-rll-draft', 'version': 1, 'routine': 'DraftSpare/Main',
                     'source_sha256': project.sha256, 'base_revision': 0,
                     'rungs': [{'number': '7', 'comment': '', 'text': 'MOV(1,DraftMissingTag);'}]}
            result = validate(project, draft)
            self.assertFalse(result['valid'])
            self.assertTrue(any('DraftSpare/Main, rung 7' in item and 'DraftMissingTag' in item
                                for item in result['diagnostics']), result)
            self.assertEqual(project.routines['draftspare/main'].rungs[0]['text'], 'NOP();')
            self.assertNotIn('draftspare/main', engine.active)

    def test_validation_rejects_a_result_after_a_project_change(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Application(directory)
            self.addCleanup(app.close)
            before = app.command('demo', {'sample': 'ConveyorDemo'})
            def swap_project(project, draft):
                self.assertEqual(project.sha256, before['source_sha256'])
                app.command('demo', {'sample': 'DataLab'})
                return {'valid': True, 'diagnostics': []}

            with patch('logixlab.ladder_drafts.validate', side_effect=swap_project):
                with self.assertRaisesRegex(ModelError, 'loaded project changed'):
                    app.command('ladder-draft-validate', {'project_generation': before['project_generation'], 'draft': {}})
            self.assertEqual(app.state()['name'], 'DataLab')
