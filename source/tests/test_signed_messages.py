"""Synthetic signed envelopes; no captured operator identity or vendor key."""
import copy
import hmac
import struct
import tempfile
import unittest

from logixlab import signed_messages as signed
from logixlab.ethernetip import Endpoint, Session
from logixlab.server import Application


KEY = bytes(range(1, 21))
INNER = bytes.fromhex('0e03200124013001')
# Independent PyCryptodome HMAC-SHA1 output, using the synthetic KEY above.
VECTORS = (
    ('3602200224010e0320012401300107000000', 'c58474124e827d7fac613bc395ec44ac44c5a935'),
    ('37022002240101030000080000000e0320012401300107000000', '2bd7d54d049c741ddeb0401f066e0730259e60e4'),
)
REPLY_VECTORS = (
    ('b60000008e000f0007000000', '9cfdcd6e12719537d2e7b293e19afd1b8a1877b5'),
    ('b700000001030000040000008e000f0007000000', 'e193213d5f2afe97c14761a6de1edbd1a69ad1c8'),
)


def request(service=0x36, inner=INNER, sequence=7):
    body = inner if service == 0x36 else struct.pack('<II', 0x301, len(inner)) + inner
    raw = bytes((service, 2)) + signed.ROUTER_PATH + body + struct.pack('<I', sequence)
    return raw + hmac.digest(KEY, raw, 'sha1')


def response(service=0x36, inner=b'\x8E\0\0\0\1\0', sequence=7):
    body = inner if service == 0x36 else struct.pack('<II', 0x301, len(inner)) + inner
    # Intentionally invalid: structural decoding must not assert authenticity.
    return bytes((service | 0x80, 0, 0, 0)) + body + struct.pack('<I', sequence) + b'\xCC'*20


