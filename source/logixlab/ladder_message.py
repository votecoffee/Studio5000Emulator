"""Bounded, in-process ladder MSG transfers to the simulated controller."""
import math
import re
import struct
from dataclasses import dataclass, replace

from . import software_clock, time_sync, wall_clock
from .identity import Identity
from .integer_math import CONTROLLERS
from .model import ModelError, coerce
from .network_objects import (
    PORT_CLASS_ID, TCPIP_CLASS_ID, TCPIP_INTERFACE_ATTRIBUTES,
    port_attributes, tcpip_class_attributes, tcpip_interface_attributes,
)
from .numeric_copy import decode, encode, location
from .templates import Catalog, MAX_BYTES, aligned

MAX_ELEMENTS = 64
THROTTLE_POSITIONS = 16
MAX_PENDING = 48
MAX_CACHED = 32
DEFAULT_TIMEOUT_US = 30_000_000
DEFAULT_CONNECTION_RATE_US = 7_500_000
MAX_TIMEOUT_MULTIPLIER = 7
PATH_BUFFER_SIZE = 82
IDENTITY_ATTRIBUTES = frozenset(range(1, 8))
GENERIC_SERVICES = {
    1: {1: (0x01, 0x03, 0x0E)},
    wall_clock.CLASS_ID: {1: (0x03, 0x0E)},
    time_sync.CLASS_ID: {1: (0x03, 0x0E)},
    PORT_CLASS_ID: dict.fromkeys((0, 1, 2), (0x01, 0x03, 0x0E)),
    TCPIP_CLASS_ID: {0: (0x01, 0x03, 0x0E), 1: (0x03, 0x0E)},
}
GENERIC_SINGLE_ATTRIBUTES = {
    1: IDENTITY_ATTRIBUTES,
    wall_clock.CLASS_ID: range(1, 12),
    time_sync.CLASS_ID: time_sync.INSTANCE_ATTRIBUTES,
    PORT_CLASS_ID: (1, 2, 3, 4, 5, 7, 8, 9),
    TCPIP_CLASS_ID: (1, 2, 3, 4, 5, 6, 101, 102),
}
GENERIC_BUFFER_TYPES = frozenset(('SINT', 'INT', 'DINT'))
MAX_ATTRIBUTE_LIST = 32
STATUS_BITS = {'EW': 2, 'ER': 4, 'DN': 5, 'ST': 6, 'EN': 7, 'TO': 8, 'EN_CC': 9}
EN_MASK = 1 << STATUS_BITS['EN']
COMPLETE_MASK = (1 << STATUS_BITS['ER']) | (1 << STATUS_BITS['DN'])
TO_MASK = 1 << STATUS_BITS['TO']
CACHE_MASK = 1 << STATUS_BITS['EN_CC']
FIELDS = {
    'FLAGS': 'INT', 'ERR': 'INT', 'EXERR': 'DINT', 'REQ_LEN': 'INT', 'DN_LEN': 'INT',
    'LocalIndex': 'DINT', 'RemoteIndex': 'DINT', 'RemoteElement': 'STRING', 'Path': 'STRING',
    'UnconnectedTimeout': 'DINT',
    'ConnectionRate': 'DINT', 'TimeoutMultiplier': 'SINT',
    'Class': 'INT', 'Instance': 'DINT', 'Attribute': 'INT',
}
TIMING_ATTRIBUTES = {
    'unconnectedtimeout': ('UnconnectedTimeout', ('DINT', 'TIME32')),
    'connectionrate': ('ConnectionRate', ('DINT', 'TIME32')),
    'timeoutmultiplier': ('TimeoutMultiplier', ('SINT',)),
}
ELEMENT_BYTES = {'SINT': 1, 'INT': 2, 'DINT': 4, 'LINT': 8, 'REAL': 4}
NAME = r'[A-Za-z_][A-Za-z_0-9]{0,39}'
INDICES = r'[0-9]{1,6}(?:[ \t]*,[ \t]*[0-9]{1,6}){0,2}'
SELECTOR = rf'\[({INDICES}|\*)\]'
ADDRESS = re.compile(rf'((?:Program:{NAME}\.)?{NAME})(?:{SELECTOR})?(\..*)?', re.ASCII | re.I)
MEMBER = re.compile(rf'({NAME})(?:{SELECTOR})?', re.ASCII | re.I)
MAX_MEMBER_DEPTH = 8
MAX_ALIAS_HOPS = 8


@dataclass(frozen=True)
class Endpoint:
    name: str
    coordinates: tuple[int, ...]
    offset: int
    variable: bool
    member_path: tuple[str | int, ...] = ()

    def start(self, parameter):
        if self.variable:
            return (parameter,)
        if self.coordinates:
            return (*self.coordinates[:-1], self.coordinates[-1] + self.offset)
        return (self.offset,) if self.offset else ()


@dataclass(frozen=True)
class RecordLayout:
    dtype: str
    size: int
    writable: bool
    leaves: tuple[tuple[tuple[str | int, ...], str], ...]
    string_capacity: int | None = None


@dataclass(frozen=True)
class Configuration:
    read: bool
    local: Endpoint
    remote: Endpoint
    remote_text: str
    count: int
    record: RecordLayout | None = None
    connected: bool = False
    cache: bool = False
    path: bytes = b''


