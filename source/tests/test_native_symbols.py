"""Synthetic metadata and wire routing; no native compiled addresses or ACDs."""
import base64
import gzip
import hashlib
import json
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from logixlab.ethernetip import CIPError, Endpoint, Session, decode_path, logical, symbol_path
from logixlab.importers import convert_acd
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_symbols import NativeSymbols, Symbol
from logixlab.server import Application


XML = '''<LogixTagInfo Name="Synthetic"><SchemaVersion Major="1" Minor="0"/>
<Tags><Tag Name="StartPB" IOI="@107 40000 0 0 0 0@"/>
<Tag Name="SpeedSetpoint" IOI="@107 70000 0 0 0 0@"/></Tags>
<Programs><Program Name="MainProgram"><Tags><Tag Name="LocalValue" IOI="@104 90000 107 7 0 0@"/>
<Tag Name="LocalArray" IOI="@104 90000 107 9 0 0@"/></Tags></Program>
<Program Name="OtherProgram"><Tags><Tag Name="LocalValue" IOI="@104 2 107 7 0 0@"/></Tags></Program></Programs>
</LogixTagInfo>'''


def container(xml, compressed=True):
    stream = gzip.compress(xml, mtime=0) if compressed else xml
    return (b'\r\n'+stream+'TagInfo.XML'.encode('utf-16le').ljust(520,b'\0')+
            struct.pack('<IIII',len(stream),2,1,0))


