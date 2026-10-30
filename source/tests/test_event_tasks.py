"""EVENT priority boundaries, source qualification and transactional task state."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_task_scheduler as fixtures
from logixlab.model import ModelError
from logixlab.runtime import Engine


class EventTaskTests(unittest.TestCase):
    setUp=fixtures.TaskSchedulerTests.setUp

    def engine(self,bodies=None,*,st=False,event_st=False,mutate=None,defer=False,priority='1',inhibited=False):
        bodies=bodies or [['ADD(Count0,1,Count0);','XIC(StartPB)EVENT(Task1);','MOV(Count1,SpeedCommand);','XIC(S:FS)ADD(First0,1,First0);'],
                          ['ADD(Count1,1,Count1);','XIC(S:FS)ADD(First1,1,First1);']]
        def extra(root):
            task=root.find('./Controller/Tasks/Task[2]')
            task.set('Watchdog','500');task.set('DisableUpdateOutputs','true')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
            for index,enabled in ((0,st),(1,event_st)):
                if not enabled:continue
                routine=root.find(f'./Controller/Programs/Program[@Name="Program{index}"]/Routines/Routine')
                routine.remove(routine.find('RLLContent'));routine.set('Type','ST');content=E.SubElement(routine,'STContent')
                for i,text in enumerate(bodies[index]):E.SubElement(content,'Line',Number=str(i)).text=text
            if mutate:mutate(root)
        return fixtures.TaskSchedulerTests.engine(self,[dict(Type='CONTINUOUS'),dict(Type='EVENT',Priority=priority,InhibitTask=str(inhibited).lower())],
                                                  bodies,mutate=extra,defer=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def graph(self,specs,bodies):
        def infos(root):
            for task in root.findall('./Controller/Tasks/Task'):
                if task.get('Type')=='EVENT':E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
        e=fixtures.TaskSchedulerTests.engine(self,specs,bodies,mutate=infos)
        self.assertEqual(e.blockers,[]);return e

    def test_untriggered_event_task_is_prescanned_but_not_periodically_released(self):
        e=self.checked();e.step(20)
        self.assertEqual((e.memory.read('Count0'),e.memory.read('Count1')),(1,0))
        row=e.scheduler_description()['tasks'][1]
        self.assertEqual((row['kind'],row['priority'],row['executions'],row['last_release_ms'],row['next_release_ms']),('Event',1,0,None,None))
        self.assertTrue(e.scheduler_description()['event_tasks']);self.assertTrue(e.first_scan_pending)
        self.assertEqual(e.memory.read('First0'),1);self.assertEqual(e.memory.read('First1'),0)

    def test_higher_priority_event_finishes_before_caller_next_instruction_each_true_call(self):
        e=self.checked();e.memory.write('StartPB',True)
        for i in range(1,4):
            e.step();self.assertEqual(e.memory.read('Count1'),i);self.assertEqual(e.memory.read('SpeedCommand'),i)
        self.assertEqual(e.memory.read('First0'),1);self.assertEqual(e.memory.read('First1'),1)
        self.assertFalse(e.first_scan_pending);self.assertIsNone(e._event_dispatch);self.assertIsNone(e._executing_task)

    def test_two_event_calls_execute_twice_but_program_first_scan_is_once(self):
        e=self.checked([['EVENT(Task1);','EVENT(Task1);','XIC(S:FS)ADD(First0,1,First0);'],
                        ['ADD(Count1,1,Count1);','XIC(S:FS)ADD(First1,1,First1);']]);e.step()
        self.assertEqual(e.memory.read('Count1'),2);self.assertEqual(e.memory.read('First1'),1);self.assertEqual(e.memory.read('First0'),1)
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],2)

    def test_false_rung_and_skipped_st_branch_retain_event_state_and_rung_output(self):
        e=self.checked([['XIC(StartPB)EVENT(Task1)OTE(RunLatch);'],['ADD(Count1,1,Count1);']]);e.step()
        self.assertFalse(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Count1'),0)
        e.memory.write('StartPB',True);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Count1'),1)
        e=self.checked([['IF FALSE THEN EVENT(Task1); END_IF;'],['Count1:=Count1+1;']],st=True,event_st=True);e.step()
        self.assertEqual(e.memory.read('Count1'),0)

    def test_structured_text_source_and_target_keep_task_trace_context(self):
        e=self.checked([['EVENT(Task1); SpeedCommand:=Count1; IF S:FS THEN First0:=First0+1; END_IF;'],
                        ['Count1:=Count1+1; IF S:FS THEN First1:=First1+1; END_IF;']],st=True,event_st=True);e.step()
        self.assertEqual(e.memory.read('SpeedCommand'),1);self.assertEqual(e.memory.read('First0'),1);self.assertEqual(e.memory.read('First1'),1)
        self.assertTrue(any(t['task']=='Task1' and t.get('language')=='ST' for t in e.trace))
        self.assertEqual({t['release_ms'] for t in e.trace},{10})

    def test_event_in_jsr_restores_caller_parameter_stack_and_task_context(self):
        def sub(root):
            routines=root.find('./Controller/Programs/Program[@Name="Program0"]/Routines')
            content=E.SubElement(E.SubElement(routines,'Routine',Name='Sub',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='EVENT(Task1);'
        e=self.checked([['JSR(Sub,0);','MOV(Count1,SpeedCommand);'],['ADD(Count1,1,Count1);']],mutate=sub);e.step()
        self.assertEqual(e.memory.read('SpeedCommand'),1);self.assertEqual(e.calls.stack,[]);self.assertEqual(e.memory.frames,{})
        self.assertEqual(e.trace[-1]['task'],'Task0')

    def test_nested_events_follow_strictly_increasing_priority_and_restore_first_scan(self):
        def infos(root):
            for task in root.findall('./Controller/Tasks/Task')[1:]:E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
        bodies=[['EVENT(Task1);','MOV(Count1,SpeedCommand);','XIC(S:FS)ADD(First0,1,First0);'],
                ['ADD(Count1,1,Count1);','EVENT(Task2);','MOV(Count2,SpeedSetpoint);','XIC(S:FS)ADD(First1,1,First1);'],
                ['ADD(Count2,1,Count2);','XIC(S:FS)ADD(First2,1,First2);']]
        e=fixtures.TaskSchedulerTests.engine(self,[dict(Type='CONTINUOUS'),dict(Type='EVENT',Priority='5'),dict(Type='EVENT',Priority='1')],bodies,mutate=infos)
        self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual([e.memory.read(f'Count{i}') for i in (1,2)],[1,1]);self.assertEqual(e.memory.read('SpeedSetpoint'),1)
        self.assertEqual([e.memory.read(f'First{i}') for i in range(3)],[1,1,1])
        self.assertEqual([t['executions'] for t in e.scheduler_description()['tasks']],[1,1,1])

    def test_active_self_request_is_discarded_and_counted_without_recursive_execution(self):
        e=self.checked([['EVENT(Task1);'],['ADD(Count1,1,Count1);','EVENT(Task1);']])
        for i in range(1,3):
            e.step();self.assertEqual(e.memory.read('Count1'),i)
            self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],i)
            self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],i)

    def test_event_body_fault_rolls_back_parent_writes_clock_and_scheduler(self):
        e=self.checked([['ADD(Count0,1,Count0);','EVENT(Task1);'],['ADD(Count1,1,Count1);','DIV(1,0,SpeedCommand);']])
        before=copy.deepcopy(e.memory.values);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        self.assertEqual((e.scan_count,e.time_ms),(0,0));self.assertIsNone(e._event_dispatch);self.assertIsNone(e._executing_task)

    def test_later_parent_fault_rolls_back_completed_events_overlaps_and_first_scans(self):
        e=self.checked([['EVENT(Task1);','DIV(1,0,SpeedCommand);'],['ADD(Count1,1,Count1);','EVENT(Task1);','XIC(S:FS)ADD(First1,1,First1);']])
        before=copy.deepcopy(e.memory.values);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        self.assertEqual(e._program_scanned,set());self.assertIsNone(e._event_dispatch)

    def test_non_event_target_is_a_noop_and_does_not_reschedule_periodic_task(self):
        e=self.checked([['ADD(Count0,1,Count0);','EVENT(Task0);'],['ADD(Count1,1,Count1);']]);e.step()
        self.assertEqual(e.memory.read('Count0'),1);self.assertEqual(e.memory.read('Count1'),0)
        def periodic(root):
            task=root.find('./Controller/Tasks/Task[2]');task.set('Type','PERIODIC');task.remove(task.find('EventInfo'))
        e=self.checked([['EVENT(Task1);'],['ADD(Count1,1,Count1);']],mutate=periodic);e.step()
        self.assertEqual(e.memory.read('Count1'),1);self.assertFalse(e.scheduler_description()['event_tasks'])

    def test_inhibited_event_does_not_execute_or_change_overlap_diagnostics(self):
        e=self.checked([['EVENT(Task1);'],['ADD(Count1,1,Count1);']],inhibited=True);e.step()
        self.assertEqual(e.memory.read('Count1'),0);self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],0)
        self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],0)

    def test_lower_or_equal_target_waits_for_whole_caller_in_rll_and_st(self):
        for priority in ('5','10'):
            def source(root):root.find('./Controller/Tasks/Task[1]').set('Type','PERIODIC');root.find('./Controller/Tasks/Task[1]').set('Priority','5')
            for st in (False,True):
                with self.subTest(priority=priority,st=st):
                    caller=['EVENT(Task1);','SpeedCommand:=Count1;'] if st else ['EVENT(Task1);','MOV(Count1,SpeedCommand);']
                    e=self.checked([caller,['ADD(Count1,1,Count1);','XIC(S:FS)ADD(First1,1,First1);']],priority=priority,mutate=source,st=st)
                    e.step();self.assertEqual((e.memory.read('SpeedCommand'),e.memory.read('Count1')),(0,1))
                    self.assertEqual(e.memory.read('First1'),1);e.step()
                    self.assertEqual((e.memory.read('SpeedCommand'),e.memory.read('Count1'),e.memory.read('First1')),(1,2,1))
            e=self.checked([['EVENT(Task1);'],['NOP();']],priority=priority,inhibited=True,mutate=source);e.step()
            self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],0)

    def test_pending_events_interleave_with_ready_base_tasks_by_priority_and_base_first_ties(self):
        specs=[dict(Priority='2'),dict(Priority='4'),dict(Priority='6'),dict(Type='EVENT',Priority='5'),dict(Type='EVENT',Priority='4')]
        bodies=[['ADD(Count0,1,Count0);','EVENT(Task3);','EVENT(Task4);'],['ADD(Count1,1,Count1);'],
                ['ADD(Count2,1,Count2);'],['ADD(Count3,1,Count3);'],['ADD(Count4,1,Count4);']]
        e=self.graph(specs,bodies);e.step()
        self.assertEqual([t['task'] for t in e.trace if t['number']=='0'],['Task0','Task1','Task4','Task3','Task2'])
        self.assertEqual({t['release_ms'] for t in e.trace},{10})

    def test_queued_event_priorities_then_fifo_request_order_ignore_source_order_for_ties(self):
        e=self.graph([dict(Priority='2'),dict(Type='EVENT',Priority='6'),dict(Type='EVENT',Priority='3'),dict(Type='EVENT',Priority='6')],
                     [['ADD(Count0,1,Count0);','EVENT(Task3);','EVENT(Task1);','EVENT(Task2);'],
                      ['ADD(Count1,1,Count1);'],['ADD(Count2,1,Count2);'],['ADD(Count3,1,Count3);']]);e.step()
        self.assertEqual([t['task'] for t in e.trace if t['number']=='0'],['Task0','Task2','Task3','Task1'])

    def test_pending_duplicates_coalesce_separately_from_active_overlaps(self):
        def source(root):root.find('./Controller/Tasks/Task[1]').set('Type','PERIODIC');root.find('./Controller/Tasks/Task[1]').set('Priority','2')
        e=self.checked([['EVENT(Task1);','EVENT(Task1);','EVENT(Task1);'],['ADD(Count1,1,Count1);','EVENT(Task1);']],priority='5',mutate=source)
        e.step();row=e.scheduler_description()['tasks'][1]
        self.assertEqual((e.memory.read('Count1'),row['executions'],row['event_instruction_overlaps'],row['event_pending_requests_coalesced']),(1,1,1,2))
        e.step();row=e.scheduler_description()['tasks'][1]
        self.assertEqual((row['executions'],row['event_instruction_overlaps'],row['event_pending_requests_coalesced']),(2,2,4))
        candidate=Engine(e.project);candidate._task_scheduler.continue_from(e._task_scheduler)
        self.assertEqual(candidate.scheduler_description(),e.scheduler_description())
        e.enter_run();row=e.scheduler_description()['tasks'][1]
        self.assertEqual((row['executions'],row['event_instruction_overlaps'],row['event_pending_requests_coalesced']),(0,0,0))

    def test_newly_eligible_event_runs_before_preempted_caller_resumes(self):
        e=self.graph([dict(Priority='5'),dict(Type='EVENT',Priority='1'),dict(Type='EVENT',Priority='3')],
                     [['EVENT(Task1);','MOV(Count2,SpeedCommand);'],
                      ['EVENT(Task2);','MOV(Count2,SpeedSetpoint);'],['ADD(Count2,1,Count2);']]);e.step()
        self.assertEqual((e.memory.read('Count2'),e.memory.read('SpeedSetpoint'),e.memory.read('SpeedCommand')),(1,0,1))

    def test_deep_child_queue_waits_for_each_active_priority_boundary(self):
        e=self.graph([dict(Type='CONTINUOUS'),dict(Type='EVENT',Priority='7'),dict(Type='EVENT',Priority='1'),dict(Type='EVENT',Priority='10')],
                     [['EVENT(Task1);','MOV(Count3,SpeedCommand);'],['EVENT(Task2);','MOV(Count3,SpeedSetpoint);'],
                      ['EVENT(Task3);'],['ADD(Count3,1,Count3);']]);e.step()
        self.assertEqual((e.memory.read('SpeedSetpoint'),e.memory.read('SpeedCommand'),e.memory.read('Count3')),(0,1,1))

    def test_active_cross_task_retrigger_is_discarded_without_pending_replay(self):
        e=self.graph([dict(Type='CONTINUOUS'),dict(Type='EVENT',Priority='5'),dict(Type='EVENT',Priority='1')],
                     [['EVENT(Task1);'],['ADD(Count1,1,Count1);','EVENT(Task2);'],['EVENT(Task1);']]);e.step()
        row=e.scheduler_description()['tasks'][1]
        self.assertEqual((e.memory.read('Count1'),row['executions'],row['event_instruction_overlaps'],row['event_pending_requests_coalesced']),(1,1,1,0))

    def test_completed_pending_task_can_be_triggered_again_in_same_advance(self):
        e=self.graph([dict(Priority='2'),dict(Type='EVENT',Priority='5'),dict(Type='EVENT',Priority='6')],
                     [['EVENT(Task1);','EVENT(Task2);'],['ADD(Count1,1,Count1);'],['EVENT(Task1);','MOV(Count1,SpeedCommand);']]);e.step()
        self.assertEqual((e.memory.read('Count1'),e.memory.read('SpeedCommand')),(2,2))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],2)

    def test_pending_work_drains_before_advancing_to_later_periodic_timestamp(self):
        e=self.graph([dict(Rate='10',Priority='2'),dict(Type='EVENT',Priority='5')],
                     [['ADD(Count0,1,Count0);','EVENT(Task1);','MOV(Count1,SpeedCommand);'],['ADD(Count1,1,Count1);','TON(StartDelay,?,?);']]);e.step(30)
        self.assertEqual((e.memory.read('Count0'),e.memory.read('Count1'),e.memory.read('SpeedCommand'),e.memory.read('StartDelay.ACC')),(3,3,2,20))
        self.assertEqual([(t['task'],t['release_ms']) for t in e.trace if t['number']=='0'],
                         [('Task0',10),('Task1',10),('Task0',20),('Task1',20),('Task0',30),('Task1',30)])
        e.step(5);self.assertEqual(e.trace,[]);self.assertEqual(e.memory.read('Count1'),3)

    def test_queued_cycle_uses_iteration_and_real_release_budget_instead_of_recursion(self):
        e=self.graph([dict(Priority='2'),dict(Type='EVENT',Priority='5'),dict(Type='EVENT',Priority='5')],
                     [['EVENT(Task1);'],['ADD(Count1,1,Count1);','EVENT(Task2);'],['ADD(Count2,1,Count2);','EVENT(Task1);']])
        before=copy.deepcopy(e.memory.values);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaisesRegex(ModelError,'release budget'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        self.assertIsNone(e._event_dispatch);self.assertEqual(e._program_scanned,set())

    def test_fault_before_deferred_execution_discards_pending_work_and_diagnostics(self):
        e=self.graph([dict(Priority='2'),dict(Type='EVENT',Priority='5')],
                     [['EVENT(Task1);','EVENT(Task1);','DIV(1,0,SpeedCommand);'],['ADD(Count1,1,Count1);']])
        before=copy.deepcopy(e.memory.values);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaisesRegex(ModelError,'rolled back'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)

    def test_deferred_fault_rolls_back_completed_tasks_and_retry_has_no_stale_queue(self):
        e=self.graph([dict(Priority='2'),dict(Type='EVENT',Priority='5'),dict(Type='EVENT',Priority='6')],
                     [['EVENT(Task1);','EVENT(Task1);','EVENT(Task2);'],['ADD(Count1,1,Count1);','TON(StartDelay,?,?);'],
                      ['DIV(10,SpeedSetpoint,SpeedCommand);']])
        e.memory.write('SpeedSetpoint',0);before=copy.deepcopy(e.memory.values);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaisesRegex(ModelError,'rolled back'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        self.assertEqual(e._program_scanned,set());e.memory.write('SpeedSetpoint',2);e.step()
        self.assertEqual((e.memory.read('Count1'),e.memory.read('SpeedCommand')),(1,5))
        self.assertEqual([t['executions'] for t in e.scheduler_description()['tasks']],[1,1,1])
        self.assertEqual(e.scheduler_description()['tasks'][1]['event_pending_requests_coalesced'],1)

    def test_later_base_fault_rolls_back_already_completed_deferred_task(self):
        e=self.graph([dict(Priority='2'),dict(Type='EVENT',Priority='5'),dict(Priority='6')],
                     [['EVENT(Task1);'],['ADD(Count1,1,Count1);'],['DIV(1,0,SpeedCommand);']])
        before=copy.deepcopy(e.memory.values);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaisesRegex(ModelError,'rolled back'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)

    def test_deferred_task_shares_global_instruction_budget(self):
        e=self.graph([dict(Priority='2'),dict(Type='EVENT',Priority='5')],
                     [['EVENT(Task1);'],['ADD(Count1,1,Count1);']*30]);e.instruction_limit=20
        before=copy.deepcopy(e.memory.values);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)

    def test_prescan_never_triggers_events_but_initializes_event_timer(self):
        def saved(root):root.find('./Controller/Tags/Tag[@Name="StartDelay"]/Data/Structure/DataValueMember[@Name="ACC"]').set('Value','123')
        e=self.checked([['EVENT(Task1);'],['TON(StartDelay,?,?);']],mutate=saved,defer=True)
        self.assertEqual(e.memory.read('StartDelay.ACC'),123);e.enter_run()
        self.assertEqual(e.memory.read('StartDelay.ACC'),0);self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],0)

    def test_event_timer_elapsed_uses_trigger_timestamp_across_inactive_steps(self):
        e=self.checked([['XIC(StartPB)EVENT(Task1);'],['TON(StartDelay,?,?);']]);e.memory.write('StartPB',True);e.step()
        e.memory.write('StartPB',False);e.step(20);self.assertEqual(e.memory.read('StartDelay.ACC'),0)
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('StartDelay.ACC'),30)

    def test_run_entry_rearms_event_first_scan_and_resets_runtime_diagnostics(self):
        e=self.checked([['EVENT(Task1);'],['ADD(Count1,1,Count1);','XIC(S:FS)ADD(First1,1,First1);','EVENT(Task1);']]);e.step();e.step()
        e.enter_run();self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],0);e.step()
        self.assertEqual(e.memory.read('Count1'),3);self.assertEqual(e.memory.read('First1'),2)
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)

    def test_unknown_target_expression_and_bad_arity_block_even_on_false_rungs(self):
        for text in ('EVENT(Missing);','EVENT();','EVENT(Task1,1);','EVENT(Task1[0]);','EVENT(1);','AFI()EVENT(Missing);'):
            self.assertTrue(self.engine([[text],['NOP();']]).blockers,text)

    def test_event_source_requires_explicit_trigger_timeout_priority_and_unambiguous_shape(self):
        for change in ('missing','duplicate','case','timeout','trigger','tag','priority','inhibit'):
            def invalid(root):
                task=root.find('./Controller/Tasks/Task[2]');info=task.find('EventInfo')
                if change=='missing':task.remove(info)
                elif change=='duplicate':task.append(copy.deepcopy(info))
                elif change=='case':info.tag='eventinfo'
                elif change=='timeout':info.set('EnableTimeout','true')
                elif change=='trigger':info.set('EventTrigger','Consumed Tag')
                elif change=='tag':info.set('EventTag','TagSource')
                elif change=='priority':task.attrib.pop('Priority')
                else:task.set('inhibittask','false')
            self.assertTrue(self.engine(mutate=invalid).blockers,change)

    def test_safety_incomplete_and_other_controller_profiles_remain_blocked(self):
        def safety(root):root.find('./Controller/Tasks/Task[2]').set('Class','Safety')
        def incomplete(root):root.set('ContainsContext','true')
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        for mutation in (safety,incomplete,old):self.assertTrue(self.engine(mutate=mutation).blockers)

    def test_routine_harness_and_for_calls_are_explicitly_unqualified(self):
        e=self.checked([['EVENT(Task1);'],['NOP();']]);harness=Engine(e.project,'routine','Program0/Main');self.assertTrue(harness.blockers)
        e=self.engine([['FOR SpeedCommand:=0 TO 2 DO EVENT(Task1); END_FOR;'],['NOP();']],st=True)
        self.assertTrue(e.blockers);self.assertIn('FOR',str(e.blockers))

    def test_while_condition_observes_event_writes_and_instruction_budget_is_shared(self):
        e=self.checked([['WHILE Count1<3 DO EVENT(Task1); END_WHILE;'],['ADD(Count1,1,Count1);']],st=True);e.step()
        self.assertEqual(e.memory.read('Count1'),3);self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],3)
        e=self.checked([['WHILE TRUE DO EVENT(Task1); END_WHILE;'],['ADD(Count1,1,Count1);']],st=True);e.instruction_limit=30
        before=copy.deepcopy(e.memory.values);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)

    def test_events_share_the_real_per_advance_release_limit(self):
        e=self.checked([['WHILE Count1<4096 DO EVENT(Task1); END_WHILE;'],['ADD(Count1,1,Count1);']],st=True)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'release budget'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],0)

    def test_unchanged_scheduler_graph_carries_event_progress_and_overlap_history(self):
        e=self.checked([['EVENT(Task1);'],['ADD(Count1,1,Count1);','EVENT(Task1);']]);e.step()
        candidate=Engine(e.project);self.assertEqual(candidate.blockers,[])
        candidate._task_scheduler.continue_from(e._task_scheduler)
        self.assertEqual(candidate.scheduler_description(),e.scheduler_description())

    def test_report_does_not_claim_native_cpu_timing_or_full_event_sources(self):
        e=self.checked();report=e.report()['event_execution']
        self.assertEqual(report['languages'],['RLL','ST']);self.assertFalse(report['native_cpu_timing']);self.assertFalse(report['native_status_parity'])
        self.assertIn('native pending-duplicate parity unverified',report['pending_policy'])


    def test_bundled_event_lab_mixes_rll_st_and_active_self_request_diagnostics(self):
        from pathlib import Path
        from logixlab.model import Project
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/EventLab.L5X'));self.assertEqual(e.blockers,[])
        e.memory.write('TriggerRLL',True);e.memory.write('TriggerST',True);e.memory.write('SelfTrigger',True);e.step()
        self.assertEqual(e.memory.read('EventCount'),2);self.assertEqual(e.memory.read('RllSeen'),1);self.assertEqual(e.memory.read('StSeen'),2)
        self.assertEqual(e.memory.read('EventFirst'),1);self.assertEqual(e.scheduler_description()['tasks'][2]['event_instruction_overlaps'],2)

    def test_bundled_event_lab_demonstrates_deferred_observations_and_merged_duplicates(self):
        from pathlib import Path
        from logixlab.model import Project
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/EventLab.L5X'));self.assertEqual(e.blockers,[])
        e.memory.write('TriggerDeferred',True)
        for i in range(1,4):
            e.step();self.assertEqual([e.memory.read(n) for n in ('DeferredCount','RllDeferredSeen','StDeferredSeen','DeferredFirst')],[i,i-1,i,1])
            row=e.scheduler_description()['tasks'][3]
            self.assertEqual((row['executions'],row['event_pending_requests_coalesced'],row['event_instruction_overlaps']),(i,i,0))
        self.assertEqual(e.memory.read('DeferredTimer.ACC'),20)
        e.memory.write('TriggerDeferred',False);e.step(20);self.assertEqual(e.memory.read('DeferredCount'),3)


if __name__=='__main__':unittest.main()
