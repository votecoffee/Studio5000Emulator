"""Read-only CIP network metadata for this process's selected IPv4 interface.

Wire layouts follow the published Port and TCP/IP Interface object tables.
This module does not change adapters, resolve DNS names, or forward messages.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def cip_string(value):
    raw = value.encode('ascii')
    if len(raw) > 255:
        raise ValueError('Network string is too long')
    return struct.pack('<H', len(raw)) + raw + b'\0' * (len(raw) % 2)


@dataclass(frozen=True)
class InterfaceSnapshot:
    address: str
    netmask: str
    gateway: str = '0.0.0.0'
    dns: tuple = ()
    domain: str = ''
    name: str = ''

    def configuration(self):
        ipaddress.IPv4Network('0.0.0.0/' + self.netmask)
        if len(self.domain.encode('ascii')) > 48:
            raise ValueError('CIP domain name exceeds 48 ASCII characters')
        addresses = (self.address, self.netmask, self.gateway, *(self.dns + ('0.0.0.0',) * 2)[:2])
        # CIP UDINTs are little endian, including their numeric IPv4 values.
        return b''.join(struct.pack('<I', int(ipaddress.IPv4Address(a))) for a in addresses) + cip_string(self.domain)

    def description(self):
        return {'address': self.address, 'netmask': self.netmask, 'gateway': self.gateway,
                'dns': list(self.dns), 'domain': self.domain, 'interface': self.name,
                'writable': False, 'captured_on_first_query': True}


def linux_snapshot(address):
    import fcntl
    selected = None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        for _, name in socket.if_nameindex():
            request = struct.pack('256s', name.encode()[:15])
            try:
                local = socket.inet_ntoa(fcntl.ioctl(probe, 0x8915, request)[20:24])
                mask = socket.inet_ntoa(fcntl.ioctl(probe, 0x891B, request)[20:24])
            except OSError:
                continue
            if local == address or (ipaddress.IPv4Address(address).is_loopback
                                    and ipaddress.IPv4Address(local).is_loopback
                                    and ipaddress.IPv4Address(address) in ipaddress.IPv4Network(local + '/' + mask, strict=False)):
                selected = name, mask
                break
    if selected is None:
        raise ValueError('Selected IPv4 interface was not found')
    name, mask = selected
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
    return InterfaceSnapshot(address, mask, gateway, tuple(dns[:2]), domain, name)


WINDOWS_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$selected = Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -eq $env:LOGIXLAB_INTERFACE_ADDRESS | Select-Object -First 1
if (-not $selected -and $env:LOGIXLAB_INTERFACE_ADDRESS.StartsWith('127.')) {
    $selected = Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -eq '127.0.0.1' | Select-Object -First 1
}
if (-not $selected) { throw 'Selected IPv4 interface was not found' }
$dns = @(Get-DnsClientServerAddress -InterfaceIndex $selected.InterfaceIndex -AddressFamily IPv4 | ForEach-Object ServerAddresses)
$route = Get-NetRoute -InterfaceIndex $selected.InterfaceIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1
$domain = (Get-DnsClient -InterfaceIndex $selected.InterfaceIndex -ErrorAction SilentlyContinue).ConnectionSpecificSuffix
@{address=$env:LOGIXLAB_INTERFACE_ADDRESS; prefix=$selected.PrefixLength; gateway=$(if ($route) {$route.NextHop} else {'0.0.0.0'}); dns=$dns; domain=[string]$domain; name=$selected.InterfaceAlias} | ConvertTo-Json -Compress
"""


def windows_snapshot(address):
    environment = dict(os.environ, LOGIXLAB_INTERFACE_ADDRESS=address)
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', WINDOWS_QUERY],
                            capture_output=True, timeout=12, env=environment, creationflags=0x08000000)
    if result.returncode:
        raise ValueError('Windows IPv4 interface query failed')
    value = json.loads(result.stdout.decode('utf-8-sig'))
    if value['address'] != address:
        raise ValueError('Interface query returned another address')
    prefix = value['prefix']
    if isinstance(prefix, bool) or not isinstance(prefix, int) or not 0 <= prefix <= 32:
        raise ValueError('Invalid IPv4 prefix')
    mask = str(ipaddress.IPv4Network('0.0.0.0/' + str(prefix)).netmask)
    return InterfaceSnapshot(address, mask, value['gateway'], tuple(value['dns']), value['domain'], value['name'])


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
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        return None, str(error)


def port_attributes(instance):
    if instance == 0:
        # Instance zero occupies the first array entry and is reserved as zero.
        return {1: b'\1\0', 2: b'\2\0', 3: b'\2\0', 8: b'\2\0',
                9: struct.pack('<HHHHHH', 0, 0, 1, 1, 4, 2)}
    if instance == 1:
        # Local slot-zero routing exists; a physical backplane object does not.
        return {1: b'\1\0', 2: b'\1\0', 3: b'\0\0',
                4: b'\x09Backplane', 5: b'\x09Backplane'}
    if instance == 2:
        return {1: b'\4\0', 2: b'\2\0', 3: b'\2\0\x20\xF5\x24\1',
                4: b'\x0BEtherNet/IP', 5: b'\x0BEtherNet/IP'}
    raise KeyError(instance)
