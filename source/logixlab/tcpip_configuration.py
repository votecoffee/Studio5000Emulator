"""Read-only CIP configuration flags for a verified Linux DHCP client.

Only the bounded ifupdown/udhcpc combination is recognized. Other network
managers and ambiguous configurations remain unavailable; no network setting
is changed and no client process is started.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import struct


@dataclass(frozen=True)
class TcpIpConfiguration:
    dns_enabled: bool

    def __post_init__(self):
        if type(self.dns_enabled) is not bool:
            raise ValueError('Invalid DNS configuration state')

    def attributes(self):
        # DHCP client and system DNS resolver support. Configuration
        # Settable stays clear: CIP setters do not control the host OS.
        return {2: struct.pack('<I', 6),
                3: struct.pack('<I', 2 | (16 if self.dns_enabled else 0))}

    def description(self):
        return {'startup': 'DHCP', 'dns_enabled': self.dns_enabled,
                'source': 'Linux ifupdown configuration and active udhcpc client',
                'configuration_settable': False, 'writable': False}


def linux_tcpip_configuration(name, dns):
    """Recognize one explicit DHCP stanza and its live, matching client."""
    try:
        if not isinstance(name, str) or name in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', name):
            return None
        text = Path('/etc/network/interfaces').read_text()
        if len(text) > 65536:
            return None
        stanzas = []
        for line in text.splitlines():
            fields = line.split('#', 1)[0].split()
            if fields and fields[0] in ('source', 'source-directory', 'mapping'):
                return None  # Included or mapped definitions could override it.
            if fields[:2] == ['iface', name] and len(fields) < 4:
                return None
            if len(fields) >= 3 and fields[:3] == ['iface', name, 'inet']:
                stanzas.append(fields)
        if stanzas != [['iface', name, 'inet', 'dhcp']]:
            return None
        pid = Path('/run', 'udhcpc.' + name + '.pid').read_text().strip()
        if not re.fullmatch(r'[1-9][0-9]{0,9}', pid):
            return None
        raw = Path('/proc', pid, 'cmdline').read_bytes()
        if not raw.endswith(b'\0') or len(raw) > 8192:
            return None
        args = raw[:-1].decode('ascii').split('\0')
        if not args or Path(args[0]).name != 'udhcpc':
            return None
        positions = [i for i, value in enumerate(args) if value == '-i']
        if len(positions) != 1 or positions[0] + 1 >= len(args) or args[positions[0]+1] != name:
            return None
        # A stale PID file can name a different client on the same interface.
        positions = [i for i, value in enumerate(args) if value == '-p']
        if len(positions) != 1 or positions[0] + 1 >= len(args):
            return None
        if args[positions[0]+1] not in ('/run/udhcpc.'+name+'.pid', '/var/run/udhcpc.'+name+'.pid'):
            return None
        return TcpIpConfiguration(bool(dns))
    except (OSError, UnicodeError, ValueError, TypeError):
        return None
