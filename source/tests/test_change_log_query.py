"""Observed reply shapes stay structural, bounded and separate from history authority."""
import hashlib,json,struct,unittest
from tools.change_log_query import frame,describe

QUERY=bytes.fromhex('4f0220ac2401')+struct.pack('<HH',12,3)


class ChangeLogQueryTests(unittest.TestCase):
    def test_cursor_only_and_opaque_summary_preserve_positions_without_interpreting_records(self):
        cursor=struct.pack('<HH',13,3);opaque=bytes(range(32))
        self.assertEqual(frame(QUERY,b'\xcf\0\0\0'+QUERY[-4:]),((12,3),(12,3),None,0))
        self.assertEqual(frame(QUERY,b'\xcf\0\0\0'+opaque+cursor),((12,3),(13,3),opaque,0))
        proof=describe(QUERY,b'\xcf\0\0\0'+opaque+cursor)
        self.assertEqual(proof['shape'],'opaque_summary');self.assertEqual(proof['summary_bytes'],32)
        self.assertEqual(proof['summary_sha256'],hashlib.sha256(opaque).hexdigest())
        self.assertTrue(proof['cursor_changed']);self.assertFalse(proof['cursor_echoed'])
        for field in ('summary_fields_interpreted','records_decoded','history_supplied','source_binding_verified',
                      'mac_verified','native_acceptance_verified','payloads_exposed'):self.assertFalse(proof[field])
        self.assertNotIn(opaque.hex(),json.dumps(proof));self.assertNotIn('next_index',proof)
        self.assertEqual(describe(QUERY,b'\xcf\0\0\0'+bytes(32)+cursor)['shape'],'opaque_summary')

    def test_rejections_and_additional_status_are_not_success_or_empty_history(self):
        for response in (bytes.fromhex('cf000c00'),bytes.fromhex('cf000c013412')):
            value=describe(QUERY,response);self.assertEqual(value['shape'],'rejected')
            self.assertEqual(value['status'],12);self.assertIsNone(value['cursor_echoed'])
        for response in (bytes.fromhex('cf000c0034'),bytes.fromhex('cf000c0134')):
            with self.assertRaises(ValueError):frame(QUERY,response)

    def test_bad_scopes_services_headers_and_payload_extents_fail_whole_decode(self):
        answer=b'\xcf\0\0\0'+QUERY[-4:]
        for request in (QUERY[:-1],QUERY+b'x',bytes.fromhex('500220ac2401')+QUERY[-4:],
                        bytes.fromhex('4f0220ac2402')+QUERY[-4:],bytes.fromhex('4f0220ab2401')+QUERY[-4:],
                        bytes.fromhex('4f0320ac24013001')+QUERY[-4:]):
            with self.assertRaises(ValueError):frame(request,answer)
        for n in range(69):
            if n in (4,36):continue
            with self.assertRaises(ValueError):frame(QUERY,b'\xcf\0\0\0'+bytes(n))
        for response in (b'',b'\xce\0\0\0'+QUERY[-4:],b'\xcf\1\0\0'+QUERY[-4:],b'\xcf\0\0\x11'+bytes(34)):
            with self.assertRaises(ValueError):frame(QUERY,response)


if __name__=='__main__':unittest.main()
