"""Software-device identity is explicit and never grants operator authority."""
import copy
import struct
import tempfile
import unittest

from logixlab import device_metadata
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.server import Application


class DeviceMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, True, 'logix-v35-l85e').start()
        self.app.endpoint = self.endpoint

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def send(self, service=0x0E, path=bytes.fromhex('206424013003'), data=b''):
        return self.endpoint.router.handle(bytes((service, len(path)//2))+path+data, Session())

    def test_model_defaults_have_exact_v35_field_widths_and_provenance(self):
        self.assertEqual(device_metadata.attributes(), {3: bytes(2), 6: b'\5\0en-US',
                                                       7: bytes(2), 8: bytes(4)})
        state = self.endpoint.state()['device_metadata']
        self.assertEqual(state['location'], '')
        self.assertEqual(state['locale'], 'en-US')
        self.assertEqual(state['trusted_slot_count'], 0)
        self.assertEqual(state['system_operator_identity'], 0)
        self.assertIn('software-device defaults', state['source'])
        for key in ('writable', 'trusted_slot_enforcement', 'operator_authorization', 'authority_services'):
            self.assertFalse(state[key])

    def test_individual_reads_and_native_list_preserve_name_and_description(self):
        for attr, value in ((3, b'\0\0'), (6, b'\5\0en-US'), (7, b'\0\0'), (8, bytes(4))):
            self.assertEqual(self.send(path=bytes.fromhex('2064240130')+bytes((attr,))),
                             bytes.fromhex('8e000000')+value)
        order = (1, 2, 3, 6, 7, 8)
        expected = (bytes.fromhex('830000000600010000000c00')+b'ConveyorDemo'+
                    bytes.fromhex('020000000000030000000000060000000500')+b'en-US'+
                    bytes.fromhex('0700000000000800000000000000'))
        self.assertEqual(self.send(3, bytes.fromhex('20642401'), struct.pack('<7H', 6, *order)), expected)
        self.assertEqual(self.send(1, bytes.fromhex('20642401')),
                         bytes.fromhex('810000000c00')+b'ConveyorDemo')

    def test_lists_keep_duplicate_order_and_report_unknown_fields_without_padding(self):
        self.assertEqual(self.send(3, bytes.fromhex('20642401'), struct.pack('<5H', 4, 6, 99, 6, 8)),
                         bytes.fromhex('83000a000400060000000500')+b'en-US'+
                         bytes.fromhex('63001400060000000500')+b'en-US'+bytes.fromhex('0800000000000000'))
        row = self.endpoint.state()['attribute_gaps'][0]
        self.assertEqual(row['class_name'], 'Extended Device')
        self.assertEqual([attr['id'] for attr in row['attributes']], [99])

    def test_model_properties_do_not_gain_or_lose_authority_when_project_changes(self):
        first = self.endpoint.state()['device_metadata']
        self.app.command('demo', {'sample': 'TextLab'})
        self.assertEqual(self.endpoint.state()['device_metadata'], first)
        self.assertEqual(self.send(path=bytes.fromhex('206424013001')),
                         bytes.fromhex('8e0000000700')+b'TextLab')
        data = device_metadata.description(); data['locale'] = 'changed'
        attrs = device_metadata.attributes(); attrs[8] = b'\xff'*4
        self.assertEqual(self.endpoint.state()['device_metadata'], first)
        self.assertEqual(self.send(path=bytes.fromhex('206424013008')), bytes.fromhex('8e00000000000000'))

    def test_setters_and_authority_services_preserve_device_properties_and_tags(self):
        memory = copy.deepcopy(self.app.engine.memory.values)
        metadata = self.endpoint.state()['device_metadata']
        for attr in (3, 6, 7, 8):
            self.assertEqual(self.send(0x10, bytes.fromhex('2064240130')+bytes((attr,)), b'\xff'*8)[2], 8)
        for service in (4, 0x5C, 0x63):
            self.assertEqual(self.send(service, bytes.fromhex('20642401'), bytes(12))[2], 8)
        self.assertEqual(self.app.engine.memory.values, memory)
        self.assertEqual(self.endpoint.state()['device_metadata'], metadata)
        self.assertFalse(self.endpoint.state()['native_session']['operator_authorization'])

    def test_malformed_lengths_and_non_controller_paths_cannot_read_or_start_challenge(self):
        for data in (b'', bytes(2), bytes.fromhex('02000300'), bytes.fromhex('01000300ff')):
            self.assertNotEqual(self.send(3, bytes.fromhex('20642401'), data)[2], 0)
        self.assertEqual(self.send(data=b'\0')[2], 0x15)
        paths = (symbol_path('Program:MainProgram')+bytes.fromhex('20642401'),
                 bytes.fromhex('20682401')+bytes.fromhex('20642401'))
        for path in paths:
            for service in (1, 3, 0x0E, 0x4B, 0x4C):
                self.assertEqual(self.send(service, path)[2], 4)

    def test_stopped_endpoint_does_not_advertise_device_metadata(self):
        self.endpoint.stop()
        self.assertIsNone(self.endpoint.state()['device_metadata'])
        self.app.endpoint = None
        self.assertIsNone(self.app.connectivity()['device_metadata'])


if __name__ == '__main__':
    unittest.main()
