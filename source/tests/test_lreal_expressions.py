"""Scoped ladder binary64 calculations, comparisons, selection and recovery."""
import itertools
import math
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
import test_file_bcd as snapshots
from logixlab.conditions import Condition
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

TYPES = ('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL', 'LREAL')


class LrealExpressionTests(unittest.TestCase):
    setUp = fixtures.NumericStorageTests.setUp
    snapshot = staticmethod(snapshots.FileBcdTests.snapshot)
    fault = snapshots.FileBcdTests.fault

    def engine(self, rungs=None, *, source='LREAL', other='LREAL', value=3, rhs=2,
               dest='LREAL', mutate=None):
        def fields(root):
            tags = root.find('./Controller/Tags')
            for name, dtype, data in [('Other', other, rhs), ('Divisor', 'LREAL', 1), ('Flag', 'BOOL', 1)]:
                tag = E.SubElement(tags, 'Tag', Name=name, DataType=dtype, TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType=dtype, Value=str(data))
            if mutate:
                mutate(root)
        return fixtures.NumericStorageTests.engine(
            self, rungs or ['CPT(Results[1],Source+Other);', 'CMP(Results[1]>Source)OTE(RunLatch);'],
            source=source, dest=dest, value=value, mutate=fields)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs)
        self.assertEqual(e.blockers, [])
        return e

    def test_all_one_hundred_numeric_source_pairs_with_lreal_destination(self):
        for source, other in itertools.product(TYPES, repeat=2):
            with self.subTest(source=source, other=other):
                e = self.checked(source=source, other=other)
                e.step()
                self.assertEqual(e.memory.read('Results'), [None, 5.0, None])
                self.assertTrue(e.memory.read('RunLatch'))
                self.assertEqual((e.memory.read('Source'), e.memory.read('Other')), (3, 2))

    def test_destination_only_promotes_constant_subtrees_and_integer_sources(self):
        for expr, result in [('1/2', .5), ('(1/2)+(1/2)', 1.0), ('-2147483648/2', -1073741824.0),
                             ('Source/2', 1.5), ('2**3**2', 64.0), ('2**(-1)', .5)]:
            e = self.checked(['CPT(Results[1],' + expr + ');'], source='DINT', other='DINT')
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), result)

    def test_binary64_precision_and_source_real_rounding_are_preserved(self):
        for source, value, expr, result in [('LREAL', 1.0000000000000002, 'Source-1', 2**-52),
                                          ('LREAL', 16777217.0, 'Source+1', 16777218.0),
                                          ('REAL', 16777217.0, 'Source+1', 16777217.0),
                                          ('DINT', 16777217, 'Source+1', 16777218.0),
                                          ('LINT', 9007199254740993, 'Source', 9007199254740992.0),
                                          ('ULINT', 18446744073709551615, 'Source', float(1 << 64))]:
            e = self.checked(['CPT(Results[1],' + expr + ');'], source=source, value=value)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), result)

    def test_all_thirteen_functions_use_binary64_results(self):
        cases = [('ABS', -3, 3.0), ('SQR', -3, math.sqrt(3)), ('TRN', -3.75, -3.0),
                 ('LN', 1, 0.0), ('LOG', 100, 2.0), ('SIN', 1, math.sin(1)),
                 ('COS', 1, math.cos(1)), ('TAN', 1, math.tan(1)), ('ASN', 1, math.asin(1)),
                 ('ACS', 0, math.acos(0)), ('ATN', 1, math.atan(1)),
                 ('DEG', 1, math.degrees(1)), ('RAD', 90, math.radians(90))]
        for function, value, expected in cases:
            e = self.checked(['CPT(Results[1],' + function + '(Source));'], value=value)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected, function)

    def test_fractional_powers_remainders_and_checked_intermediates(self):
        for expr, value, expected in [('Source**Other', 9, 3.0), ('Source MOD 3', -7.5, -1.5),
                                     ('SQR(Source)+SQR(Source)', 3, 2*math.sqrt(3)),
                                     ('(Source+1)/2', 3, 2.0)]:
            e = self.checked(['CPT(Results[1],' + expr + ');'], value=value, rhs=.5)
            e.step()
            self.assertEqual(e.memory.read('Results[1]'), expected)
        e = self.checked(['CPT(Results[1],Source*Source/Source);'], value=1e308)
        self.fault(e, 'Nonfinite')

    def test_six_comparisons_both_orders_and_boolean_composition(self):
        for op, expected in [('=', False), ('<>', True), ('<', False), ('<=', False), ('>', True), ('>=', True)]:
            for reverse in (False, True):
                expr = ('Other' + op + 'Source') if reverse else ('Source' + op + 'Other')
                e = self.checked(['CMP(' + expr + ')OTE(RunLatch);'], value=3, rhs=2)
                e.step()
                self.assertEqual(e.memory.read('RunLatch'), ({'<': True, '<=': True, '>': False, '>=': False}.get(op, expected) if reverse else expected))
        e = self.checked(['CMP((Source>Other)&&(Flag OR (Source=Other)))OTE(RunLatch);'])
        e.step()
        self.assertTrue(e.memory.read('RunLatch'))

    def test_all_numeric_tag_types_promote_in_cmp_when_lreal_is_present(self):
        for dtype in TYPES:
            for first in (True, False):
                expr = 'Source>Other' if first else 'Other<Source'
                e = self.checked(['CMP(' + expr + ')OTE(RunLatch);'], source=dtype, other='LREAL')
                e.step()
                self.assertTrue(e.memory.read('RunLatch'))

    def test_eager_booleans_do_not_hide_zero_unknown_or_domain_failures(self):
        for expr, pattern in [('(1=1)||(Source/0>0)', 'zero'), ('(0=1)&&(LN(Source)>0)', 'domain')]:
            e = self.checked(['CMP(' + expr + ')OTE(RunLatch);'], value=-1)
            self.fault(e, pattern)
        e = self.checked(['CMP((1=1)||(Source>Other))OTE(RunLatch);'])
        e.memory.values['other'] = None
        self.fault(e, 'Unknown')

    def test_false_prescan_unknown_full_writes_and_bad_indices_are_lazy(self):
        e = self.checked(['XIC(StartPB)CPT(Results[Index],Inputs[Index]+1);',
                          'XIC(StartPB)CMP(Inputs[Index]>Other)OTE(RunLatch);'])
        e.memory.write('Index', 999)
        e.step()
        self.assertEqual(e.memory.read('Results'), [None]*3)
        e.memory.write('StartPB', True)
        self.fault(e, 'outside bounds')
        e.memory.write('Index', 1)
        self.fault(e, 'Unknown')
        e.memory.write('Inputs[1]', 3)
        e.step()
        self.assertEqual(e.memory.read('Results'), [None, 4.0, None])

    def test_domain_zero_exponent_nonfinite_and_late_faults_restore_advance(self):
        for expr, value, rhs, pattern in [('Source/Other', 1, 0, 'zero'), ('LN(Source)', -1, 1, 'domain'),
                                          ('ACS(Source)', 2, 1, 'domain'), ('Source**Other', -2, .5, 'Complex'),
                                          ('Source**Other', 1, 1025, 'exponent'), ('Source*Other', 1e308, 2, 'Nonfinite')]:
            e = self.checked(['MOV(99,SpeedCommand);', 'CPT(Results[1],' + expr + ');'], value=value, rhs=rhs)
            self.fault(e, pattern)
        e = self.checked(['CPT(Results[1],Source+Other);', 'DIV(1,0,SpeedCommand);'])
        self.fault(e, 'zero')

    @staticmethod
    def member(root):
        members = E.SubElement(E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='DoublePacket', Class='User'), 'Members')
        for name, dtype in [('Value', 'LREAL'), ('Guard', 'DINT')]:
            E.SubElement(members, 'Member', Name=name, DataType=dtype, Dimension='0')
        tags = root.find('./Controller/Tags')
        obj = E.SubElement(E.SubElement(E.SubElement(tags, 'Tag', Name='Packet', DataType='DoublePacket', TagType='Base'), 'Data', Format='Decorated'), 'Structure', DataType='DoublePacket')
        E.SubElement(obj, 'DataValueMember', Name='Value', DataType='LREAL', Value='1.0000000000000002')
        E.SubElement(obj, 'DataValueMember', Name='Guard', DataType='DINT', Value='777')
        E.SubElement(tags, 'Tag', Name='Selected', DataType='LREAL', TagType='Alias', AliasFor='Packet.Value')

    def test_alias_udt_and_existing_function_indices_select_exact_cells(self):
        e = self.checked(['CPT(Results[FRD(TOD(1))],Selected-1);',
                          'CMP(Selected>1)OTE(RunLatch);'], mutate=self.member)
        e.step()
        self.assertEqual(e.memory.read('Results'), [None, 2**-52, None])
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Packet.Guard'), 777)

    @staticmethod
    def aoi_fields(root):
        import test_aoi_queues as queues
        definition = root.find('.//AddOnInstructionDefinition')
        for name in ('Buffer', 'Value', 'Item'):
            definition.find('Parameters/Parameter[@Name="' + name + '"]').set('DataType', 'LREAL')
        definition.find('LocalTags/LocalTag[@Name="Stack"]').set('DataType', 'LREAL')
        for suffix in ('A', 'B'):
            for name in ('Buffer', 'Value', 'Item'):
                for node in root.find('./Controller/Tags/Tag[@Name="' + name + suffix + '"]').iter():
                    if node.get('DataType') == 'DINT':
                        node.set('DataType', 'LREAL')
            record = root.find('./Controller/Tags/Tag[@Name="Driver' + suffix + '"]/Data/Structure')
            record.find('DataValueMember[@Name="Value"]').set('DataType', 'LREAL')
            record.find('DataValueMember[@Name="Item"]').set('DataType', 'LREAL')
            array = record.find('ArrayMember[@Name="Stack"]')
            array.set('DataType', 'LREAL')
            array.find('Element[@Index="[0]"]').set('Value', '.125')
        queues.logic(root, ['CPT(Buffer[Index],Value+Stack[0]);', 'CPT(Stack[Index],LN(Value));', 'CPT(Item,Value/2);',
                            'CMP(Buffer[Index]>Value)OTE(EnableOut);'])
        queues.logic(root, ['AFI()CPT(Stack[Index],Value/0);'], name='EnableInFalse')

    def test_warm_aoi_copied_inputs_inout_locals_and_false_routine_rollback(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_fields)
        e.memory.write('ValueA', 1.0000000000000002)
        e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 1.1250000000000002)
        self.assertEqual(e.memory.read('ItemA'), .5000000000000001)
        self.assertEqual(e.memory.read('DriverA.Stack[1]'), math.log(1.0000000000000002))
        e.memory.write('ValueA', -1)
        self.fault(e, 'domain')
        e.memory.write('ValueA', 2)
        e.memory.write('FaultDivisor', 0)
        self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1)
        e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 2.125)
        e.memory.write('EnabledA', False)
        e.memory.write('IndexA', 999)
        e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 2.125)

    def test_scoped_cache_keeps_generic_and_file_conditions_separate(self):
        e = self.checked(['CMP(Source>Other)OTE(RunLatch);'])
        e.step()
        self.assertIn(('Source>Other', True, True, True, False), e.extensions.conditions)
        for condition in (Condition('Source>Other'), e.extensions.condition('Source>Other', allow_wide=True, bcd=True)):
            with self.assertRaises(ModelError):
                condition.validate(e.memory)
        import test_file_bcd as files
        f = files.FileBcdTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.assertTrue(f.engine(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>1);'], source_type='LREAL').blockers)

    def test_copied_lreal_parameters_keep_tag_precision_and_real_constant_rules(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        for kind, value, expected in [('LREAL', 1.0000000000000002, 1.0000000000000002),
                                      ('LREAL', 1e308, 1e308), ('REAL', 1.0000000000000002, 1.0),
                                      ('DINT', 16777217, 16777217.0), ('literal', 1.0000000000000002, 1.0)]:
            def change(root):
                self.aoi_fields(root)
                if kind == 'literal':
                    for text in root.findall('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text'):
                        text.text = text.text.replace(',ValueA,', ',' + str(value) + ',')
                else:
                    tag = root.find('./Controller/Tags/Tag[@Name="ValueA"]')
                    tag.set('DataType', kind)
                    data = tag.find('Data/DataValue')
                    data.set('DataType', kind)
                    data.set('Value', str(value))
            e = f.checked(change)
            e.step()
            self.assertEqual(e.memory.read('DriverA.Value'), expected)
            self.assertEqual(e.memory.read('ItemA'), expected/2)

    def test_copied_lreal_output_requires_exact_scalar_destination_type(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        def wrong(root):
            self.aoi_fields(root)
            tag = root.find('./Controller/Tags/Tag[@Name="ItemA"]')
            tag.set('DataType', 'DINT')
            tag.find('Data/DataValue').set('DataType', 'DINT')
        self.assertTrue(f.engine(wrong).blockers)

    def test_destination_shapes_aliases_bitwise_and_literals_remain_guarded(self):
        self.assertTrue(self.engine(['AFI()CPT(Results,Source);']).blockers)
        for expr in ('Source+1e999', 'Source+2147483648', 'Source+9223372036854775808L', 'Source AND 1', 'NOT Source',
                     'FRD(Source)', 'TOD(Source)', 'SQRT(Source)', 'TRUNC(Source)'):
            self.assertTrue(self.engine(['AFI()CPT(Results[1],' + expr + ');']).blockers, expr)

    def test_bool_string_arrays_constant_destinations_and_old_profiles_are_guarded(self):
        for expr in ('Source+Flag', 'Source=Flag', 'Flag>Flag'):
            self.assertTrue(self.engine(['AFI()CMP(' + expr + ')OTE(RunLatch);']).blockers)
        self.assertTrue(self.engine(['AFI()CPT(Results,Source);']).blockers)
        def constant(root):
            root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()CPT(Results[1],Source);'], mutate=constant).blockers)
        for processor, version in [('1756-L75', '35'), ('1756-L85E', '34')]:
            def old(root):
                root.find('Controller').set('ProcessorType', processor)
                root.find('Controller').set('MajorRev', version)
            self.assertTrue(self.engine(['AFI()CPT(Results[1],Source);'], mutate=old).blockers)

    def test_report_describes_lreal_selection_and_native_boundaries(self):
        report = self.checked().report()['lreal_expression_execution']
        self.assertEqual(report['consumers'], ['CPT', 'CMP', 'FAL'])
        self.assertEqual(set(report['types']), set(TYPES))
        self.assertFalse(report['native_runtime_parity'])

    def test_wide_expression_lab_binary64_results_and_recoverable_faults(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.read('F64Results'), [None, None, 901.0])
        e.memory.write('F64Enabled', True)
        e.step()
        expected = {'F64Precision': 2**-52, 'F64Sum': 1.0, 'F64Integral': 16777218.0,
                    'F64StoredReal': 16777217.0, 'F64SignedResult': float(1 << 53),
                    'F64UnsignedResult': float(1 << 64), 'F64Root': 2*math.sqrt(3),
                    'F64Power': math.sqrt(3), 'F64Remainder': 1.0, 'F64Matches': True}
        for name, value in expected.items():
            self.assertEqual(e.memory.read(name), value, name)
        for name, pattern in [('F64DomainFault', 'domain'), ('F64OverflowFault', 'Nonfinite')]:
            e.memory.write(name, True)
            self.fault(e, pattern)
            e.memory.write(name, False)
        e.memory.write('F64Index', 1)
        e.memory.write('F64LateDivisor', 0)
        self.fault(e, 'zero')
        self.assertIsNone(e.memory.read('F64Results')[1])
        e.memory.write('F64LateDivisor', 1)
        e.step()
        self.assertEqual(e.memory.read('F64Results'), [2**-52, 2.0, 901.0])


if __name__ == '__main__':
    unittest.main()
