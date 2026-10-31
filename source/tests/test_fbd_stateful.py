"""FBD timers, counters and edge pulses across scan, enable and fault boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


class FBDStatefulTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,direct=False,mode='project',defer=False):
        root=E.parse(SAMPLES/'FBDStateLab.L5X').getroot()
        if direct:
            wire=self.sheet(root).find('Wire[@ToID="400"][@ToParam="TimerEnable"]');wire.set('FromID','5');wire.set('FromParam','In')
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'state.L5X';E.ElementTree(root).write(path,encoding='utf8',xml_declaration=True)
        return Engine(Project(path),mode,'MainProgram/TimeAndCount' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="TimeAndCount"]/FBDContent/Sheet')

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e._st_counter_edges,e._st_oneshot_edges,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def step(self,e,dt=10):e.step(dt);return {tag:e.memory.read(tag) for tag in ('RisingPulse','FallingPulse','Count','CountDone','OnACC','OnDone','RetainedACC','OffACC','OffDone')}

    def test_edge_counter_done_and_timer_chain_in_one_invocation(self):
        e=self.checked();self.assertEqual(self.step(e)['Count'],0)
        e.memory.write('Input',True);v=self.step(e);self.assertTrue(v['RisingPulse']);self.assertEqual(v['Count'],1)
        e.memory.write('Input',False);v=self.step(e);self.assertTrue(v['FallingPulse']);self.assertEqual(v['Count'],1)
        e.memory.write('Input',True);v=self.step(e);self.assertEqual(v['Count'],2);self.assertTrue(v['CountDone']);self.assertEqual(v['OnACC'],0)
        for acc in (10,20,30,30):self.assertEqual(self.step(e)['OnACC'],acc)
        self.assertTrue(e.memory.read('OnDone'))

    def test_startup_high_input_does_not_generate_an_initial_pulse_or_count(self):
        e=self.checked();e.memory.write('Input',True);v=self.step(e)
        self.assertFalse(v['RisingPulse']);self.assertFalse(v['FallingPulse']);self.assertEqual(v['Count'],0)
        e.memory.write('Input',False);self.assertTrue(self.step(e)['FallingPulse'])
        e.memory.write('Input',True);self.assertEqual(self.step(e)['Count'],1)

    def test_held_input_clears_one_shot_and_does_not_repeat_count(self):
        e=self.checked();self.step(e);e.memory.write('Input',True);self.step(e)
        v=self.step(e);self.assertFalse(v['RisingPulse']);self.assertEqual(v['Count'],1)

    def test_counter_down_edges_reset_and_negative_preset_done(self):
        e=self.checked();self.step(e);e.memory.write('CountDown',True);self.assertEqual(self.step(e)['Count'],-1)
        self.assertEqual(self.step(e)['Count'],-1);e.memory.write('CounterReset',True);self.assertEqual(self.step(e)['Count'],0)
        e.memory.write('CounterReset',False);self.assertEqual(self.step(e)['Count'],0)
        e.memory.write('CountPreset',-1);self.assertTrue(self.step(e)['CountDone'])

    def test_counter_separate_up_then_down_wraps_set_both_flags(self):
        e=self.checked();self.step(e);e.memory.write('Counter.ACC',2147483647)
        e.memory.write('Input',True);e.memory.write('CountDown',True);v=self.step(e)
        self.assertEqual(v['Count'],2147483647);self.assertTrue(e.memory.read('Overflow'));self.assertTrue(e.memory.read('Underflow'))
        e.memory.write('CounterReset',True);v=self.step(e);self.assertEqual(v['Count'],0)
        self.assertFalse(e.memory.read('Overflow'));self.assertFalse(e.memory.read('Underflow'))

    def test_counter_reset_establishes_unknown_accumulator(self):
        e=self.checked();self.unknown(e,'Counter.ACC');e.memory.write('CounterReset',True)
        self.assertEqual(self.step(e)['Count'],0)

    def test_three_timer_algorithms_retain_arm_and_complete(self):
        e=self.checked(direct=True);e.memory.write('TimerInput',True);v=self.step(e)
        self.assertEqual((v['OnACC'],v['RetainedACC'],v['OffACC'],v['OffDone']),(0,5,0,True))
        v=self.step(e);self.assertEqual((v['OnACC'],v['RetainedACC']),(10,15))
        e.memory.write('TimerInput',False);v=self.step(e);self.assertEqual((v['OnACC'],v['RetainedACC'],v['OffACC']),(0,15,0))
        self.assertEqual(self.step(e)['OffACC'],10);v=self.step(e);self.assertEqual(v['OffACC'],20);self.assertFalse(v['OffDone'])

    def test_timer_enable_pause_differs_from_disabled_fbd_call(self):
        e=self.checked(direct=True);e.memory.write('TimerInput',True);self.step(e);self.step(e)
        e.memory.write('TimerInput',False)
        for _ in range(2):self.assertEqual(self.step(e)['RetainedACC'],15)
        e.memory.write('TimerInput',True);self.assertEqual(self.step(e)['RetainedACC'],15)
        self.assertEqual(self.step(e)['RetainedACC'],25)

    def test_disabled_active_timer_retains_history_and_catches_elapsed_when_reenabled(self):
        e=self.checked(direct=True)
        for tag in ('OnPreset','RetainPreset'):e.memory.write(tag,100)
        e.memory.write('TimerInput',True);self.step(e);self.step(e);before=copy.deepcopy(e.last_timer)
        e.memory.write('BlockEnable',False)
        for _ in range(2):
            v=self.step(e);self.assertEqual((v['OnACC'],v['RetainedACC']),(10,15));self.assertEqual(e.last_timer,before)
        e.memory.write('BlockEnable',True);v=self.step(e);self.assertEqual((v['OnACC'],v['RetainedACC']),(40,45))

    def test_timer_input_false_on_reenable_applies_pause_or_reset(self):
        e=self.checked(direct=True);e.memory.write('TimerInput',True);self.step(e);self.step(e)
        e.memory.write('BlockEnable',False);e.memory.write('TimerInput',False);self.step(e);self.step(e)
        e.memory.write('BlockEnable',True);v=self.step(e);self.assertEqual((v['OnACC'],v['RetainedACC'],v['OffACC']),(0,15,0))

    def test_skipped_routine_also_retains_clock_and_sampled_edges(self):
        e=self.checked(direct=True);e.memory.write('TimerInput',True);self.step(e);self.step(e)
        e.memory.write('ExecuteGraph',False);before=copy.deepcopy((e.last_timer,e._st_counter_edges,e._st_oneshot_edges))
        self.step(e);self.step(e);self.assertEqual((e.last_timer,e._st_counter_edges,e._st_oneshot_edges),before)
        e.memory.write('ExecuteGraph',True);self.assertEqual(self.step(e)['OnACC'],30)

    def test_disabled_one_shot_holds_pulse_without_resampling(self):
        e=self.checked();self.step(e);e.memory.write('Input',True);self.assertTrue(self.step(e)['RisingPulse'])
        before=copy.deepcopy((e._st_counter_edges,e._st_oneshot_edges));e.memory.write('BlockEnable',False);e.memory.write('Input',False)
        self.assertTrue(self.step(e)['RisingPulse']);self.assertEqual((e._st_counter_edges,e._st_oneshot_edges),before)
        e.memory.write('Input',True);e.memory.write('BlockEnable',True);v=self.step(e)
        self.assertFalse(v['RisingPulse']);self.assertEqual(v['Count'],1)

    def test_disabled_inputs_observed_only_when_reenabled(self):
        e=self.checked();self.step(e);e.memory.write('BlockEnable',False);e.memory.write('Input',True);self.step(e)
        e.memory.write('BlockEnable',True);v=self.step(e);self.assertTrue(v['RisingPulse']);self.assertEqual(v['Count'],1)

    def test_disabled_first_call_does_not_initialize_history(self):
        e=self.checked();e.memory.write('BlockEnable',False);self.step(e)
        self.assertEqual((e.last_timer,e._st_counter_edges,e._st_oneshot_edges),({},{},{}))
        e.memory.write('Input',True);e.memory.write('BlockEnable',True);v=self.step(e);self.assertEqual(v['Count'],0)

    def test_unwired_enables_remain_true(self):
        def unwire(root):
            sheet=self.sheet(root)
            for wire in list(sheet.findall('Wire')):
                if wire.get('ToParam')=='EnableIn':sheet.remove(wire)
        e=self.checked(unwire,direct=True);e.memory.write('BlockEnable',False);e.memory.write('TimerInput',True)
        self.step(e);self.assertEqual(self.step(e)['OnACC'],10)

    def test_negative_timer_preset_sets_status_and_enableout_without_scan_fault(self):
        e=self.checked(direct=True);e.memory.write('OnPreset',-1);e.memory.write('TimerInput',True);self.step(e)
        self.assertEqual(e.memory.read('OnStatus'),3);self.assertTrue(e.memory.read('OnFault'));self.assertTrue(e.memory.read('OnPresetInvalid'))
        self.assertFalse(e.memory.read('OnDelay.EnableOut'));self.assertFalse(e.fault)
        e.memory.write('OnPreset',30);self.assertEqual(self.step(e)['OnACC'],0);self.assertFalse(e.memory.read('OnFault'))

    def test_invalid_preset_pauses_timer_and_valid_recovery_omits_invalid_interval(self):
        e=self.checked(direct=True);e.memory.write('TimerInput',True);self.step(e);self.step(e)
        e.memory.write('OnPreset',-1);self.step(e);self.step(e);e.memory.write('OnPreset',30)
        self.assertEqual(self.step(e)['OnACC'],10);self.assertEqual(self.step(e)['OnACC'],20)

    def test_timer_reset_dominance_and_off_delay_disarms(self):
        e=self.checked(direct=True);e.memory.write('TimerInput',True);self.step(e);self.step(e)
        e.memory.write('ResetTimers',True);v=self.step(e);self.assertEqual((v['OnACC'],v['RetainedACC'],v['OffACC']),(0,0,20))
        self.assertFalse(v['OffDone']);e.memory.write('ResetTimers',False);e.memory.write('TimerInput',False)
        self.assertFalse(self.step(e)['OffDone'])

    def test_zero_presets_complete_on_delay_and_immediate_off_delay(self):
        e=self.checked(direct=True)
        for tag in ('OnPreset','RetainPreset','OffPreset'):e.memory.write(tag,0)
        e.memory.write('TimerInput',True);v=self.step(e);self.assertTrue(v['OnDone']);self.assertTrue(v['OffDone'])
        e.memory.write('TimerInput',False);self.assertFalse(self.step(e)['OffDone'])

    def test_unknown_required_values_fault_and_rollback_every_history_store(self):
        for tag in ('Input','CountDown','CountPreset','CounterReset','OnPreset','TimerInput','ResetTimers','BlockEnable'):
            e=self.checked();self.unknown(e,tag);before=self.snapshot(e)
            with self.subTest(tag=tag),self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_disabled_blocks_do_not_read_unknown_control_values(self):
        e=self.checked();e.memory.write('BlockEnable',False)
        for tag in ('Input','CountDown','CountPreset','CounterReset','OnPreset','TimerInput','ResetTimers'):self.unknown(e,tag)
        self.assertEqual(self.step(e)['Count'],0);self.assertEqual(e.last_timer,{})

    def test_unknown_timer_status_bit_cannot_become_known_false(self):
        def alias_only(root):
            sheet=self.sheet(root);sheet.remove(sheet.find('ORef[@Operand="OnStatus"]'));sheet.remove(sheet.find('Wire[@ToID="709"]'))
        e=self.checked(alias_only);self.unknown(e,'OnDelay.Status');e.memory.write('BlockEnable',False)
        with self.assertRaisesRegex(ModelError,'unknown: OnFault'):self.step(e)

    def test_late_ladder_fault_rolls_back_edges_counters_and_elapsed_time(self):
        e=self.checked(direct=True);self.step(e);e.memory.write('Input',True);e.memory.write('TimerInput',True);e.memory.write('FaultDivisor',0)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);v=self.step(e)
        self.assertTrue(v['RisingPulse']);self.assertEqual(v['Count'],1);self.assertEqual(v['OnACC'],0)
        self.assertEqual(self.step(e)['OnACC'],10)

    def test_fault_after_elapsed_advance_does_not_double_charge_retry(self):
        e=self.checked(direct=True);e.memory.write('TimerInput',True);self.step(e);self.step(e)
        e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e)['OnACC'],20)

    def test_run_resets_clock_and_edge_history_but_retains_counter_and_rtor_acc(self):
        e=self.checked(direct=True);self.step(e);e.memory.write('TimerInput',True);e.memory.write('Input',True);self.step(e);self.step(e)
        count=e.memory.read('Count');retained=e.memory.read('RetainedACC');e.enter_run()
        self.assertEqual((e.last_timer,e._st_counter_edges,e._st_oneshot_edges),({},{},{}))
        v=self.step(e);self.assertEqual(v['Count'],count);self.assertEqual(v['OnACC'],0);self.assertEqual(v['RetainedACC'],retained)
        self.assertFalse(v['RisingPulse'])

    def test_periodic_releases_and_isolated_harness_share_timing_profile(self):
        def periodic(root):task=root.find('./Controller/Tasks/Task');task.set('Type','Periodic');task.set('Rate','10')
        e=self.checked(periodic,direct=True);e.memory.write('TimerInput',True)
        for _ in range(3):self.step(e)
        self.assertEqual(e.memory.read('OnACC'),20)
        h=self.checked(direct=True,mode='routine',defer=True);self.assertTrue(h.memory.read('OnDelay.EnableIn'))
        h.enter_run();h.memory.write('TimerInput',True);self.step(h);self.assertEqual(self.step(h)['OnACC'],10)

    def test_same_kind_st_calls_share_fbd_history_without_double_counting(self):
        def st(root):logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(TimeAndCount,0); TONR(OnDelay); CTUD(Counter);'])
        e=self.checked(st,direct=True);e.memory.write('TimerInput',True);self.step(e);e.memory.write('Input',True)
        self.step(e);self.assertEqual(e.memory.read('Counter.ACC'),1);self.assertEqual(e.memory.read('OnDelay.ACC'),10)

    def test_mixed_timer_or_one_shot_kinds_across_languages_fault_transactionally(self):
        for text in ('RTOR(OnDelay);','OSFI(Rising);'):
            def st(root):logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(TimeAndCount,0); '+text])
            e=self.checked(st);before=self.snapshot(e)
            with self.subTest(text=text),self.assertRaisesRegex(ModelError,'different|Mixed'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_timer_diagnostic_enableout_can_gate_an_independent_block(self):
        def gate(root):
            w=self.sheet(root).find('Wire[@ToID="500"][@ToParam="EnableIn"]');w.set('FromID','400');w.set('FromParam','EnableOut')
        e=self.checked(gate,direct=True);e.memory.write('TimerInput',True);self.step(e);self.step(e)
        e.memory.write('OnPreset',-1);v=self.step(e);self.assertEqual(v['RetainedACC'],15);self.assertFalse(e.memory.read('Retained.EnableOut'))

    def test_static_nested_timer_record_and_program_local_counter_alias(self):
        def nested(root):
            tags=root.find('./Controller/Tags');counter=tags.find('Tag[@Name="Counter"]');tags.remove(counter);root.find('./Controller/Programs/Program/Tags').append(counter)
            E.SubElement(tags,'Tag',Name='LocalCounter',TagType='Alias',AliasFor='Program:MainProgram.Counter');self.sheet(root).find('Block[@ID="300"]').set('Operand','LocalCounter')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='TimeCell',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='Timer',DataType='FBD_TIMER',Dimension='0')
            timer=tags.find('Tag[@Name="OnDelay"]');structure=timer.find('Data/Structure');tags.remove(timer)
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='TimeCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='TimeCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='TimeCell');item=copy.deepcopy(structure);item.tag='StructureMember';item.set('Name','Timer');obj.append(item)
            self.sheet(root).find('Block[@ID="400"]').set('Operand','Cells[1].Timer')
        e=self.checked(nested,direct=True);e.memory.write('TimerInput',True);self.step(e);self.assertEqual(self.step(e)['OnACC'],10)
        self.assertEqual(e.memory.read('Cells[0].Timer.ACC'),0)

    def test_event_fault_restores_fbd_edge_and_timer_histories(self):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(TimeAndCount,0); EVENT(StateEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            logic(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='StateEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);self.step(e);e.memory.write('Input',True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e)['Count'],1)

    def test_fbd_event_task_shares_timer_history_at_same_timestamp(self):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(TimeAndCount,0); EVENT(StateEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='TimeAndCount',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            E.SubElement(p,'Routines').append(copy.deepcopy(root.find('.//Routine[@Name="TimeAndCount"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='StateEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event,direct=True);e.memory.write('TimerInput',True);self.step(e);self.assertEqual(self.step(e)['OnACC'],10)

    def test_instruction_budget_fault_rolls_back_all_state_stores(self):
        e=self.checked();e.instruction_limit=30;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_preserves_elapsed_and_edge_history(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked(direct=True);e.memory.write('TimerInput',True);self.step(e);self.step(e);before=self.snapshot(e)
        neutral=['JSR(TimeAndCount,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(candidate._st_counter_edges,e._st_counter_edges);self.assertEqual(candidate._st_oneshot_edges,e._st_oneshot_edges)
        self.assertEqual(self.step(candidate)['OnACC'],20)

    def test_type_profile_constant_output_pin_and_record_overlap_blocks(self):
        for kind in ('profile','constant','wrongtype','outputinput','overlap'):
            def mutate(root):
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="OnDelay"]').set('Constant','true')
                elif kind=='wrongtype':self.sheet(root).find('Block[@ID="400"]').set('Operand','Counter')
                elif kind=='outputinput':self.sheet(root).find('Wire[@ToID="400"]').set('ToParam','ACC')
                else:self.sheet(root).find('Block[@ID="500"]').set('Operand','OnDelay')
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_report_has_forty_blocks_and_timer_diagnostic_pins(self):
        e=self.checked();profile=e.report()['function_blocks'];self.assertEqual(len(profile['instructions']),40)
        self.assertEqual(profile['blocks']['status_aliases']['FBD_TIMER'],{'InstructFault':'Status.0','PresetInv':'Status.1'})
        self.assertFalse(profile['native_runtime_parity'])


if __name__=='__main__':unittest.main()
