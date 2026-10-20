"""Preparation can advance a native client without transferring a project."""
import copy
from dataclasses import replace
import hmac
import unittest

from logixlab import signed_messages
from logixlab.model import ModelError
from logixlab.programming_lease import LeaseError
import test_programming_lease as leases
import test_run_inhibit as inhibits
from test_signed_batches import batch
from test_signed_messages import KEY,request

BEGIN=bytes.fromhex('6002208e2401')
END=bytes.fromhex('6202208e2401')
SINGLE=bytes.fromhex('0e03208e2401301a')
LIST=bytes.fromhex('0302208e240101001a00')
RETAIN=bytes.fromhex('0402208e24010100090000')
LIBRARY_WRITE=bytes.fromhex('4d0321007d03240102000000020000000100000000')


class PreparationModelTests(unittest.TestCase):
    setUp=leases.ProgrammingLeaseModelTests.setUp
    context=leases.ProgrammingLeaseModelTests.context

    def test_owner_inhibit_and_idempotent_preparation_keep_authority_disabled(self):
        with self.assertRaises(LeaseError):self.lease.begin_preparation(self.first,1,'a'*64)
        self.lease.acquire(self.first,1,'a'*64)
        with self.assertRaises(LeaseError):self.lease.begin_preparation(self.first,1,'a'*64)
        self.lease.set_run_inhibit(self.first,1,'a'*64,1)
        self.lease.begin_preparation(self.first,1,'a'*64);self.lease.begin_preparation(self.first,1,'a'*64)
        self.assertEqual(self.lease.preparation_status(1,'a'*64),2)
        with self.assertRaises(LeaseError):self.lease.end_preparation(self.second,1,'a'*64)
        with self.assertRaises(LeaseError):self.lease.require_prepared(self.second,1,'a'*64)
        state=self.lease.description(1,'a'*64)
        self.assertEqual(state['preparation_state'],'ready')
        for name in ('project_transfer','online_edits','controller_mode_changes','tag_write_authority'):
            self.assertFalse(state[name])
        self.lease.end_preparation(self.first,1,'a'*64);self.lease.end_preparation(self.first,1,'a'*64)
        self.assertEqual(self.lease.preparation_status(1,'a'*64),0)
        self.assertEqual(self.lease.inhibit(1,'a'*64),1)
        self.lease.begin_preparation(self.first,1,'a'*64)
        self.lease.set_run_inhibit(self.first,1,'a'*64,0)
        self.assertEqual(self.lease.preparation_status(1,'a'*64),0)

    def test_source_generation_expiry_and_context_invalidation_clear_preparation(self):
        for kind in ('generation','source','expiry','closed','key','stage','discard','release'):
            self.now=100;first=self.context();self.lease.acquire(first,1,'a'*64)
            self.lease.set_run_inhibit(first,1,'a'*64,1);self.lease.begin_preparation(first,1,'a'*64)
            generation=1;source='a'*64
            if kind=='generation':generation=2
            elif kind=='source':source='b'*64
            elif kind=='expiry':self.now=400
            elif kind=='closed':first.close()
            elif kind=='key':first.key=None
            elif kind=='stage':first.stage='operator'
            elif kind=='discard':self.lease.discard(first)
            else:self.lease.release(first,1,'a'*64)
            with self.subTest(kind=kind):
                self.assertEqual(self.lease.preparation_status(generation,source),0)
                self.assertFalse(self.lease.prepared);self.assertIsNone(self.lease.owner)


class PreparationSignedTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare
    second_client=leases.SemaphoreSignedTests.second_client

    def send(self,raw):
        result=self.signed(self.sequence,raw);self.sequence+=1;return result

    def acquire(self):
        self.prepare();self.sequence=4
        self.assertEqual(self.send(leases.ACQUIRE)[2],0)

    def ready(self):
        self.acquire();self.assertEqual(self.send(inhibits.SET)[2],0)
        self.assertEqual(self.send(BEGIN),bytes.fromhex('e0000000'))

    def test_exact_readback_end_and_release_preserve_project_and_scan_guard(self):
        self.ready();before=copy.deepcopy(self.app.engine.memory.values)
        identity=self.app.native_project_identity.manifest()
        self.assertEqual(self.send(SINGLE),bytes.fromhex('8e00000002000000'))
        self.assertEqual(self.send(LIST),bytes.fromhex('8300000001001a00000002000000'))
        self.assertEqual(self.send(BEGIN),bytes.fromhex('e0000000'))
        with self.assertRaises(ModelError):self.app.command('step',{})
        self.assertEqual(self.send(END),bytes.fromhex('e2000000'))
        self.assertEqual(self.send(SINGLE),bytes.fromhex('8e00000000000000'))
        with self.assertRaises(ModelError):self.app.command('step',{})
        self.assertEqual(self.send(leases.RELEASE)[2],0)
        self.assertEqual(self.endpoint.state()['native_programming_lease']['preparation_state'],'idle')
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.native_project_identity.manifest(),identity)
        self.assertEqual(self.app.engine.scan_count,0)
        self.app.command('step',{});self.assertEqual(self.app.engine.scan_count,1)

    def test_preconditions_source_scope_and_framing_remain_enforced(self):
        self.prepare();self.sequence=4
        self.assertEqual(self.send(BEGIN)[2],15)
        self.assertEqual(self.send(leases.ACQUIRE)[2],0)
        self.assertEqual(self.send(BEGIN)[2],12)
        self.assertEqual(self.send(RETAIN)[2],12)
        for raw,status in ((BEGIN+b'x',0x15),(END+b'x',0x15),
                (bytes.fromhex('6002208e2402'),5),(bytes.fromhex('6003208e2401301a'),4),
                (bytes.fromhex('600420682401208e2401'),4),(RETAIN[:-1],0x13),(RETAIN+b'x',0x15)):
            with self.subTest(raw=raw.hex()):self.assertEqual(self.send(raw)[2],status)
        self.assertEqual(self.cip(BEGIN)[2],8);self.assertEqual(self.cip(END)[2],8)
        self.assertEqual(self.send(inhibits.SET)[2],0)
        identity=self.app.native_project_identity;self.app.native_project_identity=None
        self.assertEqual(self.send(BEGIN)[2],12)
        self.app.native_project_identity=identity
        self.begin();self.assertEqual(self.signed(1,BEGIN)[2],15)

    def test_redundancy_ack_requires_prepared_owner_and_known_disabled_source(self):
        self.ready();configuration=self.app.engine.project.controller_configuration
        for configured in (None,True,False):
            current=replace(configuration,redundancy_configured=configured)
            self.app.engine.project.controller_configuration=current
            with self.subTest(configured=configured):
                self.assertEqual(self.send(RETAIN),bytes.fromhex('84000000010009000000') if configured is False else bytes.fromhex('84000c00'))
                self.assertIs(self.app.engine.project.controller_configuration,current)
        self.assertEqual(self.send(RETAIN[:-1]+b'\1')[2],15)
        self.assertEqual(self.send(LIBRARY_WRITE)[2],15)
        self.assertEqual(self.send(bytes.fromhex('6102208e2401'))[2],15)
        self.assertEqual(self.send(END)[2],0)
        self.assertEqual(self.send(RETAIN)[2],12)
        self.assertEqual(self.endpoint.counts['native_configuration_retained'],1)

    def test_foreign_owner_denials_and_disconnect_clear_preparation(self):
        self.ready();first=self.client;second=self.second_client()
        try:
            self.client=second
            for sequence,raw in ((4,BEGIN),(5,END),(6,RETAIN)):
                self.assertEqual(self.signed(sequence,raw)[2],15)
            self.assertEqual(self.signed(7,SINGLE),bytes.fromhex('8e00000002000000'))
            first.close()
            import time
            deadline=time.monotonic()+2
            while self.endpoint.state()['native_programming_lease']['owned'] and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(self.signed(8,SINGLE),bytes.fromhex('8e00000000000000'))
        finally:self.client=first;second.close()

    def test_signed_batch_keeps_library_data_denied_and_end_does_not_clear_inhibit(self):
        self.acquire();self.app.engine.project.controller_configuration=replace(self.app.engine.project.controller_configuration,redundancy_configured=False)
        children=(inhibits.SET,BEGIN,LIST,RETAIN,LIBRARY_WRITE,END,LIST,inhibits.SINGLE,inhibits.CLEAR)
        raw=batch(children,sequence=self.sequence);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        parsed=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual([v[2] for v in parsed.children],[0,0,0,0,15,0,0,0,0])
        self.assertEqual(parsed.children[2][-4:],b'\2\0\0\0')
        self.assertEqual(parsed.children[6][-4:],bytes(4));self.assertEqual(parsed.children[7][-2:],b'\1\0')
        self.assertFalse(self.endpoint.state()['native_programming_lease']['scan_inhibited'])

    def test_bad_mac_reset_project_reload_and_stop_clear_preparation(self):
        self.ready();raw=request(0x36,END,self.sequence)
        self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
        self.assertEqual(self.endpoint.state()['native_programming_lease']['preparation_status'],0)
        self.ready();self.app.command('reset',{})
        self.assertFalse(self.endpoint.programming_lease.prepared)
        self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()
        self.ready();self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertFalse(self.endpoint.programming_lease.prepared)
        self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()
        self.ready();self.endpoint.stop();self.assertFalse(self.endpoint.programming_lease.prepared)


if __name__=='__main__':unittest.main()
