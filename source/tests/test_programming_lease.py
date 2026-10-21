"""Coordination stays exclusive, source bound and separate from project writes."""
import copy
import hmac
import json
import tempfile
import time
import unittest

from logixlab import signed_messages
from logixlab.ethernetip import CIPError,Endpoint,Session,decode_path,logical,symbol_path
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_session import NativeSession
from logixlab.programming_lease import LeaseError,ProgrammingLease,MAX_PROGRAM_RESERVATIONS
from logixlab.server import Application
import test_native_session as native_tests
from test_ethernetip import Client
from test_signed_batches import batch
from test_signed_messages import KEY,request

ACQUIRE=bytes.fromhex('4b04208e24012074240100')
RELEASE=bytes.fromhex('4c04208e240120742401')


class ProgrammingLeaseModelTests(unittest.TestCase):
    def test_program_edit_idle_tracks_reservation_phase_transfer_and_expiry(self):
        self.assertTrue(self.lease.program_edits_idle(1,'a'*64,7))
        self.lease.acquire(self.first,1,'a'*64,selector=1)
        self.lease.reserve_program(self.first,1,'a'*64,7)
        self.assertFalse(self.lease.program_edits_idle(1,'a'*64,7))
        self.assertTrue(self.lease.program_edits_idle(1,'a'*64,8))
        self.lease.release_program(self.first,1,'a'*64,7)
        self.lease.open_edit_preparation(self.first,1,'a'*64)
        self.assertFalse(self.lease.program_edits_idle(1,'a'*64,8))
        self.lease.close_edit_preparation(self.first,1,'a'*64)
        self.lease.edit_transfer.target=(7,1)
        self.assertFalse(self.lease.program_edits_idle(1,'a'*64,8))
        self.now=401
        self.assertTrue(self.lease.program_edits_idle(1,'a'*64,7))
        self.assertIsNone(self.lease.edit_transfer.target)

    def test_program_reservations_are_owned_bounded_idempotent_and_inhibit_scans(self):
        self.lease.acquire(self.first,1,'a'*64,selector=1)
        for program in range(1,MAX_PROGRAM_RESERVATIONS+1):
            self.lease.reserve_program(self.first,1,'a'*64,program)
        self.lease.reserve_program(self.first,1,'a'*64,1)
        self.assertEqual(len(self.lease.program_reservations),MAX_PROGRAM_RESERVATIONS)
        with self.assertRaises(LeaseError) as error:self.lease.reserve_program(self.first,1,'a'*64,MAX_PROGRAM_RESERVATIONS+1)
        self.assertEqual(error.exception.status,2)
        for value in (True,False,0,-1,1<<32,'1'):
            with self.assertRaises(LeaseError):self.lease.reserve_program(self.first,1,'a'*64,value)
            with self.assertRaises(LeaseError):self.lease.release_program(self.first,1,'a'*64,value)
        with self.assertRaises(LeaseError):self.lease.release_program(self.second,1,'a'*64,1)
        self.assertTrue(self.lease.scan_inhibited(1,'a'*64))
        self.assertEqual(self.lease.inhibit(1,'a'*64),0)
        for program in range(1,MAX_PROGRAM_RESERVATIONS+1):self.lease.release_program(self.first,1,'a'*64,program)
        self.lease.release_program(self.first,1,'a'*64,1)
        self.assertFalse(self.lease.scan_inhibited(1,'a'*64))
        self.lease.release(self.first,1,'a'*64)
        self.lease.acquire(self.first,1,'a'*64,selector=0)
        with self.assertRaises(LeaseError):self.lease.reserve_program(self.first,1,'a'*64,1)

    def setUp(self):
        self.now=100.;self.lease=ProgrammingLease(lambda:self.now)
        self.first=self.context();self.second=self.context()

    def context(self):
        native=NativeSession();native.stage='bound';native.key=b'private-key';native.deadline=self.now+300
        return native

    def test_exclusive_context_ownership_idempotence_and_foreign_release_denial(self):
        self.lease.acquire(self.first,1,'a'*64);self.lease.acquire(self.first,1,'a'*64)
        with self.assertRaises(LeaseError) as error:self.lease.acquire(self.second,1,'a'*64)
        self.assertEqual(error.exception.status,0x0C)
        with self.assertRaises(LeaseError) as error:self.lease.release(self.second,1,'a'*64)
        self.assertEqual(error.exception.status,0x0F)
        self.assertIs(self.lease.owner,self.first)
        self.lease.release(self.first,1,'a'*64);self.lease.release(self.first,1,'a'*64)
        self.lease.acquire(self.second,1,'a'*64)
        self.assertIs(self.lease.owner,self.second)

    def test_generation_source_expiry_and_closed_context_discard_stale_ownership(self):
        for kind in ('generation','source','expiry','closed','key','stage'):
            self.now=100;first=self.context();self.lease.acquire(first,1,'a'*64)
            generation=1;source='a'*64
            if kind=='generation':generation=2
            elif kind=='source':source='b'*64
            elif kind=='expiry':self.now=400
            elif kind=='closed':first.close()
            elif kind=='key':first.key=None
            else:first.stage='operator'
            with self.subTest(kind=kind):
                self.assertFalse(self.lease.live(generation,source))
                self.assertIsNone(self.lease.owner)
        for native in (NativeSession(),first):
            with self.assertRaises(LeaseError):self.lease.acquire(native,1,source)

    def test_discard_matches_context_and_description_contains_no_identity_or_key(self):
        self.lease.acquire(self.first,1,'a'*64);self.lease.discard(self.second)
        state=self.lease.description(1,'a'*64)
        self.assertTrue(state['owned']);self.assertEqual(state['remaining_ms'],300000)
        self.assertFalse(state['project_transfer']);self.assertFalse(state['tag_write_authority'])
        self.assertNotIn('private-key',json.dumps(state));self.assertNotIn('a'*64,json.dumps(state))
        self.lease.discard(self.first);self.assertFalse(self.lease.description(1,'a'*64)['owned'])

    def test_edit_selector_reserves_exclusively_without_active_edit_or_download_authority(self):
        self.lease.acquire(self.first,1,'a'*64,selector=1)
        self.lease.acquire(self.first,1,'a'*64,selector=1)
        self.lease.require_edit_owner(self.first,1,'a'*64)
        state=self.lease.description(1,'a'*64)
        self.assertEqual(state['request_selector'],1)
        self.assertEqual(state['edit_preparation']['status'],'reserved')
        self.assertTrue(state['edit_preparation']['reserved'] and state['edit_preparation']['source_bound'])
        self.assertEqual(state['edit_preparation']['changes_staged'],0)
        for key in ('active_changes','accepted','testing','assembled','commit'):
            self.assertFalse(state['edit_preparation'][key])
        for key in ('project_transfer','online_edits','controller_mode_changes','tag_write_authority','scan_inhibited'):
            self.assertFalse(state[key])
        for action in (lambda:self.lease.acquire(self.second,1,'a'*64,selector=1),
                       lambda:self.lease.acquire(self.second,1,'a'*64),
                       lambda:self.lease.acquire(self.first,1,'a'*64),
                       lambda:self.lease.require_edit_owner(self.second,1,'a'*64),
                       lambda:self.lease.begin_preparation(self.first,1,'a'*64),
                       lambda:self.lease.end_preparation(self.first,1,'a'*64),
                       lambda:self.lease.require_prepared(self.first,1,'a'*64),
                       lambda:self.lease.set_run_inhibit(self.first,1,'a'*64,1)):
            with self.assertRaises(LeaseError):action()
        self.assertEqual(self.lease.description(1,'a'*64),state)
        self.lease.release(self.first,1,'a'*64)
        self.lease.acquire(self.first,1,'a'*64)
        with self.assertRaises(LeaseError):self.lease.require_edit_owner(self.first,1,'a'*64)
        with self.assertRaises(LeaseError):self.lease.acquire(self.first,1,'a'*64,selector=1)
        self.lease.set_run_inhibit(self.first,1,'a'*64,1)
        self.lease.begin_preparation(self.first,1,'a'*64)

    def test_edit_reservation_clears_with_owner_release_disconnect_source_generation_and_expiry(self):
        for kind in ('release','discard','source','generation','expiry','closed','key','stage'):
            self.now=100;first=self.context();self.lease.acquire(first,1,'a'*64,selector=1)
            self.lease.reserve_program(first,1,'a'*64,300)
            self.lease.open_edit_preparation(first,1,'a'*64)
            self.lease.prepare_zero_program_stack(first,1,'a'*64,300,0)
            prefix=b'X'*18
            self.lease.edit_transfer.accept(signed_messages.FragmentEnvelope(0x39,1,
                prefix+bytes.fromhex('09000000000000000000000000000000340000007f454c46')+bytes(8),0x101,72),
                target=(300,700),prefix=prefix)
            generation=1;source='a'*64
            if kind=='release':self.lease.release(first,1,source)
            elif kind=='discard':self.lease.discard(first)
            elif kind=='source':source='b'*64
            elif kind=='generation':generation=2
            elif kind=='expiry':self.now=400
            elif kind=='closed':first.close()
            elif kind=='key':first.key=None
            else:first.stage='operator'
            with self.subTest(kind=kind):
                state=self.lease.description(generation,source)
                self.assertIsNone(state['request_selector'])
                self.assertEqual(state['edit_preparation']['status'],'idle')
                self.assertFalse(state['edit_preparation']['reserved'] or state['edit_preparation']['source_bound'])
                self.assertIsNone(self.lease.owner)
                self.assertEqual(self.lease.program_reservations,set())
                self.assertEqual(self.lease.program_stack_preparations,{})
                self.assertFalse(self.lease.edit_phase_open)
                self.assertEqual(self.lease.edit_transfer._data,bytearray())
                self.assertFalse(self.lease.scan_inhibited(generation,source))

    def test_unknown_or_boolean_selector_never_acquires_or_changes_an_existing_reservation(self):
        for owned in (False,True):
            if owned:self.lease.acquire(self.first,1,'a'*64,selector=1)
            before=self.lease.description(1,'a'*64)
            for selector in (-1,2,255,None,True,b'\1','edit'):
                with self.subTest(owned=owned,selector=selector),self.assertRaises(LeaseError) as error:
                    self.lease.acquire(self.first,1,'a'*64,selector=selector)
                self.assertEqual(error.exception.status,3)
                self.assertEqual(self.lease.description(1,'a'*64),before)


