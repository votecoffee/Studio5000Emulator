"""Auxiliary source identities never become public/runtime tags or aliases."""
import base64
import copy
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from logixlab import native_auxiliary_symbols as aux
from logixlab import importers
from logixlab.model import ModelError
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from logixlab.ethernetip import Endpoint
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path
from tools import vmware_appliance as vm
from test_native_routines import database,container
from test_source_object_verification import bindings


def record(name='PublicTag',parent=0,instance=1,component_type=256,version=63,body_bytes=700,
           logical=None,header_version=0,kind=0xFAFA):
    body=bytearray(body_bytes);path=logical or ((0x68,parent,0x6B,instance,0,0) if parent else (0x6B,instance,0,0,0,0))
    struct.pack_into('<H6H',body,8,version,*path)
    header=bytearray(148);struct.pack_into('<I',header,0,148+len(body));struct.pack_into('<H',header,10,component_type)
    struct.pack_into('<I',header,12,header_version);encoded=name.encode('utf-16le')+bytes(2);header[24:24+len(encoded)]=encoded
    raw=header+body;return struct.pack('<HI',kind,6+len(raw))+raw


def known():return (record(),record('ScopedTag',parent=2))


def row(name='__Aux',parent=0,instance=9,component_type=256):
    return dict(program_instance=parent,instance=instance,name=name,component_type=component_type)


