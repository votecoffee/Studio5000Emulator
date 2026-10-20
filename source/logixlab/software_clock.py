"""Read-only local UTC time and the software controller's empty PTP port set.

This clock neither disciplines the host nor exchanges PTP messages. Time reads
are independent of deterministic scan time; one snapshot serves an attribute
list so its microsecond and nanosecond values refer to the same instant.
"""
import struct
import time


PORT_ATTRIBUTES = (11, 12, 13, 14, 15, 24, 25, 26)
STATIC_ATTRIBUTES = (2, *PORT_ATTRIBUTES)
TIME_ATTRIBUTES = (3, 4)


def attributes(*, read_time=False):
    # No PTP engine means no synchronized master and no emulated PTP ports.
    # Port arrays contain their UINT count, without invented entries.
    values = {2: b'\0', **{number: bytes(2) for number in PORT_ATTRIBUTES}}
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
            'master_offset_measurements': False, 'hardware_clock': False}