@dataclass(frozen=True)
class GenericRead:
    destination: Endpoint
    identity: Identity | None
    service: int
    attribute: int
    source: Endpoint | None = None
    source_size: int = 0
    class_id: int = 1
    instance: int = 1
    connected: bool = False
    cache: bool = False
    path: bytes = b''


@dataclass(frozen=True)
class DataTableTransfer:
    configuration: Configuration
    local_start: tuple[int, ...]
    remote: Endpoint | None
    remote_start: tuple[int, ...]


@dataclass(frozen=True)
class Pending:
    request: DataTableTransfer | GenericRead
    deadline_us: int | None
    path: bytes | None
    enabled: bool = True
    started: bool = False
    opening: bool = False
    response_timeout_us: int | None = None
    attribute_numbers: tuple[int, ...] | None = None


class TransferError(Exception):
    def __init__(self, code):
        self.code = code


def _number(attributes, name, minimum, maximum, default=''):
    raw = attributes.get(name, default)
    if not re.fullmatch(r'[0-9]{1,6}', raw, re.ASCII) or not minimum <= int(raw) <= maximum:
        raise ModelError(f'MESSAGE {name} requires an integer in {minimum}..{maximum}')
    return int(raw)


def _flag(attributes, name):
    value = attributes.get(name, '0').casefold()
    if value not in ('0', '1', 'false', 'true'):
        raise ModelError(f'MESSAGE {name} requires a boolean value')
    return value in ('1', 'true')


def _parse_endpoint(text, offset):
    match = ADDRESS.fullmatch(text)
    if match is None:
        return None
    name, selector, suffix = match.groups()
    segments = suffix[1:].split('.', MAX_MEMBER_DEPTH) if suffix else ()
    if len(segments) > MAX_MEMBER_DEPTH:
        return None
    member_path = []
    for segment in segments:
        member = MEMBER.fullmatch(segment)
        if member is None or selector == '*':
            return None
        if selector:
            member_path.extend(map(int, selector.split(',')))
        field, selector = member.groups()
        member_path.append(field.casefold())
    coordinates = tuple(map(int, selector.split(','))) if selector not in (None, '*') else ()
    if len(coordinates) > 1 and offset:
        return None
    return Endpoint(name.casefold(), coordinates, offset, selector == '*', tuple(member_path))


def _endpoint(attributes, side):
    offset = _number(attributes, side + 'Index', 0, 999999, '0')
    endpoint = _parse_endpoint(attributes.get(side + 'Element', '').strip(), offset)
    if endpoint is None:
        raise ModelError(f'MESSAGE {side}Element requires a supported tag or array element')
    return endpoint


def _hex_number(attributes, name):
    match = re.fullmatch(r'(?:16#)?([0-9A-F]{1,4})', attributes.get(name, ''), re.ASCII | re.I)
    if match is None:
        raise ModelError(f'CIP Generic {name} requires a hexadecimal value')
    return int(match[1], 16)


def _generic_endpoint(attributes, name):
    endpoint = _parse_endpoint(attributes.get(name, '').strip(), 0)
    if endpoint is None or endpoint.member_path or endpoint.variable or len(endpoint.coordinates) > 1:
        raise ModelError(f'CIP Generic requires a direct {name} or fixed array start')
    return endpoint


def _generic_read(project, attributes):
    service = _hex_number(attributes, 'ServiceCode')
    cls = _hex_number(attributes, 'ObjectType')
    instance = _number(attributes, 'TargetObject', 0, 65535)
    if service not in GENERIC_SERVICES.get(cls, {}).get(instance, ()):
        raise ModelError('CIP Generic requires a supported read service, class and instance')
    single = service == 0x0E
    attribute = _hex_number(attributes, 'AttributeNumber') if single or attributes.get('AttributeNumber') else 0
    if single and attribute not in GENERIC_SINGLE_ATTRIBUTES[cls]:
        raise ModelError('CIP Generic single-read attribute is outside the modeled object range')
    source = None
    source_size = 0
    if service == 0x03:
        source = _generic_endpoint(attributes, 'LocalElement')
        source_size = _number(attributes, 'RequestedLength', 4, 2 + 2 * MAX_ATTRIBUTE_LIST)
        if source_size % 2:
            raise ModelError('CIP Generic attribute list requires an even byte length')
    else:
        _number(attributes, 'RequestedLength', 0, 0, '0')
        if attributes.get('LocalElement', '').strip():
            raise ModelError('CIP Generic single and all reads require an empty source')
    if attributes.get('RemoteElement', '').strip():
        raise ModelError('CIP Generic requires an empty RemoteElement')
    destination = _generic_endpoint(attributes, 'DestinationTag')
    identity = Identity.from_project('logix-v35-l85e', project) if cls == 1 else None
    # Preserve the 16-bit pattern of an optional attribute placeholder.
    signed_attribute = attribute if attribute < 0x8000 else attribute - 0x10000
    return GenericRead(destination, identity, service, signed_attribute, source, source_size,
                       class_id=cls, instance=instance)


