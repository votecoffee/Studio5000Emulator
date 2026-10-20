"""Bounded native Task identities from the original ACD Comps.Dat records.

Only the observed component type 256, header version 0 and Task body format 18
are understood. Complete L5X task names select the corresponding controller-
scoped class 0x70 paths; old/free/collection records never synthesize an ID.
These identities grant no compiled storage, native editing or task execution.
"""
from dataclasses import dataclass
import gzip
import io
import re
import struct
from types import MappingProxyType
from typing import Mapping
import zlib

from .model import ModelError
from .native_project import _hash, acd_stream


MAX_TASKS = 32
MAX_BYTES = 128_000_000
MAX_RECORDS = 200_000
MAX_STREAM_BYTES = 16_000_000
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')


def _expected(names):
    if not isinstance(names, (list, tuple)) or len(names) > MAX_TASKS:
        raise ModelError('Invalid or excessive expected native Task names')
    result = {}
    for name in names:
        if not isinstance(name, str) or not NAME.fullmatch(name) or name.casefold() in result:
            raise ModelError('Invalid or duplicate expected native Task name')
        result[name.casefold()] = name
    return result


def task_paths(data, expected_names):
    """Read unambiguous active Task records for an explicit complete name list.

    The logical database end excludes its physical tail. FAFA records are
    candidates; FDFD/free and other known record kinds supply no identities.
    Duplicate candidates, unsupported Task versions and nested Task paths
    withhold the entire inventory. Unmatched names belong to other namespaces
    or historical components and never enlarge the caller's active inventory.
    """
    expected = _expected(expected_names)
    if not isinstance(data, (bytes, bytearray, memoryview)) or not 24 <= len(data) <= MAX_BYTES:
        raise ModelError('Native Task database size is outside its limit')
    size, position = struct.unpack_from('<II', data, 8)
    end = size + 1
    if (struct.unpack_from('<I', data)[0] + 1 != len(data)
            or not 24 <= position <= min(end, 4096) or end > len(data)):
        raise ModelError('Unsupported native Task database bounds')
    found = {}; instances = set(); records = 0
    while position < end:
        records += 1
        if records > MAX_RECORDS or end - position < 6:
            raise ModelError('Invalid native Task record count or header')
        kind, length = struct.unpack_from('<HI', data, position)
        if kind not in (0xFAFA, 0xFDFD, 0xFEFE, 0xFBBF) or not 6 <= length <= end - position:
            raise ModelError('Invalid native Task record bounds')
        record = memoryview(data)[position + 6:position + length]
        position += length
        if kind != 0xFAFA:
            continue
        if len(record) < 148:
            raise ModelError('Truncated native Task component header')
        used = struct.unpack_from('<I', record)[0]
        if not 148 <= used <= len(record) or struct.unpack_from('<I', record, 12)[0] != 0:
            raise ModelError('Unsupported native Task component header layout')
        if struct.unpack_from('<H', record, 10)[0] != 256:
            continue
        raw_name = bytes(record[24:148])
        stop = next((index for index in range(0,124,2) if raw_name[index:index+2] == b'\0\0'), None)
        if stop is None:
            raise ModelError('Unterminated native Task component name')
        try:
            name = raw_name[:stop].decode('utf-16le').casefold()
        except UnicodeError as error:
            raise ModelError('Invalid native Task component name') from error
        if name not in expected:
            continue
        body = record[148:used]
        if len(body) < 22:
            raise ModelError('Truncated native Task record body')
        version = struct.unpack_from('<H', body, 8)[0]
        logical = struct.unpack_from('<6H', body, 10)
        if logical[0] != 0x70:
            continue
        if version != 18:
            raise ModelError('Unsupported native Task body version')
        if not logical[1] or logical[2:] != (0,0,0,0):
            raise ModelError('Unsupported native Task controller path')
        if name in found:
            raise ModelError('Duplicate or ambiguous historical native Task records')
        if logical[1] in instances:
            raise ModelError('Conflicting native Task instances')
        found[name] = logical[1]; instances.add(logical[1])
    if found.keys() != expected.keys():
        raise ModelError('Incomplete native Task inventory')
    return [{'name':expected[name], 'instance':found[name]} for name in sorted(found)]


