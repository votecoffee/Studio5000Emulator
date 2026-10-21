"""Offline checkpoint reports preserve framing, scope and evidence limits."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import analyze_native_transfer as tool
from logixlab import signed_messages as sm
from test_signed_messages import request,response,KEY
from test_signed_batches import batch
from test_transport_fragments import message


def event(child,result,sequence=7):
    raw=request(inner=child,sequence=sequence)
    return dict(kind='cip',time=12345,request_hex=raw.hex(),response_hex=response(inner=result,sequence=sequence).hex())


class TransferTraceTests(unittest.TestCase):
    def test_task_collection_keeps_scope_program_ids_and_memory_fields_structural(self):
        query=bytes.fromhex('0303207025002c01020001001400')
        answer=bytes.fromhex('830000000200010000000100')+struct.pack('<I',90000)+bytes.fromhex('140000000000')
        result=tool.analyze({'events':[]},{'events':[event(query,answer)]},'upload')
        self.assertTrue(result['analysis_complete']);self.assertEqual(result['collection_layout_errors'],0)
        row,=result['collection_attribute_lists'];self.assertEqual(row['instance'],300)
        self.assertEqual([f['value_bytes'] for f in row['collection_attribute_list']['attributes']],[6,2])
        self.assertNotIn('data_hex',json.dumps(result))
        for query in ('03022070240001001400','0304206824012070240101001400'):
            result=tool.analyze({'events':[]},{'events':[event(bytes.fromhex(query),answer)]},'upload')
            self.assertEqual(result['collection_lists_observed'],0)

    def test_program_collection_uses_original_instance_and_excludes_class_and_parent_scopes(self):
        answer=bytes.fromhex('8300000001001e00000001')
        query=bytes.fromhex('030320682500d80101001e00')
        result=tool.analyze({'events':[]},{'events':[event(query,answer)]},'upload')
        self.assertTrue(result['analysis_complete']);self.assertEqual(result['collection_lists_observed'],1)
        row,=result['collection_attribute_lists'];self.assertEqual(row['instance'],472)
        self.assertEqual(row['collection_attribute_list']['attributes'][0]['value_bytes'],1)
        for query in ('03022068240001001e00','0304206824012068240101001e00','03022064240201000100'):
            result=tool.analyze({'events':[]},{'events':[event(bytes.fromhex(query),answer)]},'upload')
            self.assertEqual(result['collection_lists_observed'],0)

    def test_correlated_collection_fields_preserve_errors_without_endpoint_gap_counters(self):
        query=bytes.fromhex('0302204324010300020005000b00')
        answer=bytes.fromhex('83000a0003000200000000050014000b0000000000')
        result=tool.analyze({'events':[]},{'events':[event(query,answer)]},'upload')
        self.assertEqual(result['collection_lists_observed'],1)
        self.assertEqual(result['collection_layout_errors'],0)
        self.assertTrue(result['analysis_complete'])
        row,=result['collection_attribute_lists']
        self.assertEqual(row['sequence'],7)
        self.assertEqual([r['status'] for r in row['collection_attribute_list']['attributes']],[0,0x14,0])
        self.assertEqual(result['endpoint_attribute_gaps'],[])

    def test_bad_collection_framing_is_retained_and_reported_as_incomplete_analysis(self):
        query=bytes.fromhex('03022064240101000100')
        answer=bytes.fromhex('830000000100010000000300')+b'x'
        result=tool.analyze({'events':[]},{'events':[event(query,answer)]},'upload')
        self.assertEqual(result['requests_observed'],1);self.assertEqual(result['unparsed_events'],0)
        self.assertEqual(result['collection_layout_errors'],1);self.assertFalse(result['analysis_complete'])
        self.assertEqual(result['collection_attribute_lists'][0]['collection_attribute_list']['structure'],'UNSUPPORTED OR MALFORMED')
        entries=[event(query,bytes.fromhex('830000000100010000000100')+b'x',sequence=i) for i in range(70)]
        result=tool.analyze({'events':[]},{'events':entries},'upload')
        self.assertEqual(result['collection_lists_observed'],70)
        self.assertEqual(len(result['collection_attribute_lists']),64);self.assertTrue(result['collection_lists_truncated'])

    def test_original_identity_events_preserve_order_and_flags_without_names_or_error_text(self):
        types=dict(kind='native_source_type_verification',status='matched',types_matched=242,
            members_matched=13312,types_unavailable=0,template_ids_matched=242,template_ids_unresolved=0,
            template_identities_verified=True,storage_mapping_supported=False,errors=[],
            source_acd_sha256='private-hash',type_names=['PrivateType'])
        objects=dict(kind='native_source_object_verification',status='mismatch',programs_matched=1,
            routines_matched=2,symbols_matched=20,tables_matched=16,tables_unresolved=0,
            table_identities_verified=False,install_authority=False,commit=False,
            errors=['PrivateFailureText'],original_ids=[1234])
        result=tool.analyze({'events':[]},{'events':[types,objects]},'download')
        rows=result['source_verifications'];self.assertEqual([r['kind'] for r in rows],[types['kind'],objects['kind']])
        self.assertEqual(rows[0]['template_ids_matched'],242);self.assertTrue(rows[0]['template_identities_verified'])
        self.assertEqual(rows[1]['status'],'mismatch');self.assertEqual(rows[1]['error_categories'],1)
        self.assertFalse(rows[1]['install_authority']);self.assertFalse(rows[1]['commit'])
        self.assertEqual(result['source_verifications_observed'],2);self.assertTrue(result['analysis_complete'])
        for secret in ('PrivateType','PrivateFailureText','private-hash','1234'):self.assertNotIn(secret,json.dumps(result))
        self.assertEqual(result['failure_cause'],'NOT INFERRED');self.assertEqual(result['mac_verification'],'NOT PERFORMED')

    def test_invalid_identity_counts_flags_status_and_error_lists_make_analysis_incomplete(self):
        base=dict(kind='native_source_type_verification',status='matched',types_matched=1,errors=[])
        variants=({'types_matched':True},{'types_matched':-1},{'types_matched':2**32},
                  {'template_ids_unresolved':False},{'template_identities_verified':1},
                  {'status':'PrivateStatus'},{'errors':'PrivateError'},{'errors':[{}]*65})
        for change in variants:
            result=tool.analyze({'events':[]},{'events':[{**base,**change}]},'download')
            self.assertFalse(result['analysis_complete']);self.assertEqual(result['source_verifications_invalid'],1)
            self.assertEqual(result['source_verifications'],[]);self.assertNotIn('Private',json.dumps(result))

    def test_identity_display_limit_retains_counts_and_old_events_keep_missing_fields_absent(self):
        old=dict(kind='native_source_type_verification',status='matched',types_matched=1,errors=[])
        result=tool.analyze({'events':[]},{'events':[old]*17},'download')
        self.assertEqual(result['source_verifications_observed'],17);self.assertEqual(len(result['source_verifications']),16)
        self.assertTrue(result['source_verifications_truncated']);self.assertTrue(result['analysis_complete'])
        self.assertNotIn('template_identities_verified',result['source_verifications'][0])
        empty=tool.analyze({'events':[]},{'events':[]},'upload')
        self.assertEqual(empty['source_verifications'],[]);self.assertEqual(empty['source_verifications_observed'],0)

    def test_identity_events_obey_checkpoint_interval_and_never_retain_previous_transfer_matches(self):
        old=dict(kind='native_source_type_verification',status='matched',types_matched=242,errors=[])
        marker=dict(kind='marker');new=dict(kind='native_source_type_verification',status='unavailable',errors=[])
        result=tool.analyze({'events':[old,marker]},{'events':[old,marker,new]},'download')
        self.assertEqual(result['source_verifications'],[dict(kind=new['kind'],status='unavailable',error_categories=0)])
        self.assertEqual(result['source_verifications_observed'],1)

    def test_aoi_and_program_parent_ids_remain_distinct_in_diagnostics(self):
        from tools.upload_inventory import logical_path
        children=[]
        for parent in (logical_path(0x6D,7,program=700),logical_path(0x6D,7,aoi=700)):
            children.append(bytes((0x0E,len(parent)//2+1))+parent+b'\x30\x07')
        result=tool.analyze({'events':[]},{'events':[event(child,bytes.fromhex('8e001400'),sequence=10+i)
                for i,child in enumerate(children)]},'upload')
        self.assertEqual(result['requests_observed'],2)
        self.assertEqual([(r['program_instance'],r['aoi_instance']) for r in result['last_requests']],[(700,None),(None,700)])
        self.assertEqual(len(result['objects']),2)

    def test_checkpoint_anchor_excludes_prior_calls_ignores_duplicate_inner_events_and_sdk_clock(self):
        old=event(bytes.fromhex('0102208e2401'),bytes.fromhex('81000800'))
        new=event(bytes.fromhex('0302208e2401020001000600'),bytes.fromhex('83000a0002000100140006001400'),8)
        duplicate=dict(new,request_hex='0302208e2401020001000600',response_hex='83000a0002000100140006001400')
        before={'events':[old]};after={'events':[old,new,duplicate]}
        result=tool.analyze(before,after,'upload',{'steps':[dict(method='UploadAsync',status='failed',startedAt='other clock')]})
        self.assertEqual(result['requests_observed'],1);self.assertEqual(result['signed_envelopes'],1)
        self.assertTrue(result['analysis_complete']);self.assertEqual(result['sdk_status'],'failed')
        self.assertEqual(result['failed_requests'][0]['requested_attributes'],[1,6])
        self.assertEqual(result['failed_requests'][0]['status'],10)
        self.assertEqual(result['mac_verification'],'NOT PERFORMED');self.assertEqual(result['failure_cause'],'NOT INFERRED')

    def test_batch_children_and_scoped_targets_keep_order_without_payload_or_symbol_names(self):
        children=(bytes.fromhex('0e06206825003412206d24013007'),
                  bytes.fromhex('4d049106536563726574')+b'private-values')
        replies=(bytes.fromhex('8e001400'),bytes.fromhex('cd000f00'))
        raw=batch(children);reply=sm.encode_batch_response(sm.parse_request(raw),replies,KEY)
        result=tool.analyze({'events':[]},{'events':[dict(kind='cip',request_hex=raw.hex(),response_hex=reply.hex())]},'download')
        self.assertEqual(result['requests_observed'],2);self.assertEqual(result['failed_request_count'],2)
        self.assertEqual(result['last_requests'][0]['program_instance'],0x1234)
        self.assertEqual(result['last_requests'][0]['class_id'],0x6D)
        self.assertTrue(result['last_requests'][1]['symbolic'])
        for text in ('Secret','private-values',raw.hex(),reply.hex()):self.assertNotIn(text,json.dumps(result))

    def test_fragment_acknowledgements_and_outer_errors_remain_separate_from_inner_results(self):
        raw=message(0x101,100,b'private-fragment',sequence=10);parsed=sm.parse_request(raw)
        ack=sm.encode_fragment_ack(parsed,KEY)
        complete=dict(kind='cip',request_hex=raw.hex(),response_hex=ack.hex())
        denied=dict(complete,response_hex='b9000f013412')
        result=tool.analyze({'events':[]},{'events':[complete,denied]},'download')
        self.assertEqual(result['fragment_acknowledgements'],1);self.assertEqual(result['fragment_bytes'],16)
        self.assertEqual(result['requests_observed'],0);self.assertEqual(result['failed_requests'],[])
        self.assertEqual(result['wrapper_rejections'],[dict(service=0x39,status=15,sequence=10,additional_status=[0x1234])])

    def test_missing_ambiguous_and_oversized_checkpoints_do_not_guess_an_interval(self):
        marker={'kind':'marker'}
        for events,status in (([],'checkpoint_not_retained'),([marker,marker],'checkpoint_ambiguous')):
            result=tool.analyze({'events':[marker]},{'events':events},'upload')
            self.assertEqual(result['status'],status);self.assertFalse(result['analysis_complete'])
        with self.assertRaises(ValueError):tool.analyze({'events':[]},{'events':[{}]*(tool.MAX_EVENTS+1)},'upload')
        with self.assertRaises(ValueError):tool.analyze({'events':[]},{'events':[None]},'download')
        with self.assertRaises(ValueError):tool.analyze({'events':[]},{'events':[]},'connection')

    def test_malformed_and_truncated_envelopes_are_counted_and_never_claim_complete_analysis(self):
        valid=event(bytes.fromhex('0102208e2401'),bytes.fromhex('81000800'))
        entries=[dict(valid,truncated=True),dict(valid,response_hex='not hex'),
            dict(valid,response_hex=response(inner=b'\x81\0\x08\0',sequence=999).hex()),
            dict(valid,request_hex='36'),dict(valid,response_hex='b6000f0100')]
        result=tool.analyze({'events':[]},{'events':entries+[valid]},'upload')
        self.assertEqual(result['requests_observed'],1);self.assertEqual(result['unparsed_events'],5)
        self.assertFalse(result['analysis_complete'])

    def test_preparation_events_and_gap_deltas_exclude_source_values_and_earlier_failures(self):
        gap=dict(generation=2,class_id=0x8E,instance=1,service=3,count=4,
                 attributes=[dict(id=1,name='PrivateName'),dict(id=6)],scope='PrivateScope')
        before={'events':[],'attribute_gaps':[gap]}
        phase=dict(kind='native_download_result_query',records_prepared=904,preparation_started=True,commit=False,
                   record_sha256='secret-digest',private_name='PrivateName')
        after={'events':[phase],'attribute_gaps':[dict(gap,count=5)]}
        result=tool.analyze(before,after,'download')
        self.assertEqual(result['endpoint_attribute_gaps'][0]['interval_count'],1)
        self.assertEqual(result['endpoint_attribute_gaps'][0]['attributes'],[1,6])
        self.assertEqual(result['preparation_events'],[dict(kind=phase['kind'],records_prepared=904,preparation_started=True,commit=False)])
        for text in ('PrivateName','PrivateScope','secret-digest'):self.assertNotIn(text,json.dumps(result))
        after['attribute_gaps'][0]['attributes']*=17
        with self.assertRaises(ValueError):tool.analyze(before,after,'download')

    def test_summary_bounds_keep_tail_and_counts_and_mark_a_stopped_scan(self):
        entries=[event(bytes.fromhex('0102208e2401'),bytes.fromhex('81000800'),sequence=i) for i in range(80)]
        result=tool.analyze({'events':[]},{'events':entries},'upload')
        self.assertEqual(result['failed_request_count'],80);self.assertEqual(len(result['failed_requests']),64)
        self.assertTrue(result['failures_truncated']);self.assertEqual(len(result['last_requests']),16)
        self.assertEqual(result['last_requests'][-1]['sequence'],79)
        with patch.object(tool,'MAX_REQUESTS',2):result=tool.analyze({'events':[]},{'events':entries},'upload')
        self.assertEqual(result['requests_observed'],2);self.assertTrue(result['request_limit_reached'])
        self.assertFalse(result['analysis_complete'])

    def test_cli_reads_only_existing_json_preserves_inputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);before=root/'before.json';after=root/'after.json';out=root/'result.json'
            before.write_text(json.dumps({'events':[]}));after.write_text(json.dumps({'events':[]}))
            original=(before.read_bytes(),after.read_bytes())
            command=['analyze','--before',str(before),'--after',str(after),'--operation','upload','--output',str(out)]
            with patch('sys.argv',command),patch('builtins.print'):tool.main()
            self.assertEqual(json.loads(out.read_text())['status'],'no_complete_signed_events')
            self.assertEqual((before.read_bytes(),after.read_bytes()),original)
            with patch('sys.argv',command),patch('builtins.print'),self.assertRaises(FileExistsError):tool.main()
            with patch.object(tool,'MAX_FILE_BYTES',1),self.assertRaises(ValueError):tool.read_json(before)


if __name__=='__main__':unittest.main()
