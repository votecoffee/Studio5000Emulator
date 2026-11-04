"""Byte/word packed BCD, exact integer patterns and transactional selection."""
import unittest
from xml.etree import ElementTree as E

import test_wide_bcd as fixtures
import test_aoi_queues as queues
from logixlab.model import ModelError

TYPES=fixtures.TYPES
SMALL=('SINT','USINT','INT','UINT')


def pattern(value,dtype):
    size,signed=TYPES[dtype]
    return int.from_bytes(value.to_bytes(size,'big'),'big',signed=signed)


class SmallBCDTests(unittest.TestCase):
    setUp=fixtures.WideBCDTests.setUp
    engine=fixtures.WideBCDTests.engine
    checked=fixtures.WideBCDTests.checked
    snapshot=staticmethod(fixtures.WideBCDTests.snapshot)

    def test_all_64_tod_integer_pairs_preserve_decimal_capacity_and_signed_bits(self):
        for source in TYPES:
            for dest in TYPES:
                size,signed=TYPES[source];maximum=min((1<<(size*8-int(signed)))-1,10**(TYPES[dest][0]*2)-1)
                e=self.checked(['TOD(Source,Results[1]);'],source=source,dest=dest,value=0)
                for value in (0,9,maximum):
                    e.memory.write('Source',value);e.step()
                    self.assertEqual(e.memory.read('Results'),[None,fixtures.encoded(value,dest),None],(source,dest,value))
                    self.assertEqual(e.memory.read('Source'),value)

    def test_all_64_frd_pairs_capture_declared_pattern_and_check_destination_range(self):
        for source in TYPES:
            for dest in TYPES:
                value=pattern(0x99,source);e=self.checked(['FRD(Source,Results[1]);'],source=source,dest=dest,value=value)
                e.step();self.assertEqual(e.memory.read('Results'),[None,99,None]);self.assertEqual(e.memory.read('Source'),value)
                size,signed=TYPES[source];value=-1 if signed else (1<<(size*8))-1;e.memory.write('Source',value)
                limit=(1<<(TYPES[dest][0]*8-int(TYPES[dest][1])))-1;expected=fixtures.decoded(value,source)
                if expected>limit:
                    before=self.snapshot(e)
                    with self.assertRaisesRegex(ModelError,'overflow'):e.step()
                    self.assertEqual(self.snapshot(e),before)
                else:e.step();self.assertEqual(e.memory.read('Results[1]'),expected)

    def test_every_signed_and_unsigned_byte_pattern_weights_exactly_two_nibbles(self):
        for source in ('SINT','USINT'):
            e=self.checked(['FRD(Source,Results[1]);'],source=source,dest='DINT',value=0)
            for raw in range(256):
                e.memory.write('Source',pattern(raw,source));e.step()
                # Decimal place weights, independent of runtime conversion helper.
                self.assertEqual(e.memory.read('Results[1]'),(raw>>4)*10+(raw&15),(source,raw))

    def test_word_sign_patterns_zero_high_bits_and_nondecimal_nibbles(self):
        for source in ('INT','UINT'):
            e=self.checked(['FRD(Source,Results[1]);'],source=source,dest='DINT',value=0)
            for raw,expected in ((0x8000,8000),(0x9999,9999),(0xabcd,11233),(0xffff,16665)):
                e.memory.write('Source',pattern(raw,source));e.step();self.assertEqual(e.memory.read('Results[1]'),expected)
        for source,expected in (('SINT',165),('INT',16665),('DINT',166666665)):
            e=self.checked(['FRD(Source,Results[1]);'],source=source,dest='LINT',value=-1);e.step();self.assertEqual(e.memory.read('Results[1]'),expected)

    def test_signed_and_unsigned_small_roundtrips_use_full_packed_bit_pattern(self):
        for dest,decimal in (('SINT',99),('USINT',99),('INT',9999),('UINT',9999)):
            # Decoded must hold the decimal, independently of the packed type.
            def decoded_type(root):
                tag=root.find('./Controller/Tags/Tag[@Name="Decoded"]');tag.set('DataType','DINT');tag.find('Data/Array').set('DataType','DINT')
            e=self.checked(['TOD(Source,Results[1]);','FRD(Results[1],Decoded[1]);'],source='DINT',dest=dest,value=decimal,mutate=decoded_type)
            e.step();self.assertEqual(e.memory.read('Results[1]'),fixtures.encoded(decimal,dest));self.assertEqual(e.memory.read('Decoded'),[None,decimal,None])

    def test_small_tod_capacity_and_negative_sources_roll_back_then_recover(self):
        for dest in SMALL:
            cap=10**(TYPES[dest][0]*2)-1
            for value in (-1,cap+1):
                e=self.checked(['MOV(55,SpeedCommand);','TOD(Source,Results[1]);'],source='DINT',dest=dest,value=value);before=self.snapshot(e)
                with self.assertRaisesRegex(ModelError,'qualified'):e.step()
                self.assertEqual(self.snapshot(e),before);e.memory.write('Source',cap);e.step();self.assertEqual(e.memory.read('Results[1]'),fixtures.encoded(cap,dest))

    def test_false_prescan_and_skipped_indices_do_not_consume_unknown_inputs(self):
        for text,source,dest in [('TOD(Inputs[Index],Results[Index]);','DINT','SINT'),('FRD(Inputs[Index],Results[Index]);','SINT','DINT')]:
            e=self.checked(['XIC(StartPB)'+text],source=source,dest=dest,value=99);e.memory.write('Index',99);e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
            e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Index',1);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Inputs[1]',99 if source=='DINT' else -103);e.step();self.assertEqual(e.memory.read('Results'),[None,-103 if dest=='SINT' else 99,None])

    @staticmethod
    def members(root):
        types=root.find('./Controller/DataTypes');members=E.SubElement(E.SubElement(types,'DataType',Name='SmallPacket'),'Members')
        for name,kind in [('Packed','SINT'),('Decimal','DINT'),('Guard','DINT')]:E.SubElement(members,'Member',Name=name,DataType=kind,Dimension='0')
        tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Packet',DataType='SmallPacket',TagType='Base');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='SmallPacket');E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
        E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',DataType='SINT',TagType='Alias',AliasFor='Packet.Packed')
        root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')

    def test_member_aliases_constant_sources_and_surrounding_unknowns(self):
        e=self.checked(['TOD(Source,View);','FRD(View,Packet.Decimal);'],source='DINT',dest='SINT',value=99,mutate=self.members);e.step()
        self.assertEqual((e.memory.read('Packet.Packed'),e.memory.read('Packet.Decimal'),e.memory.read('Packet.Guard')),(-103,99,777));self.assertEqual(e.memory.read('Results'),[None]*3)

    def test_inplace_roundtrips_capture_small_signed_sources_before_write(self):
        for dtype,value in [('SINT',99),('USINT',99),('INT',9999),('UINT',9999)]:
            e=self.checked(['TOD(Source,Source);','FRD(Source,Source);'],source=dtype,dest='DINT',value=value);e.step();self.assertEqual(e.memory.read('Source'),value)

    @staticmethod
    def aoi(root):
        definition=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition');definition.find('./LocalTags/LocalTag[@Name="Stack"]').set('DataType','SINT')
        for array in root.findall('./Controller/Tags/Tag/Data/Structure/ArrayMember[@Name="Stack"]'):
            array.set('DataType','SINT')
            for element in array:element.set('Value','77' if element.get('Index')=='[3]' else '0')
        queues.logic(root,['TOD(Value,Stack[0])FRD(Stack[0],Buffer[Index]);'])
        queues.logic(root,['AFI()TOD(Value,Stack[0])FRD(Stack[0],Buffer[Index]);'],name='EnableInFalse')

    def test_aoi_small_packed_local_and_dint_inout_rollback_and_independence(self):
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(11,22))
        e.memory.write('ValueA',99);e.memory.write('ValueB',100);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'qualified'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('ValueB',88);e.step()
        self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('DriverB.Stack[0]'),e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'),e.memory.read('DriverA.Stack[3]')),(-103,-120,99,88,77))

    def test_later_fault_restores_successful_small_conversions_and_scheduling(self):
        e=self.checked(['TOD(Source,Results[1]);','DIV(1,Index,SpeedCommand);'],source='DINT',dest='SINT',value=99);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results'),[None,-103,None])

    def test_report_exposes_all_integer_pairs_and_keeps_native_flags_separate(self):
        e=self.checked(['TOD(Source,Results[1]);'],source='DINT',dest='SINT',value=99);report=e.report()['numeric_conversions']
        for op in ('TOD','FRD'):
            self.assertEqual(report['rll_operands'][op],dict(sources=list(TYPES),destinations=list(TYPES)))
        self.assertFalse(report['native_runtime_parity']);self.assertFalse(report['native_math_status'])
        self.assertIn('0..99 (8-bit)',report['tod_range']);self.assertIn('0..9999 (16-bit)',report['tod_range'])
