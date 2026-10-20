"""The optional native probe cannot silently select another target or source."""
import copy
from pathlib import Path
import tempfile
import unittest

from tools.probe_native_sdk import runtime_hashes, validate_target, validate_url


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


if __name__=='__main__':unittest.main()
