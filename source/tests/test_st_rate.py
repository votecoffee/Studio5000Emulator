"""RLIM rates, simulated/explicit timing, lifecycle and transactional history."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project,coerce
from logixlab.runtime import Engine
from logixlab.st_rate import FIELDS,MAX_DT,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,values):
    tag=E.SubElement(parent,'Tag',Name=name,DataType='RATE_LIMITER',TagType='Base')
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='RATE_LIMITER')
    for member,value in (default()|values).items():
        E.SubElement(data,'DataValueMember',Name=member,DataType=FIELDS[member],Value=str(float(value) if FIELDS[member]=='REAL' else int(value)))


class StructuredRateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        for name in ('T','U'):record(tags,name,{'IncRate':100.0,'DecRate':200.0}|dict(values or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['RLIM(T);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'rate.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e,dt=10):e.step(dt);return e.memory.read('T')

    def test_first_call_initializes_from_input_instead_of_saved_output(self):
        e=self.checked(values={'In':3.0,'Out':17.0});t=self.step(e)
        self.assertEqual((t['Out'],t['DeltaT']),(3.0,0.0));e.memory.write('T.In',10.0);self.assertEqual(self.step(e)['Out'],4.0)

    def test_increase_and_decrease_use_separate_per_second_rates(self):
        e=self.checked(values={'IncRate':8.0,'DecRate':16.0});self.step(e,125);e.memory.write('T.In',10.0)
        self.assertEqual(self.step(e,125)['Out'],1.0);self.assertEqual(self.step(e,125)['Out'],2.0)
        e.memory.write('T.In',-10.0);self.assertEqual(self.step(e,125)['Out'],0.0);self.assertEqual(self.step(e,125)['Out'],-2.0)

    def test_target_capture_does_not_overshoot_and_can_reverse_direction(self):
        e=self.checked();self.step(e);e.memory.write('T.In',0.5);self.assertEqual(self.step(e)['Out'],0.5)
        e.memory.write('T.In',-0.25);self.assertEqual(self.step(e)['Out'],-0.25);self.assertEqual(self.step(e)['Out'],-0.25)

    def test_zero_rates_hold_after_initialization(self):
        e=self.checked(values={'In':3.0,'IncRate':0.0,'DecRate':0.0});self.step(e)
        e.memory.write('T.In',10.0);self.assertEqual(self.step(e)['Out'],3.0)
        e.memory.write('T.In',-10.0);self.assertEqual(self.step(e)['Out'],3.0)

    def test_bypass_passes_input_and_seeds_the_next_ramp(self):
        e=self.checked();self.step(e);e.memory.write('T.ByPass',True);e.memory.write('T.In',10.0)
        self.assertEqual(self.step(e)['Out'],10.0);e.memory.write('T.In',-5.0);self.assertEqual(self.step(e)['Out'],-5.0)
        e.memory.write('T.ByPass',False);e.memory.write('T.In',10.0);self.assertEqual(self.step(e)['Out'],-4.0)

    def test_negative_rates_are_written_as_zero_with_diagnostics(self):
        for inc,dec,status in ((-1.0,2.0,3),(1.0,-2.0,5),(-1.0,-2.0,7)):
            with self.subTest(inc=inc,dec=dec):
                e=self.checked(values={'IncRate':inc,'DecRate':dec});t=self.step(e)
                self.assertEqual((t['IncRate'],t['DecRate'],t['Status']),(max(0.0,inc),max(0.0,dec),status))
                self.assertEqual(self.step(e)['Status'],0)

    def test_continuous_mode_uses_simulated_elapsed_seconds(self):
        e=self.checked();self.step(e);e.memory.write('T.In',100.0)
        t=self.step(e,50);self.assertEqual(t['DeltaT'],coerce(0.05,'REAL'));self.assertEqual(t['Out'],5.0)

    def test_periodic_mode_uses_configured_period_even_after_skipped_calls(self):
        def mutate(root):task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','20')
        e=self.checked(['IF StartPB THEN RLIM(T); END_IF;'],mutate=mutate)
        e.memory.write('StartPB',True);self.step(e,20);e.memory.write('T.In',100.0)
        e.memory.write('StartPB',False)
        for _ in range(5):self.step(e,20)
        e.memory.write('StartPB',True)
        t=self.step(e,20);self.assertEqual(t['DeltaT'],coerce(0.02,'REAL'));self.assertEqual(t['Out'],2.0)

    def test_skipped_continuous_calls_accumulate_elapsed_time(self):
        e=self.checked(['IF StartPB THEN RLIM(T); END_IF;']);e.memory.write('StartPB',True);self.step(e)
        e.memory.write('T.In',100.0);e.memory.write('StartPB',False);self.step(e,40)
        e.memory.write('StartPB',True);self.assertEqual(self.step(e)['Out'],5.0)

    def test_repeated_continuous_calls_at_one_timestamp_do_not_double_advance(self):
        e=self.checked(['FOR DisplayedPartCount := 0 TO 2 DO RLIM(T); END_FOR;']);self.step(e)
        e.memory.write('T.In',10.0);t=self.step(e);self.assertEqual(t['Out'],1.0);self.assertEqual(t['DeltaT'],0.0)

    def test_periodic_repeated_calls_each_use_the_configured_period(self):
        def mutate(root):task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','10')
        e=self.checked(['FOR DisplayedPartCount := 0 TO 2 DO RLIM(T); END_FOR;'],mutate=mutate)
        self.step(e);e.memory.write('T.In',10.0);self.assertEqual(self.step(e)['Out'],3.0)

    def test_oversample_repeated_calls_each_use_explicit_time(self):
        e=self.checked(['FOR DisplayedPartCount := 0 TO 2 DO RLIM(T); END_FOR;'],values={'TimingMode':1,'OversampleDT':0.125,'IncRate':2.0})
        self.step(e);e.memory.write('T.In',10.0);self.assertEqual(self.step(e)['Out'],0.75)

    def test_oversample_time_is_independent_of_simulation_step_duration(self):
        e=self.checked(values={'TimingMode':1,'OversampleDT':0.125,'IncRate':2.0});self.step(e)
        e.memory.write('T.In',10.0);self.assertEqual(self.step(e,10)['Out'],0.25);self.assertEqual(self.step(e,500)['Out'],0.5)

    def test_oversample_upper_bound_is_the_float32_represented_limit(self):
        e=self.checked(values={'TimingMode':1,'OversampleDT':4194.303});t=self.step(e)
        self.assertEqual(t['DeltaT'],MAX_DT);self.assertEqual(t['Status'],0)
        e.memory.write('T.OversampleDT',4194.304);self.assertTrue(self.step(e)['Status']<0)

    def test_invalid_oversample_holds_and_exposes_signed_high_status_bit(self):
        e=self.checked(values={'TimingMode':1,'OversampleDT':0.125});self.step(e);e.memory.write('T.In',10.0)
        for dt in (0.0,-1.0,5000.0):
            e.memory.write('T.OversampleDT',dt);t=self.step(e)
            self.assertEqual((t['Out'],t['DeltaT'],t['Status']),(0.0,0.0,-2147483647));self.assertTrue(e.memory.read('T.DeltaTInv'))
        e.memory.write('T.OversampleDT',0.125);t=self.step(e);self.assertEqual(t['Out'],10.0);self.assertEqual(t['Status'],0)

    def test_invalid_timing_hold_does_not_charge_the_gap_on_mode_change(self):
        e=self.checked(values={'TimingMode':1,'OversampleDT':0.0});self.step(e);e.memory.write('T.In',100.0)
        self.step(e,100);e.memory.write('T.TimingMode',0);self.assertEqual(self.step(e)['Out'],1.0)

    def test_invalid_mode_sets_diagnostic_and_real_time_sampling_is_blocked(self):
        e=self.checked();self.step(e);e.memory.write('T.In',100.0)
        for mode in (-1,3):
            e.memory.write('T.TimingMode',mode);t=self.step(e)
            self.assertEqual((t['Out'],t['DeltaT'],t['Status']),(0.0,0.0,134217729))
        e.memory.write('T.TimingMode',2);before=copy.deepcopy((e.memory.values,e.last_timer,e.scan_count,e.time_ms))
        with self.assertRaisesRegex(ModelError,'real time sampling'):e.step()
        self.assertEqual((e.memory.values,e.last_timer,e.scan_count,e.time_ms),before)

    def test_unused_oversample_and_rts_fields_can_remain_unknown(self):
        e=self.checked()
        e.memory.read('T').update(OversampleDT=None,RTSTime=None,RTSTimeStamp=None);self.step(e)
        e.memory.write('T.In',10.0);self.assertEqual(self.step(e)['Out'],1.0)

    def test_visible_output_writes_do_not_replace_hidden_previous_output(self):
        e=self.checked();self.step(e);e.memory.write('T.In',10.0);e.memory.write('T.Out',99.0)
        self.assertEqual(self.step(e)['Out'],1.0)

    def test_status_aliases_share_backing_word_including_bit_31(self):
        e=self.checked();e.memory.write('t.DeltaTInv',True);self.assertEqual(e.memory.read('T.Status'),-2147483648)
        e.memory.write('T.InstructFault',True);self.assertEqual(e.memory.read('T.Status'),-2147483647)
        e.memory.write('T.Status',134217729);self.assertTrue(e.memory.read('T.timingmodeinv'));self.assertFalse(e.memory.read('T.DeltaTInv'))
        self.step(e);self.assertEqual(e.memory.read('T.Status'),0)

    def test_separate_records_keep_independent_history(self):
        e=self.checked(['RLIM(T);','RLIM(U);']);self.step(e);e.memory.write('T.In',10.0);e.memory.write('U.In',-10.0)
        self.assertEqual(self.step(e)['Out'],1.0);self.assertEqual(e.memory.read('U.Out'),-2.0)

    def test_unknown_required_inputs_fault_and_unknown_outputs_can_be_initialized(self):
        for name in ('TimingMode','In','IncRate','DecRate','ByPass'):
            e=self.checked();e.memory.read('T')[name]=None;before=copy.deepcopy((e.memory.values,e.last_timer))
            with self.assertRaisesRegex(ModelError,'unknown'):e.step()
            self.assertEqual((e.memory.values,e.last_timer),before)
        e=self.checked(values={'In':7.0});e.memory.read('T')['Out']=None;self.assertEqual(self.step(e)['Out'],7.0)

    def test_nonfinite_or_wrong_value_types_are_not_silently_accepted(self):
        for name,value in (('In',float('nan')),('IncRate',float('inf')),('ByPass',1),('TimingMode',True)):
            e=self.checked();e.memory.read('T')[name]=value;before=repr((e.memory.values,e.last_timer))
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(repr((e.memory.values,e.last_timer)),before)

    def test_missing_exported_input_stays_unknown(self):
        def mutate(root):
            data=root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure');data.remove(data.find('DataValueMember[@Name="In"]'))
        e=self.checked(mutate=mutate);self.assertIsNone(e.memory.read('T')['In'])
        with self.assertRaisesRegex(ModelError,'In is unknown'):e.step()

    def test_prescan_and_run_reentry_reinitialize_only_on_next_reached_call(self):
        e=self.checked(values={'Out':17.0,'EnableOut':True},defer=True)
        self.assertTrue(e.memory.read('T.EnableIn'));e.enter_run();self.assertFalse(e.memory.read('T.EnableIn'))
        self.assertEqual(e.memory.read('T.Out'),17.0);self.step(e);e.memory.write('T.In',10.0);self.assertEqual(self.step(e)['Out'],1.0)
        e.enter_run();self.assertEqual(e.last_timer,{});self.assertEqual(e.memory.read('T.Out'),1.0);self.assertEqual(self.step(e)['Out'],10.0)

    def test_late_fault_restores_elapsed_history_in_both_directions(self):
        for target,expected in ((10.0,1.0),(-10.0,-2.0)):
            e=self.checked(['RLIM(T);','SpeedCommand := 1 / SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.step(e)
            e.memory.write('T.In',target);e.memory.write('SpeedSetpoint',0)
            before=copy.deepcopy((e.memory.values,e.last_timer,e.scan_count,e.time_ms,e.scheduler_description()))
            with self.assertRaisesRegex(ModelError,'zero'):e.step()
            self.assertEqual((e.memory.values,e.last_timer,e.scan_count,e.time_ms,e.scheduler_description()),before)
            e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)['Out'],expected)

    def test_first_call_fault_does_not_consume_initialization(self):
        e=self.checked(['RLIM(T);','SpeedCommand := 1 / SpeedSetpoint;'],values={'In':7.0});e.memory.write('SpeedSetpoint',0)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.last_timer,{});e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)['Out'],7.0)

    def test_budget_failures_restore_scan_and_prescan_history(self):
        e=self.checked(['RLIM(T);','SpeedCommand := 7;']);self.step(e);e.memory.write('T.In',10.0)
        before=copy.deepcopy((e.memory.values,e.last_timer));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual((e.memory.values,e.last_timer),before);e.instruction_limit=100;self.step(e)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan.*budget'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)

    def test_for_status_dependency_and_unsupported_operands_are_blocked(self):
        self.assertTrue(self.engine(['FOR DisplayedPartCount := 0 TO T.Status DO RLIM(T); END_FOR;']).blockers)
        for line in ('RLIM();','RLIM(T,U);','RLIM(Parts);','RLIM(T.Out);','RLIM(3);','RES(T);'):
            self.assertTrue(self.engine([line]).blockers,line)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="T"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)

    def test_other_profiles_redefinitions_and_ladder_forms_are_blocked(self):
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def profile(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version)
            self.assertTrue(self.engine(mutate=profile).blockers)
        def redefine(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='RATE_LIMITER',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
        self.assertTrue(self.engine(mutate=redefine).blockers)
        def ladder(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');logic(routine,[]);routine.set('Type','RLL');routine.remove(routine.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='RLIM(T);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_program_local_alias_uses_the_resolved_record_history(self):
        def mutate(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="T"]');tags.remove(tag)
            root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='AliasT',TagType='Alias',AliasFor='Program:MainProgram.T')
        e=self.checked(['RLIM(AliasT);'],mutate=mutate);e.step();e.memory.write('Program:MainProgram.T.In',10.0);e.step()
        self.assertEqual(e.memory.read('Program:MainProgram.T.Out'),1.0)

    def test_arrays_and_nested_udt_members_have_independent_history(self):
        def mutate(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='HolderType',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='Rate',DataType='RATE_LIMITER',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Holder',DataType='HolderType',TagType='Base')
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='HolderType')
            item=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="U"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Rate');data.append(item)
            t=root.find('./Controller/Tags/Tag[@Name="T"]');data=t.find('Data');item=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated');t.set('Dimensions','2')
            a=E.SubElement(data,'Array',DataType='RATE_LIMITER',Dimensions='2')
            for i in range(2):E.SubElement(a,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['RLIM(T[0]);','RLIM(T[1]);','RLIM(Holder.Rate);'],mutate=mutate);e.step()
        e.memory.write('T[1].In',10.0);e.memory.write('Holder.Rate.In',-10.0);e.step()
        self.assertEqual((e.memory.read('T[0].Out'),e.memory.read('T[1].Out'),e.memory.read('Holder.Rate.Out')),(0.0,1.0,-2.0))
        for ref,dtype in (('Holder.Rate.DeltaT','REAL'),('Holder.Rate.TimingMode','DINT'),('T[1].DeltaTInv','BOOL')):
            self.assertEqual(e.memory.resolve(ref)[2],dtype)

    def test_aoi_inout_and_routine_harness_share_the_supplied_record(self):
        def mutate(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions')
            if definitions is None:definitions=E.SubElement(root.find('Controller'),'AddOnInstructionDefinitions')
            d=E.SubElement(definitions,'AddOnInstructionDefinition',Name='RateBlock',Class='Standard',Revision='1.0',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            p=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='State',TagType='Base',DataType='RATE_LIMITER',Usage='InOut',Required='true',Visible='true')
            E.SubElement(d,'LocalTags');logic(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='ST'),['RLIM(State);'])
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='RateBlock',TagType='Base')
            data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='RateBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(data,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['RateBlock(Instance,T);'],mutate=mutate);self.step(e);e.memory.write('T.In',10.0)
        self.assertEqual(self.step(e)['Out'],1.0)
        harness=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(harness.blockers,[])
        self.step(harness);harness.memory.write('T.In',10.0);self.assertEqual(self.step(harness)['Out'],1.0)

    def test_detached_routine_replacement_preserves_clock_and_hidden_previous_output(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def mutate(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0]
            main.set('Type','RLL');main.remove(main.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(RateLogic,0);'
            logic(E.SubElement(routines,'Routine',Name='RateLogic',Type='ST'),['RLIM(T);'])
        e=self.checked(mutate=mutate);self.step(e);e.memory.write('T.In',10.0);self.assertEqual(self.step(e)['Out'],1.0)
        before=copy.deepcopy((e.memory.values,e.last_timer));neutral=['JSR(RateLogic,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);candidate.step();self.assertEqual(candidate.memory.read('T.Out'),2.0)
        self.assertEqual((e.memory.values,e.last_timer),before)

    def test_rate_lab_exposes_ramps_bypass_timing_and_status(self):
        from logixlab.server import SAMPLES as names
        self.assertIn('RateLab',names);e=Engine(Project(SAMPLES/'RateLab.L5X'));self.assertEqual(e.blockers,[])
        e.step();e.memory.write('Target',10.0);e.step();self.assertEqual(e.memory.read('Output'),1.0)
        e.memory.write('Bypass',True);e.step();self.assertEqual(e.memory.read('Output'),10.0)
        for name,value in (('Bypass',False),('Target',100.0),('TimingMode',1),('SampleTime',0.125)):e.memory.write(name,value)
        e.step();self.assertEqual(e.memory.read('Output'),22.5)
        e.memory.write('SampleTime',0.0);e.step();self.assertTrue(e.memory.read('TimeInvalid'));self.assertEqual(e.memory.read('Output'),22.5)

    def test_builtin_classification_instruction_counts_and_report_are_qualified(self):
        e=self.checked();self.assertNotIn('RATE_LIMITER',e.project.data_only_types);self.assertNotIn('rate_limiter',e.project.udts)
        self.assertEqual(set(e.memory.read('T')),set(FIELDS));self.assertEqual(len(ARITIES),99)
        self.assertEqual(set(ST_ONLY_ARITIES),{'TONR','TOFR','RTOR','CTUD','OSRI','OSFI','SCL','HLL','SNEG','SSUM','RLIM'})
        profile=e.report()['st_rate'];self.assertEqual(profile['instructions'],['RLIM']);self.assertFalse(profile['native_runtime_parity'])
        self.assertEqual(profile['status_aliases']['DeltaTInv'],'Status.31')


if __name__=='__main__':unittest.main()
