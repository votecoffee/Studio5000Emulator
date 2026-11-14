"""Exact typed integer RLL arithmetic and comparisons with declared-range gates."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
import test_file_bcd as snapshots
from logixlab.model import ModelError, Project, literal
from logixlab.runtime import Engine

KINDS=(('LINT','L'),('UDINT','U'),('ULINT','UL'))
BINARY={'ADD':5,'SUB':1,'MUL':6,'DIV':1,'MOD':1}
RELATIONS=('EQU','NEQ','LES','LEQ','GRT','GEQ')
ORDER={0:(False,True,True,True,False,False),1:(True,False,False,True,False,True),2:(False,True,False,False,True,True)}
BAD=('9223372036854775808L','-9223372036854775809L','4294967296U','-1U','18446744073709551616UL','-1UL','1LU','1_000L','16#FFLU','1.0UL','1e3U','(1L)','1L+1L','TRUE')


class TypedIntegerOperandTests(unittest.TestCase):
    setUp=fixtures.NumericStorageTests.setUp
    checked=fixtures.NumericStorageTests.checked
    snapshot=staticmethod(snapshots.FileBcdTests.snapshot)
    fault=snapshots.FileBcdTests.fault

    def engine(self,rungs=None,**options):
        options.setdefault('source','LINT');options.setdefault('dest','LINT')
        return fixtures.NumericStorageTests.engine(self,rungs,**options)

    def test_all_seven_math_forms_and_three_declared_constant_types(self):
        for (dtype,suffix),name in itertools.product(KINDS,BINARY):
            e=self.checked([name+'(3'+suffix+',2'+suffix+',Results[1]);'],source=dtype,dest=dtype);e.step();self.assertEqual(e.memory.read('Results'),[None,BINARY[name],None])
        for dtype,suffix in KINDS:
            for call,want in [('ABS(1'+suffix+',Results[1]);',1),('NEG(0'+suffix+',Results[1]);',0)]:
                e=self.checked([call],source=dtype,dest=dtype);e.step();self.assertEqual(e.memory.read('Results[1]'),want)

    def test_literal_sources_match_tags_and_work_in_both_binary_positions(self):
        for (dtype,suffix),name,position in itertools.product(KINDS,BINARY,range(2)):
            args='Source,2'+suffix if position==0 else '3'+suffix+',Source'
            value=3 if position==0 else 2;e=self.checked([name+'('+args+',Results[1]);'],source=dtype,dest=dtype,value=value);e.step()
            self.assertEqual(e.memory.read('Results[1]'),BINARY[name]);self.assertEqual(e.memory.read('Source'),value)

    def test_full_ranges_and_division_remain_exact_beyond_binary64(self):
        cases=[('ADD(9007199254740993L,1L,Results[1]);','LINT',9007199254740994),
               ('DIV(18446744073709551615UL,3UL,Results[1]);','ULINT',6148914691236517205),
               ('MOD(18446744073709551615UL,3UL,Results[1]);','ULINT',0),
               ('ADD(4294967294U,1U,Results[1]);','UDINT',4294967295),
               ('ADD(-9223372036854775808L,0L,Results[1]);','LINT',-(1<<63)),
               ('SUB(0L,4294967295U,Results[1]);','LINT',-4294967295)]
        for call,dtype,want in cases:
            e=self.checked([call],source=dtype,dest=dtype);e.step();self.assertEqual(e.memory.read('Results[1]'),want);self.assertIs(type(e.memory.read('Results[1]')),int)

    def test_signed_quotients_and_remainders_truncate_toward_zero(self):
        for a,b,q,r in [(-7,3,-2,-1),(7,-3,-2,1),(-7,-3,2,-1)]:
            e=self.checked([f'DIV({a}L,{b}L,Results[0]);',f'MOD({a}L,{b}L,Results[1]);']);e.step();self.assertEqual(e.memory.read('Results'),[q,r,None])

    def test_range_preserving_mixed_sources_and_bounded_legacy_constants(self):
        for source,dest,token,want in [('DINT','LINT','2L',5),('UDINT','LINT','2L',5),('UINT','UDINT','2U',5),('USINT','ULINT','2UL',5)]:
            e=self.checked(['ADD(Source,'+token+',Results[1]);'],source=source,dest=dest);e.step();self.assertEqual(e.memory.read('Results[1]'),want)
        e=self.checked(['ADD(2L,-1,Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),1)

    def test_six_relations_all_kinds_both_orders_and_constant_only_calls(self):
        for (dtype,suffix),name,position,value in itertools.product(KINDS,RELATIONS,range(2),range(3)):
            args='Source,1'+suffix if position==0 else '1'+suffix+',Source'
            e=self.checked([name+'('+args+')OTE(RunLatch);'],source=dtype,dest=dtype,value=value);e.step()
            self.assertIs(e.memory.read('RunLatch'),ORDER[value if position==0 else 2-value][RELATIONS.index(name)])
        for call,want in [('GRT(9007199254740993L,9007199254740992L)',True),('EQU(18446744073709551615UL,18446744073709551614UL)',False),('EQU(4294967295U,4294967295L)',True)]:
            e=self.checked([call+'OTE(RunLatch);']);e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_all_lim_positions_and_exact_reversed_endpoints(self):
        for (dtype,suffix),position in itertools.product(KINDS,range(3)):
            args=['1'+suffix,'1'+suffix,'1'+suffix];args[position]='Source'
            e=self.checked(['LIM('+','.join(args)+')OTE(RunLatch);'],source=dtype,dest=dtype,value=1);e.step();self.assertTrue(e.memory.read('RunLatch'))
        for value,want in [(0,True),(1,True),(2,False),(3,True),(4,True)]:
            e=self.checked(['LIM(3UL,Source,1UL)OTE(RunLatch);'],source='ULINT',dest='ULINT',value=value);e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_metadata_never_uses_saved_positive_values_to_authorize_lossy_types(self):
        for source,dest,token,bad in [('LINT','ULINT','1UL',-1),('DINT','UDINT','1U',-1),('ULINT','LINT','1L',1<<63),('UDINT','DINT','1U',1<<31)]:
            dormant=self.checked(['AFI()ADD(Source,'+token+',Results[1]);'],source=source,dest=dest,value=bad);dormant.step()
            e=self.checked(['ADD(Source,'+token+',Results[1]);'],source=source,dest=dest,value=1);e.step();self.assertEqual(e.memory.read('Results[1]'),2)
            e.memory.write('Source',bad)
            with self.assertRaisesRegex(ModelError,'overflow|range'):e.step()
            self.assertEqual(e.memory.read('Results[1]'),2)
        for call in ('EQU(1L,1UL)','LIM(0L,1UL,2L)','EQU(-1L,1U)'):
            # LINT covers UDINT, so the final signed/unsigned relation is valid.
            e=self.engine(['AFI()'+call+'OTE(RunLatch);'])
            self.assertEqual(bool(e.blockers),call!='EQU(-1L,1U)')

    def test_result_overflows_zero_divisors_and_late_failures_are_atomic(self):
        for call,dtype,pattern in [('ADD(9223372036854775807L,1L,Results[1]);','LINT','overflow'),('ABS(-9223372036854775808L,Results[1]);','LINT','overflow'),('DIV(-9223372036854775808L,-1L,Results[1]);','LINT','overflow'),('SUB(0UL,1UL,Results[1]);','ULINT','overflow'),('MUL(18446744073709551615UL,2UL,Results[1]);','ULINT','overflow'),('DIV(1UL,0UL,Results[1]);','ULINT','zero')]:
            e=self.checked(['XIC(StartPB)'+call],source=dtype,dest=dtype);e.step();e.memory.write('StartPB',True);self.fault(e,pattern)
        e=self.checked(['ADD(1L,1L,Results[1]);','DIV(1,Index,SpeedCommand);']);self.fault(e,'zero')

    def test_false_paths_and_unknown_full_writes_keep_existing_contracts(self):
        e=self.checked(['XIC(StartPB)ADD(Inputs[Index],1L,Results[Index]);']);e.memory.write('Index',999);e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',9007199254740993);e.step();self.assertEqual(e.memory.read('Results'),[None,9007199254740994,None])
        e=self.checked(['XIC(StartPB)EQU(Inputs[1],1L)OTE(RunLatch);']);e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'));e.memory.write('StartPB',True);self.fault(e,'Unknown')

    def test_zero_products_and_zero_width_limits_consume_all_required_sources(self):
        for call in ('MUL(Inputs[1],0L,Results[1]);','LIM(1L,Inputs[1],1L)OTE(RunLatch);'):
            e=self.checked([call]);self.fault(e,'Unknown')

    def test_alias_udt_members_and_overlapping_writes_preserve_exact_values(self):
        def fields(root):
            c=root.find('Controller');m=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(m,'Member',Name=name,DataType='LINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='LINT',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['ADD(9007199254740993L,0L,AliasValue);','ADD(AliasValue,1L,AliasValue);','GRT(AliasValue,9007199254740993L)OTE(RunLatch);'],mutate=fields);e.step();self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(9007199254740994,777));self.assertTrue(e.memory.read('RunLatch'))

    def aoi(self):
        import test_aoi_queues as queues
        import test_lreal_results as results
        helper=queues.AOIQueueTests();helper.setUp();self.addCleanup(helper.doCleanups)
        def fields(root):
            results.LrealResultTests.aoi_fields(root,'LINT');d=root.find('.//AddOnInstructionDefinition')
            for node in d.find('LocalTags/LocalTag[@Name="Stack"]').iter():
                if node.get('DataType')=='LREAL':node.set('DataType','LINT')
            for suffix in ('A','B'):
                for node in root.find('./Controller/Tags/Tag[@Name="Driver'+suffix+'"]/Data/Structure/ArrayMember[@Name="Stack"]').iter():
                    if node.get('DataType')=='LREAL':node.set('DataType','LINT')
            E.SubElement(d.find('LocalTags'),'LocalTag',Name='ExactCompared',DataType='BOOL',Radix='Decimal',ExternalAccess='Read/Write')
            queues.logic(root,['ADD(9007199254740993L,1L,Buffer[Index]);','DIV(9007199254740993L,3L,Item);','ADD(Buffer[Index],1L,Stack[Index]);','GRT(Stack[Index],9007199254740994L)OTE(ExactCompared);'])
            queues.logic(root,['AFI()ADD(1L,1L,Buffer[Index]);'],name='EnableInFalse')
        return helper.checked(fields)

    def test_warm_aoi_integer_inout_output_local_and_binding_rollback(self):
        e=self.aoi();e.step();self.assertEqual(e.memory.read('BufferA[1]'),9007199254740994);self.assertEqual(e.memory.read('ItemA'),3002399751580331);self.assertEqual(e.memory.read('DriverA.Stack[1]'),9007199254740995);self.assertTrue(e.memory.read('DriverA.ExactCompared'))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),9007199254740994)
        e.memory.write('EnabledA',False);e.memory.write('IndexA',999);e.step()

    def test_literal_ranges_shapes_and_other_consumers_remain_structural(self):
        for token in BAD:
            self.assertTrue(self.engine(['AFI()ADD(Source,'+token+',Results[1]);']).blockers,token)
            self.assertTrue(self.engine(['AFI()EQU(Source,'+token+')OTE(RunLatch);']).blockers,token)
        bitwise = self.checked(['AND(Source,1.0L,Results[1]);'], value=7)
        bitwise.step()
        self.assertEqual(bitwise.memory.read('Results[1]'), 1)
        for call in ('MEQ(Source,1.0L,Source)OTE(RunLatch);','FLL(1L,Results[1],1);','ADD(Inputs,1L,Results[1]);'):
            self.assertTrue(self.engine(['AFI()'+call]).blockers,call)
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)

    def test_permissions_old_profiles_and_floating_priority_are_unchanged(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()ADD(1L,1L,Results[1]);'],mutate=constant).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()ADD(1L,1L,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        e=self.checked(['EQU(Source,9007199254740992.0L)OTE(RunLatch);'],value=9007199254740993);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['EQU(Source,16777217U)OTE(RunLatch);'],source='REAL',value=16777216);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_report_exposes_exact_integer_source_and_range_contracts(self):
        r=self.checked().report();self.assertIn('Exact integer',r['scalar_math']['typed_integer_arithmetic']['calculation']);self.assertIn('Highest-ranked',r['numeric_comparisons']['typed_integer_ordering']['selection']);self.assertFalse(r['numeric_comparisons']['typed_integer_ordering']['native_runtime_parity'])

    def test_sample_exact_results_guard_and_atomic_recovery(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('TypedIntSelected'),[None,None,903]);e.memory.write('TypedIntEnabled',True);e.step()
        for name,want in [('TypedIntSigned',9007199254740994),('TypedIntQuotient',6148914691236517205),('TypedIntRemainder',0),('TypedIntDword',4294967295),('TypedIntDifference',-4294967295)]:self.assertEqual(e.memory.read(name),want)
        self.assertTrue(e.memory.read('TypedIntExact'));self.assertTrue(e.memory.read('TypedIntLimit'));self.assertEqual(e.memory.read('TypedIntSelected'),[(1<<64)-1,None,903])
        e.memory.write('TypedIntOverflow',True);self.fault(e,'overflow');e.memory.write('TypedIntOverflow',False);e.step();e.memory.write('TypedIntIndex',1);e.memory.write('TypedIntLateDivisor',0);self.fault(e,'zero');e.memory.write('TypedIntLateDivisor',1);e.step();self.assertEqual(e.memory.read('TypedIntSelected'),[(1<<64)-1]*2+[903])
        e.memory.write('TypedIntEnabled',False);e.memory.write('TypedIntIndex',999);e.step()


if __name__=='__main__':unittest.main()
