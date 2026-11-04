"""Committed host start/interval GSV windows and independent task histories."""
import copy
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_gsv_configuration as config
import test_gsv_this as current
import test_gsv_timing as single
import test_event_inhibit as events
from logixlab.model import ModelError
from logixlab.task_runtime import TaskMeasurements


class TaskStartGsvTests(unittest.TestCase):
    setUp=config.GsvConfigurationTests.setUp
    checked=config.GsvConfigurationTests.checked

    @staticmethod
    def outputs(root):
        tags=root.find('./Controller/Tags')
        for name in ('Stamp','NamedStamp'):
            config.scalar(tags,name,'LINT',-1)
        for name in ('StartWords','MinWords','MaxWords','NamedWords'):
            tag=E.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Base',Dimensions='4')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='4')
            for i,value in ((0,101),(3,999)):
                E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))

    def engine(self,logic,*,mutate=None,**kwargs):
        def change(root):
            self.outputs(root)
            if mutate:mutate(root)
        return config.GsvConfigurationTests.engine(self,logic,mutate=change,**kwargs)

    def event(self,bodies,**kwargs):
        e=events.EventInhibitTests.engine(self,bodies,mutate=self.outputs,**kwargs)
        self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def reads(task='FastTask'):
        return [f'GSV(Task,{task},{attribute},{dest});' for attribute,dest in
                [('StartTime','Stamp'),('StartTime','StartWords[1]'),
                 ('MinimumInterval','MinWords[1]'),('MaximumInterval','MaxWords[1]')]]

    @staticmethod
    def word(e,name):
        words=e.memory.read(name)[1:3]
        return struct.unpack('<Q',struct.pack('<ii',*words))[0]

    def fault(self,e,text,dt=25):
        before=copy.deepcopy((e.memory.values,e._task_scan_timings,e._task_measurements,
                              e._program_timings,e.scheduler_description(),e.scan_count,e.time_ms,e.trace))
        with self.assertRaisesRegex(ModelError,text):e.step(dt)
        self.assertEqual((e.memory.values,e._task_scan_timings,e._task_measurements,
                          e._program_timings,e.scheduler_description(),e.scan_count,e.time_ms,e.trace),before)

    def test_single_task_reads_same_committed_start_and_interval_words_as_protocol(self):
        def outputs(root):self.outputs(root)
        e=single.GsvTimingTests.engine(self,self.reads('MainTask'),mutate=outputs)
        self.assertEqual(e.blockers,[])
        with patch('logixlab.runtime.current_value_microseconds',side_effect=(1234567,2345678,3456789)),patch('logixlab.task_runtime.perf_counter_ns',side_effect=(1000,4000,11000,16000,41000,42000)):
            e.step();self.assertEqual(e.memory.read('Stamp'),0);self.assertEqual(self.word(e,'MinWords'),0)
            e.step();self.assertEqual(e.memory.read('Stamp'),1234567);self.assertEqual(self.word(e,'StartWords'),1234567);self.assertEqual(self.word(e,'MaxWords'),0)
            e.step();self.assertEqual(e.memory.read('Stamp'),2345678);self.assertEqual(self.word(e,'MinWords'),10);self.assertEqual(self.word(e,'MaxWords'),10)
        self.assertEqual(e._task_measurements.maximum_interval_ns,30000)

    def test_multitask_histories_measure_actual_host_invocations_not_simulated_rate(self):
        e=self.checked(self.reads())
        with patch('logixlab.runtime.current_value_microseconds',side_effect=(100,200,300,400)),patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,3000,10000,15000,20000,27000,30000,41000)):
            e.step(25)
        self.assertEqual(e.memory.read('Stamp'),0);self.assertEqual(e._task_scan_timings['fasttask'].minimum_interval_ns,10000)
        self.assertEqual(e._task_scan_timings['fasttask'].start_time_us,200)
        self.assertEqual(e._task_scan_timings['slowtask'].start_time_us,300)
        e.step(25);self.assertEqual(e.memory.read('Stamp'),200);self.assertEqual(self.word(e,'MinWords'),10);self.assertEqual(self.word(e,'MaxWords'),10)
        self.assertNotEqual(self.word(e,'MinWords'),10000)

    def test_named_and_this_ladder_and_st_reads_share_snapshot_in_each_owner(self):
        for st in (False,True):
            for program in ('BackgroundProgram','FastProgram','SlowProgram'):
                def move(root):
                    if program!='BackgroundProgram':current.GsvThisTests.adopt(root,program)
                task=program.replace('Program','Task')
                logic=['GSV(Task,THIS,StartTime,Stamp);',f'GSV(Task,{task},StartTime,NamedStamp);',
                       'GSV(Task,THIS,MinimumInterval,MinWords[1]);',f'GSV(Task,{task},MinimumInterval,NamedWords[1]);']
                e=self.checked(logic,st=st,mutate=move);e.step(25);prior=e._task_scan_timings[task.casefold()];e.step(25)
                self.assertEqual(e.memory.read('Stamp'),e.memory.read('NamedStamp'));self.assertEqual(e.memory.read('Stamp'),prior.start_time_us)
                self.assertEqual(self.word(e,'MinWords'),self.word(e,'NamedWords'))

    def test_events_with_multiple_invocations_read_prior_advance_and_record_each_start(self):
        e=self.event([['EVENT(Task1);','EVENT(Task1);',*self.reads('Task1')],['GSV(Task,THIS,StartTime,NamedStamp);']])
        with patch('logixlab.runtime.current_value_microseconds',side_effect=(111,222)),patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,3000,10000,15000)):
            e.step()
        self.assertEqual((e.memory.read('Stamp'),e.memory.read('NamedStamp')),(0,0))
        t=e._task_scan_timings['task1'];self.assertEqual((t.executions,t.minimum_interval_ns,t.maximum_interval_ns,t.start_time_us),(2,10000,10000,222))
        e.step();self.assertEqual((e.memory.read('Stamp'),e.memory.read('NamedStamp')),(222,222));self.assertEqual(self.word(e,'MinWords'),10)

    def test_canceled_and_inhibited_events_do_not_sample_starts(self):
        e=self.event([['UID();','EVENT(Task1);','SSV(Task,Task1,InhibitTask,SelfCommand);','UIE();',*self.reads('Task1')],['NOP();']])
        with patch('logixlab.runtime.current_value_microseconds',side_effect=AssertionError('Skipped UTC')),patch('logixlab.task_runtime.perf_counter_ns',side_effect=AssertionError('Skipped start')):
            e.step()
        self.assertEqual(e._task_scan_timings['task1'],TaskMeasurements());self.assertEqual(e.memory.read('Stamp'),0)

    def test_false_prescan_skip_indices_and_full_pair_writes_establish_unknowns(self):
        e=self.checked(['XIC(Flag)GSV(Task,FastTask,MinimumInterval,MinWords[Index]);'])
        e.memory.write('Index',99);e.enter_run();e.step(25);self.assertIsNone(e.memory.read('MinWords')[1])
        e.memory.write('Flag',True);self.fault(e,'outside bounds');e.memory.write('Index',1);prior=e._task_scan_timings['fasttask'];e.step(25)
        self.assertEqual(self.word(e,'MinWords'),prior.minimum_interval_ns//1000)
        self.assertEqual((e.memory.read('MinWords')[0],e.memory.read('MinWords')[3]),(101,999))

    def test_alias_and_complete_window_validation_before_any_write(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Selected',TagType='Alias',DataType='DINT',AliasFor='StartWords[Index]')
        e=self.checked(['XIC(Flag)GSV(Task,FastTask,StartTime,Selected);'],mutate=alias)
        e.memory.write('Flag',True);e.memory.write('Index',3);self.fault(e,'array/member boundary')
        e.memory.write('Index',1);e.step(25);self.assertEqual(e.memory.read('StartWords'),[101,0,0,999])

    def test_late_fault_restores_all_starts_intervals_counts_values_and_scheduling(self):
        e=self.checked(self.reads()+['DIV(1,Index,Out);']);e.memory.write('Index',1);e.step(25)
        e.memory.write('Index',0);self.fault(e,'zero');e.memory.write('Index',1);prior=e._task_scan_timings['fasttask'];e.step(25)
        self.assertEqual(e.memory.read('Stamp'),prior.start_time_us);self.assertEqual(self.word(e,'MaxWords'),prior.maximum_interval_ns//1000)

    def test_missing_utc_only_withholds_start_and_can_recover_without_interval_loss(self):
        e=self.checked(['GSV(Task,FastTask,MinimumInterval,MinWords[1]);','XIC(Flag)GSV(Task,FastTask,StartTime,Stamp);'])
        with patch('logixlab.runtime.current_value_microseconds',return_value=None):e.step(25)
        e.memory.write('Flag',True);self.fault(e,'unavailable');e.memory.write('Flag',False);e.step(25);e.memory.write('Flag',True);e.step(25)
        self.assertGreater(e.memory.read('Stamp'),0);self.assertEqual(e._task_scan_timings['fasttask'].executions,7)

    def test_interval_words_keep_unsigned_64_bit_patterns_and_independent_availability(self):
        e=self.checked(['GSV(Task,FastTask,MinimumInterval,MinWords[1]);','GSV(Task,FastTask,StartTime,Stamp);'])
        e._task_scan_timings['fasttask']=TaskMeasurements(minimum_interval_ns=((1<<63)+7)*1000,maximum_interval_ns=(1<<64)*1000,executions=2,last_start_ns=0,start_time_us=123)
        e.step(25);self.assertEqual(self.word(e,'MinWords'),(1<<63)+7);self.assertEqual(e.memory.read('Stamp'),123)
        e=self.checked(['GSV(Task,FastTask,MaximumInterval,MaxWords[1]);'])
        e._task_scan_timings['fasttask']=TaskMeasurements(maximum_interval_ns=(1<<64)*1000,executions=2,last_start_ns=0)
        self.fault(e,'unavailable')

    def test_complete_st_for_effects_protect_second_word_and_dynamic_enclosing_arrays(self):
        for destination,bound in (('MinWords[1]','MinWords[2]'),('MinWords[Index]','MinWords[0]')):
            e=self.engine([f'FOR Out:=0 TO {bound} DO GSV(Task,FastTask,MinimumInterval,{destination}); END_FOR;'],st=True)
            self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)
        e=self.checked(['FOR Out:=0 TO MinWords[0] DO GSV(Task,FastTask,MinimumInterval,MinWords[1]); END_FOR;'],st=True)
        e.step(25);self.assertEqual(e.memory.read('MinWords'),[101,0,0,999])

    def test_invalid_types_small_windows_constants_other_classes_and_setters_are_guarded(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Stamp"]').set('Constant','true')
        for logic in ('GSV(Task,FastTask,MinimumInterval,Stamp);','GSV(Task,FastTask,StartTime,Out);',
                      'GSV(Task,FastTask,StartTime,MinWords[3]);','GSV(Program,BackgroundProgram,StartTime,Stamp);',
                      'SSV(Task,FastTask,StartTime,Stamp);','GSV(Task,FastTask,MaxInterval,MinWords[1]);'):
            self.assertTrue(self.engine([logic]).blockers,logic)
        self.assertTrue(self.engine(['GSV(Task,FastTask,StartTime,Stamp);'],mutate=constant).blockers)

    def test_run_entry_and_detached_routine_replacement_preserve_independent_histories(self):
        e=self.checked(self.reads());e.step(25);before=copy.deepcopy(e._task_scan_timings);e.enter_run();self.assertEqual(e._task_scan_timings,before)
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        candidate,_=prepare(e,decode(container(E.tostring(xml_source(name='Main',text='NOP();')))),['NOP();'],'BackgroundProgram',0)
        self.assertEqual(candidate._task_scan_timings,before);self.assertIsNot(candidate._task_scan_timings,e._task_scan_timings)
        candidate.step(25);self.assertEqual(e._task_scan_timings,before)

    def test_source_drift_and_native_protocol_boundary_are_retained(self):
        e=self.checked(self.reads());e.step(25)
        self.assertEqual(e.task_scan_timing_attributes('FastTask',source_sha256='0'*64),{})
        self.assertEqual(e.task_measurement_attributes('FastTask',source_sha256=e.project.sha256),{})
        self.assertFalse(e.report()['task_scan_timing']['native_protocol_expanded'])
        self.assertIn('StartTime',e.report()['system_values']['timing']['task_attributes'])
        e.project.tasks[1]['name']='Changed';self.assertEqual(e.task_scan_timing_attributes('FastTask',source_sha256=e.project.sha256),{})
