"""Structured write contracts, fragment visibility and failure preservation."""
import copy
import struct
import tempfile
import unittest
from logixlab.server import Application
from logixlab.model import Tag
from logixlab.ethernetip import Endpoint, Session, logical, symbol_path
from test_ethernetip import Client, fo, request
from test_structure_reads import axis, machine


class StructureWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'StructureLab'})
        self.endpoint = Endpoint(self.app, 0, True); self.router = self.endpoint.router
        self.session = Session(handle=1, generation=self.app.generation)

    def tearDown(self):
        self.endpoint.stop(); self.app.close(); self.tmp.cleanup()

    def packet(self, name, payload, dtype='AxisState', count=1, offset=None, handle=None, code=0x02A0):
        template = self.router.templates().for_type(dtype)
        handle = template.handle if handle is None else handle
        data = struct.pack('<HHH', code, handle, count)
        if offset is not None: data += struct.pack('<I', offset)
        return request(0x53 if offset is not None else 0x4D, name, data + payload)

    def write(self, name, payload, **kwargs):
        return self.router.handle(self.packet(name, payload, **kwargs), self.session)

    def read_bytes(self, name, count=1):
        result = b''
        for _ in range(200):
            raw = request(0x52, name, struct.pack('<HI', count, len(result)))
            response = self.router.handle(raw, self.session)
            self.assertIn(response[2], (0, 6)); result += response[8:]
            if not response[2]: return result
        self.fail('Fragmented verification read did not complete')

    def assert_rejected_without_changes(self, raw, status=None):
        before = copy.deepcopy(self.app.engine.memory.values)
        result = self.router.handle(raw, self.session)
        self.assertEqual(result[2], status) if status is not None else self.assertNotEqual(result[2], 0)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_full_nested_structure_write_uses_the_declared_type_handle(self):
        result = self.write('Machines[1].Axis', axis(-5))
        self.assertEqual(result, b'\xCD\0\0\0')
        self.assertEqual(self.read_bytes('Machines[1].Axis'), axis(-5))
        self.assertEqual(self.read_bytes('Machines[0]'), machine(0))

    def test_whole_record_array_write_preserves_numeric_member_types(self):
        payload = machine(30) + machine(60)
        self.assertEqual(self.write('Machines', payload, dtype='MachineState', count=2)[2], 0)
        self.assertEqual(self.read_bytes('Machines', 2), payload)
        memory = self.app.engine.memory
        self.assertIsInstance(memory.read('Machines[0].Axis.Command'), int)
        self.assertIsInstance(memory.read('Machines[0].Axis.Actual'), float)
        self.assertEqual(self.read_bytes('Machine'), machine(10))

    def test_fragment_can_cross_record_boundary_and_split_unsigned_atom(self):
        payload = b'\xAA\xBB' + struct.pack('<i', -1234)
        self.assertEqual(self.write('Machines', payload, dtype='MachineState', count=2, offset=534)[2], 0)
        expected = bytearray(machine(0) + machine(100)); expected[534:540] = payload
        self.assertEqual(self.read_bytes('Machines', 2), expected)

    def test_fragment_can_split_a_real_and_preserve_surrounding_bytes(self):
        self.assertEqual(self.write('Machines[0].Axis', b'\xAA\xBB', offset=5)[2], 0)
        expected = bytearray(axis(0)); expected[5:7] = b'\xAA\xBB'
        self.assertEqual(self.read_bytes('Machines[0].Axis'), expected)

    def test_complete_atoms_can_establish_unknown_members(self):
        memory = self.app.engine.memory
        memory.values['machines'][0]['Axis']['Command'] = None
        memory.values['machines'][0]['Axis']['Actual'] = None
        self.assertEqual(self.write('Machines[0].Axis', struct.pack('<i', 456), offset=0)[2], 0)
        self.assertEqual(memory.read('Machines[0].Axis.Command'), 456)
        self.assertIsNone(memory.values['machines'][0]['Axis']['Actual'])

    def test_whole_structure_write_establishes_all_unknown_leaves(self):
        def unknown(value):
            if isinstance(value, dict): return {k: unknown(v) for k, v in value.items()}
            if isinstance(value, list): return [unknown(v) for v in value]
            return None
        memory = self.app.engine.memory
        memory.values['machines'][0] = unknown(memory.values['machines'][0])
        self.assertEqual(self.write('Machines[0]', machine(9), dtype='MachineState')[2], 0)
        self.assertEqual(self.read_bytes('Machines[0]'), machine(9))

    def test_unknown_split_atom_rejects_entire_fragment(self):
        self.app.engine.memory.values['machines'][0]['Axis']['Actual'] = None
        raw = self.packet('Machines[0].Axis', struct.pack('<i', 99) + b'\x01', offset=0)
        self.assert_rejected_without_changes(raw, 0x0C)

    def test_nonfinite_real_rolls_back_other_members_in_same_request(self):
        for value in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(value=value):
                raw = self.packet('Machines[0].Axis', struct.pack('<if8i', 99, value, *range(8)))
                self.assert_rejected_without_changes(raw, 0x0C)

    def test_late_record_failure_rolls_back_earlier_record_in_same_request(self):
        second = bytearray(machine(60)); struct.pack_into('<f', second, 4, float('nan'))
        self.assert_rejected_without_changes(self.packet('Machines', machine(30) + second, dtype='MachineState', count=2), 0x0C)

    def test_previously_accepted_fragment_remains_after_later_failure(self):
        self.assertEqual(self.write('Machines[0].Axis', struct.pack('<i', 77), offset=0)[2], 0)
        self.assert_rejected_without_changes(self.packet('Machines[0].Axis', struct.pack('<f', float('nan')), offset=4), 0x0C)
        self.assertEqual(self.app.engine.memory.read('Machines[0].Axis.Command'), 77)

    def test_network_write_permission_and_readonly_root_are_enforced(self):
        self.endpoint.allow_writes = False
        self.assert_rejected_without_changes(self.packet('Machines[0].Axis', axis(5)), 0x0F)
        self.endpoint.allow_writes = True
        self.assert_rejected_without_changes(self.packet('Machine.Axis', axis(5)), 0x0F)
        self.app.engine.project.tags['machines'].constant = True
        self.assert_rejected_without_changes(self.packet('Machines[0].Axis', axis(5)), 0x0F)

    def test_readonly_member_blocks_whole_write_but_not_other_fragments(self):
        schema = self.app.engine.project.udts['axisstate']
        schema.find('./Members/Member[@Name="Actual"]').set('ExternalAccess', 'Read Only')
        self.assert_rejected_without_changes(self.packet('Machines[0].Axis', axis(5)), 0x0F)
        self.assert_rejected_without_changes(self.packet('Machines[0].Axis', b'\xFF', offset=4), 0x0F)
        self.assertEqual(self.write('Machines[0].Axis', struct.pack('<i', 123), offset=0)[2], 0)
        self.assertEqual(self.app.engine.memory.read('Machines[0].Axis.Actual'), 0.5)

    def test_readonly_nested_structure_blocks_only_touched_members(self):
        schema = self.app.engine.project.udts['machinestate']
        schema.find('./Members/Member[@Name="History"]').set('ExternalAccess', 'Read Only')
        self.assert_rejected_without_changes(self.packet('Machines[0]', machine(5), dtype='MachineState'), 0x0F)
        self.assertEqual(self.write('Machines[0]', axis(7), dtype='MachineState', offset=0)[2], 0)
        self.assertEqual(self.app.engine.memory.read('Machines[0].History[0].Command'), 1)

    def test_alias_and_logical_instance_writes_keep_target_access_rules(self):
        project = self.app.engine.project
        project.tags['alias'] = Tag('Alias', '', None, alias='Machines[1].Axis')
        self.assertEqual(self.write('Alias', axis(7))[2], 0)
        symbol = next(s for s in self.router.symbols() if s['name'] == 'Alias')
        path = b'\x20\x6B' + logical(0x24, symbol['id'])
        data = self.packet('Alias', axis(8)); size = 2 + data[1] * 2
        raw = b'\x4D' + bytes((len(path) // 2,)) + path + data[size:]
        self.assertEqual(self.router.handle(raw, self.session)[2], 0)
        self.assertEqual(self.read_bytes('Machines[1].Axis'), axis(8))
        project.tags['alias'].external_access = 'Read Only'
        self.assert_rejected_without_changes(self.packet('Alias', axis(9)), 0x0F)

    def test_wrong_type_handle_and_malformed_lengths_preserve_all_data(self):
        template = self.router.templates().for_type('AxisState')
        packets = [self.packet('Machines[0].Axis', axis(1), handle=template.handle ^ 1),
                   self.packet('Machines[0].Axis', axis(1), code=0x00C4),
                   self.packet('Machines[0].Axis', axis(1)[:-1]),
                   self.packet('Machines[0].Axis', axis(1) + b'\0'),
                   request(0x4D, 'Machines[0].Axis', b'\xA0\2\0\0'),
                   request(0x53, 'Machines[0].Axis', b'\xA0\2\0\0\1\0\0')]
        for raw in packets:
            with self.subTest(raw=raw.hex()): self.assert_rejected_without_changes(raw)

    def test_invalid_counts_offsets_and_array_boundaries_are_rejected(self):
        for count, offset, payload in ((0, 0, b'x'), (4097, 0, b'x'), (2, 0, axis(1)),
                                       (1, 40, b'x'), (1, 39, b'xx'), (1, 0xFFFFFFFF, b'x'), (1, 0, b'')):
            self.assert_rejected_without_changes(self.packet('Machines[0].Axis', payload, count=count, offset=offset))
        self.assert_rejected_without_changes(self.packet('Machines[1]', machine(1), dtype='MachineState', count=2, offset=0))
        tag = Tag('Bulk', 'MachineState', [{}] * 62)
        self.app.engine.project.tags['bulk'] = tag; self.app.engine.memory.values['bulk'] = tag.value
        self.assert_rejected_without_changes(self.packet('Bulk', b'x', dtype='MachineState', count=62, offset=0), 3)

    def test_multidimensional_array_write_crosses_rows_in_row_major_order(self):
        value = self.app.engine.memory.values['machines'][0]['Axis']
        grid = [[copy.deepcopy(value) for _ in range(2)] for _ in range(2)]
        self.app.engine.project.tags['grid'] = Tag('Grid', 'AxisState', grid)
        self.app.engine.memory.values['grid'] = grid
        self.assertEqual(self.write('Grid[0,1]', axis(7) + axis(9), count=2)[2], 0)
        self.assertEqual(self.read_bytes('Grid', 4), axis(0) + axis(7) + axis(9) + axis(0))

    def test_program_scoped_structure_write_and_safety_scope_denial(self):
        value = copy.deepcopy(self.app.engine.memory.values['machines'][0]['Axis'])
        tag = Tag('Local', 'AxisState', value, scope='MainProgram')
        self.app.engine.project.tags[tag.key.lower()] = tag; self.app.engine.memory.values[tag.key.lower()] = value
        self.assertEqual(self.write(tag.key, axis(7))[2], 0)
        self.assertEqual(self.read_bytes(tag.key), axis(7))
        self.app.engine.project.programs['MainProgram']['class'] = 'Safety'
        self.assert_rejected_without_changes(self.packet(tag.key, axis(9)), 0x0F)

    def test_multiple_service_children_remain_independent(self):
        bad = struct.pack('<if8i', 99, float('nan'), *range(8))
        children = [self.packet('Machines[0].Axis', axis(7)), self.packet('Machines[1].Axis', bad)]
        body = struct.pack('<HHH', 2, 6, 6 + len(children[0])) + b''.join(children)
        result = self.router.handle(b'\x0A\x02\x20\2\x24\1' + body, self.session)
        self.assertEqual(result[2], 0x1E)
        self.assertEqual(self.read_bytes('Machines[0].Axis'), axis(7))
        self.assertEqual(self.read_bytes('Machines[1].Axis'), axis(100))

    def test_reset_invalidates_old_write_session(self):
        raw = self.packet('Machines[0].Axis', axis(7)); self.app.command('reset', {})
        self.assert_rejected_without_changes(raw, 0x10)

    def test_scan_consumes_the_network_written_structure_member(self):
        self.assertEqual(self.write('Machines[0].Axis', axis(42))[2], 0)
        self.app.command('step', {})
        self.assertFalse(self.app.engine.fault)
        self.assertEqual(self.app.engine.memory.read('Machine.History[0].Command'), 42)

    def test_connected_duplicate_request_replays_without_reapplying_write(self):
        self.endpoint.start(); client = Client(self.endpoint.port)
        try:
            client.register(); status, opened = client.cip(fo())
            self.assertEqual(status, 0); self.assertEqual(opened[2], 0)
            connection = struct.unpack_from('<I', opened, 4)[0]
            raw = self.packet('Machines[0].Axis', axis(7))
            first = client.cip(raw, connection=connection, sequence=1)
            self.assertEqual(first, (0, b'\xCD\0\0\0'))
            self.app.engine.memory.write('Machines[0].Axis.Command', 99)
            self.assertEqual(client.cip(raw, connection=connection, sequence=1), first)
            self.assertEqual(self.app.engine.memory.read('Machines[0].Axis.Command'), 99)
            self.assertEqual(client.cip(raw, connection=connection, sequence=2), first)
            self.assertEqual(self.app.engine.memory.read('Machines[0].Axis.Command'), 7)
        finally: client.close()


if __name__ == '__main__': unittest.main()