def from_tag(project, tag, element, dims):
    if (project.version != '35' or project.processor.upper() not in CONTROLLERS
            or tag.constant or tag.tag_class != 'Standard' or dims):
        raise ModelError('MESSAGE requires a writable scalar Standard tag in the v35 5580 profile')
    if tag.scope and (element.get('Usage', 'Local').casefold() != 'local' or
                      not project.program_configuration.type_attributes(tag.scope, source_sha256=project.sha256)):
        raise ModelError('MESSAGE program tags must be Local tags in an ordinary Standard program')
    data = element.findall("./Data[@Format='Message']")
    if (len(data) != 1 or len(data[0]) != 1 or data[0][0].tag != 'MessageParameters'
            or len(data[0][0]) or element.find("./Data[@Format='Decorated']") is not None):
        raise ModelError('MESSAGE requires one MessageParameters element in Message data')
    attributes = data[0][0].attrib
    kind = attributes.get('MessageType', '').casefold()
    connected = _flag(attributes, 'ConnectedFlag')
    cache = _flag(attributes, 'CacheConnections')
    if (attributes.get('CommTypeCode', '0') != '0'
            or _flag(attributes, 'LargePacketUsage') or (cache and not connected)):
        raise ModelError('MESSAGE requires standard CIP transfers and a connected request to cache')
    path_text = attributes.get('ConnectionPath', '').strip()
    path = b''
    if path_text.casefold() != 'this':
        local = re.fullmatch(r'1[ 	]*,[ 	]*([0-9]{1,2})', path_text)
        if local is None or bytes((1, int(local[1]))) != project.local_message_route:
            raise ModelError('MESSAGE path requires THIS or the declared local controller slot')
        path = project.local_message_route
    if kind == 'cip generic':
        return replace(_generic_read(project, attributes), connected=connected, cache=cache, path=path)
    if kind not in ('cip data table read', 'cip data table write'):
        raise ModelError('MESSAGE supports CIP Data Table Read, Write and bounded CIP Generic reads')
    return Configuration(kind.endswith('read'), _endpoint(attributes, 'Local'),
                         _endpoint(attributes, 'Remote'), attributes['RemoteElement'].strip(),
                         _number(attributes, 'RequestedLength', 1, MAX_ELEMENTS), connected=connected, cache=cache, path=path)


def _scope_endpoint(project, endpoint, scope):
    if scope and ':' not in endpoint.name:
        local_name = f'program:{scope.casefold()}.{endpoint.name}'
        if local_name in project.tags:
            return replace(endpoint, name=local_name)
    return endpoint


def _bind_local(project, configuration, scope):
    """Resolve the saved local element after all controller and program tags are loaded."""
    if isinstance(configuration, GenericRead):
        source = configuration.source
        return replace(configuration, destination=_scope_endpoint(project, configuration.destination, scope),
                       source=_scope_endpoint(project, source, scope) if source is not None else None)
    return replace(configuration, local=_scope_endpoint(project, configuration.local, scope))


def _record_layout(catalog, dtype):
    template = catalog.for_type(dtype)
    if template is None:
        return None
    writable = all(member.get('ExternalAccess', 'Read/Write') == 'Read/Write'
                   for item in catalog.closure((template.instance,)).values()
                   for member in catalog.project.udts[item.name.casefold()].findall('./Members/Member')
                   if member.get('Hidden', 'false').casefold() != 'true')
    leaves = tuple((tuple(int(part) if part.isdigit() else part for part in re.findall(r'\w+', ref, re.ASCII)), kind)
                   for _, kind, ref, _ in catalog.leaves(template, ''))
    return RecordLayout(dtype, template.size, writable, leaves)


def _string_layout(project, dtype):
    capacity = project.string_capacity(dtype)
    if dtype == 'STRING':
        return RecordLayout(dtype, aligned(4 + capacity, 4), True, (), capacity)
    schema = project.udts.get(dtype.casefold())
    if (capacity is None or capacity > 4096 or schema is None
            or schema.get('Family') != 'StringFamily' or schema.get('Class', 'User') != 'User'):
        return None
    members = schema.findall('./Members/Member')
    if ([member.get('Name') for member in members] != ['LEN', 'DATA']
            or members[0].get('Dimension', '0').strip() not in ('', '0')):
        return None
    access = [member.get('ExternalAccess', 'Read/Write') for member in members]
    if (any(item not in ('Read Only', 'Read/Write') for item in access)
            or any(member.get('Hidden', 'false').lower() != 'false'
                   or member.get('AOILocal', 'false').lower() != 'false'
                   or any(member.get(name) for name in ('Target', 'BitNumber', 'AliasFor'))
                   for member in members)):
        return None
    return RecordLayout(dtype, aligned(4 + capacity, 4), all(item == 'Read/Write' for item in access), (), capacity)


def initialize(project):
    catalog = None
    records = {}
    for key, configuration in project.message_configs.items():
        tag = project.tags[key]
        configuration = _bind_local(project, configuration, tag.scope)
        if isinstance(configuration, Configuration) and not configuration.local.member_path:
            local = project.tags.get(configuration.local.name)
            if (local and not local.problem and not local.alias
                    and (local.dtype.upper() == 'STRING' or local.dtype.casefold() in project.udts)):
                dtype = local.dtype.upper()
                if dtype not in records:
                    layout = _string_layout(project, dtype)
                    if layout is None:
                        if catalog is None:
                            catalog = Catalog(project)
                        layout = _record_layout(catalog, dtype)
                    records[dtype] = layout
                configuration = replace(configuration, record=records[dtype])
        project.message_configs[key] = configuration
        tag.value = initial(project, configuration)


