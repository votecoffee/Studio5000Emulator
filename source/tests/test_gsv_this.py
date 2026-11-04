"""Source-bound THIS selection in ordinary scheduled ladder/ST Program routines."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_gsv_configuration as config
import test_gsv_timing as timing
import test_aoi_queues as aoi
from logixlab.model import ModelError,Op
from logixlab import gsv_configuration


class GsvThisTests(unittest.TestCase):
    setUp=config.GsvConfigurationTests.setUp
    engine=config.GsvConfigurationTests.engine
    checked=config.GsvConfigurationTests.checked
    snapshot=staticmethod(timing.GsvTimingTests.snapshot)

    def fault(self,e,pattern):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step(25)
        self.assertEqual(self.snapshot(e),before)

    @staticmethod
    def outputs(root):
        tags=root.find('./Controller/Tags')
        for name in ('CurrentLast','NamedLast','CurrentMax','NamedMax'):config.scalar(tags,name,'DINT',-1)
        tag=E.SubElement(tags,'Tag',Name='Values',TagType='Base',DataType='DINT',Dimensions='4');array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='4')
        for i,value in ((0,2),(3,999)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))

    @staticmethod
    def adopt(root,program):
        source=root.find('./Controller/Programs/Program[@Name="BackgroundProgram"]/Routines/Routine[@Name="Main"]')
        destination=root.find(f'./Controller/Programs/Program[@Name="{program}"]/Routines/Routine[@Name="Main"]')
        saved=copy.deepcopy(source);destination.clear();destination.attrib.update(saved.attrib)
        for child in saved:destination.append(child)
        source.clear();source.attrib.update(Name='Main',Type='RLL');E.SubElement(E.SubElement(E.SubElement(source,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='NOP();'

    def test_background_task_this_name_watchdog_and_case_insensitive_token(self):
        for st in (False,True):
            e=self.checked(['GSV(Task,tHiS,Name,NameOut);','GSV(Task,THIS,Watchdog,Out);'],st=st);e.step(25)
            self.assertEqual(e.memory.string('NameOut'),'BackgroundTask');self.assertEqual(e.memory.read('Out'),500000)

    def test_periodic_programs_resolve_their_own_rate_priority_and_name(self):
        for owner,rate,priority in [('FastProgram',10000,2),('SlowProgram',25000,5)]:
            for st in (False,True):
                e=self.checked(['GSV(Task,THIS,Rate,Out);','GSV(Task,THIS,Priority,PriorityOut);','GSV(Task,THIS,Name,NameOut);'],st=st,mutate=lambda root:self.adopt(root,owner));e.step(25)
                self.assertEqual((e.memory.read('Out'),e.memory.read('PriorityOut'),e.memory.string('NameOut')),(rate,priority,owner.replace('Program','Task')))

    def test_called_rll_and_st_routines_keep_program_and_task_context(self):
        for st in (False,True):
            def called(root):
                self.outputs(root);routines=root.find('./Controller/Programs/Program[@Name="BackgroundProgram"]/Routines');routine=E.SubElement(routines,'Routine',Name='ReadCurrent',Type='ST' if st else 'RLL');content=E.SubElement(routine,'STContent' if st else 'RLLContent')
                for i,text in enumerate(['GSV(Task,THIS,Watchdog,Out);','GSV(Program,THIS,LastScanTime,CurrentLast);','GSV(Program,BackgroundProgram,LastScanTime,NamedLast);']):
                    if st:E.SubElement(content,'Line',Number=str(i)).text=text
                    else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
            e=self.checked(['JSR(ReadCurrent,0);'],mutate=called);e.step(25);e.step(25)
            self.assertEqual(e.memory.read('Out'),500000);self.assertEqual(e.memory.read('CurrentLast'),e.memory.read('NamedLast'))

    def test_each_program_this_reads_the_same_committed_snapshot_as_its_name(self):
        for owner in ('BackgroundProgram','FastProgram','SlowProgram'):
            def move(root):
                self.outputs(root)
                if owner!='BackgroundProgram':self.adopt(root,owner)
            logic=[f'GSV(Program,THIS,LastScanTime,CurrentLast); GSV(Program,{owner},LastScanTime,NamedLast);',f'GSV(Program,THIS,MaxScanTime,CurrentMax); GSV(Program,{owner},MaxScanTime,NamedMax);']
            e=self.checked(logic,st=True,mutate=move);e.step(25);e.step(25)
            self.assertEqual(e.memory.read('CurrentLast'),e.memory.read('NamedLast'));self.assertEqual(e.memory.read('CurrentMax'),e.memory.read('NamedMax'));self.assertGreaterEqual(e.memory.read('CurrentMax'),e.memory.read('CurrentLast'))

    def test_single_task_timing_this_shares_named_measurement_and_multitask_is_available(self):
        logic=['GSV(Task,THIS,LastScanTime,TaskLast);','GSV(Task,MainTask,LastScanTime,TaskMax);','GSV(Program,THIS,LastScanTime,ProgramLast);','GSV(Program,MainProgram,LastScanTime,ProgramMax);']
        e=timing.GsvTimingTests.engine(self,logic);self.assertEqual(e.blockers,[]);e.step();e.step()
        self.assertEqual(e.memory.read('TaskLast'),e.memory.read('TaskMax'));self.assertEqual(e.memory.read('ProgramLast'),e.memory.read('ProgramMax'))
        e=self.checked(['GSV(Task,THIS,LastScanTime,Out);']);e.step(25);self.assertEqual(e.memory.read('Out'),0)

    def test_configuration_destinations_are_lazy_and_unknown_full_cells_can_be_written(self):
        for instance in ('THIS','FastTask'):
            e=self.checked([f'XIC(Flag)GSV(Task,{instance},Watchdog,Values[Index]);'],mutate=self.outputs);e.memory.write('Index',99);e.step(25);self.assertIsNone(e.memory.read('Values')[1]);e.memory.write('Flag',True);self.fault(e,'outside bounds')
            e.memory.write('Index',1);e.step(25);self.assertEqual(e.memory.read('Values'),[2,500000,None,999])

    def test_program_timing_false_and_prescan_paths_skip_live_indices_and_measurements(self):
        e=timing.GsvTimingTests.engine(self,['XIC(ReadTiming)GSV(Program,THIS,LastScanTime,UnknownWords[Index]);']);self.assertEqual(e.blockers,[]);e.enter_run();e.step();e.memory.write('ReadTiming',True)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',2);e.step();self.assertGreaterEqual(e.memory.read('UnknownWords[2]'),0)

    def test_this_inhibit_read_follows_live_self_inhibition_until_next_release(self):
        e=self.checked(['SSV(Task,BackgroundTask,InhibitTask,Out);','GSV(Task,THIS,InhibitTask,Values[1]);'],mutate=self.outputs)
        e.step(25);self.assertEqual(e.memory.read('Values[1]'),1);executions=e.scheduler_description()['tasks'][0]['executions']
        e.step(25);self.assertEqual(e.memory.read('Values[1]'),1);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],executions)

    def test_runtime_this_requires_the_current_task_and_context_is_restored_after_faults(self):
        e=self.checked(['GSV(Task,THIS,Watchdog,Out);']);op=Op('GSV',['Task','THIS','Watchdog','Out'])
        before=e.memory.read('Out')
        for task in (None,'FastTask'):
            e._executing_task=task
            with self.assertRaisesRegex(ModelError,'active Task'):gsv_configuration.execute(e,op,'BackgroundProgram')
            self.assertEqual(e.memory.read('Out'),before)
        e._executing_task=None;e.step(25);self.assertIsNone(e._executing_task)

    def test_later_fault_restores_current_and_named_reads_and_timing_snapshots(self):
        e=self.checked(['GSV(Task,THIS,Watchdog,Out);','GSV(Program,THIS,LastScanTime,CurrentLast);','DIV(1,Index,NamedLast);'],mutate=self.outputs);self.fault(e,'zero');self.assertIsNone(e._executing_task)
        e.memory.write('Index',1);e.step(25);self.assertEqual(e.memory.read('Out'),500000);self.assertEqual(e.memory.read('CurrentLast'),0)

    def test_context_and_configuration_drift_are_rejected_without_guessing(self):
        e=self.checked(['GSV(Task,THIS,Watchdog,Out);']);op=Op('GSV',['Task','THIS','Watchdog','Out'])
        with self.assertRaisesRegex(ModelError,'scheduled'):gsv_configuration.validate(e,op,'Missing')
        e.project.tasks[0]['name']='Changed'
        with self.assertRaisesRegex(ModelError,'unchanged'):gsv_configuration.validate(e,op,'BackgroundProgram')

    def test_aoi_harness_invalid_event_and_empty_instance_this_forms_remain_unqualified(self):
        self.assertTrue(self.engine(['GSV(Task,THIS,Watchdog,Out);'],harness=True).blockers)
        e=aoi.AOIQueueTests.engine(self,lambda root:aoi.logic(root,['GSV(Task,THIS,Watchdog,Buffer[Index]);']));self.assertTrue(any('AOI' in b for b in e.blockers))
        import test_event_tasks as events
        e=events.EventTaskTests.engine(self,[['EVENT(Task1);'],['GSV(Task,THIS,LastScanTime,SpeedCommand);']],mutate=lambda root:root.find('./Controller/Tasks/Task[2]/EventInfo').set('EnableTimeout','true'));self.assertTrue(e.blockers)
        for cls,instance,attribute in [('Task','','Watchdog'),('Task','0','Watchdog'),('Controller','THIS','TimeSlice'),('Program','','LastScanTime')]:self.assertTrue(self.engine([f'GSV({cls},{instance},{attribute},Out);']).blockers)

    def test_configuration_st_for_effects_cover_static_and_changing_destinations(self):
        for instance in ('THIS','FastTask'):
            def alias(root):self.outputs(root);E.SubElement(root.find('./Controller/Tags'),'Tag',Name='View',TagType='Alias',DataType='DINT',AliasFor='Values[Index]')
            for dest,bound in [('Values[0]','Values[0]'),('Values[Index]','Values[3]'),('View','Values[3]')]:
                e=self.engine([f'FOR Out:=0 TO {bound} DO GSV(Task,{instance},Watchdog,{dest}); END_FOR;'],st=True,mutate=alias);self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)
            e=self.checked([f'FOR Index:=0 TO Values[0] DO GSV(Task,{instance},Watchdog,Values[1]); END_FOR;'],st=True,mutate=self.outputs);e.step(25);self.assertEqual(e.memory.read('Values'),[2,500000,None,999])

    def test_timing_this_preserves_static_and_conservative_for_effects(self):
        for dest in ('Values[0]','Values[Index]'):
            e=self.engine([f'FOR Out:=0 TO Values[0] DO GSV(Program,THIS,LastScanTime,{dest}); END_FOR;'],st=True,mutate=self.outputs);self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)
        e=self.checked(['FOR Index:=0 TO Values[0] DO GSV(Program,THIS,LastScanTime,Values[1]); END_FOR;'],st=True,mutate=self.outputs);e.step(25);self.assertEqual(e.memory.read('Values'),[2,0,None,999])

    def test_reports_keep_qualified_current_instance_and_native_boundaries_explicit(self):
        e=self.checked(['GSV(Task,THIS,Watchdog,Out);']);report=e.report()['system_values']
        self.assertIn('THIS',report['configuration']['current_instance']);self.assertIn('THIS',report['timing']['current_instance']);self.assertFalse(report['timing']['native_runtime_parity']);self.assertFalse(report['configuration']['native_runtime_equivalence'])
