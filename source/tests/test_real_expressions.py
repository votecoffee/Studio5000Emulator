"""Scoped float32 wide/typed ladder ASTs, file progress and overflow recovery."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import INT_BITS, ModelError, Project
from logixlab.real_math import real
from logixlab.runtime import Engine


class RealExpressionTests(unittest.TestCase):
    engine=fixtures.RadixExpressionTests.engine
    snapshot=staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault=fixtures.RadixExpressionTests.fault

    def test_wide_sources_real_tags_and_all_numeric_destinations(self):
        for source,dest in itertools.product(INT_BITS,(*INT_BITS,'REAL','LREAL')):
            e=self.engine(['CPT(Dest,Source+Mask);'],types=(source,'REAL',dest),values=(3,.5,0))
            e.step();self.assertEqual(e.memory.read('Dest'),3.5 if dest in ('REAL','LREAL') else 4,(source,dest))
            self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),(3,.5))

    def test_three_bases_four_word_types_and_float32_intermediates(self):
        for base,suffix in itertools.product((2,8,16),('','L','U','UL')):
            e=self.engine([f'CPT(Dest,{base}#1{suffix}+0.5);'],dtype='REAL');e.step();self.assertEqual(e.memory.read('Dest'),1.5)
        for text,want in [('16#FFFFFFFF+0.5',-.5),('(16777217U+1U)-16777216U',0.0),
                ('18446744073709551615UL MOD 3UL',1.0),('16#FFFFFFFFL',4294967296.0),
                ('ABS(16#8000000000000000L)',float(1<<63)),('SQR(16#1000001U)',4096.0)]:
            e=self.engine([f'CPT(Dest,{text});'],dtype='REAL');e.step();self.assertEqual(e.memory.read('Dest'),want,text)

    def test_functions_aliases_unary_and_bounded_powers(self):
        for text,want in [('LN(1UL)',0.0),('LOG(100U)',2.0),('SQRT(9L)',3.0),('TRN(3UL/2U)',1.0),
                ('TRUNC(3L/2UL)',1.0),('DEG(0UL)',0.0),('RAD(0U)',0.0),('SIN(0L)',0.0),
                ('COS(0UL)',1.0),('TAN(0U)',0.0),('ASN(0UL)',0.0),('ACS(1L)',0.0),
                ('ATN(0U)',0.0),('16#4UL**0.5',2.0),('-16#FFFFFFFF',1.0)]:
            e=self.engine([f'CPT(Dest,{text});'],dtype='REAL');e.step();self.assertEqual(e.memory.read('Dest'),want,text)

    def test_lreal_priority_and_exact_integer_only_forms_remain(self):
        e=self.engine(['CPT(Dest,16777217U-16777216.0L);'],dtype='REAL');e.step();self.assertEqual(e.memory.read('Dest'),1.0)
        e=self.engine(['CPT(Dest,18446744073709551615UL/3UL);'],dtype='ULINT');e.step();self.assertEqual(e.memory.read('Dest'),6148914691236517205)
        e=self.engine(['CPT(Dest,(16777217U+1U)-16777216U);'],dtype='UDINT');e.step();self.assertEqual(e.memory.read('Dest'),2)

    def test_cmp_numeric_relations_bool_composition_and_required_sides(self):
        e=self.engine(['CMP((Source+0.5=7.5)&&!StartPB)OTE(RunLatch);'],dtype='ULINT');e.step();self.assertTrue(e.memory.read('RunLatch'))
        for text in ('(Source>0.0)||(1UL/0.0>0)','(Source<0.0)&&(1UL/0.0>0)'):
            e=self.engine([f'CMP({text})OTE(RunLatch);'],dtype='ULINT');self.fault(e,'zero')
        e=self.engine(['CMP(StartPB&&(Source+1UL>0.0))OTE(RunLatch);'],dtype='REAL');e.memory.values['source']=None;self.fault(e,'Unknown')

    def test_generic_st_index_and_unsupported_operations_remain_separate(self):
        for create in (Expression,Condition,lambda text:Expression(text,subscript=True)):
            with self.assertRaises(ModelError):create('16#1UL')
        for text in ('16#1UL AND 1UL','FRD(1UL)+0.5','TOD(1L)+0.5','-1UL+0.5','1UL**1025'):
            e=self.engine([f'AFI()CPT(Dest,{text});'],dtype='REAL',checked=False)
            if '**' in text:
                self.assertEqual(e.blockers,[]);e.step();e=self.engine([f'CPT(Dest,{text});'],dtype='REAL');self.fault(e,'exponent')
            else:self.assertTrue(e.blockers,text)

    def test_structural_ranges_permissions_shapes_and_controller_gates(self):
        for text in ('9223372036854775808L+0.5','16#100000000U+0.5','1UL+1e39','Dest+StartPB+0.5'):
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'],dtype='REAL',checked=False).blockers,text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()CPT(Dest,1UL+0.5);'],dtype='REAL',mutate=constant,checked=False).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,1UL+0.5);'],dtype='REAL',mutate=lambda root:root.find('Controller').set(key,value),checked=False).blockers)

    def test_fal_all_numeric_and_incremental_typed_calculations(self):
        for mode in ('ALL','1','INC'):
            e=self.engine([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],Queue[Ctl.POS]+1UL);'],file=True,dtype='REAL')
            e.memory.write('StartPB',True);e.step()
            if mode=='1':
                e.memory.write('StartPB',False)
                for _ in range(3):e.step()
            elif mode=='INC':
                e.step();self.assertEqual(e.memory.read('Queue'),[3.0,4.0,6.0,8.0,99.0])
                for _ in range(3):e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertEqual(e.memory.read('Queue'),[3.0,5.0,7.0,9.0,99.0],mode);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_fsc_all_numeric_and_incremental_typed_float_searches(self):
        for mode in ('ALL','1','INC'):
            e=self.engine([f'XIC(StartPB)FSC(Ctl,?,?,{mode},Queue[Ctl.POS]>4U+0.0);'],file=True,dtype='LINT');e.memory.write('StartPB',True);e.step()
            if mode=='1':e.memory.write('StartPB',False);e.step();e.step()
            elif mode=='INC':
                for _ in range(2):e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertTrue(e.memory.read('Ctl.FD'),mode);self.assertEqual(e.memory.read('Ctl.POS'),2)
            before=e.memory.read('Queue');e.step();self.assertEqual(e.memory.read('Queue'),before)

    def test_mid_file_unknown_rolls_back_prefix_and_control_then_repairs(self):
        def unknown(root):
            array=root.find('./Controller/Tags/Tag[@Name="Queue"]/Data/Array');array.remove(array.find('Element[@Index="[1]"]'))
        e=self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+1UL);'],file=True,dtype='REAL',mutate=unknown)
        self.fault(e,'Unknown');e.memory.write('Queue[1]',4);e.step();self.assertEqual(e.memory.read('Queue'),[3.0,5.0,7.0,9.0,99.0])

    def test_fal_real_overflow_preserves_prefix_and_retries_failing_cell(self):
        e=self.engine(['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]*2U);'],file=True,dtype='REAL',length=3,queue=(2,3e38,6,8,99))
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue')[0],4.0);self.assertTrue(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step();self.assertEqual(e.memory.read('Queue'),[4.0,6.0,12.0,8.0,99.0]);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_integer_fal_result_overflow_is_atomic_and_not_real_er(self):
        e=self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming+0.0);'],file=True,dtype='ULINT')
        e.memory.write('Incoming',(1<<64)-1);self.fault(e,'overflow');self.assertFalse(e.memory.read('Ctl.ER'))
        e.memory.write('Incoming',1);e.step();self.assertEqual(e.memory.read('Queue'),[1,1,1,1,99])

    def test_warm_aoi_file_bindings_and_false_numeric_continuation_rollback(self):
        import test_aoi_files as aois
        h=aois.AOIFileTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text=text.text.replace('Input[Calc.POS]*Gain+Bias','Input[Calc.POS]+Bias+1UL+0.5').replace('Input[LocalCalc.POS]+Bias','Input[LocalCalc.POS]+Bias+1UL+0.5').replace('Input[Find.POS]>=Threshold','Input[Find.POS]>=1UL+0.5')
        e=h.checked(fields,kind='1');e.memory.write('Transform',True);e.memory.write('Search',True);e.step()
        self.assertEqual(e.memory.read('OutputA')[0],4);self.assertEqual(e.memory.read('DriverA.Scratch')[0],4);self.assertTrue(e.memory.read('FindA.FD'))
        e.memory.write('Transform',False);e.memory.write('Search',False);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('OutputA')[:2],[4,6])

    def test_public_example_precision_late_fault_and_report(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('MixedRealEnabled',True);e.memory.write('MixedRealIndex',1);e.step()
        for name,value in {'Result':16777216.0,'Difference':0.0,'DoubleDifference':1.0,'Signed':-.5,'Root':4096.0,'Integer':1,'Selected':[101.0,.5,999.0],'Match':True}.items():self.assertEqual(e.memory.read('MixedReal'+name),value,name)
        e.memory.write('MixedRealReal',1.5);e.memory.write('MixedRealLateDivisor',0);self.fault(e,'zero');e.memory.write('MixedRealLateDivisor',1);e.step();self.assertEqual(e.memory.read('MixedRealSelected[1]'),1.5)
        row=e.report()['real_expression_execution'];self.assertEqual(row['consumers'],['CPT','CMP','FAL','FSC']);self.assertFalse(row['native_runtime_parity'])


if __name__=='__main__':unittest.main()
