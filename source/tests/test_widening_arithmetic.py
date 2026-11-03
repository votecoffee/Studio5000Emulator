"""Mixed integer tag arithmetic with lossless destination promotion and rollback."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_scalar_math as fixtures
from logixlab.model import ModelError

# Explicit declared-type policy, independent of the runtime's bound calculation.
DESTINATIONS = {
    'SINT': {'SINT'}, 'USINT': {'USINT'}, 'INT': {'SINT', 'USINT', 'INT'},
    'UINT': {'USINT', 'UINT'}, 'DINT': {'SINT', 'USINT', 'INT', 'UINT', 'DINT'},
    'UDINT': {'USINT', 'UINT', 'UDINT'},
    'LINT': {'SINT', 'USINT', 'INT', 'UINT', 'DINT', 'UDINT', 'LINT'},
    'ULINT': {'USINT', 'UINT', 'UDINT', 'ULINT'}}
WIDE = {'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT'}


class WideningArithmeticTests(unittest.TestCase):
    setUp = fixtures.ScalarMathTests.setUp
    checked = fixtures.ScalarMathTests.checked
    snapshot = staticmethod(fixtures.ScalarMathTests.snapshot)

    def engine(self, rungs=None, *, source='LINT', other='DINT', dest='LINT', value=7, mask=3, mutate=None):
        def fields(root):
            root.find('./Controller/Tags/Tag[@Name="Mask"]/Data/DataValue').set('Value', str(mask))
            tag = E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='OtherInputs', DataType=other, Dimensions='3', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=other, Dimensions='3')
            if mutate:mutate(root)
        return fixtures.ScalarMathTests.engine(self, rungs or ['ADD(Source,Mask,Results[1]);'],
                                               dtype=other, source=source, dest=dest, value=value, mutate=fields)

    def test_complete_mixed_wide_binary_type_gate_matrix(self):
        for a in DESTINATIONS:
            for b in DESTINATIONS:
                for dest in DESTINATIONS:
                    if not {a, b, dest} & WIDE or len({a, b, dest}) == 1:continue
                    with self.subTest(a=a, b=b, dest=dest):
                        e = self.engine(source=a, other=b, dest=dest, value=3)
                        allowed = {a, b} <= DESTINATIONS[dest]
                        self.assertEqual(not e.blockers, allowed)
                        if allowed:e.step();self.assertEqual(e.memory.read('Results'), [None, 6, None])

    def test_all_seven_operations_preserve_exact_large_signed_values(self):
        a = -9007199254740993
        expected = {'ADD': a + 3, 'SUB': a - 3, 'MUL': a * 3, 'DIV': -3002399751580331, 'MOD': 0, 'NEG': -a, 'ABS': -a}
        for name, result in expected.items():
            with self.subTest(name=name):
                args = 'Source,Results[1]' if name in ('NEG', 'ABS') else 'Source,Mask,Results[1]'
                # Unary uses a distinct source/destination type rather than a homogeneous form.
                source = 'DINT' if name in ('NEG', 'ABS') else 'LINT'
                value = -2147483648 if source == 'DINT' else a
                e = self.checked([name + '(' + args + ');'], source=source, value=value)
                with patch('logixlab.scalar_math.real', side_effect=AssertionError('Integer arithmetic used REAL')):e.step()
                self.assertEqual(e.memory.read('Results'), [None, 2147483648 if source == 'DINT' else result, None])

    def test_signed_unsigned_values_keep_their_arithmetic_meaning(self):
        cases = [('UDINT', 'DINT', 'LINT', 4294967295, -1, 'ADD', 4294967294),
                 ('DINT', 'UINT', 'LINT', -7, 65535, 'MUL', -458745),
                 ('UINT', 'USINT', 'UDINT', 65535, 3, 'ADD', 65538),
                 ('ULINT', 'USINT', 'ULINT', 18446744073709551615, 3, 'SUB', 18446744073709551612)]
        for a, b, dest, value, mask, name, result in cases:
            e = self.checked([f'{name}(Source,Mask,Results[1]);'], source=a, other=b, dest=dest, value=value, mask=mask)
            e.step();self.assertEqual(e.memory.read('Results')[1], result)
        e = self.checked(['NEG(Source,Results[1]);'], source='USINT', dest='INT', value=255)
        e.step();self.assertEqual(e.memory.read('Results')[1], -255)

    def test_division_and_remainder_signs_are_integer_exact(self):
        for a, b, quotient, remainder in [(-7, 3, -2, -1), (7, -3, -2, 1), (-7, -3, 2, -1),
                                          (-9223372036854775808, 3, -3074457345618258602, -2)]:
            e = self.checked(['DIV(Source,Mask,Results[0]);', 'MOD(Source,Mask,Results[1]);'], value=a, mask=b)
            e.step();self.assertEqual(e.memory.read('Results'), [quotient, remainder, None])

    def test_false_and_prescan_skip_unknown_values_and_live_indices(self):
        e = self.checked(['XIC(StartPB)ADD(Inputs[Index],OtherInputs[Index],Results[Index]);'])
        e.memory.write('Index', 999);e.step();self.assertEqual(e.memory.read('Results'), [None] * 3)
        e.memory.write('StartPB', True);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Index', 1);e.memory.write('Inputs[1]', 7);e.memory.write('OtherInputs[1]', 3)
        e.step();self.assertEqual(e.memory.read('Results'), [None, 10, None])

    def test_each_source_is_required_and_unknowns_roll_back_then_retry(self):
        for args, write in [('Inputs[0],Mask', 'Inputs[0]'), ('Source,OtherInputs[0]', 'OtherInputs[0]')]:
            e = self.checked(['MOV(99,SpeedCommand);', 'ADD(' + args + ',Results[1]);'], value=0)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write(write, 3);e.step();self.assertIsNotNone(e.memory.read('Results[1]'))

    def test_zero_divisors_overflow_and_unsigned_underflow_roll_back(self):
        for name, source, other, dest, value, mask, error in [
                ('ADD', 'LINT', 'DINT', 'LINT', 9223372036854775807, 1, 'overflow'),
                ('MUL', 'LINT', 'DINT', 'LINT', 4611686018427387904, 4, 'overflow'),
                ('SUB', 'USINT', 'UINT', 'UDINT', 0, 1, 'overflow'),
                ('DIV', 'LINT', 'DINT', 'LINT', 7, 0, 'zero'),
                ('MOD', 'LINT', 'DINT', 'LINT', 7, 0, 'zero')]:
            e = self.checked(['MOV(99,SpeedCommand);', f'{name}(Source,Mask,Results[1]);'], source=source, other=other, dest=dest, value=value, mask=mask)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, error):e.step()
            self.assertEqual(self.snapshot(e), before)

    def test_unknown_udt_alias_destination_preserves_sibling_and_overlap(self):
        def fields(root):
            members = E.SubElement(E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='Packet', Family='NoFamily', Class='User'), 'Members')
            for name, dtype in [('Value', 'LINT'), ('Guard', 'DINT')]:E.SubElement(members, 'Member', Name=name, DataType=dtype, Dimension='0')
            tags = root.find('./Controller/Tags');tag = E.SubElement(tags, 'Tag', Name='Packet1', DataType='Packet', TagType='Base')
            record = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='Packet')
            E.SubElement(record, 'DataValueMember', Name='Guard', DataType='DINT', Value='987')
            E.SubElement(tags, 'Tag', Name='AliasValue', DataType='LINT', TagType='Alias', AliasFor='Packet1.Value')
        e = self.checked(['ADD(Source,Mask,AliasValue);', 'MUL(AliasValue,Mask,AliasValue);'], mutate=fields)
        e.step();self.assertEqual(e.memory.read('Packet1'), {'Value': 30, 'Guard': 987})

    def test_later_fault_restores_values_unknowns_and_scheduler(self):
        e = self.checked(['ADD(Source,Mask,Results[0]);', 'MUL(Source,Mask,Results[1]);', 'DIV(Source,OtherInputs[0],Results[2]);'])
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('OtherInputs[0]', 2);e.step();self.assertEqual(e.memory.read('Results'), [10, 21, 3])

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root, ['ADD(Value,Index,Buffer[Index])ADD(Buffer[Index],Value,Stack[0])SUB(Stack[0],Value,Stack[1]);'])
        queues.logic(root, ['AFI()ADD(Value,Index,Buffer[Index])ADD(Value,Index,Stack[Index]);'], name='EnableInFalse')
        root.find('.//AddOnInstructionDefinition/LocalTags/LocalTag[@Name="Stack"]').set('DataType', 'LINT')
        root.find('.//AddOnInstructionDefinition/Parameters/Parameter[@Name="Buffer"]').set('DataType', 'LINT')
        for name in ('BufferA', 'BufferB'):
            tag = root.find(f'./Controller/Tags/Tag[@Name="{name}"]');tag.set('DataType', 'LINT')
            array = tag.find('Data/Array');array.set('DataType', 'LINT')
            for item in list(array):
                if item.get('Index') in ('[1]', '[2]'):array.remove(item)
        for name in ('DriverA', 'DriverB'):
            array = root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]');array.set('DataType', 'LINT')
            for item in list(array):
                if item.get('Index') in ('[0]', '[1]'):array.remove(item)

    def test_aoi_widened_locals_instance_independence_and_binding_rollback(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_logic);e.step()
        self.assertEqual(e.memory.read('DriverA.Stack')[:2], [23, 12]);self.assertEqual(e.memory.read('DriverB.Stack')[:2], [46, 24])
        self.assertEqual(e.memory.read('BufferA')[1:3], [12, None]);self.assertEqual(e.memory.read('BufferB')[1:3], [None, 24])
        # Resolve an invalid local destination only when its instance is enabled.
        def indexed(root):
            self.aoi_logic(root);queues.logic(root, ['ADD(Value,Index,Buffer[Index])ADD(Value,Index,Stack[Index]);'])
        e = f.checked(indexed);e.memory.write('EnabledB', False);e.memory.write('IndexB', 999);e.step()
        e.memory.write('EnabledB', True);e.memory.write('ValueA', 100);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('IndexB', 2);e.step();self.assertEqual(e.memory.read('DriverB.Stack[2]'), 24)
        self.assertEqual(e.memory.read('BufferA[1]'), 101);self.assertEqual(e.memory.read('DriverA.Stack[3]'), 777)

    def test_immediate_real_narrowing_permissions_and_controller_gates_remain(self):
        for text, options in [('ADD(Source,1,Results[0]);', {'source':'DINT'}),
                              ('ADD(Source,2147483648,Results[0]);', {}),
                              ('ADD(Source,-1,Results[0]);', {'source':'ULINT','dest':'ULINT'}),
                              ('ADD(Source,Mask,Results[0]);', {'source':'LINT','dest':'DINT'}),
                              ('ADD(Source,Mask,Results[0]);', {'source':'DINT','dest':'ULINT'}),
                              ('ADD(Source,Mask,Results[0]);', {'other':'REAL'}),
                              ('ADD(Inputs,Mask,Results[0]);', {}), ('ADD(Source,Mask,Results);', {}),
                              ('ADD(StartPB,Mask,Results[0]);', {})]:
            self.assertTrue(self.engine(['AFI()' + text], **options).blockers, (text, options))
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()ADD(Source,Mask,Results[0]);'], mutate=constant).blockers)
        for processor, revision in [('1756-L75', '35'), ('1756-L85E', '34')]:
            def old(root):root.find('Controller').set('ProcessorType', processor);root.find('Controller').set('MajorRev', revision)
            self.assertTrue(self.engine(mutate=old).blockers)
        def st(root):
            routine = root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type', 'ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0').text = 'Results[1]:=Source+Mask;'
        self.assertTrue(self.engine(mutate=st).blockers, 'This ladder increment does not enable mixed ST expressions')
        report = self.checked().report()['scalar_math']['widening_arithmetic']
        self.assertEqual(len(report['instructions']), 7);self.assertEqual(set(report['types']), set(DESTINATIONS));self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
