"""Floating thresholds select REAL without requiring an actual REAL source tag."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_mixed_real_comparisons as fixtures
import test_real_integer_literals as constants
from logixlab.model import INT_BITS, Project, literal
from logixlab.runtime import Engine


class RealComparisonLiteralTests(unittest.TestCase):
    setUp = fixtures.MixedRealComparisonTests.setUp
    engine = fixtures.MixedRealComparisonTests.engine
    checked = fixtures.MixedRealComparisonTests.checked
    snapshot = staticmethod(fixtures.MixedRealComparisonTests.snapshot)
    fault = fixtures.MixedRealComparisonTests.fault

    def test_six_relations_all_integer_tag_types_both_positions(self):
        for dtype,name,position,value in itertools.product(INT_BITS,constants.RELATIONS,range(2),range(3)):
            args='Source,1.0' if position==0 else '1.0,Source'
            e=self.checked([name+'('+args+')OTE(RunLatch);'],source=dtype,values=(value,1,1));before=e.memory.read('Source');e.step()
            self.assertIs(e.memory.read('RunLatch'),constants.ORDER[value if position==0 else 2-value][constants.RELATIONS.index(name)])
            self.assertEqual(e.memory.read('Source'),before)

    def test_constant_only_relations_decimal_and_radix_words(self):
        for name,token,position in itertools.product(constants.RELATIONS,('1','1L','1U','1UL','2#1L','8#1U','16#1UL'),range(2)):
            args=token+',1.0' if position==0 else '1.0,'+token
            e=self.checked([name+'('+args+')OTE(RunLatch);'],source='DINT');e.step()
            self.assertIs(e.memory.read('RunLatch'),constants.ORDER[1][constants.RELATIONS.index(name)])
        for call,expected in [('EQU(16#FFFFFFFF,-1.0)',True),('LES(16#FFFFFFFF,0.0)',True),
                ('EQU(16#FFFFFFFFL,4294967296.0)',True),('EQU(16#FFFFFFFFFFFFFFFFUL,18446744073709551616.0)',True),
                ('GRT(16#8000000000000000L,0.0)',False)]:
            e=self.checked([call+'OTE(RunLatch);'],source='DINT');e.step();self.assertIs(e.memory.read('RunLatch'),expected)

    def test_float_selector_works_in_all_three_limit_positions(self):
        for left,right,position in itertools.product(INT_BITS,INT_BITS,range(3)):
            args=['Source','Mask','Dest'];args[position]='1.0'
            types=['DINT','DINT','DINT'];types[(position+1)%3]=left;types[(position+2)%3]=right
            e=self.checked(['LIM('+','.join(args)+')OTE(RunLatch);'],source=types[0],other=types[1],high=types[2],values=(1,1,1));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_constant_limits_normal_reversed_and_collapsed_after_rounding(self):
        for call,expected in [('LIM(0L,0.5,1UL)',True),('LIM(1U,0.5,0L)',False),('LIM(1L,0.0,0UL)',True),
                ('LIM(16777217U,16777216.0,16777216UL)',True),('LIM(0.0,16#FFFFFFFF,1UL)',False)]:
            e=self.checked([call+'OTE(RunLatch);'],source='DINT');e.step();self.assertIs(e.memory.read('RunLatch'),expected)
        e=self.checked(['LIM(Source,0.0,Mask)OTE(RunLatch);'],source='LINT',other='ULINT',values=(-1,2**64-1,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_real_rounding_underflow_zero_and_lreal_priority_are_explicit(self):
        for call,expected in [('EQU(16777217U,16777216.0)',True),('GRT(16777217U,16777216.0)',False),
                ('EQU(16777217U,16777216.0L)',False),('GRT(16777217U,16777216.0L)',True),
                ('EQU(1e-50,0.0)',True),('EQU(-0.0,0.0)',True),('GRT(1e-40,0.0)',True)]:
            e=self.checked([call+'OTE(RunLatch);'],source='DINT',high='LREAL');e.step();self.assertIs(e.memory.read('RunLatch'),expected)
        e=self.checked(['EQU(Source,16777216.0)OTE(RunLatch);'],source='DINT',values=(16777217,0,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_integer_only_ranges_and_default_parsers_do_not_expand(self):
        e=self.checked(['GRT(Source,Mask)OTE(RunLatch);'],source='LINT',other='LINT',values=(9007199254740993,9007199254740992,0));e.step();self.assertTrue(e.memory.read('RunLatch'))
        for call in ('EQU(1L,1UL)','LIM(0L,1U,2UL)'):
            self.assertTrue(self.engine([call+'OTE(RunLatch);'],source='DINT').blockers,call)
        self.assertTrue(self.engine(['EQU(Source,Mask)OTE(RunLatch);'],source='LINT',other='ULINT',values=(1,1,0)).blockers)
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)

    def test_false_prescan_and_live_unknown_or_out_of_bounds_selection(self):
        e=self.checked(['XIC(StartPB)EQU(Values[Index],1.0)OTE(RunLatch);'],source='DINT')
        e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown')
        e.memory.write('Values[1]',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_every_required_limit_source_is_consumed_when_reached(self):
        for call in ('EQU(Values[0],1.0)','LIM(1L,Values[0],0.0)','LIM(Values[0],0.0,0UL)'):
            e=self.checked([call+'OTE(RunLatch);'],source='DINT');self.fault(e,'Unknown')

    def test_literal_ranges_types_shapes_profiles_and_permissions_are_structural(self):
        for token in ('TRUE','2147483648','1e39','1e999','4294967296U','16#100000000U','-16#1L','(1L)','1L+1L','Values'):
            self.assertTrue(self.engine([f'AFI()LIM(0.0,{token},1UL)OTE(RunLatch);'],source='DINT').blockers,token)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()EQU(1UL,1.0)OTE(RunLatch);'],source='DINT',mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        for call in ('MEQ(Source,1.0,Mask)','LIM(0.0,RunLatch,1UL)'):
            self.assertTrue(self.engine([call+'OTE(RunLatch);'],source='DINT').blockers)

    def test_alias_member_reads_and_late_fault_preserve_sources_and_coils(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(members,'Member',Name=name,DataType='LINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base',Constant='true'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Value',DataType='LINT',Value='9007199254740993');E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='LINT',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['EQU(AliasValue,9007199254740992.0)OTE(RunLatch);','DIV(1,Index,SpeedCommand);'],source='DINT',mutate=fields)
        before=e.memory.read('Packet1');e.memory.write('Index',0);self.fault(e,'zero');e.memory.write('Index',1);e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Packet1'),before)

    def test_warm_aoi_copied_integer_inout_and_local_readers_are_atomic(self):
        h=constants.RealIntegerLiteralTests();h.setUp();self.addCleanup(h.doCleanups);old=h.aoi();root=E.parse(old.project.path).getroot();definition=root.find('.//AddOnInstructionDefinition')
        definition.find('Parameters/Parameter[@Name="Buffer"]').set('DataType','DINT')
        for node in definition.find('LocalTags/LocalTag[@Name="Stack"]').iter():
            if node.get('DataType')=='REAL':node.set('DataType','DINT')
        for suffix in ('A','B'):
            tag=root.find(f'./Controller/Tags/Tag[@Name="Buffer{suffix}"]');tag.set('DataType','DINT');tag.find('Data/Array').set('DataType','DINT')
            array=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/ArrayMember[@Name="Stack"]');array.set('DataType','DINT');array.find('Element[@Index="[0]"]').set('Value','0')
        import test_aoi_queues as queues
        queues.logic(root,['GRT(Value,0.5)OTE(LiteralComparedInOut);','LIM(0.0,Buffer[Index],4096UL)EQU(Stack[0],0.0)OTE(LiteralComparedLocal);'])
        queues.logic(root,['AFI()EQU(Buffer[Index],0.0)OTE(LiteralComparedInOut);'],name='EnableInFalse')
        E.ElementTree(root).write(old.project.path,encoding='utf8',xml_declaration=True);e=Engine(Project(old.project.path));self.assertEqual(e.blockers,[])
        e.step();self.assertTrue(e.memory.read('DriverA.LiteralComparedInOut'));self.assertTrue(e.memory.read('DriverA.LiteralComparedLocal'))
        e.memory.write('BufferA[1]',5000);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertFalse(e.memory.read('DriverA.LiteralComparedLocal'))
        e.memory.write('EnabledA',False);e.memory.write('IndexA',99);e.step()

    def test_public_sample_reports_precision_unknowns_and_late_recovery(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step();e.memory.write('RealCmpEnabled',True);e.step()
        flags=('LiteralEqual','MixedTag','ConstantWide','SignedWord','UnsignedWord','Normal','Reversed','Collapsed','Underflow','Selected','Binary64Diff','Unsigned64')
        for name in flags:self.assertIs(e.memory.read('RealCmp'+name),name not in ('Reversed','Binary64Diff'),name)
        e.memory.write('RealCmpIndex',1);self.fault(e,'Unknown');e.memory.write('RealCmpInputs[1]',1);e.step();self.assertTrue(e.memory.read('RealCmpSelected'))
        e.memory.write('RealCmpValue',16777218);e.memory.write('RealCmpLateDivisor',0);self.fault(e,'zero');e.memory.write('RealCmpLateDivisor',1);e.step();self.assertFalse(e.memory.read('RealCmpMixedTag'))
        e.memory.write('RealCmpEnabled',False);e.memory.write('RealCmpIndex',99);e.step();self.assertTrue(all(not e.memory.read('RealCmp'+n) for n in flags))
        row=e.report()['numeric_comparisons']['real_ordering'];self.assertIn('unsuffixed floating',row['selection_by_literal']);self.assertFalse(row['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
