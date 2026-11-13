"""Implicit REAL math selection for bounded wide/typed ladder expressions."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import INT_BITS, ModelError, Project, coerce
from logixlab.runtime import Engine

CASES = [('LN',1,0.0),('LOG',100,2.0),('SIN',0,0.0),('COS',0,1.0),
         ('TAN',0,0.0),('ASN',1,1.5707963705062866),('ACS',0,1.5707963705062866),
         ('ATN',1,0.7853981852531433),('DEG',1,57.295780181884766),
         ('RAD',1,0.01745329238474369),('SQRT',9,3.0)]


class RealFunctionExpressionTests(unittest.TestCase):
    engine=fixtures.RadixExpressionTests.engine
    snapshot=staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault=fixtures.RadixExpressionTests.fault

    def test_all_functions_all_integer_sources_and_numeric_destinations(self):
        for name,value,want in CASES:
            for source in INT_BITS:
                e=self.engine([f'CPT(Dest,{name}(Source));'],types=(source,'DINT','LINT'),values=(value,0,0))
                e.step();self.assertEqual(e.memory.read('Dest'),round(want),(name,source))
            for dest in (*INT_BITS,'REAL'):
                e=self.engine([f'CPT(Dest,{name}({value}UL));'],dtype=dest)
                e.step();self.assertEqual(e.memory.read('Dest'),coerce(want,dest),(name,dest))

    def test_decimal_radix_declared_widths_and_whole_expression_float32(self):
        for token in ('1L','1U','1UL','16#1L','8#1U','2#1UL','16#FFFFFFFF'):
            e=self.engine([f'CPT(Dest,SIN({token}));'],dtype='DINT');e.step()
            self.assertEqual(e.memory.read('Dest'),-1 if token=='16#FFFFFFFF' else 1,token)
        e=self.engine(['CPT(Dest,(16777217U+SIN(0U))-16777216U);'],dtype='DINT');e.step()
        self.assertEqual(e.memory.read('Dest'),0)
        e=self.engine(['CPT(Dest,(16777217U+1U)-16777216U);'],dtype='UDINT');e.step()
        self.assertEqual(e.memory.read('Dest'),2)

    def test_integer_abs_root_and_lreal_selection_keep_priority(self):
        for text,want in [('ABS(-9007199254740993L)',9007199254740993),('SQR(169UL)',13)]:
            e=self.engine([f'CPT(Dest,{text});'],dtype='LINT' if 'ABS' in text else 'ULINT');e.step()
            self.assertEqual(e.memory.read('Dest'),want)
        e=self.engine(['CPT(Dest,(16777217U+SIN(0U))-16777216U);'],dtype='LREAL');e.step()
        self.assertEqual(e.memory.read('Dest'),1.0)
        for text in ('TRN(1L)','TRUNC(1L)'):
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'],checked=False).blockers)

    def test_cmp_float32_relations_and_eager_required_sides(self):
        e=self.engine(['CMP(SIN(Source)>=0)OTE(RunLatch);'],dtype='ULINT');e.memory.write('Source',4);e.step()
        self.assertFalse(e.memory.read('RunLatch'));e.memory.write('Source',1);e.step();self.assertTrue(e.memory.read('RunLatch'))
        for text in ('(SIN(1UL)>0)||(ASN(2UL)>0)','(SIN(1UL)<0)&&(ASN(2UL)>0)'):
            e=self.engine([f'CMP({text})OTE(RunLatch);']);self.fault(e,'domain')
        e=self.engine(['CMP(StartPB&&(SIN(Source)>0))OTE(RunLatch);'],dtype='ULINT')
        e.memory.values['source']=None;self.fault(e,'Unknown')

    def test_false_paths_static_guards_and_lazy_selected_destination(self):
        def selected(root):
            tags=root.find('./Controller/Tags');dest=tags.find('Tag[@Name="Dest"]');dest.set('Dimensions','3');dest.remove(dest.find('Data'))
            obj=E.SubElement(E.SubElement(dest,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3')
            E.SubElement(obj,'Element',Index='[2]',Value='903')
        e=self.engine(['XIC(StartPB)CPT(Dest[SpeedCommand],SIN(Source));'],types=('ULINT','DINT','DINT'),mutate=selected)
        e.memory.write('SpeedCommand',99);e.memory.values['source']=None;e.step()
        e.memory.write('StartPB',True);self.fault(e,'outside bounds|Unknown')
        e.memory.write('SpeedCommand',1);e.memory.write('Source',1);e.step();self.assertEqual(e.memory.read('Dest'),[None,1,903])
        for text in ('SIN(16#100000000U)','SIN(-1UL)','SIN(1UL) AND 1UL','SIN(StartPB)','FRD(1UL)+SIN(1UL)'):
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'],checked=False).blockers,text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()CPT(Dest,SIN(1UL));'],mutate=constant,checked=False).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,SIN(1UL));'],mutate=lambda root:root.find('Controller').set(key,value),checked=False).blockers)

    def test_fal_all_numeric_and_inc_function_progress(self):
        for mode in ('ALL','1','INC'):
            e=self.engine([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],SIN(Queue[Ctl.POS]));'],file=True)
            e.memory.write('StartPB',True);e.step()
            if mode=='1':
                e.memory.write('StartPB',False)
                for _ in range(3):e.step()
            elif mode=='INC':
                e.step();self.assertEqual(e.memory.read('Queue'),[1,4,6,8,99])
                for _ in range(3):e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertEqual(e.memory.read('Queue'),[1,-1,0,1,99],mode);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_fsc_all_numeric_inc_and_inhibit_resume(self):
        for mode in ('ALL','1','INC'):
            e=self.engine([f'XIC(StartPB)FSC(Ctl,?,?,{mode},SIN(Queue[Ctl.POS])<0);'],file=True,queue=(2,4,1,1,99))
            e.memory.write('StartPB',True);e.step()
            if mode=='1':e.memory.write('StartPB',False);e.step()
            elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertTrue(e.memory.read('Ctl.FD'),mode);self.assertEqual(e.memory.read('Ctl.POS'),1)
            before=e.memory.read('Queue');e.step();self.assertEqual(e.memory.read('Queue'),before)
            e.memory.write('Ctl.IN',False)
            if mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True)
            e.step()
            if mode=='1':e.step()
            elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertTrue(e.memory.read('Ctl.DN'),mode)

    def test_domain_unknown_and_integer_range_failures_rollback_then_repair(self):
        e=self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],ASN(Queue[Ctl.POS]));'],file=True,queue=(0,2,1,0,99))
        self.fault(e,'domain');e.memory.write('Queue[1]',1);e.step();self.assertEqual(e.memory.read('Queue'),[0,2,2,0,99])
        e=self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],SIN(Queue[Ctl.POS]));'],file=True)
        e.memory.values['queue'][1]=None;self.fault(e,'Unknown');e.memory.write('Queue[1]',4);e.step();self.assertEqual(e.memory.read('Queue'),[1,-1,0,1,99])
        e=self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],SIN(Queue[Ctl.POS]));'],file=True,dtype='ULINT')
        self.fault(e,'overflow');self.assertFalse(e.memory.read('Ctl.ER'))
        e.memory.write('Queue[1]',1);e.memory.write('Queue[2]',1);e.memory.write('Queue[3]',1);e.step();self.assertEqual(e.memory.read('Queue'),[1,1,1,1,99])

    def test_numeric_false_continuation_fault_preserves_committed_prefix(self):
        e=self.engine(['XIC(StartPB)FAL(Ctl,?,?,1,Queue[Ctl.POS],ASN(Incoming));'],file=True)
        e.memory.write('StartPB',True);e.memory.write('Incoming',1);e.step();e.memory.write('StartPB',False);e.memory.write('Incoming',2)
        self.fault(e,'domain');self.assertEqual(e.memory.read('Queue')[0],2);self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('Incoming',0);e.step();self.assertEqual(e.memory.read('Queue')[:2],[2,0])

    def test_generic_st_index_parsers_and_warm_aoi_bindings(self):
        for create in (Expression,Condition,lambda text:Expression(text,subscript=True)):
            with self.assertRaises(ModelError):create('SIN(1UL)')
        import test_aoi_files as aois
        h=aois.AOIFileTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text=text.text.replace('Input[Calc.POS]*Gain+Bias','SIN(1UL)+Input[Calc.POS]').replace('Input[LocalCalc.POS]+Bias','SIN(1UL)+Input[LocalCalc.POS]').replace('Input[Find.POS]>=Threshold','SIN(1UL)>0')
        e=h.checked(fields,kind='1');e.memory.write('Transform',True);e.memory.write('Search',True);e.step()
        self.assertEqual(e.memory.read('OutputA')[0],3);self.assertTrue(e.memory.read('FindA.FD'))
        e.memory.write('Transform',False);e.memory.write('Search',False);e.step();self.assertEqual(e.memory.read('OutputA')[1],5)

    def test_public_example_live_inputs_fault_repair_false_gate_and_report(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('FunctionRealEnabled',True);self.fault(e,'outside bounds');e.memory.write('FunctionRealIndex',1);e.step()
        for name,value in {'Sin':0,'Cos':1,'Tan':2,'Ln':0,'Log':1,'Degrees':57,'Radians':3,'Asin':2,'Acos':2,'Atan':1,'RootAlias':3,'Selected':[101,0,999],'Match':True}.items():self.assertEqual(e.memory.read('FunctionReal'+name),value,name)
        e.memory.write('FunctionRealAngle',4);e.memory.write('FunctionRealLateDivisor',0);self.fault(e,'zero')
        e.memory.write('FunctionRealLateDivisor',1);e.step();self.assertEqual(e.memory.read('FunctionRealSelected[1]'),-1);self.assertFalse(e.memory.read('FunctionRealMatch'))
        e.memory.write('FunctionRealDomainEnabled',True);self.fault(e,'domain');e.memory.write('FunctionRealDomainSource',1);e.step();self.assertEqual(e.memory.read('FunctionRealDomainResult'),2)
        e.memory.write('FunctionRealEnabled',False);e.memory.values['functionrealangle']=None;e.step();self.assertEqual(e.memory.read('FunctionRealSin'),-1)
        row=e.report()['real_expression_execution'];self.assertEqual(row['implicit_real_functions'],sorted(n for n,_,_ in CASES));self.assertFalse(row['native_runtime_parity'])


if __name__=='__main__':unittest.main()
