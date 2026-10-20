"""An owning session may inhibit scans without changing the loaded project."""
import copy
import hmac
import unittest

from logixlab import signed_messages
from logixlab.model import ModelError
from logixlab.programming_lease import LeaseError
import test_programming_lease as lease_tests
from test_signed_batches import batch
from test_signed_messages import KEY,request

SET=bytes.fromhex('0402208e2401010007000100')
CLEAR=SET[:-2]+bytes(2)
SINGLE=bytes.fromhex('0e03208e24013007')
LIST=bytes.fromhex('0302208e240101000700')


class InhibitModelTests(unittest.TestCase):
    setUp=lease_tests.ProgrammingLeaseModelTests.setUp
    context=lease_tests.ProgrammingLeaseModelTests.context
    def test_run_inhibit_requires_owner_and_valid_mask_and_dies_with_lease(self):
        with self.assertRaises(LeaseError):self.lease.set_run_inhibit(self.first,1,'a'*64,1)
        self.lease.acquire(self.first,1,'a'*64)
        self.lease.set_run_inhibit(self.first,1,'a'*64,1)
        self.assertEqual(self.lease.inhibit(1,'a'*64),1)
        for value in (-1,2,65535,True,None):
            with self.subTest(value=value),self.assertRaises(LeaseError):self.lease.set_run_inhibit(self.first,1,'a'*64,value)
        with self.assertRaises(LeaseError):self.lease.set_run_inhibit(self.second,1,'a'*64,0)
        self.assertEqual(self.lease.inhibit(1,'a'*64),1)
        self.now=400
        self.assertEqual(self.lease.inhibit(1,'a'*64),0)
        self.assertIsNone(self.lease.owner)


class RunInhibitSignedTests(unittest.TestCase):
    setUp=lease_tests.SemaphoreSignedTests.setUp
    tearDown=lease_tests.SemaphoreSignedTests.tearDown
    cip=lease_tests.SemaphoreSignedTests.cip
    begin=lease_tests.SemaphoreSignedTests.begin
    signed=lease_tests.SemaphoreSignedTests.signed
    bind=lease_tests.SemaphoreSignedTests.bind
    prepare=lease_tests.SemaphoreSignedTests.prepare
    second_client=lease_tests.SemaphoreSignedTests.second_client

    def acquire(self):
        self.prepare();self.assertEqual(self.signed(4,lease_tests.ACQUIRE)[2],0)

    def test_owned_inhibit_single_list_readback_and_scan_guard_then_clear(self):
        self.acquire();before=copy.deepcopy(self.app.engine.memory.values)
        header=self.app.native_project_identity.manifest()
        self.assertEqual(self.signed(5,SET),bytes.fromhex('84000000010007000000'))
        self.assertEqual(self.signed(6,SINGLE),bytes.fromhex('8e0000000100'))
        self.assertEqual(self.signed(7,LIST),bytes.fromhex('830000000100070000000100'))
        self.assertTrue(self.endpoint.state()['native_programming_lease']['scan_inhibited'])
        with self.assertRaisesRegex(ModelError,'inhibits scans'):self.app.command('step',{'count':10})
        self.assertEqual(self.app.engine.scan_count,0);self.assertEqual(self.app.engine.time_ms,0)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.native_project_identity.manifest(),header)
        self.assertEqual(self.signed(8,CLEAR)[2],0)
        self.assertEqual(self.signed(9,SINGLE),bytes.fromhex('8e0000000000'))
        self.app.command('step',{'count':1})
        self.assertEqual(self.app.engine.scan_count,1)

    def test_inhibited_scans_do_not_drain_device_inputs(self):
        self.acquire();self.app.command('device-io-configure',{'allow_writes':True})
        self.app.device_io.enqueue({'request_id':'queued-input','instance_id':self.app.instance_id,'project_generation':self.app.generation,
                                   'writes':[{'tag':'SpeedSetpoint','value':77}]})
        self.assertEqual(self.signed(5,SET)[2],0)
        before=self.app.engine.memory.read('SpeedSetpoint')
        with self.assertRaises(ModelError):self.app.command('step',{})
        self.assertEqual(self.app.device_io.receipt('queued-input')['status'],'queued')
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),before)
        self.assertEqual(self.signed(6,lease_tests.RELEASE)[2],0)
        self.app.command('step',{})
        self.assertEqual(self.app.device_io.receipt('queued-input')['status'],'applied')
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),77)

    def test_foreign_context_cannot_clear_inhibit_and_owner_release_clears_it(self):
        self.acquire();second=self.second_client();first=self.client
        try:
            self.assertEqual(self.signed(5,SET)[2],0)
            self.client=second
            self.assertEqual(self.signed(4,CLEAR)[2],15)
            self.assertEqual(self.signed(5,SINGLE),bytes.fromhex('8e0000000100'))
            self.client=first
            self.assertEqual(self.signed(6,lease_tests.RELEASE)[2],0)
            self.assertEqual(self.signed(7,SINGLE),bytes.fromhex('8e0000000000'))
            self.app.command('step',{'count':1})
        finally:self.client=first;second.close()

    def test_unowned_unbound_unsigned_source_and_payload_guards(self):
        self.prepare();self.assertEqual(self.signed(4,SET)[2],15)
        self.assertEqual(self.signed(5,lease_tests.ACQUIRE)[2],0)
        for sequence,(raw,status) in enumerate(((SET[:-1],0x13),(SET+b'x',0x15),
                (SET[:-2]+b'\2\0',3),(SET[:-2]+b'\xff\xff',3),
                (bytes.fromhex('0402208e240102000700010003000a00'),15),
                (bytes.fromhex('1003208e240130070100'),15)),6):
            self.assertEqual(self.signed(sequence,raw)[2],status)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['scan_inhibited'])
        self.assertEqual(self.cip(SET)[2],8)
        self.app.native_project_identity=None
        self.assertEqual(self.signed(12,SET)[2],12)
        self.begin();self.assertEqual(self.signed(1,SET)[2],15)

    def test_signed_batch_reads_and_other_setters_keep_their_distinct_outcomes(self):
        self.acquire()
        children=(SET,SINGLE,bytes.fromhex('0402208e2401010003000a00'),CLEAR,SINGLE)
        raw=batch(children,sequence=5);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        parsed=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual([r[2] for r in parsed.children],[0,0,15,0,0])
        self.assertEqual(parsed.children[1][-2:],b'\1\0');self.assertEqual(parsed.children[4][-2:],bytes(2))
        self.assertEqual(self.endpoint.counts['native_run_inhibit_updates'],2)

    def test_bad_mac_reset_and_stop_remove_inhibit_without_project_change(self):
        self.acquire();self.assertEqual(self.signed(5,SET)[2],0)
        raw=request(0x36,CLEAR,6)
        self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['scan_inhibited'])
        self.bind();self.assertEqual(self.signed(4,lease_tests.ACQUIRE)[2],0);self.assertEqual(self.signed(5,SET)[2],0)
        self.app.command('reset',{})
        self.assertFalse(self.endpoint.state()['native_programming_lease']['scan_inhibited'])
        self.endpoint.stop();self.assertEqual(self.endpoint.programming_lease.run_inhibit,0)


if __name__=='__main__':unittest.main()
