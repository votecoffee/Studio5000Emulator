"""Repeated Table IDs must keep distinct scopes, effects and model addresses."""
from dataclasses import replace
import struct
from types import MappingProxyType
import unittest
import zlib

from logixlab.download_image import ImageError
from logixlab.download_namespace import DownloadNamespace
from logixlab.incremental_download import IncrementalDownload
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.native_routines import NativeRoutines
from logixlab.native_tables import NativeTables
from logixlab.resilient_transport import ResilientTransport
from logixlab import source_object_verification
from test_native_types import catalog,source_types
import test_device_payload as payloads
import test_download_image as images
import test_object_staging as objects


class ScopedDownloadTableTests(unittest.TestCase):
    def setUp(self):
        prefix=tuple(r for r in images.batch() if r.scopes[-1].class_id in (0x6C,0x3B2))
        rows=prefix+(objects.symbol(),objects.table())
        rows+=tuple(r for p in (2,3) for r in (objects.request(0x68,p),objects.coordinate(p),objects.symbol(program=p),
            objects.table(program=p),objects.request(0x6D,1,b'\0\0',program=p),objects.coordinate(p,False)))
        self.native=catalog(types=source_types()[:1]);self.stage=ResilientTransport()
        expanded=b''.join(payloads.record(r.request) for r in rows)
        payloads.fill(self.stage,payloads.container(zlib.compress(expanded)),expanded)
        symbols=NativeSymbols('a'*64,'b'*64,[Symbol('',0,'Global',1),Symbol('A',2,'Local',1),Symbol('B',3,'Local',1)],
            programs=[dict(name='A',instance=2),dict(name='B',instance=3)])
        routines=NativeRoutines('a'*64,'b'*64,[dict(program=n,program_instance=p,name='Logic',instance=1) for n,p in (('A',2),('B',3))])
        tables=NativeTables('a'*64,'b'*64,[dict(instance=1,name='$same$',body_bytes=420,program_instance=p) for p in (0,2,3)])
        self.catalogs=dict(native_symbols=symbols,native_routines=routines,native_tables=tables)
        self.stage.inspect_payload(self.native,**self.catalogs);self.stage.start_prepared_image()
        self.namespace=DownloadNamespace(self.stage,self.native,**self.catalogs);self.image=self.namespace._image;self.source=self.image.source

    def test_same_numeric_ids_have_unique_handles_and_exact_parent_pages(self):
        self.assertEqual(self.stage.source_object_verification['tables_matched'],3)
        handles=self.namespace._tables
        self.assertEqual([h.key for h in handles],[1,(2,1),(3,1)])
        self.assertEqual(len({h.address for h in handles}),3);self.assertEqual(len({h.value_address for h in handles}),3)
        for program,handle in zip((0,2,3),handles,strict=True):
            self.assertEqual(self.namespace.table_page(0,12,program),(False,struct.pack('<III',1,handle.address,handle.value_address)))
            self.assertEqual(self.namespace.resolve_table(handle.address).program,program)
            self.assertEqual(self.image.read_symbol(program,1,0,4,self.source),bytes(4))
        self.stage.clear();self.namespace.validate_base(self.source,self.native,**self.catalogs)
        for program in (True,-1,4):
            with self.assertRaises(ImageError):self.namespace.table_page(0,12,program)

    def writes(self,program,value):
        payload=struct.pack('<IBH',0,0,4)+struct.pack('<i',value)
        return (objects.coordinate(program),objects.request(0x6A,1,payload,0x50,program),objects.coordinate(program,False))

    def test_incremental_values_and_effect_readbacks_never_cross_programs(self):
        proposal=IncrementalDownload.prepare(self.writes(2,-123)+self.writes(3,456),self.image,self.source)
        proposal.verify_effects(self.image,self.source);self.namespace._incremental=proposal
        for handle,expected in zip(self.namespace._tables,(0,-123,456),strict=True):
            self.assertEqual(self.namespace.read_values(handle.value_address,4),struct.pack('<i',expected))
            self.assertEqual(self.image.read_table(handle.key,0,4,self.source),bytes(4))
        changed=dict(proposal._tables);changed[2,1]=replace(changed[2,1],data=changed[3,1].data)
        proposal._tables=MappingProxyType(changed)
        with self.assertRaises(ImageError):proposal.verify_effects(self.image,self.source)

    def test_missing_scoped_table_binding_cannot_be_mistaken_for_a_complete_match(self):
        controller_only=NativeTables('a'*64,'b'*64,[dict(instance=1,name='$same$',body_bytes=420)])
        result=source_object_verification.verify(self.stage.objects,self.source,self.catalogs['native_symbols'],
            self.catalogs['native_routines'],tables=controller_only)
        self.assertEqual(result['status'],'mismatch');self.assertEqual(result['tables_unresolved'],2)
        self.assertFalse(result['table_identities_verified'])

    def test_unreserved_missing_parent_and_duplicate_scoped_writes_are_rejected(self):
        rows=self.writes(2,-123)
        for batch in ((rows[1],),self.writes(4,7),rows[:2]+(rows[1],rows[2])):
            with self.assertRaises(ImageError):IncrementalDownload.prepare(batch,self.image,self.source)

    def test_equal_table_ids_do_not_hide_cross_program_effect_corruption(self):
        changed=dict(self.image._symbols);changed[2,1]=(3,1);self.image._symbols=MappingProxyType(changed)
        results=[self.image.read_preparation_effect(i,self.source) for i in range(self.image.records)]
        self.assertTrue(any(not row.matches for row in results))
        with self.assertRaises(ImageError):self.namespace.validate_base(self.source,self.native,**self.catalogs)


if __name__=='__main__':unittest.main()