class AuxiliarySymbolTests(unittest.TestCase):
    def test_converter_and_appliance_preserve_the_optional_binding_without_native_calls(self):
        raw=container(database(*known(),record('__Aux',instance=9)))
        source=Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);acd=directory/'source.ACD';acd.write_bytes(raw)
            converter=directory/'converter.exe';converter.write_bytes(b'test double')
            def run(command,**kwargs):
                Path(command[command.index('--l5x')+1]).write_bytes(source.read_bytes())
                return SimpleNamespace(returncode=0,stdout='ok',stderr='')
            def primary(path,sha):return bindings(acd=hashlib.sha256(raw).hexdigest(),l5x=sha)[0]
            with patch.object(importers.subprocess,'run',side_effect=run),patch.object(importers.NativeSymbols,'from_acd',side_effect=primary):
                receipt=importers.convert_acd(acd,directory/'output/source.L5X',converter)
            self.assertNotIn('native_auxiliary_symbols_error',receipt)
            binding=aux.NativeAuxiliarySymbols.from_manifest(receipt['native_auxiliary_symbols'],hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(binding.manifest()['symbols'],[row()])
            def convert(acd,output,converter):output.write_bytes(source.read_bytes());return receipt
            with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})), \
                    patch.object(importers,'convert_acd',side_effect=convert), \
                    patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                vm.import_project(directory,acd,str(converter))
                self.assertEqual(api.call_args.args[2]['native_auxiliary_symbols'],binding.manifest())
            self.assertEqual(acd.read_bytes(),raw)

    def test_exact_known_coverage_and_three_component_types_preserve_parent_scope(self):
        primary,_=bindings()
        data=database(*known(),record('__Map:Local',instance=2,component_type=1288),
            record('__CONTAINER',instance=3,component_type=264),record('$0123abcd$',parent=2,instance=2),
            record(instance=0,component_type=0,version=0,body_bytes=74),
            record(parent=2,instance=0,component_type=0,version=0,body_bytes=74),
            record('__Free',instance=22,kind=0xFDFD),tail=record('__Tail',instance=23))
        rows=aux.symbol_paths(data,primary)
        self.assertEqual({(r['program_instance'],r['instance']) for r in rows},{(0,2),(0,3),(2,2)})
        self.assertEqual({r['component_type'] for r in rows},{256,264,1288})
        self.assertEqual(aux.symbol_paths(database(*known()),primary),[])

    def test_missing_history_name_conflicts_unknown_parent_and_format_fail_closed(self):
        primary,_=bindings()
        bad=(database(record()),database(*known(),record()),database(*known(),record('__Aux',instance=9),record('__Aux',instance=10)),
            database(record('Other'),known()[1]),database(*known(),record('__Aux',parent=3,instance=9)),
            database(*known(),record('__Aux',instance=9,version=62)),database(*known(),record('__Aux',instance=9,body_bytes=699)),
            database(*known(),record('__Aux',instance=9,component_type=260)),database(*known(),record(header_version=1)),
            database(*known(),record(logical=(0x6B,9,1,0,0,0))),database(*known(),record('__Aux',instance=65535)))
        for data in bad:
            with self.subTest(size=len(data)),self.assertRaises(ModelError):aux.symbol_paths(data,primary)

    def test_size_record_and_compression_limits_and_original_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.ACD'
            for compressed in (False,True):
                raw=container(database(*known(),record('__Aux',instance=9)),compressed);path.write_bytes(raw)
                primary,_=bindings(acd=hashlib.sha256(raw).hexdigest())
                result=aux.NativeAuxiliarySymbols.from_acd(path,'b'*64,primary)
                self.assertEqual(result.manifest()['symbols'],[row()]);self.assertEqual(path.read_bytes(),raw)
                with self.assertRaises(ModelError):aux.NativeAuxiliarySymbols.from_acd(path,'c'*64,primary)
                with patch.object(aux,'MAX_STREAM_BYTES',10),self.assertRaises(ModelError):aux.NativeAuxiliarySymbols.from_acd(path,'b'*64,primary)
                with patch.object(aux,'MAX_BYTES',100),self.assertRaises(ModelError):aux.NativeAuxiliarySymbols.from_acd(path,'b'*64,primary)
        primary,_=bindings();data=database(*known(),record('__Aux',instance=9))
        for value in (data[:-1],data[:20],b'bad'):
            with self.assertRaises(ModelError):aux.symbol_paths(value,primary)
        with patch.object(aux,'MAX_RECORDS',1),self.assertRaises(ModelError):aux.symbol_paths(data,primary)
        with patch.object(aux,'MAX_AUXILIARY',0),self.assertRaises(ModelError):aux.symbol_paths(data,primary)

    def test_immutable_manifests_and_parent_name_id_conflicts_are_validated(self):
        primary,_=bindings();result=aux.NativeAuxiliarySymbols('a'*64,'b'*64,[row()]);result.require_parents(primary)
        self.assertEqual(aux.NativeAuxiliarySymbols.from_manifest(result.manifest(),'b'*64),result)
        with self.assertRaises(FrozenInstanceError):result.rows=()
        with self.assertRaises(TypeError):result.by_instance[(0,1)]=result.rows[0]
        for values in ([row(),row()],[row(),row(instance=10)],[row(instance=True)],[row(name='has space')],
                       [row(name='nonascii-\u00e9')],[row(name='x'*62)],[row(component_type=True)],[{**row(),'extra':0}]):
            with self.assertRaises(ModelError):aux.NativeAuxiliarySymbols('a'*64,'b'*64,values)
        for value in (row(parent=3),row(instance=1),row(name='PublicTag')):
            with self.assertRaises(ModelError):aux.NativeAuxiliarySymbols('a'*64,'b'*64,[value]).require_parents(primary)
        with self.assertRaises(ModelError):aux.NativeAuxiliarySymbols.from_manifest(result.manifest(),'c'*64)


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional independent client key generator')
class AuxiliaryImportTcpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name);self.app.command('demo',{'sample':'ConveyorDemo'})
        project=self.app.engine.project;sha=project.sha256
        self.tag=next(t for t in project.tags.values() if not t.scope and not t.alias and t.dtype=='BOOL')
        self.primary=NativeSymbols('a'*64,sha,[Symbol('',0,self.tag.name,100)],programs=[dict(name='MainProgram',instance=2)])
        self.binding=aux.NativeAuxiliarySymbols('a'*64,sha,[row(name='__CONTAINER',instance=1,component_type=264),row(parent=2,instance=1)])
        self.data=dict(name='source.L5X',content=base64.b64encode(project.path.read_bytes()).decode(),
            native_project_identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1).manifest(),
            native_symbols=self.primary.manifest(),native_auxiliary_symbols=self.binding.manifest())
        self.app.command('load',self.data)
        self.app.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start()

    def tearDown(self):self.app.close();self.temp.cleanup()

    def test_auxiliary_ids_and_names_never_enter_public_symbol_discovery_or_tag_values(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        with AnonymousClient(self.app.endpoint) as client:
            client.bind();path=logical_path(0x6B,0)
            self.assertEqual(client.request(bytes((0x4B,len(path)//2))+path),b'\xcb\0\0\0'+struct.pack('<I',100))
            path=logical_path(0x6B,1)+b'\x30\x01'
            self.assertEqual(client.request(bytes((0x0E,len(path)//2))+path)[2],5)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        description=self.app.state()['connectivity']['native_auxiliary_symbols']
        self.assertEqual(description['symbols'],2);self.assertFalse(description['runtime_tags_exposed'])
        self.assertNotIn('__CONTAINER',str(self.app.state()['provenance']))

    def test_load_rejects_foreign_and_colliding_manifests_atomically_and_reload_drops_binding(self):
        engine=self.app.engine
        for binding in (aux.NativeAuxiliarySymbols('c'*64,self.primary.source_l5x_sha256,[row()]),
                        aux.NativeAuxiliarySymbols('a'*64,self.primary.source_l5x_sha256,[row(instance=100)]),
                        aux.NativeAuxiliarySymbols('a'*64,self.primary.source_l5x_sha256,[row(parent=3)])):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_auxiliary_symbols':binding.manifest()})
            self.assertIs(self.app.engine,engine)
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_auxiliary_symbols'})
        self.assertIsNone(self.app.native_auxiliary_symbols)
        self.app.command('load',self.data);self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertIsNone(self.app.native_auxiliary_symbols)


if __name__=='__main__':unittest.main()
