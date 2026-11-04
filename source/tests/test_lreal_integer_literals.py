"""Declared integer literal ranges precede conversion in LREAL CPT/CMP."""
import copy
import itertools
import unittest
from pathlib import Path

import test_lreal_expressions as fixtures
import test_ladder_integer_literals as integers
from logixlab.model import INT_BITS, ModelError, Project
from logixlab.runtime import Engine


class LrealIntegerLiteralTests(unittest.TestCase):
    setUp = fixtures.LrealExpressionTests.setUp
    engine = fixtures.LrealExpressionTests.engine
    checked = fixtures.LrealExpressionTests.checked

    def snapshot(self, e):
        return (fixtures.LrealExpressionTests.snapshot(e), copy.deepcopy(e.addons.instances))

    def fault(self, e, match='overflow|zero|Unknown|outside bounds|domain'):
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, match):
            e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_full_declared_ranges_convert_like_integer_tags(self):
        for dtype, text, value in integers.CASES:
            e = self.checked(['CPT(Results[1],' + text + ');'], source=dtype, value=value)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), float(value))
            # Include a real selector in the expression; destination is not part of CMP.
            e = self.checked(['CMP((Source+0.0L)=' + text + ')OTE(RunLatch);'], source=dtype, value=value)
            e.step()
            self.assertTrue(e.memory.read('RunLatch'))

    def test_integer_literal_rounds_before_arithmetic_and_relations(self):
        for text, expected in [('9007199254740993L-9007199254740992L', 0.0),
                               ('9007199254740993L+1L', 9007199254740992.0),
                               ('18446744073709551615UL+1UL', float(1 << 64)),
                               ('9223372036854775807L+1L', float(1 << 63))]:
            e = self.checked(['CPT(Results[1],' + text + ');'])
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected)
        e = self.checked(['CMP(9007199254740993L=9007199254740992L+0.0L)OTE(RunLatch);'])
        e.step()
        self.assertTrue(e.memory.read('RunLatch'))

    def test_integer_only_expression_still_selects_exact_integer_evaluator(self):
        f = integers.LadderIntegerLiteralTests(); f.setUp(); self.addCleanup(f.doCleanups)
        e = f.checked(['CPT(Dest,9007199254740993L+1L);',
                       'CMP(9007199254740993L=9007199254740992L)OTE(RunLatch);'])
        e.step()
        self.assertEqual(e.memory.read('Dest'), 9007199254740994)
        self.assertFalse(e.memory.read('RunLatch'))
        self.assertTrue(f.engine(['CPT(Dest,1L+1U);']).blockers)

    def test_lreal_tag_literal_and_destination_each_select_binary64(self):
        for rungs, source, dest, expected in [(['CPT(Results[1],3L/2U);'], 'DINT', 'LREAL', 1.5),
                                              (['CPT(Results[1],Source+1L);'], 'LREAL', 'LREAL', 4.0),
                                              (['CPT(Results[1],Source+1U);'], 'LREAL', 'DINT', 4),
                                              (['CPT(Results[1],3L/2U+0.0L);'], 'DINT', 'DINT', 2)]:
            e = self.checked(rungs, source=source, dest=dest)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_all_numeric_sources_and_destinations_with_each_integer_suffix(self):
        for source, dest, suffix in itertools.product(fixtures.TYPES, fixtures.TYPES, ['L', 'U', 'UL']):
            with self.subTest(source=source, dest=dest, suffix=suffix):
                e = self.checked(['CPT(Results[1],Source+1' + suffix + '+0.5L);'], source=source, dest=dest)
                e.step()
                self.assertEqual(e.memory.read('Results[1]'), 4 if dest in INT_BITS else 4.5)

    def test_case_leading_zero_and_signed_minimum_spelling(self):
        for text, expected in [('00042l', 42.0), ('42u', 42.0), ('42uL', 42.0),
                               ('42Ul', 42.0), ('42ul', 42.0), ('-0UL', 0.0),
                               ('-(9223372036854775808L)', float(-(1 << 63))),
                               ('ABS(-9223372036854775808L)', float(1 << 63)),
                               ('-(-9223372036854775808L)', float(1 << 63))]:
            e = self.checked(['CPT(Results[1],' + text + ');'])
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_declared_range_rejected_before_double_conversion_even_on_false_calls(self):
        for _, text in integers.BAD:
            for rung in ['AFI()CPT(Results[1],' + text + '+0.0L);',
                         'AFI()CMP(' + text + '=0.0L)OTE(RunLatch);']:
                self.assertTrue(self.engine([rung]).blockers, rung)

    def test_malformed_typed_radix_and_untyped_range_guards_remain(self):
        for text in ['1LU', '1ULU', '1L2', '1 UL', '16#FFUL', '1_000L',
                     'LINT#1', '1.0UL', '2147483648', '-2147483649']:
            self.assertTrue(self.engine(['AFI()CPT(Results[1],' + text + '+0.0L);']).blockers, text)

    def test_functions_powers_remainders_and_mixed_integer_suffixes(self):
        for text, expected in [('3L/2U', 1.5), ('-7L MOD 3UL', -1.0), ('TRN(7U/2L)', 3.0),
                               ('SQR(-9L)', 3.0), ('2U**-1L', .5), ('ABS(-7L)+2UL', 9.0),
                               ('LOG(100U)+LN(1UL)', 2.0)]:
            e = self.checked(['CPT(Results[1],' + text + ');'])
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_six_relations_and_eager_boolean_composition(self):
        for op, expected in [('=', False), ('<>', True), ('<', True), ('<=', True), ('>', False), ('>=', False)]:
            e = self.checked(['CMP(3L' + op + '4UL+0.0L)OTE(RunLatch);'])
            e.step()
            self.assertEqual(e.memory.read('RunLatch'), expected)
        e = self.checked(['CMP((3L<4U+0.0L)&&(Flag OR (1UL=0L)))OTE(RunLatch);'])
        e.step()
        self.assertTrue(e.memory.read('RunLatch'))
        for text in ['(1L=1L)||(1U/0UL+0.0L>0)', '(1L=0L)&&(LN(-1L+0.0L)>0)']:
            self.fault(self.checked(['CMP(' + text + ')OTE(RunLatch);']))

    def test_final_integer_range_is_checked_after_literal_rounding(self):
        for dest, text in [('LINT', '9223372036854775807L'), ('ULINT', '18446744073709551615UL')]:
            e = self.checked(['CPT(Results[1],' + text + '+0.0L);'], dest=dest)
            self.fault(e, 'overflow')
        e = self.checked(['CPT(Results[1],-9223372036854775808L+0.0L);'], dest='LINT')
        e.step()
        self.assertEqual(e.memory.read('Results[1]'), -(1 << 63))

    def test_false_domain_unknown_indices_and_complete_unknown_write(self):
        e = self.checked(['XIC(StartPB)CPT(Results[Index],Inputs[Index]+3L+0.0L);'])
        e.memory.write('Index', 999); e.step()
        e.memory.write('StartPB', True); self.fault(e, 'outside bounds')
        e.memory.write('Index', 1); self.fault(e, 'Unknown')
        e.memory.write('Inputs[1]', 3); e.step()
        self.assertEqual(e.memory.read('Results'), [None, 6.0, None])
        e = self.checked(['AFI()CPT(Results[1],LN(-1L));'])
        e.step()
        self.assertIsNone(e.memory.read('Results')[1])

    def test_conversion_domains_and_late_faults_roll_back_earlier_writes(self):
        for text, dest in [('128U+0.0L', 'SINT'), ('1L/0UL', 'LREAL'),
                           ('LN(-1L)', 'LREAL'), ('2L**1025U', 'LREAL')]:
            e = self.checked(['MOV(99,SpeedCommand);', 'CPT(Results[1],' + text + ');'], dest=dest)
            self.fault(e, 'overflow|zero|domain|exponent')
        e = self.checked(['CPT(Results[1],3L/2U);', 'DIV(1,0,SpeedCommand);'])
        self.fault(e, 'zero')

    def test_alias_udt_and_function_index_with_typed_constant(self):
        e = self.checked(['CPT(Results[FRD(TOD(1))],Selected+3UL);',
                          'CMP(Selected>1L)OTE(RunLatch);'], mutate=fixtures.LrealExpressionTests.member)
        e.step()
        self.assertEqual(e.memory.read('Results[1]'), 4.0)
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Packet.Guard'), 777)

    @staticmethod
    def aoi_fields(root):
        import test_aoi_queues as queues
        import test_lreal_results as results
        results.LrealResultTests.aoi_fields(root, 'LINT')
        queues.logic(root, ['CPT(Stack[Index],Value+9007199254740993L);',
                            'CPT(Buffer[Index],Value+2UL);', 'CPT(Item,Value+1U);',
                            'CMP(Stack[Index]>9007199254740992L)OTE(EnableOut);'])
        queues.logic(root, ['AFI()CPT(Stack[Index],1L/0UL);'], name='EnableInFalse')

    def test_warm_aoi_literals_in_copied_outputs_inout_and_local_storage(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests(); f.setUp(); self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_fields)
        e.memory.write('ValueA', 3); e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 5)
        self.assertEqual(e.memory.read('ItemA'), 4)
        self.assertEqual(e.memory.read('DriverA.Stack[1]'), 9007199254740996.0)
        e.memory.write('ValueA', 1e308); self.fault(e, 'overflow')
        e.memory.write('ValueA', 7); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 9)
        e.memory.write('EnabledA', False); e.memory.write('IndexA', 999); e.step()

    def test_other_consumers_profiles_and_numeric_bitwise_guards_remain(self):
        from logixlab.expressions import Expression
        from logixlab.conditions import Condition
        for create in [Expression, Condition, lambda text: Expression(text, subscript=True)]:
            with self.assertRaises(ModelError): create('1UL')
        for text in ['1L AND 1U', 'NOT 0UL', 'FRD(1L)', 'TOD(1U)', 'SQRT(1L)']:
            self.assertTrue(self.engine(['AFI()CPT(Results[1],' + text + ');']).blockers)
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            self.assertTrue(self.engine(['AFI()CMP(1L=1L+0.0L)OTE(RunLatch);'],
                                       mutate=lambda root: root.find('Controller').set(key, value)).blockers)

    def test_report_records_range_conversion_selection_and_precision(self):
        row = self.checked().report()['lreal_expression_execution']['typed_integer_literals']
        self.assertEqual(row['types'], ['LINT', 'UDINT', 'ULINT'])
        self.assertIn('53', row['precision'])
        self.assertIn('LREAL', row['selection'])
        self.assertFalse(row['native_runtime_parity'])

    def test_sample_precision_selected_unknown_and_fault_retry(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step()
        self.assertEqual(e.memory.read('FIntSelected'), [None, None, 903.0])
        e.memory.write('FIntEnabled', True); e.step()
        for name, expected in [('FIntRounded', 9007199254740992.0), ('FIntDword', 4294967295.0),
                               ('FIntUnsigned', float(1 << 64)), ('FIntMinimum', float(-(1 << 63))),
                               ('FIntFraction', 1.5), ('FIntCompare', True), ('FIntConverted', 2)]:
            self.assertEqual(e.memory.read(name), expected)
        for tag in ['FIntRangeFault', 'FIntDomainFault']:
            e.memory.write(tag, True); self.fault(e); e.memory.write(tag, False); e.step()
        e.memory.write('FIntIndex', 1); e.memory.write('FIntLateDivisor', 0); self.fault(e, 'zero')
        self.assertEqual(e.memory.read('FIntSelected'), [9007199254740994.0, None, 903.0])
        e.memory.write('FIntLateDivisor', 1); e.step()
        self.assertEqual(e.memory.read('FIntSelected'), [9007199254740994.0, 9007199254740998.0, 903.0])
        e.memory.write('FIntEnabled', False); e.memory.write('FIntIndex', 999); e.step()
