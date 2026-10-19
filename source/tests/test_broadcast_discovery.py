"""Discovery filtering, source selection and optional-listener cleanup."""
import socket
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from logixlab.broadcast_discovery import BroadcastServer, DiscoveryInterface, INFO, PKTINFO, discovery_request, prepare_broadcasts
from logixlab.network_objects import InterfaceSnapshot


REQUEST = bytes.fromhex('630000000000000000000000') + b'BROWSE17' + b'\0'*4


class BroadcastDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.interface = DiscoveryInterface('192.0.2.128', '255.255.255.0', 7)
        self.destination = '192.0.2.255'
        self.peer = ('192.0.2.1', 54321)

    def info(self, index=7, local='192.0.2.128', destination='192.0.2.255'):
        return [(socket.IPPROTO_IP, PKTINFO, INFO.pack(index, socket.inet_aton(local), socket.inet_aton(destination)))]

    def server(self):
        return SimpleNamespace(interface=self.interface, server_address=(self.destination, 44818),
                               socket=Mock(), reply=Mock(return_value=b'IDENTITY'), record=Mock())

    def test_directed_and_limited_destinations_require_the_exact_local_interface(self):
        self.assertEqual(self.interface.destinations, ('192.0.2.255', '255.255.255.255'))
        for destination in self.interface.destinations:
            self.assertTrue(self.interface.accepts(self.info(destination=destination), 0, destination))
        for metadata in (self.info(index=8), self.info(local='192.0.2.129'), self.info(destination='198.51.100.255')):
            self.assertFalse(self.interface.accepts(metadata, 0, self.destination))
        self.assertFalse(self.interface.accepts(self.info(), 0, '192.0.2.128'))

    def test_missing_ambiguous_short_or_truncated_packet_info_is_rejected(self):
        metadata = self.info()
        for ancillary in ([], metadata*2, [(socket.IPPROTO_IP, PKTINFO, b'\0'*11)],
                          [(socket.IPPROTO_IP, PKTINFO, b'\0'*13)], [(socket.SOL_SOCKET, PKTINFO, metadata[0][2])]):
            self.assertFalse(self.interface.accepts(ancillary, 0, self.destination))
        for flag in (0x08, 0x20, 0x28):
            self.assertFalse(self.interface.accepts(metadata, flag, self.destination))

    def test_only_empty_discovery_requests_are_eligible(self):
        self.assertTrue(discovery_request(REQUEST))
        for command in (4, 0x63, 0x64):
            self.assertTrue(discovery_request(struct.pack('<H', command) + REQUEST[2:]))
        for offset in (0, 2, 4, 8, 20):
            invalid = bytearray(REQUEST); invalid[offset] = 0x65 if offset == 0 else 1
            self.assertFalse(discovery_request(invalid))
        for invalid in (b'', REQUEST[:-1], REQUEST+b'x', REQUEST+b'\x01\0\0\0'):
            self.assertFalse(discovery_request(invalid))

    def test_reply_is_unicast_to_the_sender_from_the_selected_plc_ip(self):
        server = self.server()
        BroadcastServer.respond(server, REQUEST, self.info(), 0, self.peer)
        server.reply.assert_called_once_with(REQUEST, self.peer)
        server.socket.sendmsg.assert_called_once_with([b'IDENTITY'],
            [(socket.IPPROTO_IP, PKTINFO, struct.pack('=I4s4s', 7, bytes((192, 0, 2, 128)), b'\0'*4))], 0, self.peer)
        self.assertEqual(server.record.call_args.args[0], 'broadcast_discovery')

    def test_foreign_interfaces_bad_requests_and_zero_ports_never_call_the_endpoint(self):
        for raw, ancillary, flags, peer in ((REQUEST, self.info(index=8), 0, self.peer),
                (REQUEST, self.info(), 0x20, self.peer), (REQUEST+b'x', self.info(), 0, self.peer),
                (REQUEST, self.info(), 0, ('192.0.2.1', 0))):
            server = self.server()
            BroadcastServer.respond(server, raw, ancillary, flags, peer)
            server.reply.assert_not_called(); server.socket.sendmsg.assert_not_called()
            self.assertEqual(server.record.call_args.args[0], 'broadcast_ignored')

    def test_send_failure_is_recorded_without_terminating_the_listener(self):
        server = self.server(); server.socket.sendmsg.side_effect = OSError('No route')
        BroadcastServer.respond(server, REQUEST, self.info(), 0, self.peer)
        self.assertEqual(server.record.call_args.args[0], 'broadcast_error')

    def test_desktop_and_loopback_paths_do_not_open_broadcast_sockets(self):
        for platform, address in (('win32', '192.0.2.128'), ('linux', '127.0.0.1')):
            with patch('logixlab.broadcast_discovery.sys.platform', platform), \
                 patch('logixlab.broadcast_discovery.interface_snapshot') as query, \
                 patch('logixlab.broadcast_discovery.BroadcastServer') as create:
                servers, status = prepare_broadcasts(address, 44818, Mock(), Mock())
                self.assertEqual(servers, []); self.assertFalse(status['broadcast_enabled'])
                query.assert_not_called(); create.assert_not_called()

    def test_both_sockets_bind_explicit_broadcast_addresses(self):
        snapshot = InterfaceSnapshot('192.0.2.128', '255.255.255.0', name='eth-test', mac=bytes.fromhex('020000000080'))
        with patch('logixlab.broadcast_discovery.sys.platform', 'linux'), \
             patch('logixlab.broadcast_discovery.interface_snapshot', return_value=(snapshot, None)), \
             patch('logixlab.broadcast_discovery.socket.if_nametoindex', return_value=7), \
             patch('logixlab.broadcast_discovery.BroadcastServer') as create:
            servers, status = prepare_broadcasts('192.0.2.128', 44818, Mock(), Mock())
        self.assertEqual(len(servers), 2); self.assertTrue(status['broadcast_enabled'])
        self.assertEqual([call.args[0] for call in create.call_args_list], [('192.0.2.255', 44818), ('255.255.255.255', 44818)])

    def test_partial_setup_failure_closes_the_first_socket(self):
        snapshot = InterfaceSnapshot('192.0.2.128', '255.255.255.0', name='eth-test', mac=bytes.fromhex('020000000080'))
        first = Mock()
        with patch('logixlab.broadcast_discovery.sys.platform', 'linux'), \
             patch('logixlab.broadcast_discovery.interface_snapshot', return_value=(snapshot, None)), \
             patch('logixlab.broadcast_discovery.socket.if_nametoindex', return_value=7), \
             patch('logixlab.broadcast_discovery.BroadcastServer', side_effect=[first, OSError('Port in use')]):
            servers, status = prepare_broadcasts('192.0.2.128', 44818, Mock(), Mock())
        self.assertEqual(servers, []); self.assertFalse(status['broadcast_enabled'])
        self.assertIn('Port in use', status['reason']); first.server_close.assert_called_once()

    def test_unavailable_non_ethernet_and_point_to_point_interfaces_are_skipped(self):
        ethernet = bytes.fromhex('020000000080')
        cases = [(None, 'No interface'),
                 (InterfaceSnapshot('192.0.2.128', '255.255.255.0', name='tun-test'), None),
                 (InterfaceSnapshot('192.0.2.128', '255.255.255.254', name='eth-test', mac=ethernet), None)]
        for snapshot in cases:
            with patch('logixlab.broadcast_discovery.sys.platform', 'linux'), \
                 patch('logixlab.broadcast_discovery.interface_snapshot', return_value=snapshot), \
                 patch('logixlab.broadcast_discovery.BroadcastServer') as create:
                servers, status = prepare_broadcasts('192.0.2.128', 44818, Mock(), Mock())
                self.assertEqual(servers, []); self.assertFalse(status['broadcast_enabled'])
                self.assertTrue(status['reason']); create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
