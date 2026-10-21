"""Clean model fault records never survive an unclassified fault as zeros."""
import unittest
from unittest.mock import patch
import test_runtime as fixtures
from logixlab.model import ModelError


class ProgramFaultTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp
    engine=fixtures.RuntimeTests.engine

    def test_normal_status_needs_real_owner_clean_whole_project_and_idle_untested_source(self):
        engine=self.engine(['NOP();'],mutate=lambda root:root.find('./Controller/Programs/Program').set('TestEdits','false'))
        args=dict(source_sha256=engine.project.sha256,task_owner=7,idle=True)
        self.assertEqual(engine.program_status_attributes('MainProgram',**args),{1:bytes(2)})
        for update in ({'task_owner':None},{'task_owner':0},{'task_owner':True},{'task_owner':65536},
                       {'idle':False},{'source_sha256':'a'*64}):
            self.assertEqual(engine.program_status_attributes('MainProgram',**{**args,**update}),{})
        engine.fault='unknown';engine.fault=''
        self.assertEqual(engine.program_status_attributes('MainProgram',**args),{})

    def test_clean_model_records_are_44_bytes_and_reads_do_not_scan(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        self.assertEqual(engine.program_fault_attributes('MAINPROGRAM',source_sha256=digest),{20:bytes(44),21:bytes(44)})
        self.assertEqual(engine.scan_count,0)
        engine.step();self.assertEqual(engine.program_fault_description()['known_clean_programs'],1)
        for name,sha in ((None,digest),('Missing',digest),('MainProgram','b'*64)):
            self.assertEqual(engine.program_fault_attributes(name,source_sha256=sha),{})

    def test_fault_history_stays_unknown_after_later_success_until_new_engine(self):
        engine=self.engine(['DIV(SpeedCommand,SpeedSetpoint,SpeedCommand);']);digest=engine.project.sha256
        engine.memory.write('SpeedSetpoint',0)
        with self.assertRaises(ModelError):engine.step()
        self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=digest),{})
        engine.memory.write('SpeedSetpoint',1);engine.step();self.assertEqual(engine.fault,'')
        self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=digest),{})
        self.assertTrue(engine.program_fault_description()['unclassified_fault_seen_since_reset'])
        reset=self.engine(['NOP();'])
        self.assertEqual(reset.program_fault_attributes('MainProgram',source_sha256=reset.project.sha256),{20:bytes(44),21:bytes(44)})

    def test_prescan_and_external_worker_fault_assignments_invalidate_clean_history(self):
        engine=self.engine(['NOP();'])
        with patch.object(engine,'_prescan',side_effect=ModelError('prescan failure')):
            with self.assertRaises(ModelError):engine.enter_run()
        engine.fault='';self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=engine.project.sha256),{})
        engine=self.engine(['NOP();']);engine.fault='external input failure';engine.fault=''
        self.assertEqual(engine.program_fault_description()['known_clean_programs'],0)

    def test_unexecutable_disabled_and_routine_harness_states_have_no_native_clean_record(self):
        for mode in ('blocked','disabled','routine'):
            def mutate(root):
                if mode=='disabled':root.find('./Controller/Programs/Program').set('Disabled','true')
            engine=self.engine(['Unsupported();'] if mode=='blocked' else ['NOP();'],mutate=mutate,
                mode='routine' if mode=='routine' else 'project',routine='MainProgram/MainRoutine')
            self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=engine.project.sha256),{})

    def test_empty_exception_message_still_invalidates_fault_record_history(self):
        engine=self.engine(['NOP();'])
        with patch.object(engine,'_routine',side_effect=ModelError('')):
            with self.assertRaises(ModelError):engine.step()
        self.assertEqual(engine.fault,'ModelError')
        self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=engine.project.sha256),{})
