"""Original Data Table IDs are independent from public/model storage addresses."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from logixlab import native_tables as nt,importers
from logixlab.model import ModelError
from tools import vmware_appliance as vm
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path
import test_native_auxiliary_symbols as auxiliary
from test_native_routines import database,container


def record(name='$0123abcd$',instance=1,**kwargs):
    return auxiliary.record(name=name,logical=kwargs.pop('logical',(0x6A,instance,0,0,0,0)),
        version=kwargs.pop('version',38),body_bytes=kwargs.pop('body_bytes',420),**kwargs)


def collection(parent=0):
    return record(name='DataTables',instance=0,component_type=0,version=0,body_bytes=74,
        logical=(0x68,parent,0x6A,0,0,0) if parent else (0x6A,0,0,0,0,0))


def row(instance=1,name='$0123abcd$',body_bytes=420,**kwargs):return dict(instance=instance,name=name,body_bytes=body_bytes,**kwargs)


class NativeTableIdentityTests(unittest.TestCase):
    def test_active_format38_paths_require_explicit_collection_and_retain_opaque_sizes(self):
        data=database(collection(),collection(2),record(),record('$Other$',2,body_bytes=539),
            record('$Free$',3,kind=0xFDFD),tail=record('$Tail$',4))
        self.assertEqual(nt.table_paths(data),[row(),row(2,'$Other$',539)])
        self.assertEqual(nt.table_paths(database(collection())),[])
        self.assertEqual(nt.table_paths(database(collection(),record(body_bytes=417))),[row(body_bytes=417)])

    def test_scoped_tables_keep_repeated_ids_and_names_in_separate_programs(self):
        scoped=lambda parent:record(logical=(0x68,parent,0x6A,1,0,0))
        rows=nt.table_paths(database(collection(),collection(2),collection(3),record(),scoped(2),scoped(3)))
        self.assertEqual(rows,[row(),row(program_instance=2),row(program_instance=3)])
        binding=nt.NativeTables('a'*64,'b'*64,rows)
        self.assertEqual(set(binding.by_instance),{1,(2,1),(3,1)})
        self.assertEqual(nt.NativeTables.from_manifest(binding.manifest(),'b'*64),binding)
        self.assertEqual(binding.description()['scoped_tables'],2)
        for data in (database(collection(),scoped(2)),database(collection(),collection(2),scoped(2),scoped(2)),
                     database(collection(),collection(2),record(logical=(0x68,2,0x6A,1,1,0)))):
            with self.assertRaises(ModelError):nt.table_paths(data)

    def test_scoped_bindings_require_source_matched_programs(self):
        symbols,_=auxiliary.bindings();binding=nt.NativeTables('a'*64,'b'*64,[row(program_instance=2)])
        binding.require_parents(symbols)
        for parent in (0xFFFF,True,-1):
            with self.assertRaises(ModelError):nt.NativeTables('a'*64,'b'*64,[row(program_instance=parent)])
        for candidate in (None,auxiliary.NativeSymbols('c'*64,'b'*64,[],programs=[dict(name='ProgramA',instance=2)]),
                          auxiliary.NativeSymbols('a'*64,'b'*64,[],programs=[dict(name='Other',instance=3)])):
            with self.assertRaises(ModelError):binding.require_parents(candidate)

    def test_ambiguous_history_unknown_formats_scopes_and_truncated_records_withhold_binding(self):
        cases=(database(),database(record()),database(collection(),collection()),database(collection(),record(),record()),
            database(collection(),record(),record(instance=2)),database(collection(),record(version=39)),
            database(collection(),record(component_type=264)),database(collection(),record(header_version=1)),
            database(collection(),record(instance=65535)),database(collection(),record(body_bytes=416)),
            database(collection(),record(logical=(0x6A,1,1,0,0,0))),
            database(collection(),record(logical=(0x68,2,0x6A,1,0,0))),database(collection(),collection(2),collection(2)),
            database(record(instance=0,component_type=0,version=0,body_bytes=73)))
        for data in cases:
            with self.subTest(size=len(data)),self.assertRaises(ModelError):nt.table_paths(data)
        with self.assertRaises(ModelError):nt.table_paths(database(collection(),record())[:-1])

    def test_raw_compressed_source_hashes_bounds_and_immutable_manifests(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.ACD'
            for compressed in (False,True):
                raw=container(database(collection(),record()),compressed);path.write_bytes(raw)
                result=nt.NativeTables.from_acd(path,'b'*64)
                self.assertEqual(result.source_acd_sha256,hashlib.sha256(raw).hexdigest());self.assertEqual(path.read_bytes(),raw)
                self.assertEqual(nt.NativeTables.from_manifest(result.manifest(),'b'*64),result)
                with self.assertRaises(FrozenInstanceError):result.rows=()
                with self.assertRaises(TypeError):result.by_instance[1]=None
                with patch.object(nt,'MAX_STREAM_BYTES',10),self.assertRaises(ModelError):nt.NativeTables.from_acd(path,'b'*64)
                with patch.object(nt,'MAX_BYTES',100),self.assertRaises(ModelError):nt.NativeTables.from_acd(path,'b'*64)
        for field,value in (('MAX_RECORDS',1),('MAX_TABLES',0),('MAX_BODY_BYTES',419)):
            with patch.object(nt,field,value),self.assertRaises(ModelError):nt.table_paths(database(collection(),record()))

    def test_manifest_fields_names_ids_and_source_versions_are_strict(self):
        for tables in ([row(),row()],[row(),row(instance=2)],[row(instance=True)],[row(instance=0)],
                [row(name='')],[row(name='x'*62)],[row(name='nonascii-\u00e9')],[row(body_bytes=True)],
                [row(body_bytes=nt.MAX_BODY_BYTES+1)],[{**row(),'value':123}]):
            with self.assertRaises(ModelError):nt.NativeTables('a'*64,'b'*64,tables)
        manifest=nt.NativeTables('a'*64,'b'*64,[row()]).manifest()
        with self.assertRaises(ModelError):nt.NativeTables.from_manifest(manifest,'c'*64)

    def test_converter_and_appliance_forward_the_optional_table_binding_without_sdk_calls(self):
        raw=container(database(collection(),record()));source=Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);acd=directory/'source.ACD';acd.write_bytes(raw)
            converter=directory/'converter.exe';converter.write_bytes(b'test double')
            def run(command,**kwargs):
                Path(command[command.index('--l5x')+1]).write_bytes(source.read_bytes())
                return SimpleNamespace(returncode=0,stdout='ok',stderr='')
            with patch.object(importers.subprocess,'run',side_effect=run):
                receipt=importers.convert_acd(acd,directory/'output/source.L5X',converter)
            self.assertNotIn('native_tables_error',receipt)
            binding=nt.NativeTables.from_manifest(receipt['native_tables'],hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(binding.manifest()['tables'],[row()])
            def convert(acd,output,converter):output.write_bytes(source.read_bytes());return receipt
            with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})), \
                    patch.object(importers,'convert_acd',side_effect=convert), \
                    patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                vm.import_project(directory,acd,str(converter))
                self.assertEqual(api.call_args.args[2]['native_tables'],binding.manifest())
            self.assertEqual(acd.read_bytes(),raw)


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional independent client key generator')
class NativeTableImportTcpTests(unittest.TestCase):
    def setUp(self):
        auxiliary.AuxiliaryImportTcpTests.setUp(self)
        self.tables=nt.NativeTables('a'*64,self.primary.source_l5x_sha256,[row()])
        self.data={**self.data,'native_tables':self.tables.manifest()};self.app.command('load',self.data)

    def tearDown(self):auxiliary.AuxiliaryImportTcpTests.tearDown(self)

    def test_original_id_binding_does_not_expose_additional_public_tables_or_values(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        with AnonymousClient(self.app.endpoint) as client:
            client.bind();path=logical_path(0x6A,0)
            self.assertEqual(client.request(bytes((0x4B,len(path)//2))+path),bytes.fromhex('cb00000064000000'))
            path=logical_path(0x6A,1)+b'\x30\x02'
            self.assertEqual(client.request(bytes((0x0E,len(path)//2))+path)[2],5)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        description=self.app.state()['connectivity']['native_tables'];self.assertEqual(description['tables'],1)
        self.assertFalse(description['public_catalog_extended']);self.assertFalse(description['values_exposed'])
        self.assertNotIn('$0123abcd$',str(self.app.state()['provenance']))

    def test_atomic_source_validation_and_reload_clear_table_binding(self):
        engine=self.app.engine
        for manifest in (nt.NativeTables('c'*64,self.primary.source_l5x_sha256,[row()]).manifest(),
                         nt.NativeTables('a'*64,'c'*64,[row()]).manifest()):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_tables':manifest})
            self.assertIs(self.app.engine,engine)
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_tables'})
        self.assertIsNone(self.app.native_tables)
        self.app.command('load',self.data);self.app.command('demo',{'sample':'ConveyorDemo'});self.assertIsNone(self.app.native_tables)


if __name__=='__main__':unittest.main()
