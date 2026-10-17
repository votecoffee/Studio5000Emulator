"""Independent structured write/read roundtrips on an isolated loopback target."""
import argparse
import hashlib
import json
import struct
import tempfile
from pathlib import Path
from interop_structure_reads import documented_catalog, expected_axis, expected_machine
from logixlab.server import Application
from logixlab.ethernetip import Endpoint


def check(app, endpoint):
    from pycomm3 import LogixDriver, __version__
    target = f'127.0.0.1:{endpoint.port}'
    with LogixDriver(target + '/0', init_tags=False) as driver:
        assert driver.name == 'StructureLab', driver.info
        driver._cfg['extended forward open'] = False; driver._cfg['connection_size'] = 256
        driver._tags = documented_catalog(driver, structures=True)
        original = driver.read('Machines{2}'); assert original, original
        assert original.value == [expected_machine(0), expected_machine(100)], original
        desired = [expected_machine(30), expected_machine(60)]
        try:
            written = driver.write(('Machines{2}', desired)); assert written, written
            roundtrip = driver.read('Machines{2}'); assert roundtrip and roundtrip.value == desired, roundtrip
            # Use the client's valid Multi Service path for small unfragmented
            # writes; its 1.2.16 single-write builder duplicates payload bytes.
            nested = driver.write(('Machines[0].Axis', expected_axis(70)), ('Machines[1].Axis', expected_axis(80)))
            assert all(nested), nested
            readback = driver.read('Machines[0].Axis', 'Machines[1].Axis')
            assert all(readback) and [r.value for r in readback] == [expected_axis(70), expected_axis(80)], readback
            handle = driver.data_types['MachineState']['template']['structure_handle']
            before = driver.read('Machines{2}'); assert before, before
            wrong = driver.generic_message(service=0x53, class_code=0x6B, instance=driver.tags['Machines']['instance_id'],
                request_data=struct.pack('<HHHIi', 0x02A0, handle ^ 1, 2, 0, 999), connected=True)
            assert not wrong, 'Wrong template handle was accepted'
            after = driver.read('Machines{2}'); assert after and after.value == before.value, after
            denied = driver.generic_message(service=0x53, class_code=0x6B, instance=driver.tags['Machine']['instance_id'],
                request_data=struct.pack('<HHHIi', 0x02A0, handle, 1, 0, 999), connected=True)
            assert not denied, 'Read Only structure was written'
            app.command('step', {})
            observed = driver.read('Machine.History[0].Command'); assert observed and observed.value == 70, observed
        finally:
            restored = driver.write(('Machines{2}', original.value)); assert restored, restored
            verified = driver.read('Machines{2}'); assert verified and verified.value == original.value, verified
    events = endpoint.state(True)['events']
    for service in ('0x4D', '0x53', '0x52'):
        assert any(e.get('service') == service and e.get('status') == 0 for e in events), service
    assert any(e.get('service') == '0x53' and e.get('status') == 0xFF for e in events), 'No wrong-handle rejection'
    assert any(e.get('service') == '0x53' and e.get('status') == 0x0F for e in events), 'No read-only rejection'
    assert any(e.get('service') == '0x4E' and 'class_id=6,' in e.get('path', '') and e.get('status') == 0 for e in events), 'Forward Close failed'
    return {'client': 'pycomm3.LogixDriver', 'client_version': __version__, 'target': target,
            'catalog_adapter': 'Supported symbol attributes plus client template parser and value codec',
            'native_tag_upload': False, 'standard_forward_open_bytes': 256,
            'automatic_fragmented_write_bytes': 1072, 'automatic_fragmented_read_bytes': 1072,
            'record_roundtrip_sha256': hashlib.sha256(json.dumps(roundtrip.value, sort_keys=True).encode()).hexdigest(),
            'small_structure_write_path': 'Multi Service; malformed single-write builder is not used',
            'wrong_handle_rejected': True, 'read_only_write_rejected': True, 'modeled_scan_observed': 70,
            'inputs_restored': True, 'forward_close': True, 'studio_go_online': 'UNVERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True); args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder); app.command('demo', {'sample': 'StructureLab'})
        endpoint = Endpoint(app, 0, True, 'logix-v35-l85e').start()
        try:
            result = check(app, endpoint)
        except Exception:
            Path(args.out).with_suffix('.failure-trace.json').write_text(json.dumps(endpoint.state(True), indent=2), encoding='utf-8')
            raise
        finally:
            endpoint.stop(); app.close()
    Path(args.out).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
