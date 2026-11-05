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
        self.assertTrue(self.engine(dtype='LINT', dest='DINT').blockers)
        self.assertTrue(self.engine(['ADD(Source,2147483648,Results[0]);'], dtype='LINT').blockers)
        self.assertTrue(self.engine(['ADD(Source,-1,Results[0]);'], dtype='ULINT').blockers)

    def test_zero_divisors_are_skipped_false_and_rollback_when_true(self):
        for name in ('DIV', 'MOD'):
            e = self.checked(['MOV(99,SpeedCommand);', 'XIC(StartPB)' + operation(name) + ';']);e.memory.write('Mask', 0);e.step()
            e.memory.write('StartPB', True);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'zero'):e.step()
            self.assertEqual(self.snapshot(e), before)
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

    def test_overflow_retains_existing_stop_and_rollback_policy(self):
        e = self.checked(['MOV(99,SpeedCommand);', 'ADD(Source,Mask,Results[0]);'], source='SINT', dest='SINT', value=127)
        e.memory.write('Mask', 1);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'overflow'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Source', 126);e.step();self.assertEqual(e.memory.read('Results[0]'), 127)

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
