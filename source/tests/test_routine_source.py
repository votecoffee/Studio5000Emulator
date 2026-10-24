"""Synthetic native source blocks decode without resolving or applying IOIs."""
import hashlib
import struct
import unittest
import zlib
from xml.etree import ElementTree as ET

from logixlab.routine_source import decode,decode_download,SourceError,MAX_EXPANDED,MAX_AUXILIARY,aligned


def xml_source(name='MainRoutine',text='NOP();'):
    root=ET.Element('RSLogix5000Content',SchemaRevision='1.0',SoftwareRevision='35.03',TargetName=name,
        TargetType='RLLContent',TargetSubType='RLL',ContainsContext='false')
    content=ET.SubElement(root,'RLLContent',Use='Create',OnlineEditType='Original')
    ET.SubElement(ET.SubElement(content,'Rung',Type='N',RegionId='1'),'TextIOI').text=text
    return root


def container(xml=None,auxiliary=b'opaque-reference-data'):
    xml=ET.tostring(xml_source(),encoding='utf-8') if xml is None else xml
    compressed=zlib.compress(xml)
    source=struct.pack('<II',0x40000000|len(compressed),len(xml))+compressed
    source+=bytes(aligned(len(source))-len(source))
    aux=struct.pack('<II',1,len(auxiliary))+zlib.compress(auxiliary)
    size=28+len(source)+aligned(len(aux))
    return struct.pack('<8I',size,28,len(source),28+len(source),len(aux),0,size,0)+source+aux+bytes(aligned(len(aux))-len(aux))


class RoutineSourceTests(unittest.TestCase):
    def test_omitted_download_content_requires_explicit_empty_target_and_never_becomes_edit_source(self):
        root=xml_source();root.remove(root[0]);xml=ET.tostring(root);blob=container(xml)
        decoded=decode_download(blob,empty=True)
        self.assertEqual(decoded.rungs,());self.assertEqual(decoded.xml_sha256,hashlib.sha256(xml).hexdigest())
        self.assertEqual(decoded.description()['rungs'],0)
        for call in (decode,decode_download,lambda b:decode_download(b,empty=1)):
            with self.assertRaises(SourceError):call(blob)
        for kind in ('protected','text','child','empty-content'):
            changed=ET.fromstring(xml)
            if kind=='protected':changed.set('Protected','true')
            elif kind=='text':changed.text='hidden source'
            elif kind=='child':ET.SubElement(changed,'EncryptedContent')
            else:ET.SubElement(changed,'RLLContent',Use='Create',OnlineEditType='Original')
            with self.subTest(kind=kind),self.assertRaises(SourceError):decode_download(container(ET.tostring(changed)),empty=True)

    def test_decodes_bounded_source_and_auxiliary_but_retains_opaque_ioi_and_region_identity(self):
        root=xml_source(text='XIC(@107 3 0 0 0 0@)OTE(@107 4 0 0 0 0@);')
        xml=b'<?xml version="1.0" encoding="UTF-16"?>'+ET.tostring(root)
        result=decode(container(xml));state=result.description()
        self.assertEqual(result.name,'MainRoutine');self.assertEqual(result.rungs[0].region_id,1)
        self.assertIn('@107 3',result.rungs[0].text_ioi)
        self.assertEqual(state['ioi_operands'],2);self.assertEqual(state['rungs'],1)
        self.assertEqual(state['xml_sha256'],hashlib.sha256(xml).hexdigest())
        for field in ('operand_bindings_verified','auxiliary_semantics_verified','text_exposed','source_applied'):
            self.assertFalse(state[field])
        self.assertNotIn('XIC',str(state));self.assertNotIn('opaque-reference-data',str(state))

    def test_rejects_wrong_offsets_extents_padding_profile_and_expansion_limits(self):
        blob=container()
        for offset,value in ((0,len(blob)),(4,24),(8,4),(12,32),(16,8),(20,1),(24,0),(28,1),
                             (32,0),(36,MAX_EXPANDED+1)):
            bad=bytearray(blob);struct.pack_into('<I',bad,offset,value)
            with self.subTest(offset=offset),self.assertRaises(SourceError):decode(bytes(bad))
        aux_offset=4+struct.unpack_from('<I',blob,12)[0]
        for offset,value in ((aux_offset,2),(aux_offset+4,MAX_AUXILIARY+1),(aux_offset+4,1)):
            bad=bytearray(blob);struct.pack_into('<I',bad,offset,value)
            with self.assertRaises(SourceError):decode(bytes(bad))
        for bad in (blob[:-1],blob+b'\0',bytearray(blob),b''):
            with self.assertRaises(SourceError):decode(bad)

    def test_truncated_compression_trailing_streams_and_invalid_xml_remain_errors(self):
        from logixlab.routine_source import inflate
        for data,expected in ((zlib.compress(b'abc')[:-1],3),(zlib.compress(b'abc')+b'X',3),
                              (zlib.compress(b'abc')+zlib.compress(b'def'),3),(zlib.compress(b'abc'),2),
                              (zlib.compress(b'abc'),4),(b'no-zlib',3)):
            with self.assertRaises(SourceError):inflate(data,expected,10)
        for xml in (b'not-xml',b'\xff',b'<root>\0</root>',b'<!DOCTYPE root><root/>',
                    b'<!ENTITY injected "value"><root/>'):
            with self.assertRaises(SourceError):decode(container(xml))

    def test_protected_context_extra_nodes_wrong_types_and_duplicate_regions_are_rejected(self):
        for kind in ('name','version','context','protected','extra','edit-type','rung-type','duplicate','region','text-child','empty'):
            root=xml_source();content=root[0];rung=content[0]
            if kind=='name':root.set('TargetName','../other')
            elif kind=='version':root.set('SoftwareRevision','36.00')
            elif kind=='context':root.set('ContainsContext','true')
            elif kind=='protected':root.set('Protected','true')
            elif kind=='extra':ET.SubElement(root,'Extra')
            elif kind=='edit-type':content.set('OnlineEditType','Accepted')
            elif kind=='rung-type':rung.set('Type','I')
            elif kind=='duplicate':content.append(ET.fromstring(ET.tostring(rung)))
            elif kind=='region':rung.set('RegionId',str(1<<32))
            elif kind=='text-child':ET.SubElement(rung[0],'Hidden')
            else:rung[0].text=''
            with self.subTest(kind=kind),self.assertRaises(SourceError):decode(container(ET.tostring(root)))


if __name__=='__main__':unittest.main()