def _words(dtype, count, record=None):
    element_bytes = record.size if record else ELEMENT_BYTES.get(dtype, 0)
    return (element_bytes * count + 1) // 2


def status_members(word):
    return {name: bool(word & (1 << bit)) for name, bit in STATUS_BITS.items()}


def _set_flags(record, **values):
    word = record['FLAGS']
    for name, value in values.items():
        mask = 1 << STATUS_BITS[name]
        word = word | mask if value else word & ~mask
    record['FLAGS'] = word


def initial(project, configuration):
    record = {
        'FLAGS': CACHE_MASK if configuration.cache else 0, 'ERR': 0, 'EXERR': 0, 'REQ_LEN': 0, 'DN_LEN': 0,
        'UnconnectedTimeout': DEFAULT_TIMEOUT_US,
        'Path': project.default('STRING'),
    }
    record['Path']['LEN'] = len(configuration.path)
    record['Path']['DATA'][:len(configuration.path)] = configuration.path
    if configuration.connected:
        record.update(ConnectionRate=DEFAULT_CONNECTION_RATE_US, TimeoutMultiplier=0)
    if isinstance(configuration, GenericRead):
        record.update(Class=configuration.class_id, Instance=configuration.instance,
                      Attribute=configuration.attribute, REQ_LEN=configuration.source_size)
        return record
    requested = 0
    try:
        endpoint = configuration.local
        local, endpoint, _ = _follow_aliases(project, endpoint, endpoint.start(0), configuration.count)
        dtype, _, _ = _member_base(project, local.dtype.upper(), local.value, endpoint.member_path)
    except TransferError:
        pass
    else:
        requested = _words(dtype, configuration.count, configuration.record)
    record.update(REQ_LEN=requested if requested <= MAX_BYTES // 2 else 0,
                  LocalIndex=configuration.local.offset, RemoteIndex=configuration.remote.offset)
    # Preserve long authored addresses that predate the writable STRING field.
    text = configuration.remote_text
    if len(text) <= project.string_capacity('STRING'):
        element = project.default('STRING')
        element['LEN'] = len(text)
        element['DATA'][:len(text)] = text.encode('ascii')
        record['RemoteElement'] = element
    return record


def _array_paths(value, start, count):
    dimensions = []
    offset = 0
    for coordinate in start or (0,):
        if not isinstance(value, list) or not 0 <= coordinate < len(value):
            raise TransferError(0x05)
        dimensions.append(len(value))
        offset = offset * len(value) + coordinate
        value = value[coordinate]
    if isinstance(value, list) or offset + count > math.prod(dimensions):
        raise TransferError(0x05)
    # Walk only the requested span, with the last dimension varying fastest.
    paths = []
    for index in range(offset, offset + count):
        path = []
        for dimension in reversed(dimensions):
            index, coordinate = divmod(index, dimension)
            path.append(coordinate)
        paths.append(tuple(reversed(path)))
    return tuple(paths)


def _member_base(project, dtype, value, member_path, *, remote=False, write=False):
    path = []
    for part in member_path:
        if isinstance(part, int):
            if not isinstance(value, list) or part >= len(value):
                raise TransferError(0x05)
        else:
            schema = project.udts.get(dtype.casefold())
            if (not isinstance(value, dict) or schema is None or schema.get('Class', 'User') != 'User'
                    or schema.get('Family', 'NoFamily') != 'NoFamily'):
                raise TransferError(0x05)
            member = next((item for item in schema.findall('./Members/Member')
                           if item.get('Name', '').casefold() == part), None)
            if member is None or member.get('AliasFor') or member.get('Target') or member.get('BitNumber'):
                raise TransferError(0x05)
            if (member.get('Hidden', 'false').lower() not in ('false', '0')
                    or member.get('AOILocal', 'false').lower() not in ('false', '0')):
                raise TransferError(0x0F)
            access = member.get('ExternalAccess', 'Read/Write')
            if remote and access != 'Read/Write' and (write or access != 'Read Only'):
                raise TransferError(0x0F)
            part = member.get('Name')
            if part not in value:
                raise TransferError(0x05)
            dtype = member.get('DataType', '').upper()
        value = value[part]
        path.append(part)
    return dtype, tuple(path), value


def _endpoint_tag(project, endpoint, scope):
    tag = project.tags.get(endpoint.name)
    if tag is None or tag.problem or tag.tag_class != 'Standard':
        raise TransferError(0x05)
    if tag.scope:
        if scope is not None and tag.scope.casefold() != scope.casefold():
            raise TransferError(0x05)
        if not project.program_configuration.type_attributes(tag.scope, source_sha256=project.sha256):
            raise TransferError(0x05)
    return tag


def _check_tag_access(tag, remote, write):
    if ((write and tag.constant) or (remote and tag.external_access != 'Read/Write'
                                    and (write or tag.external_access != 'Read Only'))):
        raise TransferError(0x0F)


