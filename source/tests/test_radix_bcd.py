"""Typed radix BCD sources retain declared patterns, capacities and transactions."""
import copy
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_wide_bcd as fixtures
from logixlab.model import ModelError,Project,literal
from logixlab.numeric_conversions import from_bcd,to_bcd
from logixlab.runtime import Engine


class RadixBCDTests(unittest.TestCase):
    setUp=fixtures.WideBCDTests.setUp
    engine=fixtures.WideBCDTests.engine
    checked=fixtures.WideBCDTests.checked

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.time_ms,
                              e.scan_count,e.trace,e.scheduler_description(),e.last_timer))

    def fault(self,e,pattern):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step()
        self.assertEqual(self.snapshot(e),before)

    @staticmethod
    def token(base,value,suffix):return f'{base}#{format(value,{2:"b",8:"o",16:"x"}[base])}{suffix}'

    def test_frd_three_bases_suffixes_and_all_eight_integer_destinations(self):
        for base,suffix,dest in itertools.product((2,8,16),('L','U','UL'),fixtures.TYPES):
            token=self.token(base,0x19,suffix)
            e=self.checked([f'FRD({token},Results[1]);'],dest=dest);e.step()
            self.assertEqual(e.memory.read('Results'),[None,19,None])

    def test_tod_three_bases_suffixes_and_byte_through_64_bit_destinations(self):
        for base,suffix,dest in itertools.product((2,8,16),('L','U','UL'),fixtures.TYPES):
            token=self.token(base,99,suffix)
            e=self.checked([f'TOD({token},Results[1]);'],dest=dest);e.step()
            self.assertEqual(e.memory.read('Results'),[None,fixtures.encoded(99,dest),None])

    def test_frd_uses_the_complete_declared_signed_or_unsigned_pattern(self):
        for base,suffix in itertools.product((2,8,16),('L','U','UL')):
            bits=32 if suffix=='U' else 64
            want=166666665 if bits==32 else 16666666666666665
            token=self.token(base,(1<<bits)-1,suffix)
            e=self.checked([f'FRD({token},Results[1]);']);e.step()
            self.assertEqual(e.memory.read('Results[1]'),want)
        for token,want in [('16#FFFFFFFFL',166666665),('16#1234567EL',12345684),('16#99u',99)]:
            e=self.checked([f'FRD({token},Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),want)

    def test_exact_16_digit_tod_round_trip_does_not_use_floating_math(self):
        for base,suffix,dest,value in itertools.product((2,8,16),('L','UL'),('LINT','ULINT'),(9007199254740993,9999999999999999)):
            token=self.token(base,value,suffix)
            e=self.checked([f'TOD({token},Results[1]);','FRD(Results[1],Decoded[1]);'],dest=dest)
            e.step();self.assertEqual(e.memory.read('Results[1]'),fixtures.encoded(value,dest))
            self.assertEqual(e.memory.read('Decoded[1]'),value)

    def test_negative_and_excessive_tod_values_and_frd_overflows_remain_transactional(self):
        for call,dest,pattern in [('TOD(16#FFFFFFFFFFFFFFFFL,Results[1]);','ULINT','qualified'),
                                  ('TOD(16#FFFFFFFFFFFFFFFFUL,Results[1]);','ULINT','qualified'),
                                  (f'TOD({self.token(16,10000000000000000,"UL")},Results[1]);','ULINT','qualified'),
                                  ('TOD(16#64U,Results[1]);','USINT','qualified'),
                                  ('FRD(16#128L,Results[1]);','SINT','overflow'),
                                  ('FRD(16#FFFFFFFFFFFFFFFFUL,Results[1]);','UDINT','overflow')]:
            e=self.checked(['MOV(77,SpeedCommand);',call],dest=dest);self.fault(e,pattern)

    def test_invalid_digits_widths_grouping_and_suffixes_block_false_calls(self):
        for token in ('16#100000000U','16#10000000000000000L','2#2UL','8#8L','16#FF U','16#FF_L','16#FFLU','-16#FFL'):
            for op in ('FRD','TOD'):
                self.assertTrue(self.engine([f'AFI(){op}({token},Results[1]);']).blockers,(op,token))

    def test_false_prescan_and_selected_full_writes_retain_unknown_neighbors(self):
        e=self.checked(['XIC(StartPB)FRD(16#99UL,Results[Index]);'])
        e.memory.write('Index',999);e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results'),[None,99,None])
        e=self.checked(['TOD(Inputs[1],Results[1]);']);self.fault(e,'Unknown')

    def test_late_fault_restores_exact_packed_values_and_retry(self):
        e=self.checked(['TOD(16#0020000000000001UL,Results[1]);','DIV(1,Index,SpeedCommand);'])
        self.fault(e,'zero');e.memory.write('Index',1);e.step()
        self.assertEqual(e.memory.read('Results'),[None,0x9007199254740993,None])

    def test_alias_members_and_inplace_decoding_capture_sources_before_writes(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Packed','Guard'):E.SubElement(members,'Member',Name=name,DataType='ULINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='ULINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='PackedView',DataType='ULINT',TagType='Alias',AliasFor='Packet1.Packed')
        e=self.checked(['TOD(16#0020000000000001UL,PackedView);','FRD(PackedView,Source);'],mutate=fields)
        e.step();self.assertEqual((e.memory.read('Packet1.Packed'),e.memory.read('Source'),e.memory.read('Packet1.Guard')),
                                  (0x9007199254740993,9007199254740993,777))
        e=self.checked(['FRD(16#9007199254740993UL,Source);','TOD(Source,Source);','FRD(Source,Source);'],source='LINT')
        e.step();self.assertEqual(e.memory.read('Source'),9007199254740993)

    def test_warm_aoi_local_patterns_inout_outputs_and_binding_rollback(self):
        import test_aoi_queues as queues
        helper=queues.AOIQueueTests();helper.setUp();self.addCleanup(helper.doCleanups)
        def fields(root):
            fixtures.WideBCDTests.aoi_logic(root)
            queues.logic(root,['TOD(16#4D2UL,Stack[0])FRD(Stack[0],Buffer[Index]);',
                               'FRD(8#37777777777U,Item);'])
        e=helper.checked(fields);e.step()
        self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('BufferA[1]'),e.memory.read('ItemA')),(0x1234,1234,166666665))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),1234)

    def test_scope_types_permissions_profiles_and_dint_helper_defaults_are_preserved(self):
        self.assertEqual(from_bcd(-1),166666665);self.assertEqual(to_bcd(99999999),-1717986919)
        with self.assertRaises(ValueError):literal('16#FFUL')
        for dest in ('REAL','LREAL','BOOL'):
            for op in ('FRD','TOD'):self.assertTrue(self.engine([f'AFI(){op}(16#99UL,Results[1]);'],dest=dest).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()FRD(16#99UL,Results[1]);'],mutate=constant).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()TOD(16#63UL,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        for call in ('SWPB(16#FFUL,REVERSE,Results[1]);','CPT(Results[1],FRD(16#FFUL));',
                     'MOV(1,Results[FRD(16#FFUL)]);','FLL(16#FFUL,Results[1],1);'):
            self.assertTrue(self.engine([call]).blockers,call)

    def test_public_sample_report_and_late_fault_recovery_cover_both_source_meanings(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/ConversionLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step();e.memory.write('ImmediateConversions',True);e.step()
        for name,value in [('ImmediateDecoded',9007199254740993),('ImmediateRadixDecoded',9007199254740993),
                           ('ImmediateWeighted',16666666666666665),('ImmediateWeightedDword',166666665),
                           ('ImmediateBytePacked',153),('ImmediateByteDecoded',99)]:self.assertEqual(e.memory.read(name),value)
        self.assertEqual(e.memory.read('ImmediatePacked'),[None,0x9007199254740993,903])
        e.memory.write('ImmediateIndex',0);e.memory.write('ImmediateLateDivisor',0);self.fault(e,'zero')
        e.memory.write('ImmediateLateDivisor',1);e.step();self.assertEqual(e.memory.read('ImmediatePacked')[0],0x9007199254740993)
        profile=e.report()['numeric_conversions']['typed_radix']
        self.assertEqual(profile['bases'],[2,8,16]);self.assertFalse(profile['native_runtime_parity'])


if __name__=='__main__':unittest.main()
