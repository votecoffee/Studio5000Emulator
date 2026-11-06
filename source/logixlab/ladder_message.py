"""Bounded, in-process ladder MSG transfers using the unconnected THIS route."""
import math
import re
from dataclasses import dataclass, replace

from .identity import Identity
from .integer_math import CONTROLLERS
from .model import ModelError, coerce

MAX_ELEMENTS = 64
MAX_PENDING = 32
DEFAULT_TIMEOUT_US = 30_000_000
IDENTITY_ATTRIBUTES = frozenset(range(1, 8))
FIELDS = dict.fromkeys(('EW', 'ER', 'DN', 'ST', 'EN', 'TO'), 'BOOL') | {
    'ERR': 'INT', 'EXERR': 'DINT', 'REQ_LEN': 'INT', 'DN_LEN': 'INT',
    'LocalIndex': 'DINT', 'RemoteIndex': 'DINT', 'RemoteElement': 'STRING',
    'UnconnectedTimeout': 'DINT',
    'Class': 'INT', 'Instance': 'DINT', 'Attribute': 'INT',
}
ELEMENT_BYTES = {'SINT': 1, 'INT': 2, 'DINT': 4, 'LINT': 8, 'REAL': 4}
NAME = r'[A-Za-z_][A-Za-z_0-9]{0,39}'
ADDRESS = re.compile(rf'((?:Program:{NAME}\.)?{NAME})(?:\[([0-9]{{1,6}}|\*)\])?', re.ASCII | re.I)


@dataclass(frozen=True)
class Endpoint:
    name: str
    subscript: int | None
    offset: int
    variable: bool

    def start(self, parameter):
        if self.variable:
            return parameter
        if self.subscript is not None:
            return self.subscript + self.offset
        return self.offset or None


@dataclass(frozen=True)
class Configuration:
    read: bool
    local: Endpoint
    remote: Endpoint
    remote_text: str
    count: int


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
    local_start: int | None
    remote: Endpoint | None
    remote_start: int | None


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
    name, selector = match.groups()
    subscript = int(selector) if selector not in (None, '*') else None
    return Endpoint(name.casefold(), subscript, offset, selector == '*')


def _endpoint(attributes, side):
    offset = _number(attributes, side + 'Index', 0, 999999, '0')
    endpoint = _parse_endpoint(attributes.get(side + 'Element', '').strip(), offset)
    if endpoint is None or (side == 'Local' and ':' in endpoint.name):
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
    if destination is None or destination.variable or ':' in destination.name:
        raise ModelError('CIP Generic Identity requires a controller DestinationTag with a fixed array start')
    identity = Identity.from_project('logix-v35-l85e', project)
    # Preserve the 16-bit pattern of an optional Get Attributes All placeholder.
    signed_attribute = attribute if attribute < 0x8000 else attribute - 0x10000
    return IdentityRead(destination, identity, read_all, signed_attribute)


def from_tag(project, tag, element, dims):
    if (project.version != '35' or project.processor.upper() not in CONTROLLERS
            or tag.scope or tag.constant or tag.tag_class != 'Standard' or dims):
        raise ModelError('MESSAGE requires a writable scalar Standard controller tag in the v35 5580 profile')
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


def _words(dtype, count):
    return (ELEMENT_BYTES.get(dtype, 0) * count + 1) // 2


def initial(project, configuration):
    record = dict.fromkeys(('EW', 'ER', 'DN', 'ST', 'EN', 'TO'), False) | {
        'ERR': 0, 'EXERR': 0, 'REQ_LEN': 0, 'DN_LEN': 0,
        'UnconnectedTimeout': DEFAULT_TIMEOUT_US,
    }
    if isinstance(configuration, IdentityRead):
        record.update(Class=configuration.class_id, Instance=configuration.instance, Attribute=configuration.attribute)
        return record
    local = project.tags.get(configuration.local.name)
    requested = _words(local.dtype.upper(), configuration.count) if local and not local.problem else 0
    record.update(REQ_LEN=requested, LocalIndex=configuration.local.offset, RemoteIndex=configuration.remote.offset)
    # Preserve long authored addresses that predate the writable STRING field.
    text = configuration.remote_text
    if len(text) <= project.string_capacity('STRING'):
        element = project.default('STRING')
        element['LEN'] = len(text)
        element['DATA'][:len(text)] = text.encode('ascii')
        record['RemoteElement'] = element
    return record


def _region(memory, endpoint, start, count, *, remote, write):
    tag = memory.project.tags.get(endpoint.name)
    if tag is None or tag.problem or tag.alias or tag.tag_class != 'Standard':
        raise TransferError(0x05)
    project = memory.project
    if tag.scope and not project.program_configuration.type_attributes(tag.scope, source_sha256=project.sha256):
        raise TransferError(0x05)
    dtype = tag.dtype.upper()
    if dtype not in ELEMENT_BYTES:
        raise TransferError(0xFC)
    if ((write and tag.constant) or (remote and tag.external_access != 'Read/Write'
                                    and (write or tag.external_access != 'Read Only'))):
        raise TransferError(0x0F)
    value = memory.values[endpoint.name]
    if isinstance(value, list):
        start = start or 0
        if not 0 <= start <= len(value) - count or (value and isinstance(value[0], list)):
            raise TransferError(0x05)
        return endpoint.name, tuple((index,) for index in range(start, start + count)), dtype
    if start is None and count == 1:
        return endpoint.name, ((),), dtype
    raise TransferError(0x05)


