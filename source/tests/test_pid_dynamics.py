"""PID derivative sampling and deadband state, separate from native qualification."""
import copy
import unittest
import test_ladder_pid as fixtures
from xml.etree import ElementTree as E
from logixlab.model import ModelError


class PIDDynamicsTests(unittest.TestCase):
    setUp = fixtures.LadderPIDTests.setUp
    engine = fixtures.LadderPIDTests.engine
    checked = fixtures.LadderPIDTests.checked
    run_step = fixtures.LadderPIDTests.run_step
    snapshot = fixtures.LadderPIDTests.snapshot

    def derivative(self, values=None, **kwargs):
        return self.checked(dict(KP=0,KI=0,KD=2,BIAS=50,CTL=1<<22)|dict(values or {}),**kwargs)

    def state(self,e):
        return next(v for k,v in e.last_timer.items() if k[0]=='RLL-PID')

    def test_independent_error_derivative_includes_setpoint_change(self):
        e=self.derivative({'CTL':(1<<22)|(1<<27)})
        self.assertEqual(self.run_step(e,Execute=True),50);self.assertEqual(self.state(e)['derivative'],0)
        self.assertEqual(self.run_step(e,PV=25),40);self.assertEqual(self.state(e)['derivative'],-10)
        self.assertEqual(self.run_step(e,Loop__SP=55),60);self.assertEqual(self.state(e)['derivative'],10)

    def test_pv_derivative_avoids_setpoint_kick(self):
        e=self.derivative();self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,Loop__SP=60),50)
        self.assertEqual(self.run_step(e,PV=25),40)
        self.assertEqual(self.run_step(e),50)

    def test_direct_action_derivative_sign_for_both_sources(self):
        for doe in (False,True):
            with self.subTest(doe=doe):
                e=self.derivative({'CTL':(1<<22)|(1<<25)|((1<<27) if doe else 0)})
                self.run_step(e,Execute=True);self.assertEqual(self.run_step(e,PV=25),60)
                self.assertEqual(self.run_step(e,Loop__SP=55),40 if doe else 50)

    def test_dependent_rate_minutes_and_proportional_gain(self):
        e=self.derivative({'KP':2,'KD':.5,'BIAS':0,'CTL':(1<<22)|(1<<23)})
        self.assertEqual(self.run_step(e,Execute=True),60)
        self.assertEqual(self.run_step(e,PV=20.25),44.5)
        self.assertEqual(self.state(e)['derivative'],-15)
        self.assertEqual(self.run_step(e,Loop__KP=0,PV=20.5),0)
        self.assertEqual(self.state(e)['derivative'],0)

    def test_percent_scaling_and_configured_update_seconds(self):
        e=self.derivative({'MINS':-50,'MAXS':150,'MINI':4000,'MAXI':20000,'UPD':.5})
        self.run_step(e,Execute=True,PV=8000)
        e.memory.write('PV',8160);e.step(60000)
        self.assertEqual(e.memory.read('Loop.PV'),2);self.assertEqual(e.memory.read('CV'),46)

    def test_derivative_mode_action_and_scaling_changes_reprime(self):
        e=self.derivative();self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,Loop__DOE=True,Loop__SP=60),50)
        self.assertEqual(self.run_step(e,Loop__SP=61),52)
        self.assertEqual(self.run_step(e,Loop__CA=True),50)
        self.assertEqual(self.run_step(e,Loop__MAXS=200),50)
        self.assertEqual(self.state(e)['derivative'],0)

    def test_zero_kd_still_refreshes_samples_before_enabling(self):
        e=self.derivative({'KD':0});self.run_step(e,Execute=True);self.run_step(e,PV=30)
        self.assertEqual(self.run_step(e,Loop__KD=2,PV=31),48)

    def test_false_call_skips_samples_and_no_elapsed_catchup(self):
        e=self.derivative();self.run_step(e,Execute=True);before=copy.deepcopy(e.last_timer)
        self.run_step(e,Execute=False,PV=30,Loop__UPD=0);self.assertEqual(e.last_timer,before)
        self.assertEqual(self.run_step(e,Execute=True,PV=32,Loop__UPD=1),26)

    def test_skipped_routine_retains_derivative_sample(self):
        def sub(root):
            routines=root.find('.//Routines');routine=copy.deepcopy(routines.find('Routine'))
            routine.set('Name','Regulate');routine.find('RLLContent').find('Rung/Text').text='PID(Loop,PV,0,CV,0,0,0);';routines.append(routine)
        e=self.derivative(lines=['XIC(Execute)JSR(Regulate,0);'],mutate=sub)
        self.run_step(e,Execute=True);self.run_step(e,Execute=False,PV=30)
        self.assertEqual(self.run_step(e,Execute=True,PV=32),26)

    def test_manual_samples_and_first_auto_transfer_suppress_derivative(self):
        e=self.derivative();self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,Loop__SWM=True,Loop__SO=70,PV=30),70)
        self.assertEqual(self.run_step(e,Loop__SWM=False,PV=35),70)
        self.assertEqual(self.state(e)['derivative'],0)
        self.assertEqual(self.run_step(e,PV=36),68)

    def test_derivative_occupies_automatic_integral_headroom(self):
        e=self.derivative({'KP':1,'KI':1,'KD':1,'BIAS':0})
        self.assertEqual(self.run_step(e,Execute=True),60)
        self.assertEqual(self.run_step(e,PV=10),100)
        self.assertEqual((self.state(e)['derivative'],e.memory.read('Loop.DATA[0]')),(10,50))
        self.assertEqual(self.run_step(e),100);self.assertEqual(e.memory.read('Loop.DATA[0]'),60)

    def test_no_zero_crossing_deadband_holds_output_and_integral(self):
        e=self.checked({'DB':2,'CTL':1<<20});self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,PV=49),45);self.assertTrue(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,PV=51),45);self.assertEqual(e.memory.read('Loop.DATA[0]'),15)
        self.assertEqual(self.run_step(e,PV=53),10.5);self.assertFalse(e.memory.read('Loop.EWD'))

    def test_deadband_boundaries_are_inclusive_and_zero_disables(self):
        e=self.checked({'DB':2,'CTL':1<<20});self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,PV=48),45);self.assertEqual(self.run_step(e,PV=52),45)
        self.run_step(e,PV=52.25);self.assertFalse(e.memory.read('Loop.EWD'))
        self.run_step(e,PV=50,Loop__DB=0);self.assertFalse(e.memory.read('Loop.EWD'))

    def test_zero_crossing_waits_then_holds_until_exit(self):
        e=self.checked({'DB':2});self.assertEqual(self.run_step(e,Execute=True,PV=47),4.5)
        self.assertEqual(self.run_step(e,PV=49),3);self.assertFalse(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,PV=50.5),3);self.assertTrue(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,PV=49),3);self.assertTrue(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,PV=47),6.5);self.assertFalse(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,PV=49),5);self.assertFalse(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,PV=50),5);self.assertTrue(e.memory.read('Loop.EWD'))

    def test_crossing_directly_from_outside_to_opposite_inside_holds(self):
        for ca,pv in ((False,51),(True,51)):
            with self.subTest(ca=ca):
                e=self.checked({'DB':2,'BIAS':50,'KI':0,'CTL':(1<<25) if ca else 0})
                old=self.run_step(e,Execute=True,PV=47)
                self.assertEqual(self.run_step(e,PV=pv),old);self.assertTrue(e.memory.read('Loop.EWD'))

    def test_deadband_latch_rearms_on_setpoint_action_or_range_change(self):
        for field,value in (('SP',51),('CA',True),('MAXS',102),('DB',1)):
            with self.subTest(field=field):
                e=self.checked({'DB':2});self.run_step(e,Execute=True,PV=47);self.run_step(e,PV=49);self.run_step(e,PV=51)
                e.memory.write('Loop.'+field,value)
                # Avoid exact zero for the changed setpoint/range: exact zero
                # is intentionally a crossing in the software profile.
                if field in ('SP','MAXS'):e.memory.write('PV',50)
                e.step();self.assertFalse(e.memory.read('Loop.EWD'))

    def test_manual_overrides_deadband_and_nozc_auto_holds_manual_output(self):
        e=self.checked({'DB':2,'CTL':1<<20});self.run_step(e,Execute=True)
        self.run_step(e,PV=49);self.assertTrue(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,Loop__SWM=True,Loop__SO=70),70);self.assertFalse(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,Loop__SO=60),60)
        self.assertEqual(self.run_step(e,Loop__SWM=False),60);self.assertTrue(e.memory.read('Loop.EWD'))

    def test_manual_resets_zero_crossing_history(self):
        e=self.checked({'DB':2});self.run_step(e,Execute=True,PV=47);self.run_step(e,PV=51)
        self.assertTrue(e.memory.read('Loop.EWD'))
        self.run_step(e,Loop__SWM=True,Loop__SO=60)
        self.assertEqual(self.run_step(e,Loop__SWM=False,PV=49),62);self.assertFalse(e.memory.read('Loop.EWD'))

    def test_first_held_call_uses_represented_out_and_known_requirement(self):
        e=self.checked({'DB':2,'CTL':1<<20,'OUT':35})
        self.assertEqual(self.run_step(e,Execute=True,PV=49),35);self.assertEqual(e.memory.read('Loop.DATA[0]'),0)
        def omit(root):
            obj=root.find('.//Structure[@DataType="PID"]');obj.remove(obj.find('DataValueMember[@Name="OUT"]'))
        e=self.checked({'DB':2,'CTL':1<<20},mutate=omit);e.memory.write('Execute',True);e.memory.write('PV',49);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'OUT is unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_first_exact_zero_uses_saved_output_with_zero_crossing(self):
        e=self.checked({'DB':2,'OUT':35});self.assertEqual(self.run_step(e,Execute=True,PV=50),35)
        self.assertTrue(e.memory.read('Loop.EWD'))

    def test_deadband_refreshes_derivative_samples_and_skips_unused_overflow(self):
        e=self.derivative({'DB':5,'CTL':(1<<20)|(1<<22),'KD':3e38,'OUT':35})
        self.assertEqual(self.run_step(e,Execute=True,PV=49),35)
        self.assertEqual(self.run_step(e,PV=51),35);self.assertEqual(self.state(e)['derivative'],0)
        self.assertEqual(self.run_step(e,Loop__KD=1,PV=56),45);self.assertFalse(e.memory.read('Loop.EWD'))

    def test_held_percent_is_clamped_and_rescaled_when_configuration_changes(self):
        e=self.checked({'DB':2,'CTL':1<<20,'OUT':75});self.run_step(e,Execute=True,PV=49)
        self.assertEqual(self.run_step(e,Loop__MAXO=60,Loop__MINCV=4000,Loop__MAXCV=20000),13600)
        self.assertEqual(e.memory.read('Loop.OUT'),60);self.assertTrue(e.memory.read('Loop.OLH'))

    def test_run_and_ini_reset_derivative_and_deadband_history(self):
        e=self.derivative();self.run_step(e,Execute=True);self.run_step(e,PV=25)
        self.assertEqual(self.run_step(e,Loop__INI=False,PV=30),50)
        e.enter_run();self.assertEqual(self.run_step(e,PV=35),50)
        e=self.checked({'DB':2});self.run_step(e,Execute=True,PV=47);self.run_step(e,PV=51)
        self.assertTrue(e.memory.read('Loop.EWD'));e.enter_run();self.run_step(e,PV=51);self.assertFalse(e.memory.read('Loop.EWD'))

    def test_late_fault_restores_new_derivative_sample_and_deadband_latch(self):
        e=self.checked({'DB':2});self.run_step(e,Execute=True,PV=47)
        e.memory.write('PV',51);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        self.assertEqual(self.run_step(e,FaultDivisor=1),4.5);self.assertTrue(e.memory.read('Loop.EWD'))
        e=self.derivative();self.run_step(e,Execute=True)
        e.memory.write('PV',25);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(self.run_step(e,FaultDivisor=1),40)

    def test_derivative_range_fault_preserves_sample_and_corrected_retry(self):
        e=self.derivative({'KD':3e38});self.run_step(e,Execute=True);e.memory.write('PV',22);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'finite REAL range'):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(self.run_step(e,Loop__KD=1),48)

    def test_smoothing_gate_negative_kd_db_and_false_skip(self):
        for settings in ({'KD':1},{'KD':-1},{'DB':-1}):
            e=self.checked(settings);self.run_step(e)
            e.memory.write('Execute',True);before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)
        e=self.checked({'KD':0});self.run_step(e,Execute=True);self.assertEqual(self.state(e)['derivative'],0)

    def test_existing_data_slots_remain_uninterpreted_and_report_limits_explicit(self):
        e=self.derivative();e.memory.write('Loop.DATA[1]',123);e.memory.write('Loop.DATA[7]',456)
        self.run_step(e,Execute=True);self.run_step(e,PV=25)
        self.assertEqual((e.memory.read('Loop.DATA[1]'),e.memory.read('Loop.DATA[7]')),(123,456))
        p=e.report()['ladder_pid'];self.assertIn('NDF',p['derivative']);self.assertIn('NOZC',p['deadband'])
        self.assertFalse(p['native_runtime_parity']);self.assertFalse(p['packed_layout'])

    def test_distinct_records_do_not_share_samples_or_deadband_latches(self):
        def second(root):
            tags=root.find('./Controller/Tags');obj=copy.deepcopy(tags.find('Tag[@Name="Loop"]'));obj.set('Name','Other');tags.append(obj)
        e=self.derivative({'KD':1},lines=['PID(Loop,PV,0,CV,0,0,0);','PID(Other,PV,0,CV,0,0,0);'],mutate=second)
        e.memory.write('Other.KD',2);self.run_step(e);self.run_step(e,PV=25)
        self.assertEqual((e.memory.read('Loop.OUT'),e.memory.read('Other.OUT')),(45,40))
        self.run_step(e,Loop__DB=30,Loop__NOZC=True,PV=26)
        self.assertEqual((e.memory.read('Loop.OUT'),e.memory.read('Other.OUT')),(45,48))
        self.assertTrue(e.memory.read('Loop.EWD'));self.assertFalse(e.memory.read('Other.EWD'))

    def test_periodic_release_still_uses_configured_upd_for_derivative(self):
        def periodic(root):root.find('.//Task').attrib.update(Type='PERIODIC',Rate='250')
        e=self.derivative({'UPD':.5},mutate=periodic);e.memory.write('Execute',True);e.step(250)
        e.memory.write('PV',25);e.step(250);self.assertEqual(e.memory.read('CV'),30)
        self.assertEqual(self.state(e)['at'],500)

    def test_event_pid_and_later_caller_fault_restore_samples_and_scheduler(self):
        def event(root):
            programs=root.find('./Controller/Programs');p=E.SubElement(programs,'Program',Name='Regulator',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='RLL')
            E.SubElement(E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='PID(Loop,PV,0,CV,0,0,0);'
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='RegulateTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false',DisableUpdateOutputs='true')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
            E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='Regulator')
        e=self.derivative(lines=['EVENT(RegulateTask);','DIV(1,FaultDivisor,Quotient);'],mutate=event)
        self.assertEqual(self.run_step(e),50);e.memory.write('PV',25);e.memory.write('FaultDivisor',0)
        before=self.snapshot(e);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(e.scheduler_description(),schedule)
        self.assertEqual(self.run_step(e,FaultDivisor=1),40)

    def test_instruction_budget_fault_restores_derivative_baseline(self):
        e=self.derivative();e.instruction_limit=2;e.memory.write('Execute',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.instruction_limit=100;self.assertEqual(self.run_step(e),50);self.assertEqual(self.run_step(e,PV=25),40)

    def test_routine_harness_runs_derivative_and_deadband(self):
        e=self.derivative({'DB':2,'CTL':(1<<20)|(1<<22)},mode='routine',routine='MainProgram/MainRoutine')
        self.run_step(e,Execute=True);self.assertEqual(self.run_step(e,PV=49),50)
        self.assertTrue(e.memory.read('Loop.EWD'))


if __name__ == '__main__':unittest.main()
