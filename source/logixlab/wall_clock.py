"""Read-only software Wall Clock Time with explicit UTC and legacy epochs.

UTC counters use the host clock. Legacy local reads require complete source
with explicit zero legacy adjustments. CST offsets, DST/timezone strings and
clock setters remain unavailable; no physical clock or PTP state is imported.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import struct
import time
from .tag_catalog import complete_tag_source

CLASS_ID = 0x8B
SCHEMA_REVISION = 4
LEGACY_EPOCH_MICROSECONDS = 63_072_000_000_000
UTC_ATTRIBUTES = (6, 7, 11)
LEGACY_ATTRIBUTES = (1, 5)
TIME_ATTRIBUTES = (*LEGACY_ATTRIBUTES, *UTC_ATTRIBUTES)


@dataclass(frozen=True)
class WallClock:
    legacy_utc: bool = False

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):return cls()
        nodes = [node for node in controller.iter()
                 if node.tag.rsplit('}', 1)[-1].casefold().startswith('wallclocktime')]
        if len(nodes) != 1 or nodes != controller.findall('WallClockTime'):return cls()
        node = nodes[0]
        return cls(not (node.attrib.keys()-{'Use', 'TimeZone', 'LocalTimeAdjustment'} or
                       node.get('Use') not in (None, 'Target') or len(node) or (node.text or '').strip()) and
                   node.get('TimeZone') == '0' and node.get('LocalTimeAdjustment') == '0')

    def attributes(self, *, read_time=False):
        values = {2: bytes(2), 4: bytes(2)} if self.legacy_utc else {}
        if not read_time:return values
        try:
            nanoseconds = time.time_ns()
            if type(nanoseconds) is not int or nanoseconds < 0:return values
            microseconds = nanoseconds//1000
            if microseconds > 0x7FFFFFFFFFFFFFFF:return values
            values[6] = values[11] = struct.pack('<q', microseconds)
            if self.legacy_utc and microseconds >= LEGACY_EPOCH_MICROSECONDS:
                values[1] = struct.pack('<Q', microseconds-LEGACY_EPOCH_MICROSECONDS)
            try:
                instant = datetime(1970, 1, 1, tzinfo=timezone.utc)+timedelta(microseconds=microseconds)
                fields = struct.pack('<7I', instant.year, instant.month, instant.day, instant.hour,
                                     instant.minute, instant.second, instant.microsecond)
                values[7] = fields
                if self.legacy_utc:values[5] = fields
            except (OverflowError, ValueError):
                pass  # A representable counter need not fit calendar fields.
        except (OSError, OverflowError, ValueError):
            pass
        return values

    def description(self):
        return {'class_id': CLASS_ID, 'schema_revision': SCHEMA_REVISION,
                'source': 'Host time.time_ns; UTC, independent of scan time',
                'source_legacy_utc_available': self.legacy_utc,
                'static_attributes': [2, 4] if self.legacy_utc else [],
                'dynamic_attributes': sorted(TIME_ATTRIBUTES if self.legacy_utc else UTC_ATTRIBUTES),
                'utc_epoch': '1970-01-01T00:00:00Z', 'legacy_epoch': '1972-01-01T00:00:00Z',
                'snapshot_scope': 'one CIP request', 'cst_offset': False, 'timezone_string': False,
                'dst_parameters': False, 'clock_setters': False, 'physical_clock': False, 'ptp_engine': False}


def class_attributes():
    return {1: struct.pack('<H', SCHEMA_REVISION), 2: struct.pack('<H', 1)}
