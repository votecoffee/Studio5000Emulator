"""Typed radix pattern consumers preserve widths, lazy data and parser isolation."""
import copy
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_typed_bitwise_operands as fixtures
from logixlab.integer_math import typed_integer
from logixlab.model import ModelError, Project, literal
from logixlab.runtime import Engine


class RadixBitwiseTests(unittest.TestCase):
    setUp = fixtures.TypedBitwiseOperandTests.setUp
    engine = fixtures.TypedBitwiseOperandTests.engine
    checked = fixtures.TypedBitwiseOperandTests.checked

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.time_ms,
                              e.scan_count,e.trace,e.scheduler_description(),e.last_timer))

    def fault(self,e,pattern):
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_binary_forms_all_bases_suffixes_positions_and_narrow_wide_results(self):
        for base,suffix,name,dest in itertools.product((2,8,16),('L','U','UL'),('AND','OR','XOR'),('SINT','ULINT')):
            token = f'{base}#{format(5,{2:"b",8:"o",16:"x"}[base])}{suffix}'
            expected = {'AND':1,'OR':7,'XOR':6}[name]
            e = self.checked([f'{name}(Source,{token},Results[0]);',f'{name}({token},Source,Results[1]);'],dest=dest)
            e.step();self.assertEqual(e.memory.read('Results'),[expected,expected,None])

    def test_not_and_signed_unsigned_source_widths_preserve_exact_patterns(self):
        for token,dest,expected in [('16#FFFFFFFFU','LINT',-4294967296),
                                    ('16#FFFFFFFFU','ULINT',18446744069414584320),
                                    ('16#FFFFFFFFFFFFFFFFL','LINT',0),
                                    ('8#1777777777777777777777UL','ULINT',0),
                                    ('2#0UL','SINT',-1),('2#0UL','ULINT',(1<<64)-1)]:
            e = self.checked([f'NOT({token},Results[1]);'],dest=dest);e.step()
            self.assertEqual(e.memory.read('Results'),[None,expected,None])
        e = self.checked(['OR(16#FFFFFFFFU,0L,Results[0]);','OR(16#FFFFFFFFFFFFFFFFL,0UL,Results[1]);'])
        e.step();self.assertEqual(e.memory.read('Results'),[4294967295,-1,None])

    def test_meq_typed_patterns_work_in_all_positions_and_bases(self):
        for base,suffix,position in itertools.product((2,8,16),('L','U','UL'),range(3)):
            args = ['Source','Mask','Dest'];value = 5 if position == 1 else 3
            args[position] = f'{base}#{format(value,{2:"b",8:"o",16:"x"}[base])}{suffix}'
            e = self.checked(['MEQ('+','.join(args)+')OTE(RunLatch);'])
            e.memory.write('Dest',3);before = (e.memory.read('Source'),e.memory.read('Mask'),e.memory.read('Dest'))
            e.step();self.assertTrue(e.memory.read('RunLatch'))
            self.assertEqual((e.memory.read('Source'),e.memory.read('Mask'),e.memory.read('Dest')),before)

    def test_meq_masks_distinguish_signed_64_and_unsigned_32_patterns(self):
        for call,want in [('MEQ(16#FFFFFFFFFFFFFFFFL,16#FFFFFFFFFFFFFFFFUL,16#FFFFFFFFU)',False),
                          ('MEQ(16#FFFFFFFFFFFFFFFFL,16#FFFFFFFFU,16#FFFFFFFFU)',True),
                          ('MEQ(16#8000000000000000L,2#1'+'0'*63+'UL,16#8000000000000000UL)',True)]:
            e = self.checked([call+'OTE(RunLatch);']);e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_false_paths_skip_indices_but_zero_masks_require_every_enabled_source(self):
        e = self.checked(['XIC(StartPB)AND(Inputs[Index],16#0UL,Results[Index]);'])
        e.memory.write('Index',999);e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);self.fault(e,'Unknown')
        e.memory.write('Inputs[1]',37);e.step();self.assertEqual(e.memory.read('Results'),[None,0,None])
        for args in ('Inputs[1],16#0UL,0L','0UL,16#0UL,Inputs[1]'):
            e = self.checked(['MEQ('+args+')OTE(RunLatch);']);self.fault(e,'Unknown')

    def test_malformed_and_overwide_patterns_are_blocked_even_on_false_rungs(self):
        for token in ('16#100000000U','16#10000000000000000L','2#2UL','8#8L','16#FF U','16#FF_L','16#FFLU','-16#FFL'):
            for call in (f'AND(Source,{token},Results[1]);',f'OR({token},Source,Results[1]);',
                         f'XOR(Source,{token},Results[1]);',f'NOT({token},Results[1]);',
                         f'MEQ(Source,{token},0L)OTE(RunLatch);'):
                self.assertTrue(self.engine(['AFI()'+call]).blockers,(token,call))

    def test_existing_floating_conversion_and_integer_meq_type_guards_remain(self):
        for dest in ('REAL','LREAL'):
            e = self.checked(['NOT(16#FFFFFFFFFFFFFFFFL,Results[1]);'],dest=dest)
            e.step();self.assertEqual(e.memory.read('Results[1]'),0.0)
            for token in ('16#1U','2#1UL'):
                self.assertTrue(self.engine([f'AFI()NOT({token},Results[1]);'],dest=dest).blockers)
        for source,value in [('REAL',1.0),('LREAL',1.0),('BOOL',True)]:
            self.assertTrue(self.engine(['AFI()MEQ(Source,16#1UL,1L)OTE(RunLatch);'],source=source,value=value).blockers)

    def test_later_fault_rolls_back_exact_wide_result_and_retry(self):
        e = self.checked(['OR(Source,16#FFFFFFFFU,Results[1]);','DIV(1,Index,SpeedCommand);'],
                         source='ULINT',dest='ULINT',value=1<<63)
        self.fault(e,'zero');e.memory.write('Index',1);e.step()
        self.assertEqual(e.memory.read('Results'),[None,(1<<63)+(1<<32)-1,None])

    def test_alias_member_results_keep_low_bits_and_preserve_neighbors(self):
        def fields(root):
            c = root.find('Controller');members = E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(members,'Member',Name=name,DataType='ULINT',Dimension='0')
            obj = E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='ULINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='ULINT',TagType='Alias',AliasFor='Packet1.Value')
        e = self.checked(['OR(16#FFFFFFFFFFFFFFFFL,0UL,AliasValue);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),((1<<64)-1,777))

    def test_warm_aoi_output_inout_local_and_masked_comparison_rollback(self):
        helper = fixtures.TypedBitwiseOperandTests();helper.setUp();self.addCleanup(helper.doCleanups)
        old = helper.aoi();root = E.parse(old.project.path).getroot()
        import test_aoi_queues as queues
        queues.logic(root,['OR(16#FFFFFFFFFFFFFFFFL,0UL,Buffer[Index]);','NOT(16#FFFFFFFFU,Item);',
                           'XOR(2#11111111111111111111111111111111U,0L,Stack[Index]);',
                           'MEQ(Stack[Index],16#FFFFFFFFU,8#1777777777777777777777UL)OTE(ExactCompared);'])
        E.ElementTree(root).write(old.project.path,encoding='utf8',xml_declaration=True)
        e = Engine(Project(old.project.path));self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('ItemA'),e.memory.read('DriverA.Stack[1]')),
                         (-1,-4294967296,4294967295));self.assertTrue(e.memory.read('DriverA.ExactCompared'))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),-1)

    def test_other_literal_consumers_and_controller_profiles_do_not_expand(self):
        self.assertIsNone(typed_integer('16#FFUL'));self.assertEqual(typed_integer('16#FFUL',radix=True),('ULINT',255))
        with self.assertRaises(ValueError):literal('16#FFUL')
        for call in ('XPY(Source,16#FFUL,Results[1]);','EQU(Source,16#FFUL)OTE(RunLatch);',
                     'FRD(16#FFUL,Results[1]);','TOD(16#FFUL,Results[1]);',
                     'CPT(Results[1],16#FFUL);','MOV(1,Results[16#FFUL]);'):
            self.assertTrue(self.engine([call]).blockers,call)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()AND(Source,16#FFUL,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)

    def test_public_sample_report_and_later_fault_cover_typed_masks(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/BitLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step();e.memory.write('WideMaskEnabled',True);e.step()
        value = (1<<63)+(1<<32)+1
        self.assertEqual(e.memory.read('WideMaskFull'),value);self.assertTrue(e.memory.read('WideMaskTopMatch'))
        self.assertEqual(e.memory.read('WideMaskAnd'),1);self.assertTrue(e.memory.read('WideMaskMatches'))
        e.memory.write('WideMaskInput',17);e.memory.write('WideMaskDivisor',0);self.fault(e,'zero')
        e.memory.write('WideMaskDivisor',1);e.step()
        self.assertEqual(e.memory.read('WideMaskFull'),17);self.assertFalse(e.memory.read('WideMaskTopMatch'))
        report = e.report()
        for profile in (report['scalar_math']['typed_integer_bitwise'],report['numeric_comparisons']['typed_integer_masked_equal']):
            self.assertEqual(profile['radix_bases'],[2,8,16]);self.assertFalse(profile['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
