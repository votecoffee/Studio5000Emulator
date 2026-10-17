"""Independent client codec checks for explicit packed-BIT UDT transfers."""
import argparse
import hashlib
import json
import struct
import tempfile
from pathlib import Path
from interop_atomic_transfers import documented_catalog
from logixlab.server import Application
from logixlab.ethernetip import Endpoint


def expected_group(seed):
    return {'Enabled': bool(seed & 1), 'Valid': bool(seed & 4), 'High': bool(seed & 128), 'Code': seed - 100}


def expected_record(seed):
    return {'Ready': bool(seed & 1), 'Running': bool(seed & 8), 'Fault': bool(seed & 128),
            'Remote': bool(seed & 1), 'Count': seed * 10, 'Group': expected_group(seed),
            'History': [expected_group(seed + i + 1) for i in range(4)]}


def check(app, endpoint):
    from pycomm3 import LogixDriver, __version__
    target = f'127.0.0.1:{endpoint.port}'
    with LogixDriver(target + '/0', init_tags=False) as driver:
        assert driver.name == 'FlagLab', driver.info
        driver._cfg['extended forward open'] = False; driver._cfg['connection_size'] = 256
        driver._tags = documented_catalog(driver, structures=True)
        layout = driver.data_types['FlagRecord']; assert layout['template']['structure_size'] == 28
        for name, offset, bit in (('Ready', 0, 0), ('Running', 0, 3), ('Fault', 0, 7), ('Remote', 1, 1)):
            metadata = layout['internal_tags'][name]
            assert (metadata['offset'], metadata['bit']) == (offset, bit), metadata
        assert not any(name.startswith('ZZZZ') for name in layout['attributes'])
        readonly = driver.read('Record'); assert readonly and readonly.value == expected_record(137), readonly
        original = driver.read('Records{12}')
        assert original and original.value == [expected_record(i) for i in range(12)], original
        desired = [expected_record(i + 137) for i in range(12)]
        try:
            written = driver.write(('Records{12}', desired)); assert written, written
            roundtrip = driver.read('Records{12}'); assert roundtrip and roundtrip.value == desired, roundtrip
            # Use the installed client's valid Multi Service path for small
            # writes; its single-write builder can duplicate payload bytes.
            groups = driver.write(('Records[0].Group', expected_group(133)), ('Records[1].Group', expected_group(0)))
            assert all(groups), groups
            readback = driver.read('Records[0].Group', 'Records[1].Group')
            assert all(readback) and [v.value for v in readback] == [expected_group(133), expected_group(0)], readback
            bits = driver.write(('Records[0].Running', False), ('Records[1].Fault', False))
            assert all(bits), bits
            changed = driver.read('Records[0]', 'Records[1]'); assert all(changed), changed
            assert changed[0].value['Ready'] and changed[0].value['Fault'] and not changed[0].value['Running']
            assert not changed[1].value['Fault']
            before = driver.read('Records{12}'); assert before, before
            handle = layout['template']['structure_handle']
            reserved = driver.generic_message(service=0x53, class_code=0x6B, instance=driver.tags['Records']['instance_id'],
                request_data=struct.pack('<HHHI', 0x02A0, handle, 12, 0) + b'\x02', connected=True)
            assert not reserved, 'An unmapped host bit was accepted'
            after = driver.read('Records{12}'); assert after and after.value == before.value, after
            denied = driver.generic_message(service=0x53, class_code=0x6B, instance=driver.tags['Record']['instance_id'],
                request_data=struct.pack('<HHHI', 0x02A0, handle, 1, 0) + b'\0', connected=True)
            assert not denied, 'Read Only record was written'
            app.command('step', {})
            observed = driver.read('Observed', 'ObservedCount'); assert all(observed), observed
            assert [value.value for value in observed] == [True, 1370], observed
        finally:
            restored = driver.write(('Records{12}', original.value)); assert restored, restored
            verified = driver.read('Records{12}'); assert verified and verified.value == original.value, verified
            app.command('step', {})
    events = endpoint.state(True)['events']
    for service in ('0x4D', '0x53', '0x52'):
        assert any(e.get('service') == service and e.get('status') == 0 for e in events), service
    assert any(e.get('service') == '0x53' and e.get('status') == 9 for e in events)
    assert any(e.get('service') == '0x53' and e.get('status') == 0x0F for e in events)
    assert any(e.get('service') == '0x4E' and 'class_id=6,' in e.get('path', '') and e.get('status') == 0 for e in events)
    return {'client': 'pycomm3.LogixDriver', 'client_version': __version__, 'target': target,
            'catalog_adapter': 'Supported symbol attributes plus client template parser and value codec',
            'native_tag_upload': False, 'record_bytes': 28, 'record_array_bytes': 336,
            'packed_bits': [0, 1, 2, 3, 7], 'multiple_hosts': True, 'nested_record_arrays': True,
            'hidden_hosts_excluded_from_public_values': True, 'automatic_fragmentation': True,
            'unused_host_bits_rejected': True, 'read_only_write_rejected': True,
            'small_write_path': 'Multi Service', 'direct_bool_writes': True,
            'roundtrip_sha256': hashlib.sha256(json.dumps(roundtrip.value, sort_keys=True).encode()).hexdigest(),
            'modeled_scan_observed': [True, 1370], 'inputs_restored': True,
            'forward_close': True, 'studio_go_online': 'UNVERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True); args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder); app.command('demo', {'sample': 'FlagLab'})
        endpoint = Endpoint(app, 0, True, 'logix-v35-l85e').start()
        try: result = check(app, endpoint)
        except Exception:
            Path(args.out).with_suffix('.failure-trace.json').write_text(json.dumps(endpoint.state(True), indent=2), encoding='utf-8')
            raise
        finally: endpoint.stop(); app.close()
    Path(args.out).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
