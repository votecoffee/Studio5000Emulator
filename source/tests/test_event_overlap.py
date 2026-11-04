"""Live Event OverlapCount reads and transactional zero resets."""
import unittest
from xml.etree import ElementTree as E

import test_event_status as status
from logixlab.model import ModelError,Op


class EventOverlapTests(unittest.TestCase):
    setUp=status.EventStatusTests.setUp
    checked=status.EventStatusTests.checked
    snapshot=staticmethod(status.EventStatusTests.snapshot)
    fault=status.EventStatusTests.fault

    def engine(self,bodies=None,**kwargs):
        bodies=bodies or [['XIC(StartPB)EVENT(Task1);','GSV(Task,Task1,OverlapCount,CallerStatus);'],
                          ['GSV(Task,THIS,OverlapCount,EntryStatus);','XIC(SelfTrigger)EVENT(Task1);',
                           'GSV(Task,THIS,OverlapCount,AfterStatus);','XIC(ClearStatus)SSV(Task,THIS,OverlapCount,Command);',
                           'GSV(Task,THIS,OverlapCount,ExitStatus);','ADD(Count1,1,Count1);']]
        return status.EventStatusTests.engine(self,bodies,**kwargs)

    def test_initial_and_live_counts_match_scheduler_feedback(self):
        e=self.checked();e.step();self.assertEqual(e.memory.read('CallerStatus'),0)
        e.memory.write('StartPB',True);e.memory.write('SelfTrigger',True)
        for count in (1,2,3):
            e.step();self.assertEqual((e.memory.read('EntryStatus'),e.memory.read('AfterStatus'),e.memory.read('ExitStatus'),e.memory.read('CallerStatus')),(count-1,count,count,count))
            self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],count)

    def test_this_zero_reset_retains_source_and_status_latch(self):
        e=self.checked();e.memory.write('StartPB',True);e.memory.write('SelfTrigger',True);e.step()
        e.memory.write('ClearStatus',True);e.step()
        self.assertEqual((e.memory.read('AfterStatus'),e.memory.read('ExitStatus'),e.memory.read('CallerStatus'),e.memory.read('Command')),(2,0,0,0))
        self.assertEqual(e._task_event_status['task1'],5);self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],0)

    def test_reset_between_requests_counts_only_later_active_requests(self):
        e=self.checked([['EVENT(Task1);','GSV(Task,Task1,OverlapCount,CallerStatus);'],
                        ['EVENT(Task1);','SSV(Task,THIS,OverlapCount,Command);','EVENT(Task1);','GSV(Task,THIS,OverlapCount,ExitStatus);']]);e.step()
        self.assertEqual((e.memory.read('CallerStatus'),e.memory.read('ExitStatus')),(1,1));self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],1)

    def test_status_clear_does_not_clear_count(self):
        e=self.checked([['EVENT(Task1);','GSV(Task,Task1,OverlapCount,CallerStatus);'],
                        ['EVENT(Task1);','SSV(Task,THIS,Status,Command);']]);e.step()
        self.assertEqual(e._task_event_status['task1'],0);self.assertEqual(e.memory.read('CallerStatus'),1)

    def test_nonzero_and_unknown_reset_sources_fault_atomically(self):
        e=self.checked([['SSV(Task,Task1,OverlapCount,Command);'],['NOP();']])
        for value in (1,-1,5):e.memory.write('Command',value);self.fault(e,'zero only')
        e.memory.values['command']=None;self.fault(e,'Unknown|known')

    def test_pending_duplicates_and_inhibited_requests_do_not_increment(self):
        def periodic(root):root.find('./Controller/Tasks/Task').attrib.update(Type='PERIODIC',Priority='5',Rate='10')
        e=self.checked([['EVENT(Task1);','EVENT(Task1);','GSV(Task,Task1,OverlapCount,CallerStatus);'],['NOP();']],priority='14',mutate=periodic);e.step()
        self.assertEqual(e.memory.read('CallerStatus'),0);self.assertEqual(e.scheduler_description()['tasks'][1]['event_pending_requests_coalesced'],1)
        e=self.checked(inhibited=True);e.memory.write('StartPB',True);e.memory.write('SelfTrigger',True);e.step();self.assertEqual(e.memory.read('CallerStatus'),0)

    def test_parent_or_child_fault_restores_reset_and_new_counts(self):
        for bodies in ([['EVENT(Task1);','SSV(Task,Task1,OverlapCount,Command);','DIV(1,Divisor,SpeedCommand);'],['EVENT(Task1);']],
                       [['EVENT(Task1);'],['EVENT(Task1);','SSV(Task,THIS,OverlapCount,Command);','DIV(1,Divisor,SpeedCommand);']]):
            e=self.checked(bodies);e._task_scheduler.overlaps[1]=7;e.memory.write('Divisor',0);self.fault(e,'zero');self.assertEqual(e._task_scheduler.overlaps[1],7)
            e.memory.write('Divisor',1);e.step();self.assertEqual(e._task_scheduler.overlaps[1],0)

    def test_false_and_prescan_skip_unknown_or_invalid_reset_source(self):
        e=self.checked([['XIC(ReadStatus)SSV(Task,Task1,OverlapCount,Values[Index]);'],['NOP();']]);e._task_scheduler.overlaps[1]=3;e.step();self.assertEqual(e._task_scheduler.overlaps[1],3)
        e.memory.write('ReadStatus',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown|known');e.memory.write('Values[1]',0);e.step();self.assertEqual(e._task_scheduler.overlaps[1],0)

    def test_gsv_complete_unknown_output_preserves_guards_and_loop_effects(self):
        e=self.checked([['XIC(ReadStatus)GSV(Task,Task1,OverlapCount,Values[Index]);'],['NOP();']]);e.step();self.assertIsNone(e.memory.read('Values')[1]);e.memory.write('ReadStatus',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Values'),[101,0,999])
        e=self.checked([['FOR Command:=0 TO Values[0] DO GSV(Task,Task1,OverlapCount,Values[1]); END_FOR;'],['NOP();']],st=True);e.step();self.assertEqual(e.memory.read('Values'),[101,0,999])
        e=self.engine([['FOR Command:=0 TO Values[2] DO GSV(Task,Task1,OverlapCount,Values[Index]); END_FOR;'],['NOP();']],st=True);self.assertTrue(any('bounds/step' in b for b in e.blockers))

    def test_st_named_and_this_live_read_reset_order(self):
        e=self.checked([['EVENT(Task1); GSV(Task,Task1,OverlapCount,CallerStatus);'],
                        ['EVENT(Task1); GSV(Task,THIS,OverlapCount,AfterStatus); SSV(Task,THIS,OverlapCount,Command); GSV(Task,THIS,OverlapCount,ExitStatus);']],st=True,event_st=True);e.step()
        self.assertEqual((e.memory.read('AfterStatus'),e.memory.read('ExitStatus'),e.memory.read('CallerStatus')),(1,0,0))

    def test_unsigned_words_unavailable_overflow_and_direct_reset(self):
        e=self.checked([['GSV(Task,Task1,OverlapCount,CallerStatus);'],['NOP();']]);e._task_scheduler.overlaps[1]=0x80000000;e.step();self.assertEqual(e.memory.read('CallerStatus'),-2147483648)
        e._task_scheduler.overlaps[1]=1<<32;self.fault(e,'unavailable')
        e=self.checked([['SSV(Task,Task1,OverlapCount,Command);','GSV(Task,Task1,OverlapCount,CallerStatus);'],['NOP();']]);e._task_scheduler.overlaps[1]=1<<32;e.step();self.assertEqual(e.memory.read('CallerStatus'),0)

    def test_run_entry_resets_counter_but_detached_edit_preserves_current_value(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();e.memory.write('StartPB',True);e.memory.write('SelfTrigger',True);e.step()
        candidate,_=prepare(e,decode(container(E.tostring(xml_source(name='Main',text='NOP();')))),['NOP();'],'Program0',0)
        self.assertEqual(candidate._task_scheduler.overlaps,e._task_scheduler.overlaps);self.assertIsNot(candidate._task_scheduler.overlaps,e._task_scheduler.overlaps)
        e.enter_run();self.assertEqual(e._task_scheduler.overlaps[1],0);self.assertEqual(e._task_event_status['task1'],5)

    def test_invalid_absolute_counter_commit_never_partially_updates_scheduler(self):
        e=self.checked();scheduler=e._task_scheduler;before=scheduler.description();batch=scheduler.prepare(10)
        for counts in ({},{1:-1},{1:True},{True:0},{1:1},{1:0,9:0},[]):
            with self.assertRaisesRegex(ModelError,'absolute Event'):scheduler.commit(batch,event_overlap_counts=counts)
            self.assertEqual(scheduler.description(),before)

    def test_context_type_and_native_status_boundaries_are_retained(self):
        for text in ('GSV(Task,Task0,OverlapCount,CallerStatus);','GSV(Task,Missing,OverlapCount,CallerStatus);','GSV(Task,Task1,OverlapCount,StartPB);','SSV(Task,Task1,OverlapCount,0);'):
            self.assertTrue(self.engine([[text],['NOP();']]).blockers,text)
        from logixlab import event_status
        e=self.checked();e.memory.frames['@AOI:test']={}
        with self.assertRaisesRegex(ModelError,'AOI/harness'):event_status.validate(e,Op('GSV',['Task','Task1','OverlapCount','CallerStatus']),'@AOI:test')
        report=e.report()['event_task_status'];self.assertIn('OverlapCount',report['attributes']);self.assertEqual(report['overlap_counts'],{'task1':0});self.assertFalse(report['native_protocol_expanded']);self.assertFalse(report['native_runtime_parity'])
