"""SRT live references and conservative ST FOR write effects."""
import copy
import unittest
from xml.etree import ElementTree as E
import test_array_sort as fixtures
from logixlab.model import ModelError


class SortReferenceTests(unittest.TestCase):
    setUp=fixtures.ArraySortTests.setUp
    checked=fixtures.ArraySortTests.checked
    multidimensional=staticmethod(fixtures.ArraySortTests.multidimensional)

    @staticmethod
    def tags(root):
        tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='Index',TagType='Base',DataType='DINT');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='1')
        for name,target in (('View','Queue'),('Selected','Queue[1]'),('Chain','Selected'),('Cursor','Ctl.POS')):E.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Alias',AliasFor=target)

    def engine(self,rungs,*,mutate=None,length=3,queue=(101,6,2,4,8,999),**kwargs):
        def refs(root):
            self.tags(root)
            if mutate:mutate(root)
        return fixtures.ArraySortTests.engine(self,rungs,length=length,queue=queue,mutate=refs,**kwargs)

    def st(self,text,*,mutate=None,**kwargs):
        def language(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'));E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=text
            if mutate:mutate(root)
        return self.engine([],mutate=language,**kwargs)

    def snapshot(self,e):return copy.deepcopy((e.memory.values,e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def test_alias_selected_element_chain_and_guards(self):
        e=self.checked(['SRT(Chain,0,Ctl,?,?);']);e.step();self.assertEqual(e.memory.read('Queue'),[101,2,4,6,8,999]);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_held_ladder_does_not_read_changed_or_unknown_start(self):
        e=self.checked(['XIC(StartPB)SRT(View[Index],0,Ctl,?,?);']);e.memory.write('StartPB',True);e.step();e.memory.values['index']=None;e.memory.write('Queue[1]',7);e.step()
        self.assertEqual(e.memory.read('Queue'),[101,7,4,6,8,999]);e.memory.write('StartPB',False);e.step();self.assertFalse(e.memory.read('Ctl.EN'))

    def test_rearm_sorts_new_window(self):
        e=self.checked(['XIC(StartPB)SRT(View[Index],0,Ctl,?,?);']);e.memory.write('StartPB',True);e.step();e.memory.write('StartPB',False);e.memory.write('Index',2);e.step()
        e.memory.write('Queue[2]',10);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue'),[101,2,6,8,10,999])

    def test_false_and_error_calls_skip_bad_source_index(self):
        for line in ('AFI()SRT(View[Index],0,Ctl,?,?);','SRT(View[Index],0,Ctl,?,?);'):
            e=self.checked([line]);e.memory.values['index']=None
            if line.startswith('SRT'):e.memory.write('Ctl.ER',True)
            e.step();self.assertEqual(e.memory.read('Queue[1]'),6)

    def test_dn_alone_does_not_inhibit_sort(self):
        e=self.checked(['SRT(View[Index],0,Ctl,?,?);']);e.memory.write('Ctl.DN',True);e.step();self.assertEqual(e.memory.read('Queue[1]'),2)

    def test_reached_unknown_and_invalid_indices_roll_back(self):
        for index in (None,-1,999):
            e=self.checked(['SRT(View[Index],0,Ctl,?,?);']);e.memory.values['index']=index;before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_size_limit_precedes_source_read(self):
        e=self.checked(['SRT(View[Index],0,Ctl,?,?);'],length=4097);e.memory.values['index']=None
        with self.assertRaisesRegex(ModelError,'software limit'):e.step()

    def test_valid_start_short_window_does_not_spill(self):
        def matrix(root):self.multidimensional((2,3),(6,10,2,12,4,8))(root)
        e=self.checked(['SRT(View[0,Index],1,Ctl,?,?);'],mutate=matrix);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'boundary'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_two_and_three_dimensional_alias_axes(self):
        def matrix(root):self.multidimensional((2,3),(6,10,2,12,4,8))(root)
        e=self.checked(['SRT(View[0,Index],0,Ctl,?,?);'],length=2,mutate=matrix);e.step();self.assertEqual(e.memory.read('Queue'),[[6,4,2],[12,10,8]])
        def cube(root):self.multidimensional((2,2,3),(6,5,4,3,2,1,12,11,10,9,8,7))(root)
        e=self.checked(['SRT(View[1,Index,0],2,Ctl,?,?);'],mutate=cube);e.step();self.assertEqual(e.memory.read('Queue')[1][1],[7,8,9])

    def test_source_alias_suffix_uses_program_namespace(self):
        def scoped(root):
            tag=E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='Index',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='2')
        e=self.checked(['SRT(View[Index],0,Ctl,?,?);'],mutate=scoped);e.step();self.assertEqual(e.memory.read('Queue'),[101,6,2,4,8,999])

    def test_control_pos_dependencies_and_read_only_arrays_block(self):
        for source in ('View[Ctl.POS]','View[Cursor]'):
            self.assertTrue(any('CONTROL.POS' in b for b in self.engine([f'SRT({source},0,Ctl,?,?);']).blockers))
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Queue"]').set('Constant','true')
        self.assertTrue(self.engine(['SRT(Selected,0,Ctl,?,?);'],mutate=constant).blockers)

    def test_late_fault_restores_selected_array_and_control(self):
        e=self.checked(['SRT(View[Index],0,Ctl,?,?);','DIV(1,0,Outgoing);']);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_st_alias_call_repeats_and_skipped_if_keeps_state(self):
        e=self.st('IF StartPB THEN SRT(View[Index],0,Ctl); END_IF;');self.assertEqual(e.blockers,[]);e.memory.values['index']=None;e.step()
        e.memory.write('Index',1);e.memory.write('StartPB',True);e.step();e.memory.write('Queue[1]',7);e.step();self.assertEqual(e.memory.read('Queue'),[101,4,6,7,8,999])

    def test_st_for_effect_covers_entire_alias_member_including_guards(self):
        for text in ('FOR Incoming:=0 TO View[5] DO SRT(View[Index],0,Ctl); END_FOR;','FOR Incoming:=0 TO 2 BY View[5] DO SRT(Chain,0,Ctl); END_FOR;'):
            self.assertTrue(any('bounds/step' in b for b in self.st(text).blockers))

    def test_st_for_preserves_len_pos_dependencies_and_unrelated_bounds(self):
        for bound in ('Ctl.LEN','Ctl.POS','Index'):
            e=self.st(f'FOR Incoming:=0 TO {bound} DO SRT(View[Index],0,Ctl); END_FOR;');self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Queue'),[101,2,4,6,8,999])

    @staticmethod
    def parents(root):
        c=root.find('Controller');dt=E.SubElement(c.find('DataTypes'),'DataType',Name='SortBank',Family='NoFamily',Class='User');members=E.SubElement(dt,'Members')
        E.SubElement(members,'Member',Name='Rows',DataType='DINT',Dimension='4');E.SubElement(members,'Member',Name='Bound',DataType='DINT',Dimension='0')
        tags=c.find('Tags');tag=E.SubElement(tags,'Tag',Name='Banks',DataType='SortBank',TagType='Base',Dimensions='2');arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='SortBank',Dimensions='2')
        for i in range(2):
            obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='SortBank');rows=E.SubElement(obj,'ArrayMember',Name='Rows',DataType='DINT',Dimensions='4')
            for j,value in enumerate((9,3,6,999)):E.SubElement(rows,'Element',Index=f'[{j}]',Value=str(value))
            E.SubElement(obj,'DataValueMember',Name='Bound',DataType='DINT',Value='2')
        E.SubElement(tags,'Tag',Name='BankView',DataType='DINT',TagType='Alias',AliasFor='Banks[Index].Rows')

    def test_st_for_widens_dynamic_parent_and_hidden_alias_effects(self):
        for source in ('Banks[Index].Rows[0]','BankView[0]'):
            for bound in ('Banks[1].Rows[3]','Banks[1].Bound'):
                e=self.st(f'FOR Incoming:=0 TO {bound} DO SRT({source},0,Ctl); END_FOR;',mutate=self.parents)
                self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)

    def test_parent_array_sort_outside_for_preserves_siblings(self):
        e=self.checked(['SRT(Banks[Index].Rows[0],0,Ctl,?,?);'],mutate=self.parents);e.step();self.assertEqual(e.memory.read('Banks[1].Rows'),[3,6,9,999]);self.assertEqual(e.memory.read('Banks[0].Rows'),[9,3,6,999]);self.assertEqual(e.memory.read('Banks[1].Bound'),2)

    def test_st_for_unknown_start_preflight_does_not_read_it(self):
        e=self.st('IF StartPB THEN FOR Incoming:=0 TO Ctl.LEN DO SRT(View[Index],0,Ctl); END_FOR; END_IF;');self.assertEqual(e.blockers,[])
        e.memory.values['index']=None;e.step();self.assertEqual(e.memory.read('Queue[1]'),6)


if __name__=='__main__':unittest.main()