def _follow_aliases(project, endpoint, start, count, *, remote=False, write=False, scope=None, allow_alias=True):
    seen = set()
    tag = _endpoint_tag(project, endpoint, scope)
    while tag.alias:
        if (not allow_alias or endpoint.member_path or endpoint.name in seen
                or len(seen) >= MAX_ALIAS_HOPS):
            raise TransferError(0x05)
        seen.add(endpoint.name)
        _check_tag_access(tag, remote, write)
        target = _parse_endpoint(tag.alias.strip(), 0)
        if (target is None or target.variable or (target.coordinates and (start or count != 1))):
            raise TransferError(0x05)
        start = start or target.coordinates
        endpoint = _scope_endpoint(project, target, tag.scope)
        tag = _endpoint_tag(project, endpoint, scope)
    return tag, endpoint, start


def _region(memory, endpoint, start, count, *, remote, write, record=None, scope=None, allow_alias=True):
    project = memory.project
    original = endpoint.name
    tag, endpoint, start = _follow_aliases(project, endpoint, start, count, remote=remote,
                                          write=write, scope=scope, allow_alias=allow_alias)
    dtype = tag.dtype.upper()
    if not endpoint.member_path and dtype not in ELEMENT_BYTES and (
            endpoint.name != original or record is None or dtype != record.dtype):
        raise TransferError(0xFC)
    _check_tag_access(tag, remote, write)
    dtype, base, value = _member_base(project, dtype, memory.values[endpoint.name], endpoint.member_path,
                                     remote=remote, write=write)
    if base and dtype not in ELEMENT_BYTES:
        raise TransferError(0xFC)
    if isinstance(value, list):
        return endpoint.name, tuple(base + path for path in _array_paths(value, start, count)), dtype
    if not start and count == 1:
        return endpoint.name, (base,), dtype
    raise TransferError(0x05)


def _control_key(engine, name, scope, instruction):
    key = name.casefold()
    project = engine.project
    program_key = f'program:{scope.casefold()}.{key}'
    if program_key in project.tags:
        key = program_key
    if ':' in name or key not in project.message_configs:
        tag = project.tags.get(key)
        detail = f': {tag.problem}' if tag and tag.dtype.upper() == 'MESSAGE' and tag.problem else ''
        raise ModelError(f'{instruction} requires a directly named controller or program-local MESSAGE with supported configuration' + detail)
    return key


def _generic_span(memory, endpoint, size, *, write):
    key, paths, dtype = _region(memory, endpoint, endpoint.start(0), 1, remote=False, write=write, allow_alias=False)
    if dtype not in GENERIC_BUFFER_TYPES or len(paths[0]) > 1:
        raise TransferError(0xFC)
    first = paths[0]
    width = ELEMENT_BYTES[dtype]
    count = (size + width - 1) // width
    if not first:
        if count > 1:
            raise TransferError(0x11)
        return key, ((),), dtype
    start = first[0]
    if count > len(memory.values[key]) - start:
        raise TransferError(0x11)
    return key, tuple((index,) for index in range(start, start + count)), dtype


def _capture_attribute_numbers(memory, request):
    try:
        key, paths, dtype = _generic_span(memory, request.source, request.source_size, write=False)
        raw = b''.join(encode(memory.at(key, path), dtype) for path in paths)[:request.source_size]
    except (ModelError, TransferError):
        return None
    count = int.from_bytes(raw[:2], 'little')
    if not 1 <= count <= MAX_ATTRIBUTE_LIST or len(raw) != 2 + 2 * count:
        return None
    return struct.unpack_from(f'<{count}H', raw, 2)


def _write_generic_reply(memory, destination, payload):
    key, paths, dtype = _generic_span(memory, destination, len(payload), write=True)
    width = ELEMENT_BYTES[dtype]
    writes = []
    for index, path in enumerate(paths):
        chunk = payload[index * width:(index + 1) * width]
        if len(chunk) < width:
            try:
                previous = encode(memory.at(key, path), dtype)
            except ModelError as error:
                raise TransferError(0x03) from error
            chunk += previous[len(chunk):]
        writes.append(decode(chunk, dtype))
    for path, value in zip(paths, writes, strict=True):
        memory.store(key, path, value)


def validate(engine, op, scope, kind='RLL'):
    if kind != 'RLL' or engine.mode != 'project' or scope in engine.memory.frames:
        raise ModelError('MSG requires a whole-project ladder scan outside AOIs')
    key = _control_key(engine, op.args[0], scope, op.name)
    configuration = engine.project.message_configs[key]
    if isinstance(configuration, GenericRead):
        endpoints = (configuration.destination, configuration.source)
    else:
        endpoints = (configuration.local,)
    for endpoint in endpoints:
        if endpoint is not None and ':' in endpoint.name and endpoint.name.partition('.')[0] != f'program:{scope.casefold()}':
            raise ModelError('MSG local data must belong to the program executing the instruction')
    if isinstance(configuration, GenericRead):
        try:
            _generic_span(engine.memory, configuration.destination, 1, write=True)
        except TransferError as error:
            raise ModelError(f'CIP Generic requires a writable SINT, INT or DINT scalar or one-dimensional array destination (16#{error.code:04X})') from error
        if configuration.source is not None:
            try:
                _generic_span(engine.memory, configuration.source, configuration.source_size, write=False)
            except TransferError as error:
                raise ModelError(f'CIP Generic attribute list requires a SINT, INT or DINT source with room for the configured byte count (16#{error.code:04X})') from error
        return key
    record = configuration.record
    if record and configuration.count * record.size > MAX_BYTES:
        raise ModelError(f'MSG record transfer exceeds {MAX_BYTES} modeled bytes')
    try:
        # A variable start needs a valid array shape, independent of its saved index.
        _region(engine.memory, configuration.local, configuration.local.start(0), configuration.count,
                remote=False, write=configuration.read, record=record, scope=scope)
    except TransferError as error:
        raise ModelError(f'MSG local element cannot address the requested span (16#{error.code:04X})') from error
    return key