def request(service, path, data=b''):
    return bytes((service,len(path)//2))+path+data


def symbol(instance, program=None):
    prefix=logical(0x20,0x68)+logical(0x24,program) if program is not None else b''
    return prefix+logical(0x20,0x6B)+logical(0x24,instance)


class NativeSymbolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.acd=self.root/'source.ACD';self.acd.write_bytes(container(XML.encode('utf-16')))
        self.l5x=self.root/'model.L5X'
        tree=ET.parse(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X')
        controller=tree.getroot().find('Controller')
        main=controller.find('./Programs/Program')
        other=ET.SubElement(controller.find('Programs'),'Program',Name='OtherProgram',Class='Standard')
        ET.SubElement(other,'Tags')
        for parent,value in ((main,11),(other,22)):
            tag=ET.SubElement(parent.find('Tags'),'Tag',Name='LocalValue',TagType='Base',DataType='DINT',ExternalAccess='Read/Write')
            ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        tag=ET.SubElement(main.find('Tags'),'Tag',Name='LocalArray',TagType='Base',DataType='DINT',Dimensions='2',ExternalAccess='Read/Write')
        array=ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='2')
        for index,value in enumerate((31,32)):ET.SubElement(array,'Element',Index=f'[{index}]',Value=str(value))
        tree.write(self.l5x,encoding='utf-8',xml_declaration=True)
        self.digest=hashlib.sha256(self.l5x.read_bytes()).hexdigest()
        self.app=Application(self.root/'app')

    def tearDown(self):self.app.close();self.temp.cleanup()

    def catalog(self):return NativeSymbols.from_acd(self.acd,self.digest)

    def load(self,manifest=None):
        self.app.command('load',{'name':'model.L5X','content':base64.b64encode(self.l5x.read_bytes()).decode(),
                                 'native_symbols':self.catalog().manifest() if manifest is None else manifest})
        endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start();self.app.endpoint=endpoint
        return endpoint

    def test_plain_compressed_utf8_and_utf16_preserve_original_and_roundtrip_manifest(self):
        for encoding in ('utf-8','utf-16','utf-16-be'):
            for compressed in (False,True):
                xml=XML.encode(encoding)
                if encoding=='utf-16-be':xml=b'\xfe\xff'+xml
                original=container(xml,compressed);self.acd.write_bytes(original)
                catalog=self.catalog()
                self.assertEqual(self.acd.read_bytes(),original)
                self.assertEqual(catalog.source_acd_sha256,hashlib.sha256(original).hexdigest())
                self.assertEqual(catalog.by_key['startpb'].instance,40000)
                self.assertEqual(catalog.program_ids[90000],'mainprogram')
                self.assertEqual(NativeSymbols.from_manifest(catalog.manifest(),self.digest).manifest(),catalog.manifest())
                self.assertFalse(catalog.description()['compiled_addresses'])

    def test_unknown_schema_missing_paths_wrong_classes_and_invalid_ids_fail_closed(self):
        variants=[XML.replace('Major="1"','Major="2"'),XML.replace('@107 40000 0 0 0 0@',''),
                  XML.replace('@107 40000 0 0 0 0@','@107 0 0 0 0 0@'),
                  XML.replace('@107 40000 0 0 0 0@','@107 40000 1 0 0 0@'),
                  XML.replace('@107 40000 0 0 0 0@','@107 4294967296 0 0 0 0@'),
                  XML.replace('@104 90000 107 7 0 0@','@105 90000 107 7 0 0@'),
                  XML.replace('@104 90000 107 7 0 0@','@104 0 107 7 0 0@'),
                  XML.replace('Name="MainProgram"','Name=""'),XML.replace('Name="StartPB"','Name="invalid name"')]
        for xml in variants:
            self.acd.write_bytes(container(xml.encode()))
            with self.subTest(xml=xml[:100]),self.assertRaises(ModelError):self.catalog()

    def test_xml_declarations_corruption_and_expansion_limits_are_rejected(self):
        for encoding in ('utf-8','utf-16'):
            self.acd.write_bytes(container(('<!DOCTYPE LogixTagInfo [<!ENTITY a "expanded">]>'+XML).encode(encoding)))
            with self.assertRaisesRegex(ModelError,'DTDs'):self.catalog()
        self.acd.write_bytes(container(XML.encode()))
        with patch('logixlab.native_symbols.MAX_XML',50),self.assertRaisesRegex(ModelError,'expanded size'):self.catalog()
        self.acd.write_bytes(container(b'\x1f\x8bnot a gzip',False))
        with self.assertRaises(ModelError):self.catalog()
        self.acd.write_bytes(container(b'\x1f\x8b\x08\0'+bytes(6)+b'\x07'+bytes(20),False))
        with self.assertRaises(ModelError):self.catalog()
        self.acd.write_bytes(container(XML.encode('utf-16-le')))
        with self.assertRaises(ModelError):self.catalog()

    def test_manifests_reject_duplicate_scopes_instances_and_noninteger_fields(self):
        good=self.catalog().manifest();first=good['symbols'][0]
        bad=[{**good,'extra':1},{**good,'source_acd_sha256':'bad'},
             {**good,'symbols':[{**first,'instance':True}]},
             {**good,'symbols':[first,{**first,'name':'OtherTag'}]},
             {**good,'symbols':[{**first,'program_instance':1}]},
             {**good,'symbols':[{**first,'scope':'P','program_instance':1},
                               {**first,'scope':'P','name':'OtherTag','instance':2,'program_instance':2}]},
             {**good,'symbols':[{**first,'scope':'P','program_instance':1},
                               {**first,'scope':'Q','program_instance':1}]}]
        for manifest in bad:
            with self.subTest(manifest=manifest),self.assertRaises(ModelError):NativeSymbols.from_manifest(manifest,self.digest)
        with self.assertRaisesRegex(ModelError,'L5X bytes'):NativeSymbols.from_manifest(good,'0'*64)

    def test_load_rebinding_is_atomic_and_lifecycle_retains_or_clears_catalog(self):
        endpoint=self.load();before=self.app.engine;generation=self.app.generation
        data={'name':'new.L5X','content':base64.b64encode(self.l5x.read_bytes()).decode()}
        bad={**self.catalog().manifest(),'source_l5x_sha256':'0'*64}
        with self.assertRaises(ModelError):self.app.command('load',{**data,'native_symbols':bad})
        self.assertIs(self.app.engine,before);self.assertEqual(self.app.generation,generation)
        identity=NativeProjectIdentity('0'*64,self.digest,0,1,0,1,2,3)
        with self.assertRaisesRegex(ModelError,'different ACD'):
            self.app.command('load',{**data,'native_symbols':self.catalog().manifest(),'native_project_identity':identity.manifest()})
        for action in ('reset','configure'):
            self.app.command(action,{})
            self.assertEqual(self.app.native_symbols.manifest(),self.catalog().manifest())
        self.app.command('load',data);self.assertIsNone(self.app.native_symbols)
        self.assertIsNone(endpoint.state()['native_symbols'])

    def test_root_instance_reads_use_imported_ids_and_do_not_fall_back_to_sorted_ids(self):
        endpoint=self.load();router=endpoint.router;session=Session()
        rows=router.symbols();self.assertEqual([s['id'] for s in rows],[40000,70000])
        self.assertEqual(router.handle(request(0x0E,symbol(70000)+b'\x30\1'),session)[6:],b'SpeedSetpoint')
        reply=router.handle(request(0x4C,symbol(70000),b'\1\0'),session)
        self.assertEqual(reply,b'\xCC\0\0\0'+struct.pack('<Hi',0xC4,50))
        self.assertEqual(router.handle(request(0x4C,symbol(1),b'\1\0'),session)[2],5)
        # Unmapped tags remain available by symbolic name, without inventing IDs.
        self.assertEqual(router.handle(request(0x4C,symbol_path('StopPB'),b'\1\0'),session)[2],0)
        self.assertFalse(endpoint.state()['native_symbols']['compiled_addresses'])

    def test_enumeration_is_sorted_by_native_id_with_inclusive_start_and_reply_limits(self):
        endpoint=self.load();router=endpoint.router;session=Session()
        payload=struct.pack('<HH',1,1)
        first=router.handle(request(0x55,symbol(0),payload),session,limit=25)
        self.assertEqual(first[2],6);self.assertEqual(struct.unpack_from('<I',first,4)[0],40000)
        second=router.handle(request(0x55,symbol(40001),payload),session)
        self.assertEqual(second[2],0);self.assertEqual(struct.unpack_from('<I',second,4)[0],70000)
        self.assertEqual(router.handle(request(0x55,symbol(70001),payload),session),b'\xD5\0\0\0')

    def test_program_object_paths_keep_scopes_distinct_and_support_array_elements(self):
        endpoint=self.load();router=endpoint.router;session=Session()
        for program,value in ((90000,11),(2,22)):
            path=symbol(7,program)
            self.assertEqual(decode_path(path).program_instance,program)
            self.assertEqual(router.handle(request(0x4C,path,b'\1\0'),session),b'\xCC\0\0\0'+struct.pack('<Hi',0xC4,value))
        path=symbol(9,90000)+logical(0x28,1)
        self.assertEqual(router.handle(request(0x4C,path,b'\1\0'),session)[4:],struct.pack('<Hi',0xC4,32))
        symbolic_scope=symbol_path('Program:MainProgram')+symbol(7)
        self.assertEqual(router.handle(request(0x4C,symbolic_scope,b'\1\0'),session)[4:],struct.pack('<Hi',0xC4,11))
        self.assertEqual(router.handle(request(0x4C,symbol(7,999),b'\1\0'),session)[2],5)
        self.app.engine.project.programs['MainProgram']['class']='Safety'
        self.assertEqual(router.handle(request(0x4C,symbol(7,90000),b'\1\0'),session)[2],0x0F)

    def test_duplicate_object_paths_and_mixed_program_scopes_remain_invalid(self):
        endpoint=self.load();router=endpoint.router
        malformed=[bytes.fromhex('20682401206b'),symbol(7,90000)+symbol(7),
                   bytes.fromhex('2068240120682402'),bytes.fromhex('20682400206b2401')]
        for path in malformed:
            with self.assertRaises(CIPError):decode_path(path)
        path=symbol(7,90000)+symbol_path('Program:OtherProgram')
        self.assertEqual(router.handle(request(0x4C,path,b'\1\0'),Session())[2],4)
        path=symbol_path('Program:')+symbol(70000)
        self.assertEqual(router.handle(request(0x4C,path,b'\1\0'),Session())[2],5)

    def test_source_changes_access_restrictions_and_write_gate_are_preserved(self):
        endpoint=self.load();router=endpoint.router;session=Session()
        tag=self.app.engine.project.tags['speedsetpoint'];tag.external_access='None'
        self.assertEqual(router.handle(request(0x4C,symbol(70000),b'\1\0'),session)[2],5)
        tag.external_access='Read/Write'
        self.assertEqual(router.handle(request(0x4D,symbol(70000),struct.pack('<HHi',0xC4,1,123)),session)[2],0x0F)
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),50)
        self.app.engine.project.sha256='0'*64
        self.assertEqual(router.handle(request(0x4C,symbol(70000),b'\1\0'),session)[2],0x0C)

    def test_importer_uses_original_metadata_even_when_converter_changes_private_copy(self):
        executable=self.root/'converter.exe';executable.write_bytes(b'fake')
        def convert(command,**kwargs):
            Path(command[command.index('--acd')+1]).write_bytes(b'changed copy')
            Path(command[command.index('--l5x')+1]).write_bytes(self.l5x.read_bytes())
            return SimpleNamespace(returncode=0,stdout='ok',stderr='')
        with patch('logixlab.importers.subprocess.run',side_effect=convert):
            result=convert_acd(self.acd,self.root/'output/project.L5X',executable)
        self.assertEqual(result['native_symbols'],self.catalog().manifest())
        self.assertIn('native_project_identity_error',result)
        self.assertEqual(json.loads((self.root/'output/provenance.json').read_text())['native_symbols'],result['native_symbols'])


if __name__=='__main__':unittest.main()