class SemaphorePathTests(unittest.TestCase):
    def test_controller_scope_and_widths_are_kept(self):
        for parent in (1,256,65536):
            raw=logical(0x20,0x8E)+logical(0x24,parent)+logical(0x20,0x74)+logical(0x24,1)
            path=decode_path(raw)
            self.assertEqual((path.controller_instance,path.class_id,path.instance),(parent,0x74,1))
            self.assertIsNone(path.program_instance);self.assertIsNone(path.io_map_instance)

    def test_missing_mixed_and_deeper_paths_are_invalid(self):
        for raw in ('208e24012074','208e240020742401','2068240020742401',
                    '208e240120742401206b2401','208e2401300120742401'):
            with self.subTest(path=raw),self.assertRaises(CIPError):decode_path(bytes.fromhex(raw))

    def test_class_revision_scope_and_unsigned_coordination_denials(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0)
            try:
                for raw in ('0e03207424003001','0e05208e2401207424003001'):
                    self.assertEqual(endpoint.router.handle(bytes.fromhex(raw),Session()),bytes.fromhex('8e0000000100'))
                for raw,status in ((ACQUIRE,15),(RELEASE,15),(bytes.fromhex('0e05208e2402207424003001'),5)):
                    self.assertEqual(endpoint.router.handle(raw,Session())[2],status)
            finally:app.close()


