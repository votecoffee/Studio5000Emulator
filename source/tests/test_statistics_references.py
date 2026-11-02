"""AVE/STD aliases and live source indices respect latches and dimensions."""
import copy
import unittest
from xml.etree import ElementTree as E
import test_array_statistics as fixtures
from logixlab.model import ModelError


class StatisticsReferenceTests(unittest.TestCase):
    setUp=fixtures.ArrayStatisticsTests.setUp
    engine=fixtures.ArrayStatisticsTests.engine
    checked=fixtures.ArrayStatisticsTests.checked
    multidimensional=staticmethod(fixtures.ArrayStatisticsTests.multidimensional)

    @staticmethod
    def tags(root):
        tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='Index',DataType='DINT',TagType='Base')
        E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='1')
        for name,target in (('View','Queue[1]'),('AliasChain','View'),('WholeView','Queue'),('Cursor','Ctl.POS')):
            E.SubElement(tags,'Tag',Name=name,TagType='Alias',DataType='DINT',AliasFor=target)

    def snapshot(self,e):return copy.deepcopy((e.memory.values,e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def test_selected_alias_chain_average_and_sample_deviation(self):
        for instruction,expected in (('AVE',4),('STD',2)):
            e=self.checked([f'{instruction}(AliasChain,0,Result,Ctl,?,?);'],length=3,queue=(101,2,4,6,999),mutate=self.tags)
            e.step();self.assertEqual(e.memory.read('Result'),expected);self.assertEqual(e.memory.read('Queue[4]'),999)

    def test_indirect_source_samples_current_start_only_when_rearmed(self):
        e=self.checked(['XIC(StartPB)AVE(WholeView[Index],0,Result,Ctl,?,?);'],length=3,queue=(101,2,4,6,8,999),mutate=self.tags)
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Result'),4)
        e.memory.write('Index',2);e.step();self.assertEqual(e.memory.read('Result'),4)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Result'),6)

    def test_false_calls_do_not_consume_unknown_or_bad_source_index(self):
        for instruction in ('AVE','STD'):
            for bad in (None,-1,999):
                e=self.checked([f'XIC(StartPB){instruction}(WholeView[Index],0,Result,Ctl,?,?);'],length=3,mutate=self.tags)
                e.memory.values['index']=bad;e.step();self.assertEqual(e.memory.read('Result'),7)

    def test_done_enable_and_error_latches_skip_live_source_index(self):
        for flag in ('DN','EN','ER'):
            e=self.checked(['AVE(WholeView[Index],0,Result,Ctl,?,?);'],length=3,mutate=self.tags)
            e.memory.write('Ctl.'+flag,True);e.memory.values['index']=None;e.step();self.assertEqual(e.memory.read('Result'),7)

    def test_reached_unknown_and_bad_index_fail_atomically(self):
        for bad in (None,-1,999):
            e=self.checked(['STD(WholeView[Index],0,Result,Ctl,?,?);'],length=3,mutate=self.tags);e.memory.values['index']=bad;before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_initial_unknown_index_can_wait_for_a_known_value(self):
        def missing(root):
            self.tags(root);c=root.find('Controller');dt=E.SubElement(c.find('DataTypes'),'DataType',Name='Offsets',Family='NoFamily',Class='User')
            E.SubElement(E.SubElement(dt,'Members'),'Member',Name='Index',DataType='DINT',Dimension='0')
            record=E.SubElement(c.find('Tags'),'Tag',Name='Offsets1',TagType='Base',DataType='Offsets');E.SubElement(E.SubElement(record,'Data',Format='Decorated'),'Structure',DataType='Offsets')
            tag=c.find('Tags/Tag[@Name="Index"]');tag.remove(tag.find('Data'));tag.attrib.update(TagType='Alias',AliasFor='Offsets1.Index')
        e=self.checked(['XIC(StartPB)AVE(WholeView[Index],0,Result,Ctl,?,?);'],length=3,mutate=missing)
        e.step();e.memory.write('Index',0);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Result'),4)

    def test_valid_start_short_dimension_cannot_spill_to_next_row(self):
        def matrix(root):self.tags(root);self.multidimensional((2,3),range(6))(root)
        e=self.checked(['AVE(WholeView[0,Index],1,Result,Ctl,?,?);'],length=3,mutate=matrix);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'dimension/member'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_two_dimensional_alias_column_uses_selected_axis(self):
        def matrix(root):self.tags(root);self.multidimensional((2,3),(2,4,6,8,10,12))(root)
        e=self.checked(['AVE(WholeView[0,Index],0,Result,Ctl,?,?);'],length=2,mutate=matrix);e.step();self.assertEqual(e.memory.read('Result'),7)

    def test_three_dimensional_indirect_plane_uses_selected_axis(self):
        def cube(root):self.tags(root);self.multidimensional((2,2,3),range(12))(root)
        e=self.checked(['AVE(WholeView[0,Index,2],0,Result,Ctl,?,?);'],length=2,mutate=cube);e.step();self.assertEqual(e.memory.read('Result'),8)

    def test_controller_alias_suffix_index_uses_program_namespace(self):
        def scoped(root):
            self.tags(root);tag=E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='Index',DataType='DINT',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='2')
        e=self.checked(['AVE(WholeView[Index],0,Result,Ctl,?,?);'],length=3,queue=(101,2,4,6,8,999),mutate=scoped);e.step();self.assertEqual(e.memory.read('Result'),6)

    def test_aliasfor_own_index_uses_its_declaration_scope(self):
        def scoped(root):
            self.tags(root);root.find('./Controller/Tags/Tag[@Name="View"]').set('AliasFor','Queue[Index]')
            tag=E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='Index',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='2')
        e=self.checked(['AVE(View,0,Result,Ctl,?,?);'],length=3,queue=(101,2,4,6,8,999),mutate=scoped);e.step();self.assertEqual(e.memory.read('Result'),4)

    def test_control_pos_dependencies_direct_alias_and_hidden_start_are_blocked(self):
        for ref in ('Queue[Ctl.POS]','WholeView[Cursor]','View'):
            def cursor(root):
                self.tags(root)
                if ref=='View':root.find('./Controller/Tags/Tag[@Name="View"]').set('AliasFor','Queue[Ctl.POS]')
            self.assertTrue(any('CONTROL.POS' in b for b in self.engine([f'AVE({ref},0,Result,Ctl,?,?);'],mutate=cursor).blockers))

    def test_source_alias_constant_is_supported(self):
        def constant(root):self.tags(root);root.find('./Controller/Tags/Tag[@Name="Queue"]').set('Constant','true')
        e=self.checked(['AVE(View,0,Result,Ctl,?,?);'],length=3,queue=(101,2,4,6,999),mutate=constant);e.step();self.assertEqual(e.memory.read('Result'),4)

    def test_whole_arrays_scalars_and_bits_stay_blocked(self):
        for source in ('WholeView','Index','Index.0'):
            self.assertTrue(self.engine([f'AVE({source},0,Result,Ctl,?,?);'],mutate=self.tags).blockers)

    def test_resource_limit_and_bad_lengths_precede_live_index_consumption(self):
        for length,message in ((4097,'software limit'),(0,'at least one'),(-1,'at least one')):
            e=self.checked(['AVE(WholeView[Index],0,Result,Ctl,?,?);'],length=length,mutate=self.tags);e.memory.values['index']=None
            with self.assertRaisesRegex(ModelError,message):e.step()

    def test_later_fault_restores_alias_result_control_and_clock(self):
        e=self.checked(['AVE(WholeView[Index],0,Result,Ctl,?,?);','DIV(1,0,Outgoing);'],length=3,mutate=self.tags);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_missing_guard_value_is_not_read(self):
        e=self.checked(['AVE(View,0,Result,Ctl,?,?);'],length=3,queue=(101,2,4,6,999),mutate=self.tags)
        e.memory.values['queue'][4]=None;e.step();self.assertEqual(e.memory.read('Result'),4)

    def test_dynamic_parent_overlap_is_checked_at_execution(self):
        def records(root):
            c=root.find('Controller');dt=E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User');E.SubElement(E.SubElement(dt,'Members'),'Member',Name='Samples',DataType='REAL',Dimension='2')
            tag=E.SubElement(c.find('Tags'),'Tag',Name='Packets',DataType='Packet',TagType='Base',Dimensions='2');arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='Packet',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='Packet');a=E.SubElement(obj,'ArrayMember',Name='Samples',DataType='REAL',Dimensions='2')
                for j in range(2):E.SubElement(a,'Element',Index=f'[{j}]',Value=str(j+1))
        e=self.checked(['AVE(Packets[Incoming].Samples[0],0,Packets[1].Samples[0],Ctl,?,?);'],length=2,mutate=records);e.memory.write('Incoming',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'overlap'):e.step()
        self.assertEqual(self.snapshot(e),before)


if __name__=='__main__':unittest.main()
