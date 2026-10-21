"""Synthetic framing cases; no captured project identities or clock samples."""
import hashlib
import struct
import unittest

from tools.time_sync_inventory import TimeSyncError, decode_attribute_list


def reply(rows, status=0):
    return bytes((0x83, 0, status, 0))+struct.pack('<H', len(rows))+b''.join(
        struct.pack('<HH', number, error)+data for number, error, data in rows)


class TimeSyncInventoryTests(unittest.TestCase):
    def test_partial_prefix_and_followup_are_independent_lists(self):
        first = reply([(1, 0, b'\0'), (3, 0, struct.pack('<q', 1234))], 6)
        decoded = decode_attribute_list(first, [1, 3, 28])
        self.assertTrue(decoded['partial'])
        self.assertEqual(decoded['remaining_attributes'], [28])
        self.assertEqual([row['value_bytes'] for row in decoded['attributes']], [1, 8])
        second = decode_attribute_list(reply([(28, 0, struct.pack('<qq', 0, 1235))]), [28])
        self.assertFalse(second['partial'])
        self.assertEqual(second['remaining_attributes'], [])
        self.assertEqual(decoded['remaining_attributes'], [28])

    def test_duplicate_attributes_and_errors_preserve_order(self):
        raw = reply([(21, 0, struct.pack('<I', 4)+b'Demo'), (5, 0x14, b''),
                     (21, 0, struct.pack('<I', 4)+b'Demo')], 0x0A)
        result = decode_attribute_list(raw, [21, 5, 21])
        self.assertEqual([row['status'] for row in result['attributes']], [0, 0x14, 0])
        self.assertIsNone(result['attributes'][1]['value_sha256'])
        self.assertEqual(result['attributes'][0]['value_sha256'],
                         hashlib.sha256(struct.pack('<I', 4)+b'Demo').hexdigest())
        self.assertNotIn('data_hex', result['attributes'][0])
        self.assertNotIn('44656d6f', str(result))
        self.assertEqual(decode_attribute_list(raw, [21, 5, 21], include_payloads=True)
                         ['attributes'][0]['data_hex'], '0400000044656d6f')

    def test_all_documented_fixed_fields_have_independent_wire_widths(self):
        widths = {1:1,2:1,3:8,4:8,5:8,6:8,7:8,8:24,9:16,10:20,11:2,
                  16:1,17:1,18:1,19:2,20:4,27:2,28:16,102:10}
        decoded = decode_attribute_list(reply([(n, 0, bytes(w)) for n, w in widths.items()]), list(widths))
        self.assertEqual([row['value_bytes'] for row in decoded['attributes']], list(widths.values()))

    def test_empty_and_counted_port_arrays_and_fixed_address_storage(self):
        widths = {12:4,13:4,14:4,15:4,24:10,25:36,26:22}
        for count in (0, 2, 10):
            rows = [(n, 0, struct.pack('<H', count)+bytes(w*count)) for n, w in widths.items()]
            result = decode_attribute_list(reply(rows), list(widths))
            self.assertEqual([row['value_bytes'] for row in result['attributes']],
                             [2+w*count for w in widths.values()])
        for attr, width, offset in ((25, 36, 18), (26, 22, 4)):
            data = bytearray(struct.pack('<H', 1)+bytes(width))
            struct.pack_into('<H', data, 2+offset, 17)
            with self.assertRaisesRegex(TimeSyncError, 'address exceeds'):
                decode_attribute_list(reply([(attr, 0, data)]), [attr])
        with self.assertRaisesRegex(TimeSyncError, 'port count'):
            decode_attribute_list(reply([(12, 0, struct.pack('<H', 11)+bytes(44))]), [12])

    def test_vendor_descriptions_use_counted_strings_and_counted_addresses(self):
        # Synthetic identity bytes deliberately carry no manufacturer OUI.
        identity = b'\x02\0\0\0\0\0\0\1'
        def text(value):
            return bytes((len(value),))+value
        clock = identity+bytes(6)+b''.join(text(s) for s in (b'Example', b'Clock', b'', b'', b'', b'1'))+bytes(6)
        for physical, protocol in ((b'', b''), (bytes(4), bytes(4)), (bytes(16), bytes(16))):
            port = identity+struct.pack('<H', 1)+text(b'Software')
            port += struct.pack('<H', len(physical))+physical+struct.pack('<HH', 0, len(protocol))+protocol
            user = identity+text(b'Demo')+text(b'')
            result = decode_attribute_list(reply([(103, 0, clock), (104, 0, port), (105, 0, user)]), [103, 104, 105])
            self.assertEqual([row['value_bytes'] for row in result['attributes']], [len(clock), len(port), len(user)])
        for attr, value in ((103, bytes(14)+b'\x41'), (104, bytes(10)+b'\x21'),
                            (104, bytes(10)+b'\0'+struct.pack('<H', 17)), (105, bytes(8)+b'\x81')):
            with self.assertRaises(TimeSyncError):
                decode_attribute_list(reply([(attr, 0, value)]), [attr])

    def test_unknown_success_and_truncation_never_guess_the_next_field(self):
        with self.assertRaisesRegex(TimeSyncError, 'no established decoder'):
            decode_attribute_list(reply([(999, 0, bytes(4))]), [999])
        self.assertEqual(decode_attribute_list(reply([(999, 0x14, b'')], 0x0A), [999])['attributes'][0]['status'], 0x14)
        raw = reply([(21, 0, struct.pack('<I', 4)+b'Demo'), (28, 0, bytes(16))])
        for size in range(len(raw)):
            with self.subTest(size=size), self.assertRaises(TimeSyncError):
                decode_attribute_list(raw[:size], [21, 28])
        with self.assertRaisesRegex(TimeSyncError, 'trailing data'):
            decode_attribute_list(raw+b'\0', [21, 28])

    def test_bad_counts_order_headers_and_statuses_are_rejected(self):
        for raw, requested in ((reply([(1, 0, b'\0')], 6), [1]),
                               (reply([], 6), [1]), (reply([(1, 0, b'\0')]), [1, 2]),
                               (reply([(2, 0, b'\0')]), [1]),
                               (reply([(1, 0x14, b'')]), [1]),
                               (reply([(1, 0, b'\0')], 0x0A), [1]),
                               (bytes.fromhex('83000800'), [1]),
                               (bytes.fromhex('8e000000'), [1]),
                               (bytes.fromhex('83000001'), [1]),
                               (reply([(1, 0, b'\0')]), []),
                               (reply([(1, 0, b'\0')]), [True])):
            with self.subTest(raw=raw, requested=requested), self.assertRaises(TimeSyncError):
                decode_attribute_list(raw, requested)


if __name__ == '__main__':
    unittest.main()