@dataclass(frozen=True)
class Task:
    name: str
    instance: int

    def __post_init__(self):
        if not isinstance(self.name, str) or not NAME.fullmatch(self.name):
            raise ModelError('Invalid native Task name')
        if type(self.instance) is not int or not 1 <= self.instance <= 0xFFFF:
            raise ModelError('Invalid native Task instance')


@dataclass(frozen=True, init=False)
class NativeTasks:
    source_acd_sha256: str
    source_l5x_sha256: str
    rows: tuple[Task, ...]
    tasks: Mapping[str, int]
    task_ids: Mapping[int, str]

    def __init__(self, source_acd_sha256, source_l5x_sha256, tasks):
        _hash(source_acd_sha256); _hash(source_l5x_sha256)
        if not isinstance(tasks, (list, tuple)) or len(tasks) > MAX_TASKS:
            raise ModelError('Invalid or excessive native Task inventory')
        rows = []; names = {}; instances = {}
        for row in tasks:
            if not isinstance(row, dict) or set(row) != {'name','instance'}:
                raise ModelError('Invalid native Task manifest fields')
            task = Task(**row); name = task.name.casefold()
            if name in names or task.instance in instances:
                raise ModelError('Duplicate native Task name or instance')
            names[name] = task.instance; instances[task.instance] = name; rows.append(task)
        rows.sort(key=lambda row:row.name.casefold())
        for field, value in (('source_acd_sha256',source_acd_sha256), ('source_l5x_sha256',source_l5x_sha256),
                ('rows',tuple(rows)), ('tasks',MappingProxyType(dict(names))), ('task_ids',MappingProxyType(dict(instances)))):
            object.__setattr__(self, field, value)

    @classmethod
    def from_acd(cls, path, source_l5x_sha256, expected_names):
        _hash(source_l5x_sha256); _expected(expected_names)
        digest, raw = acd_stream(path, 'Comps.Dat', limit=MAX_STREAM_BYTES)
        try:
            reader = gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2] == b'\x1f\x8b' else io.BytesIO(raw)
            with reader:
                data = reader.read(MAX_BYTES + 1)
        except (OSError, EOFError, zlib.error) as error:
            raise ModelError('Invalid compressed native Task inventory') from error
        return cls(digest, source_l5x_sha256, task_paths(data, expected_names))

    @classmethod
    def from_manifest(cls, manifest, source_l5x_sha256):
        _hash(source_l5x_sha256)
        if not isinstance(manifest, dict) or set(manifest) != {'source_acd_sha256','source_l5x_sha256','tasks'}:
            raise ModelError('Invalid native Task inventory manifest')
        if manifest['source_l5x_sha256'] != source_l5x_sha256:
            raise ModelError('Native Task inventory does not match the loaded L5X bytes')
        if not isinstance(manifest['tasks'], list):
            raise ModelError('Native Task manifest requires an explicit list')
        return cls(manifest['source_acd_sha256'], source_l5x_sha256, manifest['tasks'])

    def lookup(self, name):
        return self.tasks.get(name.casefold()) if isinstance(name, str) else None

    def manifest(self):
        return {'source_acd_sha256':self.source_acd_sha256, 'source_l5x_sha256':self.source_l5x_sha256,
                'tasks':[{'name':row.name,'instance':row.instance} for row in self.rows]}

    def description(self):
        return {'bound':True, 'complete':True, 'tasks':len(self.rows),
                'source':'ACD Comps.Dat Task format 18 and complete L5X task names',
                'source_acd_sha256':self.source_acd_sha256, 'source_l5x_sha256':self.source_l5x_sha256,
                'compiled_addresses':False, 'native_edit_authority':False, 'runtime_equivalence':False}
