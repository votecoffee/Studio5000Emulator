"""Narrow integer SQR nodes retain integer arithmetic in ladder expressions."""
import itertools
import math
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_bit_transfer as scalar
import test_file_bcd as files
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class LadderIntegerRootTests(unittest.TestCase):
    def setUp(self):
        self.scalar=scalar.BitTransferTests();self.scalar.setUp();self.addCleanup(self.scalar.doCleanups)
        self.files=files.FileBcdTests();self.files.setUp();self.addCleanup(self.files.doCleanups)

    def engine(self,expression='SQR(Source)+SQR(Source)',**options):
        e=self.scalar.engine(['CPT(Dest,'+expression+');','CMP('+expression+'=Dest)OTE(RunLatch);'],**options)
        self.assertEqual(e.blockers,[]);return e

    def test_nine_source_destination_pairs_round_each_root_before_addition(self):
        for source,dest in itertools.product(('SINT','INT','DINT'),repeat=2):
            e=self.engine(types=(source,'DINT',dest),values=(3,0,0));e.step()
            self.assertEqual(e.memory.read('Dest'),4);self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),3)

    def test_zero_sign_narrow_and_dint_boundaries(self):
        for value,want in ((0,0),(1,1),(2,1),(3,2),(6,2),(7,3),(-3,2),(-128,11),(-32768,181),(-2147483648,46341),(2147483647,46341),(16777217,4096)):
            e=self.engine('SQR(Source)',values=(value,0,0));e.step();self.assertEqual(e.memory.read('Dest'),want)

    def test_integer_division_powers_bitwise_and_bcd_compose_after_rounding(self):
        for expr,want in (('SQR(3)/3',0),('SQR(3)**2',4),('SQR(3) AND 1',0),('NOT SQR(3)',-3),('FRD(TOD(SQR(3)+10))',12),('SQR(FRD(TOD(3)))',2),('SQR(SQR(7)**2)',3),('(SQR(7)**2) MOD 4',1),('SQR(3)+SQR(3)*2',6)):
            e=self.engine(expr);e.step();self.assertEqual(e.memory.read('Dest'),want,expr)

    def test_six_relations_and_eager_boolean_composition(self):
        for expr,want in (('SQR(3)=2',True),('SQR(3)<>2',False),('SQR(3)<2',False),('SQR(3)<=2',True),('SQR(3)>2',False),('SQR(3)>=2',True),('(SQR(3)=2)&&(SQR(-7)=3)',True)):
            e=self.scalar.checked(['CMP('+expr+')OTE(RunLatch);']);e.step();self.assertEqual(e.memory.read('RunLatch'),want,expr)
        e=self.scalar.checked(['CMP((1=1)||(SQR(Source**2)>0))OTE(RunLatch);'],values=(50000,0,13));self.files.fault(e,'overflow')

    def test_real_destination_operand_literal_and_function_keep_floating_arithmetic(self):
        for expr,types,want in [('SQR(Source)+SQR(Source)',('DINT','DINT','REAL'),3.464101552963257),('SQR(Source)+SQR(Source)',('REAL','DINT','DINT'),3),('SQR(Source)+SQR(Source)+0.0',('DINT',)*3,3),('SQR(Source)+SQR(Source)+LN(1)',('DINT',)*3,3)]:
            e=self.engine(expr,types=types,values=(3,0,0));e.step();self.assertEqual(e.memory.read('Dest'),want)
        e=self.scalar.checked(['CMP(SQR(3)=2.0)OTE(RunLatch);']);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_existing_st_sqrt_alias_and_old_controller_paths_are_unchanged(self):
        import test_integer_expressions as st
        f=st.IntegerExpressionTests();f.setUp();self.addCleanup(f.doCleanups)
        e=f.engine('Dest:=SQRT(Source)+SQRT(Source);',st=True,values=(3,0,0));e.step();self.assertEqual(e.memory.read('Dest'),3)
        e=self.engine('SQRT(Source)+SQRT(Source)',values=(3,0,0));e.step();self.assertEqual(e.memory.read('Dest'),3)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        e=self.engine(values=(3,0,0),mutate=old);e.step();self.assertEqual(e.memory.read('Dest'),3)

    def test_false_prescan_and_unknown_full_destination_paths(self):
        e=self.scalar.checked(['XIC(StartPB)CPT(Dest,SQR(Source)+SQR(Source));','XIC(StartPB)CMP(SQR(Source)=2)OTE(RunLatch);'],values=(3,0,13));e.memory.values['source']=None;e.step();self.assertEqual(e.memory.read('Dest'),13)
        e.memory.write('Source',3);e.memory.values['dest']=None;e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Dest'),4);self.assertTrue(e.memory.read('RunLatch'))
        e.memory.values['source']=None;self.files.fault(e,'Unknown')

    def test_argument_intermediate_destination_and_late_faults_roll_back(self):
        for rungs,values,types,pattern in [(['CPT(Dest,SQR(Source**2));'],(50000,0,13),('DINT',)*3,'overflow'),(['CPT(Dest,SQR(Source+Mask));'],(2147483647,1,13),('DINT',)*3,'overflow'),(['CPT(Dest,SQR(Source));'],(32768,0,13),('DINT','DINT','SINT'),'overflow'),(['CPT(Dest,SQR(Source)+SQR(Source));','DIV(1,0,SpeedCommand);'],(3,0,13),('DINT',)*3,'zero')]:
            e=self.scalar.checked(rungs,values=values,types=types);self.files.fault(e,pattern)

    def test_alias_udt_indices_and_unknown_selected_destinations(self):
        e=self.files.checked(['CPT(ResultView[FRD(TOD(1))],SQR(SourceView[1])+SQR(SourceView[1]));','CMP(SQR(SourceView[1])=6)OTE(RunLatch);'],mutate=self.files.member_windows);e.step()
        self.assertEqual(e.memory.read('Window.Outputs'),[None,12,None,None,901]);self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Window.Guard'),777)

    def test_all_fal_and_fsc_round_before_composition_and_resume(self):
        e=self.files.checked(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],SQR(Queue[Ctl.POS])+SQR(Queue[Ctl.POS]));','FSC(FindCtl,?,?,ALL,SQR(Queue[FindCtl.POS])>=2);'],values=(2,3,6,7,777));e.step()
        self.assertEqual(e.memory.read('Results'),[2,4,4,6,101]);self.assertEqual(e.memory.read('FindCtl.POS'),1)
        e.memory.values['queue'][0]=None;e.step();self.assertEqual(e.memory.read('FindCtl.POS'),1)
        e.memory.write('FindCtl.IN',False);e.step();self.assertEqual(e.memory.read('FindCtl.POS'),2)
        e.memory.write('FindCtl.IN',False);e.step();self.assertEqual(e.memory.read('FindCtl.POS'),3);self.assertTrue(e.memory.read('FindCtl.DN'))

    def test_numeric_false_continuation_and_bad_argument_recovery(self):
        e=self.files.checked(['XIC(StartPB)FAL(Ctl,?,?,2,Results[Ctl.POS],SQR(Queue[Ctl.POS]**2));'],values=(-3,-2,50000,3,777));e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Results'),[3,2,None,None,101]);e.memory.write('StartPB',False);self.files.fault(e,'overflow')
        e.memory.write('Queue[2]',2);e.step();self.assertEqual(e.memory.read('Results'),[3,2,2,3,101]);self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EN'))

    def test_incremental_pending_edge_retry_and_reset(self):
        e=self.files.checked(['XIC(ResetFiles)RES(Ctl);','XIC(StartPB)FAL(Ctl,?,?,INC,Results[Ctl.POS],SQR(Queue[Ctl.POS]**2));'],values=(-3,50000,2,3,777));e.memory.write('StartPB',True);e.step();e.memory.write('Queue[0]',50000);e.step();self.assertEqual(e.memory.read('Results[0]'),3)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);self.files.fault(e,'overflow');e.memory.write('Queue[1]',-2);e.step();self.assertEqual(e.memory.read('Results')[:2],[3,2]);self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('StartPB',False);e.memory.write('ResetFiles',True);e.step();self.assertFalse(e._file_incremental);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_file_fsc_fault_restores_earlier_all_writes_and_required_unknowns(self):
        e=self.files.checked(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],SQR(Queue[Ctl.POS]));','FSC(FindCtl,?,?,ALL,(0=1)&&(SQR(Queue[FindCtl.POS]**2)>0));'],values=(3,50000,6,7,777));self.files.fault(e,'overflow')
        e.memory.write('Queue[1]',3);e.memory.values['queue'][2]=None;self.files.fault(e,'Unknown')

    def test_warm_aoi_copied_input_inout_and_local_state_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def mutate(root):queues.logic(root,['CPT(Buffer[Index],SQR(Value)+SQR(Value));','CPT(Stack[Index],SQR(Value**2));'])
        e=f.checked(mutate);e.step();self.assertEqual(e.memory.read('BufferA[1]'),6);self.assertEqual(e.memory.read('DriverA.Stack[1]'),11)
        e.memory.write('ValueA',50000);self.files.fault(e,'overflow');e.memory.write('ValueA',4);e.memory.write('FaultDivisor',0);self.files.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[1]'),4)

    @staticmethod
    def file_roots(root):
        for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
            text.text=re.sub(r'\bInput\[[^\]]+\]',lambda m:'SQR('+m[0]+'**2)',text.text)

    def test_file_aoi_all_numeric_inc_bindings_and_pending_argument_retry(self):
        import test_aoi_files as aoi
        f=aoi.AOIFileTests();f.setUp();self.addCleanup(f.doCleanups)
        for mode in ('ALL','2','INC'):
            e=f.checked(self.file_roots,kind=mode);e.step();f.pulse(e)
            if mode=='INC':
                e.memory.write('Transform',False);e.memory.write('Search',False);e.step();e.memory.write('InputA[1]',50000);e.memory.write('Transform',True);e.memory.write('Search',True);self.files.fault(e,'overflow');e.memory.write('InputA[1]',4);e.step()
                for _ in range(2):f.pulse(e)
            elif mode=='2':e.memory.write('Transform',False);e.memory.write('Search',False);e.step()
            self.assertEqual(e.memory.read('OutputA'),[5,9,13,17,901]);self.assertEqual(e.memory.read('OutputB'),[2,8,14,20,902]);self.assertEqual(e.memory.read('DriverA.Scratch'),[3,5,7,9,777]);e.memory.write('FaultDivisor',0);self.files.fault(e,'zero')

    def test_wide_operands_and_bcd_real_mixtures_remain_guarded(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT','BOOL'):
            e=self.scalar.engine(['AFI()CPT(Dest,SQR(Source));'],types=(dtype,'DINT','DINT'),values=(1,0,0));self.assertTrue(e.blockers,dtype)
        for expr in ('FRD(Source)+SQR(3.0)','TOD(SQR(Source)+0.0)'):
            self.assertTrue(self.scalar.engine(['AFI()CPT(Dest,'+expr+');']).blockers)

    def test_report_limits_integer_roots_to_qualified_ladder_forms(self):
        d=self.engine().report()['integer_expression_execution']['integer_roots'];self.assertEqual(d['functions'],['SQR']);self.assertEqual(d['types'],['SINT','INT','DINT']);self.assertEqual(d['consumers'],['CPT','CMP','FAL','FSC']);self.assertFalse(d['native_runtime_parity'])


    def test_control_lab_integer_and_real_results_search_reset_and_faults(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/ControlLab.L5X'));self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('RootResults'),[None,None,None,None,902])
        e.memory.write('RootEnabled',True);e.step();self.assertEqual(e.memory.read('RootResult'),4);self.assertEqual(e.memory.read('RootRealResult'),3.464101552963257);self.assertTrue(e.memory.read('RootMatches'));self.assertEqual(e.memory.read('RootResults'),[1,2,2,3,902]);self.assertEqual(e.memory.read('RootFind.POS'),1)
        for pos in (2,3):e.memory.write('RootFind.IN',False);e.step();self.assertEqual(e.memory.read('RootFind.POS'),pos)
        e.memory.write('RootRangeFault',True);self.files.fault(e,'overflow');e.memory.write('RootRangeFault',False)
        e.memory.write('RootInput',7);e.memory.write('RootLateDivisor',0);self.files.fault(e,'zero');self.assertEqual(e.memory.read('RootResult'),4)
        e.memory.write('RootLateDivisor',1);e.step();self.assertEqual(e.memory.read('RootResult'),6);self.assertFalse(e.memory.read('RootMatches'))
        e.memory.write('RootEnabled',False);e.memory.write('RootReset',True);e.step();self.assertEqual(e.memory.read('RootCalc.POS'),0);self.assertFalse(e.memory.read('RootFind.IN'));self.assertEqual(e.memory.read('RootResults'),[1,2,2,3,902])


if __name__=='__main__':unittest.main()
