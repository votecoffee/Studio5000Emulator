"""Successful long transfers retain exact intervals; failures never hide loss."""
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from logixlab import ethernetip as eip
from logixlab.server import Application
from tools import trace_journal as tool
from tools.analyze_native_transfer import analyze
from test_native_transfer_trace import event


class TraceJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.app=Application(self.root/'app');self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=eip.Endpoint(self.app,0,False);self.path=self.root/'trace.jsonl.gz'

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def writer(self,read=None):
        return tool.TraceJournal(self.path,read or (lambda data:self.endpoint.trace_page(**data)),
            self.app.instance_id,self.endpoint.source_sha256)

    def test_complete_long_transfer_recovered_after_ring_loses_both_markers(self):
        writer=self.writer();self.endpoint.record('before');before=self.endpoint.state(True)
        sample=event(bytes.fromhex('0e02208e2401'),bytes.fromhex('8e001400'))
        for i in range(2100):
            self.endpoint.record('cip',bytes.fromhex(sample['request_hex']),bytes.fromhex(sample['response_hex']))
            if i%100==99:writer.drain()
        after=self.endpoint.state(True);receipt=writer.close()
        self.assertTrue(receipt['complete']);self.assertEqual(receipt['events'],2101)
        self.assertEqual(analyze(before,after,'upload')['status'],'checkpoint_not_retained')
        result=analyze(before,after,'upload',journal=self.path)
        self.assertTrue(result['analysis_complete']);self.assertEqual(result['requests_observed'],2100)
        self.assertEqual(result['correlation'],'saved_emulator_trace_journal')
        self.assertEqual(result['mac_verification'],'NOT PERFORMED')

    def test_exact_checkpoint_range_excludes_earlier_and_later_native_events(self):
        writer=self.writer();self.endpoint.record('before');before=self.endpoint.state(True)
        self.endpoint.record('during');after=self.endpoint.state(True)
        self.endpoint.record('after');writer.close()
        rows=tool.read_interval(self.path,before,after)
        self.assertEqual([row['kind'] for row in rows],['during'])

    def test_one_read_timeout_reuses_exact_cursor_and_retains_each_event_once(self):
        calls=[];timed_out=False
        def read(body):
            nonlocal timed_out
            calls.append(dict(body))
            if body and not timed_out:
                timed_out=True;raise TimeoutError('private timeout detail')
            return self.endpoint.trace_page(**body)
        writer=self.writer(read);before=self.endpoint.state(True)
        self.endpoint.record('first');self.endpoint.record('second');after=self.endpoint.state(True)
        receipt=writer.close();self.assertTrue(receipt['complete'])
        self.assertEqual(calls[1],calls[2]);self.assertEqual(receipt['events'],2)
        self.assertEqual((receipt['diagnostic_read_timeouts'],receipt['diagnostic_read_retries']),(1,1))
        self.assertEqual([row['kind'] for row in tool.read_interval(self.path,before,after)],['first','second'])
        self.assertNotIn('private timeout detail',str(receipt))

    def test_exhausted_timeouts_are_bounded_and_leave_recording_incomplete(self):
        writer=self.writer();before=self.endpoint.state(True);self.endpoint.record('held')
        calls=[]
        def read(body):calls.append(dict(body));raise TimeoutError('unavailable')
        writer.read_page=read;receipt=writer.close()
        self.assertEqual(len(calls),3);self.assertTrue(all(x==calls[0] for x in calls))
        self.assertFalse(receipt['complete']);self.assertEqual(receipt['collection_error_type'],'TimeoutError')
        self.assertEqual((receipt['diagnostic_read_timeouts'],receipt['diagnostic_read_retries']),(3,2))
        self.assertEqual(analyze(before,self.endpoint.state(True),'upload',journal=self.path)['status'],'journal_incomplete')

    def test_timeout_does_not_allow_replaced_identity_and_other_errors_are_not_retried(self):
        for wrong in ('identity','gap','read'):
            with self.subTest(wrong=wrong):
                self.path=self.root/(wrong+'.gz');writer=self.writer();self.endpoint.record('event');calls=[]
                def read(body):
                    calls.append(dict(body))
                    if len(calls)==1:raise TimeoutError('temporary')
                    page=self.endpoint.trace_page(**body)
                    if wrong=='identity':page['instance_id']='foreign'
                    elif wrong=='gap':page['missing_events']=1
                    else:raise OSError('not a timeout')
                    return page
                writer.read_page=read;receipt=writer.close()
                self.assertFalse(receipt['complete']);self.assertEqual(len(calls),2)
                self.assertEqual(receipt['diagnostic_read_retries'],1)

    def test_diagnostic_timeouts_never_relaunch_the_owned_native_process(self):
        from unittest.mock import MagicMock
        process=MagicMock();process.__enter__.return_value=process
        process.wait.side_effect=(subprocess.TimeoutExpired(['owned'],.25),0)
        writer=self.writer();writer.read_page=lambda data:(_ for _ in ()).throw(TimeoutError())
        with patch.object(tool.subprocess,'Popen',return_value=process) as launch:
            result=tool.run_recorded(['owned'],journal=writer,stdout=None,timeout=30,background={})
        self.assertEqual(result.returncode,0);launch.assert_called_once();process.kill.assert_not_called()
        self.assertEqual(writer.close()['diagnostic_read_retries'],2)

    def test_ring_gap_and_replaced_identity_stop_recording_without_silent_recovery(self):
        for replacement in (False,True):
            with self.subTest(replacement=replacement):
                self.path=self.root/f'trace-{replacement}.gz';writer=self.writer();before=self.endpoint.state(True)
                if replacement:writer.read_page=lambda data:eip.Endpoint(self.app,0,False).trace_page()
                else:
                    for _ in range(eip.TRACE_EVENT_LIMIT+1):self.endpoint.record('overflow')
                receipt=writer.close();self.assertFalse(receipt['complete'])
                self.assertEqual(receipt['error'],'trace_collection_failed')
                result=analyze(before,self.endpoint.state(True),'upload',journal=self.path)
                self.assertEqual(result['status'],'journal_incomplete');self.assertFalse(result['analysis_complete'])

    def test_partial_journal_truncated_gzip_missing_footer_and_storage_limits_fail_closed(self):
        writer=self.writer();self.endpoint.record('marker');before=self.endpoint.state(True)
        self.endpoint.record('during');after=self.endpoint.state(True);writer.close()
        original=self.path.read_bytes()
        self.path.write_bytes(original[:-8])
        self.assertFalse(analyze(before,after,'download',journal=self.path)['analysis_complete'])
        self.path.write_bytes(original)
        text=gzip.decompress(original);rows=text.splitlines()
        self.path.write_bytes(gzip.compress(b'\n'.join(rows[:-1])+b'\n'))
        with self.assertRaises(ValueError):tool.read_interval(self.path,before,after)
        self.path=self.root/'limited.gz';writer=self.writer();self.endpoint.record('limited')
        with patch.object(tool,'MAX_EVENTS',0):receipt=writer.close()
        self.assertFalse(receipt['complete'])

    def test_duplicate_reordered_and_missing_events_are_never_accepted(self):
        writer=self.writer();before=self.endpoint.state(True)
        self.endpoint.record('one');self.endpoint.record('two');after=self.endpoint.state(True);writer.close()
        rows=gzip.decompress(self.path.read_bytes()).splitlines()
        for bad in (rows[:2]+rows[1:],rows[:1]+rows[2:3]+rows[1:2]+rows[3:],rows[:1]+rows[2:]):
            self.path.write_bytes(gzip.compress(b'\n'.join(bad)+b'\n'))
            self.assertFalse(analyze(before,after,'upload',journal=self.path)['analysis_complete'])

    def test_initial_identity_and_preexisting_output_are_checked_before_native_call(self):
        page=self.endpoint.trace_page();page['instance_id']='foreign'
        with self.assertRaises(ValueError):self.writer(lambda data:page)
        with self.assertRaises(FileExistsError):self.writer()

    def test_native_timeout_kills_only_owned_process_and_never_replays(self):
        from unittest.mock import MagicMock
        process=MagicMock();process.__enter__.return_value=process
        process.wait.return_value=-1
        journal=MagicMock()
        with patch.object(tool.subprocess,'Popen',return_value=process) as launch, \
                patch.object(tool.time,'monotonic',side_effect=(0,1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                tool.run_recorded(['owned'],journal=journal,stdout=None,timeout=.5,background={})
        launch.assert_called_once();process.kill.assert_called_once();process.wait.assert_called_once()
        journal.drain.assert_not_called()

    def test_collector_error_does_not_replay_or_abort_native_process(self):
        from unittest.mock import MagicMock
        process=MagicMock();process.__enter__.return_value=process
        process.wait.side_effect=(subprocess.TimeoutExpired(['owned'],.25),0)
        writer=self.writer();writer.read_page=lambda data:(_ for _ in ()).throw(OSError('offline'))
        with patch.object(tool.subprocess,'Popen',return_value=process) as launch:
            result=tool.run_recorded(['owned'],journal=writer,stdout=None,timeout=10,background={})
        self.assertEqual(result.returncode,0);launch.assert_called_once();process.kill.assert_not_called()
        self.assertFalse(writer.close()['complete'])


if __name__=='__main__':unittest.main()