def matches_attribute(op):
    return (len(op.args) == 4 and all(isinstance(arg, str) for arg in op.args)
            and op.args[0].casefold() == 'message'
            and (op.args[2].casefold() == 'connectionpath' or op.args[2].casefold() in TIMING_ATTRIBUTES))


def _timing_operand(memory, op, scope, member, types):
    resolve = memory.resolve if op.name == 'SSV' else memory.check_writable
    key, parts, dtype = resolve(op.args[3], scope)
    if dtype not in types or isinstance(memory.at(key, parts), (list, dict)):
        expected = ' or '.join(types)
        raise ModelError(f'{op.name} Message {member} requires one scalar {expected} tag')
    return key, parts, dtype


def _path_window(memory, op, scope):
    key, parts, dtype, region = location(memory, op.args[3], scope, writable=op.name == 'GSV')
    error = f'{op.name} Message ConnectionPath requires 82 contiguous SINT elements in a one-dimensional array'
    if dtype != 'SINT' or region is None:
        raise ModelError(error)
    base, cells = region
    start = parts[-1] if parts != base else 0
    if len(cells) - start < PATH_BUFFER_SIZE or isinstance(cells[0], list):
        raise ModelError(error)
    return key, base, start


def _path_byte(value):
    if type(value) is not int or not -128 <= value <= 127:
        raise ModelError('SSV Message ConnectionPath requires known SINT header and active bytes')
    return value & 0xFF


def _execute_path_attribute(memory, op, scope, control):
    key, base, start = _path_window(memory, op, scope)
    ref = control + '.Path'
    if op.name == 'SSV':
        cells = memory.at(key, base)
        size = _path_byte(cells[start]) | (_path_byte(cells[start + 1]) << 8)
        if size > PATH_BUFFER_SIZE - 2:
            raise ModelError('SSV Message ConnectionPath length exceeds 80 bytes')
        raw = bytes(_path_byte(value) for value in cells[start + 2:start + 2 + size])
        memory.write_string(ref, raw.decode('latin-1'))
        return

    raw = memory.string(ref).encode('latin-1')
    if len(raw) > PATH_BUFFER_SIZE - 2:
        raise ModelError('GSV Message ConnectionPath length exceeds 80 bytes')
    counted = (len(raw).to_bytes(2, 'little') + raw).ljust(PATH_BUFFER_SIZE, b'\x00')
    for index, value in enumerate(counted, start):
        memory.store(key, base + [index], value if value < 128 else value - 256)


def validate_attribute(engine, op, scope, kind):
    attribute = op.args[2].casefold()
    memory = engine.memory
    if kind != 'RLL' or engine.mode != 'project' or scope in memory.frames:
        raise ModelError(f'Message {op.args[2]} requires a whole-project ladder scan outside AOIs')
    control = _control_key(engine, op.args[1], scope, op.name)
    previous = memory.structural
    memory.structural = True
    try:
        if attribute == 'connectionpath':
            _path_window(memory, op, scope)
            return
        member, types = TIMING_ATTRIBUTES[attribute]
        if member != 'UnconnectedTimeout' and not engine.project.message_configs[control].connected:
            raise ModelError(f'{op.name} Message {member} requires a configured connected MESSAGE')
        _timing_operand(memory, op, scope, member, types)
    finally:
        memory.structural = previous


def execute_attribute(engine, op, scope):
    attribute = op.args[2].casefold()
    memory = engine.memory
    control = _control_key(engine, op.args[1], scope, op.name)
    if attribute == 'connectionpath':
        return _execute_path_attribute(memory, op, scope, control)
    member, types = TIMING_ATTRIBUTES[attribute]
    key, parts, dtype = _timing_operand(memory, op, scope, member, types)
    record = memory.values[control]
    if op.name == 'GSV':
        memory.store(key, parts, coerce(record[member], dtype))
        return

    value = memory.at(key, parts)
    if member == 'TimeoutMultiplier':
        if type(value) is not int or not 0 <= value <= MAX_TIMEOUT_MULTIPLIER:
            raise ModelError(f'SSV Message {member} requires a known value in 0..{MAX_TIMEOUT_MULTIPLIER}')
    elif type(value) is not int or value <= 0:
        raise ModelError(f'SSV Message {member} requires a known positive value')
    record[member] = value


def prescan(engine, op, scope):
    key = validate(engine, op, scope)
    record = engine.memory.values[key]
    defaults = initial(engine.project, engine.project.message_configs[key])
    for name in ('LocalIndex', 'RemoteIndex', 'RemoteElement', 'Path', 'UnconnectedTimeout',
                 'ConnectionRate', 'TimeoutMultiplier', 'Class', 'Instance', 'Attribute'):
        if name in record:
            defaults[name] = record[name]
    defaults['FLAGS'] = record['FLAGS'] & CACHE_MASK
    engine.memory.values[key] = defaults
    engine.memory.message_cache.pop(key, None)
    if engine._message_advance is not None:
        engine._message_advance.pop(key, None)


