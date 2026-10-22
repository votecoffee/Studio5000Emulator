"""Read-only local UTC time and the software controller's empty PTP port set.

This clock neither disciplines the host nor exchanges PTP messages. Time reads
are independent of deterministic scan time; one snapshot serves an attribute
list so its microsecond and nanosecond values refer to the same instant.
"""
import hashlib
import re
import struct
import time
from . import __version__


PORT_ATTRIBUTES = (11, 12, 13, 14, 15, 24, 25, 26)
DESCRIPTION_ATTRIBUTES = (21, 22, 23)
STATIC_ATTRIBUTES = (2, *PORT_ATTRIBUTES, *DESCRIPTION_ATTRIBUTES)
TIME_ATTRIBUTES = (3, 4, 28)
IDENTITY_ATTRIBUTES = (10, 105)


def clock_identity(instance_id):
    """A local software identity, stable for one app instance, never a NIC/OUI."""
    if not isinstance(instance_id, str) or not re.fullmatch(r'[0-9a-f]{32}', instance_id):
        return None
    seed = hashlib.sha256(b'LogixLab software clock\0'+bytes.fromhex(instance_id)).digest()
    return bytes(((seed[0] & 0xFC) | 2,))+seed[1:8]


def identity_attributes(instance_id):
    identity = clock_identity(instance_id)
    if identity is None:return {}
    # Free-running software clock: unknown accuracy and uncomputed variance.
    # No valid UTC offset, traceability, leap flags or PTP time scale is asserted.
    local = identity+struct.pack('<6H', 248, 0xFE, 0xFFFF, 0, 0, 0xA0)
    # Vendor user description: the same identity, then two USINT-counted strings
    # (user text and physical location), both unassigned, like attribute 23.
    return {10: local, 105: identity+bytes(2)}


def description_attributes():
    # CIP strings carry a UDINT UTF-8 byte count, with no padding or terminator.
    # Empty hardware, firmware and serial subfields are intentional: these
    # describe the software clock, independently of the compatibility profile.
    values = {}
    for number, text, maximum in ((21, 'Studio5000Emulator;LogixLab;', 64),
                                  (22, ';;'+__version__, 32), (23, '', 128)):
        if len(text)>maximum or '\0' in text:
            continue
        try:
            data = text.encode('utf-8')
        except UnicodeEncodeError:
            continue
        values[number] = struct.pack('<I', len(data))+data
    return values


def attributes(*, read_time=False, instance_id=None):
    # No PTP engine means no synchronized master and no emulated PTP ports.
    # Port arrays contain their UINT count, without invented entries.
    values = {2: b'\0', **{number: bytes(2) for number in PORT_ATTRIBUTES},
              **description_attributes(), **identity_attributes(instance_id)}
    if read_time:
        try:
            nanoseconds = time.time_ns()
            if type(nanoseconds) is int and nanoseconds >= 0:
                microseconds = nanoseconds // 1000
                if microseconds <= 0x7FFFFFFFFFFFFFFF:
                    values[3] = struct.pack('<q', microseconds)
                    # The emulator uses this same host UTC clock for local and
                    # system time, so their offset is exactly zero. The v35
                    # attribute layout puts the offset before system time.
                    # This is independent of any offset to a PTP master.
                    values[28] = struct.pack('<qq', 0, microseconds)
                if nanoseconds <= 0x7FFFFFFFFFFFFFFF:
                    values[4] = struct.pack('<q', nanoseconds)
        except (OSError, OverflowError, ValueError):
            pass  # Keep time unavailable while preserving known PTP state.
    return values


def description(*, instance_id=None):
    identity = clock_identity(instance_id)
    return {'source': 'Host time.time_ns; UTC epoch 1970-01-01',
            'dynamic_attributes': list(TIME_ATTRIBUTES),
            'static_attributes': sorted((*STATIC_ATTRIBUTES, *(IDENTITY_ATTRIBUTES if identity else ()))),
            'snapshot_scope': 'one CIP read request', 'scan_time_independent': True,
            'host_adjustments_visible': True, 'synchronized': False, 'ptp_port_count': 0,
            'system_time_offset_microseconds': 0,
            'system_time_offset_source': 'local and system time use the same host UTC clock',
            'ptp_engine': False, 'accuracy_claimed': False, 'set_time': False,
            'master_offset_measurements': False, 'hardware_clock': False,
            'description_attributes': list(description_attributes()),
            'product_description': 'Studio5000Emulator;LogixLab;',
            'software_version': __version__, 'user_description': '',
            'manufacturer_oui': None, 'hardware_revision': None,
            'firmware_revision': None, 'serial_number': None,
            'clock_identity': identity.hex() if identity else None,
            'clock_identity_source': 'locally generated from the application instance ID',
            'clock_identity_scope': 'application lifetime, independent of the loaded project',
            'identity_attributes': list(IDENTITY_ATTRIBUTES) if identity else [],
            'local_clock_class': 248 if identity else None,
            'local_clock_accuracy': 'unknown', 'local_clock_variance': 'not computed',
            'utc_offset_valid': False, 'time_traceable': False, 'frequency_traceable': False,
            'clock_type': None, 'physical_location': ''}
