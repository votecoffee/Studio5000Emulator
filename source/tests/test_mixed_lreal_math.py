"""Ladder binary64 arithmetic with one LREAL source and mixed numeric tags."""
import math
import operator
import struct
import unittest
from xml.etree import ElementTree as E

import test_lreal_math as basic
import test_lreal_advanced as advanced
from logixlab.model import INT_BITS, Project
from logixlab.runtime import Engine

TYPES=(*INT_BITS,'REAL','LREAL')
FUNCTIONS={'ADD':operator.add,'SUB':operator.sub,'MUL':operator.mul,'DIV':operator.truediv,'MOD':math.fmod}


class MixedLrealMathTests(unittest.TestCase):
    setUp=basic.LrealMathTests.setUp
    checked=basic.LrealMathTests.checked
    snapshot=staticmethod(basic.LrealMathTests.snapshot)
    fault=basic.LrealMathTests.fault

    def engine(self,rungs=None,*,source='LREAL',other='DINT',value=7.5,**kwargs):
        return basic.LrealMathTests.engine(self,rungs or ['ADD(Source,Mask,Results[1]);'],dtype=other,source=source,dest='LREAL',value=value,**kwargs)

    def test_all_nineteen_source_pairs_and_five_operations_establish_unknown_results(self):
        for source in TYPES:
            for other in TYPES:
                if 'LREAL' not in (source,other):continue
                for name,function in FUNCTIONS.items():
                    with self.subTest(source=source,other=other,name=name):
                        e=self.checked([f'{name}(Source,Mask,Results[1])OTE(RunLatch);'],source=source,other=other,value=7 if source in INT_BITS else 7.5)
                        expected=function(float(e.memory.read('Source')),float(e.memory.read('Mask')));e.step()
                        self.assertEqual(e.memory.read('Results'),[None,expected,None]);self.assertTrue(e.memory.read('RunLatch'))

    def test_dint_to_binary64_does_not_first_round_to_real(self):
        e=self.checked(value=1.0000000000000002);e.memory.write('Mask',16777217);e.step();self.assertEqual(e.memory.read('Results[1]'),16777218.0)
        e=self.checked(['SUB(Source,Mask,Results[1]);'],value=16777218.0);e.memory.write('Mask',16777217);e.step();self.assertEqual(e.memory.read('Results[1]'),1.0)
        e=self.checked(['SUB(Source,Mask,Results[1]);'],other='REAL',value=1.0000000000000002);e.memory.write('Mask',1.0);e.step();self.assertEqual(e.memory.read('Results[1]'),2**-52)

    def test_stored_real_precision_and_wide_integer_rounding_are_explicit(self):
        e=self.checked(other='REAL',value=16777218.0);e.memory.write('Mask',16777217);e.step();self.assertEqual(e.memory.read('Mask'),16777216.0);self.assertEqual(e.memory.read('Results[1]'),33554434.0)
        for source,value in [('LINT',9007199254740993),('ULINT',2**64-1)]:
            e=self.checked(['SUB(Source,Mask,Results[1]);'],source=source,other='LREAL',value=value);e.memory.write('Mask',float(value));e.step();self.assertEqual(e.memory.read('Results[1]'),0.0)
        e=self.checked(['ADD(Source,Mask,Results[1]);'],source='LINT',other='LREAL',value=-1);e.memory.write('Mask',2.0);e.step();self.assertEqual(e.memory.read('Results[1]'),1.0)

    def test_signed_quotient_remainder_and_required_zero_sources(self):
        for name,expected in [('DIV',-2.5),('MOD',-1.5)]:
            e=self.checked([f'{name}(Source,Mask,Results[1]);'],value=-7.5);e.step();self.assertEqual(e.memory.read('Results[1]'),expected)
            e.memory.write('Mask',0);self.fault(e,'zero')
        e=self.checked(['MUL(Source,Inputs[0],Results[1]);'],value=0.0);self.fault(e,'Unknown')
        e=self.checked(['MUL(Inputs[0],Mask,Results[1]);'],source='DINT',other='LREAL',value=0);e.memory.write('Mask',0.0);self.fault(e,'Unknown')

    def test_false_prescan_dynamic_indices_and_unknown_full_writes(self):
        e=self.checked(['XIC(StartPB)ADD(Inputs[Index],Mask,Results[Index]);'],source='DINT',other='LREAL',value=7)
        e.memory.write('Index',99);e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown')
        e.memory.write('Inputs[1]',16777217);e.memory.write('Mask',1.0);e.step();self.assertEqual(e.memory.read('Results'),[None,16777218.0,None])

    def test_overflow_late_fault_and_recovery_restore_task_timing(self):
        e=self.checked(['MOV(99,SpeedCommand);','MUL(Source,Mask,Results[1]);'],value=1e308);self.fault(e,'Nonfinite LREAL')
        e=self.checked(['ADD(Source,Mask,Results[1]);','DIV(1,Index,SpeedCommand);']);self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results[1]'),10.5)

    def test_alias_member_and_source_overlap_capture_sources_before_write(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='MixedDouble',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='MixedDouble',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='MixedDouble')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['ADD(Source,Mask,Source);','SUB(Source,Mask,Selected);'],mutate=fields);e.step();self.assertEqual((e.memory.read('Source'),e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(10.5,7.5,777))

    def aoi(self):
        helper=advanced.LrealAdvancedTests();helper.setUp();self.addCleanup(helper.doCleanups);e=helper.aoi();root=E.parse(e.project.path).getroot()
        advanced.queues.logic(root,['ADD(Stack[0],Value,Buffer[Index]);','SUB(Buffer[Index],Value,Stack[1]);'])
        E.ElementTree(root).write(e.project.path,encoding='utf8',xml_declaration=True);return Engine(Project(e.project.path))

    def test_aoi_mixed_copied_integer_input_and_lreal_arrays_rollback_independently(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.step();before=(e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'));e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),before);self.assertEqual((e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[1]')),(9.0,4.0))

    def test_immediates_comparisons_narrow_results_and_other_families_remain_guarded(self):
        for text in ('ADD(Source,1,Dest);','EQU(Source,TRUE);','LIM(Source,1,Source);','ADD(Source,Mask,SpeedCommand);','CPT(Dest,Source+Mask);','SQR(Mask,Dest);','AND(Source,Mask,Dest);','ADD(Inputs,Mask,Dest);'):
            self.assertTrue(self.engine([text]).blockers,text)
        self.assertTrue(self.engine(source='DINT',other='REAL',value=1).blockers)
        def readonly(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=readonly).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(mutate=old).blockers)

    def test_report_separates_arithmetic_results_from_read_only_ordering(self):
        d=self.checked().report();self.assertEqual(len(d['scalar_math']['lreal_arithmetic']['source_types']),10);self.assertFalse(d['scalar_math']['lreal_arithmetic']['native_runtime_parity'])
        self.assertEqual(d['numeric_comparisons']['lreal_ordering']['types'],['LREAL']);self.assertIn('at least one LREAL',d['numeric_comparisons']['lreal_ordering']['operands'])
