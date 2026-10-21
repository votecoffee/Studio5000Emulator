"""Explicit empty source evidence, unavailable cases, atomic loads and signed TCP."""
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

from logixlab import importers,native_diagnostic_objects as objects
from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from tools import vmware_appliance as vm
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import CollectionError,decode_attribute_list,instance_supported
from tools.analyze_native_transfer import analyze
from tools.upload_inventory import logical_path
from test_native_auxiliary_symbols import record
from test_native_routines import database,container
from test_native_transfer_trace import event


def collection(**kwargs):
    return record(name='ObjectCollection',instance=kwargs.pop('instance',0),
        logical=kwargs.pop('logical',(0x3b0,0,0,0,0,0)),component_type=kwargs.pop('component_type',0),
        version=kwargs.pop('version',0),body_bytes=kwargs.pop('body_bytes',74),**kwargs)


class ObjectSourceTests(unittest.TestCase):
    def test_populated_stored_object_layout_and_other_diagnostic_collections_are_not_empty_evidence(self):
        nonempty=record(name='Object_A',instance=1,logical=(0x3b0,1,0,0,0,0),version=0,body_bytes=361,component_type=256)
        for raw in (database(collection(),nonempty),database(collection(logical=(0x3b1,0,0,0,0,0))),
                    database(collection(logical=(0x3b2,0,0,0,0,0)))):
            with self.assertRaises(ModelError):objects.empty_object_records(raw)

    def test_explicit_empty_collection_excludes_deleted_definitions_and_allocation_tail(self):
        raw=database(collection(),collection(instance=1,logical=(0x3b0,1,0,0,0,0),kind=0xfdfd),tail=collection())
        self.assertEqual(objects.empty_object_records(raw),[])

    def test_absent_nonempty_scoped_duplicate_and_unknown_source_objects_withhold_evidence(self):
        for raw in (database(),database(collection(),collection()),database(collection(version=1)),
                database(collection(body_bytes=73)),database(collection(component_type=256)),
                database(collection(header_version=1)),database(collection(),collection(logical=(0x3b0,1,0,0,0,0))),
                database(collection(),collection(logical=(0x68,1,0x3b0,0,0,0))),
                database(collection(),collection(logical=(0x68,1,0x6d,1,0x3b0,0))),
                database(collection(logical=(0x3b0,0,1,0,0,0)))):
            with self.subTest(size=len(raw)),self.assertRaises(ModelError):objects.empty_object_records(raw)

    def test_truncated_database_record_and_resource_limits_are_rejected(self):
        raw=database(collection())
        for bad in (raw[:-1],b'',bytearray(raw)):
            with self.assertRaises(ModelError):objects.empty_object_records(bad)
        for offset,value in ((0,0),(8,0xffffffff),(12,0),(514,0xffffffff)):
            bad=bytearray(raw);struct.pack_into('<I',bad,offset,value)
            with self.assertRaises(ModelError):objects.empty_object_records(bytes(bad))
        for field,value in (('MAX_RECORDS',0),('MAX_BYTES',20)):
            with patch.object(objects,field,value),self.assertRaises(ModelError):objects.empty_object_records(raw)

    def test_raw_compressed_source_and_strict_immutable_manifest_preserve_original(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.ACD'
            for compressed in (False,True):
                raw=container(database(collection()),compressed);source.write_bytes(raw)
                binding=objects.NativeDiagnosticObjects.from_acd(source,'b'*64)
                self.assertEqual(binding.source_acd_sha256,hashlib.sha256(raw).hexdigest())
                self.assertEqual(source.read_bytes(),raw);self.assertEqual(binding.manifest()['objects'],[])
                self.assertEqual(objects.NativeDiagnosticObjects.from_manifest(binding.manifest(),'b'*64),binding)
                with self.assertRaises(FrozenInstanceError):binding.source_acd_sha256='c'*64
                with patch.object(objects,'MAX_STREAM_BYTES',1),self.assertRaises(ModelError):objects.NativeDiagnosticObjects.from_acd(source,'b'*64)
        manifest=objects.NativeDiagnosticObjects('a'*64,'b'*64).manifest()
        for change in ({'extra':[]},{'source_acd_sha256':'bad'},{'source_l5x_sha256':'c'*64},
                       {'objects':None},{'objects':()},{'objects':[1]}):
            with self.assertRaises(ModelError):objects.NativeDiagnosticObjects.from_manifest({**manifest,**change},'b'*64)
        with self.assertRaises(ModelError):objects.NativeDiagnosticObjects.from_manifest({k:v for k,v in manifest.items() if k!='objects'},'b'*64)

    def test_converter_forwards_independent_object_evidence_and_keeps_l5x_on_unsupported_source(self):
        content=(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').read_bytes();sha=hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);source=work/'source.ACD';executable=work/'converter.exe';executable.write_bytes(b'test double')
            def convert(command,**kwargs):
                Path(command[command.index('--l5x')+1]).write_bytes(content)
                return SimpleNamespace(returncode=0,stdout='ok',stderr='')
            def run(body,name):
                raw=container(database(*body));source.write_bytes(raw)
                identity=NativeProjectIdentity(hashlib.sha256(raw).hexdigest(),sha,1,1,1,1,1,1)
                with patch.object(importers.subprocess,'run',side_effect=convert),patch.object(importers.NativeProjectIdentity,'from_acd',return_value=identity):
                    result=importers.convert_acd(source,work/name/'source.L5X',executable)
                self.assertEqual(source.read_bytes(),raw)
                return result
            receipt=run([collection()],'good');self.assertEqual(receipt['native_diagnostic_objects']['objects'],[])
            # Object evidence does not depend on decoding message definitions.
            self.assertIn('native_diagnostics_error',receipt)
            def import_copy(acd,output,converter):output.write_bytes(content);return receipt
            with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})),patch.object(importers,'convert_acd',side_effect=import_copy),patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                vm.import_project(work,source,str(executable));self.assertEqual(api.call_args.args[2]['native_diagnostic_objects'],receipt['native_diagnostic_objects'])
            for body,name in (([],'absent'),([collection(),collection(logical=(0x3b0,1,0,0,0,0))],'nonempty')):
                missing=run(body,name);self.assertNotIn('native_diagnostic_objects',missing)
                self.assertIn('native_diagnostic_objects_error',missing);self.assertTrue((work/name/'source.L5X').is_file())


class ObjectWireTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name);self.app.command('demo',{'sample':'ConveyorDemo'})
        content=self.app.engine.project.path.read_bytes();sha=hashlib.sha256(content).hexdigest()
        self.identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1)
        self.binding=objects.NativeDiagnosticObjects('a'*64,sha)
        self.data=dict(name='source.L5X',content=base64.b64encode(content).decode(),native_project_identity=self.identity.manifest(),native_diagnostic_objects=self.binding.manifest())
        self.app.command('load',self.data);self.endpoint=Endpoint(self.app,0,True,'logix-v35-l85e');self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def call(self,service,path,data=b''):return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session())

    def test_reference_empty_list_all_cursors_and_proven_class_counts(self):
        for cursor in (0,1,65535,0xffffffff):
            self.assertEqual(self.call(0x4b,logical_path(0x3b0,cursor)),bytes.fromhex('cb000000'))
        for attr in (2,3):self.assertEqual(self.call(14,logical_path(0x3b0,0)+bytes((0x30,attr))),b'\x8e\0\0\0'+bytes(4))
        self.assertEqual(self.call(14,logical_path(0x3b0,0)+b'\x30\1')[2],0x14)
        self.assertEqual(self.call(14,logical_path(0x3b0,1)+b'\x30\1')[2],5)

    def test_scopes_attributes_bad_payloads_and_mutations_do_not_change_execution(self):
        before=copy.deepcopy(self.app.state());path=logical_path(0x3b0,0)
        for target,data,service,status in ((path,b'\0',0x4b,0x15),(path+b'\x30\1',b'',0x4b,4),
                (path[:-2],b'',0x4b,4),(symbol_path('Program:MainProgram')+path,b'',0x4b,4),
                (logical_path(0x68,1)+path,b'',0x4b,4),(path,b'',0x10,8),(path,b'',8,8),(path,b'',0x4d,8)):
            self.assertEqual(self.call(service,target,data)[2],status)
        for key in ('tags','scan','ms','controller','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_missing_stale_foreign_identity_and_atomic_load_replacement(self):
        engine=self.app.engine
        for identity in (None,replace(self.identity,source_acd_sha256='c'*64),replace(self.identity,source_l5x_sha256='c'*64)):
            self.app.native_project_identity=identity;self.assertEqual(self.call(0x4b,logical_path(0x3b0,0))[2],0x0c)
        self.app.native_project_identity=self.identity
        self.app.native_diagnostic_objects=replace(self.binding,source_l5x_sha256='c'*64)
        self.assertEqual(self.call(0x4b,logical_path(0x3b0,0))[2],0x0c);self.app.native_diagnostic_objects=self.binding
        for changes in ({'source_acd_sha256':'c'*64},{'source_l5x_sha256':'c'*64},{'objects':[1]}):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_diagnostic_objects':{**self.binding.manifest(),**changes}})
            self.assertIs(self.app.engine,engine)
        with self.assertRaises(ModelError):self.app.command('load',{k:v for k,v in self.data.items() if k!='native_project_identity'})
        self.app.command('reset',{});self.assertEqual(self.call(0x4b,logical_path(0x3b0,0))[2],0)
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_diagnostic_objects'})
        self.assertIsNone(self.app.native_diagnostic_objects);self.assertEqual(self.call(0x4b,logical_path(0x3b0,0))[2],0x0c)

    def test_signed_tcp_list_succeeds_and_writes_stay_denied(self):
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()
        before=copy.deepcopy(self.app.state());path=logical_path(0x3b0,0)
        with AnonymousClient(self.endpoint) as client:
            client.bind();self.assertEqual(client.request(bytes((0x4b,len(path)//2))+path),bytes.fromhex('cb000000'))
            self.assertNotEqual(client.request(bytes((0x10,len(path)//2))+path+b'\0')[2],0)
        desc=self.app.state()['connectivity']['native_diagnostic_objects']
        self.assertTrue(desc['explicit_empty_collection']);self.assertEqual(desc['objects'],0)
        self.assertFalse(desc['configuration_writes']);self.assertNotIn('definitions',desc)
        for key in ('tags','scan','ms','controller','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_profile_binding_alone_does_not_grant_object_discovery(self):
        from logixlab.native_diagnostic_profiles import NativeDiagnosticProfiles
        data={k:v for k,v in self.data.items() if k!='native_diagnostic_objects'}
        data['native_diagnostic_profiles']=NativeDiagnosticProfiles(self.identity.source_acd_sha256,self.identity.source_l5x_sha256).manifest()
        self.app.command('load',data)
        self.assertEqual(self.call(0x4b,logical_path(0x3b1,0))[2],0)
        self.assertEqual(self.call(0x4b,logical_path(0x3b0,0))[2],0x0c)
        with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_diagnostic_profiles':{**data['native_diagnostic_profiles'],'source_acd_sha256':'c'*64}})


class ObjectDecoderTests(unittest.TestCase):
    def test_profile_enable_and_counted_conditions_keep_values_private_and_ordered(self):
        order=(3,1,2,3);values={1:struct.pack('<I',12345),2:b'\1',3:struct.pack('<4H',3,7,8,50000)}
        raw=b'\x83\0\0\0'+struct.pack('<H',len(order))+b''.join(struct.pack('<HH',n,0)+values[n] for n in order)
        report=decode_attribute_list(raw,order,0x3b0)
        self.assertEqual([r['value_bytes'] for r in report['attributes']],[8,4,1,8])
        self.assertEqual([r['value_sha256'] for r in report['attributes']],[hashlib.sha256(values[n]).hexdigest() for n in order])
        self.assertNotIn('data_hex',str(report));self.assertEqual(report['value_semantics'],'NOT INFERRED')
        exposed=decode_attribute_list(raw,order,0x3b0,include_payloads=True)
        self.assertEqual(exposed['attributes'][0]['data_hex'],values[3].hex())
        for instance in (1,44,65535,0xffffffff):self.assertTrue(instance_supported(0x3b0,instance))
        for instance in (0,True,-1,1<<32):self.assertFalse(instance_supported(0x3b0,instance))
        for end in range(len(raw)):
            with self.assertRaises(CollectionError):decode_attribute_list(raw[:end],order,0x3b0)
        with self.assertRaises(CollectionError):decode_attribute_list(raw+b'\0',order,0x3b0)
        for value in (struct.pack('<H',4097)+bytes(8194),b'\1\0',b'\0\0\0'):
            bad=b'\x83\0\0\0'+struct.pack('<3H',1,3,0)+value
            with self.assertRaises(CollectionError):decode_attribute_list(bad,(3,),0x3b0)

    def test_transfer_analyzer_retains_nonzero_object_instance_fields_and_failed_attributes(self):
        query=logical_path(0x3b0,44);order=(1,2,3)
        raw=b'\x83\0\0\0'+struct.pack('<H',3)+struct.pack('<HHI',1,0,0)+struct.pack('<HHB',2,0,1)+struct.pack('<HHH',3,0,0)
        report=analyze({'events':[]},{'events':[event(bytes((3,len(query)//2))+query+struct.pack('<4H',3,*order),raw)]},'upload')
        self.assertTrue(report['analysis_complete']);self.assertEqual(report['collection_lists_observed'],1)
        self.assertEqual(report['collection_attribute_lists'][0]['instance'],44)
        self.assertEqual(report['collection_attribute_lists'][0]['collection_attribute_list']['attributes'][2]['value_bytes'],2)
        partial=b'\x83\0\6\0'+struct.pack('<HHHIHH',2,1,0,0,9,0x14)
        decoded=decode_attribute_list(partial,(1,9,3),0x3b0)
        self.assertEqual(decoded['remaining_attributes'],[3]);self.assertIsNone(decoded['attributes'][1]['value_sha256'])


if __name__=='__main__':unittest.main()

