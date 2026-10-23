"""Strict offline framing of Controller collection attribute lists.

Only established instance layouts are decoded. Values remain lengths and
hashes unless explicitly requested; framing does not establish device semantics,
security authority, clock measurements or native upload acceptance.
"""
import hashlib
from tools.time_sync_inventory import TimeSyncError, decode_attribute_list as time_sync_list

CLASSES = (0x43, 0x64, 0x67, 0x68, 0x6D, 0x70, 0x8B, 0x8E, 0xF5, 0xF6, 0x3B0, 0x3B2)
FIXED = {0x67: {1: 2, 2: 4},
         0x68: {1:2,2:4,3:4,5:4,7:4,9:4,11:2,13:4,15:2,16:4,19:1,
                20:44,21:44,22:4,24:4,25:4,26:2,27:4,29:1,30:1,31:1},
         0x70: {2:4,3:4,5:2,6:2,7:4,8:4,9:4,11:4,12:4,13:8,14:8,15:8,
                16:4,17:4,18:4,19:4,20:2,21:2,22:4,23:4},
         0x8B: {1: 8, 2: 2, 3: 8, 4: 2, 5: 28, 6: 8, 7: 28, 9: 2, 10: 1, 11: 8},
         # Observed v35 upload and connection profiles. These widths frame replies;
         # they never supply unavailable CCUIDs, signatures or memory values.
         0x8E: {1:4,3:2,6:4,7:2,8:2,9:1,10:1,11:2,12:2,13:4,15:1,16:2,17:1,
                23:1,25:4,26:4,27:8,28:8,31:1,33:32,34:32,35:1},
         0xF5: {1: 4, 2: 4, 3: 4},
         0xF6: {1: 4, 2: 4, 3: 6, 4: 44, 5: 48, 6: 4, 7: 1, 8: 1, 9: 1},
         # Executable field 8 is the four-byte Header Address, separate from
         # Code Address and the older Executable UID field.
         0x6D: {1:2,2:4,**{n:4 for n in range(8,22)},23:1,24:4,26:1,27:1,28:4},
         0x3B0: {1:4,2:1}, 0x3B2: {3:2}}


class CollectionError(ValueError):
    pass


def instance_supported(class_id, instance):
    return (type(class_id) is int and class_id in CLASSES and type(instance) is int and
            (1<=instance<=0xFFFFFFFF if class_id in (0x68,0x6D,0x70,0x3B0,0x3B2) else instance==1))


def scope_supported(class_id,*,program_instance=None,aoi_instance=None,io_map_instance=None,controller_instance=None):
    """Executable instance fields require exactly one ordinary numeric parent."""
    parents=(program_instance,aoi_instance)
    if class_id==0x6D:
        supplied=[value for value in parents if value is not None]
        return (io_map_instance is None and controller_instance is None and len(supplied)==1 and
                type(supplied[0]) is int and 1<=supplied[0]<=0xFFFFFFFF)
    return all(value is None for value in (*parents,io_map_instance,controller_instance))


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
    elif class_id==0xF6 and attribute==10:
        count=int.from_bytes(cursor.take(1),'little')
        if count>64:raise CollectionError('Ethernet interface label exceeds its bound')
        cursor.take(count)
    elif class_id==0x3B0 and attribute==3:
        count=cursor.uint()
        if count>4096:raise CollectionError('Diagnostic condition count exceeds the decoder limit')
        cursor.take(2*count)
    elif class_id==0x3B2 and attribute in (1,2):
        count=int.from_bytes(cursor.take(1),'little')
        if count>(40 if attribute==1 else 128):raise CollectionError('Diagnostic string exceeds its bound')
        cursor.take(count)
    elif class_id==0x6D and attribute in (7,22):
        cursor.string(128 if attribute==7 else 66)
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
    elif class_id == 0x68 and attribute == 32:
        count = cursor.uint()
        if count > 1000:raise CollectionError('Program child list exceeds its bound')
        cursor.take(4*count)
    elif class_id == 0x70 and attribute == 1:
        count=cursor.uint()
        if count>1028:raise CollectionError('Task Program list exceeds its bound')
        cursor.take(4*count)
    elif class_id == 0x70 and attribute == 4:
        count=cursor.uint()
        if count>4096:raise CollectionError('Task trigger exceeds the decoder limit')
        cursor.take(count)
    elif (class_id,attribute) in ((0x68,28),(0x6D,25),(0x70,24),(0x8B,8)):
        count = int.from_bytes(cursor.take(4), 'little')
        if count > (40 if class_id in (0x68,0x6D,0x70) else 82):
            raise CollectionError('Counted collection string exceeds its bound')
        cursor.take(count)
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
