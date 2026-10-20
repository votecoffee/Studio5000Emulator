"""The scan owner and native mode reads agree without a browser timer."""
import tempfile
import time
import unittest
from unittest.mock import patch

from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
import test_native_session as native_tests
from test_programming_lease import ACQUIRE, RELEASE


def wait_for(predicate, timeout=2):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Expected controller state was not reached')


class ControllerModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})

    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def test_run_scans_without_observers_and_program_freezes_values(self):
        self.app.command('controller-mode',{'mode':'Run','dt':10})
        wait_for(lambda:self.app.engine.scan_count>=3)
        worker=self.app._scan_thread
        self.app.command('controller-mode',{'mode':'Run','dt':10})
        self.assertIs(self.app._scan_thread,worker)
        self.assertEqual(self.app.command('observe',{})['controller']['mode'],'Run')
        with self.assertRaises(ModelError):self.app.command('step',{})
        self.app.command('controller-mode',{'mode':'Program'})
        before=self.app.command('snapshot',{})
        time.sleep(.04)
        self.assertEqual(self.app.command('snapshot',{}),before)
        self.assertEqual(before['controller']['mode'],'Program')
        self.app.command('controller-mode',{'mode':'Run'})
        wait_for(lambda:self.app.engine.scan_count>before['scan'])

    def test_invalid_modes_and_intervals_do_not_start_scanning(self):
        for value in ('Test','run','',None):
            with self.subTest(mode=value), self.assertRaises(ModelError):
                self.app.command('controller-mode',{'mode':value})
        for value in (0,60001,'10',2.5,True):
            with self.subTest(dt=value), self.assertRaises(ModelError):
                self.app.command('controller-mode',{'mode':'Run','dt':value})
        self.assertFalse(self.app.running)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_periodic_run_uses_task_interval_and_blocks_other_intervals(self):
        self.app.engine.project.tasks[0].update(type='Periodic',rate='20')
        with self.assertRaises(ModelError):self.app.command('controller-mode',{'mode':'Run','dt':10})
        self.app.command('controller-mode',{'mode':'Run','dt':20})
        wait_for(lambda:self.app.engine.scan_count>=2)
        state=self.app.command('controller-mode',{'mode':'Program'})
        self.assertEqual(state['ms'],state['scan']*20)

    def test_execution_blockers_cannot_be_bypassed_with_run(self):
        self.app.engine.blockers.append('Synthetic unsupported instruction')
        with self.assertRaises(ModelError):self.app.command('controller-mode',{'mode':'Run'})
        self.assertFalse(self.app.running)

    def test_load_reset_and_configure_stop_continuous_execution(self):
        for action,data in (('reset',{}),('configure',{'mode':'project'}),('demo',{})):
            self.app.command('controller-mode',{'mode':'Run','dt':10})
            wait_for(lambda:self.app.engine.scan_count>0)
            state=self.app.command(action,data)
            self.assertFalse(state['controller']['running'])
            time.sleep(.025)
            self.assertEqual(self.app.engine.scan_count,0)

    def test_fault_stops_worker_and_requires_reset_before_run(self):
        def fail(_):raise ModelError('Synthetic scan failure')
        with patch.object(self.app.engine,'step',side_effect=fail):
            self.app.command('controller-mode',{'mode':'Run'})
            wait_for(lambda:bool(self.app.engine.fault))
        state=self.app.command('observe',{})
        self.assertEqual(state['controller']['mode'],'Faulted')
        self.assertFalse(state['controller']['running'])
        with self.assertRaises(ModelError):self.app.command('controller-mode',{'mode':'Run'})
        self.app.command('reset',{})
        self.assertEqual(self.app.command('observe',{})['controller']['mode'],'Program')

    def test_close_joins_worker_and_denies_restart(self):
        self.app.command('controller-mode',{'mode':'Run'})
        wait_for(lambda:self.app.engine.scan_count>0)
        self.app.close()
        self.assertFalse(self.app._scan_thread.is_alive())
        with self.assertRaises(ModelError):self.app.command('controller-mode',{'mode':'Run'})


