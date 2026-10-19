"""Automatic TCP/UDP pair selection and failed-start resource cleanup."""
import socket
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
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

    @unittest.skipUnless(sys.platform == 'linux', 'Linux TCP TIME_WAIT behavior')
    def test_linux_restart_reuses_port_after_server_closes_an_active_connection(self):
        self.endpoint = Endpoint(self.app, 0).start()
        port = self.endpoint.port
        client = Client(port)
        try:
            client.register()
            peer_port = client.socket.getsockname()[1]
            self.endpoint.stop()  # Server closes first, so its port enters TIME_WAIT.
            self.assertEqual(client.socket.recv(1), b'')
        finally:
            client.close()
        local, peer = f'0100007F:{port:04X}', f'0100007F:{peer_port:04X}'
        deadline = time.monotonic() + 2
        while True:
            rows = [line.split() for line in Path('/proc/net/tcp').read_text().splitlines()[1:]]
            if any(row[1:4] == [local, peer, '06'] for row in rows): break
            if time.monotonic() >= deadline: self.fail('Server-side TIME_WAIT was not established')
            time.sleep(.01)
        self.endpoint = Endpoint(self.app, port).start()
        replacement = Client(port)
        try:
            replacement.register()
            self.assertEqual(replacement.packet(0x63)[0][3], 0)
        finally: replacement.close()

    @unittest.skipUnless(sys.platform == 'linux', 'Linux reusable listener ownership')
    def test_linux_running_endpoint_cannot_share_its_tcp_listener(self):
        self.endpoint = Endpoint(self.app, 0).start()
        with socket.socket() as competitor:
            competitor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with self.assertRaises(OSError): competitor.bind(('127.0.0.1', self.endpoint.port))
        second = Endpoint(self.app, self.endpoint.port)
        try:
            with self.assertRaises(ModelError): second.start()
        finally: second.stop()
        client = Client(self.endpoint.port)
        try: client.register()
        finally: client.close()

    def test_live_wildcard_listener_prevents_specific_address_startup(self):
        with socket.socket() as occupied:
            if sys.platform == 'win32':
                occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            occupied.bind(('0.0.0.0', 0)); occupied.listen()
            self.endpoint = Endpoint(self.app, occupied.getsockname()[1])
            with self.assertRaises(ModelError): self.endpoint.start()
            self.assertFalse(self.endpoint.enabled)

    def test_unavailable_broadcast_listener_preserves_tcp_and_udp_unicast(self):
        status = {'broadcast_enabled': False, 'broadcast_addresses': [], 'interface': None, 'reason': 'Port in use'}
        with patch('logixlab.ethernetip.prepare_broadcasts', return_value=([], status)):
            self.endpoint = Endpoint(self.app, 0).start()
        self.assertFalse(self.endpoint.state()['discovery']['broadcast_enabled'])
        self.assertEqual(self.endpoint.state()['discovery']['reason'], 'Port in use')
        client = Client(self.endpoint.port)
        try:
            head, identity = client.packet(0x63)
            self.assertEqual(head[3], 0)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.settimeout(2)
                udp.sendto(bytes.fromhex('630000000000000000000000') + b'BROWSE17' + b'\0'*4, ('127.0.0.1', self.endpoint.port))
                raw, _ = udp.recvfrom(4096)
                self.assertEqual(raw[24:], identity)
        finally:
            client.close()

    def test_endpoint_stop_closes_every_extra_broadcast_listener(self):
        class ExtraListener:
            def __init__(self):
                self.done = threading.Event(); self.closed = False
            def serve_forever(self, poll_interval): self.done.wait()
            def shutdown(self): self.done.set()
            def server_close(self): self.closed = True
        extra = [ExtraListener(), ExtraListener()]
        status = {'broadcast_enabled': True, 'broadcast_addresses': ['192.0.2.255', '255.255.255.255'], 'interface': 'eth-test', 'reason': None}
        with patch('logixlab.ethernetip.prepare_broadcasts', return_value=(extra, status)):
            self.endpoint = Endpoint(self.app, 0).start()
        self.assertTrue(self.endpoint.state()['discovery']['broadcast_enabled'])
        self.endpoint.stop()
        self.assertFalse(self.endpoint.state()['discovery']['broadcast_enabled'])
        for server in extra:
            self.assertTrue(server.done.is_set()); self.assertTrue(server.closed)
        for thread in self.endpoint.threads:
            thread.join(timeout=1); self.assertFalse(thread.is_alive())


if __name__ == '__main__': unittest.main()
