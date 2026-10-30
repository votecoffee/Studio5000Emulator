"""Runtime SSV inhibition controls release boundaries without changing source."""
import copy
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_task_scheduler as fixtures
from logixlab.model import ModelError,Op,Project
from logixlab.runtime import Engine
from logixlab import task_inhibit


class TaskInhibitTests(unittest.TestCase):
    setUp=fixtures.TaskSchedulerTests.setUp

    def engine(self,logic='SSV(Task,Task1,InhibitTask,Control);',*,st=False,specs=None,target=None,mutate=None,defer=False):
        def change(root):
            tags=root.find('./Controller/Tags')
            for name,dtype,value in (('Control','DINT',0),('Readout','DINT',-1),('Gate','BOOL',1),('Divisor','DINT',1),('Index','DINT',0)):
                tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base')
                E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))
            if st:
                routine=root.find('./Controller/Programs/Program[@Name="Program0"]/Routines/Routine')
                routine.remove(routine.find('RLLContent'));routine.set('Type','ST');content=E.SubElement(routine,'STContent')
                for i,line in enumerate(logic.split('\n')):E.SubElement(content,'Line',Number=str(i)).text=line
            if mutate:mutate(root)
        bodies=[logic.split('\n') if not st else ['NOP();'],target or ['ADD(Count1,1,Count1);','XIC(S:FS)ADD(First1,1,First1);']]
        return fixtures.TaskSchedulerTests.engine(self,specs or [dict(Type='CONTINUOUS'),dict(Rate='10',Priority='5')],bodies,mutate=change,defer=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_continuous_controller_inhibits_and_uninhibits_periodic_task(self):
        e=self.checked();e.memory.write('Control',1);e.step(10);self.assertEqual(e.memory.read('Count1'),1)
        e.step(20);self.assertEqual(e.memory.read('Count1'),1)
        self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited'])
        e.memory.write('Control',0);e.step(10);self.assertEqual(e.memory.read('Count1'),1)
        e.step(10);self.assertEqual(e.memory.read('Count1'),2)

    def test_higher_priority_control_affects_same_time_later_release(self):
        e=self.checked(specs=[dict(Rate='10',Priority='1'),dict(Rate='10',Priority='5')]);e.memory.write('Control',1);e.step(30)
        self.assertEqual(e.memory.read('Count1'),0);e.memory.write('Control',0);e.step(10)
        self.assertEqual(e.memory.read('Count1'),1);self.assertEqual(e.memory.read('First1'),1)

    def test_mid_advance_flag_changes_filter_each_release_and_keep_phase(self):
        logic='ADD(Control,1,Control);\nSSV(Task,Task1,InhibitTask,Control);\nGEQ(Control,2)MOV(-1,Control);'
        e=self.checked(logic,specs=[dict(Rate='10',Priority='1'),dict(Rate='10',Priority='5')]);e.step(50)
        self.assertEqual(e.memory.read('Count1'),1)
        self.assertEqual([row['release_ms'] for row in e.trace if row['task']=='Task1' and row['number']=='0'],[30])
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],None)

    def test_nonzero_signed_values_inhibit_and_zero_enables(self):
        e=self.checked('SSV(Task,Task1,InhibitTask,Control);\nGSV(Task,Task1,InhibitTask,Readout);')
        for value,flag in ((-2147483648,1),(-1,1),(2147483647,1),(0,0)):
            e.memory.write('Control',value);e.step(10);self.assertEqual(e.memory.read('Readout'),flag)

    def test_gsv_and_source_bound_task_read_follow_live_flag(self):
        e=self.checked('SSV(Task,Task1,InhibitTask,Control);\nGSV(Task,Task1,InhibitTask,Readout);');e.memory.write('Control',1);e.step()
        self.assertEqual(e.memory.read('Readout'),1)
        self.assertEqual(e.task_inhibition_attributes('Task1',source_sha256=e.project.sha256),{19:struct.pack('<I',1)})
        self.assertEqual(e.task_inhibition_attributes('Task1',source_sha256='0'*64),{})
        self.assertFalse(e.project.tasks[1]['inhibited'])
        self.assertEqual(e.project.task_configuration.attributes('Task1',source_sha256=e.project.sha256)[19],bytes(4))

    def test_case_insensitive_task_attribute_and_class_names(self):
        e=self.checked('ssv(tAsK,tAsK1,iNhIbItTaSk,Control);');e.memory.write('Control',1);e.step()
        self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited'])

    def test_false_rung_does_not_read_unknown_source_or_change_flag(self):
        e=self.checked('XIC(Gate)SSV(Task,Task1,InhibitTask,Control);');e.memory.write('Gate',False);e.memory.values['control']=None;e.step()
        self.assertFalse(e.scheduler_description()['tasks'][1]['inhibited'])

    def test_st_call_skipped_branch_and_readback(self):
        e=self.checked('IF Gate THEN SSV(Task,Task1,InhibitTask,Control); END_IF;\nGSV(Task,Task1,InhibitTask,Readout);',st=True)
        e.memory.write('Control',1);e.memory.write('Gate',False);e.step();self.assertEqual(e.memory.read('Readout'),0)
        e.memory.write('Gate',True);e.step();self.assertEqual(e.memory.read('Readout'),1)

    def test_current_periodic_task_completes_after_self_inhibition(self):
        e=self.checked('SSV(Task,Task0,InhibitTask,Control);\nADD(Count0,1,Count0);',specs=[dict(Rate='10',Priority='1'),dict(Rate='10')])
        e.memory.write('Control',1);e.step(30);self.assertEqual(e.memory.read('Count0'),1)
        self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],1)

    def test_periodic_task_can_disable_continuous_task_before_end_of_advance(self):
        e=self.checked('ADD(Count0,1,Count0);',target=['SSV(Task,Task0,InhibitTask,Control);'],specs=[dict(Type='CONTINUOUS'),dict(Rate='10')])
        e.memory.write('Control',1);e.step(20);self.assertEqual(e.memory.read('Count0'),0)
        e.memory.write('Control',0);e.step(10);self.assertEqual(e.memory.read('Count0'),1)

    def test_initially_inhibited_task_is_prescanned_and_can_be_enabled(self):
        def initial(root):root.find('./Controller/Tags/Tag[@Name="StartDelay"]/Data/Structure/DataValueMember[@Name="ACC"]').set('Value','123')
        e=self.checked(specs=[dict(Type='CONTINUOUS'),dict(InhibitTask='true')],target=['TON(StartDelay,?,?);','XIC(S:FS)ADD(First1,1,First1);'],mutate=initial)
        self.assertEqual(e.memory.read('StartDelay.ACC'),0);e.step(10)
        self.assertEqual(e.memory.read('First1'),0);e.step(10);self.assertEqual(e.memory.read('First1'),1)

    def test_periodic_phase_advances_during_inhibition_without_catchup(self):
        e=self.checked();e.memory.write('Control',1);e.step(10);e.step(27);e.memory.write('Control',0);e.step(1)
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],40)
        e.step(2);self.assertEqual(e.memory.read('Count1'),2)

    def test_run_entry_retains_inhibition_and_restarts_phase(self):
        e=self.checked();e.memory.write('Control',1);e.step(10);e.enter_run()
        self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited']);e.memory.write('Control',0);e.step(5)
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],20)
        e.step(5);self.assertEqual(e.memory.read('Count1'),2)

    def test_fresh_project_engine_restores_source_flag(self):
        e=self.checked();e.memory.write('Control',1);e.step();fresh=Engine(e.project)
        self.assertFalse(fresh.scheduler_description()['tasks'][1]['inhibited'])

    def test_unknown_source_rolls_back_prior_writes_and_task_progress(self):
        e=self.checked('MOV(7,Count0);\nSSV(Task,Task1,InhibitTask,Control);');e.memory.values['control']=None
        before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaises(ModelError):e.step(20)
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)

    def test_late_fault_rolls_back_flags_values_first_scans_and_release_phase(self):
        e=self.checked('SSV(Task,Task1,InhibitTask,Control);\nDIV(1,Divisor,Count0);');e.memory.write('Control',1);e.memory.write('Divisor',0)
        before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'zero'):e.step(25)
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        e.memory.write('Divisor',1);e.step(25);self.assertEqual(e.memory.read('Count1'),2)
        self.assertEqual(e.memory.read('First1'),1);self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited'])

    def test_fault_after_mid_advance_inhibition_restores_earlier_target_runs(self):
        e=self.checked('SSV(Task,Task1,InhibitTask,Control);\nDIV(1,Divisor,Count0);',specs=[dict(Rate='10',Priority='1'),dict(Rate='10')])
        e.memory.write('Control',1);e.memory.write('Divisor',0);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaises(ModelError):e.step(30)
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)

    def test_alias_member_and_indirect_array_sources(self):
        def add(root):
            tags=root.find('./Controller/Tags');E.SubElement(tags,'Tag',Name='AliasControl',TagType='Alias',DataType='DINT',AliasFor='Control')
            tag=E.SubElement(tags,'Tag',Name='Controls',TagType='Base',DataType='DINT',Dimensions='2')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(i))
        for source in ('AliasControl','StartDelay.PRE','Controls[Index]'):
            e=self.checked(f'SSV(Task,Task1,InhibitTask,{source});',mutate=add)
            e.memory.write('Control',1);e.memory.write('StartDelay.PRE',1);e.memory.write('Index',1);e.step()
            self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited'])

    def test_indirect_source_bounds_fault_rolls_back_inhibition(self):
        # A dynamic array reference is structurally checked without consuming its live index.
        def array(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Controls',TagType='Base',DataType='DINT',Dimensions='1')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='1');E.SubElement(arr,'Element',Index='[0]',Value='0')
        e=self.checked('SSV(Task,Task1,InhibitTask,Control);\nSSV(Task,Task1,InhibitTask,Controls[Index]);',mutate=array)
        e.memory.write('Control',1);e.memory.write('Index',2);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)

    def test_wrong_classes_attributes_names_and_source_types_block(self):
        for text in ('SSV(Controller,,InhibitTask,Control);','SSV(Task,Task1,Rate,Control);','SSV(Task,,InhibitTask,Control);',
                     'SSV(Task,Missing,InhibitTask,Control);','SSV(Task,THIS,InhibitTask,Control);','SSV(Task,Task1,InhibitTask,1);',
                     'SSV(Task,Task1,InhibitTask,Gate);','SSV(Task,Task1,InhibitTask,Control.0);'):
            self.assertTrue(self.engine(text).blockers,text)

    def test_profile_and_missing_explicit_flag_are_blocked(self):
        for change in ('revision','processor','inhibit'):
            def mutate(root):
                if change=='revision':root.find('Controller').set('MajorRev','34')
                elif change=='processor':root.find('Controller').set('ProcessorType','1756-L75')
                else:root.find('./Controller/Tasks/Task[2]').attrib.pop('InhibitTask')
            self.assertTrue(self.engine(mutate=mutate).blockers,change)

    def test_routine_harness_and_aoi_context_remain_blocked(self):
        e=self.checked();self.assertTrue(Engine(e.project,'routine','Program0/Main').blockers)
        e.memory.frames['frame']={}
        with self.assertRaisesRegex(ModelError,'AOI'):task_inhibit.validate(e,Op('SSV',['Task','Task1','InhibitTask','Control']),'frame')

    def test_ssv_inside_bounded_st_for_completes_loop(self):
        e=self.checked('FOR Index:=0 TO 1 DO SSV(Task,Task1,InhibitTask,Control); END_FOR;',st=True)
        e.memory.write('Control',1);e.step();self.assertEqual(e.memory.read('Index'),2)
        self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited'])

    def test_detached_scheduler_continuation_retains_live_flags(self):
        e=self.checked();e.memory.write('Control',1);e.step();candidate=Engine(e.project)
        candidate._task_scheduler.continue_from(e._task_scheduler)
        self.assertEqual(candidate.scheduler_description(),e.scheduler_description())
        candidate._task_scheduler.inhibitions[1]=False;self.assertTrue(e._task_scheduler.inhibitions[1])

    def test_source_configuration_mutation_remains_blocked(self):
        e=self.checked();e.project.tasks[1]['inhibited']=True
        with self.assertRaisesRegex(ModelError,'configuration changed'):e.step()

    def test_report_discloses_scope_phase_and_release_budget(self):
        e=self.checked();profile=e.report()['system_values']['task_inhibition']
        self.assertFalse(profile['native_runtime_parity']);self.assertIn('without catch-up',profile['phase'])
        self.assertIn('potential release',e.scheduler_description()['release_budget'])

    def test_constant_dint_source_and_program_local_shadow_are_readable(self):
        def local(root):
            tags=root.find('./Controller/Programs/Program[@Name="Program0"]/Tags')
            tag=E.SubElement(tags,'Tag',Name='Control',TagType='Base',DataType='DINT',Constant='true')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='-1')
        e=self.checked(mutate=local);e.step();self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited'])
        self.assertEqual(e.memory.read('Control'),0)

    def test_ssv_has_no_prescan_side_effect_even_when_source_is_nonzero(self):
        e=self.checked(defer=True);e.memory.write('Control',1);e.enter_run()
        self.assertFalse(e.scheduler_description()['tasks'][1]['inhibited']);e.step()
        self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited'])

    def test_first_scan_is_not_reasserted_on_uninhibit(self):
        e=self.checked();e.memory.write('Control',1);e.step(10);e.step(10);e.memory.write('Control',0);e.step(10);e.step(10)
        self.assertEqual(e.memory.read('Count1'),2);self.assertEqual(e.memory.read('First1'),1)

    def test_real_routine_replacement_retains_flags_without_sharing_mutable_state(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        text='SSV(Task,Task1,InhibitTask,Control);';e=self.checked(text);e.memory.write('Control',1);e.step()
        source=decode(container(E.tostring(xml_source(name='Main',text=text),encoding='utf-8')))
        candidate,_=prepare(e,source,(text,),'Program0',0)
        self.assertEqual(candidate.scheduler_description(),e.scheduler_description())
        candidate.memory.write('Control',0);candidate.step();candidate.step()
        self.assertFalse(candidate.scheduler_description()['tasks'][1]['inhibited'])
        self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited'])

    def test_event_target_remains_blocked(self):
        def event(root):
            task=root.find('./Controller/Tasks/Task[2]');task.set('Type','EVENT')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
        self.assertTrue(self.engine(mutate=event).blockers)

    def test_all_inhibited_slots_still_obey_bounded_release_budget(self):
        e=self.checked(specs=[dict(Type='CONTINUOUS'),dict(Rate='1',InhibitTask='true')])
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'release budget'):e.step(60000)
        self.assertEqual(e.memory.values,before)

    def test_system_lab_independent_controls_and_late_fault_recovery(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/SystemLab.L5X'));self.assertEqual(e.blockers,[]);e.step(25)
        self.assertEqual((e.memory.read('FastCount'),e.memory.read('SlowCount')),(2,1))
        for name,value in (('ControlTasks',True),('StApplyInhibit',True),('TaskInhibitCommand',1),('StTaskInhibitCommand',1)):e.memory.write(name,value)
        e.step(25);e.step(25);self.assertEqual((e.memory.read('FastCount'),e.memory.read('SlowCount')),(5,2))
        self.assertEqual((e.memory.read('LiveFastInhibit'),e.memory.read('StSlowInhibit')),(1,1))
        e.memory.write('TaskInhibitCommand',0);e.memory.write('StTaskInhibitCommand',0);e.step(10);e.step(15)
        self.assertEqual((e.memory.read('FastCount'),e.memory.read('SlowCount')),(7,3))
        e.memory.write('ControlDivisor',0);e.memory.write('TaskInhibitCommand',1);e.memory.write('StTaskInhibitCommand',1)
        before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'zero'):e.step(25)
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        e.memory.write('ControlDivisor',1);e.step(25)
        self.assertEqual((e.memory.read('FastCount'),e.memory.read('SlowCount')),(9,4))
        self.assertEqual((e.memory.read('LiveFastInhibit'),e.memory.read('StSlowInhibit')),(1,1))

    def test_other_numeric_source_widths_are_not_implicitly_converted(self):
        for dtype in ('SINT','INT','LINT','UDINT','REAL'):
            def mutate(root):
                tag=root.find('./Controller/Tags/Tag[@Name="Control"]');tag.set('DataType',dtype)
                tag.find('Data/DataValue').set('DataType',dtype)
            self.assertTrue(self.engine(mutate=mutate).blockers,dtype)

    def test_event_caller_can_inhibit_periodic_target_after_current_body(self):
        def event(root):
            task=root.find('./Controller/Tasks/Task[1]');task.set('Type','EVENT');task.set('Priority','1')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
        e=self.checked(target=['EVENT(Task0);','ADD(Count1,1,Count1);'],mutate=event)
        e.memory.write('Control',1);e.step(30)
        self.assertEqual(e.memory.read('Count1'),1);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],1)


if __name__=='__main__':unittest.main()
