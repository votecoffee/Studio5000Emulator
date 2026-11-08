"""Alias/indirect sequencer starts retain row semantics and array boundaries."""
import copy
import unittest
from xml.etree import ElementTree as E
import test_control_operations as fixtures
from logixlab.model import ModelError


class SequencerReferenceTests(unittest.TestCase):
    setUp=fixtures.ControlOperationTests.setUp
    engine=fixtures.ControlOperationTests.engine
    checked=fixtures.ControlOperationTests.checked

    @staticmethod
    def tags(root):
        tags=root.find('./Controller/Tags')
        tag=E.SubElement(tags,'Tag',Name='Index',DataType='DINT',TagType='Base')
        E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='1')
        E.SubElement(tags,'Tag',Name='View',TagType='Alias',DataType='DINT',AliasFor='Queue[1]')
        E.SubElement(tags,'Tag',Name='ViewAgain',TagType='Alias',DataType='DINT',AliasFor='View')
        E.SubElement(tags,'Tag',Name='Cursor',TagType='Alias',DataType='DINT',AliasFor='Ctl.POS')

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def test_alias_chain_sqo_startup_edge_and_guard_rows(self):
        e=self.checked(['XIC(StartPB)SQO(ViewAgain,255,Outgoing,Ctl,?,?);'],length=2,queue=(101,0,17,34,999),mutate=self.tags)
        e.memory.write('StartPB',True);e.step();self.assertEqual((e.memory.read('Outgoing'),e.memory.read('Ctl.POS')),(0,0))
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
        self.assertEqual((e.memory.read('Outgoing'),e.memory.read('Ctl.POS')),(17,1));self.assertEqual(e.memory.read('Queue[4]'),999)

    def test_sql_alias_writes_only_selected_window(self):
        e=self.checked(['XIC(StartPB)SQL(ViewAgain,Incoming,Ctl,?,?);'],length=2,queue=(101,0,0,0,999),mutate=self.tags)
        e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue'),[101,0,11,0,999])
        e.memory.write('Incoming',22);e.step();self.assertEqual(e.memory.read('Queue'),[101,0,22,0,999])

    def test_held_sqo_resamples_live_start_without_advancing_pos(self):
        e=self.checked(['SQO(Queue[Index],-1,Outgoing,Ctl,?,?);'],length=2,position=1,queue=(101,0,17,34,999),mutate=self.tags)
        e.step();self.assertEqual(e.memory.read('Outgoing'),17)
        e.memory.write('Index',0);e.step();self.assertEqual((e.memory.read('Outgoing'),e.memory.read('Ctl.POS')),(0,1))

    def test_held_sql_resamples_live_start_and_retains_previous_rows(self):
        e=self.checked(['SQL(Queue[Index],Incoming,Ctl,?,?);'],length=2,position=1,queue=(101,0,0,0,999),mutate=self.tags)
        e.step();e.memory.write('Index',0);e.memory.write('Incoming',22);e.step()
        self.assertEqual(e.memory.read('Queue'),[101,22,11,0,999]);self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_sqi_indirect_start_compares_current_row(self):
        e=self.checked(['SQI(Queue[Index],255,Incoming,Ctl,?,?)OTE(RunLatch);'],length=2,position=1,queue=(101,0,11,22,999),mutate=self.tags)
        e.step();self.assertTrue(e.memory.read('RunLatch'));e.memory.write('Index',0);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_false_calls_do_not_consume_unknown_or_invalid_start(self):
        for op in ('SQO(Queue[Index],-1,Outgoing,Ctl,?,?)','SQI(Queue[Index],-1,Incoming,Ctl,?,?)','SQL(Queue[Index],Incoming,Ctl,?,?)'):
            for bad in (None,999,-1):
                e=self.checked(['XIC(StartPB)'+op+';'],length=2,mutate=self.tags);e.memory.values['index']=bad;e.step()
                self.assertEqual(e.scan_count,1)

    def test_unknown_and_out_of_bounds_live_starts_roll_back(self):
        for bad in (None,999,-1):
            e=self.checked(['SQO(Queue[Index],-1,Outgoing,Ctl,?,?);'],length=2,mutate=self.tags)
            e.memory.values['index']=bad;before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_invalid_control_does_not_consume_start(self):
        for op in ('SQO(Queue[Index],-1,Outgoing,Ctl,?,?)','SQI(Queue[Index],-1,Incoming,Ctl,?,?)','SQL(Queue[Index],Incoming,Ctl,?,?)'):
            e=self.checked([op+';'],length=0,mutate=self.tags);e.memory.values['index']=None;e.step();self.assertTrue(e.memory.read('Ctl.ER'))

    def test_zero_mask_skips_data_but_still_requires_valid_start(self):
        e=self.checked(['SQO(Queue[Index],0,Outgoing,Ctl,?,?);'],length=2,mutate=self.tags)
        e.memory.values['queue'][1]=None;e.memory.values['outgoing']=None;e.step();self.assertIsNone(e.memory.values['outgoing'])
        e.memory.values['index']=None
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()

    def test_valid_start_out_of_bounds_row_sets_sqi_and_sqo_error(self):
        for op in ('SQO(Queue[Index],-1,Outgoing,Ctl,?,?)','SQI(Queue[Index],-1,Incoming,Ctl,?,?)'):
            e=self.checked([op+';'],length=3,position=3,mutate=self.tags)
            e.step()
            self.assertTrue(e.memory.read('Ctl.ER'))
            self.assertEqual(e.memory.read('Outgoing'),99)

    def test_sql_can_teach_a_valid_row_with_a_short_configured_window(self):
        e=self.checked(['SQL(ViewAgain,Incoming,Ctl,?,?);'],length=4,position=0,
                       queue=(101,0,0,999),mutate=self.tags)
        e.step()
        self.assertEqual(e.memory.read('Queue'),[101,11,0,999])
        self.assertEqual(e.memory.read('Ctl.POS'),0)
        self.assertFalse(e.memory.read('Ctl.ER'))

    def test_direct_alias_and_hidden_cursor_subscripts_are_blocked(self):
        for ref in ('Queue[Ctl.POS]','Queue[Cursor+1]','View'):
            def cursor(root):
                self.tags(root)
                if ref=='View':root.find('./Controller/Tags/Tag[@Name="View"]').set('AliasFor','Queue[Ctl.POS]')
            with self.subTest(ref=ref):
                e=self.engine(['SQO('+ref+',-1,Outgoing,Ctl,?,?);'],length=2,mutate=cursor)
                self.assertTrue(any('CONTROL.POS' in b for b in e.blockers))

    def test_nested_index_expression_cannot_hide_control_pos(self):
        def nested(root):
            self.tags(root);tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Indices',DataType='DINT',TagType='Base',Dimensions='2')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]',Value='0')
        self.assertTrue(self.engine(['SQO(Queue[Indices[Ctl.POS]],-1,Outgoing,Ctl,?,?);'],length=2,mutate=nested).blockers)

    def test_read_only_alias_source_supported_sql_write_rejected(self):
        def constant(root):self.tags(root);root.find('./Controller/Tags/Tag[@Name="Queue"]').set('Constant','true')
        e=self.checked(['SQO(View,-1,Outgoing,Ctl,?,?);'],length=2,queue=(101,7,0,0),mutate=constant);e.step();self.assertEqual(e.memory.read('Outgoing'),7)
        self.assertTrue(self.engine(['SQL(View,Incoming,Ctl,?,?);'],length=2,mutate=constant).blockers)

    def test_scalar_and_bit_table_starts_remain_blocked(self):
        for ref in ('Incoming','Incoming.0'):
            self.assertTrue(self.engine(['SQO('+ref+',-1,Outgoing,Ctl,?,?);'],length=2,mutate=self.tags).blockers)

    def test_late_fault_restores_relocated_sql_row_and_control(self):
        e=self.checked(['SQL(Queue[Index],Incoming,Ctl,?,?);','DIV(1,0,Outgoing);'],length=2,queue=(101,0,0,0,999),mutate=self.tags);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_resource_cap_precedes_live_index_consumption(self):
        e=self.checked(['SQL(Queue[Index],Incoming,Ctl,?,?);'],length=4096,mutate=self.tags);e.memory.values['index']=None
        with self.assertRaisesRegex(ModelError,'4096-element'):e.step()

    def test_index_expression_alias_offset_and_program_scope(self):
        def scoped(root):
            self.tags(root);tags=root.find('./Controller/Programs/Program/Tags')
            root.find('./Controller/Tags/Tag[@Name="View"]').set('AliasFor','Queue')
            tag=E.SubElement(tags,'Tag',Name='Offset',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='1')
        e=self.checked(['SQO(View[Index-1+Offset],-1,Outgoing,Ctl,?,?);'],length=2,queue=(101,7,11,22,999),mutate=scoped)
        e.step();self.assertEqual(e.memory.read('Outgoing'),7)

    @staticmethod
    def scoped_aliases(root):
        SequencerReferenceTests.tags(root);tags=root.find('./Controller/Tags');program=root.find('./Controller/Programs/Program/Tags')
        tags.find('Tag[@Name="View"]').set('AliasFor','Queue')
        for parent,name,value in ((tags,'Offset',0),(program,'Offset',1),(program,'Index',2),(program,'Bit',3)):
            tag=E.SubElement(parent,'Tag',Name=name,DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        E.SubElement(program,'Tag',Name='Selected',TagType='Alias',DataType='DINT',AliasFor='Queue[Index]')
        E.SubElement(tags,'Tag',Name='WordView',TagType='Alias',DataType='DINT',AliasFor='Outgoing')

    def test_shared_alias_resolver_mov_uses_program_index_namespace(self):
        e=self.checked(['MOV(View[Offset],Outgoing);'],length=2,queue=(101,7,11,22,999),mutate=self.scoped_aliases)
        e.step();self.assertEqual(e.memory.read('Outgoing'),7)

    def test_shared_alias_resolver_write_and_chain_use_callers_index(self):
        e=self.checked(['NOP();'],length=2,mutate=self.scoped_aliases)
        e.memory.write('ViewAgain[Offset]',77,'MainProgram');self.assertEqual(e.memory.read('Queue[1]'),77)
        e.memory.write('ViewAgain[Offset]',88);self.assertEqual(e.memory.read('Queue[0]'),88)

    def test_aliasfor_own_index_keeps_declaration_scope(self):
        e=self.checked(['NOP();'],length=2,queue=(101,7,11,22),mutate=self.scoped_aliases)
        self.assertEqual(e.memory.read('Program:MainProgram.Selected'),11)
        e.memory.write('Program:MainProgram.Index',3);self.assertEqual(e.memory.read('Program:MainProgram.Selected'),22)

    def test_packed_bit_suffix_uses_callers_namespace(self):
        e=self.checked(['NOP();'],length=2,mutate=self.scoped_aliases);e.memory.write('Outgoing',0)
        e.memory.write('WordView.[Bit]',True,'MainProgram');self.assertEqual(e.memory.read('Outgoing'),8)

    def test_unknown_alias_suffix_index_stays_unknown_and_can_be_retried(self):
        e=self.checked(['MOV(View[Offset],Outgoing);'],length=2,queue=(101,7,11,22),mutate=self.scoped_aliases)
        e.memory.values['program:mainprogram.offset']=None;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Program:MainProgram.Offset',2);e.step();self.assertEqual(e.memory.read('Outgoing'),11)


if __name__=='__main__':unittest.main()
