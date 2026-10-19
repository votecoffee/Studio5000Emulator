"""Synthetic batch framing; no captured bytes or native batch MAC claims."""
import copy
import struct
import tempfile
import unittest

from logixlab import signed_messages as signed
from logixlab.ethernetip import Endpoint, Session
from logixlab.server import Application


CHILDREN = (bytes.fromhex('0e03200124013001'), bytes.fromhex('4c02206b24010100'))
REPLIES = (bytes.fromhex('8e00000001'), bytes.fromhex('cc0006013412'))
# Hand-authored offset tables: request offsets 6/14; reply offsets 6/11.
REQUEST = bytes.fromhex('380220022401020006000e000e032001240130014c02206b2401010007000000') + b'\xCC'*20
RESPONSE = bytes.fromhex('b8001e00020006000b008e00000001cc000601341207000000') + b'\xDD'*20


def batch(children, *, response=False, sequence=7, status=0):
    offset = 2 + 2 * len(children)
    offsets = []
    for child in children:
        offsets.append(offset)
        offset += len(child)
    body = struct.pack('<H', len(children)) + b''.join(struct.pack('<H', n) for n in offsets)
    header = bytes((0xB8, 0, status, 0)) if response else b'\x38\x02' + signed.ROUTER_PATH
    return header + body + b''.join(children) + struct.pack('<I', sequence) + b'\xCC'*20


