"""Exact 32/64-bit BCD patterns, decimal capacities and transactional bindings."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
from logixlab.model import ModelError

TYPES={'SINT':(1,True),'INT':(2,True),'DINT':(4,True),'LINT':(8,True),
       'USINT':(1,False),'UINT':(2,False),'UDINT':(4,False),'ULINT':(8,False)}
PACKED=('DINT','UDINT','LINT','ULINT')


def encoded(value,dtype):
    # Decimal text interpreted as hexadecimal is independent of the runtime's
    # repeated divide/modulo packing. Byte decoding supplies signed storage.
    size,signed=TYPES[dtype]
    return int.from_bytes(int(str(value),16).to_bytes(size,'big'),'big',signed=signed)


def decoded(value,dtype):
    size,signed=TYPES[dtype];result=0
    for digit in value.to_bytes(size,'big',signed=signed).hex():result=result*10+int(digit,16)
    return result


class WideBCDTests(unittest.TestCase):
    setUp=fixtures.NumericStorageTests.setUp
    checked=fixtures.NumericStorageTests.checked
    snapshot=staticmethod(fixtures.NumericStorageTests.snapshot)

    def engine(self,rungs=None,*,source='ULINT',dest='ULINT',value=9007199254740993,mutate=None):
        def fields(root):
            tags=root.find('./Controller/Tags')
            tag=E.SubElement(tags,'Tag',Name='Decoded',DataType=dest,Dimensions='3',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dest,Dimensions='3')
            if mutate:mutate(root)
        return fixtures.NumericStorageTests.engine(self,rungs or ['TOD(Source,Results[1]);','FRD(Results[1],Decoded[1]);'],source=source,dest=dest,value=value,mutate=fields)

    def test_all_32_tod_source_destination_pairs_with_three_values(self):
        for source in TYPES:
            for dest in PACKED:
                size,signed=TYPES[source];maximum=min((1<<(size*8-int(signed)))-1,10**(TYPES[dest][0]*2)-1)
                e=self.checked(['TOD(Source,Results[1]);'],source=source,dest=dest,value=0)
                for value in (0,9,maximum):
                    e.memory.write('Source',value);e.step()
                    self.assertEqual(e.memory.read('Results'),[None,encoded(value,dest),None],(source,dest,value))
                    self.assertEqual(e.memory.read('Source'),value)

    def test_all_32_frd_source_destination_pairs_and_range_boundaries(self):
        for source in PACKED:
            for dest in TYPES:
                e=self.checked(['FRD(Source,Results[1]);'],source=source,dest=dest,value=0x127)
                e.step();self.assertEqual(e.memory.read('Results'),[None,127,None])
                size,signed=TYPES[source];value=-1 if signed else (1<<(size*8))-1
                e.memory.write('Source',value);result=decoded(value,source)
                outsize,outsigned=TYPES[dest];maximum=(1<<(outsize*8-int(outsigned)))-1
                if result>maximum:
                    before=self.snapshot(e)
                    with self.assertRaisesRegex(ModelError,'overflow'):e.step()
                    self.assertEqual(self.snapshot(e),before)
                else:
                    e.step();self.assertEqual(e.memory.read('Results[1]'),result,(source,dest))

    def test_sixteen_digit_signed_unsigned_round_trips_and_decimal_text(self):
        for source in ('LINT','ULINT'):
            for dest in ('LINT','ULINT'):
                e=self.checked(source=source,dest=dest,value=0)
                for value in (8000000000000000,9007199254740992,9007199254740993,9999999999999999):
                    e.memory.write('Source',value);e.step()
                    self.assertEqual(e.memory.read('Results'),[None,encoded(value,dest),None])
                    self.assertEqual(e.memory.read('Decoded'),[None,value,None])
                    leaves={r['name']:r['value'] for r in e.memory.leaves()}
                    self.assertEqual(leaves['Decoded[1]'],str(value));self.assertEqual(leaves['Results[1]'],str(encoded(value,dest)))

    def test_weighted_nondecimal_64_bit_nibbles_and_32_bit_unsigned_patterns(self):
        for source,value in (('LINT',-1),('LINT',-9223372036854775808),('ULINT',18446744073709551615),
                             ('ULINT',0x123456789abcdeff),('UDINT',0xffffffff),('DINT',-1)):
            e=self.checked(['FRD(Source,Results[1]);'],source=source,value=value);e.step()
            self.assertEqual(e.memory.read('Results[1]'),decoded(value,source))

    def test_exact_values_do_not_take_the_real_conversion_path(self):
        e=self.checked()
        with patch('logixlab.scalar_math.real',side_effect=AssertionError('BCD used REAL')):e.step()
        self.assertEqual(e.memory.read('Decoded[1]'),9007199254740993)

    def test_false_prescan_unknown_indices_sources_and_full_results(self):
        e=self.checked(['XIC(StartPB)TOD(Inputs[Index],Results[Index]);','XIC(StartPB)FRD(Results[Index],Decoded[Index]);'])
        e.memory.write('Index',999);e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',9007199254740993);e.step()
        self.assertEqual(e.memory.read('Results'),[None,encoded(9007199254740993,'ULINT'),None])
        self.assertEqual(e.memory.read('Decoded'),[None,9007199254740993,None])

    def test_tod_capacity_negative_and_later_fault_roll_back_prior_writes(self):
        for dest,value in (('LINT',10000000000000000),('ULINT',10000000000000000),('UDINT',100000000),('DINT',100000000),('ULINT',-1)):
            e=self.checked(['MOV(99,SpeedCommand);','TOD(Source,Results[1]);'],source='LINT',dest=dest,value=value)
            before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'qualified'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Source',99);e.step();self.assertEqual(e.memory.read('Results[1]'),0x99)
        e=self.checked(['TOD(Source,Results[1]);','FRD(Results[1],Decoded[1]);','DIV(1,Index,SpeedCommand);'])
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Decoded[1]'),9007199254740993)

    def test_alias_udt_members_and_inplace_capture(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='BCDRecord',Family='NoFamily',Class='User'),'Members')
            for name,dtype in (('Packed','ULINT'),('Value','LINT'),('Guard','DINT')):E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0',Hidden='false')
            tag=E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='BCDRecord',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='BCDRecord')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
            E.SubElement(c.find('./Programs/Program/Tags'),'Tag',Name='PackedView',DataType='ULINT',TagType='Alias',AliasFor='Packet.Packed')
            root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
        e=self.checked(['TOD(Source,PackedView);','FRD(PackedView,Packet.Value);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet.Packed'),e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(encoded(9007199254740993,'ULINT'),9007199254740993,777))
        e=self.checked(['TOD(Source,Source);','FRD(Source,Source);']);e.step();self.assertEqual(e.memory.read('Source'),9007199254740993)

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        aoi=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')
        aoi.find('./LocalTags/LocalTag[@Name="Stack"]').set('DataType','ULINT')
        for array in root.findall('./Controller/Tags/Tag/Data/Structure/ArrayMember[@Name="Stack"]'):
            array.set('DataType','ULINT');array.remove(array.find('Element[@Index="[0]"]'))
        queues.logic(root,['TOD(Value,Stack[0])FRD(Stack[0],Buffer[Index]);'])
        queues.logic(root,['AFI()TOD(Value,Stack[0])FRD(Stack[0],Buffer[Index]);'],name='EnableInFalse')

    def test_aoi_wide_local_packed_values_and_dint_inout_binding_recovery(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic)
        e.step();self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('BufferA[1]')),(0x11,11))
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step()
        e.memory.write('EnabledB',True);e.memory.write('ValueA',1234);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('IndexB',2);e.step()
        self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('BufferA[1]'),e.memory.read('DriverA.Stack[3]')),(0x1234,1234,777))

    def test_retained_literal_noninteger_shape_permission_and_profile_guards(self):
        for text in ('TOD(2147483648,Results[1]);','FRD(16#100000000,Results[1]);','TOD(TRUE,Results[1]);','FRD(Inputs,Results[1]);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for dtype in ('REAL','BOOL'):
            self.assertTrue(self.engine(['TOD(Source,Results[1]);'],source=dtype,value=1).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        for key,value in (('ProcessorType','1756-L75'),('MajorRev','34')):
            self.assertTrue(self.engine(mutate=lambda root:root.find('Controller').set(key,value)).blockers)

    def test_dint_shared_helpers_keep_their_default_contract(self):
        from logixlab.numeric_conversions import from_bcd,to_bcd
        self.assertEqual(from_bcd(-1),166666665);self.assertEqual(to_bcd(99999999),-1717986919)
        with self.assertRaisesRegex(ModelError,'qualified'):to_bcd(100000000)
        e=self.checked();report=e.report()['numeric_conversions']
        self.assertEqual(report['rll_operands']['FRD']['sources'],list(TYPES));self.assertFalse(report['native_runtime_parity'])
