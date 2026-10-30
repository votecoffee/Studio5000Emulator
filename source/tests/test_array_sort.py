"""Dimension-wise SRT, exact integers and Structured Text transition effects."""
import copy
import math
import unittest
from xml.etree import ElementTree as E

import test_array_statistics as fixtures
from logixlab.model import ModelError


class ArraySortTests(unittest.TestCase):
    setUp=fixtures.ArrayStatisticsTests.setUp
    checked=fixtures.ArrayStatisticsTests.checked
    multidimensional=staticmethod(fixtures.ArrayStatisticsTests.multidimensional)

    def engine(self,rungs,*,length=4,position=0,queue=(8,2,6,4,999),dtype='DINT',mutate=None):
        return fixtures.ArrayStatisticsTests.engine(self,rungs,length=length,position=position,queue=queue,dtype=dtype,mutate=mutate)

    def st(self,text,**kwargs):
        def change(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine')
            routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=text
        return self.engine([],mutate=change,**kwargs)

    def test_numeric_types_sort_ascending_and_preserve_guard(self):
        for dtype,values,expected in (('SINT',(127,-128,0,-1,99),[-128,-1,0,127,99]),
            ('INT',(32767,-32768,0,-1,999),[-32768,-1,0,32767,999]),
            ('DINT',(8,2,6,4,999),[2,4,6,8,999]),
            ('REAL',(1.5,-2.5,0.5,1.5,999),[-2.5,0.5,1.5,1.5,999])):
            e=self.checked(['SRT(Queue[0],0,Ctl,?,?);'],dtype=dtype,queue=values);e.step()
            self.assertEqual(e.memory.read('Queue'),expected)
            self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','POS')],[True,True,False,0])

    def test_dint_sort_does_not_round_through_real(self):
        e=self.checked(['SRT(Queue[0],0,Ctl,?,?);'],queue=(2147483647,16777217,16777216,-2147483648,999))
        e.step();self.assertEqual(e.memory.read('Queue'),[-2147483648,16777216,16777217,2147483647,999])

    def test_real_signed_zero_and_duplicate_values_preserved(self):
        e=self.checked(['SRT(Queue[0],0,Ctl,?,?);'],dtype='REAL',queue=(0.0,-0.0,-1.0,1.0,999))
        e.step();values=e.memory.read('Queue')
        self.assertEqual(values,[-1.0,0.0,-0.0,1.0,999])
        self.assertEqual(math.copysign(1,values[1]),1);self.assertEqual(math.copysign(1,values[2]),-1)

    def test_selected_offset_preserves_prefix_and_suffix(self):
        e=self.checked(['SRT(Queue[1],0,Ctl,?,?);'],length=3,queue=(111,6,2,4,999))
        e.step();self.assertEqual(e.memory.read('Queue'),[111,2,4,6,999])

    def test_two_dimensional_column_and_row_selection(self):
        change=self.multidimensional((2,3),(6,10,2,12,4,8))
        e=self.checked(['SRT(Queue[0,1],0,Ctl,?,?);'],length=2,mutate=change);e.step()
        self.assertEqual(e.memory.read('Queue'),[[6,4,2],[12,10,8]])
        e=self.checked(['SRT(Queue[1,0],1,Ctl,?,?);'],length=3,mutate=change);e.step()
        self.assertEqual(e.memory.read('Queue'),[[6,10,2],[4,8,12]])

    def test_three_dimensional_selection(self):
        change=self.multidimensional((2,2,3),(6,5,4,3,2,1,12,11,10,9,8,7))
        e=self.checked(['SRT(Queue[1,1,0],2,Ctl,?,?);'],length=3,mutate=change);e.step()
        self.assertEqual(e.memory.read('Queue'),[[[6,5,4],[3,2,1]],[[12,11,10],[7,8,9]]])

    def test_ladder_held_enable_does_not_repeat_false_rearms(self):
        e=self.checked(['XIC(StartPB)SRT(Queue[0],0,Ctl,?,?);'])
        e.memory.write('StartPB',True);e.step();e.memory.write('Queue[0]',10);e.step()
        self.assertEqual(e.memory.read('Queue'),[10,4,6,8,999])
        e.memory.write('StartPB',False);e.step()
        self.assertFalse(e.memory.read('Ctl.EN'));self.assertFalse(e.memory.read('Ctl.DN'))
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue'),[4,6,8,10,999])

    def test_prescan_leaves_saved_control_and_data_unchanged(self):
        def flags(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Ctl"]/Data/Structure')
            for name in ('EN','DN','ER','EU'):obj.find(f'DataValueMember[@Name="{name}"]').set('Value','1')
        e=self.checked(['SRT(Queue[0],0,Ctl,?,?);'],position=2,mutate=flags)
        self.assertTrue(all(e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','EU')))
        self.assertEqual(e.memory.read('Ctl.POS'),2);self.assertEqual(e.memory.read('Queue'),[8,2,6,4,999])
        e.step();self.assertEqual(e.memory.read('Queue'),[8,2,6,4,999])

    def test_false_rung_retains_error_position_and_other_flags(self):
        e=self.checked(['AFI()SRT(Queue[0],0,Ctl,?,?);'],position=2)
        for name in ('EN','DN','ER','EU'):e.memory.write('Ctl.'+name,True)
        e.step();self.assertFalse(e.memory.read('Ctl.EN'));self.assertFalse(e.memory.read('Ctl.DN'))
        self.assertTrue(e.memory.read('Ctl.ER'));self.assertTrue(e.memory.read('Ctl.EU'));self.assertEqual(e.memory.read('Ctl.POS'),2)

    def test_error_inhibits_until_cleared_without_data_movement(self):
        e=self.checked(['SRT(Queue[0],0,Ctl,?,?);']);e.memory.write('Ctl.ER',True);e.step()
        self.assertEqual(e.memory.read('Queue'),[8,2,6,4,999]);self.assertFalse(e.memory.read('Ctl.DN'))
        e.memory.write('Ctl.ER',False);e.step();self.assertEqual(e.memory.read('Queue'),[2,4,6,8,999])

    def test_st_three_operand_call_repeats_without_explicit_rearm(self):
        e=self.st('SRT(Queue[0],0,Ctl);');self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('Queue[0]',10);e.step();self.assertEqual(e.memory.read('Queue'),[4,6,8,10,999])
        self.assertTrue(e.memory.read('Ctl.EN'));self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),0)
        self.assertTrue(any(t.get('language')=='ST' and t.get('detail')=='SRT' for t in e.trace))

    def test_false_st_branch_is_not_a_false_scan_of_the_instruction(self):
        e=self.st('IF StartPB THEN SRT(Queue[0],0,Ctl); END_IF;');self.assertEqual(e.blockers,[])
        e.memory.write('Ctl.EN',True);e.memory.write('Ctl.DN',True);e.step()
        self.assertTrue(e.memory.read('Ctl.EN'));self.assertTrue(e.memory.read('Ctl.DN'))
        self.assertEqual(e.memory.read('Queue'),[8,2,6,4,999])
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue'),[2,4,6,8,999])

    def test_st_for_bound_and_step_protection_covers_whole_selected_array_member(self):
        for text in ('FOR Incoming:=0 TO Queue[4] DO SRT(Queue[0],0,Ctl); END_FOR;',
                     'FOR Incoming:=0 TO 2 BY Queue[4] DO SRT(Queue[0],0,Ctl); END_FOR;'):
            e=self.st(text);self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)
        e=self.st('FOR Incoming:=0 TO Ctl.LEN DO SRT(Queue[0],0,Ctl); END_FOR;')
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Incoming'),5)
        self.assertEqual(e.memory.read('Queue'),[2,4,6,8,999])

    def test_invalid_lengths_positions_and_dimension_bounds_roll_back(self):
        for length,position in ((0,0),(-1,0),(4,-1),(4,1),(6,0)):
            e=self.checked(['SRT(Queue[0],0,Ctl,?,?);'],length=length,position=position);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))
        change=self.multidimensional((2,3),(6,10,2,12,4,8))
        e=self.checked(['SRT(Queue[0,2],1,Ctl,?,?);'],length=2,mutate=change)
        with self.assertRaisesRegex(ModelError,'boundary'):e.step()
        e=self.checked(['SRT(Queue[0],0,Ctl,?,?);'],length=4097,queue=(0,)*4097)
        with self.assertRaisesRegex(ModelError,'software limit'):e.step()

    def test_unknown_and_nonfinite_data_roll_back_and_guards_are_not_read(self):
        for value in (None,float('nan'),float('inf')):
            e=self.checked(['SRT(Queue[0],0,Ctl,?,?);'],dtype='REAL');e.memory.values['queue'][1]=value
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.read('Queue[0]'),8.0);self.assertFalse(e.memory.read('Ctl.DN'))
        e=self.checked(['SRT(Queue[0],0,Ctl,?,?);']);e.memory.values['queue'][4]=None;e.step()
        self.assertEqual(e.memory.read('Queue[0]'),2);self.assertIsNone(e.memory.values['queue'][4])

    def test_late_fault_rolls_back_rll_and_st_sorting(self):
        e=self.checked(['SRT(Queue[0],0,Ctl,?,?);','DIV(1,0,SpeedCommand);'])
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)
        e=self.st('SRT(Queue[0],0,Ctl); Result:=1.0/0.0;');self.assertEqual(e.blockers,[]);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_read_only_arrays_and_controls_rejected(self):
        for name in ('Queue','Ctl'):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
            self.assertTrue(self.engine(['SRT(Queue[0],0,Ctl,?,?);'],mutate=constant).blockers)

    def test_alias_control_and_udt_array_member(self):
        def member(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Values',DataType='DINT',Dimension='4');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            tags=c.find('Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            arr=E.SubElement(obj,'ArrayMember',Name='Values',DataType='DINT',Dimensions='4')
            for i,v in enumerate((8,2,6,4)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(v))
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='999')
            E.SubElement(tags,'Tag',Name='AliasControl',TagType='Alias',DataType='CONTROL',AliasFor='Ctl')
        e=self.checked(['SRT(Packet1.Values[0],0,AliasControl,?,?);'],mutate=member);e.step()
        self.assertEqual(e.memory.read('Packet1.Values'),[2,4,6,8]);self.assertEqual(e.memory.read('Packet1.Guard'),999)
        e=self.checked(['SRT(Packet1.Values[0],0,Ctl,?,?);'],length=5,mutate=member)
        with self.assertRaisesRegex(ModelError,'boundary'):e.step()

    def test_unqualified_types_references_dimensions_and_arities_block(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            self.assertTrue(self.engine(['SRT(Queue[0],0,Ctl,?,?);'],dtype=dtype).blockers)
        for text in ('SRT(Queue,0,Ctl,?,?);','SRT(Queue[Incoming],0,Ctl,?,?);',
                     'SRT(Queue[0],Incoming,Ctl,?,?);','SRT(Queue[0],1,Ctl,?,?);',
                     'SRT(Queue[0],0,Ctl);','SRT(Queue[0],0,Ctl,4,0);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for text in ('SRT(Queue[0],0);','SRT(Queue[0],0,Ctl,4);','SRT(Queue[0],0,Ctl,4,0);'):
            self.assertTrue(self.st(text).blockers,text)

    def test_profile_and_report_expose_native_position_gap(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['SRT(Queue[0],0,Ctl,?,?);'],mutate=old).blockers)
        e=self.checked(['SRT(Queue[0],0,Ctl,?,?);']);report=e.report()['array_sort']
        self.assertEqual(report['languages'],['RLL','ST']);self.assertFalse(report['native_fault_classification'])
        self.assertIn('POS zero retained',report['position'])


    def test_bundled_stats_lab_combines_ladder_and_st_sorting(self):
        from pathlib import Path
        from logixlab.model import Project
        from logixlab.runtime import Engine
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/StatsLab.L5X'))
        self.assertEqual(e.blockers,[]);e.memory.write('Sort',True);e.memory.write('TextSort',True);e.step()
        self.assertEqual(e.memory.read('SortValues'),[2,4,6,8,999])
        self.assertEqual(e.memory.read('SortGrid'),[[6,4,2],[12,10,8]])
        e.memory.write('SortValues[0]',10);e.memory.write('SortGrid[0,1]',20);e.step()
        self.assertEqual(e.memory.read('SortValues'),[10,4,6,8,999])
        self.assertEqual(e.memory.read('SortGrid'),[[6,10,2],[12,20,8]])


if __name__=='__main__':unittest.main()
