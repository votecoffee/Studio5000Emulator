"""Time Sync source configuration never implies working PTP or clock readings."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import Project
from logixlab.server import Application
from logixlab.time_sync import TimeSync


class TimeSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, True, 'logix-v35-l85e')
        self.app.endpoint = self.endpoint
        self.root = E.parse(self.app.engine.project.path).getroot()
        self.node = E.SubElement(self.root.find('Controller'), 'TimeSynchronize',
                                 PTPEnable='false', Priority1='128', Priority2='128')
        self.load()

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def settings(self):
        return TimeSync.from_source(self.root, self.root.find('Controller'))

    def load(self):
        path = Path(self.tmp.name) / 'clock.L5X'
        E.ElementTree(self.root).write(path)
        self.app.engine.project = Project(path)

    def send(self, service=0x0E, path=bytes.fromhex('204324013001'), data=b''):
        return self.endpoint.router.handle(bytes((service, len(path)//2)) + path + data, Session())

    def test_source_settings_and_limits_are_independent_of_enabled_ptp(self):
        for enabled in (False, True):
            self.node.set('PTPEnable', str(enabled).lower())
            settings = self.settings()
            self.assertEqual(settings.attributes(), {1: bytes((enabled,)), 16: b'\x80', 17: b'\x80'})
            desc = settings.description()
            self.assertEqual(desc['ptp_enabled'], enabled)
            self.assertEqual(desc['available_attributes'], [1, 16, 17])
            for key in ('settings_writable', 'ptp_engine', 'clock_measurements', 'port_metadata'):
                self.assertFalse(desc[key])

    def test_absent_declaration_or_missing_fields_do_not_gain_defaults(self):
        self.node.attrib.clear()
        self.assertEqual(self.settings().attributes(), {})
        self.node.set('Priority1', '0')
        self.assertEqual(self.settings().attributes(), {16: b'\0'})
        self.root.find('Controller').remove(self.node)
        self.assertEqual(self.settings().attributes(), {})

    def test_priorities_accept_byte_limits_but_not_malformed_or_wrapped_values(self):
        for text, expected in (('0', 0), ('255', 255), ('001', 1), ('256', None),
                               ('-1', None), ('+1', None), ('1.0', None), ('', None),
                               (' 1', None), ('1 ', None), ('0x80', None), ('１２８', None)):
            with self.subTest(text=text):
                self.node.set('Priority1', text)
                settings = self.settings()
                self.assertEqual(settings.priority1, expected)
                self.assertEqual(settings.priority2, 128)
                self.assertEqual(settings.ptp_enabled, False)
                self.assertEqual(16 in settings.attributes(), expected is not None)

    def test_enable_requires_a_source_boolean(self):
        for text in ('TRUE', 'False', '1', '0', '', ' true', 'unknown'):
            self.node.set('PTPEnable', text)
            self.assertIsNone(self.settings().ptp_enabled)
            self.assertNotIn(1, self.settings().attributes())

    def test_partial_and_context_exports_are_unavailable(self):
        for attribute, value in (('ContainsContext', 'true'), ('TargetType', 'Tag')):
            original = self.root.get(attribute)
            self.root.set(attribute, value)
            self.assertEqual(self.settings().attributes(), {})
            self.root.set(attribute, original)
        self.node.set('Use', 'Context')
        self.assertEqual(self.settings().attributes(), {})

    def test_ambiguous_declarations_and_setting_names_are_unavailable(self):
        for mode in ('duplicate', 'nested', 'namespace', 'case', 'uid', 'attribute_case',
                     'attribute_namespace', 'attribute_uid', 'child', 'text'):
            with self.subTest(mode=mode):
                root = copy.deepcopy(self.root)
                controller = root.find('Controller'); node = controller.find('TimeSynchronize')
                if mode == 'duplicate': E.SubElement(controller, 'TimeSynchronize')
                elif mode == 'nested': controller.remove(node); controller.find('Tags').append(node)
                elif mode == 'namespace': node.tag = '{extra}TimeSynchronize'
                elif mode == 'case': node.tag = 'timesynchronize'
                elif mode == 'uid': E.SubElement(controller, 'TimeSynchronizeUId')
                elif mode == 'child': E.SubElement(node, 'Priority1', Value='2')
                elif mode == 'text': node.text = 'unparsed settings'
                else:
                    key = {'attribute_case': 'priority1', 'attribute_namespace': '{extra}Priority1',
                           'attribute_uid': 'Priority1UId'}[mode]
                    node.set(key, '2')
                self.assertEqual(TimeSync.from_source(root, controller).attributes(), {})

    def test_single_reads_and_list_follow_v35_byte_widths_and_source_order(self):
        for attr, value in ((1, b'\0'), (16, b'\x80'), (17, b'\x80')):
            self.assertEqual(self.send(path=bytes.fromhex('2043240130')+bytes((attr,))),
                             bytes.fromhex('8e000000')+value)
        self.assertEqual(self.send(3, bytes.fromhex('20432401'), struct.pack('<4H', 3, 17, 1, 16)),
                         bytes.fromhex('830000000300110000008001000000001000000080'))

    def test_native_requested_list_reports_all_unknown_measurements_and_labels(self):
        order = (*range(1, 29), 102, 103, 104, 105)
        values = self.settings().attributes()
        expected = struct.pack('<H', len(order))
        for attr in order:
            expected += struct.pack('<HH', attr, 0 if attr in values else 0x14) + values.get(attr, b'')
        self.assertEqual(self.send(3, bytes.fromhex('20432401'), struct.pack('<33H', 32, *order)),
                         bytes.fromhex('83000a00')+expected)
        gap = self.endpoint.state()['attribute_gaps'][0]
        self.assertEqual(gap['class_name'], 'Time Sync')
        self.assertEqual([row['id'] for row in gap['attributes']], [a for a in order if a not in values])
        self.assertEqual(gap['attributes'][0]['name'], 'Synchronization status')
        self.assertEqual(self.send(path=bytes.fromhex('204324013002')), bytes.fromhex('8e001400'))

    def test_class_discovery_describes_one_model_instance(self):
        for attr in (1, 2, 3):
            self.assertEqual(self.send(path=bytes.fromhex('2043240030')+bytes((attr,))),
                             bytes.fromhex('8e0000000100'))
        result = self.send(1, bytes.fromhex('20022401'))
        ids = struct.unpack('<'+'H'*((len(result)-4)//2), result[4:])
        self.assertEqual(ids[0], len(ids)-1)
        self.assertEqual(ids.count(0x43), 1)

    def test_paths_payloads_and_setters_cannot_change_configuration_or_memory(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        settings = self.app.engine.project.time_sync.description()
        for path, service, data, status in (
                (bytes.fromhex('2043'), 0x0E, b'', 4),
                (bytes.fromhex('20432402'), 0x0E, b'', 5),
                (symbol_path('Program:MainProgram')+bytes.fromhex('20432401'), 0x0E, b'', 4),
                (bytes.fromhex('20682401')+bytes.fromhex('20432401'), 0x0E, b'', 4),
                (bytes.fromhex('204324013001'), 0x0E, b'\0', 0x15),
                (bytes.fromhex('20432401'), 3, bytes.fromhex('02000100'), 0x13),
                (bytes.fromhex('20432401'), 3, bytes(2), 3),
                (bytes.fromhex('204324013001'), 0x10, b'\1', 8),
                (bytes.fromhex('20432401'), 4, bytes.fromhex('010001000100'), 8),
                (bytes.fromhex('20432401'), 1, b'', 8)):
            self.assertEqual(self.send(service, path, data)[2], status, (path.hex(), service))
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.app.engine.project.time_sync.description(), settings)

    def test_project_replacement_removes_previous_settings_and_stopped_state(self):
        self.assertIsNone(self.endpoint.state()['time_sync'])
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.assertEqual(self.send(), bytes.fromhex('8e001400'))
        self.app.endpoint = None
        self.assertIsNone(self.app.connectivity()['time_sync'])


if __name__ == '__main__':
    unittest.main()
