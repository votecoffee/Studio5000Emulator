"""Incremental FAL/FSC edges, hidden progress and transaction boundaries."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_array_statistics as fixtures
from logixlab.control_operations import FLAGS
from logixlab.model import ModelError


class IncrementalFileTests(unittest.TestCase):
    setUp=fixtures.ArrayStatisticsTests.setUp
    engine=fixtures.ArrayStatisticsTests.engine
    checked=fixtures.ArrayStatisticsTests.checked

    @staticmethod
    def call(kind,control='Ctl'):
        expression=f'Queue[{control}.POS]>Incoming' if kind=='FSC' else f'Queue[{control}.POS],Incoming'
        return f'{kind}({control},?,?,INC,{expression});'

    def test_arithmetic_requires_a_new_enable_edge_for_each_element(self):
        e=self.checked(['XIC(StartPB)'+self.call('FAL')]);e.memory.write('StartPB',True)
        for index in range(4):
            e.memory.write('Incoming',20+index);e.step()
            self.assertEqual(e.memory.read('Queue'),list(range(20,21+index))+[2,4,6,8][index+1:]+[999])
            self.assertEqual(e.memory.read('Ctl.POS'),index);self.assertEqual(e.memory.read('Ctl.DN'),index==3)
            e.memory.write('Incoming',100);e.step();self.assertEqual(e.memory.read('Queue['+str(index)+']'),20+index)
            e.memory.write('StartPB',False);e.step()
            if index<3:self.assertEqual(e.memory.read('Ctl.POS'),index);self.assertFalse(e.memory.read('Ctl.EN'))
            e.memory.write('StartPB',True)
        self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertFalse(e.memory.read('Ctl.DN'));self.assertEqual(e._file_incremental,set())
        e.step();self.assertEqual(e.memory.read('Queue[0]'),100)

    def test_search_no_match_advances_one_comparison_per_edge_and_finishes(self):
        e=self.checked(['XIC(StartPB)'+self.call('FSC')]);e.memory.write('Incoming',100)
        for index in range(4):
            e.memory.write('StartPB',True);e.step();e.step()
            self.assertEqual(e.memory.read('Ctl.POS'),index);self.assertEqual(e.memory.read('Ctl.DN'),index==3)
            self.assertFalse(e.memory.read('Ctl.FD'));e.memory.write('StartPB',False);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertEqual(e._file_incremental,set())

    def test_numeric_one_and_inc_are_different_for_both_instructions(self):
        for kind in ('FAL','FSC'):
            with self.subTest(kind=kind):
                inc=self.checked([self.call(kind)]);numeric=self.checked([self.call(kind).replace(',INC,',',1,')])
                inc.step();inc.step();numeric.step();numeric.step()
                self.assertEqual((inc.memory.read('Ctl.POS'),numeric.memory.read('Ctl.POS')),(0,1))

    def test_match_inhibits_until_cleared_and_requires_an_observed_false_edge(self):
        e=self.checked(['XIC(StartPB)'+self.call('FSC')]);e.memory.write('Incoming',1);e.memory.write('StartPB',True);e.step()
        self.assertTrue(e.memory.read('Ctl.IN'));self.assertTrue(e.memory.read('Ctl.FD'))
        e.memory.write('StartPB',False);e.step();self.assertTrue(e.memory.read('Ctl.EN'))
        e.memory.write('Ctl.IN',False);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('StartPB',False);e.step();self.assertFalse(e.memory.read('Ctl.EN'))
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.IN'))

    def test_last_element_match_retains_found_until_completed_false_cleanup(self):
        e=self.checked(['XIC(StartPB)'+self.call('FSC')]);e.memory.write('Incoming',7)
        for _ in range(3):
            e.memory.write('StartPB',True);e.step();e.memory.write('StartPB',False);e.step()
        e.memory.write('StartPB',True);e.step()
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('POS','DN','FD','IN')],[3,True,True,True])
        e.memory.write('StartPB',False);e.step();self.assertEqual(e.memory.read('Ctl.POS'),3)
        e.memory.write('Ctl.IN',False);e.step()
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('POS','EN','DN','FD')],[0,False,False,True])
        self.assertEqual(e._file_incremental,set());e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertFalse(e.memory.read('Ctl.FD'))

    def test_error_inhibits_false_edge_and_retains_progress_until_rearmed(self):
        for kind in ('FAL','FSC'):
            e=self.checked(['XIC(StartPB)'+self.call(kind)]);e.memory.write('StartPB',True);e.step()
            e.memory.write('Ctl.ER',True);e.memory.write('StartPB',False);e.step();self.assertTrue(e.memory.read('Ctl.EN'))
            e.memory.write('Ctl.ER',False);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)
            e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_held_true_and_false_calls_do_not_consume_unknown_expression_values(self):
        for kind in ('FAL','FSC'):
            e=self.checked(['XIC(StartPB)'+self.call(kind)]);e.memory.write('StartPB',True);e.step()
            e.memory.values['incoming']=None;e.step();e.memory.write('StartPB',False);e.step()
            self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertFalse(e.memory.read('Ctl.EN'))
            e.memory.write('StartPB',True);before=copy.deepcopy(e.memory.values);progress=set(e._file_incremental)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,progress)
            e.memory.write('Incoming',10);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_zero_length_completes_without_reading_expression_data(self):
        for kind in ('FAL','FSC'):
            e=self.checked([self.call(kind)],length=0);e.memory.values['incoming']=None;e.step()
            self.assertEqual([e.memory.read('Ctl.'+n) for n in ('POS','EN','DN')],[0,True,True])

    def test_saved_active_or_nonzero_controls_block_even_on_false_rungs(self):
        for kind in ('FAL','FSC'):
            self.assertTrue(self.engine(['AFI()'+self.call(kind)],position=1).blockers)
            for flag in FLAGS:
                def saved(root):root.find(f'./Controller/Tags/Tag[@Name="Ctl"]/Data/Structure/DataValueMember[@Name="{flag}"]').set('Value','1')
                e=self.engine(['AFI()'+self.call(kind)],mutate=saved)
                self.assertTrue(e.blockers,(kind,flag));self.assertIn('saved hidden progress',str(e.blockers))

    def test_source_guards_remain_bound_to_original_initial_values_after_runtime_progress(self):
        for kind in ('FAL','FSC'):
            e=self.checked(['XIC(StartPB)'+self.call(kind)]);e.memory.write('StartPB',True);e.step()
            e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertEqual(e.project.initial['ctl']['POS'],0)

    def test_reset_clears_hidden_progress_and_keeps_length_and_array_values(self):
        for kind in ('FAL','FSC'):
            e=self.checked(['XIC(StartPB)'+self.call(kind),'XIC(RunLatch)RES(Ctl);']);e.memory.write('StartPB',True);e.step()
            before=e.memory.read('Queue')[:];e.memory.write('StartPB',False);e.memory.write('RunLatch',True);e.step()
            self.assertEqual(e._file_incremental,set());self.assertEqual(e.memory.read('Ctl.LEN'),4);self.assertEqual(e.memory.read('Queue'),before)
            e.memory.write('RunLatch',False);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_fault_after_reset_restores_hidden_progress_and_public_state(self):
        for kind in ('FAL','FSC'):
            e=self.checked(['XIC(StartPB)'+self.call(kind),'XIC(RunLatch)RES(Ctl);','XIC(BitIn)DIV(1,0,SpeedCommand);'])
            e.memory.write('BitIn',False);e.memory.write('StartPB',True);e.step()
            e.memory.write('StartPB',False);e.memory.write('RunLatch',True);e.memory.write('BitIn',True)
            before=copy.deepcopy(e.memory.values);progress=set(e._file_incremental);schedule=e.scheduler_description()
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,progress);self.assertEqual(e.scheduler_description(),schedule)
            e.memory.write('BitIn',False);e.memory.write('RunLatch',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_first_iteration_fault_and_retry_do_not_lose_position_zero(self):
        for kind in ('FAL','FSC'):
            e=self.checked([self.call(kind)]);e.memory.values['incoming']=None;before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,set())
            self.assertEqual((e.scan_count,e.time_ms),(0,0));e.memory.write('Incoming',11);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_later_instruction_fault_rolls_back_new_progress_and_scheduler(self):
        for kind in ('FAL','FSC'):
            e=self.checked([self.call(kind),'DIV(1,0,SpeedCommand);']);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,set());self.assertEqual(e.scheduler_description(),schedule)

    def test_each_incremental_element_uses_the_global_instruction_budget(self):
        for kind in ('FAL','FSC'):
            e=self.checked([self.call(kind)]);e.instruction_limit=1;before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'budget'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,set())

    def test_invalid_runtime_length_and_position_roll_back_without_new_progress(self):
        for kind in ('FAL','FSC'):
            for length,position in ((-1,0),(4097,0),(4,-1),(4,5)):
                e=self.checked([self.call(kind)]);e.memory.write('Ctl.LEN',length);e.memory.write('Ctl.POS',position)
                before=copy.deepcopy(e.memory.values)
                with self.assertRaises(ModelError):e.step()
                self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,set())

    def test_control_aliases_share_one_progress_record(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='AliasCtl',TagType='Alias',DataType='CONTROL',AliasFor='Ctl')
        for kind in ('FAL','FSC'):
            e=self.checked(['XIC(StartPB)'+self.call(kind,'AliasCtl'),'XIC(StartPB)'+self.call(kind)],mutate=alias)
            e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertEqual(len(e._file_incremental),1)
            e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_selected_control_array_elements_have_independent_progress(self):
        def records(root):
            from test_control_operations import control_data
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Ctls',TagType='Base',DataType='CONTROL',Dimensions='2')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='CONTROL',Dimensions='2')
            for i in range(2):control_data(E.SubElement(array,'Element',Index=f'[{i}]'),4)
        e=self.checked(['XIC(StartPB)'+self.call('FAL','Ctls[0]'),'XIC(RunLatch)'+self.call('FSC','Ctls[1]')],mutate=records)
        e.memory.write('StartPB',True);e.step();self.assertEqual(len(e._file_incremental),1)
        e.memory.write('StartPB',False);e.memory.write('RunLatch',True);e.step();self.assertEqual(len(e._file_incremental),2)
        e.memory.write('StartPB',True);e.step();self.assertEqual([e.memory.read(f'Ctls[{i}].POS') for i in range(2)],[1,0])

    def test_run_entry_and_prescan_preview_preserve_progress(self):
        for kind in ('FAL','FSC'):
            e=self.checked(['XIC(StartPB)'+self.call(kind)]);e.memory.write('StartPB',True);e.step();before=copy.deepcopy(e.memory.values);progress=set(e._file_incremental)
            e._apply_prescan(preview=True);self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,progress)
            e.enter_run();e.step();self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertEqual(e._file_incremental,progress)
            e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_real_routine_replacement_copies_progress_without_mutating_active_engine(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        for kind in ('FAL','FSC'):
            text='XIC(StartPB)'+self.call(kind);e=self.checked([text]);e.memory.write('StartPB',True);e.step()
            source=decode(container(E.tostring(xml_source(text=text),encoding='utf-8')))
            candidate,_=prepare(e,source,(text,),'MainProgram',0)
            self.assertEqual(candidate._file_incremental,e._file_incremental);self.assertIsNot(candidate._file_incremental,e._file_incremental)
            candidate.memory.write('StartPB',False);candidate.step();candidate.memory.write('StartPB',True);candidate.step()
            self.assertEqual(candidate.memory.read('Ctl.POS'),1);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_unrelated_public_flags_are_not_used_as_internal_progress(self):
        for kind in ('FAL','FSC'):
            e=self.checked([self.call(kind)])
            for name in ('EU','EM','UL'):e.memory.write('Ctl.'+name,True)
            e.step();self.assertTrue(all(e.memory.read('Ctl.'+name) for name in ('EU','EM','UL')))
            self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_existing_numeric_expression_types_are_supported_in_incremental_mode(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            for kind in ('FAL','FSC'):
                e=self.checked(['XIC(StartPB)'+self.call(kind)],dtype=dtype,queue=(2,4,6,8,99))
                e.memory.write('StartPB',True);e.step()
                e.memory.write('StartPB',False);e.step();e.memory.write('Incoming',3);e.memory.write('StartPB',True);e.step()
                self.assertEqual(e.memory.read('Ctl.POS'),1)
                if kind=='FAL':self.assertEqual(e.memory.read('Queue'),[11,3,6,8,99])
                else:self.assertTrue(e.memory.read('Ctl.FD'));self.assertTrue(e.memory.read('Ctl.IN'))

    def test_scalar_arithmetic_accumulates_from_live_data_once_per_edge(self):
        e=self.checked(['XIC(StartPB)FAL(Ctl,?,?,INC,Outgoing,Outgoing+Queue[Ctl.POS]);']);e.memory.write('Outgoing',0)
        for total in (2,6,12,20):
            e.memory.write('StartPB',True);e.step();e.step();self.assertEqual(e.memory.read('Outgoing'),total)
            e.memory.write('StartPB',False);e.step()
        self.assertEqual(e.memory.read('Queue'),[2,4,6,8,999])

    def test_skipped_jsr_does_not_rearm_the_instruction(self):
        def sub(root):
            routines=root.find('./Controller/Programs/Program/Routines')
            content=E.SubElement(E.SubElement(routines,'Routine',Name='Sub',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='XIC(StartPB)'+self.call('FAL')
        e=self.checked(['XIC(RunLatch)JSR(Sub,0);'],mutate=sub)
        e.memory.write('RunLatch',True);e.memory.write('StartPB',True);e.step()
        e.memory.write('RunLatch',False);e.memory.write('StartPB',False);e.step()
        e.memory.write('RunLatch',True);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_later_periodic_release_fault_rolls_back_earlier_incremental_work(self):
        def tasks(root):
            task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','10')
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='Background',Type='CONTINUOUS',Class='Standard',Priority='10',InhibitTask='false')
            E.SubElement(task,'ScheduledPrograms')
        for kind in ('FAL','FSC'):
            e=self.checked([self.call(kind),'ADD(SpeedCommand,1,SpeedCommand);','EQU(SpeedCommand,2)DIV(1,0,SpeedSetpoint);'],mutate=tasks)
            e.memory.write('SpeedCommand',0);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
            with self.assertRaises(ModelError):e.step(30)
            self.assertEqual(e.memory.values,before);self.assertEqual(e._file_incremental,set());self.assertEqual(e.scheduler_description(),schedule)

    def test_report_qualifies_hidden_state_and_saved_resume_limits(self):
        e=self.checked([self.call('FAL')])
        for kind in ('file_arithmetic','file_search'):
            row=e.report()[kind];self.assertIn('INC',row['modes']);self.assertFalse(row['incremental']['native_internal_state_parity'])
            self.assertIn('Idle source CONTROL',row['incremental']['startup'])

    def test_bundled_stats_lab_incremental_controls_and_guards(self):
        from pathlib import Path
        from logixlab.model import Project
        from logixlab.runtime import Engine
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/StatsLab.L5X'));self.assertEqual(e.blockers,[])
        for index in range(3):
            for tag in ('StepTransform','StepSearch'):e.memory.write(tag,True)
            e.step();e.step();self.assertEqual(e.memory.read('StepValues')[:index+1],[5,9,13][:index+1])
            self.assertEqual(e.memory.read('StepTransformControl.POS'),index);self.assertEqual(e.memory.read('StepSearchControl.POS'),index)
            for tag in ('StepTransform','StepSearch'):e.memory.write(tag,False)
            e.step()
        self.assertTrue(e.memory.read('StepSearchControl.IN'));self.assertEqual(e.memory.read('StepValues[4]'),999)
        e.memory.write('StepSearchControl.IN',False);e.step()
        for tag in ('StepTransform','StepSearch'):e.memory.write(tag,True)
        e.step();self.assertTrue(e.memory.read('StepTransformControl.DN'));self.assertTrue(e.memory.read('StepSearchControl.DN'))
        self.assertEqual(e.memory.read('StepValues'),[5,9,13,17,999]);self.assertEqual(e.memory.read('Values'),[2,4,6,8,999])


if __name__=='__main__':unittest.main()
