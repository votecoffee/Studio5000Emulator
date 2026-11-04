"""Finite float32 promotion for REAL-tag ladder relations and limits."""
import itertools
import unittest
from xml.etree import ElementTree as E

import test_numeric_comparisons as fixtures
import test_lreal_math as rollback
import test_lreal_advanced as advanced
from logixlab.model import INT_BITS,Project
from logixlab.runtime import Engine

TYPES=(*INT_BITS,'REAL')
RELATIONS=('EQU','NEQ','LES','LEQ','GRT','GEQ')


class MixedRealComparisonTests(unittest.TestCase):
    setUp=fixtures.NumericComparisonTests.setUp
    checked=fixtures.NumericComparisonTests.checked
    snapshot=staticmethod(rollback.LrealMathTests.snapshot)
    fault=rollback.LrealMathTests.fault

    def engine(self,rungs=None,*,source='REAL',other='DINT',high='DINT',values=(7,3,10),mutate=None):
        return fixtures.NumericComparisonTests.engine(self,rungs or ['GRT(Source,Mask)OTE(RunLatch);'],types=(source,other,high),values=values,mutate=mutate)

    def test_seventeen_tag_pairs_six_relations_and_read_only_sources(self):
        for source,other in itertools.product(TYPES,repeat=2):
            if 'REAL' not in (source,other):continue
            for name,want in zip(RELATIONS,(False,True,False,False,True,True)):
                with self.subTest(source=source,other=other,name=name):
                    e=self.checked([f'{name}(Source,Mask)OTE(RunLatch);'],source=source,other=other)
                    before=(e.memory.read('Source'),e.memory.read('Mask'));e.step();self.assertIs(e.memory.read('RunLatch'),want)
                    self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),before)
                    e.memory.write('Source',3);e.step();self.assertIs(e.memory.read('RunLatch'),name in ('EQU','LEQ','GEQ'))
                    e.memory.write('Source',2);e.step();self.assertIs(e.memory.read('RunLatch'),name in ('NEQ','LES','LEQ'))

    def test_all_217_limit_type_triples_use_converted_inclusive_and_reversed_bounds(self):
        for low,test,high in itertools.product(TYPES,repeat=3):
            if 'REAL' not in (low,test,high):continue
            with self.subTest(low=low,test=test,high=high):
                e=self.checked(['LIM(Source,Mask,Dest)OTE(RunLatch);'],source=low,other=test,high=high,values=(1,2,3))
                e.step();self.assertTrue(e.memory.read('RunLatch'))
                e.memory.write('Source',3);e.memory.write('Dest',1);e.step();self.assertFalse(e.memory.read('RunLatch'))
                e.memory.write('Mask',3);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_dint_and_wide_integer_values_round_before_comparison(self):
        e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],values=(16777216,16777217,0));e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Mask'),16777217)
        for source,value,other,want in [('ULINT',2**64-1,float(2**64),True),('LINT',9007199254740993,9007199254740992.0,True),('LINT',-1,0.0,False)]:
            e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],source=source,other='REAL',values=(value,other,0));e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_integer_and_floating_constants_convert_to_real_with_a_real_tag(self):
        for call,value in [('EQU(Source,16777217)',16777216),('EQU(16777217,Source)',16777216),
                           ('EQU(Source,1.1)',1.1),('EQU(1.1,Source)',1.1),
                           ('EQU(Source,2147483647)',2147483648),('EQU(Source,-2147483648)',-2147483648),
                           ('EQU(Source,16#7FFF_FFFF)',2147483648)]:
            e=self.checked([call+'OTE(RunLatch);'],values=(value,3,10));before=e.memory.read('Source');e.step()
            self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),before)
        for args,want in [('0,Source,10',True),('Source,2,10',False),('0,2,Source',True)]:
            e=self.checked([f'LIM({args})OTE(RunLatch);'],values=(3,0,0));e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_limit_direction_and_singleton_are_determined_after_rounding(self):
        e=self.checked(['LIM(Source,Mask,Dest)OTE(RunLatch);'],source='DINT',other='REAL',high='REAL',values=(16777217,16777215,16777216))
        e.step();self.assertFalse(e.memory.read('RunLatch'));e.memory.write('Mask',16777216);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['LIM(Source,Mask,Dest)OTE(RunLatch);'],source='ULINT',other='DINT',high='REAL',values=(9007199254740993,0,9007199254740992.0))
        e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_lreal_precedence_and_integer_only_exact_ordering_remain(self):
        e=self.checked(['GRT(Source,Mask)OTE(RunLatch);'],source='LREAL',other='REAL',values=(1.0000000000000002,1.0,0));e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['GRT(Source,Mask)OTE(RunLatch);'],source='LINT',other='LINT',values=(9007199254740993,9007199254740992,0));e.step();self.assertTrue(e.memory.read('RunLatch'))
        # An unused LREAL tag does not select binary64 for these REAL/DINT inputs.
        e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],high='LREAL',values=(16777216,16777217,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_false_prescan_unknown_values_and_each_required_limit_operand(self):
        e=self.checked(['XIC(StartPB)GRT(Values[Index],Mask)OTE(RunLatch);']);e.enter_run();e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Values[1]',4);e.step();self.assertTrue(e.memory.read('RunLatch'))
        for call in ('LIM(Values[0],Source,Mask);','LIM(Source,Values[0],Mask);','LIM(Source,Mask,Values[0]);','EQU(Values[0],0);'):
            e=self.checked([call]);self.fault(e,'Unknown')

    def test_alias_udt_members_and_late_fault_keep_sources_and_coils_atomic(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='RealPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='REAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='RealPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='RealPacket')
            E.SubElement(obj,'DataValueMember',Name='Value',DataType='REAL',Value='16777216');E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='REAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['EQU(Selected,Mask)OTE(RunLatch);'],values=(1,16777217,0),mutate=fields);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Packet.Guard'),777)
        e=self.checked(['MOV(99,SpeedCommand);','EQU(Source,Mask)OTE(RunLatch);','DIV(1,Index,SpeedCommand);'],values=(16777216,16777217,0));e.memory.write('Index',0);self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def aoi(self):
        helper=advanced.LrealAdvancedTests();helper.setUp();self.addCleanup(helper.doCleanups)
        original=helper.aoi();root=E.parse(original.project.path).getroot();definition=root.find('.//AddOnInstructionDefinition')
        definition.find('Parameters/Parameter[@Name="Buffer"]').set('DataType','REAL')
        for node in definition.find('LocalTags/LocalTag[@Name="Stack"]').iter():
            if node.get('DataType')=='LREAL':node.set('DataType','REAL')
        local=E.SubElement(definition.find('LocalTags'),'LocalTag',Name='Compared',DataType='BOOL')
        E.SubElement(E.SubElement(local,'Data',Format='Decorated'),'DataValue',DataType='BOOL',Value='0')
        for suffix in ('A','B'):
            tag=root.find(f'./Controller/Tags/Tag[@Name="Buffer{suffix}"]');tag.set('DataType','REAL');tag.find('Data/Array').set('DataType','REAL')
            struct=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure');arr=struct.find('ArrayMember[@Name="Stack"]');arr.set('DataType','REAL');arr.find('Element').set('Value','16777216')
        advanced.queues.logic(root,['EQU(Stack[0],Value)OTE(Compared);','LIM(0,Stack[0],Value)OTE(EnableOut);'])
        E.ElementTree(root).write(original.project.path,encoding='utf8',xml_declaration=True);return Engine(Project(original.project.path))

    def test_warm_aoi_copied_dint_inputs_real_locals_and_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.memory.write('ValueA',16777217);e.memory.write('ValueB',16777216);e.step()
        self.assertTrue(e.memory.read('DriverA.Compared'));self.assertTrue(e.memory.read('DriverB.Compared'))
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertTrue(e.memory.read('DriverA.Compared'))

    def test_signed_zero_subnormal_and_tiny_literal_conversion(self):
        e=self.checked(['EQU(Source,0)OTE(RunLatch);'],values=(-0.0,3,10));e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['GRT(Source,1e-50)OTE(RunLatch);'],values=(1.401298464324817e-45,3,10));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_literal_type_shape_and_other_family_guards_remain_structural(self):
        for token in ('TRUE','2147483648','-2147483649','1e40','1e999','1L','Values'):
            self.assertTrue(self.engine([f'AFI()EQU(Source,{token});']).blockers,token)
        self.assertTrue(self.engine(['MEQ(Source,Mask,Dest);']).blockers)
        self.assertTrue(self.engine(['CMP(Source>Mask);'],other='ULINT').blockers)
        self.assertTrue(self.engine(['EQU(Source,1e39);'],source='LREAL').blockers)

    def test_report_records_float32_policy_and_profile_precedence(self):
        report=self.checked().report()['numeric_comparisons'];d=report['real_ordering']
        self.assertEqual(len(d['source_types']),9);self.assertEqual(len(d['instructions']),7)
        self.assertIn('float32',d['calculation']);self.assertFalse(d['native_runtime_parity'])
