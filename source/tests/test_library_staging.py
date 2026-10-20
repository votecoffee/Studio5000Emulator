"""Staging never installs code, replaces the project or exposes library names."""
import copy
import hmac
import json
import struct
import unittest

from logixlab import signed_messages
from logixlab.library_staging import LibraryError,LibraryStaging,MAX_LIBRARIES,parse_create
import test_programming_preparation as prep
import test_programming_lease as leases
import test_run_inhibit as inhibits
from test_signed_batches import batch
from test_signed_messages import KEY
from test_signed_transfer import request as transfer_request


def payload(name=b'Example.LIB',kind=0):
    return struct.pack('<HHIHH',2,3,kind,2,len(name))+name


def create(instance=1,name=b'Example.LIB'):
    return bytes.fromhex('080421007d032500')+struct.pack('<H',instance)+payload(name)


def delete(instance=1):return bytes.fromhex('090421007d032500')+struct.pack('<H',instance)


class LibraryModelTests(unittest.TestCase):
    def test_sparse_instances_duplicates_conflicts_and_resource_limit(self):
        stage=LibraryStaging()
        self.assertEqual(stage.create(65535,payload()),b'\xFF\xFF')
        self.assertEqual(stage.create(65535,payload()),b'\xFF\xFF')
        for instance,name in ((65535,b'Changed'),(2,b'Example.LIB')):
            with self.assertRaises(LibraryError):stage.create(instance,payload(name))
        for i in range(1,MAX_LIBRARIES):stage.create(i,payload(str(i).encode()))
        self.assertEqual(stage.description()['instances'],MAX_LIBRARIES)
        with self.assertRaises(LibraryError) as error:stage.create(MAX_LIBRARIES,payload(b'Overflow'))
        self.assertEqual(error.exception.status,2)
        stage.delete(65535);stage.create(MAX_LIBRARIES,payload(b'Replacement'))
        with self.assertRaises(LibraryError):stage.delete(65535)
        self.assertNotIn('Example',json.dumps(stage.description()))
        stage.clear();self.assertEqual(stage.description()['instances'],0)

    def test_initializer_has_exact_supported_fields_name_bounds_and_type(self):
        self.assertEqual(parse_create(payload(b'A'*256)).name,b'A'*256)
        for raw in (b'',payload()[:-1],payload()+b'\0',payload(b''),payload(b'A'*257),payload(kind=1),
                    payload(b'../path'),payload(b'has space'),payload(b'\xFF'),payload(b'A\0B'),
                    b'\3\0'+payload()[2:],payload()[:8]+b'\3\0'+payload()[10:]):
            with self.subTest(raw=raw[:12]),self.assertRaises(LibraryError):parse_create(raw)
        stage=LibraryStaging()
        for instance in (None,True,0,-1,65536):
            with self.assertRaises(LibraryError):stage.create(instance,payload())
        self.assertEqual(stage.description()['instances'],0)

    def test_source_generation_expiry_and_closed_owner_discard_staged_names(self):
        model=leases.ProgrammingLeaseModelTests();model.setUp()
        lease=model.lease
        for action in ('generation','source','expiry','closed','key'):
            model.now=100;owner=model.context();lease.acquire(owner,1,'a'*64)
            lease.set_run_inhibit(owner,1,'a'*64,1);lease.begin_preparation(owner,1,'a'*64)
            lease.libraries.create(1,payload())
            generation,source=1,'a'*64
            if action=='generation':generation=2
            elif action=='source':source='b'*64
            elif action=='expiry':model.now=500
            elif action=='closed':owner.close()
            else:owner.key=None
            with self.subTest(action=action):
                self.assertEqual(lease.description(generation,source)['library_staging']['instances'],0)
                self.assertEqual(lease.libraries.rows,{})


