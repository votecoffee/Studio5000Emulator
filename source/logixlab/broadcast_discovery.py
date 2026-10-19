"""Linux IPv4 discovery sockets, restricted to the selected Ethernet interface.

The unicast listener stays bound to the configured PLC IP. Separate sockets
receive directed/limited broadcasts; IP_PKTINFO selects the interface and pins
the unicast reply source. No wildcard socket or privileged network API is used.
"""
from __future__ import annotations

import ipaddress
import socket
import socketserver
import struct
import sys
from dataclasses import dataclass
from .network_objects import interface_snapshot

# Linux UAPI values; IP_PKTINFO is not exposed by every Python build.
PKTINFO = 8
TRUNCATED = 0x08 | 0x20  # MSG_CTRUNC | MSG_TRUNC
INFO = struct.Struct('=I4s4s')
HEADER = struct.Struct('<HHII8sI')


@dataclass(frozen=True)
class DiscoveryInterface:
    address: str
    netmask: str
    index: int

    @property
    def destinations(self):
        network = ipaddress.IPv4Network(self.address + '/' + self.netmask, strict=False)
        return (str(network.broadcast_address), '255.255.255.255')

    def accepts(self, ancillary, flags, destination):
        if flags & TRUNCATED or destination not in self.destinations:
            return False
        values = [data for level, kind, data in ancillary if level == socket.IPPROTO_IP and kind == PKTINFO]
        if len(values) != 1 or len(values[0]) != INFO.size:
            return False
        index, local, target = INFO.unpack(values[0])
        return (index == self.index and local == socket.inet_aton(self.address)
                and target == socket.inet_aton(destination))

    def reply_info(self):
        return INFO.pack(self.index, socket.inet_aton(self.address), b'\0' * 4)


def discovery_request(raw):
    if len(raw) != HEADER.size:
        return False
    command, size, session, status, _, options = HEADER.unpack(raw)
    return command in (4, 0x63, 0x64) and size == session == status == options == 0


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        raw, ancillary, flags = self.request
        self.server.respond(raw, ancillary, flags, self.client_address)


class BroadcastServer(socketserver.UDPServer):
    allow_reuse_address = False

    def __init__(self, address, interface, reply, record):
        self.interface = interface
        self.reply = reply
        self.record = record
        super().__init__(address, _Handler)

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.socket.setsockopt(socket.IPPROTO_IP, PKTINFO, 1)
        super().server_bind()

    def get_request(self):
        # Valid broadcast requests have only the 24-byte encapsulation header.
        raw, ancillary, flags, peer = self.socket.recvmsg(HEADER.size + 1, socket.CMSG_SPACE(INFO.size))
        return (raw, ancillary, flags), peer

    def respond(self, raw, ancillary, flags, peer):
        destination = self.server_address[0]
        if not self.interface.accepts(ancillary, flags, destination) or not discovery_request(raw) or not peer[1]:
            self.record('broadcast_ignored', destination=destination)
            return
        response = self.reply(raw, peer)
        if response is not None:
            try:
                self.socket.sendmsg([response], [(socket.IPPROTO_IP, PKTINFO, self.interface.reply_info())], 0, peer)
            except OSError as error:
                self.record('broadcast_error', destination=destination, detail=str(error))
                return
            self.record('broadcast_discovery', destination=destination, interface_index=self.interface.index)


def prepare_broadcasts(address, port, reply, record):
    """Optional discovery; failed setup closes every extra socket, preserving unicast."""
    status = {'broadcast_enabled': False, 'broadcast_addresses': [], 'interface': None, 'reason': None}
    if not sys.platform.startswith('linux'):
        status['reason'] = 'Broadcast discovery sockets are implemented on Linux only'
        return [], status
    if ipaddress.IPv4Address(address).is_loopback:
        status['reason'] = 'Loopback endpoints use unicast discovery'
        return [], status
    servers = []
    try:
        snapshot, error = interface_snapshot(address)
        if snapshot is None:
            raise ValueError(error or 'Selected interface metadata is unavailable')
        network = ipaddress.IPv4Network(address + '/' + snapshot.netmask, strict=False)
        if not snapshot.mac or network.prefixlen >= 31:
            raise ValueError('Broadcast discovery requires an Ethernet interface with a subnet prefix shorter than /31')
        interface = DiscoveryInterface(address, snapshot.netmask, socket.if_nametoindex(snapshot.name))
        if interface.index <= 0:
            raise ValueError('Selected interface index is unavailable')
        for destination in interface.destinations:
            servers.append(BroadcastServer((destination, port), interface, reply, record))
        status.update(broadcast_enabled=True, broadcast_addresses=list(interface.destinations), interface=snapshot.name)
    except (OSError, ValueError) as error:
        for server in servers:
            server.server_close()
        return [], {**status, 'reason': str(error)}
    return servers, status
