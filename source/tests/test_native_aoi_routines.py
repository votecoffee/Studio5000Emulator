"""AOI-scoped Executable identities, independent TCP reads and denied edits."""
import base64
import copy
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab.aoi_catalog import AOICatalog
from logixlab.ethernetip import decode_path,CIPError,Router
from logixlab.model import ModelError
from logixlab.native_aois import NativeAOIs
from logixlab.native_aoi_routines import NativeAOIRoutines
from logixlab.native_project import NativeProjectIdentity
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path,collect_inventory,values,Limits,InventoryError
from tools import vmware_appliance as vm
from logixlab import importers
import test_native_aois as aoi_tests
from test_native_routines import database,record as component,container


def record(**kwargs):
    return component(component_type=kwargs.pop('component_type',259),**kwargs)


class AOIRoutineIdentityTests(unittest.TestCase):
    def test_conversion_and_appliance_forward_the_original_binding_without_sdk_calls(self):
        source=Path(__file__).resolve().parents[1]/'samples/AOILab.L5X';root=E.parse(source).getroot()
        records=[]
        for i,parent in enumerate(root.findall('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')):
            records.append(aoi_tests.record(name=parent.get('Name'),instance=700+i))
            for j,routine in enumerate(parent.findall('./Routines/Routine')):
                records.append(record(name=routine.get('Name'),logical=(0x338,700+i,0x6D,7+j,0,0)))
        raw=container(database(*records))
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);acd=directory/'source.ACD';acd.write_bytes(raw)
            converter=directory/'converter.exe';converter.write_bytes(b'test double')
            def run(command,**kwargs):
                Path(command[command.index('--l5x')+1]).write_bytes(source.read_bytes())
                return SimpleNamespace(stdout='ok',stderr='',returncode=0)
            with patch.object(importers.subprocess,'run',side_effect=run):
                receipt=importers.convert_acd(acd,directory/'converted/project.L5X',converter)
            self.assertEqual(len(receipt['native_aoi_routines']['routines']),6)
            binding=NativeAOIRoutines.from_manifest(receipt['native_aoi_routines'],hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(binding.source_acd_sha256,hashlib.sha256(raw).hexdigest())
            self.assertNotIn('native_aoi_routines_error',receipt)
            def convert(acd,output,converter):output.write_bytes(source.read_bytes());return receipt
            with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})), \
                    patch.object(importers,'convert_acd',side_effect=convert), \
                    patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                vm.import_project(directory,acd,str(converter))
                self.assertEqual(api.call_args.args[2]['native_aoi_routines'],binding.manifest())
                self.assertEqual(api.call_args.args[2]['native_aois'],receipt['native_aois'])
            self.assertEqual(acd.read_bytes(),raw)

    def test_format54_keeps_aoi_namespace_even_when_program_and_child_ids_overlap(self):
        data=database(record(logical=(0x338,11,0x6D,7,0,0)),record(logical=(0x338,22,0x6D,7,0,0)),
                      record(component_type=256),record(logical=(0x338,11,0x6B,7,0,0),version=19))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.ACD'
            for compressed in (False,True):
                raw=container(data,compressed);path.write_bytes(raw)
                parents=NativeAOIs(hashlib.sha256(raw).hexdigest(),'b'*64,
                                  [{'name':'A','instance':11},{'name':'B','instance':22}])
                binding=NativeAOIRoutines.from_acd(path,'b'*64,[{'aoi':n,'name':'Run'} for n in ('A','B')],parents)
                self.assertEqual([(r.aoi_instance,r.instance) for r in binding.rows],[(11,7),(22,7)])
                self.assertEqual(binding.source_acd_sha256,parents.source_acd_sha256)
                self.assertEqual(NativeAOIRoutines.from_manifest(binding.manifest(),'b'*64),binding)
                self.assertEqual(path.read_bytes(),raw)
                with self.assertRaises(FrozenInstanceError):binding.rows=()

    def test_missing_historical_unknown_and_conflicting_records_fail_closed(self):
        for records in ((),(record(),),(record(logical=(0x338,11,0x6D,7,0,0),version=53),),
                        (record(logical=(0x338,11,0x6D,7,0,0),component_type=256),),
                        (record(logical=(0x338,11,0x6D,7,0,0)),)*2,
                        (record(logical=(0x338,11,0x6D,7,0,0),kind=0xFDFD),)):
            with self.subTest(records=len(records)),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'sample.ACD';raw=container(database(*records));path.write_bytes(raw)
                parents=NativeAOIs(hashlib.sha256(raw).hexdigest(),'b'*64,[{'name':'A','instance':11}])
                with self.assertRaises(ModelError):NativeAOIRoutines.from_acd(path,'b'*64,[{'aoi':'A','name':'Run'}],parents)

    def test_manifest_validation_rejects_stale_hashes_duplicate_ids_and_foreign_fields(self):
        row=dict(aoi='A',name='Run',aoi_instance=11,instance=7)
        binding=NativeAOIRoutines('a'*64,'b'*64,[row])
        with self.assertRaises(ModelError):NativeAOIRoutines.from_manifest(binding.manifest(),'c'*64)
        for rows in ([row,row],[row,{**row,'name':'Other'}],[{**row,'aoi_instance':True}],
                     [{**row,'instance':0}],[{**row,'program':'A'}]):
            with self.assertRaises(ModelError):NativeAOIRoutines('a'*64,'b'*64,rows)

    def test_path_decoder_retains_only_one_aoi_parent_with_explicit_child(self):
        path=logical_path(0x6D,7,aoi=60000);decoded=decode_path(path)
        self.assertEqual((decoded.aoi_instance,decoded.class_id,decoded.instance),(60000,0x6D,7))
        self.assertIsNone(decoded.program_instance)
        for suffix in (b'',b'\x20\x6b\x24\x07',logical_path(0x6D,7,program=1)):
            raw=logical_path(0x338,60000)+(b'\x20\x6d' if not suffix else suffix)
            with self.assertRaises(CIPError):decode_path(raw)
        for kwargs in ({'program':1,'aoi':2},{'aoi':0},{'aoi':True}):
            with self.assertRaises(InventoryError):logical_path(0x6D,7,**kwargs)

    def test_partial_ambiguous_and_protected_routines_do_not_become_empty_catalogs(self):
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/AOILab.L5X').getroot()
        for change in ('missing','duplicate','namespace','unknown','alias','context','content','class'):
            tree=copy.deepcopy(root);node=tree.find('./Controller/AddOnInstructionDefinitions')[0]
            section=node.find('Routines');routine=section[0]
            if change=='missing':node.remove(section)
            elif change=='duplicate':section.append(copy.deepcopy(routine))
            elif change=='namespace':routine.tag='{urn:other}Routine'
            elif change=='unknown':E.SubElement(section,'Unknown')
            elif change=='alias':routine.set('name','Other')
            elif change=='context':routine.set('Use','Context')
            elif change=='content':routine.remove(routine.find('RLLContent'))
            else:routine.set('Class','Safety')
            catalog=AOICatalog.from_source(tree,tree.find('Controller'))
            self.assertIsNotNone(catalog.metadata,change);self.assertIsNone(catalog.metadata[0].routines,change)


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional independent client key generator')
class AOIRoutineTcpTests(unittest.TestCase):
    def setUp(self):
        aoi_tests.AOIMetadataTcpTests.setUp(self)
        root=E.parse(self.app.engine.project.path).getroot();section=root.find('./Controller/AddOnInstructionDefinitions')
        for i,parent in enumerate(section):
            for routine in parent.findall('./Routines/Routine'):
                if routine.get('Name')=='Logic':E.SubElement(routine,'Description').text='Parent '+str(i)
        E.SubElement(section,'EncodedData',Name='Opaque',Class='Standard',EncodedType='AddOnInstructionDefinition',Revision='1.0').text='opaque'
        raw=E.tostring(root);sha=hashlib.sha256(raw).hexdigest()
        self.parents=NativeAOIs('a'*64,sha,[dict(name=n.get('Name'),instance=700+i) for i,n in enumerate(section)])
        self.binding=NativeAOIRoutines('a'*64,sha,[dict(aoi=n.get('Name'),name=r.get('Name'),aoi_instance=700+i,instance=7+j)
            for i,n in enumerate(section) for j,r in enumerate(n.findall('./Routines/Routine'))])
        self.data=dict(name='aoi.L5X',content=base64.b64encode(raw).decode(),native_aois=self.parents.manifest(),
            native_project_identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1).manifest(),native_aoi_routines=self.binding.manifest())
        self.app.command('load',self.data)

    def tearDown(self):aoi_tests.AOIMetadataTcpTests.tearDown(self)

    def request(self,service,parent,instance=0,attribute=None,payload=b''):
        path=logical_path(0x6D,instance,aoi=parent)
        if attribute is not None:path+=bytes((0x30,attribute))
        return bytes((service,len(path)//2))+path+payload

    def test_signed_reads_keep_reused_child_ids_separate_and_descriptions_optional(self):
        memory=copy.deepcopy(self.app.engine.memory.values)
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            for parent,count in ((700,3),(701,2),(702,1)):
                raw=client.request(self.request(0x4B,parent));self.assertEqual(raw,b'\xcb\0\0\0'+struct.pack('<'+'I'*count,*range(7,7+count)))
                text=('Parent '+str(parent-700)).encode()
                self.assertEqual(client.request(self.request(0x0E,parent,7,7)),b'\x8e\0\0\0'+struct.pack('<H',len(text))+text)
            self.assertEqual(client.request(self.request(0x0E,700,8,7))[2],0x14)
            self.assertEqual(client.request(self.request(0x0E,700,500,7))[2],5)
            self.assertEqual(client.request(self.request(0x4B,703))[2],0x0C)
            self.assertEqual(client.request(self.request(0x4B,799))[2],5)
            for service in (4,8,9,0x10,0x5C):self.assertNotEqual(client.request(self.request(service,700,7))[2],0)
            # A same-number Program cannot resolve through AOI identities.
            path=logical_path(0x6D,7,program=700)+b'\x30\x07'
            self.assertNotEqual(client.request(bytes((0x0E,len(path)//2))+path)[2],0)
        self.assertEqual(self.app.engine.memory.values,memory);self.assertEqual(self.app.engine.scan_count,0)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        gaps=self.endpoint.state()['attribute_gaps']
        self.assertTrue(any(r['class_id']==0x6D and r['aoi_instance']==700 and r['instance']==8 for r in gaps))

    def test_pagination_and_inventory_keep_parent_scope_and_aggregate_bounds(self):
        router=Router(self.app,self.endpoint)
        path=decode_path(logical_path(0x6D,0,aoi=700))
        self.assertEqual(router.instance_list(path,b'',8),(6,struct.pack('<I',7)))
        path.instance=8;self.assertEqual(router.instance_list(path,b'',12),(0,struct.pack('<2I',8,9)))
        report=collect_inventory(self.endpoint,read_values=False)
        self.assertEqual(report['aoi_executable_inventory']['discovered_count'],6)
        self.assertEqual(report['aoi_executable_inventory']['unavailable_aoi_instances'],[703])
        self.assertEqual(values(report['aois'][0]['executables'][0]['metadata']),{7:'Parent 0'})
        requests=[r for r in report['requests'] if r['class_id']==0x6D and r['aoi_instance'] is not None]
        self.assertEqual({r['aoi_instance'] for r in requests},{700,701,702,703})
        self.assertTrue(all(r['program_instance'] is None for r in requests))
        with self.assertRaises(InventoryError):collect_inventory(self.endpoint,read_values=False,limits=Limits(routines=5))

    def test_stale_foreign_missing_and_wrong_parent_bindings_stay_unavailable(self):
        variants=(None,NativeAOIRoutines('b'*64,self.binding.source_l5x_sha256,[r.manifest() for r in self.binding.rows]),
                  NativeAOIRoutines('a'*64,'b'*64,[r.manifest() for r in self.binding.rows]),
                  NativeAOIRoutines('a'*64,self.binding.source_l5x_sha256,[{**r.manifest(),'aoi_instance':800}
                      if r.aoi_instance==700 else r.manifest() for r in self.binding.rows]))
        for binding in variants:
            self.app.native_aoi_routines=binding
            with AnonymousClient(self.endpoint) as client:
                client.bind();self.assertEqual(client.request(self.request(0x4B,700))[2],0x0C)

    def test_load_validates_exact_readable_coverage_atomically_and_reload_clears_binding(self):
        engine=self.app.engine
        for rows in ([],[r.manifest() for r in self.binding.rows[1:]],
                     [{**r.manifest(),'aoi_instance':900} for r in self.binding.rows]):
            manifest={**self.binding.manifest(),'routines':rows}
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_aoi_routines':manifest})
            self.assertIs(self.app.engine,engine)
        self.app.command('demo',{'sample':'ConveyorDemo'});self.assertIsNone(self.app.native_aoi_routines)


if __name__=='__main__':unittest.main()
