"""DINT sequencer edge/level semantics, masks, row zero and bounded state."""
import copy
import unittest
from xml.etree import ElementTree as E

from logixlab.model import ModelError
import test_control_operations as fixtures


class SequencerTests(unittest.TestCase):
    setUp=fixtures.ControlOperationTests.setUp
    engine=fixtures.ControlOperationTests.engine
    checked=fixtures.ControlOperationTests.checked
    pulse=staticmethod(fixtures.ControlOperationTests.pulse)

    def test_sqo_prescan_uses_startup_row_then_edges_wrap_one_through_len(self):
        e=self.checked(['XIC(StartPB)SQO(Queue[0],16#FF,Outgoing,Ctl,?,?);'],length=3,queue=(0x12,0x34,0x56,0x78,999))
        e.memory.write('StartPB',True);e.memory.write('Outgoing',0x120000);e.step()
        self.assertEqual(e.memory.read('Outgoing'),0x120012);self.assertEqual(e.memory.read('Ctl.POS'),0)
        for pos,value in ((1,0x34),(2,0x56),(3,0x78),(1,0x34)):
            self.pulse(e,'StartPB');self.assertEqual(e.memory.read('Ctl.POS'),pos)
            self.assertEqual(e.memory.read('Outgoing'),0x120000|value)
            self.assertEqual(e.memory.read('Ctl.DN'),pos==3)
        self.assertEqual(e.memory.read('Queue[4]'),999)

    def test_sqo_held_true_reapplies_current_row_without_advancing(self):
        e=self.checked(['SQO(Queue[0],16#FF,Outgoing,Ctl,?,?);'],length=3,position=1,queue=(0,17,0,0))
        e.step();self.assertEqual(e.memory.read('Outgoing'),17)
        e.memory.write('Queue[1]',34);e.memory.write('Outgoing',0x120000);e.step()
        self.assertEqual(e.memory.read('Outgoing'),0x120022);self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_sql_held_true_reloads_same_row_then_advances_and_wraps(self):
        e=self.checked(['XIC(StartPB)SQL(Queue[0],Incoming,Ctl,?,?);'],length=3,queue=(123,0,0,0,999))
        e.step();e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Queue[1]'),11);self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('Incoming',22);e.step();self.assertEqual(e.memory.read('Queue[1]'),22)
        for pos,value in ((2,33),(3,44),(1,55)):
            self.pulse(e,'StartPB',value);self.assertEqual(e.memory.read('Ctl.POS'),pos)
            self.assertEqual(e.memory.read(f'Queue[{pos}]'),value)
            self.assertEqual(e.memory.read('Ctl.DN'),pos==3)
        self.assertEqual(e.memory.read('Queue[0]'),123);self.assertEqual(e.memory.read('Queue[4]'),999)

    def test_sql_prescan_does_not_modify_data_and_true_start_writes_row_zero(self):
        e=self.checked(['SQL(Queue[0],Incoming,Ctl,?,?);'],length=3,queue=(123,0,0,0))
        self.assertEqual(e.memory.read('Queue[0]'),123);self.assertTrue(e.memory.read('Ctl.EN'))
        e.step();self.assertEqual(e.memory.read('Queue[0]'),11);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_sqi_compares_current_masked_row_and_preserves_position_and_enable(self):
        e=self.checked(['SQI(Queue[0],16#FF,Incoming,Ctl,?,?)OTE(RunLatch);'],length=3,position=1,queue=(0,0x1234560b,0,0))
        e.memory.write('Ctl.EN',True);e.memory.write('Ctl.DN',True);e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Ctl.POS'),1)
        self.assertTrue(e.memory.read('Ctl.EN'));self.assertTrue(e.memory.read('Ctl.DN'))
        e.memory.write('Incoming',12);e.step();self.assertFalse(e.memory.read('RunLatch'))
        self.assertFalse(e.memory.read('Ctl.ER'))

    def test_sqi_false_rung_retains_error_and_true_clears_error(self):
        e=self.checked(['XIC(StartPB)SQI(Queue[0],-1,Incoming,Ctl,?,?)OTE(RunLatch);'],length=3)
        e.memory.write('Ctl.ER',True);e.step();self.assertTrue(e.memory.read('Ctl.ER'))
        e.memory.write('StartPB',True);e.step();self.assertFalse(e.memory.read('Ctl.ER'))

    def test_sqo_masks_preserve_other_bits_and_interpret_signed_result(self):
        for mask,expected in (('16#FF',0x120078),('16#FFFF_FFFF',-2147483528),('-1',-2147483528)):
            e=self.checked([f'SQO(Queue[0],{mask},Outgoing,Ctl,?,?);'],length=3,queue=(-2147483528,0,0,0))
            e.memory.write('Outgoing',0x120000);e.step();self.assertEqual(e.memory.read('Outgoing'),expected)

    def test_mask_tag_zero_extends_and_zero_mask_preserves_unknown_data(self):
        def small(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Mask',DataType='SINT',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='SINT',Value='-1')
        e=self.checked(['SQO(Queue[0],Mask,Outgoing,Ctl,?,?);'],length=3,queue=(0,0,0,0),mutate=small)
        e.memory.write('Outgoing',-1);e.step();self.assertEqual(e.memory.read('Outgoing'),-256)
        e=self.checked(['SQO(Queue[0],0,Outgoing,Ctl,?,?);'],length=3)
        e.memory.values['outgoing']=None;e.memory.values['queue'][0]=None;e.step()
        self.assertIsNone(e.memory.values['outgoing'])

    def test_full_mask_establishes_unknown_destination_partial_mask_requires_old_bits(self):
        for mask in ('-1','255'):
            e=self.checked([f'SQO(Queue[0],{mask},Outgoing,Ctl,?,?);'],length=3,queue=(7,0,0,0))
            e.memory.values['outgoing']=None
            if mask=='-1':e.step();self.assertEqual(e.memory.read('Outgoing'),7)
            else:
                with self.assertRaisesRegex(ModelError,'Unknown'):e.step()

    def test_invalid_lengths_positions_and_physical_table_bounds_set_errors(self):
        for instruction in ('SQO(Queue[0],-1,Outgoing,Ctl,?,?);','SQI(Queue[0],-1,Incoming,Ctl,?,?)OTE(RunLatch);'):
            for length,position in ((0,0),(-1,0),(3,-1),(3,4),(4,0)):
                e=self.checked([instruction],length=length,position=position);e.step()
                self.assertTrue(e.memory.read('Ctl.ER'))
                if instruction.startswith('SQI'):self.assertFalse(e.memory.read('RunLatch'))
        e=self.checked(['SQL(Queue[0],Incoming,Ctl,?,?);'],length=0)
        e.step();self.assertTrue(e.memory.read('Ctl.ER'));self.assertTrue(e.memory.read('Ctl.DN'))

    def test_sqo_error_clears_on_next_valid_enable_edge(self):
        e=self.checked(['XIC(StartPB)SQO(Queue[0],-1,Outgoing,Ctl,?,?);'],length=0)
        e.memory.write('StartPB',True);e.step();self.assertTrue(e.memory.read('Ctl.ER'))
        e.memory.write('Ctl.LEN',3);self.pulse(e,'StartPB')
        self.assertFalse(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_sql_physical_bounds_and_late_fault_roll_back_data_control_and_clock(self):
        e=self.checked(['SQL(Queue[0],Incoming,Ctl,?,?);'],length=4);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)
        e=self.checked(['SQL(Queue[0],Incoming,Ctl,?,?);','DIV(1,0,SpeedCommand);'],length=3)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))

    def test_selected_offset_table_preserves_guard_rows(self):
        e=self.checked(['XIC(StartPB)SQL(Queue[1],Incoming,Ctl,?,?);'],length=2,queue=(111,123,0,0,999))
        e.step();self.pulse(e,'StartPB',11);self.pulse(e,'StartPB',22)
        self.assertEqual(e.memory.read('Queue'),[111,123,11,22,999])

    def test_read_only_source_tables_supported_but_sql_constant_table_rejected(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Queue"]').set('Constant','true')
        e=self.checked(['SQO(Queue[0],-1,Outgoing,Ctl,?,?);'],length=3,queue=(123,0,0,0),mutate=constant)
        e.step();self.assertEqual(e.memory.read('Outgoing'),123)
        self.assertTrue(self.engine(['SQL(Queue[0],Incoming,Ctl,?,?);'],length=3,mutate=constant).blockers)

    def test_resource_unknown_and_unsupported_forms_remain_explicit(self):
        for instruction in ('SQO(Queue[0],-1,Outgoing,Ctl,?,?);','SQI(Queue[0],-1,Incoming,Ctl,?,?);','SQL(Queue[0],Incoming,Ctl,?,?);'):
            e=self.checked([instruction],length=4096)
            with self.assertRaisesRegex(ModelError,'software limit'):e.step()
        for instruction in ('SQO(Queue[0],TRUE,Outgoing,Ctl,?,?);','SQL(Queue[0],BitIn,Ctl,?,?);',
                            'SQI(Queue[Incoming],-1,Incoming,Ctl,?,?);','SQO(Queue[0],-1,Queue[1],Ctl,?,?);',
                            'SQO(Queue[0],-1,Outgoing,Ctl,3,0);'):
            self.assertTrue(self.engine([instruction],length=3).blockers)
        e=self.checked(['SQL(Queue[0],Incoming,Ctl,?,?);'],length=3);e.memory.values['incoming']=None
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()

    def test_v35_5580_profile_required_and_report_exposes_remaining_forms(self):
        def older(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['SQL(Queue[0],Incoming,Ctl,?,?);'],length=3,mutate=older).blockers)
        e=self.checked(['SQL(Queue[0],Incoming,Ctl,?,?);'],length=3)
        self.assertFalse(e.report()['sequencer_operations']['native_scan_parity'])

    def test_bundled_sequence_lab_supports_stack_pattern_and_teaching_forms(self):
        from pathlib import Path
        from logixlab.model import Project
        from logixlab.runtime import Engine
        from logixlab.server import SAMPLES
        self.assertIn('SequenceLab',SAMPLES)
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/SequenceLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step();e.memory.write('Advance',True);e.memory.write('Feedback',1);e.step()
        self.assertEqual(e.memory.read('Outputs'),0x120001);self.assertTrue(e.memory.read('Matches'))
        self.assertEqual(e.memory.read('SequenceControl.POS'),1)


if __name__=='__main__':unittest.main()
