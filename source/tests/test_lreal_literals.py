"""REAL defaults and explicit LREAL floating constants in ladder CPT/CMP."""
import itertools
import math
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_lreal_expressions as fixtures
import test_lreal_results as results
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import INT_BITS, ModelError, Project
from logixlab.runtime import Engine


class LrealLiteralTests(unittest.TestCase):
    setUp = fixtures.LrealExpressionTests.setUp
    engine = fixtures.LrealExpressionTests.engine
    checked = fixtures.LrealExpressionTests.checked
    snapshot = staticmethod(fixtures.LrealExpressionTests.snapshot)
    fault = fixtures.LrealExpressionTests.fault

    def test_unsuffixed_floating_constants_round_to_real_before_double_math(self):
        for literal, expected in [('0.1', .10000000149011612), ('1.0000000000000002', 1.0),
                                  ('16777217.0', 16777216.0), ('1.5e1', 15.0),
                                  ('.5', .5), ('1.', 1.0), ('-1e-46', -0.0)]:
            e = self.checked(['CPT(Results[1],' + literal + ');'])
            e.step()
            self.assertEqual(struct.pack('<d', e.memory.read('Results[1]')), struct.pack('<d', expected))

    def test_lreal_suffix_keeps_precision_range_subnormals_and_signed_zero(self):
        for literal, expected in [('0.1L', .1), ('1.0000000000000002L', 1.0000000000000002),
                                  ('1e308L', 1e308), ('5e-324l', 5e-324), ('-0.0L', -0.0),
                                  ('-1e308L', -1e308), ('1.L', 1.0), ('.5l', .5), ('1E+2l', 100.0)]:
            e = self.checked(['CPT(Results[1],' + literal + ');'])
            e.step()
            self.assertEqual(struct.pack('<d', e.memory.read('Results[1]')), struct.pack('<d', expected))

    def test_lreal_literal_selects_binary64_without_lreal_tags_or_destination(self):
        for dest in fixtures.TYPES:
            e = self.checked(['CPT(Results[1],3.5L);'], source='DINT', other='DINT', dest=dest)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), 4 if dest in INT_BITS else 3.5)
        e = self.checked(['CMP(1.0000000000000002L>1)OTE(RunLatch);'], source='DINT', other='DINT', dest='DINT')
        e.step()
        self.assertTrue(e.memory.read('RunLatch'))

    def test_unsuffixed_literal_with_lreal_source_supports_every_numeric_destination(self):
        for dest in fixtures.TYPES:
            e = self.checked(['CPT(Results[1],Source+0.5);'], value=3, dest=dest)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), 4 if dest in INT_BITS else 3.5)

    def test_source_tag_types_and_lreal_literal_compose_in_all_ten_numeric_types(self):
        for source in fixtures.TYPES:
            e = self.checked(['CPT(Results[1],Source+0.5L);'], source=source, other='DINT', dest='DINT')
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), 4)

    def test_six_relations_and_boolean_composition_keep_literal_precision(self):
        for op, expected in [('=', False), ('<>', True), ('<', True), ('<=', True), ('>', False), ('>=', False)]:
            e = self.checked(['CMP(0.1L' + op + '0.1)OTE(RunLatch);'])
            e.step()
            self.assertEqual(e.memory.read('RunLatch'), expected)
        e = self.checked(['CMP((1.0000000000000002L>1.0)&&(Flag OR (0.1L=0.1)))OTE(RunLatch);'])
        e.step()
        self.assertTrue(e.memory.read('RunLatch'))

    def test_nested_functions_fractional_powers_and_remainders(self):
        for expr, expected in [('Source**0.5', math.sqrt(3)), ('SQR(3.0L)+SQR(3.0L)', 2*math.sqrt(3)),
                               ('TRN(3.75L)+0.25', 3.25), ('-7.5L MOD 3.0', -1.5),
                               ('LN(1.0L)+LOG(100.0)', 2.0), ('(1e308L-1e308L)+0.5', .5),
                               ('(1.0000000000000002L-1.0)*2.0', 2**-51)]:
            e = self.checked(['CPT(Results[1],' + expr + ');'])
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_invalid_literal_ranges_and_suffixes_block_even_false_calls(self):
        for expr in ('1e39', '1e999', '1e309L', '1.0LL', '1.0L2', '1.0UL', '9223372036854775808L', '18446744073709551616UL',
                     '2147483648', '1.0D', 'LREAL#1.0', '1.0Lfoo'):
            self.assertTrue(self.engine(['AFI()CPT(Results[1],' + expr + ');']).blockers, expr)

    def test_false_domains_skip_but_eager_booleans_still_require_both_sides(self):
        e = self.checked(['AFI()CPT(Results[1],LN(-1.0L));', 'AFI()CMP(LN(-1.0L)>0.0)OTE(RunLatch);'])
        e.step()
        self.assertEqual(e.memory.read('Results'), [None]*3)
        for expr in ('(1=1)||(Source/0.0L>0)', '(0=1)&&(LN(-1.0L)>0)'):
            e = self.checked(['CMP(' + expr + ')OTE(RunLatch);'])
            self.fault(e, 'zero|domain')

    def test_unknown_inputs_dynamic_indices_and_complete_writes_remain_lazy(self):
        e = self.checked(['XIC(StartPB)CPT(Results[Index],Inputs[Index]+0.5L);'])
        e.memory.write('Index', 999)
        e.step()
        e.memory.write('StartPB', True)
        self.fault(e, 'outside bounds')
        e.memory.write('Index', 1)
        self.fault(e, 'Unknown')
        e.memory.write('Inputs[1]', 3)
        e.step()
        self.assertEqual(e.memory.read('Results'), [None, 3.5, None])

    def test_conversion_math_and_late_faults_restore_earlier_writes(self):
        for expr, dest, match in [('128.0L', 'SINT', 'overflow'), ('1e308L', 'REAL', 'float|overflow|Nonfinite'),
                                  ('1e308L*2.0', 'LREAL', 'Nonfinite'), ('(-2.0L)**0.5', 'LREAL', 'Complex'),
                                  ('1.0L/0.0', 'LREAL', 'zero'), ('1.0L**1025.0', 'LREAL', 'exponent')]:
            e = self.checked(['MOV(99,SpeedCommand);', 'CPT(Results[1],' + expr + ');'], dest=dest)
            self.fault(e, match)
        e = self.checked(['CPT(Results[1],0.1L);', 'DIV(1,0,SpeedCommand);'])
        self.fault(e, 'zero')

    def test_alias_udt_and_function_indices_keep_the_selected_double_value(self):
        e = self.checked(['CPT(Results[FRD(TOD(1))],Selected-1.0);',
                          'CMP(Selected=1.0000000000000002L)OTE(RunLatch);'], mutate=fixtures.LrealExpressionTests.member)
        e.step()
        self.assertEqual(e.memory.read('Results'), [None, 2**-52, None])
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Packet.Guard'), 777)

    @staticmethod
    def aoi_fields(root):
        import test_aoi_queues as queues
        results.LrealResultTests.aoi_fields(root)
        queues.logic(root, ['CPT(Stack[Index],Value+0.1L);', 'CPT(Buffer[Index],Value+0.5);',
                            'CPT(Item,Value*0.5L);', 'CMP(Stack[Index]>Value)OTE(EnableOut);'])

    def test_warm_aoi_literal_calculations_into_copied_outputs_inout_and_locals(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_fields)
        e.memory.write('ValueA', 3)
        e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 4)
        self.assertEqual(e.memory.read('ItemA'), 2)
        self.assertEqual(e.memory.read('DriverA.Stack[1]'), 3.1)
        e.memory.write('ValueA', 1e308)
        self.fault(e, 'overflow')
        e.memory.write('ValueA', 7)
        e.memory.write('FaultDivisor', 0)
        self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1)
        e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 8)
        self.assertEqual(e.memory.read('ItemA'), 4)
        e.memory.write('EnabledA', False)
        e.memory.write('IndexA', 999)
        e.step()

    def test_generic_file_st_and_array_index_parsers_do_not_gain_lreal_literals(self):
        from logixlab.st_expression import STExpression
        for create in (Expression, Condition, lambda text: Expression(text, subscript=True)):
            with self.assertRaises(ModelError):
                create('0.1L')
        with self.assertRaises(ModelError):
            STExpression('0.1L')
        e = self.checked(['CPT(Results[1],0.1L);'])
        with self.assertRaises(ModelError):
            e.extensions.expression('0.1L')
        self.assertIn(('0.1L', True, True, True), e.extensions.expressions)
        with self.assertRaisesRegex(ModelError, 'qualified'):
            Expression('0.1L', floating_literals=True).evaluate(e.memory)
        import test_file_bcd as files
        f = files.FileBcdTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.assertTrue(f.engine(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],0.1L);']).blockers)
        self.assertTrue(f.engine(['FSC(Ctl,?,?,ALL,0.1L>0);']).blockers)

    def test_old_profiles_and_existing_numeric_bitwise_bcd_guards_remain(self):
        for processor, version in [('1756-L75', '35'), ('1756-L85E', '34')]:
            def old(root):
                root.find('Controller').set('ProcessorType', processor)
                root.find('Controller').set('MajorRev', version)
            self.assertTrue(self.engine(['AFI()CPT(Results[1],0.1L);'], source='DINT', dest='DINT', mutate=old).blockers)
        for expr in ('FRD(1.0L)', 'TOD(1.0L)', '1.0L AND 1', 'NOT 1.0L', 'SQRT(1.0L)'):
            self.assertTrue(self.engine(['AFI()CPT(Results[1],' + expr + ');']).blockers)

    def test_report_states_default_real_and_explicit_lreal_literal_precision(self):
        report = self.checked().report()['lreal_expression_execution']
        self.assertIn('unsuffixed', report['constants'])
        self.assertIn('L/l', report['constants'])
        self.assertIn('literal', report['selection'])
        self.assertFalse(report['native_runtime_parity'])

    def test_wide_expression_lab_literal_precision_faults_and_retry(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.read('FPLitSelected'), [None, None, 903.0])
        e.memory.write('FPLitEnabled', True)
        e.step()
        expected = {'FPLitDefault': .10000000149011612, 'FPLitExplicit': .1,
                    'FPLitDelta': 2**-52, 'FPLitPower': math.sqrt(3), 'FPLitLarge': 1e308,
                    'FPLitTiny': 5e-324, 'FPLitInteger': 4, 'FPLitReal': 1.0,
                    'FPLitDifferent': True, 'FPLitLower': .5, 'FPLitScientific': 100.25}
        for name, value in expected.items():
            self.assertEqual(e.memory.read(name), value, name)
        for tag, match in [('FPLitDomainFault', 'domain'), ('FPLitRangeFault', 'overflow')]:
            e.memory.write(tag, True)
            self.fault(e, match)
            e.memory.write(tag, False)
        e.memory.write('FPLitIndex', 1)
        e.memory.write('FPLitLateDivisor', 0)
        self.fault(e, 'zero')
        self.assertIsNone(e.memory.read('FPLitSelected')[1])
        e.memory.write('FPLitLateDivisor', 1)
        e.step()
        self.assertEqual(e.memory.read('FPLitSelected'), [3.5, 7.5, 903.0])


if __name__ == '__main__':
    unittest.main()