class LibrarySignedTests(unittest.TestCase):
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

    def stage(self):self.ready();self.assertEqual(self.send(create()),b'\x88\0\0\0\1\0')
    def description(self):return self.endpoint.state()['native_programming_lease']['library_staging']

    def test_owned_create_delete_and_repeat_do_not_change_source_or_model(self):
        self.ready();values=copy.deepcopy(self.app.engine.memory.values);identity=self.app.native_project_identity.manifest()
        self.assertEqual(self.send(create()),b'\x88\0\0\0\1\0');self.assertEqual(self.send(create())[2],0)
        self.assertEqual(self.description()['instances'],1)
        self.assertEqual(self.send(create(1,b'Changed'))[2],12)
        self.assertEqual(self.send(create(2))[2],12)
        self.assertEqual(self.send(delete()),b'\x89\0\0\0');self.assertEqual(self.send(delete())[2],5)
        state=self.endpoint.state()['native_programming_lease']
        self.assertNotIn('Example',json.dumps(state));self.assertFalse(state['library_staging']['data_transfer'])
        for name in ('project_transfer','online_edits','controller_mode_changes','tag_write_authority'):self.assertFalse(state[name])
        self.assertEqual(self.app.engine.memory.values,values);self.assertEqual(self.app.native_project_identity.manifest(),identity)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_preparation_source_path_payload_and_foreign_owner_are_required(self):
        self.prepare();self.sequence=4;self.assertEqual(self.send(create())[2],15)
        self.assertEqual(self.send(leases.ACQUIRE)[2],0);self.assertEqual(self.send(create())[2],12)
        self.assertEqual(self.send(inhibits.SET)[2],0);self.assertEqual(self.send(prep.BEGIN)[2],0)
        for raw,status in ((create(0),5),(create()[:-1],19),(create()+b'x',21),(delete()+b'x',21),
                (bytes.fromhex('080421007d0324013002')+payload(),4)):
            with self.subTest(raw=raw.hex()):self.assertEqual(self.send(raw)[2],status)
        identity=self.app.native_project_identity;self.app.native_project_identity=None
        self.assertEqual(self.send(create())[2],12);self.app.native_project_identity=identity
        self.assertEqual(self.cip(create())[2],8)
        self.assertEqual(self.send(create())[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second
            for seq,raw in ((4,create(2,b'Other')),(5,delete())):self.assertEqual(self.signed(seq,raw)[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(self.description()['instances'],1)

    def test_transfer_wrapper_data_denial_keeps_stage_and_counter_for_cleanup(self):
        self.stage();raw=transfer_request(prep.LIBRARY_WRITE,self.sequence);self.sequence+=1
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.inner,b'\xCD\0\x0F\0');self.assertEqual(self.description()['instances'],1)
        self.assertEqual(self.send(delete())[2],0)
        self.assertEqual(self.send(prep.END)[2],0)
        self.assertTrue(self.endpoint.state()['native_programming_lease']['scan_inhibited'])
        self.assertEqual(self.send(leases.RELEASE)[2],0)

    def test_batch_deletion_and_end_cleanup_leave_no_project_write_authority(self):
        self.ready();children=(create(),prep.LIBRARY_WRITE,delete(),create(),prep.END,inhibits.CLEAR)
        raw=batch(children,sequence=self.sequence);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual([v[2] for v in result.children],[0,15,0,0,0,0])
        self.assertEqual(self.description()['instances'],0)

    def test_end_clear_release_reset_reload_stop_and_bad_mac_discard_descriptors(self):
        for action in ('end','clear','release','reset','reload','bad-mac','stop'):
            with self.subTest(action=action):
                self.stage();self.assertEqual(self.description()['instances'],1)
                if action=='end':self.send(prep.END)
                elif action=='clear':self.send(inhibits.CLEAR)
                elif action=='release':self.send(leases.RELEASE)
                elif action=='reset':self.app.command('reset',{})
                elif action=='reload':self.app.command('demo',{'sample':'ConveyorDemo'})
                elif action=='bad-mac':
                    raw=transfer_request(prep.LIBRARY_WRITE,self.sequence)
                    self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
                else:self.endpoint.stop()
                self.assertEqual(self.endpoint.programming_lease.libraries.description()['instances'],0)
                if action in ('reset','reload'):
                    self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()

    def test_owner_disconnect_drops_descriptors_before_another_client_acquires(self):
        self.stage();first=self.client;second=self.second_client()
        try:
            first.close()
            import time
            deadline=time.monotonic()+2
            while self.endpoint.state()['native_programming_lease']['owned'] and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(self.description()['instances'],0)
            self.client=second
            self.assertEqual(self.signed(4,leases.ACQUIRE)[2],0)
        finally:self.client=first;second.close()


if __name__=='__main__':unittest.main()
