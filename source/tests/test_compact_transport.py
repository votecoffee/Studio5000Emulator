"""Whole-device containers retain bounded bytes without accepting execution."""
import copy
from dataclasses import replace
import hmac
import json
import struct
import unittest
from logixlab import signed_messages as sm
from logixlab.resilient_transport import ResilientTransport,TransportError,DEVICE_HEADER,ASSEMBLY_SECONDS
from tools.inspect_cip_capture import describe
from tools.analyze_native_transfer import analyze
import test_transport_fragments as fragments
import test_resilient_transport as transport
import test_programming_preparation as prep
from test_signed_messages import KEY

DATA=b'private-device-data'


def message(data=DATA,sequence=7):
    return fragments.message(0x301,len(data),DEVICE_HEADER+data,sequence)


class CompactCodecTests(unittest.TestCase):
    def test_count_excludes_device_header_and_ack_is_empty_signed_storage_confirmation(self):
        raw=message();request=sm.verify_request(raw,KEY,expected_sequence=7)
        self.assertIsInstance(request,sm.CompactTransferEnvelope)
        self.assertEqual((request.fragment,request.position),(DEVICE_HEADER+DATA,len(DATA)))
        answer=sm.encode_fragment_ack(request,KEY)
        self.assertEqual(len(answer),36);self.assertEqual(answer[:16],bytes.fromhex('b9000000010300000000000007000000'))
        self.assertEqual(sm.verify_response(answer,KEY,request=request),sm.FragmentAck(0x39,7))
        self.assertNotIn('key',vars(request))
        description=describe(raw)
        self.assertTrue(description['signed_envelope']['compact_device_transfer'])
        self.assertNotIn(DATA.decode(),json.dumps(description))

    def test_mac_counter_and_every_changed_byte_are_still_verified(self):
        raw=message();request=sm.parse_request(raw);answer=sm.encode_fragment_ack(request,KEY)
        for original,verify in ((raw,lambda q:sm.verify_request(q,KEY,expected_sequence=7)),
                (answer,lambda a:sm.verify_response(a,KEY,request=request))):
            for i in range(len(original)):
                changed=original[:i]+bytes((original[i]^1,))+original[i+1:]
                with self.subTest(at=i),self.assertRaises(sm.EnvelopeError):verify(changed)
        with self.assertRaises(sm.EnvelopeError):sm.verify_request(raw,KEY[::-1],expected_sequence=7)
        with self.assertRaises(sm.EnvelopeError):sm.verify_request(raw,KEY,expected_sequence=8)

    def test_invalid_headers_counts_context_and_lengths_never_become_compact_frames(self):
        raw=message()
        for offset,value in ((6,0x302),(10,0),(10,len(DATA)-1),(10,len(DATA)+16),(10,0xffffffff)):
            bad=bytearray(raw);struct.pack_into('<I',bad,offset,value)
            with self.assertRaises(sm.EnvelopeError):sm.parse_request(bytes(bad))
        for size in range(len(raw)):
            with self.assertRaises(sm.EnvelopeError):sm.parse_request(raw[:size])
        for i in range(len(DEVICE_HEADER)):
            bad=bytearray(raw);bad[14+i]^=1
            with self.assertRaises(sm.EnvelopeError):sm.parse_request(bytes(bad))
        parsed=sm.parse_request(raw)
        for fields in ({'position':True},{'sequence':True},{'position':len(DATA)+1},
                       {'fragment':bytearray(parsed.fragment)},{'container_format':0x101}):
            with self.assertRaises(sm.EnvelopeError):sm.encode_fragment_ack(replace(parsed,**fields),KEY)
        for control in sm.TRANSFER_CONTROLS:
            legacy=fragments.message(0x301,control,DEVICE_HEADER+DATA,7)
            self.assertIsInstance(sm.parse_request(legacy),sm.TransferEnvelope)

    def test_offline_transfer_analysis_counts_complete_storage_without_payload_or_acceptance_claims(self):
        raw=message();answer=sm.encode_fragment_ack(sm.parse_request(raw),KEY)
        event=dict(kind='cip',time=1,request_hex=raw.hex(),response_hex=answer.hex())
        report=analyze({'events':[]},{'events':[event]},'download')
        self.assertTrue(report['analysis_complete']);self.assertEqual(report['compact_device_transfers'],1)
        self.assertEqual(report['fragment_acknowledgements'],1)
        self.assertEqual(report['mac_verification'],'NOT PERFORMED')
        self.assertNotIn(DATA.decode(),json.dumps(report));self.assertEqual(report['failure_cause'],'NOT INFERRED')


