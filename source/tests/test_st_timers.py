"""ST timer clocks, reset/retention, status and transaction boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_timers import FIELDS,default

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,tag_name,values):
    tag=E.SubElement(parent,'Tag',Name=tag_name,DataType='FBD_TIMER',TagType='Base')
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FBD_TIMER')
    for name,value in (default()|values).items():
        E.SubElement(data,'DataValueMember',Name=name,DataType=FIELDS[name],Value=str(int(value)))


def logic(routine,lines):
    routine.set('Type','ST')
    for child in list(routine):routine.remove(child)
    body=E.SubElement(routine,'STContent')
    for index,text in enumerate(lines):E.SubElement(body,'Line',Number=str(index)).text=text


class StructuredTimerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,name='TONR',values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        for tag in ('T','U'):record(tags,tag,{'PRE':30,'TimerEnable':True}|dict(values or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else [name+'(T);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'timers.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def advance(self,e):e.step(10);return e.memory.read('T')

    def test_tonr_starts_at_zero_accumulates_and_saturates_at_preset(self):
        e=self.checked(values={'ACC':19,'DN':True,'EN':True,'TT':True})
        for expected in (0,10,20,30,30):
            t=self.advance(e);self.assertEqual(t['ACC'],expected);self.assertEqual(t['DN'],expected==30)
            self.assertEqual(t['TT'],expected<30);self.assertTrue(t['EN']);self.assertTrue(t['EnableIn']);self.assertTrue(t['EnableOut'])

    def test_tonr_false_timer_enable_resets_acc_and_flags(self):
        e=self.checked();self.advance(e);self.advance(e);e.memory.write('T.TimerEnable',False);t=self.advance(e)
        self.assertEqual((t['ACC'],t['EN'],t['TT'],t['DN']),(0,False,False,False))
        e.memory.write('T.TimerEnable',True);self.assertEqual(self.advance(e)['ACC'],0)
        self.assertEqual(self.advance(e)['ACC'],10)

    def test_rtor_retains_acc_on_pause_and_resumes_without_charging_disabled_interval(self):
        e=self.checked(name='RTOR',values={'ACC':5});self.assertEqual(self.advance(e)['ACC'],5)
        self.assertEqual(self.advance(e)['ACC'],15);e.memory.write('T.TimerEnable',False)
        for _ in range(3):
            t=self.advance(e);self.assertEqual(t['ACC'],15);self.assertFalse(t['EN']);self.assertFalse(t['TT'])
        e.memory.write('T.TimerEnable',True);self.assertEqual(self.advance(e)['ACC'],15)
        self.assertEqual(self.advance(e)['ACC'],25)

    def test_rtor_done_retains_during_false_enable_until_reset(self):
        e=self.checked(name='RTOR',values={'ACC':30});self.assertTrue(self.advance(e)['DN'])
        e.memory.write('T.TimerEnable',False);t=self.advance(e);self.assertTrue(t['DN']);self.assertEqual(t['ACC'],30)
        e.memory.write('T.Reset',True);t=self.advance(e);self.assertEqual((t['ACC'],t['DN'],t['TT'],t['EN']),(0,False,False,False))

    def test_tofr_arms_on_true_and_times_after_falling_timer_enable(self):
        e=self.checked(name='TOFR',values={'ACC':17})
        t=self.advance(e);self.assertEqual((t['ACC'],t['DN'],t['TT'],t['EN']),(0,True,False,True))
        e.memory.write('T.TimerEnable',False)
        for expected in (0,10,20,30,30):
            t=self.advance(e);self.assertEqual(t['ACC'],expected);self.assertEqual(t['DN'],expected<30)
            self.assertEqual(t['TT'],expected<30);self.assertFalse(t['EN'])

    def test_tofr_initial_false_does_not_start_and_retains_saved_acc(self):
        e=self.checked(name='TOFR',values={'TimerEnable':False,'ACC':17,'DN':True})
        for _ in range(3):
            t=self.advance(e);self.assertEqual((t['ACC'],t['DN'],t['TT']),(17,False,False))

    def test_tofr_reenable_resets_an_incomplete_off_delay(self):
        e=self.checked(name='TOFR');self.advance(e);e.memory.write('T.TimerEnable',False)
        self.advance(e);self.advance(e);e.memory.write('T.TimerEnable',True);t=self.advance(e)
        self.assertEqual((t['ACC'],t['DN'],t['TT']),(0,True,False))

    def test_tofr_reset_sets_acc_to_pre_and_requires_rearm(self):
        e=self.checked(name='TOFR');self.advance(e);e.memory.write('T.TimerEnable',False);self.advance(e)
        e.memory.write('T.Reset',True);t=self.advance(e);self.assertEqual((t['ACC'],t['DN'],t['TT'],t['EN']),(30,False,False,False))
        e.memory.write('T.Reset',False)
        for _ in range(2):self.assertEqual((self.advance(e)['ACC'],e.memory.read('T.DN')),(30,False))
        e.memory.write('T.TimerEnable',True);self.assertTrue(self.advance(e)['DN'])

    def test_reset_has_priority_over_enable_for_all_timer_kinds(self):
        for name in ('TONR','RTOR','TOFR'):
            e=self.checked(name=name,values={'Reset':True,'ACC':19});t=self.advance(e)
            self.assertEqual((t['EN'],t['TT'],t['DN']),(False,False,False));self.assertEqual(t['ACC'],30 if name=='TOFR' else 0)
            e.memory.write('T.Reset',False);t=self.advance(e)
            self.assertEqual(t['ACC'],0)

    def test_zero_preset_completes_on_first_enabled_call_and_immediate_off_edge(self):
        for name in ('TONR','RTOR'):
            e=self.checked(name=name,values={'PRE':0});t=self.advance(e);self.assertTrue(t['DN']);self.assertFalse(t['TT'])
        e=self.checked(name='TOFR',values={'PRE':0});self.assertTrue(self.advance(e)['DN'])
        e.memory.write('T.TimerEnable',False);self.assertFalse(self.advance(e)['DN'])

    def test_st_call_forces_enable_in_even_if_stored_false_or_unknown(self):
        e=self.checked(values={'EnableIn':False});e.memory.values['t']['EnableIn']=None
        t=self.advance(e);self.assertTrue(t['EnableIn']);self.assertTrue(t['EnableOut']);self.assertTrue(t['TT'])

    def test_skipped_calls_retain_outputs_and_elapsed_time_while_active(self):
        e=self.checked(['IF StartPB THEN TONR(T); END_IF;'],values={'PRE':100})
        e.memory.write('StartPB',True);self.advance(e);self.advance(e)
        e.memory.write('StartPB',False);before=copy.deepcopy(e.memory.read('T'))
        self.advance(e);self.advance(e);self.assertEqual(e.memory.read('T'),before)
        e.memory.write('StartPB',True);self.assertEqual(self.advance(e)['ACC'],40)

    def test_two_calls_and_for_iterations_in_one_timestamp_do_not_double_count(self):
        e=self.checked(['TONR(T);','FOR DisplayedPartCount := 0 TO 2 DO TONR(T); END_FOR;'])
        self.assertEqual(self.advance(e)['ACC'],0);self.assertEqual(self.advance(e)['ACC'],10)

    def test_timers_in_separate_records_have_independent_clocks(self):
        e=self.checked(['TONR(T);','IF StartPB THEN TONR(U); END_IF;'])
        self.advance(e);self.advance(e);e.memory.write('StartPB',True);self.advance(e)
        self.assertEqual((e.memory.read('T.ACC'),e.memory.read('U.ACC')),(20,0))

    def test_different_timer_kinds_on_one_record_are_rejected_and_rolled_back(self):
        e=self.checked(['TONR(T);','RTOR(T);']);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'different ST timer'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})

    def test_negative_preset_sets_instruction_status_without_global_scan_fault(self):
        e=self.checked(values={'PRE':-1,'ACC':17,'EN':True,'TT':True,'DN':True});t=self.advance(e)
        self.assertEqual((t['Status'],t['EnableIn'],t['EnableOut']),(3,True,False))
        self.assertEqual((t['ACC'],t['EN'],t['TT'],t['DN']),(17,True,True,True));self.assertFalse(e.fault)
        self.assertTrue(e.memory.read('T.InstructFault'));self.assertTrue(e.memory.read('T.PresetInv'))
        e.memory.write('T.PRE',30);t=self.advance(e);self.assertEqual(t['Status'],0);self.assertEqual(t['ACC'],0)

    def test_invalid_preset_pauses_elapsed_history_and_valid_recovery_resumes(self):
        e=self.checked();self.advance(e);self.advance(e);e.memory.write('T.PRE',-1)
        self.advance(e);self.advance(e);e.memory.write('T.PRE',30)
        self.assertEqual(self.advance(e)['ACC'],10);self.assertEqual(self.advance(e)['ACC'],20)

    def test_status_aliases_share_one_backing_dint_and_are_case_insensitive(self):
        e=self.checked();e.memory.write('t.PresetInv',True);self.assertEqual(e.memory.read('T.Status'),2)
        e.memory.write('T.InstructFault',True);self.assertEqual(e.memory.read('T.Status'),3)
        e.memory.write('T.Status',1);self.assertFalse(e.memory.read('t.presetinv'));self.assertTrue(e.memory.read('T.InstructFault'))
        self.advance(e);self.assertEqual(e.memory.read('T.Status'),0)

    def test_unknown_required_inputs_fault_without_values_or_clock_changes(self):
        for field in ('PRE','TimerEnable','Reset'):
            e=self.checked();e.memory.values['t'][field]=None;before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'unknown'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})

    def test_unknown_retained_acc_requires_establishment_before_timing(self):
        e=self.checked(name='RTOR');e.memory.values['t']['ACC']=None
        with self.assertRaisesRegex(ModelError,'ACC.*unknown'):e.step()
        e.memory.write('T.Reset',True);self.assertEqual(self.advance(e)['ACC'],0)

    def test_tonr_first_run_and_reset_establish_unknown_acc(self):
        e=self.checked();e.memory.values['t']['ACC']=None;self.assertEqual(self.advance(e)['ACC'],0)
        e=self.checked(name='RTOR',values={'Reset':True});e.memory.values['t']['ACC']=None
        self.assertEqual(self.advance(e)['ACC'],0)

    def test_negative_retained_acc_is_rejected_when_required(self):
        for name in ('RTOR','TOFR'):
            e=self.checked(name=name,values={'ACC':-1})
            if name=='TOFR':self.advance(e);e.memory.write('T.TimerEnable',False);e.memory.write('T.ACC',-1)
            with self.assertRaisesRegex(ModelError,'nonnegative'):e.step()

    def test_prescan_only_clears_enable_pair_and_deferred_preview_preserves_saved_values(self):
        e=self.checked(values={'ACC':17,'EN':True,'TT':True,'DN':True,'EnableIn':True,'EnableOut':True},defer=True)
        self.assertTrue(e.memory.read('T.EnableIn'));self.assertEqual(e.memory.read('T.ACC'),17)
        e.enter_run();self.assertFalse(e.memory.read('T.EnableIn'));self.assertFalse(e.memory.read('T.EnableOut'))
        self.assertEqual((e.memory.read('T.ACC'),e.memory.read('T.EN'),e.memory.read('T.TT'),e.memory.read('T.DN')),(17,True,True,True))

    def test_run_entry_resets_elapsed_history_and_initializes_nonretentive_again(self):
        for name,expected in (('TONR',0),('RTOR',10)):
            e=self.checked(name=name);self.advance(e);self.advance(e);before=(e.scan_count,e.time_ms)
            e.enter_run();self.assertEqual((e.scan_count,e.time_ms),before);self.assertEqual(e.last_timer,{})
            self.assertEqual(self.advance(e)['ACC'],expected)

    def test_late_fault_rolls_back_elapsed_clock_flags_and_values_then_retries_once(self):
        e=self.checked(['TONR(T);','SpeedCommand := 1 / SpeedSetpoint;'])
        e.memory.write('SpeedSetpoint',1);self.advance(e);self.advance(e);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.scan_count,e.time_ms,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.last_timer,e.scan_count,e.time_ms,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.advance(e)['ACC'],20)

    def test_aliases_array_elements_and_program_local_records_resolve_to_owned_clock(self):
        def mutate(root):
            tags=root.find('./Controller/Tags');t=tags.find('Tag[@Name="T"]')
            tags.remove(t);root.find('./Controller/Programs/Program/Tags').append(t)
            E.SubElement(tags,'Tag',Name='AliasTimer',TagType='Alias',AliasFor='Program:MainProgram.T')
        e=self.checked(['TONR(AliasTimer);'],mutate=mutate);e.step();e.step()
        self.assertEqual(e.memory.read('Program:MainProgram.T.ACC'),10)

    def test_for_bounds_cannot_depend_on_timer_record_written_by_body(self):
        self.assertTrue(self.engine(['FOR DisplayedPartCount := 0 TO T.ACC DO TONR(T); END_FOR;']).blockers)

    def test_bad_arities_scalar_type_constant_and_other_profiles_are_rejected(self):
        for line in ('TONR();','RTOR(T,U);','TOFR(Parts);','TONR(1);','TONR(T.ACC);'):
            self.assertTrue(self.engine([line]).blockers,line)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="T"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def profile(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_rll_forms_are_blocked_and_do_not_inflate_rll_dispatch_count(self):
        self.assertEqual(len(ARITIES),101);self.assertTrue({'TONR','RTOR','TOFR'}<=set(ST_ONLY_ARITIES))
        def ladder(root):
            r=root.find('./Controller/Programs/Program/Routines/Routine');r.set('Type','RLL');r.remove(r.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(r,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='TONR(T);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_predefined_record_is_not_inferred_as_decorated_data_only(self):
        e=self.checked();self.assertNotIn('FBD_TIMER',e.project.data_only_types)
        self.assertNotIn('fbd_timer',e.project.udts);self.assertEqual(set(e.memory.read('T')),set(FIELDS))
        self.assertEqual(e.memory.resolve('T.ACC')[2],'DINT');self.assertEqual(e.memory.resolve('T.Status')[2],'DINT')

    def test_report_exposes_st_only_profile_and_clock_qualification(self):
        profile=self.checked().report()['st_timers'];self.assertEqual(profile['language'],'ST')
        self.assertEqual(profile['instructions'],['RTOR','TOFR','TONR']);self.assertFalse(profile['native_runtime_parity'])

    def test_array_timers_keep_separate_qualified_records(self):
        def mutate(root):
            tags=root.find('./Controller/Tags');t=tags.find('Tag[@Name="T"]');data=t.find('Data')
            original=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated');t.set('Dimensions','2')
            a=E.SubElement(data,'Array',DataType='FBD_TIMER',Dimensions='2')
            for i in range(2):E.SubElement(a,'Element',Index=f'[{i}]').append(copy.deepcopy(original))
        e=self.checked(['TONR(T[0]);','RTOR(T[1]);'],mutate=mutate);e.step();e.step()
        self.assertEqual(e.memory.read('T[0].ACC'),10);self.assertEqual(e.memory.read('T[1].ACC'),10)

    def test_explicit_udt_timer_member_has_builtin_field_types_and_clock(self):
        def mutate(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='HolderType',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Timer',DataType='FBD_TIMER',Dimension='0')
            tags=root.find('./Controller/Tags');original=copy.deepcopy(tags.find('Tag[@Name="T"]/Data/Structure'))
            original.tag='StructureMember';original.set('Name','Timer')
            tag=E.SubElement(tags,'Tag',Name='Holder',DataType='HolderType',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='HolderType').append(original)
        e=self.checked(['TONR(Holder.Timer);'],mutate=mutate);e.step();e.step()
        self.assertEqual(e.memory.read('Holder.Timer.ACC'),10);self.assertEqual(e.memory.resolve('Holder.Timer.Status')[2],'DINT')

    def test_preset_increase_after_completion_restarts_without_charging_done_interval(self):
        e=self.checked(values={'PRE':10});self.advance(e);self.advance(e);self.advance(e)
        e.memory.write('T.PRE',30);self.assertEqual(self.advance(e)['ACC'],10)
        self.assertEqual(self.advance(e)['ACC'],20)

    def test_periodic_task_uses_release_timestamps_for_elapsed_time(self):
        def mutate(root):
            t=root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','10')
        e=self.checked(mutate=mutate)
        self.assertEqual(self.advance(e)['ACC'],0);self.assertEqual(self.advance(e)['ACC'],10)

    def test_prescan_failure_restores_timer_values_and_existing_clock_history(self):
        e=self.checked(['TONR(T);','TONR(U);']);e.step();e.step()
        before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan.*budget'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)

    def test_aoi_inout_timer_uses_actual_record_and_own_elapsed_history(self):
        def mutate(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions')
            if definitions is None:definitions=E.SubElement(root.find('Controller'),'AddOnInstructionDefinitions')
            d=E.SubElement(definitions,'AddOnInstructionDefinition',Name='TimerBlock',Class='Standard',Revision='1.0',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            params=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                E.SubElement(params,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(params,'Parameter',Name='TimerState',TagType='Base',DataType='FBD_TIMER',Usage='InOut',Required='true',Visible='true')
            E.SubElement(d,'LocalTags');logic(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='ST'),['RTOR(TimerState);'])
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='TimerBlock',TagType='Base')
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='TimerBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(data,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['TimerBlock(Instance,T);'],mutate=mutate);e.step();e.step()
        self.assertEqual(e.memory.read('T.ACC'),10);self.assertTrue(e.memory.read('T.EnableIn'))

    def test_routine_harness_executes_st_timer_without_task_clock_aliasing(self):
        original=self.checked();e=Engine(original.project,'routine','MainProgram/MainRoutine');self.assertEqual(e.blockers,[])
        e.step();e.step();self.assertEqual(e.memory.read('T.ACC'),10)

    def test_res_of_fbd_timer_is_blocked_instead_of_guessing_ladder_reset(self):
        self.assertTrue(self.engine(['RES(T);']).blockers)

    def test_timer_lab_bundled_records_status_and_scan_transitions(self):
        from logixlab.server import SAMPLES as names
        self.assertIn('TimerLab',names);e=Engine(Project(SAMPLES/'TimerLab.L5X'));self.assertEqual(e.blockers,[])
        e.step();e.step();self.assertEqual(e.memory.read('On.ACC'),10);self.assertEqual(e.memory.read('Retained.ACC'),10)
        e.memory.write('TimerEnable',False);e.step();e.step()
        self.assertEqual(e.memory.read('On.ACC'),0);self.assertEqual(e.memory.read('Retained.ACC'),10)
        self.assertEqual(e.memory.read('Off.ACC'),10)


if __name__=='__main__':unittest.main()
