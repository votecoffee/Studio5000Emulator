"""Reference metadata has original IDs and object backing, never tag storage."""
import base64
import copy
from dataclasses import FrozenInstanceError
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab import native_auxiliary_symbols as aux
from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.native_tasks import NativeTasks
from logixlab.native_routines import NativeRoutines
from logixlab.reference_symbols import ReferenceSymbols
from logixlab.server import Application
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path
from test_native_auxiliary_symbols import record,known
from test_native_routines import database,container
from test_source_object_verification import bindings


def reference_row(kind='Program',target='MainProgram',instance=17):
    return dict(program_instance=0,instance=instance,name='$1234abcd$' if kind=='Program' else '$8765abcd$',
                component_type=256,reference_name=kind+':'+target)


def reference_record(display='Program:ProgramA',instance=17,**kwargs):
    data=bytearray(record(name=f'${instance:08x}$',instance=instance,**kwargs));offset=6+148
    raw=display.encode('ascii');struct.pack_into('<H',data,offset+90,len(raw));data[offset+92:offset+92+len(raw)]=raw
    return bytes(data)


class ReferenceSourceTests(unittest.TestCase):
    def test_reader_retains_only_explicit_root_program_task_data_names_and_original_ids(self):
        primary,_=bindings()
        raw=database(*known(),reference_record(),reference_record('Task:TaskA',instance=18),
            reference_record('Routine:Run',instance=19),record('__CONTAINER',instance=20,component_type=264))
        rows=aux.symbol_paths(raw,primary)
        self.assertEqual([r.get('reference_name') for r in rows],['Program:ProgramA','Task:TaskA',None,None])
        self.assertEqual([r['instance'] for r in rows],[17,18,19,20])
        for compressed in (False,True):
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'source.ACD';path.write_bytes(container(raw,compressed));sha=hashlib.sha256(path.read_bytes()).hexdigest()
                bound=NativeSymbols(sha,'b'*64,list(primary.by_key.values()),primary.explicit_programs)
                parsed=aux.NativeAuxiliarySymbols.from_acd(path,'b'*64,bound)
                self.assertEqual(parsed.manifest()['symbols'],rows)
                self.assertEqual(parsed.description()['reference_data_names'],2)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),sha)

    def test_reference_name_bounds_format_scope_and_manifest_fields_fail_closed(self):
        primary,_=bindings()
        bad=[]
        for display in ('Program:Bad name','Task:', 'Program:'+'A'*41):bad.append(reference_record(display))
        raw=bytearray(reference_record());struct.pack_into('<H',raw,6+148+90,200);bad.append(bytes(raw))
        raw=bytearray(reference_record());raw[6+148+92+len('Program:ProgramA')]=1;bad.append(bytes(raw))
        for value in bad:
            with self.assertRaises(ModelError):aux.symbol_paths(database(*known(),value),primary)
        for row in ({**reference_row(),'program_instance':2},{**reference_row(),'component_type':264},
                    {**reference_row(),'name':'UserTag'},{**reference_row(),'reference_name':True}):
            with self.assertRaises(ModelError):aux.NativeAuxiliarySymbols('a'*64,'b'*64,[row])


class ReferenceWireTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        root=E.parse(self.app.engine.project.path).getroot();program=root.find('./Controller/Programs/Program')
        program.set('UseAsFolder','false');program.set('TestEdits','false')
        content=E.tostring(root);sha=hashlib.sha256(content).hexdigest()
        self.identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1)
        self.symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'StartPB',3)],[dict(name='MainProgram',instance=123)])
        self.tasks=NativeTasks('a'*64,sha,[dict(name='MainTask',instance=7)])
        self.auxiliary=aux.NativeAuxiliarySymbols('a'*64,sha,[reference_row(),reference_row('Task','MainTask',18)])
        names=self.app.engine.project.executable_configuration.routine_names('MainProgram',source_sha256=self.app.engine.project.sha256)
        routines=NativeRoutines('a'*64,sha,[dict(program='MainProgram',name=name,program_instance=123,instance=i+40) for i,name in enumerate(names)])
        self.data=dict(name='source.L5X',content=base64.b64encode(content).decode(),native_project_identity=self.identity.manifest(),
            native_symbols=self.symbols.manifest(),native_tasks=self.tasks.manifest(),native_routines=routines.manifest(),native_auxiliary_symbols=self.auxiliary.manifest())
        self.app.command('load',self.data);self.endpoint=Endpoint(self.app,0,True,'logix-v35-l85e')
        self.app.endpoint=self.endpoint;self.router=self.endpoint.router

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def cip(self,service,path,data=b'',limit=480):
        return self.router.handle(bytes((service,len(path)//2))+path+data,Session(),limit=limit)

    def test_metadata_lists_have_original_ids_types_and_addresses_backed_by_live_targets(self):
        before=copy.deepcopy(self.app.state());project=self.app.engine.project;space=self.app.engine.runtime_references
        self.assertEqual(self.cip(0x4B,logical_path(0x6B,0)),b'\xcb\0\0\0'+struct.pack('<3I',3,17,18))
        catalog=self.app.native_reference_symbols
        for row in catalog.rows:
            values=self.router.symbol_attributes(next(s for s in self.router.symbols() if s['id']==row.instance))
            value=int.from_bytes(values[3],'little');header=int.from_bytes(values[5],'little')
            self.assertNotEqual(value,header);self.assertIsNotNone(space.resolve(project,value,row.kind))
            self.assertIs(space.resolve(project,header,'symbol'),row)
            expected=struct.pack('<H',12)+b''.join(struct.pack('<HH',n,0)+values[n] for n in (1,2,3,5,6,7,8,10,11,12,14,9))
            self.assertEqual(self.cip(3,logical_path(0x6B,row.instance),struct.pack('<13H',12,1,2,3,5,6,7,8,10,11,12,14,9)),b'\x83\0\0\0'+expected)
            self.assertEqual(values[2],struct.pack('<H',0x1068 if row.kind=='program' else 0x1070))
            self.assertEqual(values[12],b'\xff\xff\0\0')
            for n in values:self.assertEqual(self.cip(14,logical_path(0x6B,row.instance)+b'\x30'+bytes((n,)))[4:],values[n])
        program=self.cip(14,logical_path(0x68,123)+b'\x30\x10')[4:]
        self.assertEqual(program,self.cip(14,logical_path(0x6B,17)+b'\x30\3')[4:])
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_references_never_enter_tag_values_tables_storage_or_other_program_scopes(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.cip(0x4B,logical_path(0x6A,0)),b'\xcb\0\0\0'+struct.pack('<I',3))
        self.assertEqual({s['ref'] for s in self.router.data_tables()},{'StartPB'})
        for instance in (17,18):
            path=logical_path(0x6B,instance)
            for service,payload in ((0x4C,b'\1\0'),(0x52,b'\1\0'+bytes(4)),(0x4D,b'\xc4\0\1\0'+bytes(4)),(0x4E,b'\1\0\1\1')):
                self.assertEqual(self.cip(service,path,payload)[2],0x0F)
            self.assertEqual(self.cip(0x0E,logical_path(0x6A,instance)+b'\x30\2')[2],5)
            self.assertEqual(self.cip(0x0E,logical_path(0x6B,instance,program=123)+b'\x30\1')[2],5)
            self.assertEqual(self.cip(0x10,path+b'\x30\1',b'\1\0X')[2],8)
        self.assertNotEqual(self.cip(0x4C,symbol_path('Program:MainProgram'),b'\1\0')[2],0)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_enumeration_keeps_cursors_partial_rows_and_all_or_nothing_descriptors(self):
        path=logical_path(0x6B,17);payload=struct.pack('<3H',2,1,2)
        first=self.cip(0x55,path,payload,limit=33)
        self.assertEqual(first[:4],b'\xd5\0\6\0');self.assertEqual(struct.unpack_from('<I',first,4)[0],17)
        last=self.cip(0x55,logical_path(0x6B,18),payload)
        self.assertEqual(last[2],0);self.assertEqual(struct.unpack_from('<I',last,4)[0],18)

    def test_catalog_rebind_staleness_collisions_and_unavailable_targets_do_not_leak_references(self):
        engine=self.app.engine
        for auxiliary in (aux.NativeAuxiliarySymbols('a'*64,engine.project.sha256,[reference_row(target='Missing')]),
                          aux.NativeAuxiliarySymbols('a'*64,engine.project.sha256,[reference_row(instance=3)])):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_auxiliary_symbols':auxiliary.manifest()})
            self.assertIs(self.app.engine,engine)
        original=self.app.native_tasks;self.app.native_tasks=None
        self.assertEqual(self.cip(14,logical_path(0x6B,17)+b'\x30\1')[2],0x0C)
        self.app.native_tasks=original
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_auxiliary_symbols'})
        self.assertIsNone(self.app.native_reference_symbols)
        self.assertEqual(self.cip(14,logical_path(0x6B,17)+b'\x30\1')[2],5)

    def test_catalog_is_immutable_incomplete_inventory_and_unsupported_source_stay_unavailable(self):
        catalog=self.app.native_reference_symbols;self.assertEqual(catalog.description()['symbols'],2)
        with self.assertRaises(FrozenInstanceError):catalog.rows=()
        with self.assertRaises(TypeError):catalog.by_instance[17]=None
        partial=aux.NativeAuxiliarySymbols('a'*64,self.app.engine.project.sha256,[reference_row()])
        self.assertIsNone(ReferenceSymbols.from_source(self.app.engine.project,self.app.native_project_identity,self.app.native_symbols,self.app.native_tasks,partial))
        self.app.command('demo',{'sample':'ConveyorDemo'});self.assertIsNone(self.app.native_reference_symbols)

    def test_reset_replaces_object_addresses_and_symbol_headers_without_changing_source_bindings(self):
        first=self.cip(14,logical_path(0x6B,18)+b'\x30\3')[4:];header=self.cip(14,logical_path(0x6B,18)+b'\x30\5')[4:]
        self.app.command('reset',{})
        second=self.cip(14,logical_path(0x6B,18)+b'\x30\3')[4:];new_header=self.cip(14,logical_path(0x6B,18)+b'\x30\5')[4:]
        self.assertNotEqual(first,second);self.assertNotEqual(header,new_header)
        self.assertIsNone(self.app.engine.runtime_references.resolve(self.app.engine.project,int.from_bytes(header,'little'),'symbol'))

    def test_mutated_root_inventory_and_runtime_target_kind_revoke_reference_discovery(self):
        original=dict(self.app.native_symbols.by_key)
        self.app.native_symbols.by_key['startpb']=Symbol('',0,'StartPB',17)
        self.assertEqual(self.cip(14,logical_path(0x6B,17)+b'\x30\1')[2],0x0C)
        self.app.native_symbols.by_key=original
        self.app.engine.project.programs['MainProgram']['class']='Safety'
        self.assertEqual(self.cip(0x4B,logical_path(0x6B,0))[2],0x0C)
        self.app.engine.project.programs['MainProgram']['class']='Standard'
        self.app.engine.project.tasks[0]['type']='Event'
        self.assertEqual(self.cip(14,logical_path(0x6B,18)+b'\x30\1')[2],0x0C)

    def test_unsupported_source_classes_and_folders_never_become_standard_program_references(self):
        for change in ('Safety','folder','opaque'):
            data=copy.deepcopy(self.data);root=E.fromstring(base64.b64decode(data['content']));program=root.find('./Controller/Programs/Program')
            if change=='Safety':program.set('Class','Safety')
            elif change=='folder':program.set('UseAsFolder','true')
            else:E.SubElement(program,'OpaqueProgramData')
            content=E.tostring(root);sha=hashlib.sha256(content).hexdigest();data['content']=base64.b64encode(content).decode()
            data.pop('native_routines')
            for key in ('native_project_identity','native_symbols','native_tasks','native_auxiliary_symbols'):data[key]['source_l5x_sha256']=sha
            self.app.command('load',data)
            self.assertFalse(any(row['name'].startswith('Program:') for row in self.router.symbols()))

    def test_anonymous_signed_tcp_discovery_and_metadata_preserve_tag_values(self):
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint
        self.endpoint.start();before=copy.deepcopy(self.app.state())
        with AnonymousClient(self.endpoint) as client:
            client.bind();path=logical_path(0x6B,17)+b'\x30\2'
            self.assertEqual(client.request(bytes((14,len(path)//2))+path),b'\x8e\0\0\0'+struct.pack('<H',0x1068))
        for key in ('tags','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])


if __name__=='__main__':unittest.main()
