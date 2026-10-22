"""Original names/IDs, malformed inputs, atomic binding and signed read-only CIP."""
import base64
import copy
from dataclasses import FrozenInstanceError,replace
import hashlib
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab import importers,native_metadata_definitions as metadata
from logixlab.ethernetip import Endpoint,Session
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from tools import vmware_appliance as vm
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path
from test_native_auxiliary_symbols import record
from test_native_routines import database,container


def collection(**kwargs):
    return record(name='MetadataCollection',instance=0,logical=kwargs.pop('logical',(0x349,0,0,0,0,0)),
        version=kwargs.pop('version',0),component_type=kwargs.pop('component_type',0),body_bytes=kwargs.pop('body_bytes',74),**kwargs)


def definition(name='PropertyA',instance=7,**kwargs):
    raw=bytearray(record(name=name,instance=instance,logical=kwargs.pop('logical',(0x349,instance,0,0,0,0)),
        version=kwargs.pop('version',0),body_bytes=216,**kwargs))
    struct.pack_into('<IIIH',raw,6+148+78,1,1,130,len(name))
    raw[6+148+92:6+148+92+len(name)]=name.encode('ascii')
    return bytes(raw)


class MetadataSourceTests(unittest.TestCase):
    def test_names_and_ids_are_sorted_without_copying_unrelated_objects_or_deleted_records(self):
        raw=database(collection(),definition('PropertyB',42),definition(),definition('Deleted',9,kind=0xfdfd),
            record(name='Unrelated'),tail=definition('AllocationTail',99))
        self.assertEqual(metadata.definition_records(raw),(metadata.Definition(7,'PropertyA'),metadata.Definition(42,'PropertyB')))
        self.assertEqual(metadata.definition_records(database(collection())),())

    def test_missing_duplicate_scoped_and_unsupported_collections_withhold_inventory(self):
        for raw in (database(),database(definition()),database(collection(),collection()),
                database(collection(version=1)),database(collection(component_type=256)),database(collection(body_bytes=75)),
                database(collection(),definition(logical=(0x68,1,0x349,7,0,0))),database(collection(),definition(version=1)),
                database(collection(header_version=1))):
            with self.subTest(raw=hashlib.sha256(raw).hexdigest()),self.assertRaises(ModelError):metadata.definition_records(raw)

    def test_duplicates_bad_lengths_names_and_field_profiles_are_rejected(self):
        bad=[]
        for offset,value in ((78,2),(82,2),(86,128)):
            raw=bytearray(definition());struct.pack_into('<I',raw,6+148+offset,value);bad.append(bytes(raw))
        for offset,value in ((90,0),(90,125)):
            raw=bytearray(definition());struct.pack_into('<H',raw,6+148+offset,value);bad.append(bytes(raw))
        for offset,value in ((92,0xff),(92,ord('X')),(215,1)):
            raw=bytearray(definition());raw[6+148+offset]=value;bad.append(bytes(raw))
        for raw in bad:
            with self.assertRaises(ModelError):metadata.definition_records(database(collection(),raw))
        for rows in ((definition(),definition()),(definition(),definition('PropertyA',8)),(definition(),definition('propertya',8))):
            with self.assertRaises(ModelError):metadata.definition_records(database(collection(),*rows))
        for data in (b'',database(collection())[:-1],bytes(512)):
            with self.assertRaises(ModelError):metadata.definition_records(data)

    def test_container_and_manifest_bind_the_same_immutable_names_and_hashes(self):
        raw=container(database(collection(),definition()))
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'own.ACD';source.write_bytes(raw)
            catalog=metadata.NativeMetadataDefinitions.from_acd(source,'b'*64)
            self.assertEqual(catalog.source_acd_sha256,hashlib.sha256(raw).hexdigest())
            self.assertEqual(metadata.NativeMetadataDefinitions.from_manifest(catalog.manifest(),'b'*64),catalog)
            self.assertEqual(source.read_bytes(),raw)
        with self.assertRaises(FrozenInstanceError):catalog.rows[0].name='Changed'
        self.assertEqual(catalog.rows[0].attributes(),{1:b'\x09\0PropertyA'})
        for change in ({'source_acd_sha256':'bad'},{'source_l5x_sha256':'c'*64},{'extra':0},
                       {'definitions':None},{'definitions':[{'instance':True,'name':'Field'}]},
                       {'definitions':[{'instance':1,'name':'has space'}]},
                       {'definitions':[{'instance':1,'name':'Field'},{'instance':2,'name':'field'}]}):
            with self.assertRaises(ModelError):metadata.NativeMetadataDefinitions.from_manifest({**catalog.manifest(),**change},'b'*64)

    def test_converter_keeps_export_and_reports_unsupported_metadata_separately(self):
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').getroot()
        E.SubElement(root.find('Controller'),'Security',Code='0')
        content=E.tostring(root);sha=hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);source=work/'own.ACD';converter=work/'converter.exe';converter.write_bytes(b'test double')
            def convert(command,**kwargs):
                Path(command[command.index('--l5x')+1]).write_bytes(content)
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            for label,raw,accepted in (('supported',container(database(collection(),definition())),True),('unsupported',container(database()),False)):
                source.write_bytes(raw);identity=NativeProjectIdentity(hashlib.sha256(raw).hexdigest(),sha,1,1,1,1,1,1)
                with patch.object(importers.subprocess,'run',side_effect=convert),patch.object(importers.NativeProjectIdentity,'from_acd',return_value=identity):
                    receipt=importers.convert_acd(source,work/label/'project.L5X',converter)
                self.assertEqual('native_metadata_definitions' in receipt,accepted)
                self.assertEqual('native_metadata_definitions_error' in receipt,not accepted)
                self.assertEqual((work/label/'project.L5X').read_bytes(),content);self.assertEqual(source.read_bytes(),raw)
                if accepted:
                    def import_copy(acd,output,converter):output.write_bytes(content);return receipt
                    with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})),patch.object(importers,'convert_acd',side_effect=import_copy),patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                        vm.import_project(work,source,str(converter))
                    self.assertEqual(api.call_args.args[2]['native_metadata_definitions'],receipt['native_metadata_definitions'])


class MetadataEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        content=(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').read_bytes();sha=hashlib.sha256(content).hexdigest()
        self.identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1)
        self.catalog=metadata.NativeMetadataDefinitions('a'*64,sha,(metadata.Definition(7,'PropertyA'),metadata.Definition(42,'PropertyB')))
        self.data=dict(name='source.L5X',content=base64.b64encode(content).decode(),native_project_identity=self.identity.manifest(),native_metadata_definitions=self.catalog.manifest())
        self.app.command('load',self.data);self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e');self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def call(self,service,instance,data=b'',attribute=None,limit=65535):
        path=logical_path(0x349,instance)+(bytes((0x30,attribute)) if attribute is not None else b'')
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session(),limit=limit)

    def test_discovery_paging_names_and_class_counts_use_only_the_bound_catalog(self):
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.call(0x4b,0),b'\xcb\0\0\0'+struct.pack('<II',7,42))
        self.assertEqual(self.call(0x4b,8),b'\xcb\0\0\0'+struct.pack('<I',42))
        self.assertEqual(self.call(0x4b,43),b'\xcb\0\0\0')
        self.assertEqual(self.call(0x4b,0,limit=8),b'\xcb\0\6\0'+struct.pack('<I',7))
        self.assertEqual(self.call(0x0e,7,attribute=1),b'\x8e\0\0\0\x09\0PropertyA')
        self.assertEqual(self.call(0x0e,0,attribute=2),b'\x8e\0\0\0'+struct.pack('<I',42))
        self.assertEqual(self.call(0x0e,0,attribute=3),b'\x8e\0\0\0'+struct.pack('<I',2))
        self.assertEqual(self.call(0x0e,8,attribute=1)[2],5)
        self.assertEqual(self.call(0x0e,7,attribute=2)[2],0x14)
        after=self.app.state()
        for key in ('tags','controller','scan','ms','routines','tasks','routine_edits'):self.assertEqual(after[key],before[key])

    def test_foreign_or_stale_load_is_atomic_and_unbound_reload_clears_original_names(self):
        engine=self.app.engine
        for change in ({'source_acd_sha256':'c'*64},{'source_l5x_sha256':'c'*64}):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_metadata_definitions':{**self.catalog.manifest(),**change}})
            self.assertIs(self.app.engine,engine)
        with self.assertRaises(ModelError):self.app.command('load',{k:v for k,v in self.data.items() if k!='native_project_identity'})
        self.app.native_metadata_definitions=replace(self.catalog,source_l5x_sha256='c'*64)
        self.assertEqual(self.call(0x4b,0)[2],12);self.app.native_metadata_definitions=self.catalog
        self.app.command('reset',{});self.assertEqual(self.call(0x4b,0)[2],0)
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_metadata_definitions'})
        self.assertIsNone(self.app.native_metadata_definitions);self.assertEqual(self.call(0x0e,7,attribute=1)[2],5)

    def test_signed_tcp_exposes_names_but_keeps_writes_and_program_value_queries_denied(self):
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()
        before=copy.deepcopy(self.app.state()['tags'])
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            path=logical_path(0x349,7)
            self.assertEqual(client.request(b'\x0e'+bytes((len(path)//2+1,))+path+b'\x30\x01'),b'\x8e\0\0\0\x09\0PropertyA')
            self.assertNotEqual(client.request(b'\x04'+bytes((len(path)//2,))+path+bytes.fromhex('01000100010041'))[2],0)
            program=logical_path(0x68,1)
            self.assertEqual(client.request(b'\x50'+bytes((len(program)//2,))+program+bytes.fromhex('01011f0000000000'))[2],15)
        state=self.endpoint.state()['metadata_definition'];self.assertEqual(state['instance_count'],2)
        self.assertTrue(state['native_source_bound']);self.assertFalse(state['metadata_values'])
        self.assertEqual(self.app.state()['tags'],before)


if __name__=='__main__':unittest.main()
