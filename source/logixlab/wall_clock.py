"""Read-only software Wall Clock Time with explicit UTC and legacy epochs.

UTC counters use the host clock. Legacy local reads require complete source
with explicit zero legacy adjustments. That source profile selects the
emulator's UTC local-time policy, independently of saved extended DST settings.
A software coordinated counter supplies offsets without physical/PTP state.
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
TIME_ATTRIBUTES = (*LEGACY_ATTRIBUTES, 3, *UTC_ATTRIBUTES)
UTC_POLICY_ATTRIBUTES = (8, 9, 10)
UTC_ZONE = b'UTC+00:00 Coordinated Universal Time'


@dataclass(frozen=True)
class CoordinatedClock:
    """Elapsed monotonic microseconds within one application lifetime."""
    origin_ns: int | None = None

    @classmethod
    def start(cls):
        try:
            origin = time.monotonic_ns()
            if type(origin) is int and origin >= 0:return cls(origin)
        except (OSError, OverflowError, ValueError):
            pass
        return cls()

    @property
    def available(self):return type(self.origin_ns) is int and self.origin_ns >= 0

    def microseconds(self):
        if not self.available:return None
        try:
            current = time.monotonic_ns()
            if type(current) is int and current >= self.origin_ns:
                elapsed = (current-self.origin_ns)//1000
                if elapsed <= 0x7FFFFFFFFFFFFFFF:return elapsed
        except (OSError, OverflowError, ValueError):
            pass
        return None

    def description(self):
        return {'available': self.available, 'source': 'time.monotonic_ns elapsed microseconds',
                'scope': 'application lifetime', 'reset_on_project_load': False,
                'scan_time_independent': True, 'network_synchronized': False,
                'cip_object_exposed': False, 'gsv_exposed': False}


def current_value_microseconds():
    """One simulator WALLCLOCKTIME sample, or unavailable without a valid UTC counter."""
    try:
        nanoseconds = time.time_ns()
        if type(nanoseconds) is int and 0 <= nanoseconds < (1 << 63)*1000:
            return nanoseconds//1000
    except (OSError, OverflowError, ValueError):
        pass
    return None


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

    def attributes(self, *, read_time=False, coordinated_clock=None):
        values = {2: bytes(2), 4: bytes(2)} if self.legacy_utc else {}
        if self.legacy_utc:
            # This is explicit runtime policy, not an inference about saved
            # extended DST settings from the two obsolete source fields.
            values.update({8: struct.pack('<I',len(UTC_ZONE))+UTC_ZONE,
                           9: bytes(2), 10: bytes(1)})
        if not read_time:return values
        try:
            microseconds = current_value_microseconds()
            if microseconds is None:return values
            values[6] = values[11] = struct.pack('<q', microseconds)
            if self.legacy_utc and isinstance(coordinated_clock,CoordinatedClock):
                elapsed = coordinated_clock.microseconds()
                if elapsed is not None and 0 <= microseconds-elapsed <= 0x7FFFFFFFFFFFFFFF:
                    # The offset relates CST to the modern 1970 UTC value,
                    # not to legacy attribute 1's separate 1972 epoch.
                    values[3] = struct.pack('<q',microseconds-elapsed)
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

    def description(self, *, coordinated_clock=None):
        offset = (self.legacy_utc and isinstance(coordinated_clock,CoordinatedClock)
                  and coordinated_clock.available)
        return {'class_id': CLASS_ID, 'schema_revision': SCHEMA_REVISION,
                'source': 'Host time.time_ns; UTC, independent of scan time',
                'source_legacy_utc_available': self.legacy_utc,
                'static_attributes': [2, 4, *UTC_POLICY_ATTRIBUTES] if self.legacy_utc else [],
                'dynamic_attributes': sorted((*LEGACY_ATTRIBUTES, *UTC_ATTRIBUTES, *((3,) if offset else ()))
                                             if self.legacy_utc else UTC_ATTRIBUTES),
                'utc_epoch': '1970-01-01T00:00:00Z', 'legacy_epoch': '1972-01-01T00:00:00Z',
                'snapshot_scope': 'one CIP request', 'cst_offset': bool(offset),
                'cst_offset_relation': 'CST elapsed microseconds + offset = UTC attribute 6',
                'coordinated_clock': coordinated_clock.description() if isinstance(coordinated_clock,CoordinatedClock) else None,
                'timezone_string': self.legacy_utc, 'dst_parameters': self.legacy_utc,
                'local_time_policy': 'emulator UTC, daylight saving disabled' if self.legacy_utc else None,
                'timezone_value': UTC_ZONE.decode() if self.legacy_utc else None,
                'dst_adjustment_minutes': 0 if self.legacy_utc else None,
                'apply_dst': False if self.legacy_utc else None,
                'source_extended_timezone_dst_imported': False,
                'clock_setters': False, 'physical_clock': False, 'ptp_engine': False}


def class_attributes():
    return {1: struct.pack('<H', SCHEMA_REVISION), 2: struct.pack('<H', 1)}
