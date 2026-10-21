"""Strict offline framing of Controller collection attribute lists.

Only established instance-one layouts are decoded. Values remain lengths and
hashes unless explicitly requested; framing does not establish device semantics,
security authority, clock measurements or native upload acceptance.
"""
import hashlib
from tools.time_sync_inventory import TimeSyncError, decode_attribute_list as time_sync_list

CLASSES = (0x43, 0x64, 0x67, 0xF5, 0xF6)
FIXED = {0x67: {1: 2, 2: 4},
         0xF5: {1: 4, 2: 4, 3: 4},
         0xF6: {1: 4, 2: 4, 3: 6, 4: 44, 5: 48, 6: 4, 7: 1, 8: 1, 9: 1}}


class CollectionError(ValueError):
    pass


class Cursor:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def take(self, count):
        if count < 0 or self.offset+count > len(self.data):
            raise CollectionError('Truncated collection attribute')
        start = self.offset
        self.offset += count
        return self.data[start:self.offset]

    def uint(self):
        return int.from_bytes(self.take(2), 'little')

    def string(self, maximum, *, padded=False):
        count = self.uint()
        if count > maximum:
            raise CollectionError('Collection string exceeds its bound')
        self.take(count)
        if padded and count % 2 and self.take(1) != b'\0':
            raise CollectionError('Nonzero collection string padding')


def attribute_value(cursor, class_id, attribute):
    width = FIXED.get(class_id, {}).get(attribute)
    if width is not None:
        cursor.take(width)
    elif class_id == 0x64 and attribute in (1, 2, 3, 6):
        # These installed v35 strings carry a UINT count without word padding.
        cursor.string(40 if attribute == 1 else 128)
    elif class_id == 0x64 and attribute == 7:
        # Empty trusted-slot lists are established. Nonempty entry framing has
        # not been verified and must not be skipped by guessing entry lengths.
        if cursor.uint():
            raise CollectionError('Nonempty trusted-slot layout is unsupported')
    elif class_id == 0x64 and attribute == 8:
        cursor.take(4)
    elif class_id == 0xF5 and attribute == 4:
        words = cursor.uint()
        if words > 64:
            raise CollectionError('Physical-link path exceeds its bound')
        cursor.take(2*words)
    elif class_id == 0xF5 and attribute == 5:
        cursor.take(20)  # Five little-endian IPv4 UDINT values.
        cursor.string(48, padded=True)
    elif class_id == 0xF5 and attribute == 6:
        cursor.string(64, padded=True)
    else:
        raise CollectionError('Successful collection field has no established layout')


def decode_attribute_list(raw, requested, class_id, *, include_payloads=False):
    """Frame one ordered response; never merge a partial reply with a later read."""
    if type(class_id) is not int or class_id not in CLASSES:
        raise CollectionError('Unsupported collection object class')
    if class_id == 0x43:
        try:
            return time_sync_list(raw, requested, include_payloads=include_payloads)
        except TimeSyncError as error:
            raise CollectionError(str(error)) from error
    if (not isinstance(raw, bytes) or not 4 <= len(raw) <= 65535 or raw[0] != 0x83 or
            raw[1] != 0 or 4+2*raw[3] > len(raw) or raw[2] not in (0, 6, 0x0A)):
        raise CollectionError('Malformed collection attribute-list response')
    if (not isinstance(requested, (tuple, list)) or not 1 <= len(requested) <= 32 or
            any(type(n) is not int or not 1 <= n <= 65535 for n in requested)):
        raise CollectionError('Invalid collection attribute-list request')
    cursor = Cursor(raw[4+2*raw[3]:])
    count = cursor.uint()
    if (raw[2] == 6 and not 0 < count < len(requested) or
            raw[2] != 6 and count != len(requested)):
        raise CollectionError('Collection count differs from its requested prefix')
    rows = []
    for expected in requested[:count]:
        attribute, status = cursor.uint(), cursor.uint()
        if attribute != expected:
            raise CollectionError('Collection field order differs from its request')
        start = cursor.offset
        if status == 0:
            attribute_value(cursor, class_id, attribute)
        value = cursor.data[start:cursor.offset]
        row = {'attribute': attribute, 'status': status, 'value_bytes': len(value),
               'value_sha256': hashlib.sha256(value).hexdigest() if status == 0 else None}
        if include_payloads:
            row['data_hex'] = value.hex() if status == 0 else None
        rows.append(row)
    if cursor.offset != len(cursor.data):
        raise CollectionError('Collection attribute list has trailing data')
    errors = any(row['status'] for row in rows)
    if raw[2] == 0 and errors or raw[2] == 0x0A and not errors:
        raise CollectionError('Collection general and field statuses disagree')
    return {'status': raw[2], 'partial': raw[2] == 6, 'attributes': rows,
            'remaining_attributes': list(requested[count:]), 'value_semantics': 'NOT INFERRED'}