class SignedBatchTests(unittest.TestCase):
    def test_hand_authored_request_and_mixed_status_reply_keep_child_order(self):
        request = signed.parse_request(REQUEST)
        self.assertEqual(request, signed.BatchEnvelope(0x38, 7, CHILDREN))
        self.assertEqual(batch(CHILDREN), REQUEST)
        reply = signed.parse_response(RESPONSE, request)
        self.assertEqual(reply, signed.BatchEnvelope(0x38, 7, REPLIES, 0x1E))
        self.assertEqual(reply.children[0][-1:], b'\x01')
        self.assertEqual(reply.children[1][2], 6)
        self.assertNotIn('key', vars(reply))
        self.assertNotIn('verified', vars(reply))

    def test_bad_counts_offsets_and_truncated_tables_are_rejected(self):
        variants = []
        # Offsets cannot point into the table, skip initial bytes, repeat,
        # reverse order, or leave the final child outside the body.
        for at, value in ((6, 0), (6, 257), (6, 65535), (8, 4), (8, 7),
                          (10, 6), (10, 5), (10, 22), (10, 65535)):
            damaged = bytearray(REQUEST)
            struct.pack_into('<H', damaged, at, value)
            variants.append(bytes(damaged))
        variants += [REQUEST[:6] + body + REQUEST[-24:] for body in
                     (b'', b'\x01', b'\x02\0', b'\x02\0\x06\0', b'\x01\0\x04\0')]
        for raw in variants:
            with self.subTest(raw=raw[:12].hex()):
                with self.assertRaises(signed.EnvelopeError): signed.parse_request(raw)

    def test_every_child_header_is_validated_before_returning_the_batch(self):
        for child in (b'', b'\x0E', b'\x8E\0\0\0', b'\x0E\xFF\0\0'):
            with self.assertRaises(signed.EnvelopeError): signed.parse_request(batch((CHILDREN[0], child)))
        request = signed.parse_request(REQUEST)
        for child in (b'', b'\xCC\0\0', b'\xCD\0\0\0', b'\xCC\1\0\0', b'\xCC\0\0\1'):
            with self.assertRaises(signed.EnvelopeError):
                signed.parse_response(batch((REPLIES[0], child), response=True), request)

    def test_reply_count_services_and_counters_must_match(self):
        request = signed.parse_request(REQUEST)
        variants = [batch(REPLIES[:1], response=True), batch(REPLIES + REPLIES[:1], response=True),
                    batch(REPLIES[::-1], response=True), batch(REPLIES, response=True, sequence=8)]
        for at, value in ((0, 0xB7), (1, 1), (2, 8), (3, 1), (4, 0), (6, 4), (8, 6), (8, 65535)):
            damaged = bytearray(RESPONSE)
            if at >= 4:
                struct.pack_into('<H', damaged, at, value)
            else:
                damaged[at] = value
            variants.append(bytes(damaged))
        for raw in variants:
            with self.assertRaises(signed.EnvelopeError): signed.parse_response(raw, request)

    def test_success_and_partial_failure_statuses_and_odd_lengths_are_retained(self):
        request = signed.parse_request(REQUEST)
        for status in (0, 0x1E):
            raw = batch(REPLIES, response=True, status=status)
            result = signed.parse_response(raw, request)
            self.assertEqual(result.status, status)
            self.assertEqual(result.children, REPLIES)
        for counter in (0, 0xFFFFFFFF):
            context = signed.parse_request(batch(CHILDREN, sequence=counter))
            result = signed.parse_response(batch(REPLIES, response=True, sequence=counter), context)
            self.assertEqual(result.sequence, counter)

    def test_child_count_and_message_size_have_independent_limits(self):
        children = (b'\x0E\0',) * signed.MAX_BATCH_CHILDREN
        request = signed.parse_request(batch(children))
        self.assertEqual(len(request.children), 256)
        reply = batch((b'\x8E\0\0\0',)*256, response=True)
        self.assertEqual(len(signed.parse_response(reply, request).children), 256)
        with self.assertRaises(signed.EnvelopeError): signed.parse_request(batch(children + children[:1]))
        large_child = b'\x0E\0' + b'\0' * (signed.MAX_MESSAGE - 34 - 2)
        raw = batch((large_child,))
        self.assertEqual(len(raw), signed.MAX_MESSAGE)
        self.assertEqual(signed.parse_request(raw).children, (large_child,))
        with self.assertRaises(signed.EnvelopeError): signed.parse_request(batch((large_child + b'\0',)))
        small_request = signed.parse_request(batch((b'\x0E\0',)))
        large_reply = b'\x8E\0\0\0' + b'\0' * (signed.MAX_MESSAGE - 32 - 4)
        raw = batch((large_reply,), response=True)
        self.assertEqual(len(raw), signed.MAX_MESSAGE)
        self.assertEqual(signed.parse_response(raw, small_request).children, (large_reply,))
        with self.assertRaises(signed.EnvelopeError):
            signed.parse_response(batch((large_reply + b'\0',), response=True), small_request)

    def test_forged_request_contexts_and_mutable_input_are_rejected(self):
        contexts = [None, signed.BatchEnvelope(0x38, True, CHILDREN),
                    signed.BatchEnvelope(0x38, -1, CHILDREN), signed.BatchEnvelope(0x38, 1 << 32, CHILDREN),
                    signed.BatchEnvelope(0x37, 7, CHILDREN), signed.BatchEnvelope(0x38, 7, list(CHILDREN)),
                    signed.BatchEnvelope(0x38, 7, ()), signed.BatchEnvelope(0x38, 7, CHILDREN, 0),
                    signed.BatchEnvelope(0x38, 7, (bytearray(CHILDREN[0]),)),
                    signed.BatchEnvelope(0x38, 7, (b'\x0E\0' + b'\0'*signed.MAX_MESSAGE,)),
                    signed.BatchEnvelope(0x38, 7, (b'\x0E\0',)*257)]
        for context in contexts:
            with self.assertRaises(signed.EnvelopeError): signed.parse_response(RESPONSE, context)
        with self.assertRaises(signed.EnvelopeError): signed.parse_request(bytearray(REQUEST))
        with self.assertRaises(signed.EnvelopeError):
            signed.parse_response(bytearray(RESPONSE), signed.parse_request(REQUEST))

    def test_batch_authentication_and_encoding_remain_unavailable(self):
        key = bytes(range(20))
        request = signed.parse_request(REQUEST)
        with self.assertRaisesRegex(signed.EnvelopeError, 'Batch MAC verification is unsupported'):
            signed.verify_request(REQUEST, key, expected_sequence=7)
        with self.assertRaisesRegex(signed.EnvelopeError, 'Batch MAC verification is unsupported'):
            signed.verify_response(RESPONSE, key, request=request)
        with self.assertRaises(signed.EnvelopeError): signed.encode_response(request, REPLIES[0], key)

    def test_nested_batches_are_kept_as_opaque_child_bytes(self):
        request = signed.parse_request(batch((REQUEST,)))
        self.assertEqual(request.children, (REQUEST,))

    def test_batch_codec_does_not_enable_dispatch_or_change_model_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Application(folder)
            app.command('demo', {'sample': 'ConveyorDemo'})
            endpoint = Endpoint(app, 0, False)
            session = Session(handle=1, generation=app.generation)
            before = copy.deepcopy(app.engine.memory.values)
            try:
                signed.parse_request(REQUEST)
                self.assertEqual(endpoint.router.handle(REQUEST, session), b'\xB8\0\x08\0')
                self.assertEqual(app.engine.memory.values, before)
                self.assertEqual(set(vars(session)), {'handle', 'generation', 'connections', 'peer'})
            finally:
                app.close()


if __name__ == '__main__':
    unittest.main()
