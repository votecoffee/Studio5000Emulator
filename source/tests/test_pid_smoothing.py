"""Explicit PID software filter, isolated histories and transactional recovery."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_pid_dynamics as fixtures
from logixlab.model import ModelError


class PIDSmoothingTests(unittest.TestCase):
    setUp=fixtures.PIDDynamicsTests.setUp
    engine=fixtures.PIDDynamicsTests.engine
    checked=fixtures.PIDDynamicsTests.checked
    run_step=fixtures.PIDDynamicsTests.run_step
    snapshot=fixtures.PIDDynamicsTests.snapshot
    state=fixtures.PIDDynamicsTests.state

    def smoothing(self,values=None,**kwargs):
        return self.checked(dict(KP=0,KI=0,KD=10,BIAS=50,CTL=0)|dict(values or {}),**kwargs)

    def test_independent_step_is_filtered_and_unchanged_samples_decay(self):
        e=self.smoothing();self.assertEqual(self.run_step(e,Execute=True),50)
        self.assertEqual(self.run_step(e,PV=21),45);self.assertEqual(self.state(e)['derivative'],-5)
        self.assertEqual(self.run_step(e),47.5);self.assertEqual(self.run_step(e),48.75)

    def test_error_selection_and_direct_action_keep_their_signs(self):
        for ctl,write in ((1<<27,dict(Loop__SP=51)),(1<<25,dict(PV=21))):
            e=self.smoothing({'CTL':ctl});self.run_step(e,Execute=True)
            self.assertEqual(self.run_step(e,**write),55);self.assertEqual(self.state(e)['derivative'],5)
        e=self.smoothing();self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,Loop__SP=51),50)

    def test_dependent_minutes_filter_time_excludes_proportional_gain(self):
        fractions=[]
        for kp in (1,2):
            e=self.smoothing({'KP':kp,'KD':1/60,'CTL':1<<23});self.run_step(e,Execute=True)
            self.run_step(e,PV=21)
            d=self.state(e)['derivative'];self.assertAlmostEqual(d,-kp/1.1,places=5)
            fractions.append(d/kp)
        self.assertEqual(fractions[0],fractions[1])

    def test_larger_kd_reduces_fraction_of_raw_derivative(self):
        fractions=[]
        for kd in (2,20):
            e=self.smoothing({'KD':kd});self.run_step(e,Execute=True);self.run_step(e,PV=21)
            fractions.append(abs(self.state(e)['derivative']/kd))
        self.assertAlmostEqual(fractions[0],1/1.2,places=6)
        self.assertAlmostEqual(fractions[1],1/3,places=6)
        self.assertLess(fractions[1],fractions[0])

    def test_filter_uses_upd_rather_than_elapsed_step_time(self):
        e=self.smoothing({'UPD':.5});self.run_step(e,Execute=True)
        e.memory.write('PV',21);e.step(60000)
        self.assertAlmostEqual(self.state(e)['derivative'],-20/3,places=5)
        self.assertAlmostEqual(e.memory.read('CV'),50-20/3,places=5)

    def test_repriming_skips_unused_raw_overflow_but_reached_overflow_rolls_back(self):
        e=self.smoothing();self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,Loop__KD=3e38,PV=22),50)
        self.assertEqual(self.state(e)['derivative'],0)
        e.memory.write('PV',24);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'finite REAL range'):e.step()
        self.assertEqual(self.snapshot(e),before)
        self.assertEqual(self.run_step(e,Loop__KD=10),50)
        self.assertEqual(self.run_step(e,PV=25),45)

    def test_ndf_toggle_and_filter_configuration_changes_prime_zero(self):
        e=self.smoothing();self.run_step(e,Execute=True);self.assertEqual(self.run_step(e,PV=21),45)
        self.assertEqual(self.run_step(e,Loop__NDF=True,PV=22),40)
        self.assertEqual(self.run_step(e,Loop__NDF=False,PV=23),50)
        self.assertEqual(self.run_step(e,PV=24),45)
        for settings in (dict(Loop__KD=5),dict(Loop__UPD=.5),dict(Loop__PE=True),
                         dict(Loop__KP=2),dict(Loop__DOE=True),dict(Loop__CA=True),dict(Loop__MAXS=200)):
            self.run_step(e,**settings);self.assertEqual(self.state(e)['derivative'],0)

    def test_false_calls_preserve_filter_without_consuming_unknown_inputs(self):
        e=self.smoothing();self.run_step(e,Execute=True);self.run_step(e,PV=21)
        saved=copy.deepcopy(e.last_timer);e.memory.values['pv']=None
        self.run_step(e,Execute=False);self.assertEqual(e.last_timer,saved)
        self.assertEqual(self.run_step(e,Execute=True,PV=22),42.5)

    def test_manual_and_inhold_clear_filter_and_prime_auto_transfer(self):
        e=self.smoothing();self.run_step(e,Execute=True);self.run_step(e,PV=21)
        self.run_step(e,Loop__SWM=True,Loop__SO=60,PV=22);self.assertEqual(self.state(e)['derivative'],0)
        self.assertEqual(self.run_step(e,Loop__SWM=False,PV=23),60)
        self.assertEqual(self.run_step(e,PV=24),55)
        self.assertEqual(self.run_step(e,Inhold=True,Readback=70,PV=25),70)
        self.assertEqual(self.state(e)['derivative'],0)
        self.assertEqual(self.run_step(e,Inhold=False,PV=26),70)
        self.assertEqual(self.state(e)['derivative'],0)

    def test_deadband_clears_filter_and_refreshes_sample_on_release(self):
        e=self.smoothing();self.run_step(e,Execute=True);self.run_step(e,PV=21)
        self.assertEqual(self.run_step(e,Loop__SP=21,Loop__DB=2,Loop__NOZC=True),45)
        self.assertEqual(self.state(e)['derivative'],0);self.assertTrue(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,PV=24),35)
        self.assertEqual(self.state(e)['derivative'],-15)

    def test_run_and_ini_reset_filter_while_data_slots_do_not_seed_it(self):
        e=self.smoothing();e.memory.write('Loop.DATA[1]',123);e.memory.write('Loop.DATA[7]',456)
        self.run_step(e,Execute=True);self.run_step(e,PV=21)
        self.assertEqual(self.state(e)['derivative'],-5)
        self.assertEqual((e.memory.read('Loop.DATA[1]'),e.memory.read('Loop.DATA[7]')),(123,456))
        self.run_step(e,Loop__INI=False,PV=22);self.assertEqual(self.state(e)['derivative'],0)
        self.run_step(e,PV=23);self.assertEqual(self.state(e)['derivative'],-5)
        e.enter_run();self.run_step(e,PV=24);self.assertEqual(self.state(e)['derivative'],0)

    def test_later_fault_restores_filter_and_corrected_retry(self):
        e=self.smoothing();self.run_step(e,Execute=True);self.run_step(e,PV=21)
        e.memory.write('PV',22);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        self.assertEqual(self.run_step(e,FaultDivisor=1),42.5)

    def test_routine_replacement_copies_filter_independently(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        text='XIC(Execute)PID(Loop,PV,Tieback,CV,0,Inhold,Readback);'
        e=self.smoothing(lines=[text]);self.run_step(e,Execute=True);self.run_step(e,PV=21)
        source=decode(container(E.tostring(xml_source(text=text),encoding='utf-8')))
        candidate,_=prepare(e,source,(text,),'MainProgram',0)
        self.assertEqual(self.run_step(candidate,PV=22),42.5)
        self.assertEqual(self.state(e)['derivative'],-5);self.assertEqual(e.memory.read('CV'),45)

    def test_aoi_canonical_records_retain_independent_filters(self):
        import test_aoi_pid
        case=test_aoi_pid.AOIPIDTests();case.setUp();self.addCleanup(case.doCleanups)
        e=case.active()
        for record in ('ControlA','ControlB'):
            for name,value in dict(KP=0,KI=0,KD=10,BIAS=50,NDF=False).items():e.memory.write(record+'.'+name,value)
        e.step();e.memory.write('PVA',21);e.step()
        self.assertEqual((e.memory.read('CVA'),e.memory.read('CVB')),(45,50))
        e.step();self.assertEqual((e.memory.read('CVA'),e.memory.read('CVB')),(47.5,50))

    def test_report_names_explicit_solver_and_keeps_native_qualification_open(self):
        report=self.smoothing().report()['ladder_pid'];profile=report['smoothing']
        self.assertEqual(profile['ratio'],10);self.assertIn('UPD',profile['equation'])
        self.assertFalse(profile['native_coefficients']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
