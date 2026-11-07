"""Bounded, in-process ladder MSG transfers using the unconnected THIS route."""
import math
import re
from dataclasses import dataclass, replace

from .identity import Identity
from .integer_math import CONTROLLERS
from .model import ModelError, coerce
from .templates import Catalog, MAX_BYTES, aligned

MAX_ELEMENTS = 64
THROTTLE_POSITIONS = 16
MAX_PENDING = 48
DEFAULT_TIMEOUT_US = 30_000_000
IDENTITY_ATTRIBUTES = frozenset(range(1, 8))
STATUS_BITS = {'EW': 2, 'ER': 4, 'DN': 5, 'ST': 6, 'EN': 7, 'TO': 8, 'EN_CC': 9}
EN_MASK = 1 << STATUS_BITS['EN']
COMPLETE_MASK = (1 << STATUS_BITS['ER']) | (1 << STATUS_BITS['DN'])
TO_MASK = 1 << STATUS_BITS['TO']
FIELDS = {
    'FLAGS': 'INT', 'ERR': 'INT', 'EXERR': 'DINT', 'REQ_LEN': 'INT', 'DN_LEN': 'INT',
    'LocalIndex': 'DINT', 'RemoteIndex': 'DINT', 'RemoteElement': 'STRING',
    'UnconnectedTimeout': 'DINT',
    'Class': 'INT', 'Instance': 'DINT', 'Attribute': 'INT',
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


@dataclass(frozen=True)
class IdentityRead:
    destination: Endpoint
    identity: Identity
    read_all: bool
    attribute: int
    class_id: int = 1
    instance: int = 1


@dataclass(frozen=True)
class DataTableTransfer:
    configuration: Configuration
    local_start: tuple[int, ...]
    remote: Endpoint | None
    remote_start: tuple[int, ...]


@dataclass(frozen=True)
class Pending:
    request: DataTableTransfer | IdentityRead
    deadline_us: int
    enabled: bool = True
    started: bool = False


class TransferError(Exception):
    def __init__(self, code):
        self.code = code


def _number(attributes, name, minimum, maximum, default=''):
    raw = attributes.get(name, default)
    if not re.fullmatch(r'[0-9]{1,6}', raw, re.ASCII) or not minimum <= int(raw) <= maximum:
        raise ModelError(f'MESSAGE {name} requires an integer in {minimum}..{maximum}')
    return int(raw)


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


def _identity_read(project, attributes):
    service = _hex_number(attributes, 'ServiceCode')
    cls = _hex_number(attributes, 'ObjectType')
    instance = _number(attributes, 'TargetObject', 0, 65535)
    if (cls, instance) != (1, 1) or service not in (0x01, 0x0E):
        raise ModelError('CIP Generic supports Get Attributes All and Get Attribute Single on Identity instance 1')
    read_all = service == 0x01
    attribute = _hex_number(attributes, 'AttributeNumber') if not read_all or attributes.get('AttributeNumber') else 0
    if not read_all and attribute not in IDENTITY_ATTRIBUTES:
        raise ModelError('CIP Generic Identity supports attributes 1..7')
    _number(attributes, 'RequestedLength', 0, 0, '0')
    if attributes.get('LocalElement', '').strip() or attributes.get('RemoteElement', '').strip():
        raise ModelError('CIP Generic Identity reads require an empty source and no request payload')
    destination = _parse_endpoint(attributes.get('DestinationTag', '').strip(), 0)
    if destination is None or destination.member_path or destination.variable or len(destination.coordinates) > 1:
        raise ModelError('CIP Generic Identity requires a DestinationTag with a fixed array start')
    identity = Identity.from_project('logix-v35-l85e', project)
    # Preserve the 16-bit pattern of an optional Get Attributes All placeholder.
    signed_attribute = attribute if attribute < 0x8000 else attribute - 0x10000
    return IdentityRead(destination, identity, read_all, signed_attribute)


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
    if (attributes.get('ConnectionPath', '').strip().casefold() != 'this'
            or attributes.get('CommTypeCode', '0') != '0'
            or any(attributes.get(name, '0').casefold() not in ('0', 'false')
                   for name in ('ConnectedFlag', 'CacheConnections', 'LargePacketUsage'))):
        raise ModelError('MESSAGE supports only unconnected CIP transfers on the THIS path')
    if kind == 'cip generic':
        return _identity_read(project, attributes)
    if kind not in ('cip data table read', 'cip data table write'):
        raise ModelError('MESSAGE supports CIP Data Table Read, Write and bounded CIP Generic Identity reads')
    return Configuration(kind.endswith('read'), _endpoint(attributes, 'Local'),
                         _endpoint(attributes, 'Remote'), attributes['RemoteElement'].strip(),
                         _number(attributes, 'RequestedLength', 1, MAX_ELEMENTS))


def _scope_endpoint(project, endpoint, scope):
    if scope and ':' not in endpoint.name:
        local_name = f'program:{scope.casefold()}.{endpoint.name}'
        if local_name in project.tags:
            return replace(endpoint, name=local_name)
    return endpoint


def _bind_local(project, configuration, scope):
    """Resolve the saved local element after all controller and program tags are loaded."""
    field = 'destination' if isinstance(configuration, IdentityRead) else 'local'
    return replace(configuration, **{field: _scope_endpoint(project, getattr(configuration, field), scope)})


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
        'FLAGS': 0, 'ERR': 0, 'EXERR': 0, 'REQ_LEN': 0, 'DN_LEN': 0,
        'UnconnectedTimeout': DEFAULT_TIMEOUT_US,
    }
    if isinstance(configuration, IdentityRead):
        record.update(Class=configuration.class_id, Instance=configuration.instance, Attribute=configuration.attribute)
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


