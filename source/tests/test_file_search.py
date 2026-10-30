"""FSC match/resume, scan distribution, unknown values and rollback."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_array_statistics as fixtures
from logixlab.model import ModelError


class FileSearchTests(unittest.TestCase):
    setUp=fixtures.ArrayStatisticsTests.setUp
    engine=fixtures.ArrayStatisticsTests.engine
    checked=fixtures.ArrayStatisticsTests.checked

    def test_all_finds_first_match_and_inhibit_holds_position(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming);']);e.memory.write('Incoming',5);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),2)
        self.assertTrue(e.memory.read('Ctl.FD'));self.assertTrue(e.memory.read('Ctl.IN'))
        self.assertFalse(e.memory.read('Ctl.DN'));self.assertTrue(e.memory.read('Ctl.EN'))
        e.memory.write('Incoming',1);e.step();self.assertEqual(e.memory.read('Ctl.POS'),2)

    def test_clearing_in_resumes_after_matching_element_and_marks_last_match_done(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming);']);e.memory.write('Incoming',5);e.step()
        e.memory.write('Ctl.IN',False);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.DN'))
        self.assertTrue(e.memory.read('Ctl.FD'));self.assertTrue(e.memory.read('Ctl.IN'))

    def test_exhaustion_retains_last_compared_cursor_without_reading_guard(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);']);e.memory.values['queue'][4]=None
        e.memory.write('Incoming',100);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.DN'))
        self.assertFalse(e.memory.read('Ctl.FD'));self.assertFalse(e.memory.read('Ctl.IN'))

    def test_false_after_done_resets_enable_done_cursor_but_retains_found(self):
        e=self.checked(['XIC(StartPB)FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming);'])
        e.memory.write('Incoming',8);e.memory.write('StartPB',True);e.step()
        e.memory.write('StartPB',False);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.DN'))
        e.memory.write('Ctl.IN',False);e.step()
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','POS')],[False,False,0])
        self.assertTrue(e.memory.read('Ctl.FD'))

    def test_numeric_mode_continues_after_rung_goes_false_and_clears_next_false_scan(self):
        e=self.checked(['XIC(StartPB)FSC(Ctl,?,?,2,Queue[Ctl.POS]>Incoming);'])
        e.memory.write('Incoming',100);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.EN'));self.assertFalse(e.memory.read('Ctl.DN'))
        e.memory.write('StartPB',False);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EN'))
        e.step();self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertFalse(e.memory.read('Ctl.DN'))
        e.step();self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertFalse(e.memory.read('Ctl.EN'))

    def test_numeric_one_advances_on_each_scan_without_new_edges(self):
        e=self.checked(['FSC(Ctl,?,?,1,Queue[Ctl.POS]>Incoming);']);e.memory.write('Incoming',100)
        for position in range(4):
            e.step();self.assertEqual(e.memory.read('Ctl.POS'),position)
            self.assertEqual(e.memory.read('Ctl.DN'),position==3)
        e.step();self.assertEqual(e.memory.read('Ctl.POS'),3)

    def test_numeric_match_during_false_scan_sets_found_and_inhibits(self):
        e=self.checked(['XIC(StartPB)FSC(Ctl,?,?,2,Queue[Ctl.POS]>=Incoming);'])
        e.memory.write('Incoming',7);e.memory.write('StartPB',True);e.step()
        e.memory.write('StartPB',False);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.FD'))
        self.assertTrue(e.memory.read('Ctl.IN'));self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EN'))

    def test_rung_output_tracks_input_power_rather_than_match_result(self):
        e=self.checked(['XIC(StartPB)FSC(Ctl,?,?,2,Queue[Ctl.POS]>=Incoming)OTE(RunLatch);'])
        e.memory.write('Incoming',7);e.memory.write('StartPB',True);e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertFalse(e.memory.read('Ctl.FD'))
        e.memory.write('StartPB',False);e.step()
        self.assertFalse(e.memory.read('RunLatch'));self.assertTrue(e.memory.read('Ctl.FD'))

    def test_large_numeric_mode_clamps_to_remaining_length(self):
        e=self.checked(['FSC(Ctl,?,?,2147483647,Queue[Ctl.POS]>Incoming);']);e.memory.write('Incoming',100);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_zero_length_completes_without_evaluating_expression(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);'],length=0)
        e.memory.values['queue'][0]=None;e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertTrue(e.memory.read('Ctl.DN'))
        self.assertFalse(e.memory.read('Ctl.FD'))

    def test_saved_initial_position_and_enabled_resume(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming);'],position=1)
        e.memory.write('Incoming',3);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming);'],position=1)
        e.memory.write('Ctl.EN',True);e.memory.write('Incoming',3);e.step();self.assertEqual(e.memory.read('Ctl.POS'),2)

    def test_prescan_does_not_reset_saved_state(self):
        def flags(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Ctl"]/Data/Structure')
            for name in ('EN','DN','ER','IN','FD','EU'):obj.find(f'DataValueMember[@Name="{name}"]').set('Value','1')
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);'],position=2,mutate=flags)
        self.assertTrue(all(e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','IN','FD','EU')))
        self.assertEqual(e.memory.read('Ctl.POS'),2)

    def test_error_and_inhibit_flags_leave_state_unchanged_even_on_false(self):
        for flag in ('ER','IN'):
            e=self.checked(['AFI()FSC(Ctl,?,?,2,Queue[Ctl.POS]>Incoming);'])
            e.memory.write('Ctl.'+flag,True);e.memory.write('Ctl.EN',True);before=copy.deepcopy(e.memory.read('Ctl'))
            e.memory.values['queue'][0]=None;e.step();self.assertEqual(e.memory.read('Ctl'),before)

    def test_numeric_and_boolean_expression_types(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming&&BitIn);'],dtype=dtype,queue=(2,4,6,8,99))
            e.memory.write('Incoming',5);e.step();self.assertEqual(e.memory.read('Ctl.POS'),2)
        e=self.checked(['FSC(Ctl,?,?,ALL,BitIn);']);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_string_array_comparisons_and_case_sensitivity(self):
        from test_string_operations import string_data
        def strings(root):
            tags=root.find('./Controller/Tags')
            tag=E.SubElement(tags,'Tag',Name='Codes',TagType='Base',DataType='STRING',Dimensions='4')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='STRING',Dimensions='4')
            for i,value in enumerate(('RED','BLUE','GREEN','GUARD')):string_data(E.SubElement(array,'Element',Index=f'[{i}]'),value)
            tag=E.SubElement(tags,'Tag',Name='Needle',TagType='Base',DataType='STRING');string_data(E.SubElement(tag,'Data',Format='Decorated'),'BLUE')
        e=self.checked(['FSC(Ctl,?,?,ALL,Codes[Ctl.POS]=Needle);'],length=3,mutate=strings)
        e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.FD'))
        e.memory.write('Ctl.IN',False);e.memory.write_string('Needle','green');e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),2);self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.FD'))

    def test_alias_control_and_matching_constant_array(self):
        def alias(root):
            tags=root.find('./Controller/Tags');E.SubElement(tags,'Tag',Name='AliasCtl',TagType='Alias',DataType='CONTROL',AliasFor='Ctl')
            tags.find('Tag[@Name="Queue"]').set('Constant','true')
        e=self.checked(['FSC(AliasCtl,?,?,ALL,Queue[AliasCtl.POS]>=Incoming);'],mutate=alias)
        e.memory.write('Incoming',5);e.step();self.assertEqual(e.memory.read('Ctl.POS'),2)

    def test_unknown_data_is_deferred_until_actually_compared(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming);'])
        e.memory.values['queue'][2]=None;e.memory.write('Incoming',1);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('Ctl.IN',False);e.memory.write('Incoming',100);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_structural_validation_accepts_saved_end_and_restores_memory_mode(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);'],position=4)
        self.assertFalse(e.memory.structural);e.memory.values['queue'][4]=None;e.step()
        self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.structural)

    def test_each_comparison_consumes_budget_and_failure_rolls_back(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);']);e.memory.write('Incoming',100)
        e.instruction_limit=3;before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))

    def test_bounds_arithmetic_and_late_faults_roll_back_all_control_and_data(self):
        for expression in ('Queue[Ctl.POS+3]>Incoming','Queue[Ctl.POS]/0.0>Incoming'):
            e=self.checked([f'FSC(Ctl,?,?,ALL,{expression});']);e.memory.write('Incoming',1000)
            before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertFalse(e.memory.structural)
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming);','DIV(1,0,SpeedCommand);'])
        e.memory.write('Incoming',5);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_negative_excessive_and_unknown_length_or_position_fail_transactionally(self):
        for length,position in ((-1,0),(4,-1),(4,5),(4097,0)):
            e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);'],length=length,position=position)
            before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before)
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);']);e.memory.values['ctl']['LEN']=None
        with self.assertRaises(ModelError):e.step()

    def test_unsupported_modes_types_expressions_and_operands_block(self):
        for mode in ('INC','0','-1','1.5','Incoming','2147483648','TRUE'):
            self.assertTrue(self.engine([f'FSC(Ctl,?,?,{mode},Queue[Ctl.POS]>Incoming);']).blockers,mode)
        for text in ('FSC(Ctl,4,0,ALL,Queue[Ctl.POS]>Incoming);','FSC(Ctl,?,?,ALL);',
                     'FSC(Ctl,?,?,ALL,Queue[Ctl.POS]+Incoming);','FSC(Ctl,?,?,ALL,FRD(Incoming)>0);'):
            self.assertTrue(self.engine([text]).blockers,text)
        self.assertTrue(self.engine(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);'],dtype='LINT').blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Ctl"]').set('Constant','true')
        self.assertTrue(self.engine(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);'],mutate=constant).blockers)

    def test_st_calls_and_other_controller_profiles_remain_blocked(self):
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='FSC(Ctl,ALL,Queue[Ctl.POS]>Incoming);'
        self.assertTrue(self.engine([],mutate=st).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);'],mutate=old).blockers)

    def test_report_exposes_modes_and_native_cursor_gap(self):
        e=self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming);']);report=e.report()['file_search']
        self.assertEqual(report['modes'],['ALL','positive DINT immediate'])
        self.assertFalse(report['native_cursor_parity']);self.assertFalse(report['native_fault_classification'])


    def test_bundled_stats_lab_all_and_numeric_search_examples(self):
        from pathlib import Path
        from logixlab.model import Project
        from logixlab.runtime import Engine
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/StatsLab.L5X'))
        self.assertEqual(e.blockers,[]);e.memory.write('Search',True);e.memory.write('BatchSearch',True);e.step()
        self.assertEqual(e.memory.read('SearchControl.POS'),2);self.assertTrue(e.memory.read('SearchControl.IN'))
        self.assertEqual(e.memory.read('BatchControl.POS'),1);self.assertFalse(e.memory.read('BatchControl.DN'))
        e.memory.write('SearchControl.IN',False);e.memory.write('BatchSearch',False);e.step()
        self.assertEqual(e.memory.read('SearchControl.POS'),3);self.assertTrue(e.memory.read('SearchControl.DN'))
        self.assertTrue(e.memory.read('BatchControl.DN'));self.assertFalse(e.memory.read('BatchControl.EN'))


if __name__=='__main__':unittest.main()
