"""Bounded offline Time Sync attribute framing; no clock values are supplied.

Layouts follow the installed plain v35 Time Synchronize attribute definitions.
Decoded rows expose lengths and hashes by default, including for clock identity,
addresses and descriptions. Partial replies retain their unreturned suffix;
separate requests are never combined into an asserted simultaneous snapshot.
"""
import hashlib


class TimeSyncError(ValueError):
    pass


FIXED = {1: 1, 2: 1, 3: 8, 4: 8, 5: 8, 6: 8, 7: 8, 8: 24, 9: 16,
         10: 20, 11: 2, 16: 1, 17: 1, 18: 1, 19: 2, 20: 4, 27: 2,
         28: 16, 102: 10}
PORTS = {12: 4, 13: 4, 14: 4, 15: 4, 24: 10, 25: 36, 26: 22}
STRINGS = {21: 64, 22: 32, 23: 128}


class Cursor:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def take(self, size):
        if size < 0 or self.offset + size > len(self.data):
            raise TimeSyncError('Truncated Time Sync attribute value')
        start = self.offset
        self.offset += size
        return self.data[start:self.offset]

    def uint(self, width=2):
        return int.from_bytes(self.take(width), 'little')

    def string(self, maximum, width=1):
        size = self.uint(width)
        if size > maximum:
            raise TimeSyncError('Time Sync description exceeds its bound')
        self.take(size)


def attribute_value(cursor, attribute):
    if attribute in FIXED:
        cursor.take(FIXED[attribute])
    elif attribute in PORTS:
        count = cursor.uint()
        if count > 10:
            raise TimeSyncError('Time Sync port count exceeds its bound')
        for _ in range(count):
            value = cursor.take(PORTS[attribute])
            # Both address structures reserve 16 bytes after their size field.
            size_offset = {25: 18, 26: 4}.get(attribute)
            if size_offset is not None and int.from_bytes(value[size_offset:size_offset+2], 'little') > 16:
                raise TimeSyncError('Time Sync port address exceeds its bound')
    elif attribute in STRINGS:
        cursor.string(STRINGS[attribute], 4)
    elif attribute == 103:
        cursor.take(14)  # Clock identity, type and manufacturer identity.
        for maximum in (64, 64, 64, 32, 32, 32):
            cursor.string(maximum)
        cursor.take(6)  # Profile identity.
    elif attribute == 104:
        cursor.take(10)  # Clock identity and port number.
        cursor.string(32)
        physical_size = cursor.uint()
        if physical_size > 16:
            raise TimeSyncError('Time Sync physical address exceeds its bound')
        # The observed vendor structure transmits the counted bytes, unlike
        # attributes 25/26, whose port records reserve 16-byte address arrays.
        cursor.take(physical_size)
        cursor.take(2)  # Network protocol.
        protocol_size = cursor.uint()
        if protocol_size > 16:
            raise TimeSyncError('Time Sync protocol address exceeds its bound')
        cursor.take(protocol_size)
    elif attribute == 105:
        cursor.take(8)
        cursor.string(128)
        cursor.string(128)
    else:
        raise TimeSyncError('Successful Time Sync attribute has no established decoder')


def decode_attribute_list(raw, requested, *, include_payloads=False):
    """Decode one reply against its ordered request, preserving duplicates.

    General status 6 carries a strict prefix of the requested attributes.
    Status 0x0A instead carries every requested field, including field errors.
    No offsets, delays, identities or address values are given semantics here.
    """
    if (not isinstance(raw, bytes) or not 4 <= len(raw) <= 65535 or
            raw[0] != 0x83 or raw[1] != 0 or 4+2*raw[3] > len(raw)):
        raise TimeSyncError('Malformed Time Sync attribute-list response')
    if (not isinstance(requested, (tuple, list)) or not 1 <= len(requested) <= 32 or
            any(type(number) is not int or not 1 <= number <= 65535 for number in requested)):
        raise TimeSyncError('Invalid Time Sync attribute-list request')
    status = raw[2]
    if status not in (0, 6, 0x0A):
        raise TimeSyncError('Time Sync reply does not contain an attribute list')
    cursor = Cursor(raw[4+2*raw[3]:])
    count = cursor.uint()
    if (status == 6 and not 0 < count < len(requested) or
            status != 6 and count != len(requested)):
        raise TimeSyncError('Time Sync response count differs from its requested prefix')
    rows = []
    for expected in requested[:count]:
        attribute, field_status = cursor.uint(), cursor.uint()
        if attribute != expected:
            raise TimeSyncError('Time Sync attribute order differs from its request')
        start = cursor.offset
        if field_status == 0:
            attribute_value(cursor, attribute)
        value = cursor.data[start:cursor.offset]
        row = {'attribute': attribute, 'status': field_status, 'value_bytes': len(value),
               'value_sha256': hashlib.sha256(value).hexdigest() if field_status == 0 else None}
        if include_payloads:
            row['data_hex'] = value.hex() if field_status == 0 else None
        rows.append(row)
    if cursor.offset != len(cursor.data):
        raise TimeSyncError('Time Sync attribute list has trailing data')
    failed = any(row['status'] for row in rows)
    if status == 0 and failed or status == 0x0A and not failed:
        raise TimeSyncError('Time Sync general and attribute statuses disagree')
    return {'status': status, 'partial': status == 6, 'attributes': rows,
            'remaining_attributes': list(requested[count:]), 'clock_semantics': 'NOT INFERRED'}
