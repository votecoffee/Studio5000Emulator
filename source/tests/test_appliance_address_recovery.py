"""Guest-address timeouts reuse bounded, authenticated appliance discovery."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import vmware_appliance as vm
import test_vmware_appliance as fixtures


class AddressRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.config, self.state = fixtures.ApplianceTests().manager_fixture(self.directory)
        self.config['mac'] = '00:50:56:3a:12:34'
        (self.directory/'appliance.json').write_text(json.dumps(self.config), encoding='utf8')
        self.data = self.directory/'program-data'
        self.leases = self.data/'VMware/vmnetdhcp.leases'
        self.leases.parent.mkdir(parents=True)
        self.events = []
        self.tunnel = Mock(pid=123, poll=Mock(side_effect=[None, 1]))

    def lease(self, address='192.0.2.9', mac='00:50:56:3a:12:34'):
        self.leases.write_text('lease '+address+' { hardware ethernet '+mac+'; }', encoding='utf8')

    def manager(self, replies, *, booted=False, ssh_error=None, clock=None, state=None):
        replies = iter(replies)
        def run(args, **kwargs):
            if args[-1] == 'list': return '' if booted else self.config['vmx']
            if 'start' in args:
                self.events.append('boot'); return ''
            if 'getGuestIPAddress' in args:
                self.assertEqual(kwargs, dict(check=False, timeout=8))
                self.events.append('query'); reply = next(replies)
                if isinstance(reply, BaseException): raise reply
                return reply
            if args[-1] == 'true':
                self.assertEqual(kwargs, dict(timeout=6))
                self.assertIn('StrictHostKeyChecking=yes', args)
                self.assertIn('BatchMode=yes', args)
                self.events.append('ssh')
                if ssh_error: raise ssh_error
                return ''
            self.fail('Unexpected command, including any unsolicited poweroff: '+repr(args))
        def tunnel(*args, **kwargs):
            self.events.append('tunnel'); return self.tunnel
        def seed(*args):
            self.events.append('seed'); return 1793577600
        with patch.dict(os.environ, {'PROGRAMDATA': str(self.data)}), \
                patch.object(vm, 'vmrun', return_value='vmrun'), \
                patch.object(vm, 'run', side_effect=run) as commands, \
                patch.object(vm.subprocess, 'Popen', side_effect=tunnel) as launched, \
                patch.object(vm, 'synchronize_guest_clock', side_effect=seed) as seeded, \
                patch.object(vm, 'api', return_value=state or self.state) as api, \
                patch.object(vm.time, 'sleep') as sleeps, \
                patch.object(vm.time, 'monotonic', side_effect=clock) if clock else patch.object(vm.time, 'monotonic', return_value=0), \
                patch('builtins.print') as printed:
            self.commands, self.launched, self.seeded = commands, launched, seeded
            self.api, self.sleeps, self.printed = api, sleeps, printed
            vm.start(self.directory, open_browser=False, tray=False)

    @staticmethod
    def timeout(): return subprocess.TimeoutExpired('vmrun getGuestIPAddress', 8)

    def test_timed_out_query_authenticates_matching_lease_before_publishing_tunnel(self):
        self.lease(); self.manager([self.timeout()])
        self.assertEqual(self.events, ['query', 'ssh', 'tunnel'])
        self.launched.assert_called_once(); self.seeded.assert_not_called()
        session = json.loads((self.directory/'session.json').read_text())
        self.assertEqual(session['guest_ip'], '192.0.2.9')
        self.assertEqual(session['instance_id'], 'owned-instance')
        self.printed.assert_any_call('Guest address query timed out; trying DHCP and pinned SSH', flush=True)

    def test_newly_booted_guest_is_not_rebooted_and_clock_seeds_before_tunnel(self):
        self.lease(); self.manager([self.timeout()], booted=True)
        self.assertEqual(self.events, ['boot', 'query', 'ssh', 'seed', 'tunnel'])
        self.seeded.assert_called_once_with(self.directory, '192.0.2.9')
        self.assertEqual(sum('start' in call.args[0] for call in self.commands.call_args_list), 1)

    def test_missing_lease_retries_and_later_vmware_address_can_complete(self):
        self.manager([self.timeout(), '192.0.2.9'])
        self.assertEqual(self.events, ['query', 'query', 'tunnel'])
        self.sleeps.assert_called_once_with(2)

    def test_repeated_timeouts_without_a_lease_do_not_restart_guest(self):
        self.manager([self.timeout(), self.timeout(), '192.0.2.9'])
        self.assertEqual(self.events, ['query', 'query', 'query', 'tunnel'])
        self.assertEqual(self.sleeps.call_count, 2)

    def test_wrong_mac_off_subnet_and_host_leases_never_receive_probe(self):
        for address, mac in [('192.0.2.9', '00:50:56:3a:ff:ff'),
                              ('198.51.100.9', self.config['mac']), ('192.0.2.1', self.config['mac'])]:
            with self.subTest(address=address, mac=mac):
                self.events.clear(); self.tunnel.poll = Mock(side_effect=[None, 1])
                (self.directory/'session.json').unlink(missing_ok=True)
                self.lease(address, mac); self.manager([self.timeout(), '192.0.2.9'])
                self.assertEqual(self.events, ['query', 'query', 'tunnel'])

    def test_failed_authentication_and_ssh_timeouts_wait_before_retry(self):
        for error in [RuntimeError('authentication failed'), subprocess.TimeoutExpired('ssh', 6)]:
            with self.subTest(error=error):
                self.events.clear(); self.tunnel.poll = Mock(side_effect=[None, 1])
                (self.directory/'session.json').unlink(missing_ok=True)
                self.lease(); self.manager([self.timeout(), '192.0.2.9'], ssh_error=error)
                self.assertEqual(self.events, ['query', 'ssh', 'query', 'tunnel'])
                self.sleeps.assert_called_once_with(2)

    def test_address_deadline_expiry_does_not_publish_tunnel_or_session(self):
        with self.assertRaisesRegex(RuntimeError, 'Guest IP not available'):
            self.manager([self.timeout()], clock=[0, 0, 181])
        self.launched.assert_not_called(); self.api.assert_not_called()
        self.assertFalse((self.directory/'session.json').exists())
        self.assertEqual(self.events, ['query'])

    def test_expiry_after_boot_leaves_guest_running_without_publishing_session(self):
        with self.assertRaisesRegex(RuntimeError, 'Guest IP not available'):
            self.manager([self.timeout()], booted=True, clock=[0, 0, 181])
        self.assertEqual(self.events, ['boot', 'query'])
        self.seeded.assert_not_called(); self.launched.assert_not_called()

    def test_non_timeout_errors_remain_visible_and_do_not_enter_fallback(self):
        self.lease()
        with self.assertRaisesRegex(PermissionError, 'denied'):
            self.manager([PermissionError('denied')])
        self.assertEqual(self.events, ['query']); self.launched.assert_not_called()

    def test_normal_vmware_query_keeps_existing_path_and_skips_fallback_probe(self):
        self.lease(); self.manager(['192.0.2.9'])
        self.assertEqual(self.events, ['query', 'tunnel'])
        self.assertFalse(any('timed out' in str(call) for call in self.printed.call_args_list))

    def test_fallback_does_not_waive_guest_version_or_endpoint_checks(self):
        for state in [dict(self.state, app_version='old'),
                      dict(self.state, connectivity={'address': '192.0.2.20:44818'})]:
            with self.subTest(state=state):
                self.events.clear(); self.tunnel.poll = Mock(return_value=None)
                self.lease()
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    self.manager([self.timeout()], state=state)
                self.assertFalse((self.directory/'session.json').exists())
                self.tunnel.terminate.assert_called(); self.tunnel.wait.assert_called_with(timeout=8)
