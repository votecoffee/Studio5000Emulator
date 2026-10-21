"""Synthetic CMS batches: structure is inspected, operations never executed."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

from logixlab import device_payload as dp
from logixlab.ethernetip import decode_path,CIPError
from logixlab.resilient_transport import DEVICE_HEADER,ResilientTransport,TransportError,ASSEMBLY_SECONDS
from logixlab.signed_messages import FragmentEnvelope
from tools.inspect_device_payload import run
import test_transport_fragments as fragments
import test_resilient_transport as transport
import test_programming_lease as leases
import test_programming_preparation as prep
import test_run_inhibit as inhibits
import test_template_staging as templates
import test_diagnostic_staging as diagnostics
import test_object_staging as objects
from test_signed_messages import request


def tlv(tag,value):
    size=len(value);width=(size.bit_length()+7)//8
    length=bytes((size,)) if size<128 else bytes((0x80|width,))+size.to_bytes(width,'big')
    return bytes((tag,))+length+value


def container(compressed,*,version=b'\0',algorithm=dp.ZLIB_OID,content=dp.CONTENT_OID,null=b'',extra=b''):
    body=tlv(2,version)+tlv(0x30,tlv(6,algorithm)+null)+tlv(0x30,tlv(6,content)+tlv(0xA0,tlv(4,compressed)))
    return tlv(0x30,tlv(6,dp.COMPRESSED_OID)+tlv(0xA0,tlv(0x30,body))+extra)


def record(raw):return struct.pack('<I',len(raw))+raw
GLOBAL=bytes.fromhex('0802207e2401')+b'PrivateDefinition'
SCOPED=bytes.fromhex('080420682401207f2402')+b'PrivateRoutine'
EXPANDED=record(GLOBAL)+record(SCOPED)
ENCODED=container(zlib.compress(EXPANDED))
TEMPLATE_EXPANDED=b''.join(record(r.request) for r in templates.batch()+objects.batch())+record(diagnostics.request().request)+record(SCOPED)
TEMPLATE_ENCODED=container(zlib.compress(TEMPLATE_EXPANDED))
INSPECT=bytes.fromhex('0603210012042400')


def fill(stage,encoded=ENCODED,expanded=EXPANDED):
    stage.open(transport.payload(opaque=len(expanded)));cut=len(encoded)//2
    stage.accept(FragmentEnvelope(0x39,7,DEVICE_HEADER+encoded[:cut],0x101,len(encoded)))
    stage.accept(FragmentEnvelope(0x39,8,encoded[cut:],0x201,cut))


class PayloadCodecTests(unittest.TestCase):
    def test_observed_profile_null_algorithm_parameters_and_scopes_round_trip_structurally(self):
        for null in (b'',tlv(5,b'')):
            batch=dp.decode(container(zlib.compress(EXPANDED),null=null),len(EXPANDED))
            self.assertEqual([r.request for r in batch],[GLOBAL,SCOPED])
            self.assertEqual([(s.class_id,s.instance) for s in batch[1].scopes],[(0x68,1),(0x7F,2)])
            report=dp.summary(batch,len(EXPANDED));self.assertEqual((report['record_count'],report['scoped_records']),(2,1))
            self.assertFalse(report['execution_supported'] or report['signature_verified']);self.assertEqual(report['records_executed'],0)
            for secret in ('PrivateDefinition','PrivateRoutine',GLOBAL.hex()):self.assertNotIn(secret,json.dumps(report))
        with self.assertRaises(CIPError):decode_path(SCOPED[2:10])

    def test_container_truncation_and_nonminimal_or_indefinite_lengths_are_rejected(self):
        for size in range(len(ENCODED)):
            with self.subTest(size=size),self.assertRaises(dp.PayloadError):dp.decode(ENCODED[:size],len(EXPANDED))
        for raw in (ENCODED+b'\0',b'\x30\x80'+ENCODED[2:]+b'\0\0',b'\x30\x81'+ENCODED[1:],
                b'\x30\x84'+bytes(4),container(zlib.compress(EXPANDED),extra=tlv(5,b''))):
            with self.assertRaises(dp.PayloadError):dp.decode(raw,len(EXPANDED))

    def test_unknown_profiles_versions_parameters_and_content_are_rejected(self):
        for kwargs in ({'version':b'\1'},{'version':b'\0\0'},{'algorithm':dp.ZLIB_OID[:-1]+b'\1'},
                {'content':dp.CONTENT_OID[:-1]+b'\1'},{'null':tlv(5,b'\0')},{'null':tlv(5,b'')*2}):
            with self.subTest(kwargs=kwargs),self.assertRaises(dp.PayloadError):dp.decode(container(zlib.compress(EXPANDED),**kwargs),len(EXPANDED))

    def test_decompression_is_bounded_exact_and_rejects_trailing_concatenated_and_broken_streams(self):
        for expected in (len(EXPANDED)-1,len(EXPANDED)+1):
            with self.assertRaises(dp.PayloadError):dp.decode(ENCODED,expected)
        compressed=zlib.compress(EXPANDED)
        for data in (compressed[:-1],compressed+b'\0',compressed+compressed,bytes(len(compressed))):
            with self.assertRaises(dp.PayloadError):dp.decode(container(data),len(EXPANDED))
        bomb=container(zlib.compress(b'A'*(dp.MAX_EXPANDED_BYTES+1)))
        with self.assertRaises(dp.PayloadError):dp.decode(bomb,dp.MAX_EXPANDED_BYTES)
        for raw,expected in ((ENCODED,True),(ENCODED,0),(ENCODED,dp.MAX_EXPANDED_BYTES+1),
                (b'A'*(dp.MAX_ENCODED_BYTES+1),1),(bytearray(ENCODED),len(EXPANDED))):
            with patch('logixlab.device_payload.zlib.decompressobj') as decoder,self.assertRaises(dp.PayloadError):dp.decode(raw,expected)
            decoder.assert_not_called()

    def test_record_count_lengths_header_and_late_malformed_records_fail_closed(self):
        raw=record(bytes.fromhex('050220012401'))
        self.assertEqual(len(dp.records(raw*dp.MAX_RECORDS)),dp.MAX_RECORDS)
        for value in (raw*(dp.MAX_RECORDS+1),b'',EXPANDED+b'\0',EXPANDED[:-1],EXPANDED+struct.pack('<I',dp.MAX_RECORD_BYTES+1),
                record(b'\x85\0'),record(b'\x05\xFF'),record(b'\0\0'),record(b'\x05\0')):
            with self.assertRaises(dp.PayloadError):dp.records(value)

    def test_exact_expansion_capacity_is_accepted_with_bounded_record_lengths(self):
        prefix=bytes.fromhex('0802206c2401');unit=record(prefix+b'A'*(dp.MAX_RECORD_BYTES-len(prefix)))
        count,left=divmod(dp.MAX_EXPANDED_BYTES,len(unit))
        expanded=unit*count+record(prefix+b'Z'*(left-4-len(prefix)))
        self.assertEqual(len(expanded),dp.MAX_EXPANDED_BYTES)
        batch=dp.decode(container(zlib.compress(expanded)),len(expanded));self.assertEqual(len(batch),count+1)

    def test_paths_preserve_parents_validate_symbols_and_bound_scope_count(self):
        path=bytes.fromhex('20682401')*dp.MAX_SCOPES
        self.assertEqual(len(dp.record_path(path)),dp.MAX_SCOPES)
        symbol=bytes.fromhex('206b24019103')+b'ABC\0'+bytes.fromhex('2801')
        self.assertTrue(dp.record_path(symbol)[0].symbolic)
        for raw in (path+bytes.fromhex('20682401'),bytes.fromhex('206824013001206d2401'),
                bytes.fromhex('206824012401'),bytes.fromhex('2068'),bytes.fromhex('0100'),
                bytes.fromhex('21682401'),symbol[:-1],symbol.replace(b'ABC\0',b'ABCx')):
            with self.subTest(raw=raw),self.assertRaises(dp.PayloadError):dp.record_path(raw)


class InspectionModelTests(unittest.TestCase):
    def test_source_member_verification_is_atomic_cached_and_clears_on_expiry(self):
        from test_native_types import catalog,staged
        rows=[]
        for t in staged():
            raw=t.definition+b'\0'*(-len(t.definition)%4)
            records=list(templates.batch(t.instance,raw));records[1]=templates.request(4,templates.attrs(members=t.attributes.members,size=t.attributes.structure_bytes),t.instance)
            rows.extend(records)
        expanded=b''.join(record(r.request) for r in rows)
        native=catalog();fill(self.stage,container(zlib.compress(expanded)),expanded)
        with patch.object(native,'verify',wraps=native.verify) as verify:
            self.stage.inspect_payload(native);self.stage.inspect_payload(native);self.assertEqual(verify.call_count,1)
        value=self.stage.description()['source_type_verification'];self.assertEqual(value['status'],'matched')
        self.assertEqual(value['members_matched'],6);self.assertEqual(self.stage.inspection['records_executed'],0)
        with self.assertRaises(TransportError):self.stage.inspect_payload(catalog())
        self.now+=ASSEMBLY_SECONDS
        self.assertEqual(self.stage.description()['source_type_verification']['status'],'idle')
        self.assertIsNone(self.stage._type_catalog)

    def test_source_mismatch_publishes_no_completed_stages_and_caches_redacted_failure(self):
        from test_native_types import catalog,source_types
        from dataclasses import replace
        t=source_types()[0];bad=replace(t,members=(replace(t.members[0],name='Different'),))
        native=catalog(types=(bad,))
        from test_template_layout import definition
        raw=definition(header=b'Inner;n');raw+=b'\0'*(-len(raw)%4)
        expanded=b''.join(record(r.request) for r in templates.batch(0x101,raw))
        fill(self.stage,container(zlib.compress(expanded)),expanded)
        with patch.object(native,'verify',wraps=native.verify) as verify:
            for _ in range(2):
                with self.assertRaises(TransportError) as error:self.stage.inspect_payload(native)
                self.assertEqual(error.exception.reason,'source_type_verification_failed')
            self.assertEqual(verify.call_count,1)
        report=self.stage.description();self.assertEqual(report['source_type_verification']['status'],'mismatch')
        self.assertEqual(report['template_staging']['templates'],0)
        self.assertEqual(report['object_staging']['records_modeled'],0);self.assertEqual(report['diagnostic_staging']['messages'],0)
        report['source_type_verification']['errors'][0]['reason']='mutated'
        self.assertNotEqual(self.stage.description()['source_type_verification']['errors'][0]['reason'],'mutated')
        self.stage.clear_fragments();self.assertIsNone(self.stage.type_error)

    def setUp(self):self.now=100.;self.stage=ResilientTransport(lambda:self.now)

    def test_completed_payload_inspection_is_cached_and_summary_is_defensive(self):
        with self.assertRaises(TransportError):self.stage.inspect_payload()
        fill(self.stage)
        with patch('logixlab.resilient_transport.device_payload.decode',wraps=dp.decode) as decoder:
            self.stage.inspect_payload();self.stage.inspect_payload();self.assertEqual(decoder.call_count,1)
        snapshot=self.stage.description();snapshot['inspection']['operations'][0]['count']=999
        self.assertEqual(self.stage.description()['inspection']['record_count'],2)
        self.assertNotEqual(self.stage.description()['inspection']['operations'][0]['count'],999)
        self.assertFalse(self.stage.description()['payload_transfer']);self.assertEqual(self.stage.inspection['records_executed'],0)
        self.now+=ASSEMBLY_SECONDS;self.assertEqual(self.stage.description()['inspection']['status'],'idle')

    def test_expiry_clears_both_completed_object_models(self):
        fill(self.stage,TEMPLATE_ENCODED,TEMPLATE_EXPANDED);self.stage.inspect_payload()
        self.assertEqual(self.stage.templates.description()['templates'],1);self.assertEqual(self.stage.diagnostics.description()['messages'],1)
        self.assertEqual(self.stage.objects.description()['records_modeled'],7)
        self.now+=ASSEMBLY_SECONDS
        self.assertEqual(self.stage.description()['diagnostic_staging']['status'],'idle');self.assertEqual(self.stage.templates.templates,())
        self.assertEqual(self.stage.objects.records,0)

    def test_invalid_inspection_caches_a_redacted_reason_until_the_assembly_clears(self):
        fill(self.stage,b'broken-container',b'unknown')
        with patch('logixlab.resilient_transport.device_payload.decode',wraps=dp.decode) as decoder:
            for _ in range(2):
                with self.assertRaises(TransportError) as error:self.stage.inspect_payload()
                self.assertEqual(error.exception.status,3)
            self.assertEqual(decoder.call_count,1)
        self.assertEqual(self.stage.inspection['status'],'invalid');self.assertNotIn('broken-container',json.dumps(self.stage.description()))
        self.stage.clear_fragments();self.assertEqual(self.stage.inspection['status'],'idle')

    def test_late_template_failure_is_atomic_cached_and_cleanup_clears_error(self):
        expanded=TEMPLATE_EXPANDED+record(templates.batch(2)[0].request)
        fill(self.stage,container(zlib.compress(expanded)),expanded)
        with patch('logixlab.resilient_transport.TemplateStaging.from_batch',wraps=templates.ts.TemplateStaging.from_batch) as builder:
            for _ in range(2):
                with self.assertRaises(TransportError) as error:self.stage.inspect_payload()
                self.assertEqual(error.exception.reason,'incomplete_template_definition')
            self.assertEqual(builder.call_count,1)
        state=self.stage.description()['template_staging']
        self.assertEqual(state['status'],'invalid');self.assertEqual(state['templates'],0)
        self.assertEqual(self.stage.description()['inspection']['status'],'decoded')
        self.stage.clear_fragments();self.assertEqual(self.stage.description()['template_staging']['status'],'idle')

    def test_late_diagnostic_failure_discards_templates_and_diagnostics_together_and_caches_reason(self):
        expanded=TEMPLATE_EXPANDED+record(diagnostics.request().request)
        fill(self.stage,container(zlib.compress(expanded)),expanded)
        with patch('logixlab.resilient_transport.DiagnosticStaging.from_batch',wraps=diagnostics.ds.DiagnosticStaging.from_batch) as builder:
            for _ in range(2):
                with self.assertRaises(TransportError) as error:self.stage.inspect_payload()
                self.assertEqual(error.exception.reason,'duplicate_diagnostic_message')
            self.assertEqual(builder.call_count,1)
        self.assertEqual(self.stage.templates.templates,());self.assertEqual(self.stage.diagnostics.messages,())
        self.assertEqual(self.stage.description()['diagnostic_staging']['status'],'invalid')
        self.assertEqual(self.stage.description()['template_staging']['status'],'idle')
        self.assertNotIn('PrivateMessage',json.dumps(self.stage.description()))
        self.stage.clear_fragments();self.assertEqual(self.stage.description()['diagnostic_staging']['status'],'idle')

    def test_late_object_reference_failure_discards_all_models_and_caches_reason(self):
        expanded=TEMPLATE_EXPANDED+record(objects.symbol(3,4).request)
        fill(self.stage,container(zlib.compress(expanded)),expanded)
        with patch('logixlab.resilient_transport.ObjectStaging.from_batch',wraps=objects.os.ObjectStaging.from_batch) as builder:
            for _ in range(2):
                with self.assertRaises(TransportError) as error:self.stage.inspect_payload()
                self.assertEqual(error.exception.reason,'symbol_table_reference_mismatch')
            self.assertEqual(builder.call_count,1)
        self.assertEqual(self.stage.templates.templates,());self.assertEqual(self.stage.diagnostics.messages,());self.assertEqual(self.stage.objects.records,0)
        self.assertEqual(self.stage.description()['object_staging']['status'],'invalid')
        self.stage.clear_fragments();self.assertEqual(self.stage.description()['object_staging']['status'],'idle')


class InspectionSignedTests(unittest.TestCase):
    def object_source_fixture(self,*,extra_symbol=False):
        from test_source_object_verification import bindings
        from test_download_image import batch
        from test_native_types import catalog,source_types
        rows=batch()+(objects.symbol(instance=9,table=objects.os.NULL_REFERENCE),) if extra_symbol else batch()
        self.stage(b''.join(record(row.request) for row in rows))
        identity=self.app.native_project_identity
        self.app.native_types=catalog(acd=identity.source_acd_sha256,l5x=self.app.engine.project.sha256,types=source_types()[:1])
        self.app.native_symbols,self.app.native_routines=bindings(acd=identity.source_acd_sha256,l5x=self.app.engine.project.sha256)

    def test_signed_original_object_identity_match_and_unresolved_symbols_are_separate(self):
        self.object_source_fixture(extra_symbol=True);before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.send(INSPECT),bytes.fromhex('86000000'))
        report=self.description()['source_object_verification']
        self.assertEqual((report['status'],report['symbols_matched'],report['symbols_unresolved']),('partial',2,1))
        self.assertEqual(self.endpoint.counts['native_source_object_verification'],1)
        self.assertEqual(self.send(bytes.fromhex('4d03210012042400'))[2],15)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.send(transport.DELETE);self.assertEqual(self.description()['source_object_verification']['status'],'idle')

    def test_signed_mismatched_source_object_ids_never_publish_temporary_resources(self):
        from logixlab.native_routines import NativeRoutines
        self.object_source_fixture();before=copy.deepcopy(self.app.engine.memory.values)
        binding=self.app.native_routines
        self.app.native_routines=NativeRoutines(binding.source_acd_sha256,binding.source_l5x_sha256,
            [dict(program='ProgramA',name='Logic',program_instance=2,instance=9)])
        for _ in range(2):self.assertEqual(self.send(INSPECT)[2],3)
        state=self.description();self.assertEqual(state['source_object_verification']['status'],'mismatch')
        self.assertEqual(state['object_staging']['records_modeled'],0);self.assertEqual(state['template_staging']['templates'],0)
        self.assertEqual(state['download_image']['storage_bytes'],0)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertTrue(any(row['reason']=='source_object_verification_failed' for row in self.endpoint.state()['native_rejections']))

    def test_signed_result_query_rejects_a_mutated_cached_source_binding(self):
        self.object_source_fixture();self.assertEqual(self.send(INSPECT)[2],0)
        self.app.native_symbols.program_ids[3]='Other'
        self.assertEqual(self.send(bytes.fromhex('4d03210012042400'))[2],12)
        self.assertEqual(self.send(INSPECT)[2],12)
        self.assertTrue(any(row['reason']=='native_object_binding_changed' for row in self.endpoint.state()['native_rejections']))

    def test_signed_source_comparison_checks_binding_then_starts_temporary_image(self):
        from test_native_types import catalog,source_types
        from test_template_layout import definition
        raw=definition(header=b'Inner;n');raw+=b'\0'*(-len(raw)%4)
        self.stage(b''.join(record(r.request) for r in templates.batch(0x101,raw)))
        identity=self.app.native_project_identity
        self.app.native_types=catalog(acd='f'*64,l5x=self.app.engine.project.sha256,types=source_types()[:1])
        self.assertEqual(self.send(INSPECT)[2],12)
        self.app.native_types=catalog(acd=identity.source_acd_sha256,l5x=self.app.engine.project.sha256,types=source_types()[:1])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.send(INSPECT),bytes.fromhex('86000000'))
        self.assertTrue(self.description()['download_image']['preparation_started'])
        result=self.description()['source_type_verification'];self.assertTrue(result['member_locations_verified'])
        self.assertEqual(result['members_matched'],1)
        events=[e for e in self.endpoint.state(True)['events'] if e['kind']=='native_source_type_verification']
        self.assertEqual(len(events),1);self.assertNotIn('Inner',json.dumps(events))
        for field in ('tags','scan','ms','mode','changes'):self.assertEqual(self.app.state()[field],before[field])
        self.send(transport.DELETE);self.assertEqual(self.description()['source_type_verification']['status'],'idle')

    def test_decoded_members_emit_private_summary_and_still_deny_execution(self):
        from test_template_layout import definition
        raw=definition(((31,0xC1,0xF0000000),),trailer=b'PrivateTrailer')
        raw+=b'\0'*(-len(raw)%4)
        self.stage(b''.join(record(r.request) for r in templates.batch(data=raw)))
        before=copy.deepcopy(self.app.state());identity=self.app.native_project_identity.manifest()
        for _ in range(2):self.assertEqual(self.send(INSPECT),bytes.fromhex('86000f00'))
        state=self.description()['template_staging']['layout_inspection']
        self.assertEqual(state['status'],'decoded');self.assertEqual(state['members_decoded'],1)
        self.assertEqual(state['encoded_offset_members'],1);self.assertFalse(state['storage_mapping_supported'])
        events=[e for e in self.endpoint.state(True)['events'] if e['kind']=='native_template_layout_inspection']
        self.assertEqual(len(events),2)
        for text in ('Example','Value','PrivateTrailer',raw.hex()):self.assertNotIn(text,json.dumps(events))
        for field in ('tags','scan','ms','mode','changes'):self.assertEqual(self.app.state()[field],before[field])
        self.assertEqual(self.app.native_project_identity.manifest(),identity)
        self.send(transport.DELETE)
        self.assertEqual(self.description()['template_staging']['layout_inspection']['status'],'idle')

    setUp=fragments.FragmentSignedTests.setUp
    tearDown=fragments.FragmentSignedTests.tearDown
    cip=fragments.FragmentSignedTests.cip
    begin=fragments.FragmentSignedTests.begin
    signed=fragments.FragmentSignedTests.signed
    bind=fragments.FragmentSignedTests.bind
    prepare=fragments.FragmentSignedTests.prepare
    second_client=fragments.FragmentSignedTests.second_client
    send=fragments.FragmentSignedTests.send
    acquire=fragments.FragmentSignedTests.acquire
    ready=fragments.FragmentSignedTests.ready
    description=fragments.FragmentSignedTests.description
    fragment=fragments.FragmentSignedTests.fragment

    def stage(self,expanded=TEMPLATE_EXPANDED):
        encoded=container(zlib.compress(expanded))
        self.ready();self.send(transport.SETUP[:8]+transport.payload(opaque=len(expanded)));cut=len(encoded)//2
        self.fragment(0x101,len(encoded),DEVICE_HEADER+encoded[:cut]);self.fragment(0x201,cut,encoded[cut:])

    def test_native_inspection_records_structure_but_returns_execution_denial_and_preserves_model(self):
        self.stage();before=copy.deepcopy(self.app.state());identity=self.app.native_project_identity.manifest()
        self.assertEqual(self.send(INSPECT),bytes.fromhex('86000f00'))
        state=self.description()['inspection'];self.assertEqual(state['status'],'decoded');self.assertEqual(state['record_count'],12)
        self.assertFalse(state['execution_supported']);self.assertEqual(state['records_executed'],0)
        self.assertEqual(self.endpoint.counts['native_transport_inspection'],1)
        self.assertEqual(self.endpoint.counts['native_template_staging'],1)
        staged=self.description()['template_staging'];self.assertEqual(staged['templates'],1);self.assertEqual(staged['records_modeled'],3)
        self.assertEqual(staged['definition_bytes'],12);self.assertEqual(staged['unsupported_records'],9)
        self.assertEqual(staged['layout_inspection']['status'],'invalid')
        self.assertEqual(self.endpoint.counts['native_template_layout_inspection'],1)
        self.assertEqual(self.endpoint.counts['native_diagnostic_staging'],1)
        staged=self.description()['diagnostic_staging'];self.assertEqual(staged['messages'],1);self.assertEqual(staged['records_modeled'],1)
        staged=self.description()['object_staging'];self.assertEqual(staged['records_modeled'],7);self.assertTrue(staged['references_validated'])
        self.assertEqual(self.endpoint.counts['native_object_staging'],1)
        self.assertEqual(self.endpoint.state()['native_rejections'][0]['reason'],'source_bound_device_image_required')
        for field in ('tags','scan','ms','mode','changes'):self.assertEqual(self.app.state()[field],before[field])
        self.assertEqual(self.app.native_project_identity.manifest(),identity)

    def test_prepared_download_allocates_real_readback_and_identifies_missing_result_encoding(self):
        from test_download_image import batch
        from test_native_types import catalog,source_types
        self.stage(b''.join(record(row.request) for row in batch()))
        self.app.native_types=catalog(acd=self.app.native_project_identity.source_acd_sha256,
            l5x=self.app.engine.project.sha256,types=source_types()[:1])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.send(INSPECT),bytes.fromhex('86000000'))
        image=self.endpoint.programming_lease.transport.download_image
        self.assertEqual(image.read_table(1,0,4,image.source),bytes(4))
        self.assertEqual(image.read_symbol(0,1,0,4,image.source),bytes(4))
        self.assertEqual(self.send(INSPECT),bytes.fromhex('86000000'))
        self.assertIs(image,self.endpoint.programming_lease.transport.download_image)
        self.assertEqual(self.send(bytes.fromhex('4d03210012042400'))[2],15)
        self.assertEqual(self.endpoint.counts['native_download_result_query'],1)
        self.assertTrue(any(r['reason']=='device_image_result_encoding_unavailable'
                            for r in self.endpoint.state()['native_rejections']))
        self.assertEqual(self.send(bytes.fromhex('4d03210012042400')+b'\0')[2],0x15)
        self.assertEqual(self.send(bytes.fromhex('4d03210012042401'))[2],5)
        state=self.description()['download_image']
        self.assertTrue(state['preparation_started']);self.assertEqual(state['records_prepared'],11)
        self.assertFalse(state['commit'] or state['native_execution_supported'])
        self.send(transport.DELETE)
        self.assertFalse(self.description()['download_image']['preparation_started'])
        self.assertEqual(self.send(bytes.fromhex('4d03210012042400'))[2],12)
        self.assertEqual(self.endpoint.counts['native_download_result_query'],1)
        self.assertEqual(self.description()['download_image']['tables_allocated'],0)
        for field in ('tags','routines','tasks','scan','ms','controller'):
            self.assertEqual(self.app.state()[field],before[field])

    def test_invalid_signed_diagnostic_record_rejects_the_batch_without_retaining_completed_objects(self):
        self.stage(TEMPLATE_EXPANDED+record(diagnostics.request(diagnostics.payload()[:-1],2).request))
        before=copy.deepcopy(self.app.state());identity=self.app.native_project_identity.manifest()
        for _ in range(2):self.assertEqual(self.send(INSPECT),bytes.fromhex('86000300'))
        self.assertEqual(self.description()['diagnostic_staging']['status'],'invalid')
        self.assertEqual(self.description()['template_staging']['templates'],0)
        self.assertEqual(self.description()['diagnostic_staging']['messages'],0)
        for field in ('tags','scan','ms','mode','changes'):self.assertEqual(self.app.state()[field],before[field])
        self.assertEqual(self.app.native_project_identity.manifest(),identity)
        self.send(transport.DELETE);self.assertEqual(self.description()['diagnostic_staging']['status'],'idle')

    def test_signed_broken_reference_rejects_and_clears_every_completed_model(self):
        self.stage(TEMPLATE_EXPANDED+record(objects.symbol(3,4).request))
        before=copy.deepcopy(self.app.state());identity=self.app.native_project_identity.manifest()
        for _ in range(2):self.assertEqual(self.send(INSPECT),bytes.fromhex('86000300'))
        self.assertEqual(self.description()['object_staging']['status'],'invalid')
        self.assertFalse(self.description()['object_staging']['references_validated'])
        self.assertEqual(self.description()['template_staging']['templates'],0);self.assertEqual(self.description()['diagnostic_staging']['messages'],0)
        for field in ('tags','scan','ms','mode','changes'):self.assertEqual(self.app.state()[field],before[field])
        self.assertEqual(self.app.native_project_identity.manifest(),identity)
        self.send(transport.DELETE);self.assertEqual(self.description()['object_staging']['status'],'idle')

    def test_inspection_requires_own_prepared_complete_source_bound_exact_object_path(self):
        self.prepare();self.sequence=4;self.assertEqual(self.send(INSPECT)[2],15)
        self.send(leases.ACQUIRE);self.assertEqual(self.send(INSPECT)[2],12)
        self.send(inhibits.SET);self.send(prep.BEGIN);self.assertEqual(self.send(INSPECT)[2],12)
        self.stage();identity=self.app.native_project_identity;self.app.native_project_identity=None
        self.assertEqual(self.send(INSPECT)[2],12);self.app.native_project_identity=identity
        for raw,status in ((INSPECT+b'\0',0x15),(bytes.fromhex('06042100120424003001'),4),
                (bytes.fromhex('0603210012042401'),5)):
            self.assertEqual(self.send(raw)[2],status)
        first=self.client;second=self.second_client()
        try:self.client=second;self.assertEqual(self.signed(4,INSPECT)[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(self.description()['inspection']['status'],'idle');self.assertEqual(self.send(INSPECT)[2],15)

    def test_lifecycle_discards_cached_inspection_with_buffer_and_lease(self):
        for action in ('delete','end','clear','release','generation','bad-mac','reset','reload','disconnect','stop'):
            self.stage();self.send(INSPECT);self.assertEqual(self.description()['inspection']['status'],'decoded')
            if action=='delete':self.send(transport.DELETE)
            elif action=='end':self.send(prep.END)
            elif action=='clear':self.send(inhibits.CLEAR)
            elif action=='release':self.send(leases.RELEASE)
            elif action=='generation':self.endpoint.programming_lease.description(self.app.generation+1,self.app.engine.project.sha256)
            elif action=='bad-mac':
                raw=request(inner=INSPECT,sequence=self.sequence);self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
            elif action=='reset':self.app.command('reset',{})
            elif action=='reload':self.app.command('demo',{'sample':'ConveyorDemo'})
            elif action=='stop':self.endpoint.stop()
            else:
                self.client.close();deadline=time.monotonic()+2
                while self.description()['open'] and time.monotonic()<deadline:time.sleep(.01)
            state=self.endpoint.programming_lease.transport.description()['inspection']
            self.assertEqual(state['status'],'idle');self.assertEqual(state['record_count'],0);self.assertEqual(state['operations'],[])
            self.assertEqual(self.endpoint.programming_lease.transport.description()['template_staging']['status'],'idle')
            self.assertEqual(self.endpoint.programming_lease.transport.description()['template_staging']['layout_inspection']['status'],'idle')
            self.assertEqual(self.endpoint.programming_lease.transport.description()['diagnostic_staging']['status'],'idle')
            self.assertEqual(self.endpoint.programming_lease.transport.description()['object_staging']['status'],'idle')
            self.assertEqual(self.endpoint.programming_lease.transport.description()['source_type_verification']['status'],'idle')
            self.assertEqual(self.endpoint.programming_lease.transport.description()['source_object_verification']['status'],'idle')
            if action in ('reset','reload','disconnect'):
                self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()


class InspectionToolTests(unittest.TestCase):
    def source_fixture(self,folder):
        from test_native_types import XML
        from test_native_symbols import container as acd_container
        from test_template_layout import definition
        raw=definition(((1,0xC1,0xA0000002),(3,0x20C3,0xF0000004)),(b'Flag',b'Values'))
        raw+=b'\0'*(-len(raw)%4)
        rows=list(templates.batch(data=raw));rows[1]=templates.request(4,templates.attrs(members=2,size=12))
        expanded=b''.join(record(r.request) for r in rows)
        source=folder/'payload.bin';source.write_bytes(container(zlib.compress(expanded)))
        acd=folder/'source.ACD';acd.write_bytes(acd_container(XML.encode()))
        l5x=folder/'source.L5X';l5x.write_text('synthetic binding bytes')
        return source,acd,l5x,expanded

    def test_offline_source_comparison_records_hashes_without_exposing_types(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);source,acd,l5x,expanded=self.source_fixture(p);out=p/'report.json'
            result=run(source,out,len(expanded),inspect_templates=True,source_acd=acd,source_l5x=l5x)
            self.assertEqual(result['source_type_verification']['status'],'matched')
            self.assertEqual(result['source_type_verification']['members_matched'],2)
            self.assertTrue(result['sources_unchanged'])
            for text in ('Example','Flag','Values','synthetic binding bytes'):self.assertNotIn(text,out.read_text())
            for target in (source,acd,l5x):
                with self.assertRaises(ValueError):run(source,target,len(expanded),inspect_templates=True,source_acd=acd,source_l5x=l5x)
            for kw in ({'source_acd':acd},{'source_acd':acd,'source_l5x':l5x}):
                with self.assertRaises(ValueError):run(source,p/'unused.json',len(expanded),**kw)

    def test_offline_changed_source_is_detected_before_report_creation(self):
        from logixlab.native_types import NativeTypes
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);source,acd,l5x,expanded=self.source_fixture(p);out=p/'report.json'
            original=NativeTypes.verify
            def mutate(value,templates):
                l5x.write_text('changed');return original(value,templates)
            with patch.object(NativeTypes,'verify',mutate),self.assertRaises(ValueError):
                run(source,out,len(expanded),inspect_templates=True,source_acd=acd,source_l5x=l5x)
            self.assertFalse(out.exists())

    def test_optional_template_inspection_reports_counts_without_names_or_payloads(self):
        from test_template_layout import definition
        raw=definition(trailer=b'private-trailer');raw+=b'\0'*(-len(raw)%4)
        expanded=b''.join(record(r.request) for r in templates.batch(data=raw))
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'payload.bin';out=Path(folder)/'report.json'
            source.write_bytes(container(zlib.compress(expanded)))
            result=run(source,out,len(expanded),inspect_templates=True)
            self.assertEqual(result['template_layout_inspection']['status'],'decoded')
            self.assertEqual(result['template_layout_inspection']['members_decoded'],1)
            for text in ('Example','Value','private-trailer',raw.hex()):self.assertNotIn(text,out.read_text())

    def test_summary_does_not_overwrite_input_or_existing_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'payload.bin';out=Path(folder)/'report.json';source.write_bytes(ENCODED)
            result=run(source,out,len(EXPANDED));self.assertEqual(result['record_count'],2)
            self.assertEqual(source.read_bytes(),ENCODED);self.assertNotIn('PrivateDefinition',out.read_text())
            with self.assertRaises(FileExistsError):run(source,out,len(EXPANDED))
            with self.assertRaises(ValueError):run(source,source,len(EXPANDED))

    def test_changed_input_is_detected_before_writing_a_report(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'payload.bin';out=Path(folder)/'report.json';source.write_bytes(ENCODED)
            def changed(*args):source.write_bytes(ENCODED+b'changed');return dp.records(EXPANDED)
            with patch('tools.inspect_device_payload.decode',side_effect=changed),self.assertRaises(ValueError):run(source,out,len(EXPANDED))
            self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
