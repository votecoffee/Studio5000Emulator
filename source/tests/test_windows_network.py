"""Exercise Windows ABI decoding with isolated native structure fixtures."""
import ctypes as C
import socket
import struct
import unittest
from unittest.mock import patch

from logixlab.windows_network import AdapterNode, AddressNode, SocketAddress, UnicastNode, _walk, windows_interface


class WindowsNetworkTests(unittest.TestCase):
    def setUp(self):
        self.keepalive = []

    def address(self, ip, family=2):
        buffer = C.create_string_buffer(struct.pack('<HH', family, 0) + socket.inet_aton(ip) + b'\0' * 8)
        self.keepalive.append(buffer)
        return SocketAddress(C.addressof(buffer), 16)

    def node(self, ip):
        value = AddressNode()
        value.alignment = C.sizeof(AddressNode)
        value.address = self.address(ip)
        self.keepalive.append(value)
        return C.pointer(value)

    def adapter(self, ip='192.0.2.128', prefix=24):
        value = AdapterNode()
        value.alignment = C.sizeof(AdapterNode)
        value.friendly_name = 'Test adapter'
        value.dns_suffix = 'lab'
        value.interface_type = 6
        value.physical_length = 6
        value.physical_address[:6] = bytes.fromhex('020000000080')
        value.dns = self.node('192.0.2.53')
        value.gateway = self.node('192.0.2.1')
        unicast = UnicastNode()
        unicast.alignment = C.sizeof(UnicastNode)
        unicast.address = self.address(ip)
        unicast.prefix_length = prefix
        value.unicast = C.pointer(unicast)
        self.keepalive.extend((value, unicast))
        return value

    def read(self, value, address):
        with patch('logixlab.windows_network._adapters', return_value=(self.keepalive, C.pointer(value))):
            return windows_interface(address)

    def test_selected_interface_has_exact_prefix_gateway_dns_and_mac(self):
        self.assertEqual(self.read(self.adapter(), '192.0.2.128'),
            {'address': '192.0.2.128', 'prefix': 24, 'gateway': '192.0.2.1', 'dns': ['192.0.2.53'],
             'domain': 'lab', 'name': 'Test adapter', 'mac': '02:00:00:00:00:80'})

    def test_subnet_neighbor_is_not_treated_as_a_local_address(self):
        with self.assertRaises(ValueError):
            self.read(self.adapter(), '192.0.2.129')

    def test_loopback_alias_uses_its_real_prefix_and_never_an_ethernet_mac(self):
        value = self.adapter('127.0.0.1', 8)
        value.interface_type = 24
        value.dns = C.POINTER(AddressNode)()
        value.gateway = C.POINTER(AddressNode)()
        result = self.read(value, '127.0.0.2')
        self.assertEqual(result['prefix'], 8)
        self.assertEqual(result['gateway'], '0.0.0.0')
        self.assertEqual(result['dns'], [])
        self.assertIsNone(result['mac'])

    def test_exact_loopback_alias_takes_precedence_over_an_earlier_fallback(self):
        first = self.adapter('127.0.0.1', 8)
        second = self.adapter('127.0.0.2', 32)
        first.next = C.pointer(second)
        self.assertEqual(self.read(first, '127.0.0.2')['prefix'], 32)

    def test_invalid_prefix_and_short_or_cyclic_records_are_rejected(self):
        with self.assertRaises(ValueError):
            self.read(self.adapter(prefix=33), '192.0.2.128')
        short = self.adapter()
        short.alignment = 8
        with self.assertRaises(ValueError):
            self.read(short, '192.0.2.128')
        cyclic = self.adapter()
        cyclic.next = C.pointer(cyclic)
        with self.assertRaises(ValueError):
            list(_walk(C.pointer(cyclic)))

    def test_ipv6_dns_records_do_not_corrupt_the_ipv4_configuration(self):
        value = self.adapter()
        other = AddressNode()
        other.alignment = C.sizeof(AddressNode)
        other.address = self.address('192.0.2.1', family=23)
        other.next = value.dns
        value.dns = C.pointer(other)
        self.keepalive.append(other)
        self.assertEqual(self.read(value, '192.0.2.128')['dns'], ['192.0.2.53'])


if __name__ == '__main__':
    unittest.main()
