"""Structural contacts/coils and state-dependent one-shot reads for v35 5580."""
from .integer_math import CONTROLLERS
from .model import ModelError

INSTRUCTIONS = frozenset(('XIC', 'XIO', 'OTE', 'OTL', 'OTU', 'ONS', 'OSR', 'OSF'))
WRITES = {'OTE': (0,), 'OTL': (0,), 'OTU': (0,), 'ONS': (0,), 'OSR': (0, 1), 'OSF': (0, 1)}


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def validate(engine, op, scope):
    if op.name not in INSTRUCTIONS or not available(engine.project):return False
    memory = engine.memory
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


def execute(memory, op, power, scope):
    name, args = op.name, op.args
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
        memory.write(args[0], power, scope)
        if name == 'ONS':return pulse
        memory.write(args[1], pulse, scope)
    return power


def description(project):
    return dict(available=available(project), profile='v35-5580-bit-logic', language='RLL',
                instructions=sorted(INSTRUCTIONS),
                operands='Scalar BOOL, selected logical BOOL array elements/members, aliases and existing integer bit references',
                validation='Structural type/shape/permission checks without saved values or live indices',
                contacts='False rung skips XIC/XIO values and indices; true rung requires a known value',
                coils='OTE establishes full BOOL values; false OTL/OTU retain values and skip live references',
                one_shots='ONS/OSR false and OSF true skip prior storage reads; other transitions require known history',
                prescan='Existing OTE clear, ONS/OSR storage set, OSF storage clear and pulse-output clear; latches retained',
                packed_bits='Partial writes require known backing integers to preserve neighboring bits',
                array_recovery='Whole-project XIC/XIO/OTE/OTL/OTU/ONS skip the operation when a ladder handler clears Type 4 Code 20',
                failures='Reached unknowns, unrecovered array faults and later errors roll back the advance and existing AOI state',
                native_runtime_parity=False,
                remaining=['Native packed BOOL layout, fault/postscan/lifecycle parity and broader controller qualification'])
