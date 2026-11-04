"""Declared-width L/U/UL patterns in bitwise math and masked equality."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_scalar_bitwise as fixtures
import test_typed_integer_operands as integers
import test_file_bcd as snapshots
from logixlab.model import INT_BITS, Project, literal
from logixlab.runtime import Engine

KINDS=(('LINT','5L'),('UDINT','5U'),('ULINT','5uL'))
OPS=('AND','OR','XOR','NOT')


class TypedBitwiseOperandTests(unittest.TestCase):
    setUp=fixtures.ScalarBitwiseTests.setUp
    checked=fixtures.ScalarBitwiseTests.checked
    snapshot=staticmethod(snapshots.FileBcdTests.snapshot)
    fault=snapshots.FileBcdTests.fault

    def engine(self,rungs=None,**options):
        options.setdefault('source','DINT');options.setdefault('other','DINT');options.setdefault('dest','LINT');options.setdefault('value',3);options.setdefault('mask',5)
        return fixtures.ScalarBitwiseTests.engine(self,rungs,**options)

    def test_three_binary_forms_all_tag_result_types_and_literal_kinds(self):
        for source,dest,(_,token),name in itertools.product(INT_BITS,INT_BITS,KINDS,('AND','OR','XOR')):
            # Small independent results exercise every declared operand combination.
            expected={'AND':1,'OR':7,'XOR':6}[name]
            e=self.checked([name+'(Source,'+token+',Results[1]);'],source=source,dest=dest);e.step();self.assertEqual(e.memory.read('Results'),[None,expected,None])

    def test_typed_patterns_match_tags_of_the_same_declared_width(self):
        for (kind,token),name,dest in itertools.product(KINDS,('AND','OR','XOR'),INT_BITS):
            e=self.checked([name+'(Source,Mask,Results[0]);',name+'(Source,'+token+',Results[1]);'],source='UINT',other=kind,dest=dest);e.step();self.assertEqual(e.memory.read('Results[0]'),e.memory.read('Results[1]'))

    def test_literal_operands_work_in_both_binary_positions(self):
        for (_,token),name,position in itertools.product(KINDS,('AND','OR','XOR'),range(2)):
            args='Source,'+token if position==0 else token+',Source';e=self.checked([name+'('+args+',Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),{'AND':1,'OR':7,'XOR':6}[name])

    def test_not_uses_promoted_result_width_and_reinterprets_low_bits(self):
        for (kind,token),dest in itertools.product(KINDS,INT_BITS):
            e=self.checked(['NOT(Source,Results[0]);','NOT('+token+',Results[1]);'],source=kind,value=5,dest=dest);e.step();self.assertEqual(e.memory.read('Results[0]'),e.memory.read('Results[1]'))
            expected=-6 if not dest.startswith('U') else (1<<INT_BITS[dest])-6;self.assertEqual(e.memory.read('Results[1]'),expected)

    def test_full_pattern_ranges_zero_extension_and_destination_reinterpretation(self):
        cases=[('OR(-1L,0U,Results[1]);','LINT',-1),('OR(4294967295U,0L,Results[1]);','LINT',4294967295),
               ('NOT(4294967295U,Results[1]);','LINT',-4294967296),('NOT(-1L,Results[1]);','LINT',0),
               ('XOR(18446744073709551615UL,-1L,Results[1]);','ULINT',0),('AND(4294967295U,255UL,Results[1]);','SINT',-1),
               ('OR(16#FFFFFFFF,0L,Results[1]);','LINT',4294967295),('OR(-1,0L,Results[1]);','LINT',4294967295),
               ('OR(32768U,0L,Results[1]);','INT',-32768),('OR(32768U,0L,Results[1]);','UINT',32768),
               ('NOT(0UL,Results[1]);','USINT',255),('OR(-9223372036854775808L,0UL,Results[1]);','ULINT',1<<63)]
        for call,dest,want in cases:
            e=self.checked([call],dest=dest);e.step();self.assertEqual(e.memory.read('Results[1]'),want,call)
        e=self.checked(['OR(Source,0L,Results[1]);'],source='DINT',value=-1);e.step();self.assertEqual(e.memory.read('Results[1]'),4294967295)

    def test_meq_typed_patterns_work_in_all_three_positions(self):
        for kind,suffix in [('LINT','L'),('UDINT','U'),('ULINT','UL')]:
            for position in range(3):
                args=['Source','Mask','Dest'];args[position]=('3' if position!=1 else '5')+suffix
                e=self.checked(['MEQ('+','.join(args)+')OTE(RunLatch);'],source=kind,other=kind,dest=kind);e.memory.write('Dest',3);before=(e.memory.read('Source'),e.memory.read('Mask'),e.memory.read('Dest'));e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual((e.memory.read('Source'),e.memory.read('Mask'),e.memory.read('Dest')),before)

    def test_meq_uses_patterns_not_numeric_signed_comparisons(self):
        cases=[('MEQ(-1L,18446744073709551615UL,4294967295U)',False),('MEQ(-1L,4294967295U,4294967295U)',True),
               ('MEQ(Source,18446744073709551615UL,4294967295U)',True),('MEQ(Source,18446744073709551615UL,-1L)',False),
               ('MEQ(-9223372036854775808L,9223372036854775808UL,9223372036854775808UL)',True)]
        for call,want in cases:
            e=self.checked([call+'OTE(RunLatch);'],value=-1);e.step();self.assertIs(e.memory.read('RunLatch'),want,call)

    def test_legacy_radix_patterns_mix_without_widening_other_consumers(self):
        for token in ('16#ffff_ffff','8#37777777777','2#'+'1'*32):
            e=self.checked(['AND('+token+',18446744073709551615UL,Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),4294967295)
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)
        self.assertTrue(self.engine(['AND(4294967295,0L,Results[1]);']).blockers)
        self.assertTrue(self.engine(['AND(16#100000000,0L,Results[1]);']).blockers)

    def test_false_paths_skip_unknowns_and_bad_source_destination_indices(self):
        e=self.checked(['XIC(StartPB)OR(Inputs[Index],1UL,Results[Index]);']);e.memory.write('Index',999);e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',2);e.step();self.assertEqual(e.memory.read('Results'),[None,3,None])
        e=self.checked(['XIC(StartPB)MEQ(Inputs[1],0UL,0L)OTE(RunLatch);']);e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'));e.memory.write('StartPB',True);self.fault(e,'Unknown')

    def test_zero_masks_still_consume_unknown_required_operands(self):
        for call in ('AND(Inputs[1],0UL,Results[1]);','MEQ(Inputs[1],0UL,0L)OTE(RunLatch);','MEQ(0UL,0UL,Inputs[1])OTE(RunLatch);'):
            e=self.checked([call]);self.fault(e,'Unknown')

    def test_full_unknown_writes_overlap_and_late_faults_are_atomic(self):
        e=self.checked(['OR(18446744073709551615UL,0L,Results[1]);'],dest='ULINT');e.step();self.assertEqual(e.memory.read('Results'),[None,(1<<64)-1,None])
        e=self.checked(['OR(Source,1UL,Source);'],source='ULINT',value=1<<63);e.step();self.assertEqual(e.memory.read('Source'),(1<<63)+1)
        e=self.checked(['OR(-1L,0UL,Results[1]);','DIV(1,Index,SpeedCommand);']);self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results[1]'),-1)

    def test_alias_udt_members_preserve_unwritten_guards(self):
        def fields(root):
            c=root.find('Controller');m=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(m,'Member',Name=name,DataType='LINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='LINT',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['OR(4294967295U,0L,AliasValue);','MEQ(AliasValue,4294967295U,-1L)OTE(RunLatch);'],mutate=fields);e.step();self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(4294967295,777));self.assertTrue(e.memory.read('RunLatch'))

    def aoi(self):
        helper=integers.TypedIntegerOperandTests();helper.setUp();self.addCleanup(helper.doCleanups);old=helper.aoi();root=E.parse(old.project.path).getroot()
        import test_aoi_queues as queues
        queues.logic(root,['OR(-1L,0UL,Buffer[Index]);','NOT(4294967295U,Item);','XOR(4294967295U,0L,Stack[Index]);','MEQ(Stack[Index],4294967295U,18446744073709551615UL)OTE(ExactCompared);'])
        queues.logic(root,['AFI()AND(0UL,Buffer[Index],Buffer[Index]);'],name='EnableInFalse')
        E.ElementTree(root).write(old.project.path,encoding='utf8',xml_declaration=True);e=Engine(Project(old.project.path));self.assertEqual(e.blockers,[]);return e

    def test_warm_aoi_output_inout_local_and_masked_comparison_rollback(self):
        e=self.aoi();e.step();self.assertEqual(e.memory.read('BufferA[1]'),-1);self.assertEqual(e.memory.read('ItemA'),-4294967296);self.assertEqual(e.memory.read('DriverA.Stack[1]'),4294967295);self.assertTrue(e.memory.read('DriverA.ExactCompared'))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),-1)
        e.memory.write('EnabledA',False);e.memory.write('IndexA',999);e.step()

    def test_literal_ranges_types_shapes_permissions_and_profiles_stay_explicit(self):
        for token in (*integers.BAD,'1.0L','1.5','Inputs'):
            self.assertTrue(self.engine(['AFI()AND('+token+',0UL,Results[1]);']).blockers,token)
            self.assertTrue(self.engine(['AFI()MEQ('+token+',0UL,0L)OTE(RunLatch);']).blockers,token)
        for kind in ('REAL','LREAL','BOOL'):
            self.assertTrue(self.engine(['AFI()AND(Source,1UL,Results[1]);'],source=kind,value=1).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()OR(1L,0UL,Results[1]);'],mutate=constant).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()OR(1L,0UL,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        self.assertTrue(self.engine(['AFI()BTD(1L,0,Results[1],0,1);']).blockers)

    def test_reports_keep_pattern_and_arithmetic_rules_separate(self):
        r=self.checked().report();self.assertIn('declared',r['scalar_math']['typed_integer_bitwise']['conversion']);self.assertIn('Zero-extend',r['numeric_comparisons']['typed_integer_masked_equal']['calculation']);self.assertFalse(r['numeric_comparisons']['typed_integer_masked_equal']['native_runtime_parity'])

    def test_sample_widths_unknowns_guards_and_recovery(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('TypedBitsSelected'),[None,None,903]);e.memory.write('TypedBitsEnabled',True);e.step()
        for name,want in [('TypedBitsZeroExtended',4294967295),('TypedBitsFull',(1<<64)-1),('TypedBitsNot',-4294967296),('TypedBitsByte',-1)]:self.assertEqual(e.memory.read(name),want)
        self.assertTrue(e.memory.read('TypedBitsMatch'));e.memory.write('TypedBitsIndex',1);e.memory.write('TypedBitsLateDivisor',0);self.fault(e,'zero');e.memory.write('TypedBitsLateDivisor',1);e.step();self.assertEqual(e.memory.read('TypedBitsSelected'),[(1<<64)-1]*2+[903])
        e.memory.write('TypedBitsEnabled',False);e.memory.write('TypedBitsIndex',999);e.step();self.assertFalse(e.memory.read('TypedBitsMatch'))


if __name__=='__main__':unittest.main()
