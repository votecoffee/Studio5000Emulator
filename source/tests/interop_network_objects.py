"""Independent CIP client against a temporary read-only network-metadata target."""
import argparse
import copy
import ipaddress
import json
import socket
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logixlab.server import Application
from logixlab.ethernetip import Endpoint


def check(app, endpoint):
    from pycomm3 import LogixDriver, __version__
    from pycomm3.cip import PADDED_EPATH, PortSegment
    before = copy.deepcopy(app.engine.memory.values)
    with LogixDriver(f'127.0.0.1:{endpoint.port}/0', init_tags=False) as driver:
        driver._cfg['extended forward open'] = False
        driver._cfg['connection_size'] = 256
        def read(class_id, instance, attribute=None, service=0x0E, data=b''):
            result = driver.generic_message(service=service, class_code=class_id, instance=instance,
                attribute=attribute if attribute is not None else b'', request_data=data,
                connected=True, return_response_packet=True)
            return result.value
        ports = read(0xF4, 0, service=1)
        assert ports.service_status == 0
        assert ports.data == bytes.fromhex('0100020002000200000000000100010004000200')
        entry = read(0xF4, 0, 8)
        assert entry.service_status == 0 and entry.data == b'\2\0'
        link = read(0xF4, 2, 3)
        assert link.service_status == 0 and link.data == b'\2\0\x20\xf5\x24\1'
        node = read(0xF4, 2, 7)
        assert node.service_status == 0 and node.data == PADDED_EPATH.encode([PortSegment(2, '127.0.0.1')])
        backplane = read(0xF4, 1, 7)
        assert backplane.service_status == 0 and backplane.data == PADDED_EPATH.encode([PortSegment(1, 0)])
        config = read(0xF5, 1, 5)
        assert config.service_status == 0, endpoint.state()['network_interface_error']
        addresses = [str(ipaddress.IPv4Address(n)) for n in struct.unpack_from('<5I', config.data)]
        assert addresses[0] == '127.0.0.1'
        domain_size = struct.unpack_from('<H', config.data, 20)[0]
        assert len(config.data) == 22 + domain_size + domain_size % 2
        hostname = read(0xF5, 1, 6)
        assert hostname.service_status == 0
        size = struct.unpack_from('<H', hostname.data)[0]
        assert hostname.data[2:2+size].decode('ascii') == socket.gethostname()
        physical = read(0xF5, 1, 4)
        assert physical.service_status == 0
        snapshot = endpoint.state()['network_interface']
        mac = read(0xF6, 1, 3)
        if snapshot['mac_address']:
            assert physical.data == b'\2\0\x20\xf6\x24\1'
            assert mac.service_status == 0 and mac.data == bytes.fromhex(snapshot['mac_address'].replace(':', ''))
        else:
            assert physical.data == b'\0\0' and mac.service_status == 0x0C
        assert read(0xF4, 3, 3).service_status == 5
        assert read(0xF5, 1, 5, service=0x10, data=config.data).service_status == 8
        assert read(0xF4, 2, 99).service_status == 0x14
        mixed = read(0xF4, 2, service=3, data=struct.pack('<4H', 3, 1, 99, 2))
        assert mixed.service_status == 0x0A
    assert app.engine.memory.values == before
    return {'client': 'pycomm3.LogixDriver', 'client_version': __version__,
            'app_version': app.state()['app_version'], 'read_only_target': not endpoint.allow_writes,
            'port_inventory': True, 'entry_port': 2, 'ethernet_link_to_tcpip': True,
            'node_addresses_match_independent_path_encoder': True,
            'mac_matches_selected_interface_or_explicitly_unavailable': True,
            'interface_addresses': addresses, 'configuration_writes_rejected': True,
            'unknown_instance_and_attribute_rejected': True, 'mixed_attribute_statuses': True,
            'application_memory_preserved': True, 'studio_go_online': 'NOT VERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder)
        app.command('demo', {'sample': 'ConveyorDemo'})
        endpoint = Endpoint(app, 0, False, 'logix-v35-l85e').start()
        app.endpoint = endpoint
        try:
            result = check(app, endpoint)
        finally:
            app.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
