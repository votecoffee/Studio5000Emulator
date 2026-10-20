"""Atomic arrays have scoped model bytes, bounded allocation and live values."""
import copy
import struct
import unittest
from unittest.mock import patch

import test_data_table as fixtures
from logixlab import data_table
from logixlab.model import ModelError
from logixlab.native_symbols import Symbol


class ArrayStorageTests(unittest.TestCase):
    setUp=fixtures.DataTableTests.setUp
    tearDown=fixtures.DataTableTests.tearDown
    add=fixtures.DataTableTests.add
    bind=fixtures.DataTableTests.bind
    cip=fixtures.DataTableTests.cip

    def test_array_descriptors_link_current_values_and_keep_element_width_separate_from_total_size(self):
        self.bind(Symbol('',0,'Step',3),Symbol('',0,'Values',4))
        space=self.router.scalar_storage();cell=space.by_ref['values'];path=bytes.fromhex('206a2404')
        self.assertEqual((cell.size,cell.element_size),(20,4))
        self.assertGreaterEqual(cell.value_address,data_table.ARRAY_VALUE_BASE)
        self.assertEqual(space.by_ref['step'].value_address,data_table.VALUE_BASE)
        for i,value in enumerate((10,20,30,40,50)):self.app.engine.memory.write('Values['+str(i)+']',value)
        expected=struct.pack('<5i',10,20,30,40,50)
        self.assertEqual(self.cip(0x4F,path,struct.pack('<IH',0,20)),b'\xCF\0\0\0'+expected)
        self.assertEqual(space.read(cell.value_address+4,12,self.app.engine.memory.read),expected[4:16])
        self.assertEqual(struct.unpack_from('<3I',cell.header()),(5,0,0))
        self.assertEqual(struct.unpack_from('<H',cell.symbol_header(),10)[0],4)
        self.assertEqual(struct.unpack_from('<3I',cell.symbol_header(),20),(5,0,0))
        symbol=bytes.fromhex('206b2404')
        self.assertEqual(self.cip(14,symbol+b'\x30\x07')[4:],struct.pack('<H',4))
        self.assertEqual(self.cip(14,symbol+b'\x30\x03')[4:],self.cip(14,path+b'\x30\x07')[4:])
        self.app.engine.memory.write('Values[2]',123)
        self.assertIs(self.router.scalar_storage(),space)
        self.assertEqual(space.read(cell.value_address+8,4,self.app.engine.memory.read),struct.pack('<i',123))

    def test_multidimensional_arrays_are_row_major_and_program_ids_do_not_alias_global_storage(self):
        self.add('Grid',[[1,2],[3,4]])
        self.add('Grid',[[5,6],[7,8]],scope='MainProgram')
        self.bind(Symbol('',0,'Grid',3),Symbol('MainProgram',17,'Grid',3))
        space=self.router.scalar_storage();global_cell=space.by_ref['grid'];local=space.by_ref['program:mainprogram.grid']
        self.assertNotEqual(global_cell.value_address,local.value_address)
        for prefix,expected in ((b'',(1,2,3,4)),(bytes.fromhex('20682411'),(5,6,7,8))):
            self.assertEqual(self.cip(0x4F,prefix+bytes.fromhex('206a2403'),struct.pack('<IH',0,16)),
                b'\xCF\0\0\0'+struct.pack('<4i',*expected))
        self.assertEqual(global_cell.dimensions,(2,2,0))
        self.app.engine.project.programs['MainProgram']['class']='Safety'
        self.assertNotIn('program:mainprogram.grid',self.router.scalar_storage().by_ref)

    def test_unaligned_reads_do_not_cross_array_boundaries_or_allocated_padding(self):
        self.add('Tiny',[1,2,3]).dtype='SINT';self.bind(Symbol('',0,'Tiny',3))
        space=self.router.scalar_storage();cell=space.by_ref['tiny']
        self.assertEqual(space.read(cell.value_address+1,2,self.app.engine.memory.read),b'\2\3')
        for address,count in ((cell.value_address+2,2),(cell.value_address+3,1),(cell.value_address+7,1)):
            with self.subTest(address=address),self.assertRaises(ModelError):space.read(address,count,self.app.engine.memory.read)
        self.assertEqual(self.cip(0x4F,bytes.fromhex('206a2403'),struct.pack('<IH',1,3))[2],3)
        self.assertEqual(self.cip(0x4F,bytes.fromhex('206a2403'),struct.pack('<IH',0,3),limit=6)[2],0x1B)

    def test_array_byte_limits_omit_whole_regions_and_keep_later_descriptor_slots_accessible(self):
        rows=[({'ref':name,'id':i+1,'type':code,'dimensions':dims},fmt) for i,(name,code,dims,fmt) in enumerate((
            ('A',0x20C4,(3,0,0),'<i'),('B',0x20C4,(3,0,0),'<i'),('C',0xC4,(0,0,0),'<i')))]
        with patch.object(data_table,'MAX_ARRAY_STORAGE_BYTES',16):space=data_table.AddressSpace(rows)
        self.assertEqual(set(space.by_ref),{'a','c'});self.assertEqual(space.array_bytes,16)
        cell=space.by_ref['c'];self.assertEqual(cell.slot,2)
        self.assertEqual(space.read(cell.address,32,lambda _:0),cell.header())
        self.assertEqual(space.read(cell.symbol_address,32,lambda _:0),cell.symbol_header())
        self.assertEqual(space.read(cell.value_address,4,lambda _:77),struct.pack('<i',77))
        huge={'ref':'Huge','id':100,'type':0x20C4,'dimensions':(data_table.MAX_ARRAY_BYTES//4+1,0,0)}
        self.assertEqual(data_table.AddressSpace([(huge,'<i')]).cells,())

    def test_invalid_shapes_values_and_packed_bool_arrays_never_return_partial_values(self):
        self.bind(Symbol('',0,'Values',3));space=self.router.scalar_storage();cell=space.by_ref['values']
        for value in ([1,2],[1,2,3,4,None],[1,2,3,4,1<<40],[1,2,3,4,[5]]):
            with self.subTest(value=value),self.assertRaises(ModelError):cell.value(lambda _:value)
        row={'ref':'Packed','id':3,'type':0x20C1,'dimensions':(4,0,0)}
        self.assertEqual(data_table.AddressSpace([(row,'<B')]).cells,())
        for dims in ((0,2,0),(2,-1,0),(True,0,0),(2,0),(2,2,0)):
            with self.subTest(dimensions=dims),self.assertRaises(ModelError):
                data_table.AddressSpace([({**row,'type':0x20C4,'dimensions':dims},'<i')])

    def test_array_reads_and_rejected_writes_preserve_all_modeled_state(self):
        self.bind(Symbol('',0,'Values',3));before=copy.deepcopy(self.app.state())
        path=bytes.fromhex('206a2403')
        self.assertEqual(self.cip(0x4F,path,struct.pack('<IH',0,20))[2],0)
        for service in (4,0x10,0x4D,0x53):self.assertNotEqual(self.cip(service,path,bytes(8))[2],0)
        after=self.app.state()
        for field in ('tags','scan','ms','controller','routines'):self.assertEqual(after[field],before[field])


if __name__=='__main__':unittest.main()
