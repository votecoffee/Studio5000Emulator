"""An empty motion catalog requires complete, motion-free source evidence."""
import copy
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import Project
from logixlab.motion_catalog import MotionCatalog
from logixlab.server import Application


class MotionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e')
        self.root = E.parse(self.app.engine.project.path).getroot()

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def catalog(self, root=None):
        root = self.root if root is None else root
        return MotionCatalog.from_source(root, root.find('Controller'))

    def call(self, path=bytes.fromhex('20b02400'), data=b'', service=0x4B):
        return self.endpoint.router.handle(bytes((service, len(path)//2))+path+data, Session())

    def test_complete_motion_free_project_has_empty_catalog_and_zero_cursor_results(self):
        self.assertTrue(self.catalog().empty)
        self.assertEqual(self.app.engine.project.motion_catalog.description()['instance_count'], 0)
        for path in ('20b02400', '20b02401', '20b02600ffffffff'):
            self.assertEqual(self.call(bytes.fromhex(path)), b'\xCB\0\0\0')
            self.assertEqual(self.call(bytes.fromhex(path.replace('20b0', '20b1'))), b'\xCB\0\0\0')
            self.assertEqual(self.call(bytes.fromhex(path.replace('20b0', '21002b03'))), b'\xCB\0\0\0')

    def test_context_missing_or_ambiguous_controller_tags_do_not_prove_empty(self):
        for change in ('context', 'unknown_context', 'context_controller', 'duplicate_controller', 'context_tags', 'missing', 'duplicate', 'unknown_child', 'unknown_type', 'context_tag'):
            with self.subTest(change=change):
                root = copy.deepcopy(self.root);controller = root.find('Controller')
                if change == 'context':root.set('ContainsContext', 'true')
                elif change == 'unknown_context':root.attrib.pop('ContainsContext')
                elif change == 'context_controller':controller.set('Use', 'Context')
                elif change == 'duplicate_controller':E.SubElement(root, 'Controller')
                elif change == 'context_tags':controller.find('Tags').set('Use', 'Context')
                elif change == 'missing':controller.remove(controller.find('Tags'))
                elif change == 'duplicate':E.SubElement(controller, 'Tags')
                elif change == 'unknown_child':E.SubElement(controller.find('Tags'), 'EncryptedTags')
                elif change == 'unknown_type':controller.find('./Tags/Tag').attrib.pop('DataType')
                else:controller.find('./Tags/Tag').set('Use', 'Context')
                self.assertFalse(self.catalog(root).empty)

    def test_motion_type_or_configuration_is_detected_before_runtime_type_filtering(self):
        for mode in ('type', 'axis_type', 'coordinate_type', 'format', 'axis_format', 'coordinate_format', 'parameters', 'axis_parameters', 'coordinate_parameters', 'extension', 'namespace'):
            with self.subTest(mode=mode):
                root = copy.deepcopy(self.root);controller = root.find('Controller')
                tag = controller.find('./Tags/Tag')
                if mode == 'type':tag.set('DataType', 'MOTION_GROUP')
                elif mode == 'axis_type':tag.set('DataType', 'AXIS_CIP_DRIVE')
                elif mode == 'coordinate_type':tag.set('DataType', 'COORDINATE_SYSTEM')
                elif mode == 'format':E.SubElement(tag, 'Data', Format='MotionGroup')
                elif mode == 'axis_format':E.SubElement(tag, 'Data', Format='Axis')
                elif mode == 'coordinate_format':E.SubElement(tag, 'Data', Format='CoordinateSystem')
                elif mode == 'parameters':E.SubElement(tag, 'MotionGroupParameters')
                elif mode == 'axis_parameters':E.SubElement(tag, 'AxisParameters')
                elif mode == 'coordinate_parameters':E.SubElement(tag, 'CoordinateSystemParameters')
                elif mode == 'extension':E.SubElement(controller, 'MotionGroups')
                else:E.SubElement(controller, '{urn:extension}Tags')
                self.assertFalse(self.catalog(root).empty)
                self.assertIsNone(self.catalog(root).description()['instance_count'])

    def test_motion_source_and_source_replacement_never_return_false_empty(self):
        tag = self.root.find('./Controller/Tags/Tag');tag.set('DataType', 'MOTION_GROUP')
        path = Path(self.tmp.name)/'motion.L5X';E.ElementTree(self.root).write(path)
        project = Project(path)
        self.assertFalse(project.motion_catalog.empty)
        self.app.engine.project = project
        self.assertEqual(self.call()[2], 0x0C)
        self.assertEqual(self.call(bytes.fromhex('20b12400'))[2], 0x0C)
        self.assertEqual(self.call(bytes.fromhex('21002b032400'))[2], 0x0C)
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.assertEqual(self.call(), b'\xCB\0\0\0')

    def test_invalid_paths_payload_and_mutations_preserve_values(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        for path, data, service, status in ((bytes.fromhex('20b0'), b'', 0x4B, 4),
                (bytes.fromhex('20b024003001'), b'', 0x4B, 4),
                (bytes.fromhex('20b02400'), b'x', 0x4B, 0x15),
                (symbol_path('Program:MainProgram')+bytes.fromhex('20b02400'), b'', 0x4B, 4),
                (bytes.fromhex('20b02401'), b'', 0x0E, 8),
                (bytes.fromhex('20b02401'), b'\0', 0x10, 8)):
            self.assertEqual(self.call(path, data, service)[2], status)
        self.assertEqual(self.app.engine.memory.values, before)


if __name__ == '__main__':unittest.main()
