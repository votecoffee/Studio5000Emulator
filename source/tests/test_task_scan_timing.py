"""Independent committed multi-Task scan durations, not controller CPU timing."""
import copy
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_gsv_this as current
import test_gsv_configuration as config
from logixlab.model import ModelError
from logixlab.program_timing import ProgramTiming


class TaskScanTimingTests(unittest.TestCase):
    setUp=config.GsvConfigurationTests.setUp
    engine=config.GsvConfigurationTests.engine
    checked=config.GsvConfigurationTests.checked

    @staticmethod
    def outputs(root):
        current.GsvThisTests.outputs(root);tags=root.find('./Controller/Tags')
        for name in ('BackgroundLast','BackgroundMax','FastLast','FastMax','SlowLast','SlowMax'):
            config.scalar(tags,name,'DINT',-1)

    @staticmethod
    def reads():
        return [f'GSV(Task,{task}Task,{attr},{task}{dest});' for task in ('Background','Fast','Slow')
                for attr,dest in [('LastScanTime','Last'),('MaxScanTime','Max')]]

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.trace,e.time_ms,e.scan_count,
                              e.scheduler_description(),e._program_timings,e._task_scan_timings,e._task_measurements))

    def fault(self,e,text):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,text):e.step(25)
        self.assertEqual(self.snapshot(e),before);self.assertIsNone(e._executing_task)

    def test_each_invocation_has_independent_last_max_and_counts(self):
        e=self.checked(self.reads(),mutate=self.outputs)
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,3000,10000,15000,20000,27000,30000,41000)):
            e.step(25)
        self.assertEqual([e.memory.read(t+a) for t in ('Background','Fast','Slow') for a in ('Last','Max')],[0]*6)
        self.assertEqual([(e._task_scan_timings[t].last_ns,e._task_scan_timings[t].maximum_ns,e._task_scan_timings[t].executions)
                          for t in ('backgroundtask','fasttask','slowtask')],[(11000,11000,1),(5000,5000,2),(7000,7000,1)])
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(50000,59000,60000,64000,70000,78000,80000,82000,90000,95000)):
            e.step(25)
        self.assertEqual([e.memory.read(t+a) for t in ('Background','Fast','Slow') for a in ('Last','Max')],[11,11,5,5,7,7])
        self.assertEqual((e._task_scan_timings['fasttask'].last_ns,e._task_scan_timings['fasttask'].maximum_ns,e._task_scan_timings['fasttask'].executions),(8000,9000,5))

    def test_this_and_named_calls_in_each_program_read_prior_committed_task_snapshot(self):
        for program in ('BackgroundProgram','FastProgram','SlowProgram'):
            def move(root):
                self.outputs(root)
                if program!='BackgroundProgram':current.GsvThisTests.adopt(root,program)
            e=self.checked([f'GSV(Task,THIS,LastScanTime,CurrentLast);GSV(Task,{program.replace("Program","Task")},LastScanTime,NamedLast);',
                            f'GSV(Task,THIS,MaxScanTime,CurrentMax);GSV(Task,{program.replace("Program","Task")},MaxScanTime,NamedMax);'],st=True,mutate=move)
            e.step(25);prior=e._task_scan_timings[program.replace('Program','Task').casefold()];e.step(25)
            self.assertEqual(e.memory.read('CurrentLast'),e.memory.read('NamedLast'));self.assertEqual(e.memory.read('CurrentMax'),e.memory.read('NamedMax'))
            self.assertEqual(e.memory.read('CurrentLast'),prior.last_ns//1000)

    def test_unreleased_and_runtime_inhibited_task_retain_measurements(self):
        e=self.checked(self.reads(),mutate=self.outputs);e.step(5)
        self.assertEqual(e._task_scan_timings['fasttask'],ProgramTiming());self.assertEqual(e.memory.read('FastLast'),0)
        e.step(25);prior=e._task_scan_timings['fasttask'];e._task_scheduler.inhibitions[1]=True;e.step(25)
        self.assertEqual(e._task_scan_timings['fasttask'],prior);self.assertEqual(e.memory.read('FastLast'),prior.last_ns//1000)
        e._task_scheduler.inhibitions[1]=False;e.step(25);self.assertGreater(e._task_scan_timings['fasttask'].executions,prior.executions)

    def test_false_and_prescan_do_not_read_indices_or_measurements(self):
        e=self.checked(['XIC(Flag)GSV(Task,FastTask,LastScanTime,Values[Index]);'],mutate=self.outputs);e.memory.write('Index',99)
        with patch.object(e,'task_scan_timing_attributes',side_effect=AssertionError('Unused measurement')):
            e.enter_run();e.step(25)
        self.assertIsNone(e.memory.read('Values')[1]);e.memory.write('Flag',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);e.step(25);self.assertGreaterEqual(e.memory.read('Values[1]'),0)
        self.assertEqual((e.memory.read('Values[0]'),e.memory.read('Values[3]')),(2,999))

    def test_later_fault_rolls_back_all_task_durations_and_release_counts(self):
        e=self.checked(self.reads()+['DIV(1,Index,Out);'],mutate=self.outputs);e.memory.write('Index',1);e.step(25)
        e.memory.write('Index',0);self.fault(e,'zero');e.memory.write('Index',1);prior=e._task_scan_timings['fasttask'];e.step(25)
        self.assertEqual(e.memory.read('FastLast'),prior.last_ns//1000)

    def test_signed_words_and_independent_field_availability(self):
        e=self.checked(['GSV(Task,FastTask,LastScanTime,Out);'])
        e._task_scan_timings['fasttask']=ProgramTiming(0x80000000*1000,0xffffffff*1000,1);e.step(25);self.assertEqual(e.memory.read('Out'),-2147483648)
        e._task_scan_timings['fasttask']=ProgramTiming(5000,0x100000000*1000,1);e.step(25);self.assertEqual(e.memory.read('Out'),5)
        e=self.checked(['GSV(Task,FastTask,MaxScanTime,Out);']);e._task_scan_timings['fasttask']=ProgramTiming(5000,0x100000000*1000,1);self.fault(e,'unavailable')

    def test_drift_harness_event_inhibited_and_incomplete_source_are_guarded(self):
        e=self.checked(['GSV(Task,FastTask,LastScanTime,Out);']);digest=e.project.sha256
        self.assertEqual(e.task_scan_timing_attributes('FastTask',source_sha256='0'*64),{})
        e.project.tasks[1]['name']='Changed';self.assertEqual(e.task_scan_timing_attributes('FastTask',source_sha256=digest),{})
        for field in ('Priority','DisableUpdateOutputs','InhibitTask'):
            def missing(root):root.find('./Controller/Tasks/Task[@Name="FastTask"]').attrib.pop(field)
            self.assertTrue(self.engine(['GSV(Task,FastTask,LastScanTime,Out);'],mutate=missing).blockers)
        def inhibited(root):root.find('./Controller/Tasks/Task[@Name="FastTask"]').set('InhibitTask','true')
        self.assertTrue(self.engine(['GSV(Task,FastTask,LastScanTime,Out);'],mutate=inhibited).blockers)
        self.assertTrue(self.engine(['GSV(Task,FastTask,LastScanTime,Out);'],harness=True).blockers)
        import test_event_tasks as events
        e=events.EventTaskTests.engine(self,[['EVENT(Task1);'],['GSV(Task,Task1,LastScanTime,SpeedCommand);']]);self.assertTrue(e.blockers)

    def test_loop_effects_keep_exact_outputs_and_guard_dynamic_aliases(self):
        e=self.checked(['FOR Index:=0 TO Values[0] DO GSV(Task,FastTask,LastScanTime,Values[1]); END_FOR;'],st=True,mutate=self.outputs);e.step(25)
        self.assertEqual(e.memory.read('Values'),[2,0,None,999])
        def alias(root):self.outputs(root);E.SubElement(root.find('./Controller/Tags'),'Tag',Name='View',TagType='Alias',DataType='DINT',AliasFor='Values[Index]')
        for dest in ('Values[Index]','View'):
            e=self.engine([f'FOR Out:=0 TO Values[3] DO GSV(Task,FastTask,LastScanTime,{dest}); END_FOR;'],st=True,mutate=alias)
            self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)

    def test_run_entry_retains_committed_timings_and_fresh_engine_resets(self):
        e=self.checked(self.reads(),mutate=self.outputs);e.step(25);before=dict(e._task_scan_timings);e.enter_run();self.assertEqual(e._task_scan_timings,before)
        from logixlab.runtime import Engine
        fresh=Engine(e.project);self.assertTrue(all(v==ProgramTiming() for v in fresh._task_scan_timings.values()))

    def test_multitask_gsv_does_not_expand_native_task_measurement_or_status(self):
        e=self.checked(self.reads(),mutate=self.outputs);e.step(25)
        for task in ('BackgroundTask','FastTask','SlowTask'):
            self.assertTrue(e.task_scan_timing_attributes(task,source_sha256=e.project.sha256))
            self.assertEqual(e.task_measurement_attributes(task,source_sha256=e.project.sha256),{})
            self.assertEqual(e.task_status_attributes(task,source_sha256=e.project.sha256),{})
        self.assertIsNone(e._task_measurements);self.assertFalse(e.report()['system_values']['timing']['native_runtime_parity'])

    def test_detached_routine_replacement_retains_independent_timing_state(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked(self.reads(),mutate=self.outputs);e.step(25);before=self.snapshot(e)
        source=decode(container(E.tostring(xml_source(name='Main',text='NOP();'))))
        candidate,receipt=prepare(e,source,['NOP();'],'BackgroundProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertTrue(receipt['applied'])
        self.assertEqual(candidate._task_scan_timings,e._task_scan_timings)
        self.assertIsNot(candidate._task_scan_timings,e._task_scan_timings)
        candidate.step(25);self.assertEqual(self.snapshot(e),before)
