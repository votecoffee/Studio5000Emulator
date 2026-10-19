"""Data Table metadata stays scoped, readable and independent of tag values."""
import copy
import struct
import tempfile
import unittest

from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab.model import Tag
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.server import Application


class DataTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'TextLab'})
        self.endpoint=Endpoint(self.app,0,True,'logix-v35-l85e');self.router=self.endpoint.router

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def add(self,name,value=1,**fields):
        tag=Tag(name,'DINT',value,**fields);self.app.engine.project.tags[tag.key.lower()]=tag
        self.app.engine.memory.values[tag.key.lower()]=copy.deepcopy(value)
        return tag

    def bind(self,*symbols):
        self.app.native_symbols=NativeSymbols('1'*64,self.app.engine.project.sha256,symbols)

    def cip(self,service,path,data=b'',limit=480):
        return self.router.handle(bytes((service,len(path)//2))+path+data,Session(),limit=limit)

    def test_sparse_table_ids_link_to_source_symbol_ids_and_page_in_order(self):
        self.bind(Symbol('',0,'Step',3),Symbol('',0,'Values',70000))
        self.assertEqual(self.cip(0x4B,bytes.fromhex('206a2400'),limit=8),b'\xCB\0\6\0'+struct.pack('<I',3))
        self.assertEqual(self.cip(0x4B,bytes.fromhex('206a2404')),b'\xCB\0\0\0'+struct.pack('<I',70000))
        self.assertEqual(self.cip(0x0E,bytes.fromhex('206a2600701101003008')),b'\x8E\0\0\0'+struct.pack('<I',70000))
        self.assertEqual(self.cip(0x4B,bytes.fromhex('206a2400'),limit=7)[2],0x1B)

    def test_dimensions_type_and_link_are_exact_and_list_order_is_preserved(self):
        self.bind(Symbol('',0,'Values',70000))
        path=bytes.fromhex('206a260070110100')
        raw=self.cip(3,path,struct.pack('<5H',4,8,1,2,8))
        expected=(struct.pack('<HHHI',4,8,0,70000)+struct.pack('<HHIII',1,0,5,0,0)+
                  struct.pack('<HHH',2,0,0x20C4)+struct.pack('<HHI',8,0,70000))
        self.assertEqual(raw,b'\x83\0\0\0'+expected)

    def test_class_count_and_maximum_are_not_confused_with_sparse_ids(self):
        self.bind(Symbol('',0,'Step',3),Symbol('',0,'Values',70000))
        for attr,value in ((1,struct.pack('<H',1)),(2,struct.pack('<I',70000)),(3,struct.pack('<I',2))):
            self.assertEqual(self.cip(0x0E,bytes.fromhex('206a240030')+bytes((attr,))),b'\x8E\0\0\0'+value)

    def test_aliases_private_and_unsupported_values_do_not_create_storage(self):
        self.add('Alias',None,alias='Step');self.add('Private',external_access='None')
        self.add('PrivateAlias',None,alias='Private');self.add('Safety',tag_class='Safety')
        self.bind(Symbol('',0,'Step',3),Symbol('',0,'Alias',4),Symbol('',0,'Private',5),
                  Symbol('',0,'PrivateAlias',6),Symbol('',0,'Safety',7),Symbol('',0,'Message',8))
        self.assertEqual(self.cip(0x4B,bytes.fromhex('206a2400')),b'\xCB\0\0\0'+struct.pack('<I',3))
        for instance in (4,5,6,7,8):self.assertEqual(self.cip(0x0E,bytes((0x20,0x6A,0x24,instance,0x30,2)))[2],5)

    def test_program_tables_keep_scopes_and_external_access_boundaries(self):
        self.add('Local',42,scope='MainProgram')
        self.bind(Symbol('',0,'Step',3),Symbol('MainProgram',17,'Local',3))
        for prefix in (symbol_path('Program:MainProgram'),bytes.fromhex('20682411')):
            path=prefix+bytes.fromhex('206a2403')
            self.assertEqual(self.cip(0x0E,path+b'\x30\x08'),b'\x8E\0\0\0'+struct.pack('<I',3))
            self.assertEqual(self.cip(0x4B,prefix+bytes.fromhex('206a2400')),b'\xCB\0\0\0'+struct.pack('<I',3))
        self.app.engine.project.programs['MainProgram']['class']='Safety'
        self.assertEqual(self.cip(0x4B,bytes.fromhex('20682411206a2400'))[2],0x0F)
        self.assertEqual(self.cip(0x4B,bytes.fromhex('20682412206a2400'))[2],5)

    def test_addresses_formal_types_and_values_are_explicitly_unavailable(self):
        self.bind(Symbol('',0,'Step',3));path=bytes.fromhex('206a2403')
        for attr in (3,4,6,7,9):self.assertEqual(self.cip(0x0E,path+bytes((0x30,attr)))[2],0x14)
        raw=self.cip(3,path,struct.pack('<4H',3,2,3,8))
        self.assertEqual(raw,b'\x83\0\x0A\0'+struct.pack('<HHHHHHHHI',3,2,0,0xC4,3,0x14,8,0,3))
        self.assertEqual(self.cip(1,path)[2],8)
        self.assertEqual(self.cip(0x4C,path,b'\1\0')[2],8)

    def test_writes_bad_payloads_and_malformed_paths_leave_memory_intact(self):
        self.bind(Symbol('',0,'Step',3));before=copy.deepcopy(self.app.engine.memory.values)
        path=bytes.fromhex('206a2403')
        for service in (0x10,4,0x4D,0x53,0x4E):self.assertNotEqual(self.cip(service,path,b'\0'*8)[2],0)
        for raw in (bytes.fromhex('20682411206a'),bytes.fromhex('20682411206a2403206a2404')):
            self.assertEqual(self.cip(0x4B,raw)[2],4)
        self.assertEqual(self.cip(0x4B,path,b'x')[2],0x15)
        self.assertEqual(self.cip(0x4B,path+b'\x30\1')[2],4)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_bound_catalog_staleness_and_project_replacement_are_not_cached(self):
        self.bind(Symbol('',0,'Step',3));self.app.native_symbols.source_l5x_sha256='2'*64
        self.assertEqual(self.cip(0x4B,bytes.fromhex('206a2400'))[2],0x0C)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.cip(0x4B,bytes.fromhex('206a2400'))[2],0)
        self.assertNotIn('Step',{row['name'] for row in self.router.data_tables()})


if __name__=='__main__':unittest.main()
