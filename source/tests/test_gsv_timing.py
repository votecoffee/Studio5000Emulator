"""Committed Program/Task GSV measurements, source eligibility and rollback."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_aoi_queues as aoi
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine
from logixlab.program_timing import ProgramTiming
from logixlab.task_runtime import TaskMeasurements

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


class GsvTimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,logic,*,st=False,mutate=None,mode='project'):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        for name,dtype,value in [('ProgramLast','DINT',91),('ProgramMax','DINT',92),('TaskLast','DINT',93),('TaskMax','DINT',94),('ReadTiming','BOOL',0),('Index','DINT',99),('Limit','DINT',2),('Divisor','DINT',1)]:
            tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))
        for name,values in [('Words',[77]*6),('UnknownWords',[])]:
            tag=E.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Base',Dimensions='6');array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='6')
            for i,value in enumerate(values):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
        routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.clear();routine.attrib.update(Name='MainRoutine',Type='ST' if st else 'RLL')
        content=E.SubElement(routine,'STContent' if st else 'RLLContent')
        for i,text in enumerate(logic):
            if st:E.SubElement(content,'Line',Number=str(i)).text=text
            else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'timing.L5X';E.ElementTree(root).write(path,encoding='utf8',xml_declaration=True)
        return Engine(Project(path),mode=mode,routine='MainProgram/MainRoutine')

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    @staticmethod
    def reads(gate=''):
        return [gate+f'GSV({cls},{name},{attribute},{dest});' for cls,name,attribute,dest in
                [('Program','MainProgram','LastScanTime','ProgramLast'),('PROGRAM','mainprogram','MAXSCANTIME','ProgramMax'),
                 ('Task','MainTask','LastScanTime','TaskLast'),('TASK','maintask','MaxScanTime','TaskMax')]]

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.scan_count,e.time_ms,e.trace,
                              e.scheduler_description(),e.last_timer,e._program_timings,e._task_measurements))

    def fault(self,e,expected):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,expected):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_first_scan_reads_initialized_zero_then_previous_committed_durations(self):
        with patch.object(Engine,'program_timing_attributes',side_effect=AssertionError('Planning read')),patch.object(Engine,'task_measurement_attributes',side_effect=AssertionError('Planning read')):
            e=self.checked(self.reads())
        with patch('logixlab.runtime.perf_counter_ns',side_effect=(100,5100,10000,13000,20000,22000)),patch('logixlab.task_runtime.perf_counter_ns',side_effect=(0,8000,9000,16000,17000,24000)):
            e.step();self.assertEqual([e.memory.read(n) for n in ('ProgramLast','ProgramMax','TaskLast','TaskMax')],[0,0,0,0])
            e.step();self.assertEqual([e.memory.read(n) for n in ('ProgramLast','ProgramMax','TaskLast','TaskMax')],[5,5,8,8])
            e.step();self.assertEqual([e.memory.read(n) for n in ('ProgramLast','ProgramMax','TaskLast','TaskMax')],[3,5,7,8])
        self.assertEqual(e._program_timings['mainprogram'].last_ns,2000)

    def test_prescan_and_false_paths_do_not_read_measurements_or_live_indices(self):
        for st,logic in [(False,['XIC(ReadTiming)GSV(Task,MainTask,LastScanTime,Words[Index]);']),
                         (True,['IF ReadTiming THEN GSV(Program,MainProgram,MaxScanTime,Words[Index]); END_IF;'])]:
            e=self.checked(logic,st=st)
            with patch.object(e,'program_timing_attributes',side_effect=AssertionError('Unused read')),patch.object(e,'task_measurement_attributes',side_effect=AssertionError('Unused read')):
                e.enter_run();e.step();self.assertEqual(e.memory.read('Words'),[77]*6)
                e.memory.write('ReadTiming',True);self.fault(e,'outside bounds')
            e.memory.write('Index',2);e.step();self.assertGreaterEqual(e.memory.read('Words[2]'),0)

    def test_complete_unknown_outputs_and_alias_elements_can_be_established(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='OutputAlias',DataType='DINT',TagType='Alias',AliasFor='UnknownWords[Index]')
        e=self.checked(['GSV(Program,MainProgram,LastScanTime,UnknownWords[1]);','GSV(Task,MainTask,MaxScanTime,OutputAlias);'],mutate=alias)
        e.memory.write('Index',3);e.step();self.assertEqual(e.memory.values['unknownwords'],[None,0,None,0,None,None])

    def test_later_fault_keeps_values_and_measurements_then_recovery_reads_prior_commit(self):
        e=self.checked(self.reads()+['DIV(1,Divisor,SpeedCommand);']);e.step();prior=e._program_timings['mainprogram'];task=e._task_measurements
        e.memory.write('Divisor',0);self.fault(e,'zero');e.memory.write('Divisor',1);e.step()
        self.assertEqual(e.memory.read('ProgramLast'),prior.last_ns//1000);self.assertEqual(e.memory.read('TaskLast'),task.last_ns//1000)

    def test_same_protocol_word_bits_and_unavailable_counter_widths(self):
        e=self.checked(self.reads());e._program_timings['mainprogram']=ProgramTiming(0x80000000*1000,0xffffffff*1000,1)
        e._task_measurements=TaskMeasurements(0x80000000*1000,0xffffffff*1000,executions=1,last_start_ns=0)
        e.step();self.assertEqual([e.memory.read(n) for n in ('ProgramLast','ProgramMax','TaskLast','TaskMax')],[-2147483648,-1,-2147483648,-1])
        e._program_timings['mainprogram']=ProgramTiming(0x100000000*1000,0x100000000*1000,1)
        self.fault(e,'unavailable')
        e=self.checked(['GSV(Task,MainTask,LastScanTime,TaskLast);']);e._task_measurements=TaskMeasurements(1000,0x100000000*1000,executions=1,last_start_ns=0)
        e.step();self.assertEqual(e.memory.read('TaskLast'),1)
        e=self.checked(['GSV(Task,MainTask,MaxScanTime,TaskMax);']);e._task_measurements=TaskMeasurements(1000,0x100000000*1000,executions=1,last_start_ns=0)
        self.fault(e,'unavailable')

    def test_named_programs_use_independent_scheduled_counters(self):
        def worker(root):
            programs=root.find('./Controller/Programs');other=copy.deepcopy(programs[0]);other.set('Name','Worker')
            for text in other.findall('.//RLLContent/Rung/Text'):text.text='NOP();'
            programs.append(other);E.SubElement(root.find('./Controller/Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='Worker')
        e=self.checked(['GSV(Program,Worker,LastScanTime,ProgramLast);','GSV(Program,MainProgram,MaxScanTime,ProgramMax);'],mutate=worker)
        with patch('logixlab.runtime.perf_counter_ns',side_effect=(0,3000,10000,17000,20000,22000,23000,24000)):
            e.step();e.step()
        self.assertEqual(e.memory.read('ProgramLast'),7);self.assertEqual(e.memory.read('ProgramMax'),3)

    def test_multitask_program_reads_work_while_whole_task_reads_stay_guarded(self):
        def tasks(root):
            tasks=root.find('./Controller/Tasks');other=copy.deepcopy(tasks[0]);other.attrib.update(Name='OtherTask',Type='Periodic',Rate='20',Priority='5');other.find('ScheduledPrograms').clear();tasks.append(other)
        e=self.checked(['GSV(Program,MainProgram,LastScanTime,ProgramLast);'],mutate=tasks);e.step();e.step();self.assertGreaterEqual(e.memory.read('ProgramLast'),0)
        self.assertTrue(self.engine(['AFI()GSV(Task,MainTask,LastScanTime,TaskLast);'],mutate=tasks).blockers)

    def test_zero_initialized_scheduled_program_without_main_is_available(self):
        def empty(root):
            program=E.SubElement(root.find('./Controller/Programs'),'Program',Name='NoMain',Class='Standard',TestEdits='false',UseAsFolder='false',Disabled='false',MainRoutineName='',FaultRoutineName='');E.SubElement(program,'Tags');E.SubElement(program,'Routines')
            E.SubElement(root.find('./Controller/Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='NoMain')
        e=self.checked(['GSV(Program,NoMain,LastScanTime,ProgramLast);','GSV(Program,NoMain,MaxScanTime,ProgramMax);'],mutate=empty);e.step()
        self.assertEqual((e.memory.read('ProgramLast'),e.memory.read('ProgramMax')),(0,0))
        def malformed(root):
            empty(root);root.find('./Controller/Programs/Program[@Name="NoMain"]').attrib.pop('UseAsFolder')
        self.assertTrue(self.engine(['GSV(Program,NoMain,LastScanTime,ProgramLast);'],mutate=malformed).blockers)

    def test_source_drift_withholds_measurements_but_disk_changes_are_not_reload(self):
        e=self.checked(self.reads());e.project.path.write_bytes(e.project.path.read_bytes()+b'\n');e.step()
        e.project.sha256='0'*64;self.fault(e,'requires')

    def test_bad_names_types_permissions_modes_and_incomplete_task_settings_remain_blocked(self):
        for cls,name in [('Task',''),('Task','Missing'),('Program',''),('Program','Missing')]:
            self.assertTrue(self.engine([f'GSV({cls},{name},LastScanTime,ProgramLast);']).blockers,(cls,name))
        for dest in ('StartPB','StartDelay','Words','ProgramLast.0'):
            self.assertTrue(self.engine([f'GSV(Task,MainTask,LastScanTime,{dest});']).blockers,dest)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="ProgramLast"]').set('Constant','true')
        self.assertTrue(self.engine(['GSV(Program,MainProgram,LastScanTime,ProgramLast);'],mutate=constant).blockers)
        self.assertTrue(self.engine(self.reads(),mode='routine').blockers)
        for field in ('Priority','DisableUpdateOutputs','InhibitTask'):
            def missing(root):root.find('./Controller/Tasks/Task').attrib.pop(field)
            self.assertTrue(self.engine(['GSV(Task,MainTask,LastScanTime,TaskLast);'],mutate=missing).blockers,field)
        for processor,major in [('1756-L75','35'),('1756-L85E','34')]:
            def target(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',major)
            self.assertTrue(self.engine(self.reads(),mutate=target).blockers)
        self.assertTrue(self.engine(['SSV(Task,MainTask,LastScanTime,TaskLast);']).blockers)

    def test_disabled_unscheduled_and_folder_program_sources_are_not_fabricated(self):
        for mode in ('disabled','unscheduled','folder'):
            def worker(root):
                program=E.SubElement(root.find('./Controller/Programs'),'Program',Name='Worker',Class='Standard',MainRoutineName='Main')
                if mode=='disabled':program.set('Disabled','true')
                elif mode=='folder':program.set('UseAsFolder','true')
                E.SubElement(program,'Tags');routine=E.SubElement(E.SubElement(program,'Routines'),'Routine',Name='Main',Type='RLL')
                E.SubElement(E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='NOP();'
                if mode=='disabled':E.SubElement(root.find('./Controller/Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='Worker')
            self.assertTrue(self.engine(['GSV(Program,Worker,LastScanTime,ProgramLast);'],mutate=worker).blockers,mode)

    def test_st_loop_effects_protect_dynamic_aliases_and_allow_static_disjoint_cells(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='OutputAlias',DataType='DINT',TagType='Alias',AliasFor='Words[Index]')
        for dest,bound in [('Words[1]','Words[1]'),('Words[Index]','Words[5]'),('OutputAlias','Words[5]')]:
            e=self.engine([f'FOR Limit:=0 TO {bound} DO GSV(Program,MainProgram,LastScanTime,{dest}); END_FOR;'],st=True,mutate=alias)
            self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)
        e=self.checked(['FOR Index:=0 TO Limit DO GSV(Task,MainTask,LastScanTime,Words[1]); END_FOR;'],st=True);e.step()
        self.assertEqual(e.memory.read('Index'),3);self.assertEqual(e.memory.read('Words'),[77,0,77,77,77,77])

    @staticmethod
    def timing_aoi(root):
        aoi.logic(root,['XIC(Load)GSV(Program,MainProgram,LastScanTime,Buffer[Index]);',
                        'XIC(Push)GSV(Task,MainTask,MaxScanTime,Stack[1]);'])

    def test_typed_aoi_inout_and_local_outputs_roll_back_with_later_fault(self):
        e=aoi.AOIQueueTests.engine(self,self.timing_aoi);self.assertEqual(e.blockers,[]);e.step();prior=e._program_timings['mainprogram'];task=e._task_measurements
        for tag,value in [('Load',True),('Push',True),('FaultDivisor',0)]:e.memory.write(tag,value)
        self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual(e.memory.read('BufferA[1]'),prior.last_ns//1000);self.assertEqual(e.memory.read('BufferB[2]'),prior.last_ns//1000)
        self.assertEqual(e.memory.read('DriverA.Stack[1]'),task.maximum_ns//1000);self.assertEqual(e.memory.read('BufferA[0]'),101)

    def test_report_separates_interpreter_measurements_from_controller_prediction(self):
        e=self.checked(['NOP();']);report=e.report()['system_values']['timing']
        self.assertIn('preceding committed',report['visibility']);self.assertIn('perf_counter_ns',report['source'])
        self.assertFalse(report['native_runtime_parity']);self.assertFalse(report['controller_performance_prediction'])
