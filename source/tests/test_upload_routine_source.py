"""Upload inspection retains class/edit identity and cannot become an import."""
from dataclasses import FrozenInstanceError
import hashlib
import struct
import unittest
import zlib
from xml.etree import ElementTree as ET

from logixlab import read_transport as rt,routine_source as edits,upload_routine_source as upload
from tools.upload_inventory import logical_path
from test_routine_source import container,xml_source


def source_blob(target_class='Standard',edit_type='Original',rows=None):
    root=xml_source(name='PrivateRoutine',text='XIC(@107 3 0 0 0 0@)OTE(@107 4 0 0 0 0@);')
    root.set('TargetClass',target_class);root[0].set('OnlineEditType',edit_type)
    if rows is not None:
        for child in list(root[0]):root[0].remove(child)
        for region,kind,text in rows:
            ET.SubElement(ET.SubElement(root[0],'Rung',Type=kind,RegionId=str(region)),'TextIOI').text=text
    xml=b'<?xml version="1.0" encoding="UTF-16"?>'+ET.tostring(root,encoding='utf-8')
    return container(xml),xml


def initial_request(*,program=300,aoi=None,selector=3,service=0x5D,path=None):
    if path is None:path=logical_path(0x6D,700,program=program,aoi=aoi)
    return bytes((service,len(path)//2))+path+struct.pack('<II',1,selector)


def assembled(blob,inner=None,split=None):
    value=rt.Assembly();q=rt.ReadRequest(1,0x101,0,initial_request() if inner is None else inner)
    if split is None:value.accept(q,rt.ReadChunk(1,0x301,len(blob),blob))
    else:
        value.accept(q,rt.ReadChunk(1,0x101,len(blob),blob[:split]))
        value.accept(rt.ReadRequest(2,1,split),rt.ReadChunk(2,0x201,split,blob[split:]))
    return value


class UploadRoutineSourceTests(unittest.TestCase):
    def test_download_conversion_adds_only_target_class_and_retains_auxiliary_block(self):
        xml=b'<?xml version="1.0" encoding="UTF-16"?>'+ET.tostring(xml_source(),encoding='utf-8')
        xml=xml.replace(b'<TextIOI>NOP();</TextIOI>',b'<TextIOI><![CDATA[\nNOP();\n]]></TextIOI>')
        original=container(xml);saved=bytes(original)
        converted=upload.from_download(original,target_class='Standard');result=upload.decode(converted)
        converted_xml,_=edits._container(converted)
        self.assertEqual(converted_xml.replace(b' TargetClass="Standard"',b'',1),xml)
        old_aux=edits.source_header(original,len(original))[1];new_aux=edits.source_header(converted,len(converted))[1]
        self.assertEqual(converted[new_aux:],original[old_aux:])
        self.assertEqual(result.records[0].text_ioi,'\nNOP();\n');self.assertEqual(original,saved)
        with self.assertRaises(edits.SourceError):edits.decode(converted)

    def test_conversion_rejects_unknown_classes_empty_or_protected_source_and_upload_input(self):
        for target_class in ('Safety','standard','',None):
            with self.subTest(target_class=target_class),self.assertRaisesRegex(upload.Error,'class_unsupported'):
                upload.from_download(container(),target_class=target_class)
        root=xml_source();root.remove(root[0])
        for blob in (container(ET.tostring(root)),source_blob()[0],container(b'not XML')):
            with self.assertRaises(upload.Error):upload.from_download(blob,target_class='Standard')
        root=xml_source();root.set('Protected','true')
        with self.assertRaises(upload.Error):upload.from_download(container(ET.tostring(root)),target_class='Standard')

    def test_source_records_preserve_ioi_regions_and_hashes_without_exposing_text(self):
        blob,xml=source_blob();value=upload.decode(blob);state=value.description()
        self.assertEqual(value.name,'PrivateRoutine');self.assertEqual(value.records[0].region_id,1)
        self.assertEqual(value.records[0].kind,'N');self.assertIn('@107 3',value.records[0].text_ioi)
        self.assertEqual(state['profile'],'upload-rll-v35');self.assertEqual(state['ioi_operands'],2)
        self.assertEqual(state['container_sha256'],hashlib.sha256(blob).hexdigest())
        self.assertEqual(state['xml_sha256'],hashlib.sha256(xml).hexdigest())
        self.assertEqual(state['auxiliary_sha256'],hashlib.sha256(b'opaque-reference-data').hexdigest())
        for label in ('PrivateRoutine','@107','XIC','opaque-reference-data'):
            self.assertNotIn(label,str(state));self.assertNotIn(label,repr(value));self.assertNotIn(label,repr(value.records[0]))
        for key in ('operand_bindings_verified','auxiliary_semantics_verified','active_rungs_selected','execution_verified','text_exposed','source_applied'):
            self.assertIs(state[key],False)
        with self.assertRaises(FrozenInstanceError):value.target_class='Standard'
        with self.assertRaises(FrozenInstanceError):value.records[0].kind='IR'

    def test_standard_safety_and_test_edits_have_distinct_profiles(self):
        for target_class,edit_type in sorted(upload.PROFILES):
            with self.subTest(target_class=target_class,edit_type=edit_type):
                value=upload.decode(source_blob(target_class,edit_type)[0])
                self.assertEqual((value.target_class,value.edit_type),(target_class,edit_type))
                self.assertFalse(hasattr(value,'rungs'))
                with self.assertRaisesRegex(edits.SourceError,'edit_profile_required'):
                    edits.resolve(value,None,None,None,None,None)
                with self.assertRaisesRegex(edits.SourceError,'edit_profile_required'):
                    edits.candidate_project(value,(),None,None)
                with self.assertRaisesRegex(edits.SourceError,'edit_profile_required'):
                    edits.validate_plan(value,(),None,None)

    def test_original_edit_decoder_stays_strict_and_rejects_upload_profiles(self):
        for target_class,edit_type in upload.PROFILES:
            with self.assertRaisesRegex(edits.SourceError,'xml_profile'):
                edits.decode(source_blob(target_class,edit_type)[0])
        self.assertEqual(edits.decode(container()).rungs[0].text_ioi,'NOP();')
        with self.assertRaisesRegex(upload.Error,'class_edit_profile'):
            upload.decode(container())

    def test_test_edit_ir_r_pairs_keep_both_texts_and_input_order(self):
        rows=[(9,'N',' NOP(); '),(23,'IR','MOV(2,@107 3 0 0 0 0@);'),(23,'R','MOV(1,@107 3 0 0 0 0@);'),(24,'N','NOP();')]
        value=upload.decode(source_blob(edit_type='TestEdits',rows=rows)[0])
        self.assertEqual([(row.region_id,row.kind,row.text_ioi) for row in value.records],rows)
        self.assertEqual(value.description()['paired_regions'],1)
        self.assertEqual(value.description()['rung_kinds'],{'IR':1,'N':2,'R':1})
        self.assertFalse(value.description()['active_rungs_selected'])

    def test_nonobserved_pairs_duplicates_and_rung_kinds_are_rejected(self):
        for rows in ([(1,'IR','NOP();')],[(1,'R','NOP();')],[(1,'IR','NOP();'),(2,'R','NOP();')],
                     [(1,'N','NOP();'),(1,'N','NOP();')],[(1,'IR','NOP();'),(1,'R','NOP();'),(1,'R','NOP();')],
                     [(1,'IR','NOP();'),(2,'N','NOP();'),(1,'R','NOP();')],[(1,'I','NOP();')],[(1,'D','NOP();')]):
            with self.subTest(rows=rows),self.assertRaises(upload.Error):
                upload.decode(source_blob(edit_type='TestEdits',rows=rows)[0])
        for target_class in ('Standard','Safety'):
            with self.assertRaises(upload.Error):
                upload.decode(source_blob(target_class,rows=[(1,'IR','NOP();'),(1,'R','NOP();')])[0])

    def test_only_observed_class_edit_combinations_are_accepted(self):
        for target_class,edit_type in (('Safety','TestEdits'),('Motion','Original'),('Standard','Accepted'),
                                       ('standard','Original'),('Standard','original'),('','Original')):
            with self.subTest(target_class=target_class,edit_type=edit_type),self.assertRaisesRegex(upload.Error,'class_edit_profile'):
                upload.decode(source_blob(target_class,edit_type)[0])

    def test_unknown_attributes_context_protection_nodes_and_revision_are_rejected(self):
        for kind in ('name','version','schema','context','protected','extra-root','root-text','content-text',
                     'content-use','extra-rung','text-child','text-attribute','extra-attribute','comment','pi','region','empty'):
            root=ET.fromstring(source_blob()[1].decode());rung=root[0][0]
            if kind=='name':root.set('TargetName','../other')
            elif kind=='version':root.set('SoftwareRevision','36.00')
            elif kind=='schema':root.set('SchemaRevision','2.0')
            elif kind=='context':root.set('ContainsContext','true')
            elif kind=='protected':root.set('Protected','true')
            elif kind=='extra-root':ET.SubElement(root,'Extra')
            elif kind=='root-text':root.text='not whitespace'
            elif kind=='content-text':root[0].text='not whitespace'
            elif kind=='content-use':root[0].set('Use','Context')
            elif kind=='extra-rung':ET.SubElement(rung,'Extra')
            elif kind=='text-child':ET.SubElement(rung[0],'Hidden')
            elif kind=='text-attribute':rung[0].set('Protected','true')
            elif kind=='extra-attribute':rung.set('Number','1')
            elif kind=='comment':root[0].append(ET.Comment('unsupported'))
            elif kind=='pi':root[0].append(ET.ProcessingInstruction('other','unsupported'))
            elif kind=='region':rung.set('RegionId',str(1<<32))
            else:root[0].remove(rung)
            with self.subTest(kind=kind),self.assertRaises(upload.Error):upload.decode(container(ET.tostring(root)))

    def test_invalid_xml_encoding_declarations_and_extra_text_are_errors(self):
        for xml in (b'not XML',b'\xff',b'<root>\0</root>',b'<!DOCTYPE root><root/>',b'<!ENTITY injected "v"><root/>'):
            with self.subTest(xml=xml),self.assertRaises(upload.Error):upload.decode(container(xml))
        for label in ('rung','tail','text-tail'):
            root=ET.fromstring(source_blob()[1].decode());rung=root[0][0]
            if label=='rung':rung.text='unexpected'
            elif label=='tail':rung.tail='unexpected'
            else:rung[0].tail='unexpected'
            with self.assertRaisesRegex(upload.Error,'extra_text'):upload.decode(container(ET.tostring(root)))

    def test_rung_regions_count_and_text_have_explicit_limits(self):
        for region in (0,-1,1<<32,'01','1.0'):
            with self.subTest(region=region),self.assertRaises(upload.Error):
                upload.decode(source_blob(rows=[(region,'N','NOP();')])[0])
        for text in ('','  ', 'a'*(edits.MAX_RUNG_TEXT+1)):
            with self.assertRaisesRegex(upload.Error,'rung_text_limit'):
                upload.decode(source_blob(rows=[(1,'N',text)])[0])
        with self.assertRaisesRegex(upload.Error,'rung_limit'):
            upload.decode(source_blob(rows=[(n+1,'N','NOP();') for n in range(edits.MAX_RUNGS+1)])[0])

    def test_container_offsets_padding_auxiliary_and_expansion_remain_bounded(self):
        blob=source_blob()[0]
        for offset,value in ((0,len(blob)),(4,24),(8,4),(12,32),(16,8),(20,1),(24,0),(28,1),
                             (32,0),(32,0xC0000000| (struct.unpack_from('<I',blob,32)[0]&0x3fffffff)),(36,edits.MAX_EXPANDED+1)):
            bad=bytearray(blob);struct.pack_into('<I',bad,offset,value)
            with self.subTest(offset=offset),self.assertRaises(upload.Error):upload.decode(bytes(bad))
        off=4+struct.unpack_from('<I',blob,12)[0]
        for offset,value in ((off,2),(off+4,edits.MAX_AUXILIARY+1),(off+4,1)):
            bad=bytearray(blob);struct.pack_into('<I',bad,offset,value)
            with self.assertRaises(upload.Error):upload.decode(bytes(bad))
        for bad in (blob[:-1],blob+b'\0',bytearray(blob),b'',bytes(upload.MAX_CONTAINER+1)):
            with self.assertRaises(upload.Error):upload.decode(bad)
        stored=struct.unpack_from('<I',blob,32)[0]&0x3fffffff;size=struct.unpack_from('<I',blob,8)[0]
        for position in list(range(40+stored,32+size))+list(range(off+struct.unpack_from('<I',blob,16)[0],len(blob))):
            bad=bytearray(blob);bad[position]=1
            with self.assertRaisesRegex(upload.Error,'padding_invalid'):upload.decode(bytes(bad))

    def test_compression_truncation_trailing_data_and_false_expansion_are_errors(self):
        blob=source_blob()[0];bad=bytearray(blob);bad[40]=0
        with self.assertRaises(upload.Error):upload.decode(bytes(bad))
        for data,expected in ((zlib.compress(b'abc')[:-1],3),(zlib.compress(b'abc')+b'X',3),
                              (zlib.compress(b'abc')+zlib.compress(b'def'),3),(zlib.compress(b'abc'),2),
                              (zlib.compress(b'abc'),4)):
            with self.assertRaises(upload.Error):edits.inflate(data,expected,10)

    def test_complete_program_and_aoi_source_reads_decode_in_both_transport_shapes(self):
        blob=source_blob()[0]
        for inner in (initial_request(),initial_request(program=None,aoi=90000)):
            for split in (None,100):
                with self.subTest(split=split):
                    self.assertEqual(assembled(blob,inner,split).routine_source(),upload.decode(blob))

    def test_non_source_selectors_unscoped_wrong_classes_and_writes_do_not_decode(self):
        blob=source_blob()[0]
        inners=[initial_request(selector=9),initial_request(selector=4),initial_request(service=0x4D),
                initial_request(path=logical_path(0x6D,700)),initial_request(path=logical_path(0x338,700)),
                initial_request(path=logical_path(0x6B,700,program=300)),
                initial_request(path=logical_path(0x6D,700,program=300)+b'\x30\x01'),
                initial_request(path=logical_path(0x6D,0,program=300)),
                initial_request()+b'\0',initial_request()[:-1]]
        for inner in inners:
            with self.subTest(inner=inner.hex()),self.assertRaises(upload.Error):assembled(blob,inner).routine_source()

    def test_incomplete_or_cleared_read_cannot_expose_source(self):
        blob=source_blob()[0];value=rt.Assembly();q=rt.ReadRequest(1,0x101,0,initial_request())
        value.accept(q,rt.ReadChunk(1,0x101,len(blob),blob[:100]))
        with self.assertRaisesRegex(upload.Error,'read_incomplete'):value.routine_source()
        value.clear()
        with self.assertRaisesRegex(upload.Error,'read_incomplete'):value.routine_source()
        for value in (None,object(),blob):
            with self.assertRaisesRegex(upload.Error,'read_incomplete'):upload.decode_assembly(value)


if __name__=='__main__':unittest.main()
