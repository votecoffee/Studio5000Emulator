"""Read-only e1000e diagnostics for the selected Linux Ethernet interface.

This is a partial counter model, not an Ethernet conformance claim. Wire fields
without a provider are zero; their API values remain None and their names are
listed explicitly. In particular rx_nohandler is NOT an unknown-protocol count.
No adapter setting or host counter is changed or cleared.
"""
import ctypes
from dataclasses import dataclass
from pathlib import Path
import re
import socket
import struct
import threading
import time


INTERFACE_NAMES = ('InOctets', 'InUcastPackets', 'InNUcastPackets', 'InDiscards',
                   'InErrors', 'InUnknownProtos', 'OutOctets', 'OutUcastPackets',
                   'OutNUcastPackets', 'OutDiscards', 'OutErrors')
MEDIA_NAMES = ('AlignmentErrors', 'FCSErrors', 'SingleCollisions', 'MultipleCollisions',
               'SQETestErrors', 'DeferredTransmissions', 'LateCollisions',
               'ExcessiveCollisions', 'MACTransmitErrors', 'CarrierSenseErrors',
               'FrameTooLongs', 'MACReceiveErrors')
MAX_STATS = 4096
CACHE_SECONDS = 1.0


@dataclass(frozen=True)
class CounterSnapshot:
    interface: tuple
    media: tuple

    def __post_init__(self):
        for values, size in ((self.interface, 11), (self.media, 12)):
            if not isinstance(values, tuple) or len(values) != size or any(
                    value is not None and (type(value) is not int or not 0 <= value <= 0xFFFFFFFFFFFFFFFF)
                    for value in values):
                raise ValueError('Invalid Ethernet counter snapshot')

    def attributes(self):
        return {number: struct.pack('<' + 'I'*len(values),
                                    *(0 if value is None else value & 0xFFFFFFFF for value in values))
                for number, values in ((4, self.interface), (5, self.media))}

    def description(self):
        return {'source': 'Linux e1000e ETHTOOL_GSTATS and sysfs rx_dropped',
                'interface': dict(zip(INTERFACE_NAMES, self.interface)),
                'media': dict(zip(MEDIA_NAMES, self.media)),
                'unimplemented_interface': [name for name, value in zip(INTERFACE_NAMES, self.interface) if value is None],
                'unimplemented_media': [name for name, value in zip(MEDIA_NAMES, self.media) if value is None],
                'unimplemented_wire_value': 0, 'wire_width_bits': 32,
                'rollover': 'Low 32 bits of observed counters', 'host_counters_cleared': False,
                'atomic_driver_and_sysfs_sample': False, 'native_controller_equivalence': False}


def e1000e_snapshot(stats, rx_dropped):
    """Map explicitly identified driver fields; never guess another driver's ABI.

    Linux's e1000e ethtool table identifies these good-packet/error counters.
    They are host/driver diagnostics, not recovered controller firmware values.
    """
    keys = ('rx_packets', 'tx_packets', 'rx_bytes', 'tx_bytes', 'rx_broadcast',
            'tx_broadcast', 'rx_multicast', 'tx_multicast', 'rx_errors', 'tx_errors',
            'tx_dropped', 'rx_missed_errors', 'rx_align_errors', 'rx_crc_errors',
            'tx_single_coll_ok', 'tx_multi_coll_ok', 'tx_deferred_ok',
            'tx_abort_late_coll', 'tx_aborted_errors', 'tx_carrier_errors',
            'rx_long_length_errors')
    if any(key not in stats or type(stats[key]) is not int or not 0 <= stats[key] <= 0xFFFFFFFFFFFFFFFF for key in keys):
        raise ValueError('Missing or invalid e1000e counter')
    if type(rx_dropped) is not int or not 0 <= rx_dropped <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError('Invalid receive discard count')
    rx_nonunicast = stats['rx_broadcast'] + stats['rx_multicast']
    tx_nonunicast = stats['tx_broadcast'] + stats['tx_multicast']
    # Reject a torn/reset sample rather than emitting negative derived counts.
    if rx_nonunicast > stats['rx_packets'] or tx_nonunicast > stats['tx_packets']:
        raise ValueError('Inconsistent packet counters')
    interface = (stats['rx_bytes'], stats['rx_packets'] - rx_nonunicast, rx_nonunicast,
                 rx_dropped + stats['rx_missed_errors'], stats['rx_errors'], None,
                 stats['tx_bytes'], stats['tx_packets'] - tx_nonunicast, tx_nonunicast,
                 stats['tx_dropped'], stats['tx_errors'])
    # SQE and internal MAC failures have no unambiguous provider here. Linux
    # tx_fifo_errors/rx_missed_errors are not substituted for internal MAC errors.
    media = (stats['rx_align_errors'], stats['rx_crc_errors'], stats['tx_single_coll_ok'],
             stats['tx_multi_coll_ok'], None, stats['tx_deferred_ok'],
             stats['tx_abort_late_coll'], stats['tx_aborted_errors'], None,
             stats['tx_carrier_errors'], stats['rx_long_length_errors'], None)
    return CounterSnapshot(interface, media)


