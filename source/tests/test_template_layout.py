"""Synthetic member definitions, not copied vendor definitions or CRC vectors."""
from dataclasses import FrozenInstanceError
import json
import struct
import unittest
from unittest.mock import patch

from logixlab import template_layout as tl, template_staging as ts
from test_template_staging import batch, attrs, request


def definition(rows=((0, 0xC4, 0),), names=(b'Value',), header=b'Example;n', trailer=b''):
    return b''.join(struct.pack('<HHI', *row) for row in rows) + header + b'\0' + b'\0'.join(names) + b'\0' + trailer


def template(raw=None, count=1, instance=1):
    raw = definition() if raw is None else raw
    return ts.Template(instance, (len(raw)+23)//4, ts.Attributes(1, count, 4, 0, 0), raw)


class TemplateLayoutTests(unittest.TestCase):
    def test_atomic_array_bool_and_nested_entries_preserve_exact_words_and_order(self):
        rows=((0,0xC2,0),(7,0xC1,0),(12,0x20C3,4),(0,0x8123,28))
        raw=definition(rows,(b'Host',b'Enabled',b'Counts',b'Nested'),trailer=b'\x01\x02\x03')
        value=tl.decode(raw,4)
        self.assertEqual(value.name,'Example');self.assertEqual(value.trailer_bytes,3)
        self.assertEqual([(m.info,m.type_word,m.offset_word) for m in value.members],list(rows))
        self.assertEqual([m.name for m in value.members],['Host','Enabled','Counts','Nested'])
        with self.assertRaises(FrozenInstanceError):value.members[0].offset_word=1

    def test_encoded_offsets_and_opaque_header_and_trailer_have_no_inferred_semantics(self):
        raw=definition(((2,0xC1,0xF0000000),),header=b'Example;'+b'x'*3000,trailer=b'PrivateTrailer\0\xFF')
        result=tl.Inspection((template(raw),)).description()
        self.assertEqual(result['encoded_offset_members'],1);self.assertEqual(result['opaque_trailer_bytes'],16)
        self.assertEqual(result['status'],'decoded')
        for flag in ('storage_mapping_supported','signature_verified','definitions_exposed','execution_supported'):
            self.assertIs(result[flag],False)
        for text in ('Example','PrivateTrailer',raw.hex(),'4026531840'):self.assertNotIn(text,json.dumps(result))

    def test_missing_names_do_not_consume_unbounded_data_or_accept_truncated_entries(self):
        cases=(b'\0'*8,b'\0'*8+b'Example',b'\0'*8+b'Example\0',
               b'\0'*8+b'Example\0'+b'A'*255+b'\0',definition()[:7])
        for raw in cases:
            with self.subTest(raw=raw),self.assertRaises(tl.LayoutError):tl.decode(raw,1)

    def test_name_rules_duplicate_names_and_count_are_checked(self):
        for name in (b'',b'bad.name',b'9Name',b'A\xff',b'A'*255):
            with self.subTest(name=name),self.assertRaises(tl.LayoutError):tl.decode(definition(names=(name,)),1)
        for header in (b'',b';n',b'Invalid.Name;n',b'A'*255+b';n'):
            with self.subTest(header=header),self.assertRaises(tl.LayoutError):tl.decode(definition(header=header),1)
        with self.assertRaises(tl.LayoutError):tl.decode(definition(((0,0xC4,0),(0,0xC4,4)),(b'Value',b'value')),2)
        for count in (0,True,-1,tl.MAX_MEMBERS+1,None):
            with self.assertRaises(tl.LayoutError):tl.decode(definition(),count)

    def test_limits_before_parsing_and_exact_name_boundary(self):
        for raw in (None,bytearray(definition()),b'',b'A'*(tl.MAX_DEFINITION_BYTES+1)):
            with self.assertRaises(tl.LayoutError):tl.decode(raw,1)
        self.assertEqual(len(tl.decode(definition(names=(b'A'*254,)),1).members[0].name),254)
        with patch.object(tl,'MAX_TEMPLATES',1),self.assertRaises(tl.LayoutError):
            tl.Inspection((template(),template(instance=2)))

    def test_all_member_rows_and_names_can_reach_the_count_limit(self):
        count=tl.MAX_MEMBERS
        raw=definition(((0,0xC4,i*4) for i in range(count)),tuple(f'M{i}'.encode() for i in range(count)))
        value=tl.decode(raw,count)
        self.assertEqual(len(value.members),count);self.assertEqual(value.members[-1].name,'M4095')

    def test_partial_inspection_keeps_only_whole_definitions_and_fixed_errors(self):
        broken=template(definition(names=(b'Bad.Name',)),instance=2)
        stage=tl.Inspection((template(),broken,template(b'\0',instance=3)))
        result=stage.description()
        self.assertEqual(result['status'],'partial');self.assertEqual(result['templates_decoded'],1)
        self.assertEqual(result['templates_unavailable'],2);self.assertEqual(result['members_decoded'],1)
        self.assertEqual(result['errors'],[{'reason':'invalid_member_name','templates':1},
                                           {'reason':'truncated_member_entries','templates':1}])
        self.assertEqual(len(stage.definitions),1)
        result['errors'][0]['reason']='changed';self.assertNotEqual(stage.description()['errors'][0]['reason'],'changed')
        self.assertEqual(tl.Inspection((broken,)).description()['status'],'invalid')
        self.assertEqual(tl.Inspection().description()['status'],'idle')

    def test_staging_inspects_assembled_bytes_and_cleanup_replaces_summary(self):
        raw=definition(trailer=b'opaque');raw+=b'\0'*(-len(raw)%4)
        stage=ts.TemplateStaging.from_batch(batch(data=raw))
        result=stage.description()['layout_inspection']
        self.assertEqual(result['templates_decoded'],1);self.assertEqual(result['members_decoded'],1)
        self.assertEqual(result['status'],'decoded')
        # Opaque staging remains supported, without treating arbitrary bytes as
        # a valid layout or granting permission to execute the device batch.
        self.assertEqual(ts.TemplateStaging.from_batch(batch()).description()['layout_inspection']['status'],'invalid')
        self.assertEqual(ts.TemplateStaging().description()['layout_inspection']['status'],'idle')


if __name__=='__main__':unittest.main()
