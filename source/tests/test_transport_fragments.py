"""Synthetic fragment streams never install device data or change the project."""
import copy
from dataclasses import replace
import hmac
import json
import struct
import time
import unittest

from logixlab import signed_messages as sm
from logixlab.resilient_transport import (ResilientTransport,TransportError,DEVICE_HEADER,
                                        MAX_BUFFER_BYTES,MAX_FRAGMENTS,ASSEMBLY_SECONDS)
from tools.inspect_cip_capture import summarize
import test_capture_inspection as captures
import test_resilient_transport as transport
import test_programming_preparation as prep
import test_programming_lease as leases
import test_run_inhibit as inhibits
from test_signed_messages import KEY


def message(word,position,data,sequence):
    raw=bytes.fromhex('390220022401')+struct.pack('<II',word,position)+data+struct.pack('<I',sequence)
    return raw+hmac.digest(KEY,raw,'sha1')


def part(word,position,data):return sm.FragmentEnvelope(0x39,7,data,word,position)


# OpenSSL HMAC-SHA1 vectors with the public synthetic KEY, generated independently.
VECTORS=(
 ('39022002240101010000050000005c032100120424000100000014000000414207000000979eba51fec0a3a75bc49ed4a7a09ba0d87586b9',
  'b9000000010300000000000007000000db70d79b96649a86e862b7905dd8b3f1da6e9d57'),
 ('39022002240101000000020000004308000000e4df27d136b31046121437f9dc57e1f8ef999356',
  'b9000000010300000000000008000000ce4e9fcccb20678076ab9bcaa68b44c4f352ed17'),
 ('3902200224010102000003000000444509000000616e2ad87d3e9fc62e946d0b1616d88fc76cc704',
  'b9000000010300000000000009000000ccd613eed4e37c661dd2bb5f1dc702dca2ecab19'))


class FragmentCodecTests(unittest.TestCase):
    def test_independent_vectors_preserve_opaque_bytes_offsets_counter_and_ack(self):
        for index,(q,a) in enumerate(VECTORS,7):
            raw=bytes.fromhex(q);answer=bytes.fromhex(a)
            decoded=sm.verify_request(raw,KEY,expected_sequence=index)
            self.assertIsInstance(decoded,sm.FragmentEnvelope)
            self.assertEqual(message(decoded.container_format,decoded.position,decoded.fragment,index),raw)
            self.assertEqual(sm.encode_fragment_ack(decoded,KEY),answer)
            self.assertEqual(sm.verify_response(answer,KEY,request=decoded),sm.FragmentAck(0x39,index))
            self.assertNotIn('key',vars(decoded))

    def test_every_changed_byte_wrong_key_and_replay_counter_are_rejected(self):
        for q,a in VECTORS:
            raw=bytes.fromhex(q);parsed=sm.parse_request(raw);answer=bytes.fromhex(a)
            for original,verify in ((raw,lambda v:sm.verify_request(v,KEY,expected_sequence=parsed.sequence)),
                    (answer,lambda v:sm.verify_response(v,KEY,request=parsed))):
                for i in range(len(original)):
                    changed=original[:i]+bytes((original[i]^1,))+original[i+1:]
                    with self.subTest(at=i),self.assertRaises(sm.EnvelopeError):verify(changed)
            with self.assertRaises(sm.EnvelopeError):sm.verify_request(raw,KEY[::-1],expected_sequence=parsed.sequence)
            with self.assertRaises(sm.EnvelopeError):sm.verify_request(raw,KEY,expected_sequence=parsed.sequence+1)

    def test_empty_oversize_unknown_format_and_forged_contexts_cannot_be_acknowledged(self):
        parsed=sm.parse_request(bytes.fromhex(VECTORS[0][0]))
        for field,value in (('service',0x36),('sequence',True),('container_format',True),
                ('container_format',0x301),('position',True),('position',-1),('fragment',bytearray(b'A')),('fragment',b'')):
            with self.subTest(field=field,value=value),self.assertRaises(sm.EnvelopeError):
                sm.encode_fragment_ack(replace(parsed,**{field:value}),KEY)
        for raw in (message(1,0,b'',7),message(0x401,1,b'A',7),message(1,0,b'A'*sm.MAX_MESSAGE,7)):
            with self.assertRaises(sm.EnvelopeError):sm.parse_request(raw)
        raw=message(1,0,b'A'*(sm.MAX_MESSAGE-38),7)
        self.assertEqual(len(raw),sm.MAX_MESSAGE);self.assertEqual(sm.parse_request(raw).position,0)
        with self.assertRaises(sm.EnvelopeError):sm.encode_response(parsed,b'\xDC\0\0\0',KEY)

    def test_capture_reports_fragment_structure_without_exposing_opaque_payload_or_asserting_integrity(self):
        packets=[]
        for frame,(q,a) in enumerate(VECTORS,1):
            packets.extend((captures.packet(frame*2-1,bytes.fromhex(q)),captures.packet(frame*2,bytes.fromhex(a),frame*2-1)))
        report=summarize(packets);self.assertEqual(len(report['exchanges']),3)
        for pair in report['exchanges']:
            request=pair['request']['signed_envelope'];answer=pair['response']['signed_envelope']
            self.assertEqual(request['integrity'],'NOT VERIFIED');self.assertTrue(answer['acknowledgement'])
            self.assertIn('fragment_sha256',request);self.assertNotIn('fragment_hex',request)
        first=report['exchanges'][0]['request']['signed_envelope']['first_request']
        self.assertEqual((first['service'],first['class_id'],first['instance']),(0x5C,0x412,0))
        for q,a in VECTORS:self.assertNotIn(q,json.dumps(report))
        self.assertIn('fragment_hex',summarize(packets,True)['exchanges'][1]['request']['signed_envelope'])


