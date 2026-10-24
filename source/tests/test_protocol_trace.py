"""Complete native packets survive capture while the entire ring stays bounded."""
import tempfile
import unittest

from logixlab import ethernetip as eip, signed_messages as sm
from logixlab.server import Application
from test_signed_messages import KEY
from test_transport_fragments import message
from tools.analyze_native_transfer import analyze
from logixlab.model import ModelError


class ProtocolTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=eip.Endpoint(self.app,0,False)

    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def test_large_signed_fragment_is_retained_and_offline_reader_checks_its_acknowledgement(self):
        before=self.endpoint.state(True)
        raw=message(0x101,20000,bytes(4096),sequence=10)
        reply=sm.encode_fragment_ack(sm.parse_request(raw),KEY)
        self.endpoint.record('cip',request=raw,response=reply)
        after=self.endpoint.state(True);event=after['events'][-1]
        self.assertGreater(len(raw),1024);self.assertFalse(event['truncated'])
        self.assertEqual(bytes.fromhex(event['request_hex']),raw)
        self.assertEqual(event['request_bytes'],len(raw));self.assertEqual(event['response_bytes'],len(reply))
        result=analyze(before,after,'download')
        self.assertTrue(result['analysis_complete']);self.assertEqual(result['fragment_acknowledgements'],1)
        self.assertEqual(result['fragment_bytes'],4096);self.assertEqual(result['mac_verification'],'NOT PERFORMED')

    def test_byte_budget_evicts_whole_oldest_packets_and_reports_retained_extent(self):
        self.assertGreaterEqual(eip.TRACE_BYTE_LIMIT,2*eip.TRACE_PACKET_LIMIT)
        raw=bytes(eip.TRACE_PACKET_LIMIT)
        for i in range(25):self.endpoint.record('cip',raw,raw,ordinal=i)
        state=self.endpoint.state(True);capture=state['trace_capture']
        self.assertLess(capture['retained_bytes'],eip.TRACE_BYTE_LIMIT+1)
        self.assertGreater(capture['dropped_events'],0)
        self.assertEqual(capture['dropped_events']+len(state['events']),25)
        self.assertEqual(capture['retained_bytes'],sum((len(e['request_hex'])+len(e['response_hex']))//2 for e in state['events']))
        self.assertEqual(state['events'][-1]['ordinal'],24)
        self.assertTrue(all(not e['truncated'] for e in state['events']))
        self.assertEqual(state['counts']['cip'],25)

    def test_event_limit_also_bounds_empty_metadata_and_preserves_counter_totals(self):
        for i in range(eip.TRACE_EVENT_LIMIT+3):self.endpoint.record('progress',ordinal=i)
        state=self.endpoint.state(True)
        self.assertEqual(len(state['events']),eip.TRACE_EVENT_LIMIT)
        self.assertEqual(state['trace_capture']['dropped_events'],3)
        self.assertEqual(state['trace_capture']['retained_bytes'],0)
        self.assertEqual(state['counts']['progress'],eip.TRACE_EVENT_LIMIT+3)

    def test_oversized_packets_keep_explicit_original_lengths_and_truncation(self):
        raw=bytes(eip.TRACE_PACKET_LIMIT+1)
        self.endpoint.record('cip',raw,raw)
        event=self.endpoint.state(True)['events'][-1]
        self.assertTrue(event['truncated']);self.assertEqual(event['request_bytes'],len(raw))
        self.assertEqual(event['response_bytes'],len(raw))
        self.assertEqual(len(bytes.fromhex(event['request_hex'])),eip.TRACE_PACKET_LIMIT)
        self.assertEqual(self.endpoint.trace_payload_bytes,2*eip.TRACE_PACKET_LIMIT)

    def test_evicted_checkpoint_does_not_summarize_a_partial_native_call_as_complete(self):
        self.endpoint.record('marker');before=self.endpoint.state(True)
        for _ in range(eip.TRACE_EVENT_LIMIT):self.endpoint.record('later')
        result=analyze(before,self.endpoint.state(True),'upload')
        self.assertEqual(result['status'],'checkpoint_not_retained');self.assertFalse(result['analysis_complete'])

    def test_empty_checkpoint_detects_loss_during_a_long_call(self):
        before=self.endpoint.state(True)
        for _ in range(eip.TRACE_EVENT_LIMIT+1):self.endpoint.record('later')
        result=analyze(before,self.endpoint.state(True),'download')
        self.assertEqual(result['status'],'checkpoint_not_retained');self.assertFalse(result['analysis_complete'])

    def test_cursor_pages_are_ordered_bounded_and_do_not_change_model_or_counters(self):
        self.app.endpoint=self.endpoint
        before=self.app.state();start=self.app.command('connectivity-trace-read',{})
        self.assertEqual(start['events'],[]);self.assertEqual(start['next_event'],0)
        for i in range(300):self.endpoint.record('progress',ordinal=i)
        page=self.app.command('connectivity-trace-read',dict(after_event=0,trace_id=start['trace_id']))
        self.assertEqual(len(page['events']),256);self.assertTrue(page['has_more'])
        self.assertEqual([row['event_id'] for row in page['events']],list(range(1,257)))
        tail=self.endpoint.trace_page(page['next_event'],start['trace_id'])
        self.assertEqual(len(tail['events']),44);self.assertFalse(tail['has_more'])
        self.assertEqual(tail['missing_events'],0);self.assertEqual(tail['next_event'],300)
        self.assertEqual(self.endpoint.counts['progress'],300)
        self.assertEqual(self.app.state()['tags'],before['tags']);self.assertEqual(self.app.state()['scan'],before['scan'])
        self.assertNotIn('native_correlation',page)

    def test_cursor_eviction_and_endpoint_replacement_cannot_look_contiguous(self):
        start=self.endpoint.trace_page()
        for _ in range(eip.TRACE_EVENT_LIMIT+5):self.endpoint.record('progress')
        page=self.endpoint.trace_page(0,start['trace_id'],1)
        self.assertEqual(page['missing_events'],5);self.assertEqual(page['events'][0]['event_id'],6)
        other=eip.Endpoint(self.app,0,False)
        with self.assertRaises(ModelError):other.trace_page(0,start['trace_id'])
        for after,token,limit in ((-1,start['trace_id'],1),(True,start['trace_id'],1),(99999,start['trace_id'],1),
                (0,None,1),(None,start['trace_id'],1),(0,start['trace_id'],257),(0,start['trace_id'],False)):
            with self.assertRaises(ModelError):self.endpoint.trace_page(after,token,limit)
        self.app.endpoint=self.endpoint
        with self.assertRaises(ModelError):self.app.command('connectivity-trace-read',{'unknown':1})


if __name__=='__main__':unittest.main()
