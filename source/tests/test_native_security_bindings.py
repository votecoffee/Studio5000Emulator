"""Authority discovery requires explicit empty ACD evidence, never legacy Code."""
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

from logixlab import importers,native_security_bindings as bindings
from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_diagnostic_objects import NativeDiagnosticObjects
from logixlab.server import Application
from tools import vmware_appliance as vm
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path
from test_native_auxiliary_symbols import record
from test_native_routines import database,container


def collection(**kwargs):
    data=bytearray(record(name='AuthorityCollection',instance=kwargs.pop('instance',0),
        logical=kwargs.pop('logical',(0x36A,0,0,0,0,0)),component_type=kwargs.pop('component_type',0),
        version=kwargs.pop('version',0),body_bytes=kwargs.pop('body_bytes',74),**kwargs))
    if len(data)>=6+148+74:
        struct.pack_into('<13I',data,6+148+22,0,0,0,0,0,0xFFFFFFFF,0,0xFFFFFFFF,0,874,0,0,0xFFFFFFFF)
    return bytes(data)


class SecurityBindingSourceTests(unittest.TestCase):
    def test_unknown_collection_tail_cannot_become_an_empty_binding_list(self):
        original=collection()
        for offset in range(22,74,4):
            altered=bytearray(original);altered[6+148+offset]^=1
            with self.subTest(offset=offset),self.assertRaises(ModelError):bindings.empty_binding_records(database(bytes(altered)))

    def test_only_one_explicit_empty_collection_with_no_active_definitions_is_evidence(self):
        deleted=collection(logical=(0x36A,1,0,0,0,0),instance=1,kind=0xFDFD)
        self.assertEqual(bindings.empty_binding_records(database(collection(),deleted,tail=collection())),[])
        for raw in (database(),database(collection(),collection()),database(collection(version=1)),
                database(collection(component_type=256)),database(collection(body_bytes=75)),database(collection(header_version=1)),
                database(collection(),collection(logical=(0x36A,1,0,0,0,0),instance=1)),
                database(collection(),collection(logical=(0x68,1,0x36A,0,0,0))),
                database(collection(),collection(logical=(0x68,1,0x6D,1,0x36A,0))),
                database(collection(logical=(0x3B0,0,0,0,0,0))),database(collection(logical=(0x36A,0,1,0,0,0)))):
            with self.subTest(size=len(raw)),self.assertRaises(ModelError):bindings.empty_binding_records(raw)

    def test_database_bounds_and_bounded_raw_compressed_containers_preserve_source(self):
        raw=database(collection())
        for bad in (raw[:-1],b'',bytearray(raw)):
            with self.assertRaises(ModelError):bindings.empty_binding_records(bad)
        for offset,value in ((0,0),(8,0xffffffff),(12,0),(514,0xffffffff)):
            bad=bytearray(raw);struct.pack_into('<I',bad,offset,value)
            with self.assertRaises(ModelError):bindings.empty_binding_records(bytes(bad))
        for key,value in (('MAX_RECORDS',0),('MAX_BYTES',20)):
            with patch.object(bindings,key,value),self.assertRaises(ModelError):bindings.empty_binding_records(raw)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.ACD'
            for compressed in (False,True):
                original=container(raw,compressed);source.write_bytes(original)
                binding=bindings.NativeSecurityBindings.from_acd(source,'b'*64)
                self.assertEqual(binding.source_acd_sha256,hashlib.sha256(original).hexdigest())
                self.assertEqual(source.read_bytes(),original)
                with patch.object(bindings,'MAX_STREAM_BYTES',1),self.assertRaises(ModelError):bindings.NativeSecurityBindings.from_acd(source,'b'*64)

    def test_manifest_is_strict_immutable_empty_and_source_bound(self):
        binding=bindings.NativeSecurityBindings('a'*64,'b'*64);manifest=binding.manifest()
        self.assertEqual(bindings.NativeSecurityBindings.from_manifest(manifest,'b'*64),binding)
        with self.assertRaises(FrozenInstanceError):binding.source_acd_sha256='c'*64
        for change in ({'extra':[]},{'source_acd_sha256':'bad'},{'source_l5x_sha256':'c'*64},
                       {'bindings':None},{'bindings':()},{'bindings':[{'uri':'unsupported'}]}):
            with self.assertRaises(ModelError):bindings.NativeSecurityBindings.from_manifest({**manifest,**change},'b'*64)
        with self.assertRaises(ModelError):bindings.NativeSecurityBindings.from_manifest({k:v for k,v in manifest.items() if k!='bindings'},'b'*64)

    def test_converter_and_appliance_forward_evidence_but_keep_export_when_collection_is_unsupported(self):
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
                    receipt=importers.convert_acd(source,work/name/'source.L5X',executable)
                self.assertEqual(source.read_bytes(),raw);return receipt
            receipt=run([collection()],'good');self.assertEqual(receipt['native_security_bindings']['bindings'],[])
            def import_copy(acd,output,converter):output.write_bytes(content);return receipt
            with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})),patch.object(importers,'convert_acd',side_effect=import_copy),patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                vm.import_project(work,source,str(executable));self.assertEqual(api.call_args.args[2]['native_security_bindings'],receipt['native_security_bindings'])
            for body,name in (([],'absent'),([collection(),collection(logical=(0x36A,1,0,0,0,0),instance=1)],'nonempty')):
                missing=run(body,name);self.assertNotIn('native_security_bindings',missing)
                self.assertIn('native_security_bindings_error',missing);self.assertTrue((work/name/'source.L5X').is_file())


class SecurityBindingWireTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name);self.app.command('demo',{'sample':'ConveyorDemo'})
        root=E.parse(self.app.engine.project.path).getroot();E.SubElement(root.find('Controller'),'Security',Code='0')
        content=E.tostring(root);sha=hashlib.sha256(content).hexdigest()
        self.identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1);self.binding=bindings.NativeSecurityBindings('a'*64,sha)
        self.data=dict(name='source.L5X',content=base64.b64encode(content).decode(),native_project_identity=self.identity.manifest(),native_security_bindings=self.binding.manifest())
        self.app.command('load',self.data);self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e');self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def call(self,service,path,data=b''):
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session())

    def test_empty_list_cursors_and_known_class_revision_do_not_claim_instance_values(self):
        before=copy.deepcopy(self.app.state())
        for cursor in (0,1,65536,0xffffffff):self.assertEqual(self.call(0x4B,logical_path(0x36A,cursor)),bytes.fromhex('cb000000'))
        path=logical_path(0x36A,0)
        self.assertEqual(self.call(3,path,struct.pack('<2H',1,1)),bytes.fromhex('830000000100010000000100'))
        self.assertEqual(self.call(14,path+bytes.fromhex('3001')),bytes.fromhex('8e0000000100'))
        self.assertEqual(self.call(14,path+bytes.fromhex('3002'))[2],20)
        self.assertEqual(self.call(14,logical_path(0x36A,1)+bytes.fromhex('3001'))[2],5)
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_scope_payload_attributes_and_writes_are_rejected(self):
        for path in (logical_path(0x36A,0,program=1),symbol_path('Something')+logical_path(0x36A,0),
                     logical_path(0x338,1)+logical_path(0x36A,0),logical_path(0x8E,1)+logical_path(0x36A,0)):
            self.assertEqual(self.call(0x4B,path)[2],4)
        for service,path,data in ((0x4B,logical_path(0x36A,0),b'x'),(0x4B,logical_path(0x36A,0)+bytes.fromhex('3001'),b''),
                (0x10,logical_path(0x36A,0)+bytes.fromhex('3001'),b'\0\0'),(4,logical_path(0x36A,0),bytes(2))):
            self.assertNotEqual(self.call(service,path,data)[2],0)

    def test_missing_mismatched_and_foreign_bindings_never_replace_engine_or_grant_empty_discovery(self):
        engine=self.app.engine
        for change in ({'source_acd_sha256':'c'*64},{'source_l5x_sha256':'c'*64},{'bindings':[1]}):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_security_bindings':{**self.binding.manifest(),**change}})
            self.assertIs(self.app.engine,engine)
        with self.assertRaises(ModelError):self.app.command('load',{k:v for k,v in self.data.items() if k!='native_project_identity'})
        foreign=NativeDiagnosticObjects('c'*64,self.identity.source_l5x_sha256).manifest()
        with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_diagnostic_objects':foreign})
        self.app.native_security_bindings=replace(self.binding,source_l5x_sha256='c'*64)
        self.assertEqual(self.call(0x4B,logical_path(0x36A,0))[2],12);self.app.native_security_bindings=self.binding
        self.app.command('reset',{});self.assertEqual(self.call(0x4B,logical_path(0x36A,0))[2],0)
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_security_bindings'})
        self.assertIsNone(self.app.native_security_bindings)
        self.assertEqual(self.call(0x4B,logical_path(0x36A,0))[2],12)
        self.assertEqual(self.app.engine.project.controller_configuration.security_code,0)

    def test_signed_tcp_discovery_is_read_only_and_retains_independent_security_policy(self):
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()
        before=copy.deepcopy(self.app.state());path=logical_path(0x36A,0)
        with AnonymousClient(self.endpoint) as client:
            client.bind();self.assertEqual(client.request(bytes((0x4B,len(path)//2))+path),bytes.fromhex('cb000000'))
            self.assertEqual(client.request(bytes((0x10,len(path)//2))+path+bytes(2))[2],15)
        info=self.app.state()['connectivity']['native_security_bindings'];self.assertEqual(info['bindings'],0)
        self.assertTrue(info['explicit_empty_collection'])
        for name in ('authentication','authorization','configuration_writes','legacy_security_code_used','captured_bindings_replayed'):self.assertFalse(info[name])
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])


if __name__=='__main__':unittest.main()
