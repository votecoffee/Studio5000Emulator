"""Synthetic native diagnostics remain temporary and private."""
from dataclasses import FrozenInstanceError
import json
import struct
import unittest

from logixlab import device_payload as dp,diagnostic_staging as ds


def payload(name=b'PrivateMessage',code=b'PRIVATE-CODE',revision=1,order=(1,2,3)):
    values={1:bytes((len(name),))+name,2:bytes((len(code),))+code,3:struct.pack('<H',revision)}
    return struct.pack('<H',len(order))+b''.join(struct.pack('<H',a)+values[a] for a in order)


def request(data=None,instance=1,service=8,path=None):
    path=path if path is not None else bytes.fromhex('2100b2032600')+struct.pack('<I',instance)
    raw=bytes((service,len(path)//2))+path+(payload() if data is None else data)
    return dp.records(struct.pack('<I',len(raw))+raw)[0]


class DiagnosticModelTests(unittest.TestCase):
    def test_reordered_attributes_unsigned_revision_shared_code_and_immutable_private_objects(self):
        stage=ds.DiagnosticStaging.from_batch((request(payload(order=(3,2,1),revision=65535)),request(payload(name=b'SecondMessage'),2)))
        self.assertEqual(stage.messages[0].message_id,b'PrivateMessage');self.assertEqual(stage.messages[0].code,b'PRIVATE-CODE')
        self.assertEqual(stage.messages[0].revision,65535)
        with self.assertRaises(FrozenInstanceError):stage.messages[0].revision=0
        report=stage.description();self.assertEqual(report['messages'],2);self.assertEqual(report['records_modeled'],2)
        for secret in ('PrivateMessage','PRIVATE-CODE',b'PRIVATE-CODE'.hex(),'65535'):self.assertNotIn(secret,json.dumps(report))
        for field in ('definitions_exposed','active_catalog_replaced','commit'):self.assertFalse(report[field])
        report['messages']=99;self.assertEqual(stage.description()['messages'],2)

    def test_truncations_trailing_data_wrong_counts_duplicate_and_unknown_attributes_are_rejected(self):
        raw=payload()
        bad=[raw[:i] for i in range(len(raw))]+[raw+b'\0',payload(order=(1,1,3)),payload(order=(1,2)),raw.replace(b'\x03\0\x01\0',b'\x04\0\x01\0')]
        for data in bad:
            with self.subTest(data=data),self.assertRaises(ds.DiagnosticError):ds.DiagnosticStaging.from_batch((request(data),))

    def test_strings_are_nonempty_bounded_and_reject_controls_nonascii_and_invalid_message_ids(self):
        for name,code in ((b'',b'C'),(b'A'*41,b'C'),(b'9BAD',b'C'),(b'Bad-ID',b'C'),(b'A\xff',b'C'),
                          (b'A',b''),(b'A',b'\0'),(b'A',b'\n'),(b'A',b'\xff'),(b'A',b'\x7f')):
            with self.subTest(name=name,code=code),self.assertRaises(ds.DiagnosticError):ds.DiagnosticStaging.from_batch((request(payload(name,code)),))
        stage=ds.DiagnosticStaging.from_batch((request(payload(b'A'*40,b'C'*255,0)),))
        self.assertEqual(stage.description()['text_bytes'],295)

    def test_duplicate_instance_or_message_id_is_rejected_atomically(self):
        first=request()
        for second in (request(payload(name=b'Other')),request(instance=2)):
            with self.assertRaises(ds.DiagnosticError):ds.DiagnosticStaging.from_batch((first,second))

    def test_exact_message_and_text_capacities_accept_and_excess_is_rejected(self):
        messages=tuple(request(payload(f'M{i:04d}'.encode(),b'C'),i+1) for i in range(ds.MAX_MESSAGES))
        self.assertEqual(len(ds.DiagnosticStaging.from_batch(messages).messages),ds.MAX_MESSAGES)
        with self.assertRaises(ds.DiagnosticError):ds.DiagnosticStaging.from_batch(messages+(request(payload(b'Extra',b'C'),ds.MAX_MESSAGES+1),))
        messages=tuple(request(payload(f'M{i:03d}'.encode(),b'C'*252),i+1) for i in range(256))
        self.assertEqual(ds.DiagnosticStaging.from_batch(messages).description()['text_bytes'],ds.MAX_TEXT_BYTES)
        with self.assertRaises(ds.DiagnosticError):ds.DiagnosticStaging.from_batch(messages+(request(payload(b'Extra',b'C'),257),))

    def test_unqualified_instance_bounds_and_scope_attribute_or_symbol_paths_fail_closed(self):
        self.assertEqual(ds.DiagnosticStaging.from_batch((request(instance=0xFFFFFFFF),)).messages[0].instance,0xFFFFFFFF)
        for path in (bytes.fromhex('206824012100b2032401'),bytes.fromhex('2100b20324013001'),
                     bytes.fromhex('2100b203240191024142'),bytes.fromhex('2100b2032400')):
            with self.subTest(path=path),self.assertRaises(ds.DiagnosticError):ds.DiagnosticStaging.from_batch((request(path=path),))

    def test_unknown_operations_and_other_classes_are_never_dispatched(self):
        stage=ds.DiagnosticStaging.from_batch((request(service=5),request(path=bytes.fromhex('206c2401'))))
        self.assertEqual(stage.messages,());self.assertEqual(stage.description()['status'],'idle')


if __name__=='__main__':unittest.main()
