"""Lazy scalar arithmetic/bitwise validation with existing calculation rules."""
import copy
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
from logixlab.model import ModelError

EXPECTED = {'ADD': 10, 'SUB': 4, 'MUL': 21, 'DIV': 2, 'MOD': 1,
            'NEG': -7, 'ABS': 7, 'AND': 3, 'OR': 7, 'XOR': 4, 'NOT': -8}
UNARY = {'NEG', 'ABS', 'NOT'}


def operation(name, source='Source', other='Mask', dest='Results[1]'):
    return name + '(' + ','.join((source, dest) if name in UNARY else (source, other, dest)) + ')'


class ScalarMathTests(unittest.TestCase):
    setUp = fixtures.NumericStorageTests.setUp
    checked = fixtures.NumericStorageTests.checked
    snapshot = staticmethod(fixtures.NumericStorageTests.snapshot)

    def engine(self, rungs=None, *, dtype='DINT', source=None, dest=None, value=7, mutate=None):
        def fields(root):
            if dtype != 'DINT':
                tag = root.find('./Controller/Tags/Tag[@Name="Mask"]');tag.set('DataType', dtype)
                tag.find('Data/DataValue').set('DataType', dtype)
            root.find('./Controller/Tags/Tag[@Name="Mask"]/Data/DataValue').set('Value', '3')
            if mutate:mutate(root)
        return fixtures.NumericStorageTests.engine(self, rungs or ['ADD(Source,Mask,Results[1]);'],
                                                   source=source or dtype, dest=dest or dtype, value=value, mutate=fields)

    def test_all_eleven_instructions_establish_unknown_destination_elements(self):
        for name, expected in EXPECTED.items():
            e = self.checked([operation(name) + ';']);self.assertEqual(e.memory.read('Results'), [None] * 3)
            e.step();self.assertEqual(e.memory.read('Results'), [None, expected, None]);self.assertEqual(e.memory.read('Source'), 7)

    def test_integer_carry_and_borrow_contacts(self):
        pairs = [(kind, kind) for kind in ('SINT', 'INT', 'DINT', 'LINT')]
        pairs.append(('LINT', 'DINT'))
        for source, dest in pairs:
            with self.subTest(source=source, dest=dest):
                e = self.checked([
                    'ADD(Source,Mask,Results[0])XIC(S:C)OTE(RunLatch);',
                    'SUB(Mask,Source,Results[1])XIC(s:c)OTE(MotorRunning);',
                ], dtype=dest, source=source, value=-1)
                e.memory.write('Mask', 1)
                e.step()
                self.assertEqual(e.memory.read('Results'), [0, 2, None])
                self.assertTrue(e.memory.read('RunLatch'))
                self.assertTrue(e.memory.read('MotorRunning'))
                e.memory.write('Source', 0)
                e.step()
                self.assertEqual(e.memory.read('Results'), [1, 1, None])
                self.assertFalse(e.memory.read('RunLatch'))
                self.assertFalse(e.memory.read('MotorRunning'))

    def test_carry_updates_only_on_executed_integer_add_sub_in_the_rung(self):
        e = self.checked([
            '[ADD(-1,1,Results[0]),AFI()ADD(1,1,Results[1])]CPT(SpeedCommand,2+2)XIC(S:C)OTE(RunLatch);',
            'ADD(-1,1,Results[0])ADD(1,1,Results[2])XIO(S:C)OTE(MotorRunning);',
            'XIO(S:C)OTE(StartPB);',
        ])
        e.step()
        self.assertEqual(e.memory.read('Results'), [0, None, 2])
        self.assertEqual(e.memory.read('SpeedCommand'), 4)
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertTrue(e.memory.read('MotorRunning'))
        self.assertTrue(e.memory.read('StartPB'))
        self.assertIsNone(e.memory.rung_carry)

    def test_nested_routine_does_not_inherit_or_overwrite_caller_carry(self):
        def add_worker(root):
            routines = root.find('./Controller/Programs/Program/Routines')
            body = E.SubElement(E.SubElement(routines, 'Routine', Name='Worker', Type='RLL'), 'RLLContent')
            for number, text in enumerate(('XIC(S:C)OTE(MotorRunning);', 'ADD(1,1,Results[2]);')):
                E.SubElement(E.SubElement(body, 'Rung', Number=str(number), Type='N'), 'Text').text = text

        e = self.checked(['ADD(-1,1,Results[0])JSR(Worker,0)XIC(S:C)OTE(RunLatch);'], mutate=add_worker)
        e.step()
        self.assertEqual(e.memory.read('Results'), [0, None, 2])
        self.assertFalse(e.memory.read('MotorRunning'))
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertIsNone(e.memory.rung_carry)

    def test_carry_participates_in_scan_rollback_and_requires_contacts(self):
        def older_controller(root):
            root.find('Controller').set('ProcessorType', '1756-L75')

        self.assertTrue(self.engine(['OTE(S:C);']).blockers)
        self.assertTrue(self.engine(['ONS(S:C);']).blockers)
        self.assertTrue(self.engine(['XIC(S:C)OTE(RunLatch);'], mutate=older_controller).blockers)
        e = self.checked(['ADD(-1,1,Results[0])XIC(S:C)OTE(RunLatch);', 'CPT(SpeedCommand,1/Index);'])
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):
            e.step()
        self.assertEqual(self.snapshot(e), before)
        self.assertIsNone(e.memory.rung_carry)
        e.memory.write('Index', 1)
        e.step()
        self.assertTrue(e.memory.read('RunLatch'))

    def test_zero_and_negative_flags_observe_the_converted_store(self):
        cases = (
            ('DIV(-1.0,4.0,Dest)', 'DINT', 0, True, False),
            ('DIV(-3.0,2.0,Dest)', 'DINT', -2, False, True),
            ('DIV(2.0,0.0,Dest)', 'DINT', 2147483647, False, False),
            ('NOT(0,Dest)', 'DINT', -1, False, True),
            ('MOV(-1,Dest)', 'USINT', 255, False, False),
            ('TRN(-0.5,Dest)', 'REAL', -0.0, True, False),
            ('ABS(-2,Dest)', 'LREAL', 2.0, False, False),
            ('SQR(0,Dest)', 'LREAL', 0.0, True, False),
            ('MOD(1.0,0.0,Dest)', 'REAL', 0.0, True, False),
        )
        for instruction, dest, result, zero, negative in cases:
            with self.subTest(instruction=instruction, dest=dest):
                e = self.checked([f'{instruction}[XIC(S:Z)OTE(RunLatch),XIC(S:N)OTE(MotorRunning)];'],
                                 dest=dest)
                e.step()
                self.assertEqual(e.memory.read('Dest'), result)
                self.assertEqual(e.memory.read('RunLatch'), zero)
                self.assertEqual(e.memory.read('MotorRunning'), negative)

    def test_zero_and_negative_flags_are_replaced_and_isolated_by_rung_and_call(self):
        def add_worker(root):
            routines = root.find('./Controller/Programs/Program/Routines')
            body = E.SubElement(E.SubElement(routines, 'Routine', Name='Worker', Type='RLL'), 'RLLContent')
            E.SubElement(E.SubElement(body, 'Rung', Number='0', Type='N'), 'Text').text = 'CLR(Dest);'

        e = self.checked([
            'SUB(1,2,Results[0])JSR(Worker,0)XIC(S:N)OTE(RunLatch);',
            'XIC(S:N)OTE(StartPB);',
            'SUB(1,2,Results[1])CLR(Results[2])XIO(S:N)XIC(S:Z)OTE(MotorRunning);',
        ], mutate=add_worker)
        e.step()
        self.assertEqual(e.memory.read('Results'), [-1, -1, 0])
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertFalse(e.memory.read('StartPB'))
        self.assertTrue(e.memory.read('MotorRunning'))
        self.assertIsNone(e.memory.rung_math_result)

    def test_zero_and_negative_flag_consumers_skip_false_and_require_contacts(self):
        self.assertTrue(self.engine(['OTE(S:N);']).blockers)
        self.assertTrue(self.engine(['ONS(S:Z);']).blockers)
        e = self.checked([
            '[CLR(Dest),AFI()SUB(1,2,Results[1])]XIC(S:Z)OTE(RunLatch);',
            'ASN(2.0,Results[2])[XIC(S:Z)OTE(StartPB),XIC(S:N)OTE(MotorRunning)];',
            'XIC(S:N)OTE(StopPB);',
        ], dest='REAL')
        e.step()
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertFalse(e.memory.read('StartPB'))
        self.assertFalse(e.memory.read('MotorRunning'))
        self.assertFalse(e.memory.read('StopPB'))

    def test_overflow_contacts_coils_and_task_reporting(self):
        self.assertTrue(self.engine(['ONS(S:V);']).blockers)
        for reporting in (False, True):
            with self.subTest(reporting=reporting):
                def configure(root):
                    root.find('Controller').set('ReportMinorOverflow', str(reporting).lower())
                    for name in ('Cleared', 'OteCleared', 'MinorSeen'):
                        tag = E.SubElement(root.find('Controller/Tags'), 'Tag', Name=name,
                                           TagType='Base', DataType='BOOL')
                        E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue',
                                     DataType='BOOL', Value='0')

                e = self.checked([
                    '[XIC(StartPB)OTE(S:V),AFI()OTL(S:V)]XIC(S:V)OTE(RunLatch);',
                    'XIC(S:V)OTE(StopPB);',
                    '[XIC(StartPB)OTL(S:V),AFI()OTU(S:V)]XIC(S:V)OTE(MotorRunning);',
                    'XIC(StartPB)OTL(S:V)OTU(s:v)XIO(S:V)OTE(Cleared);',
                    '[XIC(StartPB)OTL(S:V),AFI()OTE(S:V)]XIO(S:V)OTE(OteCleared);',
                    'XIC(S:MINOR)OTE(MinorSeen);',
                ], mutate=configure)
                e.memory.write('StartPB', True)
                e.step()
                self.assertTrue(e.memory.read('RunLatch'))
                self.assertFalse(e.memory.read('StopPB'))
                self.assertTrue(e.memory.read('MotorRunning'))
                self.assertTrue(e.memory.read('Cleared'))
                self.assertTrue(e.memory.read('OteCleared'))
                self.assertEqual(e.memory.read('MinorSeen'), reporting)
                e.memory.write('StartPB', False)
                e.step()
                self.assertFalse(e.memory.read('RunLatch'))
                self.assertFalse(e.memory.read('MotorRunning'))
                self.assertFalse(e.memory.read('MinorSeen'))
                self.assertFalse(e.memory.rung_overflow)

    def test_overflow_producers_replace_flag_and_keep_caller_state(self):
        def add_worker(root):
            routines = root.find('./Controller/Programs/Program/Routines')
            body = E.SubElement(E.SubElement(routines, 'Routine', Name='Worker', Type='RLL'), 'RLLContent')
            E.SubElement(E.SubElement(body, 'Rung', Number='0', Type='N'), 'Text').text = 'XIC(S:V)OTE(StopPB);'

        e = self.checked([
            'MOV(Source,Results[0])JSR(Worker,0)XIC(S:V)OTE(RunLatch);',
            'DIV(1,0,SpeedCommand)XIC(S:V)OTE(StartPB);',
            'MOV(Source,Results[1])CLR(Results[2])XIO(S:V)OTE(MotorRunning);',
        ], source='DINT', dest='SINT', value=129, mutate=add_worker)
        e.step()
        self.assertEqual(e.memory.read('Results'), [-127, -127, 0])
        self.assertFalse(e.memory.read('StopPB'))
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertTrue(e.memory.read('StartPB'))
        self.assertTrue(e.memory.read('MotorRunning'))
        e.memory.write('Source', 1)
        e.step()
        self.assertEqual(e.memory.read('Results'), [1, 1, 0])
        self.assertFalse(e.memory.read('RunLatch'))
        self.assertFalse(e.memory.rung_overflow)

    def test_integer_mod_zero_retains_the_old_fault_policy_outside_v35_5580(self):
        def target(root):
            root.find('Controller').set('ProcessorType', '1756-L75')

        e = self.checked(['MOD(Source,0,SpeedCommand);'], mutate=target)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'MOD divide by zero'):
            e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_false_rungs_skip_unknown_values_and_invalid_indices_for_every_instruction(self):
        for name in EXPECTED:
            text = operation(name, source='Inputs[Index]', dest='Results[Index]')
            e = self.checked(['XIC(StartPB)' + text + ';']);e.memory.write('Index', 999)
            reads = [];original = e.memory.read
            def read(ref, scope=''):
                if not e.memory.structural:reads.append(ref)
                return original(ref, scope)
            with patch.object(e.memory, 'read', side_effect=read):e.step()
            self.assertNotIn('Index', reads);self.assertNotIn('Inputs[Index]', reads)
            self.assertEqual(e.memory.read('Results'), [None] * 3);self.assertFalse(e.memory.structural)

    def test_each_required_unknown_source_faults_when_enabled_then_retries(self):
        for name, expected in EXPECTED.items():
            e = self.checked(['MOV(99,SpeedCommand);', 'XIC(StartPB)' + operation(name, source='Inputs[0]') + ';']);e.step()
            e.memory.write('StartPB', True);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Inputs[0]', 7);e.step();self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_each_binary_instruction_requires_its_second_source(self):
        for name, expected in EXPECTED.items():
            if name in UNARY:continue
            e = self.checked(['MOV(99,SpeedCommand);', operation(name, other='Inputs[0]') + ';']);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Inputs[0]', 3);e.step();self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_real_arithmetic_retains_existing_results_and_full_writes(self):
        for name, expected in (('ADD', 10.5), ('SUB', 4.5), ('MUL', 22.5), ('DIV', 2.5), ('NEG', -7.5), ('ABS', 7.5)):
            e = self.checked([operation(name) + ';'], source='REAL', dest='REAL', value=7.5)
            e.step();self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_all_five_wide_types_retain_homogeneous_calculations_with_unknown_destinations(self):
        for dtype, bits in (('LINT', 64), ('USINT', 8), ('UINT', 16), ('UDINT', 32), ('ULINT', 64)):
            for name, result in EXPECTED.items():
                value = 0 if name == 'NEG' and dtype != 'LINT' else 7
                expected = 0 if name == 'NEG' and dtype != 'LINT' else (1 << bits) - 8 if name == 'NOT' and dtype != 'LINT' else result
                e = self.checked([operation(name) + ';'], dtype=dtype, value=value);e.step()
                self.assertEqual(e.memory.read('Results[1]'), expected, (dtype, name))

    def test_wide_exact_values_and_homogeneous_type_gates_are_unchanged(self):
        e = self.checked(['ADD(Inputs[0],Mask,Results[0]);'], dtype='ULINT');e.memory.write('Inputs[0]', 9007199254740993)
        e.step();self.assertEqual(e.memory.read('Results[0]'), 9007199254740996)
        narrowed=self.checked(dtype='LINT',dest='DINT');narrowed.step();self.assertEqual(narrowed.memory.read('Results[1]'),10)
        narrowed.memory.write('Source',1<<31)
        with self.assertRaisesRegex(ModelError,'overflow|range'):narrowed.step()
        self.assertTrue(self.engine(['ADD(Source,2147483648,Results[0]);'], dtype='LINT').blockers)
        self.assertTrue(self.engine(['ADD(Source,-1,Results[0]);'], dtype='ULINT').blockers)

    def test_false_rungs_skip_zero_divisors_and_true_rungs_complete(self):
        for name, zero_result in (('DIV', 7), ('MOD', 0)):
            e = self.checked(['MOV(99,SpeedCommand);', 'XIC(StartPB)' + operation(name) + ';']);e.memory.write('Mask', 0);e.step()
            self.assertEqual(e.memory.read('Results'), [None, None, None])
            e.memory.write('StartPB', True);e.step()
            self.assertEqual(e.memory.read('Results[1]'), zero_result)
            e.memory.write('Mask', 3);e.step();self.assertEqual(e.memory.read('Results[1]'), EXPECTED[name])

    def test_integer_division_and_remainder_sign_and_real_destination_rounding_remain(self):
        e = self.checked(['DIV(Source,Mask,Results[0]);', 'MOD(Source,Mask,Results[1]);'], value=-7)
        e.step();self.assertEqual(e.memory.read('Results')[:2], [-2, -1])
        e = self.checked(['DIV(Source,Mask,Results[0]);'], source='REAL', value=7.5)
        e.step();self.assertEqual(e.memory.read('Results[0]'), 2)
        e = self.checked(['DIV(Source,Mask,Results[0]);'], dest='REAL')
        e.step();self.assertAlmostEqual(e.memory.read('Results[0]'), 7 / 3, places=6)

    def test_prescan_retains_unknown_outputs_and_skipped_references(self):
        e = self.checked([operation(name, source='Inputs[Index]') + ';' for name in EXPECTED])
        self.assertEqual(e.scan_count, 0);self.assertEqual(e.memory.read('Results'), [None] * 3)
        self.assertEqual(e.memory.read('Inputs'), [None] * 3)

    def test_actual_destination_index_is_required_only_when_enabled(self):
        e = self.checked(['XIC(StartPB)ADD(Source,Mask,Results[Index]);']);e.memory.write('Index', 999);e.step()
        e.memory.write('StartPB', True);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Index', 2);e.step();self.assertEqual(e.memory.read('Results'), [None, None, 10])

    def test_signed_add_sub_wrap_and_publish_stored_result_status(self):
        for dtype, bits in (('SINT', 8), ('INT', 16), ('DINT', 32)):
            with self.subTest(dtype=dtype):
                limit = 1 << (bits - 1)
                e = self.checked([
                    'ADD(Source,Mask,Results[0])XIC(S:V)XIC(S:N)XIO(S:C)OTE(RunLatch);',
                    'SUB(Results[0],Mask,Results[1])XIC(S:V)XIO(S:N)XIO(S:C)OTE(MotorRunning);',
                    'ADD(Results[0],Results[0],Results[2])XIC(S:V)XIC(S:C)XIC(S:Z)OTE(StopPB);',
                ], dtype=dtype, value=limit - 1)
                e.memory.write('Mask', 1)
                e.step()
                self.assertEqual(e.memory.read('Results'), [-limit, limit - 1, 0])
                for tag in ('RunLatch', 'MotorRunning', 'StopPB'):
                    self.assertTrue(e.memory.read(tag))
                e.memory.write('Source', 2)
                e.step()
                self.assertEqual(e.memory.read('Results'), [3, 2, 6])
                for tag in ('RunLatch', 'MotorRunning', 'StopPB'):
                    self.assertFalse(e.memory.read(tag))

    def test_later_overflow_rolls_back_a_wrapped_add_and_its_coil(self):
        e = self.checked([
            'ADD(Source,1,Results[0])XIC(S:V)OTE(RunLatch);',
            'CPT(Results[1],Source*Mask);',
        ], dtype='SINT', value=127)
        e.memory.write('Mask', 2)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'overflow'):e.step()
        self.assertEqual(self.snapshot(e), before)
        self.assertFalse(e.memory.rung_overflow)
        e.memory.write('Mask', 1)
        e.step()
        self.assertEqual(e.memory.read('Results'), [-128, 127, None])
        self.assertTrue(e.memory.read('RunLatch'))

    def test_integer_multiply_truncates_narrow_result_and_preserves_carry(self):
        cases = (
            ('SINT', 64, 2, -128),
            ('SINT', 64, 4, 0),
            ('INT', 12000, 3, -29536),
            ('INT', -12000, 3, 29536),
        )
        for dtype, source, mask, stored in cases:
            with self.subTest(dtype=dtype, source=source, mask=mask):
                e = self.checked([
                    'XIC(StartPB)ADD(-1,1,Results[2])MUL(Source,Mask,Results[0])'
                    '[XIC(S:C)XIC(S:V)OTE(RunLatch),XIC(S:N)OTE(MotorRunning),XIC(S:Z)OTE(StopPB)];',
                ], dtype=dtype, value=source)
                e.memory.write('Mask', mask)
                e.step()
                self.assertEqual(e.memory.read('Results'), [None, None, None])
                e.memory.write('StartPB', True)
                e.step()
                self.assertEqual(e.memory.read('Results'), [stored, None, 0])
                self.assertTrue(e.memory.read('RunLatch'))
                self.assertEqual(e.memory.read('MotorRunning'), stored < 0)
                self.assertEqual(e.memory.read('StopPB'), stored == 0)
                e.memory.write('Mask', 1)
                e.step()
                self.assertEqual(e.memory.read('Results'), [source, None, 0])
                self.assertFalse(e.memory.read('RunLatch'))

    def test_radix_multiply_truncates_small_result_but_checks_dint_range(self):
        e = self.checked(['MUL(16#FFFFFF80,-1,Results[0])XIC(S:V)OTE(RunLatch);'], dest='SINT')
        e.step()
        self.assertEqual(e.memory.read('Results'), [-128, None, None])
        self.assertTrue(e.memory.read('RunLatch'))
        for dest in ('SINT', 'INT', 'DINT'):
            with self.subTest(dest=dest):
                e = self.checked(['MOV(99,SpeedCommand);', 'MUL(Source,2,Results[0]);'],
                                 source='DINT', dest=dest, value=2147483647)
                before = self.snapshot(e)
                with self.assertRaisesRegex(ModelError, 'overflow'):
                    e.step()
                self.assertEqual(self.snapshot(e), before)

    def test_integer_div_mod_narrow_the_signed_quotient_and_remainder(self):
        for dtype, dividend, divisor, quotient, remainder in (
                ('SINT', 25675, 131, -61, -126),
                ('SINT', -25675, 131, 61, 126),
                ('INT', 1600039999, 40000, -25536, -25537),
                ('INT', -1600039999, 40000, 25536, 25537)):
            with self.subTest(dtype=dtype, dividend=dividend):
                e = self.checked([
                    'ADD(-1,1,Results[2])DIV(Source,Mask,Results[0])XIC(S:C)XIC(S:V)OTE(RunLatch);',
                    'MOD(Source,Mask,Results[1])[XIC(S:V)OTE(MotorRunning),XIC(S:N)OTE(StopPB)];',
                ], dest=dtype, value=dividend)
                e.memory.write('Mask', divisor)
                e.step()
                self.assertEqual(e.memory.read('Results'), [quotient, remainder, 0])
                self.assertTrue(e.memory.read('RunLatch'))
                self.assertTrue(e.memory.read('MotorRunning'))
                self.assertEqual(e.memory.read('StopPB'), remainder < 0)
                e.memory.write('Source', -7)
                e.memory.write('Mask', 3)
                e.step()
                self.assertEqual(e.memory.read('Results'), [-2, -1, 0])
                self.assertFalse(e.memory.read('RunLatch'))
                self.assertFalse(e.memory.read('MotorRunning'))

    def test_narrow_signed_div_accepts_radix_but_checks_dint_quotient_range(self):
        e = self.checked(['DIV(16#FFFFFF80,-1,Results[0])XIC(S:V)OTE(RunLatch);'], dest='SINT')
        e.step()
        self.assertEqual(e.memory.read('Results'), [-128, None, None])
        self.assertTrue(e.memory.read('RunLatch'))
        for dest in ('SINT', 'INT', 'DINT'):
            with self.subTest(dest=dest):
                e = self.checked(['MOV(99,SpeedCommand);', 'DIV(Source,-1,Results[0]);'],
                                 dest=dest, value=-2147483648)
                before = self.snapshot(e)
                with self.assertRaisesRegex(ModelError, 'overflow'):
                    e.step()
                self.assertEqual(self.snapshot(e), before)

    def test_real_arithmetic_narrows_rounded_results_into_sint_and_int(self):
        for dtype, limit in (('SINT', 128), ('INT', 32768)):
            cases = (
                (f'ADD({limit - 1.5},1.0,Results[0])', -limit),
                (f'SUB(-{limit}.0,1.5,Results[0])', limit - 2),
                (f'MUL({(limit - 0.5) / 2},2,Results[0])', -limit),
                (f'DIV({2 * limit - 1}.0,2,Results[0])', -limit),
                (f'MOD({3 * limit - 0.5},{2 * limit},Results[0])', -limit),
                (f'NEG(-{limit - 0.5},Results[0])', -limit),
                (f'ABS(-{limit - 0.5},Results[0])', -limit),
            )
            for instruction, stored in cases:
                with self.subTest(dtype=dtype, instruction=instruction):
                    e = self.checked([
                        f'{instruction}[XIC(S:V)OTE(RunLatch),XIC(S:N)OTE(MotorRunning)];',
                    ], dest=dtype)
                    e.step()
                    self.assertEqual(e.memory.read('Results'), [stored, None, None])
                    self.assertTrue(e.memory.read('RunLatch'))
                    self.assertEqual(e.memory.read('MotorRunning'), stored < 0)

    def test_real_arithmetic_quantizes_result_before_rounding_to_integer(self):
        e = self.checked([
            'ADD(127.49999,0.000005,Results[0])XIC(S:V)OTE(RunLatch);',
            'ADD(126.5,0.0,Results[1])XIO(S:V)OTE(MotorRunning);',
        ], dest='SINT')
        e.step()
        self.assertEqual(e.memory.read('Results'), [-128, 126, None])
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertTrue(e.memory.read('MotorRunning'))

    def test_radix_add_wrap_reports_task_minor_and_false_rung_skips_it(self):
        def configure(root):
            root.find('Controller').set('ReportMinorOverflow', 'true')

        e = self.checked([
            'XIC(StartPB)ADD(16#80000000,-1,Results[0])XIC(S:V)OTE(RunLatch);',
            'XIC(S:MINOR)OTE(MotorRunning);',
        ], mutate=configure)
        for enabled in (False, True, False):
            e.memory.write('StartPB', enabled)
            e.step()
            self.assertEqual(e.memory.read('RunLatch'), enabled)
            self.assertEqual(e.memory.read('MotorRunning'), enabled)
        self.assertEqual(e.memory.read('Results'), [2147483647, None, None])

    def test_abs_and_neg_keep_narrow_signed_minimum_with_overflow(self):
        def configure(root):
            root.find('Controller').set('ReportMinorOverflow', 'true')

        for dtype, bits in (('SINT', 8), ('INT', 16), ('DINT', 32)):
            with self.subTest(dtype=dtype):
                minimum = -(1 << (bits - 1))
                e = self.checked([
                    'XIC(StartPB)ADD(-1,1,Results[2])ABS(Source,Results[0])XIC(S:C)XIC(S:V)XIC(S:N)OTE(RunLatch);',
                    'XIC(StartPB)NEG(Source,Results[1])XIC(S:V)XIC(S:N)OTE(MotorRunning);',
                    'XIC(S:MINOR)OTE(StopPB);',
                ], dtype=dtype, value=minimum, mutate=configure)
                e.step()
                self.assertEqual(e.memory.read('Results'), [None, None, None])
                self.assertFalse(e.memory.read('StopPB'))
                e.memory.write('StartPB', True)
                e.step()
                self.assertEqual(e.memory.read('Results'), [minimum, minimum, 0])
                for tag in ('RunLatch', 'MotorRunning', 'StopPB'):
                    self.assertTrue(e.memory.read(tag))
                e.memory.write('Source', -7)
                e.step()
                self.assertEqual(e.memory.read('Results'), [7, 7, 0])
                for tag in ('RunLatch', 'MotorRunning', 'StopPB'):
                    self.assertFalse(e.memory.read(tag))

    def test_abs_and_neg_wrap_radix_dint_but_keep_other_range_checks(self):
        e = self.checked([
            'ABS(16#80000000,Results[0])XIC(S:V)OTE(RunLatch);',
            'NEG(16#80000000,Results[1])XIC(S:V)OTE(MotorRunning);',
        ])
        e.step()
        self.assertEqual(e.memory.read('Results'), [-2147483648, -2147483648, None])
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertTrue(e.memory.read('MotorRunning'))
        for name in ('ABS', 'NEG'):
            with self.subTest(name=name):
                e = self.checked([f'{name}(Source,Results[0]);'], source='DINT', dest='SINT', value=-129)
                with self.assertRaisesRegex(ModelError, 'SINT overflow'):
                    e.step()
                self.assertEqual(e.memory.read('Results'), [None, None, None])

    def test_source_destination_overlap_and_alias_member_guards(self):
        def aliases(root):
            E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='OutputAlias', DataType='DINT', TagType='Alias', AliasFor='Results[1]')
        e = self.checked(['ADD(Source,Mask,OutputAlias);', 'MUL(Results[1],Mask,Results[1]);'], mutate=aliases)
        e.step();self.assertEqual(e.memory.read('Results'), [None, 30, None])
        e = self.checked(['ADD(Inputs[0],Inputs[1],Inputs[0]);']);e.memory.write('Inputs[0]', 7);e.memory.write('Inputs[1]', 3)
        e.step();self.assertEqual(e.memory.read('Inputs'), [10, 3, None])

    def test_types_shapes_constants_and_missing_tags_remain_blocked_even_false(self):
        for text in ('ADD(StartPB,1,Results[0]);', 'ADD(Source,1,Results);', 'ADD(Inputs,1,Results[0]);',
                     'ADD(Missing,1,Results[0]);', 'AND(1e309L,1,Results[0]);', 'NOT(StartPB,Results[0]);'):
            self.assertTrue(self.engine(['AFI()' + text]).blockers, text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()ADD(Source,Mask,Results[0]);'], mutate=constant).blockers)
        self.assertTrue(self.engine(['AND(Source,Mask,Results[0]);'], dest='BOOL').blockers)

    def test_later_failure_restores_established_values_and_scheduler(self):
        e = self.checked(['ADD(Source,Mask,Results[0]);', 'NOT(Source,Results[1]);', 'DIV(Source,Inputs[0],Results[2]);'])
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Inputs[0]', 2);e.step();self.assertEqual(e.memory.read('Results'), [10, -8, 3])

    def test_aoi_unknown_locals_inout_results_and_binding_rollback(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def logic(root):
            queues.logic(root, ['ADD(Value,1,Buffer[Index])SUB(Value,1,Stack[0])NOT(Value,Stack[1]);'])
            queues.logic(root, ['AFI()ADD(Value,1,Buffer[Index])SUB(Value,1,Stack[0]);'], name='EnableInFalse')
            for name in ('DriverA', 'DriverB'):
                array = root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]')
                for child in list(array):
                    if child.get('Index') in ('[0]', '[1]'):array.remove(child)
        e = f.checked(logic);e.step();self.assertEqual(e.memory.read('DriverA.Stack')[:2], [10, -12])
        e.memory.write('EnabledB', False);e.memory.write('IndexB', 999);e.step()
        e.memory.write('EnabledB', True);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('IndexB', 2);e.step();self.assertEqual(e.memory.read('BufferB[2]'), 23)

    def test_old_profiles_and_report_keep_qualification_boundaries(self):
        def old(root):root.find('Controller').set('ProcessorType', '1756-L75')
        e = self.checked(['ADD(Source,Mask,Dest);'], mutate=old);e.step();self.assertEqual(e.memory.read('Dest'), 10)
        self.assertFalse(e.report()['scalar_math']['available'])
        report = self.checked().report()['scalar_math'];self.assertEqual(len(report['instructions']), 11)
        self.assertFalse(report['native_runtime_parity']);self.assertFalse(report['native_math_status'])
