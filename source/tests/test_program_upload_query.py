"""CRC-checked Program selector reads remain separate from project transfer."""
import hashlib
import json
import struct
import unittest
import copy
from dataclasses import replace
from logixlab import program_query
from logixlab.native_symbols import NativeSymbols
from logixlab.native_session import NativeSession
from logixlab.ethernetip import Session
import test_programming_lease as leases

from tools.program_upload_query import describe
from tools.analyze_native_transfer import analyze
from tools.inspect_cip_capture import summarize
from tools.upload_inventory import logical_path
from test_capture_inspection import packet
from test_native_transfer_trace import event
from test_signed_messages import request as signed_request,response as signed_response
from test_signed_batches import batch


def query(selector=31,instance=700,path=None):
    path=logical_path(0x68,instance) if path is None else path
    return bytes((0x50,len(path)//2))+path+struct.pack('<HHI',0x101,selector,0)


def response(selector=31,word=None):
    if word is None:word=program_query.checksum(struct.pack('<I',selector))
    return bytes.fromhex('d00000000103000008000000')+struct.pack('<II',word,selector)


class ProgramUploadQueryTests(unittest.TestCase):
    def test_observed_selectors_validate_only_the_returned_payload_checksum(self):
        for selector in (31,32,33):
            result=describe(query(selector),response(selector))
            self.assertEqual(result['selector'],selector);self.assertEqual(result['record_count'],1)
            self.assertEqual(result['status'],0);self.assertTrue(result['returned_selector_matches'])
            self.assertEqual(result['opaque_word_sha256'],hashlib.sha256(response(selector)[12:16]).hexdigest())
            self.assertTrue(result['checksum_verified'])
            self.assertEqual(result['checksum_scope'],'returned_selector_uint32')
            for key in ('source_binding_verified','mac_verified','native_acceptance_verified','payloads_exposed'):
                self.assertFalse(result[key])
            self.assertEqual(result['field_semantics'],'NOT INFERRED')
            self.assertNotIn('12345678',json.dumps(result));self.assertNotIn('2018915346',json.dumps(result))

    def test_rejected_query_preserves_status_without_guessing_a_result(self):
        result=describe(query(),bytes.fromhex('d0000f00'))
        self.assertEqual(result['status'],15);self.assertEqual(result['record_count'],0)
        self.assertIsNone(result['opaque_word_sha256']);self.assertIsNone(result['returned_selector_matches'])
        self.assertTrue(analyze({'events':[]},{'events':[event(query(),bytes.fromhex('d0000f00'))]},'upload')['analysis_complete'])

    def test_unknown_selectors_offsets_versions_scopes_and_padding_are_rejected(self):
        raw=query();end=2+2*raw[1]
        bad=[query(30),query(34),raw[:end]+struct.pack('<HHI',0x201,31,0),
             raw[:end]+struct.pack('<HHI',0x101,31,1),raw+b'\0',raw[:-1],
             query(instance=0),query(path=logical_path(0x70,700)),
             query(path=logical_path(0x68,1)+logical_path(0x68,700)),
             query(path=logical_path(0x68,700)+bytes.fromhex('3001')),
             bytes.fromhex('500320682501bc02')+raw[end:],b'\x50\xff'+bytes(8)]
        for value in bad:
            with self.subTest(value=value.hex()),self.assertRaises(ValueError):describe(value,response())
        for value in (None,bytearray(raw),'private project'):
            with self.assertRaises(ValueError):describe(value,response())

    def test_unknown_success_shapes_and_unechoed_selectors_are_not_normalized(self):
        valid=response()
        bad=[bytes.fromhex('d00000000103000000000000'),response(32),valid[:-1],valid+b'\0',
             response(word=0),response(word=program_query.checksum(struct.pack('<I',31))^1),
             valid[:4]+struct.pack('<II',0x101,8)+valid[12:],
             valid[:8]+struct.pack('<I',7)+valid[12:],bytes.fromhex('d0010000')+valid[4:],
             bytes.fromhex('d0000001')+valid[4:],bytes.fromhex('d1000000')+valid[4:],
             bytes.fromhex('d0000f00')+bytes(8)]
        for value in bad:
            with self.subTest(value=value.hex()),self.assertRaises(ValueError):describe(query(),value)

    def test_plain_signed_and_batch_capture_readers_agree_with_checkpoint_report(self):
        child=query();answer=response();expected=describe(child,answer)
        single=(signed_request(inner=child),signed_response(inner=answer))
        grouped=(batch((child,)),batch((answer,),response=True))
        for request,reply in ((child,answer),single,grouped):
            captured=summarize([packet(1,request),packet(2,reply,1)])['exchanges'][0]['response']
            if 'signed_envelope' in captured:
                envelope=captured['signed_envelope'];captured=envelope['inner'] if 'inner' in envelope else envelope['children'][0]
            self.assertEqual(captured['program_upload_query'],expected)
        report=analyze({'events':[]},{'events':[event(child,answer)]},'upload')
        self.assertTrue(report['analysis_complete']);self.assertEqual(report['program_upload_queries_observed'],1)
        self.assertEqual(report['program_upload_queries'][0]['program_upload_query'],expected)

    def test_unverified_empty_trial_is_retained_as_incomplete_framing(self):
        answer=bytes.fromhex('d00000000103000000000000')
        report=analyze({'events':[]},{'events':[event(query(),answer)]},'upload')
        self.assertFalse(report['analysis_complete']);self.assertEqual(report['unparsed_events'],0)
        self.assertEqual(report['program_upload_query_errors'],1);self.assertEqual(report['requests_observed'],1)
        self.assertEqual(report['program_upload_queries'][0]['program_upload_query']['structure'],'UNSUPPORTED OR MALFORMED')
        captured=summarize([packet(1,query()),packet(2,answer,1)])['exchanges'][0]['response']
        self.assertEqual(captured['program_upload_query']['structure'],'UNSUPPORTED OR MALFORMED')

    def test_full_counts_continue_after_report_retention_limit(self):
        events=[event(query(),response(),sequence=i) for i in range(70)]
        report=analyze({'events':[]},{'events':events},'upload')
        self.assertTrue(report['analysis_complete']);self.assertEqual(report['program_upload_queries_observed'],70)
        self.assertEqual(len(report['program_upload_queries']),64);self.assertTrue(report['program_upload_queries_truncated'])
        events[-1]=event(query(),response(32),sequence=69)
        report=analyze({'events':[]},{'events':events},'upload')
        self.assertFalse(report['analysis_complete']);self.assertEqual(report['program_upload_query_errors'],1)

    def test_class_and_parent_scope_requests_stay_outside_this_profile(self):
        for raw in (query(instance=0),query(path=logical_path(0x68,1)+logical_path(0x68,700))):
            report=analyze({'events':[]},{'events':[event(raw,bytes.fromhex('d0000f00'))]},'upload')
            self.assertTrue(report['analysis_complete']);self.assertEqual(report['program_upload_queries_observed'],0)
            captured=summarize([packet(1,raw),packet(2,bytes.fromhex('d0000f00'),1)])['exchanges'][0]['response']
            self.assertNotIn('program_upload_query',captured)

    def test_codec_checks_exact_query_extent_types_and_supported_selectors(self):
        for selector in program_query.SELECTORS:
            self.assertEqual(program_query.selection(struct.pack('<HHI',0x101,selector,0)),selector)
            self.assertEqual(bytes.fromhex('d0000000')+program_query.body(selector),response(selector))
        for value in (None,bytearray(8),bytes(7),bytes(9),struct.pack('<HHI',1,31,0),
                      struct.pack('<HHI',0x101,30,0),struct.pack('<HHI',0x101,31,1)):
            with self.assertRaises(ValueError):program_query.selection(value)
        for value in (True,31.0,None,0,30,34):
            with self.assertRaises(ValueError):program_query.body(value)


class ProgramSelectorWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def source(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':700}])

    def test_signed_reads_match_generated_crc_and_leave_model_audit_and_lease_unchanged(self):
        self.source();before=copy.deepcopy(self.app.state())
        for sequence,selector in enumerate(program_query.SELECTORS,4):
            self.assertEqual(self.signed(sequence,query(selector)),response(selector))
        after=self.app.state()
        for key in ('tags','routines','tasks','scan','ms','controller','routine_edits'):
            self.assertEqual(before[key],after[key])
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.assertTrue(self.endpoint.state()['program_upload_query']['read_only'])
        self.assertEqual(self.endpoint.router.handle(query(),Session())[2],8)
        self.assertEqual(self.signed(7,bytes((0x51,))+query()[1:])[2],15)

    def test_foreign_stale_missing_and_unknown_program_bindings_are_rejected(self):
        self.source();identity=self.app.native_project_identity
        self.assertEqual(self.signed(4,query(instance=701))[2],5)
        self.app.native_symbols=NativeSymbols('b'*64,self.app.engine.project.sha256,[],[{'name':'MainProgram','instance':700}])
        self.assertEqual(self.signed(5,query())[2],12)
        self.app.native_symbols=NativeSymbols('a'*64,'b'*64,[],[{'name':'MainProgram','instance':700}])
        self.assertEqual(self.signed(6,query())[2],12)
        self.app.native_project_identity=None
        self.assertEqual(self.signed(7,query())[2],12)
        self.app.native_project_identity=replace(identity,source_l5x_sha256='b'*64)
        self.assertEqual(self.signed(8,query())[2],12)

    def test_bad_paths_payloads_and_reply_budgets_do_not_acquire_authority(self):
        self.source();native=NativeSession();native.stage='bound'
        call=lambda raw,limit=20:self.endpoint.router.native_read(raw,Session(),native,0,limit,None,registration=False)
        for raw in (query(instance=0),query(path=logical_path(0x68,700)+bytes.fromhex('3001')),
                    query(path=logical_path(0x68,1)+logical_path(0x68,700))):
            self.assertEqual(call(raw)[2],4)
        for raw in (query(34),query()[:-1],query()+b'\0'):
            self.assertEqual(call(raw)[2],3)
        self.assertEqual(call(query(),19)[2],0x1B)
        self.assertEqual(call(query()),response())
        native.stage='operator';self.assertEqual(call(query())[2],15)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])


if __name__=='__main__':unittest.main()