def _control_key(engine, name, scope, instruction):
    key = name.casefold()
    if key not in engine.project.message_configs:
        tag = engine.project.tags.get(key)
        detail = f': {tag.problem}' if tag and tag.dtype.upper() == 'MESSAGE' and tag.problem else ''
        raise ModelError(f'{instruction} requires a directly named controller MESSAGE with supported configuration' + detail)
    if f'program:{scope.casefold()}.{key}' in engine.project.tags:
        raise ModelError(f'{instruction} controller MESSAGE is shadowed by a program tag')
    return key


def _identity_destination(memory, destination):
    key, paths, dtype = _region(memory, destination, destination.start(0), 1, remote=False, write=True)
    if dtype != 'SINT' or not paths[0]:
        raise TransferError(0xFC)
    return key, paths[0][0]


def validate(engine, op, scope, kind='RLL'):
    if kind != 'RLL' or engine.mode != 'project' or scope in engine.memory.frames:
        raise ModelError('MSG requires a whole-project ladder scan outside AOIs')
    key = _control_key(engine, op.args[0], scope, op.name)
    configuration = engine.project.message_configs[key]
    if isinstance(configuration, IdentityRead):
        try:
            _identity_destination(engine.memory, configuration.destination)
        except TransferError as error:
            raise ModelError(f'CIP Generic Identity requires a writable SINT array destination (16#{error.code:04X})') from error
        return key
    try:
        # A variable start needs a valid array shape, independent of its saved index.
        _region(engine.memory, configuration.local, configuration.local.start(0), configuration.count,
                remote=False, write=configuration.read)
    except TransferError as error:
        raise ModelError(f'MSG local element cannot address the requested numeric span (16#{error.code:04X})') from error
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


def execute(engine, op, power):
    key = op.args[0].casefold()
    record = engine.memory.values[key]
    queue = engine._message_advance
    pending = queue.get(key)
    if pending is not None:
        if pending.enabled != power:
            queue[key] = replace(pending, enabled=power)
    elif not power:
        record['EN'] = False
    elif not record['EN']:
        record.update(EN=True, EW=False, ST=False, DN=False, ER=False, ERR=0, EXERR=0, DN_LEN=0)
        timeout_us = record['UnconnectedTimeout']
        if timeout_us <= 0:
            record.update(ER=True, ERR=0x03)
        elif len(queue) >= MAX_PENDING:
            record.update(ER=True, ERR=0x02)
        else:
            record['EW'] = True
            request = engine.project.message_configs[key]
            if isinstance(request, IdentityRead):
                request = replace(request, class_id=record['Class'], instance=record['Instance'],
                                  attribute=record['Attribute'])
            else:
                remote = _capture_remote(engine.memory, key, request, record)
                request = DataTableTransfer(request, request.local.start(record['LocalIndex']), remote,
                                            remote.start(record['RemoteIndex']) if remote is not None else None)
            queue[key] = Pending(request, deadline_us=engine.time_ms * 1000 + timeout_us)
    return power


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
    if request.remote is None:
        raise TransferError(0x05)
    local_key, local_paths, dtype = _region(memory, configuration.local, request.local_start,
                                            configuration.count, remote=False, write=configuration.read)
    remote_key, remote_paths, remote_dtype = _region(memory, request.remote, request.remote_start,
                                                     configuration.count, remote=True, write=not configuration.read)
    if dtype != remote_dtype:
        raise TransferError(0xFC)
    source, destination = ((remote_key, remote_paths), (local_key, local_paths)) if configuration.read else (
        (local_key, local_paths), (remote_key, remote_paths))
    values = [memory.at(source[0], path) for path in source[1]]
    if dtype == 'REAL':
        known = all(type(value) is float and math.isfinite(value) for value in values)
    else:
        known = all(type(value) is int for value in values)
    if not known:
        raise TransferError(0x03)
    for path, value in zip(destination[1], values):
        memory.store(destination[0], path, value)
    return _words(dtype, configuration.count)


def service(memory, queue, now_ms, status_word):
    now_us = now_ms * 1000
    for key, pending in tuple(queue.items()):
        record = memory.values[key]
        transferred = 0
        if record['TO'] or now_us >= pending.deadline_us:
            error = 0xFE
        elif not pending.started:
            record.update(EW=False, ST=True)
            queue[key] = replace(pending, started=True)
            continue
        else:
            try:
                transferred = _transfer(memory, pending.request, status_word)
            except TransferError as failure:
                error = failure.code
            else:
                error = 0
        record.update(EN=pending.enabled, EW=False, ST=False, TO=False,
                      DN=not error, ER=bool(error), ERR=error,
                      DN_LEN=transferred)
        del queue[key]
