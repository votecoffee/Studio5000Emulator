"""Packed BOOL table reads keep logical Symbol bits and storage words distinct."""
import copy
import struct
import unittest

import test_data_table as fixtures
from logixlab import data_table
from logixlab.model import ModelError
from logixlab.native_symbols import Symbol


class PackedBoolStorageTests(unittest.TestCase):
    setUp=fixtures.DataTableTests.setUp
    tearDown=fixtures.DataTableTests.tearDown
    add=fixtures.DataTableTests.add
    bind=fixtures.DataTableTests.bind
    cip=fixtures.DataTableTests.cip

    def bits(self,scope=''):
        values=[i in (0,7,15,31,32,47,63) for i in range(64)]
        tag=self.add('Bits',values,scope=scope);tag.dtype='BOOL'
        self.bind(Symbol(scope,17 if scope else 0,'Bits',3))
        return values

    def test_symbol_bits_and_table_words_link_to_the_same_exact_packed_bytes(self):
        self.bits();space=self.router.scalar_storage();cell=space.by_ref['bits']
        raw=struct.pack('<II',0x80008081,0x80008001)
        self.assertEqual((cell.dimensions,cell.storage_dimensions,cell.element_size,cell.size),((64,0,0),(2,0,0),4,8))
        for prefix,values in ((bytes.fromhex('206b2403'),{2:struct.pack('<H',0x20C1),8:struct.pack('<III',64,0,0),7:b'\4\0'}),
                              (bytes.fromhex('206a2403'),{2:struct.pack('<H',0x20D3),1:struct.pack('<III',2,0,0)})):
            for attribute,value in values.items():self.assertEqual(self.cip(14,prefix+bytes((0x30,attribute))),b'\x8e\0\0\0'+value)
        self.assertEqual(struct.unpack_from('<3IH',cell.header()),(2,0,0,0x20D3))
        self.assertEqual(struct.unpack_from('<HH',cell.symbol_header(),8),(0x20C1,4))
        self.assertEqual(struct.unpack_from('<3I',cell.symbol_header(),20),(64,0,0))
        self.assertEqual(space.read(cell.value_address,8,self.app.engine.memory.read),raw)
        self.assertEqual(self.cip(0x4F,bytes.fromhex('206a2403'),struct.pack('<IH',0,8)),b'\xcf\0\0\0'+raw)

    def test_current_bit_changes_update_both_words_without_reallocating_or_scanning(self):
        values=self.bits();space=self.router.scalar_storage();cell=space.by_ref['bits'];before=copy.deepcopy(self.app.state())
        for bit in (0,31,32,63):
            values[bit]=not values[bit];self.app.engine.memory.write(f'Bits[{bit}]',values[bit])
        raw=struct.pack('<II',0x00008080,0x00008000)
        self.assertIs(self.router.scalar_storage(),space)
        self.assertEqual(space.read(cell.value_address+3,2,self.app.engine.memory.read),raw[3:5])
        self.assertEqual(self.cip(0x4F,bytes.fromhex('206a2403'),struct.pack('<IH',0,8))[4:],raw)
        after=self.app.state()
        for field in ('scan','ms','controller','routines'):self.assertEqual(before[field],after[field])

    def test_scoped_storage_and_read_only_boundary_do_not_alias_or_accept_table_writes(self):
        self.bits('MainProgram');cell=self.router.scalar_storage().by_ref['program:mainprogram.bits']
        path=bytes.fromhex('20682411206a2403');before=copy.deepcopy(self.app.state())
        self.assertEqual(self.cip(0x4F,path,struct.pack('<IH',0,8))[4:],cell.value(self.app.engine.memory.read))
        self.assertEqual(self.cip(0x4F,bytes.fromhex('206a2403'),struct.pack('<IH',0,8))[2],5)
        for service in (4,0x10,0x4D,0x53,0x4E):self.assertNotEqual(self.cip(service,path,bytes(8))[2],0)
        for payload,status in ((struct.pack('<IH',0,64),3),(struct.pack('<IH',1,8),3),(struct.pack('<IH',0,7),3)):
            self.assertEqual(self.cip(0x4F,path,payload)[2],status)
        self.assertEqual(self.cip(0x4F,path,struct.pack('<IH',0,8),limit=11)[2],0x1B)
        for address,count in ((cell.value_address+7,2),(cell.value_address+8,1)):
            with self.assertRaises(ModelError):self.router.scalar_storage().read(address,count,self.app.engine.memory.read)
        after=self.app.state()
        for field in ('tags','scan','ms','controller','routines'):self.assertEqual(before[field],after[field])

    def test_incomplete_words_multidimensional_shapes_and_wrong_values_remain_unavailable(self):
        for bits,code,dimensions,fmt in ((31,0x20C1,(31,0,0),'<B'),(33,0x20C1,(33,0,0),'<B'),
                (64,0x40C1,(2,32,0),'<B'),(65568,0x20C1,(65568,0,0),'<B'),(64,0x20C1,(64,0,0),'<I')):
            with self.subTest(dimensions=dimensions,fmt=fmt):
                self.assertEqual(data_table.AddressSpace([({'ref':'Bits','id':3,'type':code,'dimensions':dimensions},fmt)]).cells,())
        self.bits();cell=self.router.scalar_storage().by_ref['bits']
        for invalid in ([False]*63,[False]*65,[0]*64,[[False]*32]*2,[False]*63+[None]):
            with self.subTest(value=repr(invalid)[:50]),self.assertRaises(ModelError):cell.value(lambda _:invalid)
        tag=self.app.engine.project.tags['bits'];tag.constant=True
        self.assertNotIn('bits',self.router.scalar_storage().by_ref)
        self.assertEqual(self.cip(14,bytes.fromhex('206b24033005'))[2],0x14)

    def test_complete_word_endpoints_are_bounded_without_rounding_or_padding(self):
        for bits in (32,65536):
            row={'ref':'Bits','id':3,'type':0x20C1,'dimensions':(bits,0,0)}
            cell=data_table.AddressSpace([(row,'<B')]).by_ref['bits']
            raw=cell.value(lambda _:[True]+[False]*(bits-2)+[True])
            self.assertEqual(cell.size,bits//8)
            self.assertEqual(raw[:4],struct.pack('<I',0x80000001 if bits==32 else 1))
            self.assertEqual(raw[-4:],struct.pack('<I',0x80000001 if bits==32 else 0x80000000))


if __name__=='__main__':unittest.main()
