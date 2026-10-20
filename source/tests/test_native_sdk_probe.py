"""The optional native probe cannot silently select another target or source."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.probe_native_sdk import (runtime_hashes, validate_target, validate_url,
                                    validate_operation, validate_idle, wait_for_cleanup, run)


class NativeSdkProbeTests(unittest.TestCase):
    def test_runtime_evidence_changes_when_managed_code_changes_under_the_same_apphost(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'probe.exe').write_bytes(b'same-apphost')
            (root/'probe.dll').write_bytes(b'first managed implementation')
            (root/'probe.runtimeconfig.json').write_text('{}')
            (root/'private.pdb').write_bytes(b'debug paths')
            before=runtime_hashes(root)
            (root/'probe.dll').write_bytes(b'changed managed implementation')
            after=runtime_hashes(root)
            self.assertEqual(before['probe.exe'],after['probe.exe'])
            self.assertNotEqual(before['probe.dll'],after['probe.dll'])
            self.assertEqual(set(after),{'probe.exe','probe.dll','probe.runtimeconfig.json'})

    def state(self):
        return {'instance_id': 'one-session', 'device_io': {'writes_enabled': False},
                'connectivity': {'enabled': True, 'profile': 'logix-v35-l85e',
                    'address': '192.0.2.8:44818', 'allow_writes': False,
                    'source_l5x_sha256': '2'*64,
                    'native_session': {'enabled': True, 'read_only': True},
                    'active_tcp_clients':0,
                    'native_programming_lease':{'available':True,'owned':False,'run_mode_inhibit':0,
                        'scan_inhibited':False,'project_transfer':False,'controller_mode_changes':False,
                        'online_edits':False,'tag_write_authority':False},
                    'native_correlation': {'bound': True, 'source_acd_sha256': '1'*64,
                                           'source_l5x_sha256': '2'*64}}}

    def check(self, state, **kwargs):
        return validate_target(state, r'TestDriver\192.0.2.8\Backplane\0', '1'*64, **kwargs)

    def test_exact_bound_endpoint_is_accepted_without_mutating_state(self):
        state = self.state(); before = copy.deepcopy(state)
        self.assertEqual(self.check(state), 'one-session')
        self.assertEqual(self.check(state, instance='one-session'), 'one-session')
        self.assertEqual(state, before)

    def test_changed_instance_project_binding_and_writable_endpoint_are_rejected(self):
        for section, field, value in (('connectivity','enabled',False),
                ('connectivity','allow_writes',True), ('connectivity','profile','research'),
                ('connectivity','address','192.0.2.9:44818'),
                ('connectivity','address','192.0.2.8:44819'),
                ('connectivity','source_l5x_sha256','3'*64),
                ('device_io','writes_enabled',True)):
            state=self.state();state[section][field]=value
            with self.assertRaises(ValueError):self.check(state)
        for section, field, value in (('native_session','enabled',False),
                ('native_session','read_only',False), ('native_correlation','bound',False),
                ('native_correlation','source_acd_sha256','3'*64),
                ('native_correlation','source_l5x_sha256','3'*64)):
            state=self.state();state['connectivity'][section][field]=value
            with self.assertRaises(ValueError):self.check(state)
        with self.assertRaises(ValueError):self.check(self.state(),instance='replaced-session')
        with self.assertRaises(ValueError):self.check(self.state(),l5x_hash='3'*64)
        for state in ({}, {'instance_id':'other'}, {'connectivity':{}}):
            with self.assertRaises(ValueError):self.check(state)

    def test_wrong_slot_ipv4_driver_and_nested_path_do_not_reach_the_sdk(self):
        for path in (r'TestDriver\192.0.2.8\Backplane\1',r'TestDriver\192.0.2.8',
                     r'TestDriver\192.0.2.9\Backplane\0',r'\192.0.2.8\Backplane\0',
                     r'TestDriver\host.example\Backplane\0',r'TestDriver\192.0.2.8\Backplane\0\1'):
            with self.assertRaises(ValueError):validate_target(self.state(),path,'1'*64)

    def test_remote_urls_credentials_paths_and_token_queries_are_rejected(self):
        self.assertEqual(validate_url('http://127.0.0.1:8786'),'http://127.0.0.1:8786')
        for url in ('http://192.0.2.8:80','http://localhost:8786','https://127.0.0.1:8786',
                    'http://127.0.0.1','http://user@127.0.0.1:8786','http://127.0.0.1:8786/',
                    'http://127.0.0.1:8786?token=private','http://127.0.0.1:8786#fragment'):
            with self.assertRaises(ValueError):validate_url(url)

    def test_download_is_explicit_and_transfer_operations_cannot_include_tag_reads(self):
        for operation in ('connection','upload','download'):
            validate_operation(operation,[])
        validate_operation('connection',['Controller/Tags/Tag'])
        for operation,tags in (('download',['Controller/Tags/Tag']),('upload',['tag']),
                ('edit',[]),('connection',['']),('connection',['x'*1025]),('connection',['tag']*33)):
            with self.subTest(operation=operation,tags_count=len(tags)),self.assertRaises(ValueError):
                validate_operation(operation,tags)

    def test_busy_inhibited_unknown_or_programmable_endpoints_are_not_admitted(self):
        state=self.state();before=copy.deepcopy(state);validate_idle(state)
        self.assertEqual(state,before)
        for field,value in (('active_tcp_clients',1),('active_tcp_clients',False),
                ('available',False),('owned',True),('run_mode_inhibit',1),('run_mode_inhibit',False),
                ('scan_inhibited',True),('project_transfer',True),('controller_mode_changes',True),
                ('online_edits',True),('tag_write_authority',True)):
            state=self.state()
            target=state['connectivity'] if field=='active_tcp_clients' else state['connectivity']['native_programming_lease']
            target[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_idle(state)
        for field in self.state()['connectivity']['native_programming_lease']:
            state=self.state();del state['connectivity']['native_programming_lease'][field]
            with self.subTest(missing=field),self.assertRaises(ValueError):validate_idle(state)

    def test_async_tcp_close_and_lease_release_finish_before_cleanup_is_confirmed(self):
        connected=self.state();connected['connectivity']['active_tcp_clients']=1
        owned=self.state();owned['connectivity']['native_programming_lease'].update(owned=True,run_mode_inhibit=1,scan_inhibited=True)
        idle=self.state()
        with patch('tools.probe_native_sdk.api',side_effect=(connected,owned,idle)) as api, \
                patch('tools.probe_native_sdk.time.monotonic',return_value=0), \
                patch('tools.probe_native_sdk.time.sleep') as sleep:
            result=wait_for_cleanup('http://127.0.0.1:8786',r'TestDriver\192.0.2.8\Backplane\0','1'*64,
                                    instance='one-session',l5x_hash='2'*64)
        self.assertEqual(result,idle)
        self.assertEqual(sleep.call_count,2)
        self.assertEqual([call.args for call in api.call_args_list],[('http://127.0.0.1:8786','state')]*3)

    def test_cleanup_timeout_and_target_replacement_remain_failures(self):
        for failure in ('busy','lease','source','instance'):
            state=self.state()
            if failure=='busy':state['connectivity']['active_tcp_clients']=1
            elif failure=='lease':state['connectivity']['native_programming_lease']['run_mode_inhibit']=1
            elif failure=='source':state['connectivity']['source_l5x_sha256']='3'*64
            else:state['instance_id']='replacement'
            with self.subTest(failure=failure),patch('tools.probe_native_sdk.api',return_value=state) as api, \
                    patch('tools.probe_native_sdk.time.monotonic',side_effect=(0,10)), \
                    patch('tools.probe_native_sdk.time.sleep') as sleep:
                with self.assertRaises(ValueError):
                    wait_for_cleanup('http://127.0.0.1:8786',r'TestDriver\192.0.2.8\Backplane\0','1'*64,
                                     instance='one-session',l5x_hash='2'*64)
                self.assertEqual(api.call_count,1);sleep.assert_not_called()

    def test_cleanup_failure_keeps_post_call_trace_and_reports_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.ACD';source.write_bytes(b'owned-acd-source')
            output=root/'report'
            args=SimpleNamespace(project=str(source),url='http://127.0.0.1:8786',
                path=r'TestDriver\192.0.2.8\Backplane\0',operation='download',tag=[],output=str(output),sdk_feed=None)
            from tools.probe_native_sdk import digest
            state=self.state();state.update(app_version='test',tags=[],scan=0,ms=0,changes=[],mode='test')
            state['connectivity']['native_correlation']['source_acd_sha256']=digest(source)
            busy=copy.deepcopy(state);busy['connectivity']['active_tcp_clients']=1
            before={'events':[],'counts':{'native_verified':0}}
            after={'events':[{'kind':'test-retained-evidence'}],'counts':{'native_verified':3}}
            def process(command,**kwargs):
                if command[0]=='dotnet':
                    (output/'bin').mkdir()
                    (output/'bin/NativeSdkProbe.exe').write_bytes(b'test-apphost')
                    (output/'bin/NativeSdkProbe.dll').write_bytes(b'test-managed-code')
                    return subprocess.CompletedProcess(command,0)
                Path(command[2]).write_text(json.dumps({'status':'failed'}))
                return subprocess.CompletedProcess(command,1)
            with patch('tools.probe_native_sdk.sys.platform','win32'), \
                    patch('tools.probe_native_sdk.background_options',return_value={}), \
                    patch('tools.probe_native_sdk.subprocess.run',side_effect=process), \
                    patch('tools.probe_native_sdk.api',side_effect=(state,state,before,busy,after)), \
                    patch('tools.probe_native_sdk.wait_for_cleanup',side_effect=ValueError('still owned')), \
                    patch('builtins.print'):
                self.assertEqual(run(args),1)
            report=json.loads((output/'summary.json').read_text())
            self.assertEqual(report['status'],'incomplete')
            self.assertFalse(report['cleanup_confirmed'])
            self.assertTrue(report['source_unchanged'] and report['model_unchanged'])
            self.assertEqual(report['native_verified_requests'],3)
            self.assertEqual(json.loads((output/'trace.json').read_text()),after)
            self.assertEqual(json.loads((output/'after-state.json').read_text()),busy)


if __name__=='__main__':unittest.main()
