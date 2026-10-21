"""Datatype IDs come from active source records and remain optional in old manifests."""
import copy
from dataclasses import replace
import json
import unittest
from logixlab.model import ModelError
from logixlab.native_types import NativeTypes,type_paths
from test_native_routines import record,database
from test_native_types import catalog,source_types,staged


def type_record(name='Example',instance=777,**kwargs):
    return record(name=name,version=177,logical=(0x6C,instance,0,0,0,0),**kwargs)


class NativeTypeIdTests(unittest.TestCase):
    def test_matching_original_ids_are_aggregate_identity_evidence_without_execution_authority(self):
        value=catalog(type_ids={'inner':0x101,'example':0x102}).verify(staged())
        self.assertEqual((value['status'],value['template_ids_matched'],value['template_ids_unresolved']),('matched',2,0))
        self.assertTrue(value['template_identities_verified'])
        for field in ('storage_mapping_supported','signature_verified','definitions_exposed','execution_supported'):
            self.assertFalse(value[field])
        for text in ('Inner','Example','257','258'):self.assertNotIn(text,json.dumps(value))

    def test_relocated_templates_and_matching_nested_references_cannot_substitute_original_ids(self):
        inner,outer=staged()
        rows=((0,0xC2,0),(1,0xC1,0xA0000002),(3,0x20C3,0xF0000004),(0,0x8301,12),(0,0xC1,16))
        remapped=(replace(inner,instance=0x301),replace(staged(rows)[1],instance=0x302))
        self.assertEqual(catalog().verify(remapped)['status'],'matched')
        result=catalog(type_ids={'inner':0x101,'example':0x102}).verify(remapped)
        self.assertEqual(result['status'],'mismatch');self.assertEqual(result['types_unavailable'],2)
        self.assertEqual(result['errors'],[dict(reason='source_template_identity_mismatch',types=2)])
        self.assertFalse(result['template_identities_verified']);self.assertEqual(result['template_ids_unresolved'],2)

    def test_old_or_partial_manifests_keep_layout_checks_without_claiming_complete_identities(self):
        for mapping,count in ((None,0),({},0),({'inner':0x101},1)):
            result=catalog(type_ids=mapping).verify(staged())
            self.assertEqual(result['status'],'matched');self.assertTrue(result['member_locations_verified'])
            self.assertEqual(result['template_ids_matched'],count);self.assertEqual(result['template_ids_unresolved'],2-count)
            self.assertFalse(result['template_identities_verified'])
        self.assertFalse(catalog(type_ids={'inner':0x101}).verify(())['template_identities_verified'])
        wrong=catalog(type_ids={'inner':0x301}).verify(staged())
        self.assertEqual(wrong['status'],'mismatch');self.assertEqual(wrong['types_matched'],1)

    def test_layout_errors_still_withhold_identity_flag_and_binding_stamp_covers_source_layout_and_ids(self):
        native=catalog(type_ids={'inner':0x101,'example':0x102});inner,outer=staged()
        result=native.verify((inner,replace(outer,attributes=replace(outer.attributes,structure_bytes=21))))
        self.assertEqual(result['template_ids_matched'],2);self.assertFalse(result['template_identities_verified'])
        original=native.binding_stamp()
        self.assertEqual(original,NativeTypes.from_manifest(native.manifest(),'b'*64).binding_stamp())
        native.type_ids['inner']=0x301;self.assertNotEqual(original,native.binding_stamp())
        native.type_ids['inner']=0x101;native.types['inner']=replace(native.types['inner'],size=8)
        self.assertNotEqual(original,native.binding_stamp())
        native.types['inner']=source_types()[0];native.source_acd_sha256='c'*64
        self.assertNotEqual(original,native.binding_stamp())

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
