"""Class reads describe exactly the catalogs reachable by instance discovery."""
import copy
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import Tag
from logixlab.native_symbols import NativeSymbols, Symbol
from logixlab.server import Application


class CatalogMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'StructureLab'})
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e')
        self.router = self.endpoint.router

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def call(self, service, path, payload=b'', limit=480):
        return self.router.handle(bytes((service, len(path)//2)) + path + payload,
                                  Session(), limit=limit)

    def class_read(self, class_id, attribute, prefix=b''):
        return self.call(0x0E, prefix + bytes((0x20, class_id, 0x24, 0, 0x30, attribute)))

    def assert_catalog(self, class_id, ids, prefix=b''):
        for attribute, value in ((1, struct.pack('<H', 1)),
                                 (2, struct.pack('<I', max(ids, default=0))),
                                 (3, struct.pack('<I', len(ids)))):
            self.assertEqual(self.class_read(class_id, attribute, prefix), b'\x8E\0\0\0' + value)
        self.assertEqual(self.call(0x4B, prefix + bytes((0x20, class_id, 0x24, 0))),
                         b'\xCB\0\0\0' + b''.join(struct.pack('<I', i) for i in ids))

    def test_symbol_maximum_is_sparse_and_counts_only_visible_instances(self):
        symbols = (Symbol('', 0, 'Command', 70000), Symbol('', 0, 'Machine', 3),
                   Symbol('', 0, 'Machines', 12))
        self.app.native_symbols = NativeSymbols('1'*64, self.app.engine.project.sha256, symbols)
        self.assert_catalog(0x6B, [3, 12, 70000])
        self.app.engine.project.tags['command'].external_access = 'None'
        self.assert_catalog(0x6B, [3, 12])
        # Alias symbols still belong to Symbol discovery, but have no own table.
        alias = Tag('Alias', 'DINT', None, alias='Machine.Axis.Command')
        self.app.engine.project.tags['alias'] = alias
        self.app.native_symbols = None
        self.assert_catalog(0x6B, [s['id'] for s in self.router.symbols()])
        self.assertEqual(len(self.router.symbols()), len(self.router.data_tables()) + 1)

    def test_empty_symbol_and_template_classes_have_zero_maximum_and_count(self):
        for tag in self.app.engine.project.tags.values():
            tag.external_access = 'None'
        self.assert_catalog(0x6B, [])
        self.assert_catalog(0x6C, [])

    def test_symbol_classes_follow_both_program_scope_forms_and_access_checks(self):
        for scope, value in (('MainProgram', 1), ('OtherProgram', 2)):
            self.app.engine.project.programs.setdefault(scope, {'class': 'Standard'})
            tag = Tag('Local', 'DINT', value, scope=scope)
            self.app.engine.project.tags[tag.key.lower()] = tag
            self.app.engine.memory.values[tag.key.lower()] = value
        self.app.native_symbols = NativeSymbols('1'*64, self.app.engine.project.sha256,
            (Symbol('', 0, 'Command', 900), Symbol('MainProgram', 42, 'Local', 70000),
             Symbol('OtherProgram', 43, 'Local', 5)))
        self.assert_catalog(0x6B, [900])
        for prefix in (symbol_path('Program:mainprogram'), bytes.fromhex('2068242a')):
            self.assert_catalog(0x6B, [70000], prefix)
        self.assert_catalog(0x6B, [5], symbol_path('Program:OtherProgram'))
        self.app.engine.project.programs['MainProgram']['class'] = 'Safety'
        self.assertEqual(self.class_read(0x6B, 3, bytes.fromhex('2068242a'))[2], 0x0F)
        self.assertEqual(self.class_read(0x6B, 3, symbol_path('Program:Missing'))[2], 5)

    def test_template_metadata_and_enumeration_include_nested_exposed_types(self):
        catalog = self.router.templates()
        ids = sorted(t.instance for t in catalog.types.values())
        self.assertEqual(len(ids), 2)
        self.assert_catalog(0x6C, ids)
        for instance in ids:
            path = bytes.fromhex('206c2500') + struct.pack('<H', instance)
            self.assertEqual(self.call(0x0E, path + b'\x30\1')[2], 0)
        # The child remains reachable through a visible parent without a root
        # tag of its own; its ID must appear in both class metadata and lists.
        self.assertEqual({t.name for t in self.router.exposed_templates().values()},
                         {'AxisState', 'MachineState'})

    def test_unreferenced_private_and_unsupported_types_do_not_leak_through_class_reads(self):
        project = self.app.engine.project
        project.udts['unused'] = E.fromstring('<DataType Name="Unused"><Members>'
            '<Member Name="Value" DataType="DINT"/></Members></DataType>')
        project.udts['unsupported'] = E.fromstring('<DataType Name="Unsupported"><Members>'
            '<Member Name="Value" DataType="UnknownType"/></Members></DataType>')
        all_types = self.router.templates().types
        self.assertIn('unused', all_types)
        self.assertNotIn('unsupported', all_types)
        ids = sorted(t.instance for key, t in all_types.items() if key != 'unused')
        self.assert_catalog(0x6C, ids)
        unused = all_types['unused'].instance
        self.assertEqual(self.call(0x0E, bytes.fromhex('206c2500') + struct.pack('<H', unused) + b'\x30\1')[2], 5)
        for name in ('machine', 'machines'):
            project.tags[name].external_access = 'None'
        self.assert_catalog(0x6C, [])

    def test_class_lists_preserve_requested_order_duplicates_and_missing_status(self):
        for class_id in (0x6B, 0x6C):
            path = bytes((0x20, class_id, 0x24, 0))
            count = struct.unpack('<I', self.class_read(class_id, 3)[4:])[0]
            result = self.call(3, path, struct.pack('<5H', 4, 3, 1, 3, 99))
            expected = (struct.pack('<HHHI', 4, 3, 0, count) + struct.pack('<3H', 1, 0, 1)
                        + struct.pack('<HHIHH', 3, 0, count, 99, 0x14))
            self.assertEqual(result, b'\x83\0\x0A\0' + expected)

    def test_class_reads_reject_bad_paths_payloads_writes_and_small_reply_budgets(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        for class_id in (0x6B, 0x6C):
            path = bytes((0x20, class_id, 0x24, 0))
            self.assertEqual(self.call(0x0E, path+b'\x30\1', b'x')[2], 0x15)
            self.assertEqual(self.call(3, path, b'\2\0\1\0')[2], 0x13)
            self.assertEqual(self.call(3, path, b'\0\0')[2], 3)
            self.assertEqual(self.call(0x0E, path+b'\x30\1', limit=5)[2], 0x1B)
            self.assertNotEqual(self.call(0x10, path+b'\x30\1', b'\2\0')[2], 0)
            self.assertEqual(self.call(0x0E, bytes((0x20, class_id, 0x30, 1)))[2], 4)
        for prefix in (symbol_path('Program:MainProgram'), bytes.fromhex('20682401')):
            self.assertEqual(self.class_read(0x6C, 1, prefix)[2], 4)
        self.assertEqual(self.app.engine.memory.values, before)


if __name__ == '__main__':
    unittest.main()
