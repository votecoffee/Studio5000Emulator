"""Dimension-wise file statistics, sample deviation and CONTROL transitions."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_control_operations as fixtures
from logixlab.model import ModelError


class ArrayStatisticsTests(unittest.TestCase):
    setUp=fixtures.ControlOperationTests.setUp
    checked=fixtures.ControlOperationTests.checked

    def engine(self,rungs,*,length=4,position=0,queue=(2,4,6,8,999),dtype='DINT',mutate=None):
        def extra(root):
            tags=root.find('./Controller/Tags')
            tag=E.SubElement(tags,'Tag',Name='Result',DataType='REAL',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='REAL',Value='7')
            if mutate:mutate(root)
        return fixtures.ControlOperationTests.engine(self,rungs,length=length,position=position,queue=queue,dtype=dtype,mutate=extra)

    @staticmethod
    def multidimensional(shape,values):
        def change(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Queue"]');dims=','.join(map(str,shape))
            tag.set('Dimensions',dims);array=tag.find('./Data/Array');array.clear()
            array.attrib.update(DataType=tag.get('DataType'),Dimensions=dims)
            import itertools
            for index,value in zip(itertools.product(*(range(n) for n in shape)),values,strict=True):
                E.SubElement(array,'Element',Index='['+','.join(map(str,index))+']',Value=str(value))
        return change

    def test_average_numeric_source_types_and_guard_values(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);'],dtype=dtype,queue=(2,4,6,8,99))
            e.step();self.assertEqual(e.memory.read('Result'),5.0)
            self.assertEqual(e.memory.read('Queue'),[2,4,6,8,99])
            self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','POS')],[True,True,False,4])

    def test_standard_deviation_uses_sample_n_minus_one(self):
        e=self.checked(['STD(Queue[0],0,Result,Ctl,?,?);']);e.step()
        self.assertAlmostEqual(e.memory.read('Result'),2.581988897,places=6)
        self.assertNotAlmostEqual(e.memory.read('Result'),2.236067977,places=4)
        self.assertEqual(e.memory.read('Ctl.POS'),4);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_fractional_negative_and_constant_samples(self):
        for values,expected in (((-2.5,-0.5,1.5),2.0),((9.25,9.25,9.25),0.0)):
            e=self.checked(['STD(Queue[0],0,Result,Ctl,?,?);'],dtype='REAL',length=3,queue=values)
            e.step();self.assertEqual(e.memory.read('Result'),expected)

    def test_offset_preserves_unselected_prefix_and_suffix(self):
        e=self.checked(['AVE(Queue[1],0,Result,Ctl,?,?);'],length=3,queue=(111,2,4,6,999))
        e.step();self.assertEqual(e.memory.read('Result'),4.0)
        self.assertEqual(e.memory.read('Queue'),[111,2,4,6,999])

    def test_two_dimensional_rows_and_columns_do_not_flatten(self):
        change=self.multidimensional((2,3),(2,4,6,8,10,12))
        for source,dimension,length,expected in (('Queue[0,1]',0,2,7.0),('Queue[1,0]',1,3,10.0)):
            e=self.checked([f'AVE({source},{dimension},Result,Ctl,?,?);'],length=length,mutate=change)
            e.step();self.assertEqual(e.memory.read('Result'),expected)
        e=self.checked(['AVE(Queue[0,2],1,Result,Ctl,?,?);'],length=2,mutate=change)
        with self.assertRaisesRegex(ModelError,'dimension/member'):e.step()

    def test_three_dimensional_axis_selection(self):
        change=self.multidimensional((2,2,3),range(12))
        for source,dimension,length,expected in (('Queue[0,1,1]',0,2,7.0),
                ('Queue[1,0,2]',1,2,9.5),('Queue[1,1,0]',2,3,10.0)):
            e=self.checked([f'AVE({source},{dimension},Result,Ctl,?,?);'],length=length,mutate=change)
            e.step();self.assertEqual(e.memory.read('Result'),expected)
        e=self.checked(['STD(Queue[1,1,0],2,Result,Ctl,?,?);'],length=3,mutate=change)
        e.step();self.assertEqual(e.memory.read('Result'),1.0)

    def test_held_true_does_not_recalculate_and_false_rearms(self):
        for name in ('AVE','STD'):
            e=self.checked([f'XIC(StartPB){name}(Queue[0],0,Result,Ctl,?,?);'])
            e.memory.write('StartPB',True);e.step();first=e.memory.read('Result')
            e.memory.write('Queue[0]',14);e.step();self.assertEqual(e.memory.read('Result'),first)
            e.memory.write('StartPB',False);e.step()
            self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','POS')],[False,False,False,0])
            e.memory.write('StartPB',True);e.step();self.assertNotEqual(e.memory.read('Result'),first)

    def test_average_false_rung_only_resets_completed_nonerror_state(self):
        e=self.checked(['XIC(StartPB)AVE(Queue[0],0,Result,Ctl,?,?);'])
        for dn,er,reset in ((False,False,False),(False,True,False),(True,True,False),(True,False,True)):
            for tag,value in dict(EN=True,DN=dn,ER=er,POS=2,EU=True).items():e.memory.write('Ctl.'+tag,value)
            e.step()
            self.assertEqual(e.memory.read('Ctl.POS'),0 if reset else 2)
            self.assertEqual(e.memory.read('Ctl.EN'),not reset);self.assertTrue(e.memory.read('Ctl.EU'))
            self.assertEqual(e.memory.read('Ctl.ER'),False if reset else er)

    def test_std_false_rung_clears_enable_error_done_and_position(self):
        e=self.checked(['XIC(StartPB)STD(Queue[0],0,Result,Ctl,?,?);'])
        for tag,value in dict(EN=True,DN=True,ER=True,POS=2,EU=True).items():e.memory.write('Ctl.'+tag,value)
        e.step();self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','POS')],[False,False,False,0])
        self.assertTrue(e.memory.read('Ctl.EU'))

    def test_prescan_differences_retain_saved_position_and_source_data(self):
        def flags(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Ctl"]/Data/Structure')
            for name in ('EN','DN','ER','EU','UL'):obj.find(f'DataValueMember[@Name="{name}"]').set('Value','1')
        for name in ('AVE','STD'):
            e=self.checked([f'{name}(Queue[0],0,Result,Ctl,?,?);'],position=2,mutate=flags)
            self.assertFalse(e.memory.read('Ctl.EN'));self.assertFalse(e.memory.read('Ctl.DN'))
            self.assertEqual(e.memory.read('Ctl.ER'),name=='AVE');self.assertEqual(e.memory.read('Ctl.POS'),2)
            self.assertTrue(e.memory.read('Ctl.EU'));self.assertEqual(e.memory.read('Result'),7.0)
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);'],position=2)
        self.assertFalse(any(e.memory.read('Ctl.'+n) for n in fixtures.FLAGS));self.assertEqual(e.memory.read('Ctl.POS'),2)

    def test_error_latch_inhibits_until_manually_cleared(self):
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);']);e.memory.write('Ctl.ER',True)
        e.step();self.assertEqual(e.memory.read('Result'),7.0);self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('Ctl.ER',False);e.step();self.assertEqual(e.memory.read('Result'),5.0)

    def test_unknown_source_rolls_back_but_inactive_guard_is_not_read(self):
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);']);e.memory.values['queue'][4]=None;e.step()
        self.assertEqual(e.memory.read('Result'),5.0)
        e=self.checked(['STD(Queue[0],0,Result,Ctl,?,?);']);e.memory.values['queue'][1]=None
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_success_establishes_unknown_destination_and_rung_out(self):
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?)OTE(RunLatch);'])
        e.memory.values['result']=None;e.step();self.assertEqual(e.memory.read('Result'),5.0)
        self.assertTrue(e.memory.read('RunLatch'))

    def test_invalid_lengths_positions_bounds_and_limits_roll_back(self):
        for name,length,position in (('AVE',0,0),('STD',1,0),('AVE',-1,0),('AVE',4,-1),('AVE',4,1),('STD',6,0)):
            e=self.checked([f'{name}(Queue[0],0,Result,Ctl,?,?);'],length=length,position=position)
            before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);'],length=4097,queue=(0,)*4097)
        with self.assertRaisesRegex(ModelError,'software limit'):e.step()

    def test_float32_accumulation_overflow_and_late_fault_roll_back(self):
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);'],dtype='REAL',length=2,queue=(3e38,3e38))
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);','DIV(1,0,SpeedCommand);'])
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_constant_sources_allowed_constant_results_and_controls_rejected(self):
        def source(root):root.find('./Controller/Tags/Tag[@Name="Queue"]').set('Constant','true')
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);'],mutate=source);e.step()
        self.assertEqual(e.memory.read('Result'),5.0)
        for tag in ('Ctl','Result'):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{tag}"]').set('Constant','true')
            self.assertTrue(self.engine(['STD(Queue[0],0,Result,Ctl,?,?);'],mutate=constant).blockers)

    def test_unsupported_dimensions_types_pseudo_operands_and_overlap_block(self):
        for text in ('AVE(Queue[0],1,Result,Ctl,?,?);','AVE(Queue[0],Incoming,Result,Ctl,?,?);',
            'AVE(Queue[0],TRUE,Result,Ctl,?,?);','AVE(Queue[0],0.0,Result,Ctl,?,?);',
            'AVE(Queue[0],0,Outgoing,Ctl,?,?);','AVE(Queue,0,Result,Ctl,?,?);',
            'AVE(Queue[Incoming],0,Result,Ctl,?,?);','AVE(Queue[0],0,Result,Ctl,4,0);',
            'STD(Queue[0],0,Result,Ctl,?);'):
            self.assertTrue(self.engine([text]).blockers,text)
        self.assertTrue(self.engine(['STD(Queue[0],0,Queue[1],Ctl,?,?);'],dtype='REAL').blockers)
        self.assertTrue(self.engine(['AVE(Queue[0],0,Result,Ctl,?,?);'],dtype='LINT').blockers)

    def test_primitive_udt_array_member_with_sibling_alias_result(self):
        def member(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Samples',DataType='REAL',Dimension='4')
            E.SubElement(members,'Member',Name='Mean',DataType='REAL',Dimension='0')
            tags=c.find('Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            arr=E.SubElement(obj,'ArrayMember',Name='Samples',DataType='REAL',Dimensions='4')
            for i,v in enumerate((2,4,6,8)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(v))
            E.SubElement(obj,'DataValueMember',Name='Mean',DataType='REAL',Value='0')
            E.SubElement(tags,'Tag',Name='MeanAlias',TagType='Alias',DataType='REAL',AliasFor='Packet1.Mean')
        e=self.checked(['AVE(Packet1.Samples[0],0,MeanAlias,Ctl,?,?);'],mutate=member);e.step()
        self.assertEqual(e.memory.read('Packet1.Mean'),5.0)
        e=self.checked(['AVE(Packet1.Samples[0],0,MeanAlias,Ctl,?,?);'],length=5,mutate=member)
        with self.assertRaisesRegex(ModelError,'boundary'):e.step()

    def test_st_calls_remain_unavailable(self):
        for text in ('AVE(Queue[0],0,Result,Ctl);','STD(Queue[0],0,Result,Ctl);'):
            def st(root):
                routine=root.find('./Controller/Programs/Program/Routines/Routine')
                routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
                E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=text
            self.assertTrue(self.engine([],mutate=st).blockers)

    def test_profile_and_report_expose_remaining_forms(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AVE(Queue[0],0,Result,Ctl,?,?);'],mutate=old).blockers)
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);']);report=e.report()['array_statistics']
        self.assertEqual(report['instructions'],['AVE','STD']);self.assertFalse(report['native_math_status'])
        self.assertIn('N-1',report['calculation'])


    def test_bundled_stats_lab_uses_independent_control_and_dimensions(self):
        from pathlib import Path
        from logixlab.model import Project
        from logixlab.runtime import Engine
        from logixlab.server import SAMPLES
        self.assertIn('StatsLab',SAMPLES)
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/StatsLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step();e.memory.write('Calculate',True);e.step()
        for tag,value in dict(Average=5.0,ColumnMean=7.0,RowMean=10.0,Ready=True).items():
            self.assertEqual(e.memory.read(tag),value,tag)
        self.assertAlmostEqual(e.memory.read('Deviation'),2.581988897,places=6)
        self.assertEqual(e.memory.read('Values[4]'),999)


if __name__=='__main__':unittest.main()
