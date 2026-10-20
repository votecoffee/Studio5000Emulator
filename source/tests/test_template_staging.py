"""Synthetic native Template models; definitions never enter the active catalog."""
from dataclasses import FrozenInstanceError
import json
import struct
import unittest
from unittest.mock import patch

from logixlab import device_payload as dp,template_staging as ts


def request(service,payload=b'',instance=1,path=None):
    path=path if path is not None else b'\x20\x6c\x25\0'+struct.pack('<H',instance)
    raw=bytes((service,len(path)//2))+path+payload
    return dp.records(struct.pack('<I',len(raw))+raw)[0]


def attrs(order=(1,2,5,6,8),**kw):
    values={1:struct.pack('<H',kw.get('handle',0x1234)),2:struct.pack('<H',kw.get('members',1)),
            5:struct.pack('<I',kw.get('size',4)),6:struct.pack('<H',kw.get('family',1)),8:bytes((kw.get('recon',2),))}
    return struct.pack('<H',len(order))+b''.join(struct.pack('<H',i)+values[i] for i in order)


def write(data=b'PrivateData!',offset=0):return struct.pack('<IH',offset,len(data))+data


def batch(instance=1,data=b'PrivateData!'):
    assert len(data)%4==0
    return (request(8,b'\1\0\4\0'+struct.pack('<I',(len(data)+20)//4),instance),
            request(4,attrs(),instance),request(0x4D,write(data),instance))


class TemplateModelTests(unittest.TestCase):
    def test_multiple_objects_fragmented_definition_and_reordered_attributes(self):
        one=list(batch());one[1]=request(4,attrs((8,6,5,2,1),family=65535,recon=255))
        one[2:]=[request(0x4D,write(b'Priv')),request(0x4D,write(b'ateData!',4))]
        other=request(8,b'opaque',path=bytes.fromhex('20682401'))
        stage=ts.TemplateStaging.from_batch(tuple(one)+batch(2)+ (other,))
        self.assertEqual(stage.templates[0].definition,b'PrivateData!')
        self.assertEqual((stage.templates[0].words,stage.templates[0].attributes.family,stage.templates[0].attributes.recon),(8,65535,255))
        report=stage.description()
        self.assertEqual([report[k] for k in ('templates','definition_bytes','write_fragments','records_modeled','unsupported_records')],[2,24,3,7,1])
        for text in ('PrivateData!',b'PrivateData!'.hex(),'4660'):self.assertNotIn(text,json.dumps(report))
        for flag in ('definitions_exposed','active_catalog_replaced','commit'):self.assertFalse(report[flag])
        with self.assertRaises(FrozenInstanceError):stage.templates[0].words=99
        report['templates']=999;self.assertEqual(stage.description()['templates'],2)

    def test_create_attributes_and_write_require_order_and_one_definition_per_instance(self):
        c,a,w=batch()
        for records in ((a,c,w),(c,w,a),(c,c,a,w),(c,a,a,w),(c,a,w,w),(c,), (c,a), (c,a,w,batch(2)[0])):
            with self.subTest(records=records),self.assertRaises(ts.TemplateError):ts.TemplateStaging.from_batch(records)

    def test_create_requires_exact_attribute_four_and_bounded_size(self):
        for payload in (b'',b'\1\0\4\0',b'\1\0\5\0'+struct.pack('<I',8),b'\1\0\4\0'+struct.pack('<I',8)+b'\0',
                        b'\1\0\4\0'+struct.pack('<I',5),b'\1\0\4\0'+struct.pack('<I',2**32-1)):
            with self.assertRaises(ts.TemplateError):ts.TemplateStaging.from_batch((request(8,payload),))

    def test_attributes_have_known_unique_ids_exact_widths_and_bounded_counts(self):
        c,a,w=batch()
        for payload in (attrs()[:-1],attrs()+b'\0',attrs((1,1,5,6,8)),attrs((1,2,5,6)),
                        attrs().replace(b'\x08\0\x02',b'\x09\0\x02'),attrs(members=0),attrs(members=ts.MAX_MEMBERS+1),
                        attrs(size=0),attrs(size=ts.MAX_STRUCTURE_BYTES+1)):
            with self.subTest(payload=payload),self.assertRaises(ts.TemplateError):ts.TemplateStaging.from_batch((c,request(4,payload),w))

    def test_write_rejects_overlap_holes_truncation_zero_trailing_and_out_of_bounds(self):
        c,a,w=batch()
        for payload in (b'',write(b''),write()[:-1],write()+b'\0',write(offset=1),write(b'X'*16),write(offset=2**32-1)):
            with self.subTest(payload=payload),self.assertRaises(ts.TemplateError):ts.TemplateStaging.from_batch((c,a,request(0x4D,payload)))
        for offset in (0,5):
            with self.assertRaises(ts.TemplateError):ts.TemplateStaging.from_batch((c,a,request(0x4D,write(b'Priv')),request(0x4D,write(b'ateData!',offset))))

    def test_definition_and_write_capacity_and_stage_limits_are_enforced_before_allocation(self):
        data=b'X'*ts.MAX_DEFINITION_BYTES;c=request(8,b'\1\0\4\0'+struct.pack('<I',(len(data)+20)//4));a=request(4,attrs())
        writes=tuple(request(0x4D,write(data[i:i+ts.MAX_WRITE_BYTES],i)) for i in range(0,len(data),ts.MAX_WRITE_BYTES))
        self.assertEqual(len(ts.TemplateStaging.from_batch((c,a)+writes).templates[0].definition),ts.MAX_DEFINITION_BYTES)
        with self.assertRaises(ts.TemplateError):ts.TemplateStaging.from_batch((c,a,request(0x4D,write(b'X'*(ts.MAX_WRITE_BYTES+1)))))
        for limit,value in (('MAX_TEMPLATES',1),('MAX_TOTAL_BYTES',23)):
            with patch.object(ts,limit,value),self.assertRaises(ts.TemplateError):ts.TemplateStaging.from_batch(batch()+batch(2))

    def test_scoped_attribute_symbol_and_invalid_instance_targets_are_rejected(self):
        for path in (bytes.fromhex('20682401206c2401'),bytes.fromhex('206c24013001'),bytes.fromhex('206c240191024142'),
                     bytes.fromhex('206c2400'),bytes.fromhex('206c25000010')):
            with self.subTest(path=path),self.assertRaises(ts.TemplateError):ts.TemplateStaging.from_batch((request(8,batch()[0].request[8:],path=path),))

    def test_unhandled_records_count_without_dispatch_and_empty_model_is_idle(self):
        stage=ts.TemplateStaging.from_batch((request(5),request(8,path=bytes.fromhex('206b2401'))))
        self.assertEqual(stage.description()['unsupported_records'],2);self.assertEqual(stage.templates,())
        self.assertEqual(ts.TemplateStaging().description()['status'],'idle')


if __name__=='__main__':unittest.main()
