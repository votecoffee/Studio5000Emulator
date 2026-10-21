"""Original Type words, legacy availability, parent scopes and private framing."""
import base64
import copy
from dataclasses import FrozenInstanceError,replace
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_routines import NativeRoutines,routine_paths
from logixlab.native_aoi_routines import NativeAOIRoutines
from logixlab.native_aois import NativeAOIs
from logixlab.native_symbols import NativeSymbols
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import decode_attribute_list,CollectionError,scope_supported
from tools.upload_inventory import logical_path
from tools.analyze_native_transfer import analyze
from tools.inspect_cip_capture import summarize
from test_capture_inspection import packet
from test_native_transfer_trace import event
from test_native_routines import record,database,container,EXPECTED,PROGRAMS
import test_routine_metadata_wire as wire_tests
import test_native_aoi_routines as aoi_tests
from test_signed_messages import request as signed_request,response as signed_response
from test_signed_batches import batch


def typed_record(word=0x7ff,*,body_size=371,storage=(297,9,1,189),**kwargs):
    data=bytearray(record(**kwargs));data.extend(bytes(body_size-22))
    struct.pack_into('<I',data,2,len(data));struct.pack_into('<I',data,6,len(data)-6)
    if body_size>=92:
        struct.pack_into('<4I',data,6+148+74,*storage);struct.pack_into('<H',data,6+148+90,word)
    return bytes(data)