class SemaphoreSignedTests(unittest.TestCase):
    setUp=native_tests.NativeSessionTests.setUp
    tearDown=native_tests.NativeSessionTests.tearDown
    cip=native_tests.NativeSessionTests.cip
    begin=native_tests.NativeSessionTests.begin
    signed=native_tests.NativeSessionTests.signed
    bind=native_tests.NativeSessionTests.bind

    def prepare(self):
        self.app.native_project_identity=NativeProjectIdentity('a'*64,self.app.engine.project.sha256,1,1,1,1,1,1)
        self.bind()

    def second_client(self):
        first=self.client;second=Client(self.endpoint.port);second.register()
        try:self.client=second;self.bind()
        finally:self.client=first
        return second

    def test_acquire_release_and_batch_keep_all_project_writes_denied(self):
        self.prepare();before=copy.deepcopy(self.app.engine.memory.values);identity=self.app.native_project_identity.manifest()
        self.assertEqual(self.signed(4,ACQUIRE),bytes.fromhex('cb000000'))
        self.assertTrue(self.endpoint.state()['native_programming_lease']['owned'])
        self.assertEqual(self.signed(5,ACQUIRE),bytes.fromhex('cb000000'))
        children=(bytes.fromhex('6102208e2401'),bytes.fromhex('100320ac2401300301000000'),RELEASE)
        raw=batch(children,sequence=6);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        response=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual([value[2] for value in response.children],[15,15,0])
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.app.native_project_identity.manifest(),identity)

    def test_another_client_cannot_acquire_or_release_until_owner_disconnects(self):
        self.prepare();second=self.second_client();first=self.client
        try:
            self.assertEqual(self.signed(4,ACQUIRE)[2],0)
            self.client=second
            self.assertEqual(self.signed(4,ACQUIRE)[2],12)
            self.assertEqual(self.signed(5,RELEASE)[2],15)
            row=self.endpoint.state()['native_rejections'][0]
            self.assertEqual((row['controller_instance'],row['class_id'],row['reason']),(1,0x74,'programming_lease_owner_required'))
            first.close()
            deadline=time.monotonic()+2
            while self.endpoint.state()['native_programming_lease']['owned'] and time.monotonic()<deadline:time.sleep(.01)
            self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
            self.assertEqual(self.signed(6,ACQUIRE)[2],0)
            self.assertEqual(self.signed(7,RELEASE)[2],0)
        finally:self.client=first;second.close()

    def test_source_correlation_payload_scope_and_unbound_guards(self):
        self.bind()
        self.assertEqual(self.signed(4,ACQUIRE)[2],12)
        self.app.native_project_identity=NativeProjectIdentity('a'*64,'b'*64,1,1,1,1,1,1)
        self.assertEqual(self.signed(5,ACQUIRE)[2],12)
        self.app.native_project_identity=NativeProjectIdentity('a'*64,self.app.engine.project.sha256,1,1,1,1,1,1)
        cases=((ACQUIRE[:-1],0x13),(ACQUIRE+b'x',0x15),(ACQUIRE[:-1]+b'\2',3),
               (RELEASE+b'\0',0x15),(bytes.fromhex('4b04208e24022074240100'),5),
               (bytes.fromhex('4b04208e24012074240200'),5),(bytes.fromhex('4b05208e240120742401300100'),4))
        for sequence,(raw,status) in enumerate(cases,6):
            self.assertEqual(self.signed(sequence,raw)[2],status)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.begin();self.assertEqual(self.signed(1,ACQUIRE)[2],15)

    def test_bad_mac_source_replacement_and_endpoint_stop_clear_ownership(self):
        self.prepare();self.assertEqual(self.signed(4,ACQUIRE)[2],0)
        raw=request(0x36,RELEASE,5)
        self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.bind();self.assertEqual(self.signed(4,ACQUIRE)[2],0)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.client.close();self.client=Client(self.endpoint.port);self.client.register()
        self.prepare();self.assertEqual(self.signed(4,ACQUIRE)[2],0)
        self.endpoint.stop();self.assertIsNone(self.endpoint.programming_lease.owner)


if __name__=='__main__':unittest.main()
