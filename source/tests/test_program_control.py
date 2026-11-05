"""Live Program DisableFlag scheduling, first scans, and transaction boundaries."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_event_tasks as events
import test_task_scheduler as fixtures
from logixlab.model import ModelError
from logixlab.runtime import Engine


class ProgramControlTests(unittest.TestCase):
    setUp = fixtures.TaskSchedulerTests.setUp

    @staticmethod
    def controls(root):
        for program in root.findall('./Controller/Programs/Program'):
            program.set('Disabled', 'false')
        tags = root.find('./Controller/Tags')
        for name, dtype, value in (('Command', 'SINT', 0), ('Readback', 'SINT', -1),
                                   ('WideReadback', 'DINT', -1), ('Gate', 'BOOL', 0),
                                   ('Index', 'DINT', 99), ('Divisor', 'DINT', 1)):
            tag = E.SubElement(tags, 'Tag', Name=name, DataType=dtype, TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue',
                         DataType=dtype, Value=str(value))
        tag = E.SubElement(tags, 'Tag', Name='Commands', DataType='SINT', TagType='Base', Dimensions='2')
        data = E.SubElement(tag, 'Data', Format='Decorated')
        array = E.SubElement(data, 'Array', DataType='SINT', Dimensions='2')
        E.SubElement(array, 'Element', Index='[1]', Value='0')

    def engine(self, logic, *, worker=None, st=False, mutate=None):
        def change(root):
            self.controls(root)
            if st:
                routine = root.find('./Controller/Programs/Program/Routines/Routine')
                routine.remove(routine.find('RLLContent'))
                routine.set('Type', 'ST')
                content = E.SubElement(routine, 'STContent')
                for i, line in enumerate(logic):
                    E.SubElement(content, 'Line', Number=str(i)).text = line
            if mutate:
                mutate(root)
        if worker is None:
            worker = ['ADD(Count1,1,Count1);', 'XIC(S:FS)ADD(First1,1,First1);']
        return fixtures.TaskSchedulerTests.engine(
            self, [dict(Priority='1'), dict(Priority='5')], [logic if not st else ['NOP();'], worker],
            mutate=change)

    def checked(self, *args, **kwargs):
        engine = self.engine(*args, **kwargs)
        self.assertEqual(engine.blockers, [])
        return engine

    def test_ladder_and_st_see_flag_and_reenable_first_scan_without_replaying_releases(self):
        reads = ['GSV(Program,program1,DisableFlag,Readback);',
                 'GSV(Program,Program1,DisableFlag,WideReadback);']
        for st, setter in ((False, 'XIC(Gate)SSV(Program,Program1,DisableFlag,Command);'),
                           (True, 'IF Gate THEN SSV(Program,Program1,DisableFlag,Command); END_IF;')):
            with self.subTest(st=st):
                engine = self.checked([setter, *reads], st=st)
                engine.step(10)
                self.assertEqual(engine.memory.read('First1'), 1)
                prior = engine._program_timings['program1']
                engine.memory.write('Gate', True)
                engine.memory.write('Command', -128)
                engine.step(30)
                self.assertEqual((engine.memory.read('Readback'), engine.memory.read('WideReadback')), (1, 1))
                self.assertEqual(engine.memory.read('Count1'), 1)
                self.assertEqual(engine._program_timings['program1'], prior)
                self.assertEqual(engine.scheduler_description()['tasks'][1]['executions'], 4)
                engine.memory.write('Command', 0)
                engine.step(20)
                self.assertEqual((engine.memory.read('Count1'), engine.memory.read('First1')), (3, 2))
                self.assertEqual((engine.memory.read('Readback'), engine.memory.read('WideReadback')), (0, 0))

    def test_self_disable_finishes_body_and_later_program_in_same_task_runs(self):
        def shared_task(root):
            tasks = root.find('./Controller/Tasks')
            E.SubElement(tasks[0].find('ScheduledPrograms'), 'ScheduledProgram', Name='Program1')
            tasks.remove(tasks[1])

        engine = self.checked(['SSV(Program,THIS,DisableFlag,Command);',
                               'GSV(Program,THIS,DisableFlag,Readback);',
                               'ADD(Count0,1,Count0);'],
                              worker=['ADD(Count1,1,Count1);'], mutate=shared_task)
        engine.memory.write('Command', 1)
        engine.step(10)
        self.assertEqual((engine.memory.read('Count0'), engine.memory.read('Count1'),
                          engine.memory.read('Readback')), (1, 1, 1))
        engine.step(10)
        self.assertEqual((engine.memory.read('Count0'), engine.memory.read('Count1')), (1, 2))

    def test_event_dispatches_but_skips_a_disabled_program_then_reenables_in_same_advance(self):
        engine = events.EventTaskTests.engine(self, [
            ['SSV(Program,Program1,DisableFlag,Command);', 'EVENT(Task1);',
             'MOV(0,Command);', 'SSV(Program,Program1,DisableFlag,Command);', 'EVENT(Task1);'],
            ['ADD(Count1,1,Count1);', 'XIC(S:FS)ADD(First1,1,First1);'],
        ], mutate=self.controls)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Command', 1)
        engine.step()
        self.assertEqual((engine.memory.read('Count1'), engine.memory.read('First1')), (1, 1))
        self.assertEqual(engine.scheduler_description()['tasks'][1]['executions'], 2)

    def test_prescan_and_skipped_paths_do_not_read_live_operands(self):
        engine = self.checked(['XIC(Gate)SSV(Program,Program1,DisableFlag,Commands[Index]);',
                               'XIC(Gate)GSV(Program,Program1,DisableFlag,Readback);'])
        engine.enter_run()
        engine.step(10)
        self.assertEqual(engine.memory.read('Readback'), -1)
        engine.memory.write('Gate', True)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):
            engine.step(10)
        engine.memory.write('Index', 0)
        with self.assertRaisesRegex(ModelError, 'known SINT'):
            engine.step(10)
        self.assertEqual(engine._disabled_programs, set())

    def test_fault_rolls_back_live_flags_first_scans_program_and_task_progress(self):
        engine = self.checked(['SSV(Program,Program1,DisableFlag,Command);',
                               'GSV(Program,Program1,DisableFlag,Readback);'],
                              worker=['DIV(1,Divisor,Count1);', 'XIC(S:FS)ADD(First1,1,First1);'])
        engine.step(10)
        engine.memory.write('Command', 1)
        engine.step(10)
        engine.memory.write('Command', 0)
        engine.memory.write('Divisor', 0)
        def snapshot():
            return copy.deepcopy((engine.memory.values, engine.scheduler_description(), engine._program_scanned,
                                  engine._disabled_programs, engine._program_timings, engine.scan_count,
                                  engine.time_ms, engine.trace))
        before = snapshot()
        with self.assertRaisesRegex(ModelError, 'zero'):
            engine.step(10)
        self.assertEqual(snapshot(), before)
        self.assertIsNone(engine._program_advance)
        engine.memory.write('Divisor', 1)
        engine.step(10)
        self.assertEqual(engine.memory.read('First1'), 2)

    def test_run_entry_and_detached_edit_retain_flags_and_fresh_load_restores_source(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container, xml_source

        engine = self.checked(['SSV(Program,Program1,DisableFlag,Command);'])
        engine.memory.write('Command', 1)
        engine.step(10)
        engine.enter_run()
        self.assertEqual(engine._disabled_programs, {'program1'})
        candidate, _ = prepare(engine, decode(container(E.tostring(xml_source(name='Main',text='NOP();')))),
                               ['NOP();'], 'Program0', 0)
        self.assertIsNot(candidate._disabled_programs, engine._disabled_programs)
        self.assertEqual(candidate._disabled_programs, {'program1'})
        candidate.step(10)
        self.assertEqual(candidate.memory.read('Count1'), 0)
        self.assertEqual(Engine(engine.project)._disabled_programs, set())
        self.assertEqual(engine.program_disable_attributes('Program1',source_sha256=engine.project.sha256), {19:b'\1'})
        self.assertEqual(engine.program_disable_attributes('Program1',source_sha256='0'*64), {})
        self.assertEqual(engine.project.program_configuration.attributes('Program1',source_sha256=engine.project.sha256), {19:b'\0'})

    def test_source_disabled_missing_unbound_and_wrong_operand_types_are_guarded(self):
        setter = ['SSV(Program,Program1,DisableFlag,Command);']
        for value in ('true', 'False', None):
            def source(root):
                program = root.find('./Controller/Programs/Program[2]')
                if value is None:
                    program.attrib.pop('Disabled')
                else:
                    program.set('Disabled', value)
            self.assertTrue(self.engine(setter,mutate=source).blockers, value)
        for line in ('SSV(Program,Program1,DisableFlag,WideReadback);',
                     'SSV(Program,Program1,DisableFlag,1);',
                     'GSV(Program,Missing,DisableFlag,WideReadback);',
                     'GSV(Program,Program1,DisableFlag,Gate);'):
            self.assertTrue(self.engine([line]).blockers, line)
