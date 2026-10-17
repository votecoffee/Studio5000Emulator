"""Guard appliance isolation, package completeness and session ownership."""
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logixlab.server import Application
from tools import vmware_appliance as vm


class ApplianceTests(unittest.TestCase):
    def test_package_closure_includes_virtual_providers_and_handles_cycles(self):
        records = [{'P': 'runtime', 'V': '1', 'D': 'so:libc.so.1 helper>=1'},
                   {'P': 'libc', 'V': '1', 'p': 'so:libc.so.1=1'},
                   {'P': 'helper', 'V': '1', 'D': 'runtime !unwanted'},
                   {'P': 'unwanted', 'V': '1'}]
        self.assertEqual([r['P'] for r in vm.resolve_packages(records, ['runtime'])],
                         ['helper', 'libc', 'runtime'])
        with self.assertRaisesRegex(ValueError, 'No package provides'):
            vm.resolve_packages(records, ['missing'])

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
                self.assertEqual(sum(name.endswith('.L5X') for name in names), 9)
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
