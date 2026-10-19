"""CIP topology bytes, actual-interface metadata and read-only negative cases."""
import copy
from dataclasses import replace
import socket
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab.ethernetip import Endpoint
from logixlab.network_objects import InterfaceSnapshot, ethernet_mac, interface_snapshot, port_attributes, windows_snapshot
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

    def test_port_node_addresses_use_the_selected_endpoint_and_slot_zero(self):
        self.assertEqual(self.send(0xF4, 1, 7)[4:], b'\1\0')
        self.endpoint.bind_address = '192.0.2.128'
        self.assertEqual(self.send(0xF4, 2, 7)[4:], b'\x12\x0b192.0.2.128\0')
        self.assertEqual(port_attributes(2, '192.0.2.10')[7], b'\x12\x0a192.0.2.10')

    def test_port_instance_all_contains_the_node_address_after_names(self):
        self.assertEqual(self.send(0xF4, 1, service=1)[4:],
                         b'\1\0\1\0\0\0\x09Backplane\x09Backplane\1\0')
        attributes = port_attributes(2)
        self.assertEqual(self.send(0xF4, 2, service=1)[4:], b''.join(attributes.values()))

    def test_physical_link_path_and_mac_describe_the_same_cached_interface(self):
        snapshot = replace(SNAPSHOT, mac=bytes.fromhex('020000000080'))
        with patch('logixlab.ethernetip.interface_snapshot', return_value=(snapshot, None)) as reader:
            self.assertEqual(self.send(0xF5, 1, 4)[4:], b'\2\0\x20\xf6\x24\1')
            self.assertEqual(self.send(0xF6, 1, 3)[4:], bytes.fromhex('020000000080'))
            reader.assert_called_once()
        self.assertEqual(self.app.connectivity()['network_interface']['mac_address'], '02:00:00:00:00:80')
        self.assertEqual(self.send(0xF6, 0, service=1)[4:], b'\1\0\1\0\1\0')

    def test_unknown_physical_link_never_fabricates_a_mac(self):
        with patch('logixlab.ethernetip.interface_snapshot', return_value=(SNAPSHOT, None)):
            self.assertEqual(self.send(0xF5, 1, 4)[4:], b'\0\0')
            self.assertEqual(self.send(0xF6, 1, 3)[2], 0x0C)
            self.assertEqual(self.send(0xF5, 1, 5)[2], 0)
        with patch('logixlab.ethernetip.interface_snapshot', return_value=(None, 'unavailable')):
            self.endpoint.interface_queried = False
            self.assertEqual(self.send(0xF5, 1, 4)[4:], b'\0\0')
            self.assertEqual(self.send(0xF6, 1, 3)[2], 0x0C)

    def test_link_metadata_rejects_writes_and_malformed_requests_with_tag_writes_enabled(self):
        self.endpoint.allow_writes = True
        before = copy.deepcopy(self.app.engine.memory.values)
        with patch('logixlab.ethernetip.interface_snapshot') as reader:
            for cls, inst, attr, service, data, status in (
                (0xF6, 1, 3, 0x10, b'\0' * 6, 8), (0xF6, 2, 3, 0x0E, b'', 5),
                (0xF6, 1, 3, 0x0E, b'\0', 0x15), (0xF6, 1, 1, 0x0E, b'', 0x14),
                (0xF6, 1, None, 3, b'\0\0', 3)):
                with self.subTest(cls=cls, attr=attr, service=service):
                    self.assertEqual(self.send(cls, inst, attr, service, data)[2], status)
            reader.assert_not_called()
        self.assertEqual(self.app.engine.memory.values, before)

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
    def test_mac_parser_retains_unicast_octet_order_and_rejects_non_ethernet_values(self):
        expected = bytes.fromhex('020000000080')
        self.assertEqual(ethernet_mac('02:00:00:00:00:80'), expected)
        self.assertEqual(ethernet_mac('02-00-00-00-00-80'), expected)
        for value in (None, '', '00:00:00:00:00:00', 'ff:ff:ff:ff:ff:ff', '01:00:5e:00:00:01', 'not a MAC'):
            self.assertIsNone(ethernet_mac(value), value)
        for value in (b'', b'\0' * 6, b'\xff' * 6, '020000000080'):
            with self.assertRaises(ValueError):
                replace(SNAPSHOT, mac=value)

    def test_windows_mac_is_optional_and_comes_from_the_selected_adapter(self):
        value = {'address': SNAPSHOT.address, 'prefix': 24, 'gateway': SNAPSHOT.gateway,
                 'dns': list(SNAPSHOT.dns), 'domain': SNAPSHOT.domain, 'name': SNAPSHOT.name,
                 'mac': '02-00-00-00-00-80'}
        with patch('logixlab.network_objects.windows_interface', return_value=value):
            self.assertEqual(windows_snapshot(SNAPSHOT.address).mac, bytes.fromhex('020000000080'))
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

    def test_windows_query_uses_explicit_address_and_validates_the_prefix(self):
        value = {'address': SNAPSHOT.address, 'prefix': 24, 'gateway': SNAPSHOT.gateway,
                 'dns': list(SNAPSHOT.dns), 'domain': SNAPSHOT.domain, 'name': SNAPSHOT.name}
        with patch('logixlab.network_objects.windows_interface', return_value=value) as reader:
            self.assertEqual(windows_snapshot(SNAPSHOT.address), SNAPSHOT)
            reader.assert_called_once_with(SNAPSHOT.address)
        value['prefix'] = True
        with patch('logixlab.network_objects.windows_interface', return_value=value):
            with self.assertRaises(ValueError):
                windows_snapshot(SNAPSHOT.address)


if __name__ == '__main__':
    unittest.main()
