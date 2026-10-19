"""Linux datagram check on an explicitly selected local Ethernet interface."""
import argparse
import copy
import json
import socket
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logixlab.ethernetip import Endpoint
from logixlab.server import Application


HEADER = struct.Struct('<HHII8sI')


def check(app, endpoint):
    state = endpoint.state()
    discovery = state['discovery']
    assert discovery['broadcast_enabled'], discovery['reason']
    before = copy.deepcopy(app.engine.memory.values)
    index = socket.if_nametoindex(discovery['interface'])
    source = socket.inet_aton(endpoint.bind_address)
    # Independently encode Linux in_pktinfo; never let limited broadcast route
    # through another interface on a machine with more than one adapter.
    ancillary = [(socket.IPPROTO_IP, 8, struct.pack('=I4s4s', index, source, b'\0'*4))]
    targets = [endpoint.bind_address, *discovery['broadcast_addresses']]
    replies = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        client.bind((endpoint.bind_address, 0))
        client.settimeout(2)
        for command in (0x63, 4, 0x64):
            expected = None
            for destination in targets:
                context = len(replies).to_bytes(8, 'little')
                client.sendmsg([HEADER.pack(command, 0, 0, 0, context, 0)], ancillary, 0, (destination, endpoint.port))
                raw, peer = client.recvfrom(4096)
                assert peer == (endpoint.bind_address, endpoint.port), peer
                fields = HEADER.unpack_from(raw)
                assert fields == (command, len(raw)-24, 0, 0, context, 0), fields
                if expected is None:
                    expected = raw[24:]
                assert raw[24:] == expected
                if command == 0x63:
                    assert struct.unpack_from('<HHH', expected) == (1, 0x0C, len(expected)-6)
                    assert expected[12:16] == source
                replies.append({'command': hex(command), 'destination': destination, 'reply_source': peer[0]})
        client.settimeout(0.2)
        for destination in discovery['broadcast_addresses']:
            # RegisterSession and a nonzero-status reply must not get a response.
            for invalid in (HEADER.pack(0x65, 4, 0, 0, b'INVALID1', 0)+b'\1\0\0\0',
                            HEADER.pack(0x63, 0, 0, 1, b'INVALID2', 0),
                            HEADER.pack(0x63, 0, 0, 0, b'INVALID3', 0)+b'x'):
                client.sendmsg([invalid], ancillary, 0, (destination, endpoint.port))
                try:
                    client.recvfrom(4096)
                except socket.timeout:
                    pass
                else:
                    raise AssertionError('Invalid broadcast datagram received a response')
    assert app.engine.memory.values == before
    counts = endpoint.state()['counts']
    assert counts.get('broadcast_discovery') == 6, counts
    assert counts.get('broadcast_ignored') == 6, counts
    return {'app_version': app.state()['app_version'], 'read_only_target': not endpoint.allow_writes,
            'selected_interface': discovery['interface'], 'bind_address': endpoint.bind_address,
            'valid_exchanges': replies, 'invalid_broadcasts_ignored': 6,
            'all_reply_sources_match_plc_ip': True, 'broadcast_payloads_match_unicast': True,
            'application_memory_preserved': True, 'linx_range_browsing': 'NOT VERIFIED',
            'studio_go_online': 'NOT VERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind-address', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if not sys.platform.startswith('linux'):
        parser.error('This probe requires Linux recvmsg/sendmsg and a local Ethernet interface')
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder)
        app.command('demo', {'sample': 'ConveyorDemo'})
        endpoint = Endpoint(app, 0, False, 'logix-v35-l85e', args.bind_address).start()
        app.endpoint = endpoint
        try:
            result = check(app, endpoint)
        finally:
            app.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
