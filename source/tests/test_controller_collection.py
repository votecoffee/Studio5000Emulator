"""Offline Controller upload framing preserves unknown fields and opaque values."""
import json
import struct
import unittest
from tools.collection_inventory import CollectionError,decode_attribute_list,instance_supported,scope_supported
from test_collection_inventory import reply


class ControllerCollectionTests(unittest.TestCase):
    def test_full_observed_profile_uses_exact_widths_without_interpreting_signatures_or_ccuids(self):
        widths={1:4,3:2,6:4,7:2,9:1,10:1,11:2,12:2,13:4,15:1,16:2,17:1,23:1,25:4,26:4,27:8,28:8,31:1,33:32,34:32,35:1}
        rows=[(n,0,bytes(range(size))) for n,size in widths.items()];raw=reply(rows)
        result=decode_attribute_list(raw,list(widths),0x8E)
        self.assertEqual([r['value_bytes'] for r in result['attributes']],list(widths.values()))
        self.assertNotIn('data_hex',json.dumps(result));self.assertEqual(result['value_semantics'],'NOT INFERRED')
        explicit=decode_attribute_list(raw,list(widths),0x8E,include_payloads=True)
        self.assertEqual(explicit['attributes'][-2]['data_hex'],bytes(range(32)).hex())
        for end in range(len(raw)):
            with self.subTest(end=end),self.assertRaises(CollectionError):decode_attribute_list(raw[:end],list(widths),0x8E)
        with self.assertRaises(CollectionError):decode_attribute_list(raw+b'\0',list(widths),0x8E)

    def test_partial_error_and_repeated_field_lists_do_not_hide_missing_suffixes(self):
        startup=decode_attribute_list(reply([(8,0,bytes(2)),(9,0,b'\0')]),[8,9],0x8E)
        self.assertEqual([r['value_bytes'] for r in startup['attributes']],[2,1])
        raw=reply([(35,0,b'\1'),(11,20,b''),(35,0,b'\1')],6)
        result=decode_attribute_list(raw,[35,11,35,33],0x8E)
        self.assertTrue(result['partial']);self.assertEqual(result['remaining_attributes'],[33])
        self.assertIsNone(result['attributes'][1]['value_sha256'])
        result=decode_attribute_list(reply([(10,0,b'\0'),(27,20,b'')],10),[10,27],0x8E)
        self.assertEqual([r['value_bytes'] for r in result['attributes']],[1,0])
        with self.assertRaises(CollectionError):decode_attribute_list(reply([(99,0,bytes(4))]),[99],0x8E)

    def test_instance_and_parent_profiles_do_not_imply_class_or_foreign_scope_support(self):
        self.assertTrue(instance_supported(0x8E,1))
        for value in (0,2,True,-1,0xffffffff):self.assertFalse(instance_supported(0x8E,value))
        self.assertTrue(scope_supported(0x8E))
        for parent in ('program_instance','aoi_instance','io_map_instance','controller_instance'):
            self.assertFalse(scope_supported(0x8E,**{parent:1}))


if __name__=='__main__':unittest.main()
