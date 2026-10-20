"""Setup has an owner and finite lifetime without accepting device data."""
import copy
from dataclasses import replace
import json
import struct
import time
import unittest

from logixlab.resilient_transport import MAX_BUFFER_BYTES,ResilientTransport,TransportError
from logixlab import signed_messages
import test_programming_lease as leases
import test_programming_preparation as prep
import test_run_inhibit as inhibits
from test_signed_messages import KEY,request
from test_signed_batches import batch


def payload(size=MAX_BUFFER_BYTES,opaque=17):return struct.pack('<HHIII',1,1,1,size,opaque)
SETUP=bytes.fromhex('4b03210012042400')+payload()
DELETE=bytes.fromhex('0903210012042400')


class TransportModelTests(unittest.TestCase):
    def test_bounded_setup_repeat_conflict_and_clear_do_not_allocate_or_expose_config(self):
        stage=ResilientTransport();raw=payload();stage.open(raw);stage.open(raw)
        self.assertEqual(stage.setup,raw);self.assertEqual(stage.buffer_bytes,MAX_BUFFER_BYTES)
        state=stage.description();self.assertTrue(state['open'] and state['setup_only'])
        for flag in ('buffer_allocated','payload_transfer','commit','configuration_exposed'):self.assertFalse(state[flag])
        self.assertNotIn('opaque',json.dumps(state));self.assertNotIn(raw.hex(),json.dumps(state))
        for other in (payload(1),payload(opaque=18)):
            with self.assertRaises(TransportError) as error:stage.open(other)
            self.assertEqual(error.exception.status,12);self.assertEqual(stage.setup,raw)
        stage.clear();stage.clear();self.assertEqual(stage.buffer_bytes,0);self.assertIsNone(stage.setup)
        stage.open(payload(1,0));self.assertEqual(stage.buffer_bytes,1)

    def test_malformed_framing_unknown_selectors_and_oversize_are_atomic(self):
        stage=ResilientTransport();stage.open(payload());before=stage.description()
        unknown=[]
        for index in range(3):
            values=[1,1,1,MAX_BUFFER_BYTES,17];values[index]=2;unknown.append(struct.pack('<HHIII',*values))
        for raw in (None,bytearray(payload()),payload()[:-1],payload()+b'\0',payload(0),payload(MAX_BUFFER_BYTES+1),*unknown):
            with self.subTest(raw=raw),self.assertRaises(TransportError):stage.open(raw)
            self.assertEqual(stage.description(),before)


class TransportSignedTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare
    second_client=leases.SemaphoreSignedTests.second_client
    send=prep.PreparationSignedTests.send
    acquire=prep.PreparationSignedTests.acquire
    ready=prep.PreparationSignedTests.ready

    def description(self):return self.endpoint.state()['native_programming_lease']['resilient_transport']

    def test_setup_and_delete_change_only_temporary_state(self):
        self.ready();before=copy.deepcopy(self.app.state());identity=self.app.native_project_identity.manifest()
        self.assertEqual(self.send(SETUP),bytes.fromhex('cb000000'))
        self.assertEqual(self.send(SETUP),bytes.fromhex('cb000000'))
        self.assertTrue(self.description()['open']);self.assertFalse(self.description()['payload_transfer'])
        self.assertEqual(self.send(DELETE),bytes.fromhex('89000000'))
        self.assertEqual(self.send(DELETE),bytes.fromhex('89000000'))
        self.assertFalse(self.description()['open']);self.assertEqual(self.description()['buffer_bytes'],0)
        after=self.app.state()
        for key in ('tags','scan','ms','mode','changes'):self.assertEqual(after[key],before[key])
        self.assertEqual(self.app.native_project_identity.manifest(),identity)
        self.assertEqual(self.endpoint.counts['native_transport_setup'],2)
        self.assertEqual(self.endpoint.counts['native_transport_delete'],2)

    def test_setup_requires_bound_owner_preparation_and_correlated_source(self):
        self.prepare();self.sequence=4;self.assertEqual(self.send(SETUP)[2],15)
        self.send(leases.ACQUIRE);self.assertEqual(self.send(SETUP)[2],12)
        self.send(inhibits.SET);self.send(prep.BEGIN)
        identity=self.app.native_project_identity
        for value in (None,replace(identity,source_l5x_sha256='f'*64)):
            self.app.native_project_identity=value;self.assertEqual(self.send(SETUP)[2],12)
        self.app.native_project_identity=identity
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,SETUP)[2],15)
        finally:self.client=first;second.close()
        self.assertFalse(self.description()['open']);self.assertEqual(self.send(SETUP)[2],0)

    def test_unsigned_bad_paths_and_conflicting_config_cannot_replace_setup(self):
        self.ready();self.send(SETUP)
        for raw,status in ((SETUP[:-1],3),(SETUP+b'\0',3),(DELETE+b'\0',0x15),
                (bytes.fromhex('4b03210012042401')+payload(),5),
                (bytes.fromhex('4b042100120424003001')+payload(),4),
                (bytes.fromhex('4b0520682401210012042400')+payload(),4),
                (SETUP[:8]+payload(1),12),(SETUP[:8]+payload(opaque=33),12)):
            self.assertEqual(self.send(raw)[2],status,raw.hex());self.assertTrue(self.description()['open'])
        self.assertEqual(self.cip(SETUP)[2],8);self.assertEqual(self.cip(DELETE)[2],8)
        self.assertEqual(self.send(bytes.fromhex('5c03210012042400')+bytes(8))[2],15)
        self.assertFalse(self.description()['payload_transfer'])

    def test_batch_uses_the_same_owner_and_keeps_child_errors(self):
        self.ready()
        raw=batch((SETUP,SETUP[:8]+payload(1),DELETE),sequence=self.sequence)
        import hmac
        raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual([v[2] for v in result.children],[0,12,0]);self.assertFalse(self.description()['open'])

    def test_preparation_end_inhibit_clear_release_reset_reload_bad_mac_and_stop_clear_setup(self):
        for action in ('end','clear','release','reset','reload','bad-mac','stop'):
            with self.subTest(action=action):
                self.ready();self.send(SETUP);self.assertTrue(self.description()['open'])
                if action=='end':self.send(prep.END)
                elif action=='clear':self.send(inhibits.CLEAR)
                elif action=='release':self.send(leases.RELEASE)
                elif action=='reset':self.app.command('reset',{})
                elif action=='reload':self.app.command('demo',{'sample':'ConveyorDemo'})
                elif action=='bad-mac':
                    raw=request(0x36,inner=SETUP,sequence=self.sequence)
                    self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
                else:self.endpoint.stop()
                self.assertFalse(self.endpoint.programming_lease.transport.description()['open'])
                if action in ('reset','reload'):
                    self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()

    def test_disconnect_expiry_source_and_generation_changes_clear_setup(self):
        for action in ('expiry','source','generation','disconnect'):
            self.ready();self.send(SETUP)
            lease=self.endpoint.programming_lease
            if action=='expiry':lease.owner.deadline=time.monotonic()-1
            elif action=='source':lease.description(self.app.generation,'f'*64)
            elif action=='generation':lease.description(self.app.generation+1,self.app.engine.project.sha256)
            else:
                self.client.close();deadline=time.monotonic()+2
                while self.description()['open'] and time.monotonic()<deadline:time.sleep(.01)
                self.client=leases.Client(self.endpoint.port);self.client.register()
            with self.subTest(action=action):
                self.assertFalse(self.description()['open']);self.assertEqual(self.description()['buffer_bytes'],0)


if __name__=='__main__':unittest.main()