def linux_counters(name):
    """Read bounded driver tables without ethtool binaries or elevated privileges."""
    try:
        if not isinstance(name, str) or name in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', name):
            return None
        import fcntl
        base = Path('/sys/class/net') / name
        if base.joinpath('type').read_text().strip() != '1':
            return None
        def read(raw):
            buffer = ctypes.create_string_buffer(raw, len(raw))
            request = struct.pack('16sP', name.encode('ascii'), ctypes.addressof(buffer)) + bytes(24-struct.calcsize('P'))
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                fcntl.ioctl(probe, 0x8946, request)  # SIOCETHTOOL, get commands only.
            return buffer.raw
        info = read(struct.pack('=I', 3) + bytes(192))  # ETHTOOL_GDRVINFO.
        if info[4:36].split(b'\0', 1)[0] != b'e1000e':
            return None
        count = struct.unpack_from('=I', info, 180)[0]
        if not 1 <= count <= MAX_STATS:
            return None
        raw_names = read(struct.pack('=III', 0x1B, 1, count) + bytes(count*32))  # GSTRINGS, ETH_SS_STATS.
        if struct.unpack_from('=III', raw_names) != (0x1B, 1, count):
            return None
        names = []; seen = set()
        for offset in range(12, len(raw_names), 32):
            raw = raw_names[offset:offset+32]
            if b'\0' not in raw:
                return None
            value = raw.split(b'\0', 1)[0].decode('ascii')
            if not re.fullmatch(r'[A-Za-z0-9_]{1,31}', value) or value in seen:
                return None
            names.append(value); seen.add(value)
        raw_stats = read(struct.pack('=II', 0x1D, count) + bytes(count*8))  # ETHTOOL_GSTATS.
        if struct.unpack_from('=II', raw_stats) != (0x1D, count):
            return None
        stats = dict(zip(names, struct.unpack_from('=' + 'Q'*count, raw_stats, 8)))
        text = base.joinpath('statistics/rx_dropped').read_text().strip()
        if not re.fullmatch(r'[0-9]{1,20}', text):
            return None
        return e1000e_snapshot(stats, int(text))
    except (ImportError, OSError, ValueError, TypeError, struct.error):
        return None


class CounterCache:
    """Endpoint-owned; API descriptions and protocol reads share one snapshot."""
    def __init__(self):
        self.lock = threading.RLock()
        self.name = None
        self.snapshot = None
        self.queried = False
        self.updated = 0.0
        self.captured_at = None

    def read(self, name):
        with self.lock:
            now = time.monotonic()
            if not self.queried or name != self.name or not 0 <= now-self.updated < CACHE_SECONDS:
                self.name = name
                self.snapshot = linux_counters(name)
                self.queried = True
                self.updated = time.monotonic()
                self.captured_at = time.time() if self.snapshot is not None else None
            return self.snapshot.attributes() if self.snapshot is not None else {}

    def description(self):
        with self.lock:
            age = time.monotonic()-self.updated if self.queried else None
            return {'queried': self.queried, 'available': self.snapshot is not None,
                    'interface': self.name, 'captured_at': self.captured_at,
                    'age_seconds': age if age is not None and age >= 0 else None,
                    'stale': self.queried and not 0 <= age < CACHE_SECONDS,
                    'cache_seconds': CACHE_SECONDS, 'get_and_clear_authorized': False,
                    'snapshot': self.snapshot.description() if self.snapshot is not None else None}
