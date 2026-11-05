"""Live Event inhibition, pending dispatch, self-inhibition and THIS control."""
import copy
import struct
import unittest
from xml.etree import ElementTree as E

import test_event_status as status
import test_gsv_configuration as config
from logixlab.model import ModelError


class EventInhibitTests(unittest.TestCase):
    setUp=status.EventStatusTests.setUp
    checked=status.EventStatusTests.checked
    snapshot=staticmethod(status.EventStatusTests.snapshot)
    fault=status.EventStatusTests.fault

    def engine(self,bodies=None,*,mutate=None,**kwargs):
        def extra(root):
            status.scalar(root.find('./Controller/Tags'),'SelfCommand','DINT',1)
            if mutate:mutate(root)
        bodies=bodies or [['XIC(ClearStatus)SSV(Task,Task1,InhibitTask,Command);','XIC(StartPB)EVENT(Task1);',
                           'GSV(Task,Task1,InhibitTask,CallerStatus);'],
                          ['GSV(Task,THIS,InhibitTask,EntryStatus);','XIC(SelfTrigger)SSV(Task,THIS,InhibitTask,SelfCommand);',
                           'GSV(Task,THIS,InhibitTask,ExitStatus);','ADD(Count1,1,Count1);']]
        return status.EventStatusTests.engine(self,bodies,mutate=extra,**kwargs)

    def test_named_event_inhibition_gates_new_requests_and_feedback_is_live(self):
        e=self.checked();e.memory.write('StartPB',True);e.memory.write('ClearStatus',True)
        for command,count in ((1,0),(-1,0),(0,1),(7,1),(0,2)):
            e.memory.write('Command',command);e.step();self.assertEqual(e.memory.read('Count1'),count)
            self.assertEqual(e.memory.read('CallerStatus'),int(command!=0));self.assertEqual(e.memory.read('Command'),command)
        self.assertEqual(e.task_inhibition_attributes('Task1',source_sha256=e.project.sha256),{19:struct.pack('<I',0)})
        self.assertFalse(e.project.tasks[1]['inhibited'])

    def test_initially_inhibited_event_can_be_enabled_then_self_inhibit_and_finish(self):
        e=self.checked(inhibited=True);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Count1'),0)
        e.memory.write('ClearStatus',True);e.memory.write('SelfTrigger',True);e.step()
        self.assertEqual((e.memory.read('Count1'),e.memory.read('EntryStatus'),e.memory.read('ExitStatus'),e.memory.read('CallerStatus')),(1,0,1,1))
        self.assertTrue(e.project.tasks[1]['inhibited']);self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)
        e.memory.write('ClearStatus',False);e.step();self.assertEqual(e.memory.read('Count1'),1)

    def test_current_event_completes_but_later_self_request_is_ignored(self):
        e=self.checked([['EVENT(Task1);'],['SSV(Task,THIS,InhibitTask,SelfCommand);','EVENT(Task1);','ADD(Count1,1,Count1);','GSV(Task,THIS,InhibitTask,ExitStatus);']]);e.step()
        self.assertEqual(e.memory.read('Count1'),1);self.assertEqual(e.memory.read('ExitStatus'),1)
        self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],0);self.assertEqual(e._task_event_status['task1'],1)
        e.step();self.assertEqual(e.memory.read('Count1'),1)

    def test_pending_event_rechecks_inhibition_and_keeps_accepted_status(self):
        def periodic(root):root.find('./Controller/Tasks/Task').attrib.update(Type='PERIODIC',Priority='5',Rate='10')
        e=self.checked([['EVENT(Task1);','SSV(Task,Task1,InhibitTask,SelfCommand);','GSV(Task,Task1,InhibitTask,CallerStatus);'],['ADD(Count1,1,Count1);']],priority='14',mutate=periodic);e.step()
        self.assertEqual((e.memory.read('Count1'),e.memory.read('CallerStatus')),(0,1));self.assertEqual(e._task_event_status['task1'],1)
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],0)

    def test_inhibit_then_enable_before_pending_dispatch_allows_execution(self):
        def periodic(root):root.find('./Controller/Tasks/Task').attrib.update(Type='PERIODIC',Priority='5',Rate='10')
        e=self.checked([['EVENT(Task1);','SSV(Task,Task1,InhibitTask,SelfCommand);','SSV(Task,Task1,InhibitTask,Command);'],['ADD(Count1,1,Count1);']],priority='14',mutate=periodic);e.step()
        self.assertEqual(e.memory.read('Count1'),1)

    def test_ignored_request_is_not_replayed_when_event_is_enabled(self):
        e=self.checked();e.memory.write('ClearStatus',True);e.memory.write('Command',1);e.memory.write('StartPB',True);e.step()
        e.memory.write('Command',0);e.memory.write('StartPB',False);e.step();self.assertEqual(e.memory.read('Count1'),0);self.assertEqual(e._task_event_status['task1'],0)
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Count1'),1)

    def test_masked_pending_event_is_discarded_at_uie_while_inhibited(self):
        e=self.checked([['UID();','EVENT(Task1);','SSV(Task,Task1,InhibitTask,SelfCommand);','UIE();'],['ADD(Count1,1,Count1);']]);e.step()
        self.assertEqual(e.memory.read('Count1'),0);self.assertEqual(e._task_event_status['task1'],1)

    def test_later_fault_restores_inhibition_status_first_scans_and_queued_work(self):
        for priority in ('1','14'):
            def periodic(root):root.find('./Controller/Tasks/Task').attrib.update(Type='PERIODIC',Priority='5',Rate='10')
            e=self.checked([['EVENT(Task1);','SSV(Task,Task1,InhibitTask,SelfCommand);','DIV(1,Divisor,SpeedCommand);'],['ADD(Count1,1,Count1);']],priority=priority,mutate=periodic)
            e.memory.write('Divisor',0);self.fault(e,'zero');self.assertFalse(e._task_scheduler.inhibitions[1]);self.assertEqual(e._task_event_status['task1'],0)
            e.memory.write('Divisor',1);e.step();self.assertTrue(e._task_scheduler.inhibitions[1])

    def test_structured_text_named_and_this_inhibition_share_live_flags(self):
        e=self.checked([['SSV(Task,Task1,InhibitTask,Command); EVENT(Task1); GSV(Task,Task1,InhibitTask,CallerStatus);'],
                        ['SSV(Task,THIS,InhibitTask,SelfCommand); GSV(Task,THIS,InhibitTask,ExitStatus); Count1:=Count1+1;']],st=True,event_st=True);e.step()
        self.assertEqual((e.memory.read('Count1'),e.memory.read('ExitStatus'),e.memory.read('CallerStatus')),(1,1,1))

    def test_continuous_and_periodic_this_setters_select_their_own_task(self):
        f=config.GsvConfigurationTests();f.setUp();self.addCleanup(f.doCleanups)
        import test_gsv_this as current
        for program in ('BackgroundProgram','FastProgram'):
            def move(root):
                if program!='BackgroundProgram':current.GsvThisTests.adopt(root,program)
            e=f.checked(['SSV(Task,THIS,InhibitTask,Out);','GSV(Task,THIS,InhibitTask,Index);'],mutate=move);e.step(25)
            self.assertEqual(e.memory.read('Index'),1)
            row=next(t for t in e.scheduler_description()['tasks'] if t['name']==program.replace('Program','Task'));self.assertTrue(row['inhibited'])

    def test_event_this_configuration_reads_explicit_name_priority_watchdog_and_flags(self):
        def tags(root):
            status.scalar(root.find('./Controller/Tags'),'PriorityOut','INT',-1)
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='NameOut',TagType='Base',DataType='STRING')
            import test_string_operations as strings
            strings.string_data(E.SubElement(tag,'Data',Format='Decorated'),'SAVED')
        e=self.checked([['EVENT(Task1);'],['GSV(Task,THIS,Name,NameOut);','GSV(Task,THIS,Priority,PriorityOut);','GSV(Task,THIS,Watchdog,EntryStatus);','GSV(Task,THIS,DisableUpdateOutputs,ExitStatus);']],mutate=tags);e.step()
        self.assertEqual(e.memory.string('NameOut'),'Task1');self.assertEqual((e.memory.read('PriorityOut'),e.memory.read('EntryStatus'),e.memory.read('ExitStatus')),(1,500000,1))

    def test_false_ssv_skips_invalid_and_unknown_source_elements(self):
        e=self.checked([['XIC(ReadStatus)SSV(Task,Task1,InhibitTask,Values[Index]);'],['NOP();']]);e.enter_run();e.step()
        e.memory.write('ReadStatus',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown|known')
        e.memory.write('Values[1]',1);e.step();self.assertTrue(e._task_scheduler.inhibitions[1])

    def test_run_entry_and_detached_replacement_retain_live_event_inhibition(self):
        from logixlab.runtime import Engine
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();e.memory.write('ClearStatus',True);e.memory.write('Command',1);e.step();e.enter_run();self.assertTrue(e._task_scheduler.inhibitions[1])
        candidate,_=prepare(e,decode(container(E.tostring(xml_source(name='Main',text='NOP();')))),['NOP();'],'Program0',0)
        self.assertTrue(candidate._task_scheduler.inhibitions[1]);candidate._task_scheduler.inhibitions[1]=False;self.assertTrue(e._task_scheduler.inhibitions[1])
        self.assertFalse(Engine(e.project)._task_scheduler.inhibitions[1])

    def test_queued_and_immediate_event_priority_uses_one_advance_snapshot(self):
        def tags(root):
            root.find('./Controller/Tasks/Task').attrib.update(Type='PERIODIC',Priority='5',Rate='10')
            for name,value in (('PriorityIn',1),('PriorityOut',-1),('EventPriority',-1)):
                status.scalar(root.find('./Controller/Tags'),name,'INT',value)
        for masked in (False,True):
            logic=['SSV(Task,Task1,Priority,PriorityIn);','GSV(Task,Task1,Priority,PriorityOut);','EVENT(Task1);']
            if masked:logic=['UID();',*logic,'UIE();']
            e=self.checked([logic+['MOV(Count1,CallerStatus);'],
                            ['GSV(Task,THIS,Priority,EventPriority);','ADD(Count1,1,Count1);']],
                           priority='14',mutate=tags)
            e.step()
            self.assertEqual((e.memory.read('PriorityOut'),e.memory.read('EventPriority')),(1,1))
            self.assertEqual((e.memory.read('CallerStatus'),e.memory.read('Count1')),(0,1))
            e.step()
            self.assertEqual((e.memory.read('CallerStatus'),e.memory.read('Count1')),(2,2))

    def test_event_priority_write_does_not_reorder_pending_queue_mid_advance(self):
        def tags(root):
            c=root.find('Controller');tags=c.find('Tags')
            status.scalar(tags,'Promote','INT',1)
            status.scalar(tags,'Observed','DINT',0)
            program=copy.deepcopy(c.find('./Programs/Program[@Name="Program1"]'))
            program.set('Name','Program2')
            program.find('.//Rung/Text').text='MOV(2,Observed);'
            c.find('Programs').append(program)
            task=copy.deepcopy(c.find('Tasks')[1]);task.attrib.update(Name='Task2',Priority='8')
            task.find('./ScheduledPrograms/ScheduledProgram').set('Name','Program2')
            c.find('Tasks').append(task)
        e=self.checked([['UID();','EVENT(Task1);','EVENT(Task2);','SSV(Task,Task1,Priority,Promote);','UIE();'],
                        ['MOV(1,Observed);']],priority='12',mutate=tags)
        e.step();self.assertEqual(e.memory.read('Observed'),1)
        e.step();self.assertEqual(e.memory.read('Observed'),2)

    def test_event_this_watchdog_sees_named_write_and_rejects_undefined_zero_default(self):
        e=self.checked([['SSV(Task,Task1,Watchdog,Command);','EVENT(Task1);',
                         'GSV(Task,Task1,Watchdog,CallerStatus);'],
                        ['GSV(Task,THIS,Watchdog,EntryStatus);','SSV(Task,THIS,Watchdog,SelfCommand);',
                         'GSV(Task,THIS,Watchdog,ExitStatus);']])
        e.memory.write('Command',125001);e.memory.write('SelfCommand',250001);e.step()
        self.assertEqual((e.memory.read('EntryStatus'),e.memory.read('ExitStatus'),e.memory.read('CallerStatus')),
                         (125001,250001,250001))
        for source in ('Command','SelfCommand'):
            original=e.memory.read(source);e.memory.write(source,0)
            self.fault(e,'zero is qualified')
            e.memory.write(source,original)
        self.assertEqual(e.scheduler_description()['tasks'][1]['watchdog_override_us'],250001)

    def test_wrong_types_aoi_harness_event_rate_and_missing_flags_remain_guarded(self):
        for text in ('SSV(Task,Task1,InhibitTask,StartPB);','SSV(Task,Task1,InhibitTask,1);','GSV(Task,Task1,Rate,CallerStatus);'):
            self.assertTrue(self.engine([[text],['NOP();']]).blockers,text)
        from logixlab.runtime import Engine
        e=self.checked();self.assertTrue(Engine(e.project,mode='routine',routine='Program0/Main').blockers)
        def missing(root):root.find('./Controller/Tasks/Task[2]').attrib.pop('InhibitTask')
        self.assertTrue(self.engine(mutate=missing).blockers)
