"""Structural contacts/coils and state-dependent one-shot reads for v35 5580."""
from .integer_math import CONTROLLERS
from .model import ArrayBoundsError, ModelError

INSTRUCTIONS = frozenset(('XIC', 'XIO', 'OTE', 'OTL', 'OTU', 'ONS', 'OSR', 'OSF'))
WRITES = {'OTE': (0,), 'OTL': (0,), 'OTU': (0,), 'ONS': (0,), 'OSR': (0, 1), 'OSF': (0, 1)}
PRESCAN_WRITES = frozenset(('OTE', 'ONS', 'OSR', 'OSF'))
MINOR_FLAG = 's:minor'
STATUS_COILS = frozenset(('OTE', 'OTL', 'OTU'))
STATUS_BIT_OPS = STATUS_COILS | {'XIC', 'XIO'}
CARRY_FLAG = 's:c'
OVERFLOW_FLAG = 's:v'
MATH_FLAGS = {
    CARRY_FLAG: 'rung_carry',
    OVERFLOW_FLAG: 'rung_overflow',
    's:n': 'rung_negative',
    's:z': 'rung_zero',
}


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def validate(engine, op, scope, *, kind='RLL'):
    if op.name not in INSTRUCTIONS or not available(engine.project):return False
    memory = engine.memory
    if any(ref.casefold() == MINOR_FLAG for ref in op.args):
        if kind != 'RLL' or op.name not in STATUS_BIT_OPS or scope in memory.frames:
            raise ModelError('S:MINOR requires a ladder contact or coil outside AOI bodies')
        return True
    if any(ref.casefold() in MATH_FLAGS for ref in op.args):
        if kind != 'RLL' or op.name not in STATUS_BIT_OPS:
            raise ModelError('Math status flags require a ladder contact or coil')
        if op.name == 'OTU' and op.args[0].casefold() == CARRY_FLAG:
            raise ModelError('S:C requires a ladder contact, OTE or OTL')
        return True
    previous = memory.structural
    memory.structural = True
    try:
        for ref in op.args:
            if memory.resolve(ref, scope)[2] != 'BOOL' or isinstance(memory.read(ref, scope), (list, dict)):
                raise ModelError('Bit instruction requires scalar BOOL or an integer bit')
        for index in WRITES.get(op.name, ()):memory.check_writable(op.args[index], scope)
    finally:
        memory.structural = previous
    return True


def write_pulse(memory, args, storage, pulse, scope):
    # The output index can depend on the storage write. Save the original
    # scalar or packed word at its resolved address for bounds recovery.
    key, parts, _ = memory.check_writable(args[0], scope)
    if parts and isinstance(parts[-1], tuple):
        parts = parts[:-1]
    previous = memory.at(key, parts)
    memory.write(args[0], storage, scope)
    try:
        memory.write(args[1], pulse, scope)
    except ArrayBoundsError:
        memory.store(key, parts, previous)
        raise


def prescan(memory, op, scope):
    name, args = op.name, op.args
    ref = args[0].casefold()
    if name == 'OTE' and (ref == MINOR_FLAG or ref in MATH_FLAGS):
        return
    try:
        if name in ('OSR', 'OSF'):
            write_pulse(memory, args, name == 'OSR', False, scope)
        else:
            memory.write(args[0], name == 'ONS', scope)
    except ArrayBoundsError:
        # Prescan continues after the instruction, with any storage write undone.
        pass


def execute(memory, op, power, scope):
    name, args = op.name, op.args
    ref = args[0].casefold()
    if ref in MATH_FLAGS:
        attribute = MATH_FLAGS[ref]
        if name in STATUS_COILS:
            if name == 'OTE' or power:
                value = power and name != 'OTU'
                if ref == OVERFLOW_FLAG:
                    memory.record_overflow(value)
                else:
                    setattr(memory, attribute, value)
            return power
        return power and (bool(getattr(memory, attribute)) == (name == 'XIC'))
    if ref == MINOR_FLAG:
        if name in ('XIC', 'XIO'):
            return power and (memory.minor_fault == (name == 'XIC'))
        if name == 'OTE' or power:
            memory.minor_fault = power and name != 'OTU'
        return power
    if name in ('XIC', 'XIO'):
        if not power:return False
        value = bool(memory.read(args[0], scope))
        return value if name == 'XIC' else not value
    if name == 'OTE':memory.write(args[0], power, scope)
    elif name in ('OTL', 'OTU'):
        if power:memory.write(args[0], name == 'OTL', scope)
    else:
        # ONS/OSR false and OSF true establish state without reading history.
        needs_history = not power if name == 'OSF' else power
        pulse = bool(memory.read(args[0], scope)) if needs_history else False
        if name != 'OSF' and needs_history:pulse = not pulse
        if name == 'ONS':
            memory.write(args[0], power, scope)
            return pulse

        write_pulse(memory, args, power, pulse, scope)
    return power


def description(project):
    return dict(available=available(project), profile='v35-5580-bit-logic', language='RLL',
                instructions=sorted(INSTRUCTIONS),
                operands='Scalar BOOL, selected logical BOOL array elements/members, aliases and existing integer bit references',
                validation='Structural type/shape/permission checks without saved values or live indices',
                contacts='False rung skips XIC/XIO values and indices; true rung requires a known value',
                coils='OTE establishes full BOOL values; false OTL/OTU retain values and skip live references',
                one_shots='ONS/OSR false and OSF true skip prior storage reads; other transitions require known history',
                prescan='OTE clears; ONS/OSR set storage; OSF clears storage; OSR/OSF clear pulse output; out-of-bounds selections skip the instruction',
                packed_bits='Partial writes require known backing integers to preserve neighboring bits',
                array_recovery='Whole-project handlers can clear Type 4 Code 20 and skip the faulting instruction or its outer ladder AOI call',
                pulse_recovery='OSR/OSF restore the original storage value before handling an out-of-bounds output index',
                minor_status='S:MINOR contacts and coils outside AOI bodies; task-local scan flag for reported DINT subscript overflow',
                carry_status='S:C contacts, OTE and OTL share the rung flag set by integer ADD/SUB. Each rung starts clear and nested routines keep independent state.',
                numeric_status='S:N and S:Z contacts, OTE, OTL and OTU share independent rung flags. A modeled stored numeric result replaces both flags after destination conversion.',
                overflow_status='S:V contacts and OTE/OTL/OTU use a rung-local flag. A powered OTU clears it and preserves the task minor flag. Signed narrow arithmetic, narrowing MOV, divide/modulo by zero and infinity-to-signed-integer results can set it.',
                failures='Reached unknowns, unrecovered array faults and later errors roll back the advance and existing AOI state',
                native_runtime_parity=False,
                remaining=['Native packed BOOL layout, fault/postscan/lifecycle parity and broader controller qualification'])
