"""Focused offline replay/capture comparison; no SDK, sockets or service calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from logixlab import signed_messages as sm
from logixlab.resilient_transport import DEVICE_HEADER
from tools import replay_download_image as tool
from test_download_image import batch
from test_native_types import catalog,source_types
from test_device_payload import record,container
from test_signed_messages import KEY,request
from test_transport_fragments import message


def fixture():
    expanded=b''.join(record(r.request) for r in batch());raw=container(zlib.compress(expanded))
    native=catalog(types=source_types()[:1]);image,report=tool.replay(raw,len(expanded),native)
    cut=len(raw)//2;events=[]
    for ordinal,(word,position,start,end) in enumerate(((0x101,len(raw),0,cut),(0x201,cut,cut,len(raw))),1):
        data=raw[start:end];data=DEVICE_HEADER+data if ordinal==1 else data
        events.append({'kind':'native_transport_fragment','container_format':word,'position':position,
                       'received_bytes':end,'total_bytes':len(raw),'fragments':ordinal,'complete':ordinal==2})
        events.append({'kind':'cip','request_hex':message(word,position,data,ordinal).hex(),'truncated':False})
    events.append({'kind':'native_download_image_preparation',**image.description(),'preparation_started':True})
    for sequence,(inner,reply) in enumerate((('0603210012042400','86000000'),
                                             ('4d03210012042400','cd000f00'),('0903210012042400','89000000')),3):
        q=request(0x36,inner=bytes.fromhex(inner),sequence=sequence)
        a=sm.encode_response(sm.parse_request(q),bytes.fromhex(reply),KEY)
        events.append({'kind':'cip','request_hex':q.hex(),'response_hex':a.hex(),'truncated':False})
    trace={'events':events,'source_l5x_sha256':native.source_l5x_sha256,
           'native_correlation':{'source_acd_sha256':native.source_acd_sha256,'source_l5x_sha256':native.source_l5x_sha256}}
    return raw,expanded,native,image,report,trace


class DownloadReplayToolTests(unittest.TestCase):
    def test_replay_compares_all_actual_resources_and_keeps_vendor_contract_unresolved(self):
        raw,expanded,native,image,report,trace=fixture()
        self.assertEqual(report['status'],'replayed');self.assertEqual(report['request_fingerprints_matched'],11)
        self.assertEqual(report['resource_effects_matched'],9);self.assertEqual(report['historical_transitions_matched'],2)
        self.assertEqual(report['vendor_result_encoding'],'unresolved');self.assertFalse(report['native_execution_performed'])
        self.assertNotIn('operation_readbacks',report)
        compared=tool.compare_trace(trace,raw,image)
        self.assertEqual(compared['status'],'matched');self.assertEqual(compared['result_queries_observed'],1)
        self.assertEqual(compared['captured_payload_prefix_bytes'],len(raw));self.assertEqual(compared['uncaptured_payload_bytes'],0)
        self.assertEqual([e['service'] for e in compared['rto_exchanges']],[6,0x4D,9])
        self.assertEqual(compared['rto_exchanges'][1]['observed_status'],15)
        self.assertEqual(compared['mac_verification'],'NOT PERFORMED')
        _,details=tool.replay(raw,len(expanded),native,include_records=True)
        self.assertEqual(len(details['operation_readbacks']),11)

    def test_truncated_capture_compares_only_present_payload_prefixes(self):
        raw,_,_,image,_,trace=fixture();event=trace['events'][1]
        event['request_hex']=event['request_hex'][:2*(14+len(DEVICE_HEADER)+1)];event['truncated']=True
        result=tool.compare_trace(trace,raw,image)
        self.assertEqual(result['status'],'matched');self.assertTrue(result['fragments'][0]['capture_truncated'])
        self.assertEqual(result['fragments'][0]['captured_payload_bytes'],1)
        self.assertGreater(result['uncaptured_payload_bytes'],0)
        self.assertIn('prefixes',result['fragment_comparison_scope'])

    def test_changed_payload_prefix_receipt_source_or_progress_is_reported_as_mismatch(self):
        raw,_,_,image,_,original=fixture()
        for kind in ('prefix','receipt','source','progress'):
            trace=copy.deepcopy(original)
            if kind=='prefix':
                q=bytes.fromhex(trace['events'][1]['request_hex']);at=14+len(DEVICE_HEADER)
                trace['events'][1]['request_hex']=(q[:at]+bytes((q[at]^1,))+q[at+1:]).hex()
            elif kind=='receipt':trace['events'][4]['storage_bytes']+=1
            elif kind=='source':trace['native_correlation']['source_acd_sha256']='f'*64
            else:trace['events'][0]['received_bytes']+=1
            result=tool.compare_trace(trace,raw,image)
            self.assertEqual(result['status'],'mismatch');self.assertTrue(result['mismatches'])

    def test_ambiguous_unbounded_or_malformed_trace_is_rejected(self):
        raw,_,_,image,_,original=fixture()
        for trace in ({},{'events':[None]},{'events':[]},
                      {**original,'events':original['events']+[original['events'][4]]}):
            with self.assertRaises(ValueError):tool.compare_trace(trace,raw,image)
        with patch.object(tool,'MAX_TRACE_EVENTS',1),self.assertRaises(ValueError):tool.compare_trace(original,raw,image)
        malformed=copy.deepcopy(original);malformed['events'][1]['request_hex']='ZZ'
        with self.assertRaises(ValueError):tool.compare_trace(malformed,raw,image)

    def test_report_preserves_inputs_uses_new_output_and_can_compare_saved_capture(self):
        raw,expanded,_,_,_,trace=fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'payload.bin';acd=root/'source.ACD';l5x=root/'source.L5X';capture=root/'trace.json';out=root/'report.json'
            p.write_bytes(raw);acd.write_bytes(b'synthetic ACD');l5x.write_bytes(b'synthetic converted L5X')
            a=hashlib.sha256(acd.read_bytes()).hexdigest();b=hashlib.sha256(l5x.read_bytes()).hexdigest()
            native=catalog(acd=a,l5x=b,types=source_types()[:1]);trace['source_l5x_sha256']=b
            trace['native_correlation']={'source_acd_sha256':a,'source_l5x_sha256':b};capture.write_text(json.dumps(trace))
            before={q:q.read_bytes() for q in (p,acd,l5x,capture)}
            with patch.object(tool.NativeTypes,'from_acd',return_value=native):
                report=tool.run(p,out,len(expanded),acd,l5x,trace=capture)
            self.assertEqual(report['status'],'replayed');self.assertEqual(report['capture_comparison']['status'],'matched')
            self.assertTrue(report['inputs_unchanged']);self.assertEqual(json.loads(out.read_text()),report)
            self.assertEqual(before,{q:q.read_bytes() for q in before})
            with self.assertRaises(ValueError):tool.run(p,out,len(expanded),acd,l5x)
            with self.assertRaises(ValueError):tool.run(p,p,len(expanded),acd,l5x)

    def test_changed_input_during_replay_cannot_write_a_report(self):
        raw,expanded,_,_,_,_=fixture()
        for changed in ('payload','acd','l5x'):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);p=root/'payload';acd=root/'acd';l5x=root/'l5x';out=root/'report'
                p.write_bytes(raw);acd.write_bytes(b'ACD');l5x.write_bytes(b'L5X')
                native=catalog(acd=hashlib.sha256(acd.read_bytes()).hexdigest(),
                               l5x=hashlib.sha256(l5x.read_bytes()).hexdigest(),types=source_types()[:1])
                target={'payload':p,'acd':acd,'l5x':l5x}[changed]
                def convert(*args):target.write_bytes(b'changed');return native
                with patch.object(tool.NativeTypes,'from_acd',side_effect=convert),self.assertRaises(ValueError):
                    tool.run(p,out,len(expanded),acd,l5x)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
