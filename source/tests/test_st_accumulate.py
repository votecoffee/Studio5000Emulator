"""Accumulation arithmetic, timing, state isolation and transactional failures."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_accumulate import MAX_DT,MAX_REAL,SCHEMAS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'
TAGS={'A':'UP_DOWN_ACCUM','I':'INTEGRATOR'}


def record(parent,name,dtype,values=None):
    tag=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType=dtype)
    obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType=dtype)
    for member,value in (default(dtype)|dict(values or {})).items():
        E.SubElement(obj,'DataValueMember',Name=member,DataType=SCHEMAS[dtype][member],
                     Value=str(int(value)) if isinstance(value,bool) else str(value))
    return tag


class StructuredAccumulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,a=None,i=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        record(tags,'A','UP_DOWN_ACCUM',a);record(tags,'I','INTEGRATOR',dict(IGain=1,TimingMode=1,OversampleDT=0.25)|dict(i or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['UPDN(A); INTG(I);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'accumulate.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e,dt=250):
        e.step(dt);return e.memory.read('A.Out'),e.memory.read('I.Out')

    def test_updn_zero_start_then_add_subtract_and_signed_inputs(self):
        e=self.checked(a={'Out':100,'InPlus':5,'InMinus':2})
        self.assertEqual(self.step(e)[0],3);self.assertEqual(self.step(e)[0],6)
        e.memory.write('A.InPlus',-4);e.memory.write('A.InMinus',-1);self.assertEqual(self.step(e)[0],3)

    def test_updn_initialize_overrides_hold_and_held_initialize_reloads(self):
        e=self.checked(a={'Initialize':True,'InitialValue':20,'Hold':True,'InPlus':5})
        self.assertEqual(self.step(e)[0],20);e.memory.write('A.InitialValue',-10);self.assertEqual(self.step(e)[0],-10)
        e.memory.write('A.Initialize',False);self.assertEqual(self.step(e)[0],-10)
        e.memory.write('A.Hold',False);self.assertEqual(self.step(e)[0],-5)

    def test_updn_hold_before_first_call_starts_zero(self):
        e=self.checked(a={'Hold':True,'Out':100});self.assertEqual(self.step(e)[0],0)

    def test_updn_same_timestamp_calls_each_accumulate(self):
        e=self.checked(['UPDN(A); UPDN(A); UPDN(A);'],a={'InPlus':2});self.assertEqual(self.step(e)[0],6)

    def test_updn_conditional_reads_do_not_fabricate_unknown_inputs(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="A"]/Data/Structure')
            for name in ('InPlus','InMinus','Hold'):obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
        e=self.checked(a={'Initialize':True,'InitialValue':8},mutate=missing);self.assertEqual(self.step(e)[0],8)
        e.memory.write('A.Initialize',False)
        with self.assertRaisesRegex(ModelError,'Hold is unknown'):self.step(e)
        e.memory.write('A.Hold',True);self.assertEqual(self.step(e)[0],8)
        e.memory.write('A.Hold',False)
        with self.assertRaisesRegex(ModelError,'InPlus is unknown'):self.step(e)

    def test_updn_overflow_rolls_back_and_reinitialization_recovers(self):
        e=self.checked(a={'InPlus':MAX_REAL});self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
        with self.assertRaisesRegex(ModelError,'REAL'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)
        e.memory.write('A.Initialize',True);e.memory.write('A.InitialValue',0);self.assertEqual(self.step(e)[0],0)

    def test_intg_startup_establishes_zero_input_and_output_history(self):
        e=self.checked(i={'In':8,'Out':99});self.assertEqual(self.step(e)[1],0)
        self.assertEqual(self.step(e)[1],1);self.assertEqual(self.step(e)[1],3)

    def test_intg_trapezoidal_area_uses_previous_sample(self):
        e=self.checked();self.step(e);e.memory.write('I.In',8);self.assertEqual(self.step(e)[1],1)
        e.memory.write('I.In',4);self.assertEqual(self.step(e)[1],2.5)
        e.memory.write('I.In',-4);self.assertEqual(self.step(e)[1],2.5)
        self.assertEqual(self.step(e)[1],1.5)

    def test_intg_gain_and_initialize_seed_previous_input(self):
        e=self.checked(i={'Initialize':True,'InitialValue':10,'In':4,'IGain':2})
        self.assertEqual(self.step(e)[1],10);self.assertEqual(self.step(e)[1],10)
        e.memory.write('I.Initialize',False);self.assertEqual(self.step(e)[1],12)

    def test_intg_directional_holds_allow_movement_in_opposite_direction(self):
        e=self.checked(i={'Initialize':True,'In':4});self.step(e);e.memory.write('I.Initialize',False)
        e.memory.write('I.HoldHigh',True);self.assertEqual(self.step(e)[1],0)
        e.memory.write('I.In',-4);self.assertEqual(self.step(e)[1],0);self.assertEqual(self.step(e)[1],-1)
        e.memory.write('I.HoldHigh',False);e.memory.write('I.HoldLow',True);self.assertEqual(self.step(e)[1],-1)
        e.memory.write('I.In',4);self.step(e);self.assertEqual(self.step(e)[1],0)

    def test_intg_both_directional_holds_sample_input_without_moving(self):
        e=self.checked(i={'HoldHigh':True,'HoldLow':True});self.step(e)
        e.memory.write('I.In',10);self.assertEqual(self.step(e)[1],0)
        e.memory.write('I.HoldHigh',False);e.memory.write('I.HoldLow',False);self.assertEqual(self.step(e)[1],2.5)

    def test_intg_limits_are_inclusive_and_do_not_wind_up(self):
        e=self.checked(i={'HighLimit':1,'LowLimit':-1});self.step(e);e.memory.write('I.In',8)
        self.assertEqual(self.step(e)[1],1);self.assertTrue(e.memory.read('I.HighAlarm'));self.assertEqual(self.step(e)[1],1)
        e.memory.write('I.In',-8);self.assertEqual(self.step(e)[1],1);self.assertEqual(self.step(e)[1],-1)
        self.assertTrue(e.memory.read('I.LowAlarm'));self.assertFalse(e.memory.read('I.HighAlarm'))

    def test_intg_invalid_limits_set_both_alarms_and_low_output(self):
        for high,low in ((3,3),(2,3)):
            e=self.checked(i={'HighLimit':high,'LowLimit':low});self.assertEqual(self.step(e)[1],low)
            self.assertEqual((e.memory.read('I.Status'),e.memory.read('I.HighAlarm'),e.memory.read('I.LowAlarm')),(5,True,True))

    def test_intg_initialize_precedes_limits_and_directional_holds_in_profile(self):
        e=self.checked(i={'Initialize':True,'InitialValue':20,'HighLimit':1,'LowLimit':2,'HoldHigh':True,'HoldLow':True})
        self.assertEqual(self.step(e)[1],20);self.assertEqual(e.memory.read('I.Status'),5)
        e.memory.write('I.Initialize',False);self.assertEqual(self.step(e)[1],2)

    def test_intg_negative_gain_is_zeroed_and_holds_then_clears_status(self):
        e=self.checked(i={'Initialize':True,'InitialValue':5,'In':4});self.step(e);e.memory.write('I.Initialize',False)
        e.memory.write('I.IGain',-1);self.assertEqual(self.step(e)[1],5)
        self.assertEqual((e.memory.read('I.IGain'),e.memory.read('I.Status')),(0,3))
        self.assertEqual(self.step(e)[1],5);self.assertEqual(e.memory.read('I.Status'),0)

    def test_intg_zero_and_invalid_oversampling_hold_input_history(self):
        e=self.checked();self.step(e);e.memory.write('I.In',8)
        for dt,status in ((0,0),(-1,-2147483647),(5000,-2147483647)):
            e.memory.write('I.OversampleDT',dt);self.assertEqual(self.step(e)[1],0)
            self.assertEqual((e.memory.read('I.DeltaT'),e.memory.read('I.Status')),(0,status))
        e.memory.write('I.OversampleDT',0.25);self.assertEqual(self.step(e)[1],1)

    def test_intg_invalid_modes_hold_and_rts_is_explicitly_blocked(self):
        for mode in (-1,3):
            e=self.checked(i={'TimingMode':mode});self.assertEqual(self.step(e)[1],0)
            self.assertEqual(e.memory.read('I.Status'),134217729)
        e=self.checked(i={'TimingMode':2});before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'real time sampling'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer),(before,{}))

    def test_intg_elapsed_time_includes_skipped_calls_but_not_skipped_samples(self):
        e=self.checked(['IF StartPB THEN INTG(I); END_IF;'],i={'TimingMode':0})
        e.memory.write('StartPB',True);self.step(e);e.memory.write('I.In',8)
        e.memory.write('StartPB',False);self.step(e);self.step(e)
        e.memory.write('StartPB',True);self.assertEqual(self.step(e)[1],3)
        self.assertEqual(e.memory.read('I.DeltaT'),0.75)

    def test_intg_periodic_task_uses_configured_period_per_reached_call(self):
        def periodic(root):
            task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','100')
        e=self.checked(['INTG(I); INTG(I);'],i={'TimingMode':0,'In':10},mutate=periodic)
        self.assertEqual(self.step(e,100)[1],0.5);self.assertAlmostEqual(e.memory.read('I.DeltaT'),0.1,places=6)

    def test_intg_maximum_oversample_and_backwards_clock(self):
        e=self.checked(i={'OversampleDT':MAX_DT});self.step(e);self.assertEqual(e.memory.read('I.DeltaT'),MAX_DT)
        e=self.checked(i={'TimingMode':0});self.step(e);next(v for k,v in e.last_timer.items() if k[1]=='i')['at']=1000
        before=copy.deepcopy(e.last_timer)
        with self.assertRaisesRegex(ModelError,'backwards'):self.step(e)
        self.assertEqual(e.last_timer,before)

    def test_enables_forced_and_visible_output_writes_do_not_replace_history(self):
        e=self.checked(a={'InPlus':2});self.step(e)
        for tag in TAGS:
            e.memory.write(tag+'.Out',99)
            for member in ('EnableIn','EnableOut'):e.memory.write(tag+'.'+member,False)
        self.assertEqual(self.step(e),(4,0))
        self.assertTrue(all(e.memory.read(tag+'.'+member) for tag in TAGS for member in ('EnableIn','EnableOut')))

    def test_run_reentry_resets_hidden_state_after_deferred_prescan(self):
        e=self.checked(a={'InPlus':2,'Out':88},i={'In':8},defer=True)
        self.assertEqual(e.memory.read('A.Out'),88);self.step(e);self.step(e);e.enter_run()
        self.assertEqual(e.last_timer,{});self.assertEqual(self.step(e),(2,0))

    def test_late_fault_rolls_back_initialization_and_both_histories(self):
        e=self.checked(['UPDN(A); INTG(I); SpeedCommand:=1/SpeedSetpoint;'],a={'InPlus':2})
        e.memory.write('SpeedSetpoint',1);self.step(e);e.memory.write('I.In',8);e.memory.write('A.Initialize',True)
        e.memory.write('A.InitialValue',100);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.scheduler_description()),before)
        e.memory.write('A.Initialize',False);e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e),(4,1))

    def test_instruction_and_prescan_budgets_restore_histories(self):
        e=self.checked(a={'InPlus':2});self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count))
        e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)
        e.fault=''
        with self.assertRaisesRegex(ModelError,'Prescan rolled back'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)

    def test_unknown_required_and_nonfinite_inputs_fault_transactionally(self):
        for ref,value in (('A.Initialize',None),('A.InPlus',None),('I.In',None),('I.HoldLow',1),('I.IGain',float('nan'))):
            e=self.checked();key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,value)
            before=copy.deepcopy((e.memory.values,e.last_timer))
            with self.subTest(ref=ref),self.assertRaises(ModelError):self.step(e)
            self.assertEqual(e.last_timer,before[1]);self.assertEqual(e.time_ms,0)

    def test_defaults_member_types_and_status_aliases(self):
        e=self.checked();self.assertEqual((len(SCHEMAS['UP_DOWN_ACCUM']),len(SCHEMAS['INTEGRATOR'])),(8,19))
        self.assertEqual(default('INTEGRATOR')['HighLimit'],MAX_REAL)
        for tag,dtype in TAGS.items():
            self.assertNotIn(dtype,e.project.data_only_types)
            for member,kind in SCHEMAS[dtype].items():self.assertEqual(e.memory.resolve(tag+'.'+member)[2],kind)
        e.memory.write('i.deltatinv',True);self.assertEqual(e.memory.read('I.Status'),-2147483648)
        self.step(e);self.assertFalse(e.memory.read('I.DeltaTInv'))
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,22))
        self.assertFalse(e.report()['st_accumulate']['native_runtime_parity'])

    def test_invalid_shapes_constants_redefinitions_arity_and_rll_forms_block(self):
        for text in ('UPDN();','UPDN(I);','INTG(A);','INTG(I,A);'):
            self.assertTrue(self.engine([text]).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="A"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        for dtype in TAGS.values():
            def redefine(root):
                m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name=dtype,Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
            self.assertTrue(self.engine(mutate=redefine).blockers)
        def ladder(root):
            t=root.find('./Controller/Programs/Program/Routines/Routine');t.remove(t.find('STContent'));t.set('Type','RLL');E.SubElement(E.SubElement(E.SubElement(t,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='UPDN(A);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_other_controller_profiles_block(self):
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_program_local_alias_and_aoi_inout_use_resolved_history(self):
        def setup(root):
            tags=root.find('./Controller/Tags');tag=tags.find('./Tag[@Name="A"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='AliasA',TagType='Alias',AliasFor='Program:MainProgram.A')
            d=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='TotalBlock',Revision='1.0');p=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='State',TagType='Base',DataType='UP_DOWN_ACCUM',Usage='InOut',Required='true',Visible='true')
            E.SubElement(d,'LocalTags');logic(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='ST'),['UPDN(State);'])
            t=E.SubElement(tags,'Tag',Name='Instance',DataType='TotalBlock',TagType='Base');obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='TotalBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['TotalBlock(Instance,AliasA); UPDN(AliasA);'],a={'InPlus':2},mutate=setup)
        e.step(250);self.assertEqual(e.memory.read('AliasA.Out'),4);self.assertEqual(len(e.last_timer),1)
        h=Engine(e.project,'routine','MainProgram/MainRoutine');h.step(250);self.assertEqual(h.memory.read('AliasA.Out'),4)

    def test_st_for_targets_cannot_be_written_by_accumulation(self):
        self.assertTrue(self.engine(['FOR A.Out:=0 TO 2 DO UPDN(A); END_FOR;']).blockers)
        self.assertTrue(self.engine(['FOR I.Out:=0 TO 2 DO INTG(I); END_FOR;']).blockers)

    def test_nested_member_and_indirect_array_elements_have_independent_totals(self):
        def nested(root):
            tags=root.find('./Controller/Tags');members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='TotalHolder',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Total',DataType='UP_DOWN_ACCUM',Dimension='0')
            t=E.SubElement(tags,'Tag',Name='Holder',TagType='Base',DataType='TotalHolder');obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='TotalHolder')
            item=copy.deepcopy(tags.find('./Tag[@Name="A"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Total');obj.append(item)
            tag=tags.find('./Tag[@Name="A"]');tag.set('Dimensions','2');data=tag.find('Data');item=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated')
            arr=E.SubElement(data,'Array',DataType='UP_DOWN_ACCUM',Dimensions='2')
            for j in range(2):E.SubElement(arr,'Element',Index=f'[{j}]').append(copy.deepcopy(item))
        e=self.checked(['UPDN(A[SpeedCommand]); UPDN(Holder.Total);'],a={'InPlus':2},mutate=nested)
        e.memory.write('SpeedCommand',0);e.step(250);e.memory.write('SpeedCommand',1);e.step(250)
        e.memory.write('SpeedCommand',0);e.step(250)
        self.assertEqual(tuple(e.memory.read(ref) for ref in ('A[0].Out','A[1].Out','Holder.Total.Out')),(4,2,6))

    def test_ladder_for_target_calls_both_blocks_at_each_iteration(self):
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='FOR(Accumulate,SpeedCommand,0,1,1);'
            logic(E.SubElement(routines,'Routine',Name='Accumulate',Type='ST'),['UPDN(A); INTG(I);'])
        e=self.checked(a={'InPlus':2},i={'In':8},mutate=caller);self.assertEqual(self.step(e),(4,1))

    def test_stored_output_rounds_to_float32_after_each_call(self):
        e=self.checked(a={'Initialize':True,'InitialValue':16777216});self.step(e)
        e.memory.write('A.Initialize',False);e.memory.write('A.InPlus',1)
        self.assertEqual(self.step(e)[0],16777216);self.assertEqual(self.step(e)[0],16777216)

    def event_engine(self,fault=False):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='AccumEvent',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST');lines=['UPDN(A); I.In:=8; INTG(I);']
            if fault:lines.append('SpeedCommand:=1/SpeedSetpoint;')
            logic(routine,lines);task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='AccumEventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='AccumEvent')
        return self.checked(['UPDN(A); INTG(I); EVENT(AccumEventTask); UPDN(A); INTG(I);'],a={'InPlus':2},mutate=event)

    def test_preempting_event_shares_record_history_in_dispatch_order(self):
        e=self.event_engine();self.assertEqual(self.step(e),(6,3));self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)

    def test_event_failure_restores_scheduler_and_both_accumulators(self):
        e=self.event_engine(fault=True);e.memory.write('SpeedSetpoint',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e),(6,3))

    def test_detached_replacement_preserves_accumulation_history(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(Accumulate,0);'
            logic(E.SubElement(routines,'Routine',Name='Accumulate',Type='ST'),['UPDN(A); INTG(I);'])
        e=self.checked(a={'InPlus':2},mutate=caller);self.step(e);e.memory.write('I.In',8);self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer))
        neutral=['JSR(Accumulate,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for j,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(j+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf-8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(self.step(candidate),(6,3))

    def test_public_sample_runs_and_rolls_back(self):
        e=Engine(Project(SAMPLES/'AccumulatorLab.L5X'));self.assertEqual(e.blockers,[]);e.step(250)
        self.assertEqual((e.memory.read('Total'),e.memory.read('Integral')),(1,0));e.step(250)
        self.assertEqual((e.memory.read('Total'),e.memory.read('Integral')),(2,0.25))
        e.memory.write('FaultDivisor',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
        with self.assertRaisesRegex(ModelError,'zero'):e.step(250)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)


if __name__=='__main__':unittest.main()
