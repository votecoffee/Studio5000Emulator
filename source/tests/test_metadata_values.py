"""Temporary typed metadata proposals are atomic and never write active objects."""
import copy
import hmac
import json
import struct
import time
import unittest

from logixlab import signed_messages
from logixlab.metadata_staging import (MetadataError,MetadataStaging,Value,parse_values,
    MAX_FIELDS,MAX_INPUT_BYTES,MAX_VALUES,MAX_VALUE_BYTES)
import test_metadata_staging as definitions
import test_programming_lease as leases
import test_programming_preparation as prep
import test_run_inhibit as inhibits
from test_signed_batches import batch
from test_signed_messages import KEY
from test_signed_transfer import request as transfer_request


def text(data=b'AB'):return Value(1,None,1,data)
def numeric(code=0xC2,data=b'\x80\x7F'):return Value(2,code,len(data)//(1 if code==0xC2 else 2),data)


def packet(target,fields,*,single=False,class_id=0x349):
    body=struct.pack('<HIII',class_id,target,0,0)
    if not single:body+=struct.pack('<H',len(fields))
    for reference,value in fields:
        body+=struct.pack('<H',0x7F)
        if not single:body+=struct.pack('<H',reference)
        body+=bytes(12)+struct.pack('<H',value.kind)
        body+=(struct.pack('<H',len(value.data)) if value.kind==1 else struct.pack('<HH',value.type_code,value.elements))+value.data
    return struct.pack('<II',0x301,len(body))+body


def write(target=1,fields=None,reference=0):
    if fields is None:fields=[(2,text())]
    return definitions.object_request(0x4F,reference,packet(target,fields,single=bool(reference)))


class MetadataValueModelTests(unittest.TestCase):
    def stage(self,count=3):
        stage=MetadataStaging()
        for i in range(1,count+1):stage.create(i,definitions.payload(f'Property_{i}'.encode()))
        return stage

    def test_hand_authored_bulk_and_single_vectors_decode_the_same_bytes(self):
        bulk=bytes.fromhex('0103000026000000490301000000000000000000000001007f000200000000000000000000000000010002004142')
        single=bytes.fromhex('010300002200000049030100000000000000000000007f00000000000000000000000000010002004142')
        self.assertEqual(packet(1,[(2,text())]),bulk)
        self.assertEqual(packet(1,[(2,text())],single=True),single)
        self.assertEqual(parse_values(bulk),(1,((2,text()),)))
        self.assertEqual(parse_values(single,2),parse_values(bulk))
        fields=[(1,text(b'')),(2,numeric()),(3,numeric(0xC3,b'\0\x80\xFF\x7F'))]
        self.assertEqual(parse_values(packet(1,fields)),(1,tuple(fields)))
        self.assertEqual(struct.unpack('<hh',fields[2][1].data),(-32768,32767))

    def test_every_truncated_prefix_and_surplus_byte_is_rejected(self):
        raw=packet(1,[(2,text()),(3,numeric())])
        for size in range(len(raw)):
            with self.subTest(size=size),self.assertRaises(MetadataError):parse_values(raw[:size])
        for data in (raw+b'x',bytearray(raw),b'x'*(MAX_INPUT_BYTES+1)):
            with self.assertRaises(MetadataError):parse_values(data)
        for offset,value in ((0,0x302),(4,len(raw)),(4,0)):
            damaged=bytearray(raw);struct.pack_into('<I',damaged,offset,value)
            with self.assertRaises(MetadataError):parse_values(bytes(damaged))

    def test_unsupported_targets_selectors_types_and_duplicate_references_fail(self):
        raw=packet(1,[(2,text())])
        for offset,fmt,value in ((8,'<H',0x6B),(14,'<I',1),(18,'<I',1),(24,'<H',0x80),
                                 (28,'<I',1),(32,'<I',1),(36,'<I',1),(40,'<H',3)):
            damaged=bytearray(raw);struct.pack_into(fmt,damaged,offset,value)
            with self.subTest(offset=offset),self.assertRaises(MetadataError):parse_values(bytes(damaged))
        for fields in ([],[(0,text())],[(2,text()),(2,text())],[(2,text(b'\0'))],[(2,text(b'\xFF'))],
                       [(2,Value(2,0xC4,1,bytes(4)))],[(2,Value(2,0xC2,0,b''))]):
            with self.assertRaises(MetadataError):parse_values(packet(1,fields))
        for reference in (-1,True,0x100000000):
            with self.assertRaises(MetadataError):parse_values(raw,reference)

    def test_atomic_merge_conflict_unknown_reference_and_bad_late_record_preserve_stage(self):
        stage=self.stage();first=packet(1,[(2,text())]);stage.stage_values(first)
        original=copy.deepcopy(stage.values)
        for raw in (packet(1,[(3,text(b'new')),(2,text(b'changed'))]),packet(1,[(3,text()),(4,text())]),
                    packet(4,[(2,text())]),packet(1,[(3,text()),(2,Value(2,0xC4,1,bytes(4)))])):
            with self.assertRaises(MetadataError):stage.stage_values(raw)
            self.assertEqual(stage.values,original)
        stage.stage_values(first);self.assertEqual(stage.description()['value_count'],1)
        stage.stage_values(packet(1,[(3,numeric())],single=True),3)
        self.assertEqual(stage.description()['value_count'],2)

    def test_delete_discards_temporary_targets_and_references_and_hides_values(self):
        stage=self.stage();stage.stage_values(packet(1,[(2,text(b'PrivateValue'))]))
        stage.stage_values(packet(2,[(1,text(b'OtherValue'))]))
        summary=json.dumps(stage.description())
        for secret in ('PrivateValue','OtherValue','Property_'):self.assertNotIn(secret,summary)
        self.assertFalse(stage.description()['active_values_transfer']);self.assertFalse(stage.description()['commit'])
        stage.delete(1);self.assertEqual(stage.description()['value_count'],0)
        self.assertEqual(stage.description()['value_targets'],0)
        stage.clear();self.assertEqual((stage.rows,stage.values),({},{}))

    def test_field_count_and_global_value_limits_are_enforced_without_partial_additions(self):
        stage=self.stage(MAX_FIELDS+1);fields=[(i,text(b'')) for i in range(1,MAX_FIELDS+1)]
        for target in range(1,MAX_VALUES//MAX_FIELDS+1):stage.stage_values(packet(target,fields))
        self.assertEqual(stage.description()['value_count'],MAX_VALUES)
        before=copy.deepcopy(stage.values)
        for raw in (packet(MAX_FIELDS+1,[(1,text())]),packet(1,[(MAX_FIELDS+1,text())])):
            with self.assertRaises(MetadataError):stage.stage_values(raw)
            self.assertEqual(stage.values,before)

    def test_value_byte_and_field_byte_limits_allow_exact_capacity_then_reject_growth(self):
        stage=self.stage(MAX_FIELDS)
        for target in range(1,9):
            for start in range(1,MAX_FIELDS+1,16):
                stage.stage_values(packet(target,[(i,text(b'A'*512)) for i in range(start,start+16)]))
        self.assertEqual(stage.description()['value_bytes'],MAX_VALUE_BYTES)
        before=copy.deepcopy(stage.values)
        for raw in (packet(9,[(1,text(b'B'))]),packet(9,[(1,text(b'A'*1025))]),
                    packet(9,[(1,Value(2,0xC3,513,bytes(1026)))])):
            with self.assertRaises(MetadataError):stage.stage_values(raw)
            self.assertEqual(stage.values,before)


class MetadataValueSignedTests(unittest.TestCase):
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

    def stage(self):
        self.ready()
        for i in (1,2,3):self.assertEqual(self.send(definitions.create(i,f'Property_{i}'.encode()))[2],0)

    def description(self):return self.endpoint.state()['native_programming_lease']['metadata_staging']

    def test_single_bulk_and_transfer_messages_keep_active_model_and_catalog_unchanged(self):
        self.stage();before=copy.deepcopy(self.app.state());identity=self.app.native_project_identity.manifest()
        self.assertEqual(self.send(write()),b'\xCF\0\0\0')
        raw=transfer_request(write(1,[(3,numeric())],3),self.sequence);self.sequence+=1
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.inner,b'\xCF\0\0\0');self.assertEqual(self.description()['value_count'],2)
        self.assertEqual(self.send(definitions.object_request(0x4B,0)),b'\xCB\0\0\0')
        state=self.endpoint.state()['native_programming_lease']
        self.assertFalse(state['metadata_staging']['active_values_transfer']);self.assertFalse(state['project_transfer'])
        for secret in ('Property_','4142'):self.assertNotIn(secret,json.dumps(state))
        after=self.app.state()
        for key in ('tags','scan','ms','mode','changes'):self.assertEqual(after[key],before[key])
        self.assertEqual(self.app.native_project_identity.manifest(),identity)
        self.assertEqual(self.endpoint.counts['native_metadata_value_packets'],2)

    def test_owner_preparation_source_and_exact_paths_are_enforced(self):
        self.prepare();self.sequence=4;self.assertEqual(self.send(write())[2],15)
        self.send(leases.ACQUIRE);self.assertEqual(self.send(write())[2],12)
        self.send(inhibits.SET);self.send(prep.BEGIN)
        self.assertEqual(self.send(write())[2],5)
        self.send(definitions.create(1));self.send(definitions.create(2,b'Other'))
        identity=self.app.native_project_identity;self.app.native_project_identity=None
        self.assertEqual(self.send(write())[2],12);self.app.native_project_identity=identity
        malformed=bytes.fromhex('4f042100490324003001')+packet(1,[(2,text())])
        self.assertEqual(self.send(malformed)[2],4);self.assertEqual(self.cip(write())[2],8)
        self.assertEqual(self.send(write())[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,write())[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(self.description()['value_count'],1)

    def test_batch_failed_value_update_preserves_prior_proposal_until_end(self):
        self.stage()
        children=(write(),write(1,[(2,text(b'changed'))]),definitions.VALUES,prep.END,inhibits.CLEAR)
        raw=batch(children,sequence=self.sequence);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual([v[2] for v in result.children],[0,12,15,0,0])
        self.assertEqual(self.description()['value_count'],0)

    def test_end_clear_release_reset_reload_bad_mac_and_stop_discard_staged_values(self):
        for action in ('end','clear','release','reset','reload','bad-mac','stop'):
            with self.subTest(action=action):
                self.stage();self.assertEqual(self.send(write())[2],0)
                if action=='end':self.send(prep.END)
                elif action=='clear':self.send(inhibits.CLEAR)
                elif action=='release':self.send(leases.RELEASE)
                elif action=='reset':self.app.command('reset',{})
                elif action=='reload':self.app.command('demo',{'sample':'ConveyorDemo'})
                elif action=='bad-mac':
                    raw=transfer_request(write(),self.sequence)
                    self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
                else:self.endpoint.stop()
                self.assertEqual(self.endpoint.programming_lease.metadata.description()['value_count'],0)
                if action in ('reset','reload'):
                    self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()

    def test_owner_disconnect_expiry_and_source_changes_remove_values(self):
        self.stage();self.send(write());owner=self.endpoint.programming_lease.owner
        owner.deadline=time.monotonic()-1
        self.assertEqual(self.description()['value_count'],0)
        self.stage();self.send(write())
        self.endpoint.programming_lease.description(self.app.generation+1,self.app.engine.project.sha256)
        self.assertEqual(self.endpoint.programming_lease.metadata.values,{})
        self.stage();self.send(write());self.client.close();deadline=time.monotonic()+2
        while self.endpoint.state()['native_programming_lease']['owned'] and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(self.description()['value_count'],0)


if __name__=='__main__':unittest.main()