class CompactStorageTests(unittest.TestCase):
    def test_complete_payload_has_exact_readback_capacity_timeout_and_no_execution(self):
        now=[1.0];stage=ResilientTransport(clock=lambda:now[0]);stage.open(transport.payload(len(DATA)))
        stage.accept(sm.parse_request(message()))
        self.assertEqual(bytes(stage._data),DATA)
        self.assertEqual((stage.total_bytes,stage.fragments,stage.complete),(len(DATA),1,True))
        self.assertFalse(stage.description()['commit'] or stage.description()['payload_transfer'])
        now[0]+=ASSEMBLY_SECONDS;self.assertFalse(stage.description()['complete'])
        self.assertTrue(stage.description()['open']);self.assertEqual(stage.description()['received_bytes'],0)

    def test_missing_setup_conflicts_overflow_and_forged_shapes_clear_only_temporary_data(self):
        complete=sm.parse_request(message())
        stage=ResilientTransport()
        with self.assertRaises(TransportError):stage.accept(complete)
        stage.open(transport.payload(len(DATA)-1))
        with self.assertRaises(TransportError):stage.accept(complete)
        self.assertEqual(stage.description()['received_bytes'],0)
        stage.clear();stage.open(transport.payload())
        for pending in (complete,fragments.part(0x101,30,DEVICE_HEADER+b'AB')):
            stage.accept(pending)
            with self.assertRaises(TransportError):stage.accept(complete)
            self.assertEqual(stage.description()['received_bytes'],0)
        with self.assertRaises(TransportError):stage.accept(replace(complete,position=len(DATA)+1))
        self.assertTrue(stage.description()['open'])


class CompactSignedTests(unittest.TestCase):
    setUp=fragments.FragmentSignedTests.setUp
    tearDown=fragments.FragmentSignedTests.tearDown
    cip=fragments.FragmentSignedTests.cip
    begin=fragments.FragmentSignedTests.begin
    signed=fragments.FragmentSignedTests.signed
    bind=fragments.FragmentSignedTests.bind
    prepare=fragments.FragmentSignedTests.prepare
    second_client=fragments.FragmentSignedTests.second_client
    send=fragments.FragmentSignedTests.send
    acquire=fragments.FragmentSignedTests.acquire
    ready=fragments.FragmentSignedTests.ready
    description=fragments.FragmentSignedTests.description
    stage=fragments.FragmentSignedTests.stage

    def transfer(self):
        raw=message(sequence=self.sequence);self.sequence+=1
        answer=self.cip(raw)
        self.assertEqual(sm.verify_response(answer,KEY,request=sm.parse_request(raw)).sequence,self.sequence-1)
        return raw

    def test_prepared_owner_stores_complete_bytes_then_normal_cleanup_stays_live(self):
        self.stage();before=copy.deepcopy(self.app.engine.memory.values);self.transfer()
        self.assertTrue(self.description()['complete'])
        self.assertEqual(bytes(self.endpoint.programming_lease.transport._data),DATA)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertEqual(self.send(prep.END)[2],0);self.assertFalse(self.description()['open'])

    def test_preparation_setup_source_ownership_replay_and_bad_mac_are_enforced(self):
        self.prepare();self.assertEqual(self.cip(message(sequence=4))[2],15)
        self.client.close();self.client=transport.leases.Client(self.endpoint.port);self.client.register();self.stage()
        identity=self.app.native_project_identity;self.app.native_project_identity=None
        raw=message(sequence=self.sequence);self.sequence+=1;self.assertEqual(self.cip(raw)[2],12)
        self.app.native_project_identity=identity
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.cip(message(sequence=4))[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(self.description()['received_bytes'],0)
        raw=self.transfer();self.assertEqual(self.cip(raw)[2],15)
        self.assertFalse(self.description()['open'])
        self.client.close();self.client=transport.leases.Client(self.endpoint.port);self.client.register();self.stage()
        raw=message(sequence=self.sequence);bad=raw[:-1]+bytes((raw[-1]^1,))
        self.assertEqual(self.cip(bad)[2],15);self.assertFalse(self.description()['open'])


if __name__=='__main__':unittest.main()
