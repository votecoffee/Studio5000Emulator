"""Exact narrow integer powers in ladder expressions and distributed files."""
import copy
import itertools
import unittest
from xml.etree import ElementTree as E

import test_integer_expressions as scalar
import test_file_bcd as files
from logixlab.expressions import Expression
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class LadderIntegerPowerTests(unittest.TestCase):
    def setUp(self):
        self.scalar=scalar.IntegerExpressionTests();self.scalar.setUp();self.addCleanup(self.scalar.doCleanups)
        self.files=files.FileBcdTests();self.files.setUp();self.addCleanup(self.files.doCleanups)

    def engine(self,expression='Source**Mask',**options):
        return self.scalar.engine(['CPT(Dest,'+expression+');','CMP('+expression+'=Dest)OTE(RunLatch);'],**options)

    def test_nine_narrow_type_pairs_use_exact_dint_intermediates(self):
        for source,exponent in itertools.product(('SINT','INT','DINT'),repeat=2):
            for dest in ('SINT','INT','DINT'):
                with self.subTest(source=source,exponent=exponent,dest=dest):
                    e=self.engine(types=(source,exponent,dest),values=(-3,3,0));e.step()
                    self.assertEqual(e.memory.read('Dest'),-27);self.assertTrue(e.memory.read('RunLatch'))

    def test_sign_zero_and_exact_dint_boundaries(self):
        for base,power,result in ((0,0,1),(0,31,0),(1,31,1),(-1,31,-1),(2,30,1073741824),(-2,31,-2147483648),(-2147483648,1,-2147483648),(46340,2,2147395600)):
            e=self.engine(values=(base,power,0));e.step();self.assertEqual(e.memory.read('Dest'),result)
            self.assertTrue(e.memory.read('RunLatch'))

    def test_precedence_left_association_and_integer_composition(self):
        for expression,result in (('2**3**2',64),('-2**2',-4),('(-2)**2',4),('2**(3**2)',512),('2**3*3',24),('(3**3/2) MOD 5',3),('(2**8) OR 1',257),('NOT (2**3)',-9),('FRD(TOD(12))**2',144),('FRD(TOD(2**3))',8)):
            e=self.engine(expression);e.step();self.assertEqual(e.memory.read('Dest'),result,expression)

    def test_invalid_exponents_intermediate_and_destination_overflow_roll_back(self):
        for values,types,pattern in (((2,-1,13),('DINT',)*3,'0..31'),((1,32,13),('DINT',)*3,'0..31'),((2,31,13),('DINT',)*3,'overflow'),((3,5,13),('DINT','DINT','SINT'),'overflow')):
            e=self.engine(values=values,types=types);self.files.fault(e,pattern)
        e=self.engine('(Source**Mask)/2',values=(2,31,13));self.files.fault(e,'overflow')
        e=self.scalar.engine(['CPT(Dest,Source**Mask);','DIV(1,0,SpeedCommand);'],values=(-3,3,13));self.files.fault(e,'zero')

    def test_false_paths_skip_unknowns_and_runtime_exponent_ranges(self):
        e=self.scalar.engine(['AFI()CPT(Dest,Source**Mask);','AFI()CMP(Source**Mask>0)OTE(RunLatch);'],values=(2,-1,13))
        e.memory.values['source']=None;e.step();self.assertEqual(e.memory.read('Dest'),13)
        self.assertFalse(e.memory.read('RunLatch'))
        e=self.engine(values=(2,3,0));e.memory.values['dest']=None;e.step();self.assertEqual(e.memory.read('Dest'),8)
        e.memory.values['mask']=None;self.files.fault(e,'Unknown')

    def test_eager_boolean_power_faults_are_not_hidden(self):
        for condition in ('(0=1)&&(Source**Mask>0)','(1=1)||(Source**Mask>0)'):
            e=self.scalar.engine(['CMP('+condition+')OTE(RunLatch);'],values=(2,-1,13));self.files.fault(e,'0..31')

    def test_real_promotion_and_st_profiles_are_unchanged(self):
        e=self.engine(values=(2,-1,0),types=('DINT','DINT','REAL'));e.step();self.assertEqual(e.memory.read('Dest'),0.5)
        e=self.scalar.engine(['CMP(Source**Mask=0.5)OTE(RunLatch);'],values=(2,-1,0));e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.scalar.engine('Dest:=Source**Mask;',st=True,values=(-3,3,0));e.step();self.assertEqual(e.memory.read('Dest'),-27)
        e=self.scalar.engine('Dest:=Source**Mask;',st=True,values=(2,-1,13));self.files.fault(e,'exponent')

    def test_wide_power_executes_while_old_profiles_and_array_indices_stay_blocked(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        import test_bit_transfer as fixture
        f=fixture.BitTransferTests();f.setUp();self.addCleanup(f.doCleanups)
        self.assertTrue(f.engine(['AFI()CPT(Dest,Source**Mask);'],mutate=old).blockers)
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            e=f.checked(['CPT(Dest,Source**Mask);'],types=(dtype,dtype,dtype),values=(2,3,0));e.step();self.assertEqual(e.memory.read('Dest'),8,dtype)
        e=self.engine()
        with self.assertRaisesRegex(ModelError,'index'):Expression('2**3').validate(e.memory,index=True)

    def test_alias_udt_and_indexed_destinations_use_selected_cells(self):
        e=self.files.engine(['CPT(ResultView[1],SourceView[1]**2);','CMP(ResultView[1]=SourceView[1]**2)OTE(RunLatch);'],mutate=self.files.member_windows)
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Window.Outputs'),[None,1089,None,None,901]);self.assertEqual(e.memory.read('Window.Guard'),777)

    def test_all_file_transform_and_search_inhibit_resume(self):
        e=self.files.engine(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],Queue[Ctl.POS]**2);','FSC(FindCtl,?,?,ALL,Queue[FindCtl.POS]**2>=8);'],values=(-3,-2,2,3,777));self.assertEqual(e.blockers,[])
        e.step();self.assertEqual(e.memory.read('Results'),[9,4,4,9,101]);self.assertEqual(e.memory.read('FindCtl.POS'),0)
        e.memory.write('Queue[0]',50000);e.step();self.assertEqual(e.memory.read('FindCtl.POS'),0)
        e.memory.write('FindCtl.IN',False);e.step();self.assertEqual(e.memory.read('FindCtl.POS'),3);self.assertTrue(e.memory.read('FindCtl.DN'))

    def test_numeric_false_continuation_and_late_element_fault_recovery(self):
        e=self.files.engine(['XIC(StartPB)FAL(Ctl,?,?,2,Results[Ctl.POS],Queue[Ctl.POS]**2);'],values=(-3,-2,50000,3,777));e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Results'),[9,4,None,None,101]);e.memory.write('StartPB',False);self.files.fault(e,'overflow')
        e.memory.write('Queue[2]',2);e.step();self.assertEqual(e.memory.read('Results'),[9,4,4,9,101]);self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EN'))

    def test_incremental_pending_edge_retries_and_reset_clears_progress(self):
        e=self.files.engine(['XIC(ResetFiles)RES(Ctl);','XIC(StartPB)FAL(Ctl,?,?,INC,Results[Ctl.POS],Queue[Ctl.POS]**2);'],values=(-3,50000,2,3,777));e.memory.write('StartPB',True);e.step()
        e.memory.write('Queue[0]',50000);e.step();self.assertEqual(e.memory.read('Results[0]'),9)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);self.files.fault(e,'overflow')
        e.memory.write('Queue[1]',-2);e.step();self.assertEqual(e.memory.read('Results')[:2],[9,4]);self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('StartPB',False);e.memory.write('ResetFiles',True);e.step();self.assertFalse(e._file_incremental);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_file_boolean_composition_and_earlier_writes_roll_back(self):
        e=self.files.engine(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],Queue[Ctl.POS]**2);','FSC(FindCtl,?,?,ALL,(Queue[FindCtl.POS]**2=Divisor)||(1=1));'],values=(-3,-2,2,3,777));e.memory.write('Divisor',9);e.step();self.assertEqual(e.memory.read('FindCtl.POS'),0)
        e=self.files.engine(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],Queue[Ctl.POS]**2);','FSC(FindCtl,?,?,ALL,(0=1)&&(2**(-1)>0));'],values=(-3,-2,2,3,777));self.files.fault(e,'0..31')

    def test_warm_aoi_copied_input_inout_and_local_arrays_roll_back(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def mutate(root):queues.logic(root,['CPT(Buffer[Index],Value**2);','CPT(Stack[Index],Value**3);'])
        e=f.engine(mutate);self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('BufferA[1]'),121);self.assertEqual(e.memory.read('DriverA.Stack[1]'),1331)
        e.memory.write('ValueA',50000);self.files.fault(e,'overflow');e.memory.write('ValueA',4);e.memory.write('FaultDivisor',0);self.files.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[1]'),16)

    def test_report_declares_bounded_exponent_and_native_limit(self):
        d=self.engine().report()['integer_expression_execution']['integer_power'];self.assertEqual(d['exponent_range'],[0,31]);self.assertEqual(d['consumers'],['CPT','CMP','FAL','FSC']);self.assertFalse(d['native_runtime_parity'])


    def test_control_lab_power_example_and_atomic_recovery(self):
        from pathlib import Path
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/ControlLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('PowerResults'),[None,None,None,None,901]);e.memory.write('PowerEnabled',True);e.step()
        self.assertEqual(e.memory.read('PowerResult'),-27);self.assertTrue(e.memory.read('PowerMatches'));self.assertEqual(e.memory.read('PowerResults'),[9,4,4,9,901]);self.assertEqual(e.memory.read('PowerFind.POS'),0)
        e.memory.write('PowerFind.IN',False);e.step();self.assertEqual(e.memory.read('PowerFind.POS'),3);self.assertTrue(e.memory.read('PowerFind.DN'))
        for tag,value,pattern in [('PowerExponent',-1,'0..31'),('PowerExponent',32,'0..31'),('PowerLateDivisor',0,'zero')]:
            e.memory.write(tag,value);self.files.fault(e,pattern);e.memory.write(tag,3 if tag=='PowerExponent' else 1)
        e.memory.write('PowerEnabled',False);e.memory.write('PowerReset',True);e.step();self.assertEqual(e.memory.read('PowerCalc.POS'),0);self.assertFalse(e.memory.read('PowerFind.IN'));self.assertEqual(e.memory.read('PowerResults'),[9,4,4,9,901])

    def test_file_aoi_all_numeric_inc_power_bindings_and_pending_retry(self):
        import re
        import test_aoi_files as aoi
        f=aoi.AOIFileTests();f.setUp();self.addCleanup(f.doCleanups)
        def mutate(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text=re.sub(r'\bInput\[[^\]]+\]',lambda m:'('+m[0]+'**2)',text.text)
        for mode in ('ALL','2','INC'):
            e=f.engine(mutate,kind=mode);self.assertEqual(e.blockers,[]);e.step();f.pulse(e)
            if mode=='INC':
                e.memory.write('Transform',False);e.memory.write('Search',False);e.step();e.memory.write('InputA[1]',50000);e.memory.write('Transform',True);e.memory.write('Search',True);self.files.fault(e,'overflow')
                e.memory.write('InputA[1]',4);e.step()
                for _ in range(2):f.pulse(e)
            elif mode=='2':e.memory.write('Transform',False);e.memory.write('Search',False);e.step()
            self.assertEqual(e.memory.read('OutputA'),[9,33,73,129,901]);self.assertEqual(e.memory.read('OutputB'),[2,26,74,146,902]);self.assertEqual(e.memory.read('DriverA.Scratch'),[5,17,37,65,777])
            e.memory.write('FaultDivisor',0);self.files.fault(e,'zero')


if __name__=='__main__':unittest.main()
