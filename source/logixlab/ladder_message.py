"""Bounded, in-process ladder MSG transfers using the unconnected THIS route."""
import math
import re
from dataclasses import dataclass, replace

from .integer_math import CONTROLLERS
from .model import ModelError

MAX_ELEMENTS = 64
MAX_PENDING = 32
FIELDS = dict.fromkeys(('EW', 'ER', 'DN', 'ST', 'EN', 'TO'), 'BOOL') | {
    'ERR': 'INT', 'EXERR': 'DINT', 'REQ_LEN': 'INT', 'DN_LEN': 'INT',
    'LocalIndex': 'DINT', 'RemoteIndex': 'DINT', 'RemoteElement': 'STRING',
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
class Pending:
    configuration: Configuration
    local_start: int | None
    remote: Endpoint | None
    remote_start: int | None
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
    if kind not in ('cip data table read', 'cip data table write'):
        raise ModelError('MESSAGE supports CIP Data Table Read and Write')
    if (attributes.get('ConnectionPath', '').strip().casefold() != 'this'
            or attributes.get('CommTypeCode', '0') != '0'
            or any(attributes.get(name, '0').casefold() not in ('0', 'false')
                   for name in ('ConnectedFlag', 'CacheConnections', 'LargePacketUsage'))):
        raise ModelError('MESSAGE supports only unconnected CIP transfers on the THIS path')
    return Configuration(kind.endswith('read'), _endpoint(attributes, 'Local'),
                         _endpoint(attributes, 'Remote'), attributes['RemoteElement'].strip(),
                         _number(attributes, 'RequestedLength', 1, MAX_ELEMENTS))


def _words(dtype, count):
    return (ELEMENT_BYTES.get(dtype, 0) * count + 1) // 2


def initial(project, configuration):
    local = project.tags.get(configuration.local.name)
    requested = _words(local.dtype.upper(), configuration.count) if local and not local.problem else 0
    record = dict.fromkeys(('EW', 'ER', 'DN', 'ST', 'EN', 'TO'), False) | {
        'ERR': 0, 'EXERR': 0, 'REQ_LEN': requested, 'DN_LEN': 0,
        'LocalIndex': configuration.local.offset, 'RemoteIndex': configuration.remote.offset,
    }
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


def validate(engine, op, scope, kind='RLL'):
    if kind != 'RLL' or engine.mode != 'project' or scope in engine.memory.frames:
        raise ModelError('MSG requires a whole-project ladder scan outside AOIs')
    key = op.args[0].casefold()
    configuration = engine.project.message_configs.get(key)
    if configuration is None:
        tag = engine.project.tags.get(key)
        detail = f': {tag.problem}' if tag and tag.dtype.upper() == 'MESSAGE' and tag.problem else ''
        raise ModelError('MSG requires a directly named controller MESSAGE with supported configuration' + detail)
    if f'program:{scope.casefold()}.{key}' in engine.project.tags:
        raise ModelError('MSG controller MESSAGE is shadowed by a program tag')
    try:
        # A variable start needs a valid array shape, independent of its saved index.
        _region(engine.memory, configuration.local, configuration.local.start(0), configuration.count,
                remote=False, write=configuration.read)
    except TransferError as error:
        raise ModelError(f'MSG local element cannot address the requested numeric span (16#{error.code:04X})') from error
    return key


def prescan(engine, op, scope):
    key = validate(engine, op, scope)
    record = engine.memory.values[key]
    defaults = initial(engine.project, engine.project.message_configs[key])
    defaults.update(LocalIndex=record['LocalIndex'], RemoteIndex=record['RemoteIndex'])
    if 'RemoteElement' in record:
        defaults['RemoteElement'] = record['RemoteElement']
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
        if len(queue) >= MAX_PENDING:
            record.update(ER=True, ERR=0x02)
        else:
            record['EW'] = True
            configuration = engine.project.message_configs[key]
            remote = _capture_remote(engine.memory, key, configuration, record)
            queue[key] = Pending(configuration, configuration.local.start(record['LocalIndex']),
                                 remote, remote.start(record['RemoteIndex']) if remote is not None else None)
    return power


def _transfer(memory, pending):
    configuration = pending.configuration
    if pending.remote is None:
        raise TransferError(0x05)
    local_key, local_paths, dtype = _region(memory, configuration.local, pending.local_start,
                                            configuration.count, remote=False, write=configuration.read)
    remote_key, remote_paths, remote_dtype = _region(memory, pending.remote, pending.remote_start,
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


def service(memory, queue):
    for key, pending in tuple(queue.items()):
        record = memory.values[key]
        transferred = 0
        if record['TO']:
            error = 0xFE
        elif not pending.started:
            record.update(EW=False, ST=True)
            queue[key] = replace(pending, started=True)
            continue
        else:
            try:
                transferred = _transfer(memory, pending)
            except TransferError as failure:
                error = failure.code
            else:
                error = 0
        record.update(EN=pending.enabled, EW=False, ST=False, TO=False,
                      DN=not error, ER=bool(error), ERR=error,
                      DN_LEN=transferred)
        del queue[key]
