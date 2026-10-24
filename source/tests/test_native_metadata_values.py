"""Original source values, immutable binding and per-session signed read streams."""
import base64
import copy
from dataclasses import FrozenInstanceError,replace
import gzip
import hashlib
import io
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from logixlab import metadata_query as wire,native_metadata_values as values,importers
from logixlab.model import ModelError
from logixlab.native_metadata_definitions import Definition,NativeMetadataDefinitions
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_session import NativeSession
from logixlab.server import Application
from logixlab.ethernetip import Endpoint,Session,CIPError
from tools.anonymous_client import AnonymousClient
from tools.metadata_upload_query import frame
from tools import vmware_appliance as vm
from test_native_routines import database


def definitions(acd='a'*64,l5x='b'*64):
    return NativeMetadataDefinitions(acd,l5x,(Definition(1,'Comment'),Definition(4,'AssociatedTag'),Definition(17,'ValueType')))


def numeric(raw=b'\1',code=0xC2):return struct.pack('<H',code)+bytes(12)+raw
def text(raw=b'Private text'):return bytes(12)+raw+b'\0'


def record(payload,definition=1,path=(0x68,700,0x6D,800,0xFFFF,10),locale=(0,0),qualifier=None,**changes):
    header=bytearray(32 if qualifier is None else 30)
    struct.pack_into('<HH',header,6,1 if qualifier is None else 23,len(payload))
    header[10:22]=struct.pack('<6H',*path);header[27]=definition;header[28:30]=bytes(locale)
    if qualifier is not None:
        header[22:26]=b'\x78\x56\x34\x12';header.extend(qualifier.encode('utf-16le')+bytes(2))
    header.extend(payload);struct.pack_into('<I',header,0,len(header)-4)
    for offset,data in changes.items():header[int(offset) : int(offset)+len(data)]=data
    return struct.pack('<HI',0xFAFA,len(header)+6)+header


def schema():
    return tuple(record(numeric(bytes((kind,))),17,path=(0x349,number,0,0,0,0)) for number,kind in ((1,0),(4,2),(17,1)))


def records():
    ref=b'Member'+bytes(35)+struct.pack('<6H',0x6C,202,0,0,0,0)+b'\0'
    return (*schema(),record(text()),record(text('Übersicht'.encode()),locale=(7,1)),
        record(ref,4,path=(0x6C,1000,0,0,0,0)),
        record(numeric(bytes.fromhex('78563412'),0xC4),17,path=(0x8E,1,0,0,0,0),qualifier='ControllerSerialNumber'))


def catalog(acd='a'*64,l5x='b'*64):
    d=definitions(acd,l5x);return values.NativeMetadataValues(acd,l5x,d,values.stored_records(database(*records()),d))


def container(raw):
    name='Comments.Dat'.encode('utf-16le');packed=gzip.compress(raw)
    return b'\r\n'+packed+name+bytes(520-len(name))+struct.pack('<II',len(packed),2)+struct.pack('<II',1,0)


def query(selection='all-objects',position=0):
    return bytes.fromhex('5303210049032400')+struct.pack('<II',1 if position else 0x101,position)+wire.SELECTIONS[selection]


