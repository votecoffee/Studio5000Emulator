"""Source locations, complete saved members and canonical reserved bytes."""
import copy
from dataclasses import replace
import struct
import unittest

from logixlab.download_image import ImageError,Region
from logixlab.download_values import encode_value,encode_initial,PreparedValues
from logixlab.native_types import NativeTypes,Type,Member
import test_download_values as values_tests


def member(name,dtype,offset,bit=None,dimensions=(),hidden=False):
    return Member(name,dtype,offset,bit,dimensions,'Read/Write',hidden)


def fixture():
    inner=Type('Reading',12,(member('Count','DINT',0),member('Packed','SINT',4,hidden=True),
        member('Ready','BOOL',4,2),member('Fault','BOOL',4,7),member('Samples','INT',6,dimensions=(3,))))
    outer=Type('Device',40,(member('Position','REAL',0),member('Current','Reading',4),
        member('History','Reading',16,dimensions=(2,))))
    types=NativeTypes('a'*64,'b'*64,[inner,outer],{'reading':0x101,'device':0x102})
    value=dict(Count=-123,Ready=True,Fault=False,Samples=[-32768,17,32767])
    raw=struct.pack('<iBB3h',-123,4,0,-32768,17,32767)
    return types,value,raw


class StructureTests(unittest.TestCase):
    def test_packed_bits_padding_and_nonzero_nested_member_array_values(self):
        types,value,raw=fixture();before=copy.deepcopy(value)
        self.assertEqual(encode_value('READING',value,types),(0x8101,raw))
        outer=dict(Position=-1.25,Current=value,History=[value,{**value,'Ready':False,'Fault':True}])
        expected=struct.pack('<f',-1.25)+raw+raw+struct.pack('<iBB3h',-123,128,0,-32768,17,32767)
        self.assertEqual(encode_value('DEVICE',outer,types),(0x8102,expected))
        self.assertEqual(value,before)

    def test_root_structure_arrays_use_explicit_size_stride_and_rank(self):
        types,value,raw=fixture()
        self.assertEqual(encode_initial('READING',[[value,value]],types),(0xC101,(1,2,0),2,raw*2))
        timer=dict(PRE=1000,ACC=-1,EN=False,TT=True,DN=False)
        self.assertEqual(encode_initial('TIMER',[timer,timer],values_tests.builtins()),
            (0xAF83,(2,0,0),2,struct.pack('<Iii',0x40000000,1000,-1)*2))

    def test_complete_fields_exact_member_shapes_and_strict_leaf_types_required(self):
        types,value,_=fixture()
        for changed in ({k:v for k,v in value.items() if k!='Ready'}, {**value,'Packed':0},
                {**value,'ready':value['Ready']}, {**value,'Ready':1}, {**value,'Count':True},
                {**value,'Count':2**31}, {**value,'Samples':[-32768,17]},
                {**value,'Samples':[[-32768,17,32767]]}, {**value,'Samples':[-32769,17,0]}):
            with self.subTest(keys=tuple(changed)),self.assertRaises(ImageError):
                encode_value('READING',changed,types)

    def test_ambiguous_overlaps_hidden_storage_and_type_identity_are_rejected(self):
        for change in ('overlap','bits','hidden','host','identity'):
            types,value,_=fixture();row=types.types['reading']
            if change=='overlap':row=replace(row,members=(*row.members[:-1],replace(row.members[-1],offset=4)))
            elif change=='bits':row=replace(row,members=(*row.members[:3],replace(row.members[3],bit=2),row.members[4]))
            elif change=='hidden':row=replace(row,members=(*row.members,member('Unknown','INT',6,hidden=True)))
            elif change=='host':row=replace(row,members=(row.members[0],replace(row.members[1],offset=5),*row.members[2:]))
            else:types.type_ids['reading']=0x1000
            types.types['reading']=row
            with self.subTest(change=change),self.assertRaises(ImageError):encode_value('READING',value,types)
        with self.assertRaises(ImageError):encode_value('READING',value,None)

    def test_cyclic_layout_cannot_recurse_or_invent_a_stride(self):
        types,_,_=fixture();types.types['reading']=Type('Reading',12,(member('Self','Reading',0),))
        value={};value['Self']=value
        with self.assertRaises(ImageError):encode_value('READING',value,types)

    def test_preparation_requires_all_bytes_including_padding_and_unused_bits(self):
        types,value,raw=fixture();headers,project=values_tests.ValueTests().fixture()
        project.tags['x'].dtype='READING';project.initial['x']=value
        region=Region(1,0x8101,(0,0,0),1,raw);headers.namespace._image._regions[1]=region
        plan=PreparedValues.prepare(headers,types)
        self.assertEqual(plan.values,(('x',1,0x8101,raw),))
        self.assertTrue(plan.description()['source_structures'])
        for index,mask in ((0,1),(4,1),(5,1),(6,1)):
            bad=bytearray(raw);bad[index]^=mask
            headers.namespace._incremental._tables[1]=replace(region,data=bytes(bad))
            with self.subTest(index=index),self.assertRaises(ImageError):PreparedValues.prepare(headers,types)
        headers.namespace._incremental._tables.clear();project.initial['x']['Ready']=False
        with self.assertRaises(ImageError):plan.validate(headers,types)


if __name__=='__main__':unittest.main()
