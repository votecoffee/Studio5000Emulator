"""Data Table and symbolic UDT reads share model layouts and current values."""
import copy
import struct
import unittest
from unittest.mock import patch

from logixlab import data_table
from logixlab.model import ModelError,Tag
from logixlab.native_symbols import NativeSymbols,Symbol
import test_structure_reads as fixtures

machine=fixtures.machine


class StructureStorageTests(unittest.TestCase):
    setUp=fixtures.StructureReadTests.setUp
    tearDown=fixtures.StructureReadTests.tearDown
    cip=fixtures.StructureReadTests.cip
    read=fixtures.StructureReadTests.read
    all_data=fixtures.StructureReadTests.all_data
    add_type=fixtures.StructureReadTests.add_type

    def bind(self,*symbols):
        self.app.native_symbols=NativeSymbols('1'*64,self.app.engine.project.sha256,symbols)

    def table(self,instance,count,limit=2048,prefix=b''):
        return self.cip(0x4F,prefix+bytes((0x20,0x6A,0x24,instance)),struct.pack('<IH',0,count),limit)

    def test_scalar_structures_share_symbolic_bytes_nested_members_and_descriptor_widths(self):
        self.bind(Symbol('',0,'Machine',3))
        space=self.router.scalar_storage();cell=space.by_ref['machine']
        self.assertEqual((cell.element_size,cell.size),(536,536))
        self.assertGreaterEqual(cell.value_address,data_table.ARRAY_VALUE_BASE)
        self.assertEqual(self.table(3,536),b'\xCF\0\0\0'+machine(10))
        self.assertEqual(self.table(3,536)[4:],self.all_data('Machine'))
        self.assertEqual(space.read(cell.value_address+4,4,self.app.engine.memory.read),struct.pack('<f',10.5))
        self.assertEqual(self.cip(14,bytes.fromhex('206b24033007'))[4:],struct.pack('<H',536))
        self.assertEqual(self.cip(14,bytes.fromhex('206b24033003'))[4:],
                         self.cip(14,bytes.fromhex('206a24033007'))[4:])
        self.app.engine.memory.write('Machine.History[11].Command',987)
        self.assertIs(self.router.scalar_storage(),space)
        self.assertEqual(self.table(3,536)[4:],self.all_data('Machine'))
        self.assertEqual(struct.unpack_from('<i',self.table(3,536),4+40+11*40)[0],987)

    def test_structure_arrays_keep_element_width_and_multidimensional_row_order(self):
        value=copy.deepcopy(self.app.engine.memory.values['machines'][0])
        grid=[[copy.deepcopy(value) for _ in range(2)] for _ in range(2)]
        for i in range(2):
            for j in range(2):grid[i][j]['Axis']['Command']=10*i+j
        self.app.engine.project.tags['grid']=Tag('Grid','MachineState',grid)
        self.app.engine.memory.values['grid']=grid
        self.bind(Symbol('',0,'Machines',3),Symbol('',0,'Grid',4))
        cell=self.router.scalar_storage().by_ref['machines']
        self.assertEqual((cell.element_size,cell.size),(536,1072))
        self.assertEqual(self.table(3,1072)[4:],machine(0)+machine(100))
        raw=self.table(4,2144,limit=2148)
        self.assertEqual(raw[2],0)
        self.assertEqual([struct.unpack_from('<i',raw,4+i*536)[0] for i in range(4)],[0,1,10,11])
        self.assertEqual(self.table(3,1072,limit=1075)[2],0x1B)
        self.assertEqual(self.table(3,536)[2],3)

    def test_packed_flags_and_reserved_padding_match_existing_symbolic_encoding(self):
        self.add_type('Flags','''<Member Name="ZZZZZZZZZZHost" DataType="SINT" Hidden="true"/>
            <Member Name="Ready" DataType="BIT" Target="ZZZZZZZZZZHost" BitNumber="0"/>
            <Member Name="Fault" DataType="BIT" Target="ZZZZZZZZZZHost" BitNumber="7"/>
            <Member Name="Value" DataType="INT"/>''',{'Ready':True,'Fault':True,'Value':-123})
        self.bind(Symbol('',0,'Extra',3))
        self.assertEqual(self.table(3,4),b'\xCF\0\0\0\x81\0'+struct.pack('<h',-123))
        self.assertEqual(self.table(3,4)[4:],self.all_data('Extra'))
        self.app.engine.memory.write('Extra.Fault',False)
        self.assertEqual(self.table(3,4)[4],1)

    def test_program_and_controller_structures_with_equal_ids_have_independent_storage(self):
        value=copy.deepcopy(self.app.engine.memory.values['machine'])
        value['Axis']['Command']=42
        tag=Tag('Local','MachineState',value,scope='MainProgram',external_access='Read Only')
        self.app.engine.project.tags[tag.key.lower()]=tag;self.app.engine.memory.values[tag.key.lower()]=value
        self.bind(Symbol('',0,'Machine',3),Symbol('MainProgram',17,'Local',3))
        space=self.router.scalar_storage()
        self.assertNotEqual(space.by_ref['machine'].value_address,space.by_ref['program:mainprogram.local'].value_address)
        self.assertEqual(struct.unpack_from('<i',self.table(3,536,prefix=bytes.fromhex('20682411')),4)[0],42)
        self.assertEqual(struct.unpack_from('<i',self.table(3,536),4)[0],10)

    def test_each_network_member_read_rechecks_access_even_after_catalog_was_cached(self):
        self.bind(Symbol('',0,'Machine',3));self.assertEqual(self.table(3,536)[2],0)
        axis=self.app.engine.project.udts['axisstate']
        axis.find('./Members/Member[@Name="Command"]').set('ExternalAccess','None')
        before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.table(3,536)[2],0x0F)
        self.assertEqual(self.app.engine.memory.values,before)
        self.router._catalog=None
        self.assertNotIn('machine',self.router.scalar_storage().by_ref)

    def test_unknown_values_invalid_shapes_and_writes_do_not_return_partial_structure_bytes(self):
        self.bind(Symbol('',0,'Machine',3),Symbol('',0,'Machines',4))
        before=copy.deepcopy(self.app.engine.memory.values)
        self.app.engine.memory.values['machine']['History'][11]['Samples'][7]=None
        self.assertEqual(self.table(3,536)[2],0x0C)
        self.app.engine.memory.values=copy.deepcopy(before)
        self.app.engine.memory.values['machines'][1]=None
        self.assertEqual(self.table(4,1072)[2],0x0C)
        self.app.engine.memory.values=copy.deepcopy(before)
        for service in (4,0x10,0x4D,0x53):
            self.assertNotEqual(self.cip(service,bytes.fromhex('206a2403'),bytes(8))[2],0)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_aggregate_allocations_share_bounds_and_never_expose_neighbor_padding(self):
        self.bind(Symbol('',0,'Machine',3))
        space=self.router.scalar_storage();cell=space.by_ref['machine']
        for address,count in ((cell.value_address+535,2),(cell.value_address+536,1),
                              (data_table.VALUE_BASE+cell.slot*8,1)):
            with self.subTest(address=address),self.assertRaises(ModelError):
                space.read(address,count,self.app.engine.memory.read)
        row=({'ref':'Machine','id':3,'type':cell.code,'dimensions':(0,0,0)},cell.fmt)
        for bound in ('MAX_ARRAY_BYTES','MAX_ARRAY_STORAGE_BYTES'):
            with patch.object(data_table,bound,535):self.assertEqual(data_table.AddressSpace([row]).cells,())

    def test_constants_aliases_and_builtins_keep_storage_unavailable(self):
        self.app.engine.project.tags['machine'].constant=True
        alias=Tag('Alias','',None,alias='Machines[0]')
        self.app.engine.project.tags['alias']=alias
        builtin=Tag('Text','STRING',{'LEN':0,'DATA':[0]*82})
        self.app.engine.project.tags['text']=builtin;self.app.engine.memory.values['text']=builtin.value
        self.bind(Symbol('',0,'Machine',3),Symbol('',0,'Alias',4),Symbol('',0,'Text',5))
        self.assertEqual(self.router.scalar_storage().cells,())
        self.assertEqual(self.table(3,536)[2],8)
        self.assertEqual(self.table(4,536)[2],5)
        self.assertEqual(self.table(5,88)[2],5)


if __name__=='__main__':unittest.main()
