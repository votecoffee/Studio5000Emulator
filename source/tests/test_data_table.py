"""Data Table metadata stays scoped, readable and independent of tag values."""
import copy
import struct
import tempfile
import unittest

from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab import data_table
from logixlab.model import ModelError,Tag
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
        self.app.engine.project.tags['step'].constant=True
        self.bind(Symbol('',0,'Step',3));path=bytes.fromhex('206a2403')
        for attr in (3,4,6,7,9):self.assertEqual(self.cip(0x0E,path+bytes((0x30,attr)))[2],0x14)
        raw=self.cip(3,path,struct.pack('<4H',3,2,3,8))
        self.assertEqual(raw,b'\x83\0\x0A\0'+struct.pack('<HHHHHHHHI',3,2,0,0xC4,3,0x14,8,0,3))
        self.assertEqual(self.cip(1,path)[2],8)
        self.assertEqual(self.cip(0x4C,path,b'\1\0')[2],8)

    def test_scalar_addresses_are_backed_by_distinct_model_descriptor_and_current_value_bytes(self):
        self.bind(Symbol('',0,'Step',3));path=bytes.fromhex('206a2403')
        space=self.router.scalar_storage();cell=space.by_ref['step']
        for attr,expected in ((3,struct.pack('<I',cell.address)),(6,bytes(2)),
                              (7,struct.pack('<I',cell.value_address)),(9,bytes(2))):
            self.assertEqual(self.cip(0x0E,path+bytes((0x30,attr))),b'\x8E\0\0\0'+expected)
        self.assertNotEqual(cell.address,cell.value_address)
        self.assertEqual(space.read(cell.address,32,self.app.engine.memory.read),cell.header())
        self.app.engine.memory.write('Step',1234)
        self.assertEqual(space.read(cell.value_address,4,self.app.engine.memory.read),struct.pack('<i',1234))
        self.assertIs(self.router.scalar_storage(),space)
        self.assertEqual(self.cip(0x4F,path,struct.pack('<IH',0,4)),b'\xCF\0\0\0'+struct.pack('<i',1234))
        self.assertEqual(self.cip(0x0E,path+b'\x30\4')[2],0x14)

    def test_full_scalar_reads_encode_each_atomic_width_without_a_tag_type_prefix(self):
        for dtype,fmt,value in (('BOOL','B',True),('SINT','b',-7),('INT','h',-300),
                ('DINT','i',-123456),('LINT','q',-(1<<40)),('USINT','B',250),
                ('UINT','H',65000),('UDINT','I',1<<31),('ULINT','Q',1<<63),('REAL','f',2.5)):
            tag=self.add('Width'+dtype,value);tag.dtype=dtype
            self.bind(Symbol('',0,tag.name,3))
            encoded=struct.pack('<'+fmt,value)
            self.assertEqual(self.cip(0x4F,bytes.fromhex('206a2403'),struct.pack('<IH',0,len(encoded))),
                             b'\xCF\0\0\0'+encoded,dtype)

    def test_scalar_read_selectors_lengths_and_response_budgets_are_strict(self):
        self.bind(Symbol('',0,'Step',3));path=bytes.fromhex('206a2403')
        initial=copy.deepcopy(self.app.engine.memory.values)
        for payload,status in ((b'',0x13),(bytes(5),0x13),(bytes(7),0x15),
                (struct.pack('<IH',1,4),3),(struct.pack('<IH',0,0),3),(struct.pack('<IH',0,3),3),
                (struct.pack('<IH',0,5),3)):
            self.assertEqual(self.cip(0x4F,path,payload)[2],status)
        self.assertEqual(self.cip(0x4F,path,struct.pack('<IH',0,4),limit=7)[2],0x1B)
        self.assertEqual(self.cip(0x4F,path+b'\x30\1',struct.pack('<IH',0,4))[2],4)
        self.app.engine.memory.values['step']=None
        self.assertEqual(self.cip(0x4F,path,struct.pack('<IH',0,4))[2],0x0C)
        self.app.engine.memory.values=initial
        for service in (4,0x10,0x4D,0x4E,0x50,0x53):
            self.assertNotEqual(self.cip(service,path,bytes(8))[2],0)
        self.assertEqual(self.app.engine.memory.values,initial)

    def test_scalar_storage_excludes_arrays_constants_private_tags_and_aliases(self):
        self.add('Const',constant=True);self.add('Private',external_access='None')
        self.add('Alias',None,alias='Step')
        self.bind(Symbol('',0,'Step',3),Symbol('',0,'Values',4),Symbol('',0,'Const',5),
                  Symbol('',0,'Private',6),Symbol('',0,'Alias',7))
        self.assertEqual(set(self.router.scalar_storage().by_ref),{'step'})
        for instance in (4,5):
            path=bytes((0x20,0x6A,0x24,instance))
            self.assertEqual(self.cip(0x0E,path+b'\x30\3')[2],0x14)
            self.assertEqual(self.cip(0x4F,path,struct.pack('<IH',0,4))[2],8)
        for instance in (6,7):
            self.assertEqual(self.cip(0x4F,bytes((0x20,0x6A,0x24,instance)),struct.pack('<IH',0,4))[2],5)

    def test_program_storage_with_the_same_instance_id_cannot_alias_controller_bytes(self):
        self.add('Local',42,scope='MainProgram');self.app.engine.memory.write('Step',17)
        self.bind(Symbol('',0,'Step',3),Symbol('MainProgram',17,'Local',3))
        space=self.router.scalar_storage()
        self.assertNotEqual(space.by_ref['step'].value_address,space.by_ref['program:mainprogram.local'].value_address)
        for prefix,value in ((b'',17),(symbol_path('Program:MainProgram'),42),(bytes.fromhex('20682411'),42)):
            self.assertEqual(self.cip(0x4F,prefix+bytes.fromhex('206a2403'),struct.pack('<IH',0,4)),
                             b'\xCF\0\0\0'+struct.pack('<i',value))
        self.app.engine.project.programs['MainProgram']['class']='Safety'
        self.assertNotIn('program:mainprogram.local',self.router.scalar_storage().by_ref)
        self.assertEqual(self.cip(0x4F,bytes.fromhex('20682411206a2403'),struct.pack('<IH',0,4))[2],0x0F)

    def test_address_ranges_never_cross_cells_padding_or_unknown_addresses(self):
        self.bind(Symbol('',0,'Step',3));space=self.router.scalar_storage();cell=space.by_ref['step']
        for address,count in ((cell.address-1,1),(cell.address+31,2),(cell.value_address+3,2),
                (cell.value_address+4,1),(0,1),(1<<32,1),(cell.address,0),(cell.address,33),(True,1)):
            with self.assertRaises(ModelError):space.read(address,count,self.app.engine.memory.read)
        with self.assertRaises(ModelError):
            data_table.AddressSpace([]).read(data_table.VALUE_BASE,1,self.app.engine.memory.read)

    def test_storage_limit_omits_excess_cells_without_overlapping_address_ranges(self):
        rows=[({'ref':f'Cell{i:05}','id':i+1,'type':0xC4},'<i') for i in range(data_table.MAX_SCALARS+1)]
        space=data_table.AddressSpace(rows)
        self.assertEqual(len(space.cells),data_table.MAX_SCALARS)
        self.assertNotIn(f'cell{data_table.MAX_SCALARS:05}',space.by_ref)
        self.assertEqual(len({cell.address for cell in space.cells}),data_table.MAX_SCALARS)
        self.assertEqual(len({cell.value_address for cell in space.cells}),data_table.MAX_SCALARS)

    def test_storage_catalog_is_rebuilt_on_source_replacement_and_stale_bindings_fail(self):
        self.bind(Symbol('',0,'Step',3));before=self.router.scalar_storage()
        self.app.native_symbols.source_l5x_sha256='2'*64
        self.assertEqual(self.cip(0x4F,bytes.fromhex('206a2403'),struct.pack('<IH',0,4))[2],0x0C)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertIsNot(self.router.scalar_storage(),before)
        self.assertNotIn('step',self.router.scalar_storage().by_ref)

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
