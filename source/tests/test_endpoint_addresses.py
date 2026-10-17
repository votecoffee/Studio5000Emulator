"""Address isolation and advertised socket addresses on actual TCP/UDP sockets."""
import socket
import struct
import tempfile
import unittest

from logixlab.ethernetip import Endpoint
from logixlab.model import ModelError
from logixlab.server import Application
from test_ethernetip import Client, H, request


class EndpointAddressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'TextLab'})

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def start(self):
        state = self.app.command('connectivity-start', {'port': 0, 'bind_address': '127.0.0.2'})
        self.assertEqual(state['connectivity']['bind_address'], '127.0.0.2')
        return self.app.endpoint

    def test_selected_address_is_used_by_tcp_udp_and_list_identity(self):
        endpoint = self.start()
        self.assertEqual(endpoint.state()['address'], f'127.0.0.2:{endpoint.port}')
        self.assertEqual(endpoint.tcp.server_address, ('127.0.0.2', endpoint.port))
        self.assertEqual(endpoint.udp.server_address, ('127.0.0.2', endpoint.port))
        client = Client(endpoint.port, '127.0.0.2')
        try:
            header, identity = client.packet(0x63, handle=0)
            self.assertEqual(header[3], 0)
            self.assertEqual(struct.unpack_from('>HH4s', identity, 8),
                             (2, endpoint.port, socket.inet_aton('127.0.0.2')))
            client.register()
            self.assertEqual(client.cip(request(0x4C, 'Step', b'\1\0')),
                             (0, b'\xCC\0\0\0\xC4\0\x02\0\0\0'))
        finally:
            client.close()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.settimeout(2)
            udp.sendto(H.pack(0x63, 0, 0, 0, b'TESTWIRE', 0), ('127.0.0.2', endpoint.port))
            raw, peer = udp.recvfrom(4096)
            self.assertEqual(peer, ('127.0.0.2', endpoint.port))
            self.assertEqual(raw[24:], identity)

    def test_specific_binding_does_not_listen_on_other_loopback_address(self):
        endpoint = self.start()
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', endpoint.port), timeout=0.2)

    def test_two_specific_addresses_can_use_the_same_port_independently(self):
        first = self.start()
        second = Endpoint(self.app, first.port).start()
        try:
            a, b = Client(first.port, '127.0.0.2'), Client(first.port)
            try:
                self.assertEqual(a.packet(0x63, handle=0)[1][12:16], socket.inet_aton('127.0.0.2'))
                self.assertEqual(b.packet(0x63, handle=0)[1][12:16], socket.inet_aton('127.0.0.1'))
            finally:
                a.close(); b.close()
        finally:
            second.stop()

    def test_occupied_udp_port_releases_partially_bound_tcp_socket(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as occupied:
            occupied.bind(('127.0.0.2', 0))
            port = occupied.getsockname()[1]
            endpoint = Endpoint(self.app, port, bind_address='127.0.0.2')
            with self.assertRaisesRegex(ModelError, f'UDP at 127.0.0.2:{port}'):
                endpoint.start()
            self.assertFalse(endpoint.enabled)
            self.assertIsNone(endpoint.tcp)
            self.assertIsNone(endpoint.udp)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
                tcp.bind(('127.0.0.2', port))

    def test_invalid_or_ambiguous_bindings_are_rejected_before_startup(self):
        for value in ('0.0.0.0', '0.0.0.1', '224.0.0.1', '255.255.255.255', '240.0.0.1',
                      'localhost', '::1', '127.00.0.1', '127.0.0.1:44818', '', None, True, 123):
            with self.subTest(value=value), self.assertRaisesRegex(ModelError, 'Bind IP'):
                Endpoint(self.app, 0, bind_address=value)
        self.assertIsNone(self.app.endpoint)
