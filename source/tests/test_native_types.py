"""Synthetic source binding and member comparisons, without native acceptance claims."""
import base64
from dataclasses import asdict,dataclass,replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from logixlab import native_types as nt
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from logixlab.ethernetip import Endpoint
from logixlab.importers import convert_acd
from logixlab.template_layout import decode
from test_native_symbols import container
from test_template_layout import definition, template


def source_types():
    return (nt.Type('Inner',4,(nt.Member('Value','DINT',0,None,(),'Read/Write',False),)),
            nt.Type('Example',20,(
                nt.Member('Host','SINT',0,None,(),'Read/Write',True),
                nt.Member('Enabled','BOOL',0,17,(),'Read Only',False),
                nt.Member('Counts','INT',4,None,(3,),'None',False),
                nt.Member('Child','Inner',12,None,(),'Read/Write',False),
                nt.Member('Active','BOOL',16,None,(),'Read/Write',False))))


def catalog(acd='a'*64,l5x='b'*64,types=None,type_ids=None):return nt.NativeTypes(acd,l5x,source_types() if types is None else types,type_ids)


def staged(rows=None):
    rows=rows or ((0,0xC2,0),(1,0xC1,0xA0000002),(3,0x20C3,0xF0000004),(0,0x8101,12),(0,0xC1,16))
    inner=template(definition(header=b'Inner;n'),instance=0x101)
    outer=template(definition(rows,(b'Host',b'Enabled',b'Counts',b'Child',b'Active'),trailer=b'opaque'),5,0x102)
    outer=replace(outer,attributes=replace(outer.attributes,structure_bytes=20))
    return inner,outer


XML='''<LogixTagInfo><SchemaVersion Major="1" Minor="0"/><DataTypes>
<DataType Name="Example" Size="12"><Members>
<Member Name="Flag" DataType="BOOL" Offset="0" Bit="17" ExtAcc="Read Only" Index="0"/>
<Member Name="Values" DataType="INT" Offset="4" Hidden="true" ExtAcc="None" Index="1"><Dimensions><Dim Size="3"/></Dimensions></Member>
</Members></DataType></DataTypes><Tags/><Programs/></LogixTagInfo>'''


