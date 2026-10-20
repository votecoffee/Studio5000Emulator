"""Negotiated Class 3 sizes must cover replies, sequence words and signed data."""
import copy
import hmac
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab import native_session, signed_messages
from logixlab.ethernetip import Endpoint
from logixlab.model import Tag
from logixlab.server import Application
from test_ethernetip import Client, fo, request as tag_request
from test_key_exchange import offer
from test_signed_batches import batch
from test_signed_messages import KEY, request as signed_request


class ConnectedSizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'TextLab'})
        self.payload = bytes(i % 127 for i in range(4096))
        for name, dtype, value in (('Blob', 'SINT', list(self.payload)), ('DescriptorPayload', 'DINT', 42)):
            tag = Tag(name, dtype, value)
            self.app.engine.project.tags[tag.key.lower()] = tag
            self.app.engine.project.initial[tag.key.lower()] = copy.deepcopy(value)
            self.app.engine.memory.values[tag.key.lower()] = copy.deepcopy(value)
        self.endpoint = Endpoint(self.app, 0).start()
        self.app.endpoint = self.endpoint
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.app.close()
        self.tmp.cleanup()

    def client(self):
        client = Client(self.endpoint.port); client.register(); self.clients.append(client)
        return client

    def cip(self, client, raw, connection=None, sequence=0):
        status, result = client.cip(raw, connection, sequence)
        self.assertEqual(status, 0)
        return result

    def open(self, client, *, large=False, incoming=None, outgoing=None, serial=0x3123):
        raw = bytearray(fo(large, serial=serial))
        for offset, size in ((26, incoming), (34 if large else 32, outgoing)):
            if size is not None:
                struct.pack_into('<I' if large else '<H', raw, 6+offset,
                                 (0x42000000 if large else 0x4200) | size)
        result = self.cip(client, bytes(raw))
        self.assertEqual(result[2], 0)
        return struct.unpack_from('<I', result, 4)[0]

    def read(self, client, count, connection=None, sequence=0, offset=None):
        data = struct.pack('<H', count) if offset is None else struct.pack('<HI', count, offset)
        return self.cip(client, tag_request(0x4C if offset is None else 0x52, 'Blob', data), connection, sequence)

    def test_standard_connection_uses_its_full_budget_and_fragments_one_byte_above(self):
        client = self.client(); connection = self.open(client)
        exact = self.read(client, 492, connection, 1)
        self.assertEqual(exact, bytes.fromhex('cc000000c200')+self.payload[:492])
        self.assertEqual(len(exact)+2, 500)
        first = self.read(client, 493, connection, 2)
        self.assertEqual(first, bytes.fromhex('cc000600c200')+self.payload[:492])
        last = self.read(client, 493, connection, 3, offset=492)
        self.assertEqual(last, bytes.fromhex('d2000000c200')+self.payload[492:493])

    def test_large_connection_uses_all_4000_bytes_and_reassembles_partial_data(self):
        client = self.client(); connection = self.open(client, large=True)
        exact = self.read(client, 3992, connection, 1)
        self.assertEqual(exact, bytes.fromhex('cc000000c200')+self.payload[:3992])
        self.assertEqual(len(exact)+2, 4000)
        first = self.read(client, 4096, connection, 2)
        self.assertEqual(first, bytes.fromhex('cc000600c200')+self.payload[:3992])
        last = self.read(client, 4096, connection, 3, offset=3992)
        self.assertEqual(last, bytes.fromhex('d2000000c200')+self.payload[3992:])
        self.assertEqual(first[6:]+last[6:], self.payload)

    def test_each_connection_uses_its_outgoing_size_with_asymmetric_limits(self):
        for incoming, outgoing, count, data_size, status in ((16, 4000, 1000, 1000, 0),
                (4000, 16, 1000, 8, 6), (4000, 64, 1000, 56, 6)):
            with self.subTest(incoming=incoming, outgoing=outgoing):
                client = self.client()
                connection = self.open(client, large=True, incoming=incoming, outgoing=outgoing)
                result = self.read(client, count, connection, 1)
                self.assertEqual(result, bytes((0xCC, 0, status, 0, 0xC2, 0))+self.payload[:data_size])
                self.assertLessEqual(len(result)+2, outgoing)

    def test_ucmm_and_other_connections_do_not_borrow_a_large_reply_budget(self):
        client = self.client()
        large = self.open(client, large=True)
        small = self.open(client, large=True, outgoing=64, serial=0x3124)
        self.assertEqual(len(self.read(client, 1000, large, 1)), 1006)
        self.assertEqual(len(self.read(client, 1000, small, 1)), 62)
        unconnected = self.read(client, 1000)
        self.assertEqual(unconnected, bytes.fromhex('cc000600c200')+self.payload[:474])
        self.assertEqual(len(unconnected), 480)

    def test_oversized_incoming_message_is_rejected_before_dispatch_and_sequence_consumption(self):
        client = self.client(); connection = self.open(client, large=True, incoming=16)
        before = copy.deepcopy(self.app.engine.memory.values)
        raw = tag_request(0x4C, 'Blob', struct.pack('<H', 10))+bytes(5)
        self.assertEqual(len(raw)+2, 17)
        status, _ = client.cip(raw, connection, 1)
        self.assertNotEqual(status, 0)
        self.assertEqual(self.read(client, 10, connection, 1), bytes.fromhex('cc000000c200')+self.payload[:10])
        self.assertEqual(self.app.engine.memory.values, before)

    def test_large_cached_reply_replays_without_reading_changed_values(self):
        client = self.client(); connection = self.open(client, large=True)
        first = self.read(client, 1000, connection, 1)
        self.assertGreater(len(first), 480)
        self.app.engine.memory.write('Blob[0]', -1)
        self.assertEqual(self.read(client, 1000, connection, 1), first)
        self.assertEqual(self.read(client, 1000, connection, 2)[6:], b'\xff'+self.payload[1:1000])
        status, _ = client.cip(tag_request(0x4C, 'Blob', struct.pack('<H', 999)), connection, 2)
        self.assertNotEqual(status, 0)

    def test_fixed_metadata_reply_above_480_requires_a_sufficient_negotiated_size(self):
        client = self.client()
        standard = self.open(client)
        large = self.open(client, large=True, serial=0x3124)
        symbol = next(item for item in self.endpoint.router.symbols() if item['name']=='DescriptorPayload')
        path = bytes.fromhex('206b2600')+struct.pack('<I', symbol['id'])
        query = bytes((3, len(path)//2))+path+struct.pack('<33H', 32, *([1]*32))
        name = b'DescriptorPayload'
        expected = bytes.fromhex('830000002000')+(struct.pack('<HHH', 1, 0, len(name))+name)*32
        self.assertGreater(len(expected), 498)
        self.assertEqual(self.cip(client, query, standard, 1), bytes.fromhex('83001b00'))
        self.assertEqual(self.cip(client, query, large, 1), expected)
        self.assertEqual(self.cip(client, query), bytes.fromhex('83001b00'))

    def bind_native(self, client):
        original = native_session.NativeSession.begin
        with patch.object(native_session.NativeSession, 'begin', lambda obj, raw: original(obj, raw, nonce=KEY)):
            self.assertEqual(self.cip(client, bytes.fromhex('4b0220642401')+offer())[2], 0)
        self.assertEqual(self.cip(client, bytes.fromhex('4c02206424011400')+bytes(20))[2], 0)
        def signed(sequence, inner, service=0x36):
            raw = signed_request(service, inner, sequence)
            return signed_messages.verify_response(self.cip(client, raw), KEY,
                        request=signed_messages.parse_request(raw)).inner
        self.assertEqual(signed(1, bytes.fromhex('5c02208e2401')+b'operator', 0x37), bytes.fromhex('dc000000'))
        context = signed(2, bytes.fromhex('4b03210078032401')+b'anonymous-context')[4:]
        self.assertEqual(signed(3, bytes.fromhex('6302208e2401')+context), bytes.fromhex('e3000000'))

    def start_native(self):
        self.endpoint.stop()
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e', native_read_only=True).start()
        self.app.endpoint = self.endpoint
        client = self.client(); self.bind_native(client)
        return client

    def test_signed_single_wrappers_fit_negotiated_size_with_mac_and_container_overhead(self):
        for service, overhead in ((0x36, 28), (0x37, 36)):
            with self.subTest(service=service):
                client = self.start_native()
                small = self.open(client)
                large = self.open(client, large=True, serial=0x3124)
                inner = tag_request(0x4C, 'Blob', struct.pack('<H', 1000))
                for sequence, connection, transport, limit in ((4, small, 1, 498), (5, large, 1, 3998)):
                    raw = signed_request(service, inner, sequence)
                    response = self.cip(client, raw, connection, transport)
                    result = signed_messages.verify_response(response, KEY,
                                request=signed_messages.parse_request(raw)).inner
                    self.assertLessEqual(len(response), limit)
                    self.assertEqual(len(response), len(result)+overhead)
                    expected_size = min(1000, limit-overhead-6)
                    self.assertEqual(result, bytes((0xCC, 0, 0 if expected_size==1000 else 6, 0, 0xC2, 0))+
                                     self.payload[:expected_size])

    def test_signed_large_batch_and_denied_write_preserve_values(self):
        client = self.start_native(); large = self.open(client, large=True)
        inner = tag_request(0x4C, 'Blob', struct.pack('<H', 1000))
        raw = batch((inner, inner), sequence=4)
        raw = raw[:-20]+hmac.digest(KEY, raw[:-20], 'sha1')
        response = self.cip(client, raw, large, 1)
        parsed = signed_messages.verify_response(response, KEY, request=signed_messages.parse_request(raw))
        self.assertGreater(len(response), 480); self.assertLessEqual(len(response)+2, 4000)
        self.assertEqual(parsed.children, (bytes.fromhex('cc000000c200')+self.payload[:1000],)*2)
        before = copy.deepcopy(self.app.engine.memory.values)
        write = signed_request(0x36, tag_request(0x4D, 'Blob[0]', bytes.fromhex('c200010001')), 5)
        denied = signed_messages.verify_response(self.cip(client, write, large, 2), KEY,
                    request=signed_messages.parse_request(write))
        self.assertEqual(denied.inner[2], 0x0F)
        self.assertEqual(self.app.engine.memory.values, before)


if __name__ == '__main__':
    unittest.main()
