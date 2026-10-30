"""Bit diagnostics across words, resumable edges, result wrap and rollback."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
from logixlab import control_operations as controls

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def array(tags,name,values):
    t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='DINT',Dimensions=str(len(values)))
    a=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions=str(len(values)))
    for i,value in enumerate(values):E.SubElement(a,'Element',Index=f'[{i}]',Value=str(value))


def control(tags,name,length,position,flags):
    t=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='CONTROL')
    data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='CONTROL')
    for member,value in (controls.default()|dict(LEN=length,POS=position)|flags).items():
        E.SubElement(data,'DataValueMember',Name=member,DataType='DINT' if member in ('LEN','POS') else 'BOOL',Value=str(int(value)))


class FileBitCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def instruction(self,name='FBC',source='Source[0]',reference='Reference[0]',result='Result[0]',compare='Compare',output='ResultControl'):
        return f'{name}({source},{reference},{result},{compare},?,?,{output},?,?)'

    def engine(self,logic=None,*,name='FBC',length=40,position=0,capacity=3,result_position=0,
               source=(-2147483615,129,999),reference=(0,0,888),result=(-1,-1,-1,999),one=False,flags=None,result_flags=None,mutate=None):
        root=E.parse(SAMPLES/'BitLab.L5X').getroot();tags=root.find('./Controller/Tags')
        for tag,values in (('Source',source),('Reference',reference),('Result',result)):array(tags,tag,values)
        control(tags,'Compare',length,position,dict(IN=one)|dict(flags or {}))
        control(tags,'ResultControl',capacity,result_position,dict(result_flags or {}))
        content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent')
        for child in list(content):content.remove(child)
        for index,text in enumerate(logic if logic is not None else [self.instruction(name)+'OTE(BitOK);']):
            E.SubElement(E.SubElement(content,'Rung',Number=str(index),Type='N'),'Text').text=text
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'diagnostics.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path))

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_all_mode_reports_lsb_first_offsets_and_wraps_result_list(self):
        e=self.checked();before=copy.deepcopy(e.memory.read('Reference'));e.step()
        self.assertEqual(e.memory.read('Result'),[32,39,31,999]);self.assertEqual(e.memory.read('Reference'),before)
        self.assertEqual([e.memory.read('Compare.'+n) for n in ('POS','EN','DN','FD')],[40,True,True,True])
        self.assertEqual([e.memory.read('ResultControl.'+n) for n in ('POS','DN')],[2,False]);self.assertTrue(e.memory.read('BitOK'))

    def test_ddt_updates_only_compared_reference_bits_and_preserves_guard_words(self):
        e=self.checked(name='DDT',reference=(0,0x40000000,888));e.step()
        self.assertEqual(e.memory.read('Reference'),[-2147483615,0x40000081,888])
        self.assertEqual(e.memory.read('Source'),[-2147483615,129,999]);self.assertEqual(e.memory.read('Result'),[32,39,31,999])

    def test_one_at_a_time_requires_new_enable_edges_and_continues_after_match(self):
        for name in ('FBC','DDT'):
            e=self.checked(['XIC(Enable)'+self.instruction(name)+';'],one=True)
            for expected in (1,6,32,33,40):
                e.step();self.assertEqual(e.memory.read('Compare.POS'),expected);self.assertTrue(e.memory.read('Compare.FD'))
                before=copy.deepcopy(e.memory.values);e.step();self.assertEqual(e.memory.values,before)
                if expected!=40:
                    e.memory.write('Enable',False);e.step();e.memory.write('Enable',True)
            self.assertTrue(e.memory.read('Compare.DN'));self.assertEqual(e.memory.read('Result'),[32,39,31,999])

    def test_one_mode_false_rung_preserves_partial_cursor_and_result_position(self):
        e=self.checked(['XIC(Enable)'+self.instruction()+'OTE(BitOK);'],one=True)
        e.step();e.memory.write('Enable',False);e.step()
        self.assertEqual([e.memory.read('Compare.'+n) for n in ('POS','EN','DN','FD','IN')],[1,False,False,False,True])
        self.assertEqual(e.memory.read('ResultControl.POS'),1);self.assertEqual(e.memory.read('Result'),[0,-1,-1,999])
        e.memory.write('Enable',True);e.step();self.assertEqual(e.memory.read('Result[1]'),5)

    def test_one_ddt_changes_one_reference_bit_per_edge(self):
        e=self.checked(name='DDT',one=True,reference=(0,0x40000000,888));e.step()
        self.assertEqual(e.memory.read('Reference'),[1,0x40000000,888]);self.assertEqual(e.memory.read('Compare.POS'),1)

    def test_no_mismatch_reaches_end_without_reading_result_state_or_changing_result(self):
        e=self.checked(reference=(-2147483615,129,888));e.memory.write('ResultControl.LEN',0)
        e.memory.values['resultcontrol']['DN']=None;e.step()
        self.assertTrue(e.memory.read('Compare.DN'));self.assertFalse(e.memory.read('Compare.FD'))
        self.assertEqual(e.memory.read('Result'),[-1,-1,-1,999])

    def test_result_full_sets_done_and_wraps_only_on_next_mismatch(self):
        e=self.checked(length=32);e.step()
        self.assertEqual(e.memory.read('Result'),[0,5,31,999]);self.assertEqual(e.memory.read('ResultControl.POS'),3)
        self.assertTrue(e.memory.read('ResultControl.DN'))
        e=self.checked(length=31,capacity=2);e.step()
        self.assertEqual(e.memory.read('Result')[:3],[0,5,-1]);self.assertTrue(e.memory.read('ResultControl.DN'))

    def test_existing_full_result_restarts_at_zero_on_next_record(self):
        e=self.checked(one=True,result_position=3,result_flags={'DN':True});e.step()
        self.assertEqual(e.memory.read('Result'),[0,-1,-1,999]);self.assertEqual(e.memory.read('ResultControl.POS'),1)
        self.assertFalse(e.memory.read('ResultControl.DN'))

    def test_result_start_position_appends_and_preserves_unwritten_slots(self):
        e=self.checked(length=6,result_position=1);e.step()
        self.assertEqual(e.memory.read('Result'),[-1,0,5,999]);self.assertTrue(e.memory.read('ResultControl.DN'))

    def test_saved_compare_position_skips_earlier_bits(self):
        e=self.checked(position=6);e.step()
        self.assertEqual(e.memory.read('Result'),[31,32,39,999]);self.assertTrue(e.memory.read('ResultControl.DN'))

    def test_partial_last_word_preserves_uncompared_reference_bits(self):
        e=self.checked(name='DDT',length=33,reference=(0,0x40000080,888));e.step()
        self.assertEqual(e.memory.read('Reference'),[-2147483615,0x40000081,888])
        self.assertEqual(e.memory.read('Result'),[32,5,31,999])

    def test_array_start_offsets_produce_relative_bit_numbers(self):
        e=self.checked([self.instruction('DDT',source='Source[1]',reference='Reference[1]')+';'],length=8)
        e.step();self.assertEqual(e.memory.read('Result'),[0,7,-1,999]);self.assertEqual(e.memory.read('Reference'),[0,129,888])

    def test_false_and_prescan_clear_enable_found_and_reset_completed_positions(self):
        for name in ('FBC','DDT'):
            e=self.checked(name=name,position=7,result_position=2,flags={'EN':True,'DN':True,'FD':True,'ER':True,'IN':True,'UL':True},result_flags={'DN':True,'EN':True})
            self.assertEqual([e.memory.read('Compare.'+n) for n in ('EN','FD','DN','POS')],[False,False,False,0])
            self.assertEqual([e.memory.read('ResultControl.'+n) for n in ('DN','POS','EN')],[False,0,True])
            self.assertTrue(e.memory.read('Compare.ER'));self.assertTrue(e.memory.read('Compare.IN'));self.assertTrue(e.memory.read('Compare.UL'))
            self.assertEqual(e.memory.read('Reference'),[0,0,888]);self.assertEqual(e.memory.read('Result'),[-1,-1,-1,999])

    def test_incomplete_prescan_retains_positions_result_done_error_and_mode(self):
        e=self.checked(position=6,result_position=3,flags={'EN':True,'FD':True,'ER':True,'IN':True},result_flags={'DN':True})
        self.assertEqual([e.memory.read('Compare.'+n) for n in ('EN','FD','POS','ER','IN')],[False,False,6,True,True])
        self.assertEqual(e.memory.read('ResultControl.POS'),3);self.assertTrue(e.memory.read('ResultControl.DN'))

    def test_completed_false_scan_resets_controls_but_retains_data_for_next_cycle(self):
        e=self.checked(['XIC(Enable)'+self.instruction()+';']);e.step();values=e.memory.read('Result')[:]
        e.memory.write('Enable',False);e.step()
        self.assertEqual([e.memory.read('Compare.'+n) for n in ('EN','FD','DN','POS')],[False,False,False,0])
        self.assertEqual([e.memory.read('ResultControl.'+n) for n in ('DN','POS')],[False,0])
        self.assertEqual(e.memory.read('Result'),values)

    def test_false_rung_and_held_enable_do_not_read_unknown_array_data(self):
        e=self.checked(['XIC(Enable)'+self.instruction()+';']);e.memory.write('Enable',False)
        e.memory.values['source'][0]=None;e.memory.values['reference'][0]=None;e.step()
        e.memory.write('Enable',True);e.memory.write('Compare.EN',True);e.step()
        self.assertEqual(e.scan_count,2)

    def test_saved_done_on_true_rung_only_latches_enable(self):
        e=self.checked();e.memory.write('Compare.DN',True);e.memory.write('Compare.FD',True);e.memory.write('Compare.ER',True)
        e.memory.values['source'][0]=None;e.step()
        self.assertTrue(e.memory.read('Compare.EN'));self.assertTrue(e.memory.read('Compare.FD'));self.assertTrue(e.memory.read('Compare.ER'))

    def test_invalid_compare_length_or_negative_position_sets_error_without_data_writes(self):
        for length,position in ((0,0),(-1,0),(40,-1)):
            e=self.checked(length=length,position=position);e.step()
            self.assertTrue(e.memory.read('Compare.ER'));self.assertTrue(e.memory.read('Compare.EN'))
            self.assertFalse(e.memory.read('Compare.FD'));self.assertFalse(e.memory.read('Compare.DN'))
            self.assertEqual(e.memory.read('Result'),[-1,-1,-1,999])

    def test_position_at_or_after_configured_end_completes_without_array_reads(self):
        for position in (40,41):
            e=self.checked(position=position);e.memory.values['source'][0]=None;e.step()
            self.assertTrue(e.memory.read('Compare.DN'));self.assertEqual(e.memory.read('Compare.POS'),40)

    def test_old_error_clears_when_rearmed_for_valid_compare(self):
        e=self.checked(flags={'ER':True});e.step();self.assertFalse(e.memory.read('Compare.ER'))

    def test_required_unknown_later_word_rolls_back_earlier_results_and_ddt_updates(self):
        for name in ('FBC','DDT'):
            for field in ('source','reference'):
                e=self.checked(name=name);e.memory.values[field][1]=None;before=copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
                self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))

    def test_unknown_unvisited_word_does_not_block_one_mismatch_mode(self):
        e=self.checked(one=True);e.memory.values['source'][1]=None;e.step()
        self.assertEqual(e.memory.read('Result[0]'),0);self.assertEqual(e.memory.read('Compare.POS'),1)

    def test_unknown_result_slots_are_established_by_writes(self):
        e=self.checked();e.memory.values['result']=[None,None,None,None];e.step()
        self.assertEqual(e.memory.values['result'],[32,39,31,None])

    def test_unknown_required_control_flags_fault_without_partial_mutation(self):
        for key,field in (('compare','EN'),('compare','DN'),('compare','IN'),('resultcontrol','DN')):
            e=self.checked(name='DDT');e.memory.values[key][field]=None;before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'unknown'):e.step()
            self.assertEqual(e.memory.values,before)

    def test_each_compared_bit_consumes_budget_and_failure_rolls_back(self):
        e=self.checked(name='DDT');e.instruction_limit=4;before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before);e.instruction_limit=100;e.step()
        self.assertTrue(e.memory.read('Compare.DN'))

    def test_software_limit_and_array_bound_failures_roll_back(self):
        for options in ({'length':4097},{'length':97},{'capacity':5}):
            e=self.checked(name='DDT',**options);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before)

    def test_maximum_bit_span_reaches_high_bit_without_touching_guard_word(self):
        e=self.checked(name='DDT',length=4096,capacity=1,source=tuple([0]*127+[-2147483648,999]),reference=tuple([0]*128+[888]))
        e.step();self.assertEqual(e.memory.read('Result'),[4095,-1,-1,999])
        self.assertEqual(e.memory.read('Reference[127]'),-2147483648);self.assertEqual(e.memory.read('Reference[128]'),888)
        self.assertEqual(e.memory.read('Compare.POS'),4096);self.assertTrue(e.memory.read('Compare.DN'))

    def test_multidimensional_regions_flatten_within_the_selected_array(self):
        def mutate(root):
            for name,values in (('Source',(1,2,4,8)),('Reference',(0,0,0,0))):
                tag=root.find(f'./Controller/Tags/Tag[@Name="{name}"]');tag.set('Dimensions','2,2')
                a=tag.find('./Data/Array');a.clear();a.attrib.update(DataType='DINT',Dimensions='2,2')
                for i,value in enumerate(values):E.SubElement(a,'Element',Index=f'[{i//2},{i%2}]',Value=str(value))
        e=self.checked([self.instruction(source='Source[0,1]',reference='Reference[0,1]')+';'],length=64,mutate=mutate)
        e.step();self.assertEqual(e.memory.read('Result'),[1,34,-1,999])

    def test_invalid_result_cursor_state_faults_and_rolls_back_reference_writes(self):
        for capacity,position in ((0,0),(-1,0),(3,-1),(3,3),(3,4)):
            e=self.checked(name='DDT',capacity=capacity,result_position=position);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before)

    def test_late_fault_rolls_back_both_controls_results_and_reference_then_retry_commits_once(self):
        e=self.checked([self.instruction('DDT')+';','DIV(1,FaultDivisor,GuardResult);'])
        e.memory.write('FaultDivisor',0);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('Reference')[:2],[-2147483615,129])
        self.assertEqual(e.memory.read('Result'),[32,39,31,999]);before=copy.deepcopy(e.memory.values);e.step();self.assertEqual(e.memory.values,before)

    def test_disabled_mcr_uses_false_reset_without_learning_changed_inputs(self):
        e=self.checked(['XIC(Enable)MCR();',self.instruction('DDT')+';','MCR();'])
        e.step();e.memory.write('Enable',False);e.memory.write('Source[0]',0);e.step()
        self.assertEqual(e.memory.read('Reference[0]'),-2147483615);self.assertFalse(e.memory.read('Compare.FD'))
        self.assertTrue(e.trace[1]['mcr_forced_false']);e.memory.write('Enable',True);e.step()
        self.assertEqual(e.memory.read('Reference[0]'),0);self.assertTrue(e.memory.read('Compare.FD'))

    def test_program_local_arrays_and_control_aliases(self):
        def mutate(root):
            tags=root.find('./Controller/Tags');local=root.find('./Controller/Programs/Program/Tags')
            ref=tags.find('Tag[@Name="Reference"]');tags.remove(ref);local.append(ref)
            E.SubElement(tags,'Tag',Name='AliasCompare',TagType='Alias',AliasFor='Compare')
        e=self.checked([self.instruction(compare='AliasCompare')+';'],mutate=mutate);e.step()
        self.assertEqual(e.memory.read('Result'),[32,39,31,999]);self.assertTrue(e.memory.read('Compare.DN'))

    def test_readonly_input_tables_allowed_but_writable_roles_require_writable_storage(self):
        for name in ('Source','Reference'):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
            e=self.checked(mutate=constant);e.step()
        for role in ('Reference','Result','Compare','ResultControl'):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{role}"]').set('Constant','true')
            self.assertTrue(self.engine(name='DDT',mutate=constant).blockers)

    def test_alias_or_indirect_array_starts_wrong_types_and_scalar_arrays_block(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='AliasSource',TagType='Alias',AliasFor='Source[0]')
        for source in ('AliasSource','Source[Compare.POS]','Source[0].0','42','Status'):
            self.assertTrue(self.engine([self.instruction(source=source)+';'],mutate=alias).blockers,source)
        for role in ('Source','Reference','Result'):
            def wrong(root):root.find(f'./Controller/Tags/Tag[@Name="{role}"]').set('DataType','REAL')
            self.assertTrue(self.engine(mutate=wrong).blockers)

    def test_controls_and_writable_array_roles_cannot_share_base_tags(self):
        for logic in (self.instruction(output='Compare'),self.instruction(result='Source[0]'),self.instruction(result='Reference[0]'),self.instruction('DDT',reference='Source[1]')):
            self.assertTrue(self.engine([logic+';']).blockers,logic)
        e=self.checked([self.instruction(reference='Source[0]')+';']);e.step();self.assertFalse(e.memory.read('Compare.FD'))

    def test_bad_arities_pseudooperands_other_profiles_and_st_are_blocked(self):
        for logic in ('FBC(Source[0],Reference[0],Result[0],Compare,40,0,ResultControl,3,0);','DDT(Source[0],Reference[0],Result[0],Compare,?,?);'):
            self.assertTrue(self.engine([logic]).blockers)
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def profile(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version)
            self.assertTrue(self.engine(mutate=profile).blockers)
        def st(root):
            r=root.find('./Controller/Programs/Program/Routines/Routine');r.set('Type','ST');r.remove(r.find('RLLContent'))
            E.SubElement(E.SubElement(r,'STContent'),'Line',Number='0').text=self.instruction()+';'
        self.assertTrue(self.engine([],mutate=st).blockers)

    def test_deferred_prescan_preview_and_routine_harness_keep_correct_boundaries(self):
        e=self.checked(flags={'EN':True,'DN':True,'FD':True},position=7,result_position=2,result_flags={'DN':True})
        deferred=Engine(e.project,defer_prescan=True);self.assertEqual(deferred.memory.read('Compare.POS'),7)
        deferred.enter_run();self.assertEqual(deferred.memory.read('Compare.POS'),0)
        harness=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(harness.blockers,[])
        harness.step();self.assertEqual(harness.memory.read('Result'),[32,39,31,999])

    def test_report_exposes_mode_units_limits_and_native_qualification(self):
        report=self.checked().report()['file_bit_compare'];self.assertEqual(report['instructions'],['DDT','FBC'])
        self.assertEqual(report['max_bits'],4096);self.assertFalse(report['native_runtime_parity'])

    def test_detached_routine_replacement_does_not_mutate_active_values(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked(['NOP();']);e.step();before=copy.deepcopy(e.memory.values)
        logic=[self.instruction('DDT')+';'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId='1'),'TextIOI').text=logic[0]
        source=decode(container(E.tostring(xml,encoding='utf-8')))
        candidate,_=prepare(e,source,tuple(logic),'MainProgram',0)
        self.assertEqual(e.memory.values,before);self.assertEqual(candidate.memory.values,before)
        candidate.step();self.assertEqual(candidate.memory.read('Reference')[:2],[-2147483615,129])
        self.assertEqual(e.memory.values,before)


if __name__=='__main__':unittest.main()
