"""CIP topology bytes, actual-interface metadata and read-only negative cases."""
import copy
import json
import socket
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab.ethernetip import Endpoint
from logixlab.network_objects import InterfaceSnapshot, interface_snapshot, windows_snapshot
from logixlab.server import Application
from test_ethernetip import Client


SNAPSHOT = InterfaceSnapshot('192.0.2.128', '255.255.255.0', '192.0.2.1',
                             ('192.0.2.53', '192.0.2.54'), 'lab', 'test-interface')


def query(class_id, instance, attribute=None, service=0x0E, data=b''):
    path = bytes((0x20, class_id, 0x24, instance))
    if attribute is not None:
        path += bytes((0x30, attribute))
    return bytes((service, len(path) // 2)) + path + data


class NetworkObjectTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = Application(self.folder.name)
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0).start()
        self.app.endpoint = self.endpoint
        self.client = Client(self.endpoint.port)
        self.client.register()

    def tearDown(self):
        self.client.close()
        self.app.close()
        self.folder.cleanup()

    def send(self, *args, **kwargs):
        status, result = self.client.cip(query(*args, **kwargs))
        self.assertEqual(status, 0)
        return result

    def test_port_inventory_has_reserved_zero_and_one_local_backplane_and_ethernet(self):
        self.assertEqual(self.send(0xF4, 0, 8), b'\x8e\0\0\0\2\0')
        self.assertEqual(self.send(0xF4, 0, 9)[4:], bytes.fromhex('000000000100010004000200'))
        # Class Get_Attributes_All: revision, max, count, entry port, info array.
        self.assertEqual(self.send(0xF4, 0, service=1)[4:],
                         bytes.fromhex('0100020002000200000000000100010004000200'))

    def test_link_paths_reference_only_implemented_objects(self):
        self.assertEqual(self.send(0xF4, 1, 3)[4:], b'\0\0')
        self.assertEqual(self.send(0xF4, 2, 3)[4:], b'\2\0\x20\xf5\x24\1')
        self.assertEqual(self.send(0xF4, 2, 4)[4:], b'\x0bEtherNet/IP')
        self.assertEqual(self.send(0xF5, 0, service=1)[4:], b'\1\0\1\0\1\0')

    def test_ipv4_configuration_golden_udints_and_padded_domain(self):
        self.endpoint.bind_address = SNAPSHOT.address
        with patch('logixlab.ethernetip.interface_snapshot', return_value=(SNAPSHOT, None)) as reader:
            first = self.send(0xF5, 1, 5)
            self.assertEqual(self.send(0xF5, 1, 5), first)
            reader.assert_called_once_with('192.0.2.128')
        self.assertEqual(first, b'\x8e\0\0\0' + bytes.fromhex(
            '800200c000ffffff010200c0350200c0360200c003006c616200'))
        self.assertEqual(self.app.connectivity()['network_interface']['netmask'], '255.255.255.0')

    def test_metadata_query_is_lazy_and_hostname_uses_current_host(self):
        with patch('logixlab.ethernetip.interface_snapshot') as reader, patch.object(socket, 'gethostname', return_value='lab-vm'):
            self.assertEqual(self.send(0xF5, 1, 6)[4:], b'\6\0lab-vm')
            self.send(0xF4, 0, service=1)
            self.app.state()
            reader.assert_not_called()

    def test_unknown_configuration_is_explicit_and_not_a_fabricated_subnet(self):
        with patch('logixlab.ethernetip.interface_snapshot', return_value=(None, 'Unavailable')):
            self.assertEqual(self.send(0xF5, 1, 5)[2], 0x0C)
        state = self.app.connectivity()
        self.assertIsNone(state['network_interface'])
        self.assertEqual(state['network_interface_error'], 'Unavailable')
        self.assertTrue(state['network_interface_queried'])

    def test_mixed_attribute_list_retains_individual_unsupported_status(self):
        result = self.send(0xF4, 2, service=3, data=struct.pack('<4H', 3, 1, 99, 2))
        self.assertEqual(result[:4], b'\x83\0\x0a\0')
        self.assertEqual(result[4:], bytes.fromhex('030001000000040063001400020000000200'))

    def test_rejected_writes_paths_lengths_and_unmodeled_instances_preserve_memory(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        cases = [(query(0xF4, 3, 3), 5), (query(0xF5, 2, 5), 5),
                 (query(0xF4, 2, 99), 0x14), (query(0xF4, 2, 1, data=b'\0'), 0x15),
                 (query(0xF4, 0, service=1, data=b'\0'), 0x15),
                 (query(0xF4, 2, 1, service=0x10, data=b'\1\0'), 8),
                 (query(0xF5, 1, 5, service=0x10, data=b'\0' * 22), 8),
                 (query(0xF5, 1, service=1), 8),
                 (query(0xF5, 1, service=3, data=b'\0\0'), 3),
                 (b'\x0e\1\x20\xf4', 4),
                 (b'\x0e\4\x20\xf4\x24\1\x91\1X\0', 4)]
        for request, expected in cases:
            with self.subTest(request=request.hex()):
                status, result = self.client.cip(request)
                self.assertEqual(status, 0)
                self.assertEqual(result[2], expected)
        self.assertEqual(self.app.engine.memory.values, before)


class InterfaceReaderTests(unittest.TestCase):
    def test_snapshot_rejects_invalid_mask_dns_and_overlong_domain(self):
        for snapshot in (InterfaceSnapshot('192.0.2.1', '255.0.255.0'),
                         InterfaceSnapshot('192.0.2.1', '255.255.255.0', dns=('invalid',)),
                         InterfaceSnapshot('192.0.2.1', '255.255.255.0', domain='a' * 49)):
            with self.subTest(snapshot=snapshot), self.assertRaises(ValueError):
                snapshot.configuration()

    def test_platform_errors_and_mismatched_addresses_are_unavailable(self):
        with patch('logixlab.network_objects.sys.platform', 'win32'), patch('logixlab.network_objects.windows_snapshot', return_value=SNAPSHOT):
            snapshot, error = interface_snapshot('192.0.2.10')
            self.assertIsNone(snapshot)
            self.assertIn('another address', error)
        with patch('logixlab.network_objects.sys.platform', 'unknown'):
            self.assertIsNone(interface_snapshot('192.0.2.10')[0])

    def test_windows_query_uses_explicit_address_and_never_changes_configuration(self):
        value = {'address': SNAPSHOT.address, 'prefix': 24, 'gateway': SNAPSHOT.gateway,
                 'dns': list(SNAPSHOT.dns), 'domain': SNAPSHOT.domain, 'name': SNAPSHOT.name}
        with patch('logixlab.network_objects.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(value).encode()
            self.assertEqual(windows_snapshot(SNAPSHOT.address), SNAPSHOT)
            call = run.call_args
            self.assertEqual(call.kwargs['env']['LOGIXLAB_INTERFACE_ADDRESS'], SNAPSHOT.address)
            self.assertEqual(call.kwargs['timeout'], 12)
        value['prefix'] = True
        with patch('logixlab.network_objects.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(value).encode()
            with self.assertRaises(ValueError):
                windows_snapshot(SNAPSHOT.address)


if __name__ == '__main__':
    unittest.main()
