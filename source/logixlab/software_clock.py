"""Read-only local UTC time and the software controller's empty PTP port set.

This clock neither disciplines the host nor exchanges PTP messages. Time reads
are independent of deterministic scan time; one snapshot serves an attribute
list so its microsecond and nanosecond values refer to the same instant.
"""
import struct
import time
from . import __version__


PORT_ATTRIBUTES = (11, 12, 13, 14, 15, 24, 25, 26)
DESCRIPTION_ATTRIBUTES = (21, 22, 23)
STATIC_ATTRIBUTES = (2, *PORT_ATTRIBUTES, *DESCRIPTION_ATTRIBUTES)
TIME_ATTRIBUTES = (3, 4)


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


def attributes(*, read_time=False):
    # No PTP engine means no synchronized master and no emulated PTP ports.
    # Port arrays contain their UINT count, without invented entries.
    values = {2: b'\0', **{number: bytes(2) for number in PORT_ATTRIBUTES},
              **description_attributes()}
    if read_time:
        try:
            nanoseconds = time.time_ns()
            if type(nanoseconds) is int and nanoseconds >= 0:
                microseconds = nanoseconds // 1000
                if microseconds <= 0x7FFFFFFFFFFFFFFF:
                    values[3] = struct.pack('<q', microseconds)
                if nanoseconds <= 0x7FFFFFFFFFFFFFFF:
                    values[4] = struct.pack('<q', nanoseconds)
        except (OSError, OverflowError, ValueError):
            pass  # Keep time unavailable while preserving known PTP state.
    return values


def description():
    return {'source': 'Host time.time_ns; UTC epoch 1970-01-01',
            'dynamic_attributes': list(TIME_ATTRIBUTES), 'static_attributes': list(STATIC_ATTRIBUTES),
            'snapshot_scope': 'one CIP read request', 'scan_time_independent': True,
            'host_adjustments_visible': True, 'synchronized': False, 'ptp_port_count': 0,
            'ptp_engine': False, 'accuracy_claimed': False, 'set_time': False,
            'master_offset_measurements': False, 'hardware_clock': False,
            'description_attributes': list(description_attributes()),
            'product_description': 'Studio5000Emulator;LogixLab;',
            'software_version': __version__, 'user_description': '',
            'manufacturer_oui': None, 'hardware_revision': None,
            'firmware_revision': None, 'serial_number': None}