def _capture_remote(memory, key, configuration, record):
    if 'RemoteElement' not in record:
        return configuration.remote
    try:
        text = memory.string(key + '.RemoteElement')
    except ModelError:
        return None
    if not text.isascii():
        return None
    text = text.strip()
    if text.casefold() == configuration.remote_text.casefold():
        return configuration.remote
    return _parse_endpoint(text, 0)


def _capture_path(memory, key):
    try:
        path = memory.string(key + '.Path').encode('latin-1')
    except ModelError:
        return None
    return path if path in (b'', memory.project.local_message_route) else None


def _admit(engine, key, power):
    record = engine.memory.values[key]
    queue = engine._message_advance
    if len(queue) >= MAX_PENDING or sum(not request.started for request in queue.values()) >= THROTTLE_POSITIONS:
        return
    configuration = engine.project.message_configs[key]
    cache = engine.memory.message_cache
    path = _capture_path(engine.memory, key)
    reused = configuration.connected and path is not None and cache.get(key) == path
    if not reused:
        cache.pop(key, None)
    timeout_us = record['UnconnectedTimeout']
    response_us = None
    if configuration.connected:
        rate, multiplier = record['ConnectionRate'], record['TimeoutMultiplier']
        response_us = rate << (multiplier + 2) if rate > 0 and 0 <= multiplier <= MAX_TIMEOUT_MULTIPLIER else 0
    if (not reused and timeout_us <= 0) or response_us == 0:
        _set_flags(record, EN=power, ER=True)
        record['ERR'] = 0x03
        cache.pop(key, None)
        return
    request = configuration
    numbers = None
    if isinstance(request, GenericRead):
        request = replace(request, class_id=record['Class'], instance=record['Instance'],
                          attribute=record['Attribute'])
        if request.source is not None:
            numbers = _capture_attribute_numbers(engine.memory, request)
    else:
        remote = _capture_remote(engine.memory, key, request, record)
        request = DataTableTransfer(request, request.local.start(record['LocalIndex']), remote,
                                    remote.start(record['RemoteIndex']) if remote is not None else ())
    deadline = None if reused else engine.time_ms * 1000 + timeout_us
    queue[key] = Pending(request, deadline, path, enabled=power, opening=configuration.connected and not reused,
                         response_timeout_us=response_us, attribute_numbers=numbers)
    _set_flags(record, EW=True)


def execute(engine, op, power, scope):
    key = _control_key(engine, op.args[0], scope, op.name)
    record = engine.memory.values[key]
    queue = engine._message_advance
    pending = queue.get(key)
    if pending is not None:
        if pending.enabled != power:
            queue[key] = replace(pending, enabled=power)
    elif record['FLAGS'] & EN_MASK:
        if not record['FLAGS'] & COMPLETE_MASK:
            # An enabled control with no queue entry or result is waiting for admission.
            if record['FLAGS'] & TO_MASK:
                _finish(record, power, 0xFE)
                engine.memory.message_cache.pop(key, None)
            else:
                _admit(engine, key, power)
        elif not power:
            _set_flags(record, EN=False)
    elif power:
        record.update(FLAGS=(record['FLAGS'] & (TO_MASK | CACHE_MASK)) | EN_MASK, ERR=0, EXERR=0, DN_LEN=0)
        _admit(engine, key, power)
    return power


def _known_scalar(value, dtype):
    if dtype == 'REAL':
        return type(value) is float and math.isfinite(value)
    if dtype == 'BOOL':
        return type(value) is bool
    return type(value) is int


def _check_string(value, capacity):
    if not isinstance(value, dict) or value.keys() != {'LEN', 'DATA'}:
        raise TransferError(0x03)
    length, data = value['LEN'], value['DATA']
    if (type(length) is not int or not 0 <= length <= capacity
            or not isinstance(data, list) or len(data) != capacity
            or None in data[:length]
            or any(type(byte) is not int or not -128 <= byte <= 127 for byte in data if byte is not None)):
        raise TransferError(0x03)


def _check_record(value, record):
    if record.string_capacity is not None:
        _check_string(value, record.string_capacity)
        return
    try:
        for path, dtype in record.leaves:
            member = value
            for part in path:
                member = member[part]
            if not _known_scalar(member, dtype) or coerce(member, dtype) != member:
                raise TransferError(0x03)
    except (ModelError, IndexError, KeyError, TypeError, OverflowError) as error:
        raise TransferError(0x03) from error


def _attribute_list_reply(numbers, values):
    result = bytearray(struct.pack('<H', len(numbers)))
    failed = False
    for number in numbers:
        value = values.get(number)
        result += struct.pack('<HH', number, 0x14 if value is None else 0)
        if value is None:
            failed = True
        else:
            result += value
    return (0x0A if failed else 0), result


