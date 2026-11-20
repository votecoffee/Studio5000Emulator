import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
import test_runtime as fixtures
from logixlab.model import Project,ModelError
from logixlab.runtime import Engine
from logixlab.structured import Parser
from logixlab.server import Application


class StructuredTests(unittest.TestCase):
    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/TextLab.L5X').getroot()

    def text(self,source,name='MainRoutine'):
        content=self.root.find(f'./Controller/Programs/Program/Routines/Routine[@Name="{name}"]/STContent');content.clear()
        for i,line in enumerate(source.split('\n')):E.SubElement(content,'Line',Number=str(i)).text=line

    def engine(self,source=None):
        if source is not None:self.text(source)
        path=Path(self.tmp.name)/'fixture.L5X';E.ElementTree(self.root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path))

    def lreal_tags(self, **values):
        tags = self.root.find('./Controller/Tags')
        for name, value in values.items():
            tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType='LREAL')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue',
                         DataType='LREAL', Value=str(value))

    def test_lreal_binary64_assignments_conditions_and_explicit_literal_precision(self):
        self.lreal_tags(Binary64=1.0000000000000002, Delta=0, Promoted=0, Root=0)
        e = self.engine(
            'Delta := Binary64 - 1.0L; Promoted := 1.0000000000000002; '
            'Done := TRUE AND Binary64 > Promoted; '
            'IF Done AND NOT (Binary64=1e0L) THEN Root:=SQRT(9.0L); END_IF;')
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.read('Delta'), 2**-52)
        self.assertEqual(e.memory.read('Promoted'), 1.0)
        self.assertEqual(e.memory.read('Root'), 3.0)
        self.assertIs(e.memory.read('Done'), True)

    def test_lreal_runtime_faults_roll_back_prior_assignments_and_skip_unreached_branch(self):
        self.lreal_tags(Binary64=1e308, Delta=42)
        for expression, message in (
            ('Binary64/0.0L', 'divide by zero'),
            ('Binary64*2.0L', 'Nonfinite LREAL'),
            ('LN(-1.0L)', 'domain/range'),
        ):
            with self.subTest(expression=expression):
                e = self.engine('State:=17; IF Enable THEN Delta:='+expression+'; END_IF;')
                self.assertEqual(e.blockers, [])
                e.memory.write('Enable', False)
                e.step()
                self.assertEqual(e.memory.read('Delta'), 42)
                e.memory.write('Enable', True)
                e.memory.write('State', 99)
                before = copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError, message):
                    e.step()
                self.assertEqual(e.memory.values, before)

    def test_lreal_rejects_nonfinite_literals_and_unqualified_types_in_false_branches(self):
        self.lreal_tags(Binary64=1.0, Delta=0)
        for statement in (
            'Delta:=1e309L;', 'Delta:=1e309;', 'Delta:=Binary64+1L;', 'Delta:=Binary64+State;',
            'State:=Binary64;', 'Delta:=Binary64 AND Binary64;', 'Delta:=Binary64>0.0L;',
        ):
            with self.subTest(statement=statement):
                self.assertTrue(self.engine('IF FALSE THEN '+statement+' END_IF;').blockers)

    def test_text_lab_full_scan_and_prescan(self):
        e=self.engine();self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.read('ClearedOnRun'),0);self.assertEqual(e.memory.read('ScanTotal'),0)
        self.assertEqual(e.memory.read('Accumulator.Count'),0)
        for _ in range(3):e.step()
        expected={'ScanTotal':3,'ClearedOnRun':17,'Sum':30,'Values':[0,3,6,9,12],'Scaled':61,'CaseResult':20,
                  'WhileCount':3,'RepeatCount':2,'SearchResult':3,'AOITotal':6,'Packed':15,'Done':True,'Truth':True}
        for ref,value in expected.items():self.assertEqual(e.memory.read(ref),value,ref)
        self.assertEqual(e.memory.string('Message'),'SCAN 3');self.assertEqual(e.memory.string('Shadow'),'SCAN 3')

    def time_tag(self, name, dtype, value=None, *, elements=None):
        tags = self.root.find('./Controller/Tags')
        tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType=dtype)
        data = E.SubElement(tag, 'Data', Format='Decorated')
        if elements is None:
            E.SubElement(data, 'DataValue', DataType=dtype, Value=str(value))
        else:
            tag.set('Dimensions', str(len(elements)))
            array = E.SubElement(data, 'Array', DataType=dtype, Dimensions=str(len(elements)))
            for index, item in enumerate(elements):
                if item is not None:
                    E.SubElement(array, 'Element', Index=f'[{index}]', Value=str(item))

    def test_temporal_assignments_copy_exact_types_and_literal_ticks(self):
        expected = {}
        lines = []
        for dtype, source, ticks in (
            ('TIME32', 'T32#-1ms_2us', -1002),
            ('TIME', 'T#1s_3us', 1000003),
            ('LTIME', 'LT#1s_1ns', 1000000001),
            ('DT', 'DT#1970-01-01-05:30:00.000_001(UTC+05:30)', 1),
            ('LDT', 'LDT#2020-10-25-11:05:20.123_456_789', 1603623920123456789),
        ):
            formal, result = 'Source' + dtype, 'Result' + dtype
            self.time_tag(formal, dtype, 0)
            self.time_tag(result, dtype, 0)
            lines.extend([f'{formal}:={source};', f'{result}:={formal};'])
            expected[formal] = expected[result] = ticks

        e = self.engine('\n'.join(lines))
        self.assertEqual(e.blockers, [])
        e.step()
        for name, ticks in expected.items():
            self.assertEqual(e.memory.read(name, allow_time=True), ticks)

    def test_temporal_assignment_resolves_indirect_alias_only_in_reached_branch(self):
        ticks = 1603623920123456789
        self.time_tag('SavedTimes', 'LDT', elements=(None, ticks))
        self.time_tag('ResultTimes', 'LDT', elements=(None, None))
        tags = self.root.find('./Controller/Tags')
        E.SubElement(tags, 'Tag', Name='TimeView', TagType='Alias', AliasFor='SavedTimes')
        e = self.engine('IF Enable THEN ResultTimes[BitIndex]:=TimeView[Selector]; END_IF;')
        self.assertEqual(e.blockers, [])
        e.memory.write('Enable', False)
        e.memory.write('Selector', 99)
        e.memory.write('BitIndex', 99)
        e.step()
        self.assertEqual(e.memory.read('ResultTimes', allow_time=True), [None, None])
        e.memory.write('Enable', True)
        e.memory.write('Selector', 0)
        e.memory.write('BitIndex', 1)
        before = copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError, 'Unknown initial byte/value'):
            e.step()
        self.assertEqual(e.memory.values, before)
        e.memory.write('Selector', 1)
        e.step()
        self.assertEqual(e.memory.read('ResultTimes', allow_time=True), [None, ticks])

    def test_temporal_nonretentive_assignment_and_late_fault_rollback(self):
        self.time_tag('Stamp', 'LDT', 777)
        e = self.engine(
            'IF FALSE THEN Stamp [:=] LDT#1970-01-01-00:00:00.000_000_001; END_IF; '
            'Stamp:=LDT#2020-10-25-11:05:20.123_456_789; State:=1/0;')
        self.assertEqual(e.blockers, [])
        self.assertEqual(e.memory.read('Stamp', allow_time=True), 0)
        with self.assertRaisesRegex(ModelError, 'zero'):
            e.step()
        self.assertEqual(e.memory.read('Stamp', allow_time=True), 0)
        self.assertEqual(e.scan_count, 0)

    def test_temporal_assignment_converts_exact_ticks_within_each_family(self):
        self.time_tag('Start', 'DT', 1767225600000001)
        self.time_tag('Stamp', 'LDT', 0)
        self.time_tag('Backdated', 'DT', 0)
        self.time_tag('NarrowDelay', 'TIME32', -1002)
        self.time_tag('MicroDelay', 'TIME', 0)
        self.time_tag('NanoDelay', 'LTIME', 0)
        self.time_tag('SelectedDelays', 'TIME32', elements=(11, None, 77))
        e = self.engine(
            'Stamp:=Start; Backdated:=Stamp; '
            'MicroDelay:=NarrowDelay; NanoDelay:=MicroDelay; '
            'SelectedDelays[Selector]:=NanoDelay; '
            'NanoDelay:=T32#-1ms_3us;')
        self.assertEqual(e.blockers, [])
        e.memory.write('Selector', 1)
        e.step()
        expected = {
            'Stamp': 1767225600000001000,
            'Backdated': 1767225600000001,
            'MicroDelay': -1002,
            'NanoDelay': -1003000,
            'SelectedDelays': [11, -1002, 77],
        }
        for ref, value in expected.items():
            self.assertEqual(e.memory.read(ref, allow_time=True), value, ref)

    def test_temporal_assignment_faults_only_when_conversion_is_reached(self):
        self.time_tag('Clock', 'DT', 12)
        self.time_tag('FineDelay', 'LTIME', -1001)
        self.time_tag('CoarseDelay', 'TIME', 34)
        self.time_tag('NarrowDelay', 'TIME32', 56)
        for assignment, message in (
            ('CoarseDelay:=FineDelay;', 'fractional ticks'),
            ('Clock:=LDT#1970-01-01-00:00:00.000_000_001;', 'fractional ticks'),
            ('NarrowDelay:=T#2147483648us;', 'TIME32 requires exact ticks in range'),
        ):
            with self.subTest(assignment=assignment):
                e = self.engine(f'State:=7; IF Enable THEN {assignment} END_IF;')
                self.assertEqual(e.blockers, [])
                e.memory.write('Enable', False)
                e.step()
                self.assertEqual(e.memory.read('State'), 7)
                e.memory.write('State', 5)
                e.memory.write('Enable', True)
                before = copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError, message):
                    e.step()
                self.assertEqual(e.memory.values, before)
                self.assertEqual(e.scan_count, 1)

    def test_temporal_assignment_rejects_cross_family_sources_and_whole_arrays(self):
        self.time_tag('Stamp', 'LDT', 0)
        self.time_tag('Delay', 'TIME', 0)
        self.time_tag('Times', 'LDT', elements=(0, 0))
        for statement, message in (
            ('Stamp:=Delay;', 'source from the same time/date family'),
            ('Delay:=Stamp;', 'source from the same time/date family'),
            ('Stamp:=State;', 'source from the same time/date family'),
            ('Stamp:=1;', 'requires a temporal tag or typed literal'),
            ('Times:=Stamp;', 'requires a scalar destination'),
            ('Stamp:=Times;', 'requires one scalar element'),
        ):
            with self.subTest(statement=statement):
                e = self.engine('IF FALSE THEN ' + statement + ' END_IF;')
                self.assertIn(message, str(e.blockers))

    def test_temporal_arithmetic_keeps_exact_mixed_precision_ticks(self):
        self.time_tag('Clock', 'DT', 1)
        self.time_tag('Delay', 'TIME', 1)
        self.time_tag('FineDelay', 'LTIME', 0)
        self.time_tag('Elapsed', 'LTIME', 0)
        self.time_tag('Times', 'LDT', elements=(None, None))
        self.time_tag('Backdated', 'DT', 0)
        e = self.engine(
            'FineDelay:=Delay+LT#1ns; '
            'Times[0]:=Clock+FineDelay; '
            'Times[1]:=FineDelay+LDT#1970-01-01-00:00:00.000_001_000; '
            'Elapsed:=Clock-Times[0]; '
            'FineDelay:=Delay-FineDelay; '
            'Backdated:=Times[1]-LT#1us_1ns;')
        self.assertEqual(e.blockers, [])
        e.step()
        for ref, ticks in (('FineDelay', -1), ('Elapsed', -1001), ('Times', [2001, 2001]), ('Backdated', 1)):
            self.assertEqual(e.memory.read(ref, allow_time=True), ticks, ref)

    def test_temporal_arithmetic_defers_faults_and_restores_earlier_writes(self):
        self.time_tag('Coarse', 'TIME', 7)
        self.time_tag('Narrow', 'TIME32', 8)
        self.time_tag('Stamp', 'LDT', 9)
        for assignment, message in (
            ('Coarse:=T#1us+LT#1ns;', 'fractional ticks'),
            ('Narrow:=T32#2147483647us+T32#1us;', 'TIME32 requires exact ticks in range'),
            ('Stamp:=LDT#1970-01-01-00:00:00-LT#1ns;', 'LDT requires exact ticks in range'),
        ):
            with self.subTest(assignment=assignment):
                e = self.engine(f'State:=7; IF Enable THEN {assignment} END_IF;')
                self.assertEqual(e.blockers, [])
                e.memory.write('Enable', False)
                e.step()
                self.assertEqual(e.memory.read('State'), 7)
                e.memory.write('State', 5)
                e.memory.write('Enable', True)
                before = copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError, message):
                    e.step()
                self.assertEqual(e.memory.values, before)
                self.assertEqual(e.scan_count, 1)

    def test_temporal_arithmetic_rejects_unsupported_shapes_and_result_families(self):
        self.time_tag('Clock', 'DT', 1)
        self.time_tag('Delay', 'TIME', 1)
        for assignment, message in (
            ('Clock:=Clock+Clock;', 'Temporal arithmetic supports'),
            ('Delay:=Delay-Clock;', 'Temporal arithmetic supports'),
            ('Delay:=Clock+Delay;', 'result family must match'),
            ('Delay:=(Delay+Delay)-Delay;', 'one + or - operation'),
            ('Delay:=Delay+1;', 'one + or - operation'),
        ):
            with self.subTest(assignment=assignment):
                e = self.engine(f'IF FALSE THEN {assignment} END_IF;')
                self.assertIn(message, str(e.blockers))

    def test_temporal_relations_distinguish_adjacent_nanoseconds(self):
        self.time_tag('Stamp', 'LDT', 1603623920123456789)
        for operation, expected in (('=', False), ('<>', True), ('<', True),
                                    ('<=', True), ('>', False), ('>=', False)):
            with self.subTest(operation=operation):
                e = self.engine(f'Done:=Stamp {operation} LDT#2020-10-25-11:05:20.123_456_790;')
                self.assertEqual(e.blockers, [])
                e.step()
                self.assertIs(e.memory.read('Done'), expected)

    def test_temporal_tag_families_compare_across_precisions_in_if_and_while(self):
        self.time_tag('Delay', 'TIME32', -1002)
        self.time_tag('Stamp', 'LDT', 1001)
        self.time_tag('CoarseStamp', 'DT', 1)
        e = self.engine(
            'IF Delay=LT#-1ms_2us THEN State:=7; END_IF; '
            'WhileCount:=0; WHILE Stamp>CoarseStamp DO '
            'WhileCount:=WhileCount+1; Stamp:=LDT#1970-01-01-00:00:00.000_001_000; END_WHILE;')
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.read('State'), 7)
        self.assertEqual(e.memory.read('WhileCount'), 1)
        self.assertEqual(e.memory.read('Stamp', allow_time=True), 1000)

    def test_temporal_if_skips_unreached_indices_and_rolls_back_unknown_reads(self):
        self.time_tag('Times', 'LDT', elements=(None, 2))
        e = self.engine(
            'State:=7; IF Enable THEN '
            'IF Times[Selector]>LDT#1970-01-01-00:00:00.000_000_001 THEN State:=12; END_IF; '
            'END_IF;')
        self.assertEqual(e.blockers, [])
        e.memory.write('Enable', False)
        e.memory.write('Selector', 99)
        e.step()
        self.assertEqual(e.memory.read('State'), 7)
        e.memory.write('Enable', True)
        e.memory.write('Selector', 0)
        e.memory.write('State', 5)
        before = copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError, 'Unknown initial byte/value'):
            e.step()
        self.assertEqual(e.memory.values, before)
        e.memory.write('Selector', 1)
        e.step()
        self.assertEqual(e.memory.read('State'), 12)

    def test_temporal_comparisons_require_one_relation_and_matching_families(self):
        self.time_tag('Stamp', 'LDT', 1)
        self.time_tag('Delay', 'TIME', 0)
        for condition in ('Stamp>Delay', 'Stamp=1', '(Stamp>Stamp) OR Enable', 'Stamp+Delay>Stamp'):
            with self.subTest(condition=condition):
                e = self.engine(f'IF FALSE THEN IF {condition} THEN State:=1; END_IF; END_IF;')
                self.assertTrue(e.blockers)

    def test_if_elsif_else_select_first_true_branch(self):
        source='IF Selector=1 THEN State:=1; ELSIF Selector>0 THEN State:=2; ELSIF Selector=3 THEN State:=3; ELSE State:=-1; END_IF;'
        e=self.engine(source);self.assertEqual(e.blockers,[])
        for selector,result in ((1,1),(3,2),(-1,-1)):
            e.memory.write('Selector',selector);e.step();self.assertEqual(e.memory.read('State'),result)

    def test_false_st_branch_is_not_false_scanned(self):
        e=self.engine('IF Enable THEN State:=7; END_IF;');e.step();e.memory.write('Enable',False);e.step()
        self.assertEqual(e.memory.read('State'),7)

    def test_unreached_faulting_branch_does_not_evaluate(self):
        e=self.engine('IF Enable THEN State:=4; ELSE State:=1.0/0.0; END_IF;');self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('State'),4)

    def test_unknown_instruction_in_false_branch_still_blocks(self):
        self.assertTrue(self.engine('IF FALSE THEN SECRET(State); END_IF;').blockers)

    def test_st_rejects_ladder_only_instruction_forms(self):
        for text in ('OTE(Done);','TON(Accumulator,?,?);','MOV(1,State);','CMP(State=1);'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_nonretentive_assignment_resets_even_in_false_branch(self):
        e=self.engine('IF FALSE THEN ClearedOnRun [:=] 7; END_IF;');self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.read('ClearedOnRun'),0);e.memory.write('ClearedOnRun',9);e.step()
        self.assertEqual(e.memory.read('ClearedOnRun'),9)

    def test_ordinary_assignment_retains_imported_value_until_executed(self):
        e=self.engine('IF FALSE THEN ClearedOnRun:=7; END_IF;');self.assertEqual(e.memory.read('ClearedOnRun'),99)

    def test_tnd_ends_the_routine_from_a_loop_and_prescan_still_visits_following_lines(self):
        engine = self.engine(
            'State:=1;\n'
            'FOR Index:=0 TO 2 DO\n'
            '  IF Index=1 AND Enable THEN\n'
            '    TND();\n'
            '  END_IF;\n'
            '  State:=State+1;\n'
            'END_FOR;\n'
            'ClearedOnRun [:=] 12;')
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.read('ClearedOnRun'), 0)

        engine.memory.write('Enable', True)
        engine.step()
        self.assertEqual(engine.memory.read('State'), 2)
        self.assertEqual(engine.memory.read('Index'), 1)
        self.assertEqual(engine.memory.read('ClearedOnRun'), 0)
        terminal = engine.trace[-1]
        self.assertEqual((terminal['number'], terminal['detail']), ('3', 'temporary end'))

        engine.memory.write('Enable', False)
        engine.step()
        self.assertEqual(engine.memory.read('State'), 4)
        self.assertEqual(engine.memory.read('Index'), 3)
        self.assertEqual(engine.memory.read('ClearedOnRun'), 12)
        self.assertFalse(any(row.get('detail') == 'temporary end' for row in engine.trace))

    def test_tnd_rejects_operands_during_preflight_even_when_unreached(self):
        engine = self.engine('IF FALSE THEN TND(State); END_IF;')
        self.assertTrue(any('TND' in blocker and 'operand' in blocker for blocker in engine.blockers))

    def test_for_positive_negative_zero_iterations_and_terminal_counter(self):
        for start,end,step,total,index in ((0,4,1,10,5),(4,0,-2,6,-2),(4,0,1,0,4),(0,4,-1,0,0)):
            with self.subTest(start=start,end=end,step=step):
                e=self.engine(f'Sum:=0; FOR Index:={start} TO {end} BY {step} DO Sum:=Sum+Index; END_FOR;')
                self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Sum'),total);self.assertEqual(e.memory.read('Index'),index)

    def test_for_exit_leaves_counter_at_exit_value(self):
        e=self.engine('Sum:=0; FOR Index:=0 TO 9 DO IF Index=3 THEN EXIT; END_IF; Sum:=Sum+Index; END_FOR;')
        e.step();self.assertEqual(e.memory.read('Sum'),3);self.assertEqual(e.memory.read('Index'),3)

    def test_exit_affects_nearest_nested_loop(self):
        e=self.engine('Sum:=0; FOR Index:=0 TO 1 DO FOR BitIndex:=0 TO 5 DO Sum:=Sum+1; EXIT; END_FOR; Sum:=Sum+10; END_FOR;')
        e.step();self.assertEqual(e.memory.read('Sum'),22)

    def test_for_zero_step_rolls_back(self):
        e=self.engine('State:=9; FOR Index:=0 TO 4 BY Step DO Sum:=Sum+1; END_FOR;');e.memory.write('Step',0)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.time_ms,0)

    def test_for_rejects_real_bounds_or_counter(self):
        self.assertTrue(self.engine('FOR Index:=0 TO 2.0 DO Sum:=1; END_FOR;').blockers)
        self.assertTrue(self.engine('FOR Done:=0 TO 2 DO Sum:=1; END_FOR;').blockers)

    def test_for_mutating_bounds_and_aggregate_counter_are_blocked(self):
        for source in ('FOR Index:=0 TO Step DO Step:=Step+1; END_FOR;',
                       'FOR Index:=0 TO Index+3 DO Sum:=1; END_FOR;',
                       'FOR Values:=0 TO 2 DO Sum:=1; END_FOR;'):
            with self.subTest(source=source):self.assertTrue(self.engine(source).blockers)

    def test_for_indirect_counter_keeps_its_selected_cell_when_selector_changes(self):
        tags = self.root.find('./Controller/Tags')
        E.SubElement(tags, 'Tag', Name='Counters', TagType='Alias', AliasFor='Values')
        engine = self.engine(
            'Sum:=0; FOR Counters[Selector]:=0 TO 4 BY Step DO '
            'Sum:=Sum+Values[1]; Selector:=99; END_FOR;')
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Selector', 1)
        engine.memory.write('Values[3]', 77)
        engine.step()
        self.assertEqual(engine.memory.read('Selector'), 99)
        self.assertEqual(engine.memory.read('Sum'), 6)
        self.assertEqual(engine.memory.read('Values'), [0, 6, 0, 77, 0])

    def test_for_indirect_counter_checks_live_overlap_with_bound_before_initializing(self):
        engine = self.engine(
            'FOR Values[Selector]:=0 TO Values[2] BY Step DO Sum:=Sum+1; END_FOR;')
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Selector', 1)
        engine.memory.write('Values[2]', 4)
        engine.step()
        self.assertEqual(engine.memory.read('Values'), [0, 6, 4, 0, 0])

        engine.memory.write('Selector', 2)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'FOR bounds/step cannot depend on its counter'):
            engine.step()
        self.assertEqual(engine.memory.values, before)
        self.assertEqual(engine.scan_count, 1)

    def test_for_indirect_counter_resolves_bounds_only_in_reached_loops(self):
        source = ('State:=7; IF Enable THEN FOR Values[Selector]:=0 TO 2 DO '
                  'Sum:=Sum+1; END_FOR; END_IF;')
        engine = self.engine(source)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Enable', False)
        engine.memory.write('Selector', 99)
        engine.step()
        self.assertEqual(engine.memory.read('State'), 7)

        engine.memory.write('State', 9)
        engine.memory.write('Enable', True)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'Array index outside bounds'):
            engine.step()
        self.assertEqual(engine.memory.values, before)

        self.root.find('Controller').set('MajorRev', '34')
        self.assertTrue(self.engine(source).blockers)

    def test_for_indirect_limit_and_increment_support_selectors_and_aliases(self):
        tags = self.root.find('./Controller/Tags')
        E.SubElement(tags, 'Tag', Name='Bounds', TagType='Alias', AliasFor='Values')
        engine = self.engine(
            'Sum:=0; FOR Index:=4 TO Bounds[Selector] BY Values[Selector+1] DO '
            'Sum:=Sum+Index; END_FOR;')
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Selector', 1)
        engine.memory.write('Values[1]', 0)
        engine.memory.write('Values[2]', -2)
        engine.step()
        self.assertEqual(engine.memory.read('Sum'), 6)
        self.assertEqual(engine.memory.read('Index'), -2)

    def test_for_indirect_bounds_protect_subscript_dependencies_and_candidate_cells(self):
        for body in ('Selector:=2;', 'Values[4]:=2;'):
            with self.subTest(body=body):
                engine = self.engine(f'FOR Index:=0 TO Values[Selector] DO {body} END_FOR;')
                self.assertIn('FOR body cannot modify tags', str(engine.blockers))
        engine = self.engine('FOR Index:=0 TO Values[Values[Index]] DO Sum:=Sum+1; END_FOR;')
        self.assertIn('FOR bounds/step cannot depend on its counter', str(engine.blockers))

    def test_for_indirect_limit_checks_overlap_and_skips_unreached_indices(self):
        engine = self.engine(
            'IF Enable THEN FOR Values[0]:=0 TO Values[Selector] DO '
            'Sum:=Sum+1; END_FOR; END_IF;')
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Enable', False)
        engine.memory.write('Selector', 99)
        engine.step()
        engine.memory.write('Enable', True)
        engine.memory.write('Selector', 1)
        engine.memory.write('Values[1]', 1)
        engine.step()
        self.assertEqual(engine.memory.read('Values[0]'), 2)
        engine.memory.write('Selector', 0)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'FOR bounds/step cannot depend on its counter'):
            engine.step()
        self.assertEqual(engine.memory.values, before)
        self.assertEqual(engine.scan_count, 2)

    def test_for_jsr_rolls_back_a_write_to_the_selected_indirect_limit(self):
        engine = self.engine(
            'FOR Index:=0 TO Values[Selector] DO JSR(LadderScale,1,Index,Values[1]); END_FOR;')
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Selector', 1)
        engine.memory.write('Values[1]', 4)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'JSR changed an active FOR limit or increment'):
            engine.step()
        self.assertEqual(engine.memory.values, before)

    def test_for_read_only_tag_bound_is_supported(self):
        e=self.engine('Sum:=0; FOR Index:=0 TO Step DO Sum:=Sum+Index; END_FOR;');self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Sum'),3)

    def test_for_with_tag_limit_and_increment_calls_ladder_with_nested_st(self):
        project = self.engine(
            'Sum:=0; FOR Index:=0 TO Selector+1 BY Step DO '
            'JSR(LadderScale,1,Index,Scaled); Sum:=Sum+Scaled; END_FOR;')
        harness = Engine(project.project, 'routine', 'MainProgram/MainRoutine')
        for engine in (project, harness):
            with self.subTest(mode=engine.mode):
                self.assertEqual(engine.blockers, [])
                engine.memory.write('Selector', 3)
                engine.memory.write('Step', 2)
                engine.step()
                self.assertEqual(engine.memory.read('Sum'), 15)
                self.assertEqual(engine.memory.read('Index'), 6)
                self.assertEqual(engine.memory.read('Scaled'), 9)

    def test_for_jsr_rejects_return_to_limit_and_rolls_back_all_writes(self):
        engine = self.engine(
            'State:=7; FOR Index:=0 TO Step DO JSR(LadderScale,1,Index,Step); END_FOR;')
        self.assertEqual(engine.blockers, [])
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'JSR changed an active FOR limit or increment'):
            engine.step()
        self.assertEqual(engine.memory.values, before)
        self.assertEqual(engine.scan_count, 0)

    def test_nested_for_jsr_protects_outer_increment_from_alias_write(self):
        tags = self.root.find('./Controller/Tags')
        E.SubElement(tags, 'Tag', Name='StepAlias', TagType='Alias', AliasFor='Step')
        self.text('SBR(AdjustInput); StepAlias:=StepAlias+1; RET(AdjustInput);', 'TextAdjust')
        engine = self.engine(
            'FOR Index:=0 TO Selector BY Step DO FOR BitIndex:=0 TO 0 DO '
            'IF Enable THEN JSR(LadderScale,1,Index,Scaled); END_IF; END_FOR; END_FOR;')
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Selector', 4)
        engine.memory.write('Step', 2)
        engine.memory.write('Enable', False)
        engine.step()
        self.assertEqual(engine.memory.read('Index'), 6)
        engine.memory.write('Enable', True)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'JSR changed an active FOR limit or increment'):
            engine.step()
        self.assertEqual(engine.memory.values, before)
        self.assertEqual(engine.scan_count, 1)

    def test_while_can_execute_zero_times_repeat_executes_once(self):
        e=self.engine('Sum:=0; WHILE FALSE DO Sum:=100; END_WHILE; REPEAT Sum:=Sum+1; UNTIL TRUE END_REPEAT;')
        e.step();self.assertEqual(e.memory.read('Sum'),1)

    def test_while_and_repeat_exit(self):
        for loop in ('WHILE TRUE DO Sum:=Sum+1; EXIT; END_WHILE;','REPEAT Sum:=Sum+1; EXIT; UNTIL FALSE END_REPEAT;'):
            e=self.engine('Sum:=0;'+loop);e.step();self.assertEqual(e.memory.read('Sum'),1)

    def test_empty_infinite_loops_hit_budget_and_rollback(self):
        for text in ('State:=7; WHILE TRUE DO END_WHILE;','State:=7; REPEAT UNTIL FALSE END_REPEAT;'):
            e=self.engine(text);e.instruction_limit=30
            with self.assertRaisesRegex(ModelError,'budget'):e.step()
            self.assertEqual(e.memory.read('State'),0);self.assertEqual(e.scan_count,0)

    def test_exit_outside_loop_is_blocked(self):self.assertTrue(self.engine('IF TRUE THEN EXIT; END_IF;').blockers)

    def test_case_single_list_range_else_and_no_fallthrough(self):
        e=self.engine('CASE Selector OF 1,2: State:=10; 3..5: State:=20; 4: State:=99; ELSE State:=-1; END_CASE;')
        self.assertEqual(e.blockers,[])
        for selector,state in ((1,10),(4,20),(9,-1)):
            e.memory.write('Selector',selector);e.step();self.assertEqual(e.memory.read('State'),state)

    def test_case_without_match_retains_value(self):
        e=self.engine('CASE Selector OF 9: State:=4; END_CASE;');e.memory.write('State',8);e.step();self.assertEqual(e.memory.read('State'),8)

    def test_case_rejects_bool_dynamic_and_descending_selectors(self):
        for text in ('CASE TRUE OF 1: State:=1; END_CASE;','CASE Selector OF Step: State:=1; END_CASE;','CASE Selector OF 5..1: State:=1; END_CASE;'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_st_precedence_relations_before_and_and_equality(self):
        e=self.engine('Done := 1<2 AND 3=3 OR FALSE; State:=2**3**2; Truth:=NOT FALSE AND TRUE;');e.step()
        self.assertTrue(e.memory.read('Done'));self.assertTrue(e.memory.read('Truth'));self.assertEqual(e.memory.read('State'),64)

    def test_st_function_names_and_real_rounding(self):
        e=self.engine('State:=TRUNC(-3.9); Sum:=SQRT(9.0)+ABS(-2); Done:=ACOS(1.0)=0.0;');e.step()
        self.assertEqual(e.memory.read('State'),-3);self.assertEqual(e.memory.read('Sum'),5);self.assertTrue(e.memory.read('Done'))

    def test_numeric_integer_limits_and_negative_modulo(self):
        e=self.engine('State := -2147483648; Sum := -7 MOD 3;');e.step()
        self.assertEqual(e.memory.read('State'),-2147483648);self.assertEqual(e.memory.read('Sum'),-1)

    def test_narrow_integer_division_and_wide_assignment_use_their_profiles(self):
        e=self.engine('State:=7/2;');self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('State'),3)
        t=self.root.find('./Controller/Tags/Tag[@Name="State"]');t.set('DataType','LINT');t.find('Data/DataValue').set('DataType','LINT')
        e=self.engine('State:=1;');self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('State'),1)

    def test_bool_assignment_accepts_bool_or_0_1_only(self):
        for text in ('Done:=TRUE;','Done:=1;','Done:=FALSE;','Done:=0;'):
            self.assertEqual(self.engine(text).blockers,[])
        for text in ('Done:=2;','Done:=1.0;','Done:=Step;','State:=Enable;','IF 1 THEN State:=1; END_IF;'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_three_comment_forms_and_case_insensitivity(self):
        e=self.engine("// hello\nsTaTe:=4; (* ignored State:=99; *)\n/*ignored*/ sUm:=state+2;")
        e.step();self.assertEqual(e.memory.read('Sum'),6)

    def test_strings_literal_escapes_comparison_and_copy(self):
        e=self.engine("Message:='A$27B$$C$0A'; Shadow:=Message; Done:=Shadow='A$27B$$C$0A';")
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.string('Message'),"A'B$C\n");self.assertTrue(e.memory.read('Done'))
        e.memory.write('Message.DATA[1]',90);self.assertEqual(e.memory.string('Shadow'),"A'B$C\n")

    def test_comment_markers_inside_strings_are_data(self):
        e=self.engine("Message:='// (* /* '; ");e.step();self.assertEqual(e.memory.string('Message'),'// (* /* ')

    def test_empty_string_and_nonretentive_string(self):
        e=self.engine("Prefix [:=] ''; Message:='';");self.assertEqual(e.memory.string('Prefix'),'');e.step();self.assertEqual(e.memory.string('Message'),'')

    def test_string_bounds_and_wrongly_typed_assignments_are_blocked(self):
        for text in ("Message:='"+'a'*83+"';",'Message:=1;','State:=Message;','Values:=1;'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_malformed_source_is_blocked(self):
        for text in ('IF Enable THEN State:=1;','WHILE Enable DO State:=1;','State:=;', 'State:=2#2;',
                     '(* unclosed','/* unclosed',"Message:='unclosed;", "Message:='line\nbreak';",'State:=__import__(os);'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_indirect_array_bounds_checked_at_runtime_after_loop_initialization(self):
        e=self.engine('FOR Index:=0 TO 4 DO Values[Index]:=Index; END_FOR;');self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Values'),[0,1,2,3,4])
        e=self.engine('State:=8; Values[Index]:=1;');self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'bounds'):e.step()
        self.assertEqual(e.memory.read('State'),0)

    def test_indirect_bits_validate_width_and_preserve_other_bits(self):
        e=self.engine('Packed:=16#80; FOR BitIndex:=0 TO 3 DO Packed.[BitIndex]:=1; END_FOR;');e.step();self.assertEqual(e.memory.read('Packed'),143)
        e=self.engine('Packed.[BitIndex]:=1;');self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'bit selection'):e.step()

    def test_unknown_initial_data_is_read_only_when_reached(self):
        array=self.root.find('./Controller/Tags/Tag[@Name="Values"]/Data/Array');array.remove(array[-1])
        e=self.engine('IF FALSE THEN State:=Values[4]; END_IF;');self.assertEqual(e.blockers,[]);e.step()
        e=self.engine('Sum:=99; State:=Values[4];');self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.read('Sum'),0)

    def test_constant_assignment_is_blocked_even_unreached(self):
        self.root.find('./Controller/Tags/Tag[@Name="State"]').set('Constant','true')
        self.assertTrue(self.engine('IF FALSE THEN State:=1; END_IF;').blockers)

    def test_st_aoi_not_invoked_in_false_branch_retains_state_and_input(self):
        e=self.engine();e.step();e.memory.write('Enable',False);e.memory.write('Step',9);e.step()
        self.assertEqual(e.memory.read('AOITotal'),2);self.assertEqual(e.memory.read('Accumulator.Step'),2)
        self.assertEqual(e.memory.read('Accumulator.Count'),2)

    def test_rll_false_call_executes_st_aoi_false_routine(self):
        r=self.root.find('./Controller/Programs/Program/Routines/Routine[@Name="MainRoutine"]');r.clear();r.set('Name','MainRoutine');r.set('Type','RLL')
        rung=E.SubElement(E.SubElement(r,'RLLContent'),'Rung',Number='0',Type='N');E.SubElement(rung,'Text').text='AFI()LabSTAccumulator(Accumulator,Step,AOITotal);'
        e=self.engine();self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('AOITotal'),-1)

    def test_st_aoi_hidden_defaults_remain_unknown_without_prescan(self):
        self.root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition').set('ExecutePrescan','false')
        e=self.engine();self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.read('ScanTotal'),0)

    def test_trace_preserves_st_line_and_instance_context(self):
        e=self.engine();e.step();st=[t for t in e.trace if t.get('language')=='ST']
        self.assertTrue(any(t['routine']=='MainProgram/MainRoutine' and t['statement']=='for' for t in st))
        self.assertTrue(any(t['routine']=='AOI:LabSTAccumulator/Logic' and t['context']=='Accumulator' for t in st))

    def test_native_xml_line_wrappers_preserve_trace_and_call_numbers(self):
        for line in self.root.findall('.//STContent/Line'):line.text='\n'+(line.text or '')+'\n'
        e=self.engine();self.assertEqual(e.blockers,[]);e.step()
        main=e.project.routines['mainprogram/mainroutine']
        self.assertEqual(main.lines[5]['text'],'    Values[Index] := Index * 3;')
        self.assertTrue(any(r['number']=='37' and r['nodes'][0].name=='JSR' for r in main.rungs))
        self.assertTrue(any(t['routine']==main.key and t['number']=='1' and t.get('detail')=='ScanTotal = 1' for t in e.trace))
        self.assertTrue(any(t['routine']=='AOI:LabSTAccumulator/Logic' and t['number']=='0' and t['context']=='Accumulator' for t in e.trace))

    def test_embedded_multiline_content_in_numbered_line_blocks(self):
        self.text('State:=1;')
        self.root.find('.//Programs/Program/Routines/Routine/STContent/Line').text='State:=1;\nState:=2;'
        self.assertTrue(self.engine().blockers)

    def test_application_exports_st_source_and_traces(self):
        app=Application(self.tmp.name);state=app.command('demo',{'sample':'TextLab'});self.assertEqual(state['blockers'],[])
        routine=next(r for r in state['routines'] if r['key']=='MainProgram/MainRoutine')
        self.assertEqual(routine['kind'],'ST');self.assertEqual(routine['lines'][0]['number'],'0')
        self.assertIn('Text Lab',routine['lines'][0]['text'])
        state=app.command('step',{'count':3});self.assertEqual(state['scan'],3)
        self.assertTrue(any(t.get('language')=='ST' for t in state['trace']))
        self.assertTrue(app.command('report',{})['structured_text']['constructs']['for'])

    def test_nonsequential_st_lines_and_missing_source_block(self):
        r=self.root.find('./Controller/Programs/Program/Routines/Routine[@Name="MainRoutine"]')
        r.find('STContent/Line').set('Number','9');self.assertTrue(self.engine().blockers)
        r.remove(r.find('STContent'));self.assertTrue(self.engine().blockers)

    def test_st_sbr_must_be_first_statement_and_main_ret_blocks(self):
        self.text('State:=1; SBR(AdjustInput); RET(AdjustOutput);','TextAdjust')
        self.assertTrue(self.engine().blockers)
        self.assertTrue(self.engine('RET();').blockers)

    def test_arithmetic_fault_restores_prior_st_aoi_and_call_writes(self):
        e=self.engine('LabSTAccumulator(Accumulator,Step,AOITotal); JSR(LadderScale,1,Step,Scaled); State:=1.0/0.0;')
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.calls.stack,[]);self.assertEqual(e.time_ms,0)


if __name__=='__main__':unittest.main()
