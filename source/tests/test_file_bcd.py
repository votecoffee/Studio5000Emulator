"""BCD expressions in ladder FAL/FSC with existing scan-distribution modes."""
import copy
import itertools
import re
import unittest
from xml.etree import ElementTree as E

import test_file_arithmetic as fixtures
import test_control_operations as controls
from logixlab.expressions import Expression
from logixlab.conditions import Condition
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class FileBcdTests(unittest.TestCase):
    setUp=fixtures.FileArithmeticTests.setUp
    checked=fixtures.FileArithmeticTests.checked

    def engine(self,rungs=None,*,source_type='DINT',dest_type='DINT',values=(18,33,26,99,777),mutate=None,**options):
        def fields(root):
            tags=root.find('./Controller/Tags')
            tag=E.SubElement(tags,'Tag',Name='Results',DataType=dest_type,Dimensions='5',TagType='Base')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dest_type,Dimensions='5');E.SubElement(arr,'Element',Index='[4]',Value='101')
            tag=E.SubElement(tags,'Tag',Name='FindCtl',DataType='CONTROL',TagType='Base');controls.control_data(E.SubElement(tag,'Data',Format='Decorated'),options.get('length',4))
            for name,dtype,value in [('Threshold','DINT',21),('Divisor','DINT',1),('LateDivisor','DINT',1),('ResetFiles','BOOL',0)]:
                tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))
            if mutate:mutate(root)
        return fixtures.FileArithmeticTests.engine(self,rungs or ['FAL(Ctl,?,?,ALL,Results[Ctl.POS],FRD(Queue[Ctl.POS]));'],dtype=source_type,queue=values,mutate=fields,**options)

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved if e.project.aois else None,e.addons.instances,e._file_incremental,
                              e.scan_count,e.time_ms,e.trace,e.scheduler_description(),e._program_timings,e._task_measurements,e._task_scan_timings))

    def fault(self,e,text):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,text):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertFalse(e.memory.structural)

    def pulse(self,e,**writes):
        e.memory.write('StartPB',False);e.step()
        for name,value in writes.items():e.memory.write(name,value)
        e.memory.write('StartPB',True);e.step()

    def test_all_nine_narrow_tag_pairings_and_both_fal_conversions(self):
        for source,dest in itertools.product(('SINT','INT','DINT'),repeat=2):
            for function,values,want in [('FRD',(18,33,26,99,77),(12,21,20,63)),('TOD',(12,21,20,9,77),(18,33,32,9))]:
                e=self.checked([f'FAL(Ctl,?,?,ALL,Results[Ctl.POS],{function}(Queue[Ctl.POS]));'],source_type=source,dest_type=dest,values=values);e.step()
                self.assertEqual(e.memory.read('Results'),[*want,101]);self.assertEqual(e.memory.read('Queue'),list(values));self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),3)

    def test_nested_patterns_arithmetic_and_selected_unknown_results(self):
        for expression,want in [('FRD(-1)',166666665),('TOD(99999999)',-1717986919),('FRD(TOD(99999999))',99999999),('(FRD(-1) AND 255)',169),('FRD(TOD(Queue[Ctl.POS]+1))',13)]:
            e=self.checked([f'FAL(Ctl,?,?,ALL,Results[Ctl.POS],{expression});'],values=(12,12,12,12,777));e.step();self.assertEqual(e.memory.read('Results'),[want]*4+[101])
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],FRD(Queue[Ctl.POS]));']);e.step();self.assertEqual(e.memory.read('Queue'),[12,21,20,63,777])

    def test_numeric_fal_continues_while_false_and_recovers_partial_range_fault(self):
        e=self.checked(['XIC(StartPB)FAL(Ctl,?,?,2,Results[Ctl.POS],TOD(Queue[Ctl.POS]));'],values=(12,21,20,9,777));e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Results'),[18,33,None,None,101]);self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('StartPB',False);e.memory.write('Queue[2]',-1);self.fault(e,'qualified');e.memory.write('Queue[2]',20);e.step()
        self.assertEqual(e.memory.read('Results'),[18,33,32,9,101]);self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EN'));e.step();self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertFalse(e.memory.read('Ctl.DN'))

    def test_inc_fal_held_skip_pending_edge_retry_and_reset_progress(self):
        e=self.checked(['XIC(ResetFiles)RES(Ctl);','XIC(StartPB)FAL(Ctl,?,?,INC,Results[Ctl.POS],TOD(Queue[Ctl.POS]));'],values=(12,21,20,9,777));e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Results'),[18,None,None,None,101]);e.memory.write('Queue[0]',-1);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('StartPB',False);e.step();e.memory.write('Queue[1]',-1);e.memory.write('StartPB',True);self.fault(e,'qualified');e.memory.write('Queue[1]',21);e.step()
        self.assertEqual(e.memory.read('Results'),[18,33,None,None,101]);self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertEqual(len(e._file_incremental),1)
        e.memory.write('StartPB',False);e.memory.write('ResetFiles',True);e.step();self.assertEqual(e._file_incremental,set());e.memory.write('ResetFiles',False);e.memory.write('Queue[0]',1);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Results[0]'),1);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_fsc_all_match_inhibit_resume_and_final_cleanup(self):
        e=self.checked(['XIC(StartPB)FSC(Ctl,?,?,ALL,FRD(Queue[Ctl.POS])=Threshold);']);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.FD'));self.assertTrue(e.memory.read('Ctl.IN'))
        e.memory.values['queue'][0]=e.memory.values['queue'][1]=None;e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('Threshold',63);e.memory.write('Ctl.IN',False);e.step();self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.DN'));self.assertTrue(e.memory.read('Ctl.IN'))
        e.memory.write('Ctl.IN',False);e.memory.write('StartPB',False);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertFalse(e.memory.read('Ctl.DN'));self.assertTrue(e.memory.read('Ctl.FD'))

    def test_numeric_fsc_false_continuation_requires_next_live_value(self):
        e=self.checked(['XIC(StartPB)FSC(Ctl,?,?,2,FRD(Queue[Ctl.POS])=Threshold);']);e.memory.write('Threshold',63);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('StartPB',False);e.memory.values['queue'][2]=None;self.fault(e,'Unknown');e.memory.write('Queue[2]',26);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.FD'));self.assertTrue(e.memory.read('Ctl.IN'));self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EN'))

    def test_inc_search_needs_inhibit_clear_and_observed_false_before_resuming(self):
        e=self.checked(['XIC(StartPB)FSC(Ctl,?,?,INC,FRD(Queue[Ctl.POS])=Threshold);']);e.memory.write('StartPB',True);e.step();self.assertFalse(e.memory.read('Ctl.FD'));e.memory.values['queue'][0]=None;e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)
        self.pulse(e);self.assertTrue(e.memory.read('Ctl.IN'));self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.memory.write('Ctl.IN',False);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('Threshold',63);self.pulse(e);self.assertEqual(e.memory.read('Ctl.POS'),2);self.assertFalse(e.memory.read('Ctl.IN'));self.pulse(e);self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.DN'));self.assertTrue(e.memory.read('Ctl.FD'))

    def test_false_inhibited_done_and_zero_length_calls_skip_unknown_sources(self):
        for op,mode in itertools.product(('FAL','FSC'),('ALL','2','INC')):
            call=f'FAL(Ctl,?,?,{mode},Results[Ctl.POS],FRD(Queue[Ctl.POS]));' if op=='FAL' else f'FSC(Ctl,?,?,{mode},FRD(Queue[Ctl.POS])>0);'
            e=self.checked(['XIC(StartPB)'+call]);e.memory.values['queue'][0]=None;e.enter_run();e.step();e.memory.write('StartPB',True);self.fault(e,'Unknown')
            e.memory.write('Ctl.ER',True);e.step();self.assertIsNone(e.memory.read('Queue')[0]);e.memory.write('Ctl.ER',False);e.memory.write('Ctl.DN',True);e.step();self.assertIsNone(e.memory.read('Queue')[0])
            if op=='FSC':e.memory.write('Ctl.DN',False);e.memory.write('Ctl.IN',True);e.step();self.assertIsNone(e.memory.read('Queue')[0])
            e=self.checked([call],length=0);e.memory.values['queue'][0]=None;e.step();self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Results'),[None,None,None,None,101])

    def test_partial_all_work_and_later_faults_restore_arrays_controls_and_time(self):
        for call in ('FAL(Ctl,?,?,ALL,Results[Ctl.POS],TOD(Queue[Ctl.POS]));','FSC(Ctl,?,?,ALL,FRD(TOD(Queue[Ctl.POS]))>999);'):
            e=self.checked(['MOV(99,SpeedCommand);',call],values=(12,21,-1,9,777));self.fault(e,'qualified');e.memory.write('Queue[2]',20);e.step();self.assertTrue(e.memory.read('Ctl.DN'))
        e=self.checked(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],TOD(Queue[Ctl.POS]));','DIV(1,LateDivisor,SpeedCommand);'],values=(12,21,20,9,777));e.memory.write('LateDivisor',0);self.fault(e,'zero');e.memory.write('LateDivisor',1);e.step();self.assertEqual(e.memory.read('Results'),[18,33,32,9,101])
        e=self.checked(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],TOD(Queue[Ctl.POS]));'],values=(99,1,1,1,77),dest_type='SINT');self.fault(e,'overflow')

    @staticmethod
    def aliases(root):
        tags=root.find('./Controller/Tags')
        for name,target in [('SourceView','Queue'),('ResultView','Results')]:E.SubElement(tags,'Tag',Name=name,DataType='DINT',Dimensions='5',TagType='Alias',AliasFor=target)

    def test_alias_and_function_indices_preserve_sequential_source_windows(self):
        e=self.checked(['FAL(Ctl,?,?,ALL,ResultView[Ctl.POS],FRD(SourceView[FRD(TOD(Ctl.POS))]));','FSC(FindCtl,?,?,ALL,FRD(SourceView[FindCtl.POS])=Threshold);'],mutate=self.aliases);e.step()
        self.assertEqual(e.memory.read('Results'),[12,21,20,63,101]);self.assertEqual(e.memory.read('Queue'),[18,33,26,99,777]);self.assertEqual(e.memory.read('FindCtl.POS'),1)

    @staticmethod
    def member_windows(root):
        members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='BcdWindow',Class='User'),'Members')
        for name,dimension in [('Inputs','5'),('Outputs','5'),('Guard','0')]:E.SubElement(members,'Member',Name=name,DataType='DINT',Dimension=dimension)
        tags=root.find('./Controller/Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Window',DataType='BcdWindow',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='BcdWindow')
        for name,values in [('Inputs',[(0,18),(1,33),(2,26),(3,99),(4,888)]),('Outputs',[(4,901)])]:
            arr=E.SubElement(obj,'ArrayMember',Name=name,DataType='DINT',Dimensions='5')
            for index,value in values:E.SubElement(arr,'Element',Index=f'[{index}]',Value=str(value))
        E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
        for name,target in [('SourceView','Window.Inputs'),('ResultView','Window.Outputs')]:E.SubElement(tags,'Tag',Name=name,DataType='DINT',Dimensions='5',TagType='Alias',AliasFor=target)

    def test_udt_member_windows_keep_unknown_results_and_sibling_guards(self):
        e=self.checked(['FAL(Ctl,?,?,ALL,ResultView[Ctl.POS],FRD(SourceView[Ctl.POS]));','FSC(FindCtl,?,?,ALL,FRD(SourceView[FindCtl.POS])=Threshold);'],mutate=self.member_windows);e.step()
        self.assertEqual(e.memory.read('Window.Outputs'),[12,21,20,63,901]);self.assertEqual(e.memory.read('Window.Inputs'),[18,33,26,99,888]);self.assertEqual(e.memory.read('Window.Guard'),777);self.assertEqual(e.memory.read('FindCtl.POS'),1)

    def test_fsc_both_conversion_functions_accept_all_three_narrow_sources(self):
        for source in ('SINT','INT','DINT'):
            for function,values,threshold in [('FRD',(18,33,26,99,77),21),('TOD',(12,21,20,9,77),33)]:
                e=self.checked([f'FSC(Ctl,?,?,ALL,{function}(Queue[Ctl.POS])=Threshold);'],source_type=source,values=values);e.memory.write('Threshold',threshold);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Queue'),list(values))

    def aoi(self,kind='INC'):
        import test_aoi_files as files
        f=files.AOIFileTests();f.setUp();self.addCleanup(f.doCleanups)
        def bcd(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text=re.sub(r'\bInput\[[^\]]+\]',lambda match:'FRD(TOD('+match[0]+'))',text.text)
        return f.engine(bcd,kind=kind)

    def test_aoi_all_numeric_and_incremental_modes_keep_independent_bindings(self):
        for mode in ('ALL','2','INC'):
            e=self.aoi(mode);self.assertEqual(e.blockers,[]);e.step()
            if mode=='INC':
                for _ in range(4):
                    e.memory.write('Transform',False);e.memory.write('Search',False);e.step();e.memory.write('Transform',True);e.memory.write('Search',True);e.step()
            else:
                e.memory.write('Transform',True);e.memory.write('Search',True);e.step()
                if mode=='2':e.memory.write('Transform',False);e.memory.write('Search',False);e.step()
            self.assertEqual(e.memory.read('OutputA'),[5,9,13,17,901]);self.assertEqual(e.memory.read('OutputB'),[2,8,14,20,902]);self.assertEqual(e.memory.read('DriverA.Scratch'),[3,5,7,9,777]);self.assertEqual(e.memory.read('FindA.POS'),2)

    def test_warm_aoi_pending_range_and_late_faults_restore_hidden_progress(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.step();e.memory.write('Transform',True);e.memory.write('Search',True);e.step()
        e.memory.write('Transform',False);e.memory.write('Search',False);e.step();e.memory.write('InputA[1]',-1);e.memory.write('Transform',True);e.memory.write('Search',True);self.fault(e,'qualified');self.assertEqual(e.memory.read('OutputA[0]'),5)
        e.memory.write('InputA[1]',4);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('OutputA')[:2],[5,9]);self.assertEqual(e.memory.read('CalcA.POS'),1)

    def test_fsc_eager_conditions_and_scoped_generic_st_grammar(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,(1=1)||(TOD(Queue[Ctl.POS])=0));'],values=(-1,1,1,1,77));self.fault(e,'qualified')
        e=self.checked();e.step()
        with self.assertRaisesRegex(ModelError,'Unsupported expression function'):e.extensions.expression('FRD(Queue[Ctl.POS])')
        with self.assertRaisesRegex(ModelError,'Unsupported expression function'):e.extensions.condition('FRD(Queue[Ctl.POS])>0',allow_wide=True)
        with self.assertRaisesRegex(ModelError,'Unsupported expression function'):Expression('TOD(1)')
        with self.assertRaisesRegex(ModelError,'Unsupported expression function'):Condition('TOD(1)>0')

    def test_other_types_real_functions_readonly_results_and_profiles_stay_guarded(self):
        for dtype in ('BOOL','REAL','LREAL','LINT','USINT','UINT','UDINT','ULINT'):
            for call in ('FAL(Ctl,?,?,ALL,Results[Ctl.POS],FRD(Queue[Ctl.POS]));','FSC(Ctl,?,?,ALL,TOD(Queue[Ctl.POS])>0);'):
                self.assertTrue(self.engine(['AFI()'+call],source_type=dtype,values=(1,1,1,1,1)).blockers,(dtype,call))
            self.assertTrue(self.engine(['AFI()FAL(Ctl,?,?,ALL,Results[Ctl.POS],TOD(Queue[Ctl.POS]));'],dest_type=dtype,values=(1,1,1,1,1)).blockers,dtype)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(mutate=old).blockers)

    def test_report_records_file_modes_conversions_and_native_boundaries(self):
        d=self.checked().report()['integer_expression_execution']['bcd_files'];self.assertEqual(d['instructions'],['FAL','FSC']);self.assertEqual(d['functions'],['FRD','TOD']);self.assertEqual(d['modes'],['ALL','positive DINT immediate','INC']);self.assertFalse(d['native_runtime_parity'])


if __name__=='__main__':unittest.main()
