"""UPDN/INTG FBD wire, enable, shared-history and rollback contracts."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_accumulate import MAX_REAL
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/FBDTotalLab.L5X'


class FBDAccumulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="AccumulateSignals"]/FBDContent/Sheet')

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'totals.L5X';E.ElementTree(root).write(path,encoding='utf8',xml_declaration=True)
        return Engine(Project(path),mode,'MainProgram/AccumulateSignals' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def step(self,e,dt=10):
        e.step(dt);return tuple(e.memory.read(t) for t in ('Total','Integral'))

    def settings(self,e,**values):
        for tag,value in values.items():e.memory.write(tag,value)

    def test_startup_distinguishes_per_call_total_from_timed_integral(self):
        e=self.checked();self.assertEqual(self.step(e),(1.5,0));self.assertEqual(self.step(e),(3,.5))
        self.assertEqual(self.step(e),(4.5,1.5));self.assertEqual(e.memory.read('Elapsed'),.25)
        self.assertEqual(len(e.last_timer),2)

    def test_updn_signed_inputs_accumulate_each_reached_call(self):
        e=self.checked();self.settings(e,Plus=-3,Minus=-1)
        self.assertEqual(self.step(e)[0],-2);self.assertEqual(self.step(e)[0],-4)

    def test_updn_initialize_overrides_hold_and_reloads_while_held(self):
        e=self.checked();self.settings(e,InitializeTotal=True,HoldTotal=True)
        self.assertEqual(self.step(e)[0],10);e.memory.write('TotalSeed',-4);self.assertEqual(self.step(e)[0],-4)
        e.memory.write('InitializeTotal',False);self.assertEqual(self.step(e)[0],-4)
        e.memory.write('HoldTotal',False);self.assertEqual(self.step(e)[0],-2.5)

    def test_updn_initialize_and_hold_only_consume_required_inputs(self):
        e=self.checked();self.settings(e,InitializeTotal=True)
        for t in ('Plus','Minus','HoldTotal'):self.unknown(e,t)
        self.assertEqual(self.step(e)[0],10);self.settings(e,InitializeTotal=False,HoldTotal=True)
        self.assertEqual(self.step(e)[0],10);self.settings(e,HoldTotal=False);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'UPDN InPlus'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_first_hold_starts_total_at_zero_instead_of_saved_out(self):
        e=self.checked();self.settings(e,HoldTotal=True);e.memory.write('TotalState.Out',55)
        self.assertEqual(self.step(e)[0],0)

    def test_intg_trapezoid_uses_previous_consumed_input(self):
        e=self.checked();self.step(e);e.memory.write('Rate',8);self.assertEqual(self.step(e)[1],1)
        e.memory.write('Rate',4);self.assertEqual(self.step(e)[1],2.5)
        e.memory.write('Rate',-4);self.assertEqual(self.step(e)[1],2.5);self.assertEqual(self.step(e)[1],1.5)

    def test_intg_initialize_seeds_output_and_previous_input(self):
        e=self.checked();self.settings(e,InitializeIntegral=True,IntegralSeed=2,Gain=2)
        self.assertEqual(self.step(e)[1],2);self.assertEqual(self.step(e)[1],2)
        e.memory.write('InitializeIntegral',False);self.assertEqual(self.step(e)[1],4)

    def test_directional_holds_sample_input_and_allow_opposite_motion(self):
        e=self.checked();self.settings(e,InitializeIntegral=True);self.step(e)
        self.settings(e,InitializeIntegral=False,HoldHigh=True);self.assertEqual(self.step(e)[1],0)
        e.memory.write('Rate',-4);self.assertEqual(self.step(e)[1],0);self.assertEqual(self.step(e)[1],-1)
        self.settings(e,HoldHigh=False,HoldLow=True);self.assertEqual(self.step(e)[1],-1)
        e.memory.write('Rate',4);self.assertEqual(self.step(e)[1],-1);self.assertEqual(self.step(e)[1],0)

    def test_both_directional_holds_update_sample_before_release(self):
        e=self.checked();self.settings(e,HoldHigh=True,HoldLow=True);self.step(e)
        e.memory.write('Rate',8);self.assertEqual(self.step(e)[1],0)
        self.settings(e,HoldHigh=False,HoldLow=False);self.assertEqual(self.step(e)[1],2)

    def test_clamped_history_avoids_hidden_excess_and_alarms_are_inclusive(self):
        e=self.checked();self.settings(e,HighLimit=1,LowLimit=-1,Rate=8);self.step(e)
        self.assertEqual(self.step(e)[1],1);self.assertTrue(e.memory.read('HighAlarm'))
        self.assertEqual(self.step(e)[1],1);e.memory.write('Rate',-8)
        self.assertEqual(self.step(e)[1],1);self.assertEqual(self.step(e)[1],-1)
        self.assertTrue(e.memory.read('LowAlarm'));self.assertFalse(e.memory.read('HighAlarm'))

    def test_invalid_limits_and_initialize_precedence_are_shared_with_st(self):
        e=self.checked();self.settings(e,HighLimit=1,LowLimit=2,InitializeIntegral=True,IntegralSeed=20)
        self.assertEqual(self.step(e)[1],20);self.assertEqual(e.memory.read('IntegralStatus'),5)
        self.assertTrue(e.memory.read('LimitsInvalid'));self.assertTrue(e.memory.read('HighAlarm'));self.assertTrue(e.memory.read('LowAlarm'))
        e.memory.write('InitializeIntegral',False);self.assertEqual(self.step(e)[1],2)
        self.settings(e,HighLimit=5,LowLimit=-5);self.step(e);self.assertFalse(e.memory.read('LimitsInvalid'))

    def test_negative_gain_correction_and_status_recovery(self):
        e=self.checked();self.settings(e,InitializeIntegral=True,IntegralSeed=2);self.step(e)
        self.settings(e,InitializeIntegral=False,Gain=-1);self.assertEqual(self.step(e)[1],2)
        self.assertEqual(e.memory.read('IntegralState.IGain'),0);self.assertEqual(e.memory.read('IntegralStatus'),3)
        self.assertTrue(e.memory.read('GainInvalid'));self.settings(e,Gain=1);self.step(e)
        self.assertFalse(e.memory.read('IntegralFault'))

    def test_zero_oversample_holds_without_diagnostic_and_invalid_intervals_report(self):
        e=self.checked();self.step(e);e.memory.write('Rate',8)
        for dt,status,invalid in ((0,0,False),(-1,-2147483647,True),(5000,-2147483647,True)):
            self.settings(e,SampleTime=dt);self.assertEqual(self.step(e)[1],0)
            self.assertEqual(e.memory.read('IntegralStatus'),status);self.assertIs(e.memory.read('SampleInvalid'),invalid)
        e.memory.write('SampleTime',.25);self.assertEqual(self.step(e)[1],1)

    def test_mode_diagnostic_and_rts_failure_roll_back_earlier_total(self):
        e=self.checked();self.step(e);e.memory.write('TimingMode',9)
        self.assertEqual(self.step(e)[1],0);self.assertTrue(e.memory.read('TimingInvalid'))
        self.assertEqual(e.memory.read('IntegralStatus'),134217729);e.memory.write('TimingMode',2);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'real time sampling'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_disabled_first_call_retains_saved_outputs_without_creating_history(self):
        e=self.checked();e.memory.write('BlockEnable',False)
        self.assertEqual(self.step(e),(0,0));self.assertEqual(e.last_timer,{})
        e.memory.write('BlockEnable',True);self.assertEqual(self.step(e),(1.5,0))

    def test_disabled_blocks_skip_unknowns_initialization_and_unsupported_mode(self):
        e=self.checked();previous=self.step(e);history=copy.deepcopy(e.last_timer)
        self.settings(e,BlockEnable=False,InitializeTotal=True,InitializeIntegral=True,TimingMode=2)
        for t in ('Plus','Minus','TotalSeed','IntegralSeed','Rate'):self.unknown(e,t)
        self.assertEqual(self.step(e),previous);self.assertEqual(e.last_timer,history)
        self.assertFalse(e.memory.read('TotalState.EnableOut'));self.assertFalse(e.memory.read('IntegralState.EnableOut'))

    def test_elapsed_disable_gap_integrates_only_current_and_previous_sample(self):
        e=self.checked();self.settings(e,TimingMode=0);self.step(e)
        self.settings(e,BlockEnable=False,Rate=8);self.step(e,40)
        self.settings(e,BlockEnable=True);v=self.step(e)
        self.assertEqual(v[0],3);self.assertAlmostEqual(v[1],.2,places=6)
        self.assertAlmostEqual(e.memory.read('Elapsed'),.05,places=7)

    def test_skipped_graph_retains_history_and_total_counts_once_on_resume(self):
        e=self.checked();self.settings(e,TimingMode=0);self.step(e);history=copy.deepcopy(e.last_timer)
        self.settings(e,ExecuteGraph=False,Rate=8);self.assertEqual(self.step(e,40),(1.5,0));self.assertEqual(e.last_timer,history)
        self.settings(e,ExecuteGraph=True);v=self.step(e);self.assertEqual(v[0],3);self.assertAlmostEqual(v[1],.2,places=6)

    def test_unwired_enable_forces_execution_despite_saved_false(self):
        def unwire(root):
            sheet=self.sheet(root)
            for w in list(sheet.findall('Wire')):
                if w.get('ToParam')=='EnableIn':sheet.remove(w)
        e=self.checked(unwire);e.memory.write('BlockEnable',False);self.assertEqual(self.step(e),(1.5,0))
        self.assertTrue(e.memory.read('TotalState.EnableIn'));self.assertTrue(e.memory.read('IntegralState.EnableOut'))

    def test_status_alias_can_gate_independent_total(self):
        def gate(root):
            w=self.sheet(root).find('Wire[@ToID="100"][@ToParam="EnableIn"]');w.set('FromID','200');w.set('FromParam','IGainInv')
        e=self.checked(gate);self.assertEqual(self.step(e),(0,0));e.memory.write('Gain',-1)
        self.assertEqual(self.step(e)[0],1.5);e.memory.write('Gain',1);self.assertEqual(self.step(e)[0],1.5)

    def test_updn_output_wire_feeds_integrator_in_dependency_order(self):
        def chain(root):
            w=self.sheet(root).find('Wire[@ToID="200"][@ToParam="In"]');w.set('FromID','100');w.set('FromParam','Out')
        e=self.checked(chain);self.assertEqual(self.step(e),(1.5,0))
        self.assertEqual(self.step(e),(3,.375));self.assertEqual(self.step(e),(4.5,1.3125))

    def test_direct_output_writes_do_not_replace_total_or_integral_state(self):
        e=self.checked();self.step(e);self.step(e)
        self.settings(e,**{'TotalState.Out':99,'IntegralState.Out':-99})
        self.assertEqual(self.step(e),(4.5,1.5))

    def test_required_unknown_input_faults_with_whole_advance_rollback(self):
        for tag in ('BlockEnable','InitializeTotal','Plus','Rate','Gain','HoldHigh'):
            e=self.checked();self.unknown(e,tag);before=self.snapshot(e)
            with self.subTest(tag=tag),self.assertRaises(ModelError):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_intg_always_requires_input_even_during_initialize_or_hold(self):
        for settings in ({'InitializeIntegral':True},{'HoldHigh':True,'HoldLow':True}):
            e=self.checked();self.settings(e,**settings);self.unknown(e,'Rate');before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'INTG In is unknown'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_omitted_saved_input_stays_unknown_without_declaration_default(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="TotalState"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="InPlus"]'))
            sheet=self.sheet(root);sheet.remove(sheet.find('Wire[@ToID="100"][@ToParam="InPlus"]'))
        e=self.checked(missing)
        with self.assertRaisesRegex(ModelError,'UPDN InPlus is unknown'):self.step(e)

    def test_late_integral_fault_restores_total_and_histories_before_retry(self):
        e=self.checked();self.step(e);self.settings(e,InitializeIntegral=True);self.unknown(e,'IntegralSeed');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'INTG InitialValue'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,IntegralSeed=2);self.assertEqual(self.step(e),(3,2))

    def test_late_ladder_fault_restores_integral_samples_and_diagnostic_correction(self):
        e=self.checked();self.step(e);self.settings(e,Rate=8,Gain=-1,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,Gain=1,FaultDivisor=1)
        self.assertEqual(self.step(e),(3,1));self.assertFalse(e.memory.read('IntegralFault'))

    def test_accumulator_overflow_is_transactional_and_initialize_recovers(self):
        e=self.checked();self.settings(e,Plus=MAX_REAL,Minus=0);self.step(e);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'REAL'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,InitializeTotal=True,TotalSeed=0)
        self.assertEqual(self.step(e)[0],0)

    def test_run_resets_hidden_accumulators_and_preserves_outputs_until_next_call(self):
        e=self.checked();self.step(e);self.step(e);e.enter_run()
        self.assertEqual(e.last_timer,{});self.assertEqual((e.memory.read('Total'),e.memory.read('Integral')),(3,.5))
        self.assertEqual(self.step(e),(1.5,0))

    def test_periodic_and_harness_use_existing_startup_and_timing_rules(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        e=self.checked(periodic);self.settings(e,TimingMode=0);self.assertEqual(self.step(e),(1.5,0))
        self.assertAlmostEqual(self.step(e)[1],.02,places=7);self.assertAlmostEqual(e.memory.read('Elapsed'),.01,places=7)
        e=self.checked(mode='routine',defer=True);self.assertTrue(e.memory.read('TotalState.EnableIn'));e.enter_run()
        self.assertFalse(e.memory.read('TotalState.EnableIn'));self.assertEqual(self.step(e),(1.5,0))

    def test_st_fbd_same_record_calls_share_state_with_per_call_oversampling(self):
        def st(root):logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(AccumulateSignals,0); UPDN(TotalState); INTG(IntegralState);'])
        e=self.checked(st);self.assertEqual(self.step(e),(1.5,0))
        self.assertEqual((e.memory.read('TotalState.Out'),e.memory.read('IntegralState.Out')),(3,.5))
        self.assertEqual(self.step(e),(4.5,1.5));self.assertEqual(e.memory.read('IntegralState.Out'),2.5)
        self.assertEqual(len(e.last_timer),2)

    def test_st_fbd_repeated_continuous_timestamp_does_not_add_time(self):
        def st(root):logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(AccumulateSignals,0); INTG(IntegralState);'])
        e=self.checked(st);self.settings(e,TimingMode=0);self.step(e)
        self.assertAlmostEqual(self.step(e)[1],.02,places=7);self.assertEqual(e.memory.read('IntegralState.DeltaT'),0)

    def event_engine(self,fault=False):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(AccumulateSignals,0); EVENT(TotalEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine' if fault else 'AccumulateSignals',Class='Standard',Disabled='false');E.SubElement(p,'Tags');routines=E.SubElement(p,'Routines')
            if fault:logic(E.SubElement(routines,'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            else:routines.append(copy.deepcopy(root.find('.//Routine[@Name="AccumulateSignals"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='TotalEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_calls_accumulate_twice_and_share_integrator_clock(self):
        e=self.event_engine();self.settings(e,TimingMode=0);self.assertEqual(self.step(e),(3,0))
        v=self.step(e);self.assertEqual(v[0],6);self.assertAlmostEqual(v[1],.02,places=7);self.assertEqual(e.memory.read('Elapsed'),0)

    def test_event_late_fault_restores_both_hidden_accumulators(self):
        e=self.event_engine(True);self.step(e);self.settings(e,Rate=8,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e),(3,1))

    def test_program_local_total_alias_and_nested_integrator_record(self):
        def nested(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="TotalState"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='LocalTotal',TagType='Alias',AliasFor='Program:MainProgram.TotalState');self.sheet(root).find('Block[@Type="UPDN"]').set('Operand','LocalTotal')
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='IntegralCell',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Area',DataType='INTEGRATOR',Dimension='0')
            tag=tags.find('Tag[@Name="IntegralState"]');structure=tag.find('Data/Structure');tags.remove(tag)
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='IntegralCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='IntegralCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='IntegralCell');item=copy.deepcopy(structure);item.tag='StructureMember';item.set('Name','Area');obj.append(item)
            self.sheet(root).find('Block[@Type="INTG"]').set('Operand','Cells[1].Area')
        e=self.checked(nested);self.step(e);self.assertEqual(self.step(e),(3,.5));self.assertEqual(e.memory.read('Cells[0].Area.Out'),0)

    def test_wrong_profile_constant_type_redefinition_and_wire_direction_block(self):
        for kind in ('profile','constant','record','redefined','wiretype','aliasinput','output','function'):
            def mutate(root):
                sheet=self.sheet(root)
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="TotalState"]').set('Constant','true')
                elif kind=='record':sheet.find('Block[@Type="INTG"]').set('Operand','TotalState')
                elif kind=='redefined':
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='INTEGRATOR',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
                elif kind=='wiretype':sheet.find('IRef[@ID="3"]').set('Operand','TimingMode')
                elif kind=='aliasinput':sheet.find('Wire[@ToID="200"]').set('ToParam','IGainInv')
                elif kind=='output':sheet.find('Wire[@ToID="200"]').set('ToParam','Out')
                else:sheet.find('Block').tag='Function'
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_budget_failure_rolls_back_all_wire_writes_and_histories(self):
        e=self.checked();e.instruction_limit=20;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_preserves_shared_integral_and_total(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);self.step(e);before=self.snapshot(e)
        texts=['JSR(AccumulateSignals,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(self.step(candidate),(4.5,1.5));self.assertTrue(all(candidate.project.instruction_counts[n]==1 for n in ('UPDN','INTG')))

    def test_inventory_has_thirty_three_blocks_with_typed_integrator_aliases(self):
        e=self.checked();profile=e.report()['function_blocks'];self.assertEqual(len(profile['instructions']),33)
        self.assertEqual(profile['blocks']['status_aliases']['INTEGRATOR']['DeltaTInv'],'Status.31')
        self.assertIn('trapezoidal',profile['blocks']['accumulation']);self.assertFalse(profile['native_runtime_parity'])


if __name__=='__main__':unittest.main()
