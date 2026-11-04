"""Homogeneous tagged ladder binary64 arithmetic, ordering and atomic faults."""
import copy
import math
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_scalar_math as fixtures
import test_aoi_queues as queues
from logixlab.model import ModelError

ARITHMETIC={'ADD':10.5,'SUB':4.5,'MUL':22.5,'DIV':2.5,'MOD':1.5,'NEG':-7.5,'ABS':7.5}
RELATIONS={'EQU':False,'NEQ':True,'LES':False,'LEQ':False,'GRT':True,'GEQ':True}


class LrealMathTests(unittest.TestCase):
    setUp=fixtures.ScalarMathTests.setUp
    checked=fixtures.ScalarMathTests.checked

    def engine(self,rungs=None,**kwargs):
        options=dict(dtype='LREAL',value=7.5);options.update(kwargs)
        return fixtures.ScalarMathTests.engine(self,rungs,**options)

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.scan_count,e.time_ms,e.trace,
                              e.scheduler_description(),e._program_timings,e._task_measurements,e._task_scan_timings))

    def fault(self,e,text):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,text):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertFalse(e.memory.structural)

    def test_all_seven_operations_keep_binary64_and_establish_unknown_results(self):
        for name,expected in ARITHMETIC.items():
            e=self.checked([fixtures.operation(name)+';']);e.step()
            self.assertEqual(e.memory.read('Results'),[None,expected,None]);self.assertEqual(e.memory.read('Source'),7.5)
        e=self.checked(value=1.0000000000000002);e.memory.write('Mask',1.0);e.step()
        self.assertEqual(e.memory.read('Results[1]'),2.0)
        e=self.checked(['SUB(Source,Mask,Results[1]);'],value=1.0000000000000002);e.memory.write('Mask',1.0);e.step()
        self.assertEqual(e.memory.read('Results[1]'),2**-52)

    def test_six_relations_compare_stored_values_without_real_narrowing(self):
        for name,expected in RELATIONS.items():
            e=self.checked([f'{name}(Source,Mask)OTE(RunLatch);'],value=1.0000000000000002)
            e.memory.write('Mask',1.0);e.step();self.assertIs(e.memory.read('RunLatch'),expected)
        e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],value=-0.0);e.memory.write('Mask',0.0);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_limits_include_endpoints_and_reversed_outside_ranges(self):
        for low,value,high,expected in [(1,1,3,True),(1,3,3,True),(1,0,3,False),(3,3,1,True),(3,1,1,True),(3,2,1,False),(3,4,1,True)]:
            e=self.checked(['LIM(Inputs[0],Source,Mask)OTE(RunLatch);'],value=value)
            e.memory.write('Inputs[0]',float(low));e.memory.write('Mask',float(high));e.step();self.assertIs(e.memory.read('RunLatch'),expected)

    def test_signed_zero_subnormals_large_values_and_remainder_sign(self):
        for name,value,other,expected in [('NEG',0.0,3,-0.0),('ABS',-0.0,3,0.0),('MUL',-0.0,3,-0.0),('DIV',-0.0,3,-0.0),('MOD',-0.0,3,-0.0),('DIV',1e-323,2,5e-324),('MUL',1e150,1e150,9.999999999999999e299),('MOD',-7.5,3,-1.5),('MOD',7.5,-3,1.5),('MOD',1.0,5e-324,0.0)]:
            e=self.checked([fixtures.operation(name)+';'],value=value);e.memory.write('Mask',float(other));e.step()
            self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',expected))

    def test_false_and_prescan_skip_all_live_indices_values_and_zero_divisors(self):
        calls=[fixtures.operation(n,source='Inputs[Index]',dest='Results[Index]') for n in ARITHMETIC]
        calls += [f'{n}(Inputs[Index],Source)OTE(RunLatch)' for n in RELATIONS]
        calls += ['LIM(Inputs[Index],Source,Mask)OTE(RunLatch)']
        for call in calls:
            e=self.checked(['XIC(StartPB)'+call+';']);e.memory.write('Index',99);e.memory.write('Mask',0.0)
            e.enter_run()
            with patch.object(e.memory,'read',wraps=e.memory.read) as reads:e.step()
            self.assertNotIn('Inputs[Index]',[c.args[0] for c in reads.call_args_list]);self.assertEqual(e.memory.read('Results'),[None]*3)

    def test_each_required_unknown_source_and_bad_output_index_rolls_back(self):
        for name in ARITHMETIC:
            e=self.checked([fixtures.operation(name,source='Inputs[0]')+';']);self.fault(e,'Unknown')
            e=self.checked([fixtures.operation(name,dest='Results[Index]')+';']);e.memory.write('Index',99);self.fault(e,'outside bounds')
        for name in RELATIONS:
            e=self.checked([f'{name}(Source,Inputs[0])OTE(RunLatch);']);self.fault(e,'Unknown')
        e=self.checked(['LIM(Source,Mask,Inputs[0])OTE(RunLatch);']);self.fault(e,'Unknown')

    def test_zero_divisors_and_nonfinite_results_fault_without_partial_updates(self):
        for name in ('DIV','MOD'):
            for zero in (0.0,-0.0):
                e=self.checked(['MOV(99,SpeedCommand);',fixtures.operation(name)+';']);e.memory.write('Mask',zero);self.fault(e,'zero')
        for name,value,other in [('ADD',1e308,1e308),('SUB',-1e308,1e308),('MUL',1e308,1e308),('DIV',1e308,1e-308)]:
            e=self.checked(['MOV(99,SpeedCommand);',fixtures.operation(name)+';'],value=value);e.memory.write('Mask',other);self.fault(e,'Nonfinite LREAL')

    def test_alias_member_outputs_source_overlap_and_late_fault_recovery(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='WidePair',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Pair',DataType='WidePair',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='WidePair')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Pair.Value')
        e=self.checked(['ADD(Source,Mask,Selected);','MUL(Source,Mask,Source);','DIV(1,Index,SpeedCommand);'],mutate=fields)
        self.fault(e,'zero');e.memory.write('Index',1);e.step()
        self.assertEqual((e.memory.read('Pair.Value'),e.memory.read('Pair.Guard'),e.memory.read('Source')),(10.5,777,22.5))

    def test_mixed_types_immediates_aggregates_constants_and_other_profiles_are_guarded(self):
        for text in ('ADD(Source,1,Dest);','SUB(1.0,Source,Dest);','ADD(Source,SpeedCommand,Dest);','MUL(Source,Mask,SpeedCommand);','EQU(Source,1);','EQU(Source,SpeedCommand);','LIM(Source,1.0,Mask);','ADD(Inputs,Mask,Dest);'):
            self.assertTrue(self.engine([text]).blockers,text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()ADD(Source,Mask,Results[1]);'],mutate=constant).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(mutate=old).blockers)

    def test_st_expressions_cpt_cmp_bitwise_and_advanced_math_remain_guarded(self):
        for text in ('CPT(Dest,Source+Mask);','CMP(Source>Mask);','AND(Source,Mask,Dest);','SQR(Source,Dest);'):
            self.assertTrue(self.engine([text]).blockers,text)
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='Dest := Source+Mask;'
        self.assertTrue(self.engine(mutate=st).blockers)

    def test_existing_aoi_lreal_inout_and_local_arrays_retain_atomic_bindings(self):
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def change(root):
            definition=root.find('.//AddOnInstructionDefinition');definition.find('Parameters/Parameter[@Name="Buffer"]').set('DataType','LREAL')
            for node in definition.find('LocalTags/LocalTag[@Name="Stack"]').iter():
                if node.get('DataType')=='DINT':node.set('DataType','LREAL')
            for suffix in ('A','B'):
                tag=root.find(f'./Controller/Tags/Tag[@Name="Buffer{suffix}"]');tag.set('DataType','LREAL');tag.find('Data/Array').set('DataType','LREAL')
                array=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/ArrayMember[@Name="Stack"]');array.set('DataType','LREAL');array.find('Element').set('Value','1.0000000000000002')
            queues.logic(root,['ADD(Buffer[Index],Stack[0],Buffer[Index]);','NEG(Stack[0],Stack[1]);'])
            queues.logic(root,['NOP();'],'EnableInFalse')
        e=f.checked(change);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual(e.memory.read('BufferA[1]'),1.0000000000000002);self.assertEqual(e.memory.read('BufferB[2]'),1.0000000000000002)
        self.assertEqual(e.memory.read('DriverA.Stack[1]'),-1.0000000000000002)
        self.assertEqual(e.memory.frames['@AOI:drivera']['buffer'],('BufferA',''))
        self.assertEqual(e.memory.frames['@AOI:driverb']['buffer'],('BufferB',''))

    def test_report_states_homogeneous_binary64_and_native_limits(self):
        report=self.checked().report()
        self.assertEqual(report['scalar_math']['lreal_arithmetic']['instructions'],sorted(ARITHMETIC))
        self.assertEqual(len(report['numeric_comparisons']['lreal_ordering']['instructions']),7)
        self.assertFalse(report['scalar_math']['lreal_arithmetic']['native_runtime_parity'])
