"""Synthetic source-bound definitions; no native signatures or physical data."""
import base64
import copy
from dataclasses import replace
import importlib.util
import json
import struct
import unittest
from unittest.mock import patch

from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_templates import NativeTemplates
from logixlab.native_types import NativeTypes, Type, Member
from logixlab.template_staging import Attributes, Template
from logixlab.templates import Catalog
from logixlab.ethernetip import Endpoint, Session, logical
from tools.upload_inventory import collect_inventory
import test_structure_reads as fixtures


def saved(project):
    catalog = Catalog(project)
    ids = {key: 0x500+i for i, key in enumerate(sorted(catalog.types))}
    types = []; templates = []
    for key in sorted(catalog.types):
        model = catalog.types[key]; source_members = []; entries = []
        nodes = {n.get('Name'): n for n in project.udts[key].findall('./Members/Member')}
        for member in model.members:
            access = nodes[member.name].get('ExternalAccess', 'Read/Write')
            source_members.append(Member(member.name, member.dtype, member.offset, member.bit,
                (member.count,) if member.array else (), access, member.hidden))
            code = ((member.code & ~0xFFF) | ids[member.dtype.casefold()]) if member.code & 0x8000 else member.code
            code |= 0x2000 if member.array else 0
            info = member.bit if member.bit is not None else member.count if member.array else 0
            offset = member.offset | (0xA0000000 if access == 'Read Only' else 0)
            entries.append(struct.pack('<HHI', info, code, offset))
        types.append(Type(model.name, model.size, tuple(source_members)))
        raw = b''.join(entries)+(model.name+';nOpaque\0'+'\0'.join(m.name for m in model.members)+'\0').encode()
        raw += b'\xED'*(-(len(raw)+3)%4)+b'XYZ'
        templates.append(Template(ids[key], (len(raw)+20)//4,
            Attributes(0x4321+len(templates), len(model.members), model.size, 0, 0), raw))
    native = NativeTypes('a'*64, project.sha256, types, ids)
    return native, tuple(templates)


