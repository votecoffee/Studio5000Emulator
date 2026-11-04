"""Typed scalar MOV/CLR, conversion bits, lazy values and rollback."""
import copy
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class NumericStorageTests(unittest.TestCase):
    setUp = fixtures.BitTransferTests.setUp
    checked = fixtures.BitTransferTests.checked

    def engine(self, rungs=None, *, source='DINT', dest='SINT', value=3, mutate=None):
        def fields(root):
            tags = root.find('./Controller/Tags')
            for name, kind in (('Inputs', source), ('Results', dest)):
                tag = E.SubElement(tags, 'Tag', Name=name, DataType=kind, Dimensions='3', TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=kind, Dimensions='3')
            tag = E.SubElement(tags, 'Tag', Name='Index', DataType='DINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='0')
            if mutate:mutate(root)
        return fixtures.BitTransferTests.engine(self, rungs or ['MOV(Source,Results[1]);'],
                                               types=(source, 'DINT', dest), values=(value, 1, 0), mutate=fields)

    @staticmethod
    def snapshot(e):
        bindings = (e.memory.frames, e.memory._resolved, e.addons.instances) if e.project.aois else None
        return copy.deepcopy((e.memory.values, bindings, e.time_ms, e.scan_count, e.trace, e.scheduler_description()))

    def test_all_eighty_one_numeric_source_destination_pairs(self):
        types = ('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL')
        for source in types:
            for dest in types:
                with self.subTest(source=source, dest=dest):
                    value = 3.5 if source == 'REAL' else 3
                    expected = 3.5 if source == dest == 'REAL' else 4 if source == 'REAL' else 3.0 if dest == 'REAL' else 3
                    e = self.checked(source=source, dest=dest, value=value);e.step()
                    self.assertEqual(e.memory.read('Results'), [None, expected, None]);self.assertEqual(e.memory.read('Source'), value)

    def test_integer_narrowing_signed_unsigned_and_widening_patterns(self):
        for source, dest, value, expected in (
                ('DINT', 'SINT', 0x12345678, 120), ('DINT', 'INT', 0x12345678, 22136),
                ('LINT', 'DINT', 0x12345678ffffffff, -1), ('ULINT', 'LINT', 18446744073709551615, -1),
                ('LINT', 'ULINT', -1, 18446744073709551615), ('DINT', 'UINT', -2, 65534),
                ('USINT', 'DINT', 255, 255), ('SINT', 'DINT', -1, -1), ('SINT', 'UDINT', -1, 4294967295),
                ('UDINT', 'DINT', 4294967295, -1), ('INT', 'USINT', -1, 255)):
            e = self.checked(source=source, dest=dest, value=value);e.step();self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_real_rounding_ties_precision_and_large_integer_to_real(self):
        for value, expected in ((2.5, 2), (3.5, 4), (-2.5, -2), (-3.5, -4)):
            e = self.checked(source='REAL', dest='INT', value=value);e.step();self.assertEqual(e.memory.read('Results[1]'), expected)
        e = self.checked(dest='REAL', value=16777217);e.step();self.assertEqual(e.memory.read('Results[1]'), 16777216.0)
        e = self.checked(source='ULINT', dest='REAL', value=18446744073709551615);e.step()
        self.assertEqual(e.memory.read('Results[1]'), 18446744073709551616.0)

    def test_real_range_errors_remain_excluded_and_roll_back(self):
        for dest, value in (('SINT', 127.5), ('USINT', 255.5), ('UDINT', -1.0), ('LINT', 2**63), ('ULINT', 2**64)):
            e = self.checked(['MOV(99,SpeedCommand);', 'MOV(Source,Results[1]);'], source='REAL', dest=dest, value=value)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'overflow'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Source', 2.5);e.step();self.assertEqual(e.memory.read('Results[1]'), 2)

    def test_integer_and_real_negative_to_unsigned_have_distinct_boundaries(self):
        e = self.checked(source='DINT', dest='USINT', value=-1);e.step();self.assertEqual(e.memory.read('Results[1]'), 255)
        e = self.checked(source='REAL', dest='USINT', value=-1.0)
        with self.assertRaisesRegex(ModelError, 'overflow'):e.step()

    def test_clr_all_nine_scalar_types_establishes_unknowns(self):
        for dtype in ('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL'):
            e = self.checked(['CLR(Results[1]);'], dest=dtype);e.step()
            value = e.memory.read('Results[1]');self.assertEqual(value, 0)
            self.assertEqual(type(value), float if dtype == 'REAL' else int)
            self.assertEqual(e.memory.read('Results')[::2], [None, None])

    def test_prescan_retains_unknown_storage(self):
        e = self.checked(['MOV(Source,Results[0]);', 'CLR(Results[1]);'])
        self.assertEqual(e.memory.read('Results'), [None] * 3);self.assertEqual(e.scan_count, 0)

    def test_false_mov_and_clr_skip_unknown_values_and_invalid_indices(self):
        e = self.checked(['XIC(StartPB)MOV(Inputs[Index],Results[Index]);', 'XIC(StartPB)CLR(Results[Index]);'])
        e.memory.write('Index', 999);reads = [];original = e.memory.read
        def read(ref, scope=''):
            if not e.memory.structural:reads.append(ref)
            return original(ref, scope)
        with patch.object(e.memory, 'read', side_effect=read):e.step()
        self.assertNotIn('Index', reads);self.assertEqual(e.memory.read('Results'), [None] * 3)
        e.memory.write('StartPB', True);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_unknown_reached_source_then_external_establishment_and_retry(self):
        e = self.checked(['XIC(StartPB)MOV(Inputs[0],Results[0]);']);e.step()
        e.memory.write('StartPB', True);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Inputs[0]', 4660);e.step();self.assertEqual(e.memory.read('Results[0]'), 52)

    def test_known_scalar_self_moves_and_index_destination_overlap(self):
        e = self.checked(['MOV(Source,Source);', 'MOV(Index,Results[Index]);']);e.step()
        self.assertEqual(e.memory.read('Source'), 3);self.assertEqual(e.memory.read('Results[0]'), 0)
        e = self.checked(['MOV(1,Index);', 'MOV(Source,Results[Index]);']);e.step()
        self.assertEqual(e.memory.read('Results'), [None, 3, None])

    def test_alias_udt_members_and_independent_guards(self):
        def aggregate(root):
            c = root.find('Controller');members = E.SubElement(E.SubElement(c.find('DataTypes'), 'DataType', Name='Packet', Family='NoFamily', Class='User'), 'Members')
            E.SubElement(members, 'Member', Name='Value', DataType='USINT', Dimension='0');E.SubElement(members, 'Member', Name='Guard', DataType='DINT', Dimension='0')
            obj = E.SubElement(E.SubElement(E.SubElement(c.find('Tags'), 'Tag', Name='Packet1', DataType='Packet', TagType='Base'), 'Data', Format='Decorated'), 'Structure', DataType='Packet')
            E.SubElement(obj, 'DataValueMember', Name='Guard', DataType='DINT', Value='777')
            E.SubElement(c.find('Tags'), 'Tag', Name='AliasValue', DataType='USINT', TagType='Alias', AliasFor='Packet1.Value')
        e = self.checked(['MOV(Source,AliasValue);'], value=-1, mutate=aggregate);e.step()
        self.assertEqual((e.memory.read('Packet1.Value'), e.memory.read('Packet1.Guard')), (255, 777))

    def test_immediate_limits_and_declared_source_dest_shapes_stay_explicit(self):
        for text in ('MOV(TRUE,Results[0]);', 'MOV(2147483648,Results[0]);', 'MOV(16#FFFFFFFF,Results[0]);',
                     'MOV(Source,Results);', 'MOV(Inputs,Results[0]);', 'MOV(Source,StartPB);', 'CLR(StartPB);', 'CLR(Source.0);'):
            self.assertTrue(self.engine([text]).blockers, text)
        for text in ('MOV(-2147483648,Results[0]);', 'MOV(2147483647,Results[0]);', 'MOV(3.5,Results[0]);'):
            e = self.checked([text]);e.step()

    def test_constants_remain_blocked_even_while_false(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant', 'true')
        for text in ('AFI()MOV(Source,Results[0]);', 'AFI()CLR(Results[0]);'):
            self.assertTrue(self.engine([text], mutate=constant).blockers)

    def test_late_fault_restores_new_values_source_guards_and_scheduler(self):
        e = self.checked(['MOV(Source,Results[0]);', 'CLR(Results[1]);', 'DIV(1,Mask,SpeedCommand);'], value=4660)
        e.memory.write('Mask', 0);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Mask', 1);e.step();self.assertEqual(e.memory.read('Results'), [52, 0, None])

    def test_old_controller_retains_legacy_range_guard_and_same_type_moves(self):
        def old(root):root.find('Controller').set('ProcessorType', '1756-L75')
        e = self.checked(['MOV(Source,Dest);'], value=3, mutate=old);e.step();self.assertEqual(e.memory.read('Dest'), 3)
        e = self.checked(['MOV(Source,Dest);'], value=128, mutate=old)
        with self.assertRaisesRegex(ModelError, 'overflow'):e.step()
        self.assertFalse(e.report()['numeric_storage']['available'])

    def test_aoi_typed_inout_and_local_storage_and_binding_rollback(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def logic(root):
            definition = root.find('.//AddOnInstructionDefinition')
            definition.find('Parameters/Parameter[@Name="Buffer"]').set('DataType', 'INT')
            definition.find('LocalTags/LocalTag[@Name="Stack"]').set('DataType', 'SINT')
            for name in ('BufferA', 'BufferB'):
                tag = root.find(f'./Controller/Tags/Tag[@Name="{name}"]');tag.set('DataType', 'INT');tag.find('Data/Array').set('DataType', 'INT')
            for name in ('DriverA', 'DriverB'):
                array = root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]');array.set('DataType', 'SINT')
                for child in array:child.set('Value', '77' if child.get('Value') == '777' else child.get('Value'))
            root.find('./Controller/Tags/Tag[@Name="ValueA"]/Data/DataValue').set('Value', '305419896')
            queues.logic(root, ['MOV(Value,Buffer[Index])MOV(Value,Stack[0])CLR(Stack[1]);'])
            queues.logic(root, ['AFI()MOV(Value,Buffer[Index])CLR(Stack[1]);'], name='EnableInFalse')
        e = f.checked(logic);e.step();self.assertEqual(e.memory.read('BufferA[1]'), 22136);self.assertEqual(e.memory.read('DriverA.Stack[0]'), 120)
        e.memory.write('IndexB', 999);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('IndexB', 2);e.step();self.assertEqual(e.memory.read('DriverA.Stack[3]'), 77)

    def test_explicit_aoi_prescan_can_establish_local_numeric_storage(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def prescan(root):
            definition = root.find('.//AddOnInstructionDefinition');definition.set('ExecutePrescan', 'true')
            content = E.SubElement(E.SubElement(definition.find('Routines'), 'Routine', Name='Prescan', Type='RLL'), 'RLLContent')
            E.SubElement(E.SubElement(content, 'Rung', Number='0', Type='N'), 'Text').text = 'MOV(42,Stack[0])CLR(Stack[1]);'
            for name in ('DriverA', 'DriverB'):
                array = root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]')
                array.remove(array[0]);array.remove(array[0])
        e = f.checked(prescan)
        self.assertEqual(e.memory.read('DriverA.Stack')[:2], [42, 0]);self.assertEqual(e.memory.read('DriverB.Stack')[:2], [42, 0])

    def test_report_separates_storage_conversion_from_arithmetic(self):
        e = self.checked();report = e.report()['numeric_storage']
        self.assertEqual(len(report['types']), 10);self.assertFalse(report['native_math_status']);self.assertFalse(report['native_runtime_parity'])
        self.assertIn('numeric_storage', e.report()['integer_execution']['storage_moves'])
