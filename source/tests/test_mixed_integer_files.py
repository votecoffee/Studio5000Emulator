"""Bounded mixed integer FAL with exact common-type intermediates and progress."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_integer_files as fixtures
import test_aoi_files as aoi
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class MixedIntegerFileTests(unittest.TestCase):
    setUp = fixtures.IntegerFileTests.setUp
    snapshot = staticmethod(fixtures.IntegerFileTests.snapshot)

    def engine(self, expr='Queue[Ctl.POS]+Small', *, mode='ALL', small_type='DINT', small=3,
               mutate=None, rungs=None, **kwargs):
        def fields(root):
            tag = E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Small', DataType=small_type, TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType=small_type, Value=str(small))
            if mutate:mutate(root)
        logic = rungs if rungs is not None else [f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],{expr});']
        return fixtures.IntegerFileTests.engine(self, logic, mutate=fields, **kwargs)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs);self.assertEqual(e.blockers, []);return e

    def fault(self, e, pattern):
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, pattern):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_common_range_integer_pairs_and_five_binary_operators(self):
        pairs = [('LINT', 'DINT'), ('LINT', 'UDINT'), ('UDINT', 'UINT'),
                 ('UINT', 'USINT'), ('ULINT', 'UDINT'), ('ULINT', 'UINT')]
        for dtype, small_type in pairs:
            for op, expected in [('+', 8), ('-', 4), ('*', 12), ('/', 3), (' MOD ', 0)]:
                with self.subTest(dtype=dtype, small=small_type, op=op):
                    e = self.checked('Queue[Ctl.POS]' + op + 'Small', dtype=dtype, small_type=small_type,
                                     small=2, length=1, queue=(6, 99))
                    e.memory.write('StartPB', True);e.step()
                    self.assertEqual(e.memory.read('Queue'), [expected, 99])

    def test_large_signed_unsigned_values_division_remainder_and_abs_are_exact(self):
        for expression, value, small, result in [('Queue[Ctl.POS]+Small', 9007199254740993, 3, 9007199254740996),
                ('Queue[Ctl.POS]/Small', -9223372036854775808, 3, -3074457345618258602),
                ('Queue[Ctl.POS] MOD Small', -9223372036854775808, 3, -2),
                ('ABS(Queue[Ctl.POS])+Small', -9007199254740993, 3, 9007199254740996)]:
            e = self.checked(expression, queue=(value, 99), length=1, small=small)
            e.memory.write('StartPB', True);e.step();self.assertEqual(e.memory.read('Queue[0]'), result)
        e = self.checked('Queue[Ctl.POS]-Small', dtype='ULINT', small_type='UDINT',
                         queue=(18446744073709551615, 99), length=1)
        e.memory.write('StartPB', True);e.step();self.assertEqual(e.memory.read('Queue[0]'), 18446744073709551612)

    def test_numeric_mode_continues_on_false_and_unknown_input_rolls_back_progress(self):
        e = self.checked(mode='2');e.step();e.memory.write('StartPB', True);e.step()
        self.assertEqual(e.memory.read('Queue'), [5, 7, 6, 8, 99])
        e.memory.write('StartPB', False);e.memory.values['small'] = None;self.fault(e, 'Unknown')
        e.memory.write('Small', 5);e.step()
        self.assertEqual(e.memory.read('Queue'), [5, 7, 11, 13, 99]);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_inc_edges_defer_unknown_operands_until_the_next_reached_iteration(self):
        e = self.checked(mode='INC', length=2, queue=(9007199254740993, 9007199254740994, 99))
        e.step();e.memory.write('StartPB', True);e.step();e.memory.values['small'] = None;e.step()
        self.assertEqual(e.memory.read('Ctl.POS'), 0)
        e.memory.write('StartPB', False);e.step();e.memory.write('StartPB', True);self.fault(e, 'Unknown')
        e.memory.write('Small', 5);e.step()
        self.assertEqual(e.memory.read('Queue'), [9007199254740996, 9007199254740999, 99])
        self.assertTrue(e.memory.read('Ctl.DN'))

    def test_false_and_completed_calls_skip_unknown_values_and_live_alias_indices(self):
        def alias(root):
            tags = root.find('./Controller/Tags')
            tag = E.SubElement(tags, 'Tag', Name='Offset', DataType='DINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='99')
            E.SubElement(tags, 'Tag', Name='Selected', TagType='Alias', AliasFor='Queue[Ctl.POS+Offset]')
        text = 'XIC(StartPB)FAL(Ctl,?,?,ALL,Selected,Selected+Small);'
        e = self.checked(mutate=alias, rungs=[text], length=2)
        e.memory.values['small'] = None;e.step();e.memory.write('StartPB', True);self.fault(e, 'outside bounds')
        e.memory.write('Offset', 0);self.fault(e, 'Unknown')
        e.memory.write('Small', 3);e.step()
        e.memory.write('Offset', 99);e.memory.values['small'] = None;e.step()
        self.assertEqual(e.memory.read('Queue')[:2], [5, 7])

    def test_full_mixed_results_establish_unknown_destinations_without_reading_old_values(self):
        e = self.checked(rungs=['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming+Small);'])
        e.memory.values['queue'][:4] = [None] * 4;e.step()
        e.memory.write('Incoming', 9007199254740993);e.memory.write('StartPB', True);e.step()
        self.assertEqual(e.memory.read('Queue'), [9007199254740996] * 4 + [99])

    def test_overflow_underflow_division_and_late_fault_restore_integer_file_work(self):
        for dtype, small_type, value, expr, pattern in [('LINT', 'DINT', 9223372036854775807, 'Queue[Ctl.POS]+Small-Small', 'overflow'),
                ('ULINT', 'UDINT', 0, 'Queue[Ctl.POS]-Small', 'overflow|range'),
                ('LINT', 'DINT', 1, 'Queue[Ctl.POS]/Small', 'zero')]:
            e = self.checked(expr, dtype=dtype, small_type=small_type, small=0 if pattern == 'zero' else 3,
                             length=1, queue=(value, 99))
            e.memory.write('StartPB', True);self.fault(e, pattern)
            self.assertFalse(e.memory.read('Ctl.ER'))
        e = self.checked(rungs=['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+Small);',
                                'XIC(StartPB)DIV(1,0,SpeedCommand);'])
        e.step();e.memory.write('StartPB', True);self.fault(e, 'zero')

    def test_every_mixed_arithmetic_subtree_requires_the_common_source_type(self):
        for expr in ('Queue[Ctl.POS]+(Small+1)', 'Queue[Ctl.POS]+ABS(Small)', '(Small*Small)+Queue[Ctl.POS]',
                     '(NOT Queue[Ctl.POS])+Small', 'Queue[Ctl.POS] AND Small', 'Queue[Ctl.POS]**(Small+1)'):
            self.assertTrue(self.engine(expr).blockers, expr)
        e = self.checked('(Queue[Ctl.POS]+Small)+1');e.memory.write('StartPB', True);e.step()
        self.assertEqual(e.memory.read('Queue')[:2], [6, 8])

    def test_source_ranges_destination_and_typed_literal_limits_remain_explicit(self):
        self.assertTrue(self.engine(dtype='ULINT', small_type='DINT', small=1).blockers)
        self.assertTrue(self.engine('Queue[Ctl.POS]+Small+1U').blockers)
        self.assertTrue(self.engine('Queue[Ctl.POS]+Small+2147483648').blockers)
        def narrow_dest(root):root.find('./Controller/Tags/Tag[@Name="Outgoing"]').set('DataType', 'DINT')
        self.assertTrue(self.engine(rungs=['FAL(Ctl,?,?,ALL,Outgoing,Queue[Ctl.POS]+Small);'], mutate=narrow_dest).blockers)
        for processor, revision in [('1756-L75', '35'), ('1756-L85E', '34')]:
            def target(root):root.find('Controller').set('ProcessorType', processor);root.find('Controller').set('MajorRev', revision)
            self.assertTrue(self.engine(mutate=target).blockers)

    @staticmethod
    def aoi_types(root):
        names = {'Input', 'Output', 'Scratch', 'Total', 'InputA', 'OutputA', 'InputB', 'OutputB'}
        for node in root.iter():
            if node.get('Name') in names and node.get('DataType') == 'DINT':
                for child in node.iter():
                    if child.get('DataType') == 'DINT':child.set('DataType', 'LINT')

    def test_aoi_mixed_gain_bias_and_local_arrays_keep_exact_values_and_rollback(self):
        helper = aoi.AOIFileTests();helper.setUp();self.addCleanup(helper.doCleanups)
        for mode, pulses in [('ALL', 1), ('2', 2), ('INC', 4)]:
            e = helper.checked(self.aoi_types, kind=mode);e.memory.write('InputA[0]', 9007199254740993)
            e.memory.write('Transform', True);e.memory.write('FaultDivisor', 0)
            before = helper.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'zero'):e.step()
            self.assertEqual(helper.snapshot(e), before)
            e.memory.write('FaultDivisor', 1)
            for _ in range(pulses):helper.pulse(e)
            self.assertEqual(e.memory.read('OutputA[0]'), 18014398509481987)
            self.assertEqual(e.memory.read('DriverA.Scratch[0]'), 9007199254740994)

    def test_stats_lab_default_and_changed_dint_adjustments_preserve_exact_results(self):
        from pathlib import Path
        e = Engine(Project(Path(__file__).resolve().parents[1] / 'samples/StatsLab.L5X'))
        self.assertEqual(e.blockers, []);e.step();e.memory.write('WideFiles', True);e.step()
        self.assertEqual(e.memory.read('WideMapped')[:2], [18014398509481987, 18014398509481989])
        e.memory.write('WideFiles', False);e.step();e.memory.write('WideFileDelta', 3);e.memory.write('WideFiles', True);e.step()
        self.assertEqual(e.memory.read('WideMapped')[:2], [18014398509481989, 18014398509481991])
        self.assertIsNone(e.memory.read('WideMapped')[2])

    def test_reports_expose_mixed_fal_and_keep_native_parity_unqualified(self):
        e = self.checked();report = e.report()
        profile = report['file_arithmetic']['mixed_integer_arithmetic']
        self.assertEqual(profile['modes'], ['ALL', 'positive DINT immediate', 'INC'])
        self.assertIn('FAL', report['wide_ladder_expressions']['file_consumers'])
        self.assertFalse(profile['native_runtime_parity'])


if __name__ == '__main__':
    unittest.main()