class FragmentModelTests(unittest.TestCase):
    def setUp(self):
        self.now=100.;self.stage=ResilientTransport(lambda:self.now);self.stage.open(transport.payload())

    def start(self,total=5,data=b'AB'):self.stage.accept(part(0x101,total,DEVICE_HEADER+data))

    def test_contiguous_fragments_complete_without_installing_or_exposing_bytes(self):
        self.start();self.stage.accept(part(1,2,b'C'));self.stage.accept(part(0x201,3,b'DE'))
        self.assertEqual(self.stage._data,b'ABCDE');state=self.stage.description()
        self.assertTrue(state['complete']);self.assertEqual((state['received_bytes'],state['total_bytes'],state['fragments']),(5,5,3))
        self.assertTrue(state['buffer_allocated']);self.assertFalse(state['payload_transfer'] or state['commit'])
        self.assertNotIn('ABCDE',json.dumps(state));self.stage.open(transport.payload())
        self.assertEqual(self.stage._data,b'ABCDE');self.stage.clear();self.assertFalse(self.stage.description()['buffer_allocated'])

    def test_offsets_holes_duplicates_premature_end_and_overflow_discard_only_fragments(self):
        for raw in (part(1,0,b'C'),part(1,3,b'C'),part(0x201,2,b'C'),part(1,2,b'CDE'),
                part(0x201,2,b'CDEF'),part(0x101,5,DEVICE_HEADER+b'AB'),part(1,2,b'')):
            self.start()
            with self.subTest(raw=raw),self.assertRaises(TransportError):self.stage.accept(raw)
            state=self.stage.description();self.assertTrue(state['open']);self.assertEqual(state['received_bytes'],0)
        with self.assertRaises(TransportError):self.stage.accept(part(1,2,b'C'))

    def test_exact_capacity_and_fragment_count_limits_are_bounded(self):
        self.start(MAX_BUFFER_BYTES,b'A')
        while len(self.stage._data)<MAX_BUFFER_BYTES:
            left=MAX_BUFFER_BYTES-len(self.stage._data);size=min(left,60000)
            self.stage.accept(part(0x201 if size==left else 1,len(self.stage._data),b'Z'*size))
        self.assertEqual(self.stage.description()['received_bytes'],MAX_BUFFER_BYTES)
        self.stage.clear_fragments();self.start(MAX_FRAGMENTS+1,b'A')
        for offset in range(1,MAX_FRAGMENTS):self.stage.accept(part(1,offset,b'B'))
        with self.assertRaises(TransportError):self.stage.accept(part(0x201,MAX_FRAGMENTS,b'C'))
        self.assertEqual(self.stage.description()['received_bytes'],0)
        self.start(MAX_FRAGMENTS,b'A')
        for offset in range(1,MAX_FRAGMENTS):self.stage.accept(part(0x201 if offset==MAX_FRAGMENTS-1 else 1,offset,b'B'))
        self.assertTrue(self.stage.complete);self.assertEqual(self.stage.fragments,MAX_FRAGMENTS)

    def test_first_header_unknown_selectors_and_announced_size_are_checked_before_allocating(self):
        for total,data in ((MAX_BUFFER_BYTES+1,DEVICE_HEADER+b'A'),(1,DEVICE_HEADER+b'A'),(0,DEVICE_HEADER+b'A'),
                (5,DEVICE_HEADER),(5,DEVICE_HEADER[:-1]+b'\1A'),(5,bytes(16)+b'A')):
            with self.subTest(total=total,data=data),self.assertRaises(TransportError):self.stage.accept(part(0x101,total,data))
            self.assertFalse(self.stage.description()['buffer_allocated'])
        self.stage.clear()
        with self.assertRaises(TransportError):self.start()

    def test_absolute_timeout_expires_partial_and_complete_buffers_without_renewal(self):
        self.start();self.now+=ASSEMBLY_SECONDS-1;self.stage.accept(part(1,2,b'C'))
        self.now+=1;self.assertEqual(self.stage.description()['received_bytes'],0)
        with self.assertRaises(TransportError):self.stage.accept(part(0x201,3,b'DE'))
        self.start();self.stage.accept(part(0x201,2,b'CDE'));self.now+=ASSEMBLY_SECONDS
        self.assertTrue(self.stage.description()['open']);self.assertFalse(self.stage.complete)