class NativeControllerModeTests(unittest.TestCase):
    setUp=native_tests.NativeSessionTests.setUp
    tearDown=native_tests.NativeSessionTests.tearDown
    cip=native_tests.NativeSessionTests.cip
    begin=native_tests.NativeSessionTests.begin
    signed=native_tests.NativeSessionTests.signed
    bind=native_tests.NativeSessionTests.bind

    def correlate(self):
        self.app.native_project_identity=NativeProjectIdentity('1'*64,self.app.engine.project.sha256,1,2,3,4,5,6)

    def test_signed_run_program_and_web_run_share_status_and_keep_scanning_offline(self):
        self.correlate();self.bind()
        self.assertEqual(self.signed(4,ACQUIRE)[2],0)
        self.assertEqual(self.signed(5,bytes.fromhex('0602208e2401')),bytes.fromhex('86000000'))
        wait_for(lambda:self.app.engine.scan_count>=2)
        self.assertEqual(self.cip(bytes.fromhex('0e03200124013005'))[4:],bytes.fromhex('6030'))
        self.assertEqual(self.signed(6,bytes.fromhex('0702208e2401')),bytes.fromhex('87000000'))
        stopped=self.app.command('snapshot',{})
        time.sleep(.025)
        self.assertEqual(stopped,self.app.command('snapshot',{}))
        self.app.command('controller-mode',{'mode':'Run','dt':10})
        self.assertEqual(self.signed(7,bytes.fromhex('0e03200124013005'))[4:],bytes.fromhex('6030'))
        self.signed(8,RELEASE);self.client.close()
        count=self.app.engine.scan_count
        wait_for(lambda:self.app.engine.scan_count>count)
        self.app.command('connectivity-stop',{})
        self.assertTrue(self.app.running)
        self.app.command('controller-mode',{'mode':'Program'})

    def test_mode_changes_require_bound_source_owner_and_exact_request(self):
        run=bytes.fromhex('0602208e2401')
        self.assertEqual(self.cip(run)[2],8)
        self.bind()
        self.assertEqual(self.signed(4,run)[2],0x0C)
        self.correlate()
        self.assertEqual(self.signed(5,run)[2],0x0F)
        self.assertEqual(self.signed(6,ACQUIRE)[2],0)
        self.app.native_project_identity=NativeProjectIdentity('1'*64,'2'*64,1,2,3,4,5,6)
        self.assertEqual(self.signed(7,run)[2],0x0C)
        self.correlate()
        for sequence,(raw,status) in enumerate(((run+b'x',0x15),(bytes.fromhex('0602208e2402'),5),
                (bytes.fromhex('0603208e24013001'),4),(bytes.fromhex('0802208e2401'),15)),8):
            self.assertEqual(self.signed(sequence,raw)[2],status)
        self.assertFalse(self.app.running)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_inhibit_stops_scans_blocks_run_and_never_auto_resumes(self):
        self.correlate();self.bind();self.signed(4,ACQUIRE)
        self.app.command('controller-mode',{'mode':'Run','dt':10})
        wait_for(lambda:self.app.engine.scan_count>0)
        self.assertEqual(self.signed(5,bytes.fromhex('0402208e2401010007000100'))[2],0)
        self.assertFalse(self.app.running)
        count=self.app.engine.scan_count
        self.assertEqual(self.signed(6,bytes.fromhex('0602208e2401'))[2],0x0C)
        with self.assertRaises(ModelError):self.app.command('controller-mode',{'mode':'Run'})
        self.assertEqual(self.signed(7,bytes.fromhex('0702208e2401'))[2],0)
        self.signed(8,RELEASE)
        time.sleep(.025)
        self.assertFalse(self.app.running)
        self.assertEqual(self.app.engine.scan_count,count)
