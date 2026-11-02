"""One-way ladder PID cascade: authored order, modes and atomic advances."""
import copy
import unittest
from xml.etree import ElementTree as E
import test_ladder_pid as fixtures
from logixlab.model import ModelError


class PIDCascadeTests(unittest.TestCase):
    setUp = fixtures.LadderPIDTests.setUp
    engine = fixtures.LadderPIDTests.engine
    checked = fixtures.LadderPIDTests.checked
    run_step = fixtures.LadderPIDTests.run_step

    def cascade(self, **kwargs):
        e = self.checked(**kwargs)
        for name in ('Execute', 'IntExecute', 'Cascade', 'CascadeMaster', 'IntCascade'):
            e.memory.write(name, True)
        return e

    def snapshot(self, e):
        return copy.deepcopy((e.memory.values, e.last_timer, e.scan_count, e.time_ms,
                              e.scheduler_description(), e.trace))

    def test_master_percent_sets_slave_sp_and_integer_cv_each_scan(self):
        e = self.cascade(); e.step()
        self.assertEqual((e.memory.read('CV'), e.memory.read('IntLoop.SP'), e.memory.read('RawCV')), (45, 45, 6553))
        e.step(); self.assertEqual((e.memory.read('IntLoop.SP'), e.memory.read('RawCV')), (60, 11468))

    def test_slave_setpoint_uses_its_engineering_span(self):
        e = self.cascade(); e.memory.write('IntLoop.MINS', -50); e.memory.write('IntLoop.MAXS', 150)
        e.step(); self.assertEqual(e.memory.read('IntLoop.SP'), 40)
        self.assertEqual(e.memory.read('IntLoop.PV'), 0); self.assertEqual(e.memory.read('IntLoop.ERR'), 40)

    def test_master_runs_from_its_own_sp_and_is_not_modified_by_slave(self):
        e = self.cascade(lines=['XIC(Execute)PID(Loop,PV,Tieback,CV,0,Inhold,Readback);',
                                'XIC(IntExecute)PID(IntLoop,RawPV,Tieback,RawCV,Loop,IntInhold,IntReadback);'])
        e.step(); master = copy.deepcopy(e.memory.read('Loop'))
        e.memory.write('Execute', False); e.memory.write('IntLoop.MAXO', 1); e.step()
        master['CTL'] &= (1 << 31) - 1
        self.assertEqual(e.memory.read('Loop'), master)
        self.assertEqual(e.memory.read('IntLoop.SP'), 45); self.assertEqual(e.memory.read('IntLoop.OUT'), 1)

    def test_reversed_rungs_sample_last_stored_output(self):
        e = self.cascade(lines=['XIC(IntExecute)PID(IntLoop,RawPV,Tieback,RawCV,Loop,IntInhold,IntReadback);',
                                'XIC(Execute)PID(Loop,PV,Tieback,CV,0,Inhold,Readback);'])
        e.step(); self.assertEqual((e.memory.read('IntLoop.SP'), e.memory.read('CV')), (0, 45))
        e.step(); self.assertEqual((e.memory.read('IntLoop.SP'), e.memory.read('CV')), (45, 60))

    def test_false_slave_does_not_consume_unknown_master(self):
        e = self.cascade(); e.memory.write('Execute', False); e.memory.write('IntExecute', False)
        e.memory.values['loop']['OUT'] = None
        e.step(); self.assertFalse(e.memory.read('IntLoop.EN')); self.assertEqual(e.memory.read('IntLoop.SP'), 50)

    def test_disabled_master_samples_saved_out_without_requiring_its_enable(self):
        e = self.cascade(); e.memory.write('Execute', False); e.memory.write('Loop.OUT', 75)
        e.step(); self.assertEqual(e.memory.read('IntLoop.SP'), 75); self.assertFalse(e.memory.read('Loop.EN'))

    def test_ct_alone_is_retained_and_ignored_without_cl(self):
        e = self.checked(); self.run_step(e, Execute=True, CascadeMaster=True)
        self.assertEqual(e.memory.read('CV'), 45); self.assertTrue(e.memory.read('Loop.CT'))

    def test_inactive_cascade_ignores_unknown_master_values(self):
        e = self.checked(); e.memory.values['loop']['OUT'] = None
        e.memory.write('IntExecute', True); e.step()
        self.assertEqual(e.memory.read('RawCV'), 8192)

    def test_manual_and_inhold_bypass_master_sampling(self):
        for mode in ('MO', 'SWM', 'Inhold'):
            with self.subTest(mode=mode):
                e = self.cascade(); e.memory.write('Execute', False); e.memory.values['loop']['OUT'] = None
                e.memory.write('Int'+mode if mode == 'Inhold' else 'IntLoop.'+mode, True)
                e.memory.write('IntLoop.SO', 70); e.memory.write('IntReadback', 20000)
                e.memory.write('Tieback', 60)
                e.step(); self.assertEqual(e.memory.read('IntLoop.SP'), 50)
                self.assertEqual(e.memory.read('RawCV'), {'MO':19660, 'SWM':22937, 'Inhold':20000}[mode])

    def test_manual_pvt_establishes_sp_then_auto_consumes_master(self):
        e = self.cascade(); e.memory.values['intloop']['SP'] = None
        e.memory.write('IntManual', True); e.memory.write('IntPVTracking', True); e.step()
        self.assertEqual(e.memory.read('IntLoop.SP'), 25)
        e.memory.write('IntManual', False); e.step(); self.assertEqual(e.memory.read('IntLoop.SP'), 60)

    def test_active_cascade_establishes_unknown_slave_sp(self):
        e = self.cascade(); e.memory.values['intloop']['SP'] = None; e.step()
        self.assertEqual(e.memory.read('IntLoop.SP'), 45)

    def test_role_configuration_errors_roll_back(self):
        for tag, value in (('CascadeMaster', False), ('IntCascadeMaster', True)):
            with self.subTest(tag=tag):
                e = self.cascade(); e.memory.write(tag, value); before = self.snapshot(e)
                with self.assertRaisesRegex(ModelError, 'master needs literal 0|distinct master'):e.step()
                self.assertEqual(self.snapshot(e), before)

    def test_unknown_bad_master_output_and_flags_roll_back(self):
        for field, value in (('OUT', None), ('OUT', -1), ('OUT', 101), ('OUT', float('inf')), ('CTL', 0)):
            with self.subTest(field=field, value=value):
                e = self.cascade(); e.memory.write('Execute', False); e.memory.values['loop'][field] = value
                before = self.snapshot(e)
                with self.assertRaises(ModelError):e.step()
                self.assertEqual(self.snapshot(e), before)

    def test_self_master_and_cv_overwrite_are_blocked(self):
        for args in ('Loop,PV,Tieback,CV,Loop,0,0', 'IntLoop,RawPV,Tieback,Loop.OUT,Loop,0,0', 'Loop,PV,Tieback,CV,PV,0,0'):
            with self.subTest(args=args):self.assertTrue(self.engine(lines=['PID('+args+');']).blockers)

    def test_master_reference_shape_is_required_even_when_not_sampled(self):
        e=self.checked();e.memory.values['loop']['DATA'].pop()
        with self.assertRaisesRegex(ModelError,'seventeen-element'):e.step()

    def test_manual_master_output_drives_slave_in_same_scan(self):
        e = self.cascade(); e.memory.write('Manual', True); e.memory.write('Tieback', 80); e.step()
        self.assertEqual((e.memory.read('CV'), e.memory.read('IntLoop.SP'), e.memory.read('IntLoop.OUT')), (80, 80, 55))

    def test_late_fault_restores_both_loops_sp_and_histories(self):
        e = self.cascade(); e.step(); e.memory.write('FaultDivisor', 0); before = self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('FaultDivisor', 1); e.step()
        self.assertEqual((e.memory.read('CV'), e.memory.read('IntLoop.SP'), e.memory.read('RawCV')), (60, 60, 11468))

    def test_changing_slave_to_independent_retains_last_sampled_sp(self):
        e = self.cascade(); e.step(); e.memory.write('IntCascade', False); e.step()
        self.assertEqual(e.memory.read('IntLoop.SP'), 45)
        e.memory.write('IntLoop.SP', 55); e.step(); self.assertEqual(e.memory.read('IntLoop.SP'), 55)

    def test_derivative_on_error_observes_cascade_setpoint_changes(self):
        for doe, expected in ((False, 50), (True, 80)):
            with self.subTest(doe=doe):
                e = self.cascade(); e.memory.write('Execute', False)
                for tag,value in [('Loop.OUT',40),('IntLoop.KP',0),('IntLoop.BIAS',50),('IntLoop.KD',2),('IntLoop.NDF',True),('IntLoop.DOE',doe)]:e.memory.write(tag,value)
                e.step(); e.memory.write('Loop.OUT',55); e.step(); self.assertEqual(e.memory.read('IntLoop.OUT'), expected)

    def test_periodic_release_samples_with_configured_pid_upd(self):
        def periodic(root):
            task=root.find('.//Task');task.set('Type','PERIODIC');task.set('Rate','20')
        e=self.cascade(mutate=periodic);e.step(20);self.assertEqual(e.memory.read('CV'),45)
        e.memory.write('Loop.SP',60);e.step(20);self.assertEqual(e.memory.read('IntLoop.SP'),75)


if __name__ == '__main__':unittest.main()
