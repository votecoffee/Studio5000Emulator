"""Finite tagged binary64 roots/powers/logarithms/trigonometry in ladder."""
import math
import struct
import unittest
from xml.etree import ElementTree as E

import test_lreal_math as basic
import test_aoi_queues as queues

CASES={'SQR':(9.0,3.0),'LN':(1.0,0.0),'LOG':(100.0,2.0),'XPY':(2.0,8.0),
       'DEG':(math.pi/2,90.0),'RAD':(180.0,math.pi),'SIN':(math.pi/6,0.5),
       'COS':(math.pi/3,0.5),'TAN':(math.pi/4,1.0),'ASN':(1.0,math.pi/2),
       'ACS':(-1.0,math.pi),'ATN':(1.0,math.pi/4)}


def operation(name,source='Source',dest='Results[1]'):
    return f'{name}({source},Mask,{dest})' if name=='XPY' else f'{name}({source},{dest})'


class LrealAdvancedTests(unittest.TestCase):
    setUp=basic.LrealMathTests.setUp
    engine=basic.LrealMathTests.engine
    checked=basic.LrealMathTests.checked
    snapshot=staticmethod(basic.LrealMathTests.snapshot)
    fault=basic.LrealMathTests.fault

    def test_all_twelve_forms_establish_unknown_results_with_known_reference_values(self):
        for name,(value,expected) in CASES.items():
            with self.subTest(name=name):
                e=self.checked([operation(name)+'OTE(RunLatch);'],value=value);e.step()
                self.assertAlmostEqual(e.memory.read('Results[1]'),expected,places=15)
                self.assertEqual(e.memory.read('Results')[::2],[None,None]);self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),value)

    def test_precision_and_large_small_values_do_not_pass_through_real(self):
        for name,value,other,expected in [('LN',1.0000000000000002,3,2.2204460492503128e-16),('XPY',1.0000000000000002,2,1.0000000000000004),('SIN',1e-300,3,1e-300),('SQR',1e308,3,1e154)]:
            e=self.checked([operation(name)+';'],value=value);e.memory.write('Mask',float(other));e.step()
            self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',expected))
        for name in ('LN','LOG'):
            e=self.checked([operation(name)+';'],value=5e-324);e.step();self.assertTrue(math.isfinite(e.memory.read('Results[1]')));self.assertLess(e.memory.read('Results[1]'),-300)

    def test_negative_root_absolute_value_and_signed_zero_follow_existing_rule(self):
        e=self.checked(['SQR(Source,Results[1]);'],value=-9.0);e.step();self.assertEqual(e.memory.read('Results[1]'),3.0)
        for name in ('SIN','TAN','ASN','ATN','DEG','RAD'):
            e=self.checked([operation(name)+';'],value=-0.0);e.step();self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',-0.0))
        e=self.checked(['SQR(Source,Results[1]);'],value=-0.0);e.step();self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),bytes(8))

    def test_power_integer_fractional_zero_and_underflow_cases(self):
        for value,exponent,expected in [(-2.0,3.0,-8.0),(4.0,0.5,2.0),(0.0,0.0,1.0),(1e-308,2.0,0.0),(-1e-308,3.0,-0.0)]:
            e=self.checked(['XPY(Source,Mask,Results[1]);'],value=value);e.memory.write('Mask',exponent);e.step()
            self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',expected))

    def test_false_and_prescan_skip_unknowns_invalid_indices_and_domain_values(self):
        for name in CASES:
            e=self.checked(['XIC(StartPB)'+operation(name,source='Inputs[Index]',dest='Results[Index]')+';'])
            e.memory.write('Index',99);e.memory.write('Mask',0.5);e.enter_run();e.step()
            self.assertEqual(e.memory.read('Results'),[None]*3);self.assertFalse(e.memory.structural)

    def test_each_required_unknown_source_and_bad_output_index_faults_atomically(self):
        for name in CASES:
            e=self.checked([operation(name,source='Inputs[0]')+';']);self.fault(e,'Unknown')
            e=self.checked([operation(name,dest='Results[Index]')+';'],value=0.5);e.memory.write('Index',99);self.fault(e,'outside bounds')
        e=self.checked(['XPY(Source,Inputs[0],Results[1]);'],value=1.0);self.fault(e,'Unknown')

    def test_domain_and_overflow_faults_roll_back_prior_math_and_task_history(self):
        for name,value,other in [('LN',0,3),('LN',-1,3),('LOG',0,3),('ASN',1.0000000000000002,3),('ACS',-1.0000000000000002,3),('XPY',-2,0.5),('XPY',0,-1),('XPY',1e308,2),('DEG',1e308,3)]:
            e=self.checked(['MOV(99,SpeedCommand);',operation(name)+';'],value=value);e.memory.write('Mask',float(other));self.fault(e,'finite|Nonfinite')

    def test_unknown_complete_alias_member_and_overlapping_source_outputs(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='WideMath',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='WideMath',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='WideMath')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['XPY(Source,Mask,Source);','SQR(Source,Selected);'],value=3,mutate=fields);e.memory.write('Mask',2.0);e.step()
        self.assertEqual((e.memory.read('Source'),e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(9.0,3.0,777))

    def test_late_fault_keeps_all_outputs_and_recovery_uses_current_source(self):
        e=self.checked(['SQR(Source,Results[1]);','DIV(1,Index,SpeedCommand);'],value=9)
        self.fault(e,'zero');e.memory.write('Index',1);e.memory.write('Source',16.0);e.step();self.assertEqual(e.memory.read('Results[1]'),4.0)

    def test_mixed_types_immediates_aggregates_readonly_and_old_profiles_remain_guarded(self):
        for name in CASES:
            for source,dest in [('REAL','LREAL'),('LREAL','REAL'),('DINT','LREAL'),('LREAL','LINT')]:
                self.assertTrue(self.engine([operation(name)+';'],source=source,dest=dest).blockers,(name,source,dest))
            self.assertTrue(self.engine([operation(name,source='1.0')+';']).blockers,name)
            self.assertTrue(self.engine([operation(name,source='Inputs')+';']).blockers,name)
        self.assertTrue(self.engine(['XPY(Source,1.0,Dest);']).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()SQR(Source,Results[1]);'],mutate=constant).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['SQR(Source,Dest);'],mutate=old).blockers)

    def test_lreal_st_cpt_and_newer_instruction_aliases_remain_guarded(self):
        for text in ('CPT(Dest,SQR(Source));','SQRT(Source,Dest);','EXPT(Source,Mask,Dest);'):
            self.assertTrue(self.engine([text]).blockers,text)
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='Dest := SQRT(Source);'
        self.assertTrue(self.engine(mutate=st).blockers)

    def aoi(self):
        q=queues.AOIQueueTests();q.setUp();self.addCleanup(q.doCleanups)
        def change(root):
            definition=root.find('.//AddOnInstructionDefinition');definition.find('Parameters/Parameter[@Name="Buffer"]').set('DataType','LREAL')
            for node in definition.find('LocalTags/LocalTag[@Name="Stack"]').iter():
                if node.get('DataType')=='DINT':node.set('DataType','LREAL')
            for suffix,value in [('A','9.0'),('B','4.0')]:
                tag=root.find(f'./Controller/Tags/Tag[@Name="Buffer{suffix}"]');tag.set('DataType','LREAL');tag.find('Data/Array').set('DataType','LREAL')
                array=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/ArrayMember[@Name="Stack"]');array.set('DataType','LREAL');array.find('Element').set('Value',value)
            queues.logic(root,['SQR(Stack[0],Buffer[Index]);','LN(Stack[0],Stack[1]);']);queues.logic(root,['NOP();'],'EnableInFalse')
        return q.checked(change)

    def test_aoi_local_and_inout_arrays_preserve_independent_state_after_late_fault(self):
        e=self.aoi();e.step();e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(3.0,2.0))
        self.assertEqual(e.memory.read('DriverA.Stack[1]'),math.log(9.0));self.assertEqual(e.memory.read('DriverB.Stack[1]'),math.log(4.0))
        self.assertEqual(e.memory.frames['@AOI:drivera']['buffer'],('BufferA',''))

    def test_report_keeps_narrow_profile_and_separate_lreal_scope(self):
        r=self.checked(['SQR(Source,Dest);']).report()['real_math']
        self.assertEqual(len(r['lreal']['instructions']),12);self.assertEqual(r['lreal']['destination'],'Scalar LREAL tag')
        self.assertEqual(r['destinations'],['DINT','INT','REAL','SINT']);self.assertFalse(r['lreal']['native_runtime_parity'])
