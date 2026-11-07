"""Read-only CIP network metadata for this process's selected IPv4 interface.

Wire layouts follow the published Port and TCP/IP Interface object tables.
This module does not change adapters, resolve DNS names, or forward messages.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from .windows_network import windows_interface
from .ethernet_link import LinkSnapshot, linux_link
from .tcpip_configuration import TcpIpConfiguration, linux_tcpip_configuration
from .linux_network import linux_ipv4_addresses


def cip_string(value):
    raw = value.encode('ascii')
    if len(raw) > 255:
        raise ValueError('Network string is too long')
    return struct.pack('<H', len(raw)) + raw + b'\0' * (len(raw) % 2)


def ethernet_mac(value):
    """Only publish a real unicast Ethernet address; loopback has no MAC."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}', value):
        return None
    raw = bytes.fromhex(value.replace(':', '').replace('-', ''))
    return raw if raw != b'\0' * 6 and not raw[0] & 1 else None


@dataclass(frozen=True)
class InterfaceSnapshot:
    address: str
    netmask: str
    gateway: str = '0.0.0.0'
    dns: tuple = ()
    domain: str = ''
    name: str = ''
    mac: bytes | None = None
    link: LinkSnapshot | None = None
    tcpip: TcpIpConfiguration | None = None

    def __post_init__(self):
        if self.mac is not None and (not isinstance(self.mac, bytes) or len(self.mac) != 6
                                     or self.mac == b'\0' * 6 or self.mac[0] & 1):
            raise ValueError('A physical MAC must contain six unicast Ethernet octets')

    def configuration(self):
        ipaddress.IPv4Network('0.0.0.0/' + self.netmask)
        if len(self.domain.encode('ascii')) > 48:
            raise ValueError('CIP domain name exceeds 48 ASCII characters')
        addresses = (self.address, self.netmask, self.gateway, *(self.dns + ('0.0.0.0',) * 2)[:2])
        # CIP UDINTs are little endian, including their numeric IPv4 values.
        return b''.join(struct.pack('<I', int(ipaddress.IPv4Address(a))) for a in addresses) + cip_string(self.domain)

    def description(self, *, captured_on_first_query=True):
        return {'address': self.address, 'netmask': self.netmask, 'gateway': self.gateway,
                'dns': list(self.dns), 'domain': self.domain, 'interface': self.name,
                'mac_address': self.mac.hex(':') if self.mac else None,
                'ethernet_link': self.link.description() if self.link else None,
                'tcpip_configuration': self.tcpip.description() if self.tcpip else None,
                'writable': False, 'captured_on_first_query': captured_on_first_query}

    def interface_label(self):
        """Installed v35 Ethernet Link field 10: a byte count and 64 characters."""
        if not isinstance(self.name, str):return None
        try:raw=self.name.encode('ascii')
        except UnicodeEncodeError:return None
        if not 1<=len(raw)<=64 or any(c<32 or c>126 for c in raw):return None
        return bytes((len(raw),))+raw


def linux_snapshot(address):
    rows=linux_ipv4_addresses();selected=next((row for row in rows if row.address==address),None)
    if selected is None and ipaddress.IPv4Address(address).is_loopback:
        selected=next((row for row in rows if ipaddress.IPv4Address(row.address).is_loopback
                       and ipaddress.IPv4Address(address) in ipaddress.IPv4Network(
                           row.address+'/'+str(row.prefix),strict=False)),None)
    if selected is None:
        raise ValueError('Selected IPv4 interface was not found')
    name=socket.if_indextoname(selected.index)
    mask=str(ipaddress.IPv4Network('0.0.0.0/'+str(selected.prefix)).netmask)
    gateway = '0.0.0.0'
    routes = []
    for line in Path('/proc/net/route').read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 8 and fields[0] == name and fields[1] == '00000000' and int(fields[3], 16) & 3 == 3:
            routes.append((int(fields[6]), socket.inet_ntoa(bytes.fromhex(fields[2])[::-1])))
    if routes:
        gateway = min(routes)[1]
    dns, domain = [], ''
    for line in Path('/etc/resolv.conf').read_text().splitlines():
        fields = line.split('#', 1)[0].split()
        if len(fields) >= 2 and fields[0] == 'nameserver':
            try:
                value = str(ipaddress.IPv4Address(fields[1]))
            except ipaddress.AddressValueError:
                continue
            if value not in dns:
                dns.append(value)
        if len(fields) >= 2 and fields[0] in ('domain', 'search'):
            domain = fields[1]
    mac = None
    try:
        base = Path('/sys/class/net') / name
        if base.joinpath('type').read_text().strip() == '1':
            mac = ethernet_mac(base.joinpath('address').read_text().strip())
    except OSError:
        pass  # Missing physical-link data must not invalidate IPv4 data.
    return InterfaceSnapshot(address, mask, gateway, tuple(dns[:2]), domain, name, mac, linux_link(name),
                             linux_tcpip_configuration(name, dns))


