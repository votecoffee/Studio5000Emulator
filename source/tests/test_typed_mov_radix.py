"""Typed radix MOV uses declared source patterns without widening other parsers."""
import copy
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
from logixlab.model import ModelError, Project, literal
from logixlab.numeric_storage import typed_literal
from logixlab.runtime import Engine

TYPES = ('SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT','REAL','LREAL')


class TypedMovRadixTests(unittest.TestCase):
    setUp = fixtures.NumericStorageTests.setUp
    engine = fixtures.NumericStorageTests.engine
    checked = fixtures.NumericStorageTests.checked

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.time_ms,
                              e.scan_count,e.trace,e.scheduler_description(),e.last_timer))

    def fault(self,e,pattern):
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_declared_sources_match_tag_conversion_across_bases_and_ten_destinations(self):
        for base,(dtype,suffix,bits,value),dest in itertools.product((2,8,16),
                [('LINT','L',64,-1),('UDINT','U',32,(1<<32)-1),('ULINT','UL',64,(1<<64)-1)],TYPES):
            digits = format((1<<bits)-1,{2:'b',8:'o',16:'x'}[base])
            text = f'{base}#{digits}{suffix}'
            with self.subTest(source=text,dest=dest):
                e = self.checked(['MOV(Source,Results[0]);',f'MOV({text},Results[1]);'],
                                 source=dtype,dest=dest,value=value)
                e.step();row = e.memory.read('Results')
                self.assertEqual(row[0],row[1]);self.assertIsNone(row[2])
                self.assertIs(type(row[1]),float if dest in ('REAL','LREAL') else int)

    def test_short_patterns_zero_fill_to_suffix_width_before_conversion(self):
        for source,expected in [('16#FFFFFFFF',-1),('16#FFFFFFFFL',4294967295),
                                ('16#FFFFFFFFU',4294967295),('16#FFFFFFFFUL',4294967295),
                                ('16#FFFFL',65535),('2#1L',1),('8#1234U',668)]:
            e = self.checked([f'MOV({source},Results[1]);'],dest='LINT')
            e.step();self.assertEqual(e.memory.read('Results[1]'),expected)

    def test_signed_bit63_boundaries_and_full_width_unsigned_stay_exact(self):
        for base,value in itertools.product((2,8,16),((1<<63)-1,1<<63,(1<<63)+1,(1<<64)-1)):
            digits = format(value,{2:'b',8:'o',16:'x'}[base])
            expected = value-(1<<64) if value >= 1<<63 else value
            self.assertEqual(typed_literal(f'{base}#{digits}L'),('LINT',expected))
            self.assertEqual(typed_literal(f'{base}#{digits}UL'),('ULINT',value))

    def test_suffix_case_grouping_and_leading_zeroes_keep_declared_types(self):
        for text,dtype,value in [('16#00ff ffL','LINT',65535),('16#0000_FFFFu','UDINT',65535),
                                (' 16#0000_ffffUl ','ULINT',65535),('2#1010_0101l','LINT',165),
                                ('8#000_1234uL','ULINT',668),('16#0000000000000000000000UL','ULINT',0)]:
            self.assertEqual(typed_literal(text),(dtype,value))
            e = self.checked([f'MOV({text},Results[1]);'],dest=dtype)
            e.step();self.assertEqual(e.memory.read('Results[1]'),value)

    def test_declared_width_overflow_is_a_blocker_even_on_false_rungs(self):
        for base,suffix in itertools.product((2,8,16),('L','U','UL')):
            bits = 32 if suffix == 'U' else 64
            text = f'{base}#{format(1<<bits,{2:"b",8:"o",16:"x"}[base])}{suffix}'
            e = self.engine([f'AFI()MOV({text},Results[1]);'])
            self.assertTrue(e.blockers);self.assertIn(f'{bits}-bit',str(e.blockers))

    def test_invalid_digits_signs_group_boundaries_and_other_spellings_stay_blocked(self):
        for text in ('2#2L','8#8UL','16#GUL','16#___L','16# FFU','16#FF U','16#FF_L',
                     '16#FFLU','16#FFULL','16#FFL2','+16#FFL','-16#FFL','16#FF.0L',
                     '10#42L','LINT#16#FF','(16#FFL)','16#FFL+1L'):
            self.assertTrue(self.engine([f'AFI()MOV({text},Results[1]);']).blockers,text)

    def test_false_prescan_and_unknown_selected_destinations_keep_existing_rules(self):
        e = self.checked(['XIC(StartPB)MOV(16#FFFF_FFFF_FFFF_FFFFUL,Results[Index]);'],dest='ULINT')
        e.memory.write('Index',999);e.memory.values['source'] = None;e.step()
        self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);e.step()
        self.assertEqual(e.memory.read('Results'),[None,(1<<64)-1,None])

    def test_later_fault_restores_exact_values_and_retry_preserves_guards(self):
        e = self.checked(['MOV(16#0020_0000_0000_0001L,Results[1]);','DIV(1,Index,Dest);'],dest='LINT')
        self.fault(e,'zero');e.memory.write('Index',1);e.step()
        self.assertEqual(e.memory.read('Results'),[None,9007199254740993,None])

    def test_alias_member_writes_use_source_width_and_preserve_neighbor(self):
        def fields(root):
            c = root.find('Controller')
            members = E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(members,'Member',Name=name,DataType='LINT',Dimension='0')
            obj = E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='LINT',TagType='Alias',AliasFor='Packet1.Value')
        e = self.checked(['MOV(16#FFFF_FFFFL,AliasValue);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(4294967295,777))

    @staticmethod
    def aoi_fields(root):
        import test_aoi_queues as queues
        import test_lreal_results as results
        results.LrealResultTests.aoi_fields(root,'LINT')
        queues.logic(root,['MOV(16#0020_0000_0000_0001L,Buffer[Index]);',
                           'MOV(16#FFFF_FFFF_FFFF_FFFFL,Item);','MOV(16#FFFF_FFFFu,Stack[Index]);'])
        queues.logic(root,['AFI()MOV(16#FFFF_FFFF_FFFF_FFFFUL,Stack[Index]);'],name='EnableInFalse')

    def test_warm_aoi_inputs_outputs_inout_locals_and_later_rollback(self):
        import test_aoi_queues as queues
        helper = queues.AOIQueueTests();helper.setUp();self.addCleanup(helper.doCleanups)
        e = helper.checked(self.aoi_fields);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('ItemA'),e.memory.read('DriverA.Stack[1]')),
                         (9007199254740993,-1,4294967295.0))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),9007199254740993)
        e.memory.write('EnabledA',False);e.memory.write('IndexA',999);e.step()

    def test_controller_permissions_and_other_literal_consumers_do_not_expand(self):
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()MOV(16#FFUL,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()MOV(16#FFUL,Results[1]);'],mutate=constant).blockers)
        for text in ('ADD(16#FFUL,1,Results[1]);','CPT(Results[1],16#FFUL);','FLL(16#FFUL,Results[1],1);',
                     'EQU(16#FFUL,Source)OTE(RunLatch);','MOV(1,Results[16#FFUL]);','CLR(16#FFUL);'):
            self.assertTrue(self.engine([text]).blockers,text)
        with self.assertRaises(ValueError):literal('16#FFUL')

    def test_public_sample_and_report_expose_the_typed_radix_contract(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('RadixLongShort'),0)
        e.memory.write('RadixEnabled',True);e.step()
        for name,value in [('RadixLongShort',4294967295),('RadixLongNegative',-1),('RadixDwordMax',4294967295),
                           ('RadixUlongMax',(1<<64)-1),('RadixBinaryMin',-(1<<63)),('RadixOctalMax',(1<<64)-1)]:
            self.assertEqual(e.memory.read(name),value)
        profile = e.report()['numeric_storage']['radix_mov_literals']
        self.assertEqual(profile['typed_suffixes']['L'],dict(source_type='LINT',bits=64,signed=True))
        self.assertEqual(profile['typed_suffixes']['U']['bits'],32)
        self.assertFalse(profile['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
