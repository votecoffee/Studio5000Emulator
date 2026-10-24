"""Explicit BIT host layout, access, rollback and modeled scan contracts."""
import copy
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E
from logixlab.ethernetip import Endpoint, Session, logical
from logixlab.model import Tag
from logixlab.server import Application
from test_ethernetip import request


def group_bytes(seed):
    return struct.pack('<Bxh', seed & 0x85, seed - 100)


def record_bytes(seed):
    return (struct.pack('<BB2xi', seed & 0x89, (seed & 1) << 1, seed * 10)
            + group_bytes(seed) + b''.join(group_bytes(seed + i + 1) for i in range(4)))


class PackedBitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'FlagLab'})
        self.endpoint = Endpoint(self.app, 0, True); self.router = self.endpoint.router
        self.session = Session(handle=1, generation=self.app.generation)

    def tearDown(self): self.app.close(); self.tmp.cleanup()

    def packet(self, service, ref, payload=b'', limit=480):
        return self.router.handle(request(service, ref, payload), self.session, limit=limit)

    def read(self, ref, count=1, offset=None, limit=480):
        payload = struct.pack('<H', count) + (struct.pack('<I', offset) if offset is not None else b'')
        return self.packet(0x52 if offset is not None else 0x4C, ref, payload, limit)

    def write(self, ref, payload, count=1, offset=None, dtype='FlagRecord'):
        template = self.router.templates().for_type(dtype)
        data = struct.pack('<3H', 0x02A0, template.handle, count)
        if offset is not None: data += struct.pack('<I', offset)
        return self.packet(0x53 if offset is not None else 0x4D, ref, data + payload)

    def assert_rejected(self, operation, status):
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(operation()[2], status)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_fixture_has_covered_logic_and_no_hidden_storage_values(self):
        self.assertEqual(self.app.engine.blockers, [])
        self.assertEqual({s['name'] for s in self.router.symbols()}, {'Record', 'Records', 'Observed', 'ObservedCount'})
        self.assertFalse(any(name.startswith('ZZZZ') for name in self.app.engine.memory.values['record']))

    def test_template_exposes_host_and_bit_metadata_with_shared_offsets(self):
        template = self.router.templates().for_type('FlagRecord')
        self.assertEqual((template.size, template.alignment), (28, 4))
        self.assertEqual([m.offset for m in template.members], [0, 0, 0, 0, 1, 1, 4, 8, 12])
        rows = [struct.unpack_from('<HHI', template.definition, i * 8) for i in range(len(template.members))]
        self.assertEqual(rows[:6], [(0, 0xC2, 0), (0, 0xC1, 0), (3, 0xC1, 0), (7, 0xC1, 0), (0, 0xC2, 1), (1, 0xC1, 1)])
        path = b'\x20\x6C' + logical(0x24, template.instance)
        raw = bytes((0x4C, len(path)//2)) + path + struct.pack('<IH', 0, 65535)
        self.assertEqual(self.router.handle(raw, self.session), b'\xcc\0\0\0'+template.definition+bytes(3))
        compact = bytes((0x4C, len(path)//2)) + path + struct.pack('<IH', 0, len(template.definition))
        self.assertEqual(self.router.handle(compact, self.session), b'\xcc\0\0\0'+template.definition)

    def test_reads_pack_flags_nested_records_and_reserved_bits_exactly(self):
        self.assertEqual(self.read('Record')[8:], record_bytes(137))
        self.assertEqual(self.read('Records[3]')[8:], record_bytes(3))
        self.assertEqual(self.read('Records[3].Group')[8:], group_bytes(3))
        self.assertEqual(self.read('Records[3].History', 4)[8:], b''.join(group_bytes(i) for i in range(4, 8)))

    def test_fragmented_array_read_matches_independent_byte_sequence(self):
        actual = b''; handle = None
        for _ in range(50):
            response = self.read('Records', 12, len(actual), limit=37)
            self.assertIn(response[2], (0, 6)); self.assertLessEqual(len(response), 37)
            if handle is None: handle = response[4:8]
            self.assertEqual(response[4:8], handle); actual += response[8:]
            if response[2] == 0: break
        else: self.fail('Fragmented packed-bit read did not finish')
        self.assertEqual(actual, b''.join(record_bytes(i) for i in range(12)))

    def test_symbol_instance_address_returns_the_same_packed_record(self):
        symbol = next(s for s in self.router.symbols() if s['name'] == 'Records')
        path = b'\x20\x6B' + logical(0x24, symbol['id']) + b'\x28\3'
        response = self.router.handle(bytes((0x4C, len(path)//2)) + path + b'\1\0', self.session)
        self.assertEqual(response[8:], record_bytes(3))

    def test_whole_record_write_updates_visible_flags_without_creating_hosts(self):
        self.assertEqual(self.write('Records[0]', record_bytes(137))[2], 0)
        memory = self.app.engine.memory
        self.assertTrue(memory.read('Records[0].Fault')); self.assertTrue(memory.read('Records[0].Running'))
        self.assertTrue(memory.read('Records[0].Ready')); self.assertTrue(memory.read('Records[0].Remote'))
        self.assertEqual(self.read('Records[0]')[8:], record_bytes(137))
        self.assertFalse(any(name.startswith('ZZZZ') for name in memory.values['records'][0]))

    def test_single_host_fragment_changes_all_its_bits_and_preserves_other_fields(self):
        before = bytearray(record_bytes(0)); before[0] = 0x81
        self.assertEqual(self.write('Records[0]', b'\x81', offset=0)[2], 0)
        self.assertEqual(self.read('Records[0]')[8:], before)
        self.assertFalse(self.app.engine.memory.read('Records[0].Running'))

    def test_direct_atomic_bool_writes_and_reads_agree_with_whole_record(self):
        for ref, value in (('Records[0].Fault', 1), ('Records[0].Ready', 1), ('Records[0].Group.High', 1)):
            self.assertEqual(self.packet(0x4D, ref, struct.pack('<HHB', 0xC1, 1, value))[2], 0)
            self.assertEqual(self.read(ref)[4:], struct.pack('<HB', 0xC1, value))
        data = self.read('Records[0]')[8:]; self.assertEqual((data[0], data[8]), (0x81, 0x80))

    def test_unknown_visible_bit_rejects_read_and_a_complete_host_write_establishes_it(self):
        self.app.engine.memory.values['records'][0]['Ready'] = None
        self.assertEqual(self.read('Records[0]')[2], 0x0C)
        self.assertEqual(self.write('Records[0]', b'\x01', offset=0)[2], 0)
        self.assertTrue(self.app.engine.memory.read('Records[0].Ready'))
        self.assertEqual(self.read('Records[0]')[2], 0)

    def test_unrelated_unknown_members_do_not_block_host_fragment_writes(self):
        memory = self.app.engine.memory; memory.values['records'][0]['Group']['High'] = None
        memory.values['records'][0]['Count'] = None
        self.assertEqual(self.write('Records[0]', b'\x80', offset=0)[2], 0)
        self.assertIsNone(memory.values['records'][0]['Count'])
        self.assertIsNone(memory.values['records'][0]['Group']['High'])

    def test_nonzero_unused_bits_reject_the_entire_request(self):
        for offset, payload in ((0, b'\x02'), (1, b'\x01'), (8, b'\x02')):
            self.assert_rejected(lambda: self.write('Records[0]', payload, offset=offset), 9)
        payload = bytearray(record_bytes(137)); payload[24] |= 0x02
        self.assert_rejected(lambda: self.write('Records[0]', payload), 9)

    def test_padding_only_fragments_remain_noops_and_nonzero_padding_is_rejected(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.write('Records[0]', b'\0\0', offset=2)[2], 0)
        self.assertEqual(self.app.engine.memory.values, before)
        self.assert_rejected(lambda: self.write('Records[0]', b'\1', offset=9), 9)

    def test_readonly_bit_blocks_its_host_byte_even_if_unchanged_but_other_hosts_work(self):
        node = self.app.engine.project.udts['flagrecord'].find('./Members/Member[@Name="Fault"]')
        node.set('ExternalAccess', 'Read Only')
        self.assert_rejected(lambda: self.write('Records[0]', b'\1', offset=0), 0x0F)
        self.assert_rejected(lambda: self.write('Records[0]', record_bytes(0)), 0x0F)
        self.assertEqual(self.write('Records[0]', b'\2', offset=1)[2], 0)
        self.assertEqual(self.packet(0x4D, 'Records[0].Ready', struct.pack('<HHB', 0xC1, 1, 1))[2], 0)

    def test_private_bit_hides_whole_template_but_public_atomic_member_stays_accessible(self):
        node = self.app.engine.project.udts['flagrecord'].find('./Members/Member[@Name="Fault"]')
        node.set('ExternalAccess', 'None')
        self.assertNotIn('Records', {s['name'] for s in self.router.symbols()})
        self.assertEqual(self.read('Records[0]')[2], 8)
        self.assertEqual(self.read('Records[0].Ready')[2], 0)
        self.assertEqual(self.read('Records[0].Fault')[2], 0x0F)

    def test_hidden_hosts_are_never_directly_accessible(self):
        ref = 'Records[0].ZZZZZZZZZZState'
        self.assertEqual(self.read(ref)[2], 0x0F)
        self.assert_rejected(lambda: self.packet(0x4D, ref, struct.pack('<HHb', 0xC2, 1, 0)), 0x0F)

    def test_explicit_host_names_do_not_change_nested_bytes_or_visibility(self):
        project = self.app.engine.project
        for schema in project.udts.values():
            nodes = schema.findall('./Members/Member')
            renamed = {n.get('Name'): 'Packed' + str(i) for i, n in enumerate(nodes)
                       if n.get('Hidden') == 'true'}
            for node in nodes:
                if node.get('Name') in renamed: node.set('Name', renamed[node.get('Name')])
                if node.get('Target') in renamed: node.set('Target', renamed[node.get('Target')])
        self.router._catalog = None
        self.assertEqual(self.read('Record')[8:], record_bytes(137))
        self.assertEqual(self.read('Records[3].Group')[8:], group_bytes(3))
        self.assertEqual(self.read('Records[0].Packed0')[2], 0x0F)
        self.assert_rejected(lambda: self.packet(0x4D, 'Records[0].Packed0', struct.pack('<HHb', 0xC2, 1, 0)), 0x0F)
        self.assertNotIn('Packed0', self.app.engine.memory.values['records'][0])
        self.assertEqual(self.write('Records[0]', record_bytes(137))[2], 0)
        self.assertEqual(self.read('Records[0]')[8:], record_bytes(137))

    def test_named_hosts_retain_unused_bit_and_member_access_write_guards(self):
        nodes = self.app.engine.project.udts['flagrecord'].findall('./Members/Member')
        nodes[0].set('Name', 'Packed')
        for node in nodes:
            if node.get('Target') == 'ZZZZZZZZZZState': node.set('Target', 'Packed')
        self.router._catalog = None
        self.assert_rejected(lambda: self.write('Records[0]', b'\x02', offset=0), 9)
        next(n for n in nodes if n.get('Name') == 'Fault').set('ExternalAccess', 'Read Only')
        self.assert_rejected(lambda: self.write('Records[0]', b'\x01', offset=0), 0x0F)
        self.assertEqual(self.read('Records[0]')[8:], record_bytes(0))

    def test_network_root_alias_and_constant_permissions_are_enforced(self):
        self.assert_rejected(lambda: self.write('Record', record_bytes(0)), 0x0F)
        self.endpoint.allow_writes = False
        self.assert_rejected(lambda: self.write('Records[0]', record_bytes(0)), 0x0F)
        self.endpoint.allow_writes = True
        project = self.app.engine.project
        project.tags['alias'] = Tag('Alias', '', None, alias='Records[0]', external_access='Read Only')
        self.assert_rejected(lambda: self.write('Alias', record_bytes(0)), 0x0F)
        project.tags['records'].constant = True
        self.assert_rejected(lambda: self.write('Records[0]', record_bytes(0)), 0x0F)

    def test_fragment_across_record_boundary_updates_each_host_and_preserves_padding(self):
        payload = group_bytes(128) + b'\x89\x02'
        self.assertEqual(self.write('Records', payload, count=12, offset=24)[2], 0)
        self.assertTrue(self.app.engine.memory.read('Records[0].History[3].High'))
        self.assertTrue(self.app.engine.memory.read('Records[1].Fault'))
        self.assertTrue(self.app.engine.memory.read('Records[1].Remote'))

    def test_late_record_reserved_bit_failure_rolls_back_all_records_in_request(self):
        payload = bytearray(record_bytes(137) + record_bytes(138)); payload[-4] |= 0x02
        self.assert_rejected(lambda: self.write('Records', payload, count=2), 9)

    def test_all_eight_bits_share_one_byte_and_bit_seven_is_unsigned(self):
        project = self.app.engine.project
        members = '<Member Name="ZZZZZZZZZZAll" DataType="SINT" Hidden="true"/>'
        members += ''.join(f'<Member Name="B{i}" DataType="BIT" Target="ZZZZZZZZZZAll" BitNumber="{i}"/>' for i in range(8))
        project.udts['allbits'] = E.fromstring('<DataType Name="AllBits"><Members>' + members + '</Members></DataType>')
        value = {f'B{i}': True for i in range(8)}; project.tags['all'] = Tag('All', 'AllBits', value)
        self.app.engine.memory.values['all'] = value
        self.assertEqual(self.read('All')[8:], b'\xFF\0\0\0')
        self.assertEqual(self.write('All', b'\x80', offset=0, dtype='AllBits')[2], 0)
        self.assertEqual(self.app.engine.memory.values['all'], {f'B{i}': i == 7 for i in range(8)})

    def test_malformed_or_unrelated_hidden_storage_is_not_advertised(self):
        original = copy.deepcopy(self.app.engine.project.udts['flagrecord'])
        changes = [('Ready', 'Target', 'Missing'), ('Ready', 'Target', 'Count'),
                   ('Ready', 'BitNumber', '-1'), ('Ready', 'BitNumber', '8'),
                   ('Ready', 'Dimension', '2'), ('Ready', 'Hidden', 'true'),
                   ('Running', 'BitNumber', '0'), ('ZZZZZZZZZZState', 'DataType', 'DINT'),
                   ('ZZZZZZZZZZState', 'Dimension', '2'), ('ZZZZZZZZZZState', 'Hidden', 'false'),
                   ('ZZZZZZZZZZState', 'Target', 'Other'), ('ZZZZZZZZZZState', 'AOILocal', 'true')]
        for name, attr, value in changes:
            with self.subTest(name=name, attr=attr, value=value):
                schema = copy.deepcopy(original); schema.find(f'./Members/Member[@Name="{name}"]').set(attr, value)
                self.app.engine.project.udts['flagrecord'] = schema; self.router._catalog = None
                self.assertIsNone(self.router.templates().for_type('FlagRecord'))
                self.assertNotIn('Records', {s['name'] for s in self.router.symbols()})
        schema = copy.deepcopy(original); nodes = schema.find('Members'); host = nodes[0]; nodes.remove(host); nodes.append(host)
        self.app.engine.project.udts['flagrecord'] = schema; self.router._catalog = None
        self.assertIsNone(self.router.templates().for_type('FlagRecord'))

    def test_scan_uses_network_flags_and_numeric_fields(self):
        self.assertEqual(self.write('Records[0]', record_bytes(137))[2], 0)
        self.app.command('step', {})
        self.assertFalse(self.app.engine.fault); self.assertTrue(self.app.engine.memory.read('Observed'))
        self.assertEqual(self.app.engine.memory.read('ObservedCount'), 1370)


if __name__ == '__main__': unittest.main()
