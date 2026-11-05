"""Exact v35 time/date storage, matching ladder operands and rollback."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab import time_values
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
import test_bit_transfer as fixtures


class TimeValueTests(unittest.TestCase):
    setUp = fixtures.BitTransferTests.setUp

    def engine(self, rungs, *, dtype='LTIME', values=('LT#1s_1ns', 0, 0), mutate=None):
        return fixtures.BitTransferTests.engine(self, rungs, types=(dtype,) * 3, values=values, mutate=mutate)

    def checked(self, rungs, **options):
        engine = self.engine(rungs, **options)
        self.assertEqual(engine.blockers, [])
        return engine

    def test_matching_moves_and_clear_on_all_five_declared_types(self):
        for dtype, raw, expected in (
            ('TIME32', 'T32#-1ms_2us', -1002),
            ('TIME', 'T#31d_12h_59m_59s_999ms_999us', 2725199999999),
            ('LTIME', 'LT#31d_12h_59m_59s_999ms_999us_999ns', 2725199999999999),
            ('DT', 'DT#2020-03-05-08:11:44.345_678(UTC+08:00)', 1583367104345678),
            ('LDT', 'LDT#2020-10-25-11:05:20.123_456_789', 1603623920123456789),
        ):
            with self.subTest(dtype=dtype):
                e = self.checked(['MOV(Source,Dest);', 'MOV('+raw+',Mask);',
                                  'EQU(Dest,Mask)OTE(RunLatch);', 'CLR(Mask);'],
                                 dtype=dtype, values=(raw, 0, 0))
                e.step()
                self.assertEqual(e.memory.read('Source', allow_time=True), expected)
                self.assertEqual(e.memory.read('Dest', allow_time=True), expected)
                self.assertTrue(e.memory.read('RunLatch'))
                self.assertEqual(e.memory.read('Mask', allow_time=True), 0)
                dest = next(row for row in e.memory.leaves() if row['name'] == 'Dest')
                self.assertEqual((dest['value'], dest['kind'], dest['type']),
                                 (str(expected), 'integer_text', dtype))

    def test_exact_timestamp_ordering_across_adjacent_nanoseconds(self):
        for op, expected in (('EQU', False), ('NEQ', True), ('LES', True), ('LEQ', True),
                             ('GRT', False), ('GEQ', False)):
            with self.subTest(op=op):
                e = self.checked([f'{op}(Source,LDT#2026-11-05-00:00:00.000_000_002)OTE(RunLatch);'],
                                 dtype='LDT', values=('LDT#2026-11-05-00:00:00.000_000_001', 0, 0))
                e.step()
                self.assertEqual(e.memory.read('RunLatch'), expected)

    def test_bounds_precision_calendar_and_literal_formats(self):
        for text, value in (
            ('T32#-35m_47s_483ms_647us', -2147483647),
            ('LT#-1d_1ns', -86400000000001),
            ('DT#1970-01-01-05:30:00(UTC+05:30)', 0),
            ('LDT#1969-12-31-19:00:00(UTC-05:00)', 0),
            ('LDT#2250-12-31-23:59:59.999_999_999', 8867491199999999999),
        ):
            self.assertEqual(time_values.literal(text)[1], value)
        for text in (
            'T32#-35m_47s_483ms_648us', 'T#32d', 'LT#32d',
            'T#1ns', 'LT#1s_1s', 'T#1us_1s', 'T#1.5s',
            'DT#1969-12-31-23:59:59.999999', 'LDT#2251-01-01-00:00:00',
            'DT#2026-02-29-00:00:00', 'DT#2026-11-05-00:00:00.0000001',
            'LDT#2026-11-05-00:00:00(UTC+24:00)',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                time_values.literal(text)
        for value in (True, 1.0, 2147483648, 'LT#1ns'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                time_values.coerce(value, 'TIME32')

    def test_scope_and_invalid_operands_are_structural_blockers_even_while_false(self):
        for text in ('MOV(T#1s,Dest);', 'MOV(1,Dest);', 'MOV(Source,SpeedCommand);',
                     'MOV(Source.0,Dest);', 'EQU(Source,T#1s)OTE(RunLatch);',
                     'LIM(Source,Source,Source)OTE(RunLatch);', 'ADD(Source,Source,Dest);',
                     'CPT(Dest,Source+Source);', 'EQU(Source,LT#32d)OTE(RunLatch);',
                     'COP(Source,Dest,1);', 'CPS(Source,Dest,1);'):
            with self.subTest(text=text):
                self.assertTrue(self.engine(['AFI()'+text]).blockers)
        def older(root):
            root.find('Controller').set('ProcessorType', '1756-L75')
        self.assertTrue(self.engine(['MOV(Source,Dest);'], mutate=older).blockers)
        def constant(root):
            root.find('.//Tag[@Name="Dest"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()CLR(Dest);'], mutate=constant).blockers)
        def structured(root):
            routine = root.find('.//Routine')
            routine.set('Type', 'ST')
            routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0').text = 'Dest := Source;'
        self.assertTrue(self.engine([], mutate=structured).blockers)

    @staticmethod
    def array_tags(root):
        tags = root.find('./Controller/Tags')
        dtype = E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='TimePacket', Family='NoFamily')
        members = E.SubElement(dtype, 'Members')
        E.SubElement(members, 'Member', Name='Ticks', DataType='LTIME', Dimension='3')
        tag = E.SubElement(tags, 'Tag', Name='Packet', DataType='TimePacket', TagType='Base')
        struct = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='TimePacket')
        arr = E.SubElement(struct, 'ArrayMember', Name='Ticks', DataType='LTIME', Dimensions='3')
        E.SubElement(arr, 'Element', Index='[2]', Value='LT#9ns')
        E.SubElement(tags, 'Tag', Name='FirstTick', DataType='LTIME', TagType='Alias', AliasFor='Packet.Ticks[0]')

    def test_lazy_alias_and_selected_unknown_writes_and_whole_scan_rollback(self):
        e = self.checked([
            'XIC(StartPB)MOV(Source,Packet.Ticks[SpeedSetpoint]);',
            'XIC(StartPB)CLR(Packet.Ticks[1]);',
            'XIC(StartPB)EQU(FirstTick,LT#1s_1ns)OTE(RunLatch);',
            'DIV(1,SpeedCommand,DisplayedPartCount);',
        ], mutate=self.array_tags)
        e.memory.write('SpeedSetpoint', 99)
        e.memory.write('SpeedCommand', 1)
        e.step()
        self.assertEqual(e.memory.read('Packet')['Ticks'], [None, None, 9])
        e.memory.write('StartPB', True)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):
            e.step()
        e.memory.write('SpeedSetpoint', 0)
        e.memory.write('SpeedCommand', 0)
        before = copy.deepcopy((e.memory.values, e.scan_count, e.time_ms, e.scheduler_description()))
        with self.assertRaisesRegex(ModelError, 'zero'):
            e.step()
        self.assertEqual((e.memory.values, e.scan_count, e.time_ms, e.scheduler_description()), before)
        e.memory.write('SpeedCommand', 1)
        e.step()
        self.assertEqual(e.memory.read('Packet')['Ticks'], [1000000001, 0, 9])
        self.assertTrue(e.memory.read('RunLatch'))

    def test_bundled_data_lab_moves_time_types_and_compares_nanoseconds(self):
        p = Path(__file__).resolve().parents[1] / 'samples/DataLab.L5X'
        e = Engine(Project(p))
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.read('LongStamp', allow_time=True), 0)
        e.memory.write('TimeDateDemo', True)
        e.step()
        self.assertEqual(e.memory.read('LongStamp', allow_time=True), 1767225600000000001)
        self.assertTrue(e.memory.read('EarlierNano'))
        self.assertEqual(e.memory.read('ShortDelay', allow_time=True), -1501)
        self.assertEqual(e.memory.read('TimeToClear', allow_time=True), 0)


if __name__ == '__main__':
    unittest.main()
