"""Read-only Ethernet Link fields reported by the selected Linux interface.

Missing ethtool support leaves these optional fields unavailable. No hardware
counters, negotiation settings or adapters are fabricated or modified.
"""
import ctypes
import re
import socket
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LinkSnapshot:
    speed: int
    full_duplex: bool
    autonegotiation: bool
    carrier: bool
    enabled: bool
    interface_type: int

    def __post_init__(self):
        if type(self.speed) is not int or not 1 <= self.speed <= 65535:
            raise ValueError('Unavailable or unrepresentable Ethernet speed')
        if any(type(v) is not bool for v in (self.full_duplex, self.autonegotiation, self.carrier, self.enabled)):
            raise ValueError('Invalid Ethernet link state')
        if type(self.interface_type) is not int or self.interface_type not in (0, 1, 2, 3):
            raise ValueError('Invalid Ethernet interface type')

    def attributes(self):
        negotiation = (3 if self.carrier else 0) if self.autonegotiation else 4
        flags = int(self.carrier) | (int(self.full_duplex) << 1) | (negotiation << 2)
        control = 1 if self.autonegotiation else int(self.full_duplex) << 1
        state = 1 if self.enabled and self.carrier else 2 if not self.enabled else 0
        return {1: struct.pack('<I', self.speed), 2: struct.pack('<I', flags),
                6: struct.pack('<HH', control, 0 if self.autonegotiation else self.speed),
                7: bytes((self.interface_type,)), 8: bytes((state,)),
                9: bytes((1 if self.enabled else 2,))}

    def description(self):
        return {'speed_mbps': self.speed, 'full_duplex': self.full_duplex,
                'autonegotiation': self.autonegotiation, 'carrier': self.carrier,
                'enabled': self.enabled, 'interface_type': self.interface_type,
                'source': 'Linux sysfs and read-only ETHTOOL_GSET',
                'negotiation_status': 'Inferred from carrier and autonegotiation configuration',
                'counter_status': 'See endpoint ethernet_counters for on-demand diagnostic coverage',
                'writable': False}


def linux_link(name):
    """Read one interface; failure must not invalidate its IPv4/MAC snapshot."""
    try:
        if not isinstance(name, str) or name in ('.','..') or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', name):
            raise ValueError('Invalid Ethernet interface name')
        import fcntl
        base = Path('/sys/class/net') / name
        if base.joinpath('type').read_text().strip() != '1':
            return None  # Loopback, tunnels and non-Ethernet media.
        carrier = base.joinpath('carrier').read_text().strip()
        if carrier not in ('0', '1'):
            return None
        flags = int(base.joinpath('flags').read_text().strip(), 16)
        # struct ethtool_cmd is 44 bytes. ETHTOOL_GSET is a read-only ioctl.
        command = ctypes.create_string_buffer(44)
        struct.pack_into('=I', command, 0, 1)
        pointer_size = struct.calcsize('P')
        request = struct.pack('16sP', name.encode('ascii'), ctypes.addressof(command)) + bytes(24 - pointer_size)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            fcntl.ioctl(probe, 0x8946, request)
        raw = command.raw
        speed = struct.unpack_from('=H', raw, 12)[0] | (struct.unpack_from('=H', raw, 28)[0] << 16)
        duplex, port, autoneg = raw[14], raw[15], raw[18]
        if duplex not in (0, 1) or autoneg not in (0, 1):
            return None
        return LinkSnapshot(speed, bool(duplex), bool(autoneg), carrier == '1', bool(flags & 1),
                            {0: 2, 3: 3}.get(port, 0))
    except (ImportError, OSError, ValueError, TypeError, struct.error):
        return None