class NativeTemplateTests(unittest.TestCase):
    setUp = fixtures.StructureReadTests.setUp
    tearDown = fixtures.StructureReadTests.tearDown
    cip = fixtures.StructureReadTests.cip

    def load_saved(self):
        original = self.app.engine.project
        self.native, self.rows = saved(original)
        self.snapshot = NativeTemplates(self.native, self.rows)
        data = {'name': 'Model.L5X', 'content': base64.b64encode(original.path.read_bytes()).decode(),
            'native_project_identity': NativeProjectIdentity('a'*64, original.sha256, 1, 1, 1, 1, 1, 1).manifest(),
            'native_types': self.native.manifest(), 'native_templates': self.snapshot.manifest()}
        self.app.command('load', data)
        self.session = Session(handle=1, generation=self.app.generation)
        return data

    def test_bound_catalog_preserves_exact_definitions_native_ids_handles_and_nested_links(self):
        self.load_saved(); before = copy.deepcopy(self.app.engine.memory.values)
        self.endpoint.native_read_only = True
        catalog = self.router.templates()
        for model in catalog.types.values():
            row = next(row for row in self.rows if row.instance == model.instance)
            self.assertEqual(model.definition_storage, row.definition)
            self.assertEqual(model.attributes()[1], struct.pack('<H', row.attributes.handle))
            self.assertEqual(model.attributes()[4], struct.pack('<I', row.words))
            self.assertEqual(model.attributes()[7], bytes(4))
            self.assertEqual(model.attributes()[8], b'\0')
            for member in model.members:
                if member.code & 0x8000:
                    self.assertEqual(member.code & 0xFFF, catalog.for_type(member.dtype).instance)
            path = b'\x20\x6c'+logical(0x24, model.instance)
            self.assertEqual(self.cip(0x4C, path, struct.pack('<IH', 0, 65535))[4:], row.definition)
        symbols = {row['name']: row for row in self.router.symbols()}
        self.assertEqual(symbols['Machine']['type'] & 0xFFF, catalog.for_type('MachineState').instance)
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.app.engine.scan_count, 0)

    def test_snapshot_never_changes_ordinary_research_layout_or_exposes_private_types(self):
        self.load_saved()
        self.assertEqual(self.router.templates().for_type('AxisState').instance, 0x100)
        self.endpoint.native_read_only = True
        self.assertNotEqual(self.router.templates().for_type('AxisState').instance, 0x100)
        self.app.engine.project.tags['machine'].external_access = 'None'
        self.app.engine.project.tags['machines'].external_access = 'None'
        self.assertEqual(self.router.exposed_templates(), {})
        self.endpoint.native_read_only = False
        self.assertEqual(self.router.templates().for_type('AxisState').instance, 0x100)

    def test_named_packed_hosts_bind_exact_source_metadata_without_application_values(self):
        self.app.command('demo', {'sample': 'FlagLab'})
        project = self.app.engine.project
        for schema in project.udts.values():
            nodes = schema.findall('./Members/Member')
            names = {n.get('Name'): 'Packed' + str(i) for i, n in enumerate(nodes)
                     if n.get('Hidden') == 'true'}
            for node in nodes:
                if node.get('Name') in names: node.set('Name', names[node.get('Name')])
                if node.get('Target') in names: node.set('Target', names[node.get('Target')])
        native, rows = saved(project)
        self.assertEqual(len(rows), 2)
        snapshot = NativeTemplates(native, rows)
        bound = snapshot.bind(project, native)
        model = bound.for_type('FlagRecord')
        original = next(row for row in rows if row.instance == model.instance)
        self.assertEqual(model.definition_storage, original.definition)
        self.assertEqual([m.offset for m in model.members[:6]], [0, 0, 0, 0, 1, 1])
        raw = bound.encode(model, 'Record', self.app.engine.memory.read)
        self.assertEqual(raw[:8], struct.pack('<BB2xi', 0x89, 2, 1370))
        self.assertNotIn('Packed0', self.app.engine.memory.values['record'])

    def test_manifest_roundtrip_and_description_keep_definition_bytes_private(self):
        self.load_saved()
        restored = NativeTemplates.from_manifest(self.snapshot.manifest(), self.native)
        self.assertEqual(restored.manifest(), self.snapshot.manifest())
        info = restored.description()
        self.assertNotIn('AxisState', json.dumps(info))
        self.assertNotIn('definition_hex', info)
        for key in ('native_code_installed', 'signature_verified', 'native_execution'):
            self.assertFalse(info[key])
        self.app.command('reset', {})
        self.assertEqual(self.app.native_templates.manifest(), self.snapshot.manifest())
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.assertIsNone(self.app.native_templates)

    def test_wrong_source_ids_layouts_allocations_and_hex_are_rejected_before_installing(self):
        data = self.load_saved(); original = self.app.engine
        manifest = self.snapshot.manifest()
        variants = [dict(manifest, format_version=True), dict(manifest, source_acd_sha256='b'*64),
                    dict(manifest, templates=[]), dict(manifest, extra=1)]
        for field, value in (('instance', 0x555), ('words', True), ('words', 7), ('members', 1),
                             ('structure_bytes', 1), ('definition_hex', 'bad'), ('definition_hex', '00 '*30)):
            variant = copy.deepcopy(manifest); variant['templates'][0][field] = value; variants.append(variant)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ModelError):
                self.app.command('load', {**data, 'native_templates': value})
            self.assertIs(self.app.engine, original)
        for rows in ((self.rows[0], self.rows[0]), (replace(self.rows[0], definition=self.rows[0].definition+b'\0'),)):
            with self.assertRaises(ModelError):NativeTemplates(self.native, rows)
        with patch('logixlab.native_templates.MAX_TOTAL_BYTES', 1), self.assertRaises(ModelError):
            NativeTemplates(self.native, self.rows)

    def test_cached_source_layout_or_identity_changes_reject_wire_reads(self):
        self.load_saved(); self.endpoint.native_read_only = True
        template = self.router.templates().for_type('AxisState')
        self.app.native_types.type_ids['axisstate'] += 1
        path = b'\x20\x6c'+logical(0x24, template.instance)+b'\x30\x01'
        self.assertEqual(self.cip(14, path)[2], 0x0C)
        self.app.native_types.type_ids['axisstate'] -= 1
        self.app.native_types.types['axisstate'] = replace(self.app.native_types.types['axisstate'], size=1)
        self.assertEqual(self.cip(14, path)[2], 0x0C)

    def test_different_model_access_or_noncanonical_family_rejects_binding(self):
        self.load_saved()
        schema = self.app.engine.project.udts['axisstate']
        node = schema.find('./Members/Member')
        node.set('ExternalAccess', 'Read Only')
        with self.assertRaisesRegex(ModelError, 'member access'):
            self.snapshot.bind(self.app.engine.project, self.native)
        node.attrib.pop('ExternalAccess')
        schema.attrib.pop('Family')
        with self.assertRaisesRegex(ModelError, 'unsupported software layout'):
            self.snapshot.bind(self.app.engine.project, self.native)

    @unittest.skipUnless(importlib.util.find_spec('cryptography'), 'optional anonymous client key generator')
    def test_signed_inventory_reads_opaque_trailers_and_structured_values_without_writes(self):
        self.load_saved()
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e', native_read_only=True).start()
        self.app.endpoint = self.endpoint
        before = copy.deepcopy(self.app.engine.memory.values)
        report = collect_inventory(self.endpoint)
        self.assertTrue(report['templates'])
        for row in report['templates']:
            self.assertEqual(row['definition']['definition_profile'], 'saved_native')
            self.assertIsNone(row['definition']['reserved_padding_zero'])
            self.assertTrue(row['definition']['data_hex'].endswith('58595a'))
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.app.engine.scan_count, 0)
        self.assertEqual(self.endpoint.state()['active_tcp_clients'], 0)


if __name__ == '__main__':
    unittest.main()
