"""Committed instruction-only Event Task and current-Program scan timings."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_event_inhibit as inhibit
import test_event_status as status
from logixlab.model import ModelError,Op
from logixlab.task_runtime import TaskMeasurements


class EventTimingTests(unittest.TestCase):
    setUp=inhibit.EventInhibitTests.setUp
    checked=status.EventStatusTests.checked
    snapshot=staticmethod(status.EventStatusTests.snapshot)
    fault=status.EventStatusTests.fault

    def engine(self,bodies=None,**kwargs):
        bodies=bodies or [['XIC(StartPB)EVENT(Task1);','GSV(Task,Task1,LastScanTime,CallerStatus);','GSV(Task,Task1,MaxScanTime,AfterStatus);'],
                          ['GSV(Task,THIS,LastScanTime,EntryStatus);','GSV(Program,THIS,LastScanTime,ExitStatus);','ADD(Count1,1,Count1);']]
        return inhibit.EventInhibitTests.engine(self,bodies,**kwargs)

    def test_event_duration_first_zero_then_previous_committed_last_and_max(self):
        e=self.checked();e.memory.write('StartPB',True)
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,7000)):e.step()
        self.assertEqual((e.memory.read('CallerStatus'),e.memory.read('AfterStatus'),e.memory.read('EntryStatus'),e.memory.read('ExitStatus')),(0,0,0,0))
        prior_program=e._program_timings['program1']
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(10000,14000)):e.step()
        self.assertEqual((e.memory.read('CallerStatus'),e.memory.read('AfterStatus'),e.memory.read('EntryStatus')),(7,7,7))
        self.assertEqual(e.memory.read('ExitStatus'),prior_program.last_ns//1000)
        self.assertEqual(tuple(getattr(e._task_scan_timings['task1'],a) for a in ('last_ns','maximum_ns','executions')),(4000,7000,2))

    def test_multiple_events_in_one_advance_share_the_prior_snapshot(self):
        e=self.checked([['EVENT(Task1);','GSV(Task,Task1,LastScanTime,CallerStatus);','EVENT(Task1);','GSV(Task,Task1,LastScanTime,AfterStatus);'],['GSV(Task,THIS,LastScanTime,EntryStatus);','ADD(Count1,1,Count1);']])
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,3000,10000,15000)):e.step()
        self.assertEqual((e.memory.read('CallerStatus'),e.memory.read('AfterStatus'),e.memory.read('EntryStatus'),e.memory.read('Count1')),(0,0,0,2))
        self.assertEqual(tuple(getattr(e._task_scan_timings['task1'],a) for a in ('last_ns','maximum_ns','executions')),(5000,5000,2))

    def test_active_overlap_does_not_add_a_timing_record(self):
        e=self.checked([['EVENT(Task1);'],['EVENT(Task1);','ADD(Count1,1,Count1);']])
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,9000)):e.step()
        self.assertEqual(tuple(getattr(e._task_scan_timings['task1'],a) for a in ('last_ns','maximum_ns','executions')),(9000,9000,1));self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],1)

    def test_deferred_pending_duplicates_record_only_the_executed_body(self):
        def periodic(root):root.find('./Controller/Tasks/Task').attrib.update(Type='PERIODIC',Priority='5',Rate='10')
        e=self.checked([['EVENT(Task1);','EVENT(Task1);','GSV(Task,Task1,LastScanTime,CallerStatus);'],['GSV(Task,THIS,LastScanTime,EntryStatus);']],priority='14',mutate=periodic)
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,5000)):e.step()
        self.assertEqual((e.memory.read('CallerStatus'),e.memory.read('EntryStatus')),(0,0));self.assertEqual(tuple(getattr(e._task_scan_timings['task1'],a) for a in ('last_ns','maximum_ns','executions')),(5000,5000,1))

    def test_masked_pending_cancellation_does_not_sample_or_update_timing(self):
        e=self.checked([['UID();','EVENT(Task1);','SSV(Task,Task1,InhibitTask,SelfCommand);','UIE();'],['NOP();']])
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=AssertionError('Canceled body clock')):e.step()
        self.assertEqual(e._task_scan_timings['task1'],TaskMeasurements());self.assertEqual(e._task_event_status['task1'],1)

    def test_runtime_inhibition_retains_successful_measurement_until_a_new_run(self):
        e=self.checked([['SSV(Task,Task1,InhibitTask,Command);','EVENT(Task1);','GSV(Task,Task1,LastScanTime,CallerStatus);'],['ADD(Count1,1,Count1);']])
        e.step();prior=e._task_scan_timings['task1'];e.memory.write('Command',1);e.step()
        self.assertEqual(e._task_scan_timings['task1'],prior);self.assertEqual(e.memory.read('CallerStatus'),prior.last_ns//1000)
        e.memory.write('Command',0);e.step();self.assertEqual(e._task_scan_timings['task1'].executions,2)

    def test_initially_inhibited_event_has_zero_then_measures_enabled_self_inhibited_body(self):
        e=self.checked([['XIC(ClearStatus)SSV(Task,Task1,InhibitTask,Command);','EVENT(Task1);','GSV(Task,Task1,LastScanTime,CallerStatus);'],['SSV(Task,THIS,InhibitTask,SelfCommand);','ADD(Count1,1,Count1);']],inhibited=True)
        e.step();self.assertEqual(e._task_scan_timings['task1'],TaskMeasurements());self.assertEqual(e.memory.read('CallerStatus'),0)
        e.memory.write('ClearStatus',True)
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,5000)):e.step()
        self.assertEqual(tuple(getattr(e._task_scan_timings['task1'],a) for a in ('last_ns','maximum_ns','executions')),(5000,5000,1));self.assertTrue(e._task_scheduler.inhibitions[1])

    def test_parent_and_event_faults_restore_all_event_measurements(self):
        for bodies in ([['EVENT(Task1);','DIV(1,Divisor,SpeedCommand);'],['EVENT(Task1);']],
                       [['EVENT(Task1);'],['DIV(1,Divisor,SpeedCommand);']]):
            e=self.checked(bodies);e.memory.write('Divisor',0);self.fault(e,'zero');self.assertEqual(e._task_scan_timings['task1'],TaskMeasurements())
            e.memory.write('Divisor',1);e.step();self.assertEqual(e._task_scan_timings['task1'].executions,1)

    def test_st_this_program_and_task_reads_match_their_named_snapshots(self):
        e=self.checked([['EVENT(Task1); GSV(Task,Task1,LastScanTime,CallerStatus);'],['GSV(Task,THIS,LastScanTime,EntryStatus); GSV(Program,THIS,LastScanTime,ExitStatus); GSV(Program,Program1,LastScanTime,AfterStatus);']],st=True,event_st=True)
        e.step();prior=e._task_scan_timings['task1'];e.step()
        self.assertEqual(e.memory.read('CallerStatus'),e.memory.read('EntryStatus'));self.assertEqual(e.memory.read('EntryStatus'),prior.last_ns//1000);self.assertEqual(e.memory.read('ExitStatus'),e.memory.read('AfterStatus'))

    def test_nested_event_task_durations_are_independent_and_inclusive(self):
        import test_task_scheduler as scheduler
        def infos(root):
            for task in root.findall('./Controller/Tasks/Task')[1:]:E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
        e=scheduler.TaskSchedulerTests.engine(self,[dict(Type='CONTINUOUS'),dict(Type='EVENT',Priority='5',DisableUpdateOutputs='true'),dict(Type='EVENT',Priority='1',DisableUpdateOutputs='true')],
                [['EVENT(Task1);'],['EVENT(Task2);'],['NOP();']],mutate=infos);self.assertEqual(e.blockers,[])
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,1000,4000,9000)):e.step()
        self.assertEqual((e._task_scan_timings['task1'].last_ns,e._task_scan_timings['task2'].last_ns),(9000,3000))

    def test_dormant_index_unknown_destinations_and_st_for_effects(self):
        e=self.checked([['XIC(ReadStatus)GSV(Task,Task1,LastScanTime,Values[Index]);'],['NOP();']]);e.enter_run();e.step();self.assertIsNone(e.memory.read('Values')[1])
        e.memory.write('ReadStatus',True);self.fault(e,'outside bounds');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Values'),[101,0,999])
        e=self.checked([['FOR Command:=0 TO Values[0] DO GSV(Task,Task1,LastScanTime,Values[1]); END_FOR;'],['NOP();']],st=True);e.step();self.assertEqual(e.memory.read('Values'),[101,0,999])
        e=self.engine([['FOR Command:=0 TO Values[2] DO GSV(Task,Task1,LastScanTime,Values[Index]); END_FOR;'],['NOP();']],st=True);self.assertTrue(any('bounds/step' in b for b in e.blockers))

    def test_event_counter_words_have_independent_field_availability(self):
        e=self.checked();e._task_scan_timings['task1']=TaskMeasurements(0x80000000*1000,0xffffffff*1000,executions=1,last_start_ns=0);e.step()
        self.assertEqual((e.memory.read('CallerStatus'),e.memory.read('AfterStatus')),(-2147483648,-1))
        e=self.checked([['GSV(Task,Task1,LastScanTime,CallerStatus);'],['NOP();']]);e._task_scan_timings['task1']=TaskMeasurements(5000,0x100000000*1000,executions=1,last_start_ns=0);e.step();self.assertEqual(e.memory.read('CallerStatus'),5)
        e=self.checked([['GSV(Task,Task1,MaxScanTime,CallerStatus);'],['NOP();']]);e._task_scan_timings['task1']=TaskMeasurements(5000,0x100000000*1000,executions=1,last_start_ns=0);self.fault(e,'unavailable')

    def test_event_only_project_stays_idle_with_initialized_zero_timings(self):
        def only_event(root):
            tasks=root.find('./Controller/Tasks');tasks.remove(tasks[0]);programs=root.find('./Controller/Programs');programs.remove(programs[0])
        e=self.checked(mutate=only_event);self.assertEqual(e._task_scan_timings,{'task1':TaskMeasurements()});e.step();self.assertEqual(e._task_scan_timings['task1'],TaskMeasurements())
        self.assertEqual(e.task_scan_timing_attributes('Task1',source_sha256=e.project.sha256),{7:bytes(4),8:bytes(4),13:bytes(8),14:bytes(8),15:bytes(8)});self.assertEqual(e.task_measurement_attributes('Task1',source_sha256=e.project.sha256),{})

    def test_metadata_context_native_boundary_and_detached_lifecycle(self):
        for field in ('Priority','DisableUpdateOutputs','InhibitTask'):
            def missing(root):root.find('./Controller/Tasks/Task[2]').attrib.pop(field)
            self.assertTrue(self.engine(mutate=missing).blockers,field)
        e=self.checked();self.assertEqual(e.task_scan_timing_attributes('Task1',source_sha256='0'*64),{})
        from logixlab.runtime import Engine
        self.assertTrue(Engine(e.project,mode='routine',routine='Program1/Main').blockers)
        from logixlab import gsv_timing
        e.memory.frames['@AOI:test']={}
        with self.assertRaisesRegex(ModelError,'AOI/harness'):gsv_timing.validate(e,Op('GSV',['Task','Task1','LastScanTime','CallerStatus']),'@AOI:test')
        e.memory.frames.clear();e.memory.write('StartPB',True);e.step();before=self.snapshot(e);e.enter_run();self.assertEqual(e._task_scan_timings,before[-2])
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        candidate,_=prepare(e,decode(container(E.tostring(xml_source(name='Main',text='NOP();')))),['NOP();'],'Program0',0)
        self.assertEqual(candidate._task_scan_timings,e._task_scan_timings);self.assertIsNot(candidate._task_scan_timings,e._task_scan_timings)
        self.assertEqual(e.task_measurement_attributes('Task1',source_sha256=e.project.sha256),{});self.assertFalse(e.report()['system_values']['timing']['native_runtime_parity'])
        self.assertEqual(Engine(e.project)._task_scan_timings['task1'],TaskMeasurements())
