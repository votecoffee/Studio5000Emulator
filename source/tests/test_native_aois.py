"""AOI identities and read-only metadata never infer compiled definitions."""
import base64
import copy
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.aoi_catalog import AOICatalog
from logixlab.ethernetip import Endpoint,Session
from logixlab.model import ModelError
from logixlab.native_aois import NativeAOIs,definition_paths
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path,decode_attribute_list,values,collect_inventory,Limits,InventoryError
import test_native_tasks as fixtures


def record(name='LabAccumulator',instance=700,**kwargs):
    return fixtures.record(name,instance,version=kwargs.pop('version',21),class_id=0x338,**kwargs)


class NativeAOIIdentityTests(unittest.TestCase):
    def test_only_expected_original_standalone_format21_paths_bind(self):
        raw=fixtures.database(record(),record('Other',20),record(instance=0,component_type=0),
            record(instance=9,kind=0xFDFD),record(child=(0x6D,3,0,0)),tail=record(instance=30))
        self.assertEqual(definition_paths(raw,['LabAccumulator']),[{'name':'LabAccumulator','instance':700}])
        for bad in (fixtures.database(),fixtures.database(record(),record()),
                    fixtures.database(record(),record(instance=9)),fixtures.database(record(version=20)),
                    fixtures.database(record(instance=0)),fixtures.database(record(child=(1,0,0,0))),
                    fixtures.database(record(header_version=1)),raw[:-1]):
            with self.subTest(size=len(bad)),self.assertRaises(ModelError):definition_paths(bad,['LabAccumulator'])

    def test_names_ids_bounds_and_immutable_manifests_are_validated(self):
        binding=NativeAOIs('a'*64,'b'*64,[{'name':'LabAccumulator','instance':700}])
        self.assertEqual(NativeAOIs.from_manifest(binding.manifest(),'b'*64),binding)
        with self.assertRaises(FrozenInstanceError):binding.source_l5x_sha256='c'*64
        with self.assertRaises(TypeError):binding.definitions['other']=('Other',1)
        for row in ({'name':'Bad.Name','instance':1},{'name':'Name','instance':True},
                    {'name':'Name','instance':0},{'name':'Name','instance':65536},{'name':'Name','instance':1,'extra':0}):
            with self.assertRaises(ModelError):NativeAOIs('a'*64,'b'*64,[row])
        with self.assertRaises(ModelError):NativeAOIs.from_manifest(binding.manifest(),'c'*64)
        with self.assertRaises(ModelError):definition_paths(fixtures.database(),['Name','name'])
        with self.assertRaises(ModelError):definition_paths(fixtures.database(),['a'*40])

    def test_bounded_raw_and_compressed_acd_members_bind_to_original_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.ACD'
            for compressed in (False,True):
                payload=fixtures.container(fixtures.database(record()),compressed)
                path.write_bytes(payload);binding=NativeAOIs.from_acd(path,'b'*64,['LabAccumulator'])
                self.assertEqual(binding.source_acd_sha256,hashlib.sha256(payload).hexdigest())
                self.assertEqual(path.read_bytes(),payload)
                self.assertEqual(binding.manifest()['definitions'],[{'name':'LabAccumulator','instance':700}])


