"""Independent template/value-codec checks for mixed-width aligned numeric UDTs."""
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
    return {'Byte': -5 + seed, 'Short': -1234 - seed, 'Code': 200 + seed, 'Samples': [-4 - seed, 0, 5 + seed]}


def expected_record(seed):
    return {'Prefix': -8 + seed, 'Short': -30000 + seed, 'Bytes': [0, 127, 255 - seed],
            'Wide': -(1 << 63) + seed, 'Count': 100 + seed, 'Words': [1, 32768, 65535 - seed],
            'Group': expected_group(seed), 'Huge': (1 << 64) - 1 - seed, 'Ratio': 1.25 + seed,
            'Trailing': 120 - seed, 'Unsigned': (1 << 32) - 1 - seed}


def check(app, endpoint):
    from pycomm3 import LogixDriver, __version__
    target = f'127.0.0.1:{endpoint.port}'
    with LogixDriver(target + '/0', init_tags=False) as driver:
        assert driver.name == 'LayoutLab', driver.info
        driver._cfg['extended forward open'] = False; driver._cfg['connection_size'] = 256
        driver._tags = documented_catalog(driver, structures=True)
        layout = driver.data_types['MixedRecord']
        assert layout['template']['structure_size'] == 64, layout
        assert [layout['internal_tags'][name]['offset'] for name in layout['attributes']] == [0, 2, 4, 8, 16, 20, 28, 40, 48, 52, 56]
        readonly = driver.read('Record'); assert readonly and readonly.value == expected_record(9), readonly
        original = driver.read('Records{8}'); assert original and original.value == [expected_record(i) for i in range(8)], original
        desired = [expected_record(i + 10) for i in range(8)]
        try:
            written = driver.write(('Records{8}', desired)); assert written, written
            roundtrip = driver.read('Records{8}'); assert roundtrip and roundtrip.value == desired, roundtrip
            assert roundtrip.value[0]['Wide'] == -(1 << 63) + 10
            assert roundtrip.value[0]['Huge'] == (1 << 64) - 11
            # Keep the client's small-write workaround explicit, as in the
            # other acceptance probes; no malformed packets are accepted.
            grouped = driver.write(('Records[0].Group', expected_group(20)), ('Records[1].Group', expected_group(21)))
            assert all(grouped), grouped
            check_groups = driver.read('Records[0].Group', 'Records[1].Group')
            assert all(check_groups) and [r.value for r in check_groups] == [expected_group(20), expected_group(21)], check_groups
            member_arrays = driver.write(('Records[0].Words{3}', [10, 20, 30]), ('Records[0].Group.Samples{3}', [-10, 0, 10]))
            assert all(member_arrays), member_arrays
            arrays = driver.read('Records[0].Words{3}', 'Records[0].Group.Samples{3}')
            assert all(arrays) and [r.value for r in arrays] == [[10, 20, 30], [-10, 0, 10]], arrays
            before = driver.read('Records{8}'); assert before, before
            handle = layout['template']['structure_handle']
            rejected = driver.generic_message(service=0x53, class_code=0x6B, instance=driver.tags['Records']['instance_id'],
                request_data=struct.pack('<HHHI', 0x02A0, handle, 8, 1) + b'\x80', connected=True)
            assert not rejected, 'Nonzero reserved padding was accepted'
            after = driver.read('Records{8}'); assert after and after.value == before.value, after
            app.command('step', {})
            observed = driver.read('Observed'); assert observed and observed.value == 110, observed
        finally:
            restored = driver.write(('Records{8}', original.value)); assert restored, restored
            verified = driver.read('Records{8}'); assert verified and verified.value == original.value, verified
    events = endpoint.state(True)['events']
    assert any(e.get('service') == '0x53' and e.get('status') == 9 for e in events), 'Padding rejection not observed'
    for service in ('0x4D', '0x53', '0x52'):
        assert any(e.get('service') == service and e.get('status') == 0 for e in events), service
    assert any(e.get('service') == '0x4E' and 'class_id=6,' in e.get('path', '') and e.get('status') == 0 for e in events)
    return {'client': 'pycomm3.LogixDriver', 'client_version': __version__, 'target': target,
            'catalog_adapter': 'Supported symbol attributes plus client template parser and value codec',
            'native_tag_upload': False, 'record_bytes': 64, 'record_array_bytes': 512,
            'numeric_types': ['SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL'],
            'exact_64_bit_values': True, 'nested_alignment': True, 'nonzero_padding_rejected': True,
            'atomic_arrays_inside_record_arrays': True,
            'small_structure_write_path': 'Multi Service', 'automatic_fragmentation': True,
            'roundtrip_sha256': hashlib.sha256(json.dumps(roundtrip.value, sort_keys=True).encode()).hexdigest(),
            'modeled_scan_observed': 110, 'inputs_restored': True, 'forward_close': True, 'studio_go_online': 'UNVERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True); args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder); app.command('demo', {'sample': 'LayoutLab'})
        endpoint = Endpoint(app, 0, True, 'logix-v35-l85e').start()
        try: result = check(app, endpoint)
        except Exception:
            Path(args.out).with_suffix('.failure-trace.json').write_text(json.dumps(endpoint.state(True), indent=2), encoding='utf-8')
            raise
        finally: endpoint.stop(); app.close()
    Path(args.out).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
