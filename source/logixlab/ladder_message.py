"""Bounded, in-process ladder MSG transfers using the unconnected THIS route."""
import re
from dataclasses import dataclass, replace

from .integer_math import CONTROLLERS
from .model import ModelError

MAX_ELEMENTS = 64
MAX_PENDING = 32
FIELDS = dict.fromkeys(('EW', 'ER', 'DN', 'ST', 'EN', 'TO'), 'BOOL') | {
    'ERR': 'INT', 'EXERR': 'DINT', 'REQ_LEN': 'INT', 'DN_LEN': 'INT',
}
ADDRESS = re.compile(r'([A-Za-z_][A-Za-z_0-9]{0,39})(?:\[([0-9]{1,6})\])?', re.ASCII)


@dataclass(frozen=True)
class Endpoint:
    name: str
    index: int | None


@dataclass(frozen=True)
class Configuration:
    read: bool
    local: Endpoint
    remote: Endpoint
    count: int


@dataclass(frozen=True)
class Pending:
    configuration: Configuration
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


def _endpoint(attributes, side):
    match = ADDRESS.fullmatch(attributes.get(side + 'Element', '').strip())
    if match is None:
        raise ModelError(f'MESSAGE {side}Element requires a controller tag or literal array element')
    offset = _number(attributes, side + 'Index', 0, 999999, '0')
    index = int(match[2]) + offset if match[2] is not None else offset or None
    return Endpoint(match[1].casefold(), index)


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
                         _endpoint(attributes, 'Remote'), _number(attributes, 'RequestedLength', 1, MAX_ELEMENTS))


def initial(configuration):
    return dict.fromkeys(('EW', 'ER', 'DN', 'ST', 'EN', 'TO'), False) | {
        'ERR': 0, 'EXERR': 0, 'REQ_LEN': 2 * configuration.count, 'DN_LEN': 0,
    }


def _region(memory, endpoint, count, *, remote, write):
    tag = memory.project.tags.get(endpoint.name)
    if tag is None or tag.problem or tag.alias or tag.tag_class != 'Standard':
        raise TransferError(0x05)
    if tag.dtype.upper() != 'DINT':
        raise TransferError(0xFC)
    if ((write and tag.constant) or (remote and tag.external_access != 'Read/Write'
                                    and (write or tag.external_access != 'Read Only'))):
        raise TransferError(0x0F)
    value = memory.values[endpoint.name]
    if isinstance(value, list):
        start = endpoint.index or 0
        if start + count > len(value) or (value and isinstance(value[0], list)):
            raise TransferError(0x05)
        return endpoint.name, tuple((index,) for index in range(start, start + count))
    if endpoint.index is None and count == 1:
        return endpoint.name, ((),)
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
        _region(engine.memory, configuration.local, configuration.count, remote=False, write=configuration.read)
    except TransferError as error:
        raise ModelError(f'MSG local element cannot address the requested DINT span (16#{error.code:04X})') from error
    return key


def prescan(engine, op, scope):
    key = validate(engine, op, scope)
    engine.memory.values[key] = initial(engine.project.message_configs[key])
    if engine._message_advance is not None:
        engine._message_advance.pop(key, None)


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
            queue[key] = Pending(engine.project.message_configs[key])
    return power


def _transfer(memory, configuration):
    local_key, local_paths = _region(memory, configuration.local, configuration.count,
                                     remote=False, write=configuration.read)
    remote_key, remote_paths = _region(memory, configuration.remote, configuration.count,
                                       remote=True, write=not configuration.read)
    source, destination = ((remote_key, remote_paths), (local_key, local_paths)) if configuration.read else (
        (local_key, local_paths), (remote_key, remote_paths))
    values = [memory.at(source[0], path) for path in source[1]]
    if any(type(value) is not int for value in values):
        raise TransferError(0x03)
    for path, value in zip(destination[1], values):
        memory.store(destination[0], path, value)


def service(memory, queue):
    for key, pending in tuple(queue.items()):
        record = memory.values[key]
        if record['TO']:
            error = 0xFE
        elif not pending.started:
            record.update(EW=False, ST=True)
            queue[key] = replace(pending, started=True)
            continue
        else:
            try:
                _transfer(memory, pending.configuration)
            except TransferError as failure:
                error = failure.code
            else:
                error = 0
        record.update(EN=pending.enabled, EW=False, ST=False, TO=False,
                      DN=not error, ER=bool(error), ERR=error,
                      DN_LEN=0 if error else 2 * pending.configuration.count)
        del queue[key]