def windows_snapshot(address):
    value = windows_interface(address)
    if value['address'] != address:
        raise ValueError('Interface query returned another address')
    prefix = value['prefix']
    if isinstance(prefix, bool) or not isinstance(prefix, int) or not 0 <= prefix <= 32:
        raise ValueError('Invalid IPv4 prefix')
    mask = str(ipaddress.IPv4Network('0.0.0.0/' + str(prefix)).netmask)
    return InterfaceSnapshot(address, mask, value['gateway'], tuple(value['dns']), value['domain'], value['name'], ethernet_mac(value.get('mac')))


def interface_snapshot(address):
    """Return verified local configuration or an explicit unavailable reason."""
    try:
        address = str(ipaddress.IPv4Address(address))
        if sys.platform == 'win32':
            value = windows_snapshot(address)
        elif sys.platform.startswith('linux'):
            value = linux_snapshot(address)
        else:
            raise ValueError('Interface queries are not implemented on this platform')
        if value.address != address:
            raise ValueError('Interface query returned another address')
        value.configuration()  # Validate before exposing any configuration.
        return value, None
    except (OSError, ValueError, KeyError, TypeError) as error:
        return None, str(error)


PORT_CLASS_ID = 0xF4
TCPIP_CLASS_ID = 0xF5
ETHERNET_LINK_CLASS_ID = 0xF6
TCPIP_INTERFACE_ATTRIBUTES = frozenset(range(1, 6))
ETHERNET_LINK_ATTRIBUTES = frozenset((1, 2, 3, 6, 7, 8, 9, 10))


@dataclass(frozen=True)
class NetworkBinding:
    address: str
    interface: InterfaceSnapshot | None = None
    hostname: bytes | None = None


def tcpip_class_attributes():
    # The separate management UI is not an embedded HTTP service on this port.
    return {1: b'\1\0', 2: b'\1\0', 3: b'\1\0', 101: b'\0', 102: b'\0'}


def tcpip_interface_attributes(snapshot, hostname, *, include_interface):
    values = {6: hostname} if hostname is not None else {}
    if include_interface:
        values[4] = b'\2\0\x20\xF6\x24\1' if snapshot is not None and snapshot.mac else b'\0\0'
        if snapshot is not None:
            values[1] = struct.pack('<I', 1)
            values[5] = snapshot.configuration()
            if snapshot.tcpip is not None:
                values.update(snapshot.tcpip.attributes())
    return values


def ethernet_link_class_attributes():
    return {1: b'\1\0', 2: b'\1\0', 3: b'\1\0'}


def ethernet_link_attributes(snapshot):
    if snapshot is None:
        return {}
    values = snapshot.link.attributes() if snapshot.link is not None else {}
    if snapshot.mac is not None:
        values[3] = snapshot.mac
    label = snapshot.interface_label()
    if label is not None:
        values[10] = label
    return values


def ethernet_port_segment(address):
    text = str(ipaddress.IPv4Address(address)).encode('ascii')
    return bytes((0x12, len(text))) + text + bytes(len(text) % 2)


def port_attributes(instance, address='127.0.0.1'):
    if instance == 0:
        # Instance zero occupies the first array entry and is reserved as zero.
        return {1: b'\1\0', 2: b'\2\0', 3: b'\2\0', 8: b'\2\0',
                9: struct.pack('<HHHHHH', 0, 0, 1, 1, 4, 2)}
    if instance == 1:
        # Local slot-zero routing exists; a physical backplane object does not.
        return {1: b'\1\0', 2: b'\1\0', 3: b'\0\0',
                4: b'\x09Backplane', 5: b'\x09Backplane', 7: b'\1\0'}
    if instance == 2:
        values = {1: b'\4\0', 2: b'\2\0', 3: b'\2\0\x20\xF5\x24\1',
                  4: b'\x0BEtherNet/IP', 5: b'\x0BEtherNet/IP'}
        if address is not None:
            values[7] = ethernet_port_segment(address)
        return values
    raise KeyError(instance)
