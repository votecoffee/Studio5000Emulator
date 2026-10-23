"""Bounded v35 Executable Name reads with original parent/source bindings."""
import copy
from dataclasses import replace
import struct
import unittest

from logixlab.ethernetip import Session
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import decode_attribute_list,CollectionError
from tools.upload_inventory import logical_path
from tools.analyze_native_transfer import analyze
from tools.inspect_cip_capture import summarize
from test_capture_inspection import packet
from test_native_transfer_trace import event
import test_native_routine_types as types
import test_native_aoi_routines as aois


def request(service,parent=10,instance=7,attribute=None,payload=b''):
    path=logical_path(0x6d,instance,program=parent)
    if attribute is not None:path+=bytes((0x30,attribute))
    return bytes((service,len(path)//2))+path+payload


class RoutineNameTests(unittest.TestCase):
    setUp=types.RoutineTypeWireTests.setUp
    tearDown=types.RoutineTypeWireTests.tearDown

    def test_signed_single_duplicate_and_mixed_reads_preserve_execution_and_audit(self):
        before=copy.deepcopy(self.app.state())
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            for parent in (10,20):
                value=struct.pack('<I',11)+b'MainRoutine'
                self.assertEqual(client.request(request(14,parent,attribute=25)),b'\x8e\0\0\0'+value)
                order=(25,29,25)
                raw=client.request(request(3,parent,payload=struct.pack('<4H',3,*order)))
                rows=decode_attribute_list(raw,order,0x6d,include_payloads=True)['attributes']
                self.assertEqual([row['status'] for row in rows],[0,20,0])
                self.assertEqual(bytes.fromhex(rows[0]['data_hex']),value);self.assertEqual(rows[0],rows[2])
                self.assertEqual(client.request(request(0x10,parent,attribute=25,payload=value))[2],15)
        after=self.app.state()
        for key in ('tags','controller','scan','ms','routines','tasks','routine_edits'):self.assertEqual(after[key],before[key])
        self.assertFalse(after['connectivity']['native_programming_lease']['owned'])

    def test_missing_foreign_and_stale_identities_withhold_names(self):
        query=request(14,attribute=25)
        for identity in (None,replace(self.identity,source_acd_sha256='c'*64),replace(self.identity,source_l5x_sha256='c'*64)):
            self.app.native_project_identity=identity
            self.assertEqual(self.endpoint.router.handle(query,Session())[2],20)
        self.app.native_project_identity=self.identity
        for parent,child in ((99,7),(10,99),(20,99)):
            self.assertEqual(self.endpoint.router.handle(request(14,parent,child,25),Session())[2],5)
        self.app.command('load',self.data)
        self.assertNotEqual(self.endpoint.router.handle(query,Session())[2],0)

    def test_names_are_bounded_exact_ascii_and_independent_of_type_word(self):
        router=self.endpoint.router;binding=self.app.native_routines
        for text in ('A','A'*40,'Mixed_Case9'):
            values=router.routine_identity_attributes(binding,None,7,text)
            self.assertEqual(values[25],struct.pack('<I',len(text))+text.encode('ascii'))
            self.assertNotIn(1,values)
        for text in ('','A'*41,'é','9Bad','Bad\0Name','Bad\n',None,7):
            self.assertNotIn(25,router.routine_identity_attributes(binding,None,7,text))
        for query in (request(14,10,attribute=25),request(14,20,attribute=25)):
            self.assertEqual(router.handle(query,Session(),limit=8)[2],27)
        self.assertEqual(router.handle(bytes.fromhex('0e03206d24073019'),Session())[2],4)
        self.assertEqual(router.handle(request(14,instance=0,attribute=25),Session())[2],20)

    def test_known_name_does_not_assert_clean_execution_or_unchanged_logic(self):
        engine=self.app.engine;engine.project.runtime_revision=1
        engine.project.runtime_edited_routines=('MainProgram/MainRoutine',)
        engine.fault='Unclassified simulated fault'
        self.assertEqual(self.endpoint.router.handle(request(14,attribute=25),Session()),
            b'\x8e\0\0\0'+struct.pack('<I',11)+b'MainRoutine')
        self.assertEqual(self.endpoint.router.handle(request(14,attribute=2),Session())[2],20)


class AOIRoutineNameTests(unittest.TestCase):
    setUp=aois.AOIRoutineTcpTests.setUp
    tearDown=aois.AOIRoutineTcpTests.tearDown
    request=aois.AOIRoutineTcpTests.request

    def test_bound_aoi_names_preserve_parent_scope_and_protected_children_stay_unavailable(self):
        before=copy.deepcopy(self.app.state())
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            for row in self.binding.rows:
                self.assertEqual(client.request(self.request(14,row.aoi_instance,row.instance,25)),
                    b'\x8e\0\0\0'+struct.pack('<I',len(row.name))+row.name.encode('ascii'))
            self.assertEqual(client.request(self.request(14,703,7,25))[2],12)
            self.assertEqual(client.request(self.request(14,700,99,25))[2],5)
            self.app.native_project_identity=None
            self.assertEqual(client.request(self.request(14,700,7,25))[2],12)
        after=self.app.state()
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(after[key],before[key])


class RoutineNameFramingTests(unittest.TestCase):
    def test_exact_udint_length_and_both_scope_decoders_omit_names_by_default(self):
        value=struct.pack('<I',5)+b'Logic';raw=b'\x83\0\0\0'+struct.pack('<3H',1,25,0)+value
        for scope in ('program','aoi'):
            path=logical_path(0x6d,7,**{scope:11});query=bytes((3,len(path)//2))+path+struct.pack('<2H',1,25)
            report=analyze({'events':[]},{'events':[event(query,raw)]},'upload')
            self.assertTrue(report['analysis_complete']);row=report['collection_attribute_lists'][0]
            self.assertEqual(row[scope+'_instance'],11);self.assertEqual(row['collection_attribute_list']['attributes'][0]['value_bytes'],9)
            capture=summarize([packet(1,query),packet(2,raw,1)])
            self.assertNotIn('Logic',str(report));self.assertNotIn('Logic',str(capture))
        for count in (0,1,40):
            answer=raw[:10]+struct.pack('<I',count)+b'A'*count
            self.assertEqual(decode_attribute_list(answer,(25,),0x6d)['attributes'][0]['value_bytes'],4+count)
        for bad in (raw+b'\0',raw[:10]+struct.pack('<I',41)+b'A'*41,raw[:10]+struct.pack('<I',0xffffffff)):
            with self.assertRaises(CollectionError):decode_attribute_list(bad,(25,),0x6d)
        for end in range(len(raw)):
            with self.assertRaises(CollectionError):decode_attribute_list(raw[:end],(25,),0x6d)


if __name__=='__main__':unittest.main()
