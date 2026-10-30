"""Enhanced selection, control arbitration and rate-of-change execution."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab import st_select,st_derivative
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'
RECORDS={'S':('SELECT_ENHANCED',st_select),'D':('DERIVATIVE',st_derivative)}


def record(parent,name,dtype,module,values):
    tag=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType=dtype)
    obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType=dtype)
    for member,value in (module.default()|dict(values or {})).items():
        E.SubElement(obj,'DataValueMember',Name=member,DataType=module.FIELDS[member],Value=str(int(value)) if isinstance(value,bool) else str(value))
    return tag


class StructuredProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,s=None,d=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        record(tags,'S','SELECT_ENHANCED',st_select,dict(SelectorMode=1,InsUsed=3,In1=10,In2=20,In3=30)|dict(s or {}))
        record(tags,'D','DERIVATIVE',st_derivative,dict(TimingMode=1,OversampleDT=0.25)|dict(d or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['ESEL(S); DERV(D);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'process.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e,dt=250):e.step(dt);return e.memory.read('S'),e.memory.read('D')

    def test_esel_high_low_and_first_input_ties(self):
        for mode,expected,index in ((1,30,2),(2,10,1)):
            e=self.checked(s={'SelectorMode':mode,'In2':30,'In3':30});s,_=self.step(e)
            self.assertEqual((s['Out'],s['SelectedIn'],s['Status']),(expected,index,0))

    def test_esel_healthy_prefix_excludes_faulted_and_unused_values(self):
        e=self.checked(s={'In3Fault':True,'In6':1000});s,_=self.step(e);self.assertEqual((s['Out'],s['SelectedIn']),(20,2))
        e.memory.write('S.In2Fault',True);s,_=self.step(e);self.assertEqual((s['Out'],s['SelectedIn']),(10,1))

    def test_esel_odd_median_and_even_median_choose_available_first_found(self):
        for values,expected,index in (((10,30,20),20,3),((10,3,20,7),10,1),((10,20,20,30),20,2)):
            s={'SelectorMode':3,'InsUsed':len(values)}|{'In'+str(i):v for i,v in enumerate(values,1)}
            e=self.checked(s=s);actual,_=self.step(e);self.assertEqual((actual['Out'],actual['SelectedIn']),(expected,index))

    def test_esel_average_uses_only_healthy_values_and_selected_zero(self):
        e=self.checked(s={'SelectorMode':4,'In2Fault':True});s,_=self.step(e)
        self.assertEqual((s['Out'],s['SelectedIn']),(20,0))
        e.memory.write('S.In1Fault',True);s,_=self.step(e);self.assertEqual(s['Out'],30)

    def test_esel_all_used_faulted_holds_visible_output_and_selection(self):
        e=self.checked();self.step(e)
        for i in range(1,4):e.memory.write('S.In'+str(i)+'Fault',True)
        e.memory.write('S.Out',77);e.memory.write('S.SelectedIn',5);s,_=self.step(e)
        self.assertEqual((s['Out'],s['SelectedIn'],s['Status']),(77,5,3))
        e.memory.write('S.In2Fault',False);s,_=self.step(e);self.assertEqual((s['Out'],s['SelectedIn'],s['Status']),(20,2,0))

    def test_esel_manual_uses_operator_on_startup_and_selector_zero_holds(self):
        e=self.checked(s={'SelectorMode':0,'ProgOper':True,'ProgSelector':3,'OperSelector':2});s,_=self.step(e)
        self.assertEqual((s['Out'],s['SelectedIn'],s['ProgOper']),(20,2,False))
        e.memory.write('S.OperSelector',0);e.memory.write('S.In2',99);s,_=self.step(e)
        self.assertEqual((s['Out'],s['SelectedIn']),(20,2))

    def test_esel_manual_profile_ignores_count_and_health_but_reports_count(self):
        e=self.checked(s={'SelectorMode':0,'OperSelector':6,'InsUsed':0,'In6':60,'In6Fault':True});s,_=self.step(e)
        self.assertEqual((s['Out'],s['SelectedIn'],s['Status']),(60,6,5))

    def test_esel_program_requests_lock_control_and_operator_requests_clear(self):
        e=self.checked(s={'SelectorMode':0,'OperSelector':1,'ProgSelector':3,'ProgProgReq':True,'OperOperReq':True})
        s,_=self.step(e);self.assertEqual((s['Out'],s['ProgOper'],s['OperOperReq']),(30,True,False))
        e.memory.write('S.OperOperReq',True);s,_=self.step(e);self.assertTrue(s['ProgOper']);self.assertFalse(s['OperOperReq'])
        e.memory.write('S.ProgOperReq',True);s,_=self.step(e);self.assertEqual((s['Out'],s['ProgOper']),(10,False))

    def test_esel_operator_requests_switch_only_without_program_lock(self):
        e=self.checked(s={'SelectorMode':0,'ProgSelector':3,'OperSelector':2});self.step(e)
        e.memory.write('S.OperProgReq',True);s,_=self.step(e);self.assertEqual((s['Out'],s['ProgOper'],s['OperProgReq']),(30,True,False))
        e.memory.write('S.OperOperReq',True);s,_=self.step(e);self.assertEqual((s['Out'],s['ProgOper'],s['OperOperReq']),(20,False,False))

    def test_esel_simultaneous_operator_requests_follow_current_control(self):
        e=self.checked(s={'OperProgReq':True,'OperOperReq':True});s,_=self.step(e);self.assertTrue(s['ProgOper'])
        e.memory.write('S.OperProgReq',True);e.memory.write('S.OperOperReq',True);s,_=self.step(e);self.assertFalse(s['ProgOper'])

    def test_esel_override_is_level_sensitive_and_value_reset_consumes_requests(self):
        e=self.checked(s={'OperSelector':2,'ProgOverrideReq':True});s,_=self.step(e);self.assertEqual((s['Out'],s['Override']),(20,True))
        e.memory.write('S.ProgOverrideReq',False);s,_=self.step(e);self.assertEqual((s['Out'],s['Override']),(30,False))
        for name in ('ProgProgReq','ProgOperReq','ProgOverrideReq','ProgValueReset'):e.memory.write('S.'+name,True)
        s,_=self.step(e);self.assertEqual((s['Out'],s['ProgOper'],s['Override']),(20,False,True))
        self.assertTrue(all(not s[name] for name in ('ProgProgReq','ProgOperReq','ProgOverrideReq')))
        s,_=self.step(e);self.assertEqual((s['Out'],s['Override']),(30,False))

    def test_esel_invalid_count_mode_and_selectors_have_independent_status(self):
        e=self.checked(s={'InsUsed':0,'SelectorMode':9,'ProgSelector':7,'OperSelector':-1,'Out':55,'SelectedIn':4})
        s,_=self.step(e);self.assertEqual((s['Out'],s['SelectedIn'],s['Status']),(55,4,61))
        e.memory.write('S.InsUsed',3);e.memory.write('S.SelectorMode',1);s,_=self.step(e);self.assertEqual((s['Out'],s['Status']),(30,49))
        e.memory.write('S.SelectorMode',0);s,_=self.step(e);self.assertEqual((s['Out'],s['Status']),(30,49))

    def test_esel_unknown_bad_or_unused_values_are_not_read(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="S"]/Data/Structure')
            for name in ('In3','In6','In6Fault'):obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
        e=self.checked(s={'In3Fault':True},mutate=missing);self.assertEqual(self.step(e)[0]['Out'],20)
        e.memory.write('S.In3Fault',False)
        with self.assertRaisesRegex(ModelError,'In3 is unknown'):self.step(e)

    def test_esel_unknown_health_is_not_false_and_manual_reads_selected_only(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="S"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="In1Fault"]'))
        e=self.checked(mutate=missing)
        with self.assertRaisesRegex(ModelError,'In1Fault is unknown'):self.step(e)
        e.memory.write('S.SelectorMode',0);e.memory.write('S.OperSelector',2);self.assertEqual(self.step(e)[0]['Out'],20)

    def test_derv_startup_samples_without_initial_spike_then_signed_gain(self):
        e=self.checked(d={'In':100,'Out':99});self.assertEqual(self.step(e)[1]['Out'],0)
        e.memory.write('D.In',102);self.assertEqual(self.step(e)[1]['Out'],8)
        e.memory.write('D.Gain',-2);e.memory.write('D.In',101);self.assertEqual(self.step(e)[1]['Out'],8)
        self.assertEqual(self.step(e)[1]['Out'],0)

    def test_derv_bypass_tracks_input_and_releases_without_stale_spike(self):
        e=self.checked(d={'ByPass':True,'In':10});self.assertEqual(self.step(e)[1]['Out'],10)
        e.memory.write('D.In',20);self.assertEqual(self.step(e)[1]['Out'],20)
        e.memory.write('D.ByPass',False);e.memory.write('D.In',21);self.assertEqual(self.step(e)[1]['Out'],4)

    def test_derv_zero_and_invalid_intervals_hold_output_but_sample_input(self):
        e=self.checked();self.step(e);e.memory.write('D.In',4);self.assertEqual(self.step(e)[1]['Out'],16)
        for dt,status in ((0,0),(-1,-2147483647),(5000,-2147483647)):
            e.memory.write('D.OversampleDT',dt);e.memory.write('D.In',e.memory.read('D.In')+1);d=self.step(e)[1]
            self.assertEqual((d['Out'],d['DeltaT'],d['Status']),(16,0,status))
        e.memory.write('D.OversampleDT',0.25);e.memory.write('D.In',8);self.assertEqual(self.step(e)[1]['Out'],4)

    def test_derv_elapsed_timing_accounts_for_skipped_duration(self):
        e=self.checked(['IF StartPB THEN DERV(D); END_IF;'],d={'TimingMode':0})
        e.memory.write('StartPB',True);self.step(e);e.memory.write('StartPB',False);self.step(e);self.step(e)
        e.memory.write('D.In',6);e.memory.write('StartPB',True);d=self.step(e)[1];self.assertEqual((d['Out'],d['DeltaT']),(8,0.75))

    def test_derv_periodic_and_repeated_oversample_calls(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','100')
        e=self.checked(d={'TimingMode':0},mutate=periodic);self.step(e,100);e.memory.write('D.In',1);d=self.step(e,100)[1]
        self.assertEqual(d['Out'],10);self.assertAlmostEqual(d['DeltaT'],0.1,places=6)
        e=self.checked(['DERV(D); D.In:=D.In+1; DERV(D);']);self.assertEqual(self.step(e)[1]['Out'],4)

    def test_derv_same_timestamp_elapsed_calls_sample_without_calculation(self):
        e=self.checked(['DERV(D); D.In:=D.In+1; DERV(D);'],d={'TimingMode':0});d=self.step(e)[1]
        self.assertEqual((d['Out'],d['DeltaT']),(0,0))
        self.assertEqual(self.step(e)[1]['Out'],0)

    def test_derv_invalid_mode_holds_and_bypass_still_passes_input(self):
        e=self.checked(d={'TimingMode':3,'In':8,'ByPass':True});d=self.step(e)[1]
        self.assertEqual((d['Out'],d['DeltaT'],d['Status']),(8,0,134217729))
        e.memory.write('D.ByPass',False);e.memory.write('D.In',10);self.assertEqual(self.step(e)[1]['Out'],8)
        e.memory.write('D.TimingMode',2)
        with self.assertRaisesRegex(ModelError,'real time sampling'):self.step(e)

    def test_derv_unused_gain_rts_and_oversample_may_be_unknown(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="D"]/Data/Structure')
            for name in ('Gain','RTSTime','RTSTimeStamp','OversampleDT'):obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
        e=self.checked(d={'TimingMode':0,'ByPass':True,'In':8},mutate=missing);self.assertEqual(self.step(e)[1]['Out'],8)
        e.memory.write('D.ByPass',False)
        with self.assertRaisesRegex(ModelError,'Gain is unknown'):self.step(e)

    def test_derv_overflow_rolls_back_then_bypass_recovers(self):
        e=self.checked(d={'Gain':3.4e38});self.step(e);e.memory.write('D.In',2)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
        with self.assertRaisesRegex(ModelError,'REAL'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)
        e.memory.write('D.ByPass',True);self.assertEqual(self.step(e)[1]['Out'],2)

    def test_derv_maximum_interval_and_backwards_clock(self):
        e=self.checked(d={'OversampleDT':st_derivative.MAX_DT});self.assertEqual(self.step(e)[1]['DeltaT'],st_derivative.MAX_DT)
        e=self.checked(d={'TimingMode':0});self.step(e);next(v for k,v in e.last_timer.items() if k[0]=='ST-DERIVATIVE')['at']=1000
        with self.assertRaisesRegex(ModelError,'backwards'):self.step(e)

    def test_unknown_controls_and_nonfinite_inputs_fault_without_history_commit(self):
        for ref,value in (('S.ProgOperReq',None),('S.SelectorMode',True),('S.In1',float('nan')),('D.In',None),('D.ByPass',0)):
            e=self.checked();key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,value)
            with self.subTest(ref=ref),self.assertRaises(ModelError):self.step(e)
            self.assertEqual((e.last_timer,e.time_ms,e.scan_count),({},0,0))

    def test_status_aliases_types_and_reports(self):
        e=self.checked();self.assertEqual((len(st_select.FIELDS),len(st_derivative.FIELDS)),(29,12))
        for tag,(dtype,module) in RECORDS.items():
            self.assertNotIn(dtype,e.project.data_only_types)
            for member,kind in module.FIELDS.items():self.assertEqual(e.memory.resolve(tag+'.'+member)[2],kind)
        e.memory.write('S.InsFaulted',True);self.assertEqual(e.memory.read('S.Status'),2)
        e.memory.write('d.deltatinv',True);self.assertEqual(e.memory.read('D.Status'),-2147483648)
        self.step(e);self.assertEqual((e.memory.read('S.Status'),e.memory.read('D.Status')),(0,0))
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,27))
        for name in ('st_select','st_derivative'):self.assertFalse(e.report()[name]['native_runtime_parity'])

    def test_enables_are_forced_and_skipped_calls_retain_requests_and_history(self):
        e=self.checked(['IF StartPB THEN ESEL(S); DERV(D); END_IF;']);e.memory.write('StartPB',True);self.step(e)
        for tag in RECORDS:
            for member in ('EnableIn','EnableOut'):e.memory.write(tag+'.'+member,False)
        e.memory.write('StartPB',False);e.memory.write('S.OperProgReq',True);before=copy.deepcopy(e.last_timer);self.step(e)
        self.assertEqual(e.last_timer,before);self.assertTrue(e.memory.read('S.OperProgReq'))
        e.memory.write('StartPB',True);self.step(e);self.assertFalse(e.memory.read('S.OperProgReq'))
        self.assertTrue(all(e.memory.read(tag+'.'+member) for tag in RECORDS for member in ('EnableIn','EnableOut')))

    def test_run_reentry_and_failed_prescan_restore_prior_states(self):
        e=self.checked(s={'ProgProgReq':True},d={'In':8},defer=True);self.assertEqual(e.last_timer,{})
        self.step(e);e.memory.write('D.In',10);self.step(e);e.memory.write('S.ProgProgReq',False)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan rolled back'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)
        e.instruction_limit=100;e.fault='';e.enter_run();s,d=self.step(e);self.assertEqual((s['ProgOper'],d['Out']),(False,0))

    def test_late_fault_restores_consumed_requests_control_and_derivative_history(self):
        e=self.checked(['ESEL(S); DERV(D); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.step(e)
        e.memory.write('S.OperProgReq',True);e.memory.write('D.In',8);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);s,d=self.step(e);self.assertEqual((s['ProgOper'],s['OperProgReq'],d['Out']),(True,False,32))

    def test_instruction_budget_restores_first_blocks_control_update(self):
        e=self.checked(s={'OperProgReq':True});e.instruction_limit=1
        before=copy.deepcopy((e.memory.values,e.last_timer))
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer),before)

    def test_constants_redefinitions_wrong_types_arity_and_ladder_forms_block(self):
        for text in ('ESEL();','ESEL(D);','DERV(S);','DERV(D,S);','SEL(S);','MUX(S);'):
            self.assertTrue(self.engine([text]).blockers)
        for tag,(dtype,_) in RECORDS.items():
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{tag}"]').set('Constant','true')
            self.assertTrue(self.engine(mutate=constant).blockers)
            def redefine(root):
                m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name=dtype,Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
            self.assertTrue(self.engine(mutate=redefine).blockers)
        def ladder(root):
            t=root.find('./Controller/Programs/Program/Routines/Routine');t.remove(t.find('STContent'));t.set('Type','RLL');E.SubElement(E.SubElement(E.SubElement(t,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='ESEL(S);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_other_controller_profiles_block(self):
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_st_for_cannot_modify_its_bounds_via_block_record(self):
        self.assertTrue(self.engine(['FOR SpeedCommand:=0 TO S.SelectedIn DO ESEL(S); END_FOR;']).blockers)
        self.assertTrue(self.engine(['FOR SpeedCommand:=0 TO D.Status DO DERV(D); END_FOR;']).blockers)

    def test_alias_local_and_aoi_bindings_share_resolved_control_and_history(self):
        def setup(root):
            tags=root.find('./Controller/Tags');tag=tags.find('./Tag[@Name="S"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='AliasS',TagType='Alias',AliasFor='Program:MainProgram.S')
            a=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='SelectBlock',Revision='1.0');p=E.SubElement(a,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='State',TagType='Base',DataType='SELECT_ENHANCED',Usage='InOut',Required='true',Visible='true')
            E.SubElement(a,'LocalTags');logic(E.SubElement(E.SubElement(a,'Routines'),'Routine',Name='Logic',Type='ST'),['ESEL(State);'])
            t=E.SubElement(tags,'Tag',Name='Instance',DataType='SelectBlock',TagType='Base');obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='SelectBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['SelectBlock(Instance,AliasS); DERV(D);'],s={'OperProgReq':True},mutate=setup);e.step(250)
        self.assertEqual((e.memory.read('AliasS.Out'),e.memory.read('AliasS.ProgOper')),(30,True))
        h=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(h.blockers,[]);h.step(250);self.assertEqual(h.memory.read('AliasS.Out'),30)

    def test_indirect_arrays_and_nested_records_keep_separate_histories(self):
        def nested(root):
            tags=root.find('./Controller/Tags');members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='ProcessHolder',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Rate',DataType='DERIVATIVE',Dimension='0')
            tag=E.SubElement(tags,'Tag',Name='Holder',TagType='Base',DataType='ProcessHolder');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='ProcessHolder')
            item=copy.deepcopy(tags.find('./Tag[@Name="D"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Rate');obj.append(item)
            tag=tags.find('./Tag[@Name="D"]');tag.set('Dimensions','2');data=tag.find('Data');item=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated');arr=E.SubElement(data,'Array',DataType='DERIVATIVE',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['DERV(D[SpeedCommand]); DERV(Holder.Rate);'],mutate=nested)
        for i in (0,1):e.memory.write('SpeedCommand',i);e.step(250)
        e.memory.write('SpeedCommand',0);e.memory.write('D[0].In',2);e.memory.write('Holder.Rate.In',3);e.step(250)
        self.assertEqual(tuple(e.memory.read(ref) for ref in ('D[0].Out','D[1].Out','Holder.Rate.Out')),(8,0,12))

    def event_engine(self,fault=False):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='ProcessEvent',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST');lines=['S.OperProgReq:=TRUE; ESEL(S); D.In:=4; DERV(D);']
            if fault:lines.append('SpeedCommand:=1/SpeedSetpoint;')
            logic(routine,lines);task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='ProcessEventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='ProcessEvent')
        return self.checked(['DERV(D); EVENT(ProcessEventTask); D.In:=5; DERV(D);'],mutate=event)

    def test_event_dispatch_shares_control_and_input_history(self):
        e=self.event_engine();s,d=self.step(e);self.assertEqual((s['ProgOper'],s['OperProgReq'],d['Out']),(True,False,4))

    def test_event_failure_restores_consumed_request_history_and_scheduler(self):
        e=self.event_engine(fault=True);e.memory.write('SpeedSetpoint',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)[1]['Out'],4)

    def test_detached_replacement_preserves_control_and_derivative_history(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(Process,0);'
            logic(E.SubElement(routines,'Routine',Name='Process',Type='ST'),['ESEL(S); DERV(D);'])
        e=self.checked(s={'OperProgReq':True},mutate=caller);self.step(e);e.memory.write('D.In',4);self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer))
        neutral=['JSR(Process,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf-8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        candidate.memory.write('D.In',5);s,d=self.step(candidate);self.assertEqual((s['ProgOper'],d['Out']),(True,4))

    def test_public_process_lab_chains_selection_and_rate_of_change(self):
        e=Engine(Project(SAMPLES/'ProcessLab.L5X'));self.assertEqual(e.blockers,[]);e.step(250)
        self.assertEqual((e.memory.read('SelectedValue'),e.memory.read('ChangePerSecond')),(30,0))
        e.memory.write('Sensor2',40);e.step(250);self.assertEqual((e.memory.read('SelectedValue'),e.memory.read('ChangePerSecond')),(40,40))


if __name__=='__main__':unittest.main()
