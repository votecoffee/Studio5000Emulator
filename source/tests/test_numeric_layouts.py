"""Independent byte expectations for v35 numeric alignment and padding policy."""
import copy
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E
from logixlab.server import Application
from logixlab.model import Tag
from logixlab.ethernetip import Endpoint, Session, logical
from test_ethernetip import request


PADDING = (1, 7, 26, 27, 29, 33, 34, 35, 39, 53, 54, 55, 60, 61, 62, 63)


def record_bytes(seed):
    data = bytearray(64)
    for offset, fmt, values in (
        (0, 'b', [-8 + seed]), (2, 'h', [-30000 + seed]), (4, '3B', [0, 127, 255 - seed]),
        (8, 'q', [-(1 << 63) + seed]), (16, 'i', [100 + seed]), (20, '3H', [1, 32768, 65535 - seed]),
        (28, 'b', [-5 + seed]), (30, 'h', [-1234 - seed]), (32, 'B', [200 + seed]),
        (36, '3b', [-4 - seed, 0, 5 + seed]), (40, 'Q', [(1 << 64) - 1 - seed]),
        (48, 'f', [1.25 + seed]), (52, 'b', [120 - seed]), (56, 'I', [(1 << 32) - 1 - seed])):
        struct.pack_into('<' + fmt, data, offset, *values)
    return bytes(data)


class NumericLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'LayoutLab'})
        self.endpoint = Endpoint(self.app, 0, True); self.router = self.endpoint.router
        self.session = Session(handle=1, generation=self.app.generation)

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def read(self, name, count=1):
        data = b''
        for _ in range(200):
            result = self.router.handle(request(0x52, name, struct.pack('<HI', count, len(data))), self.session)
            self.assertIn(result[2], (0, 6)); data += result[8:]
            if not result[2]: return data
        self.fail('Read did not finish')

    def write(self, name, payload, count=1, offset=None, dtype='MixedRecord'):
        template = self.router.templates().for_type(dtype)
        data = struct.pack('<HHH', 0x02A0, template.handle, count)
        if offset is not None: data += struct.pack('<I', offset)
        return self.router.handle(request(0x53 if offset is not None else 0x4D, name, data + payload), self.session)

    def test_template_offsets_include_scalar_array_nested_and_trailing_alignment(self):
        template = self.router.templates().for_type('MixedRecord')
        self.assertEqual((template.size, template.alignment), (64, 8))
        path = b'\x20\x6C' + logical(0x24, template.instance)
        response = self.router.handle(b'\x4C' + bytes((len(path) // 2,)) + path + struct.pack('<IH', 0, 65535), self.session)
        self.assertEqual(response[2], 0)
        rows = [struct.unpack_from('<HHI', response, 4 + i * 8) for i in range(11)]
        self.assertEqual([r[2] for r in rows], [0, 2, 4, 8, 16, 20, 28, 40, 48, 52, 56])
        self.assertEqual(rows[2][:2], (3, 0x20C6)); self.assertEqual(rows[5][:2], (3, 0x20C7))
        self.assertEqual(rows[3][:2], (0, 0xC5)); self.assertEqual(rows[7][:2], (0, 0xC9))
        nested = self.router.templates().for_type('SmallGroup')
        self.assertEqual((nested.size, nested.alignment), (12, 4))
        self.assertEqual([m.offset for m in nested.members], [0, 2, 4, 8])

    def test_all_numeric_widths_read_exact_bytes_and_reserved_padding_is_zero(self):
        self.assertEqual(self.read('Record'), record_bytes(9))
        self.assertEqual(self.read('Records', 8), b''.join(record_bytes(i) for i in range(8)))
        self.assertTrue(all(self.read('Records[0]')[p] == 0 for p in PADDING))

    def test_full_write_roundtrips_signed_unsigned_and_64_bit_extremes(self):
        data = record_bytes(0)
        self.assertEqual(self.write('Records[1]', data)[2], 0); self.assertEqual(self.read('Records[1]'), data)
        memory = self.app.engine.memory
        self.assertEqual(memory.read('Records[1].Wide'), -(1 << 63))
        self.assertEqual(memory.read('Records[1].Huge'), (1 << 64) - 1)
        self.assertEqual(memory.read('Records[1].Words[2]'), 65535)
        self.assertEqual(memory.read('Records[1].Unsigned'), (1 << 32) - 1)

    def test_fragment_splitting_a_lint_preserves_the_other_bytes(self):
        expected = bytearray(record_bytes(0)); expected[11:14] = b'\x11\x22\x33'
        self.assertEqual(self.write('Records[0]', b'\x11\x22\x33', offset=11)[2], 0)
        self.assertEqual(self.read('Records[0]'), expected)

    def test_fragment_crossing_scalar_padding_and_int_preserves_all_other_bytes(self):
        payload = struct.pack('<bxh', -1, -7)
        self.assertEqual(self.write('Records[0]', payload, offset=0)[2], 0)
        expected = bytearray(record_bytes(0)); expected[:4] = payload
        self.assertEqual(self.read('Records[0]'), expected)

    def test_nonzero_padding_rejects_every_request_without_mutation(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        for position in PADDING:
            with self.subTest(position=position):
                data = bytearray(record_bytes(1)); data[position] = 1
                self.assertEqual(self.write('Records[0]', data)[2], 9)
                self.assertEqual(self.app.engine.memory.values, before)
                self.assertEqual(self.write('Records[0]', b'\x80', offset=position)[2], 9)
                self.assertEqual(self.app.engine.memory.values, before)

    def test_zero_padding_only_fragment_is_a_noop(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.write('Records[0]', b'\0\0', offset=26)[2], 0)
        self.assertEqual(self.write('Records[0]', b'\0'*4, offset=60)[2], 0)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_unknown_application_value_is_not_replaced_by_padding(self):
        memory = self.app.engine.memory; memory.values['records'][0]['Wide'] = None
        result = self.router.handle(request(0x4C, 'Records[0]', b'\1\0'), self.session)
        self.assertEqual(result[2], 0x0C)
        before = copy.deepcopy(memory.values)
        self.assertEqual(self.write('Records[0]', b'\0', offset=9)[2], 0x0C)
        self.assertEqual(memory.values, before)
        self.assertEqual(self.write('Records[0]', struct.pack('<q', (1 << 63) - 1), offset=8)[2], 0)
        self.assertEqual(memory.read('Records[0].Wide'), (1 << 63) - 1)

    def test_nonfinite_real_rolls_back_mixed_width_fields_in_same_request(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        data = bytearray(record_bytes(1)); struct.pack_into('<f', data, 48, float('nan'))
        self.assertEqual(self.write('Records[0]', data)[2], 0x0C)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_fragment_crossing_trailing_padding_and_next_record(self):
        payload = b'\0'*4 + struct.pack('<b', -50)
        self.assertEqual(self.write('Records', payload, count=8, offset=60)[2], 0)
        expected = bytearray(b''.join(record_bytes(i) for i in range(8))); expected[60:65] = payload
        self.assertEqual(self.read('Records', 8), expected)

    def test_nested_64_bit_structure_propagates_alignment_to_parent(self):
        schema = E.fromstring('<DataType Name="Outer"><Members><Member Name="Prefix" DataType="DINT"/>'
                              '<Member Name="Child" DataType="MixedRecord"/><Member Name="Tail" DataType="SINT"/></Members></DataType>')
        self.app.engine.project.udts['outer'] = schema
        value = {'Prefix': 7, 'Child': copy.deepcopy(self.app.engine.memory.values['record']), 'Tail': -1}
        self.app.engine.project.tags['outervalue'] = Tag('OuterValue', 'Outer', value)
        self.app.engine.memory.values['outervalue'] = value
        template = self.router.templates().for_type('Outer')
        self.assertEqual((template.size, template.alignment), (80, 8))
        self.assertEqual([m.offset for m in template.members], [0, 8, 72])
        expected = struct.pack('<i4x', 7) + record_bytes(9) + struct.pack('<b7x', -1)
        self.assertEqual(self.read('OuterValue'), expected)
        self.assertEqual(self.write('OuterValue', expected, dtype='Outer')[2], 0)

    def test_readonly_member_checks_use_variable_width_coverage(self):
        self.app.engine.project.udts['mixedrecord'].find('./Members/Member[@Name="Wide"]').set('ExternalAccess', 'Read Only')
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.write('Records[0]', b'\0', offset=15)[2], 0x0F)
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.write('Records[0]', struct.pack('<i', 777), offset=16)[2], 0)
        self.assertEqual(self.app.engine.memory.read('Records[0].Count'), 777)

    def test_padded_transfer_size_bound_includes_reserved_bytes(self):
        result = self.router.handle(request(0x52, 'Records', struct.pack('<HI', 513, 0)), self.session)
        self.assertEqual(result[2], 3)
        self.assertEqual(self.write('Records', b'x', count=513, offset=0)[2], 3)

    def test_explicit_user_string_layout_has_dint_length_sint_data_and_padding(self):
        self.app.engine.project.udts['customstring'] = E.fromstring('<DataType Name="CustomString"><Members>'
            '<Member Name="LEN" DataType="DINT"/><Member Name="DATA" DataType="SINT" Dimension="10"/></Members></DataType>')
        template = self.router.templates().for_type('CustomString')
        self.assertEqual(template.size, 16)
        self.assertEqual([(m.name, m.dtype, m.offset, m.count) for m in template.members],
                         [('LEN', 'DINT', 0, 1), ('DATA', 'SINT', 4, 10)])

    def test_scan_consumes_count_from_a_mixed_width_record(self):
        data = bytearray(record_bytes(0)); struct.pack_into('<i', data, 16, 987)
        self.assertEqual(self.write('Records[0]', data)[2], 0)
        self.app.command('step', {})
        self.assertFalse(self.app.engine.fault); self.assertEqual(self.app.engine.memory.read('Observed'), 987)

    def test_atomic_array_member_within_record_array_supports_direct_read_write(self):
        name = 'Records[0].Words'
        read = self.router.handle(request(0x4C, name, b'\3\0'), self.session)
        self.assertEqual(read, b'\xCC\0\0\0' + struct.pack('<4H', 0xC7, 1, 32768, 65535))
        write = self.router.handle(request(0x4D, name, struct.pack('<5H', 0xC7, 3, 10, 20, 30)), self.session)
        self.assertEqual(write[2], 0)
        expected = bytearray(record_bytes(0)); struct.pack_into('<3H', expected, 20, 10, 20, 30)
        self.assertEqual(self.read('Records[0]'), expected)
        before = copy.deepcopy(self.app.engine.memory.values)
        bad = self.router.handle(request(0x4D, name, struct.pack('<6H', 0xC7, 4, 1, 2, 3, 4)), self.session)
        self.assertNotEqual(bad[2], 0); self.assertEqual(self.app.engine.memory.values, before)

    def test_fragmented_atomic_array_member_access_keeps_nested_array_boundary(self):
        name = 'Records[0].Group.Samples'
        raw = request(0x53, name, struct.pack('<HHI', 0xC2, 3, 1) + b'\x7F')
        self.assertEqual(self.router.handle(raw, self.session)[2], 0)
        self.assertEqual(self.app.engine.memory.read(name), [-4, 127, 5])
        read = self.router.handle(request(0x52, name, struct.pack('<HI', 3, 1)), self.session)
        self.assertEqual(read, b'\xD2\0\0\0' + struct.pack('<Hbb', 0xC2, 127, 5))
        before = copy.deepcopy(self.app.engine.memory.values)
        bad = request(0x53, name, struct.pack('<HHI', 0xC2, 4, 0) + b'\x01')
        self.assertNotEqual(self.router.handle(bad, self.session)[2], 0)
        self.assertEqual(self.app.engine.memory.values, before)


if __name__ == '__main__': unittest.main()
