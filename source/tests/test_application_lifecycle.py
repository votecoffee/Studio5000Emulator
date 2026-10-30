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
