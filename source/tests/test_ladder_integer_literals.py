"""Exact decimal L/U/UL constants in direct ladder CPT/CMP only."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_ladder_wide_expressions as fixtures
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

CASES = [('LINT', '9223372036854775807L', 9223372036854775807),
         ('LINT', '-9223372036854775808L', -9223372036854775808),
         ('UDINT', '4294967295U', 4294967295),
         ('ULINT', '18446744073709551615UL', 18446744073709551615)]
BAD = [('LINT', '9223372036854775808L'), ('LINT', '-9223372036854775809L'),
       ('UDINT', '4294967296U'), ('UDINT', '-1U'),
       ('ULINT', '18446744073709551616UL'), ('ULINT', '-1UL')]


class LadderIntegerLiteralTests(unittest.TestCase):
    setUp = fixtures.LadderWideExpressionTests.setUp
    engine = fixtures.LadderWideExpressionTests.engine
    checked = fixtures.LadderWideExpressionTests.checked

    def snapshot(self, e):
        return (fixtures.LadderWideExpressionTests.snapshot(self, e),
                copy.deepcopy(e.addons.instances))

    def fault(self, e, match='overflow|zero|Unknown|outside bounds'):
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, match):
            e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_full_width_constants_establish_unknown_destinations_exactly(self):
        for dtype, text, expected in CASES:
            e = self.checked(['CPT(Dest,' + text + ');'], dtype=dtype)
            e.memory.values['dest'] = None
            e.step()
            self.assertEqual(e.memory.read('Dest'), expected)
            self.assertIs(type(e.memory.read('Dest')), int)

    def test_decimal_magnitude_case_and_unary_signs(self):
        for dtype, text, expected in [('LINT', '-(9223372036854775808l)', -9223372036854775808),
                                     ('LINT', '+00042L', 42), ('UDINT', '-0u', 0),
                                     ('ULINT', '42ul', 42), ('ULINT', '42Ul', 42), ('ULINT', '42uL', 42)]:
            e = self.checked(['CPT(Dest,' + text + ');'], dtype=dtype)
            e.step()
            self.assertEqual(e.memory.read('Dest'), expected)

    def test_arithmetic_and_quotients_remain_exact_above_double_precision(self):
        for dtype, text, expected in [('LINT', '9007199254740993L+2L', 9007199254740995),
                                     ('LINT', '-9223372036854775808L/3L', -3074457345618258602),
                                     ('LINT', '-9223372036854775808L MOD 3L', -2),
                                     ('UDINT', '4294967295U/3U', 1431655765),
                                     ('ULINT', '18446744073709551615UL/3UL', 6148914691236517205),
                                     ('LINT', 'ABS(-7L)*2L-1', 13)]:
            e = self.checked(['CPT(Dest,' + text + ');'], dtype=dtype)
            e.step()
            self.assertEqual(e.memory.read('Dest'), expected)

    def test_matching_tags_and_untyped_dint_constants_combine(self):
        for dtype, suffix in [('LINT', 'L'), ('UDINT', 'U'), ('ULINT', 'UL')]:
            e = self.checked(['CPT(Dest,Source+2' + suffix + '+1);',
                              'CMP(Source>1' + suffix + ')OTE(RunLatch);'], dtype=dtype)
            e.step()
            self.assertEqual(e.memory.read('Dest'), 10)
            self.assertTrue(e.memory.read('RunLatch'))

    def test_aliases_program_locals_and_tag_suffix_text_preserve_identity(self):
        def tags(root):
            controller = root.find('Controller')
            E.SubElement(controller.find('Tags'), 'Tag', Name='Source1L', TagType='Alias',
                         DataType='LINT', AliasFor='Source')
            E.SubElement(controller.find('Tags'), 'Tag', Name='AliasDest', TagType='Alias',
                         DataType='LINT', AliasFor='Dest')
            tag = E.SubElement(controller.find('./Programs/Program/Tags'), 'Tag',
                               Name='Local', TagType='Base', DataType='LINT')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue',
                         DataType='LINT', Value='0')
        e = self.checked(['CPT(Local,Source1L+2L);', 'CPT(AliasDest,Local+1L);',
                          'CMP(AliasDest=9007199254740996L)OTE(RunLatch);'],
                         values=(9007199254740993, 3, 13), mutate=tags)
        e.step()
        self.assertEqual(e.memory.read('Dest'), 9007199254740996)
        self.assertTrue(e.memory.read('RunLatch'))
        expression = Expression('9007199254740993L+2L', integer_literals=True)
        self.assertEqual(expression.refs, [])
        self.assertEqual(expression.typed_types, {'LINT'})

    def test_bitwise_constants_use_the_declared_width(self):
        for dtype, text, expected in [('LINT', 'NOT 0L', -1), ('UDINT', 'NOT 0U', 4294967295),
                                     ('ULINT', 'NOT 0UL', 18446744073709551615),
                                     ('ULINT', '9223372036854775808UL OR 1UL', 9223372036854775809),
                                     ('ULINT', '18446744073709551615UL AND 3UL XOR 1UL', 2)]:
            e = self.checked(['CPT(Dest,' + text + ');'], dtype=dtype)
            e.step()
            self.assertEqual(e.memory.read('Dest'), expected)

    def test_literal_only_relations_and_boolean_composition_select_integer_profile(self):
        for op, expected in [('=', False), ('<>', True), ('<', True), ('<=', True), ('>', False), ('>=', False)]:
            e = self.checked(['CMP(9007199254740992L' + op + '9007199254740993L)OTE(RunLatch);'])
            e.step()
            self.assertEqual(e.memory.read('RunLatch'), expected)
        e = self.checked(['CMP((18446744073709551615UL=NOT 0UL)&&!StartPB)OTE(RunLatch);'])
        e.step()
        self.assertTrue(e.memory.read('RunLatch'))

    def test_invalid_declared_ranges_block_even_false_calls(self):
        for dtype, text in BAD:
            for rung in ['AFI()CPT(Dest,' + text + ');', 'AFI()CMP(' + text + '=0)OTE(RunLatch);']:
                self.assertTrue(self.engine([rung], dtype=dtype).blockers, rung)

    def test_malformed_radix_and_other_typed_forms_remain_blocked(self):
        for text in ['1LU', '1ULL', '1ULgarbage', '1L2', '1 U', '1_000L',
                     '16#FFU', '2#11UL', '8#77L', 'LINT#1', '1.0UL', '1e3U']:
            self.assertTrue(self.engine(['AFI()CPT(Dest,' + text + ');']).blockers, text)

    def test_matching_type_boundary_rejects_narrow_mixed_and_floating_combinations(self):
        for dtype, text in [('LINT', '1U'), ('ULINT', '1L'), ('UINT', '1U'),
                            ('DINT', '1L'), ('REAL', '1L'), ('LREAL', '1LU'),
                            ('LINT', '1L+1U'), ('LINT', '1L+0.5'), ('LINT', '1L+1e999L')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,' + text + ');'], dtype=dtype).blockers, (dtype, text))
        self.assertTrue(self.engine(['CPT(Dest,Source+1L);'], types=('DINT', 'LINT', 'LINT')).blockers)

    def test_existing_function_power_bcd_and_unsigned_immediate_guards_remain(self):
        for text in ['SQR(1L)', 'TRN(1L)', '1L**2', 'FRD(1U)', 'TOD(1U)', '1L+2147483648']:
            self.assertTrue(self.engine(['AFI()CPT(Dest,' + text + ');']).blockers, text)

    def test_false_calls_and_prescan_skip_domains_but_required_cmp_sides_are_eager(self):
        e = self.checked(['AFI()CPT(Dest,1L/0L);', 'AFI()CMP(1L/0L>0)OTE(RunLatch);'])
        e.step()
        self.assertEqual(e.memory.read('Dest'), 13)
        for text in ['(1L=1L)||(1L/0L>0)', '(0L=1L)&&(1L/0L>0)']:
            e = self.checked(['CMP(' + text + ')OTE(RunLatch);'])
            self.fault(e, 'zero')

    def test_unknown_required_source_and_full_write_contract(self):
        e = self.checked(['XIC(StartPB)CPT(Dest,Source+9007199254740993L);'])
        e.memory.values['source'] = None
        e.step()
        e.memory.write('StartPB', True)
        self.fault(e, 'Unknown')
        e.memory.write('Source', 2)
        e.step()
        self.assertEqual(e.memory.read('Dest'), 9007199254740995)

    def test_intermediate_and_late_faults_restore_all_earlier_writes(self):
        for dtype, text in [('LINT', '9223372036854775807L+1L'), ('ULINT', '0UL-1UL'),
                            ('LINT', 'ABS(-9223372036854775808L)'), ('LINT', '-9223372036854775808L/-1L'),
                            ('UDINT', '4294967295U+1U'), ('ULINT', '1UL/0UL')]:
            e = self.checked(['MOV(99,SpeedCommand);', 'CPT(Dest,' + text + ');'], dtype=dtype)
            self.fault(e)
        e = self.checked(['CPT(Dest,9007199254740993L);', 'DIV(1,0,SpeedCommand);'])
        self.fault(e, 'zero')

    def test_v35_5580_gate_also_applies_to_literal_only_comparisons(self):
        for key, value in [('ProcessorType', '1756-L75'), ('ProcessorType', '5069-L340ERM'), ('MajorRev', '34')]:
            e = self.engine(['AFI()CMP(1L=1L)OTE(RunLatch);'], dtype='DINT',
                            mutate=lambda root: root.find('Controller').set(key, value))
            self.assertTrue(e.blockers)

    def test_generic_file_and_index_consumers_do_not_gain_ladder_suffixes(self):
        for create, text in [(Expression, '1L'), (Condition, '1U=1U'),
                             (lambda text: Expression(text, subscript=True), '1UL')]:
            with self.assertRaises(ModelError):
                create(text)
        e = self.checked(['CPT(Dest,1L);'])
        self.assertIn(('1L', True, True, True), e.extensions.expressions)
        with self.assertRaisesRegex(ModelError, 'qualified'):
            Expression('1L', integer_literals=True).evaluate(e.memory)
        import test_file_bcd as files
        f = files.FileBcdTests(); f.setUp(); self.addCleanup(f.doCleanups)
        for rung in ['FAL(Ctl,?,?,ALL,Results[Ctl.POS],1L);', 'FSC(Ctl,?,?,ALL,1L=1L);']:
            self.assertTrue(f.engine([rung]).blockers)

    @staticmethod
    def aoi_fields(root):
        import test_aoi_queues as queues
        for node in root.iter():
            if node.get('DataType') == 'DINT':
                node.set('DataType', 'LINT')
        # Array indices and loop/queue control stay narrow DINT.
        for node in root.iter():
            if node.get('Name') in ('Index', 'IndexA', 'IndexB', 'FaultDivisor', 'FaultResult'):
                for child in node.iter():
                    if child.get('DataType') == 'LINT': child.set('DataType', 'DINT')
        queues.logic(root, ['CPT(Stack[Index],Value+9007199254740993L);',
                            'CPT(Buffer[Index],Value+2L);', 'CPT(Item,Value+1L);',
                            'CMP(Stack[Index]>9007199254740993L)OTE(EnableOut);'])
        queues.logic(root, ['AFI()CPT(Stack[Index],1L/0L);'], name='EnableInFalse')

    def test_warm_aoi_copied_outputs_inout_local_and_late_rollback(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests(); f.setUp(); self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_fields)
        e.memory.write('ValueA', 3); e.step()
        self.assertEqual(e.memory.read('DriverA.Stack[1]'), 9007199254740996)
        self.assertEqual(e.memory.read('BufferA[1]'), 5)
        self.assertEqual(e.memory.read('ItemA'), 4)
        e.memory.write('ValueA', 9223372036854775807); self.fault(e, 'overflow')
        e.memory.write('ValueA', 7); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 9)
        e.memory.write('EnabledA', False); e.memory.write('IndexA', 999); e.step()

    def test_report_states_literal_profile_without_native_equivalence(self):
        row = self.checked(['CPT(Dest,1L);']).report()['wide_ladder_expressions']
        self.assertEqual(row['typed_integer_literals']['instructions'], ['CPT', 'CMP'])
        self.assertFalse(row['typed_integer_literals']['native_runtime_parity'])

    def test_wide_expression_lab_exact_constants_and_recovery(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step()
        self.assertEqual(e.memory.read('ILitSelected'), [None, None, 903])
        e.memory.write('ILitEnabled', True); e.step()
        for name, expected in [('ILitSigned', -9223372036854775808), ('ILitUnsigned', 18446744073709551615),
                               ('ILitDword', 4294967295), ('ILitNot', 18446744073709551615),
                               ('ILitQuotient', 6148914691236517205), ('ILitExact', True)]:
            self.assertEqual(e.memory.read(name), expected)
        e.memory.write('ILitIndex', 1); e.memory.write('ILitLateDivisor', 0); self.fault(e, 'zero')
        self.assertEqual(e.memory.read('ILitSelected'), [9007199254740995, None, 903])
        e.memory.write('ILitLateDivisor', 1); e.step()
        self.assertEqual(e.memory.read('ILitSelected'), [9007199254740995, 9007199254740999, 903])
        e.memory.write('ILitOverflow', True); self.fault(e, 'overflow')
        e.memory.write('ILitOverflow', False); e.memory.write('ILitEnabled', False)
        e.memory.write('ILitIndex', 999); e.step()
