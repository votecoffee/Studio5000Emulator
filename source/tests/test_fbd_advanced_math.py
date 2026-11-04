"""Finite REAL FBD roots/powers/logs/trig, shared math and rollback boundaries."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project,coerce
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/FBDAdvancedMathLab.L5X'
BLOCKS=(('SQR','RootState','Root'),('LN','NaturalState','NaturalLog'),('LOG','CommonState','CommonLog'),('XPY','PowerState','Power'),('RAD','RadiansState','Radians'),('SIN','SineState','Sine'),('COS','CosineState','Cosine'),('TAN','TangentState','Tangent'),('ASN','ArcSineState','ArcSine'),('ACS','ArcCosineState','ArcCosine'),('ATN','ArcTangentState','ArcTangent'),('DEG','DegreesState','RecoveredDegrees'))


class FBDAdvancedMathTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="AdvancedMath"]/FBDContent/Sheet')

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'advanced.L5X';E.ElementTree(root).write(p,encoding='utf-8',xml_declaration=True)
        return Engine(Project(p),mode,'MainProgram/AdvancedMath' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def settings(e,**values):
        for tag,value in values.items():e.memory.write(tag,value)

    @staticmethod
    def corrupt(e,ref,value=None):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,value)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def step(self,e):
        e.step(10);return tuple(e.memory.read(out) for _,_,out in BLOCKS)

    def test_default_twelve_block_graph_and_typed_float_outputs(self):
        e=self.checked();values=self.step(e)
        expected=(3,math.log(100),2,8,math.pi/6,.5,math.sqrt(3)/2,1/math.sqrt(3),math.pi/6,math.pi/3,math.pi/4,30)
        for actual,wanted in zip(values,expected,strict=True):self.assertAlmostEqual(actual,wanted,places=5);self.assertIs(type(actual),float)
        self.assertIs(e.memory.read('MathEnabled'),True);self.assertEqual(e.last_timer,{})

    def test_negative_square_root_uses_absolute_value(self):
        e=self.checked()
        for value,result in ((-9,3),(-.25,.5),(0,0),(16,4)):
            self.settings(e,RootInput=value);self.step(e);self.assertEqual(e.memory.read('Root'),result)

    def test_root_signed_zero_becomes_positive(self):
        e=self.checked();self.settings(e,RootInput=-0.0);self.step(e);self.assertEqual(math.copysign(1,e.memory.read('Root')),1)

    def test_logarithm_bases_and_fractional_values(self):
        e=self.checked()
        for value,base10 in ((1,0),(10,1),(.01,-2)):
            self.settings(e,LogInput=value);self.step(e);self.assertAlmostEqual(e.memory.read('CommonLog'),base10,places=6)
            self.assertEqual(e.memory.read('NaturalLog'),coerce(math.log(coerce(value,'REAL')),'REAL'))

    def test_power_source_order_and_negative_integral_exponents(self):
        e=self.checked()
        for a,b,result in ((2,3,8),(3,2,9),(-2,3,-8),(-2,2,4),(4,.5,2),(2,-3,.125)):
            self.settings(e,PowerBase=a,PowerExponent=b);self.step(e);self.assertEqual(e.memory.read('Power'),result)

    def test_trig_zero_and_quadrants(self):
        e=self.checked()
        for degrees,sine,cosine in ((0,0,1),(30,.5,math.sqrt(3)/2),(-30,-.5,math.sqrt(3)/2),(180,0,-1)):
            self.settings(e,AngleDegrees=degrees);self.step(e)
            self.assertAlmostEqual(e.memory.read('Sine'),sine,places=6);self.assertAlmostEqual(e.memory.read('Cosine'),cosine,places=6)

    def test_tangent_units_and_inverse_tangent(self):
        e=self.checked();self.settings(e,AngleDegrees=45,Slope=-1);self.step(e)
        self.assertAlmostEqual(e.memory.read('Tangent'),1,places=6);self.assertAlmostEqual(e.memory.read('ArcTangent'),-math.pi/4,places=6)

    def test_inverse_trig_endpoints_and_degree_conversion(self):
        e=self.checked()
        for ratio,sine,cosine,degrees in ((-1,-math.pi/2,math.pi,-90),(0,0,math.pi/2,0),(1,math.pi/2,0,90)):
            self.settings(e,Ratio=ratio);self.step(e)
            self.assertAlmostEqual(e.memory.read('ArcSine'),sine,places=6);self.assertAlmostEqual(e.memory.read('ArcCosine'),cosine,places=6);self.assertAlmostEqual(e.memory.read('RecoveredDegrees'),degrees,places=5)

    def test_float32_intermediate_is_used_by_downstream_trig(self):
        e=self.checked();self.settings(e,AngleDegrees=1234567);self.step(e)
        angle=coerce(math.radians(coerce(1234567,'REAL')),'REAL');self.assertEqual(e.memory.read('Radians'),angle)
        self.assertEqual(e.memory.read('Sine'),coerce(math.sin(angle),'REAL'))

    def test_rll_and_fbd_share_finite_math_without_native_parity_claim(self):
        def ladder(root):
            tags=root.find('./Controller/Tags');body=root.find('.//Routine[@Name="MainRoutine"]/RLLContent')
            refs=('RootInput','LogInput','LogInput','PowerBase,PowerExponent','AngleDegrees','Radians','Radians','Radians','Ratio','Ratio','Slope','ArcSine')
            for i,((op,_,out),args) in enumerate(zip(BLOCKS,refs,strict=True),3):
                name='Ladder'+out;tag=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='REAL');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='REAL',Value='0')
                E.SubElement(E.SubElement(body,'Rung',Number=str(i),Type='N'),'Text').text=op+'('+args+','+name+');'
        e=self.checked(ladder);self.settings(e,RootInput=-25,PowerBase=-2,PowerExponent=3,Ratio=-.5,AngleDegrees=-30,Slope=-2);self.step(e)
        for _,_,out in BLOCKS:self.assertEqual(e.memory.read(out),e.memory.read('Ladder'+out))

    def test_domains_fail_without_partial_outputs_or_advance(self):
        for values,op in (({'LogInput':0},'LN'),({'LogInput':-1},'LN'),({'Ratio':1.01},'ASN'),({'Ratio':-1.01},'ASN'),({'PowerBase':-2,'PowerExponent':.5},'XPY'),({'PowerBase':0,'PowerExponent':-1},'XPY')):
            e=self.checked();self.step(e);self.settings(e,**values);before=self.snapshot(e)
            with self.subTest(values=values),self.assertRaisesRegex(ModelError,'FBD '+op+' outside'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_log_and_acos_domains_independently(self):
        for ident,tag,pin,value,op in ((300,'CommonState','Source',0,'LOG'),(1000,'ArcCosineState','Source',2,'ACS')):
            def unwire(root):self.sheet(root).remove(self.sheet(root).find(f'Wire[@ToID="{ident}"][@ToParam="{pin}"]'))
            e=self.checked(unwire);self.settings(e,**{tag+'.'+pin:value});before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'FBD '+op+' outside'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_host_and_float32_power_overflow_roll_back(self):
        for a,b in ((1e20,3),(1e30,100)):
            e=self.checked();self.settings(e,PowerBase=a,PowerExponent=b);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'finite REAL'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_every_new_block_rejects_unknown_required_fields_at_own_read(self):
        for i,(op,tag,_) in enumerate(BLOCKS,1):
            for pin in (('SourceA','SourceB') if op=='XPY' else ('Source',)):
                def unwire(root):self.sheet(root).remove(self.sheet(root).find(f'Wire[@ToID="{i*100}"][@ToParam="{pin}"]'))
                e=self.checked(unwire);self.corrupt(e,tag+'.'+pin);before=self.snapshot(e)
                with self.subTest(op=op,pin=pin),self.assertRaisesRegex(ModelError,'FBD '+op+' '+pin+' is unknown'):self.step(e)
                self.assertEqual(self.snapshot(e),before)

    def test_power_zero_exponent_still_requires_known_base(self):
        e=self.checked();self.settings(e,PowerExponent=0);self.corrupt(e,'PowerBase')
        with self.assertRaisesRegex(ModelError,'XPY SourceA is unknown'):self.step(e)

    def test_each_new_block_rejects_nonfinite_values(self):
        for i,(op,tag,_) in enumerate(BLOCKS,1):
            pin='SourceA' if op=='XPY' else 'Source'
            def unwire(root):self.sheet(root).remove(self.sheet(root).find(f'Wire[@ToID="{i*100}"][@ToParam="{pin}"]'))
            for value in (float('nan'),float('inf'),float('-inf')):
                e=self.checked(unwire);self.corrupt(e,tag+'.'+pin,value)
                with self.subTest(op=op,value=value),self.assertRaisesRegex(ModelError,'finite REAL'):self.step(e)
                self.assertEqual(e.scan_count,0)

    def test_disabled_blocks_do_not_evaluate_invalid_domains(self):
        e=self.checked();before=self.step(e);self.settings(e,BlockEnable=False,LogInput=0,Ratio=2,PowerBase=-2,PowerExponent=.5)
        self.assertEqual(self.step(e),before);self.assertFalse(e.memory.read('MathEnabled'))

    def test_skipped_calls_hold_results_then_recompute(self):
        e=self.checked();before=self.step(e);self.settings(e,ExecuteGraph=False,RootInput=-25);self.assertEqual(self.step(e),before)
        self.settings(e,ExecuteGraph=True);self.step(e);self.assertEqual(e.memory.read('Root'),5)

    def test_unwired_enables_execute_despite_saved_false(self):
        def unwire(root):
            for wire in list(self.sheet(root).findall('Wire')):
                if wire.get('ToParam')=='EnableIn':self.sheet(root).remove(wire)
        e=self.checked(unwire);self.settings(e,BlockEnable=False)
        for _,tag,_ in BLOCKS:self.settings(e,**{tag+'.EnableIn':False})
        self.step(e);self.assertTrue(e.memory.read('MathEnabled'))

    def test_direct_result_write_holds_disabled_and_next_enabled_replaces(self):
        e=self.checked();self.step(e);self.settings(e,BlockEnable=False,**{'PowerState.Dest':99});self.step(e);self.assertEqual(e.memory.read('Power'),99)
        self.settings(e,BlockEnable=True);self.step(e);self.assertEqual(e.memory.read('Power'),8)

    def test_prescan_and_run_retain_all_new_enables_and_results(self):
        def saved(root):
            for obj in root.findall('./Controller/Tags/Tag/Data/Structure'):
                obj.find('DataValueMember[@Name="EnableOut"]').set('Value','1');obj.find('DataValueMember[@Name="Dest"]').set('Value','99')
        e=self.checked(saved)
        for _,tag,_ in BLOCKS:self.assertEqual(e.memory.read(tag+'.Dest'),99);self.assertTrue(e.memory.read(tag+'.EnableOut'))
        self.step(e);before=copy.deepcopy(e.memory.values);e.enter_run();self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})

    def test_late_ladder_fault_and_corrected_retry(self):
        e=self.checked();self.step(e);self.settings(e,RootInput=-25,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,FaultDivisor=1);self.step(e);self.assertEqual(e.memory.read('Root'),5)

    def test_profile_record_and_wrong_pin_types_remain_blocked(self):
        for kind in ('profile','version','record','wiretype','function','alias'):
            def mutate(root):
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='version':root.find('Controller').set('MajorRev','34')
                elif kind=='record':self.sheet(root).find('Block[@Type="XPY"]').set('Operand','RootState')
                elif kind=='wiretype':self.sheet(root).find('IRef[@ID="1"]').set('Operand','CallCount')
                elif kind=='function':self.sheet(root).find('Block').tag='Function'
                else:self.sheet(root).find('Block[@Type="SQR"]').set('Type','SQRT')
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_single_record_rll_st_overloads_remain_blocked(self):
        for language in ('RLL','ST'):
            for name,tag,_ in BLOCKS:
                def call(root):
                    routine=root.find('.//Routine[@Name="MainRoutine"]')
                    if language=='ST':logic(routine,[name+'('+tag+');'])
                    else:routine.find('RLLContent/Rung/Text').text=name+'('+tag+');'
                with self.subTest(language=language,name=name):self.assertTrue(self.engine(call).blockers)

    def test_periodic_and_harness_execution(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        for e in (self.checked(periodic),self.checked(mode='routine',defer=True)):self.step(e);self.assertEqual(e.memory.read('Power'),8)

    def test_budget_failure_rolls_back(self):
        e=self.checked();e.instruction_limit=25;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_keeps_results_and_instruction_inventory(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);before=self.snapshot(e);texts=['JSR(AdvancedMath,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertTrue(all(candidate.project.instruction_counts[n]==1 for n,_,_ in BLOCKS));self.step(candidate);self.assertEqual(candidate.memory.read('Power'),8)

    def test_report_counts_and_shared_math_contract(self):
        p=self.checked().report()['function_blocks'];self.assertEqual(len(p['instructions']),63)
        self.assertEqual(len(p['blocks']['math']['instructions']),19);self.assertIn('Absolute value',p['blocks']['math']['square_root']);self.assertIn('radians',p['blocks']['math']['transcendental'])
        self.assertFalse(p['native_runtime_parity']);self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(104,29))


if __name__=='__main__':unittest.main()
