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
        self.assertFalse(state['controller']['first_scan_pending'])
        self.post('write', {'tag': 'SelfTrigger', 'value': True})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['EventCount'], 4)
        self.assertEqual(state['task_schedule']['tasks'][2]['event_instruction_overlaps'], 2)
        self.assertEqual(state['task_schedule']['tasks'][2]['executions'], 4)
        self.assertFalse(self.post('report', {})['event_execution']['native_cpu_timing'])

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
        self.post('write', {'tag': 'SearchText', 'value': 'PART'})
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        self.assertEqual(values['Location'], 1)
        self.assertEqual(values['StPosition'], 1)
        self.assertFalse(values['AllOK'])
        self.assertEqual(self.post('report', {})['string_operations']['instructions'], ['DELETE','FIND','INSERT'])

    def test_string_lab_case_and_real_conversions_in_rll_and_st(self):
        state = self.post('demo', {'sample': 'StringLab'})
        self.assertEqual(state['blockers'], [])
        state = self.post('step', {'dt': 10})
        values = {row['name']: row['value'] for row in state['tags']}
        for prefix in ('', 'St'):
            self.assertEqual(values[prefix + 'Lowered'], 'abc 09')
            self.assertEqual(values[prefix + 'Uppered'], 'ABC 09')
            self.assertEqual(values[prefix + 'ParsedReal'], -12.5)
            self.assertEqual(values[prefix + 'FormattedReal'], '15.3001003')
        self.post('write', {'tag': 'Convert', 'value': False})
        self.post('write', {'tag': 'CaseText', 'value': 'new'})
        self.post('write', {'tag': 'NumericText', 'value': 'invalid'})
        state = self.post('step', {'dt': 10})
        held = {row['name']: row['value'] for row in state['tags']}
        for name in ('Lowered', 'Uppered', 'ParsedReal', 'FormattedReal', 'StLowered', 'StUppered', 'StParsedReal', 'StFormattedReal'):
            self.assertEqual(held[name], values[name])
        report = self.post('report', {})['string_conversions']
        self.assertEqual(report['instructions'], ['LOWER', 'RTOS', 'STOR', 'UPPER'])
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
        profile=self.post('report', {})['st_oneshot'];self.assertEqual(profile['instructions'],['OSFI','OSRI'])
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
