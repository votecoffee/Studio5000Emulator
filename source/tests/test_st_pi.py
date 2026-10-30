"""PI regulation equations, bounds, shaping and transactional lifecycle."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_pi import FIELDS,MIN_GAIN,MAX_DT,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,values=None):
    t=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType='PROP_INT')
    obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='PROP_INT')
    for member,value in (default()|dict(values or {})).items():
        E.SubElement(obj,'DataValueMember',Name=member,DataType=FIELDS[member],Value=str(int(value)) if isinstance(value,bool) else str(value))
    return t


class StructuredPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();record(root.find('./Controller/Tags'),'T',dict(Kp=2,Wld=1,TimingMode=1,OversampleDT=0.25)|dict(values or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['PI(T);'])
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'pi.L5X';E.ElementTree(root).write(p,encoding='utf-8',xml_declaration=True)
        return Engine(Project(p),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e,dt=250):e.step(dt);return e.memory.read('T')

    def test_linear_pi_combines_proportional_and_trapezoidal_integral(self):
        e=self.checked(values={'In':4});self.assertEqual(self.step(e)['Out'],0)
        self.assertEqual(self.step(e)['Out'],9);self.assertEqual(self.step(e)['Out'],11)
        e.memory.write('T.In',2);self.assertEqual(self.step(e)['Out'],8.5)

    def test_negative_error_and_current_gain_changes(self):
        e=self.checked(values={'In':-4});self.step(e);self.assertEqual(self.step(e)['Out'],-9)
        e.memory.write('T.Kp',1);self.assertEqual(self.step(e)['Out'],-6)

    def test_startup_ignores_saved_out_and_explicit_out_writes_do_not_replace_history(self):
        e=self.checked(values={'In':4,'Out':77});self.assertEqual(self.step(e)['Out'],0);self.assertEqual(self.step(e)['Out'],9)
        e.memory.write('T.Out',100);e.memory.write('T.In',0);self.assertEqual(self.step(e)['Out'],2)

    def test_held_initialize_clamps_initial_value_and_ignores_directional_holds(self):
        e=self.checked(values={'Initialize':True,'InitialValue':20,'HighLimit':10,'LowLimit':-10,'HoldHigh':True,'HoldLow':True})
        t=self.step(e);self.assertEqual((t['Out'],t['HighAlarm'],t['LowAlarm']),(10,True,False))
        e.memory.write('T.InitialValue',-20);t=self.step(e);self.assertEqual((t['Out'],t['HighAlarm'],t['LowAlarm']),(-10,False,True))

    def test_initialize_assigns_integrator_and_captures_integral_input(self):
        e=self.checked(values={'Initialize':True,'InitialValue':10,'In':4});self.step(e)
        e.memory.write('T.Initialize',False);self.assertEqual(self.step(e)['Out'],20)

    def test_directional_holds_affect_integral_while_proportional_still_changes(self):
        e=self.checked(values={'In':4,'HoldHigh':True});self.step(e);self.assertEqual(self.step(e)['Out'],8)
        e.memory.write('T.In',-4);self.assertEqual(self.step(e)['Out'],-8);self.assertEqual(self.step(e)['Out'],-10)
        e.memory.write('T.HoldHigh',False);e.memory.write('T.HoldLow',True);self.assertEqual(self.step(e)['Out'],-10)

    def test_output_saturation_discards_proposed_integral_without_windup(self):
        e=self.checked(values={'In':4,'HighLimit':8,'LowLimit':-8});self.step(e)
        for _ in range(3):
            t=self.step(e);self.assertEqual((t['Out'],t['HighAlarm']),(8,True))
        e.memory.write('T.In',0);t=self.step(e);self.assertEqual((t['Out'],t['HighAlarm']),(1,False))

    def test_invalid_limits_precede_initialize_and_force_low_with_both_alarms(self):
        for high,low in ((3,3),(2,3)):
            e=self.checked(values={'HighLimit':high,'LowLimit':low,'Initialize':True,'InitialValue':10});t=self.step(e)
            self.assertEqual((t['Out'],t['Status'],t['HighAlarm'],t['LowAlarm']),(low,9,True,True))

    def test_disabled_interval_still_applies_new_output_limits(self):
        e=self.checked(values={'In':4});self.step(e);self.step(e);e.memory.write('T.OversampleDT',0);e.memory.write('T.HighLimit',5)
        t=self.step(e);self.assertEqual((t['Out'],t['HighAlarm'],t['DeltaT']),(5,True,0))

    def test_invalid_gains_are_bounded_internally_without_writing_requests(self):
        e=self.checked(values={'Kp':0,'Wld':0});t=self.step(e)
        self.assertEqual((t['Kp'],t['Wld'],t['Status']),(0,0,7));self.assertTrue(e.memory.read('T.KpInv'))
        e=self.checked(values={'Wld':100});t=self.step(e);self.assertEqual((t['Wld'],t['Status']),(100,5))

    def test_linear_proportional_shaping_inside_positive_and_negative_ranges(self):
        for value,shape,expected in ((2,3,6),(-2,0.5,-3.5)):
            e=self.checked(values={'In':value,'NonLinearMode':True,'ShapeKpPlus':shape,'ShapeKpMinus':shape,'KpInRange':4,'HoldHigh':True,'HoldLow':True})
            self.step(e);self.assertEqual(self.step(e)['Out'],expected)

    def test_parabolic_shaping_uses_documented_display_coefficient(self):
        e=self.checked(values={'In':2,'NonLinearMode':True,'ParabolicLinear':True,'ShapeKpPlus':3,'KpInRange':4,'HoldHigh':True,'HoldLow':True})
        self.step(e);self.assertAlmostEqual(self.step(e)['Out'],4.666,places=5)

    def test_outside_proportional_range_uses_displayed_extension(self):
        for value,shape,expected in ((8,3,28),(-8,0.5,-8)):
            e=self.checked(values={'In':value,'NonLinearMode':True,'ShapeKpPlus':shape,'ShapeKpMinus':shape,'KpInRange':4,'HoldHigh':True,'HoldLow':True})
            self.step(e);self.assertEqual(self.step(e)['Out'],expected)

    def test_integral_shaping_and_input_range_clamp(self):
        for parabolic,expected in ((False,5),(True,4.75)):
            e=self.checked(values={'In':2,'NonLinearMode':True,'ParabolicLinear':parabolic,'ShapeWldPlus':3,'WldInRange':4})
            self.step(e);self.assertEqual(self.step(e)['Out'],expected)
        e=self.checked(values={'In':8,'NonLinearMode':True,'ShapeWldPlus':3,'WldInRange':4})
        self.step(e);self.assertEqual(self.step(e)['Out'],19)

    def test_shaping_validation_combines_status_without_changing_requested_values(self):
        values=dict(NonLinearMode=True,Kp=0,Wld=0,ShapeKpPlus=0,ShapeKpMinus=11,KpInRange=0,ShapeWldPlus=-1,ShapeWldMinus=11,WldInRange=0)
        e=self.checked(values=values);t=self.step(e);self.assertEqual(t['Status'],1015)
        for name,value in values.items():self.assertEqual(t[name],value)

    def test_unused_shaping_fields_and_rts_values_may_be_unknown(self):
        e=self.checked()
        for name in ('ParabolicLinear','ShapeKpPlus','ShapeKpMinus','KpInRange','ShapeWldPlus','ShapeWldMinus','WldInRange','RTSTime','RTSTimeStamp'):
            key,parts,_=e.memory.resolve('T.'+name);e.memory.store(key,parts,None)
        self.step(e);e.memory.write('T.In',4);self.assertEqual(self.step(e)['Out'],9)
        e.memory.write('T.NonLinearMode',True)
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)

    def test_zero_and_invalid_intervals_hold_and_do_not_sample_intermediate_input(self):
        e=self.checked();self.step(e)
        for interval,status in ((0,0),(-1,-2147483647),(5000,-2147483647)):
            e.memory.write('T.OversampleDT',interval);e.memory.write('T.In',6);t=self.step(e)
            self.assertEqual((t['Out'],t['DeltaT'],t['Status']),(0,0,status))
        e.memory.write('T.OversampleDT',0.25);e.memory.write('T.In',4);self.assertEqual(self.step(e)['Out'],9)

    def test_invalid_timing_mode_holds_and_rts_faults_explicitly(self):
        e=self.checked(values={'TimingMode':3});t=self.step(e);self.assertEqual((t['Out'],t['Status']),(0,134217729))
        e.memory.write('T.TimingMode',2);before=copy.deepcopy(e.last_timer)
        with self.assertRaisesRegex(ModelError,'real time sampling'):self.step(e)
        self.assertEqual(e.last_timer,before)

    def test_periodic_uses_configured_period_and_repeated_explicit_calls_advance(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','100')
        e=self.checked(values={'TimingMode':0,'In':4},mutate=periodic);self.step(e,100);t=self.step(e,100)
        self.assertAlmostEqual(t['Out'],8.4,places=5);self.assertAlmostEqual(t['DeltaT'],0.1,places=6)
        e=self.checked(['PI(T); PI(T);'],values={'In':4});self.assertEqual(self.step(e)['Out'],9)

    def test_elapsed_timing_includes_skipped_calls_without_sampling_them(self):
        e=self.checked(['IF StartPB THEN PI(T); END_IF;'],values={'TimingMode':0});e.memory.write('StartPB',True);self.step(e)
        e.memory.write('StartPB',False);self.step(e);self.step(e);e.memory.write('StartPB',True);e.memory.write('T.In',4)
        t=self.step(e);self.assertEqual((t['Out'],t['DeltaT']),(11,0.75))

    def test_maximum_oversample_and_backwards_clock(self):
        e=self.checked(values={'OversampleDT':MAX_DT});t=self.step(e);self.assertEqual((t['DeltaT'],t['Status']),(MAX_DT,5))
        e=self.checked(values={'TimingMode':0});self.step(e);next(v for k,v in e.last_timer.items() if k[0]=='ST-PI')['at']=1000
        with self.assertRaisesRegex(ModelError,'backwards'):self.step(e)

    def test_unknown_required_and_nonfinite_values_are_not_defaulted(self):
        for name,value in (('In',None),('Initialize',1),('HoldHigh',None),('Kp',float('nan')),('LowLimit',float('-inf'))):
            e=self.checked();key,parts,_=e.memory.resolve('T.'+name);e.memory.store(key,parts,value)
            with self.subTest(name=name),self.assertRaises(ModelError):self.step(e)
            self.assertEqual((e.last_timer,e.time_ms),({},0))

    def test_late_fault_rolls_back_failed_initialize_and_integral_input_history(self):
        e=self.checked(['PI(T); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.step(e)
        e.memory.write('T.In',4);e.memory.write('T.Initialize',True);e.memory.write('T.InitialValue',50);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.scheduler_description()),before)
        e.memory.write('T.Initialize',False);e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)['Out'],9)

    def test_run_and_failed_prescan_restore_existing_state(self):
        e=self.checked(values={'In':4,'Out':77},defer=True);self.assertEqual(e.memory.read('T.Out'),77);self.step(e);self.step(e)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count));e.instruction_limit=0
        with self.assertRaisesRegex(ModelError,'Prescan rolled back'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)
        e.fault='';e.instruction_limit=100;e.enter_run();self.assertEqual(self.step(e)['Out'],0)

    def test_instruction_budget_rolls_back_repeated_calls(self):
        e=self.checked(['PI(T); PI(T);'],values={'In':4});self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer),before)

    def test_enables_forced_and_skipped_calls_retain_values_and_history(self):
        e=self.checked(['IF StartPB THEN PI(T); END_IF;']);e.memory.write('StartPB',True);self.step(e)
        for member in ('EnableIn','EnableOut'):e.memory.write('T.'+member,False)
        e.memory.write('StartPB',False);before=copy.deepcopy(e.last_timer);self.step(e);self.assertEqual(e.last_timer,before)
        self.assertFalse(e.memory.read('T.EnableOut'));e.memory.write('StartPB',True);t=self.step(e);self.assertTrue(t['EnableIn'] and t['EnableOut'])

    def test_defaults_types_status_aliases_and_report_are_qualified(self):
        e=self.checked();self.assertEqual(len(FIELDS),28);self.assertEqual(default()['Kp'],MIN_GAIN)
        self.assertNotIn('PROP_INT',e.project.data_only_types)
        for name,kind in FIELDS.items():self.assertEqual(e.memory.resolve('T.'+name)[2],kind)
        e.memory.write('T.DeltaTInv',True);self.assertEqual(e.memory.read('T.Status'),-2147483648)
        self.step(e);self.assertEqual(e.memory.read('T.Status'),0)
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,27));self.assertFalse(e.report()['st_pi']['native_runtime_parity'])
        self.assertIn('0.333',e.report()['st_pi']['shaping'])

    def test_wrong_types_arity_constants_redefinitions_and_ladder_block(self):
        for text in ('PI();','PI(T,T);','PI(SpeedCommand);'):
            self.assertTrue(self.engine([text]).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="T"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        def redefine(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='PROP_INT',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
        self.assertTrue(self.engine(mutate=redefine).blockers)
        def ladder(root):
            t=root.find('./Controller/Programs/Program/Routines/Routine');t.remove(t.find('STContent'));t.set('Type','RLL');E.SubElement(E.SubElement(E.SubElement(t,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='PI(T);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_other_controller_profiles_block(self):
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_program_local_alias_aoi_inout_and_harness_share_history(self):
        def setup(root):
            tags=root.find('./Controller/Tags');t=tags.find('./Tag[@Name="T"]');tags.remove(t);root.find('./Controller/Programs/Program/Tags').append(t)
            E.SubElement(tags,'Tag',Name='AliasT',TagType='Alias',AliasFor='Program:MainProgram.T')
            a=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='Regulator',Revision='1.0');p=E.SubElement(a,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='State',TagType='Base',DataType='PROP_INT',Usage='InOut',Required='true',Visible='true')
            E.SubElement(a,'LocalTags');logic(E.SubElement(E.SubElement(a,'Routines'),'Routine',Name='Logic',Type='ST'),['PI(State);'])
            t=E.SubElement(tags,'Tag',Name='Instance',DataType='Regulator',TagType='Base');obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='Regulator')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['Regulator(Instance,AliasT);'],values={'In':4},mutate=setup);e.step(250);e.step(250);self.assertEqual(e.memory.read('AliasT.Out'),9)
        h=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(h.blockers,[]);h.step(250);h.step(250);self.assertEqual(h.memory.read('AliasT.Out'),9)

    def test_nested_indirect_array_records_keep_independent_integrators(self):
        def nested(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='RegCell',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='State',DataType='PROP_INT',Dimension='0')
            tags=root.find('./Controller/Tags');t=E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='RegCell',Dimensions='2');arr=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='RegCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='RegCell');item=copy.deepcopy(tags.find('./Tag[@Name="T"]/Data/Structure'));item.tag='StructureMember';item.set('Name','State');obj.append(item)
        e=self.checked(['PI(Cells[SpeedCommand].State);'],mutate=nested)
        for i in (0,1):e.memory.write('SpeedCommand',i);e.step(250)
        e.memory.write('SpeedCommand',0);e.memory.write('Cells[0].State.In',4);e.step(250)
        self.assertEqual((e.memory.read('Cells[0].State.Out'),e.memory.read('Cells[1].State.Out')),(9,0))

    def test_st_for_bounds_are_protected_and_ladder_for_calls_advance(self):
        self.assertTrue(self.engine(['FOR SpeedCommand:=0 TO T.Status DO PI(T); END_FOR;']).blockers)
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='FOR(Regulate,SpeedCommand,0,2,1);'
            logic(E.SubElement(routines,'Routine',Name='Regulate',Type='ST'),['T.In:=SpeedCommand; PI(T);'])
        self.assertEqual(self.step(self.checked(mutate=caller))['Out'],5)

    def event_engine(self,fault=False):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='PIEvent',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST');lines=['T.In:=2; PI(T);']
            if fault:lines.append('SpeedCommand:=1/SpeedSetpoint;')
            logic(routine,lines);t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='PIEventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='PIEvent')
        return self.checked(['PI(T); EVENT(PIEventTask); T.In:=3; PI(T);'],mutate=event)

    def test_event_dispatch_shares_integrator_in_execution_order(self):
        self.assertEqual(self.step(self.event_engine())['Out'],7.75)

    def test_event_failure_rolls_back_integrator_and_scheduler(self):
        e=self.event_engine(fault=True);e.memory.write('SpeedSetpoint',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)['Out'],7.75)

    def test_detached_replacement_preserves_integrator_input_and_clock(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(Regulate,0);'
            logic(E.SubElement(routines,'Routine',Name='Regulate',Type='ST'),['PI(T);'])
        e=self.checked(values={'In':4},mutate=caller);self.step(e);self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer))
        neutral=['JSR(Regulate,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf-8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(self.step(candidate)['Out'],11)

    def test_public_regulator_lab_step_response_converges_and_plant_fault_rolls_back(self):
        e=Engine(Project(SAMPLES/'RegulatorLab.L5X'));self.assertEqual(e.blockers,[]);e.step(125)
        e.step(125);self.assertEqual((e.memory.read('ControlOutput'),e.memory.read('Feedback')),(10,1.25))
        for _ in range(198):e.step(125)
        self.assertAlmostEqual(e.memory.read('Feedback'),5,places=4)
        e.memory.write('PlantTimeConstant',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
        with self.assertRaisesRegex(ModelError,'zero'):e.step(125)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)


if __name__=='__main__':unittest.main()
