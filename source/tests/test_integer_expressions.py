"""Narrow integer expression division across ST, CPT, CMP and file consumers."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
import test_array_statistics as files
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class IntegerExpressionTests(unittest.TestCase):
    setUp=fixtures.BitTransferTests.setUp

    def engine(self,body,*,st=False,types=('DINT','DINT','DINT'),values=(-7,3,13),mutate=None):
        def extra(root):
            if st:
                routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.remove(routine.find('RLLContent'));routine.set('Type','ST')
                E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=body
            if mutate:mutate(root)
        e=fixtures.BitTransferTests.engine(self,[] if st else body,types=types,values=values,mutate=extra)
        self.assertEqual(e.blockers,[]);return e

    def test_signed_dint_quotients_match_across_st_cpt_and_cmp(self):
        for a,b,expected in ((7,2,3),(-7,2,-3),(7,-2,-3),(-7,-2,3),(-2147483648,3,-715827882),(2147483647,7,306783378)):
            with self.subTest(a=a,b=b):
                for st,body in ((True,'Dest:=Source/Mask;'),(False,['CPT(Dest,Source/Mask);'])):
                    e=self.engine(body,st=st,values=(a,b,0));e.step();self.assertEqual(e.memory.read('Dest'),expected)
                e=self.engine([f'CMP(Source/Mask={expected})OTE(RunLatch);'],values=(a,b,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_modulo_retains_dividend_sign_and_quotient_identity(self):
        for a,b,remainder in ((-7,3,-1),(7,-3,1),(-7,-3,-1),(-2147483648,3,-2)):
            for st,body in ((True,'Dest:=Source MOD Mask;'),(False,['CPT(Dest,Source MOD Mask);'])):
                e=self.engine(body,st=st,values=(a,b,0));e.step();self.assertEqual(e.memory.read('Dest'),remainder)
            e=self.engine(['CMP((Source/Mask)*Mask+(Source MOD Mask)=Source)OTE(RunLatch);'],values=(a,b,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_sint_int_and_mixed_narrow_sources_use_dint_intermediates(self):
        for types in (('SINT','SINT','SINT'),('INT','INT','INT'),('DINT','DINT','DINT'),('SINT','INT','DINT')):
            for st,body in ((True,'Dest:=Source/Mask;'),(False,['CPT(Dest,Source/Mask);'])):
                e=self.engine(body,st=st,types=types);e.step();self.assertEqual(e.memory.read('Dest'),-2)

    def test_each_integer_subexpression_truncates_before_following_arithmetic(self):
        for expr,expected in (('Source/Mask*Mask',-6),('Source/(Mask*2)',-1),('(Source+Mask)/Mask',-1),('(1/2)+(1/2)',0)):
            for st,body in ((True,'Dest:='+expr+';'),(False,['CPT(Dest,'+expr+');'])):
                e=self.engine(body,st=st);e.step();self.assertEqual(e.memory.read('Dest'),expected)

    def test_full_negative_dint_literal_is_evaluated_without_positive_overflow(self):
        e=self.engine(['CPT(Dest,-2147483648/2);','CMP(-2147483648/2=-1073741824)OTE(RunLatch);']);e.step()
        self.assertEqual(e.memory.read('Dest'),-1073741824);self.assertTrue(e.memory.read('RunLatch'))

    def test_division_can_feed_integer_bitwise_operations(self):
        for st,body in ((True,'Dest:=(Source/Mask) AND 16#FF;'),(False,['CPT(Dest,(Source/Mask) AND 16#FF);'])):
            e=self.engine(body,st=st);e.step();self.assertEqual(e.memory.read('Dest'),254)

    def test_cpt_real_destination_promotes_but_st_real_destination_only_converts_result(self):
        e=self.engine(['CPT(Dest,Source/Mask);'],types=('DINT','DINT','REAL'),values=(7,2,0));e.step();self.assertEqual(e.memory.read('Dest'),3.5)
        e=self.engine('Dest:=Source/Mask;',st=True,types=('DINT','DINT','REAL'),values=(7,2,0));e.step();self.assertEqual(e.memory.read('Dest'),3.0)

    def test_explicit_real_operand_preserves_real_division_and_integer_destination_rounding(self):
        for st,body in ((True,'Dest:=(Source+0.0)/Mask;'),(False,['CPT(Dest,(Source+0.0)/Mask);'])):
            e=self.engine(body,st=st,values=(7,2,0));e.step();self.assertEqual(e.memory.read('Dest'),4)
        e=self.engine('Dest:=(Source+0.0)/Mask;',st=True,types=('DINT','DINT','REAL'),values=(7,2,0));e.step();self.assertEqual(e.memory.read('Dest'),3.5)

    def test_cmp_real_operand_or_literal_promotes_the_entire_comparison(self):
        e=self.engine(['CMP(Source/Mask>3)OTE(RunLatch);'],values=(7,2,0));e.step();self.assertFalse(e.memory.read('RunLatch'))
        e=self.engine(['CMP(Source/Mask>3.0)OTE(RunLatch);'],values=(7,2,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_zero_divisors_roll_back_prior_writes_and_scheduler(self):
        for st,body in ((True,'SpeedCommand:=99; Dest:=Source/Mask;'),
                        (False,['MOV(99,SpeedCommand);','CPT(Dest,Source/Mask);']),
                        (False,['MOV(99,SpeedCommand);','CMP(Source/Mask>0)OTE(RunLatch);'])):
            e=self.engine(body,st=st,values=(7,0,13));before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
            with self.assertRaisesRegex(ModelError,'zero'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule);self.assertEqual((e.scan_count,e.time_ms),(0,0))

    def test_false_rungs_and_skipped_st_bodies_do_not_evaluate_zero_divisors(self):
        for st,body in ((True,'IF StartPB THEN Dest:=Source/Mask; END_IF;'),
                        (False,['AFI()CPT(Dest,Source/Mask);']),
                        (False,['AFI()CMP(Source/Mask>0)OTE(RunLatch);'])):
            e=self.engine(body,st=st,values=(7,0,13));e.memory.values['source']=None;e.step();self.assertEqual(e.memory.read('Dest'),13)

    def test_eager_boolean_evaluation_does_not_hide_integer_division_faults(self):
        for st,body in ((True,'IF FALSE AND (Source/Mask>0) THEN Dest:=1; END_IF;'),
                        (False,['CMP((0=1)&&(Source/Mask>0))OTE(RunLatch);'])):
            e=self.engine(body,st=st,values=(7,0,13));before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'zero'):e.step()
            self.assertEqual(e.memory.values,before)

    def test_dint_minimum_divided_by_minus_one_faults_before_comparison_or_store(self):
        for st,body in ((True,'Dest:=Source/Mask;'),(False,['CPT(Dest,Source/Mask);']),
                        (False,['CMP(Source/Mask>0)OTE(RunLatch);'])):
            e=self.engine(body,st=st,values=(-2147483648,-1,13));before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'overflow'):e.step()
            self.assertEqual(e.memory.values,before)

    def test_narrow_destination_overflow_remains_a_transactional_fault(self):
        for st,body in ((True,'Dest:=Source/Mask;'),(False,['CPT(Dest,Source/Mask);'])):
            e=self.engine(body,st=st,types=('DINT','DINT','SINT'),values=(1000,2,13));before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'overflow'):e.step()
            self.assertEqual(e.memory.values,before)

    def test_unknown_sources_are_deferred_and_unknown_destinations_can_be_written(self):
        for st,body in ((True,'Dest:=Source/Mask;'),(False,['CPT(Dest,Source/Mask);'])):
            e=self.engine(body,st=st);e.memory.values['dest']=None;e.step();self.assertEqual(e.memory.read('Dest'),-2)
            e.memory.values['mask']=None;before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(e.memory.values,before)

    def test_integer_division_drives_st_case_and_for_bounds(self):
        source='Dest:=0; CASE Source/Mask OF -2:Dest:=11; ELSE Dest:=12; END_CASE; FOR SpeedCommand:=0 TO 6/3 DO Dest:=Dest+1; END_FOR;'
        e=self.engine(source,st=True);e.step();self.assertEqual(e.memory.read('Dest'),14);self.assertEqual(e.memory.read('SpeedCommand'),3)

    def test_array_indices_remain_restricted_and_cpt_cmp_integer_power_stays_blocked(self):
        from logixlab.expressions import Expression
        e=self.engine(['NOP();'])
        with self.assertRaisesRegex(ModelError,'index'):Expression('Source/Mask').validate(e.memory,index=True)
        from logixlab.model import Op
        for op in (Op('CPT',['Dest','Source**2']),Op('CMP',['Source**2>0'])):
            with self.assertRaisesRegex(ModelError,'power'):e.extensions.validate(op,'MainProgram')

    def file_engine(self,rungs,**kwargs):
        e=files.ArrayStatisticsTests.engine(self,rungs,queue=(-7,-4,4,7,999),**kwargs);self.assertEqual(e.blockers,[]);e.memory.write('Incoming',3);return e

    def test_fal_all_and_numeric_modes_use_integer_quotients_and_preserve_guard(self):
        e=self.file_engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]/Incoming);']);e.step()
        self.assertEqual(e.memory.read('Queue'),[-2,-1,1,2,999]);self.assertTrue(e.memory.read('Ctl.DN'))
        e=self.file_engine(['XIC(StartPB)FAL(Ctl,?,?,2,Queue[Ctl.POS],Queue[Ctl.POS]/Incoming);']);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Queue'),[-2,-1,4,7,999]);e.memory.write('StartPB',False);e.step()
        self.assertEqual(e.memory.read('Queue'),[-2,-1,1,2,999]);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_fsc_searches_using_integer_division_and_resumes_after_match(self):
        e=self.file_engine(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]/Incoming=-1);']);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.IN'))
        e.memory.write('Ctl.IN',False);e.memory.write('Incoming',0);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);e.memory.write('Incoming',3);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.FD'))

    def test_incremental_fal_fault_preserves_prior_committed_element_and_pending_edge(self):
        def denominators(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Denoms',DataType='DINT',TagType='Base',Dimensions='4')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='4')
            for i,value in enumerate((3,0,3,3)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
        e=self.file_engine(['XIC(StartPB)FAL(Ctl,?,?,INC,Queue[Ctl.POS],Queue[Ctl.POS]/Denoms[Ctl.POS]);'],mutate=denominators)
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue[0]'),-2)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);before=copy.deepcopy(e.memory.values);progress=set(e._file_incremental)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,progress)
        e.memory.write('Denoms[1]',3);e.step();self.assertEqual(e.memory.read('Queue')[:2],[-2,-1]);self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_st_aoi_bindings_use_integer_quotient_and_remainder(self):
        import test_runtime as runtime
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/AOILab.L5X').getroot()
        logic=self.root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines/Routine[@Name="Logic"]')
        logic.remove(logic.find('RLLContent'));logic.set('Type','ST')
        E.SubElement(E.SubElement(logic,'STContent'),'Line',Number='0').text='Total:=Shared/Step; Shared:=Shared MOD Step;'
        e=runtime.RuntimeTests.engine(self);self.assertEqual(e.blockers,[]);e.memory.write('SharedA',7);e.memory.write('StepA',3);e.step()
        self.assertEqual(e.memory.read('TotalA'),2);self.assertEqual(e.memory.read('SharedA'),1)

    def test_report_qualifies_real_promotion_and_native_status_limits(self):
        row=self.engine(['CPT(Dest,Source/Mask);']).report()['integer_expression_execution']
        self.assertEqual(row['intermediate_type'],'DINT');self.assertFalse(row['native_status_parity']);self.assertIn('FSC',row['consumers'])

    def test_math_lab_compares_consumers_and_recovers_from_late_st_failure(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/MathLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        for name in ('LadderQuotient','CptQuotient','StQuotient'):self.assertEqual(e.memory.read(name),-2)
        for name in ('LadderRemainder','CptRemainder','StRemainder'):self.assertEqual(e.memory.read(name),-1)
        self.assertTrue(e.memory.read('CmpMatches'));self.assertTrue(e.memory.read('IntegerMathMatches'))
        self.assertEqual(e.memory.read('StRealDestination'),-2.0)
        self.assertEqual(e.memory.read('CptRealQuotient'),e.memory.read('StRealQuotient'))
        e.memory.write('StDivisor',2);e.step();self.assertEqual(e.memory.read('StQuotient'),-3);self.assertFalse(e.memory.read('IntegerMathMatches'))
        e.memory.write('StDivisor',0);e.memory.write('Dividend',15);e.memory.write('Input',-25.0)
        before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        self.assertEqual(e.memory.read('Root'),4.0)
        e.memory.write('StDivisor',3);e.step();self.assertEqual(e.memory.read('StQuotient'),5);self.assertEqual(e.memory.read('Root'),5.0)
        self.assertTrue(e.memory.read('IntegerMathMatches'));self.assertTrue(e.memory.read('AllOK'))


if __name__=='__main__':unittest.main()
