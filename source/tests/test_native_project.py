"""Synthetic ACD containers and source-bound native comparison behavior."""
import base64
import gzip
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from logixlab.native_project import NativeProjectIdentity
from logixlab.importers import convert_acd
from logixlab.model import ModelError
from logixlab.server import Application
from logixlab.ethernetip import Endpoint, Session


def varint(value):
    result = bytearray()
    while value > 127: result.append((value & 127) | 128); value >>= 7
    result.append(value); return bytes(result)


FIELDS = {3: 0x10203040, 8: 0x20304050, 9: 0x30405060, 10: 0x40506070, 11: 7, 12: 3}


def container(fields=None, compressed=True, header=None):
    if header is None: header = b''.join(varint(n*8)+varint(v) for n, v in (FIELDS if fields is None else fields).items())
    stream = struct.pack('<I', len(header))+header+b'\0'*4
    if compressed: stream = gzip.compress(stream, mtime=0)
    name = 'OfflineChangelog.Dat'.encode('utf-16le').ljust(520, b'\0')
    return b'\r\n'+stream+name+struct.pack('<IIII', len(stream), 2, 1, 0)


class NativeProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.acd = self.root/'synthetic.ACD'; self.acd.write_bytes(container())
        self.l5x = Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
        self.digest = hashlib.sha256(self.l5x.read_bytes()).hexdigest()

    def tearDown(self): self.temp.cleanup()

    def identity(self): return NativeProjectIdentity.from_acd(self.acd, self.digest)

    def test_reads_compressed_and_plain_headers_without_modifying_input(self):
        for compressed in (False, True):
            original = container(compressed=compressed); self.acd.write_bytes(original)
            identity = self.identity(); attributes = identity.attributes()
            self.assertEqual(self.acd.read_bytes(), original)
            self.assertEqual(identity.source_acd_sha256, hashlib.sha256(original).hexdigest())
            self.assertEqual(struct.unpack('<HHIIHHIIII', b''.join(attributes.values())),
                             (7, 3, FIELDS[10], FIELDS[8], 0, 0, 2, FIELDS[3], 65537, FIELDS[9]))
            self.assertEqual(NativeProjectIdentity.from_manifest(identity.manifest(), self.digest), identity)
            self.assertFalse(identity.description()['firmware_authentication'])

    def test_rejects_missing_duplicate_wrong_wire_and_overflow_fields(self):
        bad = [container(fields={3: 1}), container(header=b'\x18\1\x18\2'),
               container(header=b'\x19\1'), container(fields={**FIELDS, 11: 65536}),
               container(header=b'\x18'+b'\xff'*6), container(header=b'\x2a\x7fabc')]
        for data in bad:
            self.acd.write_bytes(data)
            with self.assertRaises(ModelError): self.identity()

    def test_rejects_container_offsets_duplicates_and_bounded_header_lengths(self):
        good = container(); table = len(good)-536
        duplicate = good[:table]+good[table:-8]*2+struct.pack('<II', 2, 0)
        bad_offset = bytearray(good); struct.pack_into('<I', bad_offset, len(good)-12, len(good))
        oversized = b'\r\n'+struct.pack('<I', 65537)+good[table:table+520]+struct.pack('<IIII', 4, 2, 1, 0)
        for data in (b'bad', duplicate, bad_offset, oversized, good[:-1]):
            self.acd.write_bytes(data)
            with self.assertRaises((ModelError, UnicodeError)): self.identity()

    def test_manifest_checks_exact_fields_hashes_and_integer_ranges(self):
        good = self.identity().manifest()
        for manifest in ({**good, 'extra': 1}, {**good, 'online_index': True},
                         {**good, 'project_uid': -1}, {**good, 'source_acd_sha256': 'bad'}):
            with self.assertRaises(ModelError): NativeProjectIdentity.from_manifest(manifest, self.digest)
        with self.assertRaisesRegex(ModelError, 'L5X bytes'):
            NativeProjectIdentity.from_manifest(good, '0'*64)

    def test_import_carries_identity_and_failed_rebinding_preserves_live_model(self):
        app = Application(self.root/'data')
        try:
            data = {'name': 'model.L5X', 'content': base64.b64encode(self.l5x.read_bytes()).decode(),
                    'native_project_identity': self.identity().manifest()}
            app.command('load', data)
            endpoint = Endpoint(app, 0, False, 'logix-v35-l85e', native_read_only=True).start(); app.endpoint = endpoint
            raw = b'\x01\x02\x20\xac\x24\1'
            self.assertEqual(endpoint.router.handle(raw, Session())[4:], b''.join(self.identity().attributes().values()))
            self.assertTrue(endpoint.state()['native_correlation']['bound'])
            old = app.engine; generation = app.generation
            with self.assertRaises(ModelError):
                app.command('load', {**data, 'native_project_identity': {**data['native_project_identity'], 'source_l5x_sha256': '0'*64}})
            self.assertIs(app.engine, old); self.assertEqual(app.generation, generation)
            for action in ('reset', 'configure'):
                app.command(action, {}); self.assertEqual(app.native_project_identity, self.identity())
            app.command('demo', {})
            self.assertIsNone(app.native_project_identity); self.assertIsNone(endpoint.state()['native_correlation'])
        finally: app.close()

    def test_converter_records_identity_from_original_even_if_private_copy_changes(self):
        executable = self.root/'converter.exe'; executable.write_bytes(b'test double')
        def convert(command, **kwargs):
            Path(command[command.index('--acd')+1]).write_bytes(b'changed working copy')
            Path(command[command.index('--l5x')+1]).write_bytes(self.l5x.read_bytes())
            return SimpleNamespace(returncode=0, stdout='ok', stderr='')
        with patch('logixlab.importers.subprocess.run', side_effect=convert):
            result = convert_acd(self.acd, self.root/'out/project.L5X', executable)
        self.assertEqual(result['native_project_identity'], self.identity().manifest())
        self.assertEqual(json.loads((self.root/'out/provenance.json').read_text())['native_project_identity'], self.identity().manifest())


if __name__ == '__main__': unittest.main()
