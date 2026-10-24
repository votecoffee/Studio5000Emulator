"""Original scoped Routine Symbols link to their own interpreter headers."""
import base64
import copy
import hashlib
import struct
import unittest
from dataclasses import FrozenInstanceError
from xml.etree import ElementTree as E

import test_reference_symbols as fixtures
from logixlab import native_auxiliary_symbols as aux
from logixlab.model import ModelError
from logixlab.native_routines import NativeRoutines
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.reference_symbols import RoutineReferenceSymbols
from logixlab.ethernetip import symbol_path
from tools.upload_inventory import logical_path


class RoutineReferenceTests(unittest.TestCase):
    tearDown=fixtures.ReferenceWireTests.tearDown
    cip=fixtures.ReferenceWireTests.cip

    def setUp(self):
        fixtures.ReferenceWireTests.setUp(self)
        tree=E.fromstring(base64.b64decode(self.data['content']));parent=tree.find('./Controller/Programs')
        other=copy.deepcopy(parent[0]);other.set('Name','OtherProgram');parent.append(other)
        content=E.tostring(tree);sha=hashlib.sha256(content).hexdigest()
        self.data['content']=base64.b64encode(content).decode()
        for key in ('native_project_identity','native_tasks'):self.data[key]['source_l5x_sha256']=sha
        symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'StartPB',3)],
            [dict(name='MainProgram',instance=123),dict(name='OtherProgram',instance=124)])
        routines=[];references=[fixtures.reference_row(),fixtures.reference_row('Task','MainTask',18),fixtures.reference_row(target='OtherProgram',instance=19)]
        references[-1]['name']='$1234abce$'
        for program,instance in (('MainProgram',123),('OtherProgram',124)):
            for i,name in enumerate(('MainRoutine','Reporting')):
                routines.append(dict(program=program,name=name,program_instance=instance,instance=40+i,type_word=0x7FF))
                references.append(dict(program_instance=instance,instance=3+i,name=f'${instance*65536+3+i:08x}$',
                    component_type=256,reference_name='Routine:'+name))
        self.data.update(native_symbols=symbols.manifest(),native_routines=NativeRoutines('a'*64,sha,routines).manifest(),
            native_auxiliary_symbols=aux.NativeAuxiliarySymbols('a'*64,sha,references).manifest())
        self.app.command('load',self.data)

    def test_scoped_discovery_original_ids_header_links_and_no_data_table_sentinel(self):
        before=copy.deepcopy(self.app.state());registry=self.app.engine.runtime_references;addresses=set()
        root_header=self.cip(14,logical_path(0x6B,3)+b'\x30\5')[4:]
        for program,instance in (('MainProgram',123),('OtherProgram',124)):
            self.assertEqual(self.cip(0x4B,logical_path(0x6B,0,program=instance)),b'\xcb\0\0\0'+struct.pack('<II',3,4))
            self.assertEqual(self.cip(0x4B,logical_path(0x6A,0,program=instance)),b'\xcb\0\0\0')
            for symbol,routine in ((3,40),(4,41)):
                path=logical_path(0x6B,symbol,program=instance)
                self.assertEqual(self.cip(14,path+b'\x30\2'),b'\x8e\0\0\0'+struct.pack('<H',0x106D))
                self.assertEqual(self.cip(14,path+b'\x30\x0c'),b'\x8e\0\0\0'+struct.pack('<I',65535))
                header=self.cip(14,path+b'\x30\5')[4:];value=self.cip(14,path+b'\x30\3')[4:]
                self.assertNotEqual(header,root_header);self.assertNotEqual(header,value)
                self.assertEqual(value,self.cip(14,logical_path(0x6D,routine,program=instance)+b'\x30\x08')[4:])
                self.assertIsNotNone(registry.resolve(self.app.engine.project,int.from_bytes(header,'little'),'scoped_symbol'))
                self.assertNotIn(value,addresses);addresses.add(value)
                named=symbol_path('Program:'+program)+bytes((0x20,0x6B,0x24,symbol))
                self.assertEqual(self.cip(14,named+b'\x30\1'),self.cip(14,path+b'\x30\1'))
        for key in ('tags','scan','ms','routines','controller'):self.assertEqual(before[key],self.app.state()[key])

    def test_enumeration_pagination_and_all_attribute_widths_are_preserved(self):
        attributes=(1,2,3,5,6,7,8,10,11,12,14,9);payload=struct.pack('<13H',12,*attributes)
        for row in self.router.reference_symbols('MainProgram'):
            symbol=next(s for s in self.router.symbols('MainProgram') if s['id']==row.instance)
            values=self.router.symbol_attributes(symbol)
            expected=struct.pack('<H',12)+b''.join(struct.pack('<HH',n,0)+values[n] for n in attributes)
            self.assertEqual(self.cip(3,logical_path(0x6B,row.instance,program=123),payload),b'\x83\0\0\0'+expected)
        attrs=struct.pack('<3H',2,1,2);path=logical_path(0x6B,3,program=123)
        first=self.cip(0x55,path,attrs,limit=33)
        self.assertEqual(first[:4],b'\xd5\0\6\0');self.assertEqual(struct.unpack_from('<I',first,4)[0],3)
        self.assertEqual(self.cip(0x55,logical_path(0x6B,4,program=123),attrs)[2],0)

    def test_metadata_references_never_supply_tag_values_writes_or_table_storage(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for instance in (123,124):
            path=logical_path(0x6B,3,program=instance)
            for service,payload in ((0x4C,b'\1\0'),(0x52,b'\1\0'+bytes(4)),(0x4D,b'\xc4\0\1\0'+bytes(4)),(0x4E,b'\1\0\1\1')):
                self.assertEqual(self.cip(service,path,payload)[2],0x0F)
            self.assertEqual(self.cip(14,logical_path(0x6A,3,program=instance)+b'\x30\2')[2],5)
            self.assertEqual(self.cip(0x10,path+b'\x30\1',b'\1\0X')[2],8)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(set(self.router.scalar_storage().by_ref),{'startpb'})

    def test_missing_or_legacy_routine_bindings_and_incomplete_inventory_do_not_invent_symbols(self):
        for missing in ('native_routines','native_auxiliary_symbols'):
            self.app.command('load',{k:v for k,v in self.data.items() if k!=missing})
            self.assertIsNone(self.app.native_routine_reference_symbols)
            self.assertEqual(self.cip(0x4B,logical_path(0x6B,0,program=123)),b'\xcb\0\0\0')
        changed=copy.deepcopy(self.data);changed['native_auxiliary_symbols']['symbols'].pop()
        self.app.command('load',changed);self.assertIsNone(self.app.native_routine_reference_symbols)
        self.assertIsNotNone(self.app.native_reference_symbols)

    def test_unknown_target_duplicate_and_tag_id_collision_reject_load_atomically(self):
        original=self.app.engine
        for change in ('unknown','duplicate','collision'):
            data=copy.deepcopy(self.data);rows=data['native_auxiliary_symbols']['symbols']
            if change=='unknown':rows[-1]['reference_name']='Routine:Missing'
            elif change=='duplicate':rows[-1]['reference_name']='Routine:MainRoutine'
            else:data['native_symbols']['symbols'].append(dict(scope='MainProgram',program_instance=123,name='StartPB',instance=3))
            with self.subTest(change=change),self.assertRaises(ModelError):self.app.command('load',data)
            self.assertIs(self.app.engine,original)

    def test_stale_native_sources_runtime_target_kinds_and_replaced_bindings_revoke_discovery(self):
        saved=self.app.native_routines;self.app.native_routines=None
        self.assertEqual(self.cip(14,logical_path(0x6B,3,program=123)+b'\x30\1')[2],0x0C)
        self.app.native_routines=saved
        self.app.engine.project.routines['mainprogram/mainroutine'].kind='ST'
        self.assertEqual(self.cip(0x4B,logical_path(0x6B,0,program=123))[2],0x0C)
        self.app.engine.project.routines['mainprogram/mainroutine'].kind='RLL'
        self.app.engine.project.programs['MainProgram']['class']='Safety'
        self.assertFalse(self.app.native_routine_reference_symbols.current(self.app.engine.project,self.app.native_project_identity,
            self.app.native_symbols,self.app.native_routines,self.app.native_auxiliary_symbols))

    def test_immutable_catalog_and_reset_revoke_old_addresses(self):
        catalog=self.app.native_routine_reference_symbols
        self.assertEqual(catalog.description()['symbols'],4)
        with self.assertRaises(FrozenInstanceError):catalog.rows=()
        with self.assertRaises(TypeError):catalog.by_scope[(123,3)]=None
        path=logical_path(0x6B,3,program=123)+b'\x30\5';old=self.cip(14,path)[4:]
        self.app.command('reset',{});new=self.cip(14,path)[4:]
        self.assertNotEqual(old,new)
        self.assertIsNone(self.app.engine.runtime_references.resolve(self.app.engine.project,int.from_bytes(old,'little'),'scoped_symbol'))


if __name__=='__main__':unittest.main()
