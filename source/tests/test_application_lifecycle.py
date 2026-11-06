"""Exercise real HTTP sessions and graceful process shutdown."""
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from pathlib import Path
from urllib.request import Request, urlopen

from logixlab import __version__
from tools.vmware_appliance import background_options


class ApplicationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        source = Path(__file__).resolve().parents[1]
        self.process = subprocess.Popen([sys.executable, str(source / 'launch.py'), '--no-browser',
                                         '--no-tray', '--data-dir', self.tmp.name],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,**background_options())
        deadline = time.monotonic() + 8
        receipt = Path(self.tmp.name) / 'last-session.json'
        while time.monotonic() < deadline:
            if receipt.is_file():
                try:
                    self.session = json.loads(receipt.read_text(encoding='utf-8'))
                    break
                except ValueError:
                    pass
            if self.process.poll() is not None:
                self.fail(self.process.stderr.read().decode())
            time.sleep(0.02)
        else:
            self.process.kill()
            self.process.wait()
            self.fail('Server startup timed out')
        self.url = self.session['url']
        script = self.get('/session.js').decode()
        self.token = json.loads(re.search(r'LOGIX_TOKEN = (".*?")', script)[1])

    def tearDown(self):
        if self.process.poll() is None:
            try:
                self.post('quit', {})
                self.process.wait(timeout=5)
            finally:
                if self.process.poll() is None:
                    self.process.kill()
                    self.process.wait()
        self.process.stderr.close()
        self.tmp.cleanup()

    def get(self, path):
        with urlopen(Request(self.url + path), timeout=3) as response:
            return response.read()

    def post(self, action, data):
        request = Request(self.url + '/api/' + action, json.dumps(data).encode(),
                          {'X-Logix-Token': self.token, 'Content-Type': 'application/json'})
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_data_lab_clipped_record_operations_preserve_neighbors_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'DataLab'});self.assertEqual(state['blockers'],[])
        self.assertEqual(len(state['routines']),3)
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':25})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def counts(s,name):
            v=values(s);return [v[f'{name}[{i}].Count'] for i in range(3)]
        state=step();self.assertEqual(counts(state,'ClipRecordSources'),[10,20,30])
        write('ClipRecordIndex',2);write('ClipRecordFill',True);state=step()
        self.assertEqual(counts(state,'ClipRecordSources'),[10,20,0])
        self.assertIs(values(state)['ClipRecordSources[2].Enabled'],False)
        self.assertEqual(values(state)['ClipRecordSources[2].Timer.ACC'],0)
        write('ClipRecordFill',False);write('ClipRecordCopy',True);state=step()
        for name in ('ClipRecordCopies','ClipRecordSync'):self.assertEqual(counts(state,name),[101,0,999])
        write('ClipRecordSources[2].Count',77);state=step()
        for name in ('ClipRecordCopies','ClipRecordSync'):self.assertEqual(counts(state,name),[101,77,999])
        write('ClipRecordIndex',99)
        before=state_now()
        with self.assertRaises(HTTPError) as caught:step()
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','trace','routine_edits'):self.assertEqual(after[key],before[key])
        write('ClipRecordIndex',2);state=step();self.assertFalse(state['fault'])
        report=self.post('report',{})
        for name in ('aggregate_copy','aggregate_fill'):
            self.assertTrue(report[name]['clipping']);self.assertFalse(report[name]['native_runtime_parity'])

    def test_conversion_lab_small_packed_bcd_guarded_values_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'ConversionLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':25})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertIsNone(values(step())['SmallBytePacked[1]'])
        write('SmallBCDIndex',1);write('SmallBCD',True);state=step();v=values(state)
        self.assertEqual([v[f'SmallBytePacked[{i}]'] for i in range(3)],[11,-103,77])
        self.assertEqual([v[f'SmallDecoded[{i}]'] for i in range(4)],[99,99,9999,9999])
        self.assertEqual((v['SmallByteUnsigned'],v['SmallWordSigned'],v['SmallWordUnsigned']),(153,-26215,39321))
        for tag,value,recovery in [('SmallDecimal',100,88),('SmallWordDecimal',10000,1234),('SmallBCDIndex',99,1)]:
            write(tag,value);before=state_now()
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);error.exception.close();after=state_now()
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key])
            write(tag,recovery);state=step();self.assertFalse(state['fault'])
        write('SmallBCD',False);write('SmallBCDIndex',99);retained=values(state)['SmallBytePacked[1]'];self.assertEqual(values(step())['SmallBytePacked[1]'],retained)
        report=self.post('report',{})['numeric_conversions'];self.assertEqual(len(report['rll_operands']['FRD']['sources']),8);self.assertFalse(report['native_runtime_parity'])

    def test_record_lab_basic_record_snapshots_guards_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'RecordLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':25})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertIsNone(values(step())['SnapshotTimerOut.ACC'])
        write('SnapshotIndex',1);write('SnapshotLoad',True);v=values(step())
        for name in ('TimerQueue','CounterStack','ControlQueue','RecordQueue'):self.assertEqual(v['Snapshot'+name+'.POS'],1)
        self.assertEqual((v['SnapshotTimers[1].ACC'],v['SnapshotCounters[1].ACC'],v['SnapshotControls[1].LEN'],v['SnapshotRecords[1].Id']),(125,3,7,42))
        for tag,value in [('SnapshotTimerSource.ACC',999),('SnapshotCounterSource.ACC',8),('SnapshotControlSource.LEN',9),('SnapshotRecordSource.Id',84)]:write(tag,value)
        v=values(step());self.assertEqual(v['SnapshotTimers[1].ACC'],125);self.assertEqual(v['SnapshotTimerQueue.POS'],1)
        write('SnapshotLoad',False);write('SnapshotUnload',True);v=values(step())
        self.assertEqual((v['SnapshotTimerOut.ACC'],v['SnapshotCounterOut.ACC'],v['SnapshotControlOut.LEN'],v['SnapshotRecordOut.Id']),(125,3,7,42))
        self.assertEqual((v['SnapshotRecordOut.Timer.ACC'],v['SnapshotRecordOut.Counter.ACC'],v['SnapshotRecordOut.Control.POS']),(125,3,2))
        self.assertEqual((v['SnapshotTimers[2].ACC'],v['SnapshotControls[2].LEN'],v['SnapshotRecords[2].Id']),(0,0,0));self.assertIs(v['SnapshotRecords[2].Timer.EN'],False)
        self.assertEqual((v['SnapshotTimers[0].PRE'],v['SnapshotTimers[3].PRE'],v['SnapshotRecords[0].Id'],v['SnapshotRecords[3].Id']),(1000,9000,1003,9003))
        write('SnapshotIndex',99);v=values(step());self.assertEqual(v['SnapshotTimerOut.ACC'],125)
        write('SnapshotUnload',False);step();write('SnapshotLoad',True)
        for tag,value,recovery in [('SnapshotIndex',99,1),('FaultDivisor',0,1)]:
            write(tag,value);before=state_now()
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);error.exception.close();after=state_now()
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key])
            write(tag,recovery)
        v=values(step());self.assertEqual(v['SnapshotTimers[1].ACC'],999)
        report=self.post('report',{})['control_operations'];self.assertEqual(report['basic_record_payloads'],['TIMER','COUNTER','CONTROL']);self.assertFalse(report['native_control_layout'])

    def test_event_lab_overlap_count_read_reset_status_and_rollback(self):
        self.assertEqual(self.post('demo',{'sample':'EventLab'})['blockers'],[])
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertIsNone(values(step())['OverlapWords[1]']);write('ReadOverlap',True);before=now()
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        for tag,value in [('OverlapIndex',1),('TriggerRLL',True),('SelfTrigger',True)]:write(tag,value)
        v=values(step());self.assertEqual([v[n] for n in ('ThisOverlapBefore','ThisOverlapAfter','ThisOverlapExit','NamedOverlap','StOverlap')],[0,1,1,1,1]);self.assertEqual(v['OverlapWords[1]'],1)
        write('ResetOverlap',True);v=values(step());self.assertEqual((v['ThisOverlapAfter'],v['ThisOverlapExit'],v['NamedOverlap'],v['OverlapResetValue']),(2,0,0,0));report=self.post('report',{})['event_task_status'];self.assertEqual(report['overlap_counts']['workevent'],0);self.assertEqual(report['values']['workevent'],5)
        write('OverlapResetValue',1);before=now();report=self.post('report',{})['event_task_status']
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        self.assertEqual(self.post('report',{})['event_task_status'],report);write('OverlapResetValue',0);write('OverlapDivisor',0);before=now()
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        write('OverlapDivisor',1);v=values(step());self.assertEqual([v[f'OverlapWords[{i}]'] for i in (0,2)],[101,999]);self.assertEqual(self.post('report',{})['event_task_status']['overlap_counts']['workevent'],0)

    def test_event_lab_timing_named_this_st_inhibition_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'EventLab'})['blockers'],[])
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertIsNone(values(step())['EventTimingWords[1]']);write('ReadEventTiming',True);before=now();timings=self.post('report',{})['task_scan_timing']
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        self.assertEqual(self.post('report',{})['task_scan_timing'],timings)
        for tag,value in [('EventTimingIndex',1),('TriggerRLL',True),('TriggerDeferred',True)]:write(tag,value)
        step();v=values(step())
        self.assertEqual(v['EventTimingWords[1]'],v['ThisWorkTaskLast']);self.assertEqual(v['ThisWorkTaskLast'],v['StWorkTaskLast']);self.assertEqual(v['ThisWorkTaskMax'],v['WorkTaskMax']);self.assertGreaterEqual(v['WorkTaskMax'],v['ThisWorkTaskLast'])
        self.assertEqual(v['DeferredTaskLast'],v['ThisDeferredTaskLast']);self.assertEqual(v['DeferredTaskLast'],v['StDeferredTaskLast']);self.assertEqual(v['ThisWorkProgramLast'],v['NamedWorkProgramLast'])
        write('ControlEventInhibit',True);write('EventInhibitCommand',1);step();first=self.post('report',{})['task_scan_timing']['tasks']['workevent'];step();self.assertEqual(self.post('report',{})['task_scan_timing']['tasks']['workevent'],first)
        write('EventInhibitCommand',0);write('TimingDivisor',0);before=now();timings=self.post('report',{})['task_scan_timing']
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        self.assertEqual(self.post('report',{})['task_scan_timing'],timings);write('TimingDivisor',1);v=values(step());self.assertEqual([v[f'EventTimingWords[{i}]'] for i in (0,2)],[101,999])
        self.assertFalse(self.post('report',{})['task_scan_timing']['native_protocol_expanded'])

    def test_event_lab_live_inhibition_pending_requests_this_and_rollback(self):
        self.assertEqual(self.post('demo',{'sample':'EventLab'})['blockers'],[])
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        write('TriggerRLL',True);write('ControlEventInhibit',True);write('EventInhibitCommand',1);v=values(step())
        self.assertEqual((v['EventCount'],v['LiveEventInhibit']),(0,1));write('EventInhibitCommand',0);write('ReadEventConfig',True);v=values(step())
        self.assertEqual((v['EventCount'],v['LiveEventInhibit'],v['ThisEventPriority'],v['ThisEventWatchdog']),(1,0,1,500000));self.assertEqual(v['ThisEventTaskName'],'WorkEvent')
        write('ControlEventInhibit',False);write('SelfInhibitEvent',True);v=values(step());self.assertEqual(v['ThisEventInhibit'],1);count=v['EventCount'];v=values(step());self.assertEqual(v['EventCount'],count);self.assertEqual(v['LiveEventInhibit'],1)
        write('SelfInhibitEvent',False);write('ControlEventInhibit',True);write('EventInhibitCommand',0);write('TriggerDeferred',True);write('ControlDeferredInhibit',True);write('DeferredInhibitCommand',1);v=values(step())
        self.assertEqual((v['DeferredCount'],v['LiveDeferredInhibit']),(0,1));write('DeferredInhibitCommand',0);v=values(step());self.assertEqual(v['DeferredCount'],0);v=values(step());self.assertEqual(v['DeferredCount'],1)
        write('EventInhibitCommand',1);write('InhibitDivisor',0);before=now();report=self.post('report',{})['event_task_status']
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        self.assertEqual(self.post('report',{})['event_task_status'],report);write('InhibitDivisor',1);v=values(step());self.assertEqual(v['LiveEventInhibit'],1)

    def test_event_lab_status_read_clear_this_st_guards_and_rollback(self):
        self.assertEqual(self.post('demo',{'sample':'EventLab'})['blockers'],[])
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertIsNone(values(step())['EventStatusWords[1]']);write('ReadEventStatus',True);before=now()
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        write('EventStatusIndex',1);write('TriggerRLL',True);v=values(step())
        self.assertEqual([v[n] for n in ('WorkEntryStatus','WorkActiveStatus','WorkExitStatus','NamedWorkStatus','StWorkStatus')],[1]*5)
        write('SelfTrigger',True);v=values(step());self.assertEqual(v['WorkActiveStatus'],5);self.assertEqual(v['EventStatusWords[1]'],5)
        write('ClearEventStatus',True);write('EventStatusCommand',4);v=values(step());self.assertEqual(v['WorkExitStatus'],4);self.assertEqual(v['NamedWorkStatus'],4);self.assertEqual(v['EventStatusCommand'],4)
        write('TriggerRLL',False);write('SelfTrigger',False);write('EventStatusCommand',0);step();self.assertEqual(self.post('report',{})['event_task_status']['values']['workevent'],0)
        write('TriggerRLL',True);write('ClearEventStatus',False);write('StatusDivisor',0);before=now();status=self.post('report',{})['event_task_status']
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        self.assertEqual(self.post('report',{})['event_task_status'],status);write('StatusDivisor',1);v=values(step());self.assertEqual(v['NamedWorkStatus'],1)
        self.assertEqual([v[f'EventStatusWords[{i}]'] for i in (0,2)],[101,999])
        profile=self.post('report',{})['event_task_status'];self.assertFalse(profile['native_protocol_expanded']);self.assertFalse(profile['native_runtime_parity'])

    def test_system_lab_multitask_timing_named_this_st_inhibition_and_rollback(self):
        state=self.post('demo',{'sample':'SystemLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':25})
        def now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertIsNone(values(step())['TaskWords[1]']);write('ReadTaskTiming',True);before=now()
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(before[key],after[key])
        write('TaskTimingIndex',1);v=values(step())
        self.assertEqual(v['TaskWords[1]'],v['StBackgroundTaskLast']);self.assertEqual(v['TaskWords[1]'],v['ThisBackgroundTaskLast'])
        for task in ('Fast','Slow'):
            self.assertEqual(v[task+'TaskLast'],v['St'+task+'TaskLast']);self.assertEqual(v[task+'TaskLast'],v['This'+task+'TaskLast']);self.assertGreaterEqual(v[task+'TaskMax'],v[task+'TaskLast'])
        self.assertEqual([v[f'TaskWords[{i}]'] for i in (0,2,3)],[101,77,999])
        write('ControlTasks',True);write('TaskInhibitCommand',1);step();first=self.post('report',{})['task_scan_timing']['tasks']['fasttask'];step();second=self.post('report',{})['task_scan_timing']['tasks']['fasttask'];self.assertEqual(first,second)
        write('ReadTaskTiming',False);write('TaskTimingIndex',99);old=values(now());v=values(step());self.assertEqual(v['FastTaskLast'],old['FastTaskLast']);self.assertEqual(v['TaskWords[1]'],old['TaskWords[1]'])
        report=self.post('report',{})['task_scan_timing'];self.assertEqual(report['tasks_available'],3);self.assertFalse(report['native_protocol_expanded']);self.assertFalse(report['native_runtime_parity'])

    def test_system_lab_this_contexts_named_snapshots_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'SystemLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':25})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertIsNone(values(step())['ThisWords[1]']);write('ReadThis',True);before=state_now()
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close();after=state_now()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key])
        write('ThisIndex',1);write('ReadTiming',True);write('TimingIndex',1);v=values(step())
        self.assertEqual((v['ThisWatchdog'],v['StThisWatchdog'],v['ThisFastRate'],v['ThisSlowRate'],v['ThisFastPriority'],v['ThisSlowPriority']),(500000,500000,10000,25000,2,5))
        self.assertEqual(v['ThisWords[1]'],v['StThisProgramLast']);self.assertEqual(v['ThisWords[1]'],v['TimingWords[1]']);self.assertGreaterEqual(v['ThisProgramMax'],v['ThisWords[1]'])
        self.assertEqual([v[f'ThisWords[{i}]'] for i in (0,2)],[101,999])
        before={k:value for k,value in v.items() if k.startswith(('This','StThis'))};write('ReadThis',False);write('ThisIndex',99);v=values(step())
        for key,value in before.items():
            if key!='ThisIndex':self.assertEqual(v[key],value)
        report=self.post('report',{})['system_values'];self.assertIn('THIS',report['configuration']['current_instance']);self.assertFalse(report['timing']['native_runtime_parity'])

    def test_system_lab_task_starts_intervals_st_windows_and_rollback(self):
        self.post('demo',{'sample':'SystemLab'})
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':25})
        values=lambda t:{row['name']:row['value'] for row in t['tags']}
        t=step();v=values(t);self.assertEqual(v['TaskStartIndex'],99);self.assertIsNone(v['TaskStartWords[1]'])
        self.assertIsNone(v['TaskMinTimeWords[1]']);self.assertIsNone(v['TaskMaxTimeWords[1]'])
        write('ReadTypedTimes',True);write('TaskStartIndex',1);write('ReadTaskStarts',True)
        prior=self.post('report',{})['task_scan_timing']['tasks'];v=values(step())
        self.assertEqual(int(v['ThisTaskStart']),prior['backgroundtask']['start_time_us']);self.assertEqual(v['StTaskStart'],v['ThisTaskStart'])
        import struct
        word=lambda prefix:struct.unpack('<Q',struct.pack('<ii',int(v[prefix+'[1]']),int(v[prefix+'[2]'])))[0]
        self.assertEqual(word('TaskStartWords'),prior['fasttask']['start_time_us'])
        self.assertEqual(word('TaskMinWords'),word('StTaskMin'));self.assertEqual(word('TaskMaxWords'),word('StTaskMax'))
        self.assertEqual(word('TaskMinTimeWords'),word('TaskMinWords'))
        self.assertEqual(word('TaskMaxTimeWords'),word('TaskMaxWords'))
        for prefix in ('TaskStartWords','TaskMinWords','TaskMaxWords','StTaskMin','StTaskMax','TaskMinTimeWords','TaskMaxTimeWords'):
            self.assertEqual((int(v[prefix+'[0]']),int(v[prefix+'[3]'])),(101,999))
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertEqual((int(v['FastMinAfterReset']),int(v['FastMaxAfterReset'])),(-1,-1))
        write('ResetTaskIntervals',True)
        timings=self.post('report',{})['task_scan_timing'];write('TaskStartDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:step()
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        for key in ('tags','scan','ms','task_schedule','routines'):self.assertEqual(after[key],before[key])
        self.assertEqual(self.post('report',{})['task_scan_timing'],timings)
        write('TaskStartDivisor',1);v=values(step())
        self.assertEqual((int(v['FastMinAfterReset']),int(v['FastMaxAfterReset'])),(0,0))
        write('ResetTaskIntervals',False);write('ReadTaskStarts',False);write('TaskStartIndex',99);step()

    def test_integer_lab_lreal_storage_precision_conversions_and_atomic_recovery(self):
        self.post('demo',{'sample':'IntegerLab'})
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':10})
        values=lambda t:{row['name']:row['value'] for row in t['tags']}
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        v=values(step());self.assertEqual(v['DoubleIndex'],99);self.assertIsNone(v['DoubleCopies[1]'])
        write('DoubleIndex',1);write('EnableDouble',True);v=values(step())
        self.assertEqual(v['DoubleCopies[1]'],1.0000000000000002);self.assertEqual(v['DoubleRounded'],1.0)
        self.assertEqual(v['DoubleFromInt'],9007199254740991.0);self.assertEqual(int(v['DoubleAsInteger']),1);self.assertEqual(v['DoubleClear'],0.0)
        self.assertEqual((v['DoubleCopies[0]'],v['DoubleCopies[2]']),(101.125,999.5))
        write('DoubleInput',3.5);write('DoubleDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:step()
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        for key in ('tags','scan','ms','task_schedule','routines'):self.assertEqual(after[key],before[key])
        write('DoubleDivisor',1);v=values(step());self.assertEqual(v['DoubleCopies[1]'],3.5);self.assertEqual(int(v['DoubleAsInteger']),4)
        write('EnableDouble',False);write('DoubleIndex',99);step()

    def test_integer_lab_lreal_math_precision_conditions_and_atomic_recovery(self):
        self.post('demo',{'sample':'IntegerLab'})
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':10})
        values=lambda t:{row['name']:row['value'] for row in t['tags']}
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        v=values(step());self.assertEqual(v['DoubleMathIndex'],99);self.assertIsNone(v['DoubleMathResults[1]'])
        write('DoubleMathIndex',1);write('EnableDoubleMath',True);v=values(step())
        self.assertEqual(v['DoubleSum'],2.0);self.assertEqual(v['DoubleDifference'],2**-52);self.assertEqual(v['DoubleRemainder'],2**-52)
        self.assertEqual(v['DoubleProduct'],1.0000000000000002);self.assertEqual(v['DoubleQuotient'],1.0000000000000002)
        self.assertEqual(v['DoubleNegated'],-1.0000000000000002);self.assertEqual(v['DoubleAbsolute'],1.0000000000000002)
        self.assertEqual([v[n] for n in ('DoubleEq','DoubleNe','DoubleLt','DoubleLe','DoubleGt','DoubleGe','DoubleInLimits')],[False,True,False,False,True,True,True])
        self.assertEqual((v['DoubleMathResults[0]'],v['DoubleMathResults[2]']),(101.125,999.5))
        for tag in ('DoubleB','DoubleMathDivisor'):
            write(tag,0);before=state_now()
            with self.assertRaises(HTTPError) as caught:step()
            self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
            for key in ('tags','scan','ms','task_schedule','routines'):self.assertEqual(after[key],before[key])
            write(tag,1);step()
        write('EnableDoubleMath',False);write('DoubleMathIndex',99);step()

    def test_math_lab_lreal_advanced_precision_domains_and_atomic_recovery(self):
        import math
        self.post('demo',{'sample':'MathLab'})
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':10})
        values=lambda t:{row['name']:row['value'] for row in t['tags']}
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        v=values(step());self.assertEqual(v['LrealIndex'],99);self.assertIsNone(v['LrealResults[1]'])
        write('LrealIndex',1);write('LrealMath',True);v=values(step())
        self.assertEqual(v['LrealSqr'],3.0000000000000004);self.assertEqual(v['LrealLn'],2.2204460492503128e-16);self.assertEqual(v['LrealPower'],1.0000000000000004)
        for name,expected in [('LrealLog',math.log10(1.0000000000000002)),('LrealDeg',math.degrees(0.5)),('LrealRad',math.pi),('LrealSin',math.sin(0.5)),('LrealCos',math.cos(0.5)),('LrealTan',math.tan(0.5)),('LrealAsn',math.asin(0.5)),('LrealAcs',math.acos(0.5)),('LrealAtn',math.atan(0.5))]:self.assertEqual(v[name],expected)
        self.assertEqual((v['LrealResults[0]'],v['LrealResults[2]']),(101.125,999.5))
        for tag,bad,good in [('LrealLogInput',0,1.0000000000000002),('LrealInverse',1.0000000000000002,0.5),('LrealLateDivisor',0,1)]:
            write(tag,bad);before=state_now()
            with self.assertRaises(HTTPError) as caught:step()
            self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
            for key in ('tags','scan','ms','task_schedule','routines'):self.assertEqual(after[key],before[key])
            write(tag,good);step()
        write('LrealMath',False);write('LrealIndex',99);step()

    def test_math_lab_lreal_truncation_precision_wide_ranges_and_atomic_recovery(self):
        self.post('demo',{'sample':'MathLab'})
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':10})
        values=lambda t:{row['name']:row['value'] for row in t['tags']}
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        v=values(step());self.assertEqual(v['TrnIndex'],99);self.assertIsNone(v['TrnResults[1]'])
        write('TrnIndex',1);write('TrnEnabled',True);v=values(step())
        for name,expected in [('TrnResults[1]',16777217.0),('TrnDint',16777217),('TrnReal',16777216.0),('TrnLint','9007199254740991'),('TrnUlint','18446744073709549568'),('TrnFromReal',-16.0)]:self.assertEqual(v[name],expected)
        self.assertEqual((v['TrnResults[0]'],v['TrnResults[2]']),(101.125,999.5))
        for tag,bad,good in [('TrnSignedInput',float(2**63),9007199254740991.0),('TrnUnsignedInput',float(2**64),18446744073709549568.0),('TrnDivisor',0,1)]:
            write(tag,bad);before=state_now()
            with self.assertRaises(HTTPError) as caught:step()
            self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
            for key in ('tags','scan','ms','task_schedule','routines'):self.assertEqual(after[key],before[key])
            write(tag,good);step()
        write('TrnInput',-3.9999999999999996);v=values(step());self.assertEqual(v['TrnDint'],-3)
        write('TrnEnabled',False);write('TrnIndex',99);step()

    def test_copy_lab_lreal_images_partial_bytes_and_atomic_recovery(self):
        self.post('demo',{'sample':'CopyLab'})
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':10})
        values=lambda t:{row['name']:row['value'] for row in t['tags']}
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        v=values(step());self.assertEqual(v['DoubleCopyIndex'],99);self.assertIsNone(v['DoubleResults[1]'])
        write('DoubleCopyIndex',1);write('DoubleCopy',True);v=values(step())
        self.assertEqual(v['DoubleImage'],'4607182418800017409');self.assertEqual((v['DoubleWords[0]'],v['DoubleWords[1]']),(1,1072693248))
        for name in ('DoubleRoundtrip','DoubleResults[1]','DoublePartial'):self.assertEqual(v[name],1.0000000000000002)
        self.assertEqual((v['DoubleResults[0]'],v['DoubleResults[2]']),(101.125,999.5))
        for tag,bad,good in [('DoubleCopyIndex',99,1),('DoubleInject',True,False),('DoubleDivisor',0,1)]:
            write(tag,bad);before=state_now()
            with self.assertRaises(HTTPError) as caught:step()
            self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
            for key in ('tags','scan','ms','task_schedule','routines'):self.assertEqual(after[key],before[key])
            write(tag,good);step()
        write('DoubleInput',5e-324);v=values(step());self.assertEqual(v['DoubleImage'],'1');self.assertEqual(v['DoubleRoundtrip'],5e-324)
        write('DoubleCopy',False);write('DoubleCopyIndex',99);step()

    def test_integer_lab_mixed_lreal_precision_and_atomic_recovery(self):
        self.post('demo',{'sample':'IntegerLab'})
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':10})
        values=lambda t:{row['name']:row['value'] for row in t['tags']}
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        v=values(step());self.assertEqual(v['MixedDoubleIndex'],99);self.assertIsNone(v['MixedDoubleResults[1]'])
        write('MixedDoubleIndex',1);write('EnableMixedDouble',True);v=values(step())
        expected=dict(MixedDoubleAdd=16777218.0,MixedDoubleSubtract=2**-52,MixedDoubleMultiply=16777217.000000004,MixedDoubleDivide=.5000000000000001,MixedDoubleRemainder=1.0000000000000002,MixedDoubleWide=0.0,MixedDoubleUnsigned=float(2**64))
        for name,value in expected.items():self.assertEqual(v[name],value)
        self.assertEqual((v['MixedDoubleResults[0]'],v['MixedDoubleResults[2]']),(101.125,999.5))
        for tag,bad,good in [('MixedDoubleIndex',99,1),('MixedDoubleDivisor',0,2),('MixedDoubleLateDivisor',0,1)]:
            write(tag,bad);before=state_now()
            with self.assertRaises(HTTPError) as caught:step()
            self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
            for key in ('tags','scan','ms','task_schedule','routines'):self.assertEqual(after[key],before[key])
            write(tag,good);step()
        write('EnableMixedDouble',False);write('MixedDoubleIndex',99);step()

    def test_integer_lab_mixed_lreal_comparisons_and_atomic_recovery(self):
        self.post('demo',{'sample':'IntegerLab'})
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':10})
        values=lambda t:{row['name']:row['value'] for row in t['tags']}
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        v=values(step());self.assertEqual(v['DoubleCompareIndex'],99);self.assertFalse(v['DoubleCompareEq'])
        write('DoubleCompareIndex',1);write('EnableDoubleCompare',True);v=values(step())
        expected=dict(Eq=True,Ne=False,Lt=False,Le=False,Gt=True,Ge=True,InLimit=True,ReverseLimit=False,WideEqual=True,UnsignedEqual=True,TinyGreater=True)
        for suffix,value in expected.items():self.assertIs(v['DoubleCompare'+suffix],value)
        self.assertEqual(v['DoubleCompareLint'],'9007199254740993');self.assertEqual(v['DoubleCompareUlint'],'18446744073709551615')
        self.assertEqual((v['DoubleCompareValues[0]'],v['DoubleCompareValues[1]'],v['DoubleCompareValues[2]']),(101.125,16777217.0,999.5))
        for tag,bad,good in [('DoubleCompareIndex',99,1),('DoubleCompareLateDivisor',0,1)]:
            write(tag,bad);before=state_now()
            with self.assertRaises(HTTPError) as caught:step()
            self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
            for key in ('tags','scan','ms','task_schedule','routines'):self.assertEqual(after[key],before[key])
            write(tag,good);step()
        write('DoubleCompareValues[1]',16777218.0);v=values(step());self.assertTrue(v['DoubleCompareInLimit']);self.assertTrue(v['DoubleCompareReverseLimit']);self.assertTrue(v['DoubleCompareNe'])
        write('EnableDoubleCompare',False);write('DoubleCompareIndex',99);v=values(step())
        for suffix in expected:self.assertFalse(v['DoubleCompare'+suffix])

    def test_running_version_matches_html_api_and_session_before_and_after_import(self):
        self.assertEqual(self.session['app_version'], __version__)
        html = self.get('/').decode()
        self.assertIn(f'id="app-version">{__version__}<', html)
        self.assertIn(f'<title>LogixLab {__version__} · Offline PLC lab</title>', html)
        self.assertNotIn('__LOGIXLAB_VERSION__', html)
        empty = self.post('settings', {'converter': ''})
        self.assertFalse(empty['loaded'])
        self.assertEqual(empty['app_version'], __version__)
        self.assertFalse(empty['desktop']['tray_available'])
        loaded = self.post('demo', {'sample': 'ConveyorDemo'})
        self.assertEqual(loaded['app_version'], __version__)
        self.assertEqual(loaded['version'], '35')
        self.assertIn(__version__, self.get('/').decode())

    def test_copy_lab_bit_images_partial_elements_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'CopyLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step():return self.post('step',{'dt':10})
        v=values(step());self.assertEqual((v['BitPattern'],v['FloatOutput'],v['Roundtrip']),(1065353216,1,1))
        self.assertEqual([v['Packed['+str(i)+']'] for i in range(3)],[0x04030201,0x11223305,0x55667788])
        self.assertEqual([v['DecodedBytes['+str(i)+']'] for i in range(8)],[1,2,3,4,5,51,34,17])
        write('FloatInput',2);write('CopyLength',-1);before=state_now()
        with self.assertRaises(HTTPError) as caught:step()
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('CopyLength',20);v=values(step());self.assertEqual((v['BitPattern'],v['Roundtrip']),(1073741824,2))
        write('IntegerInput',2143289344);before=state_now()
        with self.assertRaises(HTTPError) as caught:step()
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now();self.assertEqual(after['tags'],before['tags'])
        write('IntegerInput',-1071644672);v=values(step());self.assertEqual(v['FloatOutput'],-2.5)
        report=self.post('report',{});self.assertTrue(report['numeric_copy']['available']);self.assertFalse(report['numeric_copy']['native_runtime_parity'])
        self.assertIn('copy-demo',self.get('/').decode())

    def test_regulator_lab_closed_loop_disabled_timing_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'RegulatorLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step():return self.post('step',{'dt':125})
        self.assertEqual(values(step())['ControlOutput'],0);v=values(step());self.assertEqual((v['ControlOutput'],v['Feedback']),(10,1.25))
        write('Setpoint',8);write('FaultDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:step()
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);v=values(step());self.assertEqual((v['ControlOutput'],v['Feedback']),(10,2.34375))
        feedback=v['Feedback'];write('SampleTime',0);v=values(step());self.assertEqual((v['ControlOutput'],v['Feedback']),(10,feedback))
        write('SampleTime',-1);v=values(step());self.assertEqual((v['Feedback'],v['PIState.Status']),(feedback,-2147483647))
        write('SampleTime',0.125);write('CallLogic',False);v=values(step());self.assertEqual(v['Feedback'],feedback)
        report=self.post('report',{});self.assertEqual(report['st_pi']['instructions'],['PI'])
        self.assertFalse(report['st_pi']['native_runtime_parity']);self.assertIn('regulator-demo',self.get('/').decode())

    def test_curve_delay_lab_interpolation_resize_health_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'CurveDelayLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step(curve,delay):
            state=self.post('step',{'dt':250});v=values(state)
            self.assertEqual((v['CurveOutput'],v['DelayedOutput']),(curve,delay));return state
        step(0,0);write('Input',5);step(50,0);write('Input',10);step(100,0);write('Input',15);step(75,50)
        write('DelaySeconds',0.75);step(75,100);write('InputFault',True);step(75,100)
        write('InputFault',False);write('Input',20);step(50,50);write('SelectSecond',True);write('Input',10);step(200,50)
        write('Input',20);write('FaultDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:self.post('step',{'dt':250})
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);step(400,50);write('DelaySeconds',0);step(400,400)
        write('X2[1]',0);state=step(400,400);self.assertEqual(values(state)['CurveState.Status'],9)
        write('X2[1]',10);state=step(400,400);self.assertEqual(values(state)['CurveState.Status'],0)
        report=self.post('report',{});self.assertEqual(report['st_curves']['instructions'],['DEDT','FGEN'])
        self.assertFalse(report['st_curves']['native_runtime_parity']);self.assertIn('curve-demo',self.get('/').decode())

    def test_process_lab_selection_derivative_requests_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'ProcessLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step(selected,rate):
            state=self.post('step',{'dt':250});v=values(state)
            self.assertEqual((v['SelectedValue'],v['ChangePerSecond']),(selected,rate));return state
        step(30,0);write('Sensor2',40);step(40,40);write('Fault2',True);step(30,-40)
        write('SelectMode',2);step(10,-80);write('SelectMode',4);step(20,40)
        write('SelectMode',0);write('SelectorState.OperProgReq',True);write('FaultDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:self.post('step',{'dt':250})
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);state=step(30,40);v=values(state)
        self.assertTrue(v['SelectorState.ProgOper']);self.assertFalse(v['SelectorState.OperProgReq'])
        write('BypassDerivative',True);step(30,30);write('SampleTime',-1);state=step(30,30)
        self.assertEqual(values(state)['DerivativeState.Status'],-2147483647)
        report=self.post('report',{});self.assertEqual(report['st_select']['instructions'],['ESEL']);self.assertEqual(report['st_derivative']['instructions'],['DERV'])
        self.assertFalse(report['st_select']['native_runtime_parity']);self.assertIn('process-demo',self.get('/').decode())

    def test_accumulator_lab_totals_integration_holds_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'AccumulatorLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step(total,integral):
            state=self.post('step',{'dt':250});v=values(state)
            self.assertEqual((v['Total'],v['Integral']),(total,integral));return state
        step(1,0);step(2,0.25);step(3,0.75)
        write('HoldTotal',True);write('HoldHigh',True);step(3,0.75)
        write('InitializeTotal',True);write('InitialTotal',10);write('InitializeIntegral',True);write('InitialIntegral',4)
        step(10,4);write('InitializeTotal',False);write('InitializeIntegral',False);write('HoldTotal',False);write('HoldHigh',False)
        step(11,4.5);state=step(12,5);self.assertTrue(values(state)['HighAlarm'])
        write('Input',-2);write('FaultDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:self.post('step',{'dt':250})
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);step(13,5);step(14,4.5)
        write('SampleTime',-1);state=step(15,4.5);self.assertEqual(values(state)['IntegralState.Status'],-2147483647)
        report=self.post('report',{});self.assertEqual(report['st_accumulate']['instructions'],['INTG','UPDN'])
        self.assertFalse(report['st_accumulate']['native_runtime_parity']);self.assertIn('accumulator-demo',self.get('/').decode())

    def test_digital_lab_startup_edges_dominance_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'DigitalLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step(expected):
            state=self.post('step',{'dt':10});v=values(state)
            self.assertEqual(tuple(v[n] for n in ('DOutput','ToggleOutput','ResetDominantOutput','SetDominantOutput')),expected)
            self.assertEqual(tuple(v[n] for n in ('DComplement','ToggleComplement','ResetComplement','SetComplement')),tuple(not x for x in expected));return state
        write('Clock',True);write('DInput',True);step((False,False,False,True))
        write('Clock',False);step((False,False,False,True));write('Clock',True);write('SetInput',True);write('ResetInput',True)
        step((True,True,False,True));write('DInput',False);step((True,True,False,True))
        write('Clear',True);step((False,False,False,True));write('Clear',False);step((False,False,False,True))
        write('Clock',False);write('SetInput',False);write('ResetInput',False);step((False,False,False,True))
        write('Clock',True);write('DInput',True);write('SetInput',True);write('FaultDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:self.post('step',{'dt':10})
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);state=step((True,True,True,True));self.assertEqual(state['scan'],before['scan']+1)
        write('CallLogic',False);write('Clear',True);write('ResetInput',True);step((True,True,True,True))
        report=self.post('report',{});self.assertEqual(report['st_digital']['instructions'],['DFF','JKFF','RESD','SETD'])
        self.assertFalse(report['st_digital']['native_runtime_parity']);self.assertIn('digital-demo',self.get('/').decode())

    def test_filter_lab_orders_timing_diagnostics_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'FilterLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step(expected,status=0,delta=0.125):
            state=self.post('step',{'dt':125});v=values(state)
            self.assertAlmostEqual(v['Filtered'],expected,places=5);self.assertEqual((v['FilterState.Status'],v['ElapsedSeconds']),(status,delta));return state
        step(0);write('Input',10);step(5);step(10)
        write('SampleTime',0);write('Input',100);step(10,delta=0)
        write('InitializeFilter',True);write('Input',0);step(0,delta=0)
        write('InitializeFilter',False);write('SampleTime',0.125);write('FilterOrder',3);step(0)
        write('Input',10);step(5/3);step(20/3)
        write('FilterOrder',4);step(10,status=5);write('FilterOrder',1);write('SampleTime',-1);step(10,status=-2147483647,delta=0)
        write('SampleTime',0.125);write('Input',0);write('FaultDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:self.post('step',{'dt':125})
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);step(5)
        report=self.post('report',{});self.assertIn('software approximation',report['st_filter']['solver'])
        self.assertFalse(report['st_filter']['native_runtime_parity']);self.assertIn('filter-demo',self.get('/').decode())

    def test_capture_lab_extrema_resets_skip_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'CaptureLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step(expected):
            state=self.post('step',{'dt':10});v=values(state);self.assertEqual((v['Maximum'],v['Minimum']),expected);return state
        write('Input',-7);step((-7.0,-7.0));write('Input',-3);step((-3.0,-7.0))
        write('Input',-12);step((-3.0,-12.0));write('CallCapture',False);write('Input',100);step((-3.0,-12.0))
        write('CallCapture',True);write('ResetCapture',True);write('ResetHigh',5);write('ResetLow',-5);step((5.0,-5.0))
        write('ResetHigh',2);write('ResetLow',-2);step((2.0,-2.0));write('ResetCapture',False);write('Input',0);step((2.0,-2.0))
        write('HighState.Out',-100);write('LowState.Out',100);step((2.0,-2.0))
        write('Input',10);write('FaultDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:self.post('step',{'dt':10})
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);write('Input',1);state=step((2.0,-2.0))
        self.assertEqual(state['scan'],before['scan']+1);self.assertEqual(values(state)['CallCount'],8)
        report=self.post('report',{});self.assertEqual(report['st_capture']['instructions'],['MAXC','MEQ','MINC'])
        self.assertFalse(report['st_capture']['native_runtime_parity']);self.assertIn('capture-demo',self.get('/').decode())

    def test_moving_lab_samples_weights_resize_diagnostics_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'MovingLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):self.post('write',{'tag':tag,'value':value})
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        def step(expected):
            state=self.post('step',{'dt':10});v=values(state)
            self.assertEqual((v['Average'],v['PopulationMean'],v['Deviation']),expected);return v
        write('Input',2);step((2.0,2.0,0.0));write('Input',4);step((3.0,3.0,1.0))
        write('TakeSample',False);write('Input',100);step((3.0,3.0,1.0))
        write('ResetStatistics',True);write('Input',10);step((10.0,10.0,0.0))
        write('ResetStatistics',False);write('TakeSample',True);write('Input',6);step((6.0,6.0,0.0))
        write('Weighted',True);write('Input',8);step((5.5,7.0,1.0))
        write('Window',0);v=step((5.5,7.0,1.0))
        self.assertTrue(v['LengthInvalid']);self.assertTrue(v['InstructionFault']);self.assertEqual(v['MeanState.Status'],5)
        write('Window',2);write('Weighted',False);write('Input',10);step((10.0,10.0,0.0))
        write('Input',14);write('FaultDivisor',0);before=state_now()
        with self.assertRaises(HTTPError) as caught:self.post('step',{'dt':10})
        self.assertEqual(caught.exception.code,400);caught.exception.close();after=state_now()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);v=step((12.0,12.0,2.0));self.assertFalse(v['InstructionFault'])
        report=self.post('report',{});self.assertEqual(report['st_moving']['instructions'],['MAVE','MSTD'])
        self.assertFalse(report['st_moving']['native_runtime_parity']);self.assertIn('moving-demo',self.get('/').decode())

    def test_loop_lab_ranges_breaks_false_calls_and_late_fault_through_http(self):
        state=self.post('demo',{'sample':'LoopLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):self.post('write',{'tag':tag,'value':value})
        state=self.post('step',{'dt':10});v=values(state)
        self.assertEqual((v['Total'],v['Iterations'],v['Index'],v['Completed']),(10,5,5,True))
        write('BreakEnabled',True);state=self.post('step',{'dt':10});v=values(state)
        self.assertEqual((v['Total'],v['Iterations'],v['TailRuns'],v['Index']),(1,3,2,2))
        self.assertTrue(any(row.get('control')=='break' for row in state['trace']))
        write('BreakEnabled',False);write('Start',4);write('Finish',0);write('Increment',-2)
        state=self.post('step',{'dt':10});v=values(state)
        self.assertEqual((v['Total'],v['Iterations'],v['Index']),(6,3,-2))
        write('Enabled',False);state=self.post('step',{'dt':10});v=values(state)
        self.assertEqual((v['Iterations'],v['Index'],v['Completed']),(0,-2,False))
        write('Enabled',True);write('FaultDivisor',0);before=json.load(urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3))
        with self.assertRaises(HTTPError) as caught:self.post('step',{'dt':10})
        self.assertEqual(caught.exception.code,400);caught.exception.close()
        after=json.load(urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3));self.assertEqual((after['tags'],after['scan'],after['ms']),(before['tags'],before['scan'],before['ms']))
        write('FaultDivisor',1);state=self.post('step',{'dt':10});v=values(state)
        self.assertEqual((v['Total'],v['Iterations'],v['Index'],state['scan']),(6,3,-2,before['scan']+1))
        report=self.post('report',{});self.assertIn('FOR',report['supported_instructions'])
        self.assertIn('BRK',report['supported_instructions']);self.assertFalse(report['ladder_loops']['native_runtime_parity'])

    def test_task_lab_schedules_through_http_and_reports_pending_first_scans(self):
        state = self.post('demo', {'sample': 'TaskLab'})
        self.assertEqual(state['blockers'], [])
        self.assertEqual(len(state['task_schedule']['tasks']), 3)
        self.assertTrue(state['controller']['first_scan_pending'])
        state = self.post('step', {'dt': 5})
        self.assertTrue(state['controller']['first_scan_pending'])
        for _ in range(5): state = self.post('step', {'dt': 5})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual([values[k] for k in ('BackgroundCount','FastCount','SlowCount')], [6,3,1])
        self.assertFalse(state['controller']['first_scan_pending'])
        self.assertEqual([t['executions'] for t in state['task_schedule']['tasks']], [6,3,1])
        self.assertEqual(state['controller']['scan_interval_ms'], 10)

    def test_event_lab_priority_dispatch_overlap_and_task_context_through_http(self):
        self.assertIn('id="event-demo"', self.get('/').decode())
        state = self.post('demo', {'sample': 'EventLab'})
        self.assertEqual(state['blockers'], [])
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['EventCount'], 0)
        self.assertTrue(state['controller']['first_scan_pending'])
        self.post('write', {'tag': 'TriggerRLL', 'value': True})
        self.post('write', {'tag': 'TriggerST', 'value': True})
        self.post('write', {'tag': 'TriggerDeferred', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual((values['EventCount'], values['RllSeen'], values['StSeen']), (2, 1, 2))
        self.assertEqual(values['EventFirst'], 1)
        self.assertEqual([values[k] for k in ('DeferredCount','RllDeferredSeen','StDeferredSeen')], [1,0,1])
        self.assertEqual(state['task_schedule']['tasks'][3]['event_pending_requests_coalesced'], 1)
        self.assertTrue(state['controller']['first_scan_pending'])
        self.assertEqual(values['TimeoutDemoRuns'], 0)
        self.post('write', {'tag': 'SelfTrigger', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['EventCount'], 4)
        self.assertEqual(state['task_schedule']['tasks'][2]['event_instruction_overlaps'], 2)
        self.assertEqual(state['task_schedule']['tasks'][2]['executions'], 4)
        state = self.post('step', {'dt': 5})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual((values['TimeoutDemoRuns'], values['TimeoutDemoFirst'], values['TimeoutDemoStatus']), (1, 1, 2))
        self.assertFalse(state['controller']['first_scan_pending'])
        self.assertFalse(self.post('report', {})['event_execution']['native_cpu_timing'])

    def test_system_lab_gsv_program_routine_names_and_task_slots(self):
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])
        def values(state):return {row['name']:row['value'] for row in state['tags']}
        before=values(self.post('step',{'dt':25}))
        self.assertEqual((before['ObjectRoutineName'],before['StObjectRoutineName'],
                          before['ObjectTaskSlot'],before['StObjectTaskSlot']),('','',-1,-1))
        self.post('write',{'tag':'ReadObjectIdentity','value':True})
        v=values(self.post('step',{'dt':25}))
        self.assertEqual((v['ObjectProgramName'],v['ObjectRoutineName'],v['ObjectTaskSlot']),
                         ('BackgroundProgram','ReadCurrentInstances',0))
        self.assertEqual((v['StObjectProgramName'],v['StObjectRoutineName'],v['StObjectTaskSlot']),
                         ('FastProgram','ReadSettings',2))
        report=self.post('report',{})['system_values']['configuration']
        self.assertIn('Zero-based slot',report['task_instance'])
        self.assertFalse(report['native_runtime_equivalence'])

    def test_system_lab_controller_device_identity_across_ladder_and_st(self):
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])
        def values(state):return {row['name']:row['value'] for row in state['tags']}
        fields=('DeviceProductCode','DeviceProductRev','DeviceType','DeviceVendor')
        before=values(self.post('step',{'dt':25}))
        self.assertEqual(tuple(before[name] for name in fields),(-1,-1,-1,-1))
        self.assertEqual(before['DeviceNameBytes[0]'],-1)
        self.post('write',{'tag':'ReadControllerDevice','value':True})
        after=values(self.post('step',{'dt':25}))
        self.assertEqual(tuple(after[name] for name in fields),(168,0x0B23,14,1))
        self.assertEqual(bytes(after[f'DeviceNameBytes[{i}]'] for i in range(33)),b'\x09' + b'1756-L85E' + bytes(23))

    def test_system_lab_module_status_preserves_dint_high_word(self):
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])

        def step_values():
            state=self.post('step',{'dt':25})
            tags={row['name']:row['value'] for row in state['tags']}
            return tags['IoLedStatus'],tags['IoForceStatus']

        self.assertEqual(step_values(),(-1,0x1234FFFF))
        self.post('write',{'tag':'ReadModuleStatus','value':True})
        self.assertEqual(step_values(),(0,0x12340000))
        self.post('write',{'tag':'IoForceStatus','value':-1})
        self.post('write',{'tag':'ReadConfig','value':False})
        self.assertEqual(step_values(),(0,-1))

    def test_system_lab_controller_source_flags_in_ladder_and_st(self):
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])
        names=('UseProducerRpi','RedundancyFlag','RetainTestEdits','FirmwareUpdateInhibit')

        def step_values():
            state=self.post('step',{'dt':25})
            values={row['name']:row['value'] for row in state['tags']}
            return tuple(values[name] for name in names)

        self.assertEqual(step_values(),(-1,-1,-1,False))
        self.post('write',{'tag':'ReadControllerFlags','value':True})
        self.assertEqual(step_values(),(1,0,1,True))
        self.post('write',{'tag':'ReadConfig','value':False})
        self.post('write',{'tag':'RetainTestEdits','value':-1})
        self.post('write',{'tag':'UseProducerRpi','value':-1})
        self.assertEqual(step_values(),(1,0,-1,True))

    def test_system_lab_reads_typed_gsv_settings_without_changing_task_schedule(self):
        self.assertIn('id="system-demo"', self.get('/').decode())
        state = self.post('demo', {'sample': 'SystemLab'})
        self.assertEqual(state['blockers'], [])
        state = self.post('step', {'dt': 25})
        values = {row['name']: row['value'] for row in state['tags']}
        for name, expected in {'FastRate': 10000, 'SlowRate': 25000, 'FastWatchdog': 500000, 'FastPriority': 2,
                               'SlowPriority': 5, 'CommTimeSlice': 30, 'ShareUnused': 1, 'FastInhibit': 0, 'FastNoOutput': 0}.items():
            self.assertEqual(values[name], expected)
        self.assertEqual(values['FastTaskName'], 'FastTask')
        self.assertEqual(values['ControllerName'], 'SystemLab')
        self.assertEqual(values['StSlowRate'], values['SlowRate'])
        self.assertEqual(values['StCommTimeSlice'], values['CommTimeSlice'])
        self.assertEqual([t['executions'] for t in state['task_schedule']['tasks']], [1, 2, 1])
        self.post('write', {'tag': 'ReadConfig', 'value': False})
        self.post('write', {'tag': 'FastRate', 'value': -1})
        state = self.post('step', {'dt': 25})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['FastRate'], -1)
        self.assertEqual([t['executions'] for t in state['task_schedule']['tasks']], [2, 5, 2])
        self.post('write', {'tag': 'ReadConfig', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['FastRate'], 10000)
        self.assertFalse(self.post('report', {})['system_values']['configuration']['native_runtime_equivalence'])

    def test_bit_lab_packs_values_through_http_and_reports_instruction_scope(self):
        state = self.post('demo', {'sample': 'BitLab'})
        self.assertEqual(state['blockers'], [])
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Status'], 0x123400aa)
        self.assertEqual(values['Packed'], -305397590)
        self.assertEqual(values['LowWord'], 170)
        self.assertEqual(values['HighByte'], -19)
        self.assertEqual(values['MixedMask'], -171)
        self.assertEqual(values['Overlap'], 0x2344)
        self.assertEqual(values['Truncated'], -15150)
        self.assertTrue(values['BitOK'])
        report = self.post('report', {})
        self.assertEqual(report['bit_transfer']['instructions'], ['BTD', 'MVM'])
        self.assertFalse(report['bit_transfer']['native_math_status'])

    def test_alarm_lab_delay_acknowledge_and_false_rung_through_http(self):
        state = self.post('demo', {'sample': 'AlarmLab'})
        self.assertEqual(state['blockers'], [])

        def write(tag, value):
            self.post('write', {'tag': tag, 'value': value})

        def step():
            state = self.post('step', {'dt': 10})
            return {row['name']: row['value'] for row in state['tags']}

        write('MotorAlarm.UseProgTime', True)
        write('MotorAlarm.ProgTime', '9007199254740993')
        write('MotorAlarm.Severity', 0)
        write('Trip', True)
        pending = step()
        self.assertFalse(pending['MotorAlarm.InAlarm'])
        self.assertEqual(pending['MotorAlarm.InAlarmTime'], '0')
        write('MotorAlarm.ProgTime', '9007199254740995')
        self.assertFalse(step()['MotorAlarm.InAlarm'])
        active = step()
        self.assertTrue(active['MotorAlarm.InAlarmUnack'])
        self.assertEqual(active['MotorAlarm.AlarmCount'], 1)
        self.assertEqual(active['MotorAlarm.InAlarmTime'], '9007199254740993')
        self.assertEqual(active['MotorAlarm.Status'], 5)
        self.assertEqual(active['MotorAlarm.Severity'], 0)
        write('MotorAlarm.Severity', 500)
        write('Trip', False)
        write('Acknowledge', True)
        write('Healthy', False)
        latched = step()
        self.assertTrue(latched['MotorAlarm.InAlarm'])
        self.assertTrue(latched['MotorAlarm.Acked'])
        self.assertEqual(latched['MotorAlarm.AckTime'], '9007199254740995')
        self.assertEqual(latched['MotorAlarm.Status'], 0)
        self.assertFalse(latched['MotorAlarm.In'])
        self.assertTrue(latched['SignalAlarm.InAlarm'])
        write('ResetAlarm', True)
        self.assertFalse(step()['MotorAlarm.InAlarm'])
        report = self.post('report', {})['ladder_alarms']
        self.assertTrue(report['false_rung_executes'])
        self.assertFalse(report['native_runtime_parity'])

    def test_alarm_lab_consumes_shelf_request_after_deferred_prescan(self):
        self.assertEqual(self.post('demo', {'sample': 'AlarmLab'})['blockers'], [])

        def request_shelf():
            self.post('write', {'tag': 'MotorAlarm.OperShelve', 'value': True})

        def step():
            state = self.post('step', {'dt': 10})
            return {row['name']: row['value'] for row in state['tags']}

        request_shelf()
        first = step()
        self.assertFalse(first['MotorAlarm.Shelved'])
        self.assertFalse(first['MotorAlarm.OperShelve'])
        request_shelf()
        second = step()
        self.assertTrue(second['MotorAlarm.Shelved'])
        self.assertFalse(second['MotorAlarm.OperShelve'])

    def test_alarm_lab_analog_delay_and_deadband_through_http(self):
        self.assertEqual(self.post('demo', {'sample': 'AlarmLab'})['blockers'], [])

        def write(tag, value):
            self.post('write', {'tag': tag, 'value': value})

        def step():
            state = self.post('step', {'dt': 10})
            return {row['name']: row['value'] for row in state['tags']}

        write('AnalogRun', True)
        write('Pressure', 80)
        self.assertFalse(step()['PressureAlarm.HInAlarm'])
        self.assertFalse(step()['PressureAlarm.HInAlarm'])
        self.assertTrue(step()['PressureAlarm.HInAlarm'])
        write('Pressure', 90)
        self.assertTrue(step()['PressureAlarm.HHInAlarm'])
        write('Pressure', 88)
        self.assertTrue(step()['PressureAlarm.HHInAlarm'])
        write('Pressure', 87.5)
        row = step()
        self.assertFalse(row['PressureAlarm.HHInAlarm'])
        self.assertTrue(row['PressureAlarm.HInAlarm'])
        self.assertEqual(row['PressureAlarm.HHAlarmCount'], 1)

    def test_alarm_lab_analog_rate_and_acknowledgment_through_http(self):
        self.assertEqual(self.post('demo', {'sample': 'AlarmLab'})['blockers'], [])

        def write(tag, value):
            self.post('write', {'tag': tag, 'value': value})

        def step():
            state = self.post('step', {'dt': 10})
            return {row['name']: row['value'] for row in state['tags']}

        write('AnalogRun', True)
        write('PressureAlarm.ROCPeriod', 0.01)
        write('PressureAlarm.ROCPosLimit', 100)
        write('PressureAlarm.ROCNegLimit', 100)
        write('Pressure', 50)
        self.assertEqual(step()['PressureAlarm.ROC'], 0.0)
        write('Pressure', 51)
        self.assertTrue(step()['PressureAlarm.ROCPosInAlarmUnack'])
        write('Pressure', 50)
        row = step()
        self.assertEqual(row['PressureAlarm.ROC'], -100.0)
        self.assertFalse(row['PressureAlarm.ROCPosInAlarm'])
        self.assertTrue(row['PressureAlarm.ROCNegInAlarmUnack'])
        write('AckAnalog', True)
        write('Pressure', 49)
        row = step()
        self.assertTrue(row['PressureAlarm.ROCNegInAlarm'])
        self.assertTrue(row['PressureAlarm.ROCPosAcked'])
        self.assertTrue(row['PressureAlarm.ROCNegAcked'])
        self.assertFalse(row['PressureAlarm.AnyInAlarmUnack'])

    def test_string_lab_executes_rll_st_and_reflects_input_search_changes(self):
        state = self.post('demo', {'sample': 'StringLab'})
        self.assertEqual(state['blockers'], [])
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Location'], 10)
        self.assertEqual(values['StPosition'], 10)
        self.assertEqual(values['MissingPos'], 0)
        self.assertEqual(values['RllEdited'], 'PART=ABC;<OK>STATE=IDLE')
        self.assertEqual(values['Cleaned'], values['SourceText'])
        self.assertEqual(values['StEdited'], values['SourceText'])
        self.assertTrue(values['AllOK'])
        self.assertEqual(values['MidDest'], '')
        self.post('write', {'tag': 'SearchText', 'value': 'PART'})
        self.post('write', {'tag': 'MidWindow', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Location'], 1)
        self.assertEqual(values['StPosition'], 1)
        self.assertFalse(values['AllOK'])
        self.assertEqual(values['MidDest'], 'BC')
        self.assertIsNone(values['MidSource.DATA[0]'])
        self.assertIsNone(values['MidSource.DATA[3]'])
        self.assertEqual(self.post('report', {})['string_operations']['instructions'], ['DELETE','FIND','INSERT'])

    def test_string_lab_ladder_relations_compare_literals_and_rollback_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'StringLab'})['blockers'], [])
        def write(tag, value):
            return self.post('write', {'tag':tag, 'value':value})
        def step():
            return self.post('step', {'dt':10})
        def results(state):
            row = {tag['name']:tag['value'] for tag in state['tags']}
            return tuple(row[name] for name in ('CompareLabel','ComparePrefix','CompareCase'))
        self.assertEqual(results(step()), (False, False, False))
        before = write('CompareStrings', True)
        with self.assertRaises(HTTPError) as error:
            step()
        with error.exception as failure:
            self.assertEqual(failure.code, 400)
            self.assertIn('outside bounds', failure.read().decode())
        request = Request(self.url+'/api/state', headers={'X-Logix-Token':self.token})
        with urlopen(request, timeout=3) as response:
            after = json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','trace'):
            self.assertEqual(after[key], before[key], key)
        write('CompareStringIndex', 0)
        write('IndexedSource[0]', 'ABC')
        state = step()
        self.assertEqual(results(state), (True, True, True))
        relation = next(op for routine in state['routines'] for rung in routine.get('rungs', [])
                        for op in rung['nodes'] if op.get('name') == 'NEQ' and op['args'] == ["'A'","'a'"])
        self.assertEqual({ref:info['value'] for ref,info in relation['literal_values'].items()}, {"'A'":'A', "'a'":'a'})
        write('SourceText', 'PART=ABC;STATE=RUN')
        write('IndexedSource[0]', 'AB')
        self.assertEqual(results(step()), (False, False, True))
        profile = self.post('report', {})['string_operations']['comparison_literals']
        self.assertEqual(len(profile['instructions']), 6)
        self.assertFalse(profile['native_runtime_parity'])

    def test_string_lab_ladder_mov_clips_and_preserves_literal_punctuation_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'StringLab'})['blockers'], [])
        def write(tag, value):
            return self.post('write', {'tag':tag, 'value':value})
        def step():
            return self.post('step', {'dt':10})
        def values(state):
            return {row['name']:row['value'] for row in state['tags']}
        self.assertIsNone(values(step())['MoveShort.LEN'])
        before = write('MoveStrings', True)
        with self.assertRaises(HTTPError) as error:
            step()
        with error.exception as failure:
            self.assertEqual(failure.code, 400)
            self.assertIn('outside bounds', failure.read().decode())
        request = Request(self.url+'/api/state', headers={'X-Logix-Token':self.token})
        with urlopen(request, timeout=3) as response:
            after = json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','trace'):
            self.assertEqual(after[key], before[key], key)
        write('IndexedSource[0]', 'selected')
        write('MoveStringIndex', 0)
        state = step()
        row = values(state)
        self.assertEqual(row['MoveShort'], 'ABCDEFGHIJKLMNOPQRSTUVWXYZ012345')
        self.assertEqual(row['MoveShort.LEN'], 32)
        self.assertEqual(row['MoveLiteral'], "Line [1], (ready); 'OK' $")
        self.assertEqual(row['MoveSelected'], 'selected')
        self.assertEqual(row['MoveSource'], 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        literal = next(op for routine in state['routines'] for rung in routine.get('rungs', [])
                       for op in rung['nodes'] if op.get('name') == 'MOV' and op['args'][1] == 'MoveLiteral')
        self.assertEqual(literal['literal_values'][literal['args'][0]]['value'], row['MoveLiteral'])
        write('MoveSource', 'AB')
        row = values(step())
        self.assertEqual(row['MoveShort'], 'AB')
        self.assertEqual(row['MoveShort.DATA[31]'], ord('5'))
        self.assertFalse(self.post('report', {})['string_operations']['mov']['native_math_status'])

    def test_string_lab_case_and_real_conversions_in_rll_and_st(self):
        state = self.post('demo', {'sample': 'StringLab'})
        self.assertEqual(state['blockers'], [])
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        for prefix in ('', 'St'):
            self.assertEqual(values[prefix + 'Lowered'], 'abc 09')
            self.assertEqual(values[prefix + 'Uppered'], 'ABC 09')
            self.assertEqual(values[prefix + 'ParsedReal'], -12.5)
            self.assertEqual(values[prefix + 'ParsedInteger'], -12)
            self.assertEqual(values[prefix + 'FormattedReal'], '15.3001003')
            self.assertEqual(values[prefix + 'RoundedText'], '15')
        self.post('write', {'tag': 'RealSource', 'value': -3.5})
        self.post('write', {'tag': 'NumericText', 'value': 'W=-.75/99'})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        for prefix in ('', 'St'):
            self.assertEqual(values[prefix + 'RoundedText'], '-4')
            self.assertEqual(values[prefix + 'FormattedReal'], '-3.5')
            self.assertEqual(values[prefix + 'ParsedInteger'], 0)
            self.assertEqual(values[prefix + 'ParsedReal'], -.75)
        self.post('write', {'tag': 'Convert', 'value': False})
        self.post('write', {'tag': 'CaseText', 'value': 'new'})
        self.post('write', {'tag': 'NumericText', 'value': 'invalid'})
        self.post('write', {'tag': 'RealSource', 'value': 2147483648})
        state = self.post('step', {'dt': 10})
        held = {row['name']: row['value'] for row in state['tags']}
        for prefix in ('', 'St'):
            for name in ('Lowered', 'Uppered', 'ParsedReal', 'ParsedInteger', 'FormattedReal', 'RoundedText'):
                self.assertEqual(held[prefix + name], values[prefix + name])
        report = self.post('report', {})['string_conversions']
        self.assertEqual(report['instructions'], ['LOWER', 'RTOS', 'STOR', 'UPPER'])
        self.assertIn('ties to even', report['dtos_real'])
        self.assertIn('a leading decimal point gives zero', report['stod'])
        self.assertFalse(report['native_formatting_parity'])

    def test_control_lab_shifts_and_fifo_edges_through_http(self):
        state = self.post('demo', {'sample': 'ControlLab'})
        self.assertEqual(state['blockers'], [])
        self.post('step', {'dt': 10})
        self.post('write', {'tag': 'ShiftLeft', 'value': True})
        self.post('write', {'tag': 'Load', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['LeftBits[0]'], 1)
        self.assertEqual(values['LeftBits[1]'], 0x12345679)
        self.assertEqual(values['Queue[0]'], 11)
        self.assertEqual(values['QueueControl.POS'], 1)
        state = self.post('step', {'dt': 10})
        self.assertEqual(next(row['value'] for row in state['tags'] if row['name']=='QueueControl.POS'), 1)
        self.post('write', {'tag': 'Load', 'value': False})
        self.post('write', {'tag': 'Unload', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Outgoing'], 11)
        self.assertEqual(values['QueueControl.POS'], 0)
        self.assertTrue(values['QueueControl.EM'])
        self.assertEqual(values['Queue[3]'], 999)
        self.assertFalse(self.post('report', {})['control_operations']['native_control_layout'])

    def test_sequence_lab_current_rows_compare_feedback_and_teach_while_held(self):
        state = self.post('demo', {'sample': 'SequenceLab'})
        self.assertEqual(state['blockers'], [])
        self.post('step', {'dt': 10})
        self.post('write', {'tag': 'Advance', 'value': True})
        self.post('write', {'tag': 'Feedback', 'value': 1})
        self.post('write', {'tag': 'Teach', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['SequenceControl.POS'], 1)
        self.assertEqual(values['Outputs'], 0x120001)
        self.assertTrue(values['Matches'])
        self.assertEqual(values['Learned[1]'], 40)
        self.post('write', {'tag': 'TeachValue', 'value': 41})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['TeachControl.POS'], 1)
        self.assertEqual(values['Learned[1]'], 41)
        self.assertEqual(values['Patterns[4]'], 999)
        self.assertFalse(self.post('report', {})['sequencer_operations']['native_scan_parity'])

    def test_conversion_lab_bcd_and_st_byte_swapping_through_http(self):
        state = self.post('demo', {'sample': 'ConversionLab'})
        self.assertEqual(state['blockers'], [])
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Packed'], 0x12345678)
        self.assertEqual(values['Decoded'], 12345678)
        self.assertEqual(values['Weighted'], 12345684)
        self.assertEqual(values['Reverse'], 0x78563412)
        self.assertEqual(values['STValue'], 0x34127856)
        self.assertEqual(values['SwappedWords[0]'], -21742)
        self.assertEqual(values['SwappedWords[1]'], 255)
        self.assertEqual(values['SwappedWords[2]'], 999)
        self.assertTrue(values['AllOK'])
        self.assertFalse(self.post('report', {})['numeric_conversions']['native_math_status'])

    def test_math_lab_roots_trig_logs_and_power_through_http(self):
        state = self.post('demo', {'sample': 'MathLab'})
        self.assertEqual(state['blockers'], [])
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Root'], 4.0)
        self.assertEqual(values['Root'], values['CptRoot'])
        self.assertEqual(values['Root'], values['StRoot'])
        self.assertEqual(values['Radians'], values['StAngle'])
        self.assertEqual(values['Log10'], 2.0)
        self.assertEqual(values['Powered'], 8.0)
        self.assertEqual(values['RoundTrip'], 30.0)
        self.assertAlmostEqual(values['Sine'], 0.5, places=6)
        self.assertTrue(values['AllOK'])
        self.assertFalse(self.post('report', {})['real_math']['native_math_status'])

    def test_control_lab_mcr_false_scan_and_late_fault_recovery_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'ControlLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('step',{'dt':10});row=values(self.post('step',{'dt':10}))
        self.assertTrue(row['ZoneOutput']);self.assertTrue(row['ZoneLatch']);self.assertEqual(row['ZoneTimer.ACC'],10)
        self.post('write',{'tag':'ZoneEnable','value':False});self.post('write',{'tag':'ZoneDivisor','value':0})
        state=self.post('step',{'dt':10});row=values(state)
        self.assertEqual((row['ZoneOutput'],row['ZoneTimer.ACC'],row['ZoneScans'],row['AfterZone']),(False,0,2,3))
        self.assertTrue(any(trace.get('mcr_forced_false') for trace in state['trace']))
        self.post('write',{'tag':'ZoneEnable','value':True});before=self.post('write',{'tag':'Load','value':True})
        with self.assertRaises(HTTPError) as context:self.post('step',{'dt':10})
        self.assertEqual(context.exception.code,400);context.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'ZoneDivisor','value':1});row=values(self.post('step',{'dt':10}))
        self.assertEqual((row['QueueControl.POS'],row['ZoneCounter.ACC'],row['ZoneScans'],row['AfterZone']),(1,1,3,4))
        profile=self.post('report',{})['mcr_execution'];self.assertEqual(profile['planned_zones'],1);self.assertFalse(profile['native_runtime_parity'])

    def test_record_lab_fifo_values_guards_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'RecordLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('step',{'dt':10});self.post('write',{'tag':'LoadPart','value':True})
        row=values(self.post('step',{'dt':10}))
        self.assertEqual((row['PartQueue[0].Id'],row['PartQueue[0].Name'],row['PartQueue[0].Lot']),(101,'PART-A','9007199254740993'))
        self.post('write',{'tag':'IncomingPart.Id','value':202});self.post('write',{'tag':'IncomingPart.Name','value':'BETA'})
        row=values(self.post('step',{'dt':10}));self.assertEqual((row['PartControl.POS'],row['PartQueue[0].Id']),(1,101))
        self.post('write',{'tag':'LoadPart','value':False});self.post('step',{'dt':10});self.post('write',{'tag':'LoadPart','value':True});self.post('step',{'dt':10})
        self.post('write',{'tag':'UnloadPart','value':True});row=values(self.post('step',{'dt':10}))
        self.assertEqual((row['OutgoingPart.Id'],row['OutgoingPart.Name'],row['PartQueue[0].Id'],row['PartQueue[2].Lot']),(101,'PART-A',202,'0'))
        self.assertEqual(row['PartQueue[3].Id'],999)
        self.post('write',{'tag':'LoadPart','value':False});self.post('write',{'tag':'UnloadPart','value':False});self.post('step',{'dt':10})
        self.post('write',{'tag':'LoadPart','value':True});before=self.post('write',{'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as context:self.post('step',{'dt':10})
        self.assertEqual(context.exception.code,400);context.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'FaultDivisor','value':1});row=values(self.post('step',{'dt':10}));self.assertEqual(row['PartControl.POS'],2)
        self.assertIn('UDT',self.post('report',{})['control_operations']['fifo'])

    def test_system_lab_ssv_controls_and_atomic_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('step',{'dt':25})
        for tag,value in (('ControlTasks',True),('StApplyInhibit',True),('TaskInhibitCommand',1),('StTaskInhibitCommand',-1)):
            self.post('write',{'tag':tag,'value':value})
        self.post('step',{'dt':25});state=self.post('step',{'dt':25});row=values(state)
        self.assertEqual((row['FastCount'],row['SlowCount'],row['LiveFastInhibit'],row['StSlowInhibit']),(5,2,1,1))
        self.assertTrue(all(t['inhibited'] for t in state['task_schedule']['tasks'][1:]))
        self.post('write',{'tag':'TaskInhibitCommand','value':0});self.post('write',{'tag':'StTaskInhibitCommand','value':0})
        state=self.post('step',{'dt':25});self.assertFalse(any(t['inhibited'] for t in state['task_schedule']['tasks']))
        self.post('write',{'tag':'TaskInhibitCommand','value':1});before=self.post('write',{'tag':'ControlDivisor','value':0})
        with self.assertRaises(HTTPError) as context:self.post('step',{'dt':25})
        self.assertEqual(context.exception.code,400);context.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'ControlDivisor','value':1});state=self.post('step',{'dt':25})
        self.assertEqual(values(state)['LiveFastInhibit'],1)
        profile=self.post('report',{})['system_values']['task_inhibition'];self.assertFalse(profile['native_runtime_parity'])

    def test_text_lab_real_case_selection_and_late_fault_recovery_through_http(self):
        state=self.post('demo', {'sample':'TextLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        row=values(self.post('step', {'dt':10}));self.assertEqual((row['RealCaseResult'],row['RealCaseVisits']),(20,1))
        self.post('write', {'tag':'RealCaseInput','value':1.0})
        row=values(self.post('step', {'dt':10}));self.assertEqual((row['RealCaseResult'],row['RealCaseVisits']),(10,2))
        before=self.post('write', {'tag':'RealCaseDivisor','value':0.0})
        def current_state():
            request=Request(self.url+'/api/state',headers={'X-Logix-Token':self.token})
            with urlopen(request,timeout=3) as response:return json.load(response)
        with self.assertRaises(HTTPError) as context:self.post('step', {'dt':10})
        self.assertEqual(context.exception.code,400);context.exception.close();after=current_state()
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write', {'tag':'RealCaseDivisor','value':1.0})
        row=values(self.post('step', {'dt':10}));self.assertEqual((row['RealCaseResult'],row['RealCaseVisits'],row['ScanTotal']),(10,3,3))
        profile=self.post('report',{})['structured_text']['case'];self.assertIn('REAL',profile['numeric_types']);self.assertFalse(profile['native_runtime_parity'])

    def test_integer_lab_typed_st_literals_retain_full_ranges_through_http(self):
        state=self.post('demo', {'sample':'IntegerLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        row=values(self.post('step', {'dt':10}))
        self.assertEqual(row['StLiteralSigned'],'-9223372036854775808')
        self.assertEqual(row['StLiteralUnsigned'],'18446744073709551615')
        self.assertEqual(row['StLiteralDword'],4294967295)
        self.assertEqual(row['StLiteralNot'],'18446744073709551615')
        self.assertEqual(row['StLiteralQuotient'],'6148914691236517205')
        self.assertTrue(row['StLiteralCheck']);self.assertTrue(row['StAllMatches'])
        self.post('write', {'tag':'StLiteralOffset','value':'1'})
        row=values(self.post('step', {'dt':10}));self.assertEqual(row['StLiteralSigned'],'-9223372036854775807');self.assertFalse(row['StLiteralCheck'])
        self.post('write', {'tag':'StLiteralOffset','value':'0'})
        row=values(self.post('step', {'dt':10}));self.assertTrue(row['StLiteralCheck']);self.assertTrue(row['StAllMatches'])
        report=self.post('report', {})['wide_st_execution'];self.assertIn('L/U/UL',report['literals']);self.assertFalse(report['native_runtime_parity'])

    def test_math_lab_integer_division_and_real_promotion_through_http(self):
        state=self.post('demo', {'sample':'MathLab'});self.assertEqual(state['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        row=values(self.post('step', {'dt':10}))
        for name in ('LadderQuotient','CptQuotient','StQuotient'):self.assertEqual(row[name],-2)
        for name in ('LadderRemainder','CptRemainder','StRemainder'):self.assertEqual(row[name],-1)
        self.assertTrue(row['CmpMatches']);self.assertTrue(row['IntegerMathMatches'])
        self.assertEqual(row['StRealDestination'],-2.0);self.assertAlmostEqual(row['CptRealQuotient'],-7/3,places=6)
        self.assertEqual(row['CptRealQuotient'],row['StRealQuotient'])
        self.post('write', {'tag':'StDivisor','value':2});row=values(self.post('step', {'dt':10}))
        self.assertEqual(row['StQuotient'],-3);self.assertFalse(row['IntegerMathMatches'])
        self.post('write', {'tag':'StDivisor','value':3});row=values(self.post('step', {'dt':10}))
        self.assertTrue(row['IntegerMathMatches']);self.assertTrue(row['AllOK'])
        report=self.post('report', {})['integer_expression_execution']
        self.assertEqual(report['intermediate_type'],'DINT');self.assertFalse(report['native_status_parity'])

    def test_integer_lab_wide_st_matches_ladder_with_exact_http_values(self):
        state=self.post('demo', {'sample':'IntegerLab'});self.assertEqual(state['blockers'], [])
        state=self.post('step', {'dt':10});values={row['name']:row['value'] for row in state['tags']}
        self.assertEqual(values['StSignedSum'],'9007199254740995')
        self.assertEqual(values['StUnsignedSum'],'18446744073709551615')
        self.assertEqual(values['StUnsignedComplement'],'1');self.assertTrue(values['StAllMatches'])
        self.assertTrue(any(row.get('language')=='ST' for row in state['trace']))
        self.post('write', {'tag':'StDelta','value':'3'})
        state=self.post('step', {'dt':10});values={row['name']:row['value'] for row in state['tags']}
        self.assertEqual(values['StSignedSum'],'9007199254740996');self.assertFalse(values['StAllMatches'])
        self.post('write', {'tag':'StDelta','value':'2'})
        state=self.post('step', {'dt':10});values={row['name']:row['value'] for row in state['tags']}
        self.assertTrue(values['StAllMatches'])
        report=self.post('report', {})['wide_st_execution']
        self.assertTrue(report['available']);self.assertFalse(report['native_runtime_parity'])
        self.assertFalse(report['mixed_numeric_types'])

    def test_stats_lab_incremental_edges_match_inhibit_and_reset_through_http(self):
        state=self.post('demo', {'sample':'StatsLab'});self.assertEqual(state['blockers'], [])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        for flag in ('StepTransform','StepSearch'):self.post('write', {'tag':flag,'value':True})
        first=self.post('step', {'dt':10});held=self.post('step', {'dt':10})
        self.assertEqual(values(first)['StepValues[0]'],5)
        self.assertEqual([values(held)[f'StepValues[{i}]'] for i in range(5)], [5,0,0,0,999])
        self.assertEqual(values(held)['StepTransformControl.POS'],0)
        self.assertEqual(values(held)['StepSearchControl.POS'],0)
        for position in (1,2):
            for flag in ('StepTransform','StepSearch'):self.post('write', {'tag':flag,'value':False})
            self.post('step', {'dt':10})
            for flag in ('StepTransform','StepSearch'):self.post('write', {'tag':flag,'value':True})
            state=self.post('step', {'dt':10});row=values(state)
            self.assertEqual(row['StepTransformControl.POS'],position)
            self.assertEqual(row['StepSearchControl.POS'],position)
        self.assertTrue(row['StepSearchControl.IN']);self.assertTrue(row['StepSearchControl.FD'])
        self.assertEqual([row[f'StepValues[{i}]'] for i in range(5)], [5,9,13,0,999])
        for flag in ('StepTransform','StepSearch'):self.post('write', {'tag':flag,'value':False})
        self.post('write', {'tag':'Reset','value':True});state=self.post('step', {'dt':10});row=values(state)
        for control in ('StepTransformControl','StepSearchControl'):
            self.assertEqual(row[control+'.POS'],0);self.assertFalse(row[control+'.EN']);self.assertFalse(row[control+'.DN'])
            self.assertEqual(row[control+'.LEN'],4)
        self.assertFalse(row['StepSearchControl.IN'])
        self.post('write', {'tag':'Reset','value':False});self.post('write', {'tag':'Gain','value':3})
        for flag in ('StepTransform','StepSearch'):self.post('write', {'tag':flag,'value':True})
        row=values(self.post('step', {'dt':10}));self.assertEqual(row['StepValues[0]'],7)
        self.assertEqual(row['StepTransformControl.POS'],0);self.assertEqual(row['StepSearchControl.POS'],0)
        report=self.post('report', {})
        self.assertIn('INC',report['file_arithmetic']['modes'])
        self.assertFalse(report['file_search']['incremental']['native_internal_state_parity'])

    def test_stats_lab_average_sample_deviation_dimensions_and_rearm(self):
        state = self.post('demo', {'sample': 'StatsLab'})
        self.assertEqual(state['blockers'], [])
        self.post('step', {'dt': 10})
        self.post('write', {'tag': 'Calculate', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Average'], 5.0)
        self.assertAlmostEqual(values['Deviation'], 2.581988897, places=6)
        self.assertEqual(values['ColumnMean'], 7.0)
        self.assertEqual(values['RowMean'], 10.0)
        self.assertTrue(values['Ready'])
        self.post('write', {'tag': 'Values[0]', 'value': 14})
        state = self.post('step', {'dt': 10})
        self.assertEqual(next(row['value'] for row in state['tags'] if row['name']=='Average'), 5.0)
        self.post('write', {'tag': 'Calculate', 'value': False})
        self.post('step', {'dt': 10})
        self.post('write', {'tag': 'Calculate', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Average'], 8.0)
        self.assertEqual(values['MeanControl.POS'], 4)
        self.assertEqual(values['Values[4]'], 999)
        self.assertFalse(self.post('report', {})['array_statistics']['native_math_status'])

    def test_stats_lab_sorting_ladder_edges_and_repeated_st_calls(self):
        state = self.post('demo', {'sample': 'StatsLab'})
        self.assertEqual(state['blockers'], [])
        self.post('write', {'tag': 'Sort', 'value': True})
        self.post('write', {'tag': 'TextSort', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual([values[f'SortValues[{i}]'] for i in range(5)], [2,4,6,8,999])
        self.assertEqual(values['SortGrid[0,1]'], 4.0)
        self.assertEqual(values['SortGrid[1,1]'], 10.0)
        self.post('write', {'tag': 'SortValues[0]', 'value': 10})
        self.post('write', {'tag': 'SortGrid[0,1]', 'value': 20})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['SortValues[0]'], 10)
        self.assertEqual(values['SortGrid[0,1]'], 10.0)
        self.assertEqual(values['SortGrid[1,1]'], 20.0)
        self.assertEqual(values['SortControl.POS'], 0)
        self.assertFalse(self.post('report', {})['array_sort']['native_fault_classification'])

    def test_stats_lab_file_search_match_resume_and_numeric_false_scan(self):
        state = self.post('demo', {'sample': 'StatsLab'})
        self.assertEqual(state['blockers'], [])
        self.post('write', {'tag': 'Search', 'value': True})
        self.post('write', {'tag': 'BatchSearch', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['SearchControl.POS'], 2)
        self.assertTrue(values['SearchControl.FD'])
        self.assertTrue(values['SearchControl.IN'])
        self.assertEqual(values['BatchControl.POS'], 1)
        self.assertFalse(values['BatchControl.DN'])
        self.post('write', {'tag': 'SearchControl.IN', 'value': False})
        self.post('write', {'tag': 'BatchSearch', 'value': False})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['SearchControl.POS'], 3)
        self.assertTrue(values['SearchControl.DN'])
        self.assertEqual(values['BatchControl.POS'], 3)
        self.assertTrue(values['BatchControl.DN'])
        self.assertFalse(values['BatchControl.EN'])
        self.assertFalse(values['BatchControl.FD'])
        self.assertFalse(self.post('report', {})['file_search']['native_cursor_parity'])

    def test_stats_lab_binary64_fsc_match_resume_and_rollback_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'StatsLab'})['blockers'], [])
        def write(tag, value):
            self.post('write', {'tag':tag, 'value':value})
        def step():
            return self.post('step', {'dt':10})
        def state():
            request = Request(self.url+'/api/state', headers={'X-Logix-Token':self.token})
            with urlopen(request, timeout=3) as response:
                return json.load(response)
        def control(state, name):
            values = {row['name']:row['value'] for row in state['tags']}
            return tuple(values[f'Binary64{name}Control.{field}'] for field in ('POS','FD','IN','DN'))
        self.assertEqual(control(step(), 'Find'), (0, False, False, False))
        write('Binary64Find', True)
        write('Binary64Divisors[1]', 0)
        before = state()
        with self.assertRaises(HTTPError) as error:
            step()
        with error.exception as failure:
            self.assertEqual(failure.code, 400)
            self.assertIn('divide by zero', failure.read().decode().lower())
        after = state()
        for field in ('tags','routines','scan','ms','task_schedule','aoi_bindings','trace'):
            self.assertEqual(after[field], before[field], field)
        write('Binary64Divisors[1]', 1)
        write('Binary64FindBatch', True)
        write('Binary64FindStep', True)
        first = step()
        self.assertEqual(control(first, 'Find'), (1, True, True, False))
        self.assertEqual(control(first, 'FindBatch'), (0, False, False, False))
        self.assertEqual(control(first, 'FindStep'), (0, True, True, False))
        write('Binary64FindBatch', False)
        held = step()
        self.assertEqual(control(held, 'Find'), (1, True, True, False))
        self.assertEqual(control(held, 'FindBatch'), (1, False, False, False))
        self.assertEqual(control(held, 'FindStep'), (0, True, True, False))
        write('Binary64FindControl.IN', False)
        write('Binary64FindStepControl.IN', False)
        write('Binary64FindStep', False)
        resumed = step()
        self.assertEqual(control(resumed, 'Find'), (2, True, True, True))
        self.assertEqual(control(resumed, 'FindBatch'), (2, True, True, True))
        write('Binary64FindStep', True)
        self.assertEqual(control(step(), 'FindStep'), (1, True, True, False))
        profile = self.post('report', {})['file_search']['binary64']
        self.assertEqual(profile['modes'], ['ALL','positive DINT immediate','INC'])
        self.assertFalse(profile['native_runtime_parity'])

    def test_stats_lab_binary64_fal_modes_and_mid_file_rollback_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'StatsLab'})['blockers'], [])
        def write(tag, value):
            self.post('write', {'tag':tag, 'value':value})
        def step():
            return self.post('step', {'dt':10})
        def state():
            request = Request(self.url+'/api/state', headers={'X-Logix-Token':self.token})
            with urlopen(request, timeout=3) as response:
                return json.load(response)
        def tags(state):
            return {row['name']:row['value'] for row in state['tags']}
        def values(row, name):
            return tuple(row[f'{name}[{index}]'] for index in range(4))
        self.assertEqual(values(tags(step()), 'Binary64Mapped'), (None, None, None, 901.0))
        write('Binary64Transform', True)
        write('Binary64Divisors[1]', 0)
        before = state()
        with self.assertRaises(HTTPError) as error:
            step()
        with error.exception as failure:
            self.assertEqual(failure.code, 400)
            self.assertIn('divide by zero', failure.read().decode().lower())
        after = state()
        for field in ('tags','routines','scan','ms','task_schedule','aoi_bindings','trace'):
            self.assertEqual(after[field], before[field], field)
        write('Binary64Divisors[1]', 1)
        write('Binary64Batch', True)
        write('Binary64Step', True)
        row = tags(step())
        self.assertEqual(values(row, 'Binary64Mapped'), (2**-52, 1.5, 2.5, 901.0))
        self.assertEqual(values(row, 'Binary64Batched'), (1.5, None, None, 902.0))
        self.assertEqual(values(row, 'Binary64Rounded'), (1, None, None, 903))
        write('Binary64Batch', False)
        write('Binary64Step', False)
        row = tags(step())
        self.assertEqual(values(row, 'Binary64Batched'), (1.5, 3.0, None, 902.0))
        write('Binary64Step', True)
        row = tags(step())
        self.assertEqual(values(row, 'Binary64Batched'), (1.5, 3.0, 4.0, 902.0))
        self.assertEqual(values(row, 'Binary64Rounded'), (1, 2, None, 903))
        write('Binary64Step', False)
        step()
        write('Binary64Step', True)
        self.assertEqual(values(tags(step()), 'Binary64Rounded'), (1, 2, 4, 903))
        profile = self.post('report', {})['file_arithmetic']['binary64']
        self.assertEqual(profile['modes'], ['ALL','positive DINT immediate','INC'])
        self.assertFalse(profile['native_runtime_parity'])

    def test_stats_lab_file_arithmetic_all_and_numeric_false_scan(self):
        state = self.post('demo', {'sample': 'StatsLab'})
        self.assertEqual(state['blockers'], [])
        self.post('write', {'tag': 'Transform', 'value': True})
        self.post('write', {'tag': 'BatchTransform', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual([values[f'MappedValues[{i}]'] for i in range(5)], [5, 9, 13, 17, 999])
        self.assertEqual([values[f'BatchValues[{i}]'] for i in range(5)], [5, 9, 0, 0, 999])
        self.assertEqual(values['TransformControl.POS'], 3)
        self.assertTrue(values['TransformControl.DN'])
        self.assertFalse(values['BatchTransformControl.DN'])
        self.post('write', {'tag': 'BatchTransform', 'value': False})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual([values[f'BatchValues[{i}]'] for i in range(5)], [5, 9, 13, 17, 999])
        self.assertTrue(values['BatchTransformControl.DN'])
        self.assertFalse(values['BatchTransformControl.EN'])
        self.assertFalse(self.post('report', {})['file_arithmetic']['native_cursor_parity'])

    def test_bit_lab_dtr_true_false_masks_and_late_fault_through_http(self):
        state=self.post('demo', {'sample':'BitLab'});self.assertEqual(state['blockers'], [])
        rows=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('step', {'dt':10})
        self.post('write', {'tag':'TransitionSource','value':1})
        first=self.post('step', {'dt':10});self.assertTrue(rows(first)['TransitionPulse'])
        self.assertEqual(rows(first)['TransitionCount'],1);self.assertEqual(rows(first)['TransitionReference'],1)
        self.assertFalse(rows(self.post('step', {'dt':10}))['TransitionPulse'])
        self.post('write', {'tag':'TransitionSource','value':257})
        self.assertFalse(rows(self.post('step', {'dt':10}))['TransitionPulse'])
        self.post('write', {'tag':'TransitionEnable','value':False})
        self.post('write', {'tag':'TransitionSource','value':2})
        false=self.post('step', {'dt':10});self.assertEqual(rows(false)['TransitionReference'],2)
        self.assertFalse(rows(false)['TransitionPulse']);self.assertEqual(rows(false)['TransitionCount'],1)
        self.post('write', {'tag':'TransitionEnable','value':True})
        self.assertFalse(rows(self.post('step', {'dt':10}))['TransitionPulse'])
        self.post('write', {'tag':'TransitionSource','value':3})
        self.post('write', {'tag':'FaultDivisor','value':0})
        before=self.post('write', {'tag':'SourceByte','value':42})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
        self.assertEqual(error.exception.code,400);failure=json.load(error.exception);error.exception.close()
        self.assertIn('rolled back',failure['error'])
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        self.assertIn('divide by zero',after['fault'])
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write', {'tag':'FaultDivisor','value':1})
        retry=self.post('step', {'dt':10});self.assertTrue(rows(retry)['TransitionPulse'])
        self.assertEqual(rows(retry)['TransitionCount'],2);self.assertEqual(rows(retry)['TransitionReference'],3)
        self.assertEqual(rows(retry)['Status']&255,42)
        held=self.post('step', {'dt':10});self.assertFalse(rows(held)['TransitionPulse'])
        self.assertEqual(rows(held)['TransitionCount'],2)
        report=self.post('report', {})['data_transition']
        self.assertEqual(report['instructions'],['DTR']);self.assertFalse(report['native_runtime_parity'])

    def test_bit_lab_fbc_ddt_result_wrap_learning_and_fault_recovery_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'BitLab'})['blockers'], [])
        rows=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('step', {'dt':10})
        self.post('write', {'tag':'CompareEnable','value':True})
        self.post('write', {'tag':'DetectEnable','value':True})
        first=self.post('step', {'dt':10});v=rows(first)
        self.assertEqual([v[f'MismatchBits[{i}]'] for i in range(4)],[32,39,31,999])
        self.assertEqual((v['CompareControl.POS'],v['CompareControl.DN']),(40,True))
        self.assertEqual((v['DetectControl.POS'],v['ChangedBits[0]'],v['LearnReference[0]']),(1,0,1))
        held=rows(self.post('step', {'dt':10}));self.assertEqual(held['DetectControl.POS'],1)
        self.post('write', {'tag':'DetectEnable','value':False});self.post('step', {'dt':10})
        self.post('write', {'tag':'DetectEnable','value':True});v=rows(self.post('step', {'dt':10}))
        self.assertEqual((v['DetectControl.POS'],v['ChangedBits[1]'],v['LearnReference[0]']),(6,5,33))
        self.post('write', {'tag':'DetectEnable','value':False});self.post('step', {'dt':10})
        self.post('write', {'tag':'DetectEnable','value':True})
        before=self.post('write', {'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write', {'tag':'FaultDivisor','value':1});v=rows(self.post('step', {'dt':10}))
        self.assertEqual((v['DetectControl.POS'],v['ChangedBits[2]'],v['LearnReference[0]']),(32,31,-2147483615))
        self.assertTrue(v['DetectResultControl.DN'])
        for position in (33,40):
            self.post('write', {'tag':'DetectEnable','value':False});self.post('step', {'dt':10})
            self.post('write', {'tag':'DetectEnable','value':True});v=rows(self.post('step', {'dt':10}))
            self.assertEqual(v['DetectControl.POS'],position)
        self.assertEqual([v[f'ChangedBits[{i}]'] for i in range(4)],[32,39,31,999])
        self.assertEqual((v['LearnReference[1]'],v['LearnReference[2]']),(1073741953,777))
        self.assertEqual(v['CompareReference[0]'],0);self.assertEqual(v['CompareReference[1]'],0)
        profile=self.post('report', {})['file_bit_compare']
        self.assertEqual(profile['instructions'],['DDT','FBC']);self.assertFalse(profile['native_runtime_parity'])

    def test_timer_lab_st_delays_retention_status_and_clock_rollback_through_http(self):
        state=self.post('demo', {'sample':'TimerLab'});self.assertEqual(state['blockers'], [])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('step', {'dt':10});v=values(self.post('step', {'dt':10}))
        self.assertEqual((v['On.ACC'],v['Retained.ACC'],v['Off.ACC']),(10,10,0))
        self.post('write', {'tag':'TimerEnable','value':False})
        self.post('step', {'dt':10});v=values(self.post('step', {'dt':10}))
        self.assertEqual((v['On.ACC'],v['Retained.ACC'],v['Off.ACC']),(0,10,10))
        self.assertTrue(v['Off.DN']);self.assertFalse(v['On.DN'])
        self.post('write', {'tag':'TimerEnable','value':True})
        before=self.post('write', {'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write', {'tag':'FaultDivisor','value':1});v=values(self.post('step', {'dt':10}))
        self.assertEqual((v['On.ACC'],v['Retained.ACC'],v['Off.ACC']),(0,10,0))
        v=values(self.post('step', {'dt':10}));self.assertEqual((v['On.ACC'],v['Retained.ACC']),(10,20))
        self.post('write', {'tag':'Preset','value':-1});v=values(self.post('step', {'dt':10}))
        self.assertTrue(v['AnyFault']);self.assertEqual(v['On.Status'],3);self.assertFalse(v['On.EnableOut'])
        self.post('write', {'tag':'Preset','value':30});self.post('write', {'tag':'ResetTimers','value':True})
        v=values(self.post('step', {'dt':10}));self.assertFalse(v['AnyFault'])
        self.assertEqual((v['On.ACC'],v['Retained.ACC'],v['Off.ACC']),(0,0,30))
        profile=self.post('report', {})['st_timers'];self.assertEqual(profile['instructions'],['RTOR','TOFR','TONR'])
        self.assertFalse(profile['native_runtime_parity'])

    def test_rate_lab_timing_bypass_status_and_clock_rollback_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'RateLab'})['blockers'], [])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        for tag,value in (('IncreaseRate',8.0),('DecreaseRate',16.0)):
            self.post('write', {'tag':tag,'value':value})
        self.post('step', {'dt':125});self.post('write', {'tag':'Target','value':10.0})
        self.assertEqual(values(self.post('step', {'dt':125}))['Output'],1.0)
        self.assertEqual(values(self.post('step', {'dt':125}))['Output'],2.0)
        self.post('write', {'tag':'Target','value':-10.0});self.assertEqual(values(self.post('step', {'dt':125}))['Output'],0.0)
        self.post('write', {'tag':'Bypass','value':True});self.post('write', {'tag':'Target','value':7.0})
        self.assertEqual(values(self.post('step', {'dt':125}))['Output'],7.0)
        for tag,value in (('Bypass',False),('Target',100.0),('TimingMode',1),('SampleTime',0.125)):
            self.post('write', {'tag':tag,'value':value})
        self.assertEqual(values(self.post('step', {'dt':125}))['Output'],8.0)
        self.post('write', {'tag':'CallRate','value':False});self.post('write', {'tag':'Target','value':-10.0})
        self.assertEqual(values(self.post('step', {'dt':500}))['Output'],8.0)
        self.post('write', {'tag':'CallRate','value':True});self.assertEqual(values(self.post('step', {'dt':125}))['Output'],6.0)
        self.post('write', {'tag':'SampleTime','value':0.0});v=values(self.post('step', {'dt':125}))
        self.assertEqual(v['Output'],6.0);self.assertTrue(v['TimeInvalid']);self.assertEqual(v['RateState.Status'],-2147483647)
        self.post('write', {'tag':'SampleTime','value':0.125});self.assertEqual(values(self.post('step', {'dt':125}))['Output'],4.0)
        for target,expected in ((100.0,5.0),(-100.0,3.0)):
            self.post('write', {'tag':'Target','value':target});before=self.post('write', {'tag':'FaultDivisor','value':0})
            with self.assertRaises(HTTPError) as error:self.post('step', {'dt':125})
            self.assertEqual(error.exception.code,400);error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
            self.post('write', {'tag':'FaultDivisor','value':1});self.assertEqual(values(self.post('step', {'dt':125}))['Output'],expected)
        before=self.post('write', {'tag':'TimingMode','value':2})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':125})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write', {'tag':'TimingMode','value':1});self.assertEqual(values(self.post('step', {'dt':125}))['Output'],1.0)
        profile=self.post('report', {})['st_rate'];self.assertEqual(profile['instructions'],['ACS','ASN','ATN','BTDT','COS','DEG','FRD','LN','LOG','MOD','RAD','RLIM','SIN','SQR','TAN','TOD','TRN','XPY']);self.assertFalse(profile['native_runtime_parity'])

    def test_signal_lab_limits_negation_sum_and_rollback_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'SignalLab'})['blockers'], [])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        v=values(self.post('step', {'dt':10}));self.assertEqual((v['LimitedValue'],v['NegatedValue'],v['SumValue']),(5.0,5.0,6.0))
        self.post('write', {'tag':'Input','value':10.0});v=values(self.post('step', {'dt':10}))
        self.assertTrue(v['HighAlarm']);self.assertEqual(v['LimitedValue'],10.0)
        for tag,value in (('Input',20.0),('Negate',True),('UseNegated',True)):
            self.post('write', {'tag':tag,'value':value})
        v=values(self.post('step', {'dt':10}));self.assertEqual((v['LimitedValue'],v['NegatedValue'],v['SumValue']),(10.0,-20.0,-9.0))
        self.post('write', {'tag':'LimitMode','value':2});v=values(self.post('step', {'dt':10}))
        self.assertEqual(v['SumValue'],1.0);self.assertFalse(v['HighAlarm'])
        for tag,value in (('LimitMode',9),('HighLimit',0.0),('LowLimit',10.0),('Input',5.0)):
            self.post('write', {'tag':tag,'value':value})
        v=values(self.post('step', {'dt':10}));self.assertEqual(v['Limiter.Status'],7)
        self.assertTrue(v['LimitsInvalid']);self.assertTrue(v['SelectorInvalid']);self.assertEqual(v['LimitedValue'],10.0)
        self.post('write', {'tag':'CallSignals','value':False});self.post('write', {'tag':'HighLimit','value':20.0})
        v=values(self.post('step', {'dt':10}));self.assertEqual(v['Limiter.Status'],7)
        self.post('write', {'tag':'CallSignals','value':True});self.post('write', {'tag':'LimitMode','value':0})
        before=self.post('write', {'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write', {'tag':'FaultDivisor','value':1});v=values(self.post('step', {'dt':10}));self.assertEqual(v['Limiter.Status'],0)
        self.post('write', {'tag':'UseLimited','value':False});self.post('write', {'tag':'NegatedGain','value':3e38})
        before=self.post('write', {'tag':'Input','value':20.0})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write', {'tag':'UseNegated','value':False});v=values(self.post('step', {'dt':10}));self.assertEqual(v['SumValue'],1.0)
        self.assertEqual(self.post('report', {})['st_signal']['instructions'],['HLL','SNEG','SSUM'])

    def test_scale_lab_alarms_limits_status_and_rollback_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'ScaleLab'})['blockers'], [])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('write', {'tag':'RawValue','value':2047.5})
        self.assertEqual(values(self.post('step', {'dt':10}))['ScaledValue'],50.0)
        self.post('write', {'tag':'RawValue','value':8190.0});v=values(self.post('step', {'dt':10}))
        self.assertEqual(v['ScaledValue'],200.0);self.assertTrue(v['HighAlarm'])
        self.post('write', {'tag':'LimitOutput','value':True});self.assertEqual(values(self.post('step', {'dt':10}))['ScaledValue'],100.0)
        self.post('write', {'tag':'RawValue','value':-4095.0});v=values(self.post('step', {'dt':10}))
        self.assertEqual(v['ScaledValue'],0.0);self.assertTrue(v['LowAlarm'])
        self.post('write', {'tag':'RawMaximum','value':0.0});v=values(self.post('step', {'dt':10}))
        self.assertEqual(v['ScaledValue'],0.0);self.assertTrue(v['ScaleFault']);self.assertTrue(v['InvalidRange'])
        self.post('write', {'tag':'RawMaximum','value':4095.0});self.post('write', {'tag':'RawValue','value':2047.5})
        v=values(self.post('step', {'dt':10}));self.assertEqual(v['ScaledValue'],50.0);self.assertFalse(v['ScaleFault'])
        self.post('write', {'tag':'CallScale','value':False});self.post('write', {'tag':'RawMaximum','value':0.0})
        v=values(self.post('step', {'dt':10}));self.assertFalse(v['InvalidRange']);self.assertEqual(v['ScaledValue'],50.0)
        self.post('write', {'tag':'CallScale','value':True});self.assertTrue(values(self.post('step', {'dt':10}))['InvalidRange'])
        self.post('write', {'tag':'RawMaximum','value':4095.0});self.post('write', {'tag':'RawValue','value':8190.0})
        self.post('write', {'tag':'LimitOutput','value':False})
        for invalid in (False,True):
            if invalid:self.post('write', {'tag':'RawMinimum','value':4095.0})
            before=self.post('write', {'tag':'FaultDivisor','value':0})
            with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
            self.post('write', {'tag':'FaultDivisor','value':1});v=values(self.post('step', {'dt':10}))
            self.assertEqual(v['ScaledValue'],200.0);self.assertEqual(v['InvalidRange'],invalid)
        self.post('write', {'tag':'RawMinimum','value':0.0});self.post('write', {'tag':'EUMinimum','value':100.0})
        self.post('write', {'tag':'EUMaximum','value':-100.0});self.post('write', {'tag':'RawValue','value':2047.5})
        v=values(self.post('step', {'dt':10}));self.assertEqual(v['ScaledValue'],0.0);self.assertFalse(v['ScaleFault'])
        profile=self.post('report', {})['st_scale'];self.assertEqual(profile['instructions'],['ACS','ASN','ATN','BTDT','COS','DEG','FRD','LN','LOG','MOD','RAD','SCL','SIN','SQR','TAN','TOD','TRN','XPY']);self.assertFalse(profile['native_runtime_parity'])

    def test_pulse_lab_st_edges_skips_and_rollback_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'PulseLab'})['blockers'], [])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('step', {'dt':10});self.post('write', {'tag':'Input','value':True})
        v=values(self.post('step', {'dt':10}));self.assertTrue(v['RisingOutput']);self.assertEqual(v['RisingPulses'],1)
        self.post('write', {'tag':'CallEdges','value':False});v=values(self.post('step', {'dt':10}))
        self.assertTrue(v['RisingOutput']);self.assertEqual(v['RisingPulses'],1)
        self.post('write', {'tag':'CallEdges','value':True});v=values(self.post('step', {'dt':10}))
        self.assertFalse(v['RisingOutput']);self.assertEqual(v['RisingPulses'],1)
        self.post('write', {'tag':'Input','value':False});before=self.post('write', {'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write', {'tag':'FaultDivisor','value':1});v=values(self.post('step', {'dt':10}))
        self.assertTrue(v['FallingOutput']);self.assertEqual(v['FallingPulses'],1)
        v=values(self.post('step', {'dt':10}));self.assertFalse(v['FallingOutput']);self.assertEqual(v['FallingPulses'],1)
        self.post('write', {'tag':'Input','value':True});before=self.post('write', {'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
        error.exception.close()
        self.post('write', {'tag':'FaultDivisor','value':1});v=values(self.post('step', {'dt':10}))
        self.assertTrue(v['RisingOutput']);self.assertEqual(v['RisingPulses'],2)
        profile=self.post('report', {})['st_oneshot'];self.assertEqual(profile['instructions'],['ACS','ASN','ATN','BTDT','COS','DEG','FRD','LN','LOG','MOD','OSFI','OSRI','RAD','SIN','SQR','TAN','TOD','TRN','XPY'])
        self.assertFalse(profile['native_runtime_parity'])

    def test_counter_lab_st_edges_wrap_reset_and_retry_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'CounterLab'})['blockers'], [])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('step', {'dt':10})
        self.post('write', {'tag':'UpInput','value':True});v=values(self.post('step', {'dt':10}))
        self.assertEqual(v['Count'],1);self.assertEqual(values(self.post('step', {'dt':10}))['Count'],1)
        self.post('write', {'tag':'DownInput','value':True});v=values(self.post('step', {'dt':10}))
        self.assertEqual(v['Count'],0)
        self.post('write', {'tag':'ResetCounter','value':True});self.post('step', {'dt':10})
        self.post('write', {'tag':'ResetCounter','value':False});self.assertEqual(values(self.post('step', {'dt':10}))['Count'],0)
        for tag in ('UpInput','DownInput'):self.post('write', {'tag':tag,'value':False})
        self.post('step', {'dt':10});self.post('write', {'tag':'UpInput','value':True})
        before=self.post('write', {'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step', {'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write', {'tag':'FaultDivisor','value':1});self.assertEqual(values(self.post('step', {'dt':10}))['Count'],1)
        self.assertEqual(values(self.post('step', {'dt':10}))['Count'],1)
        self.post('write', {'tag':'UpInput','value':False});self.post('step', {'dt':10})
        self.post('write', {'tag':'Counter.ACC','value':2147483647})
        for tag in ('UpInput','DownInput'):self.post('write', {'tag':tag,'value':True})
        v=values(self.post('step', {'dt':10}));self.assertEqual(v['Count'],2147483647)
        self.assertTrue(v['Overflow']);self.assertTrue(v['Underflow'])
        self.post('write', {'tag':'ResetCounter','value':True});v=values(self.post('step', {'dt':10}))
        self.assertEqual(v['Count'],0);self.assertFalse(v['Overflow']);self.assertFalse(v['Underflow'])
        profile=self.post('report', {})['st_counter'];self.assertEqual(profile['instructions'],['CTUD'])
        self.assertFalse(profile['native_runtime_parity'])

    def test_selector_lab_function_blocks_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'SelectorLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(10,11))
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['SelectedOutput'],v['MultiplexedOutput']),(10,10))
        self.post('write',{'tag':'ManualMode','value':True});self.post('write',{'tag':'ManualValue','value':12.5})
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['SelectedOutput'],v['MultiplexedOutput']),(12.5,12.5))
        self.post('write',{'tag':'Channel','value':8});v=values(self.post('step',{'dt':10}));self.assertEqual(v['MultiplexedOutput'],80)
        self.post('write',{'tag':'Channel','value':0});v=values(self.post('step',{'dt':10}));self.assertEqual((v['MultiplexedOutput'],v['SelectorStatus']),(80,3))
        self.post('write',{'tag':'BlockEnable','value':False});v=values(self.post('step',{'dt':10}));self.assertFalse(v['Choice.EnableOut'])
        self.post('write',{'tag':'BlockEnable','value':True});self.post('write',{'tag':'Channel','value':1})
        self.post('write',{'tag':'ManualValue','value':22});before=self.post('write',{'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write',{'tag':'ManualValue','value':33});self.post('write',{'tag':'FaultDivisor','value':1})
        state=self.post('step',{'dt':10});self.assertEqual(values(state)['MultiplexedOutput'],33)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),2)
        profile=self.post('report',{})['function_blocks'];self.assertEqual(profile['instructions'],['ABS','ACS','ADD','AND','ASN','ATN','BAND','BNOT','BOR','BTDT','BXOR','COS','CTUD','DEG','DERV','DFF','DIV','EQU','ESEL','FRD','GEQ','GRT','HLL','INTG','JKFF','LEQ','LES','LIM','LN','LOG','MAXC','MEQ','MINC','MOD','MUL','MUX','MVMT','NEG','NEQ','NOT','OR','OSFI','OSRI','RAD','RESD','RLIM','RTOR','SCL','SEL','SETD','SIN','SNEG','SQR','SSUM','SUB','TAN','TOD','TOFR','TONR','TRN','UPDN','XOR','XPY'])
        self.assertFalse(profile['native_runtime_parity'])

    def test_fbd_signal_lab_diagnostic_wires_enables_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'FBDSignalLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(33,35))
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Scaled'],v['Limited'],v['Negated'],v['Summed']),(50,50,50,53))
        self.post('write',{'tag':'RawMax','value':0});self.post('write',{'tag':'LimitMode','value':9})
        v=values(self.post('step',{'dt':10}));self.assertTrue(v['ScaleFault']);self.assertTrue(v['RangeInvalid']);self.assertTrue(v['ModeInvalid'])
        self.post('write',{'tag':'BlockEnable','value':False});self.post('write',{'tag':'RawMax','value':10})
        v=values(self.post('step',{'dt':10}));self.assertTrue(v['RangeInvalid']);self.assertFalse(v['Scaler.EnableOut'])
        self.post('write',{'tag':'BlockEnable','value':True});self.post('write',{'tag':'LimitMode','value':0})
        self.post('write',{'tag':'Negate','value':True});v=values(self.post('step',{'dt':10}));self.assertEqual(v['Summed'],-47)
        self.assertFalse(v['ScaleFault']);self.assertFalse(v['ModeInvalid'])
        self.post('write',{'tag':'RawInput','value':8});before=self.post('write',{'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write',{'tag':'RawInput','value':2});self.post('write',{'tag':'FaultDivisor','value':1})
        state=self.post('step',{'dt':10});self.assertEqual(values(state)['Summed'],-17)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),4)
        profile=self.post('report',{})['function_blocks'];self.assertFalse(profile['native_runtime_parity'])
        self.assertEqual(profile['blocks']['status_aliases']['SCALE']['InRawRangeInv'],'Status.1')

    def test_fbd_state_lab_clock_edges_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDStateLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(34,39))
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        self.post('write',{'tag':'OnPreset','value':100});self.post('step',{'dt':10})
        for bit,count in ((True,1),(False,1),(True,2)):
            self.post('write',{'tag':'Input','value':bit});v=values(self.post('step',{'dt':10}));self.assertEqual(v['Count'],count)
        self.assertEqual(v['OnACC'],0);self.assertTrue(v['CountDone'])
        self.assertEqual(values(self.post('step',{'dt':10}))['OnACC'],10)
        self.post('write',{'tag':'BlockEnable','value':False})
        for _ in range(2):self.assertEqual(values(self.post('step',{'dt':10}))['OnACC'],10)
        self.post('write',{'tag':'BlockEnable','value':True});v=values(self.post('step',{'dt':10}));self.assertEqual(v['OnACC'],40)
        self.post('write',{'tag':'Input','value':False});before=self.post('write',{'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write',{'tag':'FaultDivisor','value':1});v=values(self.post('step',{'dt':10}))
        self.assertTrue(v['FallingPulse']);self.assertEqual(v['OnACC'],50)
        self.post('write',{'tag':'Input','value':True});v=values(self.post('step',{'dt':10}));self.assertEqual(v['Count'],3)
        self.post('write',{'tag':'OnPreset','value':-1});v=values(self.post('step',{'dt':10}))
        self.assertEqual(v['OnStatus'],3);self.assertTrue(v['OnFault']);self.assertTrue(v['OnPresetInvalid'])
        self.assertFalse(v['OnDelay.EnableOut'])
        self.post('write',{'tag':'OnPreset','value':100});state=self.post('step',{'dt':10});self.assertFalse(values(state)['OnFault'])
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),6)
        profile=self.post('report',{})['function_blocks'];self.assertEqual(len(profile['instructions']),63)
        self.assertFalse(profile['native_runtime_parity']);self.assertIn('elapsed',profile['blocks']['timing'])

    def test_fbd_boolean_lab_latches_clock_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDLogicLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(28,37))
        self.assertIn(b'FBD Boolean lab',self.get('/'));values=lambda s:{row['name']:row['value'] for row in s['tags']}
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['AndOut'],v['OrOut'],v['NotOut'],v['XorOut']),(False,True,True,True))
        self.assertFalse(v['ResetLatch']);self.assertTrue(v['SetLatch'])
        for tag,value in (('Clock',True),('DInput',True),('SetInput',True),('ResetInput',True)):
            self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertTrue(v['DOut']);self.assertTrue(v['ToggleOut'])
        self.assertFalse(v['ResetLatch']);self.assertTrue(v['SetLatch']);self.assertFalse(v['NotOut'])
        self.post('write',{'tag':'BlockEnable','value':False});self.post('write',{'tag':'Clock','value':False})
        v=values(self.post('step',{'dt':10}));self.assertTrue(v['ToggleOut']);self.assertFalse(v['ToggleState.EnableOut'])
        self.post('write',{'tag':'BlockEnable','value':True});self.post('step',{'dt':10})
        self.post('write',{'tag':'Clock','value':True});self.post('write',{'tag':'DInput','value':False})
        before=self.post('write',{'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        self.post('write',{'tag':'FaultDivisor','value':1});self.post('write',{'tag':'DInput','value':True})
        state=self.post('step',{'dt':10});v=values(state);self.assertTrue(v['DOut']);self.assertFalse(v['ToggleOut'])
        self.assertFalse(values(self.post('step',{'dt':10}))['ToggleOut'])
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),8)

    def test_fbd_rate_capture_lab_timing_diagnostics_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDTrendLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(23,25))
        self.assertIn(b'FBD rate/capture lab',self.get('/'));values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        write('TimingMode',1);self.post('step',{'dt':10});write('Signal',5)
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Limited'],v['Maximum'],v['Minimum']),(.5,.5,0))
        write('SampleTime',0);v=values(self.post('step',{'dt':10}))
        self.assertEqual(v['RateStatus'],-2147483647);self.assertTrue(v['SampleInvalid']);self.assertTrue(v['RateFault'])
        write('BlockEnable',False);write('SampleTime',.25);write('ResetCapture',True)
        v=values(self.post('step',{'dt':10}));self.assertEqual(v['Maximum'],.5);self.assertFalse(v['Ramp.EnableOut'])
        write('BlockEnable',True);v=values(self.post('step',{'dt':10}))
        self.assertEqual((v['Limited'],v['Maximum'],v['Minimum']),(1,10,-10));self.assertFalse(v['RateFault'])
        write('ResetCapture',False);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        write('FaultDivisor',1);state=self.post('step',{'dt':10});self.assertEqual(values(state)['Limited'],1.5)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),3)
        profile=self.post('report',{})['function_blocks'];self.assertEqual(len(profile['instructions']),63)
        self.assertEqual(profile['blocks']['status_aliases']['RATE_LIMITER']['DeltaTInv'],'Status.31')
        self.assertFalse(profile['native_runtime_parity'])

    def test_fbd_accumulation_lab_initialize_holds_diagnostics_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDTotalLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(29,28))
        self.assertIn(b'FBD accumulation lab',self.get('/'));values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Total'],v['Integral']),(1.5,0))
        for tag,value in (('InitializeTotal',True),('HoldTotal',True),('InitializeIntegral',True),('IntegralSeed',2)):
            write(tag,value)
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Total'],v['Integral']),(10,2))
        for tag,value in (('InitializeTotal',False),('InitializeIntegral',False),('HoldHigh',True),('Rate',8)):
            write(tag,value)
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Total'],v['Integral']),(10,2))
        write('HoldHigh',False);write('SampleTime',0);v=values(self.post('step',{'dt':10}))
        self.assertEqual(v['Integral'],2);self.assertEqual(v['IntegralStatus'],0)
        write('SampleTime',-1);v=values(self.post('step',{'dt':10}))
        self.assertTrue(v['SampleInvalid']);self.assertEqual(v['IntegralStatus'],-2147483647)
        write('SampleTime',.25);write('Gain',-1);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        write('Gain',1);write('FaultDivisor',1);write('HoldTotal',False)
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Total'],v['Integral']),(11.5,4))
        self.assertFalse(v['IntegralFault']);write('BlockEnable',False)
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Total'],v['Integral']),(11.5,4))
        self.assertFalse(v['IntegralState.EnableOut']);write('BlockEnable',True)
        state=self.post('step',{'dt':10});v=values(state);self.assertEqual((v['Total'],v['Integral']),(13,5));self.assertTrue(v['HighAlarm'])
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),2)
        profile=self.post('report',{})['function_blocks'];self.assertEqual(len(profile['instructions']),63)
        self.assertEqual(profile['blocks']['status_aliases']['INTEGRATOR']['HighLowLimsInv'],'Status.2')
        self.assertFalse(profile['native_runtime_parity'])

    def test_fbd_process_lab_health_requests_derivative_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDProcessLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(38,38))
        self.assertIn(b'FBD process lab',self.get('/'));values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Selected'],v['SelectedInput'],v['Derivative']),(30,3,0))
        write('Input3',40);v=values(self.post('step',{'dt':10}));self.assertEqual((v['Selected'],v['Derivative']),(40,40))
        write('Fault3',True);v=values(self.post('step',{'dt':10}));self.assertEqual((v['Selected'],v['SelectedInput'],v['Derivative']),(20,2,-80))
        write('SelectionMode',0);write('ProgramRequest',True);write('ResetRequests',True)
        v=values(self.post('step',{'dt':10}));self.assertTrue(v['ProgramControl']);self.assertFalse(v['Selector.ProgProgReq']);self.assertTrue(v['ProgramRequest'])
        write('ProgramSelection',1);write('RequestOperator',True);self.assertTrue(values(self.post('step',{'dt':10}))['ProgramControl'])
        write('ProgramRequest',False);v=values(self.post('step',{'dt':10}));self.assertFalse(v['ProgramControl']);self.assertFalse(v['Selector.OperOperReq'])
        write('SampleTime',-1);write('Input1',15);v=values(self.post('step',{'dt':10}))
        self.assertTrue(v['SampleInvalid']);self.assertEqual(v['DerivativeStatus'],-2147483647)
        write('SampleTime',.25);write('Input1',20);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Derivative'],20)
        write('Input1',30);write('RequestProgram',True);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        write('RequestOperator',False);write('Input1',40);write('FaultDivisor',1)
        state=self.post('step',{'dt':10});v=values(state);self.assertTrue(v['ProgramControl']);self.assertEqual(v['Derivative'],80)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),2)
        profile=self.post('report',{})['function_blocks'];self.assertEqual(len(profile['instructions']),63)
        self.assertEqual(profile['blocks']['status_aliases']['SELECT_ENHANCED']['InsFaulted'],'Status.1');self.assertFalse(profile['native_runtime_parity'])

    def test_fbd_arithmetic_lab_chain_disable_and_fault_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDMathLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(19,23));self.assertIn(b'FBD arithmetic lab',self.get('/'))
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Sum'],v['Difference'],v['Product'],v['Quotient'],v['Negative'],v['Magnitude']),(8,7,21,7,-7,7))
        for tag,value in (('A',2),('B',6),('Offset',10),('Gain',4),('Divisor',2)):write(tag,value)
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Difference'],v['Quotient'],v['Negative'],v['Magnitude']),(-2,-4,4,4))
        write('BlockEnable',False);write('Divisor',0);v=values(self.post('step',{'dt':10}))
        self.assertEqual(v['Quotient'],-4);self.assertFalse(v['MathEnabled']);before=write('BlockEnable',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);self.assertIn('minor-fault',json.load(error.exception)['error']);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        write('Divisor',2);write('A',20);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Quotient'],32)
        before=write('Gain',3.4028234663852886e38)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        write('Gain',4);state=self.post('step',{'dt':10});self.assertEqual(values(state)['Magnitude'],32)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),6)
        profile=self.post('report',{})['function_blocks'];self.assertEqual(len(profile['instructions']),63)
        self.assertEqual(profile['blocks']['math']['instructions'],['ABS','ACS','ADD','ASN','ATN','COS','DEG','DIV','LN','LOG','MOD','MUL','NEG','RAD','SIN','SQR','SUB','TAN','XPY']);self.assertFalse(profile['native_runtime_parity'])

    def test_fbd_comparison_lab_bool_selector_timer_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDCompareLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(29,41));self.assertIn(b'FBD comparison lab',self.get('/'))
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertFalse(v['Equal']);self.assertTrue(v['Greater']);self.assertTrue(v['InRange'])
        self.assertEqual((v['SelectedValue'],v['TimerACC']),(100,0))
        self.post('step',{'dt':10});v=values(self.post('step',{'dt':10}));self.assertEqual(v['TimerACC'],20);self.assertTrue(v['TimerDone'])
        write('A',2);v=values(self.post('step',{'dt':10}));self.assertTrue(v['Equal']);self.assertFalse(v['NotEqual']);self.assertEqual(v['SelectedValue'],0)
        write('LowLimit',10);write('HighLimit',0);v=values(self.post('step',{'dt':10}));self.assertFalse(v['InRange']);self.assertEqual(v['TimerACC'],0)
        write('A',10);v=values(self.post('step',{'dt':10}));self.assertTrue(v['InRange']);self.assertEqual(v['SelectedValue'],100)
        before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        write('FaultDivisor',1);state=self.post('step',{'dt':10});self.assertEqual(values(state)['TimerACC'],10)
        write('BlockEnable',False);write('A',5);v=values(self.post('step',{'dt':10}));self.assertTrue(v['InRange']);self.assertFalse(v['CompareEnabled'])
        write('BlockEnable',True);state=self.post('step',{'dt':10});v=values(state);self.assertFalse(v['InRange']);self.assertEqual(v['TimerACC'],0)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),9)
        p=self.post('report',{})['function_blocks'];self.assertEqual(len(p['instructions']),63)
        self.assertEqual(p['blocks']['comparison']['records']['FBD_COMPARE']['Dest'],'BOOL');self.assertFalse(p['native_runtime_parity'])

    def test_fbd_bitwise_lab_masks_target_bool_timer_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDBitwiseLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram']
        self.assertEqual((len(graph['nodes']),len(graph['wires'])),(28,37));self.assertIn(b'FBD bitwise lab',self.get('/'))
        self.assertIn(b"loadDemo('FBDBitwiseLab')",self.get('/app.js'))
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertEqual(tuple(v[t] for t in ('AndValue','OrValue','XorValue','Inverted','Merged')),(136,238,102,-103,250));self.assertIs(v['Matches'],True)
        self.assertEqual((v['SelectedValue'],v['TimerACC']),(100,0))
        self.post('step',{'dt':10});self.assertTrue(values(self.post('step',{'dt':10}))['TimerDone'])
        write('CompareValue',11);v=values(self.post('step',{'dt':10}));self.assertFalse(v['Matches']);self.assertEqual((v['SelectedValue'],v['TimerACC']),(0,0))
        write('Mask',0);write('Target',-123);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Merged'],-123);self.assertTrue(v['Matches'])
        write('Mask',-1);write('A',-456);write('CompareValue',-456);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Merged'],-456);self.assertTrue(v['Matches'])
        before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
        write('FaultDivisor',1);self.assertTrue(values(self.post('step',{'dt':10}))['Matches'])
        write('BlockEnable',False);write('MoveState.Dest',123);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Merged'],123);self.assertFalse(v['BitwiseEnabled'])
        write('BlockEnable',True);state=self.post('step',{'dt':10});self.assertEqual(values(state)['Merged'],-456)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),8)
        p=self.post('report',{})['function_blocks'];self.assertEqual(len(p['instructions']),63)
        self.assertEqual(p['blocks']['bitwise']['records']['FBD_MASK_EQUAL']['Dest'],'BOOL');self.assertFalse(p['native_runtime_parity'])

    def test_fbd_advanced_math_lab_domains_rounding_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDAdvancedMathLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram'];self.assertEqual((len(graph['nodes']),len(graph['wires'])),(33,38))
        self.assertIn(b'FBD advanced math lab',self.get('/'));self.assertIn(b"loadDemo('FBDAdvancedMathLab')",self.get('/app.js'))
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['Root'],v['CommonLog'],v['Power']),(3,2,8));self.assertAlmostEqual(v['Sine'],.5,places=6);self.assertAlmostEqual(v['RecoveredDegrees'],30,places=5)
        write('RootInput',-25);write('PowerBase',-2);write('PowerExponent',3);v=values(self.post('step',{'dt':10}));self.assertEqual((v['Root'],v['Power']),(5,-8))
        for tag,bad,good in (('LogInput',0,100),('PowerExponent',.5,3),('Ratio',2,.5)):
            before=write(tag,bad)
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
            write(tag,good);self.assertEqual(values(self.post('step',{'dt':10}))['Power'],-8)
        write('BlockEnable',False);write('LogInput',0);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Power'],-8);self.assertFalse(v['MathEnabled'])
        write('LogInput',100);write('BlockEnable',True);write('AngleDegrees',-30);state=self.post('step',{'dt':10});self.assertAlmostEqual(values(state)['Sine'],-.5,places=6)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),12)
        profile=self.post('report',{})['function_blocks'];self.assertEqual(len(profile['instructions']),63);self.assertEqual(len(profile['blocks']['math']['instructions']),19);self.assertFalse(profile['native_runtime_parity'])

    def test_fbd_conversion_lab_remainder_truncation_bcd_and_retry_through_http(self):
        state=self.post('demo',{'sample':'FBDConversionLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram'];self.assertEqual((len(graph['nodes']),len(graph['wires'])),(16,17))
        self.assertIn(b'FBD conversion lab',self.get('/'));self.assertIn(b"loadDemo('FBDConversionLab')",self.get('/app.js'))
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertEqual(tuple(v[t] for t in ('Remainder','Truncated','PackedBCD','Roundtrip','Decoded')),(2.75,2,0x12345678,12345678,12345684))
        write('Value',-17.75);write('DecimalInput',99999999);write('RawBCD',-1);v=values(self.post('step',{'dt':10}));self.assertEqual((v['Remainder'],v['Truncated'],v['PackedBCD'],v['Roundtrip'],v['Decoded']),(-2.75,-2,-1717986919,99999999,166666665))
        for tag,bad,good in (('Divisor',0,5),('DecimalInput',-1,99999999),('FaultDivisor',0,1)):
            before=write(tag,bad)
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
            write(tag,good);self.assertEqual(values(self.post('step',{'dt':10}))['Truncated'],-2)
        write('BlockEnable',False);write('Divisor',0);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Truncated'],-2);self.assertFalse(v['ConversionEnabled'])
        write('Divisor',5);write('BlockEnable',True);state=self.post('step',{'dt':10});self.assertEqual(values(state)['Roundtrip'],99999999)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),5)
        profile=self.post('report',{})['function_blocks'];self.assertEqual(len(profile['instructions']),63);self.assertEqual(profile['blocks']['conversion']['records']['FBD_TRUNCATE']['Dest'],'DINT');self.assertFalse(profile['native_runtime_parity'])

    def test_target_move_lab_st_fbd_gating_dynamic_fields_and_retry_through_http(self):
        state=self.post('demo',{'sample':'TargetMoveLab'});self.assertEqual(state['blockers'],[])
        graph=next(row for row in state['routines'] if row['kind']=='FBD')['diagram'];self.assertEqual((len(graph['nodes']),len(graph['wires'])),(12,13))
        self.assertIn(b'Target bit move lab',self.get('/'));self.assertIn(b"loadDemo('TargetMoveLab')",self.get('/app.js'))
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['TextFieldValue'],v['GraphFieldValue']),(0x236700aa,0x236700aa));self.assertEqual((v['TextOutput'],v['GraphOutput']),(0x23670078,0x23670078))
        write('BlockEnable',False);write('Word',0);write('BaseWord',0);v=values(self.post('step',{'dt':10}));self.assertEqual(v['TextOutput'],0);self.assertEqual(v['GraphOutput'],0x23670078);self.assertTrue(v['TextEnabled']);self.assertFalse(v['GraphEnabled'])
        write('BlockEnable',True);write('ExecuteText',False);write('Word',-1);write('SourceOffset',0);write('BitCount',32);write('DestinationOffset',0);write('Mask',-1);v=values(self.post('step',{'dt':10}));self.assertEqual(v['TextOutput'],0);self.assertEqual(v['GraphOutput'],-1)
        write('ExecuteText',True)
        for tag,bad,good in (('BitCount',0,32),('FaultDivisor',0,1)):
            before=write(tag,bad)
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule'):self.assertEqual(after[key],before[key],key)
            write(tag,good);state=self.post('step',{'dt':10});self.assertEqual(values(state)['TextOutput'],-1);self.assertEqual(values(state)['GraphOutput'],-1)
        self.assertEqual(len([t for t in state['trace'] if t.get('language')=='FBD']),2)
        p=self.post('report',{});self.assertEqual(len(p['function_blocks']['instructions']),63);self.assertEqual(p['st_bit_moves']['instructions'],['BTDT','MVMT']);self.assertFalse(p['st_bit_moves']['native_runtime_parity'])

    def test_quit_exits_process_and_releases_protocol_and_http_listeners(self):
        self.post('demo', {'sample': 'ConveyorDemo'})
        state = self.post('connectivity-start', {'port': 0})
        protocol_port = int(state['connectivity']['address'].split(':')[-1])
        http_port = int(self.url.split(':')[-1])
        self.assertEqual(self.post('quit', {}), {'closed': True})
        self.assertEqual(self.process.wait(timeout=5), 0)
        marker=json.loads((Path(self.tmp.name)/'shutdown-request.json').read_text())
        self.assertEqual(marker,dict(instance_id=self.session['instance_id'],app_version=__version__,reason='api'))
        for port in (protocol_port, http_port):
            with self.assertRaises(OSError):
                socket.create_connection(('127.0.0.1', port), timeout=0.2)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.bind(('127.0.0.1', protocol_port))

    def test_device_api_has_scoped_tokens_cached_reads_and_queued_input_acknowledgements(self):
        self.post('demo',{'sample':'NetworkLab'})
        self.post('device-io-configure',{'allow_writes':True})
        session=json.loads(self.get('/api/device-io/session'))
        def device(path,body=None,token=None,headers=None):
            request=Request(self.url+'/api/device-io/'+path,json.dumps(body).encode() if body is not None else None,
                            {'X-Logix-Device-Token':token or session['read_token'],**(headers or {})})
            return urlopen(request,timeout=3)
        with device('snapshot') as response:
            frame=json.load(response);etag=response.headers['ETag']
        with self.assertRaises(HTTPError) as error:device('snapshot',headers={'If-None-Match':etag})
        self.assertEqual(error.exception.code,304)
        body={'request_id':'http-device','instance_id':frame['instance_id'],
              'project_generation':frame['project_generation'],'writes':[{'tag':'Command','value':76}]}
        with self.assertRaises(HTTPError) as error:device('write',body)
        self.assertEqual(error.exception.code,403)
        with device('write',body,session['write_token']) as response:
            self.assertEqual(response.status,202);self.assertEqual(json.load(response)['status'],'queued')
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url+'/api/step',b'{}',{'X-Logix-Token':session['write_token']}),timeout=3)
        self.assertEqual(error.exception.code,403)
        self.post('step',{'count':1,'dt':10})
        with device('requests/http-device') as response:self.assertEqual(json.load(response)['status'],'applied')
        with device('snapshot') as response:
            values={t['name']:t['value'] for t in json.load(response)['tags']}
        self.assertEqual(values['Observed'],76)

    def test_ladder_wide_lab_exact_values_gating_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'WideExpressionLab'});self.assertEqual(state['blockers'],[])
        self.assertEqual({row['kind'] for row in state['routines']},{'RLL'})
        self.assertIn(b'Ladder wide expression lab',self.get('/'));self.assertIn(b"loadDemo('WideExpressionLab')",self.get('/app.js'))
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        v=values(self.post('step',{'dt':10}));self.assertEqual(v['SignedResult'],'9007199254740995');self.assertEqual(v['UnsignedResult'],'18446744073709551615')
        self.assertTrue(v['ExactCompare']);self.assertTrue(v['MaskMatches']);self.assertEqual(v['SignedQuotient'],'-3074457345618258602')
        write('Execute',False);write('SignedInput','1');v=values(self.post('step',{'dt':10}));self.assertEqual(v['SignedResult'],'9007199254740995');self.assertFalse(v['ExactCompare'])
        write('Execute',True);write('SignedInput','9007199254740992');v=values(self.post('step',{'dt':10}));self.assertEqual(v['SignedResult'],'9007199254740994')
        before=write('FaultDivisor','0')
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        self.assertEqual((after['tags'],after['scan'],after['ms']),(before['tags'],before['scan'],before['ms']))
        write('FaultDivisor','1');v=values(self.post('step',{'dt':10}));self.assertEqual(v['Scans'],4)
        report=self.post('report',{})['wide_ladder_expressions'];self.assertEqual(report['instructions'],['CPT','CMP','MEQ']);self.assertFalse(report['native_runtime_parity'])

    def test_queue_reference_lab_aliases_indirect_edges_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'QueueReferenceLab'});self.assertEqual(state['blockers'],[])
        self.assertEqual({r['kind'] for r in state['routines']},{'RLL'})
        self.assertIn(b'Queue reference lab',self.get('/'));self.assertIn(b"loadDemo('QueueReferenceLab')",self.get('/app.js'))
        values=lambda s:{row['name']:row['value'] for row in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        self.post('step',{'dt':10});write('Load',True);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Buffer[1]'],11);self.assertEqual(v['QueueControl.POS'],1)
        write('StartIndex',999);v=values(self.post('step',{'dt':10}));self.assertEqual(v['QueueControl.POS'],1)
        write('Load',False);self.post('step',{'dt':10});before=write('Load',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        self.assertEqual((after['tags'],after['scan'],after['ms']),(before['tags'],before['scan'],before['ms']))
        write('StartIndex',1);v=values(self.post('step',{'dt':10}));self.assertEqual(v['Buffer[2]'],11)
        write('Load',False);write('Push',True);write('ShiftLeft',True);v=values(self.post('step',{'dt':10}));self.assertEqual((v['Stack[1]'],v['Bits[1]']),(11,1))
        write('Push',False);write('ShiftLeft',False);self.post('step',{'dt':10})
        for tag,value in (('Incoming',22),('Load',True),('Push',True),('ShiftLeft',True),('FaultDivisor',0)):before=write(tag,value)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        self.assertEqual((after['tags'],after['scan'],after['ms']),(before['tags'],before['scan'],before['ms']))
        write('FaultDivisor',1);v=values(self.post('step',{'dt':10}));self.assertEqual((v['Buffer[3]'],v['Stack[2]'],v['Bits[1]']),(22,22,3))
        self.assertEqual((v['Buffer[0]'],v['Buffer[6]'],v['Stack[0]'],v['Stack[5]'],v['Bits[0]'],v['Bits[3]']),(101,999,102,998,103,777))
        profile=self.post('report',{})['control_operations'];self.assertIn('indirect',profile['starting_references']);self.assertFalse(profile['native_control_layout'])

    def test_aoi_queue_lab_instances_disable_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'AOIQueueLab'});self.assertEqual(state['blockers'],[])
        self.assertIn(b'AOI queue lab',self.get('/'));self.assertIn(b"loadDemo('AOIQueueLab')",self.get('/app.js'))
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.post('step',{'dt':10})
        for tag in ('Load','Push','Shift'):write(tag,True)
        v=values(self.post('step',{'dt':10}));self.assertEqual((v['BufferA[1]'],v['BufferB[2]'],v['DriverA.Stack[0]'],v['DriverB.Stack[0]']),(11,22,11,22))
        write('EnabledA',False);write('IndexA',999);v=values(self.post('step',{'dt':10}));self.assertFalse(v['StateA.EN']);self.assertTrue(v['StateB.EN'])
        write('EnabledA',True);write('IndexA',1);write('ValueA',33);v=values(self.post('step',{'dt':10}));self.assertEqual((v['BufferA[2]'],v['DriverA.Popped'],v['DriverA.Word'],v['DriverB.Word']),(33,0,3,1))
        for tag in ('Load','Push','Shift'):write(tag,False)
        self.post('step',{'dt':10});write('ValueA',55);write('ValueB',66)
        for tag in ('Load','Push','Shift'):write(tag,True)
        before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);v=values(self.post('step',{'dt':10}));self.assertEqual((v['BufferB[3]'],v['DriverB.Stack[1]'],v['DriverA.Word'],v['DriverB.Word']),(66,66,7,3))
        for tag in ('Load','Push','Shift'):write(tag,False)
        self.post('step',{'dt':10});write('Unload',True);before=write('IndexB',999)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        self.assertEqual((after['tags'],after['scan'],after['ms']),(before['tags'],before['scan'],before['ms']))
        write('IndexB',2);v=values(self.post('step',{'dt':10}));self.assertEqual((v['ItemA'],v['ItemB']),(11,22))
        self.assertEqual((v['BufferA[0]'],v['BufferA[5]'],v['BufferB[0]'],v['BufferB[5]'],v['DriverA.Stack[3]'],v['DriverB.Stack[3]'],v['DriverA.Bits[2]'],v['DriverB.Bits[2]']),(101,901,102,902,777,777,888,888))
        report=self.post('report',{});self.assertEqual(len(report['add_on_instructions']['instances']),2);self.assertIn('InOut',report['control_operations']['aoi_arrays'])

    def test_aoi_file_lab_progress_inhibit_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'AOIFileLab'});self.assertEqual(state['blockers'],[])
        self.assertIn(b'AOI file lab',self.get('/'));self.assertIn(b"loadDemo('AOIFileLab')",self.get('/app.js'))
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        self.post('step',{'dt':10});write('Transform',True);write('Search',True);v=values(step())
        self.assertEqual((v['OutputA[0]'],v['OutputB[0]'],v['CalcA.POS'],v['CalcB.POS']),(5,2,0,0))
        v=values(step());self.assertEqual(v['CalcA.POS'],0)
        for _ in range(2):
            write('Transform',False);write('Search',False);step();write('Transform',True);write('Search',True);v=values(step())
        self.assertEqual((v['OutputA[2]'],v['OutputB[2]'],v['FindA.POS']),(13,14,2));self.assertTrue(v['FindA.IN']);self.assertTrue(v['DriverA.Found'])
        write('Transform',False);write('Search',False);step();write('Transform',True);write('Search',True);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);v=values(step());self.assertEqual((v['OutputA[3]'],v['OutputB[3]'],v['DriverA.Total'],v['DriverB.Total']),(17,20,24,12));self.assertTrue(v['CalcA.DN']);self.assertTrue(v['FindB.DN'])
        write('FindA.IN',False);v=values(step());self.assertEqual(v['FindA.POS'],2)
        write('Search',False);write('Transform',False);step();write('Search',True);v=values(step());self.assertEqual(v['FindA.POS'],3);self.assertTrue(v['FindA.DN']);self.assertTrue(v['FindA.IN'])
        self.assertEqual((v['InputA[4]'],v['InputB[4]'],v['OutputA[4]'],v['OutputB[4]'],v['DriverA.Scratch[4]'],v['DriverB.Scratch[4]']),(999,998,901,902,777,777))
        report=self.post('report',{});self.assertIn('InOut',report['file_arithmetic']['aoi']);self.assertIn('InOut',report['file_search']['aoi']);self.assertEqual(len(report['add_on_instructions']['instances']),2)


    def test_pid_lab_modes_scaling_and_rollback_through_http(self):
        state=self.post('demo',{'sample':'PIDLab'});self.assertEqual(state['blockers'],[])
        self.assertIn(b'id="pid-demo"',self.get('/'));self.assertIn(b"loadDemo('PIDLab')",self.get('/app.js'))
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        write('Execute',True);self.assertEqual(values(step())['CV'],45)
        self.assertEqual(values(step())['CV'],60)
        write('Loop.SWM',True);write('Loop.SO',70);self.assertEqual(values(step())['CV'],70)
        write('Loop.SWM',False);self.assertEqual(values(step())['CV'],70)
        before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        write('FaultDivisor',1);self.assertEqual(values(step())['CV'],85)
        write('Execute',False);self.assertEqual(values(step())['CV'],85)
        p=self.post('report',{})['ladder_pid'];self.assertFalse(p['native_runtime_parity']);self.assertEqual(p['data_elements'],17)


    def test_pid_derivative_deadband_and_rollback_through_http(self):
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        def fault(before):
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        self.assertEqual(self.post('demo',{'sample':'PIDLab'})['blockers'],[])
        for tag,value in [('Loop.KP',0),('Loop.KI',0),('Loop.BIAS',50),('Loop.KD',2),('Loop.NDF',True),('Execute',True)]:write(tag,value)
        self.assertEqual(step()['CV'],50);write('PV',25);self.assertEqual(step()['CV'],40)
        write('Loop.SP',55);self.assertEqual(step()['CV'],50)
        write('Loop.DOE',True);write('Loop.SP',60);self.assertEqual(step()['CV'],50)
        write('Loop.SP',61);self.assertEqual(step()['CV'],52)
        write('PV',26);fault(write('FaultDivisor',0));write('FaultDivisor',1);self.assertEqual(step()['CV'],48)
        self.assertEqual(self.post('demo',{'sample':'PIDLab'})['blockers'],[])
        for tag,value in [('Loop.DB',2),('Execute',True),('PV',47)]:write(tag,value)
        self.assertEqual(step()['CV'],4.5);write('PV',49);row=step();self.assertEqual(row['CV'],3);self.assertFalse(row['Loop.CTL']&(1<<11))
        write('PV',51);row=step();self.assertEqual(row['CV'],3);self.assertTrue(row['Loop.CTL']&(1<<11))
        write('PV',47);fault(write('FaultDivisor',0));write('FaultDivisor',1);self.assertEqual(step()['CV'],6.5)
        write('Loop.NOZC',True);write('PV',49);self.assertEqual(step()['CV'],6.5)
        write('Loop.SWM',True);write('Loop.SO',70);self.assertEqual(step()['CV'],70)
        write('Loop.SWM',False);row=step();self.assertEqual(row['CV'],70);self.assertTrue(row['Loop.CTL']&(1<<11))
        p=self.post('report',{})['ladder_pid'];self.assertIn('NDF',p['derivative']);self.assertIn('NOZC',p['deadband']);self.assertFalse(p['native_runtime_parity'])


    def test_pid_integer_loops_hardware_manual_and_rollback_through_http(self):
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        def fault(before):
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        loaded=self.post('demo',{'sample':'PIDLab'});self.assertEqual(loaded['blockers'],[])
        self.assertIs(type(values(loaded)['Manual']),bool);self.assertIs(type(values(loaded)['IntManual']),bool)
        write('Execute',True);write('IntExecute',True);row=step();self.assertEqual((row['CV'],row['RawCV'],row['IntLoop.PV']),(45,8192,25))
        for tag,value in [('Manual',True),('IntManual',True),('Tieback',60)]:write(tag,value)
        row=step();self.assertEqual((row['CV'],row['RawCV'],row['Loop.TIE'],row['IntLoop.TIE']),(60,19660,60,60))
        for tag,value in [('IntManual',False),('IntSoftwareManual',True),('IntLoop.SO',50)]:write(tag,value)
        self.assertEqual(step()['RawCV'],16384);write('IntSoftwareManual',False);self.assertEqual(step()['RawCV'],16384)
        write('IntManual',True);write('Tieback',75);fault(write('FaultDivisor',0));write('FaultDivisor',1)
        row=step();self.assertEqual((row['CV'],row['RawCV'],row['IntLoop.DATA[14]']),(75,24575,24575))
        for tag,value in [('IntManual',False),('IntLoop.DB',2),('IntNoZeroCrossing',True),('RawPV',11840)]:write(tag,value)
        row=step();self.assertEqual((row['RawCV'],row['IntLoop.OUT']),(0,75));self.assertTrue(row['IntLoop.CTL']&(1<<11))
        write('IntManual',True);write('Tieback',60);row=step();self.assertEqual(row['RawCV'],19660);self.assertFalse(row['IntLoop.CTL']&(1<<11))
        fault(write('IntLoop.MAXCV',100000));write('IntLoop.MAXCV',32767);self.assertEqual(step()['RawCV'],19660)
        p=self.post('report',{})['ladder_pid'];self.assertIn('ties-to-even',p['conversions']);self.assertIn('MO overrides SWM',p['manual']);self.assertFalse(p['native_runtime_parity'])


    def test_pid_tracking_inhold_release_and_rollback_through_http(self):
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        def fault(before):
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            self.assertEqual((after['tags'],after['scan'],after['ms'],after['task_schedule']),(before['tags'],before['scan'],before['ms'],before['task_schedule']))
        self.assertEqual(self.post('demo',{'sample':'PIDLab'})['blockers'],[])
        write('Execute',True);self.assertEqual(step()['CV'],45)
        write('Inhold',True);write('Readback',75);row=step();self.assertEqual((row['CV'],row['Loop.OUT'],row['Loop.DATA[0]']),(75,75,45));self.assertTrue(row['Inhold'])
        write('Readback',80);fault(write('FaultDivisor',0));write('FaultDivisor',1);self.assertEqual(step()['CV'],80)
        write('Inhold',False);self.assertEqual(step()['CV'],80)
        write('Manual',True);write('PVTracking',True);write('PV',25);row=step();self.assertEqual((row['CV'],row['Loop.SP'],row['Loop.ERR']),(50,25,0))
        write('Inhold',True);write('Readback',65);write('PV',30);row=step();self.assertEqual((row['CV'],row['Loop.SP']),(65,25))
        write('Inhold',False);row=step();self.assertEqual((row['CV'],row['Loop.SP']),(50,30))
        write('IntExecute',True);write('IntInhold',True);write('IntReadback',20000);row=step();self.assertEqual((row['RawCV'],row['IntLoop.DATA[14]']),(20000,20000))
        fault(write('IntReadback',-1));write('IntReadback',21000);self.assertEqual(step()['RawCV'],21000)
        p=self.post('report',{})['ladder_pid'];self.assertIn('PVT',p['pv_tracking']);self.assertIn('acknowledgement',p['inhold']);self.assertFalse(p['native_runtime_parity'])

    def test_pid_cascade_scan_order_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'PIDLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        for tag in ('Execute','IntExecute','Cascade','CascadeMaster','IntCascade'):write(tag,True)
        row=step();self.assertEqual((row['CV'],row['IntLoop.SP'],row['RawCV']),(45,45,6553))
        before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FaultDivisor',1);row=step();self.assertEqual((row['CV'],row['IntLoop.SP'],row['RawCV']),(60,60,11468))
        write('Execute',False);row=step();self.assertEqual(row['IntLoop.SP'],60)
        p=self.post('report',{})['ladder_pid'];self.assertIn('one-way',p['cascade']);self.assertFalse(p['native_runtime_parity'])

    def test_aoi_pid_lab_local_inout_modes_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'AOIPIDLab'})['blockers'],[])
        self.assertIn(b'AOI PID lab',self.get('/'));self.assertIn(b"loadDemo('AOIPIDLab')",self.get('/app.js'))
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        write('EnabledA',True);write('EnabledB',True);row=step()
        self.assertEqual((row['CVA'],row['CVB'],row['DriverA.AuxValue'],row['DriverB.AuxValue']),(45,22.5,5,0))
        before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FaultDivisor',1);self.assertEqual(step()['CVA'],60)
        write('EnabledA',False);row=step();self.assertFalse(row['ControlA.CTL']&(1<<31));self.assertTrue(row['ControlB.CTL']&(1<<31))
        write('EnabledA',True);write('HoldA',True);write('ReadbackA',70);row=step();self.assertEqual((row['CVA'],row['DriverA.AuxValue']),(70,70))
        report=self.post('report',{});self.assertEqual(len(report['add_on_instructions']['instances']),2);self.assertIn('InOut',report['ladder_pid']['aoi'])

    def test_aoi_sequencer_lab_tables_false_mode_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'AOISequencerLab'})['blockers'],[])
        self.assertIn(b'AOI sequencer lab',self.get('/'));self.assertIn(b"loadDemo('AOISequencerLab')",self.get('/app.js'))
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        step();write('Step',True);write('Teach',True);row=step()
        self.assertEqual((row['OutputsA'],row['OutputsB'],row['LearnedA[2]'],row['DriverB.Scratch[3]']),(0x120001,0x340008,11,22))
        self.assertTrue(row['DriverA.Matched']);self.assertTrue(row['DriverB.Matched'])
        write('ValueA',33);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FaultDivisor',1);row=step();self.assertEqual((row['LearnedA[2]'],row['DriverA.Scratch[2]']),(33,33))
        write('EnabledA',False);write('IndexA',999);row=step();self.assertFalse(row['SequenceA.EN']);self.assertTrue(row['SequenceB.EN'])
        write('IndexA',1);write('EnabledA',True);row=step();self.assertEqual((row['SequenceA.POS'],row['SequenceB.POS']),(2,1))
        profile=self.post('report',{})['sequencer_operations'];self.assertIn('indirect',profile['starting_references']);self.assertIn('InOut',profile['aoi']);self.assertFalse(profile['native_scan_parity'])

    def test_sequencer_alias_suffix_keeps_caller_scope_through_http(self):
        import base64
        from xml.etree import ElementTree as E
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/SequenceLab.L5X').getroot()
        tags=root.find('./Controller/Tags');program=root.find('./Controller/Programs/Program/Tags')
        E.SubElement(tags,'Tag',Name='PatternView',DataType='DINT',Dimensions='5',TagType='Alias',AliasFor='Patterns')
        for parent,value in ((tags,0),(program,1)):
            tag=E.SubElement(parent,'Tag',Name='Offset',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        tags.find('Tag[@Name="SequenceControl"]/Data/Structure/DataValueMember[@Name="LEN"]').set('Value','2')
        content=root.find('.//Program/Routines/Routine/RLLContent');content.clear()
        E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='SQO(PatternView[Offset],255,Outputs,SequenceControl,?,?);'
        loaded=self.post('load',{'name':'CallerScope.L5X','content':base64.b64encode(E.tostring(root,encoding='utf-8',xml_declaration=True)).decode()});self.assertEqual(loaded['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        self.assertEqual(values(self.post('step',{'dt':10}))['Outputs'],0x120001)
        self.post('write',{'tag':'Program:MainProgram.Offset','value':2})
        self.assertEqual(values(self.post('step',{'dt':10}))['Outputs'],0x120002)

    def test_aoi_statistics_lab_dimensions_latches_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'AOIStatsLab'})['blockers'],[])
        self.assertIn(b'AOI statistics lab',self.get('/'));self.assertIn(b"loadDemo('AOIStatsLab')",self.get('/app.js'))
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        write('Calculate',True);row=step()
        self.assertEqual(tuple(row[t] for t in ('DriverA.Mean','DriverA.Deviation','DriverA.ColumnMean','DriverA.RowMean','DriverA.PlaneMean','DriverB.Mean','DriverB.Deviation')),(4,2,7,10,7,20,10))
        write('IndexA',999);self.assertEqual(step()['DriverA.Mean'],4)
        write('Calculate',False);row=step();self.assertFalse(row['MeanA.DN']);self.assertEqual(row['MeanA.POS'],0)
        write('IndexA',2);write('Calculate',True);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FaultDivisor',1);row=step();self.assertEqual((row['DriverA.Mean'],row['DriverA.LocalMean']),(6,6))
        write('EnabledA',False);row=step();self.assertFalse(row['DriverA.Ready']);self.assertTrue(row['DriverB.Ready'])
        write('EnabledA',True);row=step();self.assertTrue(row['DriverA.Ready'])
        report=self.post('report',{})['array_statistics'];self.assertIn('InOut',report['aoi']);self.assertIn('indirect',report['starting_references']);self.assertFalse(report['native_math_status'])

    def test_statistics_alias_column_latching_and_bad_start_through_http(self):
        import base64
        from xml.etree import ElementTree as E
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/StatsLab.L5X').getroot();tags=root.find('./Controller/Tags');program=root.find('./Controller/Programs/Program/Tags')
        E.SubElement(tags,'Tag',Name='GridView',DataType='DINT',Dimensions='2,3',TagType='Alias',AliasFor='Grid')
        for parent,value in ((tags,0),(program,1)):
            tag=E.SubElement(parent,'Tag',Name='Offset',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        content=root.find('.//Program/Routines/Routine/RLLContent');content.clear();E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='XIC(Calculate)AVE(GridView[0,Offset],0,ColumnMean,ColumnControl,?,?);'
        self.assertEqual(self.post('load',{'name':'CallerStatistics.L5X','content':base64.b64encode(E.tostring(root,encoding='utf-8',xml_declaration=True)).decode()})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        self.post('write',{'tag':'Calculate','value':True});self.assertEqual(values(self.post('step',{'dt':10}))['ColumnMean'],7)
        self.post('write',{'tag':'Program:MainProgram.Offset','value':999});self.assertEqual(values(self.post('step',{'dt':10}))['ColumnMean'],7)
        self.post('write',{'tag':'Calculate','value':False});self.post('step',{'dt':10});before=self.post('write',{'tag':'Calculate','value':True})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'Program:MainProgram.Offset','value':2});self.assertEqual(values(self.post('step',{'dt':10}))['ColumnMean'],9)

    def test_aoi_sort_lab_axes_latches_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'AOISortLab'})['blockers'],[])
        self.assertIn(b'AOI sort lab',self.get('/'));self.assertIn(b"loadDemo('AOISortLab')",self.get('/app.js'))
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        write('Sort',True);row=step()
        self.assertEqual(tuple(row[t] for t in ('SamplesA[1]','SamplesB[2]','GridA[0,1]','GridB[0,2]','CubeA[1,1,0]','DriverA.Scratch[1]')),(2,10,4,10,7,3))
        write('IndexA',999);write('SamplesA[1]',7);self.assertEqual(step()['SamplesA[1]'],7)
        write('Sort',False);step();write('IndexA',1);write('Sort',True);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FaultDivisor',1);row=step();self.assertEqual((row['SamplesA[1]'],row['SamplesA[2]'],row['SamplesA[3]']),(4,6,7))
        write('EnabledA',False);row=step();self.assertFalse(row['OrderA.EN']);self.assertTrue(row['OrderB.EN'])
        report=self.post('report',{})['array_sort'];self.assertIn('InOut',report['aoi']);self.assertIn('parent arrays',report['write_effects']);self.assertFalse(report['native_math_status'])

    def test_st_sort_alias_repeated_calls_and_late_fault_through_http(self):
        import base64
        from xml.etree import ElementTree as E
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/StatsLab.L5X').getroot();tags=root.find('./Controller/Tags');program=root.find('./Controller/Programs/Program/Tags')
        E.SubElement(tags,'Tag',Name='GridView',DataType='REAL',Dimensions='2,3',TagType='Alias',AliasFor='SortGrid')
        for parent,name,value in ((tags,'Offset',0),(program,'Offset',1),(tags,'FaultDivisor',1)):
            tag=E.SubElement(parent,'Tag',Name=name,DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        routine=root.find('.//Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
        E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='IF TextSort THEN SRT(GridView[0,Offset],0,TextSortControl); END_IF; ColumnMean:=1.0/FaultDivisor;'
        self.assertEqual(self.post('load',{'name':'AliasSort.L5X','content':base64.b64encode(E.tostring(root,encoding='utf-8',xml_declaration=True)).decode()})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        self.post('write',{'tag':'TextSort','value':True});self.assertEqual(values(self.post('step',{'dt':10}))['SortGrid[0,1]'],4)
        self.post('write',{'tag':'SortGrid[0,1]','value':20});self.assertEqual(values(self.post('step',{'dt':10}))['SortGrid[0,1]'],10)
        self.post('write',{'tag':'SortGrid[0,1]','value':30});before=self.post('write',{'tag':'FaultDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'FaultDivisor','value':1});self.assertEqual(values(self.post('step',{'dt':10}))['SortGrid[0,1]'],20)

    def test_aoi_bit_diagnostics_arrays_learning_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'AOIBitLab'})['blockers'],[])
        self.assertIn(b'AOI bit diagnostics lab',self.get('/'));self.assertIn(b"loadDemo('AOIBitLab')",self.get('/app.js'))
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        write('CompareEnable',True);write('DetectEnable',True);row=step()
        self.assertEqual(tuple(row[t] for t in ('CompareResultsA[1]','CompareResultsA[2]','CompareResultsA[3]','LearnedA[1]','LearnedB[1]','DriverA.Scratch[1]')),(32,39,31,1,2,1))
        write('DetectEnable',False);step();write('DetectEnable',True);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FaultDivisor',1);row=step();self.assertEqual((row['LearnedA[1]'],row['DriverA.Scratch[1]'],row['DetectA.POS']),(33,33,6))
        write('EnabledA',False);write('SourceIndexA',999);row=step();self.assertFalse(row['DetectA.EN']);self.assertTrue(row['DetectB.EN'])
        write('SourceIndexA',1);write('EnabledA',True);row=step();self.assertEqual(row['DetectA.POS'],32)
        profile=self.post('report',{})['file_bit_compare'];self.assertIn('one-dimensional',profile['aoi']);self.assertIn('before',profile['sampling']);self.assertFalse(profile['native_runtime_parity'])

    def test_ddt_result_index_is_sampled_before_learning_through_http(self):
        import base64
        from xml.etree import ElementTree as E
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/BitLab.L5X').getroot()
        # A two-bit operation uses the existing first source/reference/result
        # elements; the result address depends on the reference being learned.
        tags=root.find('./Controller/Tags')
        for name,value in (('CompareSource',3),('LearnReference',0)):
            tags.find(f'Tag[@Name="{name}"]/Data/Array/Element[@Index="[0]"]').set('Value',str(value))
        state=tags.find('Tag[@Name="DetectControl"]/Data/Structure');state.find('DataValueMember[@Name="LEN"]').set('Value','2');state.find('DataValueMember[@Name="IN"]').set('Value','0')
        content=root.find('.//Program/Routines/Routine/RLLContent');content.clear();E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='DDT(CompareSource[0],LearnReference[0],ChangedBits[LearnReference[0]],DetectControl,?,?,DetectResultControl,?,?);'
        self.assertEqual(self.post('load',{'name':'SampledResult.L5X','content':base64.b64encode(E.tostring(root,encoding='utf-8',xml_declaration=True)).decode()})['blockers'],[])
        values={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual((values['LearnReference[0]'],values['ChangedBits[0]'],values['ChangedBits[1]']),(3,0,1))

    def test_math_lab_integer_results_round_retain_and_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'MathLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        row=values(self.post('step',{'dt':10}))
        for tag in ('ByteRoot','WordRoot','DintRoot'):self.assertEqual(row[tag],4)
        self.assertEqual((row['RoundedRoot'],row['RoundedPower']),(2,-2))
        self.post('write',{'tag':'RoundingInput','value':12.25})
        self.assertEqual(values(self.post('step',{'dt':10}))['RoundedRoot'],4)
        for tag,value in (('Enable',False),('Input',40000),('RoundingInput',6.25)):self.post('write',{'tag':tag,'value':value})
        row=values(self.post('step',{'dt':10}));self.assertEqual((row['ByteRoot'],row['RoundedRoot'],row['StRoot']),(4,4,200.0))
        before=self.post('write',{'tag':'Enable','value':True})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'Input','value':25});row=values(self.post('step',{'dt':10}))
        self.assertEqual(tuple(row[t] for t in ('Root','ByteRoot','WordRoot','DintRoot','RoundedRoot','RoundedPower')),(5.0,5,5,5,2,-2))
        report=self.post('report',{})['real_math'];self.assertEqual(report['destinations'],['DINT','INT','REAL','SINT']);self.assertIn('ties to even',report['integer_conversion']);self.assertFalse(report['native_math_status'])

    def test_stats_lab_integer_averages_latch_round_and_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'StatsLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        write('Calculate',True);row=step()
        self.assertEqual(tuple(row[t] for t in ('Average','ByteAverage','WordAverage','DintAverage','RoundingValues[4]')),(5.0,2,2,2,777))
        write('RoundingValues[0]',5);self.assertEqual(step()['ByteAverage'],2)
        write('Calculate',False);row=step();self.assertFalse(row['ByteMeanControl.DN']);self.assertEqual(row['ByteMeanControl.POS'],0)
        write('Calculate',True);self.assertEqual(step()['ByteAverage'],4)
        write('Calculate',False);step()
        for i in range(4):write(f'RoundingValues[{i}]',127.5)
        before=write('Calculate',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('RoundingValues[0]',125.5);row=step()
        self.assertEqual(tuple(row[t] for t in ('ByteAverage','WordAverage','DintAverage','ByteMeanControl.POS','RoundingValues[4]')),(127,127,127,4,777))
        write('Calculate',False);write('Reset',True);row=step();self.assertEqual(row['DintMeanControl.POS'],0)
        report=self.post('report',{})['array_statistics'];self.assertEqual(report['destinations']['STD'],['REAL']);self.assertIn('SINT',report['destinations']['AVE']);self.assertFalse(report['native_math_status'])

    def test_conversion_lab_narrow_bcd_roundtrips_and_range_recovery_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'ConversionLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        row=step();self.assertEqual(tuple(row[t] for t in ('BytePacked','ByteDecoded','WordPacked','WordDecoded','RawByteDecoded','NarrowOK')),(0x99,99,0x12345,12345,99,True))
        write('ByteDecimal',127);write('WordDecimal',32767);write('RawByteBCD',0x7f);row=step()
        self.assertEqual((row['ByteDecoded'],row['WordDecoded'],row['RawByteDecoded']),(127,32767,85))
        write('Enable',False);write('ByteDecimal',99);write('RawByteBCD',0x128);row=step();self.assertEqual((row['ByteDecoded'],row['RawByteDecoded']),(127,85))
        before=write('Enable',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('RawByteBCD',0x127);row=step();self.assertEqual((row['ByteDecoded'],row['RawByteDecoded']),(99,127))
        write('ByteDecimal',100);before=write('WordDecimal',-1)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('WordDecimal',9999);row=step();self.assertEqual((row['ByteDecoded'],row['WordDecoded'],row['NarrowOK']),(100,9999,True))
        report=self.post('report',{})['numeric_conversions'];self.assertEqual(report['rll_operands']['TOD']['sources'],['SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT']);self.assertFalse(report['native_math_status'])

    def test_data_lab_numeric_fill_conversions_lazy_indices_and_retry_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'DataLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        write('FillNumeric',True);row=step()
        self.assertEqual(tuple(row[t] for t in ('ByteFill[1]','WordFill[2]','SignedFill[3]','RealFill[1]','ByteFill[0]','ByteFill[4]')),(120,22136,-1,2,101,99))
        write('FillNumeric',False);write('FillIndex',999);self.assertEqual(step()['ByteFill[1]'],120)
        before=write('FillNumeric',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FillIndex',1);write('FillSource',128);row=step();self.assertEqual((row['ByteFill[1]'],row['WordFill[1]']),(-128,128))
        write('FillSource',42);before=write('FillReal',32767.5)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FillReal',32766.5);row=step();self.assertEqual((row['ByteFill[1]'],row['WordFill[1]'],row['RealFill[1]']),(42,42,32766))
        report=self.post('report',{})['numeric_fill'];self.assertTrue(report['available']);self.assertFalse(report['clipping']);self.assertFalse(report['native_runtime_parity'])

    def test_data_lab_size_truncate_and_recovery_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'DataLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        write('InspectData',True);row=step()
        self.assertEqual(tuple(row[t] for t in ('SizeResult','StringCapacity','TruncatedWide','TruncatedUnsigned')),(3.0,82,'2',2))
        write('InspectData',False);write('FillReal',-3.9);self.assertEqual(step()['TruncatedWide'],'2')
        before=write('InspectData',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FillReal',16777217);row=step()
        self.assertEqual((row['TruncatedWide'],row['TruncatedUnsigned']),('16777216',16777216))
        report=self.post('report',{})['size_truncate'];self.assertTrue(report['available']);self.assertIn('ULINT',report['trn_destinations']);self.assertFalse(report['native_runtime_parity'])

    def test_data_lab_numeric_comparisons_skip_false_indices_and_retry_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'DataLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        write('CompareEnable',True);row=step()
        self.assertTrue(all(row[t] for t in ('MaskedMatch','InRange','CompareEqual')))
        write('CompareValues[0]',4661);row=step();self.assertTrue(row['MaskedMatch']);self.assertFalse(row['CompareEqual'])
        write('CompareEnable',False);write('CompareIndex',999);row=step()
        self.assertFalse(any(row[t] for t in ('MaskedMatch','InRange','CompareEqual')))
        before=write('CompareEnable',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('CompareIndex',0);write('CompareValues[0]',5001);row=step();self.assertFalse(row['InRange'])
        report=self.post('report',{})['numeric_comparisons'];self.assertEqual(len(report['instructions']),8);self.assertFalse(report['native_runtime_parity'])

    def test_imported_unknown_numeric_comparisons_are_lazy_and_atomic_through_http(self):
        import base64
        from test_numeric_comparisons import NumericComparisonTests
        fixture=NumericComparisonTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)MEQ(Values[Index],0,0)OTE(RunLatch);','XIC(StartPB)LIM(0,Values[1],10)OTE(BatchComplete);'])
            raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownComparisons.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'Index','value':0});self.post('write',{'tag':'StartPB','value':True})
        def state():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Values[0]',123),('Values[1]',5)):
            before=state()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            after=state()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertTrue(row['RunLatch']);self.assertTrue(row['BatchComplete'])

    def test_bit_lab_contacts_latches_and_edges_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        row=step();self.assertFalse(row['LogicOutput']);self.assertTrue(row['LogicInverse'])
        write('LogicInput',True);row=step()
        self.assertTrue(all(row[t] for t in ('LogicOutput','LogicLatched','OneShotPulse','RisePulse')));self.assertFalse(row['FallPulse'])
        row=step();self.assertFalse(row['OneShotPulse']);self.assertFalse(row['RisePulse'])
        write('LogicInput',False);row=step();self.assertTrue(row['FallPulse']);self.assertTrue(row['LogicLatched'])
        write('LogicReset',True);self.assertFalse(step()['LogicLatched'])
        write('LogicReset',False);write('LogicInput',True);before=write('FaultDivisor',0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FaultDivisor',1);row=step();self.assertTrue(row['OneShotPulse']);self.assertTrue(row['RisePulse'])
        report=self.post('report',{})['bit_logic'];self.assertTrue(report['available']);self.assertEqual(len(report['instructions']),8);self.assertFalse(report['native_runtime_parity'])

    def test_unknown_bool_members_and_oneshot_history_recover_through_http(self):
        import base64
        from test_bit_logic import BitLogicTests
        fixture=BitLogicTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)XIC(State.Contact)OTE(State.Output);','XIC(StartPB)OTL(State.Latch);','XIC(StartPB)ONS(Flags[Index])OTE(State.Pulse);'])
            raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownBitLogic.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.assertIsNone(next(row['value'] for row in state['tags'] if row['name']=='State.Output'))
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        before=current()
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'State.Contact','value':True});row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertTrue(row['State.Output']);self.assertTrue(row['State.Latch']);self.assertTrue(row['State.Pulse'])
        self.post('write',{'tag':'Index','value':1});before=current()
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'StartPB','value':False});row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertFalse(row['Flags[1]']);self.assertTrue(row['State.Latch'])
        self.post('write',{'tag':'StartPB','value':True});row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']};self.assertTrue(row['State.Pulse'])

    def test_data_lab_numeric_moves_clear_and_range_recovery_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'DataLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertEqual(step()['ClearValue'],'99');write('MoveNumeric',True);row=step()
        self.assertEqual(tuple(row[t] for t in ('MoveByte','MoveWord','MoveUnsigned','MoveRounded','MoveRealResult','ClearValue','ByteFill[1]')),(120,22136,'18446744073709551615',2,2.5,'0',120))
        write('MoveNumeric',False);write('FillIndex',999);write('MoveSource',42);self.assertEqual(step()['MoveByte'],120)
        before=write('MoveNumeric',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('FillIndex',1);row=step();self.assertEqual((row['MoveByte'],row['ByteFill[1]']),(42,42))
        before=write('MoveReal',2147483648.0)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('MoveReal',3.5);row=step();self.assertEqual((row['MoveRounded'],row['ByteFill[0]'],row['ByteFill[4]']),(4,101,99))
        report=self.post('report',{})['numeric_storage'];self.assertEqual(len(report['types']),9);self.assertFalse(report['native_math_status'])

    def test_imported_unknown_numeric_move_and_clear_recover_through_http(self):
        import base64
        from test_numeric_storage import NumericStorageTests
        fixture=NumericStorageTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)MOV(Inputs[Index],Results[Index]);','XIC(StartPB)CLR(Results[2]);']);raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownNumericStorage.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});before=self.post('write',{'tag':'StartPB','value':True})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'Inputs[0]','value':4660});row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(52,None,0))
        self.post('write',{'tag':'StartPB','value':False});self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10})
        self.post('write',{'tag':'Index','value':1});self.post('write',{'tag':'Inputs[1]','value':-1});self.post('write',{'tag':'StartPB','value':True})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']};self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(52,-1,0))

    def test_math_lab_basic_arithmetic_bitwise_and_fault_recovery_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'MathLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        step();write('BasicMath',True);row=step()
        names=('BasicSum','BasicDifference','BasicProduct','BasicQuotient','BasicRemainder','BasicNegative','BasicAbsolute','BasicAnd','BasicOr','BasicXor','BasicNot')
        self.assertEqual(tuple(row[t] for t in names),(10,4,21,2,1,-7,7,3,7,4,-8))
        write('BasicMath',False);write('BasicB',0);self.assertEqual(step()['BasicSum'],10)
        before=write('BasicMath',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('BasicB',3);self.assertEqual(step()['BasicQuotient'],2)
        write('BasicA',2147483647);before=write('BasicB',1)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('BasicA',7);write('BasicB',3);self.assertEqual(step()['BasicSum'],10)
        report=self.post('report',{})['scalar_math'];self.assertEqual(len(report['instructions']),11);self.assertFalse(report['native_runtime_parity'])

    def test_imported_unknown_scalar_math_is_lazy_and_atomic_through_http(self):
        import base64
        from test_scalar_math import ScalarMathTests
        fixture=ScalarMathTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)ADD(Inputs[Index],Mask,Results[Index]);','XIC(StartPB)NOT(Inputs[Index],Results[2]);','XIC(StartPB)DIV(Source,Inputs[2],SpeedCommand);']);raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownScalarMath.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Inputs[0]',7),('Inputs[2]',2)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close();after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']};self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(10,None,-8))
        self.post('write',{'tag':'StartPB','value':False});self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10})
        self.post('write',{'tag':'Index','value':1});self.post('write',{'tag':'Inputs[1]','value':100});self.post('write',{'tag':'StartPB','value':True})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']};self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(10,103,-101))

    def test_math_lab_real_modulo_sign_rounding_zero_and_recovery_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'MathLab'})['blockers'],[])
        def step():return {row['name']:row['value'] for row in self.post('step',{'dt':10})['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        self.assertEqual(step()['ModuloResult'],0.0);write('RealModulo',True);row=step()
        self.assertEqual((row['ModuloResult'],row['ModuloRounded']),(-1.5,-2))
        write('ModuloA',7.5);write('ModuloB',-2);row=step()
        self.assertEqual((row['ModuloResult'],row['ModuloRounded']),(1.5,2))
        write('RealModulo',False);write('ModuloB',0);self.assertEqual(step()['ModuloResult'],1.5)
        before=write('RealModulo',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('ModuloB',4);row=step();self.assertEqual((row['ModuloResult'],row['ModuloRounded']),(3.5,4))
        report=self.post('report',{})['scalar_math']['real_remainder'];self.assertFalse(report['native_precision'])

    def test_imported_unknown_real_modulo_and_late_failure_are_atomic_through_http(self):
        import base64
        from test_real_remainder import RealRemainderTests
        fixture=RealRemainderTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)MOD(Inputs[Index],Mask,Results[Index]);','XIC(StartPB)DIV(Source,Inputs[2],SpeedCommand);']);raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownRealModulo.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Inputs[0]',-7.5),('Inputs[2]',2)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close();after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(-1.5,None,None))
        self.post('write',{'tag':'StartPB','value':False});self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10})

    def test_bit_lab_real_bitwise_converts_rounds_and_rolls_back_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        names=('RealBitAnd','RealBitOr','RealBitXor','RealBitNot')

        def step_values():
            state=self.post('step',{'dt':10})
            tags={row['name']:row['value'] for row in state['tags']}
            return tuple(tags[name] for name in names)

        self.assertEqual(step_values(),(-99,-99,-99,-99))
        self.post('write',{'tag':'RealBitwise','value':True})
        self.assertEqual(step_values(),(4,5.0,2,-5.0))
        self.post('write',{'tag':'RealBitInput','value':2147483648.0})
        with self.assertRaises(HTTPError) as caught:
            step_values()
        self.assertEqual(caught.exception.code,400)
        self.assertIn(b'DINT overflow',caught.exception.read())
        caught.exception.close()
        self.post('write',{'tag':'RealBitwise','value':False})
        self.assertEqual(step_values(),(4,5.0,2,-5.0))
        self.post('write',{'tag':'RealBitInput','value':-1.5})
        self.post('write',{'tag':'RealBitwise','value':True})
        self.assertEqual(step_values(),(6,-1.0,-8,1.0))

    def test_bit_lab_plain_wide_masks_and_late_fault_recovery_through_http(self):
        self.assertEqual(self.post('demo', {'sample':'BitLab'})['blockers'], [])
        def write(tag, value):
            return self.post('write', {'tag':tag, 'value':value})
        def step():
            return self.post('step', {'dt':10})
        def results(state):
            values = {row['name']:row['value'] for row in state['tags']}
            return tuple(values['WideMask'+name] for name in ('And','Or','Xor','Not','Matches'))
        def state():
            request = Request(self.url+'/api/state', headers={'X-Logix-Token':self.token})
            with urlopen(request, timeout=3) as response:
                return json.load(response)
        self.assertEqual(results(step()), ('0','0','0','0',False))
        write('WideMaskEnabled', True)
        self.assertEqual(results(step()), ('1','9223372043297226753','9223372045444710398','18446744069414584320',True))
        write('WideMaskInput', '9223372041149743106')
        write('WideMaskDivisor', 0)
        before = state()
        with self.assertRaises(HTTPError) as error:
            step()
        with error.exception as failure:
            self.assertEqual(failure.code, 400)
            self.assertIn('zero', failure.read().decode().lower())
        after = state()
        for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):
            self.assertEqual(after[key], before[key], key)
        write('WideMaskDivisor', 1)
        self.assertEqual(results(step()), ('2','9223372043297226754','9223372045444710397','18446744069414584320',False))
        report = self.post('report', {})['scalar_math']['mixed_integer_immediates']
        self.assertEqual(report['width'], 32)
        self.assertFalse(report['native_runtime_parity'])

    def test_bit_lab_mixed_floating_bitwise_preserves_unsigned_results_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        names=('MixedFloatOr','MixedFloatXor','MixedFloatAnd','MixedFloatNot')

        def write(tag,value):
            self.post('write',{'tag':tag,'value':value})

        def step_values():
            state=self.post('step',{'dt':10})
            tags={row['name']:row['value'] for row in state['tags']}
            return tuple(tags[name] for name in names)

        self.assertEqual(step_values(),('0','0',0,'0'))
        write('MixedFloatBitwise',True)
        baseline=('9223372041149743102','18446744069414584321',4294967294,'1')
        self.assertEqual(step_values(),baseline)
        write('MixedFloatInput',2.5)
        write('MixedFloatLrealInput',float(1 << 63))
        with self.assertRaises(HTTPError) as caught:
            step_values()
        self.assertEqual(caught.exception.code,400)
        self.assertIn(b'LINT overflow',caught.exception.read())
        caught.exception.close()
        write('MixedFloatBitwise',False)
        self.assertEqual(step_values(),baseline)
        write('MixedFloatLrealInput',0.5)
        write('MixedFloatBitwise',True)
        self.assertEqual(step_values(),('9223372036854775810','18446744073709551613',2,'18446744073709551615'))

    def test_bit_lab_lreal_bitwise_preserves_lint_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        names=('LrealBitAnd','LrealBitOr','LrealBitXor','LrealBitNot')

        def step_values():
            state=self.post('step',{'dt':10})
            tags={row['name']:row['value'] for row in state['tags']}
            return tuple(tags[name] for name in names)

        self.assertEqual(step_values(),('-99','-99','-99',-99.0))
        self.post('write',{'tag':'LrealBitwise','value':True})
        self.assertEqual(step_values(),('9007199254740992','9007199254740993','9007199254740996',-9007199254740992.0))
        self.post('write',{'tag':'LrealBitInput','value':float(1 << 63)})
        with self.assertRaises(HTTPError) as caught:
            step_values()
        self.assertEqual(caught.exception.code,400)
        self.assertIn(b'LINT overflow',caught.exception.read())
        caught.exception.close()
        self.post('write',{'tag':'LrealBitInput','value':-1.5})
        self.assertEqual(step_values(),('9007199254740992','-1','-6',1.0))

    def test_bit_lab_declared_width_bitwise_results_and_false_retention_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        def step():return {row['name']:row['value'] for row in self.post('step',{'dt':10})['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        self.assertEqual(step()['NotWidened'],0);write('BitwiseWidths',True);row=step()
        names=('AndWidths','OrWidths','XorWidths','NotWidened','NotNarrowed')
        self.assertEqual(tuple(row[t] for t in names),(0,131071,65791,-256,-1))
        write('BitwiseWidths',False);write('LogicByte',0);write('LogicWord',0);write('LogicDword',255)
        row=step();self.assertEqual(tuple(row[t] for t in names),(0,131071,65791,-256,-1))
        write('BitwiseWidths',True);row=step();self.assertEqual(tuple(row[t] for t in names),(0,255,255,-1,0))
        report=self.post('report',{})['scalar_math']['bitwise'];self.assertEqual(report['types'],['SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT']);self.assertFalse(report['native_precision'])

    def test_imported_unknown_bitwise_widths_and_late_failure_are_atomic_through_http(self):
        import base64
        from test_scalar_bitwise import ScalarBitwiseTests
        fixture=ScalarBitwiseTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)OR(Inputs[Index],Mask,Results[Index]);','XIC(StartPB)NOT(Source,Results[2]);','XIC(StartPB)DIV(1,Inputs[2],SpeedCommand);']);raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownBitwiseWidths.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Inputs[0]',-1),('Inputs[2]',1)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close();after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(511,None,-256))
        self.post('write',{'tag':'StartPB','value':False});self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10})

    def test_math_lab_indexed_operands_skip_false_indices_and_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'MathLab'})['blockers'],[])
        def step():return {row['name']:row['value'] for row in self.post('step',{'dt':10})['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        row=step();self.assertIsNone(row['IndexedRoots[1]']);self.assertEqual(row['MathIndex'],99)
        before=write('IndexedMath',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('MathIndex',1);row=step();self.assertEqual((row['IndexedRoots[1]'],row['IndexedPowers[1]']),(3.0,81.0))
        self.assertIsNone(row['IndexedRoots[0]']);write('IndexedMath',False);write('MathIndex',999);row=step()
        self.assertEqual((row['IndexedRoots[1]'],row['IndexedPowers[1]']),(3.0,81.0))
        write('MathIndex',0);write('IndexedMath',True);row=step()
        self.assertEqual((row['IndexedRoots[0]'],row['IndexedPowers[0]']),(4.0,256.0))
        before=write('IndexedInputs[0]',1e20)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('IndexedInputs[0]',25);row=step();self.assertEqual((row['IndexedRoots[0]'],row['IndexedPowers[0]']),(5.0,625.0))
        report=self.post('report',{})['real_math'];self.assertIn('no live indices',report['validation']);self.assertFalse(report['native_math_status'])

    def test_imported_unknown_math_index_and_late_failure_are_atomic_through_http(self):
        import base64
        from test_math_operands import MathOperandTests
        fixture=MathOperandTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)SQR(Inputs[Index],Results[Index]);','XIC(StartPB)DIV(1,Inputs[2],SpeedCommand);'],index=None);raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownMathIndex.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Index',1),('Inputs[1]',-16),('Inputs[2]',1)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close();after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(None,4.0,None))
        self.post('write',{'tag':'StartPB','value':False});self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10})

    def test_bit_lab_indexed_transfers_skip_false_indices_and_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        def step():return {row['name']:row['value'] for row in self.post('step',{'dt':10})['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        row=step();self.assertEqual(row['TransferIndex'],99);self.assertIsNone(row['TransferMoved[0]'])
        before=write('IndexedTransfers',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('TransferIndex',0);row=step();self.assertEqual((row['TransferMoved[0]'],row['TransferBits[0]']),(305419896,13398))
        self.assertIsNone(row['TransferMoved[1]']);write('IndexedTransfers',False);write('TransferIndex',999);row=step()
        self.assertEqual((row['TransferMoved[0]'],row['TransferBits[0]']),(305419896,13398))
        write('TransferIndex',2);write('IndexedTransfers',True);row=step()
        self.assertEqual((row['TransferMoved[2]'],row['TransferBits[2]']),(-1,-1));self.assertIsNone(row['TransferMoved[1]'])
        report=self.post('report',{})['bit_transfer'];self.assertIn('5580',report['preflight']);self.assertFalse(report['native_math_status'])

    def test_imported_unknown_bit_transfer_indices_masks_and_late_failure_are_atomic_through_http(self):
        import base64
        from test_bit_transfer_operands import BitTransferOperandTests
        fixture=BitTransferOperandTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)MVM(Inputs[Index],Masks[Index],Results[Index]);','XIC(StartPB)BTD(Inputs[Index],0,Results[Index],8,8);','XIC(StartPB)DIV(1,Inputs[2],SpeedCommand);'],index=None);raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownBitTransferOperands.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Index',1),('Masks[1]',-1),('Inputs[1]',4660),('Inputs[2]',1)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close();after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(None,13364,None))
        self.post('write',{'tag':'StartPB','value':False});self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10})

    def test_conversion_lab_indexed_operands_skip_false_indices_and_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'ConversionLab'})['blockers'],[])
        def step():return {row['name']:row['value'] for row in self.post('step',{'dt':10})['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        row=step();self.assertEqual(row['ConversionIndex'],99);self.assertIsNone(row['IndexedPacked[0]'])
        before=write('IndexedConversions',True)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('ConversionIndex',0);row=step();self.assertEqual((row['IndexedPacked[0]'],row['IndexedDecoded[0]'],row['IndexedSwapped[0]']),(4660,1234,305397760))
        self.assertIsNone(row['IndexedPacked[1]']);write('IndexedConversions',False);write('ConversionIndex',999);row=step()
        self.assertEqual(row['IndexedDecoded[0]'],1234)
        write('ConversionIndex',2);write('IndexedConversions',True);row=step()
        self.assertEqual((row['IndexedPacked[2]'],row['IndexedDecoded[2]'],row['IndexedSwapped[2]']),(-2147483648,80000000,32768))
        before=write('IndexedDecimal[2]',100000000)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close();after=current()
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('IndexedDecimal[2]',99);row=step();self.assertEqual((row['IndexedPacked[2]'],row['IndexedDecoded[2]'],row['IndexedSwapped[2]']),(153,99,10027008))
        report=self.post('report',{})['numeric_conversions'];self.assertIn('no saved dynamic indices',report['preflight']);self.assertFalse(report['native_math_status'])

    def test_imported_unknown_conversion_indices_and_late_failure_are_atomic_through_http(self):
        import base64
        from test_conversion_operands import ConversionOperandTests
        fixture=ConversionOperandTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)TOD(Inputs[Index],Results[Index]);','XIC(StartPB)FRD(Results[Index],Results[2]);','XIC(StartPB)SWPB(Results[Index],WORD,Results[0]);','XIC(StartPB)DIV(1,Inputs[2],SpeedCommand);'],index=None);raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownConversionOperands.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Index',1),('Inputs[1]',1234),('Inputs[2]',1)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close();after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(305397760,4660,1234))
        self.post('write',{'tag':'StartPB','value':False});self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10})

    def test_bit_lab_mixed_integer_tags_preserve_exact_values_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        def step():return {row['name']:row['value'] for row in self.post('step',{'dt':10})['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        self.assertEqual(step()['MixedOr'],'0');write('MixedBitwise',True);row=step()
        names=('MixedAnd','MixedOr','MixedXor','MixedNot','MixedLow')
        self.assertEqual(tuple(row[t] for t in names),(0,'9007199254741247','-65537','18446744073709551360',255))
        write('MixedBitwise',False);write('MixedSmall',0);write('MixedDwordMask',1)
        write('MixedWide','9007199254740994');write('MixedSigned','-9223372036854775808')
        row=step();self.assertEqual(tuple(row[t] for t in names),(0,'9007199254741247','-65537','18446744073709551360',255))
        write('MixedBitwise',True);row=step()
        self.assertEqual(tuple(row[t] for t in names),(0,'9007199254740994','-9223372036854775807','18446744073709551615',0))
        report=self.post('report',{})['scalar_math']['bitwise'];self.assertEqual(len(report['types']),8);self.assertFalse(report['native_precision'])

    def test_imported_mixed_bitwise_unknowns_and_late_failure_are_atomic_through_http(self):
        import base64
        from test_mixed_bitwise import MixedBitwiseTests
        fixture=MixedBitwiseTests();fixture.setUp()
        try:
            engine=fixture.checked(['XIC(StartPB)OR(Inputs[Index],Mask,Results[Index]);','XIC(StartPB)NOT(Source,Results[2]);','XIC(StartPB)DIV(1,LateValues[0],SpeedCommand);']);raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'MixedBitwiseUnknowns.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Index',1),('Inputs[1]',2147483649),('LateValues[0]',1)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close();after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual((row['Results[0]'],row['Results[1]'],row['Results[2]']),(None,'2147483903','18446744071562067966'))
        self.post('write',{'tag':'StartPB','value':False});self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10})

    def test_data_lab_mixed_integer_meq_preserves_exact_inputs_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'DataLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        row=step();self.assertFalse(any(row[t] for t in ('MixedMaskMatch','MixedExactMatch','MixedWidthMatch')))
        write('MixedCompare',True);row=step()
        self.assertEqual((row['MixedMaskMatch'],row['MixedExactMatch'],row['MixedWidthMatch']),(True,False,False))
        self.assertEqual((row['MixedSmall'],row['MixedMask'],row['MixedExact'],row['MixedFullMask']),(-1,'65536','9007199254740993','-1'))
        write('MixedExpectedExact','9007199254740993');write('MixedExpected','4294967295');row=step()
        self.assertEqual((row['MixedMaskMatch'],row['MixedExactMatch'],row['MixedWidthMatch']),(False,True,True))
        write('MixedCompare',False);row=step();self.assertFalse(any(row[t] for t in ('MixedMaskMatch','MixedExactMatch','MixedWidthMatch')))
        report=self.post('report',{})['numeric_comparisons'];self.assertTrue(report['meq_mixed_integer_tags']);self.assertEqual(len(report['meq_types']),8);self.assertFalse(report['native_runtime_parity'])

    def test_imported_mixed_meq_unknowns_zero_mask_and_late_failure_are_atomic_through_http(self):
        import base64
        from test_mixed_meq import MixedMeqTests
        fixture=MixedMeqTests();fixture.setUp()
        try:
            def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
            engine=fixture.checked(['XIC(StartPB)MEQ(Values[Index],Mask,Dest)OTE(RunLatch);','XIC(StartPB)DIV(1,SpeedCommand,SpeedCommand);'],types=('ULINT','USINT','DINT'),values=(7,0,7),mutate=constant)
            raw=engine.project.path.read_bytes()
        finally:fixture.doCleanups()
        state=self.post('load',{'name':'UnknownMixedMEQ.L5X','content':base64.b64encode(raw).decode()});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True});self.post('write',{'tag':'SpeedCommand','value':0})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Index',0),('Values[0]','9007199254740993'),('SpeedCommand',1)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertTrue(row['RunLatch']);self.assertEqual(row['Values[0]'],'9007199254740993');self.assertEqual(row['Dest'],7)

    def test_conversion_lab_wide_bcd_exact_values_capacity_and_retry_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'ConversionLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return values(self.post('step',{'dt':10}))
        row=step();self.assertEqual(row['WidePacked'],'0');self.assertFalse(row['WideOK'])
        write('WideConversions',True);row=step()
        self.assertEqual(row['WidePacked'],'10378291982571407763');self.assertEqual(row['SignedPacked'],'-8068452091138143853')
        self.assertEqual((row['WideDecoded'],row['SignedDecoded'],row['WideWeighted']),('9007199254740993','9007199254740993','16666666666666665'))
        self.assertEqual(row['UnsignedPacked'],2576980377);self.assertTrue(row['WideOK'])
        before=write('WideDecimal','10000000000000000')
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
        write('WideDecimal','9999999999999999');row=step();self.assertEqual(row['WideDecoded'],'9999999999999999');self.assertEqual(row['WidePacked'],'11068046444225730969')
        write('WideConversions',False);write('WideDecimal','10000000000000000');row=step();self.assertEqual(row['WidePacked'],'11068046444225730969');self.assertFalse(row['WideOK'])
        report=self.post('report',{})['numeric_conversions'];self.assertEqual(report['rll_operands']['FRD']['sources'],['SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT']);self.assertFalse(report['native_runtime_parity'])

    def test_imported_wide_bcd_unknown_results_indices_and_late_fault_are_atomic_through_http(self):
        import base64
        from test_wide_bcd import WideBCDTests
        f=WideBCDTests();f.setUp()
        try:
            engine=f.checked(['XIC(StartPB)TOD(Inputs[Index],Results[Index]);','XIC(StartPB)FRD(Results[Index],Decoded[Index]);','XIC(StartPB)DIV(1,SpeedCommand,SpeedCommand);'])
            raw=engine.project.path.read_bytes()
        finally:f.doCleanups()
        self.assertEqual(self.post('load',{'name':'UnknownWideBCD.L5X','content':base64.b64encode(raw).decode()})['blockers'],[])
        self.post('write',{'tag':'Index','value':999});self.post('step',{'dt':10});self.post('write',{'tag':'StartPB','value':True});self.post('write',{'tag':'SpeedCommand','value':0})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        for tag,value in (('Index',1),('Inputs[1]','9007199254740993'),('SpeedCommand',1)):
            before=current()
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);error.exception.close()
            after=current()
            for key in ('tags','scan','ms','task_schedule'):self.assertEqual(after[key],before[key])
            self.post('write',{'tag':tag,'value':value})
        row={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertEqual(row['Decoded[1]'],'9007199254740993');self.assertIsNone(row['Results[0]']);self.assertIsNone(row['Decoded[2]'])

    def test_logic_view_assets_are_served_with_graph_modules_before_app_and_no_state_changes(self):
        page=self.get('/').decode('utf8')
        self.assertLess(page.index('src="/ladder-graph.js"'),page.index('src="/logic-view.js"'))
        self.assertLess(page.index('src="/instruction-view.js"'),page.index('src="/logic-view.js"'))
        self.assertLess(page.index('src="/logic-values.js"'),page.index('src="/logic-view.js"'))
        self.assertLess(page.index('src="/logic-view.js"'),page.index('src="/app.js"'))
        self.assertIn('id="instruction-inspector"',page);self.assertIn('id="logic-fit"',page)
        self.assertIn('Read-only monitor',page)
        self.post('demo',{'sample':'ConveyorDemo'})
        def current():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:return json.load(response)
        before=current()
        for name in ('ladder-graph.js','instruction-view.js','logic-values.js','logic-view.js','logic-view.css'):
            self.assertEqual(self.get('/'+name),(Path(__file__).resolve().parents[1]/'web'/name).read_bytes())
        after=current()
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits'):self.assertEqual(after[key],before[key])
        with self.assertRaises(HTTPError) as error:self.get('/web/logic-view.js')
        self.assertEqual(error.exception.code,404);error.exception.close()

    def test_logic_view_aoi_bindings_expose_canonical_tag_references_without_writes(self):
        state=self.post('demo',{'sample':'AOIQueueLab'})
        bindings={name.lower():value for name,value in state['aoi_bindings'].items()}
        self.assertEqual(bindings['drivera']['buffer'],'BufferA')
        self.assertEqual(bindings['driverb']['buffer'],'BufferB')
        self.assertEqual(bindings['drivera']['value'],'DriverA.Value')
        self.assertTrue(all(isinstance(ref,str) and not ref.startswith('@') for fields in bindings.values() for ref in fields.values()))
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','aoi_bindings','routine_edits'):self.assertEqual(after[key],state[key])

    def test_logic_view_aoi_definitions_preserve_parameter_metadata_without_writes(self):
        state=self.post('demo',{'sample':'AOIQueueLab'})
        definition=state['aoi_definitions']['LABQUEUEDRIVER']
        self.assertEqual(definition['name'],'LabQueueDriver')
        parameters=definition['parameters']
        self.assertEqual([p['name'] for p in parameters[:4]],['EnableIn','EnableOut','Load','Unload'])
        buffer=next(p for p in parameters if p['name']=='Buffer')
        self.assertEqual((buffer['type'],buffer['usage'],buffer['dimensions']),('DINT','InOut','6'))
        self.assertTrue(buffer['visible']);self.assertTrue(buffer['required'])
        popped=next(p for p in parameters if p['name']=='Popped')
        self.assertFalse(popped['visible']);self.assertFalse(popped['required'])
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','aoi_definitions','aoi_bindings','routine_edits'):self.assertEqual(after[key],state[key])

    def test_integer_lab_widening_arithmetic_and_atomic_failure_through_http(self):
        state=self.post('demo',{'sample':'IntegerLab'});self.assertEqual(state['blockers'],[])
        self.post('step',{'dt':10})
        self.post('write',{'tag':'MixedArithmetic','value':True})
        state=self.post('step',{'dt':10});row={r['name']:r['value'] for r in state['tags']}
        self.assertEqual({name:row[name] for name in ('MixedSum','MixedDifference','MixedProduct','MixedQuotient','MixedRemainder','MixedNegated','MixedAbs','MixedUnsignedDifference')},
                         dict(MixedSum='9007199254740995',MixedDifference='9007199254740990',MixedProduct='-21',MixedQuotient='3002399751580331',MixedRemainder='0',MixedNegated=-3,MixedAbs='7',MixedUnsignedDifference='18446744073709551611'))
        report=self.post('report',{})['scalar_math']['widening_arithmetic'];self.assertEqual(len(report['instructions']),7);self.assertFalse(report['native_runtime_parity'])
        before=self.post('write',{'tag':'NarrowDivisor','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'NarrowDivisor','value':3});state=self.post('step',{'dt':10});self.assertEqual(state['scan'],before['scan']+1)

    def test_integer_lab_arithmetic_constants_and_zero_divisor_rollback_through_http(self):
        state=self.post('demo',{'sample':'IntegerLab'});self.assertEqual(state['blockers'],[])
        self.post('write',{'tag':'ArithmeticConstants','value':True});state=self.post('step',{'dt':10})
        row={r['name']:r['value'] for r in state['tags']}
        wanted=dict(ConstantSum='-6',ConstantDifference='17',ConstantProduct='-21',ConstantQuotient='-2',ConstantRemainder='-1',ConstantUnsignedSum=4,ConstantReverseQuotient='-715827882',ConstantAbs='2147483648')
        self.assertEqual({name:row[name] for name in wanted},wanted);self.assertTrue(row['StAllMatches'])
        before=self.post('write',{'tag':'MixedSmall','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'MixedSmall','value':3});state=self.post('step',{'dt':10});self.assertEqual(state['scan'],before['scan']+1)

    def test_integer_lab_mixed_relations_exact_limits_and_gate_through_http(self):
        state=self.post('demo',{'sample':'IntegerLab'});self.assertEqual(state['blockers'],[])
        self.post('write',{'tag':'MixedRelations','value':True});state=self.post('step',{'dt':10});rows={r['name']:r['value'] for r in state['tags']}
        true=['RelationEqual','RelationNotEqual','RelationLess','RelationLessEqual','RelationGreater','RelationGreaterEqual','RelationInRange']
        self.assertTrue(all(rows[name] for name in true));self.assertFalse(rows['RelationExactLimit']);self.assertFalse(rows['RelationReversed'])
        self.assertEqual(rows['SignedInput'],'9007199254740993');self.assertEqual(rows['RelationHigh'],'9007199254740992')
        self.post('write',{'tag':'RelationHigh','value':'9007199254740993'});self.post('write',{'tag':'RelationTest','value':2})
        rows={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']};self.assertTrue(rows['RelationExactLimit']);self.assertTrue(rows['RelationReversed'])
        self.post('write',{'tag':'MixedRelations','value':False});rows={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertTrue(all(rows[name] is False for name in true+['RelationExactLimit','RelationReversed']))
        report=self.post('report',{})['numeric_comparisons']['mixed_integer_ordering'];self.assertEqual(len(report['instructions']),7);self.assertEqual(len(report['types']),8);self.assertFalse(report['native_runtime_parity'])

    def test_integer_lab_mixed_limit_constants_positions_and_endpoints_through_http(self):
        state=self.post('demo',{'sample':'IntegerLab'});self.assertEqual(state['blockers'],[])
        self.post('write',{'tag':'RelationConstants','value':True});state=self.post('step',{'dt':10});rows={r['name']:r['value'] for r in state['tags']}
        true=['LimitConstantLow','LimitConstantTest','LimitConstantHigh','LimitConstantMinimum','LimitConstantEndpoint','LimitConstantMaximum']
        self.assertTrue(all(rows[name] for name in true));self.assertFalse(rows['LimitConstantReversed']);self.assertFalse(rows['LimitConstantExact'])
        self.assertEqual(rows['SignedInput'],'9007199254740993');self.assertEqual(rows['RelationDword'],4294967295);self.assertTrue(rows['StAllMatches'])
        self.post('write',{'tag':'RelationTest','value':2});self.post('write',{'tag':'SignedInput','value':'65535'})
        rows={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']};self.assertTrue(rows['LimitConstantReversed']);self.assertTrue(rows['LimitConstantExact'])
        self.post('write',{'tag':'RelationConstants','value':False});rows={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertTrue(all(rows[name] is False for name in true+['LimitConstantReversed','LimitConstantExact']))
        report=self.post('report',{})['numeric_comparisons']['mixed_integer_ordering'];self.assertIn('signed-DINT',report['constants']);self.assertFalse(report['native_runtime_parity'])

    def test_integer_lab_mixed_cmp_boolean_composition_and_gate_through_http(self):
        state=self.post('demo',{'sample':'IntegerLab'});self.assertEqual(state['blockers'],[])
        self.post('write',{'tag':'MixedConditions','value':True});state=self.post('step',{'dt':10});rows={r['name']:r['value'] for r in state['tags']}
        true=['MixedConditionEqual','MixedConditionAnd','MixedConditionOr','MixedConditionNot','MixedConditionXor','MixedConditionWords']
        self.assertTrue(all(rows[name] for name in true));self.assertFalse(rows['MixedConditionGate']);self.assertFalse(rows['MixedConditionExact'])
        self.assertEqual(rows['SignedInput'],'9007199254740993');self.assertEqual(rows['RelationHigh'],'9007199254740992');self.assertTrue(rows['StAllMatches'])
        self.post('write',{'tag':'MixedRelations','value':True});self.post('write',{'tag':'RelationHigh','value':'9007199254740993'})
        rows={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']};self.assertTrue(rows['MixedConditionGate']);self.assertTrue(rows['MixedConditionExact'])
        self.post('write',{'tag':'MixedConditions','value':False});rows={r['name']:r['value'] for r in self.post('step',{'dt':10})['tags']}
        self.assertTrue(all(rows[name] is False for name in true+['MixedConditionGate','MixedConditionExact']))
        report=self.post('report',{})['wide_ladder_expressions']['mixed_integer_comparisons'];self.assertEqual(report['instructions'],['CMP']);self.assertEqual(len(report['types']),8);self.assertFalse(report['native_runtime_parity'])

    def test_indexed_calculations_unknown_inputs_rollback_and_recovery_through_http(self):
        state=self.post('demo',{'sample':'WideExpressionLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        state=self.post('step',{'dt':10});self.assertIsNone(values(state)['ExpressionResults[0]']);self.assertFalse(values(state)['ExpressionWideMatches'])
        for tag,value in [('ExpressionIndex',0),('ExpressionValues[0]','9007199254740993'),('ExecuteIndexed',True)]:state=self.post('write',{'tag':tag,'value':value})
        before=state
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);self.assertIn('Unknown',error.exception.read().decode());error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'ExpressionNarrow[0]','value':5});state=self.post('step',{'dt':10});row=values(state)
        self.assertEqual(row['ExpressionResults[0]'],'9007199254740995');self.assertEqual(row['ExpressionNarrowResults[0]'],6);self.assertTrue(row['ExpressionWideMatches']);self.assertTrue(row['ExpressionNarrowMatches'])
        self.assertIsNone(row['ExpressionResults[1]']);self.assertIsNone(row['ExpressionNarrowResults[2]']);self.assertEqual(row['ExpressionValues[0]'],'9007199254740993')
        self.post('write',{'tag':'ExecuteIndexed','value':False});self.post('write',{'tag':'ExpressionIndex','value':99});row=values(self.post('step',{'dt':10}))
        self.assertEqual(row['ExpressionResults[0]'],'9007199254740995');self.assertFalse(row['ExpressionWideMatches']);self.assertFalse(row['ExpressionNarrowMatches'])
        report=self.post('report',{})['integer_expression_execution']['ladder_selection'];self.assertEqual(report['instructions'],['CPT','CMP']);self.assertEqual(len(report['types']),9);self.assertFalse(report['native_runtime_parity'])

    def test_mixed_expression_math_exact_results_zero_divisor_and_gate_through_http(self):
        state=self.post('demo',{'sample':'WideExpressionLab'});self.assertEqual(state['blockers'],[])
        self.post('write',{'tag':'MixedExpressionMath','value':True});state=self.post('step',{'dt':10});values=lambda s:{r['name']:r['value'] for r in s['tags']};row=values(state)
        expected=dict(ExpressionSum='9007199254740996',ExpressionDifference='9007199254740990',ExpressionProduct='-14',ExpressionQuotient='-3074457345618258602',ExpressionRemainder='-2',ExpressionUnsigned='18446744073709551611',ExpressionAbsolute='14',ExpressionNested='4503599627370498')
        self.assertEqual({name:row[name] for name in expected},expected);self.assertTrue(row['MixedExpressionMatches']);self.assertEqual(row['ExpressionDelta'],3)
        before=self.post('write',{'tag':'ExpressionDelta','value':0})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);self.assertIn('zero',error.exception.read().decode());error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'ExpressionDelta','value':3});row=values(self.post('step',{'dt':10}));self.assertEqual({name:row[name] for name in expected},expected)
        self.post('write',{'tag':'MixedExpressionMath','value':False});self.post('write',{'tag':'ExpressionDelta','value':0});row=values(self.post('step',{'dt':10}));self.assertEqual({name:row[name] for name in expected},expected);self.assertFalse(row['MixedExpressionMatches'])
        report=self.post('report',{})['wide_ladder_expressions']['mixed_integer_arithmetic'];self.assertEqual(report['instructions'],['CPT','CMP']);self.assertEqual(len(report['types']),8);self.assertFalse(report['native_runtime_parity'])

    def test_string_lab_indexed_unknown_operands_gate_rollback_and_recovery_through_http(self):
        state=self.post('demo',{'sample':'StringLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        row=values(self.post('step',{'dt':10}));self.assertIsNone(row['IndexedJoined[0].LEN']);self.assertFalse(row['IndexedMatch'])
        for tag,value in [('StringIndex',0),('IndexedSource[0]','ABC STATE'),('IndexedStrings',True)]:self.post('write',{'tag':tag,'value':value})
        state=self.post('step',{'dt':10});row=values(state)
        for tag,wanted in [('IndexedJoined[0]','ABC STATE<OK>'),('IndexedSlice[0]','STATE'),('IndexedLower[0]','abc state<ok>'),('IndexedNumber[0]','5')]:
            self.assertEqual(row[tag+'.LEN'],len(wanted));self.assertEqual(row[tag],wanted)
        self.assertEqual(row['IndexedPosition[0]'],5);self.assertTrue(row['IndexedMatch']);self.assertIsNone(row['IndexedJoined[1].LEN']);self.assertIsNone(row['IndexedJoined[0].DATA[31]'])
        self.post('write',{'tag':'IndexedStrings','value':False});self.post('write',{'tag':'StringIndex','value':99});row=values(self.post('step',{'dt':10}));self.assertFalse(row['IndexedMatch']);self.assertEqual(row['IndexedJoined[0].LEN'],13)
        before=self.post('write',{'tag':'IndexedStrings','value':True})
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);self.assertIn('outside bounds',error.exception.read().decode());error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'StringIndex','value':0});row=values(self.post('step',{'dt':10}));self.assertTrue(row['IndexedMatch'])
        report=self.post('report',{})['string_operations']['operand_selection'];self.assertEqual(len(report['instructions']),18);self.assertFalse(report['native_runtime_parity'])

    def test_copy_lab_indexed_unknown_lengths_and_ladder_recovery_through_http(self):
        state=self.post('demo',{'sample':'CopyLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        row=values(self.post('step',{'dt':10}));self.assertIsNone(row['SelectedBytes[0]']);self.assertFalse(row['CopyMatches'])
        self.post('write',{'tag':'IndexedCopy','value':True})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        fault('Unknown');self.post('write',{'tag':'SelectedLength[0]','value':4});fault('outside bounds')
        for tag,value in [('CopyIndex',0),('OutputIndex',0)]:self.post('write',{'tag':tag,'value':value})
        fault('known integer');self.post('write',{'tag':'SelectedSource[0]','value':16909060});row=values(self.post('step',{'dt':10}))
        self.assertEqual([row[f'SelectedBytes[{i}]'] for i in range(4)],[4,3,2,1]);self.assertEqual(row['SelectedRoundtrip[0]'],16909060);self.assertTrue(row['CopyMatches']);self.assertIsNone(row['SelectedBytes[4]']);self.assertIsNone(row['SelectedRoundtrip[1]'])
        self.post('write',{'tag':'IndexedCopy','value':False});self.post('write',{'tag':'CopyIndex','value':99});row=values(self.post('step',{'dt':10}));self.assertEqual(row['SelectedRoundtrip[0]'],16909060);self.assertFalse(row['CopyMatches'])
        self.assertIn('Structural',self.post('report',{})['numeric_copy']['selection'])

    def test_counter_lab_ladder_unknown_initialization_resets_and_recovery_through_http(self):
        state=self.post('demo',{'sample':'CounterLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        row=values(step());self.assertIsNone(row['LadderCounts[0].ACC']);self.assertIsNone(row['ResetTimers[0].ACC'])
        write('LadderCounter',True);fault('COUNTER.ACC');write('ResetCount',True);row=values(step());self.assertEqual(row['LadderCounts[0].ACC'],0);self.assertEqual(row['LadderCounts[0].PRE'],3);write('ResetCount',False)
        for i in range(1,4):
            write('UpInput',True);row=values(step());self.assertEqual(row['LadderCounts[0].ACC'],i);write('UpInput',False);step()
        self.assertTrue(row['LadderDone']);write('DownInput',True);row=values(step());self.assertEqual(row['LadderCounts[0].ACC'],2);self.assertFalse(row['LadderDone'])
        write('ResetRecord',True);fault('outside bounds');write('ResetIndex',0);row=values(step())
        for name in ('ResetCounters','ResetTimers'):self.assertEqual(row[name+'[0].ACC'],0);self.assertIsNone(row[name+'[0].PRE']);self.assertFalse(row[name+'[0].DN']);self.assertIsNone(row[name+'[1].ACC'])
        report=self.post('report',{})['ladder_counters'];self.assertTrue(report['available']);self.assertFalse(report['native_runtime_parity'])

    def test_timer_lab_ladder_unknown_done_pause_off_delay_and_recovery_through_http(self):
        state=self.post('demo',{'sample':'TimerLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        row=values(step());self.assertEqual(row['LadderRetained.ACC'],7);self.assertIsNone(row['LadderRetained.DN'])
        write('LadderTimers',True);before=write('TimerEnable',True)
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);self.assertIn('TIMER.DN',error.exception.read().decode());error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        write('LadderReset',True);row=values(step());self.assertEqual(row['LadderRetained.ACC'],0);self.assertFalse(row['LadderRetained.DN']);write('LadderReset',False)
        for wanted in (10,20,30):row=values(step());self.assertEqual(row['LadderRetained.ACC'],wanted);self.assertEqual(row['LadderOn.ACC'],wanted)
        self.assertTrue(row['LadderOn.DN']);self.assertTrue(row['LadderRetained.DN']);self.assertFalse(row['LadderRetained.TT'])
        write('LadderRetained.PRE',100);write('LadderRetained.DN',False);row=values(step());self.assertEqual(row['LadderRetained.ACC'],40);write('LadderRetained.DN',True);step();row=values(step());self.assertEqual(row['LadderRetained.ACC'],40);self.assertFalse(row['LadderRetained.TT'])
        write('LadderRetained.DN',False);row=values(step());self.assertEqual(row['LadderRetained.ACC'],50);write('TimerEnable',False);row=values(step());self.assertEqual(row['LadderOn.ACC'],0);self.assertTrue(row['LadderOff.TT']);self.assertEqual(row['LadderOff.ACC'],0)
        for wanted in (10,20,30):row=values(step());self.assertEqual(row['LadderOff.ACC'],wanted)
        self.assertFalse(row['LadderOff.DN']);self.assertFalse(row['LadderOff.TT']);self.assertEqual(row['LadderRetained.ACC'],50)
        report=self.post('report',{})['ladder_timers'];self.assertTrue(report['available']);self.assertFalse(report['native_runtime_parity'])

    def test_data_lab_aggregate_fill_unknowns_typed_records_and_recovery_through_http(self):
        state=self.post('demo',{'sample':'DataLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        row=values(step());self.assertIsNone(row['ZeroRecords[1].Enabled']);self.assertIsNone(row['ZeroTimers[1].ACC']);write('FillAggregates',True);fault('Unknown');write('AggregateLength[0]',1);fault('outside bounds');write('AggregateIndex',1);fault('Unknown');write('AggregateSource[0]',0)
        row=values(step());self.assertIs(row['ZeroRecords[1].Enabled'],False);self.assertEqual(row['ZeroRecords[1].Count'],0);self.assertIs(type(row['ZeroRecords[1].Measure']),float);self.assertEqual(row['ZeroRecords[1].Measure'],0.0);self.assertIs(row['ZeroRecords[1].Timer.EN'],False);self.assertIs(row['ZeroRecords[1].Counter.CU'],False)
        self.assertEqual(row['ZeroTimers[1].ACC'],0);self.assertIs(row['ZeroTimers[1].EN'],False);self.assertIs(row['ZeroCounters[1].CU'],False);self.assertEqual(row['ZeroStrings[1]'],'');self.assertEqual(row['ZeroStrings[1].DATA[81]'],0);self.assertEqual((row['ZeroRecords[0].Count'],row['ZeroRecords[2].Count']),(111,999));self.assertIsNone(row['ZeroTimers[0].ACC'])
        write('FillAggregates',False);write('AggregateIndex',99);row=values(step());self.assertEqual(row['ZeroRecords[1].Count'],0);write('AggregateIndex',1);write('AggregateSource[0]',1);write('FillAggregates',True);fault('integer zero only');write('AggregateSource[0]',0);step()
        report=self.post('report',{})['aggregate_fill'];self.assertTrue(report['available']);self.assertFalse(report['native_runtime_parity'])

    def test_data_lab_matching_aggregate_copies_lazy_references_and_recovery_through_http(self):
        state=self.post('demo',{'sample':'DataLab'});self.assertEqual(state['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        row=values(step());self.assertIsNone(row['CopyRecords[1].Count']);self.assertIsNone(row['CopyTimers[1].ACC'])
        write('CopyAggregates',True);fault('Unknown');write('AggregateCopyLength[0]',1);fault('outside bounds');write('AggregateCopySourceIndex',1);fault('outside bounds');write('AggregateCopyDestIndex',1)
        row=values(step());self.assertIsNone(row['CopyRecords[1].Count']);self.assertIsNone(row['CopyTimers[1].EN'])
        write('AggregateIndex',1);write('AggregateLength[0]',1);write('AggregateSource[0]',0);write('FillAggregates',True);row=values(step())
        self.assertIs(row['CopyRecords[1].Enabled'],False);self.assertIs(type(row['CopyRecords[1].Measure']),float);self.assertIs(row['CopyTimers[1].EN'],False);self.assertEqual(row['CopyStrings[1]'],'')
        write('FillAggregates',False);write('ZeroRecords[1].Count',73);write('ZeroTimers[1].ACC',42);write('ZeroStrings[1].DATA[81]',77);row=values(step())
        self.assertEqual((row['CopyRecords[1].Count'],row['CopyTimers[1].ACC'],row['CopyStrings[1].DATA[81]']),(73,42,77));self.assertIsNone(row['CopyRecords[0].Count']);self.assertIsNone(row['CopyTimers[2].ACC']);self.assertEqual((row['ZeroRecords[0].Count'],row['ZeroRecords[2].Count']),(111,999))
        write('CopyAggregates',False);write('AggregateCopySourceIndex',99);write('AggregateCopyDestIndex',99);row=values(step());self.assertEqual(row['CopyRecords[1].Count'],73)
        write('CopyAggregates',True);fault('outside bounds');write('AggregateCopySourceIndex',1);write('AggregateCopyDestIndex',1);step()
        report=self.post('report',{})['aggregate_copy'];self.assertTrue(report['available']);self.assertFalse(report['native_runtime_parity'])

    def test_control_lab_lazy_payloads_and_control_reset_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'ControlLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        row=values(step());self.assertIsNone(row['ResetControls[1].POS']);write('IndexedShift',True);fault('outside bounds');write('PayloadIndex',1);fault('Unknown');write('PayloadBits[1]',True);row=values(step());self.assertEqual(row['IndexedBits[0]'],1)
        write('PayloadIndex',99);row=values(step());self.assertEqual(row['IndexedBits[0]'],1);write('IndexedShift',False);write('IndexedLoad',True);fault('outside bounds');write('PayloadIndex',1);write('PayloadValues[1]',67);row=values(step());self.assertEqual(row['IndexedQueue[0]'],67)
        write('PayloadIndex',99);row=values(step());self.assertEqual(row['IndexedQueueControl.POS'],1);write('IndexedLoad',False);write('IndexedUnload',True);fault('outside bounds');write('OutputIndex',1);row=values(step());self.assertEqual(row['UnloadedValues[1]'],67);self.assertIsNone(row['UnloadedValues[0]']);self.assertEqual(row['IndexedQueue[2]'],999)
        write('IndexedUnload',False);write('IndexedReset',True);fault('outside bounds');write('ResetControlIndex',1);row=values(step());self.assertIsNone(row['ResetControls[1].LEN']);self.assertEqual(row['ResetControls[1].POS'],0);self.assertIs(row['ResetControls[1].EN'],False);self.assertIs(row['ResetControls[1].FD'],False);self.assertIsNone(row['ResetControls[0].POS'])
        write('IndexedReset',False);write('ResetControlIndex',99);row=values(step());self.assertEqual(row['ResetControls[1].POS'],0)
        profile=self.post('report',{})['control_operations'];self.assertIn('payload',profile['skipped_references']);self.assertIn('CONTROL RES',profile['reset_selection'])

    def test_sequence_lab_lazy_masks_payloads_held_calls_and_recovery_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'SequenceLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        row=values(step());self.assertIsNone(row['IndexedOutputs[1]']);write('IndexedAdvance',True);fault('outside bounds');write('MaskIndex',1);fault('Unknown');write('Masks[1]',-1);fault('outside bounds');write('OutputIndex',1);row=values(step());self.assertEqual(row['IndexedOutputs[1]'],1)
        write('IndexedCompare',True);fault('outside bounds');write('SourceIndex',1);fault('Unknown');write('FeedbackInputs[1]',1);row=values(step());self.assertTrue(row['IndexedMatches']);write('IndexedTeach',True);fault('Unknown');write('TeachInputs[1]',67);row=values(step());self.assertEqual(row['IndexedLearned[1]'],67)
        write('IndexedPatterns[1]',4);write('FeedbackInputs[1]',4);write('TeachInputs[1]',77);row=values(step());self.assertEqual((row['IndexedOutputs[1]'],row['IndexedLearned[1]']),(4,77));self.assertEqual((row['IndexedSequenceControl.POS'],row['IndexedTeachControl.POS']),(1,1));self.assertTrue(row['IndexedMatches']);self.assertEqual((row['IndexedPatterns[3]'],row['IndexedLearned[0]'],row['IndexedLearned[3]']),(999,111,999))
        write('IndexedTeach',False);write('Masks[1]',0);write('OutputIndex',99);write('SourceIndex',99);row=values(step());self.assertEqual(row['IndexedOutputs[1]'],4);self.assertTrue(row['IndexedMatches']);write('Masks[1]',-1);fault('outside bounds');write('OutputIndex',1);fault('outside bounds');write('SourceIndex',1);step()
        profile=self.post('report',{})['sequencer_operations'];self.assertIn('Structural',profile['selection']);self.assertIn('table window',profile['zero_mask'])

    def test_stats_lab_indirect_unknown_results_latch_and_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'StatsLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        row=values(step());self.assertIsNone(row['IndexedMeans[1]']);write('IndexedStatistics',True);fault('outside bounds');write('StatisticsSourceIndex',1);fault('outside bounds');write('StatisticsResultIndex',1);fault('Unknown')
        for i,value in enumerate((2,4,6),1):write(f'SelectedSamples[{i}]',value)
        write('IndexedDeviationControl.LEN',1);fault('at least two');write('IndexedDeviationControl.LEN',3);row=values(step());self.assertEqual((row['IndexedMeans[1]'],row['IndexedDeviations[1]'],row['IndexedIntegerMeans[1]']),(4.0,2.0,4));self.assertIs(type(row['IndexedMeans[1]']),float);self.assertIs(type(row['IndexedIntegerMeans[1]']),int);self.assertIsNone(row['IndexedMeans[0]'])
        write('StatisticsSourceIndex',99);write('StatisticsResultIndex',99);row=values(step());self.assertEqual(row['IndexedMeans[1]'],4.0);write('IndexedStatistics',False);step();write('IndexedStatistics',True);fault('outside bounds');write('StatisticsSourceIndex',1);write('StatisticsResultIndex',2);write('SelectedSamples[1]',8);row=values(step());self.assertEqual((row['IndexedMeans[1]'],row['IndexedMeans[2]'],row['IndexedDeviations[2]'],row['IndexedIntegerMeans[2]']),(4.0,6.0,2.0,6));self.assertEqual((row['SelectedSamples[0]'],row['SelectedSamples[4]']),(111.0,999.0))
        profile=self.post('report',{})['array_statistics'];self.assertIn('result indices',profile['selection']);self.assertIn('unknown',profile['result_writes'])

    def test_call_lab_indirect_arguments_capture_return_addresses_and_recover_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'CallLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        row=values(step());self.assertIsNone(row['IndexedCallResults[1]']);write('IndirectCall',True);fault('outside bounds');write('CallInputIndex',1);fault('outside bounds');write('CallOutputIndex',1);fault('Unknown');write('IndexedCallInputs[1]',7);write('RedirectReturn',True);row=values(step());self.assertEqual(row['IndexedCallResults[1]'],14);self.assertEqual(row['CallOutputIndex'],2);self.assertIsNone(row['IndexedCallResults[2]'])
        write('IndirectCall',False);write('RedirectReturn',False);write('CallInputIndex',99);step();write('CallInputIndex',1);write('CallOutputIndex',2);write('IndexedCallInputs[1]',11);write('IndirectCall',True);row=values(step());self.assertEqual((row['IndexedCallResults[1]'],row['IndexedCallResults[2]']),(14,22));self.assertIsNone(row['IndexedCallResults[0]'])
        write('IndirectCall',False);write('IndirectPairCall',True);write('CallOutputIndex',1);write('IndexedPairInputs[1].A',23);row=values(step());self.assertEqual(row['IndexedPairResults[1].A'],23);self.assertIsNone(row['IndexedPairResults[1].B']);self.assertIsNone(row['IndexedPairResults[0].A']);write('IndexedPairInputs[1].A',31);write('IndirectPairCall',False);row=values(step());self.assertEqual(row['IndexedPairResults[1].A'],23)
        profile=self.post('report',{})['routine_parameters']['indirect'];self.assertTrue(profile['available']);self.assertIn('call entry',profile['capture']);self.assertFalse(profile['native_runtime_parity'])

    def test_loop_lab_indirect_operands_and_completed_prescan_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'LoopLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            before=self.post('report',{})
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:old=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:new=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(new[key],old[key])
            self.assertEqual(self.post('report',{})['ladder_loops'],before['ladder_loops'])
        row=values(step());self.assertIsNone(row['IndexSlots[1]']);write('SelectedLoop',True);fault('outside bounds');write('LoopSlot',1);fault('outside bounds');write('BoundsSlot',1);fault('Unknown')
        for tag,value in [('InitialValues[1]',0),('TerminalValues[1]',4),('StepValues[1]',1)]:write(tag,value)
        row=values(step());self.assertEqual((row['SelectedTotal'],row['SelectedIterations'],row['IndexSlots[1]']),(10,5,5));self.assertTrue(row['SelectedCompleted']);self.assertIsNone(row['IndexSlots[0]'])
        for tag,value in [('LoopSlot',2),('BoundsSlot',2),('InitialValues[2]',3),('TerminalValues[2]',-1),('StepValues[2]',-2)]:write(tag,value)
        row=values(step());self.assertEqual((row['SelectedTotal'],row['SelectedIterations'],row['IndexSlots[2]']),(3,3,-3));self.assertEqual(row['IndexSlots[1]'],5)
        write('FaultDivisor',0);fault('zero');write('FaultDivisor',1);write('SelectedLoop',False);write('LoopSlot',99);write('BoundsSlot',99);row=values(step());self.assertFalse(row['SelectedCompleted']);self.assertEqual(row['IndexSlots[2]'],-3)
        report=self.post('report',{})['ladder_loops'];self.assertIn('Structural',report['selection']);self.assertIn('retained',report['index']);self.assertFalse(report['native_runtime_parity'])

    def test_event_lab_nested_interrupt_mask_drains_at_outer_enable_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'EventLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        row=values(self.post('step',{'dt':10}));self.assertEqual(row['EventCount'],0)
        self.post('write',{'tag':'GuardEvents','value':True});row=values(self.post('step',{'dt':10}))
        self.assertEqual((row['GuardSeen'],row['ReleasedSeen'],row['EventCount']),(0,1,1))
        row=values(self.post('step',{'dt':10}));self.assertEqual((row['GuardSeen'],row['ReleasedSeen'],row['EventCount']),(1,2,2))
        self.post('write',{'tag':'GuardEvents','value':False});row=values(self.post('step',{'dt':10}));self.assertEqual(row['EventCount'],2)
        report=self.post('report',{});self.assertTrue({'UID','UIE'}<=set(report['supported_instructions']));self.assertIn('outermost',report['user_interrupts']['nesting']);self.assertFalse(report['user_interrupts']['native_runtime_parity'])

    def test_stats_lab_exact_wide_file_transforms_searches_and_rearm_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'StatsLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        row=values(self.post('step',{'dt':10}));self.assertIsNone(row['WideMapped[0]'])
        self.post('write',{'tag':'WideFiles','value':True});row=values(self.post('step',{'dt':10}))
        self.assertEqual(tuple(int(row[n]) for n in ('WideMapped[0]','WideMapped[1]','UnsignedMapped[0]','UnsignedMapped[1]')),(18014398509481987,18014398509481989,18446744073709551614,9007199254740992))
        self.assertEqual((row['WideFindControl.POS'],row['UnsignedFindControl.POS']),(1,1));self.assertTrue(row['WideFindControl.IN']);self.assertIsNone(row['WideMapped[2]']);self.assertIsNone(row['UnsignedMapped[2]'])
        self.post('write',{'tag':'WideFactor','value':9223372036854775807});self.post('step',{'dt':10})
        self.post('write',{'tag':'WideFiles','value':False});self.post('step',{'dt':10});self.post('write',{'tag':'WideFiles','value':True})
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
        with self.assertRaises(HTTPError) as error:self.post('step',{'dt':10})
        self.assertEqual(error.exception.code,400);self.assertIn('overflow',error.exception.read().decode().lower());error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        self.post('write',{'tag':'WideFactor','value':3});row=values(self.post('step',{'dt':10}));self.assertEqual(int(row['WideMapped[0]']),27021597764222980)

    def test_data_lab_numeric_fill_clips_requests_and_keeps_runtime_guards_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'DataLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        def fault(expected):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(expected,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        row=values(step());self.assertEqual(row['ClipValues[3]'],44);write('ClipNumeric',True);fault('outside bounds');write('ClipIndex',3);row=values(step());self.assertEqual([row[f'ClipValues[{i}]'] for i in range(5)],[11,22,33,120,120]);self.assertEqual(row['ClipScalar'],22136)
        write('ClipLength',100001);fault('0..100000');write('ClipLength',100000);write('ClipSource',-1);write('ClipIndex',1);row=values(step());self.assertEqual([row[f'ClipValues[{i}]'] for i in range(5)],[11,-1,-1,-1,-1]);self.assertEqual(row['ClipScalar'],-1)
        write('ClipNumeric',False);write('ClipIndex',99);row=values(step());self.assertEqual(row['ClipValues[4]'],-1);report=self.post('report',{})['numeric_fill'];self.assertTrue(report['clipping']);self.assertIn('logical',report['clipping_boundary']);self.assertFalse(report['native_runtime_parity'])

    def test_control_lab_mixed_numeric_queues_preserve_edges_conversion_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'ControlLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':10})
        step();write('MixedLoad',True);write('MixedPush',True);row=values(step())
        self.assertEqual((row['MixedQueue[0]'],row['MixedStack[0]']),(4,52));self.assertEqual((row['MixedQueueControl.POS'],row['MixedStackControl.POS']),(1,1))
        row=values(step());self.assertEqual((row['MixedQueueControl.POS'],row['MixedStackControl.POS']),(1,1))
        write('MixedLoad',False);write('MixedPush',False);write('MixedUnload',True);write('MixedPop',True);row=values(step())
        self.assertEqual((row['MixedResult'],row['MixedStackResult']),(4,52.0));self.assertEqual((row['MixedQueue[0]'],row['MixedStack[0]']),(0,0))
        self.assertEqual((row['MixedQueue[3]'],row['MixedStack[3]']),(999,99))
        write('MixedUnload',False);write('MixedPop',False);write('MixedSource',40000.0);step();write('MixedLoad',True)
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);self.assertIn('overflow',error.exception.read().decode());error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        write('MixedSource',-3.5);row=values(step());self.assertEqual(row['MixedQueue[0]'],-4)
        report=self.post('report',{})['control_operations'];self.assertIn('FFL/FFU/LFL/LFU',report['numeric_conversions']);self.assertFalse(report['native_fault_classification'])

    def test_system_lab_wall_clock_reads_typed_fields_and_keeps_lazy_rollback_through_http(self):
        import struct
        from datetime import datetime,timezone
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':25})
        write('ClockIndex',99);row=values(step());self.assertEqual(int(row['ClockMicros']),0)
        write('ReadClock',True)
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);self.assertIn('outside bounds',error.exception.read().decode());error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        write('ClockIndex',1);start=time.time_ns()//1000;row=values(step());end=time.time_ns()//1000
        words=struct.unpack('<q',struct.pack('<ii',row['ClockWords[1]'],row['ClockWords[2]']))[0]
        for value in (int(row['ClockMicros']),int(row['StClockMicros']),words):self.assertLessEqual(start,value);self.assertLessEqual(value,end)
        for name,first in [('ClockUtc',1),('ClockLocal',1),('StClockUtc',0)]:
            fields=[row[f'{name}[{i}]'] for i in range(first,first+7)];instant=datetime(*fields,tzinfo=timezone.utc)
            self.assertLess(abs(instant.timestamp()*1000000-int(row['ClockMicros'])),5000000)
        for name,last in [('ClockWords',3),('ClockUtc',8),('ClockLocal',8)]:self.assertEqual((row[f'{name}[0]'],row[f'{name}[{last}]']),(101,999))
        retained={k:v for k,v in row.items() if k.startswith(('Clock','StClock'))}
        write('ReadClock',False);row=values(step());self.assertEqual({k:v for k,v in row.items() if k in retained},retained)
        report=self.post('report',{})['system_values']['wall_clock'];self.assertIn('time.time_ns',report['source']);self.assertFalse(report['clock_setters']);self.assertFalse(report['native_runtime_parity'])

    def test_system_lab_activates_imported_standby_on_next_scheduled_invocation(self):
        state=self.post('demo',{'sample':'SystemLab'})
        self.assertEqual(state['blockers'],[])
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step(dt):return self.post('step',{'dt':dt})
        def values(state):return {row['name']:row['value'] for row in state['tags']}
        v=values(step(25))
        self.assertEqual((v['StandbyProgramDisabled'],v['StandbyCount'],v['StandbyFirst'],v['SlowCount']),(1,0,0,1))
        write('ActivateStandbyProgram',True)
        write('TaskStartIndex',1);write('ReadTaskStarts',True);write('TaskStartDivisor',0)
        before=self.post('report',{})
        with self.assertRaises(HTTPError) as error:step(1)
        self.assertEqual(error.exception.code,400);error.exception.close()
        self.assertEqual(self.post('report',{})['program_control'],before['program_control'])
        write('TaskStartDivisor',1)
        v=values(step(1))
        self.assertEqual((v['StandbyProgramDisabled'],v['StandbyCount'],v['StandbyFirst']),(0,0,0))
        v=values(step(24))
        self.assertEqual((v['StandbyCount'],v['StandbyFirst'],v['SlowCount']),(1,1,2))
        v=values(step(25))
        self.assertEqual((v['StandbyCount'],v['StandbyFirst'],v['SlowCount']),(2,1,3))
        self.post('reset',{})
        v=values(step(25))
        self.assertEqual((v['StandbyProgramDisabled'],v['StandbyCount'],v['StandbyFirst']),(1,0,0))

    def test_system_lab_program_disable_keeps_task_phase_and_rolls_back(self):
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step(dt=25):return self.post('step',{'dt':dt})
        def values(state):return {row['name']:row['value'] for row in state['tags']}
        initial=values(step())
        self.assertEqual((initial['FastCount'],initial['SlowCount'],initial['FastFirst'],initial['SlowFirst']),(2,1,1,1))
        write('ControlFastProgram',True);write('ControlSlowProgram',True)
        write('TaskStartIndex',1);write('ReadTaskStarts',True);write('TaskStartDivisor',0)
        before=self.post('report',{})
        with self.assertRaises(HTTPError) as error:step(1)
        self.assertEqual(error.exception.code,400);error.exception.close()
        after=self.post('report',{})
        for key in ('program_control','task_schedule','task_scan_timing'):self.assertEqual(after[key],before[key])
        write('TaskStartDivisor',1);v=values(step(1))
        self.assertEqual((v['LiveFastProgramDisabled'],v['LiveSlowProgramDisabled']),(1,1))
        t=step();v=values(t)
        self.assertEqual((v['FastCount'],v['SlowCount']),(2,1))
        self.assertTrue(all(not task['inhibited'] for task in t['task_schedule']['tasks']))
        write('FastProgramDisable',0);write('SlowProgramDisable',0);step(1)
        v=values(step())
        self.assertEqual((v['LiveFastProgramDisabled'],v['LiveSlowProgramDisabled']),(0,0))
        self.assertEqual((v['FastFirst'],v['SlowFirst']),(2,2))

    def test_system_lab_timing_resets_ladder_and_st_with_late_rollback(self):
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])
        write=lambda tag,value:self.post('write',{'tag':tag,'value':value})
        step=lambda:self.post('step',{'dt':25})
        values=lambda state:{r['name']:r['value'] for r in state['tags']}
        def state_now():
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:
                return json.load(response)
        v=values(step())
        self.assertEqual((v['ProgramMaxAfterReset'],v['FastTaskMaxAfterReset']),(-1,-1))
        self.assertEqual((v['ProgramLastAfterReset'],v['FastTaskLastAfterReset'],int(v['FastTaskStartAfterReset'])),(-1,-1,1))
        write('ReadConfig',True);write('ResetScanMax',True);write('ResetLastAndStart',True)
        write('TaskStartIndex',1);write('ReadTaskStarts',True);write('TaskStartDivisor',0)
        before=state_now();timings=self.post('report',{})['task_scan_timing']
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);error.exception.close()
        after=state_now()
        for key in ('tags','routines','scan','ms','task_schedule','trace'):self.assertEqual(after[key],before[key])
        self.assertEqual(self.post('report',{})['task_scan_timing'],timings)
        write('TaskStartDivisor',1)
        v=values(step())
        self.assertEqual((v['ProgramMaxAfterReset'],v['FastTaskMaxAfterReset']),(0,0))
        self.assertEqual((v['ProgramLastAfterReset'],v['FastTaskLastAfterReset'],int(v['FastTaskStartAfterReset'])),(0,0,0))
        timing=self.post('report',{})['system_values']['timing']
        for field in ('max_scan_reset','last_scan_reset','start_time_reset'):
            self.assertIn('known zero',timing[field])

    def test_system_lab_scan_time_gsv_keeps_committed_values_and_rollback_through_http(self):
        self.assertEqual(self.post('demo',{'sample':'SystemLab'})['blockers'],[])
        values=lambda s:{r['name']:r['value'] for r in s['tags']}
        def write(tag,value):return self.post('write',{'tag':tag,'value':value})
        def step():return self.post('step',{'dt':25})
        write('TimingIndex',99);row=values(step());self.assertEqual(row['TimingWords[1]'],-1)
        write('ReadTiming',True)
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
        with self.assertRaises(HTTPError) as error:step()
        self.assertEqual(error.exception.code,400);self.assertIn('outside bounds',error.exception.read().decode());error.exception.close()
        with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
        for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace'):self.assertEqual(after[key],before[key])
        write('TimingIndex',1);row=values(step());self.assertEqual(row['TimingWords[1]'],row['StProgramLast']);self.assertEqual(row['ProgramMax'],row['StProgramMax'])
        for last,maximum in [('TimingWords[1]','ProgramMax'),('FastLast','FastMax'),('SlowLast','SlowMax')]:self.assertGreaterEqual(row[last],0);self.assertGreaterEqual(row[maximum],row[last])
        self.assertEqual([row[f'TimingWords[{i}]'] for i in (0,2,3)],[101,77,999])
        retained={k:v for k,v in row.items() if k in ('ProgramMax','FastLast','FastMax','SlowLast','SlowMax','StProgramLast','StProgramMax') or k.startswith('TimingWords[')}
        write('ReadTiming',False);write('TimingIndex',99);row=values(step());self.assertEqual({k:v for k,v in row.items() if k in retained},retained)
        report=self.post('report',{})['system_values']['timing'];self.assertIn('committed',report['visibility']);self.assertFalse(report['controller_performance_prediction'])

    def test_integer_lab_lreal_constants_precision_limits_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'IntegerLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace','aoi_bindings'):self.assertEqual(before[key],after[key])
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['DoubleConstantsIndex'],99)
        write('EnableDoubleConstants',True);fault('outside bounds');write('DoubleConstantsIndex',1)
        row=values(step());self.assertEqual(tuple(row['DoubleConstants'+name] for name in ('Add','Sub','Mul','Div','Mod','Precision')),(10.5,-4.5,22.5,0.4,1.5,0.0))
        expected=dict(Eq=False,Ne=True,Lt=False,Le=False,Gt=True,Ge=True,NormalLimit=True,ReverseLimit=False,ConstantTest=True,PrecisionGreater=True)
        for name,want in expected.items():self.assertIs(row['DoubleConstants'+name],want)
        self.assertEqual(tuple(row['DoubleConstantsValues['+str(i)+']'] for i in range(3)),(101.125,7.5,999.5))
        write('DoubleConstantsZeroFault',True);fault('zero');write('DoubleConstantsZeroFault',False)
        write('DoubleConstantsLateDivisor',0);fault('zero');write('DoubleConstantsLateDivisor',1);step()
        write('EnableDoubleConstants',False);write('DoubleConstantsIndex',99);row=values(step())
        for name in expected:self.assertFalse(row['DoubleConstants'+name])
        for item in (self.post('report',{})['scalar_math']['lreal_arithmetic'],self.post('report',{})['numeric_comparisons']['lreal_ordering']):self.assertIn('Signed DINT',item['constants'])

    def test_math_lab_mixed_lreal_powers_precision_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'MathLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace','aoi_bindings'):self.assertEqual(before[key],after[key])
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['MixedPowerIndex'],99);self.assertIsNone(row['MixedPowerResults[1]'])
        write('MixedPowerEnabled',True);fault('outside bounds');write('MixedPowerIndex',1);row=values(step())
        self.assertEqual(tuple(row['MixedPower'+n] for n in ('Precision','ConstantBase','DintResult','RealResult','WideBaseResult','WideExponentResult','NegativeResult')),(1.0000000000000004,4.0,281475010265089.0,281474976710656.0,9007199254740992.0,1.0,-8.0))
        self.assertEqual(tuple(row['MixedPowerResults['+str(i)+']'] for i in range(3)),(101.125,8.0,999.5))
        write('MixedPowerDomainFault',True);fault('finite LREAL');write('MixedPowerDomainFault',False)
        write('MixedPowerOverflowFault',True);fault('finite LREAL');write('MixedPowerOverflowFault',False)
        write('MixedPowerLateDivisor',0);fault('zero');write('MixedPowerLateDivisor',1)
        write('MixedPowerValues[1]',3);row=values(step());self.assertEqual(row['MixedPowerResults[1]'],27.0)
        write('MixedPowerEnabled',False);write('MixedPowerIndex',99);row=values(step());self.assertEqual(row['MixedPowerResults[1]'],27.0)
        power=self.post('report',{})['real_math']['lreal']['power'];self.assertEqual(len(power['source_types']),10);self.assertIn('Signed DINT',power['constants']);self.assertFalse(power['native_runtime_parity'])

    def test_math_lab_numeric_unary_lreal_results_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'MathLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace','aoi_bindings'):self.assertEqual(before[key],after[key])
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['UnaryDoubleIndex'],99);self.assertIsNone(row['UnaryDoubleResults[1]'])
        write('UnaryDoubleEnabled',True);fault('outside bounds');write('UnaryDoubleIndex',1);row=values(step())
        self.assertEqual(tuple(row['UnaryDouble'+name] for name in ('DintRoot','RealRoot','UnsignedRoot','SignedRoot','LiteralRoot')),(4096.000122070311,4096.0,4294967296.0,4.0,3.0))
        self.assertEqual(tuple(row['UnaryDoubleResults['+str(i)+']'] for i in range(3)),(101.125,3.0,999.5))
        self.assertAlmostEqual(row['UnaryDoubleRadians'],1.5707963267948966);self.assertEqual(row['UnaryDoubleLn'],0);self.assertEqual(row['UnaryDoubleLog'],2)
        self.assertAlmostEqual(row['UnaryDoubleSine'],0.8414709848078965);self.assertEqual(row['UnaryDoubleCosine'],1);self.assertEqual(row['UnaryDoubleTangent'],0)
        for name in ('DomainFault','LiteralFault','OverflowFault'):
            write('UnaryDouble'+name,True);fault('finite LREAL');write('UnaryDouble'+name,False)
        write('UnaryDoubleLateDivisor',0);fault('zero');write('UnaryDoubleLateDivisor',1)
        write('UnaryDoubleInputs[1]',16);row=values(step());self.assertEqual(row['UnaryDoubleResults[1]'],4.0)
        write('UnaryDoubleEnabled',False);write('UnaryDoubleIndex',99);row=values(step());self.assertEqual(row['UnaryDoubleResults[1]'],4.0)
        unary=self.post('report',{})['real_math']['lreal']['unary'];self.assertEqual(len(unary['instructions']),11);self.assertEqual(len(unary['source_types']),10);self.assertFalse(unary['native_runtime_parity'])

    def test_integer_lab_lreal_result_selection_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'IntegerLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace','aoi_bindings'):self.assertEqual(before[key],after[key])
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['DoubleResultsIndex'],99);self.assertIsNone(row['DoubleResultsValues[1]'])
        write('DoubleResultsEnabled',True);fault('outside bounds');write('DoubleResultsIndex',1);row=values(step())
        self.assertEqual(tuple(row['DoubleResults'+n] for n in ('Sub','Mul','Div','Mod','Power','Neg','Abs','LiteralDivide','LiteralPower','Precision','WideRemainder')),(1.0,6.0,1.5,1.0,9.0,-3.0,3.0,1.5,8.0,16777218.0,1.0))
        self.assertEqual(row['DoubleResultsWideNeg'],-float(2**64));self.assertEqual(row['DoubleResultsWide'],'18446744073709551615')
        self.assertEqual(tuple(row['DoubleResultsValues['+str(i)+']'] for i in range(3)),(101.125,5.0,999.5))
        for name in ('DomainFault','ZeroFault','OverflowFault'):
            write('DoubleResults'+name,True);fault('zero' if name=='ZeroFault' else 'finite LREAL');write('DoubleResults'+name,False)
        write('DoubleResultsLateDivisor',0);fault('zero');write('DoubleResultsLateDivisor',1)
        write('DoubleResultsInputs[1]',4);row=values(step());self.assertEqual(row['DoubleResultsValues[1]'],6.0)
        write('DoubleResultsEnabled',False);write('DoubleResultsIndex',99);row=values(step());self.assertEqual(row['DoubleResultsValues[1]'],6.0)
        report=self.post('report',{});self.assertIn('no LREAL source',report['scalar_math']['lreal_arithmetic']['operands']);self.assertIn('no LREAL source',report['real_math']['lreal']['power']['operands']);self.assertIn('at least one LREAL',report['numeric_comparisons']['lreal_ordering']['operands'])

    def test_integer_lab_real_comparison_promotion_limits_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'IntegerLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','routine_edits','trace','aoi_bindings'):self.assertEqual(before[key],after[key])
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['RealCompareIndex'],99);self.assertFalse(row['RealCompareEq'])
        write('RealCompareEnabled',True);fault('outside bounds');write('RealCompareIndex',1);row=values(step())
        expected=dict(Eq=True,Ne=False,Lt=False,Le=True,Gt=False,Ge=True,NormalLimit=True,ReverseLimit=False,CollapsedLimit=False,WideEqual=True,LiteralEqual=True,TinyPositive=True,ZeroEqual=True,DoublePriority=True,ExactInteger=True)
        for name,want in expected.items():self.assertIs(row['RealCompare'+name],want)
        self.assertEqual(row['RealCompareDint'],16777217);self.assertEqual(row['RealCompareUlint'],'18446744073709551615')
        self.assertEqual(tuple(row['RealCompareValues['+str(i)+']'] for i in range(3)),(101.125,16777216.0,999.5))
        write('RealCompareLateDivisor',0);fault('zero');write('RealCompareLateDivisor',1)
        write('RealCompareValue',16777216);write('RealCompareValues[1]',16777218);row=values(step());self.assertTrue(row['RealCompareCollapsedLimit']);self.assertTrue(row['RealCompareNormalLimit']);self.assertTrue(row['RealCompareReverseLimit']);self.assertFalse(row['RealCompareEq'])
        write('RealCompareEnabled',False);write('RealCompareIndex',99);row=values(step())
        for name in expected:self.assertFalse(row['RealCompare'+name])
        report=self.post('report',{})['numeric_comparisons']['real_ordering'];self.assertEqual(len(report['source_types']),9);self.assertFalse(report['native_runtime_parity'])

    def test_integer_lab_real_result_math_precision_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'IntegerLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key],key)
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['RealResultsIndex'],99);self.assertIsNone(row['RealResultsValues[1]'])
        write('RealResultsEnabled',True);fault('outside bounds');write('RealResultsIndex',1);row=values(step())
        self.assertEqual(tuple(row['RealResults'+n] for n in ('Sub','Mul','Div','Mod','Power','Neg','Abs','Sqrt','Ln','Log','Precision','WideRemainder')),(1.0,6.0,1.5,1.0,9.0,-3.0,3.0,4294967296.0,0.0,2.0,16777216.0,1.0))
        self.assertEqual(row['RealResultsWideNeg'],-float(2**64));self.assertEqual(row['RealResultsWide'],'18446744073709551615');self.assertEqual(row['RealResultsPrecisionInput'],16777217)
        self.assertEqual(tuple(row['RealResultsValues['+str(i)+']'] for i in range(3)),(101.125,5.0,999.5))
        for name in ('DomainFault','ZeroFault','OverflowFault'):
            write('RealResults'+name,True);fault('zero' if name=='ZeroFault' else 'REAL');write('RealResults'+name,False)
        write('RealResultsLateDivisor',0);fault('zero');write('RealResultsLateDivisor',1);write('RealResultsOther',4);row=values(step());self.assertEqual(row['RealResultsValues[1]'],7.0);self.assertEqual(row['RealResultsPower'],81.0)
        write('RealResultsEnabled',False);write('RealResultsIndex',99);self.assertEqual(values(step())['RealResultsValues[1]'],7.0)
        report=self.post('report',{});self.assertEqual(len(report['scalar_math']['real_arithmetic']['source_types']),9);self.assertEqual(len(report['real_math']['real_destination']['instructions']),12)

    def test_bit_lab_index_arithmetic_bitwise_wide_tags_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key],key)
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['IndexMathDivisor'],0);self.assertIsNone(row['IndexMathResults[1]'])
        write('IndexMathEnabled',True);fault('zero');write('IndexMathDivisor',2);row=values(step())
        self.assertEqual(tuple(row['IndexMathResults['+str(i)+']'] for i in range(7)),(101,33,33,55,10,33,999));self.assertTrue(row['IndexMathCheck'])
        write('IndexMathWide',4294967296);fault('outside bounds');write('IndexMathWide',3)
        write('IndexMathLateDivisor',0);fault('zero');write('IndexMathLateDivisor',1)
        write('IndexMathValues[3]',123);row=values(step());self.assertEqual(row['IndexMathResults[1]'],123);self.assertEqual(row['IndexMathResults[2]'],123);self.assertEqual(row['IndexMathResults[5]'],123);self.assertFalse(row['IndexMathCheck'])
        write('IndexMathEnabled',False);write('IndexMathDivisor',0);row=values(step());self.assertEqual(row['IndexMathResults[1]'],123);self.assertFalse(row['IndexMathCheck'])
        report=self.post('report',{})['integer_expression_execution']['array_indices'];self.assertEqual(len(report['simple_tag_types']),8);self.assertFalse(report['native_runtime_parity'])

    def test_bit_lab_index_functions_bcd_roots_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key],key)
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['IndexFuncDecimal'],-1);self.assertIsNone(row['IndexFuncResults[1]'])
        write('IndexFuncEnabled',True);fault('qualified');write('IndexFuncDecimal',17);row=values(step())
        self.assertEqual(tuple(row['IndexFuncResults['+str(i)+']'] for i in range(8)),(101,221,223,202,217,207,223,999));self.assertTrue(row['IndexFuncCheck'])
        for tag,bad,restore,text in [('IndexFuncDecimal',100000000,17,'qualified'),('IndexFuncRoot',2147483647,3,'outside bounds'),('IndexFuncPacked',-1,33,'outside bounds'),('IndexFuncLateDivisor',0,1,'zero')]:
            write(tag,bad);fault(text);write(tag,restore)
        write('IndexFuncPacked',34);write('IndexFuncDecimal',18);write('IndexFuncRoot',8);row=values(step())
        self.assertEqual(tuple(row['IndexFuncResults['+str(i)+']'] for i in range(1,7)),(222,224,203,218,200,225));self.assertFalse(row['IndexFuncCheck'])
        write('IndexFuncEnabled',False);write('IndexFuncDecimal',-1);self.assertEqual(values(step())['IndexFuncResults[1]'],222)
        report=self.post('report',{})['integer_expression_execution']['array_indices'];self.assertEqual(report['functions'],['FRD','TOD','SQR']);self.assertFalse(report['native_runtime_parity'])

    def test_sequence_lab_narrow_sources_patterns_held_rows_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'SequenceLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key],key)
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['NarrowIndex'],99);self.assertIsNone(row['NarrowByteTable[1]'])
        write('NarrowEnabled',True);fault('outside bounds');write('NarrowIndex',1);row=values(step())
        self.assertEqual((row['NarrowByteControl.POS'],row['NarrowWordControl.POS']),(1,1))
        self.assertEqual((row['NarrowByteTable[1]'],row['NarrowWordTable[1]'],row['NarrowPatterns[1]']),(-1,-32768,-1))
        self.assertTrue(row['NarrowByteMatch']);self.assertTrue(row['NarrowWordMatch']);self.assertTrue(row['NarrowPatternMatch'])
        self.assertEqual((row['NarrowByteOutput'],row['NarrowWordOutput']),(0x123400ff,0x56788000))
        write('NarrowLateDivisor',0);fault('zero');write('NarrowLateDivisor',1)
        write('NarrowByteSources[1]',-2);write('NarrowWordSources[1]',-1);row=values(step())
        self.assertEqual((row['NarrowByteTable[1]'],row['NarrowWordTable[1]'],row['NarrowByteControl.POS']),(-2,-1,1));self.assertEqual((row['NarrowByteOutput'],row['NarrowWordOutput']),(0x123400fe,0x5678ffff))
        write('NarrowEnabled',False);step();write('NarrowEnabled',True);row=values(step());self.assertEqual(row['NarrowByteControl.POS'],2);self.assertTrue(row['NarrowByteControl.DN'])
        self.assertEqual((row['NarrowByteTable[0]'],row['NarrowWordTable[0]'],row['NarrowByteTable[3]'],row['NarrowWordTable[3]'],row['NarrowPatterns[2]']),(101,102,999,998,997))
        write('NarrowEnabled',False);write('NarrowIndex',99);row=values(step());self.assertEqual(row['NarrowByteOutput'],0x123400fe);self.assertFalse(row['NarrowByteMatch'])
        report=self.post('report',{})['sequencer_operations'];self.assertEqual(report['source_types'],['SINT','INT','DINT']);self.assertFalse(report['native_scan_parity'])

    def test_bit_lab_bcd_cpt_conversions_selected_results_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key],key)
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(row['CptBcdDecimal'],-1);self.assertIsNone(row['CptBcdResults[1]'])
        write('CptBcdEnabled',True);fault('qualified');write('CptBcdDecimal',42);fault('outside bounds');write('CptBcdIndex',1);row=values(step())
        self.assertEqual(tuple(row['CptBcd'+name] for name in ('Exact','RoundTrip','NarrowResult','Pattern','Mix','Truncated','LateResult')),(12345678,42,166666665,-1717986919,78,8,1));self.assertEqual(row['CptBcdResults[1]'],43)
        for tag,bad,restore,text in [('CptBcdDecimal',100000000,42,'qualified'),('CptBcdIndex',99,1,'outside bounds'),('CptBcdDivisor',0,1,'zero'),('CptBcdLateDivisor',0,1,'zero')]:
            write(tag,bad);fault(text);write(tag,restore)
        write('CptBcdPacked',34);write('CptBcdDecimal',21);row=values(step())
        self.assertEqual(tuple(row['CptBcd'+name] for name in ('Exact','RoundTrip','Mix')),(22,21,55));self.assertEqual(row['CptBcdResults[1]'],22)
        self.assertEqual((row['CptBcdResults[0]'],row['CptBcdResults[2]']),(101,999))
        write('CptBcdEnabled',False);write('CptBcdDecimal',-1);write('CptBcdIndex',99);self.assertEqual(values(step())['CptBcdResults[1]'],22)
        report=self.post('report',{})['integer_expression_execution']['bcd_cpt'];self.assertEqual(report['functions'],['FRD','TOD']);self.assertFalse(report['native_runtime_parity'])

    def test_bit_lab_bcd_cmp_match_coils_unknown_operands_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'BitLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        matches=lambda row:tuple(row['CmpBcd'+name+'Match'] for name in ('Decode','RoundTrip','Pattern','Mask','Gate','Indexed'))
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key],key)
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        row=values(step());self.assertEqual(matches(row),(False,)*6);self.assertIsNone(row['CmpBcdRows[1]'])
        write('CmpBcdEnabled',True);fault('qualified');write('CmpBcdDecimal',42);fault('outside bounds');write('CmpBcdIndex',1);fault('Unknown');write('CmpBcdRows[1]',33)
        row=values(step());self.assertEqual(matches(row),(True,)*6);self.assertEqual((row['CmpBcdRows[0]'],row['CmpBcdRows[2]']),(101,999))
        for tag,bad,restore,text in [('CmpBcdDecimal',100000000,42,'qualified'),('CmpBcdIndex',99,1,'outside bounds'),('CmpBcdDivisor',0,1,'zero'),('CmpBcdLateDivisor',0,1,'zero')]:
            write(tag,bad);fault(text);write(tag,restore)
        write('CmpBcdGate',False);write('CmpBcdDivisor',0);fault('zero');write('CmpBcdDivisor',1);self.assertFalse(values(step())['CmpBcdGateMatch'])
        write('CmpBcdGate',True);write('CmpBcdPacked',34);write('CmpBcdDecimal',21);write('CmpBcdRows[1]',34);row=values(step());self.assertEqual(matches(row),(False,True,True,False,True,False))
        write('CmpBcdEnabled',False);write('CmpBcdDecimal',-1);write('CmpBcdIndex',99);self.assertEqual(matches(values(step())),(False,)*6)
        report=self.post('report',{})['integer_expression_execution']['bcd_cmp'];self.assertEqual(report['functions'],['FRD','TOD']);self.assertTrue(report['boolean_composition']);self.assertFalse(report['native_runtime_parity'])

    def test_control_lab_bcd_files_all_numeric_inc_and_atomic_recovery(self):
        self.assertEqual(self.post('demo',{'sample':'ControlLab'})['blockers'],[])
        values=lambda state:{row['name']:row['value'] for row in state['tags']}
        step=lambda:self.post('step',{'dt':10})
        write=lambda name,value:self.post('write',{'tag':name,'value':value})
        def fault(text):
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:before=json.load(response)
            timing=self.post('report',{})['task_scan_timing']
            with self.assertRaises(HTTPError) as error:step()
            self.assertEqual(error.exception.code,400);self.assertIn(text,error.exception.read().decode());error.exception.close()
            with urlopen(Request(self.url+'/api/state',headers={'X-Logix-Token':self.token}),timeout=3) as response:after=json.load(response)
            for key in ('tags','routines','scan','ms','task_schedule','aoi_bindings','routine_edits','trace'):self.assertEqual(after[key],before[key],key)
            self.assertEqual(self.post('report',{})['task_scan_timing'],timing)
        def reset():
            for mode in ('All','Numeric','Increment'):write('BcdFile'+mode,False)
            write('BcdFileReset',True);step();write('BcdFileReset',False)
        row=values(step());self.assertIsNone(row['BcdDecoded[0]']);self.assertIsNone(row['BcdRepacked[0]']);self.assertIsNone(row['BcdIncremented[0]'])
        write('BcdFileAll',True);row=values(step());self.assertEqual(tuple(row[f'BcdDecoded[{i}]'] for i in range(5)),(12,21,20,99,901));self.assertTrue(row['BcdAllCalc.DN']);self.assertEqual(row['BcdAllFind.POS'],1);self.assertTrue(row['BcdAllFind.IN'])
        write('BcdFindValue',99);write('BcdAllFind.IN',False);row=values(step());self.assertEqual(row['BcdAllFind.POS'],3);self.assertTrue(row['BcdAllFind.DN'])
        reset();write('BcdFindValue',21);write('BcdPacked[0]',34);write('BcdFileAll',True);write('BcdFileLateDivisor',0);fault('zero');write('BcdFileLateDivisor',1);self.assertEqual(values(step())['BcdDecoded[0]'],22);write('BcdPacked[0]',18)
        reset();write('BcdFileNumeric',True);row=values(step());self.assertEqual(tuple(row[f'BcdRepacked[{i}]'] for i in range(5)),(18,33,None,None,902))
        write('BcdFileNumeric',False);write('BcdDecimal[2]',-1);fault('qualified');write('BcdDecimal[2]',20);row=values(step());self.assertEqual(tuple(row[f'BcdRepacked[{i}]'] for i in range(5)),(18,33,32,153,902));self.assertTrue(row['BcdNumericCalc.DN']);self.assertFalse(row['BcdNumericCalc.EN'])
        reset();write('BcdFileIncrement',True);row=values(step());self.assertEqual(row['BcdIncremented[0]'],13);self.assertEqual(row['BcdIncCalc.POS'],0)
        write('BcdDecimal[0]',-1);self.assertEqual(values(step())['BcdIncCalc.POS'],0)
        write('BcdFileIncrement',False);step();write('BcdDecimal[1]',-1);write('BcdFileIncrement',True);fault('qualified');write('BcdDecimal[1]',21);row=values(step());self.assertEqual(row['BcdIncremented[1]'],22);self.assertEqual(row['BcdIncFind.POS'],1);self.assertTrue(row['BcdIncFind.IN'])
        write('BcdFindValue',99);write('BcdIncFind.IN',False)
        for _ in range(2):write('BcdFileIncrement',False);step();write('BcdFileIncrement',True);row=values(step())
        self.assertEqual(tuple(row[f'BcdIncremented[{i}]'] for i in range(5)),(13,22,21,100,903));self.assertEqual(row['BcdIncFind.POS'],3);self.assertTrue(row['BcdIncFind.DN']);self.assertTrue(row['BcdIncFind.FD'])
        self.assertEqual((row['BcdPacked[4]'],row['BcdDecimal[4]'],row['BcdDecoded[4]'],row['BcdRepacked[4]']),(777,777,901,902))
        reset();row=values(step());self.assertEqual(row['BcdIncCalc.POS'],0);self.assertFalse(row['BcdIncCalc.DN']);self.assertEqual(row['BcdIncremented[3]'],100)
        profile=self.post('report',{})['integer_expression_execution']['bcd_files'];self.assertEqual(profile['instructions'],['FAL','FSC']);self.assertFalse(profile['native_runtime_parity'])
