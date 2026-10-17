"""Automatic TCP/UDP pair selection and failed-start resource cleanup."""
import socket
import socketserver
import tempfile
import unittest
from unittest.mock import patch
from logixlab.model import ModelError
from logixlab.server import Application
from logixlab.ethernetip import Endpoint
from test_ethernetip import Client


class EndpointBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'TextLab'}); self.endpoint = None

    def tearDown(self):
        if self.endpoint: self.endpoint.stop()
        self.app.close(); self.tmp.cleanup()

    def test_automatic_port_retries_when_udp_cannot_use_the_tcp_port(self):
        real_udp = socketserver.UDPServer; attempts = []
        def bind_udp(address, handler):
            attempts.append(address)
            if len(attempts) == 1: raise PermissionError(10013, 'Simulated unavailable UDP port')
            return real_udp(address, handler)
        self.endpoint = Endpoint(self.app, 0)
        with patch('logixlab.ethernetip.socketserver.UDPServer', side_effect=bind_udp): self.endpoint.start()
        self.assertEqual(len(attempts), 2); self.assertTrue(self.endpoint.enabled)
        self.assertEqual(self.endpoint.tcp.server_address, self.endpoint.udp.server_address)
        client = Client(self.endpoint.port)
        try:
            client.register(); self.assertNotEqual(client.session, 0)
            header, data = client.packet(0x63); self.assertEqual(header[3], 0); self.assertIn(b'LogixLab', data)
        finally: client.close()

    def test_automatic_port_exhaustion_is_bounded_and_stop_is_safe(self):
        self.endpoint = Endpoint(self.app, 0)
        with patch('logixlab.ethernetip.socketserver.UDPServer', side_effect=OSError('No UDP pair available')) as bind:
            with self.assertRaises(ModelError): self.endpoint.start()
        self.assertEqual(bind.call_count, 8); self.assertFalse(self.endpoint.enabled)
        self.assertIsNone(self.endpoint.tcp); self.assertIsNone(self.endpoint.udp); self.assertEqual(self.endpoint.port, 0)
        self.assertFalse(self.endpoint.threads)

    def test_fixed_port_udp_failure_does_not_relocate_and_releases_tcp(self):
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0)); port = available.getsockname()[1]
        self.endpoint = Endpoint(self.app, port)
        with patch('logixlab.ethernetip.socketserver.UDPServer', side_effect=PermissionError('UDP denied')) as bind:
            with self.assertRaises(ModelError): self.endpoint.start()
        self.assertEqual(bind.call_count, 1); self.assertEqual(self.endpoint.port, port)
        self.assertIsNone(self.endpoint.tcp); self.assertIsNone(self.endpoint.udp)
        with socket.socket() as released: released.bind(('127.0.0.1', port))

    def test_fixed_port_tcp_failure_does_not_attempt_udp(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0)); occupied.listen()
            self.endpoint = Endpoint(self.app, occupied.getsockname()[1])
            with patch('logixlab.ethernetip.socketserver.UDPServer') as bind:
                with self.assertRaises(ModelError): self.endpoint.start()
            bind.assert_not_called()
        self.assertFalse(self.endpoint.enabled); self.assertIsNone(self.endpoint.tcp)


if __name__ == '__main__': unittest.main()
