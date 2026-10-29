"""Common finite REAL math, documented negative roots and scan rollback."""
import copy
import math
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
from logixlab.real_math import INSTRUCTIONS


class RealMathTests(unittest.TestCase):
    setUp = fixtures.BitTransferTests.setUp
    checked = fixtures.BitTransferTests.checked

    def engine(self, rungs, *, types=('REAL','REAL','REAL'), values=(0.5,2.0,7.0), mutate=None):
        return fixtures.BitTransferTests.engine(self,rungs,types=types,values=values,mutate=mutate)

    def st(self,text,**kwargs):
        def change(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine')
            routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=text
        return self.engine([],mutate=change,**kwargs)

    def test_each_unary_instruction_with_known_reference_values(self):
        cases=(('SQR',9,3),('LN',1,0),('LOG',100,2),('DEG',0,0),('RAD',180,math.pi),
               ('SIN',0,0),('COS',0,1),('TAN',0,0),('ASN',1,math.pi/2),
               ('ACS',-1,math.pi),('ATN',1,math.pi/4))
        for name,value,expected in cases:
            with self.subTest(name=name):
                e=self.checked([f'{name}(Source,Dest);'],values=(value,2,7));e.step()
                self.assertAlmostEqual(e.memory.read('Dest'),expected,places=6)
                self.assertEqual(e.memory.read('Source'),float(value))

    def test_square_root_uses_absolute_value_for_all_supported_source_types(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            e=self.checked(['SQR(Source,Dest);'],types=(dtype,'REAL','REAL'),values=(-16,2,7))
            e.step();self.assertEqual(e.memory.read('Dest'),4.0)
        e=self.checked(['SQR(Source,Dest);'],types=('DINT','REAL','REAL'),values=(-2147483648,2,7))
        e.step();self.assertEqual(e.memory.read('Dest'),46340.94921875)

    def test_negative_root_cpt_and_st_functions_share_documented_rule(self):
        e=self.checked(['CPT(Dest,SQR(-16.0));']);e.step();self.assertEqual(e.memory.read('Dest'),4.0)
        e=self.st('Dest:=SQRT(-25.0);');self.assertEqual(e.blockers,[])
        e.step();self.assertEqual(e.memory.read('Dest'),5.0)

    def test_power_supports_negative_integral_and_fractional_positive_cases(self):
        for base,exponent,expected in ((2,3,8),(2,-3,0.125),(-2,3,-8),(-2,4,16),(9,0.5,3),(0,0,1),(0,2,0)):
            e=self.checked(['XPY(Source,Mask,Dest);'],values=(base,exponent,7));e.step()
            self.assertEqual(e.memory.read('Dest'),float(expected))

    def test_angles_and_inverse_trig_are_radians(self):
        e=self.checked(['RAD(30.0,Dest);','SIN(Dest,Mask);']);e.step()
        self.assertAlmostEqual(e.memory.read('Mask'),0.5,places=6)
        e=self.checked(['ASN(0.5,Dest);','DEG(Dest,Mask);']);e.step()
        self.assertAlmostEqual(e.memory.read('Mask'),30.0,places=5)
        for name,source,expected in (('ACS',1,0),('ASN',-1,-math.pi/2),('ATN',-1,-math.pi/4)):
            e=self.checked([f'{name}(Source,Dest);'],values=(source,2,7));e.step()
            self.assertAlmostEqual(e.memory.read('Dest'),expected,places=6)

    def test_sources_and_results_are_rounded_to_float32(self):
        e=self.checked(['XPY(Source,1.0,Dest);'],types=('DINT','REAL','REAL'),values=(16777217,2,7))
        e.step();self.assertEqual(e.memory.read('Dest'),16777216.0)
        e=self.checked(['SQR(2.0,Dest);']);e.step()
        self.assertEqual(e.memory.read('Dest'),1.4142135381698608)

    def test_representable_immediates_and_narrow_integer_sources(self):
        for source in ('16.0','16','16#10','8#20','2#10000'):
            e=self.checked([f'SQR({source},Dest);']);e.step();self.assertEqual(e.memory.read('Dest'),4.0)
        for dtype in ('SINT','INT','DINT'):
            e=self.checked(['XPY(Source,Mask,Dest);'],types=(dtype,dtype,'REAL'),values=(2,3,7))
            e.step();self.assertEqual(e.memory.read('Dest'),8.0)

    def test_domain_and_overflow_failures_roll_back_prior_writes_and_scheduler(self):
        for text in ('LN(0.0,Dest);','LOG(-1.0,Dest);','ASN(1.1,Dest);','ACS(-1.1,Dest);',
                     'XPY(-2.0,0.5,Dest);','XPY(0.0,-1.0,Dest);','XPY(2.0,128.0,Dest);','DEG(3.0e38,Dest);'):
            e=self.checked(['MOV(23,Mask);',text]);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before,text)
            self.assertEqual((e.scan_count,e.time_ms),(0,0))
            self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_prescan_and_false_rungs_retain_results_without_reading_unknown_sources(self):
        for name in INSTRUCTIONS:
            args='Source,Mask,Dest' if name=='XPY' else 'Source,Dest'
            e=self.checked([f'AFI(){name}({args});'])
            self.assertEqual(e.memory.read('Dest'),7.0)
            e.memory.values['source']=e.memory.values['mask']=None;e.step()
            self.assertEqual(e.memory.read('Dest'),7.0)

    def test_full_results_establish_unknown_destination_and_preserve_rung_power(self):
        for name in INSTRUCTIONS:
            args='Source,Mask,Dest' if name=='XPY' else 'Source,Dest'
            e=self.checked([f'{name}({args})OTE(RunLatch);']);e.memory.values['dest']=None;e.step()
            self.assertIsInstance(e.memory.read('Dest'),float);self.assertTrue(e.memory.read('RunLatch'))

    def test_unknown_or_nonfinite_sources_roll_back(self):
        for value in (None,float('nan'),float('inf'),-float('inf')):
            e=self.checked(['SQR(Source,Dest);']);e.memory.values['source']=value
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.read('Dest'),7.0)

    def test_in_place_result_captures_source(self):
        e=self.checked(['SQR(Source,Source);'],values=(-16,2,7));e.step()
        self.assertEqual(e.memory.read('Source'),4.0)
        e=self.checked(['XPY(Source,Mask,Source);'],values=(2,3,7));e.step()
        self.assertEqual(e.memory.read('Source'),8.0)

    def test_constant_sources_allowed_and_constant_destinations_rejected(self):
        def source(root):root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
        e=self.checked(['SQR(Source,Dest);'],mutate=source);e.step()
        def dest(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['SQR(Source,Dest);'],mutate=dest).blockers)

    def test_unqualified_types_immediates_arities_and_mnemonics_block(self):
        for dtype in ('BOOL','LINT','USINT','UINT','UDINT','ULINT'):
            self.assertTrue(self.engine(['SQR(Source,Dest);'],types=(dtype,'REAL','REAL'),values=(0,2,7)).blockers)
        for dtype in ('SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT'):
            self.assertTrue(self.engine(['SQR(Source,Dest);'],types=('REAL','REAL',dtype),values=(0.5,2,0)).blockers)
        for text in ('SQR(TRUE,Dest);','SQR(2147483648,Dest);','SQR(16#FFFF_FFFF,Dest);',
                     'SQR(1e40,Dest);','SQR(1e309,Dest);','SQR(Source);','XPY(Source,Dest);',
                     'SQRT(Source,Dest);','EXPT(Source,Mask,Dest);','ACOS(Source,Dest);'):
            self.assertTrue(self.engine([text]).blockers,text)

    def test_st_uses_expression_functions_not_ladder_call_forms(self):
        for text in ('SQR(Source,Dest);','LN(Source,Dest);','SIN(Source,Dest);','XPY(Source,Mask,Dest);'):
            self.assertTrue(self.st(text).blockers)
        e=self.st('Dest:=SQRT(-16.0)+SIN(0.0)+ACOS(1.0)+(2.0**3.0);')
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Dest'),12.0)

    def test_scalar_array_alias_member_and_indirect_access(self):
        def tags(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='REAL',Dimension='0')
            tags=c.find('Tags');array=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Values',DataType='REAL',Dimensions='2',TagType='Base'),'Data',Format='Decorated'),'Array',DataType='REAL',Dimensions='2')
            for i,value in enumerate((-16,999)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
            struct=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(struct,'DataValueMember',Name='Value',DataType='REAL',Value='0')
            E.SubElement(tags,'Tag',Name='AliasValue',TagType='Alias',DataType='REAL',AliasFor='Packet1.Value')
        e=self.checked(['SQR(Values[Source],AliasValue);'],types=('DINT','REAL','REAL'),values=(0,2,7),mutate=tags)
        e.step();self.assertEqual(e.memory.read('Packet1.Value'),4.0);self.assertEqual(e.memory.read('Values[1]'),999.0)
        self.assertTrue(self.engine(['SQR(Values,Dest);'],mutate=tags).blockers)
        self.assertTrue(self.engine(['SQR(Source,Values);'],mutate=tags).blockers)

    def test_nested_aoi_input_and_output_bindings(self):
        import test_addons as aoi
        f=aoi.AddOnTests();f.setUp();self.addCleanup(f.doCleanups)
        f.body('LabScale')[0].find('Text').text='SQR(Raw,Scaled)XPY(Scaled,Gain,Result);'
        e=f.engine();self.assertEqual(e.blockers,[]);e.memory.write('RawValue',-16.0);e.step()
        self.assertEqual(e.memory.read('NestedScale.Core.Scaled'),4.0)
        self.assertEqual(e.memory.read('ScaledValue'),16.0)

    def test_late_fault_rolls_back_math_and_expression_outputs(self):
        e=self.checked(['SQR(Source,Dest);','CPT(Mask,SQRT(-25.0));','DIV(1,0,SpeedCommand);'])
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_profile_and_report_expose_remaining_forms(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['SQR(Source,Dest);'],mutate=old).blockers)
        e=self.checked(['SQR(Source,Dest);']);report=e.report()['real_math']
        self.assertEqual(len(report['instructions']),12);self.assertEqual(report['destination'],'REAL')
        self.assertFalse(report['native_math_status']);self.assertFalse(report['native_fault_classification'])


    def test_bundled_math_lab_roots_and_all_new_instruction_families(self):
        from logixlab.server import SAMPLES
        self.assertIn('MathLab',SAMPLES)
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/MathLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step()
        for name,value in dict(Root=4.0,CptRoot=4.0,StRoot=4.0,Log10=2.0,Powered=8.0,
                               RoundTrip=30.0,Sine=0.5,AllOK=True).items():
            self.assertEqual(e.memory.read(name),value,name)
        self.assertEqual(e.memory.read('Radians'),e.memory.read('StAngle'))
        self.assertAlmostEqual(e.memory.read('Cosine'),0.8660254,places=6)
        self.assertAlmostEqual(e.memory.read('ArcCosine'),1.04719755,places=6)


if __name__=='__main__':unittest.main()
