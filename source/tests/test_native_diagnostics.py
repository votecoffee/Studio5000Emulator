"""Synthetic source definitions, strict framing, immutable bindings and owned TCP."""
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

from logixlab import importers,native_diagnostics as nd
from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from tools import vmware_appliance as vm
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import CollectionError,decode_attribute_list,instance_supported
from tools.upload_inventory import logical_path
from test_native_auxiliary_symbols import record as component
from test_native_routines import database,container
from test_native_transfer_trace import event
from tools.analyze_native_transfer import analyze


def row(instance=1,message_id='Diag_A',message_code='TEST-1',revision=7):
    return dict(instance=instance,message_id=message_id,message_code=message_code,revision=revision)


def record(instance=1,message_id='Diag_A',message_code='TEST-1',revision=7,**kwargs):
    raw=bytearray(component(name=message_id,instance=instance,logical=kwargs.pop('logical',(0x3b2,instance,0,0,0,0)),
        version=kwargs.pop('version',0),body_bytes=kwargs.pop('body_bytes',270),**kwargs))
    start=6+148
    if len(raw)-start>=270:
        struct.pack_into('<4I',raw,start+74,0xc4,2,1,172)
        for offset,part in ((90,message_id),(131,message_code)):
            encoded=part.encode('ascii');raw[start+offset]=len(encoded);raw[start+offset+1:start+offset+1+len(encoded)]=encoded
        struct.pack_into('<H',raw,start+260,revision)
    return bytes(raw)


def collection(**kwargs):return record(instance=0,message_id='DiagnosticDefinitions',body_bytes=74,component_type=0,**kwargs)


class DiagnosticSourceTests(unittest.TestCase):
    def test_fixed_source_fields_keep_original_ids_and_skip_deleted_records_and_tail(self):
        raw=database(collection(),record(),record(instance=50000,message_id='Diag_B',revision=65535),
                     record(instance=2,kind=0xfdfd),tail=record(instance=3))
        self.assertEqual(nd.message_records(raw),[row(),row(50000,'Diag_B',revision=65535)])
        self.assertEqual(nd.message_records(database(collection())),[])
        self.assertEqual(nd.message_records(database(collection(),record(message_id='A'*40,message_code='B'*128,revision=0))),[row(message_id='A'*40,message_code='B'*128,revision=0)])
        self.assertEqual(nd.message_records(database(collection(),record(message_code=''))),[row(message_code='')])

    def test_bad_profiles_missing_collection_ambiguous_ids_and_scope_fail_closed(self):
        cases=(database(),database(record()),database(collection(),collection()),database(collection(),record(),record()),
            database(collection(),record(),record(instance=2)),database(collection(),record(version=1)),
            database(collection(),record(component_type=264)),database(collection(),record(header_version=1)),
            database(collection(),record(instance=65535)),database(collection(),record(body_bytes=269)),
            database(collection(),record(logical=(0x3b2,1,1,0,0,0))),database(collection(),record(logical=(0x68,2,0x3b2,1,0,0))),
            database(record(instance=0,component_type=0,body_bytes=73)))
        for data in cases:
            with self.subTest(size=len(data)),self.assertRaises(ModelError):nd.message_records(data)
        for field,value in (('MAX_RECORDS',1),('MAX_MESSAGES',0),('MAX_BYTES',20)):
            with patch.object(nd,field,value),self.assertRaises(ModelError):nd.message_records(database(collection(),record()))
        with self.assertRaises(ModelError):nd.message_records(database(collection(),record())[:-1])

    def test_string_bounds_padding_ascii_header_name_and_data_extent_are_checked(self):
        variants=[];start=6+148
        for offset,value in ((90,41),(131,129),(91,255),(91+6,1),(132+6,1),(74,0),(86,0)):
            raw=bytearray(record());raw[start+offset]=value;variants.append(bytes(raw))
        raw=bytearray(record());raw[6+24]=ord('X');variants.append(bytes(raw))
        for value in variants:
            with self.assertRaises(ModelError):nd.message_records(database(collection(),value))

    def test_revision_comes_from_definition_data_and_not_component_storage_headers(self):
        raw=bytearray(record(revision=321));struct.pack_into('<I',raw,6+148+82,99)
        self.assertEqual(nd.message_records(database(collection(),raw))[0]['revision'],321)

    def test_raw_and_compressed_source_manifests_preserve_input_and_are_immutable(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.ACD'
            for compressed in (False,True):
                raw=container(database(collection(),record()),compressed);source.write_bytes(raw)
                binding=nd.NativeDiagnostics.from_acd(source,'b'*64)
                self.assertEqual(binding.source_acd_sha256,hashlib.sha256(raw).hexdigest())
                self.assertEqual(binding.manifest()['messages'],[row()]);self.assertEqual(source.read_bytes(),raw)
                self.assertEqual(nd.NativeDiagnostics.from_manifest(binding.manifest(),'b'*64),binding)
                with self.assertRaises(FrozenInstanceError):binding.rows=()
                with self.assertRaises(TypeError):binding.by_instance[1]=None
                with patch.object(nd,'MAX_STREAM_BYTES',1),self.assertRaises(ModelError):nd.NativeDiagnostics.from_acd(source,'b'*64)

    def test_manifest_hashes_fields_names_and_numeric_types_are_strict(self):
        for messages in ([row(),row()],[row(),row(2)],[row(instance=True)],[row(instance=0)],[row(instance=65535)],
                         [row(message_id='')],[row(message_id='a'*41)],[row(message_code='a'*129)],
                         [row(message_code='bad\0code')],[row(message_id='nonascii-\u00e9')],[row(revision=True)],
                         [row(revision=-1)],[row(revision=65536)],[{**row(),'value':123}]):
            with self.assertRaises(ModelError):nd.NativeDiagnostics('a'*64,'b'*64,messages)
        manifest=nd.NativeDiagnostics('a'*64,'b'*64,[row()]).manifest()
        for change in ({'extra':[]},{'source_acd_sha256':'bad'},{'source_l5x_sha256':'c'*64},{'messages':None}):
            with self.assertRaises(ModelError):nd.NativeDiagnostics.from_manifest({**manifest,**change},'b'*64)

    def test_converter_and_appliance_forward_only_source_bound_definitions(self):
        sample=Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X';content=sample.read_bytes();sha=hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);source=work/'source.ACD';raw=container(database(collection(),record()));source.write_bytes(raw)
            executable=work/'converter.exe';executable.write_bytes(b'test double')
            identity=NativeProjectIdentity(hashlib.sha256(raw).hexdigest(),sha,1,1,1,1,1,1)
            def convert(command,**kwargs):
                Path(command[command.index('--l5x')+1]).write_bytes(content)
                return SimpleNamespace(returncode=0,stdout='ok',stderr='')
            with patch.object(importers.subprocess,'run',side_effect=convert),patch.object(importers.NativeProjectIdentity,'from_acd',return_value=identity):
                receipt=importers.convert_acd(source,work/'output/source.L5X',executable)
            self.assertEqual(receipt['native_diagnostics']['messages'],[row()])
            def import_copy(acd,output,converter):output.write_bytes(content);return receipt
            with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})),patch.object(importers,'convert_acd',side_effect=import_copy),patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                vm.import_project(work,source,str(executable));self.assertEqual(api.call_args.args[2]['native_diagnostics'],receipt['native_diagnostics'])
            with patch.object(importers.subprocess,'run',side_effect=convert):
                missing=importers.convert_acd(source,work/'missing/source.L5X',executable)
            self.assertNotIn('native_diagnostics',missing);self.assertIn('native_diagnostics_error',missing)
            self.assertEqual(source.read_bytes(),raw)


class DiagnosticWireTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name);self.app.command('demo',{'sample':'ConveyorDemo'})
        content=self.app.engine.project.path.read_bytes();sha=hashlib.sha256(content).hexdigest()
        self.identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1)
        self.binding=nd.NativeDiagnostics('a'*64,sha,[row(),row(50000,'Diag_B','TEST-2',8)])
        self.data=dict(name='source.L5X',content=base64.b64encode(content).decode(),native_project_identity=self.identity.manifest(),native_diagnostics=self.binding.manifest())
        self.app.command('load',self.data);self.endpoint=Endpoint(self.app,0,True,'logix-v35-l85e');self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def call(self,service,path,data=b'',limit=480):return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session(),limit=limit)

    def test_lists_paginate_original_sparse_ids_and_report_class_counts(self):
        path=logical_path(0x3b2,0)
        self.assertEqual(self.call(0x4b,path),b'\xcb\0\0\0'+struct.pack('<2I',1,50000))
        self.assertEqual(self.call(0x4b,path,limit=8),b'\xcb\0\6\0'+struct.pack('<I',1))
        self.assertEqual(self.call(0x4b,logical_path(0x3b2,2)),b'\xcb\0\0\0'+struct.pack('<I',50000))
        self.assertEqual(self.call(0x4b,logical_path(0x3b2,50001)),b'\xcb\0\0\0')
        for attr,value in ((1,b'\1\0'),(2,struct.pack('<I',50000)),(3,struct.pack('<I',2))):
            self.assertEqual(self.call(14,path+b'\x30'+bytes((attr,))),b'\x8e\0\0\0'+value)
        self.assertEqual(self.call(0x4b,path,limit=7)[2],0x1b)

    def test_counted_strings_revision_list_order_duplicates_and_unknown_attributes(self):
        path=logical_path(0x3b2,1);attrs=self.binding.rows[0].attributes()
        for attr,value in attrs.items():self.assertEqual(self.call(14,path+b'\x30'+bytes((attr,))),b'\x8e\0\0\0'+value)
        order=(2,3,1,2);expected=struct.pack('<H',4)+b''.join(struct.pack('<HH',n,0)+attrs[n] for n in order)
        self.assertEqual(self.call(3,path,struct.pack('<5H',4,*order)),b'\x83\0\0\0'+expected)
        response=self.call(3,path,struct.pack('<3H',2,9,3))
        self.assertEqual(response,b'\x83\0\x0a\0'+struct.pack('<5H',2,9,0x14,3,0)+attrs[3])

    def test_bad_paths_mutations_and_payloads_preserve_values_and_execution(self):
        before=copy.deepcopy(self.app.state());path=logical_path(0x3b2,1)
        for target,data,service,status in ((path,b'\0',14,0x15),(path,b'',0x10,8),(path,b'',0x4d,8),
                (path,b'\1',0x4b,0x15),(path+b'\x30\1',b'',0x4b,4),(path[:-2],b'',0x4b,4),
                (symbol_path('Program:MainProgram')+path,b'',0x4b,4),(logical_path(0x3b2,2),b'',14,5),
                (logical_path(0x68,1)+path,b'',0x4b,4)):
            self.assertEqual(self.call(service,target,data)[2],status)
        for key in ('tags','scan','ms','controller','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])
        self.assertIsNone(self.app.state()['connectivity']['native_diagnostics'])
        description=self.app.native_diagnostics.description()
        self.assertEqual(description['messages'],2);self.assertFalse(description['live_faults']);self.assertFalse(description['event_generation'])

    def test_stale_bindings_missing_identity_failed_load_and_replacement_do_not_leak_definitions(self):
        engine=self.app.engine
        for value in (None,replace(self.identity,source_acd_sha256='c'*64),replace(self.identity,source_l5x_sha256='c'*64)):
            self.app.native_project_identity=value;self.assertEqual(self.call(0x4b,logical_path(0x3b2,0))[2],0x0c)
        self.app.native_project_identity=self.identity
        for change in ({'source_acd_sha256':'c'*64},{'source_l5x_sha256':'c'*64}):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_diagnostics':{**self.binding.manifest(),**change}})
            self.assertIs(self.app.engine,engine)
        with self.assertRaises(ModelError):self.app.command('load',{k:v for k,v in self.data.items() if k!='native_project_identity'})
        self.app.command('reset',{});self.assertEqual(self.call(0x4b,logical_path(0x3b2,0))[2],0)
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_diagnostics'})
        self.assertIsNone(self.app.native_diagnostics);self.assertEqual(self.call(0x4b,logical_path(0x3b2,0))[2],0x0c)

    def test_real_signed_tcp_reads_metadata_without_granting_configuration_writes(self):
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()
        before=copy.deepcopy(self.app.state());path=logical_path(0x3b2,1)
        with AnonymousClient(self.endpoint) as client:
            client.bind();reply=client.request(bytes((3,len(path)//2))+path+struct.pack('<4H',3,1,2,3))
            self.assertEqual(reply[2],0);self.assertEqual(decode_attribute_list(reply,(1,2,3),0x3b2)['status'],0)
            self.assertNotEqual(client.request(bytes((0x10,len(path)//2))+path+b'\0')[2],0)
        self.assertEqual(self.app.state()['connectivity']['native_diagnostics']['messages'],2)
        for key in ('tags','scan','ms','controller','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])


class DiagnosticCollectionTests(unittest.TestCase):
    def test_shared_decoder_and_trace_retain_nonzero_instance_fields_without_values(self):
        attrs=nd.DiagnosticMessage(**row()).attributes();order=(1,2,3)
        raw=b'\x83\0\0\0'+struct.pack('<H',3)+b''.join(struct.pack('<HH',n,0)+attrs[n] for n in order)
        report=decode_attribute_list(raw,order,0x3b2);self.assertEqual([r['value_bytes'] for r in report['attributes']],[7,7,2])
        self.assertNotIn('Diag_A',str(report));self.assertNotIn('data_hex',str(report))
        self.assertTrue(instance_supported(0x3b2,50000));self.assertFalse(instance_supported(0x3b2,0))
        query=logical_path(0x3b2,50000);trace=analyze({'events':[]},{'events':[event(bytes((3,len(query)//2))+query+struct.pack('<4H',3,*order),raw)]},'upload')
        self.assertTrue(trace['analysis_complete']);self.assertEqual(trace['collection_lists_observed'],1)
        self.assertEqual(trace['collection_attribute_lists'][0]['instance'],50000)
        for bad in (raw[:-1],raw+b'\0',raw[:10]+b'\xff'+raw[11:]):
            with self.assertRaises(CollectionError):decode_attribute_list(bad,order,0x3b2)


if __name__=='__main__':unittest.main()