def _generic_reply(engine, request, numbers, status_word):
    project = engine.project
    services = GENERIC_SERVICES.get(request.class_id, {}).get(request.instance)
    if services is None:
        raise TransferError(0x05)
    if request.service not in services:
        raise TransferError(0x08)
    if request.service == 0x03 and numbers is None:
        raise TransferError(0x03)

    if request.class_id == 1:
        identity = request.identity
        if identity is None:
            try:
                identity = Identity.from_project('logix-v35-l85e', project)
            except ModelError as error:
                raise TransferError(0x05) from error
        if request.service == 0x01:
            return 0, identity.all_attributes(status_word=status_word)
        attributes = identity.attributes(status_word=status_word)
        values = {number: attributes[number] for number in IDENTITY_ATTRIBUTES}
    elif request.class_id == PORT_CLASS_ID:
        binding = engine.network_binding() if request.instance == 2 and engine.network_binding else None
        values = port_attributes(request.instance, binding.address if binding else None)
        if request.service == 0x01:
            if request.instance == 2 and binding is None:
                raise TransferError(0x0C)
            return 0, b''.join(values.values())
    elif request.class_id == TCPIP_CLASS_ID:
        if request.instance == 0:
            values = tcpip_class_attributes()
            if request.service == 0x01:
                return 0, b''.join(values[n] for n in (1, 2, 3))
        else:
            binding = engine.network_binding() if engine.network_binding else None
            if binding is None:
                raise TransferError(0x0C)
            requested = numbers if request.service == 0x03 else (request.attribute,)
            include_interface = bool(TCPIP_INTERFACE_ATTRIBUTES.intersection(requested))
            values = tcpip_interface_attributes(binding.interface, binding.hostname,
                                                include_interface=include_interface)
            if include_interface and binding.interface is None and request.service == 0x03:
                raise TransferError(0x0C)
            if include_interface and request.service == 0x0E and request.attribute not in values:
                raise TransferError(0x0C)
    else:
        requested = numbers if request.service == 0x03 else (request.attribute,)
        if request.class_id == wall_clock.CLASS_ID:
            values = project.wall_clock.attributes(
                read_time=any(number in wall_clock.TIME_ATTRIBUTES for number in requested),
                coordinated_clock=engine.coordinated_clock,
            )
        else:
            values = project.time_sync.cip_attributes(
                read_time=any(number in software_clock.TIME_ATTRIBUTES for number in requested),
                instance_id=engine.application_instance_id,
            )
    if request.service == 0x03:
        return _attribute_list_reply(numbers, values)
    value = values.get(request.attribute)
    if value is None:
        raise TransferError(0x14)
    return 0, value


def _transfer(engine, request, status_word, attribute_numbers):
    memory = engine.memory
    if isinstance(request, GenericRead):
        error, payload = _generic_reply(engine, request, attribute_numbers, status_word)
        _write_generic_reply(memory, request.destination, payload)
        return error, len(payload)
    configuration = request.configuration
    record = configuration.record
    if request.remote is None:
        raise TransferError(0x05)
    local_key, local_paths, dtype = _region(memory, configuration.local, request.local_start,
                                            configuration.count, remote=False, write=configuration.read, record=record)
    remote_key, remote_paths, remote_dtype = _region(memory, request.remote, request.remote_start,
                                                     configuration.count, remote=True, write=not configuration.read,
                                                     record=record)
    if dtype != remote_dtype:
        raise TransferError(0xFC)
    if record and not configuration.read and not record.writable:
        raise TransferError(0x0F)
    source, destination = ((remote_key, remote_paths), (local_key, local_paths)) if configuration.read else (
        (local_key, local_paths), (remote_key, remote_paths))
    values = [memory.at(source[0], path) for path in source[1]]
    if record:
        for value in values:
            _check_record(value, record)
    elif not all(_known_scalar(value, dtype) for value in values):
        raise TransferError(0x03)
    for path, value in zip(destination[1], values):
        memory.store(destination[0], path, value)
    return 0, _words(dtype, configuration.count, record)


def _finish(record, enabled, error, transferred=0):
    _set_flags(record, EN=enabled, EW=False, ST=False, TO=False, DN=not error, ER=bool(error))
    record.update(ERR=error, DN_LEN=transferred)


def service(engine, status_word):
    memory = engine.memory
    queue = engine._message_advance
    cache = memory.message_cache
    now_us = engine.time_ms * 1000
    for key, pending in tuple(queue.items()):
        record = memory.values[key]
        transferred = 0
        if record['FLAGS'] & TO_MASK or (pending.deadline_us is not None and now_us >= pending.deadline_us):
            error = 0xFE
        elif pending.opening:
            # One advance begins the virtual open; the next can start the transfer.
            queue[key] = replace(pending, opening=False)
            continue
        elif not pending.started:
            _set_flags(record, EW=False, ST=True)
            deadline = (now_us + pending.response_timeout_us if pending.response_timeout_us is not None
                        else pending.deadline_us)
            queue[key] = replace(pending, started=True, deadline_us=deadline)
            continue
        else:
            try:
                if pending.path is None:
                    raise TransferError(0x05)
                error, transferred = _transfer(engine, pending.request, status_word, pending.attribute_numbers)
            except TransferError as failure:
                error = failure.code
        _finish(record, pending.enabled, error, transferred)
        if error:
            cache.pop(key, None)
        elif record['FLAGS'] & CACHE_MASK and len(cache) < MAX_CACHED:
            cache[key] = pending.path
        del queue[key]