class AOISourceMetadataTests(unittest.TestCase):
    def setUp(self):self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/AOILab.L5X').getroot()

    def catalog(self,root=None):
        root=self.root if root is None else root
        return AOICatalog.from_source(root,root.find('Controller'))

    def test_source_fields_are_exact_width_and_missing_or_malformed_fields_stay_absent(self):
        catalog=self.catalog();self.assertFalse(catalog.empty);row=catalog.metadata[0]
        self.assertEqual(row.attributes(),{1:b'\0\0',12:b'\1\0',13:b'\0\0',21:b'\10\0LogixLab'})
        node=self.root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')
        node.set('Revision','65535.65535');node.set('RevisionExtension','')
        self.assertEqual(self.catalog().metadata[0].attributes()[12],b'\xff\xff')
        self.assertEqual(self.catalog().metadata[0].attributes()[19],b'\0\0')
        for revision in ('-1.0','1','65536.0','1.x','1.0.0'):
            node.set('Revision',revision);fields=self.catalog().metadata[0].attributes()
            self.assertNotIn(12,fields);self.assertNotIn(13,fields)
        node.set('Vendor','x'*41);node.set('RevisionExtension','non-ascii-\u00e9')
        fields=self.catalog().metadata[0].attributes();self.assertNotIn(19,fields);self.assertNotIn(21,fields)

    def test_encoded_headers_are_included_but_never_gain_a_clean_state_or_decoded_payload(self):
        section=self.root.find('./Controller/AddOnInstructionDefinitions')
        node=E.SubElement(section,'EncodedData',EncodedType='AddOnInstructionDefinition',Name='Protected',Class='Standard',Revision='2.3')
        E.SubElement(node,'Data').text='opaque-private-payload'
        rows=self.catalog().metadata;self.assertEqual(len(rows),4);self.assertTrue(rows[-1].protected)
        self.assertEqual(rows[-1].attributes(),{12:b'\2\0',13:b'\3\0'})
        node.set('EncodedType','Unknown');self.assertIsNone(self.catalog().metadata)

    def test_ambiguous_partial_hidden_or_pending_edit_declarations_withhold_inventory(self):
        for change in ('context','duplicate','namespace','case','unknown','class','pending','protected','alias-name','section-context'):
            root=copy.deepcopy(self.root);section=root.find('./Controller/AddOnInstructionDefinitions');node=section[0]
            if change=='context':root.set('ContainsContext','true')
            elif change=='duplicate':section.append(copy.deepcopy(node))
            elif change=='namespace':node.tag='{urn:other}AddOnInstructionDefinition'
            elif change=='case':node.tag='addoninstructiondefinition'
            elif change=='unknown':E.SubElement(section,'VendorDefinition')
            elif change=='class':node.set('Class','Other')
            elif change=='pending':node.find('./Routines/Routine/RLLContent').set('OnlineEditType','TestEdits')
            elif change=='protected':E.SubElement(node,'ProtectedContent')
            elif change=='alias-name':node.set('name','Other')
            else:section.set('Use','Context')
            with self.subTest(change=change):self.assertIsNone(self.catalog(root).metadata)


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional independent client key generator')
class AOIMetadataTcpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name)
        self.app.command('demo',{'sample':'AOILab'});sha=self.app.engine.project.sha256
        self.app.native_project_identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1)
        self.app.native_aois=NativeAOIs('a'*64,sha,[{'name':row.name,'instance':700+i}
                                                  for i,row in enumerate(self.app.engine.project.aoi_catalog.metadata)])
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start();self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.temp.cleanup()

    def request(self,service,instance,payload=b'',attribute=None):
        path=logical_path(0x338,instance)+(bytes((0x30,attribute)) if attribute is not None else b'')
        return bytes((service,len(path)//2))+path+payload

    def test_real_signed_state_metadata_and_ordered_partial_lists_preserve_execution_state(self):
        before=copy.deepcopy(self.app.state())
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            self.assertEqual(client.request(self.request(3,0,b'\1\0\1\0')),bytes.fromhex('830000000100010000000600'))
            self.assertEqual(client.request(self.request(0x4B,0)),b'\xcb\0\0\0'+struct.pack('<3I',700,701,702))
            self.assertEqual(client.request(self.request(0x0E,700,attribute=1)),b'\x8e\0\0\0\0\0')
            requested=(1,12,13,19,21,1,16,3);schema={1:2,12:2,13:2,19:'ascii16',21:'ascii16',16:None,3:None}
            raw=client.request(self.request(3,700,struct.pack('<9H',len(requested),*requested)))
            result=decode_attribute_list(raw,requested,schema)
            self.assertEqual(result['status'],0x0A);self.assertEqual(values(result),{1:0,12:1,13:0,21:'LogixLab'})
            self.assertEqual(client.request(self.request(0x0E,799,attribute=1))[2],5)
            for service in (4,8,9,0x10):self.assertNotEqual(client.request(self.request(service,700))[2],0)
        for key in ('tags','scan','ms','routines','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_missing_stale_or_cross_acd_bindings_never_invent_an_empty_inventory(self):
        sha=self.app.engine.project.sha256
        for binding in (None,NativeAOIs('b'*64,sha,[{'name':'LabAccumulator','instance':700}]),
                        NativeAOIs('a'*64,'b'*64,[{'name':'LabAccumulator','instance':700}]),
                        NativeAOIs('a'*64,sha,[{'name':'Other','instance':700}])):
            self.app.native_aois=binding
            with AnonymousClient(self.endpoint) as client:
                client.bind();self.assertEqual(client.request(self.request(0x4B,0))[2],0x0C)

    def test_load_validates_binding_atomically_and_reload_drops_old_identities(self):
        content=base64.b64encode(self.app.engine.project.path.read_bytes()).decode();before=self.app.engine
        bad=self.app.native_aois.manifest();bad['definitions'][0]['name']='Other'
        with self.assertRaises(ModelError):self.app.command('load',{'name':'aoi.L5X','content':content,'native_aois':bad})
        self.assertIs(self.app.engine,before)
        self.app.command('load',{'name':'aoi.L5X','content':content,'native_aois':self.app.native_aois.manifest(),
                              'native_project_identity':self.app.native_project_identity.manifest()})
        self.assertIsNotNone(self.app.native_aois)
        self.app.command('demo',{'sample':'ConveyorDemo'});self.assertIsNone(self.app.native_aois)

    def test_independent_inventory_keeps_aoi_metadata_separate_from_definition_upload(self):
        report=collect_inventory(self.endpoint,read_values=False)
        self.assertEqual(report['aoi_catalog']['instances'],[700,701,702])
        self.assertEqual(len(report['aois']),3)
        self.assertEqual(values(report['aois'][0]['metadata'])[1],0)
        self.assertFalse(report['aoi_definition_upload']);self.assertFalse(report['project_upload_complete'])
        with self.assertRaises(InventoryError):collect_inventory(self.endpoint,limits=Limits(aois=2))

    def test_protected_declaration_keeps_plain_header_and_returns_attribute_unavailable_for_state(self):
        root=E.parse(self.app.engine.project.path).getroot();section=root.find('./Controller/AddOnInstructionDefinitions')
        node=E.SubElement(section,'EncodedData',EncodedType='AddOnInstructionDefinition',Name='Protected',Class='Standard',Revision='2.3')
        E.SubElement(node,'Data').text='opaque-private-payload'
        raw=E.tostring(root);sha=hashlib.sha256(raw).hexdigest()
        binding=self.app.native_aois.manifest();binding['source_l5x_sha256']=sha
        binding['definitions'].append({'name':'Protected','instance':900})
        self.app.command('load',{'name':'protected.L5X','content':base64.b64encode(raw).decode(),'native_aois':binding,
            'native_project_identity':NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1).manifest()})
        with AnonymousClient(self.endpoint) as client:
            client.bind();self.assertEqual(client.request(self.request(0x0E,900,attribute=1))[2],0x14)
            self.assertEqual(client.request(self.request(0x0E,900,attribute=12)),b'\x8e\0\0\0\2\0')


if __name__=='__main__':unittest.main()
