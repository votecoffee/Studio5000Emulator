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


def container(fields=None, compressed=True, header=None, tail=bytes(4)):
    if header is None: header = b''.join(varint(n*8)+varint(v) for n, v in (FIELDS if fields is None else fields).items())
    stream = struct.pack('<I', len(header))+header+tail
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

    def test_empty_change_log_search_is_exact_source_cursor_with_no_history_fabrication(self):
        app=Application(self.root/'search-data')
        try:
            app.command('load',{'name':'model.L5X','content':base64.b64encode(self.l5x.read_bytes()).decode(),
                                'native_project_identity':self.identity().manifest()})
            endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True).start();app.endpoint=endpoint
            session=Session();prefix=bytes.fromhex('4f0220ac2401');cursor=struct.pack('<HH',7,3)
            self.assertEqual(endpoint.router.handle(prefix+cursor,session),b'\xCF\0\0\0'+cursor)
            for payload in (struct.pack('<HH',6,3),struct.pack('<HH',7,2)):
                self.assertEqual(endpoint.router.handle(prefix+payload,session)[2],0x0C)
            self.assertEqual(endpoint.router.handle(prefix+cursor[:-1],session)[2],0x13)
            self.assertEqual(endpoint.router.handle(prefix+cursor+b'x',session)[2],0x15)
            self.assertEqual(endpoint.router.handle(bytes.fromhex('0e0320ac24003001'),session)[4:],b'\5\0')
            app.command('demo',{})
            self.assertEqual(endpoint.router.handle(prefix+cursor,Session())[2],0x0C)
        finally:app.close()

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

    def test_empty_source_profile_requires_exact_zero_trailer_eof_and_zero_index(self):
        for compressed in (False,True):
            for tail in (b'',bytes(3),bytes(5),b'\1\0\0\0',bytes(4)+b'record'):
                self.acd.write_bytes(container(fields={**FIELDS,11:0},compressed=compressed,tail=tail))
                with self.subTest(compressed=compressed,tail=tail):
                    self.assertFalse(self.identity().empty_change_log)
            raw=container(fields={**FIELDS,11:0},compressed=compressed);self.acd.write_bytes(raw)
            identity=self.identity();self.assertTrue(identity.empty_change_log)
            self.assertEqual(self.acd.read_bytes(),raw)
            self.assertTrue(identity.description()['empty_change_log_source'])
            self.assertFalse(identity.description()['change_log_records_supplied'])
        self.acd.write_bytes(container());self.assertFalse(self.identity().empty_change_log)

    def test_empty_evidence_round_trips_and_legacy_manifests_grant_no_extra_query(self):
        self.acd.write_bytes(container(fields={**FIELDS,11:0}));identity=self.identity();good=identity.manifest()
        self.assertEqual(NativeProjectIdentity.from_manifest(good,self.digest),identity)
        legacy={k:v for k,v in good.items() if k!='empty_change_log'}
        self.assertFalse(NativeProjectIdentity.from_manifest(legacy,self.digest).empty_change_log)
        for change in ({'empty_change_log':1},{'empty_change_log':'true'},{'online_index':1}):
            with self.assertRaises(ModelError):NativeProjectIdentity.from_manifest({**good,**change},self.digest)

    def test_empty_upload_lookup_echoes_only_its_supported_cursors_without_records(self):
        self.acd.write_bytes(container(fields={**FIELDS,11:0}));identity=self.identity()
        current=struct.pack('<HH',0,3);upload=struct.pack('<HH',0,4)
        self.assertEqual(identity.empty_log_search(current),current)
        self.assertEqual(identity.empty_log_search(upload),upload)
        end=struct.pack('<HH',1,3);self.assertEqual(identity.empty_log_search(end),end)
        self.assertNotEqual(identity.empty_log_search(upload),current)
        for data in (b'',bytes(3),bytes(5),bytearray(upload),None,struct.pack('<HH',2,3),
                     struct.pack('<HH',0,2),struct.pack('<HH',0,5)):
            with self.subTest(data=data):self.assertIsNone(identity.empty_log_search(data))
        for revision in (1,-1,False,None,'0'):
            self.assertIsNone(identity.empty_log_search(upload,runtime_revision=revision))
            self.assertIsNone(identity.empty_log_search(end,runtime_revision=revision))
        legacy=NativeProjectIdentity.from_manifest({k:v for k,v in identity.manifest().items() if k!='empty_change_log'},self.digest)
        self.assertIsNone(legacy.empty_log_search(upload))
        self.assertIsNone(legacy.empty_log_search(end))
        self.acd.write_bytes(container(fields={**FIELDS,11:0,12:65535}));identity=self.identity()
        self.assertIsNone(identity.empty_log_search(bytes(4)))

    def test_source_bound_wire_upload_lookup_does_not_change_state_or_survive_structural_edits(self):
        self.acd.write_bytes(container(fields={**FIELDS,11:0}));app=Application(self.root/'empty-log-data')
        try:
            data={'name':'model.L5X','content':base64.b64encode(self.l5x.read_bytes()).decode(),
                  'native_project_identity':self.identity().manifest()}
            app.command('load',data)
            endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True);app.endpoint=endpoint
            prefix=bytes.fromhex('4f0220ac2401');cursor=struct.pack('<HH',0,4);before=app.state()
            self.assertEqual(endpoint.router.handle(prefix+cursor,Session()),b'\xcf\0\0\0'+cursor)
            after=app.state()
            for key in ('tags','routines','tasks','scan','ms','controller','routine_edits'):
                self.assertEqual(before[key],after[key])
            self.assertIsNone(endpoint.programming_lease.owner)
            app.engine.project.runtime_revision=1
            self.assertEqual(endpoint.router.handle(prefix+cursor,Session())[2],12)
            self.assertEqual(endpoint.router.handle(prefix+struct.pack('<HH',0,3),Session())[2],0)
            app.engine.project.runtime_revision=0
            app.native_project_identity=NativeProjectIdentity.from_manifest({**self.identity().manifest(),'source_l5x_sha256':'a'*64},'a'*64)
            self.assertEqual(endpoint.router.handle(prefix+cursor,Session())[2],12)
        finally:app.close()


if __name__ == '__main__': unittest.main()