class SignedMessageTests(unittest.TestCase):
    def test_independent_reply_vectors_preserve_authenticated_embedded_errors(self):
        for service, (body, mac) in zip((0x36, 0x37), REPLY_VECTORS):
            context = signed.parse_request(request(service))
            raw = bytes.fromhex(body+mac)
            self.assertEqual(signed.encode_response(context, b'\x8E\0\x0F\0', KEY), raw)
            parsed = signed.verify_response(raw, KEY, request=context)
            self.assertEqual(parsed.inner, b'\x8E\0\x0F\0')
            self.assertEqual(parsed.sequence, 7)
            self.assertNotIn('key', vars(parsed))
            self.assertNotIn('key', vars(context))

    def test_every_altered_reply_byte_fails_authentication_or_framing(self):
        for service, (body, mac) in zip((0x36, 0x37), REPLY_VECTORS):
            context = signed.parse_request(request(service))
            original = bytes.fromhex(body+mac)
            for position in range(len(original)):
                damaged = bytearray(original); damaged[position] ^= 1
                with self.subTest(service=service, position=position):
                    with self.assertRaises(signed.EnvelopeError):
                        signed.verify_response(bytes(damaged), KEY, request=context)

    def test_reply_verification_requires_key_service_and_request_counter(self):
        context = signed.parse_request(request())
        raw = bytes.fromhex(''.join(REPLY_VECTORS[0]))
        for key in (KEY[::-1], None, KEY[:-1], bytearray(KEY)):
            with self.assertRaises(signed.EnvelopeError): signed.verify_response(raw, key, request=context)
        contexts = (signed.parse_request(request(0x37)), signed.parse_request(request(sequence=8)),
                    signed.parse_request(request(inner=b'\x01\0')), None,
                    signed.Envelope(0x36,7,'bad'), signed.Envelope(0x36,True,INNER),
                    signed.Envelope(0x37,7,INNER,0x302))
        for invalid in contexts:
            with self.assertRaises(signed.EnvelopeError): signed.verify_response(raw, KEY, request=invalid)
        # An unverified parse still accepts structure, including a wrong MAC.
        opaque = response()
        self.assertEqual(signed.parse_response(opaque, context).sequence, 7)
        with self.assertRaisesRegex(signed.EnvelopeError, 'MAC'):
            signed.verify_response(opaque, KEY, request=context)

    def test_reply_encoder_rejects_malformed_inner_headers_and_contexts(self):
        for service in (0x36, 0x37):
            context = signed.parse_request(request(service))
            for inner in (None, b'', b'\x8E\0\0', b'\x8F\0\0\0',
                          b'\x8E\1\0\0', b'\x8E\0\0\1', bytearray(b'\x8E\0\0\0')):
                with self.assertRaises(signed.EnvelopeError): signed.encode_response(context, inner, KEY)
            with self.assertRaises(signed.EnvelopeError):
                signed.encode_response(context, b'\x8E\0\0\0', b'')
        for context in (None, signed.Envelope(0x36,-1,INNER), signed.Envelope(0x36,7,b''),
                        signed.Envelope(0x36,7,INNER,0x301)):
            with self.assertRaises(signed.EnvelopeError): signed.encode_response(context, b'\x8E\0\0\0', KEY)

    def test_reply_bounds_additional_status_and_counter_extremes(self):
        for service in (0x36, 0x37):
            for counter in (0, 0xFFFFFFFF):
                context = signed.parse_request(request(service, sequence=counter))
                inner = b'\x8E\0\x14\1\x34\x12'
                raw = signed.encode_response(context, inner, KEY)
                self.assertEqual(signed.verify_response(raw, KEY, request=context).inner, inner)
            overhead = 28 + (8 if service == 0x37 else 0)
            context = signed.parse_request(request(service))
            inner = b'\x8E\0\0\0' + b'\0'*(signed.MAX_MESSAGE-overhead-4)
            raw = signed.encode_response(context, inner, KEY)
            self.assertEqual(len(raw), signed.MAX_MESSAGE)
            self.assertEqual(signed.verify_response(raw, KEY, request=context).inner, inner)
            with self.assertRaises(signed.EnvelopeError): signed.encode_response(context, inner+b'\0', KEY)

    def test_independent_vectors_cover_outer_header_container_and_counter(self):
        for body, mac in VECTORS:
            raw = bytes.fromhex(body + mac)
            parsed = signed.verify_request(raw, KEY, expected_sequence=7)
            self.assertEqual(parsed.inner, INNER)
            self.assertEqual(parsed.sequence, 7)
            self.assertEqual(parsed.container_format, 0x301 if parsed.service == 0x37 else None)
            self.assertEqual(raw, request(parsed.service))

    def test_every_changed_byte_fails_verification(self):
        for body, mac in VECTORS:
            original = bytes.fromhex(body + mac)
            for position in range(len(original)):
                raw = bytearray(original); raw[position] ^= 1
                with self.subTest(service=original[0], position=position):
                    with self.assertRaises(signed.EnvelopeError):
                        signed.verify_request(bytes(raw), KEY, expected_sequence=7)

    def test_wrong_key_and_replay_counter_are_rejected_without_state(self):
        raw = request()
        with self.assertRaisesRegex(signed.EnvelopeError, 'MAC'):
            signed.verify_request(raw, KEY[::-1], expected_sequence=7)
        for counter in (0, 6, 8, 0xFFFFFFFF):
            with self.assertRaisesRegex(signed.EnvelopeError, 'sequence'):
                signed.verify_request(raw, KEY, expected_sequence=counter)
        # The caller advances its expected sequence; this pure codec has no
        # hidden state and cannot itself confer replay protection on a session.
        self.assertEqual(signed.verify_request(raw, KEY, expected_sequence=7).inner, INNER)

    def test_key_and_sequence_argument_bounds(self):
        for key in (None, '', b'', KEY[:-1], KEY+b'\0', bytearray(KEY)):
            with self.assertRaises(signed.EnvelopeError):
                signed.verify_request(request(), key, expected_sequence=7)
        for counter in (None, True, -1, 1 << 32, '7'):
            with self.assertRaises(signed.EnvelopeError):
                signed.verify_request(request(), KEY, expected_sequence=counter)
        for counter in (0, 0xFFFFFFFF):
            self.assertEqual(signed.verify_request(request(sequence=counter), KEY,
                                                  expected_sequence=counter).sequence, counter)

    def test_malformed_outer_paths_unsupported_services_and_sizes(self):
        raw = request()
        variants = [b'', bytearray(raw), raw[:27], b'\0'*(signed.MAX_MESSAGE+1)]
        for position, value in ((0, 0x38), (0, 0xB6), (1, 3), (3, 3), (5, 2)):
            damaged = bytearray(raw); damaged[position] = value; variants.append(bytes(damaged))
        for damaged in variants:
            with self.assertRaises(signed.EnvelopeError): signed.parse_request(damaged)

    def test_container_version_and_exact_length_are_required(self):
        raw = request(0x37)
        for offset, value in ((6, 0x302), (10, 0), (10, len(INNER)-1), (10, 0xFFFFFFFF)):
            damaged = bytearray(raw); struct.pack_into('<I', damaged, offset, value)
            with self.assertRaises(signed.EnvelopeError): signed.parse_request(bytes(damaged))
        for inner in (b'', b'\x0E', b'\x8E\0\0\0', b'\x0E\xFF\0\0'):
            for service in (0x36, 0x37):
                with self.assertRaises(signed.EnvelopeError): signed.parse_request(request(service, inner))

    def test_responses_expose_structure_without_claiming_mac_verification(self):
        for service in (0x36, 0x37):
            parsed = signed.parse_request(request(service))
            inner = b'\x8E\0\x14\1\x34\x12'
            result = signed.parse_response(response(service, inner), parsed)
            self.assertEqual(result.inner, inner)
            self.assertEqual(result.sequence, 7)
            # No verification flag or key is returned or retained.
            self.assertEqual(set(vars(result)), {'service','sequence','inner','container_format'})

    def test_response_pairing_headers_additional_status_and_counters(self):
        parsed = signed.parse_request(request())
        variants = [response(0x37), response(sequence=8), response(inner=b'\x8E\0\0'),
                    response(inner=b'\x8F\0\0\0'), response(inner=b'\x8E\1\0\0'),
                    response(inner=b'\x8E\0\0\1'), b'\xB6\0\x08\0',
                    b'\xB6\0\x08\0'+response()[4:]]
        for raw in variants:
            with self.assertRaises(signed.EnvelopeError): signed.parse_response(raw, parsed)
        for invalid in (None, signed.Envelope(0x38,7,INNER), signed.Envelope(0x36,7,b'')):
            with self.assertRaises(signed.EnvelopeError): signed.parse_response(response(), invalid)

    def test_codec_does_not_enable_live_dispatch_or_change_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Application(folder); app.command('demo', {'sample': 'ConveyorDemo'})
            endpoint = Endpoint(app, 0, False)
            session = Session(handle=1, generation=app.generation)
            before = copy.deepcopy(app.engine.memory.values)
            try:
                for service in (0x36, 0x37):
                    raw = request(service)
                    signed.verify_request(raw, KEY, expected_sequence=7)
                    self.assertEqual(endpoint.router.handle(raw, session), bytes((service | 0x80,0,8,0)))
                self.assertEqual(app.engine.memory.values, before)
                self.assertEqual(set(vars(session)), {'handle','generation','connections','peer'})
            finally: app.close()


if __name__ == '__main__': unittest.main()
