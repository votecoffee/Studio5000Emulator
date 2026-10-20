"""Known Template family reads preserve unresolved fields and source absence."""
import copy
import importlib.util
import struct
import tempfile
import unittest

import test_structure_reads as fixtures
from logixlab.ethernetip import Endpoint,logical
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from tools.anonymous_client import AnonymousClient


class TemplateMetadataTests(unittest.TestCase):
    setUp=fixtures.StructureReadTests.setUp
    tearDown=fixtures.StructureReadTests.tearDown
    cip=fixtures.StructureReadTests.cip
    template_path=fixtures.StructureReadTests.template_path
    add_type=fixtures.StructureReadTests.add_type

    def test_explicit_no_family_is_a_word_between_known_and_unresolved_fields(self):
        path=self.template_path('AxisState');template=self.router.templates().for_type('AxisState')
        before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.cip(14,path+b'\x30\6'),b'\x8E\0\0\0\0\0')
        request=struct.pack('<6H',5,5,6,7,8,6)
        expected=(struct.pack('<HHHI',5,5,0,template.size)+struct.pack('<HHH',6,0,0)+
                  struct.pack('<HHHH',7,0x14,8,0x14)+struct.pack('<HHH',6,0,0))
        self.assertEqual(self.cip(3,path,request),b'\x83\0\x0A\0'+expected)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_absent_or_noncanonical_family_does_not_gain_an_explicit_source_value(self):
        self.add_type('DefaultFamily','<Member Name="Value" DataType="DINT"/>',{'Value':1})
        path=self.template_path('DefaultFamily')
        self.assertEqual(self.cip(14,path+b'\x30\6')[2],0x14)
        self.assertEqual(self.cip(14,path+b'\x30\5')[2],0)
        schema=self.app.engine.project.udts['defaultfamily']
        schema.set('Family','NoFamily');self.router._catalog=None
        self.assertEqual(self.cip(14,path+b'\x30\6'),b'\x8E\0\0\0\0\0')
        schema.attrib.pop('Family');schema.set('family','NoFamily');self.router._catalog=None
        self.assertEqual(self.cip(14,path+b'\x30\6')[2],0x14)
        for shadow in ('family','{test}Family'):
            schema.attrib.pop('family',None);schema.attrib.pop('{test}Family',None)
            schema.set('Family','NoFamily');schema.set(shadow,'NoFamily');self.router._catalog=None
            self.assertEqual(self.cip(14,path+b'\x30\6')[2],0x14)

    def test_private_or_unsupported_templates_and_setters_remain_unavailable(self):
        self.add_type('PrivateType','<Member Name="Value" DataType="DINT"/>',{'Value':7},access='None')
        path=self.template_path('PrivateType')
        self.assertEqual(self.cip(14,path+b'\x30\6')[2],5)
        public=self.template_path('AxisState');before=copy.deepcopy(self.app.engine.memory.values)
        for service,payload in ((0x10,b'\0\0'),(4,struct.pack('<HHH',1,6,0))):
            self.assertNotEqual(self.cip(service,public+b'\x30\6',payload)[2],0)
        for number in (7,8):self.assertEqual(self.cip(14,public+bytes((0x30,number)))[2],0x14)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_compact_and_aligned_reads_agree_with_words_without_changing_type_handles(self):
        path=self.template_path('AxisState');template=self.router.templates().for_type('AxisState')
        words=struct.unpack('<I',template.attributes()[4])[0]
        compact=4*words-23;aligned=4*words-20
        short=self.cip(0x4C,path,struct.pack('<IH',0,compact))
        full=self.cip(0x4C,path,struct.pack('<IH',0,aligned))
        self.assertEqual(short,b'\xCC\0\0\0'+template.definition)
        self.assertEqual(full,short+bytes(3))
        self.assertEqual(aligned%4,0)
        self.assertEqual(self.cip(0x4C,path,struct.pack('<IH',compact,3)),b'\xCC\0\0\0'+bytes(3))
        self.assertEqual(self.cip(0x4C,path,struct.pack('<IH',aligned,1))[2],0x20)
        self.assertEqual(struct.unpack('<H',template.attributes()[1])[0],template.handle)

    def test_small_replies_can_finish_in_reserved_storage_without_exposing_other_types(self):
        path=self.template_path('AxisState');template=self.router.templates().for_type('AxisState')
        compact=len(template.definition);initial=copy.deepcopy(self.app.engine.memory.values)
        first=self.cip(0x4C,path,struct.pack('<IH',compact-1,8),limit=6)
        self.assertEqual(first,b'\xCC\0\6\0'+template.definition[-1:]+b'\0')
        second=self.cip(0x4C,path,struct.pack('<IH',compact+1,8),limit=6)
        self.assertEqual(second,b'\xCC\0\0\0'+bytes(2))
        self.assertEqual(self.app.engine.memory.values,initial)
        self.assertEqual(self.app.engine.scan_count,0)


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional cryptography client key generator')
class SignedTemplateMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name)
        self.app.command('demo',{'sample':'StructureLab'})
        self.app.native_project_identity=NativeProjectIdentity('a'*64,self.app.engine.project.sha256,1,1,1,1,1,1)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start()
        self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.temp.cleanup()

    def test_actual_signed_tcp_reads_known_family_and_preserves_unknown_fields_and_aligned_extent(self):
        template=self.endpoint.router.templates().for_type('AxisState')
        path=b'\x20\x6C'+logical(0x24,template.instance)
        before=copy.deepcopy(self.app.engine.memory.values)
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            def request(service,payload=b'',attribute=None):
                target=path+(bytes((0x30,attribute)) if attribute is not None else b'')
                return client.request(bytes((service,len(target)//2))+target+payload)
            self.assertEqual(request(14,attribute=6),b'\x8E\0\0\0\0\0')
            expected=struct.pack('<HHHHHHH',3,6,0,0,7,0x14,8)+struct.pack('<H',0x14)
            self.assertEqual(request(3,struct.pack('<4H',3,6,7,8)),b'\x83\0\x0A\0'+expected)
            size=len(template.definition_storage)
            self.assertEqual(request(0x4C,struct.pack('<IH',0,size)),b'\xCC\0\0\0'+template.definition_storage)
            self.assertEqual(request(0x4C,struct.pack('<IH',size,1))[2],0x20)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)


if __name__=='__main__':unittest.main()
