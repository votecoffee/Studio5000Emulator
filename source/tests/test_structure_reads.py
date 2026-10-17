"""Protocol contracts for bounded templates, nested reads and rejection paths."""
import copy
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E
from logixlab.server import Application
from logixlab.model import Tag
from logixlab.ethernetip import Endpoint, Session, logical, symbol_path
from test_ethernetip import request


def axis(seed):
    return struct.pack('<if8i', seed, seed + 0.5, *range(seed, seed + 8))


def machine(seed):
    return axis(seed) + b''.join(axis(seed + i + 1) for i in range(12)) + struct.pack('<4I', *range(seed, seed + 4))


class StructureReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'StructureLab'})
        self.endpoint = Endpoint(self.app, 0, True); self.router = self.endpoint.router
        self.session = Session(handle=1, generation=self.app.generation)

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def cip(self, service, path, data=b'', limit=480):
        return self.router.handle(bytes((service, len(path) // 2)) + path + data, self.session, limit=limit)

    def read(self, name, count=1, offset=None, limit=480):
        payload = struct.pack('<H', count) + (struct.pack('<I', offset) if offset is not None else b'')
        return self.cip(0x52 if offset is not None else 0x4C, symbol_path(name), payload, limit)

    def template_path(self, dtype):
        template = self.router.templates().for_type(dtype)
        return b'\x20\x6C' + logical(0x24, template.instance)

    def all_data(self, name, count=1, limit=480):
        data = b''; type_data = None
        for _ in range(200):
            result = self.read(name, count, len(data), limit)
            self.assertIn(result[2], (0, 6)); self.assertGreater(len(result), 8)
            self.assertEqual(result[4:6], b'\xA0\x02')
            if type_data is None: type_data = result[4:8]
            self.assertEqual(result[4:8], type_data); data += result[8:]
            if result[2] == 0: return data
        self.fail('Structured read did not finish')

    def add_type(self, name, members, value=None, access='Read/Write', scope=''):
        project = self.app.engine.project
        project.udts[name.lower()] = E.fromstring(f'<DataType Name="{name}" Class="User"><Members>{members}</Members></DataType>')
        tag = Tag('Extra', name, value if value is not None else {}, scope=scope, external_access=access)
        project.tags[tag.key.lower()] = tag; self.app.engine.memory.values[tag.key.lower()] = copy.deepcopy(tag.value)
        self.router._catalog = None
        return tag.key

    def test_symbols_publish_structure_instance_and_array_dimensions(self):
        symbols = {s['name']: s for s in self.router.symbols()}
        root = symbols['Machine']; array = symbols['Machines']
        self.assertTrue(root['type'] & 0x8000)
        self.assertEqual(array['type'], root['type'] | 0x2000)
        self.assertEqual(array['dimensions'], [2, 0, 0]); self.assertEqual(root['external_access'], 2)
        result = self.cip(0x0E, self.template_path('MachineState') + b'\x30\5')
        self.assertEqual(result, b'\x8E\0\0\0' + struct.pack('<I', 536))

    def test_template_attributes_describe_the_returned_definition(self):
        path = self.template_path('MachineState')
        result = self.cip(3, path, struct.pack('<5H', 4, 4, 5, 2, 1))
        self.assertEqual(result[:4], b'\x83\0\0\0'); self.assertEqual(result[4:6], b'\4\0')
        words = struct.unpack_from('<I', result, 10)[0]
        self.assertEqual(struct.unpack_from('<HHI', result, 14), (5, 0, 536))
        self.assertEqual(struct.unpack_from('<HHH', result, 22), (2, 0, 3))
        definition = self.cip(0x4C, path, struct.pack('<IH', 0, words * 4 - 23))
        self.assertEqual(definition[2], 0); self.assertEqual(len(definition[4:]), words * 4 - 23)
        self.assertEqual(result[-2:], self.read('Machine')[6:8])

    def test_template_members_have_correct_nested_types_arrays_offsets_and_names(self):
        path = self.template_path('MachineState'); data = self.cip(0x4C, path, struct.pack('<IH', 0, 65535))[4:]
        nested = self.router.templates().for_type('AxisState').instance
        self.assertEqual(struct.unpack_from('<HHI', data), (0, 0x8000 | nested, 0))
        self.assertEqual(struct.unpack_from('<HHI', data, 8), (12, 0xA000 | nested, 40))
        self.assertEqual(struct.unpack_from('<HHI', data, 16), (4, 0x20C8, 520))
        self.assertTrue(data[24:].startswith(b'MachineState;n\0Axis\0History\0Counters\0'))

    def test_template_pagination_respects_requested_range_and_response_limit(self):
        path = self.template_path('AxisState'); whole = self.cip(0x4C, path, struct.pack('<IH', 0, 65535))[4:]
        gathered = b''
        while len(gathered) < len(whole):
            result = self.cip(0x4C, path, struct.pack('<IH', len(gathered), 65535), limit=17)
            self.assertLessEqual(len(result), 17); self.assertIn(result[2], (0, 6)); gathered += result[4:]
        self.assertEqual(gathered, whole); self.assertEqual(result[2], 0)
        self.assertEqual(self.cip(0x4C, path, struct.pack('<IH', 3, 7))[4:], whole[3:10])

    def test_scalar_nested_and_large_structure_reads_match_known_bytes(self):
        self.assertEqual(self.read('Machine.Axis')[8:], axis(10))
        first = self.read('Machine'); self.assertEqual(first[2], 6); self.assertEqual(len(first), 480)
        self.assertEqual(first[8:], machine(10)[:472])
        self.assertEqual(self.all_data('Machine'), machine(10))

    def test_structure_arrays_and_members_within_arrays_respect_boundaries(self):
        self.assertEqual(self.all_data('Machines', 2), machine(0) + machine(100))
        self.assertEqual(self.all_data('Machines[1]'), machine(100))
        self.assertEqual(self.read('Machines[1].Axis')[8:], axis(100))
        self.assertEqual(self.all_data('Machines[1].History', 12), b''.join(axis(101 + i) for i in range(12)))
        self.assertNotEqual(self.read('Machines[1]', 2)[2], 0)
        self.assertNotEqual(self.read('Machines[0].Axis', 2)[2], 0)

    def test_logical_symbol_address_and_alias_read_the_same_structure(self):
        tag = Tag('Alias', '', None, alias='Machine.Axis')
        self.app.engine.project.tags['alias'] = tag
        symbols = {s['name']: s for s in self.router.symbols()}
        logical_path = b'\x20\x6B' + logical(0x24, symbols['Machine']['id']) + symbol_path('Axis')
        self.assertEqual(self.cip(0x4C, logical_path, b'\1\0'), self.read('Machine.Axis'))
        self.assertEqual(self.read('Alias'), self.read('Machine.Axis'))

    def test_multidimensional_root_array_reads_cross_rows_in_row_major_order(self):
        value = self.app.engine.memory.values['machines'][0]
        grid = [[[copy.deepcopy(value) for _ in range(2)] for _ in range(2)] for _ in range(2)]
        for a in range(2):
            for b in range(2):
                for c in range(2): grid[a][b][c]['Axis']['Command'] = a * 4 + b * 2 + c
        tag = Tag('Grid', 'MachineState', grid)
        self.app.engine.project.tags['grid'] = tag; self.app.engine.memory.values['grid'] = grid
        symbol = next(s for s in self.router.symbols() if s['name'] == 'Grid')
        self.assertEqual(symbol['dimensions'], [2, 2, 2]); self.assertEqual((symbol['type'] >> 13) & 3, 3)
        expected = b''.join(struct.pack('<i', i) + machine(0)[4:] for i in (3, 4, 5))
        self.assertEqual(self.all_data('Grid[0,1,1]', 3), expected)

    def test_atomic_member_access_still_works_inside_structured_arrays(self):
        name = 'Machines[1].Axis.Command'
        self.assertEqual(self.read(name)[4:], struct.pack('<Hi', 0xC4, 100))
        result = self.router.handle(request(0x4D, name, struct.pack('<HHi', 0xC4, 1, 123)), self.session)
        self.assertEqual(result[2], 0); self.assertEqual(self.read(name)[4:], struct.pack('<Hi', 0xC4, 123))
        self.assertEqual(self.read('Machines[1].Axis')[8:12], struct.pack('<i', 123))

    def test_modeled_scan_changes_are_visible_in_structured_reads(self):
        self.app.command('step', {'count': 1})
        self.assertEqual(self.read('Machine.Axis')[8:16], struct.pack('<if', 7, 7.0))
        self.assertEqual(self.app.engine.scan_count, 1); self.assertFalse(self.app.engine.fault)

    def test_unknown_member_rejects_even_a_fragment_elsewhere_in_the_structure(self):
        self.app.engine.memory.values['machine']['History'][11]['Samples'][7] = None
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.read('Machine', offset=0)[2], 0x0C)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_malformed_structured_writes_and_readonly_member_writes_do_not_mutate(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        for service in (0x4D, 0x53, 0x4E):
            for name in ('Machine', 'Machines'):
                self.assertNotEqual(self.router.handle(request(service, name, b'\xA0\x02\1\0' + b'\0' * 32), self.session)[2], 0)
        self.assertNotEqual(self.router.handle(request(0x4D, 'Machine.Axis.Command', struct.pack('<HHi', 0xC4, 1, 99)), self.session)[2], 0)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_unsupported_packing_and_private_members_are_not_advertised(self):
        cases = ['<Member Name="A" DataType="BOOL"/>', '<Member Name="A" DataType="LREAL"/>',
                 '<Member Name="A" DataType="DINT" Hidden="true"/>',
                 '<Member Name="A" DataType="DINT" ExternalAccess="None"/>',
                 '<Member Name="A" DataType="DINT" Dimension="2,2"/>',
                 '<Member Name="A" DataType="DINT" Dimension="4096"/><Member Name="B" DataType="DINT" Dimension="4096"/><Member Name="C" DataType="DINT"/>']
        for members in cases:
            with self.subTest(members=members):
                ref = self.add_type('Unsupported', members)
                self.assertNotIn('Extra', {s['name'] for s in self.router.symbols()})
                self.assertEqual(self.read(ref)[2], 8)

    def test_recursive_missing_and_decorated_only_types_are_rejected(self):
        for dtype in ('Unsupported', 'Missing'):
            self.add_type('Unsupported', f'<Member Name="A" DataType="{dtype}"/>')
            self.assertEqual(self.read('Extra')[2], 8)
        self.add_type('Unsupported', '<Member Name="A" DataType="DINT"/>', {'A': 1})
        self.app.engine.project.udts['unsupported'].set('Class', 'DecoratedDataOnly')
        self.assertEqual(self.read('Extra')[2], 8)

    def test_unreferenced_private_templates_are_not_disclosed(self):
        self.add_type('PrivateType', '<Member Name="Secret" DataType="DINT"/>', {'Secret': 1}, access='None')
        self.assertEqual(self.cip(0x0E, self.template_path('PrivateType') + b'\x30\1')[2], 5)
        self.assertNotIn('Extra', {s['name'] for s in self.router.symbols()})

    def test_nesting_limit_holds_even_when_child_templates_were_cached_first(self):
        project = self.app.engine.project
        for index in range(8):
            dtype = f'Child{index}'
            child = f'Child{index + 1}' if index < 7 else 'DINT'
            project.udts[dtype.lower()] = E.fromstring(f'<DataType Name="{dtype}"><Members><Member Name="A" DataType="{child}"/></Members></DataType>')
        self.add_type('ZRoot', '<Member Name="A" DataType="Child0"/>')
        self.assertIsNotNone(self.router.templates().for_type('Child0'))
        self.assertIsNone(self.router.templates().for_type('ZRoot'))
        self.assertEqual(self.read('Extra')[2], 8)

    def test_transfer_size_and_member_count_limits_reject_oversized_requests(self):
        tag = Tag('Bulk', 'MachineState', [{}] * 62)
        self.app.engine.project.tags['bulk'] = tag; self.app.engine.memory.values['bulk'] = tag.value
        self.assertEqual(self.read('Bulk', 62)[2], 3)
        members = ''.join(f'<Member Name="A{i}" DataType="DINT"/>' for i in range(257))
        self.add_type('TooManyMembers', members)
        self.assertEqual(self.read('Extra')[2], 8)

    def test_program_scoped_public_types_can_be_discovered(self):
        self.add_type('LocalType', '<Member Name="Value" DataType="DINT"/>', {'Value': 42}, scope='MainProgram')
        self.assertEqual(self.read('Program:MainProgram.Extra')[8:], struct.pack('<i', 42))
        self.assertEqual(self.cip(0x0E, self.template_path('LocalType') + b'\x30\5')[4:], struct.pack('<I', 4))

    def test_invalid_template_paths_attributes_lengths_and_offsets_preserve_state(self):
        path = self.template_path('AxisState'); before = copy.deepcopy(self.app.engine.memory.values)
        for payload in (b'', struct.pack('<IH', 0, 0), struct.pack('<IH', 9999, 1), struct.pack('<IH', 0, 1) + b'x'):
            self.assertNotEqual(self.cip(0x4C, path, payload)[2], 0)
        self.assertEqual(self.cip(0x4C, path + b'\x30\1', struct.pack('<IH', 0, 1))[2], 4)
        self.assertEqual(self.cip(0x0E, path + b'\x30\xFF')[2], 0x14)
        mixed = self.cip(3, path, struct.pack('<HHH', 2, 5, 99))
        self.assertEqual(mixed[2], 0x0A); self.assertEqual(mixed[-4:], struct.pack('<HH', 99, 0x14))
        self.assertEqual(self.cip(0x4C, symbol_path('Extra') + path, struct.pack('<IH', 0, 1))[2], 4)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_invalid_read_ranges_and_small_reply_limits_fail(self):
        for count, offset in ((0, None), (4097, None), (1, 536), (1, 0xFFFFFFFF)):
            self.assertNotEqual(self.read('Machine', count, offset)[2], 0)
        self.assertEqual(self.read('Machine', limit=8)[2], 0x1B)
        self.assertEqual(self.cip(0x4C, self.template_path('AxisState'), struct.pack('<IH', 0, 1), limit=4)[2], 0x1B)

    def test_project_replacement_invalidates_sessions_and_type_catalog(self):
        old_path = self.template_path('MachineState')
        self.app.command('demo', {'sample': 'TextLab'})
        self.assertEqual(self.cip(0x0E, old_path + b'\x30\5')[2], 0x10)
        self.session = Session(handle=2, generation=self.app.generation)
        self.assertEqual(self.cip(0x0E, old_path + b'\x30\5')[2], 5)


if __name__ == '__main__': unittest.main()
