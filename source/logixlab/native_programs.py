"""Bounded v35 program paths in Comps.Dat, checked against TagInfo names.

This original reader uses acd-tools' documented record layouts as a reference.
It reads logical identities only; it does not import logic or compiled storage.
Ambiguous historical records and unsupported layouts withhold the inventory.
"""
import gzip
import io
import struct
import zlib

from .model import ModelError
from .native_project import acd_stream

MAX_BYTES = 128_000_000
MAX_RECORDS = 200_000
MAX_PROGRAMS = 4096


def read_programs(path, expected_names):
    if len(expected_names) > MAX_PROGRAMS:
        raise ModelError('Native program inventory exceeds its limit')
    digest, raw = acd_stream(path, 'Comps.Dat', limit=16_000_000)
    try:
        reader = gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2] == b'\x1f\x8b' else io.BytesIO(raw)
        with reader:
            data = reader.read(MAX_BYTES + 1)
    except (OSError, EOFError, zlib.error) as error:
        raise ModelError('Invalid compressed program inventory') from error
    return digest, program_paths(data, expected_names)


def program_paths(data, expected_names):
    """Accept only unambiguous Program format 19 records in a bounded database.

    TagInfo establishes the active names. Every such name must have one logical
    path across the FAFA component records; conflicting historical paths fail.
    FDFD/free and other database regions never supply a binding. This is not an
    index reader or a general Comps database reconstruction.
    """
    expected = {name.casefold(): name for name in expected_names}
    if len(expected) != len(expected_names) or len(expected) > MAX_PROGRAMS:
        raise ModelError('Duplicate or excessive native program names')
    if not 24 <= len(data) <= MAX_BYTES:
        raise ModelError('Program inventory size is outside its limit')
    size, pos = struct.unpack_from('<II', data, 8)
    end = size + 1
    if struct.unpack_from('<I', data)[0] + 1 != len(data) or not 24 <= pos <= min(end, 4096) or end > len(data):
        raise ModelError('Unsupported program database bounds')
    found = {}
    records = 0
    while pos < end:
        records += 1
        if records > MAX_RECORDS or end - pos < 6:
            raise ModelError('Invalid program database record count or header')
        kind, length = struct.unpack_from('<HI', data, pos)
        if kind not in (0xFAFA, 0xFDFD, 0xFEFE, 0xFBBF) or not 6 <= length <= end - pos:
            raise ModelError('Invalid program database record bounds')
        record = memoryview(data)[pos + 6:pos + length]
        pos += length
        if kind != 0xFAFA:
            continue
        if len(record) < 148:
            raise ModelError('Truncated component header')
        used = struct.unpack_from('<I', record)[0]
        if not 148 <= used <= len(record) or struct.unpack_from('<I', record, 12)[0]:
            raise ModelError('Unsupported component record layout')
        if struct.unpack_from('<H', record, 10)[0] != 256:
            continue
        body = record[148:used]
        if len(body) < 22:
            continue
        version = struct.unpack_from('<H', body, 8)[0]
        logical = struct.unpack_from('<6H', body, 10)
        if logical[0] != 0x68 or logical[2:] != (0, 0, 0, 0):
            continue
        name_bytes = bytes(record[24:148])
        stop = next((i for i in range(0, 124, 2) if name_bytes[i:i+2] == b'\0\0'), None)
        if stop is None:
            raise ModelError('Unterminated program component name')
        try:
            name = name_bytes[:stop].decode('utf-16le').casefold()
        except UnicodeError as error:
            raise ModelError('Invalid program component name') from error
        if name not in expected:
            continue
        if version != 19 or not logical[1]:
            raise ModelError('Unsupported native Program record version or path')
        if name in found and found[name] != logical[1]:
            raise ModelError('Ambiguous historical native program paths')
        found[name] = logical[1]
    if found.keys() != expected.keys() or len(set(found.values())) != len(found):
        raise ModelError('Incomplete or conflicting native program inventory')
    return [{'name': expected[name], 'instance': found[name]} for name in sorted(found)]