class RoutineTypeSourceTests(unittest.TestCase):
    def test_validated_profile_preserves_exact_word_and_unknown_layout_keeps_only_identity(self):
        for word in (0,0x7fc,0x7ff,65535):
            result=routine_paths(database(typed_record(word)),EXPECTED,PROGRAMS)
            self.assertEqual(result[0]['type_word'],word)
        for component in (typed_record(body_size=370),typed_record(body_size=418),record(),
                          typed_record(storage=(297,8,1,189)),typed_record(storage=(297,9,2,189)),
                          typed_record(storage=(297,9,1,188))):
            self.assertNotIn('type_word',routine_paths(database(component),EXPECTED,PROGRAMS)[0])
        self.assertEqual(routine_paths(database(typed_record(),typed_record(1,kind=0xfdfd)),EXPECTED,PROGRAMS)[0]['type_word'],0x7ff)

    def test_raw_and_compressed_original_acd_words_reach_program_and_aoi_manifests(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.ACD'
            for compressed in (False,True):
                raw=container(database(typed_record(0x7fc)),compressed);path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
                symbols=NativeSymbols(sha,'b'*64,[],[{'name':'ProgramA','instance':11}])
                binding=NativeRoutines.from_acd(path,'b'*64,EXPECTED,symbols)
                self.assertEqual(binding.lookup('ProgramA','Run').type_word,0x7fc)
                self.assertEqual(NativeRoutines.from_manifest(binding.manifest(),'b'*64).manifest(),binding.manifest())
                self.assertEqual(path.read_bytes(),raw)
            raw=container(database(typed_record(123,logical=(0x338,11,0x6d,7,0,0),component_type=259)));path.write_bytes(raw)
            parents=NativeAOIs(hashlib.sha256(raw).hexdigest(),'b'*64,[{'name':'AOI_A','instance':11}])
            binding=NativeAOIRoutines.from_acd(path,'b'*64,[{'aoi':'AOI_A','name':'Run'}],parents)
            self.assertEqual(binding.lookup('AOI_A','Run').type_word,123)
            self.assertEqual(NativeAOIRoutines.from_manifest(binding.manifest(),'b'*64).manifest(),binding.manifest())
            self.assertEqual(path.read_bytes(),raw)

    def test_optional_words_are_strict_immutable_and_never_added_to_legacy_manifests(self):
        base=dict(program='ProgramA',name='Run',program_instance=11,instance=7)
        legacy=NativeRoutines('a'*64,'b'*64,[base]);self.assertIsNone(legacy.rows[0].type_word)
        self.assertEqual(legacy.manifest()['routines'],[base]);self.assertEqual(legacy.description()['type_words_available'],0)
        for word in (True,None,-1,65536,1.5,'2047'):
            with self.assertRaises(ModelError):NativeRoutines('a'*64,'b'*64,[{**base,'type_word':word}])
            with self.assertRaises(ModelError):NativeAOIRoutines('a'*64,'b'*64,[dict(aoi='A',name='Run',aoi_instance=11,instance=7,type_word=word)])
        binding=NativeRoutines('a'*64,'b'*64,[{**base,'type_word':0x7ff}])
        with self.assertRaises(FrozenInstanceError):binding.rows[0].type_word=0
        manifest=binding.manifest();manifest['routines'][0]['type_word']=0
        self.assertEqual(binding.rows[0].type_word,0x7ff)


class RoutineTypeWireTests(unittest.TestCase):
    def setUp(self):
        wire_tests.RoutineMetadataWireTests.setUp(self)
        self.identity=NativeProjectIdentity('a'*64,self.digest,1,1,1,1,1,1)
        self.binding=NativeRoutines('a'*64,self.digest,[{**r.manifest(),'type_word':0x7ff if r.program_instance==10 else 0x7fc} for r in self.routines.rows])
        self.payload={**self.data,'native_project_identity':self.identity.manifest(),'native_symbols':self.symbols.manifest(),'native_routines':self.binding.manifest()}
        self.app.command('load',self.payload)
        from logixlab.ethernetip import Endpoint
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()

    tearDown=wire_tests.RoutineMetadataWireTests.tearDown

    def test_signed_reads_preserve_parent_specific_words_and_deny_modification(self):
        before=copy.deepcopy(self.app.state())
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            for parent,word in ((10,0x7ff),(20,0x7fc)):
                path=logical_path(0x6d,7,program=parent)
                self.assertEqual(client.request(bytes((14,(len(path)+2)//2))+path+b'\x30\1'),b'\x8e\0\0\0'+struct.pack('<H',word))
                answer=client.request(bytes((3,len(path)//2))+path+struct.pack('<4H',3,1,7,1))
                fields=decode_attribute_list(answer,(1,7,1),0x6d)['attributes']
                self.assertEqual(fields[0]['value_sha256'],hashlib.sha256(struct.pack('<H',word)).hexdigest())
                self.assertEqual(fields[0],fields[2])
                self.assertNotEqual(client.request(bytes((0x10,(len(path)+2)//2))+path+b'\x30\1\0\0')[2],0)
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_missing_foreign_and_stale_identity_withholds_type_without_inventing_default(self):
        from logixlab.ethernetip import Session
        query=bytes.fromhex('0e052068240a206d24073001')
        for identity in (None,replace(self.identity,source_acd_sha256='c'*64),replace(self.identity,source_l5x_sha256='c'*64)):
            self.app.native_project_identity=identity;self.assertEqual(self.endpoint.router.handle(query,Session())[2],0x14)
        self.app.native_project_identity=self.identity;self.app.native_routines=self.routines
        self.assertEqual(self.endpoint.router.handle(query,Session())[2],0x14)
        self.app.command('load',self.payload);self.app.command('reset',{})
        self.assertEqual(self.endpoint.router.handle(query,Session())[-2:],bytes.fromhex('ff07'))
        before=self.app.engine
        bad=copy.deepcopy(self.payload);bad['native_routines']['routines'][0]['type_word']=True
        with self.assertRaises(ModelError):self.app.command('load',bad)
        self.assertIs(self.app.engine,before)


class RoutineTypeDecoderTests(unittest.TestCase):
    def test_scoped_capture_and_transfer_framing_keeps_program_and_aoi_namespaces(self):
        answer=bytes.fromhex('83000000010001000000fc07')
        for scope in ('program','aoi'):
            path=logical_path(0x6d,7,**{scope:11});query=bytes((3,len(path)//2))+path+struct.pack('<2H',1,1)
            trace=analyze({'events':[]},{'events':[event(query,answer)]},'upload')
            self.assertTrue(trace['analysis_complete']);row=trace['collection_attribute_lists'][0]
            self.assertEqual(row[scope+'_instance'],11);self.assertEqual(row['collection_attribute_list']['attributes'][0]['value_bytes'],2)
            for q,a in ((query,answer),(signed_request(0x36,query),signed_response(0x36,answer)),(batch((query,)),batch((answer,),response=True))):
                response=summarize([packet(1,q),packet(2,a,1)])['exchanges'][0]['response']
                if 'signed_envelope' in response:
                    envelope=response['signed_envelope'];response=envelope.get('inner') or envelope['children'][0]
                self.assertEqual(response['collection_attribute_list']['attributes'][0]['value_bytes'],2)
                self.assertNotIn('data_hex',str(response))
        for path in (logical_path(0x6d,0),logical_path(0x6d,7),logical_path(0x68,0)+logical_path(0x6d,7)):
            query=bytes((3,len(path)//2))+path+struct.pack('<2H',1,1)
            response=summarize([packet(1,query),packet(2,answer,1)])['exchanges'][0]['response']
            self.assertNotIn('collection_attribute_list',response)
        self.assertFalse(scope_supported(0x6d));self.assertFalse(scope_supported(0x6d,program_instance=1,aoi_instance=1))
        self.assertFalse(scope_supported(0x6d,program_instance=True));self.assertFalse(scope_supported(0x3b0,program_instance=1))

    def test_truncated_unknown_successful_and_overlong_description_fields_fail_framing(self):
        raw=bytes.fromhex('83000000020001000000ff07070000000300')+b'abc'
        for end in range(len(raw)):
            with self.assertRaises(CollectionError):decode_attribute_list(raw[:end],(1,7),0x6d)
        for data,attrs in ((raw+b'\0',(1,7)),(bytes.fromhex('8300000001000500000000000000'),(5,)),
                           (bytes.fromhex('830000000100070000008100')+bytes(129),(7,))):
            with self.assertRaises(CollectionError):decode_attribute_list(data,attrs,0x6d)


class RoutineTypeAOITests(unittest.TestCase):
    setUp=aoi_tests.AOIRoutineTcpTests.setUp
    tearDown=aoi_tests.AOIRoutineTcpTests.tearDown
    request=aoi_tests.AOIRoutineTcpTests.request

    def test_signed_type_words_follow_the_aoi_parent_and_matching_project_identity(self):
        binding=NativeAOIRoutines(self.binding.source_acd_sha256,self.binding.source_l5x_sha256,
            [{**row.manifest(),'type_word':0x7ff if row.aoi_instance==700 else 0x7fc} for row in self.binding.rows])
        self.app.command('load',{**self.data,'native_aoi_routines':binding.manifest()})
        before=copy.deepcopy(self.app.state())
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            for parent,word in ((700,0x7ff),(701,0x7fc)):
                self.assertEqual(client.request(self.request(14,parent,7,1)),b'\x8e\0\0\0'+struct.pack('<H',word))
            self.app.native_project_identity=None
            self.assertEqual(client.request(self.request(14,700,7,1))[2],0x0c)
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])


if __name__=='__main__':unittest.main()
