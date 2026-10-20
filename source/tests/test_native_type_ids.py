"""Datatype IDs come from active source records and remain optional in old manifests."""
import copy
import unittest
from logixlab.model import ModelError
from logixlab.native_types import NativeTypes,type_paths
from test_native_routines import record,database
from test_native_types import catalog,source_types


def type_record(name='Example',instance=777,**kwargs):
    return record(name=name,version=177,logical=(0x6C,instance,0,0,0,0),**kwargs)


class NativeTypeIdTests(unittest.TestCase):
    def test_active_format177_records_bind_names_without_numbering_missing_or_other_records(self):
        self.assertEqual(type_paths(database(type_record(),type_record(name='Inner',instance=91)),{'example','inner'}),
                         {'example':777,'inner':91})
        self.assertEqual(type_paths(database(type_record(kind=0xFDFD),record(name='Example')),{'example'}),{})
        for data in (database(type_record(),type_record()),database(type_record(),type_record(name='Inner')),
                     database(type_record(instance=0)),b'bad'):
            with self.assertRaises(ModelError):type_paths(data,{'example','inner'})

    def test_optional_manifest_handles_round_trip_and_bad_or_ambiguous_maps_are_rejected(self):
        value=NativeTypes('a'*64,'b'*64,source_types(),{'example':777,'inner':91})
        manifest=value.manifest();loaded=NativeTypes.from_manifest(manifest,'b'*64)
        self.assertEqual(loaded.type_ids,value.type_ids);self.assertEqual(loaded.manifest(),manifest)
        old=copy.deepcopy(manifest);del old['type_ids'];self.assertEqual(NativeTypes.from_manifest(old,'b'*64).type_ids,{})
        for mapping in ([],{'missing':1},{'example':True},{'example':0},{'example':65536},
                        {'example':1,'inner':1}):
            with self.subTest(mapping=mapping),self.assertRaises(ModelError):NativeTypes.from_manifest({**manifest,'type_ids':mapping},'b'*64)


if __name__=='__main__':unittest.main()