class FragmentSignedTests(unittest.TestCase):
    setUp=transport.TransportSignedTests.setUp
    tearDown=transport.TransportSignedTests.tearDown
    cip=transport.TransportSignedTests.cip
    begin=transport.TransportSignedTests.begin
    signed=transport.TransportSignedTests.signed
    bind=transport.TransportSignedTests.bind
    prepare=transport.TransportSignedTests.prepare
    second_client=transport.TransportSignedTests.second_client
    send=transport.TransportSignedTests.send
    acquire=transport.TransportSignedTests.acquire
    ready=transport.TransportSignedTests.ready
    description=transport.TransportSignedTests.description

    def stage(self):self.ready();self.send(transport.SETUP)

    def fragment(self,word,position,data,*,expect=0):
        raw=message(word,position,data,self.sequence);self.sequence+=1;response=self.cip(raw)
        self.assertEqual(response[2],expect)
        if expect==0:self.assertEqual(sm.verify_response(response,KEY,request=sm.parse_request(raw)).sequence,self.sequence-1)
        return raw

    def first(self):return self.fragment(0x101,5,DEVICE_HEADER+b'AB')

    def test_signed_stream_shares_counter_with_reads_and_keeps_device_processing_denied(self):
        self.stage();before=copy.deepcopy(self.app.state());identity=self.app.native_project_identity.manifest()
        self.first();self.assertEqual(self.send(inhibits.SINGLE)[2],0)
        self.fragment(1,2,b'C');self.fragment(0x201,3,b'DE')
        self.assertTrue(self.description()['complete']);self.assertEqual(self.description()['received_bytes'],5)
        self.assertEqual(self.send(bytes.fromhex('0603210012042400')),bytes.fromhex('86000f00'))
        self.assertTrue(self.description()['complete']);self.assertEqual(self.endpoint.counts['native_transport_fragment'],3)
        for key in ('tags','scan','ms','mode','changes'):self.assertEqual(self.app.state()[key],before[key])
        self.assertEqual(self.app.native_project_identity.manifest(),identity)
        self.send(transport.DELETE);self.assertEqual(self.description()['received_bytes'],0)

    def test_owner_preparation_setup_and_source_are_required_before_buffer_changes(self):
        self.prepare();self.sequence=4;self.fragment(0x101,5,DEVICE_HEADER+b'AB',expect=15)
        self.send(leases.ACQUIRE);self.fragment(0x101,5,DEVICE_HEADER+b'AB',expect=12)
        self.send(inhibits.SET);self.send(prep.BEGIN);self.fragment(0x101,5,DEVICE_HEADER+b'AB',expect=12)
        self.send(transport.SETUP);identity=self.app.native_project_identity;self.app.native_project_identity=None
        self.fragment(0x101,5,DEVICE_HEADER+b'AB',expect=12);self.app.native_project_identity=identity
        self.first();first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.cip(message(1,2,b'C',4))[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(self.description()['received_bytes'],2);self.fragment(0x201,2,b'CDE')

    def test_bad_offsets_discard_buffer_but_keep_setup_and_live_context_for_cleanup(self):
        self.stage();self.first();self.fragment(1,3,b'C',expect=3)
        self.assertTrue(self.description()['open']);self.assertEqual(self.description()['received_bytes'],0)
        self.first();self.fragment(0x201,2,b'CDE');self.send(prep.END)
        self.assertFalse(self.description()['open']);self.assertEqual(self.description()['received_bytes'],0)

    def test_replay_and_bad_mac_discard_owning_context_and_all_stages(self):
        for action in ('replay','bad-mac'):
            self.stage();raw=self.first()
            if action=='bad-mac':raw=message(1,2,b'C',self.sequence);raw=raw[:-1]+bytes((raw[-1]^1,))
            self.assertEqual(self.cip(raw)[2],15)
            self.assertFalse(self.description()['open']);self.assertEqual(self.description()['received_bytes'],0)

    def test_end_clear_release_reset_reload_stop_and_disconnect_discard_payloads(self):
        for action in ('end','clear','release','reset','reload','disconnect','stop'):
            self.stage();self.first();self.assertTrue(self.description()['buffer_allocated'])
            if action=='end':self.send(prep.END)
            elif action=='clear':self.send(inhibits.CLEAR)
            elif action=='release':self.send(leases.RELEASE)
            elif action=='reset':self.app.command('reset',{})
            elif action=='reload':self.app.command('demo',{'sample':'ConveyorDemo'})
            elif action=='stop':self.endpoint.stop()
            else:
                self.client.close();deadline=time.monotonic()+2
                while self.description()['open'] and time.monotonic()<deadline:time.sleep(.01)
            state=self.endpoint.programming_lease.transport.description()
            self.assertEqual(state['received_bytes'],0);self.assertFalse(state['buffer_allocated'])
            if action in ('reset','reload','disconnect'):
                self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()


if __name__=='__main__':unittest.main()
