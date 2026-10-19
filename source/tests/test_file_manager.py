"""File Manager class discovery, absent devices and rejected file operations."""
import copy
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from logixlab.ethernetip import Endpoint, symbol_path
from logixlab.server import Application
from test_ethernetip import Client


CLASS_PATH = bytes.fromhex('21001a032400')


class FileManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name); self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, True, 'logix-v35-l85e').start(); self.app.endpoint = self.endpoint
        self.client = Client(self.endpoint.port); self.client.register()

    def tearDown(self):
        self.client.close(); self.app.close(); self.tmp.cleanup()

    def cip(self, raw):
        status, result = self.client.cip(raw)
        self.assertEqual(status, 0)
        return result

    def test_captured_native_revision_queries_have_identical_uint_values(self):
        self.assertEqual(self.cip(bytes.fromhex('030321001a03240001000100')),
                         bytes.fromhex('830000000100010000000100'))
        self.assertEqual(self.cip(bytes.fromhex('0e0421001a0324003001')), b'\x8E\0\0\0\1\0')

    def test_zero_instance_count_is_udint_and_lists_preserve_order(self):
        self.assertEqual(self.cip(b'\x0E\4' + CLASS_PATH + b'\x30\3'), b'\x8E\0\0\0' + b'\0'*4)
        body = struct.pack('<4H', 3, 3, 1, 3)
        self.assertEqual(self.cip(b'\x03\3' + CLASS_PATH + body), b'\x83\0\0\0' +
            struct.pack('<HHHIHHHHHI', 3, 3, 0, 0, 1, 0, 1, 3, 0, 0))

    def test_unknown_class_attributes_are_reported_separately(self):
        response = self.cip(b'\x03\3' + CLASS_PATH + struct.pack('<4H', 3, 2, 1, 3))
        self.assertEqual(response, b'\x83\0\x0A\0' + struct.pack('<HHHHHHHHI', 3, 2, 0x14, 1, 0, 1, 3, 0, 0))
        self.assertEqual(self.cip(b'\x0E\4' + CLASS_PATH + b'\x30\2')[2], 0x14)

    def test_no_storage_instances_or_capacity_are_advertised(self):
        for instance in (1, 2, 255):
            path = bytes.fromhex('21001a03') + bytes((0x24, instance))
            for service in (0x0E, 0x4B, 0x4D):
                self.assertEqual(self.cip(bytes((service, 4)) + path + b'\x30\1')[2], 5)
        self.assertEqual(self.cip(bytes.fromhex('0e0621001a032600000000003003')), b'\x8E\0\0\0' + b'\0'*4)

    def test_malformed_lists_attribute_paths_and_payloads_are_rejected(self):
        for data in (b'', b'\0\0', b'\1\0', b'\1\0\1\0x', struct.pack('<H', 33) + b'\1\0'*33):
            self.assertNotEqual(self.cip(b'\x03\3' + CLASS_PATH + data)[2], 0)
        for extra in (symbol_path('Extra'), b'\x28\0'):
            path = CLASS_PATH + extra
            self.assertEqual(self.cip(bytes((3, len(path)//2)) + path + b'\1\0\1\0')[2], 4)
        self.assertEqual(self.cip(b'\x0E\4' + CLASS_PATH + b'\x30\1x')[2], 0x15)
        self.assertEqual(self.cip(b'\x03\4' + CLASS_PATH + b'\x30\1\1\0\1\0')[2], 8)

    def test_discovery_and_rejected_file_commands_preserve_values_and_files(self):
        def files():
            return {str(p.relative_to(self.tmp.name)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in Path(self.tmp.name).rglob('*') if p.is_file()}
        memory = copy.deepcopy(self.app.engine.memory.values); before = files()
        token = self.endpoint.state()['catalog_revision']
        for service in (1, 0x10, 0x4B, 0x4C, 0x4D, 0x53, 0x54):
            self.assertEqual(self.cip(bytes((service, 3)) + CLASS_PATH)[2], 8)
        self.cip(b'\x03\3' + CLASS_PATH + struct.pack('<3H', 2, 1, 3))
        self.assertTrue(self.endpoint.allow_writes)
        self.assertEqual(self.app.engine.memory.values, memory); self.assertEqual(files(), before)
        self.assertEqual(self.endpoint.state()['catalog_revision'], token)

    def test_connectivity_metadata_matches_wire_and_clears_when_stopped(self):
        metadata = self.endpoint.state()['file_manager']
        self.assertEqual(metadata, {'object_revision': 1, 'instance_count': 0, 'emulated_storage': False, 'file_operations': False})
        self.assertEqual(struct.unpack('<I', self.cip(b'\x0E\4' + CLASS_PATH + b'\x30\3')[4:])[0], metadata['instance_count'])
        self.endpoint.stop(); self.assertIsNone(self.endpoint.state()['file_manager'])
        self.app.endpoint = None; self.assertIsNone(self.app.connectivity()['file_manager'])


if __name__ == '__main__':
    unittest.main()
