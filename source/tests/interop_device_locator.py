"""Independent Flash_LEDs client checks against an isolated read-only target."""
import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logixlab.server import Application
from logixlab.ethernetip import Endpoint


def check(app, endpoint):
    from pycomm3 import LogixDriver, __version__
    target = f'127.0.0.1:{endpoint.port}'
    before = copy.deepcopy(app.engine.memory.values); source = app.engine.project.sha256
    with LogixDriver(target + '/0', init_tags=False) as driver:
        driver._cfg['extended forward open'] = False; driver._cfg['connection_size'] = 256
        def send(payload):
            result = driver.generic_message(service=0x4B, class_code=1, instance=1,
                request_data=payload, connected=True, return_response_packet=True)
            return result.value
        stopped = send(b'\0'); assert stopped.service_status == 0 and stopped.data == b''
        assert not app.connectivity()['locator']['active']
        try:
            started = send(b'\x09'); assert started.service_status == 0 and started.data == b''
            state = app.connectivity()['locator']; assert state['active'] and 0 < state['remaining_ms'] <= 9000
            first = state['request_id']
            replaced = send(b'\x1E'); assert replaced.service_status == 0
            state = app.connectivity()['locator']; assert state['active'] and 29000 < state['remaining_ms'] <= 30000
            assert state['request_id'] != first
            for payload, expected in ((b'\x01', 3), (b'', 0x13), (b'\x09\0', 0x15)):
                rejected = send(payload); assert rejected.service_status == expected
                assert app.connectivity()['locator']['request_id'] == state['request_id']
            assert app.engine.memory.values == before and app.engine.project.sha256 == source
        finally:
            final = send(b'\0'); assert final.service_status == 0
        assert not app.connectivity()['locator']['active']
    events = endpoint.state(True)['events']
    assert any(e.get('service') == '0x4B' and e.get('status') == 0 for e in events)
    return {'client': 'pycomm3.LogixDriver', 'client_version': __version__, 'target': target,
            'class': 1, 'instance': 1, 'service': '0x4B', 'readonly_endpoint': not endpoint.allow_writes,
            'zero_duration_stop': True, 'nine_second_start': True, 'replacement_duration': True,
            'invalid_duration_rejected': True, 'malformed_lengths_rejected': True,
            'application_memory_preserved': True, 'indicator_stopped': True,
            'factorytalk_linx_button': 'MANUAL VALIDATION PENDING', 'studio_go_online': 'UNVERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True); args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder); app.command('demo', {'sample': 'ConveyorDemo'})
        endpoint = Endpoint(app, 0, False, 'logix-v35-l85e').start(); app.endpoint = endpoint
        try: result = check(app, endpoint)
        except Exception:
            Path(args.out).with_suffix('.failure-trace.json').write_text(json.dumps(endpoint.state(True), indent=2), encoding='utf-8')
            raise
        finally: app.close()
    Path(args.out).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
