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
        for text in ('MOV(DT#1970-01-01-00:00:00,Dest);', 'MOV(1,Dest);', 'MOV(Source,SpeedCommand);',
                     'MOV(Source.0,Dest);', 'EQU(Source,DT#1970-01-01-00:00:00)OTE(RunLatch);',
                     'LIM(Source,Source,Source)OTE(RunLatch);', 'MUL(Source,Source,Dest);',
                     'CPT(Dest,Source*Source);', 'EQU(Source,LT#32d)OTE(RunLatch);',
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

    def test_lossless_moves_scale_each_family_and_bridge_raw_lint_ticks(self):
        for source, dest, literal, expected in (
            ('TIME32', 'TIME', 'T32#-1ms_2us', -1002),
            ('TIME', 'LTIME', 'T#-1ms_2us', -1002000),
            ('LTIME', 'TIME32', 'LT#-1ms_2us_0ns', -1002),
            ('DT', 'LDT', 'DT#2026-01-01-00:00:00.000_001', 1767225600000001000),
            ('LDT', 'DT', 'LDT#2026-01-01-00:00:00.000_001_000', 1767225600000001),
            ('LDT', 'LINT', 'LDT#2026-01-01-00:00:00.000_000_001', 1767225600000000001),
            ('LINT', 'LDT', '1767225600000000001', 1767225600000000001),
        ):
            with self.subTest(source=source, dest=dest):
                e = fixtures.BitTransferTests.engine(
                    self, ['MOV(Source,Dest);'], types=(source, 'DINT', dest), values=(literal, 0, 0))
                self.assertEqual(e.blockers, [])
                e.step()
                self.assertEqual(e.memory.read('Dest', allow_time=True), expected)
        e = self.checked(['MOV(T#1ms_2us,Dest);'])
        e.step()
        self.assertEqual(e.memory.read('Dest', allow_time=True), 1002000)

    def test_mixed_temporal_comparisons_preserve_submicrosecond_order(self):
        for dtype, raw, op, other in (
            ('LTIME', 'LT#-1us_1ns', 'LES', 'T#-1us'),
            ('TIME32', 'T32#1ms_2us', 'EQU', 'T#1ms_2us'),
            ('DT', 'DT#2026-01-01-00:00:00.000_001', 'GRT', 'LDT#2026-01-01-00:00:00.000_000_999'),
            ('LDT', 'LDT#1970-01-01-05:30:00(UTC+05:30)', 'EQU', 'DT#1970-01-01-00:00:00'),
        ):
            with self.subTest(dtype=dtype, op=op, other=other):
                e = self.checked([f'{op}(Source,{other})OTE(RunLatch);'], dtype=dtype, values=(raw, 0, 0))
                e.step()
                self.assertTrue(e.memory.read('RunLatch'))

    def test_lossy_moves_and_out_of_range_bridges_roll_back_only_when_reached(self):
        for source, dest, raw, reason in (
            ('LTIME', 'TIME', 'LT#-1ns', 'fractional ticks'),
            ('LDT', 'DT', 'LDT#1970-01-01-00:00:00.000_000_001', 'fractional ticks'),
            ('TIME', 'TIME32', 'T#1h', 'exact ticks in range'),
            ('LINT', 'LDT', '-1', 'exact ticks in range'),
        ):
            with self.subTest(source=source, dest=dest):
                e = fixtures.BitTransferTests.engine(
                    self, ['MOV(55,SpeedCommand);', 'XIC(StartPB)MOV(Source,Dest);'],
                    types=(source, 'DINT', dest), values=(raw, 0, 0))
                self.assertEqual(e.blockers, [])
                e.step()
                e.memory.write('StartPB', True)
                e.memory.write('SpeedCommand', 7)
                before = copy.deepcopy((e.memory.values, e.scan_count, e.time_ms, e.scheduler_description()))
                with self.assertRaisesRegex(ModelError, reason):
                    e.step()
                self.assertEqual((e.memory.values, e.scan_count, e.time_ms, e.scheduler_description()), before)
                e.memory.write('Source', 1000)
                e.step()
                self.assertEqual(e.memory.read('Dest', allow_time=True), 1 if source in ('LTIME', 'LDT') else 1000)

    def test_ladder_serialization_supplies_only_valid_exact_temporal_literals(self):
        from logixlab.model import parse_rung
        from logixlab.server import serialize_nodes

        timestamp = 'LDT#2026-01-01-00:00:00.000_000_001'
        rung = f'[MOV({timestamp},A),MOV(T#1ns,B),MOV(T#-1ms_1us,C),MOV(16#FF,D)];'
        branch = serialize_nodes(parse_rung(rung))[0]['branch']
        self.assertEqual(branch[0][0]['literal_values'],
                         {timestamp: {'type': 'LDT literal', 'value': '1767225600000000001'}})
        self.assertNotIn('literal_values', branch[1][0])
        self.assertEqual(branch[2][0]['literal_values'],
                         {'T#-1ms_1us': {'type': 'TIME literal', 'value': '-1001'}})
        self.assertNotIn('literal_values', branch[3][0])

    def test_add_sub_preserve_mixed_units_order_and_signed_elapsed_time(self):
        for op, left_type, left, right_type, right, dest, expected in (
            ('ADD', 'TIME32', -1501, 'TIME', 1250007, 'TIME', 1248506),
            ('SUB', 'TIME', 1250007, 'TIME32', 2000000, 'TIME', -749993),
            ('ADD', 'DT', 1767225600000001, 'LTIME', 1, 'LDT', 1767225600000001001),
            ('ADD', 'LTIME', 1, 'DT', 1767225600000001, 'LDT', 1767225600000001001),
            ('SUB', 'LDT', 1767225600000001001, 'LTIME', 2, 'LDT', 1767225600000000999),
            ('SUB', 'TIME', 2, 'LDT', 1, 'LDT', 1999),
            ('SUB', 'DT', 1767225600000001, 'LDT', 1767225600000001001, 'LTIME', -1),
        ):
            with self.subTest(op=op, left=left_type, right=right_type, dest=dest):
                e = fixtures.BitTransferTests.engine(
                    self, [f'{op}(Source,Mask,Dest);'],
                    types=(left_type, right_type, dest), values=(left, right, 0))
                self.assertEqual(e.blockers, [])
                e.step()
                self.assertEqual(e.memory.read('Dest', allow_time=True), expected)
        e = self.checked(['ADD(LT#1us_1ns,LT#-1ns,Source);', 'SUB(Source,LT#1us,Source);'])
        e.step()
        self.assertEqual(e.memory.read('Source', allow_time=True), 0)

    def test_time_arithmetic_blocks_bad_families_and_non_temporal_operands(self):
        for text, dest, diagnostic in (
            ('ADD(DT#1970-01-01-00:00:00,LDT#1970-01-01-00:00:00,Dest);', 'LTIME', 'two timestamps'),
            ('SUB(DT#1970-01-01-00:00:00,LDT#1970-01-01-00:00:00,Dest);', 'DT', 'duration destination'),
            ('ADD(T#1us,LT#2ns,Dest);', 'DT', 'duration destination'),
            ('ADD(LDT#1970-01-01-00:00:00,LT#2ns,Dest);', 'LTIME', 'timestamp destination'),
            ('ADD(Source,1L,Dest);', 'LTIME', 'time/date source operands'),
            ('SUB(LT#2ns,1,Dest);', 'LTIME', 'time/date source operands'),
        ):
            with self.subTest(text=text, dest=dest):
                e = fixtures.BitTransferTests.engine(
                    self, ['AFI()'+text], types=('LTIME', 'DINT', dest), values=(0, 0, 0))
                self.assertTrue(any(diagnostic in problem for problem in e.blockers), e.blockers)
        for text in ('ADD(LT#1ns,LT#2ns,SpeedCommand);',
                     'ADD(Source,LT#2ns,Packet.Ticks);', 'ADD(Packet.Ticks,LT#2ns,Dest);'):
            self.assertTrue(self.engine(['AFI()'+text], mutate=self.array_tags).blockers)
        def constant(root):
            root.find('.//Tag[@Name="Dest"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()ADD(Source,LT#2ns,Dest);'], mutate=constant).blockers)

    def test_temporal_precision_range_and_exact_cancellation(self):
        for op, source, raw, right, dest, reason in (
            ('ADD', 'LTIME', -1001, 'LT#0ns', 'TIME', 'fractional ticks'),
            ('ADD', 'TIME32', 2147483647, 'T32#1us', 'TIME32', 'exact ticks in range'),
            ('SUB', 'DT', 0, 'LT#1us', 'LDT', 'exact ticks in range'),
            ('ADD', 'LDT', time_values.BOUNDS['LDT'][1], 'LT#1ns', 'LDT', 'exact ticks in range'),
        ):
            with self.subTest(op=op, source=source, dest=dest, raw=raw):
                e = fixtures.BitTransferTests.engine(
                    self, ['MOV(33,SpeedCommand);', f'XIC(StartPB){op}(Source,{right},Dest);'],
                    types=(source, 'DINT', dest), values=(raw, 0, 0))
                self.assertEqual(e.blockers, [])
                e.step()
                e.memory.write('StartPB', True)
                e.memory.write('SpeedCommand', 7)
                before = copy.deepcopy((e.memory.values, e.scan_count, e.time_ms, e.scheduler_description()))
                with self.assertRaisesRegex(ModelError, reason):
                    e.step()
                self.assertEqual((e.memory.values, e.scan_count, e.time_ms, e.scheduler_description()), before)
        e = fixtures.BitTransferTests.engine(
            self, ['ADD(LT#1us_1ns,LT#-1ns,Dest);', 'SUB(LT#-1us_1ns,LT#-1ns,Source);'],
            types=('TIME', 'DINT', 'TIME'), values=(0, 0, 0))
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.read('Dest', allow_time=True), 1)
        self.assertEqual(e.memory.read('Source', allow_time=True), -1)

    def test_lazy_temporal_sources_and_unknown_destination_retry(self):
        e = self.checked([
            'XIC(StartPB)ADD(Packet.Ticks[SpeedSetpoint],LT#1ns,Packet.Ticks[1]);',
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
        with self.assertRaisesRegex(ModelError, 'Unknown'):
            e.step()
        e.memory.write('SpeedSetpoint', 2)
        e.memory.write('SpeedCommand', 0)
        before = copy.deepcopy((e.memory.values, e.scan_count, e.time_ms, e.scheduler_description()))
        with self.assertRaisesRegex(ModelError, 'zero'):
            e.step()
        self.assertEqual((e.memory.values, e.scan_count, e.time_ms, e.scheduler_description()), before)
        e.memory.write('SpeedCommand', 1)
        e.step()
        self.assertEqual(e.memory.read('Packet')['Ticks'], [None, 10, 9])

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
        self.assertEqual(e.memory.read('ConvertedDuration', allow_time=True), 1250007000)
        self.assertTrue(e.memory.read('DurationMatches'))
        self.assertEqual(e.memory.read('TimestampTicks'), 1767225600000000001)
        self.assertEqual(e.memory.read('BridgedStamp', allow_time=True), 1767225600000000001)
        self.assertEqual(e.memory.read('PromotedWallStamp', allow_time=True), 1767225600000001000)
        self.assertEqual(e.memory.read('DurationTotal', allow_time=True), 1248506)
        self.assertEqual(e.memory.read('DurationDelta', allow_time=True), -749993)
        self.assertEqual(e.memory.read('NextStamp', allow_time=True), 1767225600000001001)
        self.assertEqual(e.memory.read('NanoDelta', allow_time=True), 1)
        self.assertEqual(e.memory.read('EarlierStamp', allow_time=True), 1767225600000000999)


if __name__ == '__main__':
    unittest.main()
