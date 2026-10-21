"""Measured execution, rollback and native DWORD limits for Program timing."""
import copy
from dataclasses import FrozenInstanceError
import struct
import unittest
from unittest.mock import patch
import test_runtime as fixtures
from logixlab.model import ModelError
from logixlab.program_timing import ProgramTiming


class ProgramTimingTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp
    engine=fixtures.RuntimeTests.engine
    def test_initial_then_measured_last_and_maximum_are_whole_microseconds(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        self.assertEqual(engine.program_timing_attributes('MAINPROGRAM',source_sha256=digest),{2:bytes(4),3:bytes(4)})
        with patch('logixlab.runtime.perf_counter_ns',side_effect=(100,250099,900000,1000123)):
            engine.step();engine.step()
        self.assertEqual(engine.program_timing_attributes('MainProgram',source_sha256=digest),
                         {2:struct.pack('<I',100),3:struct.pack('<I',249)})
        self.assertEqual(engine.program_timing_description()['successful_program_executions'],2)
        for name,sha in ((None,digest),('Missing',digest),('MainProgram','a'*64)):
            self.assertEqual(engine.program_timing_attributes(name,source_sha256=sha),{})

    def test_later_program_fault_rolls_back_all_new_measurements_and_values(self):
        def extra(root):
            import xml.etree.ElementTree as E
            programs=root.find('./Controller/Programs');other=copy.deepcopy(programs[0]);other.set('Name','Second');programs.append(other)
            E.SubElement(root.find('./Controller/Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='Second')
        engine=self.engine(['ADD(SpeedCommand,1,SpeedCommand);'],mutate=extra)
        with patch('logixlab.runtime.perf_counter_ns',side_effect=(0,2000,3000,6000)):engine.step()
        before=copy.deepcopy(engine.memory.values);timings=dict(engine._program_timings);routine=engine._routine
        def fail_second(key,depth):
            if key.startswith('second/'):raise ModelError('second program fault')
            return routine(key,depth)
        with patch.object(engine,'_routine',side_effect=fail_second),patch('logixlab.runtime.perf_counter_ns',side_effect=(0,9000,10000)):
            with self.assertRaisesRegex(ModelError,'Scan rolled back'):engine.step()
        self.assertEqual(engine._program_timings,timings);self.assertEqual(engine.memory.values,before)
        self.assertEqual(engine.scan_count,1)

    def test_nested_calls_are_inside_one_measurement_and_prescan_does_not_update(self):
        engine=self.engine(['JSR(Sub,0);'],mutate=lambda root: self.add_sub(root))
        self.assertFalse(engine.blockers)
        with patch('logixlab.runtime.perf_counter_ns',side_effect=(100,8100)) as timer:
            engine.enter_run();engine.step()
            self.assertEqual(timer.call_count,2)
        self.assertEqual(engine._program_timings['mainprogram'],ProgramTiming(8000,8000,1))

    @staticmethod
    def add_sub(root):
        import xml.etree.ElementTree as E
        routines=root.find('./Controller/Programs/Program/Routines');routine=E.SubElement(routines,'Routine',Name='Sub',Type='RLL')
        content=E.SubElement(routine,'RLLContent');rung=E.SubElement(content,'Rung',Number='0',Type='N');E.SubElement(rung,'Text').text='NOP();'

    def test_routine_harness_blocked_disabled_and_unscheduled_programs_have_no_counters(self):
        for mode in ('routine','blocked','disabled','unscheduled'):
            def mutate(root):
                program=root.find('./Controller/Programs/Program')
                if mode=='disabled':program.set('Disabled','true')
                elif mode=='unscheduled':root.find('./Controller/Tasks/Task/ScheduledPrograms').clear()
            engine=self.engine(['Unknown();'] if mode=='blocked' else ['NOP();'],mutate=mutate,
                               mode='routine' if mode=='routine' else 'project',routine='MainProgram/MainRoutine')
            self.assertEqual(engine.program_timing_attributes('MainProgram',source_sha256=engine.project.sha256),{})

    def test_folder_cannot_run_in_task_or_isolated_harness_or_resolve_task_owner(self):
        for mode in ('project','routine'):
            engine=self.engine(['MOV(42,SpeedCommand);'],mode=mode,routine='MainProgram/MainRoutine',
                               mutate=lambda root:root.find('./Controller/Programs/Program').set('UseAsFolder','true'))
            self.assertTrue(any('folder' in item.lower() for item in engine.blockers))
            with self.assertRaises(ModelError):engine.step()
            self.assertEqual(engine.scan_count,0)
            self.assertIsNone(engine.project.task_configuration._tasks['maintask'].scheduled_programs)

    def test_unscheduled_folder_does_not_block_its_independently_scheduled_child(self):
        def folder(root):
            import xml.etree.ElementTree as E
            node=E.SubElement(root.find('./Controller/Programs'),'Program',Name='Folder',UseAsFolder='true',Class='Standard')
            E.SubElement(node,'Tags');group=E.SubElement(node,'ChildPrograms');E.SubElement(group,'ChildProgram',Name='MainProgram')
        engine=self.engine(['NOP();'],mutate=folder)
        self.assertFalse(engine.blockers);engine.step()
        self.assertEqual(engine._program_timings['mainprogram'].executions,1)
        self.assertEqual(engine.program_timing_attributes('Folder',source_sha256=engine.project.sha256),{})
        self.assertEqual(engine.project.program_configuration.flag_attributes('Folder',source_sha256=engine.project.sha256),{31:b'\0'})

    def test_duration_bounds_keep_real_measurements_without_native_wrap_or_clamp(self):
        self.assertEqual(ProgramTiming(0xFFFFFFFF*1000,0xFFFFFFFF*1000,1).attributes(),{2:b'\xff'*4,3:b'\xff'*4})
        timing=ProgramTiming((0x100000000)*1000,(0x100000000)*1000,1)
        self.assertEqual(timing.attributes(),{})
        for args in ((-1,0,1),(1,0,1),(False,0,0),(0,5,0)):
            with self.assertRaises(ValueError):ProgramTiming(*args)
        with self.assertRaises(FrozenInstanceError):timing.executions=2


