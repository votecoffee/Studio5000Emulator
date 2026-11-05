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
            for name,dtype,value in (('Control','DINT',0),('Readout','DINT',-1),('Gate','BOOL',1),('Divisor','DINT',1),('Index','DINT',0),('PrioIn','INT',1),('PrioOut','INT',-1)):
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
        for text in ('SSV(Controller,,InhibitTask,Control);','SSV(Task,Task0,Rate,Control);','SSV(Task,,InhibitTask,Control);',
                     'SSV(Task,Missing,InhibitTask,Control);','SSV(Task,0,InhibitTask,Control);','SSV(Task,Task1,InhibitTask,1);',
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

    def test_event_target_can_be_inhibited_without_running_it(self):
        def event(root):
            task=root.find('./Controller/Tasks/Task[2]');task.set('Type','EVENT')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
        e=self.checked(mutate=event);e.memory.write('Control',1);e.step();self.assertTrue(e.scheduler_description()['tasks'][1]['inhibited']);self.assertEqual(e.memory.read('Count1'),0)

    def test_all_inhibited_slots_still_obey_bounded_release_budget(self):
        e=self.checked(specs=[dict(Type='CONTINUOUS'),dict(Rate='1',InhibitTask='true')])
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'release budget'):e.step(60000)
        self.assertEqual(e.memory.values,before)

    def test_rate_write_rephases_only_after_batch_and_keeps_unchanged_phase(self):
        e=self.checked('XIC(Gate)SSV(Task,Task1,Rate,Control);\nGSV(Task,Task1,Rate,Readout);',
                       specs=[dict(Priority='1'),dict(Priority='5')])
        e.memory.write('Control',20000);e.step(35)
        task=e.scheduler_description()['tasks'][1]
        self.assertEqual((task['rate_ms'],task['source_rate_ms'],task['next_release_ms']),(20,10,55))
        self.assertEqual((e.memory.read('Readout'),e.memory.read('Count1')),(20000,3))
        e.step(20);e.step(20)
        self.assertEqual(e.memory.read('Count1'),5)
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],95)

    def test_staged_rate_is_visible_to_ladder_and_st_and_net_no_change_keeps_phase(self):
        logic=('SSV(Task,Task1,Rate,Control);\nGSV(Task,Task1,Rate,Readout);\n'
               'Control := 10000;\nSSV(Task,Task1,Rate,Control);')
        e=self.checked(logic,st=True,target=['GSV(Task,Task1,Rate,Count1);'])
        e.memory.write('Control',17000);e.step(15)
        self.assertEqual((e.memory.read('Readout'),e.memory.read('Count1')),(17000,10000))
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],20)
        self.assertEqual(e.project.task_timing.attributes('Task1',source_sha256=e.project.sha256)[2],struct.pack('<I',10000))

    def test_bad_rate_and_later_fault_roll_back_rates_phase_and_progress(self):
        e=self.checked('XIC(Gate)SSV(Task,Task1,Rate,Control);\nGSV(Task,Task1,Rate,Readout);\nDIV(1,Divisor,Count0);')
        e.memory.write('Gate',False);e.step(17)
        e.memory.write('Gate',True)
        before=copy.deepcopy(e.scheduler_description())
        for rate,divisor,expected in ((999,1,'whole milliseconds'),(-1000,1,'whole milliseconds'),
                                      (60001000,1,'whole milliseconds'),(0,1,'whole milliseconds'),(25000,0,'zero')):
            e.memory.write('Control',rate);e.memory.write('Divisor',divisor);values=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,expected):e.step(10)
            self.assertEqual(e.scheduler_description(),before)
            self.assertEqual(e.memory.values,values)
        e.memory.write('Divisor',1);e.step(10)
        self.assertEqual((e.memory.read('Count1'),e.memory.read('Readout')),(2,25000))
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],52)

    def test_periodic_this_retains_rate_on_run_entry_and_detached_replacement(self):
        def explicit(root):
            root.find('./Controller/Programs/Program').attrib.update(UseAsFolder='false',Disabled='false')
        logic='SSV(Task,THIS,Rate,Control);'
        e=self.checked(logic,specs=[dict(Rate='10')],mutate=explicit)
        e.memory.write('Control',15000);e.step(10);e.enter_run()
        self.assertEqual(e.fixed_scan_interval(),15)
        self.assertEqual(e.scheduler_description()['tasks'][0]['next_release_ms'],25)
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        source=decode(container(E.tostring(xml_source(name='Main',text=logic),encoding='utf-8')))
        candidate,_=prepare(e,source,(logic,),'Program0',0)
        candidate.memory.write('Control',30000);candidate.step(15)
        self.assertEqual((candidate.fixed_scan_interval(),e.fixed_scan_interval(),Engine(e.project).fixed_scan_interval()),(30,15,10))

    def test_single_periodic_app_steps_runs_and_resets_at_effective_rate(self):
        import base64
        from logixlab.server import Application
        from test_controller_mode import wait_for
        e=self.checked('SSV(Task,Task0,Rate,Control);\nADD(Count0,1,Count0);',specs=[dict(Rate='10')])
        app=Application(self.tmp.name);self.addCleanup(app.close)
        app.command('load',{'name':'Rate.L5X','content':base64.b64encode(e.project.path.read_bytes()).decode()})
        app.command('write',{'tag':'Control','value':20000})
        state=app.command('step',{'count':3})
        self.assertEqual((state['scan'],state['ms'],state['controller']['scan_interval_ms']),(3,50,20))
        with self.assertRaisesRegex(ModelError,'20 ms'):app.command('step',{'dt':10})
        app.command('write',{'tag':'Control','value':15000})
        app.command('controller-mode',{'mode':'Run'})
        wait_for(lambda:app.engine.scan_count>=6)
        state=app.command('controller-mode',{'mode':'Program'})
        self.assertFalse(state['fault'])
        self.assertEqual(state['controller']['scan_interval_ms'],15)
        self.assertEqual(state['ms'],70+(state['scan']-4)*15)
        state=app.command('reset',{})
        self.assertEqual(state['controller']['scan_interval_ms'],10)

    def test_priority_updates_coincident_releases_on_next_advance_without_rephase(self):
        e=self.checked('XIC(Gate)SSV(Task,Task1,Priority,PrioIn);\nGSV(Task,Task1,Priority,PrioOut);',
                       specs=[dict(Priority='5'),dict(Priority='8')],target=['NOP();'])
        e.step(20)
        trace=lambda:[row['task'] for row in e.trace if row['number']=='0']
        self.assertEqual(trace(),['Task0','Task1']*2)
        self.assertEqual(e.memory.read('PrioOut'),1)
        task=e.scheduler_description()['tasks'][1]
        self.assertEqual((task['priority'],task['source_priority'],task['next_release_ms']),(1,8,30))
        e.memory.write('PrioIn',5);e.step(10)
        self.assertEqual(trace(),['Task1','Task0'])
        e.memory.write('Gate',False);e.step(10)
        self.assertEqual(trace(),['Task0','Task1'])

    def test_priority_fault_restores_staged_priority_rate_and_values(self):
        e=self.checked('XIC(Gate)SSV(Task,Task1,Priority,PrioIn);\nXIC(Gate)SSV(Task,Task1,Rate,Control);\n'
                       'GSV(Task,Task1,Priority,PrioOut);\nDIV(1,Divisor,Count0);')
        e.memory.write('Gate',False);e.step()
        schedule=e.scheduler_description()
        e.memory.write('Gate',True);e.memory.write('Control',20000)
        for priority,divisor,pattern in ((0,1,r'INT in 1\.\.15'),(16,1,r'INT in 1\.\.15'),(15,0,'zero')):
            e.memory.write('PrioIn',priority);e.memory.write('Divisor',divisor)
            before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,pattern):e.step()
            self.assertEqual(e.scheduler_description(),schedule)
            self.assertEqual(e.memory.values,before)
        e.memory.write('Divisor',1);e.step()
        self.assertEqual(e.memory.read('PrioOut'),15)
        task=e.scheduler_description()['tasks'][1]
        self.assertEqual((task['priority'],task['rate_ms'],task['next_release_ms']),(15,20,40))

    def test_priority_requires_exact_int_tag_and_explicit_eligible_target(self):
        for text in ('AFI()SSV(Task,Task1,Priority,Control);','AFI()SSV(Task,Task1,Priority,1);',
                     'AFI()SSV(Task,Task1,Priority,PrioIn.0);','AFI()SSV(Task,Task0,Priority,PrioIn);'):
            self.assertTrue(self.engine(text).blockers,text)
        e=self.checked('XIC(Gate)SSV(Task,Task1,Priority,PrioIn);',defer=True)
        e.enter_run();e.memory.write('Gate',False);e.memory.values['prioin']=None
        e.step();self.assertEqual(e.scheduler_description()['tasks'][1]['priority'],5)

    def test_st_this_priority_persists_on_run_and_detached_replacement(self):
        def explicit(root):
            root.find('./Controller/Programs/Program').attrib.update(UseAsFolder='false',Disabled='false')
        e=self.checked('SSV(Task,THIS,Priority,PrioIn); GSV(Task,THIS,Priority,PrioOut);',
                       st=True,specs=[dict(Priority='5'),dict(Priority='8')],target=['NOP();'],mutate=explicit)
        e.step();e.enter_run()
        self.assertEqual((e.memory.read('PrioOut'),e.scheduler_description()['tasks'][0]['priority']),(1,1))
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        source=decode(container(E.tostring(xml_source(name='Main',text='NOP();'),encoding='utf-8')))
        candidate,_=prepare(e,source,('NOP();',),'Program1',0)
        candidate.memory.write('PrioIn',4);candidate.step()
        self.assertEqual(candidate.scheduler_description()['tasks'][0]['priority'],4)
        self.assertEqual(e.scheduler_description()['tasks'][0]['priority'],1)
        self.assertEqual(Engine(e.project).scheduler_description()['tasks'][0]['priority'],5)

    @staticmethod
    def explicit_watchdogs(root):
        for task in root.findall('./Controller/Tasks/Task'):task.set('Watchdog','125.001')
        for program in root.findall('./Controller/Programs/Program'):
            program.attrib.update(UseAsFolder='false',Disabled='false')

    def test_watchdog_writes_keep_exact_microseconds_and_use_task_specific_zero_defaults(self):
        for name,default in (('Task0',5000000),('Task1',500000)):
            e=self.checked(f'SSV(Task,{name},Watchdog,Control);\nGSV(Task,{name},Watchdog,Readout);',
                           mutate=self.explicit_watchdogs)
            for source,expected in ((1000,1000),(1001,1001),(2000000000,2000000000),(0,default)):
                e.memory.write('Control',source);e.step()
                self.assertEqual(e.memory.read('Readout'),expected)
                self.assertEqual(e.memory.read('Control'),source)
            row=next(row for row in e.scheduler_description()['tasks'] if row['name']==name)
            self.assertEqual(row['watchdog_override_us'],default)
            self.assertEqual(e.project.task_timing.attributes(name,source_sha256=e.project.sha256)[12],struct.pack('<I',125001))
            self.assertFalse(e.scheduler_description()['watchdog_enforced'])

    def test_watchdog_range_and_late_failure_roll_back_override_and_progress(self):
        logic='XIC(Gate)SSV(Task,Task1,Watchdog,Control);\nGSV(Task,Task1,Watchdog,Readout);\nDIV(1,Divisor,Count0);'
        e=self.checked(logic,mutate=self.explicit_watchdogs,defer=True)
        e.enter_run();e.memory.write('Gate',False);e.memory.values['control']=None;e.step()
        self.assertEqual(e.memory.read('Readout'),125001)
        self.assertEqual(e._task_scheduler.watchdog_overrides,{})
        e.memory.write('Gate',True);e.memory.write('Control',1001);e.step()
        schedule=e.scheduler_description()
        for value,divisor,pattern in ((-1,1,'DINT microseconds'),(999,1,'DINT microseconds'),
                                      (2000000001,1,'DINT microseconds'),(150001,0,'zero')):
            e.memory.write('Control',value);e.memory.write('Divisor',divisor)
            before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,pattern):e.step()
            self.assertEqual(e.memory.values,before)
            self.assertEqual(e.scheduler_description(),schedule)
        e.memory.write('Divisor',1);e.step()
        self.assertEqual(e.memory.read('Readout'),150001)

    def test_st_this_watchdog_survives_run_and_detached_replacement_and_fresh_load_restores_source(self):
        logic='SSV(Task,THIS,Watchdog,Control); GSV(Task,THIS,Watchdog,Readout);'
        e=self.checked(logic,st=True,mutate=self.explicit_watchdogs)
        e.memory.write('Control',12345);e.step();e.enter_run()
        self.assertEqual(e._task_scheduler.watchdog_overrides,{0:12345})
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        source=decode(container(E.tostring(xml_source(name='Main',text='NOP();'),encoding='utf-8')))
        candidate,_=prepare(e,source,('NOP();',),'Program1',0)
        candidate.memory.write('Control',2001);candidate.step()
        self.assertEqual((e.memory.read('Readout'),candidate.memory.read('Readout')),(12345,2001))
        self.assertEqual(e._task_scheduler.watchdog_overrides,{0:12345})
        self.assertEqual(Engine(e.project)._task_scheduler.watchdog_overrides,{})

    def test_watchdog_requires_explicit_eligible_source_and_exact_dint(self):
        for operand in ('Gate','PrioIn','Control.0','1000'):
            self.assertTrue(self.engine(f'AFI()SSV(Task,Task1,Watchdog,{operand});',
                                        mutate=self.explicit_watchdogs).blockers)
        for raw in (None,'0','bad'):
            def invalid(root):
                self.explicit_watchdogs(root)
                task=root.find('./Controller/Tasks/Task[2]')
                if raw is None:task.attrib.pop('Watchdog')
                else:task.set('Watchdog',raw)
            self.assertTrue(self.engine('AFI()SSV(Task,Task1,Watchdog,Control);',mutate=invalid).blockers)

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
