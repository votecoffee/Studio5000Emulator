"""LPF bilinear software equations, timing, diagnostics and state transactions."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project,coerce
from logixlab.runtime import Engine
from logixlab.st_filter import FIELDS,default,MAX_DT
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,values=None):
    tag=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType='FILTER_LOW_PASS')
    obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FILTER_LOW_PASS')
    for member,value in (default()|dict(values or {})).items():
        E.SubElement(obj,'DataValueMember',Name=member,DataType=FIELDS[member],Value=str(float(value) if FIELDS[member]=='REAL' else int(value)))
    return tag


class StructuredFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        for name in ('T','U'):record(tags,name,{'TimingMode':1,'OversampleDT':0.125,'WLag':16.0}|dict(values or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['LPF(T);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'filter.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e,dt=125):e.step(dt);return e.memory.read('T')

    def test_first_call_seeds_from_input_and_ignores_saved_output(self):
        e=self.checked(values={'In':-7,'Out':999});self.assertEqual(e.memory.read('T.Out'),999)
        self.assertEqual(self.step(e)['Out'],-7);self.assertEqual(self.step(e)['Out'],-7)

    def test_first_order_known_bilinear_step_at_unit_ratio(self):
        e=self.checked();self.step(e);e.memory.write('T.In',10)
        self.assertEqual(self.step(e)['Out'],5);self.assertEqual(self.step(e)['Out'],10);self.assertEqual(self.step(e)['Out'],10)

    def test_second_order_known_biquad_step(self):
        e=self.checked(values={'Order':2});self.step(e);e.memory.write('T.In',10)
        den=2+math.sqrt(2);a2=(2-math.sqrt(2))/den
        for expected in (10/den,30/den,40/den-a2*10/den):self.assertAlmostEqual(self.step(e)['Out'],expected,places=5)

    def test_third_order_known_cascade_step(self):
        e=self.checked(values={'Order':3});self.step(e);e.memory.write('T.In',10)
        for expected in (5/3,20/3,100/9):self.assertAlmostEqual(self.step(e)['Out'],expected,places=5)

    def test_all_orders_converge_to_constant_input(self):
        for order in (1,2,3):
            e=self.checked(values={'Order':order});self.step(e);e.memory.write('T.In',10)
            for _ in range(100):self.step(e)
            self.assertAlmostEqual(e.memory.read('T.Out'),10,places=6)

    def test_all_orders_attenuate_alternating_nyquist_input(self):
        for order in (1,2,3):
            e=self.checked(values={'Order':order});self.step(e)
            for i in range(160):e.memory.write('T.In',10 if i%2 else -10);self.step(e)
            self.assertLess(abs(e.memory.read('T.Out')),1e-5)

    def test_small_ratio_first_order_matches_closed_form(self):
        e=self.checked(values={'WLag':4});self.step(e);e.memory.write('T.In',10)
        a=0.6
        for n in range(1,8):self.assertAlmostEqual(self.step(e)['Out'],10-8*a**(n-1),places=5)

    def test_initialize_seeds_sections_until_released(self):
        for order in (1,2,3):
            e=self.checked(values={'Order':order});self.step(e);e.memory.write('T.In',10);self.step(e)
            e.memory.write('T.Initialize',True);e.memory.write('T.In',-5);self.assertEqual(self.step(e)['Out'],-5)
            e.memory.write('T.In',3);self.assertEqual(self.step(e)['Out'],3)
            e.memory.write('T.Initialize',False);self.assertAlmostEqual(self.step(e)['Out'],3,places=6)

    def test_order_change_reseeds_from_current_input(self):
        e=self.checked();self.step(e);e.memory.write('T.In',10);self.assertEqual(self.step(e)['Out'],5)
        e.memory.write('T.Order',3);self.assertEqual(self.step(e)['Out'],10);self.assertEqual(self.step(e)['Out'],10)

    def test_frequency_change_recomputes_coefficients_without_reseeding(self):
        e=self.checked();self.step(e);e.memory.write('T.In',10);self.step(e);e.memory.write('T.WLag',8)
        self.assertAlmostEqual(self.step(e)['Out'],25/3,places=5)

    def test_explicit_interval_change_recomputes_coefficients(self):
        e=self.checked();self.step(e);e.memory.write('T.In',10);self.step(e);e.memory.write('T.OversampleDT',0.0625)
        self.assertAlmostEqual(self.step(e)['Out'],25/3,places=5)

    def test_visible_out_write_does_not_replace_hidden_sections(self):
        e=self.checked();self.step(e);e.memory.write('T.In',10);self.step(e);e.memory.write('T.Out',999)
        self.assertEqual(self.step(e)['Out'],10)

    def test_continuous_timing_uses_elapsed_whole_simulated_milliseconds(self):
        e=self.checked(values={'TimingMode':0});self.assertEqual(self.step(e)['DeltaT'],0)
        e.memory.write('T.In',10);t=self.step(e);self.assertEqual((t['Out'],t['DeltaT']),(5,0.125))

    def test_periodic_timing_uses_configured_period(self):
        def periodic(root):task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','125')
        e=self.checked(values={'TimingMode':0},mutate=periodic);self.assertEqual(self.step(e)['DeltaT'],0.125)
        e.memory.write('T.In',10);self.assertEqual(self.step(e)['Out'],5)

    def test_repeated_continuous_call_holds_but_oversample_call_advances(self):
        for mode,expected in ((0,5),(1,10)):
            e=self.checked(['LPF(T); LPF(T);'],values={'TimingMode':mode});self.step(e);e.memory.write('T.In',10)
            self.assertEqual(self.step(e)['Out'],expected)

    def test_repeated_periodic_calls_each_use_one_period(self):
        def periodic(root):task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','125')
        e=self.checked(['LPF(T); LPF(T);'],values={'TimingMode':0},mutate=periodic);self.step(e);e.memory.write('T.In',10)
        self.assertEqual(self.step(e)['Out'],10)

    def test_skipped_continuous_calls_accrue_elapsed_gap(self):
        e=self.checked(['IF StartPB THEN LPF(T); END_IF;'],values={'TimingMode':0,'WLag':4})
        e.memory.write('StartPB',True);self.step(e);history=copy.deepcopy(e.last_timer)
        e.memory.write('StartPB',False);self.step(e);self.step(e);self.assertEqual(e.last_timer,history)
        e.memory.write('StartPB',True);e.memory.write('T.In',10);t=self.step(e)
        self.assertEqual(t['DeltaT'],0.375);self.assertAlmostEqual(t['Out'],30/7,places=5)

    def test_skipped_periodic_calls_resume_with_one_period(self):
        def periodic(root):task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','125')
        e=self.checked(['IF StartPB THEN LPF(T); END_IF;'],values={'TimingMode':0,'WLag':4},mutate=periodic)
        e.memory.write('StartPB',True);self.step(e);e.memory.write('StartPB',False);self.step(e);self.step(e)
        e.memory.write('StartPB',True);e.memory.write('T.In',10);t=self.step(e);self.assertEqual((t['DeltaT'],t['Out']),(0.125,2))

    def test_oversampling_is_independent_of_advance_duration(self):
        e=self.checked();self.step(e);e.memory.write('T.In',10)
        self.assertEqual(self.step(e,dt=500)['Out'],5);self.assertEqual(self.step(e,dt=50)['Out'],10)

    def test_zero_oversample_disables_without_invalid_delta_flag(self):
        e=self.checked();self.step(e);e.memory.write('T.OversampleDT',0);e.memory.write('T.In',20)
        t=self.step(e);self.assertEqual((t['Out'],t['DeltaT'],t['Status']),(0,0,0))
        e.memory.write('T.In',10);e.memory.write('T.OversampleDT',0.125);self.assertEqual(self.step(e)['Out'],5)

    def test_invalid_interval_holds_and_sets_signed_status_bit_31(self):
        for dt in (-1,5000):
            e=self.checked();self.step(e);e.memory.write('T.OversampleDT',dt);e.memory.write('T.In',10)
            t=self.step(e);self.assertEqual((t['Out'],t['DeltaT'],t['Status']),(0,0,-2147483647));self.assertTrue(e.memory.read('T.DeltaTInv'))
            e.memory.write('T.OversampleDT',0.125);self.assertEqual(self.step(e)['Out'],5)

    def test_invalid_mode_holds_with_bit_27_and_rts_mode_is_unsupported(self):
        e=self.checked();self.step(e);e.memory.write('T.In',10)
        for mode in (-1,3):
            e.memory.write('T.TimingMode',mode);t=self.step(e);self.assertEqual((t['Out'],t['DeltaT'],t['Status']),(0,0,134217729))
        e.memory.write('T.TimingMode',2);before=copy.deepcopy((e.memory.values,e.last_timer))
        with self.assertRaisesRegex(ModelError,'real time sampling'):e.step()
        self.assertEqual((e.memory.values,e.last_timer),before)

    def test_initialization_still_seeds_when_timing_is_disabled_or_invalid(self):
        for mode,dt,status in ((1,0,0),(1,-1,-2147483647),(3,0,134217729)):
            e=self.checked(values={'TimingMode':mode,'OversampleDT':dt,'Initialize':True,'In':7})
            t=self.step(e);self.assertEqual((t['Out'],t['DeltaT'],t['Status']),(7,0,status))

    def test_invalid_order_uses_first_order_without_changing_requested_value(self):
        for order in (0,-1,1.5,4):
            e=self.checked(values={'Order':order});self.step(e);e.memory.write('T.In',10);t=self.step(e)
            self.assertEqual((t['Out'],t['Order'],t['Status']),(5,order,5));self.assertTrue(e.memory.read('T.OrderInv'))

    def test_order_specific_lower_cutoff_clamps_only_internal_frequency(self):
        for order,scale in ((1,1e-7),(2,1e-5),(3,0.001)):
            e=self.checked(values={'Order':order,'WLag':-1});self.step(e);e.memory.write('T.In',10);t=self.step(e);r=scale/2
            expected=10*r/(1+r) if order==1 else 10*r*r/(1+math.sqrt(2)*r+r*r) if order==2 else 10*r/(1+r)*r*r/(1+r+r*r)
            self.assertAlmostEqual(t['Out'],expected,delta=max(1e-13,abs(expected)*1e-6))
            self.assertEqual((t['WLag'],t['Status']),(-1,3))

    def test_high_cutoff_limit_and_order_diagnostics_combine(self):
        e=self.checked(values={'WLag':1000,'Order':4});self.step(e);e.memory.write('T.In',10);t=self.step(e);r=0.35*math.pi
        self.assertAlmostEqual(t['Out'],10*r/(1+r),places=5);self.assertEqual((t['WLag'],t['Status']),(1000,7))

    def test_zero_elapsed_time_does_not_apply_frequency_bounds(self):
        e=self.checked(values={'TimingMode':0,'WLag':-1});t=self.step(e);self.assertEqual((t['DeltaT'],t['Status']),(0,0))
        self.assertEqual(self.step(e)['Status'],3)

    def test_unused_oversample_and_rts_values_can_stay_unknown(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure')
            for name in ('OversampleDT','RTSTime','RTSTimeStamp'):obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
        e=self.checked(values={'TimingMode':0},mutate=missing);self.step(e);e.memory.write('T.In',10);self.assertEqual(self.step(e)['Out'],5)

    def test_missing_required_parameters_remain_unknown(self):
        for name in ('In','Initialize','WLag','Order','TimingMode','OversampleDT'):
            def missing(root):
                obj=root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure');obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
            e=self.checked(mutate=missing);self.assertIsNone(e.memory.read('T')[name])
            with self.subTest(name=name),self.assertRaisesRegex(ModelError,'unknown'):e.step()

    def test_nonfinite_required_value_faults_without_committing_history(self):
        for name in ('In','Order','WLag','OversampleDT'):
            e=self.checked();key,parts,_=e.memory.resolve('T.'+name);e.memory.store(key,parts,float('nan'))
            with self.subTest(name=name),self.assertRaises(ModelError):e.step()
            self.assertEqual((e.last_timer,e.time_ms,e.scan_count),({},0,0))

    def test_late_fault_restores_every_section_for_corrected_retry(self):
        for order,expected in ((1,2),(2,4/(2+math.sqrt(2))),(3,2/3)):
            e=self.checked(['LPF(T); SpeedCommand:=1/SpeedSetpoint;'],values={'Order':order});e.memory.write('SpeedSetpoint',1);self.step(e)
            e.memory.write('T.In',10);e.memory.write('SpeedSetpoint',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace))
            with self.assertRaisesRegex(ModelError,'zero'):e.step(125)
            self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace),before)
            e.memory.write('T.In',4);e.memory.write('SpeedSetpoint',1);self.assertAlmostEqual(self.step(e)['Out'],expected,places=5)

    def test_failed_initialize_does_not_replace_prior_sections(self):
        e=self.checked(['LPF(T); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.step(e)
        e.memory.write('T.In',10);self.step(e);e.memory.write('T.Initialize',True);e.memory.write('T.In',100);e.memory.write('SpeedSetpoint',0)
        with self.assertRaisesRegex(ModelError,'zero'):e.step(125)
        e.memory.write('T.Initialize',False);e.memory.write('T.In',0);e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)['Out'],5)

    def test_run_reentry_and_deferred_prescan(self):
        e=self.checked(values={'Out':77},defer=True);self.assertEqual(e.memory.read('T.Out'),77);self.step(e)
        e.memory.write('T.In',10);self.assertEqual(self.step(e)['Out'],5);e.enter_run()
        self.assertEqual((e.memory.read('T.Out'),e.last_timer),(5,{}));self.assertEqual(self.step(e)['Out'],10)

    def test_failed_prescan_and_budget_restore_existing_history(self):
        e=self.checked(['LPF(T); LPF(T);']);self.step(e);e.memory.write('T.In',10);self.step(e)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan rolled back'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)

    def test_backwards_clock_is_rejected_and_history_restored(self):
        e=self.checked(values={'TimingMode':0});self.step(e);key=next(k for k in e.last_timer if k[0]=='ST-LOW-PASS');e.last_timer[key]['at']=1000
        before=copy.deepcopy(e.last_timer)
        with self.assertRaisesRegex(ModelError,'backwards'):e.step(125)
        self.assertEqual(e.last_timer,before)

    def test_redefinitions_constants_bad_arity_and_rll_forms_block(self):
        for text in ('LPF(T,U);','LPF();','LPF(SpeedCommand);'):
            self.assertTrue(self.engine([text]).blockers)
        def const(root):root.find('./Controller/Tags/Tag[@Name="T"]').set('Constant','true')
        self.assertTrue(self.engine(['IF FALSE THEN LPF(T); END_IF;'],mutate=const).blockers)
        def redefine(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FILTER_LOW_PASS',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
        self.assertTrue(self.engine(mutate=redefine).blockers)
        def ladder(root):
            r=root.find('./Controller/Programs/Program/Routines/Routine');r.remove(r.find('STContent'));r.set('Type','RLL');E.SubElement(E.SubElement(E.SubElement(r,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='LPF(T);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_other_profiles_are_blocked(self):
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_status_aliases_share_the_backing_word_and_member_types(self):
        e=self.checked();e.memory.write('T.DeltaTInv',True);self.assertEqual(e.memory.read('T.Status'),-2147483648)
        for name,kind in FIELDS.items():self.assertEqual(e.memory.resolve('T.'+name)[2],kind)
        self.step(e);self.assertEqual(e.memory.read('T.Status'),0)

    def test_detached_replacement_preserves_section_histories(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(Filter,0);'
            logic(E.SubElement(routines,'Routine',Name='Filter',Type='ST'),['LPF(T);'])
        e=self.checked(mutate=caller);self.step(e);e.memory.write('T.In',10);self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer))
        neutral=['JSR(Filter,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        candidate.memory.write('T.In',0);self.assertEqual(self.step(candidate)['Out'],5)

    def test_counts_classification_and_report_expose_software_solver(self):
        e=self.checked();self.assertEqual(len(ARITIES),101);self.assertEqual(len(ST_ONLY_ARITIES),20)
        self.assertNotIn('FILTER_LOW_PASS',e.project.data_only_types);self.assertEqual(set(e.memory.read('T')),set(FIELDS))
        profile=e.report()['st_filter'];self.assertEqual(profile['instructions'],['LPF']);self.assertFalse(profile['native_runtime_parity'])
        self.assertIn('software approximation',profile['solver'])

    def test_program_local_alias_uses_the_resolved_section_history(self):
        def local(root):
            tags=root.find('./Controller/Tags');tag=tags.find('./Tag[@Name="T"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='AliasT',TagType='Alias',AliasFor='Program:MainProgram.T')
        e=self.checked(['LPF(AliasT);'],mutate=local);e.step(125);e.memory.write('AliasT.In',10);e.step(125)
        self.assertEqual(e.memory.read('AliasT.Out'),5)

    def test_nested_member_and_indirect_array_elements_keep_independent_history(self):
        def nested(root):
            tags=root.find('./Controller/Tags');members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FilterHolder',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Filter',DataType='FILTER_LOW_PASS',Dimension='0')
            tag=E.SubElement(tags,'Tag',Name='Holder',TagType='Base',DataType='FilterHolder');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FilterHolder')
            item=copy.deepcopy(tags.find('./Tag[@Name="T"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Filter');obj.append(item)
            tag=tags.find('./Tag[@Name="T"]');tag.set('Dimensions','2');data=tag.find('Data');item=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated')
            arr=E.SubElement(data,'Array',DataType='FILTER_LOW_PASS',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['LPF(T[SpeedCommand]); LPF(Holder.Filter);'],mutate=nested)
        for i in (0,1):e.memory.write('SpeedCommand',i);e.step(125)
        e.memory.write('SpeedCommand',0);e.memory.write('T[0].In',10);e.memory.write('Holder.Filter.In',20);e.step(125)
        self.assertEqual((e.memory.read('T[0].Out'),e.memory.read('T[1].Out'),e.memory.read('Holder.Filter.Out')),(5,0,10))

    def test_aoi_inout_and_harness_share_the_same_model(self):
        def aoi(root):
            d=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='FilterBlock',Revision='1.0');p=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='State',TagType='Base',DataType='FILTER_LOW_PASS',Usage='InOut',Required='true',Visible='true')
            E.SubElement(d,'LocalTags');logic(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='ST'),['LPF(State);'])
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='FilterBlock',TagType='Base');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FilterBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['FilterBlock(Instance,T);'],mutate=aoi);self.step(e);e.memory.write('T.In',10);self.assertEqual(self.step(e)['Out'],5)
        h=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(h.blockers,[]);self.step(h);h.memory.write('T.In',10);self.assertEqual(self.step(h)['Out'],5)

    def test_ladder_for_target_advances_explicit_sampling_per_call(self):
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='FOR(Filter,SpeedCommand,0,1,1);'
            logic(E.SubElement(routines,'Routine',Name='Filter',Type='ST'),['LPF(T);'])
        e=self.checked(mutate=caller);self.step(e);e.memory.write('T.In',10);self.assertEqual(self.step(e)['Out'],10)

    def event_engine(self,fault=False):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='FilterEvent',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST');lines=['T.In:=10; LPF(T);']
            if fault:lines.append('SpeedCommand:=1/SpeedSetpoint;')
            logic(routine,lines)
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='FilterEventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='FilterEvent')
        return self.checked(['T.In:=0; LPF(T); EVENT(FilterEventTask); T.In:=10; LPF(T);'],mutate=event)

    def test_preempting_event_updates_shared_explicit_sample_sections(self):
        e=self.event_engine();self.assertEqual(self.step(e)['Out'],10)
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)

    def test_preempting_event_fault_restores_sections_clock_and_scheduler(self):
        e=self.event_engine(fault=True);e.memory.write('SpeedSetpoint',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):e.step(125)
        self.assertEqual((e.memory.values,e.last_timer,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)['Out'],10)

    def test_overshoot_overflow_rolls_back_and_explicit_initialization_recovers(self):
        e=self.checked(values={'Order':2});self.step(e);e.memory.write('T.In',3.4e38);self.step(e);self.step(e)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
        with self.assertRaisesRegex(ModelError,'REAL'):e.step(125)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)
        e.memory.write('T.Initialize',True);e.memory.write('T.In',0);self.assertEqual(self.step(e)['Out'],0)

    def test_maximum_valid_oversample_and_normal_scan_budget(self):
        e=self.checked(values={'OversampleDT':MAX_DT,'WLag':0.0001});t=self.step(e);self.assertEqual((t['DeltaT'],t['Status']),(MAX_DT,0))
        e=self.checked(['LPF(T); LPF(T);']);self.step(e);e.memory.write('T.In',10);before=copy.deepcopy((e.memory.values,e.last_timer));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):e.step(125)
        self.assertEqual((e.memory.values,e.last_timer),before)

    def test_public_filter_lab_uses_documented_software_recurrence(self):
        e=Engine(Project(SAMPLES/'FilterLab.L5X'));self.assertEqual(e.blockers,[]);e.step(125)
        e.memory.write('Input',10);e.step(125);self.assertEqual(e.memory.read('Filtered'),5)
        self.assertFalse(e.report()['st_filter']['native_runtime_parity'])


if __name__=='__main__':unittest.main()
