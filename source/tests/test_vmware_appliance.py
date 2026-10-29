"""Guard appliance isolation, package completeness and session ownership."""
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from logixlab.server import Application
from tools import vmware_appliance as vm


class ApplianceTests(unittest.TestCase):
    def test_background_commands_capture_output_without_windows_console(self):
        with patch.object(subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True), \
                patch.object(subprocess, 'run', return_value=Mock(returncode=0, stdout='ready\n')) as launch:
            self.assertEqual(vm.run(['ssh', 'host', 'true'], creationflags=4), 'ready')
            self.assertEqual(launch.call_args.kwargs['creationflags'], 0x08000004)
            self.assertTrue(launch.call_args.kwargs['capture_output'])
            self.assertEqual(launch.call_args.kwargs['timeout'], 30)
            launch.return_value = Mock(returncode=1, stderr='diagnostic retained', stdout='')
            with self.assertRaisesRegex(RuntimeError, 'diagnostic retained'):
                vm.run(['ssh', 'host', 'true'])
        with patch.object(subprocess, 'CREATE_NO_WINDOW', 0, create=True):
            self.assertEqual(vm.background_options(), {'creationflags': 0})

    @unittest.skipUnless(sys.platform == 'win32', 'Windows console process behavior')
    def test_windows_background_child_has_no_console(self):
        result = vm.run([sys.executable, '-c',
                         'import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())'])
        self.assertEqual(result, '0')

    def test_tunnel_runs_without_console_or_interactive_stdin(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            config = {'vmx': str(directory / 'LogixLab.vmx'), 'subnet': '192.0.2.0/24',
                      'host_ip': '192.0.2.1', 'app_version': vm.__version__}
            (directory / 'appliance.json').write_text(json.dumps(config))
            (directory / 'host-key.pub').write_text('ssh-ed25519 example-key')
            state = {'app_version': vm.__version__, 'instance_id': 'test-instance',
                     'connectivity': {'address': '192.0.2.9:44818'}}
            tunnel = Mock(pid=123, poll=Mock(return_value=None))
            with patch.object(subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True), \
                    patch.object(subprocess, 'Popen', return_value=tunnel) as launch, \
                    patch.object(vm, 'vmrun', return_value='vmrun'), \
                    patch.object(vm, 'run', side_effect=[config['vmx'], '192.0.2.9', '']) as command, \
                    patch.object(vm, 'api', side_effect=[state, KeyboardInterrupt]), \
                    patch.object(vm.time, 'sleep'):
                vm.start(directory, open_browser=False, tray=False)
            self.assertEqual(launch.call_args.kwargs['creationflags'], 0x08000000)
            self.assertEqual(launch.call_args.kwargs['stdin'], subprocess.DEVNULL)
            self.assertEqual(launch.call_args.kwargs['stdout'], subprocess.DEVNULL)
            self.assertIn('BatchMode=yes', launch.call_args.args[0])
            self.assertIn('StrictHostKeyChecking=yes', launch.call_args.args[0])
            self.assertIn('127.0.0.1:8786:127.0.0.1:8786', launch.call_args.args[0])
            self.assertEqual(command.call_args.args[0][-1], 'poweroff')
            tunnel.terminate.assert_called_once()
            tunnel.wait.assert_called_once_with(timeout=8)

    def test_package_closure_includes_virtual_providers_and_handles_cycles(self):
        records = [{'P': 'runtime', 'V': '1', 'D': 'so:libc.so.1 helper>=1'},
                   {'P': 'libc', 'V': '1', 'p': 'so:libc.so.1=1'},
                   {'P': 'helper', 'V': '1', 'D': 'runtime !unwanted'},
                   {'P': 'unwanted', 'V': '1'}]
        self.assertEqual([r['P'] for r in vm.resolve_packages(records, ['runtime'])],
                         ['helper', 'libc', 'runtime'])
        with self.assertRaisesRegex(ValueError, 'No package provides'):
            vm.resolve_packages(records, ['missing'])

    def manager_fixture(self,directory):
        config={'vmx':str(directory/'LogixLab.vmx'),'subnet':'192.0.2.0/24',
                'host_ip':'192.0.2.1','app_version':vm.__version__}
        (directory/'appliance.json').write_text(json.dumps(config))
        (directory/'host-key.pub').write_text('ssh-ed25519 example-key')
        state={'app_version':vm.__version__,'instance_id':'owned-instance',
               'connectivity':{'address':'192.0.2.9:44818'}}
        return config,state

    def test_poll_timeouts_recover_without_shutting_down_or_restarting_guest(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);config,state=self.manager_fixture(directory)
            tunnel=Mock(pid=123,poll=Mock(side_effect=[None,None,None,None,1]))
            with patch.object(vm.subprocess,'Popen',return_value=tunnel),patch.object(vm,'vmrun',return_value='vmrun'), \
                    patch.object(vm,'run',side_effect=[config['vmx'],'192.0.2.9']) as command, \
                    patch.object(vm,'api',side_effect=[state,TimeoutError(),TimeoutError(),state]), \
                    patch.object(vm,'shutdown_requested',return_value=False) as intent,patch.object(vm.time,'sleep'):
                vm.start(directory,open_browser=False,tray=False)
            self.assertEqual(command.call_count,2)
            self.assertFalse(any('poweroff' in call.args[0] for call in command.call_args_list))
            intent.assert_called_once_with(directory,'192.0.2.9','owned-instance')
            self.assertEqual(json.loads((directory/'last-state.json').read_text()),state)

    def test_guest_shutdown_requires_matching_explicit_intent_after_failed_polls(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);config,state=self.manager_fixture(directory);tunnel=Mock(pid=123,poll=Mock(return_value=None))
            with patch.object(vm.subprocess,'Popen',return_value=tunnel),patch.object(vm,'vmrun',return_value='vmrun'), \
                    patch.object(vm,'run',side_effect=[config['vmx'],'192.0.2.9','']) as command, \
                    patch.object(vm,'api',side_effect=[state,TimeoutError(),TimeoutError()]), \
                    patch.object(vm,'shutdown_requested',return_value=True) as intent,patch.object(vm.time,'sleep'):
                vm.start(directory,open_browser=False,tray=False)
            intent.assert_called_once_with(directory,'192.0.2.9','owned-instance')
            self.assertEqual(command.call_args.args[0][-1],'poweroff')

    def test_changed_guest_instance_does_not_power_off_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);config,state=self.manager_fixture(directory);tunnel=Mock(pid=123,poll=Mock(return_value=None))
            with patch.object(vm.subprocess,'Popen',return_value=tunnel),patch.object(vm,'vmrun',return_value='vmrun'), \
                    patch.object(vm,'run',side_effect=[config['vmx'],'192.0.2.9']) as command, \
                    patch.object(vm,'api',side_effect=[state,dict(state,instance_id='replacement')]),patch.object(vm.time,'sleep'):
                with self.assertRaisesRegex(ValueError,'different process'):vm.start(directory,open_browser=False,tray=False)
            self.assertEqual(command.call_count,2)
            self.assertFalse(any('poweroff' in call.args[0] for call in command.call_args_list))

    def test_shutdown_marker_rejects_stale_unknown_malformed_and_unavailable_intent(self):
        good=dict(instance_id='owned',app_version=vm.__version__,reason='api')
        for marker in (dict(good,instance_id='other'),dict(good,app_version='old'),dict(good,reason='crash'),
                       dict(good,extra=True),[],None,{'instance_id':'owned'}):
            with self.subTest(marker=marker),patch.object(vm,'ssh_args',return_value=['ssh']),patch.object(vm,'run',return_value=json.dumps(marker)):
                self.assertFalse(vm.shutdown_requested(Path('unused'),'192.0.2.9','owned'))
        for value in ('not-json',''):
            with patch.object(vm,'ssh_args',return_value=['ssh']),patch.object(vm,'run',return_value=value):
                self.assertFalse(vm.shutdown_requested(Path('unused'),'192.0.2.9','owned'))
        for error in (OSError(),RuntimeError(),subprocess.TimeoutExpired('ssh',8)):
            with patch.object(vm,'ssh_args',return_value=['ssh']),patch.object(vm,'run',side_effect=error):
                self.assertFalse(vm.shutdown_requested(Path('unused'),'192.0.2.9','owned'))
        with patch.object(vm,'ssh_args',return_value=['ssh']),patch.object(vm,'run',return_value=json.dumps(good)):
            self.assertTrue(vm.shutdown_requested(Path('unused'),'192.0.2.9','owned'))

    def test_signed_index_archive_is_parsed_without_extracting_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'index.tar.gz'
            path.write_bytes(vm.tar_bytes([('APKINDEX', 'P:python3\nV:3.14\nD:so:libc.so\n\n', 0o644),
                                           ('../../ignored', 'unused', 0o644)]))
            self.assertEqual(vm.package_index(path, 'main')[0]['repository'], 'main')
            self.assertEqual(vm.package_index(path, 'main')[0]['P'], 'python3')
            self.assertFalse((Path(folder).parent / 'ignored').exists())

    def test_nat_and_ambiguous_network_names_are_rejected(self):
        with patch.object(vm, 'run', return_value='8 vmnet8 nat true 192.168.189.0 255.255.255.0') as run:
            with self.assertRaisesRegex(ValueError, 'host-only'):
                vm.host_network('VMnet8')
            self.assertEqual(run.call_count, 1)
        with patch.object(vm, 'run') as run:
            with self.assertRaises(ValueError):
                vm.host_network("VMnet1'; arbitrary")
            run.assert_not_called()

    def test_dhcp_lookup_is_constrained_to_own_mac_and_subnet(self):
        config = {'mac': '00:50:56:3a:12:34', 'subnet': '192.0.2.0/24', 'host_ip': '192.0.2.1'}
        leases = '''lease 192.0.2.9 { hardware ethernet 00:50:56:3a:12:34; }
lease 192.0.2.20 { hardware ethernet 00:50:56:3a:aa:bb; }
lease 198.51.100.9 { hardware ethernet 00:50:56:3a:12:34; }
lease 192.0.2.1 { hardware ethernet 00:50:56:3a:12:34; }'''
        self.assertEqual(vm.lease_address(config, leases), '192.0.2.9')
        self.assertIsNone(vm.lease_address(config, ''))

    def test_overlay_limits_bundled_files_and_protects_guest_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for name in ('client-key.pub', 'host-key', 'host-key.pub'):
                (directory / name).write_text('test-key-content')
            with tarfile.open(fileobj=io.BytesIO(vm.overlay(directory))) as archive:
                names = archive.getnames()
                from logixlab.server import SAMPLES
                self.assertEqual({name for name in names if name.endswith('.L5X')},
                                 {'opt/logixlab/samples/'+sample+'.L5X' for sample in SAMPLES})
                self.assertEqual(archive.extractfile('opt/logixlab/web/icons/plc-simulator.ico').read(),
                                 (vm.SOURCE / 'web/icons/plc-simulator.ico').read_bytes())
                self.assertFalse(any(name.lower().endswith(('.acd', '.exe', '.pyc', '.dll')) for name in names))
                self.assertEqual(archive.getmember('etc/ssh/ssh_host_ed25519_key').mode, 0o600)
                config = archive.extractfile('etc/ssh/sshd_config').read().decode()
                self.assertIn('PasswordAuthentication no', config)
                self.assertIn('PermitOpen 127.0.0.1:8786', config)
                startup = archive.extractfile('etc/local.d/logixlab.start').read().decode()
                self.assertIn('su logixlab', startup)
                self.assertIn('--eip-port 44818', startup)
                self.assertNotIn('--eip-writes', startup)

    def test_manifest_cannot_control_another_vm(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / 'appliance.json').write_text(json.dumps({'vmx': str(directory / 'different.vmx')}))
            with self.assertRaisesRegex(ValueError, 'does not identify'):
                vm.load_config(directory)

    def test_reused_ui_port_cannot_control_a_different_application_instance(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            config = {'vmx': str(directory / 'LogixLab.vmx'), 'subnet': '192.0.2.0/24', 'host_ip': '192.0.2.1'}
            (directory / 'appliance.json').write_text(json.dumps(config))
            (directory / 'session.json').write_text(json.dumps({'url': 'http://127.0.0.1:8786',
                'guest_ip': '192.0.2.9', 'instance_id': 'expected'}))
            with patch.object(vm, 'api', return_value={'instance_id': 'other'}):
                with self.assertRaisesRegex(ValueError, 'different process'):
                    vm.validated_state(directory)

    def test_application_identity_stays_stable_through_model_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Application(folder)
            other = Application(folder)
            identity = app.state()['instance_id']
            self.assertNotEqual(identity, other.state()['instance_id'])
            self.assertEqual(app.command('demo', {'sample': 'ConveyorDemo'})['instance_id'], identity)
            self.assertEqual(app.command('reset', {})['instance_id'], identity)
