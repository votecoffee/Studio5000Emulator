"""Ladder minor-fault records and controller summary for the v35 software model."""
from dataclasses import dataclass

from . import gsv_configuration
from .model import ModelError

ARITHMETIC_OVERFLOW = 4
INSTRUCTION_BIT = 1 << 4
EVENT_LIMIT = 32767
ATTRIBUTES = {'minorfaultbits': ('DINT', 'bits'), 'minorevents': ('INT', 'events')}


@dataclass(frozen=True)
class MinorFaultRecord:
    timestamp_us: int | None
    code: int
    cleared: bool = False


@dataclass
class MinorFaultLog:
    bits: int = 0
    events: int = 0

    def record_instruction_fault(self):
        self.bits |= INSTRUCTION_BIT
        self.events = min(self.events + 1, EVENT_LIMIT)


def matches(op):
    return (len(op.args) == 4 and all(isinstance(arg, str) for arg in op.args)
            and op.args[0].casefold() == 'faultlog'
            and op.args[2].casefold() in ATTRIBUTES)


def access(engine, op, scope, *, executing, kind='RLL'):
    if kind != 'RLL' or op.args[1]:
        raise ModelError('FaultLog minor attributes require ladder logic and an empty instance')
    gsv_configuration.current_instance(engine, 'Program', 'THIS', scope,
                                       executing=executing, allow_event=True)
    memory = engine.memory
    dtype, member = ATTRIBUTES[op.args[2].casefold()]
    ref = op.args[3]
    log = engine._program_advance.fault_log if executing and engine._program_advance is not None else None
    if executing and log is None:
        raise ModelError('FaultLog minor attributes require an active simulation advance')
    previous = memory.structural
    memory.structural = not executing
    try:
        if op.name == 'GSV':
            key, paths, destination_type = gsv_configuration.destination(memory, ref, scope, dtype, None)
            if executing:
                memory.store(key, paths[0], getattr(log, member))
            return key, paths, destination_type
        key, parts, source_type = memory.resolve(ref, scope)
        if source_type != dtype or isinstance(memory.at(key, parts), (dict, list)):
            raise ModelError(f'SSV FaultLog {op.args[2]} requires one scalar {dtype} source')
        if executing:
            value = memory.read(ref, scope)
            if member == 'events' and value != 0:
                raise ModelError('SSV FaultLog MinorEvents requires zero')
            setattr(log, member, value)
    finally:
        memory.structural = previous
