"""Synthetic object graphs, with no active catalog or memory installation."""
from dataclasses import FrozenInstanceError
import json
import struct
import unittest
from logixlab import device_payload as dp,object_staging as os
import test_template_staging as templates


def request(cls,instance=1,payload=b'',service=8,program=0,path=None):
    path=path if path is not None else ((b'\x20\x68\x25\0'+struct.pack('<H',program) if program else b'')
        +bytes((0x20,cls,0x25,0))+struct.pack('<H',instance))
    raw=bytes((service,len(path)//2))+path+payload
    return dp.records(struct.pack('<I',len(raw))+raw)[0]


def symbol(instance=1,table=1,program=0,order=(12,9),safety=0):
    values={12:struct.pack('<I',table),9:bytes((safety,))}
    data=struct.pack('<H',len(order))+b''.join(struct.pack('<H',a)+values[a] for a in order)
    return request(0x6B,instance,data,program=program)


def table(instance=1,symbol=1,code=0xC4,dims=(0,0,0),use=0x6A,extended=0,order=(6,2,1,8,9)):
    values={6:struct.pack('<H',use),2:struct.pack('<H',code),1:struct.pack('<III',*dims),8:struct.pack('<I',symbol),9:struct.pack('<H',extended)}
    data=struct.pack('<H',len(order))+b''.join(struct.pack('<H',a)+values[a] for a in order)
    return request(0x6A,instance,data)


def coordinate(program=2,acquire=True):return request(0x74,1,b'\1' if acquire else b'',0x4B if acquire else 0x4C,program)


def batch():
    return (symbol(),table(),request(0x68,2),coordinate(),symbol(table=os.NULL_REFERENCE,program=2),
            request(0x6D,1,b'\0\0',program=2),coordinate(acquire=False))


class ObjectModelTests(unittest.TestCase):
    def test_scoped_ids_forward_references_and_immutable_private_models(self):
        stage=os.ObjectStaging.from_batch(batch());report=stage.description()
        self.assertEqual([report[f] for f in ('symbols','tables','programs','routines','coordination_records','records_modeled','storage_bytes')],[2,1,1,1,2,7,4])
        self.assertTrue(report['references_validated']);self.assertEqual(report['open_coordination'],0)
        self.assertEqual([(s.program,s.instance) for s in stage.symbols],[(0,1),(2,1)])
        with self.assertRaises(FrozenInstanceError):stage.symbols[0].table=2
        for flag in ('definitions_exposed','active_catalog_replaced','commit'):self.assertFalse(report[flag])
        self.assertNotIn('instance',json.dumps(report));report['tables']=999;self.assertEqual(stage.description()['tables'],1)

    def test_attributes_can_reorder_and_table_references_validate_after_all_creates(self):
        stage=os.ObjectStaging.from_batch((table(order=(9,8,1,2,6)),symbol(order=(9,12))))
        self.assertEqual(stage.tables[0].type_code,0xC4)
        for factory in (symbol,table):
            rec=factory();start=2+2*rec.request[1];data=rec.request[start:]
            for raw in (data[:i] for i in range(len(data))):
                with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((request(rec.scopes[-1].class_id,payload=raw),))
            with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((request(rec.scopes[-1].class_id,payload=data+b'\0'),))
        for rec in (symbol(order=(12,12)),table(order=(6,2,1,8,8))):
            with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((rec,))

    def test_missing_or_nonreciprocal_links_are_rejected(self):
        for records in ((symbol(),),(table(),),(symbol(table=2),table()),(symbol(),table(symbol=2)),
                        (symbol(table=0),),(symbol(table=65536),),(symbol(table=os.NULL_REFERENCE),table())):
            with self.subTest(records=records),self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch(records)

    def test_scoped_symbols_require_a_created_parent_held_coordination_and_unbound_reference(self):
        for records in ((symbol(table=os.NULL_REFERENCE,program=2),),
                        (request(0x68,2),symbol(table=os.NULL_REFERENCE,program=2)),
                        (request(0x68,2),coordinate(),symbol(program=2),coordinate(acquire=False))):
            with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch(records)

    def test_coordination_requires_exact_balanced_acquire_release_and_routine_payloads(self):
        program=request(0x68,2)
        for tail in ((coordinate(),),(coordinate(acquire=False),),(coordinate(),coordinate()),
                     (request(0x74,1,b'\0',0x4B,2),),(coordinate(),request(0x74,1,b'\0',0x4C,2)),
                     (request(0x74,2,b'\1',0x4B,2),),(request(0x6D,1,b'\0\0',program=2),),
                     (coordinate(),request(0x6D,1,b'',program=2),coordinate(acquire=False)),
                     (coordinate(),request(0x6D,1,b'\1\0',program=2),coordinate(acquire=False))):
            with self.subTest(tail=tail),self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((program,)+tail)
        with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((request(0x68,payload=b'\0'),))

    def test_duplicate_instances_are_rejected_per_class_and_program_scope(self):
        for records in (batch()[:1]*2,batch()[:2]+(table(),),(request(0x68),)*2,
                        (request(0x68,2),coordinate(),request(0x6D,1,b'\0\0',program=2),request(0x6D,1,b'\0\0',program=2),coordinate(acquire=False))):
            with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch(records)
        rows=tuple(r for p in (1,2) for r in (request(0x68,p),coordinate(p),symbol(table=os.NULL_REFERENCE,program=p),request(0x6D,1,b'\0\0',program=p),coordinate(p,False)))
        self.assertEqual(len(os.ObjectStaging.from_batch(rows).routines),2)

    def test_structures_require_staged_templates_and_use_declared_metadata_size(self):
        types=templates.ts.TemplateStaging.from_batch(templates.batch()).templates
        rows=(symbol(),table(code=0x8001))
        with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch(rows)
        self.assertEqual(os.ObjectStaging.from_batch(rows,types).tables[0].storage_bytes,4)

    def test_type_rank_dimension_and_element_limits_are_checked(self):
        for code,dims in ((0xC4,(1,0,0)),(0x20C4,(0,0,0)),(0x20C4,(1,1,0)),(0x40C4,(1,0,0)),
                          (0x10C4,(0,0,0)),(0xFF,(0,0,0)),(0x20C4,(os.MAX_ELEMENTS+1,0,0)),(0x60C4,(0xFFFFFFFF,0xFFFFFFFF,0xFFFFFFFF))):
            with self.subTest(code=code,dims=dims),self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((symbol(),table(code=code,dims=dims)))
        for rank,dims,elements in ((1,(2,0,0),2),(2,(2,3,0),6),(3,(2,3,4),24)):
            row=os.ObjectStaging.from_batch((symbol(),table(code=0xC4|(rank<<13),dims=dims))).tables[0]
            self.assertEqual((row.elements,row.storage_bytes),(elements,elements*4))

    def test_internal_tables_and_profile_flags_do_not_create_active_memory(self):
        self.assertEqual(os.ObjectStaging.from_batch((table(symbol=os.NULL_REFERENCE,use=4,code=0x20C2,dims=(123,0,0)),)).tables[0].storage_bytes,123)
        for records in ((symbol(safety=1),),(symbol(),table(extended=1)),(table(use=4),),
                        (table(symbol=os.NULL_REFERENCE),),(table(use=7),)):
            with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch(records)

    def test_exact_aggregate_storage_capacity_and_excess(self):
        def rows(count):return tuple(r for i in range(1,count+1) for r in (symbol(i,i),table(i,i,0x20C5,(os.MAX_ELEMENTS,0,0))))
        self.assertEqual(os.ObjectStaging.from_batch(rows(2)).description()['storage_bytes'],os.MAX_STORAGE_BYTES)
        with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch(rows(3))
        types=templates.ts.TemplateStaging.from_batch(templates.batch()).templates
        from dataclasses import replace
        types=(replace(types[0],attributes=replace(types[0].attributes,structure_bytes=os.MAX_STORAGE_BYTES)),)
        with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((symbol(),table(code=0xA001,dims=(2,0,0))),types)

    def test_exact_object_caps_and_excess(self):
        groups=(tuple(symbol(i,os.NULL_REFERENCE) for i in range(1,os.MAX_SYMBOLS+1)),
                tuple(table(i,os.NULL_REFERENCE,use=4) for i in range(1,os.MAX_TABLES+1)),
                tuple(request(0x68,i) for i in range(1,os.MAX_PROGRAMS+1)))
        extras=(symbol(os.MAX_SYMBOLS+1,os.NULL_REFERENCE),table(os.MAX_TABLES+1,os.NULL_REFERENCE,use=4),request(0x68,os.MAX_PROGRAMS+1))
        for rows,extra in zip(groups,extras):
            os.ObjectStaging.from_batch(rows)
            with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch(rows+(extra,))
        rows=(request(0x68,2),coordinate())+tuple(request(0x6D,i,b'\0\0',program=2) for i in range(1,os.MAX_ROUTINES+1))
        self.assertEqual(len(os.ObjectStaging.from_batch(rows+(coordinate(acquire=False),)).routines),os.MAX_ROUTINES)
        with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch(rows+(request(0x6D,os.MAX_ROUTINES+1,b'\0\0',program=2),coordinate(acquire=False)))

    def test_qualified_unexpected_parent_zero_and_reserved_instances_are_rejected(self):
        for path in (bytes.fromhex('206b24013001'),bytes.fromhex('206b240191024142'),bytes.fromhex('20692401206b2401'),
                     bytes.fromhex('206b2400'),bytes.fromhex('206b2500ffff'),bytes.fromhex('206b260000000100')):
            with self.subTest(path=path),self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((request(0x6B,path=path),))
        for cls in (0x6D,0x74):
            with self.assertRaises(os.ObjectError):os.ObjectStaging.from_batch((request(cls),))

    def test_unhandled_services_and_unrelated_classes_do_not_dispatch(self):
        stage=os.ObjectStaging.from_batch((request(0x6A,service=3),request(0x7F)))
        self.assertEqual(stage.description()['status'],'idle');self.assertEqual(stage.records,0)


if __name__=='__main__':unittest.main()
