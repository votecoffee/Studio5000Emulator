"""Synthetic 0x39 vectors and live policy; no library-data writes are enabled."""
import copy
import hmac
import json
import struct
import unittest

from logixlab import signed_messages as signed
from tools.inspect_cip_capture import summarize
import test_capture_inspection as captures
import test_programming_lease as leases
from test_signed_messages import KEY

INNER=bytes.fromhex('4d0321007d03240102000000020000000100000000')
# Independent OpenSSL HMAC-SHA1 output with the public synthetic KEY.
REQUEST=bytes.fromhex('39022002240101030000010000004d0321007d0324010200000002000000010000000007000000d41e999727e85bf11ee4135a433b875dcf71609a')
RESPONSE=bytes.fromhex('b90000000103000001000000cd000f0007000000e1116bfc71291fcc270e94dfaa473e7180f7d3a2')


def request(inner=INNER,sequence=7):
    raw=bytes.fromhex('3902200224010103000001000000')+inner+struct.pack('<I',sequence)
    return raw+hmac.digest(KEY,raw,'sha1')


def controlled_request(inner=INNER,sequence=7,control=8):
    raw=bytes.fromhex('390220022401')+struct.pack('<II',0x301,control)+inner+struct.pack('<I',sequence)
    return raw+hmac.digest(KEY,raw,'sha1')


class TransferCodecTests(unittest.TestCase):
    def test_control_eight_preserves_inner_counter_and_exact_response_pairing(self):
        original=controlled_request()
        context=signed.verify_request(original,KEY,expected_sequence=7)
        self.assertEqual((context.container_control,context.inner),(8,INNER))
        answer=signed.encode_response(context,b'\xCD\0\x0F\0',KEY)
        result=signed.verify_response(answer,KEY,request=context)
        self.assertEqual((result.container_control,result.inner),(8,b'\xCD\0\x0F\0'))
        with self.assertRaises(signed.EnvelopeError):signed.parse_response(answer,signed.parse_request(REQUEST))
        for offset in range(len(original)):
            damaged=bytearray(original);damaged[offset]^=1
            with self.assertRaises(signed.EnvelopeError):signed.verify_request(bytes(damaged),KEY,expected_sequence=7)
        with self.assertRaises(signed.EnvelopeError):signed.verify_request(original,KEY,expected_sequence=8)
        for control in (0,2,7,9,0xFFFFFFFF):
            with self.assertRaises(signed.EnvelopeError):signed.parse_request(controlled_request(control=control))

    def test_independent_vectors_preserve_denial_and_control_without_retaining_key(self):
        self.assertEqual(request(),REQUEST)
        parsed=signed.verify_request(REQUEST,KEY,expected_sequence=7)
        self.assertIsInstance(parsed,signed.TransferEnvelope)
        self.assertEqual((parsed.inner,parsed.container_format,parsed.container_control),(INNER,0x301,1))
        self.assertEqual(signed.encode_response(parsed,b'\xCD\0\x0F\0',KEY),RESPONSE)
        decoded=signed.verify_response(RESPONSE,KEY,request=parsed)
        self.assertEqual((decoded.sequence,decoded.inner,decoded.container_control),(7,b'\xCD\0\x0F\0',1))
        self.assertNotIn('key',vars(decoded));self.assertNotIn('verified',vars(parsed))

    def test_each_changed_request_and_response_byte_fails_framing_or_mac(self):
        parsed=signed.parse_request(REQUEST)
        for raw,verify in ((REQUEST,lambda v:signed.verify_request(v,KEY,expected_sequence=7)),
                           (RESPONSE,lambda v:signed.verify_response(v,KEY,request=parsed))):
            for i in range(len(raw)):
                damaged=bytearray(raw);damaged[i]^=1
                with self.subTest(size=len(raw),at=i),self.assertRaises(signed.EnvelopeError):verify(bytes(damaged))
        opaque=REQUEST[:-20]+bytes(20)
        self.assertEqual(signed.parse_request(opaque).inner,INNER)
        with self.assertRaises(signed.EnvelopeError):signed.verify_request(opaque,KEY,expected_sequence=7)

    def test_unsupported_controls_lengths_paths_and_nested_replies_are_rejected(self):
        for at,value in ((6,0x302),(10,0),(10,2),(10,0xFFFFFFFF)):
            raw=bytearray(REQUEST);struct.pack_into('<I',raw,at,value)
            with self.subTest(at=at,value=value),self.assertRaises(signed.EnvelopeError):signed.parse_request(bytes(raw))
        for inner in (b'',b'\x4D',b'\xCD\0\0\0',b'\x4D\xFF'):
            with self.assertRaises(signed.EnvelopeError):signed.parse_request(request(inner))
        parsed=signed.parse_request(REQUEST)
        for context in (signed.Envelope(0x39,7,INNER,0x301),signed.TransferEnvelope(0x36,7,INNER),
                signed.TransferEnvelope(0x39,7,INNER,0x301,True),signed.TransferEnvelope(0x39,7,INNER,0x301,2)):
            with self.assertRaises(signed.EnvelopeError):signed.encode_response(context,b'\xCD\0\0\0',KEY)
        with self.assertRaises(signed.EnvelopeError):signed.encode_response(parsed,b'\xCC\0\0\0',KEY)
        with self.assertRaises(signed.EnvelopeError):signed.parse_request(REQUEST+bytes(signed.MAX_MESSAGE))

    def test_counter_key_and_full_response_budget_are_checked(self):
        for seq in (0,0xFFFFFFFF):
            parsed=signed.verify_request(request(sequence=seq),KEY,expected_sequence=seq)
            inner=b'\xCD\0\0\0'+bytes(signed.MAX_MESSAGE-40)
            raw=signed.encode_response(parsed,inner,KEY)
            self.assertEqual(len(raw),signed.MAX_MESSAGE)
            self.assertEqual(signed.verify_response(raw,KEY,request=parsed).inner,inner)
            with self.assertRaises(signed.EnvelopeError):signed.encode_response(parsed,inner+b'x',KEY)
        for key,seq in ((KEY[::-1],7),(KEY,6),(KEY,8)):
            with self.assertRaises(signed.EnvelopeError):signed.verify_request(REQUEST,key,expected_sequence=seq)

    def test_capture_pair_exposes_structural_transfer_fields_with_private_payloads(self):
        report=summarize([captures.packet(1,REQUEST),captures.packet(2,RESPONSE,1)])
        pair,=report['exchanges']
        for message in (pair['request'],pair['response']):
            envelope=message['signed_envelope']
            self.assertEqual(envelope['integrity'],'NOT VERIFIED')
            self.assertEqual(envelope['container_control'],1)
            self.assertEqual(envelope['inner']['service'],0x4D)
            self.assertNotIn('message_hex',envelope['inner'])
        self.assertEqual(pair['response']['signed_envelope']['inner']['status'],15)
        self.assertNotIn(REQUEST.hex(),json.dumps(report))
        malformed=bytearray(REQUEST);malformed[10]=2
        report=summarize([captures.packet(1,bytes(malformed))])
        self.assertEqual(report['unpaired_requests'][0]['signed_envelope']['structure'],'UNSUPPORTED OR MALFORMED')


class TransferPolicyTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def transfer(self,inner,sequence):
        raw=request(inner,sequence)
        return signed.verify_response(self.cip(raw),KEY,request=signed.parse_request(raw)).inner

    def test_control_eight_denies_unknown_write_without_invalidating_context_or_changing_model(self):
        self.prepare();before=copy.deepcopy(self.app.state())
        raw=controlled_request(bytes.fromhex('5c0420682401206d2401')+struct.pack('<5I',2,5,0,1,123),4)
        result=signed.verify_response(self.cip(raw),KEY,request=signed.parse_request(raw))
        self.assertEqual((result.container_control,result.inner),(8,b'\xDC\0\x0F\0'))
        self.assertEqual(self.signed(5,bytes.fromhex('0e03208e24013007')),b'\x8E\0\0\0\0\0')
        for field in ('routines','tags','scan','controller'):self.assertEqual(self.app.state()[field],before[field])

    def test_bound_policy_preserves_memory_and_shares_counter_with_other_envelopes(self):
        self.prepare();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.transfer(INNER,4),b'\xCD\0\x0F\0')
        self.assertEqual(self.transfer(bytes.fromhex('0e03200124013001'),5),b'\x8E\0\0\0\1\0')
        self.assertEqual(self.signed(6,bytes.fromhex('0e03208e24013007')),b'\x8E\0\0\0\0\0')
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.cip(request(INNER,4))[2],15)

    def test_unbound_invalid_mac_and_disabled_endpoint_never_dispatch(self):
        self.begin()
        self.assertEqual(self.transfer(b'\x5C\2\x20\x8E\x24\1operator',1)[2],15)
        self.assertEqual(self.signed(2,b'\x5C\2\x20\x8E\x24\1operator')[2],0)
        raw=request(INNER,3);self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
        self.assertEqual(self.cip(request(INNER,4))[2],15)
        self.endpoint.native_read_only=False
        self.assertEqual(self.cip(request(INNER,1))[2],8)


if __name__=='__main__':unittest.main()
