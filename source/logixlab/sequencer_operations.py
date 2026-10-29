"""Bounded v35 5580 DINT ladder sequencers, with saved CONTROL LEN/POS."""
from . import bit_transfer, control_operations as controls
from .integer_math import CONTROLLERS, bit_value
from .model import ModelError

INSTRUCTIONS = frozenset(('SQI', 'SQO', 'SQL'))


def array_region(memory, ref, count, scope, *, writable=False):
    # Reuse static start/member/resource checks. Read-only input tables are legal.
    return controls.array_region(memory, ref, count, scope, writable=writable)


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('Sequencers require the v35 ControlLogix 5580 software profile')
    a = op.args;control_index = 2 if op.name == 'SQL' else 3
    if a[control_index + 1:] != ['?', '?']:
        raise ModelError('Sequencer LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, a[control_index], scope)
    key, _, dtype = array_region(memory, a[0], 0, scope, writable=op.name == 'SQL')
    if dtype != 'DINT':raise ModelError('Sequencer table must be a DINT array')
    _, parts, _ = memory.resolve(a[0], scope)
    ck, cp, _ = memory.resolve(a[control_index], scope)
    if ck == key and (parts[:len(cp)] == cp or cp[:len(parts)] == parts):
        raise ModelError('Sequencer table and CONTROL cannot overlap')
    if op.name == 'SQL':
        controls.scalar(memory, a[1], scope, 'DINT')
    else:
        bit_transfer.operand(memory, a[1], scope)
        controls.scalar(memory, a[2], scope, 'DINT', destination=op.name == 'SQO')
        if op.name == 'SQO':
            dk, _, _ = memory.resolve(a[2], scope)
            if dk == key:raise ModelError('SQO destination must not share the table base tag')


def prescan(memory, op, scope):
    if op.name != 'SQI':
        controls.control(memory, op.args[2 if op.name == 'SQL' else 3], scope)['EN'] = True


def execute(memory, op, power, scope):
    validate(memory, op, scope)
    a = op.args;n = op.name
    obj = controls.control(memory, a[2 if n == 'SQL' else 3], scope)
    if not power:
        if n != 'SQI':obj['EN'] = False
        return False
    length, position = controls.integer(obj, 'LEN'), controls.integer(obj, 'POS')
    if n == 'SQI':
        obj['ER'] = False
        if length <= 0 or not 0 <= position <= length:
            obj['ER'] = True
            return False
    else:
        obj['DN'] = False
        if length <= 0 or position < 0:
            obj.update(EN=True, ER=True, DN=position == length)
            return True
        if not controls.flag(obj, 'EN'):
            obj.update(EN=True, ER=False)
            position = position + 1 if position < length else 1
            obj['POS'] = position
        obj['DN'] = position == length
        if position > length:
            obj['ER'] = True
            return True
    # LEN counts cyclic rows 1..LEN; row zero is retained for startup. The
    # bounded profile qualifies the whole configured table including row zero.
    if length + 1 > controls.MAX_ELEMENTS:
        raise ModelError('Sequencer table exceeds the 4096-element software limit')
    try:
        key, paths, _ = array_region(memory, a[0], length + 1, scope, writable=n == 'SQL')
    except ModelError:
        if n == 'SQL':raise
        obj['ER'] = True
        return False if n == 'SQI' else True
    if n == 'SQL':
        value = memory.read(a[1], scope)
        memory.store(key, paths[position], bit_value(value, 'DINT'))
        return True
    width = bit_transfer.operand(memory, a[1], scope)
    mask = bit_transfer.unsigned(memory, a[1], scope, width)
    if not mask:return True
    source = memory.read(memory.address(key, paths[position]))
    if type(source) is not int:raise ModelError('Sequencer table row is unknown or not DINT')
    if n == 'SQI':
        value = memory.read(a[2], scope)
        return (source & mask) == (value & mask)
    old = 0 if mask == 0xffffffff else memory.read(a[2], scope)
    memory.write(a[2], bit_value((old & ~mask) | (source & mask), 'DINT'), scope)
    return True


def description():
    return dict(instructions=sorted(INSTRUCTIONS), language='RLL', profile='v35-5580-DINT-tables',
                rows='Startup row zero; edge advances through 1..LEN then wraps to one',
                held_true='SQO rewrites masked output; SQL reloads current row; SQI compares without advancing',
                masks='SINT/INT/DINT zero-filled patterns and 32-bit radix immediates',
                bounds='Static selected-member region including LEN+1 rows, maximum 4096 elements',
                invalid_state='ER with data retained for modeled SQI/SQO cases; SQL bounds stop and roll back',
                native_scan_parity=False, native_control_layout=False,
                remaining=['Mixed SQL/SQI source types', 'Indirect/alias/AOI table starts',
                           'Native faults/invalid-state parity and broader controller profiles'])
