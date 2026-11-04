"""Read-only mixed numeric comparisons promoted by an actual LREAL tag."""
import itertools
import unittest
from xml.etree import ElementTree as E

import test_lreal_math as basic
import test_lreal_advanced as advanced
from logixlab.model import INT_BITS, Project
from logixlab.runtime import Engine

TYPES=(*INT_BITS,'REAL','LREAL')
RELATIONS=('EQU','NEQ','LES','LEQ','GRT','GEQ')


class MixedLrealComparisonTests(unittest.TestCase):
    setUp=basic.LrealMathTests.setUp
    checked=basic.LrealMathTests.checked
    snapshot=staticmethod(basic.LrealMathTests.snapshot)
    fault=basic.LrealMathTests.fault

    def engine(self,rungs=None,*,source='LREAL',other='DINT',value=7.5,high='DINT',high_value=10,mutate=None):
        def fields(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='High',DataType=high,TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=high,Value=str(high_value))
            if mutate:mutate(root)
        return basic.LrealMathTests.engine(self,rungs or ['GRT(Source,Mask)OTE(RunLatch);'],dtype=other,source=source,dest='LREAL',value=value,mutate=fields)

    def test_all_nineteen_numeric_pairs_and_six_relations_preserve_sources(self):
        for source,other in itertools.product(TYPES,repeat=2):
            if 'LREAL' not in (source,other):continue
            for name in RELATIONS:
                with self.subTest(source=source,other=other,name=name):
                    e=self.checked([f'{name}(Source,Mask)OTE(RunLatch);'],source=source,other=other,value=7 if source in INT_BITS else 7.5)
                    a,b=e.memory.read('Source'),e.memory.read('Mask');e.step();self.assertIs(e.memory.read('RunLatch'),name in ('NEQ','GRT','GEQ'));self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),(a,b))
                    e.memory.write('Source',3);e.step();self.assertIs(e.memory.read('RunLatch'),name in ('EQU','LEQ','GEQ'))
                    e.memory.write('Source',2);e.step();self.assertIs(e.memory.read('RunLatch'),name in ('NEQ','LES','LEQ'))

    def test_all_271_limit_type_triples_use_inclusive_and_reversed_limits(self):
        for low,test,high in itertools.product(TYPES,repeat=3):
            if 'LREAL' not in (low,test,high):continue
            with self.subTest(low=low,test=test,high=high):
                e=self.checked(['LIM(Source,Mask,High)OTE(RunLatch);'],source=low,other=test,high=high,value=1,high_value=3);e.memory.write('Mask',2);e.step();self.assertTrue(e.memory.read('RunLatch'))
                e.memory.write('Source',3);e.memory.write('High',1);e.step();self.assertFalse(e.memory.read('RunLatch'))
                e.memory.write('Mask',3);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_dint_precision_and_stored_real_precision_have_no_tolerance(self):
        e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],value=16777217.0);e.memory.write('Mask',16777217);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['GRT(Source,Mask)OTE(RunLatch);'],other='REAL',value=1.0000000000000002);e.memory.write('Mask',1);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],other='REAL',value=16777217.0);e.memory.write('Mask',16777217);e.step();self.assertEqual(e.memory.read('Mask'),16777216.0);self.assertFalse(e.memory.read('RunLatch'))

    def test_large_integers_round_before_comparison_and_limit_direction(self):
        for source,value in [('LINT',9007199254740993),('ULINT',2**64-1)]:
            e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],source=source,other='LREAL',value=value);e.memory.write('Mask',float(value));e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['LIM(Source,Mask,High)OTE(RunLatch);'],source='ULINT',other='LINT',value=9007199254740993,high='LREAL',high_value=9007199254740992.0)
        e.memory.write('Mask',9007199254740992);e.step();self.assertTrue(e.memory.read('RunLatch'));e.memory.write('Mask',0);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_signed_numeric_values_zero_subnormal_and_large_finite_ordering(self):
        for value,other,mask,want in [(-1.0,'ULINT',2**64-1,False),(5e-324,'REAL',0,True),(1e308,'ULINT',2**64-1,True)]:
            e=self.checked(other=other,value=value);e.memory.write('Mask',mask);e.step();self.assertIs(e.memory.read('RunLatch'),want)
        e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],value=-0.0);e.memory.write('Mask',0);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_false_prescan_invalid_indices_and_each_required_unknown_are_lazy(self):
        e=self.checked(['XIC(StartPB)GRT(Inputs[Index],Mask)OTE(RunLatch);']);e.memory.write('Index',99);e.enter_run();e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',4.0);e.step();self.assertTrue(e.memory.read('RunLatch'))
        for text in ('LIM(Inputs[0],Mask,High);','LIM(Source,Inputs[0],High);','LIM(Source,Mask,Inputs[0]);'):
            e=self.checked([text]);self.fault(e,'Unknown')
        e=self.checked(['EQU(Source,Mask);']);e.memory.values['mask']=None;self.fault(e,'Unknown')

    def test_late_fault_restores_coils_values_scheduler_and_timing_then_recovers(self):
        e=self.checked(['MOV(99,SpeedCommand);','GRT(Source,Mask)OTE(RunLatch);','DIV(1,Index,SpeedCommand);']);self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_alias_and_udt_members_retain_declared_comparison_types(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='LimitPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='LimitPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='LimitPacket')
            E.SubElement(obj,'DataValueMember',Name='Value',DataType='LREAL',Value='3.0000000000000004');E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['GRT(Selected,Mask)OTE(RunLatch);'],mutate=fields);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Packet.Guard'),777)

    def aoi(self):
        helper=advanced.LrealAdvancedTests();helper.setUp();self.addCleanup(helper.doCleanups);e=helper.aoi();root=E.parse(e.project.path).getroot()
        advanced.queues.logic(root,['LES(Stack[0],Value)OTE(Latched);','LIM(Index,Stack[0],Value)OTE(CompareEqual);'])
        # Reuse existing declared BOOL storage rather than inventing instance members.
        definition=root.find('.//AddOnInstructionDefinition');local_names={x.get('Name') for x in definition.find('LocalTags')}
        # This fixture's local Boolean names are selected explicitly below.
        for name in ('Latched','CompareEqual'):
            if name not in local_names:
                E.SubElement(definition.find('LocalTags'),'LocalTag',Name=name,DataType='BOOL',Radix='Decimal',ExternalAccess='Read/Write')
        E.ElementTree(root).write(e.project.path,encoding='utf8',xml_declaration=True);return Engine(Project(e.project.path))

    def test_aoi_copied_integer_inputs_lreal_locals_and_warm_state_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.step();e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertTrue(e.memory.read('DriverA.Latched'));self.assertTrue(e.memory.read('DriverB.Latched'));self.assertTrue(e.memory.read('DriverA.CompareEqual'));self.assertTrue(e.memory.read('DriverB.CompareEqual'))

    def test_immediates_bool_aggregate_cmp_and_other_profiles_remain_guarded(self):
        for text in ('EQU(Source,1);','LIM(1,Source,High);','LIM(Source,Mask,3);','EQU(Source,TRUE);','EQU(Inputs,Mask);','MEQ(Source,Mask,Source);','CMP(Source>Mask);'):
            self.assertTrue(self.engine([text]).blockers,text)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(mutate=old).blockers)

    def test_report_records_promotion_and_read_only_boundaries(self):
        d=self.checked().report()['numeric_comparisons']['lreal_ordering'];self.assertEqual(len(d['source_types']),10);self.assertIn('large integers may round',d['calculation']);self.assertFalse(d['native_runtime_parity'])