class NativeTypeTests(unittest.TestCase):
    def test_binding_rechecks_every_member_field_after_repeated_reads(self):
        expected=lambda c:hashlib.sha256(json.dumps(c.manifest(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for field,value in (('name','Changed'),('dtype','REAL'),('offset',1),('bit',0),('dimensions',(1,)),
                            ('access','None'),('hidden',True),('name','quote"slash\\unicode\u00e9')):
            c=catalog();original=c.binding_stamp();self.assertEqual(c.binding_stamp(),original)
            object.__setattr__(next(iter(c.types.values())).members[0],field,value)
            self.assertEqual(c.binding_stamp(),expected(c));self.assertNotEqual(c.binding_stamp(),original)

    def test_binding_rechecks_source_type_ids_order_and_mutable_fallbacks(self):
        expected=lambda c:hashlib.sha256(json.dumps(c.manifest(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for modify in (lambda c:setattr(c,'source_acd_sha256','c'*64),lambda c:setattr(c,'source_l5x_sha256','d'*64),
                       lambda c:c.type_ids.update(inner=9),lambda c:object.__setattr__(c.types['inner'],'size',8),
                       lambda c:object.__setattr__(c.types['inner'],'name','Other'),
                       lambda c:setattr(c,'types',dict(reversed(tuple(c.types.items()))))):
            c=catalog();original=c.binding_stamp();modify(c)
            self.assertEqual(c.binding_stamp(),expected(c));self.assertNotEqual(c.binding_stamp(),original)
        c=catalog();c.binding_stamp();member=c.types['inner'].members[0]
        object.__setattr__(member,'dimensions',[1]);self.assertEqual(c.binding_stamp(),expected(c))
        member.dimensions.append(2);self.assertEqual(c.binding_stamp(),expected(c))
        c.manifest=lambda:{'override':[1]};self.assertEqual(c.binding_stamp(),expected(c))
        c.manifest=lambda:{'override':[2]};self.assertEqual(c.binding_stamp(),expected(c))

    def test_manifest_preserves_legacy_canonical_bytes_and_detached_member_dimensions(self):
        c=catalog()
        legacy={'source_acd_sha256':c.source_acd_sha256,'source_l5x_sha256':c.source_l5x_sha256,
                'type_ids':dict(c.type_ids),'types':[{'name':t.name,'size':t.size,
                'members':[{**asdict(m),'dimensions':list(m.dimensions)} for m in t.members]} for t in c.types.values()]}
        canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')
        self.assertEqual(canonical(c.manifest()),canonical(legacy))
        self.assertEqual(c.binding_stamp(),hashlib.sha256(canonical(legacy)).hexdigest())
        changed=c.manifest();changed['types'][1]['members'][2]['dimensions'].append(2)
        self.assertEqual(c.manifest(),legacy)
        @dataclass(frozen=True)
        class Extended(nt.Member):extra:int=7
        m=Extended('Value','DINT',0,None,(),'Read/Write',False)
        subclass=nt.NativeTypes('a'*64,'b'*64,(nt.Type('Example',4,(m,)),))
        self.assertEqual(subclass.manifest()['types'][0]['members'][0],{**asdict(m),'dimensions':[]})

    def test_nested_array_direct_and_packed_bool_locations_match_without_authorizing_storage(self):
        value=catalog().verify(staged())
        self.assertEqual((value['status'],value['types_matched'],value['members_matched']),('matched',2,6))
        self.assertTrue(value['member_locations_verified'])
        for flag in ('storage_mapping_supported','signature_verified','definitions_exposed','execution_supported'):
            self.assertFalse(value[flag])
        for text in ('Example','Inner','Enabled','opaque','2684354562'):self.assertNotIn(text,json.dumps(value))
        self.assertEqual(catalog().verify(())['status'],'idle')

    def test_type_name_size_member_count_order_and_location_mismatches_are_redacted(self):
        inner,outer=staged()
        variants=(replace(outer,attributes=replace(outer.attributes,structure_bytes=21)),
                  replace(outer,definition=outer.definition.replace(b'Example',b'Unknown')),
                  replace(outer,definition=outer.definition.replace(b'Enabled',b'Changed')),
                  replace(outer,attributes=replace(outer.attributes,members=4)))
        for value in variants:
            result=catalog().verify((inner,value));self.assertEqual(result['status'],'mismatch')
            self.assertFalse(result['member_locations_verified']);self.assertEqual(result['types_unavailable'],1)
        for index,field,value in ((0,0,1),(0,1,0xC4),(0,2,1),(1,0,2),(1,2,0xA0000003),
                                  (2,0,2),(2,1,0x40C3),(2,2,4),(3,1,0x8FFF),(3,1,0x0101),
                                  (4,0,1),(4,2,0x90000010)):
            rows=[list((m.info,m.type_word,m.offset_word)) for m in decode(outer.definition,5).members]
            rows[index][field]=value
            with self.subTest(index=index,field=field,value=value):
                result=catalog().verify(staged(rows));self.assertEqual(result['status'],'mismatch')
                self.assertEqual(result['types_matched'],1)

    def test_duplicate_template_ids_names_missing_nested_types_and_bad_definitions_fail(self):
        inner,outer=staged()
        for rows in ((inner,inner),(outer,), (inner,replace(outer,instance=0x101)),
                     (inner,replace(inner,instance=0x103)), (inner,replace(outer,definition=b'bad'))):
            result=catalog().verify(rows);self.assertEqual(result['status'],'mismatch')
            self.assertFalse(result['member_locations_verified'])

    def test_source_catalog_rejects_invalid_names_sizes_dimensions_access_and_bits(self):
        t=source_types()[0];m=t.members[0]
        for member in (replace(m,name='bad.name'),replace(m,dtype='Missing'),replace(m,offset=4),
                replace(m,offset=True),replace(m,hidden=1),replace(m,access='RW'),replace(m,dimensions=(0,)),
                replace(m,dimensions=(65536,)),replace(m,dimensions=(256,256)),replace(m,bit=0)):
            with self.subTest(member=member),self.assertRaises(ModelError):catalog(types=(replace(t,members=(member,)),))
        for types in ((t,t),(replace(t,name='DINT'),),(replace(t,size=0),),(replace(t,size=True),),(replace(t,members=(m,m)),)):
            with self.assertRaises(ModelError):catalog(types=types)
        with self.assertRaises(ModelError):catalog(acd='invalid')

    def test_source_extent_limit_is_exact_and_recursive_or_deep_types_are_rejected(self):
        t=nt.Type('Bytes',nt.MAX_SIZE,(nt.Member('Values','SINT',nt.MAX_SIZE-1,None,(),'Read/Write',False),))
        self.assertEqual(catalog(types=(t,)).member_count,1)
        with self.assertRaises(ModelError):catalog(types=(replace(t,members=(replace(t.members[0],dimensions=(2,)),)),))
        cycle=nt.Type('Cycle',4,(nt.Member('Next','Cycle',0,None,(),'Read/Write',False),))
        with self.assertRaises(ModelError):catalog(types=(cycle,))
        chain=[nt.Type('T0',4,(nt.Member('Value','DINT',0,None,(),'Read/Write',False),))]
        for i in range(1,nt.MAX_DEPTH+1):chain.append(nt.Type(f'T{i}',4,(nt.Member('Child',f'T{i-1}',0,None,(),'Read/Write',False),)))
        for types in (chain,list(reversed(chain))):
            with self.assertRaises(ModelError):catalog(types=types)

    def test_unsupported_array_ranks_and_bool_arrays_are_not_certified(self):
        for dtype,dims in (('DINT',(1,1)),('BOOL',(32,))):
            t=nt.Type('Example',4,(nt.Member('Value',dtype,0,None,dims,'Read/Write',False),))
            result=catalog(types=(t,)).verify((template(definition(((1,0x20C1,0),))),))
            self.assertEqual(result['status'],'mismatch');self.assertFalse(result['member_locations_verified'])

    def test_manifest_roundtrip_is_independent_and_wrong_bindings_and_fields_fail(self):
        c=catalog();manifest=c.manifest();self.assertEqual(nt.NativeTypes.from_manifest(manifest,'b'*64).manifest(),manifest)
        manifest['types'][0]['members'][0]['offset']=99
        self.assertEqual(c.manifest()['types'][0]['members'][0]['offset'],0)
        with self.assertRaises(ModelError):nt.NativeTypes.from_manifest(c.manifest(),'c'*64)
        for value in ({},None,{**c.manifest(),'extra':1},{**c.manifest(),'types':{}},
                      {**c.manifest(),'types':[{'name':'Wrong'}]}):
            with self.assertRaises(ModelError):nt.NativeTypes.from_manifest(value,'b'*64)
        with patch.object(nt,'MAX_TOTAL_MEMBERS',5),self.assertRaises(ModelError):catalog()
        with patch.object(nt,'MAX_TYPES',1),self.assertRaises(ModelError):catalog()
        with patch.object(nt,'MAX_TOTAL_MEMBERS',5),self.assertRaises(ModelError):nt.NativeTypes.from_manifest(c.manifest(),'b'*64)

    def test_xml_parses_supported_encodings_and_compression_and_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'synthetic.ACD'
            for encoding in ('utf-8-sig','utf-16','utf-16-be'):
                text=XML if encoding!='utf-16-be' else '<?xml version="1.0" encoding="UTF-16BE"?>'+XML
                # Big-endian XML uses its BOM to make the chosen encoding explicit.
                raw=text.encode(encoding);raw=b'\xfe\xff'+raw if encoding=='utf-16-be' else raw
                for compressed in (False,True):
                    p.write_bytes(container(raw,compressed));c=nt.NativeTypes.from_acd(p,'b'*64)
                    self.assertEqual(c.member_count,2);self.assertEqual(c.types['example'].members[0].bit,17)
                    self.assertEqual(c.types['example'].members[1].dimensions,(3,))

    def test_xml_rejects_unknown_fields_order_duplicate_names_dtds_and_bad_dimensions(self):
        variants=(XML.replace('Index="1"','Index="0"'),XML.replace('Index="1"','Index="-1"'),
            XML.replace('Name="Values"','Name="Flag"'),XML.replace('Size="3"','Size="0"'),
            XML.replace('Hidden="true"','Hidden="yes"'),XML.replace('ExtAcc="None"','ExtAcc="Bad"'),
            XML.replace('Name="Values"','Other="Values"'),XML.replace('<Dim Size="3"/>','<Unknown/>'),
            XML.replace('Minor="0"','Minor="1"'),XML.replace('<Members>','<Unknown/><Members>'),
            XML.replace('<DataTypes>','<DataTypes><Unknown/>'),XML.replace('<DataTypes>','<DataTypes Unknown="1">'),
            XML.replace('<Members>','<Members Unknown="1">'),XML.replace('<LogixTagInfo>','<!DOCTYPE LogixTagInfo><LogixTagInfo>'))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'synthetic.ACD'
            for value in variants:
                p.write_bytes(container(value.encode()))
                with self.subTest(value=value[:80]),self.assertRaises(ModelError):nt.NativeTypes.from_acd(p,'b'*64)

    def test_validated_string_marker_does_not_add_string_execution_semantics(self):
        text=XML.replace('<Members>','<String Length="8"/><Members>')
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'synthetic.ACD';p.write_bytes(container(text.encode()))
            self.assertEqual(nt.NativeTypes.from_acd(p,'b'*64).member_count,2)
            for fragment in ('<String Length="0"/>','<String Length="8" Unknown="1"/>','<String/>'):
                p.write_bytes(container(text.replace('<String Length="8"/>',fragment).encode()))
                with self.assertRaises(ModelError):nt.NativeTypes.from_acd(p,'b'*64)


class NativeTypeBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.app=Application(self.root/'app');self.l5x=Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
        self.digest=hashlib.sha256(self.l5x.read_bytes()).hexdigest()
        self.data={'name':'demo.L5X','content':base64.b64encode(self.l5x.read_bytes()).decode()}
        self.native=catalog(l5x=self.digest)

    def tearDown(self):self.app.close();self.temp.cleanup()

    def test_load_binding_is_atomic_and_keeps_polled_provenance_small(self):
        self.app.command('load',{**self.data,'native_types':self.native.manifest()})
        self.app.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start()
        state=self.app.state();self.assertEqual(state['connectivity']['native_types']['members'],6)
        self.assertEqual(state['provenance']['native_types']['types'],2)
        self.assertNotIn('Inner',json.dumps(state['provenance']['native_types']))
        before=self.app.engine;generation=self.app.generation
        for value in ({**self.native.manifest(),'source_l5x_sha256':'0'*64},
                      {**self.native.manifest(),'types':[{'bad':'fields'}]}):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_types':value})
            self.assertIs(self.app.engine,before);self.assertEqual(self.app.generation,generation)
        for action in ('reset','configure'):
            self.app.command(action,{});self.assertEqual(self.app.native_types.manifest(),self.native.manifest())
        self.app.command('load',self.data);self.assertIsNone(self.app.native_types)
        self.assertIsNone(self.app.endpoint.state()['native_types'])

    def test_conflicting_acd_identity_or_symbol_binding_is_rejected_before_model_swap(self):
        from logixlab.native_symbols import NativeSymbols
        self.app.command('load',self.data);before=self.app.engine
        identity=NativeProjectIdentity('c'*64,self.digest,0,1,0,1,2,3)
        for other in ({'native_project_identity':identity.manifest()},
                      {'native_symbols':NativeSymbols('c'*64,self.digest,()).manifest()}):
            with self.assertRaisesRegex(ModelError,'different ACD'):
                self.app.command('load',{**self.data,'native_types':self.native.manifest(),**other})
            self.assertIs(self.app.engine,before)

    def test_conversion_carries_optional_types_and_preserves_original(self):
        p=self.root/'input.ACD';p.write_bytes(container(XML.encode('utf-16')))
        converter=self.root/'converter.exe';converter.write_bytes(b'synthetic')
        out=self.root/'export.L5X';original=p.read_bytes()
        def convert(*args,**kw):
            out.write_bytes(self.l5x.read_bytes())
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch('logixlab.importers.subprocess.run',side_effect=convert):result=convert_acd(p,out,converter)
        self.assertIn('native_types',result);self.assertEqual(p.read_bytes(),original)
        self.assertEqual(len(result['native_types']['types']),1)


if __name__=='__main__':unittest.main()
