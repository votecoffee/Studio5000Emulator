"""Source-backed configuration reads and discovery without authority services."""
import base64
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint
from logixlab.controller_configuration import ControllerConfiguration
from logixlab.server import Application
from test_ethernetip import Client


CONTROLLER = b'\x20\x8E\x24\1'
DEFINITIONS = bytes.fromhex('210049032400')


class ControllerConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.source = Path(__file__).resolve().parents[1] / 'samples/TextLab.L5X'
        self.clients = []
        self.load('0')
        self.endpoint = Endpoint(self.app, 0, True, 'logix-v35-l85e').start()
        self.app.endpoint = self.endpoint
        self.client = self.connect()

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.app.close()
        self.tmp.cleanup()

    def load(self, code, *, duplicate=False, description=None):
        root = E.fromstring(self.source.read_bytes())
        controller = root.find('Controller')
        for node in controller.findall('Security'):
            controller.remove(node)
        if code is not None:
            node = E.SubElement(controller, 'Security')
            if code != 'MISSING':
                node.set('Code', code)
            if duplicate:
                E.SubElement(controller, 'Security', Code='0')
        for node in controller.findall('Description'):
            controller.remove(node)
        if description is not None:
            E.SubElement(controller, 'Description').text = description
        return self.app.command('load', {'name': 'configuration.L5X',
            'content': base64.b64encode(E.tostring(root)).decode('ascii')})

    def connect(self):
        client = Client(self.endpoint.port)
        client.register()
        self.clients.append(client)
        return client

    def cip(self, raw):
        status, result = self.client.cip(raw)
        self.assertEqual(status, 0)
        return result

    def test_security_code_single_and_list_reads_use_source_udint(self):
        for text, value in (('0', 0), ('0000000042', 42), ('4294967295', 0xFFFFFFFF)):
            self.load(text)
            self.client = self.connect()
            self.assertEqual(self.cip(b'\x0E\3' + CONTROLLER + b'\x30\x0D'),
                             b'\x8E\0\0\0' + struct.pack('<I', value))
            self.assertEqual(self.cip(b'\x03\2' + CONTROLLER + struct.pack('<HH', 1, 13)),
                             b'\x83\0\0\0' + struct.pack('<HHHI', 1, 13, 0, value))

    def test_missing_ambiguous_and_invalid_source_is_never_reported_as_zero(self):
        for code, duplicate in ((None, False), ('MISSING', False), ('0', True),
                                ('', False), ('-1', False), ('4294967296', False),
                                ('16#0000_0000', False), ('1.0', False), ('0'*1000, False)):
            with self.subTest(code=code, duplicate=duplicate):
                self.load(code, duplicate=duplicate)
                self.client = self.connect()
                self.assertEqual(self.cip(b'\x0E\3' + CONTROLLER + b'\x30\x0D'), b'\x8E\0\x14\0')
                self.assertEqual(self.cip(b'\x03\2' + CONTROLLER + b'\1\0\x0D\0'),
                                 b'\x83\0\x0A\0' + struct.pack('<HHH', 1, 13, 0x14))
                state = self.endpoint.state()['controller_configuration']
                self.assertFalse(state['security_code_available'])
                self.assertIsNone(state['legacy_security_configured'])

    def test_list_order_duplicates_and_unknown_attributes_are_preserved(self):
        raw = b'\x03\2' + CONTROLLER + struct.pack('<4H', 3, 13, 14, 13)
        self.assertEqual(self.cip(raw), b'\x83\0\x0A\0' + struct.pack('<HHHIHHHHI', 3, 13, 0, 0, 14, 0x14, 13, 0, 0))

    def test_class_revision_reads_and_metadata_definition_udint_counts(self):
        for path in (b'\x20\x8E\x24\0', b'\x20\x64\x24\0', DEFINITIONS):
            self.assertEqual(self.cip(bytes((0x0E, len(path)//2+1)) + path + b'\x30\1'), b'\x8E\0\0\0\1\0')
            self.assertEqual(self.cip(bytes((3, len(path)//2)) + path + b'\1\0\1\0'),
                             bytes.fromhex('830000000100010000000100'))
        for attr in (2, 3):
            self.assertEqual(self.cip(b'\x0E\4' + DEFINITIONS + bytes((0x30, attr))), b'\x8E\0\0\0' + bytes(4))
        self.assertEqual(self.cip(b'\x03\3' + DEFINITIONS + struct.pack('<4H', 3, 2, 1, 3)),
                         b'\x83\0\0\0' + struct.pack('<HHHIHHHHHI', 3, 2, 0, 0, 1, 0, 1, 3, 0, 0))

    def test_extended_device_name_and_description_single_list_and_all_reads(self):
        for description in (None, '', 'Virtual conveyor', 'x'*128):
            self.load('0', description=description)
            self.client = self.connect()
            name = b'\7\0TextLab'
            encoded = (description or '').encode('ascii')
            text = struct.pack('<H', len(encoded)) + encoded
            for attr, value in ((1, name), (2, text)):
                self.assertEqual(self.cip(b'\x0E\3\x20\x64\x24\1' + bytes((0x30, attr))), b'\x8E\0\0\0' + value)
            self.assertEqual(self.cip(b'\x03\2\x20\x64\x24\1'+struct.pack('<3H', 2, 1, 2)),
                             b'\x83\0\0\0'+struct.pack('<3H', 2, 1, 0)+name+struct.pack('<HH', 2, 0)+text)
            # Retain the established name-only Get Attributes All response.
            self.assertEqual(self.cip(b'\x01\2\x20\x64\x24\1'), b'\x81\0\0\0'+name)

    def test_empty_metadata_instance_list_has_no_count_and_accepts_paging_cursors(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for cursor in (b'\x24\0',b'\x24\1',b'\x25\0\xff\xff',b'\x26\0\0\0\1\0'):
            path=bytes.fromhex('21004903')+cursor
            self.assertEqual(self.cip(bytes((0x4B,len(path)//2))+path),b'\xCB\0\0\0')
        self.assertTrue(self.endpoint.state()['metadata_definition']['instance_list'])
        self.assertEqual(self.app.engine.memory.values,before)

    def test_metadata_list_rejects_attribute_symbol_payload_and_missing_cursor(self):
        for path,data,status in ((DEFINITIONS+b'\x30\1',b'',4),
                (DEFINITIONS+b'\x91\x02xx',b'',4),(bytes.fromhex('21004903'),b'',4),
                (DEFINITIONS,b'\0',0x15)):
            self.assertEqual(self.cip(bytes((0x4B,len(path)//2))+path+data)[2],status)

    def test_extended_device_unknown_or_unrepresentable_text_is_not_truncated(self):
        for description in ('x'*129, '\u2603'):
            self.load('0', description=description)
            self.client = self.connect()
            self.assertEqual(self.cip(b'\x0E\3\x20\x64\x24\1\x30\2'), b'\x8E\0\x14\0')
            self.assertEqual(self.cip(b'\x03\2\x20\x64\x24\1'+struct.pack('<3H', 2, 1, 2))[2], 0x0A)
        self.assertEqual(self.cip(b'\x0E\3\x20\x64\x24\1\x30\x63')[2], 0x14)

    def test_ambiguous_descriptions_and_long_names_are_not_inferred(self):
        for description in ('<Description><LocalizedDescription Lang="en">Text</LocalizedDescription></Description>',
                            '<Description>First</Description><Description>Second</Description>'):
            controller = E.fromstring('<Controller Name="'+'x'*41+'">'+description+'</Controller>')
            configuration = ControllerConfiguration.from_controller(controller)
            self.assertEqual(configuration.extended_device_attributes(), {})

    def test_source_configuration_does_not_enable_authority_or_registration(self):
        self.load('1234567890')
        self.client = self.connect()
        before = copy.deepcopy(self.app.engine.memory.values)
        configuration = self.endpoint.state()['controller_configuration']
        self.assertTrue(configuration['legacy_security_configured'])
        self.assertEqual(configuration['security_enforcement'], 'NOT IMPLEMENTED')
        self.assertFalse(configuration['operator_registration'])
        self.assertFalse(configuration['authority_services'])
        self.assertNotIn('security_code', configuration)
        for service in (0x10, 4, 0x5C, 0x63, 7):
            self.assertEqual(self.cip(bytes((service, 2)) + CONTROLLER + bytes(4))[2], 8)
        for service in (1, 4, 0x10, 0x53):
            self.assertEqual(self.cip(bytes((service, 3)) + DEFINITIONS + bytes(26))[2], 8)
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.endpoint.state()['controller_configuration'], configuration)
        key = self.endpoint.state()['key_exchange']
        self.assertFalse(key['confirmation'])
        self.assertFalse(key['signed_messages'])

    def test_project_replacement_invalidates_sessions_and_updates_availability(self):
        old_hash = self.endpoint.state()['source_l5x_sha256']
        self.load(None)
        self.assertEqual(self.client.cip(b'\x0E\3' + CONTROLLER + b'\x30\x0D')[0], 0x64)
        self.assertNotEqual(self.endpoint.state()['source_l5x_sha256'], old_hash)
        self.client = self.connect()
        self.assertEqual(self.cip(b'\x0E\3' + CONTROLLER + b'\x30\x0D')[2], 0x14)
        self.endpoint.stop()
        self.assertIsNone(self.endpoint.state()['controller_configuration'])
        self.assertIsNone(self.endpoint.state()['metadata_definition'])
        self.app.endpoint = None
        self.assertIsNone(self.app.connectivity()['controller_configuration'])
        self.assertIsNone(self.app.connectivity()['metadata_definition'])

    def test_unsupported_instances_and_malformed_paths_and_lists_are_rejected(self):
        for raw in (b'\x0E\3\x20\x8E\x24\2\x30\x0D',
                    b'\x0E\4' + DEFINITIONS[:-1] + b'\1\x30\1'):
            self.assertEqual(self.cip(raw)[2], 5)
        for path in (CONTROLLER + b'\x28\0', DEFINITIONS + b'\x28\0'):
            self.assertEqual(self.cip(bytes((3, len(path)//2)) + path + b'\1\0\1\0')[2], 4)
        for data in (b'', b'\0\0', b'\1\0', b'\1\0\x0D\0extra'):
            self.assertNotEqual(self.cip(b'\x03\2' + CONTROLLER + data)[2], 0)
        self.assertEqual(self.cip(b'\x0E\3' + CONTROLLER + b'\x30\x0Dextra')[2], 0x15)


if __name__ == '__main__':
    unittest.main()
