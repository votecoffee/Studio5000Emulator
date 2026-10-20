"""Synthetic program records, manifest binding and read-only Program discovery."""
import copy
import gzip
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logixlab import native_programs
from logixlab.ethernetip import Endpoint, Session, logical, symbol_path
from logixlab.model import ModelError
from logixlab.native_symbols import NativeSymbols, Symbol
from logixlab.server import Application


def record(name='MainProgram', instance=1234, version=19, kind=0xFAFA):
    body = bytes(8) + struct.pack('<7H', version, 0x68, instance, 0, 0, 0, 0)
    header = bytearray(148)
    struct.pack_into('<I', header, 0, len(header) + len(body))
    struct.pack_into('<H', header, 10, 256)
    struct.pack_into('<II', header, 16, 0x12345678, 0x23456789)
    encoded = name.encode('utf-16le') + bytes(2)
    header[24:24+len(encoded)] = encoded
    value = bytes(header) + body
    return struct.pack('<HI', kind, len(value)+6) + value


def database(*records, tail=b''):
    data = bytearray(512) + b''.join(records)
    logical_size = len(data)
    data += tail
    struct.pack_into('<I', data, 0, len(data)-1)
    struct.pack_into('<II', data, 8, logical_size-1, 512)
    return bytes(data)


def container(comps, xml=None, compressed=True):
    xml = xml or b'<LogixTagInfo><SchemaVersion Major="1" Minor="0"/><Tags/><Programs><Program Name="MainProgram"><Tags/></Program></Programs></LogixTagInfo>'
    values = [('TagInfo.XML', xml), ('Comps.Dat', comps)]
    payload = b'\r\n'; directory = b''
    for name, value in values:
        value = gzip.compress(value, mtime=0) if compressed else value
        directory += name.encode('utf-16le').ljust(520, b'\0') + struct.pack('<II', len(value), len(payload))
        payload += value
    return payload + directory + struct.pack('<II', len(values), 0)


class NativeProgramTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.acd = self.root/'source.ACD'
        self.acd.write_bytes(container(database(record())))
        self.app = Application(self.root/'app')
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.digest = self.app.engine.project.sha256
        self.router = Endpoint(self.app, 0, False, 'logix-v35-l85e').router

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def call(self, service, path, data=b'', limit=480):
        return self.router.handle(bytes((service, len(path)//2))+path+data, Session(), limit=limit)

    def bind(self):
        self.app.native_symbols = NativeSymbols.from_acd(self.acd, self.digest)
        return self.app.native_symbols

    def test_empty_program_is_bound_without_synthetic_local_tags_and_roundtrips(self):
        original = self.acd.read_bytes()
        for compressed in (False, True):
            self.acd.write_bytes(container(database(record()), compressed=compressed))
            catalog = self.bind()
            self.assertEqual(catalog.programs, {'mainprogram': 1234})
            self.assertEqual(catalog.by_key, {})
            self.assertEqual(catalog.source_acd_sha256, hashlib.sha256(self.acd.read_bytes()).hexdigest())
            self.assertEqual(NativeSymbols.from_manifest(catalog.manifest(), self.digest).manifest(), catalog.manifest())
            self.assertIsNone(catalog.description()['program_inventory_error'])
        self.acd.write_bytes(original); self.bind()
        self.assertEqual(self.acd.read_bytes(), original)

    def test_database_ignores_padding_free_records_and_inactive_physical_tail(self):
        data = database(record(), record(instance=55, kind=0xFDFD),
                        tail=record(instance=66))
        self.assertEqual(native_programs.program_paths(data, ['MainProgram']), [{'name':'MainProgram', 'instance':1234}])
        self.assertEqual(native_programs.program_paths(database(record(), record()), ['mainprogram']),
                         [{'name':'mainprogram', 'instance':1234}])

    def test_ambiguous_historical_paths_missing_programs_and_conflicting_ids_are_rejected(self):
        cases = ((database(record(), record(instance=5)), ['MainProgram']),
                 (database(record('Other')), ['MainProgram']),
                 (database(record(), record('Other')), ['MainProgram', 'Other']),
                 (database(record()), ['MainProgram', 'MAINPROGRAM']))
        for data, names in cases:
            with self.subTest(names=names), self.assertRaises(ModelError):
                native_programs.program_paths(data, names)

    def test_unsupported_program_format_path_and_legacy_header_are_withheld(self):
        for value in (record(version=18), record(instance=0)):
            with self.assertRaises(ModelError):native_programs.program_paths(database(value), ['MainProgram'])
        data = bytearray(database(record()))
        struct.pack_into('<I', data, 512+6+12, 1)
        with self.assertRaisesRegex(ModelError, 'layout'):native_programs.program_paths(data, ['MainProgram'])

    def test_bad_database_sizes_markers_lengths_and_limits_fail_closed(self):
        good = database(record())
        variants = [good[:-1], b'', good[:24]]
        for offset, value, fmt in ((0, len(good), '<I'), (8, len(good)+10, '<I'),
                                   (12, 10, '<I'), (512, 0x1234, '<H'),
                                   (514, 0, '<I'), (514, len(good), '<I'),
                                   (518, 147, '<I'), (518, len(good), '<I')):
            data = bytearray(good);struct.pack_into(fmt, data, offset, value);variants.append(data)
        for data in variants:
            with self.subTest(data=bytes(data[:12])), self.assertRaises(ModelError):
                native_programs.program_paths(data, ['MainProgram'])
        with patch.object(native_programs, 'MAX_RECORDS', 0), self.assertRaises(ModelError):
            native_programs.program_paths(good, ['MainProgram'])
        with patch.object(native_programs, 'MAX_BYTES', 50), self.assertRaises(ModelError):
            native_programs.read_programs(self.acd, ['MainProgram'])

    def test_bad_program_inventory_preserves_valid_taginfo_ids_with_a_diagnostic(self):
        xml = b'<LogixTagInfo><SchemaVersion Major="1" Minor="0"/><Tags><Tag Name="StartPB" IOI="@107 3 0 0 0 0@"/></Tags><Programs><Program Name="MainProgram"><Tags/></Program></Programs></LogixTagInfo>'
        self.acd.write_bytes(container(database(record(version=1)), xml))
        catalog = self.bind()
        self.assertEqual(catalog.by_key['startpb'].instance, 3)
        self.assertEqual(catalog.programs, {})
        self.assertIn('Unsupported', catalog.description()['program_inventory_error'])
        self.assertNotIn('programs', catalog.manifest())
        self.assertEqual(self.call(0x4B, bytes.fromhex('20682400'))[2], 0x0C)
        xml = xml.replace(b'<Tags/></Program>', b'<Tags><Tag Name="Local" IOI="@104 50 107 4 0 0@"/></Tags></Program>')
        self.acd.write_bytes(container(database(record()), xml))
        catalog = self.bind()
        self.assertEqual(catalog.programs, {'mainprogram':50})
        self.assertEqual(catalog.by_key['program:mainprogram.local'].instance, 4)
        self.assertEqual(catalog.explicit_programs, [])
        self.assertIn('Conflicting', catalog.program_inventory_error)

    def test_acd_drift_is_rejected_instead_of_combining_two_sources(self):
        with patch('logixlab.native_symbols.read_programs', return_value=('2'*64, [])):
            with self.assertRaisesRegex(ModelError, 'ACD changed'):NativeSymbols.from_acd(self.acd, self.digest)

    def test_explicit_program_manifest_conflicts_types_and_stale_source_are_rejected(self):
        good = self.bind().manifest()
        for programs in (None, [{'name':'MainProgram','instance':True}],
                         [{'name':'Bad name','instance':1}],
                         [{'name':'A','instance':1},{'name':'B','instance':1}],
                         [{'name':'A','instance':1},{'name':'a','instance':2}],
                         [{'name':'A','instance':1,'extra':0}]):
            with self.subTest(programs=programs), self.assertRaises(ModelError):
                NativeSymbols.from_manifest({**good, 'programs': programs}, self.digest)
        with self.assertRaises(ModelError):NativeSymbols.from_manifest({**good, 'program_inventory_error':'Unavailable'}, self.digest)
        with self.assertRaises(ModelError):NativeSymbols.from_manifest(good, '0'*64)
        with self.assertRaisesRegex(ModelError, 'Conflicting'):
            NativeSymbols('1'*64, self.digest, [Symbol('MainProgram', 50, 'Local', 1)], good['programs'])

    def test_class_metadata_instance_names_and_empty_child_scopes_use_source_ids(self):
        self.bind(); instance = bytes.fromhex('20682500') + struct.pack('<H', 1234)
        self.assertEqual(self.call(0x4B, bytes.fromhex('20682400')), b'\xCB\0\0\0'+struct.pack('<I', 1234))
        self.assertEqual(self.call(0x4B, bytes.fromhex('20682500')+struct.pack('<H', 1235)), b'\xCB\0\0\0')
        for attribute, expected in ((1, b'\1\0'), (2, struct.pack('<I', 1234)), (3, struct.pack('<I', 1))):
            self.assertEqual(self.call(0x0E, bytes.fromhex('2068240030')+bytes((attribute,))), b'\x8E\0\0\0'+expected)
        self.assertEqual(self.call(0x0E, instance+b'\x30\x1C'), b'\x8E\0\0\0'+struct.pack('<I', 11)+b'MainProgram')
        self.assertEqual(self.call(0x0E, instance+bytes.fromhex('206b24003003')), b'\x8E\0\0\0'+bytes(4))
        self.assertEqual(self.call(0x0E, instance+bytes.fromhex('206a24003003')), b'\x8E\0\0\0'+bytes(4))
        self.assertEqual(self.call(0x0E, bytes.fromhex('20682401301c'))[2], 5)

    def test_unbound_incomplete_safety_and_stale_program_inventories_are_not_empty_success(self):
        for bindings in (None, NativeSymbols('1'*64, self.digest, [], [])):
            self.app.native_symbols = bindings
            self.assertEqual(self.call(0x4B, bytes.fromhex('20682400'))[2], 0x0C)
            self.assertEqual(self.call(0x0E, bytes.fromhex('206824003001')), b'\x8E\0\0\0\1\0')
            self.assertEqual(self.call(0x0E, bytes.fromhex('206824003003'))[2], 0x14)
        self.bind(); self.app.engine.project.programs['MainProgram']['class'] = 'Safety'
        self.assertEqual(self.call(0x4B, bytes.fromhex('20682400')), b'\xCB\0\0\0')
        self.assertEqual(self.call(0x0E, bytes.fromhex('20682500')+struct.pack('<H', 1234)+b'\x30\x1C')[2], 5)
        self.app.engine.project.sha256 = '0'*64
        self.assertEqual(self.call(0x4B, bytes.fromhex('20682400'))[2], 0x0C)

    def test_bad_requests_write_denials_and_reply_limits_preserve_memory(self):
        self.bind(); before = copy.deepcopy(self.app.engine.memory.values)
        path = bytes.fromhex('20682400')
        self.assertEqual(self.call(0x4B, path, limit=7)[2], 0x1B)
        self.assertEqual(self.call(0x4B, path, b'x')[2], 0x15)
        self.assertEqual(self.call(0x4B, path+b'\x30\1')[2], 4)
        self.assertEqual(self.call(0x4B, symbol_path('Program:MainProgram')+path)[2], 4)
        self.assertEqual(self.call(0x0E, bytes.fromhex('2068'))[2], 4)
        self.assertEqual(self.call(0x0E, path+b'\x30\1', b'x')[2], 0x15)
        self.assertEqual(self.call(3, path, b'\2\0\3\0')[2], 0x13)
        self.assertEqual(self.call(0x10, path+b'\x30\1', b'\2\0')[2], 8)
        self.assertEqual(self.app.engine.memory.values, before)


if __name__ == '__main__':unittest.main()