def _identity_destination(memory, destination):
    key, paths, dtype = _region(memory, destination, destination.start(0), 1, remote=False, write=True, allow_alias=False)
    if dtype != 'SINT' or len(paths[0]) != 1:
        raise TransferError(0xFC)
    return key, paths[0][0]


def validate(engine, op, scope, kind='RLL'):
    if kind != 'RLL' or engine.mode != 'project' or scope in engine.memory.frames:
        raise ModelError('MSG requires a whole-project ladder scan outside AOIs')
    key = _control_key(engine, op.args[0], scope, op.name)
    configuration = engine.project.message_configs[key]
    endpoint = configuration.destination if isinstance(configuration, IdentityRead) else configuration.local
    if ':' in endpoint.name and endpoint.name.partition('.')[0] != f'program:{scope.casefold()}':
        raise ModelError('MSG local data must belong to the program executing the instruction')
    if isinstance(configuration, IdentityRead):
        try:
            _identity_destination(engine.memory, configuration.destination)
        except TransferError as error:
            raise ModelError(f'CIP Generic Identity requires a writable SINT array destination (16#{error.code:04X})') from error
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


def matches_timeout_attribute(op):
    return (len(op.args) == 4 and all(isinstance(arg, str) for arg in op.args)
            and op.args[0].casefold() == 'message'
            and op.args[2].casefold() == 'unconnectedtimeout')


def _timeout_operand(memory, ref, scope, instruction):
    resolve = memory.resolve if instruction == 'SSV' else memory.check_writable
    key, parts, dtype = resolve(ref, scope)
    if dtype not in ('DINT', 'TIME32') or isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError(f'{instruction} Message UnconnectedTimeout requires one scalar DINT or TIME32 tag')
    return key, parts, dtype


def validate_timeout_attribute(engine, op, scope, kind):
    memory = engine.memory
    if kind != 'RLL' or engine.mode != 'project' or scope in memory.frames:
        raise ModelError('Message UnconnectedTimeout requires a whole-project ladder scan outside AOIs')
    _control_key(engine, op.args[1], scope, op.name)
    previous = memory.structural
    memory.structural = True
    try:
        _timeout_operand(memory, op.args[3], scope, op.name)
    finally:
        memory.structural = previous


