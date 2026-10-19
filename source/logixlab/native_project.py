"""Read only the offline correlation header; never extract or modify an ACD.

These identifiers let a native client compare its offline project to this model.
They do not establish firmware authenticity or equivalent execution semantics.
"""
import gzip
import hashlib
import io
import re
import struct
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path

from .model import ModelError


def acd_stream(path, stream_name, limit=4_000_000):
    """Read one bounded container member in memory, without extracting paths."""
    path = Path(path)
    if not 8 <= path.stat().st_size <= 100_000_000: raise ModelError('ACD size is outside the import limit')
    data = path.read_bytes(); digest = hashlib.sha256(data).hexdigest()
    count, _ = struct.unpack_from('<II', data, len(data)-8)
    table = len(data)-8-count*528
    if data[:2] != b'\r\n' or not 1 <= count <= 4096 or table < 2:
        raise ModelError('Unsupported ACD container directory')
    stream = None
    for offset in range(table, len(data)-8, 528):
        name = data[offset:offset+520].decode('utf-16le', errors='strict').split('\0', 1)
        if len(name) != 2: raise ModelError('Unterminated ACD directory name')
        if name[0].casefold() != stream_name.casefold(): continue
        size, start = struct.unpack_from('<II', data, offset+520)
        if stream is not None or not 1 <= size <= limit or start < 2 or start+size > table:
            raise ModelError('Invalid ACD metadata stream bounds: ' + stream_name)
        stream = data[start:start+size]
    if stream is None: raise ModelError('ACD has no supported metadata stream: ' + stream_name)
    return digest, stream


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ModelError('Native correlation requires complete lowercase SHA-256 hashes')
    return value


def _varint(data, pos):
    value = 0
    for shift in range(0, 35, 7):
        if pos >= len(data): break
        byte = data[pos]; pos += 1; value |= (byte & 127) << shift
        if not byte & 128 and value <= 0xFFFFFFFF: return value, pos
    raise ModelError('Invalid uint32 in offline change-log header')


def _fields(data):
    fields = {}; pos = 0
    while pos < len(data):
        key, pos = _varint(data, pos); number, wire = key >> 3, key & 7
        if not 1 <= number <= 13 or number in fields:
            raise ModelError('Unsupported or duplicate offline change-log field')
        if number == 5 and wire == 2:
            size, pos = _varint(data, pos)
            if size > len(data) - pos: raise ModelError('Truncated offline schema revision')
            fields[number] = data[pos:pos+size]; pos += size
        elif number != 5 and wire == 0: fields[number], pos = _varint(data, pos)
        else: raise ModelError('Unsupported offline change-log wire type')
    return fields


@dataclass(frozen=True)
class NativeProjectIdentity:
    source_acd_sha256: str
    source_l5x_sha256: str
    online_index: int
    online_generation: int
    download_uid: int
    copy_uid: int
    project_uid: int
    timeline_uid: int

    def __post_init__(self):
        _hash(self.source_acd_sha256); _hash(self.source_l5x_sha256)
        for name in ('online_index', 'online_generation', 'download_uid', 'copy_uid', 'project_uid', 'timeline_uid'):
            value = getattr(self, name); maximum = 0xFFFF if name.startswith('online_') else 0xFFFFFFFF
            if type(value) is not int or not 0 <= value <= maximum:
                raise ModelError('Native correlation field is outside its wire range: ' + name)

    @classmethod
    def from_manifest(cls, manifest, source_l5x_sha256):
        if not isinstance(manifest, dict) or set(manifest) != set(cls.__dataclass_fields__):
            raise ModelError('Invalid native project correlation manifest')
        identity = cls(**manifest)
        if identity.source_l5x_sha256 != source_l5x_sha256:
            raise ModelError('Native project correlation does not match the loaded L5X bytes')
        return identity

    @classmethod
    def from_acd(cls, path, source_l5x_sha256):
        digest, stream = acd_stream(path, 'OfflineChangelog.Dat')
        try:
            reader = gzip.GzipFile(fileobj=io.BytesIO(stream)) if stream[:2] == b'\x1f\x8b' else io.BytesIO(stream)
            with reader:
                prefix = reader.read(4)
                if len(prefix) != 4: raise ModelError('Truncated offline change-log header')
                size = struct.unpack('<I', prefix)[0]
                if not 1 <= size <= 65536: raise ModelError('Offline change-log header is too large')
                header = reader.read(size)
                if len(header) != size: raise ModelError('Truncated offline change-log header')
        except (OSError, EOFError, zlib.error) as error:
            raise ModelError('Invalid compressed offline change-log stream') from error
        fields = _fields(header)
        if not {3, 8, 9, 10, 11, 12} <= fields.keys():
            raise ModelError('Offline change-log header lacks required correlation fields')
        return cls(digest, source_l5x_sha256, fields[11], fields[12], fields[10], fields[8], fields[3], fields[9])

    def manifest(self): return asdict(self)

    def attributes(self):
        # UID is the download UID; Image UID is the project UID. These are
        # distinct from the copy/timeline UIDs and the hardware Identity object.
        values = (self.online_index, self.online_generation, self.download_uid, self.copy_uid,
                  0, 0, 2, self.project_uid, 0x00010001, self.timeline_uid)
        widths = (2, 2, 4, 4, 2, 2, 4, 4, 4, 4)
        return {n: value.to_bytes(width, 'little') for n, (value, width) in enumerate(zip(values, widths), 1)}

    def description(self):
        return {'bound': True, 'source': 'ACD OfflineChangelog header',
                'source_acd_sha256': self.source_acd_sha256, 'source_l5x_sha256': self.source_l5x_sha256,
                'firmware_authentication': False, 'runtime_equivalence': False}
