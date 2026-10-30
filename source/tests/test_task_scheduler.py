"""Deterministic continuous/periodic scheduling, separate from CPU timing."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class TaskSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def engine(self, specs, bodies=None, *, mutate=None, defer=False):
        root = E.parse(Path(__file__).resolve().parents[1] / 'samples/ConveyorDemo.L5X').getroot()
        c = root.find('Controller'); programs = c.find('Programs'); programs.clear()
        tasks = c.find('Tasks'); tasks.clear(); tags = c.find('Tags')
        for i, spec in enumerate(specs):
            for name in (f'Count{i}', f'First{i}'):
                tag = E.SubElement(tags, 'Tag', Name=name, DataType='DINT', TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='0')
            name = f'Program{i}'
            p = E.SubElement(programs, 'Program', Name=name, MainRoutineName='Main', Class='Standard')
            E.SubElement(p, 'Tags')
            content = E.SubElement(E.SubElement(E.SubElement(p, 'Routines'), 'Routine', Name='Main', Type='RLL'), 'RLLContent')
            rungs = bodies[i] if bodies is not None else [f'ADD(Count{i},1,Count{i});', f'XIC(S:FS)ADD(First{i},1,First{i});']
            for n, text in enumerate(rungs): E.SubElement(E.SubElement(content, 'Rung', Number=str(n), Type='N'), 'Text').text = text
            attrs = dict(Name=f'Task{i}', Type='PERIODIC', Class='Standard', Rate='10', Priority='10', InhibitTask='false')
            attrs.update(spec)
            t = E.SubElement(tasks, 'Task', **attrs)
            E.SubElement(E.SubElement(t, 'ScheduledPrograms'), 'ScheduledProgram', Name=name)
        if mutate: mutate(root)
        path = Path(self.tmp.name) / 'tasks.L5X'
        E.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
        return Engine(Project(path), defer_prescan=defer)

    def mixed(self, **kwargs):
        return self.engine([dict(Type='CONTINUOUS'), dict(Rate='10', Priority='2'), dict(Rate='25', Priority='5')], **kwargs)

    def counts(self, e): return [e.memory.read(f'Count{i}') for i in range(3)]

    def test_continuous_and_two_periodic_tasks_follow_independent_rates(self):
        e = self.mixed(); self.assertEqual(e.blockers, [])
        e.step(10); self.assertEqual(self.counts(e), [1, 1, 0])
        e.step(10); self.assertEqual(self.counts(e), [2, 2, 0])
        e.step(10); self.assertEqual(self.counts(e), [3, 3, 1])
        self.assertEqual(e.time_ms, 30)

    def test_long_step_preserves_every_release_and_timestamp(self):
        e = self.mixed(); self.assertEqual(e.blockers, []); e.step(50)
        self.assertEqual(self.counts(e), [1, 5, 2])
        rows = [(x['task'], x['release_ms']) for x in e.trace if x['number'] == '0']
        self.assertEqual(rows, [('Task1', 10), ('Task1', 20), ('Task2', 25), ('Task1', 30),
                                ('Task1', 40), ('Task1', 50), ('Task2', 50), ('Task0', 50)])

    def test_priority_orders_simultaneous_releases_and_source_order_breaks_ties(self):
        for priorities, expected in ((('9', '1'), ['Task1', 'Task0']), (('4', '4'), ['Task0', 'Task1'])):
            e = self.engine([dict(Priority=priorities[0]), dict(Priority=priorities[1])])
            self.assertEqual(e.blockers, []); e.step(10)
            self.assertEqual([x['task'] for x in e.trace if x['number'] == '0'], expected)

    def test_step_boundaries_do_not_replay_a_release(self):
        e = self.mixed(); self.assertEqual(e.blockers, [])
        for dt in (7, 3, 15, 5): e.step(dt)
        self.assertEqual(self.counts(e), [4, 3, 1])
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'], 40)

    def test_periodic_only_project_can_advance_without_an_execution(self):
        e = self.engine([dict(Rate='10'), dict(Rate='25')]); self.assertEqual(e.blockers, [])
        e.step(5); self.assertEqual(e.trace, [])
        self.assertEqual(e.memory.read('Count0'), 0)
        e.step(5); self.assertEqual(e.memory.read('Count0'), 1)

    def test_first_scan_is_independent_for_each_program(self):
        e = self.mixed(); self.assertEqual(e.blockers, [])
        for _ in range(6): e.step(5)
        self.assertEqual([e.memory.read(f'First{i}') for i in range(3)], [1, 1, 1])
        e.enter_run()
        for _ in range(5): e.step(5)
        self.assertEqual([e.memory.read(f'First{i}') for i in range(3)], [2, 2, 2])

    def test_mode_transition_restarts_periodic_phase_at_current_time(self):
        e = self.mixed(); e.step(7); e.enter_run(); e.step(9)
        self.assertEqual(self.counts(e), [2, 0, 0])
        e.step(1); self.assertEqual(self.counts(e), [3, 1, 0])
        self.assertEqual(e.time_ms, 17)

    def test_inhibited_task_is_prescanned_without_normal_execution(self):
        def initial(root):
            root.find("./Controller/Tags/Tag[@Name='StartDelay']/Data/Structure/DataValueMember[@Name='ACC']").set('Value', '123')
        e = self.engine([dict(Type='CONTINUOUS'), dict(InhibitTask='true')],
                        [['NOP();'], ['TON(StartDelay,?,?);']], mutate=initial)
        self.assertEqual(e.blockers, []); e.step(20)
        self.assertEqual(e.memory.read('StartDelay.ACC'), 0)
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'], 0)

    def test_all_inhibited_tasks_can_advance_clock_without_executing(self):
        e = self.engine([dict(InhibitTask='true')]); self.assertEqual(e.blockers, [])
        e.step(10); self.assertEqual(e.memory.read('Count0'), 0)
        self.assertEqual(e.trace, []); self.assertEqual(e.time_ms, 10)

    def test_periodic_timer_elapsed_uses_release_time_not_outer_step_end(self):
        e = self.engine([dict(Type='CONTINUOUS'), dict(Rate='10')],
                        [['NOP();'], ['TON(StartDelay,?,?);']])
        self.assertEqual(e.blockers, []); e.step(40)
        self.assertEqual(e.memory.read('StartDelay.ACC'), 30)

    def test_failure_rolls_back_values_clock_phase_counts_and_first_scan(self):
        e = self.mixed(bodies=[['NOP();'], ['ADD(Count1,1,Count1);', 'XIC(S:FS)ADD(First1,1,First1);'], ['DIV(1,0,Count2);']])
        self.assertEqual(e.blockers, [])
        before = copy.deepcopy(e.scheduler_description())
        with self.assertRaisesRegex(ModelError, 'rolled back'): e.step(30)
        self.assertEqual(self.counts(e), [0, 0, 0]); self.assertEqual(e.memory.read('First1'), 0)
        self.assertEqual(e.time_ms, 0); self.assertEqual(e.scheduler_description(), before)

    def test_invalid_rates_priorities_duplicate_programs_and_continuous_tasks_block(self):
        for spec in (dict(Rate='0'), dict(Rate='0.5'), dict(Rate='NaN'), dict(Rate='60001'),
                     dict(Priority='0'), dict(Priority='16'), dict(Priority='bad')):
            with self.subTest(spec=spec): self.assertTrue(self.engine([spec]).blockers)
        self.assertTrue(self.engine([dict(Type='CONTINUOUS'), dict(Type='CONTINUOUS')]).blockers)
        def duplicate(root):
            root.find('./Controller/Tasks/Task[2]/ScheduledPrograms/ScheduledProgram').set('Name', 'Program0')
        self.assertTrue(self.mixed(mutate=duplicate).blockers)

    def test_event_and_safety_tasks_remain_blocked(self):
        for spec in (dict(Type='EVENT'), dict(Class='Safety')):
            self.assertTrue(self.engine([dict(Type='CONTINUOUS'), spec]).blockers)

    def test_single_periodic_interval_contract_is_preserved(self):
        e = self.engine([dict(Rate='20')]); self.assertEqual(e.blockers, [])
        with self.assertRaisesRegex(ModelError, '20 ms'): e.step(10)
        e.step(20); self.assertEqual(e.memory.read('Count0'), 1)

    def test_routine_harness_ignores_scheduler_and_task_rates(self):
        e = self.mixed(); harness = Engine(e.project, 'routine', 'Program2/Main')
        self.assertEqual(harness.blockers, []); harness.step(1)
        self.assertEqual(self.counts(harness), [0, 0, 1])

    def test_release_budget_rejects_huge_advance_without_state_changes(self):
        e = self.engine([dict(Type='CONTINUOUS'), dict(Rate='1')]); self.assertEqual(e.blockers, [])
        before = copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError, 'release budget'): e.step(60000)
        self.assertEqual(e.memory.values, before); self.assertEqual(e.time_ms, 0)

    def test_changed_source_task_configuration_requires_reload(self):
        e = self.mixed(); self.assertEqual(e.blockers, [])
        e.project.tasks[1]['rate'] = '20'
        with self.assertRaisesRegex(ModelError, 'configuration changed'): e.step(10)

    def test_multi_task_counts_do_not_invent_native_measurements(self):
        e = self.mixed(); self.assertEqual(e.blockers, []); e.step(30)
        for task in e.project.tasks:
            self.assertEqual(e.task_measurement_attributes(task['name'], source_sha256=e.project.sha256), {})
            self.assertEqual(e.task_status_attributes(task['name'], source_sha256=e.project.sha256), {})
        self.assertEqual([t['executions'] for t in e.scheduler_description()['tasks']], [1, 3, 1])

    def test_structured_text_program_uses_its_task_release_and_trace_context(self):
        def st(root):
            routine = root.find("./Controller/Programs/Program[@Name='Program1']/Routines/Routine")
            routine.clear(); routine.set('Name', 'Main'); routine.set('Type', 'ST')
            E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0').text = 'Count1:=Count1+1;'
        e = self.mixed(mutate=st); self.assertEqual(e.blockers, []); e.step(30)
        self.assertEqual(e.memory.read('Count1'), 3)
        rows = [(x['task'], x['release_ms']) for x in e.trace if x.get('language') == 'ST']
        self.assertEqual(rows, [('Task1', 10), ('Task1', 20), ('Task1', 30)])

    def test_scheduled_program_order_and_first_scan_within_one_task(self):
        def combine(root):
            tasks = root.find('./Controller/Tasks')
            source = tasks[1].find('ScheduledPrograms'); node = source[0]; source.remove(node)
            tasks[0].find('ScheduledPrograms').append(node)
        e = self.engine([dict(Type='CONTINUOUS'), {}],
                        [['MOV(1,SpeedCommand);', 'XIC(S:FS)ADD(First0,1,First0);'],
                         ['ADD(SpeedCommand,2,SpeedCommand);', 'XIC(S:FS)ADD(First1,1,First1);']], mutate=combine)
        self.assertEqual(e.blockers, []); e.step(10); e.step(10)
        self.assertEqual(e.memory.read('SpeedCommand'), 3)
        self.assertEqual([e.memory.read('First0'), e.memory.read('First1')], [1, 1])

    def test_bundled_task_lab_counts_and_timer_are_repeatable(self):
        path = Path(__file__).resolve().parents[1] / 'samples/TaskLab.L5X'
        e = Engine(Project(path)); self.assertEqual(e.blockers, [])
        for _ in range(3): e.step(10)
        self.assertEqual([e.memory.read(x) for x in ('BackgroundCount', 'FastCount', 'SlowCount')], [3, 3, 1])
        self.assertEqual([e.memory.read(x) for x in ('BackgroundFirst', 'FastFirst', 'SlowFirst')], [1, 1, 1])
        self.assertEqual(e.memory.read('FastTimer.ACC'), 20)
        self.assertFalse(e.first_scan_pending)

    def test_blocked_project_reports_first_scan_state_without_missing_routine_lookup(self):
        def missing(root): root.find('./Controller/Programs/Program').set('MainRoutineName', 'Missing')
        e = self.mixed(mutate=missing)
        self.assertTrue(e.blockers)
        self.assertIsInstance(e.first_scan_pending, bool)

    def test_routine_replacement_preserves_phase_counts_and_program_first_scan_state(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container, xml_source
        e = self.mixed(); e.step(30)
        before = copy.deepcopy(e.scheduler_description())
        source = decode(container(E.tostring(xml_source(name='Main', text='NOP();'), encoding='utf-8')))
        candidate, _ = prepare(e, source, ('NOP();',), 'Program0', 0)
        self.assertEqual(candidate.scheduler_description(), before)
        self.assertEqual(candidate._program_scanned, e._program_scanned)
        self.assertIs(candidate._task_scheduler.source, candidate.project.tasks)
        candidate.step(5)
        self.assertEqual([candidate.memory.read(f'Count{i}') for i in range(3)], [1, 3, 1])
        self.assertEqual([candidate.memory.read(f'First{i}') for i in range(3)], [1, 1, 1])
        self.assertEqual(e.scheduler_description(), before)


if __name__ == '__main__': unittest.main()
