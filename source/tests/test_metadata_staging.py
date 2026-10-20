"""Definition staging stays bounded, private and independent of active metadata."""
import copy
import hmac
import json
import struct
import time
import unittest

from logixlab import signed_messages
from logixlab.ethernetip import logical
from logixlab.metadata_staging import MetadataError,MetadataStaging,MAX_DEFINITIONS,parse_create
import test_programming_lease as leases
import test_programming_preparation as prep
import test_run_inhibit as inhibits
import test_library_staging as libraries
from test_signed_batches import batch
from test_signed_messages import KEY
from test_signed_transfer import request as transfer_request


def payload(name=b'ExampleProperty'):
    return struct.pack('<HHH',1,1,len(name))+name


def object_request(service,instance,data=b''):
    path=logical(0x20,0x349)+logical(0x24,instance)
    return bytes((service,len(path)//2))+path+data


def create(instance=1,name=b'ExampleProperty'):return object_request(8,instance,payload(name))
def delete(instance=1):return object_request(9,instance)
_UNSUPPORTED_TARGET=struct.pack('<HIIIH',0x6B,1,0,0,1)
VALUES=object_request(0x4F,0,struct.pack('<II',0x301,len(_UNSUPPORTED_TARGET))+_UNSUPPORTED_TARGET)


class MetadataModelTests(unittest.TestCase):
    def test_full_udint_instances_limits_idempotence_and_conflicts(self):
        stage=MetadataStaging()
        self.assertEqual(stage.create(0xFFFFFFFF,payload()),b'\xFF'*4)
        self.assertEqual(stage.create(0xFFFFFFFF,payload()),b'\xFF'*4)
        for instance,name in ((0xFFFFFFFF,b'Changed'),(2,b'ExampleProperty')):
            with self.assertRaises(MetadataError):stage.create(instance,payload(name))
        for i in range(1,MAX_DEFINITIONS):stage.create(i,payload(f'Property_{i}'.encode()))
        self.assertEqual(stage.description()['instances'],MAX_DEFINITIONS)
        with self.assertRaises(MetadataError) as error:stage.create(MAX_DEFINITIONS,payload(b'Overflow'))
        self.assertEqual(error.exception.status,2)
        stage.delete(0xFFFFFFFF);stage.create(MAX_DEFINITIONS,payload(b'Replacement'))
        with self.assertRaises(MetadataError):stage.delete(0xFFFFFFFF)
        self.assertNotIn('Property_',json.dumps(stage.description()))
        stage.clear();self.assertEqual(stage.description()['name_bytes'],0)

    def test_initializer_rejects_ambiguous_fields_lengths_types_and_identifiers(self):
        self.assertEqual(parse_create(payload(b'A'*128)),b'A'*128)
        for raw in (b'',bytearray(payload()),payload()[:-1],payload()+b'\0',payload(b''),payload(b'A'*129),
                    payload(b'../path'),payload(b'1Invalid'),payload(b'has space'),payload(b'\xFF'),payload(b'A\0B'),
                    b'\2\0'+payload()[2:],payload()[:2]+b'\2\0'+payload()[4:]):
            with self.subTest(raw=raw[:6]),self.assertRaises(MetadataError):parse_create(raw)
        stage=MetadataStaging()
        for instance in (None,True,False,0,-1,0x100000000):
            with self.assertRaises(MetadataError):stage.create(instance,payload())
        self.assertEqual(stage.description()['instances'],0)

    def test_source_generation_expiry_and_context_invalidation_clear_both_stages(self):
        model=leases.ProgrammingLeaseModelTests();model.setUp();lease=model.lease
        for action in ('generation','source','expiry','closed','key','discard'):
            model.now=100;owner=model.context();lease.acquire(owner,1,'a'*64)
            lease.set_run_inhibit(owner,1,'a'*64,1);lease.begin_preparation(owner,1,'a'*64)
            lease.metadata.create(1,payload());lease.libraries.create(1,libraries.payload())
            generation,source=1,'a'*64
            if action=='generation':generation=2
            elif action=='source':source='b'*64
            elif action=='expiry':model.now=500
            elif action=='closed':owner.close()
            elif action=='key':owner.key=None
            else:lease.discard(owner)
            with self.subTest(action=action):
                state=lease.description(generation,source)
                self.assertEqual(state['metadata_staging']['instances'],0)
                self.assertEqual(state['library_staging']['instances'],0)
                self.assertEqual(lease.metadata.rows,{})


class MetadataSignedTests(unittest.TestCase):
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

    def stage(self):self.ready();self.assertEqual(self.send(create()),b'\x88\0\0\0\1\0\0\0')
    def description(self):return self.endpoint.state()['native_programming_lease']['metadata_staging']

    def test_numeric_widths_preserve_source_catalog_identity_values_and_mode(self):
        self.ready();before=copy.deepcopy(self.app.state());identity=self.app.native_project_identity.manifest()
        for i in (1,256,65536,0xFFFFFFFF):
            self.assertEqual(self.send(create(i,f'Property_{i}'.encode())),b'\x88\0\0\0'+struct.pack('<I',i))
        self.assertEqual(self.send(libraries.create())[2],0)
        self.assertEqual(self.description()['instances'],4)
        self.assertEqual(self.endpoint.state()['native_programming_lease']['library_staging']['instances'],1)
        self.assertEqual(self.send(object_request(0x4B,0)),b'\xCB\0\0\0')
        self.assertEqual(self.send(object_request(3,0,struct.pack('<3H',2,2,3))),
                         bytes.fromhex('83000000020002000000000000000300000000000000'))
        state=self.endpoint.state()['native_programming_lease']
        self.assertNotIn('Property_',json.dumps(state));self.assertFalse(state['metadata_staging']['active_values_transfer'])
        self.assertEqual(state['metadata_staging']['values_scope'],'staged_definitions')
        for name in ('project_transfer','online_edits','controller_mode_changes','tag_write_authority'):self.assertFalse(state[name])
        after=self.app.state()
        for name in ('tags','scan','ms','mode','changes'):self.assertEqual(after[name],before[name])
        self.assertEqual(self.app.native_project_identity.manifest(),identity)

    def test_preparation_source_exact_paths_and_lengths_are_required(self):
        self.prepare();self.sequence=4;self.assertEqual(self.send(create())[2],15)
        self.assertEqual(self.send(leases.ACQUIRE)[2],0);self.assertEqual(self.send(create())[2],12)
        self.assertEqual(self.send(inhibits.SET)[2],0);self.assertEqual(self.send(prep.BEGIN)[2],0)
        for raw,status in ((create(0),5),(create()[:-1],19),(create()+b'x',21),(delete()+b'x',21),
                (bytes.fromhex('08042100490324013001')+payload(),4),
                (bytes.fromhex('080521004903240191024141')+payload(),4)):
            with self.subTest(raw=raw.hex()):self.assertEqual(self.send(raw)[2],status)
        identity=self.app.native_project_identity;self.app.native_project_identity=None
        self.assertEqual(self.send(create())[2],12);self.app.native_project_identity=identity
        self.assertEqual(self.cip(create())[2],5)
        self.assertEqual(self.description()['instances'],0)

    def test_conflicts_repeats_and_delete_never_replace_or_leak_definitions(self):
        self.stage();self.assertEqual(self.send(create())[2],0)
        self.assertEqual(self.send(create(1,b'Changed'))[2],12)
        self.assertEqual(self.send(create(2))[2],12)
        self.assertEqual(self.description()['instances'],1)
        self.assertEqual(self.send(delete()),b'\x89\0\0\0');self.assertEqual(self.send(delete())[2],5)
        self.assertEqual(self.description()['instances'],0)
        self.assertEqual(self.endpoint.counts['native_metadata_create'],2)
        self.assertEqual(self.endpoint.counts['native_metadata_delete'],1)

    def test_foreign_context_cannot_create_or_delete_and_owner_disconnect_cleans_up(self):
        self.stage();first=self.client;second=self.second_client()
        try:
            self.client=second
            for seq,raw in ((4,create(2,b'Other')),(5,delete())):self.assertEqual(self.signed(seq,raw)[2],15)
            self.assertEqual(self.signed(6,object_request(0x4B,0)),b'\xCB\0\0\0')
            first.close();deadline=time.monotonic()+2
            while self.endpoint.state()['native_programming_lease']['owned'] and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(self.description()['instances'],0)
            self.assertEqual(self.signed(7,leases.ACQUIRE)[2],0)
        finally:self.client=first;second.close()

    def test_signed_transfer_value_denial_preserves_counter_stage_and_memory(self):
        self.stage();before=copy.deepcopy(self.app.engine.memory.values)
        raw=transfer_request(VALUES,self.sequence);self.sequence+=1
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.inner,b'\xCF\0\x0F\0');self.assertEqual(self.description()['instances'],1)
        self.assertEqual(self.send(VALUES),b'\xCF\0\x0F\0')
        self.assertEqual(self.send(delete())[2],0)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.endpoint.state()['native_rejections'][0]['reason'],'metadata_values_not_permitted')

    def test_batch_errors_do_not_install_values_or_prevent_stage_cleanup(self):
        self.ready();children=(create(),VALUES,delete(),create(),prep.END,inhibits.CLEAR)
        raw=batch(children,sequence=self.sequence);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual([v[2] for v in result.children],[0,15,0,0,0,0])
        self.assertEqual(self.description()['instances'],0)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['scan_inhibited'])

    def test_end_clear_release_reset_reload_stop_and_bad_mac_discard_both_stages(self):
        for action in ('end','clear','release','reset','reload','bad-mac','stop'):
            with self.subTest(action=action):
                self.stage();self.assertEqual(self.send(libraries.create())[2],0)
                if action=='end':self.send(prep.END)
                elif action=='clear':self.send(inhibits.CLEAR)
                elif action=='release':self.send(leases.RELEASE)
                elif action=='reset':self.app.command('reset',{})
                elif action=='reload':self.app.command('demo',{'sample':'ConveyorDemo'})
                elif action=='bad-mac':
                    raw=transfer_request(VALUES,self.sequence)
                    self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
                else:self.endpoint.stop()
                lease=self.endpoint.programming_lease
                self.assertEqual(lease.metadata.description()['instances'],0)
                self.assertEqual(lease.libraries.description()['instances'],0)
                if action in ('reset','reload'):
                    self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()


if __name__=='__main__':unittest.main()