def execute_timeout_attribute(engine, op, scope):
    memory = engine.memory
    control = _control_key(engine, op.args[1], scope, op.name)
    key, parts, dtype = _timeout_operand(memory, op.args[3], scope, op.name)
    record = memory.values[control]
    if op.name == 'SSV':
        value = memory.at(key, parts)
        if type(value) is not int or value <= 0:
            raise ModelError('SSV Message UnconnectedTimeout requires a known positive value')
        record['UnconnectedTimeout'] = value
    else:
        memory.store(key, parts, coerce(record['UnconnectedTimeout'], dtype))


def prescan(engine, op, scope):
    key = validate(engine, op, scope)
    record = engine.memory.values[key]
    defaults = initial(engine.project, engine.project.message_configs[key])
    for name in ('LocalIndex', 'RemoteIndex', 'RemoteElement', 'UnconnectedTimeout', 'Class', 'Instance', 'Attribute'):
        if name in record:
            defaults[name] = record[name]
    engine.memory.values[key] = defaults
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


def _admit(engine, key, power):
    record = engine.memory.values[key]
    queue = engine._message_advance
    if len(queue) >= MAX_PENDING or sum(not request.started for request in queue.values()) >= THROTTLE_POSITIONS:
        return
    timeout_us = record['UnconnectedTimeout']
    if timeout_us <= 0:
        _set_flags(record, EN=power, ER=True)
        record['ERR'] = 0x03
        return
    request = engine.project.message_configs[key]
    if isinstance(request, IdentityRead):
        request = replace(request, class_id=record['Class'], instance=record['Instance'],
                          attribute=record['Attribute'])
    else:
        remote = _capture_remote(engine.memory, key, request, record)
        request = DataTableTransfer(request, request.local.start(record['LocalIndex']), remote,
                                    remote.start(record['RemoteIndex']) if remote is not None else ())
    queue[key] = Pending(request, deadline_us=engine.time_ms * 1000 + timeout_us, enabled=power)
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
            else:
                _admit(engine, key, power)
        elif not power:
            _set_flags(record, EN=False)
    elif power:
        record.update(FLAGS=(record['FLAGS'] & TO_MASK) | EN_MASK, ERR=0, EXERR=0, DN_LEN=0)
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


def _transfer(memory, request, status_word):
    if isinstance(request, IdentityRead):
        if (request.class_id, request.instance) != (1, 1):
            raise TransferError(0x05)
        key, start = _identity_destination(memory, request.destination)
        if request.read_all:
            payload = request.identity.all_attributes(status_word=status_word)
        else:
            if request.attribute not in IDENTITY_ATTRIBUTES:
                raise TransferError(0x14)
            payload = request.identity.attributes(status_word=status_word)[request.attribute]
        if len(payload) > len(memory.values[key]) - start:
            raise TransferError(0x11)
        for index, byte in enumerate(payload, start):
            memory.store(key, (index,), byte if byte < 128 else byte - 256)
        return len(payload)
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
    return _words(dtype, configuration.count, record)


def _finish(record, enabled, error, transferred=0):
    _set_flags(record, EN=enabled, EW=False, ST=False, TO=False, DN=not error, ER=bool(error))
    record.update(ERR=error, DN_LEN=transferred)


def service(memory, queue, now_ms, status_word):
    now_us = now_ms * 1000
    for key, pending in tuple(queue.items()):
        record = memory.values[key]
        transferred = 0
        if record['FLAGS'] & TO_MASK or now_us >= pending.deadline_us:
            error = 0xFE
        elif not pending.started:
            _set_flags(record, EW=False, ST=True)
            queue[key] = replace(pending, started=True)
            continue
        else:
            try:
                transferred = _transfer(memory, pending.request, status_word)
            except TransferError as failure:
                error = failure.code
            else:
                error = 0
        _finish(record, pending.enabled, error, transferred)
        del queue[key]
