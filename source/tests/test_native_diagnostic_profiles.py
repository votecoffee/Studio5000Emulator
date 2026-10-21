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

from logixlab import importers,native_diagnostic_profiles as profiles
from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from tools import vmware_appliance as vm
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path
from test_native_auxiliary_symbols import record
from test_native_routines import database,container


def collection(**kwargs):
    return record(name='ProfileCollection',instance=kwargs.pop('instance',0),
        logical=kwargs.pop('logical',(0x3b1,0,0,0,0,0)),component_type=kwargs.pop('component_type',0),
        version=kwargs.pop('version',0),body_bytes=kwargs.pop('body_bytes',74),**kwargs)


class ProfileSourceTests(unittest.TestCase):
    def test_explicit_empty_collection_excludes_deleted_definitions_and_allocation_tail(self):
        raw=database(collection(),collection(instance=1,logical=(0x3b1,1,0,0,0,0),kind=0xfdfd),tail=collection())
        self.assertEqual(profiles.empty_profile_records(raw),[])

    def test_absent_nonempty_scoped_duplicate_and_unknown_source_profiles_withhold_evidence(self):
        for raw in (database(),database(collection(),collection()),database(collection(version=1)),
                database(collection(body_bytes=73)),database(collection(component_type=256)),
                database(collection(header_version=1)),database(collection(),collection(logical=(0x3b1,1,0,0,0,0))),
                database(collection(),collection(logical=(0x68,1,0x3b1,0,0,0))),
                database(collection(),collection(logical=(0x68,1,0x6d,1,0x3b1,0))),
                database(collection(logical=(0x3b1,0,1,0,0,0)))):
            with self.subTest(size=len(raw)),self.assertRaises(ModelError):profiles.empty_profile_records(raw)

    def test_truncated_database_record_and_resource_limits_are_rejected(self):
        raw=database(collection())
        for bad in (raw[:-1],b'',bytearray(raw)):
            with self.assertRaises(ModelError):profiles.empty_profile_records(bad)
        for offset,value in ((0,0),(8,0xffffffff),(12,0),(514,0xffffffff)):
            bad=bytearray(raw);struct.pack_into('<I',bad,offset,value)
            with self.assertRaises(ModelError):profiles.empty_profile_records(bytes(bad))
        for field,value in (('MAX_RECORDS',0),('MAX_BYTES',20)):
            with patch.object(profiles,field,value),self.assertRaises(ModelError):profiles.empty_profile_records(raw)

    def test_raw_compressed_source_and_strict_immutable_manifest_preserve_original(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.ACD'
            for compressed in (False,True):
                raw=container(database(collection()),compressed);source.write_bytes(raw)
                binding=profiles.NativeDiagnosticProfiles.from_acd(source,'b'*64)
                self.assertEqual(binding.source_acd_sha256,hashlib.sha256(raw).hexdigest())
                self.assertEqual(source.read_bytes(),raw);self.assertEqual(binding.manifest()['profiles'],[])
                self.assertEqual(profiles.NativeDiagnosticProfiles.from_manifest(binding.manifest(),'b'*64),binding)
                with self.assertRaises(FrozenInstanceError):binding.source_acd_sha256='c'*64
                with patch.object(profiles,'MAX_STREAM_BYTES',1),self.assertRaises(ModelError):profiles.NativeDiagnosticProfiles.from_acd(source,'b'*64)
        manifest=profiles.NativeDiagnosticProfiles('a'*64,'b'*64).manifest()
        for change in ({'extra':[]},{'source_acd_sha256':'bad'},{'source_l5x_sha256':'c'*64},
                       {'profiles':None},{'profiles':()},{'profiles':[1]}):
            with self.assertRaises(ModelError):profiles.NativeDiagnosticProfiles.from_manifest({**manifest,**change},'b'*64)
        with self.assertRaises(ModelError):profiles.NativeDiagnosticProfiles.from_manifest({k:v for k,v in manifest.items() if k!='profiles'},'b'*64)

    def test_converter_forwards_independent_profile_evidence_and_keeps_l5x_on_unsupported_source(self):
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
            receipt=run([collection()],'good');self.assertEqual(receipt['native_diagnostic_profiles']['profiles'],[])
            # Profile evidence does not depend on decoding message definitions.
            self.assertIn('native_diagnostics_error',receipt)
            def import_copy(acd,output,converter):output.write_bytes(content);return receipt
            with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})),patch.object(importers,'convert_acd',side_effect=import_copy),patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                vm.import_project(work,source,str(executable));self.assertEqual(api.call_args.args[2]['native_diagnostic_profiles'],receipt['native_diagnostic_profiles'])
            for body,name in (([],'absent'),([collection(),collection(logical=(0x3b1,1,0,0,0,0))],'nonempty')):
                missing=run(body,name);self.assertNotIn('native_diagnostic_profiles',missing)
                self.assertIn('native_diagnostic_profiles_error',missing);self.assertTrue((work/name/'source.L5X').is_file())


class ProfileWireTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name);self.app.command('demo',{'sample':'ConveyorDemo'})
        content=self.app.engine.project.path.read_bytes();sha=hashlib.sha256(content).hexdigest()
        self.identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1)
        self.binding=profiles.NativeDiagnosticProfiles('a'*64,sha)
        self.data=dict(name='source.L5X',content=base64.b64encode(content).decode(),native_project_identity=self.identity.manifest(),native_diagnostic_profiles=self.binding.manifest())
        self.app.command('load',self.data);self.endpoint=Endpoint(self.app,0,True,'logix-v35-l85e');self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def call(self,service,path,data=b''):return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session())

    def test_reference_empty_list_all_cursors_and_proven_class_counts(self):
        for cursor in (0,1,65535,0xffffffff):
            self.assertEqual(self.call(0x4b,logical_path(0x3b1,cursor)),bytes.fromhex('cb000000'))
        for attr in (2,3):self.assertEqual(self.call(14,logical_path(0x3b1,0)+bytes((0x30,attr))),b'\x8e\0\0\0'+bytes(4))
        self.assertEqual(self.call(14,logical_path(0x3b1,0)+b'\x30\1')[2],0x14)
        self.assertEqual(self.call(14,logical_path(0x3b1,1)+b'\x30\1')[2],5)

    def test_scopes_attributes_bad_payloads_and_mutations_do_not_change_execution(self):
        before=copy.deepcopy(self.app.state());path=logical_path(0x3b1,0)
        for target,data,service,status in ((path,b'\0',0x4b,0x15),(path+b'\x30\1',b'',0x4b,4),
                (path[:-2],b'',0x4b,4),(symbol_path('Program:MainProgram')+path,b'',0x4b,4),
                (logical_path(0x68,1)+path,b'',0x4b,4),(path,b'',0x10,8),(path,b'',8,8),(path,b'',0x4d,8)):
            self.assertEqual(self.call(service,target,data)[2],status)
        for key in ('tags','scan','ms','controller','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_missing_stale_foreign_identity_and_atomic_load_replacement(self):
        engine=self.app.engine
        for identity in (None,replace(self.identity,source_acd_sha256='c'*64),replace(self.identity,source_l5x_sha256='c'*64)):
            self.app.native_project_identity=identity;self.assertEqual(self.call(0x4b,logical_path(0x3b1,0))[2],0x0c)
        self.app.native_project_identity=self.identity
        self.app.native_diagnostic_profiles=replace(self.binding,source_l5x_sha256='c'*64)
        self.assertEqual(self.call(0x4b,logical_path(0x3b1,0))[2],0x0c);self.app.native_diagnostic_profiles=self.binding
        for changes in ({'source_acd_sha256':'c'*64},{'source_l5x_sha256':'c'*64},{'profiles':[1]}):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_diagnostic_profiles':{**self.binding.manifest(),**changes}})
            self.assertIs(self.app.engine,engine)
        with self.assertRaises(ModelError):self.app.command('load',{k:v for k,v in self.data.items() if k!='native_project_identity'})
        self.app.command('reset',{});self.assertEqual(self.call(0x4b,logical_path(0x3b1,0))[2],0)
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_diagnostic_profiles'})
        self.assertIsNone(self.app.native_diagnostic_profiles);self.assertEqual(self.call(0x4b,logical_path(0x3b1,0))[2],0x0c)

    def test_signed_tcp_list_succeeds_and_writes_stay_denied(self):
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()
        before=copy.deepcopy(self.app.state());path=logical_path(0x3b1,0)
        with AnonymousClient(self.endpoint) as client:
            client.bind();self.assertEqual(client.request(bytes((0x4b,len(path)//2))+path),bytes.fromhex('cb000000'))
            self.assertNotEqual(client.request(bytes((0x10,len(path)//2))+path+b'\0')[2],0)
        desc=self.app.state()['connectivity']['native_diagnostic_profiles']
        self.assertTrue(desc['explicit_empty_collection']);self.assertEqual(desc['profiles'],0)
        self.assertFalse(desc['configuration_writes']);self.assertNotIn('definitions',desc)
        for key in ('tags','scan','ms','controller','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])


if __name__=='__main__':unittest.main()
