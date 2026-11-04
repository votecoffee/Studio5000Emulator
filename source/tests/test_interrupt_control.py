"""Balanced task-local UID/UIE, priority boundaries and transaction rollback."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_event_tasks as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class InterruptControlTests(unittest.TestCase):
    setUp = fixtures.EventTaskTests.setUp
    engine = fixtures.EventTaskTests.engine
    graph = fixtures.EventTaskTests.graph
    checked = fixtures.EventTaskTests.checked

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.calls.stack, e.scan_count, e.time_ms,
                              e.last_timer, e.trace, e.scheduler_description(), e._program_scanned))

    def fails(self, e, expected):
        e.enter_run(); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, expected):e.step()
        self.assertEqual(self.snapshot(e), before); self.assertIsNone(e._event_dispatch); self.assertIsNone(e._executing_task)

    def test_nested_mask_drains_only_at_outer_enable_before_next_instruction(self):
        e = self.checked([['UID()UID()EVENT(Task1)MOV(Count1,SpeedCommand);', 'UIE()MOV(Count1,SpeedSetpoint);', 'UIE()MOV(Count1,Count0);'],
                          ['ADD(Count1,1,Count1);']]); e.step()
        self.assertEqual(tuple(e.memory.read(n) for n in ('SpeedCommand', 'SpeedSetpoint', 'Count0', 'Count1')), (0, 0, 1, 1))
        e.step(); self.assertEqual(e.memory.read('Count1'), 2); self.assertEqual(e.memory.read('Count0'), 2)

    def test_false_rungs_prescan_and_disabled_mcr_do_not_change_depth(self):
        e = self.checked([['AFI()UID();', 'EVENT(Task1)MOV(Count1,SpeedCommand);', 'AFI()UIE();',
                           'AFI()MCR();', 'UID()UIE();', 'MCR();'], ['ADD(Count1,1,Count1);']], defer=True)
        e.enter_run(); self.assertEqual(e.memory.read('Count1'), 0); self.assertIsNone(e._event_dispatch)
        e.step(); self.assertEqual(e.memory.read('SpeedCommand'), 1)

    def test_queued_duplicates_keep_priority_fifo_and_existing_diagnostics(self):
        e = self.graph([dict(Type='CONTINUOUS'), dict(Type='EVENT', Priority='1'), dict(Type='EVENT', Priority='2')],
                       [['UID();', 'EVENT(Task2);', 'EVENT(Task1);', 'EVENT(Task1);', 'UIE();'],
                        ['ADD(Count1,1,Count1);', 'EVENT(Task1);'], ['ADD(Count2,1,Count2);']]); e.step()
        self.assertEqual([t['task'] for t in e.trace if t['task'] != 'Task0' and t['number'] == '0'], ['Task1', 'Task2'])
        row = e.scheduler_description()['tasks'][1]
        self.assertEqual((row['executions'], row['event_pending_requests_coalesced'], row['event_instruction_overlaps']), (1, 1, 1))

    def test_lower_and_equal_priorities_still_wait_for_task_return(self):
        for priority in ('5', '10'):
            def periodic(root):
                t = root.find('./Controller/Tasks/Task'); t.set('Type', 'PERIODIC'); t.set('Priority', '5')
            e = self.checked([['UID()EVENT(Task1)UIE()MOV(Count1,SpeedCommand);'], ['ADD(Count1,1,Count1);']], priority=priority, mutate=periodic)
            e.step(); self.assertEqual((e.memory.read('SpeedCommand'), e.memory.read('Count1')), (0, 1))

    def test_depth_is_shared_across_jsr_and_ladder_loop_calls(self):
        def sub(root):
            routines = root.find('./Controller/Programs/Program/Routines')
            content = E.SubElement(E.SubElement(routines, 'Routine', Name='Worker', Type='RLL'), 'RLLContent')
            E.SubElement(E.SubElement(content, 'Rung', Number='0', Type='N'), 'Text').text = 'UID()EVENT(Task1)UIE();'
        for call in ('JSR(Worker,0)', 'FOR(Worker,Count0,0,1,1)'):
            e = self.checked([['UID()' + call + 'MOV(Count1,SpeedCommand)UIE()MOV(Count1,SpeedSetpoint);'], ['ADD(Count1,1,Count1);']], mutate=sub)
            e.step(); self.assertEqual((e.memory.read('SpeedCommand'), e.memory.read('SpeedSetpoint')), (0, 1)); self.assertEqual(e.calls.stack, [])

    def test_balanced_depth_can_span_programs_in_the_same_task(self):
        def extra(root):
            programs = root.find('./Controller/Programs'); p = copy.deepcopy(programs[0]); p.set('Name', 'OtherProgram')
            content = p.find('./Routines/Routine/RLLContent'); content.clear()
            E.SubElement(E.SubElement(content, 'Rung', Number='0', Type='N'), 'Text').text = 'UIE()MOV(Count1,SpeedCommand);'
            programs.append(p); E.SubElement(root.find('./Controller/Tasks/Task/ScheduledPrograms'), 'ScheduledProgram', Name='OtherProgram')
        e = self.checked([['UID()EVENT(Task1);'], ['ADD(Count1,1,Count1);']], mutate=extra); e.step()
        self.assertEqual(e.memory.read('SpeedCommand'), 1)

    def test_child_has_its_own_depth_and_can_release_higher_priority_work(self):
        e = self.graph([dict(Type='CONTINUOUS'), dict(Type='EVENT', Priority='3'), dict(Type='EVENT', Priority='1')],
                       [['UID()EVENT(Task1)UIE()MOV(Count2,Count0);'],
                        ['UID()EVENT(Task2)MOV(Count2,Count1)UIE()MOV(Count2,SpeedCommand);'], ['ADD(Count2,1,Count2);']]); e.step()
        self.assertEqual(tuple(e.memory.read(n) for n in ('Count1', 'SpeedCommand', 'Count0')), (0, 1, 1))

    def test_structured_text_calls_and_while_iterations_share_the_task_mask(self):
        e = self.checked([['UID(); UID(); EVENT(Task1); SpeedCommand:=Count1; UIE(); SpeedSetpoint:=Count1; UIE(); Count0:=Count1;'],
                          ['ADD(Count1,1,Count1);']], st=True); e.step()
        self.assertEqual(tuple(e.memory.read(n) for n in ('SpeedCommand', 'SpeedSetpoint', 'Count0')), (0, 0, 1))
        e = self.checked([['Count0:=0; WHILE Count0<2 DO UID(); EVENT(Task1); UIE(); Count0:=Count0+1; END_WHILE;'],
                          ['ADD(Count1,1,Count1);']], st=True); e.step(); self.assertEqual(e.memory.read('Count1'), 2)

    def test_unmatched_enable_and_task_return_are_explicit_atomic_guards(self):
        for body, expected in [(['ADD(Count0,1,Count0)UIE();'], 'requires an active UID'),
                               (['UID()EVENT(Task1);'], 'Unbalanced UID/UIE'),
                               (['UID()UID()EVENT(Task1)UIE();'], 'Unbalanced UID/UIE')]:
            e = self.checked([body, ['ADD(Count1,1,Count1);']]); self.fails(e, expected)
        e = self.checked([['UID()EVENT(Task1)UIE();'], ['UIE();']]); self.fails(e, 'requires an active UID')

    def test_child_and_later_faults_restore_pending_writes_first_scans_and_retry(self):
        for child in (True, False):
            bodies = [['UID()EVENT(Task1)UIE()ADD(Count0,1,Count0);'], ['ADD(Count1,1,Count1);']]
            bodies[1 if child else 0].append('DIV(1,SpeedSetpoint,SpeedCommand);')
            e = self.checked(bodies); e.memory.write('SpeedSetpoint', 0); self.fails(e, 'zero')
            e.memory.write('SpeedSetpoint', 1); e.step(); self.assertEqual((e.memory.read('Count0'), e.memory.read('Count1')), (1, 1))

    def test_instruction_budget_and_run_entry_do_not_leave_a_mask_or_queue(self):
        e = self.checked([['UID(); WHILE TRUE DO EVENT(Task1); END_WHILE;'], ['ADD(Count1,1,Count1);']], st=True)
        e.instruction_limit = 80; self.fails(e, 'budget')
        with self.assertRaisesRegex(ModelError, 'Reset the faulted project'):e.enter_run()
        e = Engine(e.project); e.enter_run(); self.assertEqual(e.memory.read('Count1'), 0); self.assertIsNone(e._event_dispatch)

    def test_profile_harness_aoi_arguments_and_st_for_forms_are_guarded(self):
        e = self.checked([['UID()UIE();'], ['NOP();']]); self.assertTrue(Engine(e.project, 'routine', 'Program0/Main').blockers)
        for body in ('UID(Count0);', 'UIE(1);'):
            self.assertTrue(self.engine([[body], ['NOP();']]).blockers)
        for version, processor in (('34', '1756-L85E'), ('35', '1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev', version); root.find('Controller').set('ProcessorType', processor)
            self.assertTrue(self.engine([['AFI()UID();'], ['NOP();']], mutate=profile).blockers)
        self.assertTrue(self.engine([['FOR Count0:=0 TO 1 DO UID(); UIE(); END_FOR;'], ['NOP();']], st=True).blockers)
        path = Path(__file__).resolve().parents[1] / 'samples/AOILab.L5X'; root = E.parse(path).getroot()
        root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text').text = 'UID()UIE();'
        path = Path(self.tmp.name) / 'aoi.L5X'; E.ElementTree(root).write(path, encoding='utf8', xml_declaration=True); self.assertTrue(Engine(Project(path)).blockers)

    def test_report_states_software_guards_and_unchanged_timing_boundaries(self):
        e = self.checked([['UID()UIE();'], ['NOP();']]); row = e.report()['user_interrupts']
        self.assertEqual(row['languages'], ['RLL', 'ST']); self.assertIn('outermost', row['nesting']); self.assertFalse(row['native_runtime_parity'])
        self.assertTrue({'UID', 'UIE'} <= set(e.report()['supported_instructions'])); self.assertIn('Unmasked', e.report()['event_execution']['dispatch'])


if __name__ == '__main__':unittest.main()
