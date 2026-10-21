"""Metadata comparisons omit native identities and retain missing-field doubt."""
import json
import struct
import unittest

from tools.routine_metadata_profile import describe,BULK_ATTRIBUTES
from tools.collection_inventory import CollectionError
from tools.analyze_native_transfer import analyze
from tools.inspect_cip_capture import summarize
from tools.upload_inventory import logical_path
from test_collection_inventory import reply
from test_native_transfer_trace import event
from test_capture_inspection import packet


def values(instance=700,header=0x10000000,blob=bytes(range(64))):
    return {1:bytes.fromhex('ff07'),2:bytes(4),8:struct.pack('<I',header),9:struct.pack('<I',instance),
            **{number:bytes(4) for number in range(10,22)},22:b'\x42\0\0\x08'+blob,
            23:b'\0',24:bytes(4),26:b'\0',27:b'\0',28:bytes(4)}


def response(overrides=None):
    fields=values();fields.update(overrides or {})
    return reply([(number,0,fields[number]) for number in BULK_ATTRIBUTES])


class RoutineMetadataProfileTests(unittest.TestCase):
    def test_complete_null_code_profile_and_identity_comparison_retain_explicit_limits(self):
        state=describe(response(),BULK_ATTRIBUTES,700)
        self.assertTrue(state['complete']);self.assertTrue(state['code_address_zero'])
        self.assertTrue(state['header_reference_nonzero']);self.assertTrue(state['executable_instance_matches_path'])
        self.assertTrue(state['all_edit_buffer_fields_zero']);self.assertEqual(state['zero_edit_buffer_fields'],12)
        self.assertEqual(state['source_key_bytes'],66);self.assertTrue(state['source_key_observed_format'])
        self.assertEqual(state['failed_attributes'],[]);self.assertEqual(state['unreturned_attributes'],[])
        for key in ('source_binding_verified','mac_verified','native_acceptance_verified','payloads_exposed'):
            self.assertIs(state[key],False)
        for text in (bytes(range(64)).hex(),'data_hex','268435456','header_address','00000010'):
            self.assertNotIn(text,json.dumps(state))

    def test_fingerprint_ignores_only_opaque_object_identity_but_keeps_state_type_and_flags(self):
        baseline=describe(response(),BULK_ATTRIBUTES,700)
        changed=response({8:struct.pack('<I',0x70000000),9:struct.pack('<I',90000),22:b'\x42\0\0\x08'+b'z'*64})
        other=describe(changed,BULK_ATTRIBUTES,90000)
        self.assertEqual(baseline['nonidentity_fields_sha256'],other['nonidentity_fields_sha256'])
        self.assertTrue(other['executable_instance_matches_path'])
        for field,data in ((1,bytes.fromhex('fc07')),(2,struct.pack('<I',7)),(24,struct.pack('<I',2)),
                           (10,struct.pack('<I',4)),(23,b'\1'),(28,struct.pack('<I',1))):
            with self.subTest(field=field):
                self.assertNotEqual(baseline['nonidentity_fields_sha256'],describe(response({field:data}),BULK_ATTRIBUTES,700)['nonidentity_fields_sha256'])

    def test_mismatches_are_byte_facts_without_inferred_client_failure(self):
        state=describe(response({2:b'\1\0\0\0',8:bytes(4),9:struct.pack('<I',701),12:b'\1\0\0\0'}),BULK_ATTRIBUTES,700)
        self.assertFalse(state['code_address_zero']);self.assertFalse(state['header_reference_nonzero'])
        self.assertFalse(state['executable_instance_matches_path']);self.assertFalse(state['all_edit_buffer_fields_zero'])
        self.assertEqual(state['zero_edit_buffer_fields'],11);self.assertFalse(state['native_acceptance_verified'])

    def test_partial_and_failed_fields_stay_unknown_and_never_produce_complete_fingerprint(self):
        fields=values();raw=reply([(n,0,fields[n]) for n in BULK_ATTRIBUTES[:3]],6)
        state=describe(raw,BULK_ATTRIBUTES,700)
        self.assertFalse(state['complete']);self.assertIsNone(state['nonidentity_fields_sha256'])
        self.assertEqual(state['unreturned_attributes'],list(BULK_ATTRIBUTES[3:]))
        for key in ('executable_instance_matches_path','all_edit_buffer_fields_zero','source_key_observed_format','source_key_bytes'):
            self.assertIsNone(state[key])
        rows=[(n,0x14,b'') if n in (2,8,9,22) else (n,0,fields[n]) for n in BULK_ATTRIBUTES]
        state=describe(reply(rows,0x0a),BULK_ATTRIBUTES,700)
        self.assertEqual(state['failed_attributes'],[2,8,9,22]);self.assertFalse(state['complete'])
        for key in ('code_address_zero','header_reference_nonzero','executable_instance_matches_path','source_key_observed_format'):
            self.assertIsNone(state[key])

    def test_unknown_source_key_profile_is_reported_without_exposing_or_accepting_content(self):
        for key in (b'\0\0',b'\x42\0\x01\x08'+b'z'*64,b'\x02\0xx'):
            state=describe(response({22:key}),BULK_ATTRIBUTES,700)
            self.assertTrue(state['complete']);self.assertFalse(state['source_key_observed_format'])
            self.assertFalse(state['native_acceptance_verified']);self.assertNotIn('7a7a7a',json.dumps(state))

    def test_malformed_frames_and_ambiguous_request_context_are_rejected(self):
        raw=response()
        for size in range(len(raw)):
            with self.assertRaises(CollectionError):describe(raw[:size],BULK_ATTRIBUTES,700)
        for attrs in (None,[],(1,),BULK_ATTRIBUTES[::-1],(*BULK_ATTRIBUTES,1)):
            with self.assertRaises(CollectionError):describe(raw,attrs,700)
        for instance in (None,True,0,-1,1<<32,'700'):
            with self.assertRaises(CollectionError):describe(raw,BULK_ATTRIBUTES,instance)
        with self.assertRaises(CollectionError):describe(raw+b'\0',BULK_ATTRIBUTES,700)

    def test_capture_and_checkpoint_readers_share_profile_for_program_and_aoi_scopes(self):
        for parent in ({'program':300},{'aoi':300}):
            path=logical_path(0x6d,700,**parent);q=bytes((3,len(path)//2))+path+struct.pack('<23H',22,*BULK_ATTRIBUTES);a=response()
            captured=summarize([packet(1,q),packet(2,a,1)])['exchanges'][0]['response']['routine_bulk_profile']
            checkpoint=analyze({'events':[]},{'events':[event(q,a)]},'upload')
            trace=checkpoint['collection_attribute_lists'][0]['routine_bulk_profile']
            self.assertEqual(captured,trace);self.assertEqual(trace,describe(a,BULK_ATTRIBUTES,700))
            self.assertNotIn('data_hex',json.dumps(checkpoint));self.assertEqual(checkpoint['failure_cause'],'NOT INFERRED')
        for path in (logical_path(0x6d,700),logical_path(0x6d,0),logical_path(0x6d,700,program=300)+b'\x30\x01'):
            q=bytes((3,len(path)//2))+path+struct.pack('<23H',22,*BULK_ATTRIBUTES)
            self.assertNotIn('routine_bulk_profile',json.dumps(analyze({'events':[]},{'events':[event(q,response())]},'upload')))


if __name__=='__main__':unittest.main()