class StoredMetadataTests(unittest.TestCase):
    def test_saved_controller_numeric_qualifier_retains_exact_source_value_and_roundtrips(self):
        d=NativeMetadataDefinitions('a'*64,'b'*64,(*definitions().rows,Definition(36,'SystemNumeric')))
        declaration=record(numeric(b'\1'),17,path=(0x349,36,0,0,0,0))
        value=record(numeric(struct.pack('<I',0x4C),0xC4),36,path=(0x8E,1,0,0,0,0),qualifier='ProjectType',**{'6':b'\x0c\0'})
        raw=database(*schema(),declaration,value)
        c=values.NativeMetadataValues('a'*64,'b'*64,d,values.stored_records(raw,d))
        item=c.rows[-1]
        self.assertEqual((item.target, item.definition,item.locale_word,item.kind,item.type_code,item.elements,item.data),
            (wire.Target(0x8E,1,0,0,b'ProjectType'),36,0x7F,2,0xC4,1,struct.pack('<I',0x4C)))
        self.assertEqual(wire.records(c.body('controller-all')),(item,))
        self.assertEqual(values.NativeMetadataValues.from_manifest(c.manifest(),'b'*64,d),c)
        # Stored values are preserved even when they are not the known marker.
        other=record(numeric(struct.pack('<I',17),0xC4),36,path=(0x8E,1,0,0,0,0),qualifier='OtherProperty',**{'6':b'\x0c\0'})
        rows=values.stored_records(database(*schema(),declaration,other),d)
        self.assertEqual(rows[-1].data,struct.pack('<I',17))

    def test_saved_qualifier_form_rejects_unestablished_targets_types_locales_and_names(self):
        d=NativeMetadataDefinitions('a'*64,'b'*64,(*definitions().rows,Definition(36,'SystemNumeric')))
        declaration=record(numeric(b'\1'),17,path=(0x349,36,0,0,0,0))
        base=dict(definition=36,path=(0x8E,1,0,0,0,0),qualifier='ProjectType',**{'6':b'\x0c\0'})
        cases=[dict(path=(0x68,1,0,0,0,0)),dict(path=(0x8E,2,0,0,0,0)),dict(path=(0x8E,1,1,0,0,0)),
            dict(path=(0x8E,1,0,0,0,1)),dict(definition=17),dict(locale=(7,1)),dict(qualifier='Bad.Name'),
            dict(qualifier=''),{'6':b'\x0d\0'},{'26':b'\1'},{'22':bytes(4)}]
        for changed in cases:
            with self.subTest(changed=changed),self.assertRaises(ModelError):
                values.stored_records(database(*schema(),declaration,record(numeric(bytes(4),0xC4),**(base|changed))),d)
        for payload in (text(),numeric(b'\1'),numeric(bytes(2),0xC3),numeric(bytes(8),0xC4)):
            with self.subTest(payload=payload),self.assertRaises(ModelError):
                values.stored_records(database(*schema(),declaration,record(payload,**base)),d)

    def test_original_layout_retains_scopes_locales_numeric_arrays_and_reference_targets(self):
        c=catalog();self.assertEqual(len(c.rows),7)
        first=c.rows[3];self.assertEqual(first.data,b'Private text');self.assertEqual(first.locale_word,0x7F)
        self.assertEqual(values._path(first.target),struct.pack('<6H',0x68,700,0x6D,800,0xFFFF,10))
        self.assertEqual(c.rows[4].locale_word,0x407);self.assertEqual(c.rows[4].data,'Übersicht'.encode())
        self.assertEqual(c.rows[5].references[0].name,b'Member')
        self.assertEqual(values._path(c.rows[5].references[0].target),struct.pack('<6H',0x6C,202,0,0,0,0))
        self.assertEqual(c.rows[6].target.qualifier,b'ControllerSerialNumber')
        self.assertEqual(c.rows[6].data,bytes.fromhex('78563412'));self.assertEqual(c.rows[6].elements,1)
        self.assertEqual([r.record_word for r in c.rows],list(range(1,8)))
        self.assertEqual(wire.records(c.body('all-objects')),c.rows)
        self.assertEqual(wire.records(c.body('controller-all')),(c.rows[6],))
        self.assertEqual(c.body('controller-attribute-26'),b'')
        with self.assertRaises(FrozenInstanceError):c.rows=()
        self.assertFalse(c.description()['source_targets_resolved']);self.assertFalse(c.description()['metadata_writes'])
        for secret in ('Private text','Member','ControllerSerialNumber'):self.assertNotIn(secret,str(c.description()))

    def test_container_manifest_and_source_hashes_round_trip_without_modifying_original(self):
        raw=container(database(*records()))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'own.ACD';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();d=definitions(sha)
            c=values.NativeMetadataValues.from_acd(path,'b'*64,d)
            self.assertEqual(c.source_acd_sha256,sha);self.assertEqual(path.read_bytes(),raw)
            self.assertEqual(values.NativeMetadataValues.from_manifest(c.manifest(),'b'*64,d),c)
        for change in ({'source_l5x_sha256':'c'*64},{'source_acd_sha256':'c'*64},{'extra':0},
                       {'values_hex':'bad'},{'values_hex':None},{'values_hex':''}):
            with self.assertRaises(ModelError):values.NativeMetadataValues.from_manifest({**c.manifest(),**change},'b'*64,d)
        with self.assertRaises(ModelError):values.NativeMetadataValues.from_manifest(c.manifest(),'b'*64,None)

    def test_unsupported_headers_locales_qualifiers_and_late_values_withhold_whole_catalog(self):
        bad=[record(text(),**{'4':b'\1\0'}),record(text(),**{'6':b'\2\0'}),record(text(),**{'8':b'\xFF\xFF'}),
            record(text(),**{'22':b'\1'}),record(text(),**{'26':b'\1'}),record(text(),**{'30':b'\1'}),
            record(text(),locale=(1,1)),record(text(),definition=99),record(text(b'\xff')),
            record(text(b'A\0B')),record(bytes(11)+b'X\0'),record(numeric(b'\1',0xCA),17),
            record(numeric(b'\1',0xC3),17),record(numeric(),17,qualifier=''),
            record(numeric(),17,qualifier='Good',**{'22':bytes(4)}),record(b'x',4)]
        for raw in bad:
            with self.subTest(raw=hashlib.sha256(raw).hexdigest()),self.assertRaises(ModelError):
                values.stored_records(database(*schema(),raw),definitions())
        for raw in (database(),database(*schema()[:-1]),database(*schema(),schema()[0]),database(*records(),records()[3])):
            with self.assertRaises(ModelError):catalog_rows=values.stored_records(raw,definitions());values.NativeMetadataValues('a'*64,'b'*64,definitions(),catalog_rows)
        raw=database(*records())
        for value in (raw[:-1],bytes(512),b'',bytearray(raw)):
            with self.assertRaises(ModelError):values.stored_records(value,definitions())

    def test_deleted_records_and_allocation_tails_cannot_supply_active_values(self):
        deleted=bytearray(record(text(b'Ignored')));struct.pack_into('<H',deleted,0,0xFDFD)
        base=record(text());allocated=base+b'old-allocation'
        allocated=allocated[:2]+struct.pack('<I',len(allocated))+allocated[6:]
        rows=values.stored_records(database(*schema(),bytes(deleted),allocated,tail=record(text(b'Outside'))),definitions())
        self.assertEqual(len(rows),4);self.assertEqual(rows[-1].data,b'Private text')
        c=catalog()
        for changed in (replace(c.rows[0],record_word=True),replace(c.rows[3],data=b'\xff'),
                        replace(c.rows[3],target=replace(c.rows[3].target,class_id=0)),
                        replace(c.rows[3],definition=4),replace(c.rows[3],record_word=999)):
            with self.assertRaises(ModelError):values.NativeMetadataValues('a'*64,'b'*64,c.definitions,(changed,*c.rows[1:]))

    def test_conversion_and_appliance_forward_values_and_keep_unsupported_export(self):
        content=(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').read_bytes();sha=hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'own.ACD';source.write_bytes(container(database(*records())));exe=root/'convert.exe';exe.write_bytes(b'double')
            identity=NativeProjectIdentity(hashlib.sha256(source.read_bytes()).hexdigest(),sha,1,1,1,1,1,1)
            d=definitions(identity.source_acd_sha256,sha)
            def convert(command,**kwargs):Path(command[command.index('--l5x')+1]).write_bytes(content);return SimpleNamespace(returncode=0,stdout='',stderr='')
            with patch.object(importers.subprocess,'run',side_effect=convert),patch.object(importers.NativeProjectIdentity,'from_acd',return_value=identity),patch.object(importers.NativeMetadataDefinitions,'from_acd',return_value=d):
                receipt=importers.convert_acd(source,root/'supported/project.L5X',exe)
            self.assertIn('native_metadata_values',receipt)
            def import_copy(acd,output,converter):output.write_bytes(content);return receipt
            with patch.object(vm,'validated_state',return_value=({'url':'http://127.0.0.1:1'},{})),patch.object(importers,'convert_acd',side_effect=import_copy),patch.object(vm,'api',return_value={'app_version':'test','name':'fixture'}) as api:
                vm.import_project(root,source,str(exe))
            self.assertEqual(api.call_args.args[2]['native_metadata_values'],receipt['native_metadata_values'])
            source.write_bytes(container(database()))
            with patch.object(importers.subprocess,'run',side_effect=convert),patch.object(importers.NativeProjectIdentity,'from_acd',return_value=identity),patch.object(importers.NativeMetadataDefinitions,'from_acd',return_value=d):
                receipt=importers.convert_acd(source,root/'unsupported/project.L5X',exe)
            self.assertIn('native_metadata_values_error',receipt);self.assertEqual((root/'unsupported/project.L5X').read_bytes(),content)


class MetadataValueEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        content=(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').read_bytes();sha=hashlib.sha256(content).hexdigest()
        self.catalog=catalog(l5x=sha);identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1)
        self.data=dict(name='own.L5X',content=base64.b64encode(content).decode(),native_project_identity=identity.manifest(),
                       native_metadata_definitions=self.catalog.definitions.manifest(),native_metadata_values=self.catalog.manifest())
        self.app.command('load',self.data)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def test_small_response_budgets_reassemble_source_and_never_change_model(self):
        before=copy.deepcopy(self.app.state());native=NativeSession();native.stage='bound'
        assembly=wire.Assembly();position=0
        while not assembly.complete:
            raw=query(position=position);response=self.endpoint.router.native_read(raw,Session(),native,0,37,None,registration=False)
            self.assertLessEqual(len(response),37);q,c,status=frame(raw,response);self.assertEqual(status,0)
            assembly.accept(q,c);position+=len(c.data)
        self.assertEqual(assembly.data(),self.catalog.body('all-objects'));self.assertIsNone(native.metadata_query)
        after=self.app.state()
        for key in ('tags','controller','scan','ms','routines','tasks','routine_edits'):self.assertEqual(after[key],before[key])
        self.assertEqual(self.endpoint.router.handle(query(),Session())[2],8)
        native=NativeSession();native.stage='bound'
        call=lambda raw,limit:self.endpoint.router.native_read(raw,Session(),native,0,limit,None,registration=False)
        self.assertEqual(call(query(),12)[2],0x1B);self.assertIsNone(native.metadata_query)
        self.assertEqual(call(query('controller-attribute-26'),11)[2],0x1B)
        self.assertEqual(call(query()[:-1],50)[2],3)
        self.assertIsNone(native.metadata_query)

    def test_cursors_cannot_cross_sessions_sources_or_selection_and_close_discards_them(self):
        a=NativeSession();a.stage='bound';b=NativeSession();b.stage='bound'
        call=lambda raw,n:self.endpoint.router.native_read(raw,Session(),n,0,50,None,registration=False)
        first=call(query(),a);q,c,_=frame(query(),first);position=len(c.data);self.assertIsNotNone(a.metadata_query)
        self.assertEqual(call(query(position=position),b)[2],12)
        self.assertEqual(call(query('controller-all',position),a)[2],12);self.assertIsNone(a.metadata_query)
        self.assertEqual(call(query(position=position),a)[2],12)
        call(query(),a);a.close();self.assertIsNone(a.metadata_query)
        a.stage='bound';call(query(),a)
        self.app.engine.project.runtime_revision=1
        self.assertEqual(call(query(position=position),a)[2],12)
        self.assertEqual(call(query('controller-all'),a)[2],12)
        self.assertEqual(call(query('controller-attribute-26'),a)[2],0)
        self.app.engine.project.runtime_revision=0;call(query(),a)
        self.app.generation+=1;self.assertEqual(call(query(position=position),a)[2],12)
        self.app.native_metadata_values=replace(self.catalog,source_acd_sha256='c'*64,definitions=replace(self.catalog.definitions,source_acd_sha256='c'*64))
        self.assertEqual(call(query(),a)[2],12)

    def test_source_load_validation_is_atomic_reset_retains_and_unbound_reload_clears(self):
        engine=self.app.engine
        for change in ({'source_acd_sha256':'c'*64},{'source_l5x_sha256':'c'*64},{'values_hex':'00'}):
            with self.assertRaises(ModelError):self.app.command('load',{**self.data,'native_metadata_values':{**self.catalog.manifest(),**change}})
            self.assertIs(self.app.engine,engine);self.assertEqual(self.app.native_metadata_values,self.catalog)
        with self.assertRaises(ModelError):self.app.command('load',{k:v for k,v in self.data.items() if k!='native_metadata_definitions'})
        self.app.command('reset',{});self.assertEqual(self.app.native_metadata_values,self.catalog)
        self.app.command('load',{k:v for k,v in self.data.items() if k!='native_metadata_values'})
        self.assertIsNone(self.app.native_metadata_values)

    def test_signed_tcp_reads_full_and_controller_streams_but_no_metadata_writes(self):
        self.endpoint.start();before=copy.deepcopy(self.app.state()['tags'])
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            for selection in ('all-objects','controller-all','controller-attribute-26'):
                assembly=wire.Assembly();position=0
                while not assembly.complete:
                    raw=query(selection,position);response=client.request(raw);q,c,status=frame(raw,response)
                    self.assertEqual(status,0);assembly.accept(q,c);position+=len(c.data)
                self.assertEqual(assembly.data(),self.catalog.body(selection))
            self.assertEqual(client.request(bytes.fromhex('4f03210049032400')+bytes(16))[2],15)
            self.assertEqual(client.request(bytes.fromhex('50022068240101011f0000000000'))[2],12)
        self.assertEqual(self.app.state()['tags'],before)
        self.assertTrue(self.endpoint.state()['metadata_values']['read_only'])
        self.assertTrue(self.endpoint.state()['metadata_definition']['metadata_values'])


if __name__=='__main__':unittest.main()
