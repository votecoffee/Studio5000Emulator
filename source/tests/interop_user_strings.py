"""Independent user-string template and value codec on an isolated loopback target."""
import argparse
import base64
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logixlab import __version__ as app_version
from logixlab.server import Application
from logixlab.ethernetip import Endpoint
from interop_atomic_transfers import documented_catalog
from test_string_transfers import fixture


def check(endpoint, app):
    from pycomm3 import LogixDriver, __version__
    with LogixDriver(f'127.0.0.1:{endpoint.port}/0', init_tags=False) as client:
        # Initial controller-name discovery may already open a connection.
        # Discover metadata at 128 bytes, then negotiate a genuinely small
        # connection for the client's automatic array fragmentation.
        assert client._forward_close()
        client._cfg['extended forward open'] = False
        client._cfg['connection_size'] = 128
        client._tags = documented_catalog(client, structures=True)
        values = [client.read(name) for name in ('Text', 'Texts{2}', 'Record')]
        assert all(values), values
        assert values[0].value == 'abc', values
        assert values[1].value == ['alpha', '\xff\x80'], values
        assert values[2].value == {'Sequence': 7, 'Text': 'abc'}, values
        assert client._forward_close()
        client._cfg['connection_size'] = 24
        fragmented = client.read('Texts{2}')
        assert fragmented and fragmented.value == ['alpha', '\xff\x80'], fragmented
        written = client.write(('Texts{2}', ['one', 'two']))
        assert written, written
        readback = client.read('Texts{2}')
        assert readback and readback.value == ['one', 'two'], readback
        assert client._forward_close()
        client._cfg['connection_size'] = 128
        # Use the client's valid Multiple Service write path for small records.
        denied = client.write(('Readonly', 'blocked'), ('Text', 'yes'))
        assert not denied[0] and denied[1], denied
        assert app.engine.memory.string('Text') == 'yes'
        assert client._forward_close()
    events = endpoint.state(True)['events']
    assert any(e.get('service') == '0x52' and e.get('status') == 6 for e in events)
    assert any(e.get('service') == '0x53' and e.get('status') == 0 for e in events)
    return {'app_version': app_version, 'client': 'pycomm3', 'client_version': __version__,
            'catalog_adapter': 'Supported symbol attributes; independent template and value codec',
            'fragment_connection_bytes': 24, 'user_string_size': 16,
            'scalar_array_nested_reads': True, 'fragmented_read_write': True,
            'readonly_tag_rejected': True, 'forward_close': True,
            'native_tag_upload': False, 'studio_go_online': 'UNVERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder)
        app.command('load', {'name': 'StringWireLab.L5X',
                            'content': base64.b64encode(fixture()).decode()})
        endpoint = Endpoint(app, 0, True).start()
        try:
            result = check(endpoint, app)
        except Exception:
            args.out.with_suffix('.failure-trace.json').write_text(json.dumps(endpoint.state(True), indent=2), encoding='utf-8')
            raise
        finally:
            endpoint.stop(); app.close()
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
