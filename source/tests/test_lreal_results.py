"""Final numeric destination conversions for binary64 ladder CPT results."""
import itertools
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_lreal_expressions as fixtures
from logixlab.model import INT_BITS, ModelError, Project
from logixlab.runtime import Engine


class LrealResultTests(unittest.TestCase):
    setUp = fixtures.LrealExpressionTests.setUp
    engine = fixtures.LrealExpressionTests.engine
    checked = fixtures.LrealExpressionTests.checked
    snapshot = staticmethod(fixtures.LrealExpressionTests.snapshot)
    fault = fixtures.LrealExpressionTests.fault

    def test_all_one_hundred_other_source_and_destination_pairs(self):
        for other, dest in itertools.product(fixtures.TYPES, repeat=2):
            with self.subTest(other=other, dest=dest):
                e = self.checked(['CPT(Results[1],Source+Other);'], value=2.5, rhs=1, other=other, dest=dest)
                e.step()
                expected = 4 if dest in INT_BITS else 3.5
                self.assertEqual(e.memory.read('Results'), [None, expected, None])
                self.assertEqual((e.memory.read('Source'), e.memory.read('Other')), (2.5, 1))

    def test_all_integer_destinations_round_ties_to_even_after_calculation(self):
        for dest in INT_BITS:
            for value, expected in ((2.5, 2), (3.5, 4), (-.5, 0)):
                e = self.checked(['CPT(Results[1],Source);'], dest=dest, value=value)
                e.step()
                self.assertEqual(e.memory.read('Results[1]'), expected)
        for dest in ('SINT', 'INT', 'DINT', 'LINT'):
            for value, expected in ((-2.5, -2), (-3.5, -4)):
                e = self.checked(['CPT(Results[1],Source);'], dest=dest, value=value)
                e.step()
                self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_rounding_happens_only_after_binary64_subexpressions(self):
        for expr, value, expected in [('Source-1', 3.5, 2), ('Source', 16777217.0, 16777217),
                                      ('Source+1', 16777217.0, 16777218),
                                      ('(Source*0)+(1/2)+(1/2)', 3.5, 1),
                                      ('SQR(Source)+SQR(Source)', 3.0, 3)]:
            e = self.checked(['CPT(Results[1],' + expr + ');'], value=value, dest='DINT')
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_real_results_round_to_binary32_once_and_keep_signed_zero(self):
        for value, expected in [(1.0000000000000002, 1.0), (16777217.0, 16777216.0),
                                (1+2**-24, 1.0), (1+3*2**-24, 1+2**-22),
                                (1e-46, 0.0), (-1e-46, -0.0), (-0.0, -0.0),
                                (3.4028234663852886e38, 3.4028234663852886e38)]:
            e = self.checked(['CPT(Results[1],Source);'], value=value, dest='REAL')
            e.step()
            self.assertEqual(struct.pack('<f', e.memory.read('Results[1]')), struct.pack('<f', expected))

    def test_integer_result_boundaries_fit_and_overflow_without_low_bit_wrapping(self):
        limits = [('SINT', 127, 128), ('USINT', 255, 256), ('INT', 32767, 32768),
                  ('UINT', 65535, 65536), ('DINT', 2147483647, 2147483648),
                  ('UDINT', 4294967295, 4294967296), ('LINT', (1 << 63)-1024, 1 << 63),
                  ('ULINT', (1 << 64)-2048, 1 << 64)]
        for dest, valid, invalid in limits:
            e = self.checked(['CPT(Results[1],Source);'], value=float(valid), dest=dest)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), valid)
            e.memory.write('Source', float(invalid))
            self.fault(e, 'overflow')
        for dest in ('USINT', 'UINT', 'UDINT', 'ULINT'):
            e = self.checked(['CPT(Results[1],Source);'], value=-.5000000000000001, dest=dest)
            self.fault(e, 'overflow')

    def test_real_result_range_failures_and_integer_rounding_overflow_are_atomic(self):
        for dest, value, match in [('REAL', 1e308, 'float|Nonfinite|overflow'),
                                    ('SINT', 127.5, 'overflow'), ('DINT', 2147483647.5, 'overflow')]:
            e = self.checked(['MOV(99,SpeedCommand);', 'CPT(Results[1],Source);'], value=value, dest=dest)
            self.fault(e, match)

    def test_nonfinite_intermediate_faults_before_a_later_reduction(self):
        e = self.checked(['CPT(Results[1],Source*Source/Source/Source);'], value=1e308, dest='DINT')
        self.fault(e, 'Nonfinite')

    def test_domains_zero_complex_powers_and_late_faults_restore_integer_outputs(self):
        for expr, value, rhs, match in [('Source/Other', 1, 0, 'zero'), ('LN(Source)', -1, 1, 'domain'),
                                       ('Source**Other', -2, .5, 'Complex'), ('Source**Other', 1, 1025, 'exponent')]:
            e = self.checked(['CPT(Results[1],' + expr + ');'], value=value, rhs=rhs, dest='DINT')
            self.fault(e, match)
        e = self.checked(['CPT(Results[1],Source);', 'DIV(1,0,SpeedCommand);'], value=3.5, dest='DINT')
        self.fault(e, 'zero')

    def test_unknown_destinations_and_dormant_bad_indices_remain_lazy(self):
        for dest in ('DINT', 'REAL', 'LINT', 'ULINT'):
            e = self.checked(['XIC(StartPB)CPT(Results[Index],Inputs[Index]);'], dest=dest)
            e.memory.write('Index', 999)
            e.step()
            self.assertEqual(e.memory.read('Results'), [None]*3)
            e.memory.write('StartPB', True)
            self.fault(e, 'outside bounds')
            e.memory.write('Index', 1)
            self.fault(e, 'Unknown')
            e.memory.write('Inputs[1]', 3.5)
            e.step()
            self.assertEqual(e.memory.read('Results'), [None, 3.5 if dest == 'REAL' else 4, None])

    @staticmethod
    def member(root):
        members = E.SubElement(E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='ResultPacket', Class='User'), 'Members')
        for name, dtype in [('Source', 'LREAL'), ('Result', 'DINT'), ('Guard', 'DINT')]:
            E.SubElement(members, 'Member', Name=name, DataType=dtype, Dimension='0')
        tags = root.find('./Controller/Tags')
        record = E.SubElement(E.SubElement(E.SubElement(tags, 'Tag', Name='Packet', DataType='ResultPacket', TagType='Base'), 'Data', Format='Decorated'), 'Structure', DataType='ResultPacket')
        E.SubElement(record, 'DataValueMember', Name='Source', DataType='LREAL', Value='3.5')
        E.SubElement(record, 'DataValueMember', Name='Guard', DataType='DINT', Value='777')
        E.SubElement(tags, 'Tag', Name='ResultAlias', DataType='DINT', TagType='Alias', AliasFor='Packet.Result')

    def test_alias_member_and_function_indices_keep_unwritten_storage(self):
        e = self.checked(['CPT(ResultAlias,Packet.Source);', 'CPT(Results[FRD(TOD(1))],Packet.Source);'],
                         mutate=self.member, dest='DINT')
        e.step()
        self.assertEqual(e.memory.read('Packet.Result'), 4)
        self.assertEqual(e.memory.read('Packet.Guard'), 777)
        self.assertEqual(e.memory.read('Results'), [None, 4, None])

    @staticmethod
    def aoi_fields(root, dest='DINT'):
        import test_aoi_queues as queues
        fixtures.LrealExpressionTests.aoi_fields(root)
        definition = root.find('.//AddOnInstructionDefinition')
        for name in ('Buffer', 'Item'):
            definition.find('Parameters/Parameter[@Name="' + name + '"]').set('DataType', dest)
        for suffix in ('A', 'B'):
            for name in ('Buffer', 'Item'):
                for node in root.find('./Controller/Tags/Tag[@Name="' + name + suffix + '"]').iter():
                    if node.get('DataType') == 'LREAL':
                        node.set('DataType', dest)
            for element in root.findall('./Controller/Tags/Tag[@Name="Buffer' + suffix + '"]/Data/Array/Element'):
                if int(element.get('Value', '0')) > 127:
                    element.set('Value', '77')
            record = root.find('./Controller/Tags/Tag[@Name="Driver' + suffix + '"]/Data/Structure')
            record.find('DataValueMember[@Name="Item"]').set('DataType', dest)
        queues.logic(root, ['CPT(Stack[Index],Value+Stack[0]);', 'CPT(Buffer[Index],Value/2);',
                            'CPT(Item,SQR(Value)+SQR(Value));', 'CMP(Buffer[Index]<=Value)OTE(EnableOut);'])

    def test_all_ten_aoi_result_types_use_exact_parameters_and_local_binary64(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        for dest in fixtures.TYPES:
            e = f.checked(lambda root: self.aoi_fields(root, dest))
            e.memory.write('ValueA', 7)
            e.step()
            self.assertEqual(e.memory.read('BufferA[1]'), 4 if dest in INT_BITS else 3.5)
            result = 2*(7**.5)
            if dest == 'REAL':
                result = struct.unpack('<f', struct.pack('<f', result))[0]
            self.assertEqual(e.memory.read('ItemA'), round(result) if dest in INT_BITS else result)
            self.assertEqual(e.memory.read('DriverA.Stack[1]'), 7.125)

    def test_warm_aoi_conversion_and_later_faults_restore_copies_bindings_and_locals(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_fields)
        e.memory.write('ValueA', 7)
        e.step()
        e.memory.write('ValueA', 1e308)
        self.fault(e, 'overflow')
        e.memory.write('ValueA', 8.5)
        e.memory.write('FaultDivisor', 0)
        self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1)
        e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 4)
        self.assertEqual(e.memory.read('ItemA'), 6)
        self.assertEqual(e.memory.read('DriverA.Stack[1]'), 8.625)
        e.memory.write('EnabledA', False)
        e.memory.write('IndexA', 999)
        e.step()
        self.assertEqual(e.memory.read('ItemA'), 6)

    def test_prescan_and_run_reentry_retain_calculated_results(self):
        e = self.checked(['CPT(Results[1],Source);'], dest='DINT', value=3.5)
        e.enter_run()
        self.assertEqual(e.memory.read('Results'), [None]*3)
        e.step()
        e.enter_run()
        self.assertEqual(e.memory.read('Results'), [None, 4, None])

    def test_without_lreal_the_existing_integer_and_real_profiles_are_unchanged(self):
        for source, dest, expected in [('DINT', 'DINT', 1), ('REAL', 'DINT', 2), ('DINT', 'REAL', 1.5)]:
            e = self.checked(['CPT(Results[1],Source/2);'], source=source, dest=dest, value=3)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected)
        self.assertTrue(self.engine(['CPT(Results[1],Source+1);'], source='LINT', dest='DINT').blockers)

    def test_result_report_and_excluded_consumers_remain_explicit(self):
        d = self.checked(dest='DINT').report()['lreal_expression_execution']
        self.assertEqual(set(d['destination_types']), set(fixtures.TYPES))
        self.assertIn('nearest-even', d['destination_conversion'])
        self.assertFalse(d['native_runtime_parity'])

    def test_wide_expression_lab_result_types_selection_and_atomic_recovery(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.read('R64Selected'), [None, None, 902])
        e.memory.write('R64Enabled', True)
        e.step()
        for dtype in fixtures.TYPES:
            self.assertEqual(e.memory.read('R64' + dtype), 4 if dtype in INT_BITS else 3.5)
        self.assertEqual(e.memory.read('R64Selected'), [None, 16777217, 902])
        self.assertTrue(e.memory.read('R64Converted'))
        for tag, pattern in [('R64IntegerFault', 'overflow'), ('R64RealFault', 'float|Nonfinite|overflow')]:
            e.memory.write(tag, True)
            self.fault(e, pattern)
            e.memory.write(tag, False)
        e.memory.write('R64Source', 7.5)
        e.memory.write('R64Index', 0)
        e.memory.write('R64LateDivisor', 0)
        self.fault(e, 'zero')
        self.assertEqual(e.memory.read('R64DINT'), 4)
        self.assertIsNone(e.memory.read('R64Selected')[0])
        e.memory.write('R64LateDivisor', 1)
        e.step()
        self.assertEqual(e.memory.read('R64DINT'), 8)
        self.assertEqual(e.memory.read('R64Selected'), [16777217, 16777217, 902])


if __name__ == '__main__':
    unittest.main()
