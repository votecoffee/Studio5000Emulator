"""Independent pycomm3 parsing of templates and structured reads, on loopback.

The tag-cache adapter uses documented symbol attributes; template discovery,
template decoding and value decoding use the installed client's implementation.
Native firmware-address tag upload and Studio Go Online are not exercised.
"""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from interop_atomic_transfers import documented_catalog
from logixlab.server import Application
from logixlab.ethernetip import Endpoint


def expected_axis(seed):
    return {'Command': seed, 'Actual': seed + 0.5, 'Samples': list(range(seed, seed + 8))}


def expected_machine(seed):
    return {'Axis': expected_axis(seed), 'History': [expected_axis(seed + i + 1) for i in range(12)],
            'Counters': list(range(seed, seed + 4))}


def check(app, endpoint):
    from pycomm3 import LogixDriver, __version__
    target = f'127.0.0.1:{endpoint.port}'
    with LogixDriver(target + '/0', init_tags=False) as driver:
        assert driver.name == 'StructureLab', driver.info
        # Standard Class 3, 256-byte connection: the client automatically chooses
        # fragmented requests for the fixture's 536-byte record and record array.
        driver._cfg['extended forward open'] = False
        driver._cfg['connection_size'] = 256
        driver._tags = documented_catalog(driver, structures=True)
        assert set(driver.tags) == {'Command', 'Machine', 'Machines'}
        assert driver.data_types['MachineState']['template']['structure_size'] == 536
        assert driver.data_types['AxisState']['template']['structure_size'] == 40
        record = driver.read('Machine'); assert record and record.value == expected_machine(10), record
        records = driver.read('Machines{2}')
        assert records and records.value == [expected_machine(0), expected_machine(100)], records
        nested = driver.read('Machines[1].Axis'); assert nested and nested.value == expected_axis(100), nested
        history = driver.read('Machine.History{12}')
        assert history and history.value == expected_machine(10)['History'], history
        app.command('step', {})
        observed = driver.read('Machine.Axis')
        assert observed and observed.value['Command'] == 7 and observed.value['Actual'] == 7.0, observed
        types = sorted(driver.data_types)
    events = endpoint.state(True)['events']
    for service in ('0x03', '0x4C', '0x52'):
        assert any(e.get('service') == service and e.get('status') in (0, 6) for e in events), service
    assert any(e.get('service') == '0x52' and e.get('status') == 6 for e in events), 'No partial structured response'
    assert any(e.get('service') == '0x4E' and 'class_id=6,' in e.get('path', '') and e.get('status') == 0 for e in events), 'Forward Close failed'
    return {'client': 'pycomm3.LogixDriver', 'client_version': __version__, 'target': target,
            'catalog_adapter': 'Symbol attributes 1,2,8,10; client template parser and value codec',
            'native_tag_upload': False, 'templates': types, 'standard_forward_open_bytes': 256,
            'structured_record_bytes': 536, 'structured_array_bytes': 1072,
            'record_value_sha256': hashlib.sha256(json.dumps(record.value, sort_keys=True).encode()).hexdigest(),
            'nested_member_and_array_reads': True, 'automatic_fragmentation': True,
            'modeled_scan_observed': True, 'endpoint_writes_enabled': endpoint.allow_writes,
            'forward_close': True, 'studio_go_online': 'UNVERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True); args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder); app.command('demo', {'sample': 'StructureLab'})
        endpoint = Endpoint(app, 0, False, 'logix-v35-l85e').start()
        try:
            result = check(app, endpoint)
        except Exception:
            Path(args.out).with_suffix('.failure-trace.json').write_text(json.dumps(endpoint.state(True), indent=2), encoding='utf-8')
            raise
        finally:
            endpoint.stop(); app.close()
    Path(args.out).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
