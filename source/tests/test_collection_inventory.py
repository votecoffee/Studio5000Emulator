"""Synthetic collection framing checks; no private device data is bundled."""
import hashlib
import json
import struct
import unittest
from tools.collection_inventory import CollectionError, decode_attribute_list


def reply(rows, status=0):
    return bytes((0x83,0,status,0))+struct.pack('<H',len(rows))+b''.join(
        struct.pack('<HH',number,error)+data for number,error,data in rows)


def string(value, *, padded=False):
    return struct.pack('<H',len(value))+value+(b'\0' if padded and len(value)%2 else b'')


class CollectionInventoryTests(unittest.TestCase):
    def test_extended_device_odd_strings_empty_trust_and_operator_keep_exact_boundaries(self):
        values={1:string(b'Demo1'),2:string(b'Example'),3:string(b''),6:string(b'en-US'),7:bytes(2),8:bytes(4)}
        raw=reply([(n,0,data) for n,data in values.items()])
        decoded=decode_attribute_list(raw,list(values),0x64)
        self.assertEqual([r['value_bytes'] for r in decoded['attributes']],[7,9,2,7,2,4])
        self.assertEqual(decoded['attributes'][0]['value_sha256'],hashlib.sha256(values[1]).hexdigest())
        for private in ('Demo1','Example','en-US',values[1].hex()):self.assertNotIn(private,json.dumps(decoded))
        self.assertEqual(decode_attribute_list(raw,list(values),0x64,include_payloads=True)['attributes'][0]['data_hex'],values[1].hex())

    def test_network_paths_ipv4_strings_and_link_counters_have_different_layouts(self):
        values={1:bytes(4),2:bytes(4),3:bytes(4),4:b'\2\0\x20\xf6\x24\1',
                5:bytes(20)+string(b'lab',padded=True),6:string(b'vm1',padded=True)}
        decoded=decode_attribute_list(reply([(n,0,v) for n,v in values.items()]),list(values),0xF5)
        self.assertEqual([r['value_bytes'] for r in decoded['attributes']],[4,4,4,6,26,6])
        widths={1:4,2:4,3:6,4:44,5:48,6:4,7:1,8:1,9:1}
        decoded=decode_attribute_list(reply([(n,0,bytes(w)) for n,w in widths.items()]),list(widths),0xF6)
        self.assertEqual([r['value_bytes'] for r in decoded['attributes']],list(widths.values()))
        mapping=decode_attribute_list(reply([(1,0,bytes(2)),(2,0,bytes(4))]),[1,2],0x67)
        self.assertEqual([r['value_bytes'] for r in mapping['attributes']],[2,4])

    def test_partial_lists_errors_and_duplicates_keep_unreturned_suffix_separate(self):
        raw=reply([(1,0,bytes(4)),(20,0x14,b''),(1,0,bytes(4))],6)
        result=decode_attribute_list(raw,[1,20,1,6],0xF5)
        self.assertEqual([r['attribute'] for r in result['attributes']],[1,20,1])
        self.assertEqual(result['remaining_attributes'],[6]);self.assertTrue(result['partial'])
        self.assertIsNone(result['attributes'][1]['value_sha256'])
        errors=decode_attribute_list(reply([(20,0x14,b'')],0x0A),[20],0xF5)
        self.assertEqual(errors['attributes'][0]['value_bytes'],0)
        clock=decode_attribute_list(reply([(2,0,b'\0'),(5,0x14,b'')],0x0A),[2,5],0x43)
        self.assertEqual(clock['clock_semantics'],'NOT INFERRED')

    def test_opaque_trust_paths_unknown_success_and_oversize_strings_are_not_guessed(self):
        cases=((0x64,7,b'\1\0'),(0x64,1,string(b'x'*41)),(0x64,2,string(b'x'*129)),
               (0xF5,4,struct.pack('<H',65)+bytes(130)),(0xF5,5,bytes(20)+string(b'x'*49,padded=True)),
               (0xF5,6,string(b'x'*65,padded=True)),(0xF5,10,bytes(1)),(0x67,3,bytes(4)))
        for cls,n,data in cases:
            with self.subTest(cls=cls,n=n),self.assertRaises(CollectionError):
                decode_attribute_list(reply([(n,0,data)]),[n],cls)

    def test_every_truncation_trailing_data_and_wrong_padding_reject_without_partial_rows(self):
        raw=reply([(5,0,bytes(20)+string(b'lab',padded=True)),(6,0,string(b'vm1',padded=True))])
        for end in range(len(raw)):
            with self.subTest(end=end),self.assertRaises(CollectionError):decode_attribute_list(raw[:end],[5,6],0xF5)
        for malformed in (raw+b'\0',reply([(6,0,string(b'vm1')+b'x')]),reply([(6,0,string(b'vm1'))])):
            with self.assertRaises(CollectionError):decode_attribute_list(malformed,[5,6] if malformed.startswith(raw) else [6],0xF5)
        # Extended Device strings are not the padded TCP/IP string profile.
        with self.assertRaises(CollectionError):decode_attribute_list(reply([(1,0,string(b'abc',padded=True))]),[1],0x64)

    def test_invalid_headers_counts_order_status_and_requests_fail_closed(self):
        for raw,requested in ((reply([(1,0,bytes(4))],6),[1]),(reply([],6),[1]),
                (reply([(1,0,bytes(4))]),[2]),(reply([(1,0,bytes(4))],0x0A),[1]),
                (reply([(1,0x14,b'')]),[1]),(bytes.fromhex('83000001'),[1])):
            with self.assertRaises(CollectionError):decode_attribute_list(raw,requested,0xF5)
        raw=reply([(1,0,bytes(4))])
        for requested in ([],[1]*33,[True],[0],[65536],None):
            with self.assertRaises(CollectionError):decode_attribute_list(raw,requested,0xF5)
        for cls in (True,None,0x8E):
            with self.assertRaises(CollectionError):decode_attribute_list(raw,[1],cls)
        with self.assertRaises(CollectionError):decode_attribute_list(bytes.fromhex('83000000010001000000'),[1],0x43)


if __name__=='__main__':unittest.main()
