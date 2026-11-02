"""Manual PV tracking and explicit inhold readback, not an analog module model."""
import copy
import unittest
import test_ladder_pid as fixtures
from xml.etree import ElementTree as E
from logixlab.model import ModelError


class PIDRestartTests(unittest.TestCase):
    setUp = fixtures.LadderPIDTests.setUp
    engine = fixtures.LadderPIDTests.engine
    checked = fixtures.LadderPIDTests.checked
    run_step = fixtures.LadderPIDTests.run_step
    snapshot = fixtures.LadderPIDTests.snapshot

    def test_pvt_tracks_scaled_pv_in_software_manual_and_retains_on_auto(self):
        e=self.checked();self.assertEqual(self.run_step(e,Execute=True,SoftwareManual=True,PVTracking=True,Loop__SO=70),70)
        self.assertEqual((e.memory.read('Loop.SP'),e.memory.read('Loop.ERR'),e.memory.read('Loop.DATA[0]')),(20,0,70))
        self.run_step(e,PV=25);self.assertEqual(e.memory.read('Loop.SP'),25)
        self.assertEqual(self.run_step(e,SoftwareManual=False),70)
        self.run_step(e,PV=30);self.assertEqual(e.memory.read('Loop.SP'),25)

    def test_pvt_hardware_manual_both_actions_and_scaled_input(self):
        for ca in (False,True):
            with self.subTest(ca=ca):
                e=self.checked({'MINI':4000,'MAXI':20000,'MINS':-50,'MAXS':150})
                self.assertEqual(self.run_step(e,Execute=True,Manual=True,PVTracking=True,Loop__CA=ca,Tieback=60,PV=8000),60)
                self.assertEqual((e.memory.read('Loop.PV'),e.memory.read('Loop.SP'),e.memory.read('Loop.ERR')),(0,0,0))

    def test_pvt_does_not_change_sp_in_automatic_or_false_calls(self):
        e=self.checked();self.run_step(e,PVTracking=True,PV=30);self.assertEqual(e.memory.read('Loop.SP'),50)
        self.run_step(e,Execute=True);self.assertEqual(e.memory.read('Loop.SP'),50)

    def test_tracking_can_establish_unknown_sp_only_in_controlling_manual(self):
        def missing(root):
            obj=root.find('.//Structure[@DataType="PID"]');obj.remove(obj.find('DataValueMember[@Name="SP"]'))
        e=self.checked(mutate=missing);self.assertEqual(self.run_step(e,Execute=True,SoftwareManual=True,PVTracking=True,Loop__SO=60),60)
        self.assertEqual(e.memory.read('Loop.SP'),20)
        e=self.checked(mutate=missing);e.memory.write('PVTracking',True);e.memory.write('Execute',True)
        with self.assertRaisesRegex(ModelError,'SP is unknown'):e.step()

    def test_out_of_range_tracked_sp_rolls_back(self):
        e=self.checked();self.run_step(e,Execute=True,Manual=True,PVTracking=True)
        e.memory.write('PV',101);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'engineering range'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_tracking_bias_with_zero_ki_and_nobc(self):
        for nobc,expected in ((False,70),(True,0)):
            e=self.checked({'KI':0});self.run_step(e,Execute=True,SoftwareManual=True,PVTracking=True,Loop__SO=70,Loop__NOBC=nobc)
            self.assertEqual(e.memory.read('Loop.BIAS'),0 if nobc else 70)
            self.assertEqual(self.run_step(e,SoftwareManual=False),expected)

    def test_inhold_copies_readback_and_seeds_integral_for_auto_release(self):
        e=self.checked();self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,Inhold=True,Readback=75),75)
        self.assertEqual((e.memory.read('Loop.OUT'),e.memory.read('Loop.DATA[0]')),(75,45))
        self.assertEqual(self.run_step(e,Inhold=False),75);self.assertEqual(self.run_step(e),90)

    def test_inhold_is_held_each_true_call_and_does_not_clear_input(self):
        e=self.checked();self.assertEqual(self.run_step(e,Execute=True,Inhold=True,Readback=70),70)
        self.assertTrue(e.memory.read('Inhold'));self.assertEqual(self.run_step(e,Readback=60),60)
        self.assertTrue(e.memory.read('Inhold'));self.assertEqual(e.memory.read('Loop.DATA[0]'),30)

    def test_readback_uses_cv_units_and_inverse_percent(self):
        e=self.checked({'MINCV':4000,'MAXCV':20000})
        self.assertEqual(self.run_step(e,Execute=True,Inhold=True,Readback=16000),16000)
        self.assertEqual(e.memory.read('Loop.OUT'),75)
        self.assertEqual(self.run_step(e,Inhold=False),16000)

    def test_zero_ki_restart_seeds_bias_even_when_manual_nobc_is_set(self):
        e=self.checked({'KI':0,'CTL':1<<21});self.assertEqual(self.run_step(e,Execute=True,Inhold=True,Readback=70),70)
        self.assertEqual(e.memory.read('Loop.BIAS'),40)
        self.assertEqual(self.run_step(e,Inhold=False),70)

    def test_inhold_overrides_manual_and_does_not_consume_station_or_so(self):
        e=self.checked();e.memory.values['tieback']=None;e.memory.values['loop']['SO']=None
        e.memory.values['loop']['MINTIE']=None;e.memory.values['loop']['MAXTIE']=None
        self.assertEqual(self.run_step(e,Execute=True,Manual=True,SoftwareManual=True,Inhold=True,Readback=65),65)
        self.assertEqual(e.memory.read('Loop.SO'),65)
        self.assertEqual(self.run_step(e,Inhold=False,Manual=False),65)

    def test_inhold_suppresses_manual_pvt_and_keeps_requested_sp(self):
        e=self.checked();self.run_step(e,Execute=True,Manual=True,PVTracking=True,Inhold=True,Readback=60)
        self.assertEqual((e.memory.read('Loop.SP'),e.memory.read('Loop.ERR')),(50,30))
        self.run_step(e,Inhold=False);self.assertEqual(e.memory.read('Loop.SP'),20)

    def test_inhold_bypasses_deadband_and_auto_output_limits(self):
        e=self.checked({'DB':2,'MINO':20,'MAXO':60,'CTL':1<<20})
        self.assertEqual(self.run_step(e,Execute=True,PV=49,Inhold=True,Readback=80),80)
        self.assertFalse(e.memory.read('Loop.EWD'));self.assertFalse(e.memory.read('Loop.OLH'))
        self.assertEqual(self.run_step(e,Inhold=False),60);self.assertTrue(e.memory.read('Loop.EWD'))

    def test_inhold_integer_cv_bypasses_band_zero_and_mirrors_assigned(self):
        def integer(root):
            tag=root.find('./Controller/Tags/Tag[@Name="CV"]');tag.set('DataType','INT');tag.find('./Data/DataValue').set('DataType','INT')
        e=self.checked({'DB':2,'CTL':1<<20},mutate=integer)
        self.assertEqual(self.run_step(e,Execute=True,PV=49,Inhold=True,Readback=70.5),70)
        self.assertEqual((e.memory.read('Loop.OUT'),e.memory.read('Loop.DATA[14]')),(70,70))
        self.assertEqual(self.run_step(e,Inhold=False),0)

    def test_range_and_destination_conversion_failures_restore_state(self):
        for value in (-1,101):
            e=self.checked();e.memory.write('Execute',True);e.memory.write('Inhold',True);e.memory.write('Readback',value);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'CV scaling span'):e.step()
            self.assertEqual(self.snapshot(e),before)
        def narrow(root):
            tag=root.find('./Controller/Tags/Tag[@Name="CV"]');tag.set('DataType','SINT');tag.find('./Data/DataValue').set('DataType','SINT')
        e=self.checked({'MAXCV':200},mutate=narrow);e.memory.write('Execute',True);e.memory.write('Inhold',True);e.memory.write('Readback',150);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'SINT overflow'):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(self.run_step(e,Readback=100),100)

    def test_inhold_readback_only_consumed_when_flag_is_true(self):
        e=self.checked();e.memory.values['readback']=None
        self.assertEqual(self.run_step(e,Execute=True),45)
        self.assertEqual(self.run_step(e,SoftwareManual=True,Loop__SO=60),60)
        e.memory.write('Inhold',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(self.run_step(e,Readback=70),70)

    def test_unknown_bool_faults_on_true_call_but_false_skips_it(self):
        e=self.checked();e.memory.values['inhold']=None;self.run_step(e)
        e.memory.write('Execute',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_false_and_skipped_calls_do_not_sample_readback(self):
        e=self.checked();self.run_step(e,Execute=True,Inhold=True,Readback=60);before=copy.deepcopy(e.last_timer)
        self.assertEqual(self.run_step(e,Execute=False,Readback=80),60);self.assertEqual(e.last_timer,before)
        self.assertEqual(self.run_step(e,Execute=True),80)

    def test_restart_refreshes_samples_and_release_suppresses_derivative(self):
        e=self.checked({'KP':0,'KI':0,'KD':2,'BIAS':50,'CTL':1<<22});self.run_step(e,Execute=True)
        self.run_step(e,PV=25);self.assertEqual(e.memory.read('CV'),40)
        self.assertEqual(self.run_step(e,Inhold=True,Readback=70,PV=30),70)
        self.assertEqual(self.run_step(e,Inhold=False),70)
        self.assertEqual(self.run_step(e,PV=31),68)

    def test_later_fault_restores_tracking_sp_and_inhold_history(self):
        e=self.checked();self.run_step(e,Execute=True)
        e.memory.write('Manual',True);e.memory.write('PVTracking',True);e.memory.write('PV',25);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.run_step(e,FaultDivisor=1);self.assertEqual(e.memory.read('Loop.SP'),25)
        e.memory.write('Inhold',True);e.memory.write('Readback',80);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(self.run_step(e,FaultDivisor=1),80)

    def test_inhold_bit_alias_and_readback_selected_array(self):
        def inputs(root):
            tags=root.find('./Controller/Tags')
            t=E.SubElement(tags,'Tag',Name='Flags',TagType='Base',DataType='DINT');E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='1')
            t=E.SubElement(tags,'Tag',Name='Values',TagType='Base',DataType='REAL',Dimensions='2');arr=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='REAL',Dimensions='2')
            for i,value in enumerate((70,777)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(value))
        e=self.checked(lines=['PID(Loop,PV,0,CV,0,Flags.0,Values[0]);'],mutate=inputs)
        self.assertEqual(self.run_step(e),70);self.assertEqual(e.memory.read('Values[1]'),777)

    def test_sentinel_zero_value_and_unsupported_operands(self):
        e=self.checked(lines=['PID(Loop,PV,0,CV,0,Inhold,0);']);self.assertEqual(self.run_step(e,Inhold=True),0)
        for text in ('PID(Loop,PV,0,CV,Loop,0,0);','PID(Loop,PV,0,CV,0,TRUE,0);','PID(Loop,PV,0,CV,0,PV,Readback);',
                     'PID(Loop,PV,0,CV,0,Inhold,70);','PID(Loop,PV,0,CV,0,Loop.EN,Readback);','PID(Loop,PV,0,CV,0,Inhold,Loop.OUT);','PID(Loop,PV,0,CV,0,S:FS,Readback);'):
            with self.subTest(text=text):self.assertTrue(self.engine(lines=[text]).blockers)

    def test_independent_loop_inputs_and_manual_tracking_aliases(self):
        e=self.checked();self.run_step(e,Execute=True,IntExecute=True,Manual=True,PVTracking=True,Tieback=60)
        self.assertEqual((e.memory.read('Loop.SP'),e.memory.read('IntLoop.SP')),(20,50))
        self.run_step(e,Inhold=True,Readback=70,IntInhold=True,IntReadback=20000)
        self.assertEqual((e.memory.read('CV'),e.memory.read('RawCV')),(70,20000))
        self.assertEqual(e.memory.read('Loop.SP'),20)

    def test_run_reentry_uses_current_inhold_without_saved_solver_state(self):
        e=self.checked();self.run_step(e,Execute=True,Inhold=True,Readback=70)
        e.enter_run();self.assertEqual(self.run_step(e,Readback=60),60)
        self.assertEqual(self.run_step(e,Inhold=False),60)

    def test_periodic_and_routine_modes(self):
        def periodic(root):root.find('.//Task').attrib.update(Type='PERIODIC',Rate='250')
        e=self.checked(mutate=periodic);e.memory.write('Execute',True);e.memory.write('Inhold',True);e.step(250)
        self.assertEqual(e.memory.read('CV'),50)
        e=self.checked(mode='routine',routine='MainProgram/MainRoutine');self.assertEqual(self.run_step(e,Execute=True,Inhold=True,Readback=70),70)

    def test_report_separates_inhold_inputs_from_module_model(self):
        p=self.checked().report()['ladder_pid'];self.assertIn('PVT',p['pv_tracking']);self.assertIn('acknowledgement',p['inhold'])
        self.assertFalse(p['native_runtime_parity']);self.assertFalse(p['packed_layout'])

    def test_inhold_bit_alias_unknown_backing_word_and_retry(self):
        def inputs(root):
            tags=root.find('./Controller/Tags')
            t=E.SubElement(tags,'Tag',Name='Flags',TagType='Base',DataType='DINT');E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='1')
            E.SubElement(tags,'Tag',Name='Feedback',TagType='Alias',DataType='BOOL',AliasFor='Flags.0')
        e=self.checked(lines=['PID(Loop,PV,0,CV,0,Feedback,Readback);'],mutate=inputs)
        self.assertEqual(self.run_step(e,Readback=70),70)
        e.memory.values['flags']=None;before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(self.run_step(e,Flags=0),70)

    def test_whole_bool_array_inhold_is_rejected(self):
        def array(root):
            t=root.find('./Controller/Tags/Tag[@Name="Inhold"]');t.set('Dimensions','2');t.remove(t.find('Data'))
            arr=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='BOOL',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]',Value='0')
        self.assertTrue(self.engine(mutate=array).blockers)

    def test_inhold_later_fault_rolls_back_event_release_and_tracking(self):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='Regulator',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='RLL')
            E.SubElement(E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='PID(Loop,PV,Tieback,CV,0,Inhold,Readback);'
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='RestartTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false',DisableUpdateOutputs='true')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
            E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='Regulator')
        e=self.checked(lines=['EVENT(RestartTask);','DIV(1,FaultDivisor,Quotient);'],mutate=event)
        self.run_step(e,Inhold=True,Readback=70)
        e.memory.write('Readback',80);e.memory.write('FaultDivisor',0);before=self.snapshot(e);schedule=copy.deepcopy(e.scheduler_description())
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(e.scheduler_description(),schedule)
        self.assertEqual(self.run_step(e,FaultDivisor=1),80)


if __name__ == '__main__':unittest.main()
