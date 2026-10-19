"""Source-bound Symbol metadata links to backed, scoped scalar storage."""
import copy
import struct
import tempfile
import unittest

from logixlab import data_table, symbol_metadata
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import ModelError, Tag
from logixlab.native_symbols import NativeSymbols, Symbol
from logixlab.server import Application


class SymbolStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'TextLab'})
        self.endpoint = Endpoint(self.app, 0, True, 'logix-v35-l85e')
        self.router = self.endpoint.router
        self.bind(Symbol('', 0, 'Step', 3))

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def bind(self, *symbols):
        self.app.native_symbols = NativeSymbols('1' * 64, self.app.engine.project.sha256, symbols)

    def add(self, name, value=1, **fields):
        tag = Tag(name, 'DINT', value, **fields)
        self.app.engine.project.tags[tag.key.lower()] = tag
        self.app.engine.memory.values[tag.key.lower()] = copy.deepcopy(value)
        return tag

    def cip(self, service, path=bytes.fromhex('206b2403'), data=b'', limit=480):
        return self.router.handle(bytes((service, len(path) // 2)) + path + data, Session(), limit=limit)

    def test_scalar_attribute_list_has_exact_widths_and_backed_links(self):
        cell = self.router.scalar_storage().by_ref['step']
        values = {1: b'\4\0Step', 2: struct.pack('<H', 0xC4),
                  3: struct.pack('<I', cell.value_address), 5: struct.pack('<I', cell.symbol_address),
                  6: bytes(4), 7: struct.pack('<H', 4), 8: bytes(12), 9: b'\0',
                  10: b'\0', 11: b'\0', 12: struct.pack('<I', 3), 14: bytes(4)}
        order = (1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 14, 9)
        expected = struct.pack('<H', len(order))
        for attr in order:
            self.assertEqual(self.cip(0x0E, bytes.fromhex('206b240330') + bytes((attr,))),
                             b'\x8E\0\0\0' + values[attr])
            expected += struct.pack('<HH', attr, 0) + values[attr]
        self.assertEqual(self.cip(3, data=struct.pack('<13H', len(order), *order)),
                         b'\x83\0\0\0' + expected)
        space = self.router.scalar_storage()
        self.assertEqual(space.read(cell.symbol_address, 32, self.app.engine.memory.read),
                         struct.pack('<IIHHI4I', cell.value_address, cell.address, 0xC4, 4, 3, 0, 0, 0, 0))
        self.app.engine.memory.write('Step', 314)
        self.assertEqual(space.read(cell.value_address, 4, self.app.engine.memory.read), struct.pack('<i', 314))

    def test_each_atomic_width_matches_its_backed_value(self):
        for dtype, fmt, value in (('BOOL', 'B', True), ('SINT', 'b', -7), ('INT', 'h', -300),
                ('DINT', 'i', -12345), ('LINT', 'q', -(1 << 40)), ('USINT', 'B', 250),
                ('UINT', 'H', 65000), ('UDINT', 'I', 1 << 31), ('ULINT', 'Q', 1 << 63), ('REAL', 'f', 2.5)):
            tag = self.add('Width' + dtype, value); tag.dtype = dtype
            self.bind(Symbol('', 0, tag.name, 3))
            cell = self.router.scalar_storage().by_ref[tag.name.lower()]
            self.assertEqual(self.cip(0x0E, bytes.fromhex('206b24033007'))[4:], struct.pack('<H', struct.calcsize(fmt)))
            self.assertEqual(self.router.scalar_storage().read(cell.value_address, cell.size, self.app.engine.memory.read),
                             struct.pack('<' + fmt, value))

    def test_constants_aliases_and_arrays_keep_storage_unavailable(self):
        self.add('Const', constant=True); self.add('Alias', None, alias='Step')
        for name in ('Const', 'Alias', 'Values'):
            self.bind(Symbol('', 0, name, 3))
            for attr in (3, 5, 6, 7, 12, 14):
                self.assertEqual(self.cip(0x0E, bytes.fromhex('206b240330') + bytes((attr,)))[2], 0x14, (name, attr))
            self.assertEqual(self.cip(0x0E, bytes.fromhex('206b2403300b'))[4:], bytes((name == 'Const',)))
            self.assertEqual(self.cip(0x0E, bytes.fromhex('206b24033009'))[4:], b'\0')

    def test_scoped_same_ids_get_distinct_storage_and_actual_table_links(self):
        self.add('Local', 42, scope='MainProgram')
        self.bind(Symbol('', 0, 'Step', 3), Symbol('MainProgram', 17, 'Local', 3))
        space = self.router.scalar_storage()
        self.assertNotEqual(space.by_ref['step'].symbol_address, space.by_ref['program:mainprogram.local'].symbol_address)
        for prefix in (symbol_path('Program:MainProgram'), bytes.fromhex('20682411')):
            self.assertEqual(self.cip(0x0E, prefix + bytes.fromhex('206b24033005'))[4:],
                             struct.pack('<I', space.by_ref['program:mainprogram.local'].symbol_address))
            self.assertEqual(self.cip(0x0E, prefix + bytes.fromhex('206b2403300c'))[4:], struct.pack('<I', 3))
        self.app.engine.project.programs['MainProgram']['class'] = 'Safety'
        self.assertEqual(self.cip(0x0E, bytes.fromhex('20682411206b24033005'))[2], 0x0F)

    def test_enumeration_uses_same_descriptors_and_rejects_unavailable_fields(self):
        attrs = (5, 3, 6, 7, 12, 9, 11, 14)
        values = self.router.symbol_attributes(self.router.symbols()[0])
        payload = struct.pack('<9H', len(attrs), *attrs)
        expected = struct.pack('<I', 3) + b''.join(values[a] for a in attrs)
        self.assertEqual(self.cip(0x55, data=payload), b'\xD5\0\0\0' + expected)
        self.assertEqual(self.cip(0x55, data=payload, limit=len(expected) + 3)[2], 0x1B)
        self.bind(Symbol('', 0, 'Values', 3))
        self.assertEqual(self.cip(0x55, data=payload)[2], 0x14)

    def test_read_only_properties_do_not_change_when_endpoint_writes_are_disabled(self):
        self.app.engine.project.tags['step'].external_access = 'Read Only'
        for enabled in (True, False):
            self.endpoint.allow_writes = enabled
            self.assertEqual(self.cip(0x0E, bytes.fromhex('206b2403300a'))[4:], b'\2')
            self.assertEqual(self.cip(0x0E, bytes.fromhex('206b2403300b'))[4:], b'\0')
            self.assertEqual(self.cip(0x0E, bytes.fromhex('206b24033006'))[4:], bytes(4))

    def test_symbol_bank_boundaries_and_padding_cannot_expose_other_bytes(self):
        space = self.router.scalar_storage(); cell = space.by_ref['step']
        for address, count in ((cell.symbol_address - 1, 1), (cell.symbol_address + 31, 2),
                               (cell.symbol_address + 32, 1), (cell.symbol_address, 33)):
            with self.assertRaises(ModelError): space.read(address, count, self.app.engine.memory.read)
        self.assertEqual(space.read(cell.symbol_address + 8, 4, self.app.engine.memory.read), struct.pack('<HH', 0xC4, 4))
        self.assertEqual(len({cell.address, cell.value_address, cell.symbol_address}), 3)

    def test_source_access_changes_and_replacement_rebuild_or_reject_storage(self):
        before = self.router.scalar_storage()
        self.app.engine.project.tags['step'].constant = True
        self.assertIsNot(self.router.scalar_storage(), before)
        self.assertEqual(self.cip(0x0E, bytes.fromhex('206b24033003'))[2], 0x14)
        self.app.native_symbols.source_l5x_sha256 = '2' * 64
        self.assertEqual(self.cip(0x0E, bytes.fromhex('206b24033001'))[2], 0x0C)
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.assertNotIn('step', self.router.scalar_storage().by_ref)

    def test_unknown_fields_bad_payloads_and_setters_preserve_values(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        for attr in (4, 13, 255):
            self.assertEqual(self.cip(0x0E, bytes.fromhex('206b240330') + bytes((attr,)))[2], 0x14)
        mixed = self.cip(3, data=struct.pack('<4H', 3, 7, 4, 12))
        self.assertEqual(mixed, b'\x83\0\x0A\0' + struct.pack('<HHHHHHHHI', 3, 7, 0, 4, 4, 0x14, 12, 0, 3))
        for service in (4, 0x10, 0x4D, 0x53, 0x4E):
            self.assertNotEqual(self.cip(service, data=bytes(8))[2], 0)
        self.assertEqual(self.cip(0x0E, bytes.fromhex('206b24033005'), b'\0')[2], 0x15)
        self.assertEqual(self.cip(3, data=b'\2\0\5\0')[2], 0x13)
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertFalse(symbol_metadata.description()['physical_addresses'])


if __name__ == '__main__':
    unittest.main()
