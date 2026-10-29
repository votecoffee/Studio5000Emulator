"""Logical CONTROL state with bounded ladder shifts and numeric FIFO/LIFO pairs.

No native CONTROL byte layout, fault record or unimplemented consumer is implied.
Length/position pseudo-operands use saved LEN/POS, never per-scan initialization.
"""
import re

from .model import ModelError, coerce, literal

FLAGS = ('EN', 'EU', 'DN', 'EM', 'ER', 'UL', 'IN', 'FD')
INSTRUCTIONS = frozenset(('BSL', 'BSR', 'FFL', 'FFU', 'LFL', 'LFU'))
NUMERIC = frozenset(('SINT', 'INT', 'DINT', 'REAL'))
MAX_ELEMENTS = 4096


def default():
    return dict(LEN=0, POS=0, **dict.fromkeys(FLAGS, False))


def control(memory, ref, scope):
    key, parts, dtype = memory.check_writable(ref, scope)
    if dtype != 'CONTROL':
        raise ModelError('A scalar writable CONTROL record is required')
    obj = memory.at(key, parts)
    if not isinstance(obj, dict) or set(obj) != set(default()):
        raise ModelError('A scalar writable CONTROL record is required')
    return obj


def integer(obj, name):
    value = obj[name]
    if type(value) is not int:
        raise ModelError('CONTROL.' + name + ' is unknown or not an integer')
    return coerce(value, 'DINT')


def flag(obj, name):
    if type(obj[name]) is not bool:
        raise ModelError('CONTROL.' + name + ' is unknown or not BOOL')
    return obj[name]


def static_array(memory, ref, scope, *, writable=True):
    # Static starting references keep .POS out of array subscripts. References
    # are re-resolved on each scan; the selected member remains the boundary.
    if not re.fullmatch(r'[A-Za-z_][\w:]*(?:\.[A-Za-z_]\w*|\[\d+(?:,\d+)*\])*', ref):
        raise ModelError('Shift/FIFO start requires a static array reference')
    if scope in memory.frames:
        raise ModelError('Shift/FIFO array bindings inside AOIs are not yet qualified')
    explicit = re.match(r'Program:(\w+)\.(.+)', ref, re.I)
    owner, local = explicit.groups() if explicit else (scope, ref)
    name = re.match(r'[A-Za-z_][\w:]*', local)[0]
    tag = memory.project.tags.get(f'Program:{owner}.{name}'.lower()) or memory.project.tags.get(name.lower())
    if tag is not None and tag.alias:
        raise ModelError('Alias starting arrays are not yet qualified for shifts/FIFO')
    key, parts, dtype = (memory.check_writable if writable else memory.resolve)(ref, scope)
    if dtype not in NUMERIC:raise ModelError('Shift/FIFO operand requires a supported numeric array')
    value = memory.at(key, parts)
    if not isinstance(value, list) and not any(isinstance(memory.at(key, parts[:i]), list)
                                             for i, part in enumerate(parts) if isinstance(part, int)):
        raise ModelError('Shift/FIFO operand must address an array')
    return key, parts, dtype


def array_region(memory, ref, count, scope, *, writable=True):
    static_array(memory, ref, scope, writable=writable)
    if not 0 <= count <= MAX_ELEMENTS:
        raise ModelError('Shift/FIFO operation exceeds the 4096-element software limit')
    return memory.region(ref, count, scope)


def scalar(memory, ref, scope, dtype, *, destination=False):
    if not destination:
        try:
            value = literal(ref)
        except ValueError:
            pass
        else:
            if type(value) not in (int, float) or isinstance(value, float) and dtype != 'REAL':
                raise ModelError('FIFO immediate must match its numeric element type')
            if type(value) is int:coerce(value, 'DINT')
            coerce(value, dtype)
            return
    key, parts, kind = (memory.check_writable if destination else memory.resolve)(ref, scope)
    if kind != dtype or isinstance(memory.at(key, parts), (dict, list)):
        raise ModelError('FIFO currently requires matching scalar SINT/INT/DINT/REAL types')


def validate(memory, op, scope):
    n, a = op.name, op.args
    shift = n in ('BSL', 'BSR')
    ctrl = a[1] if shift else a[2]
    control(memory, ctrl, scope)
    if a[3:] != (['?'] if shift else ['?', '?']):
        raise ModelError('Use neutral-text ? pseudo-operands; CONTROL.LEN/POS hold saved values')
    array = a[1] if n in ('FFL', 'LFL') else a[0]
    key, _, dtype = array_region(memory, array, 0, scope)
    _, parts, _ = memory.resolve(array, scope)
    ck, cp, _ = memory.resolve(ctrl, scope)
    if ck == key and (parts[:len(cp)] == cp or cp[:len(parts)] == parts):
        raise ModelError('Array and CONTROL storage cannot overlap')
    if shift:
        if dtype != 'DINT':raise ModelError('BSL/BSR requires a DINT array')
        bk, bp, bt = memory.resolve(a[2], scope)
        if bt != 'BOOL':raise ModelError('BSL/BSR source must be a BOOL tag or integer bit')
        if bk == ck and (bp[:len(cp)] == cp or cp[:len(bp)] == bp):
            raise ModelError('Shift source must not overlap its CONTROL record')
    else:
        if dtype not in NUMERIC:raise ModelError('FIFO currently supports SINT/INT/DINT/REAL arrays')
        value = a[0] if n in ('FFL', 'LFL') else a[1]
        scalar(memory, value, scope, dtype, destination=n in ('FFU', 'LFU'))
        if n in ('FFU', 'LFU'):
            dk, dp, _ = memory.resolve(value, scope)
            if dk == key:
                raise ModelError('FFU destination must not share the FIFO base tag')


def fifo_status(obj):
    length, position = integer(obj, 'LEN'), integer(obj, 'POS')
    obj['DN'] = length <= 0 or position < 0 or position >= length
    obj['EM'] = length <= 0 or position <= 0
    return length, position


def prescan(memory, op, scope):
    obj = control(memory, op.args[1] if op.name in ('BSL', 'BSR') else op.args[2], scope)
    if op.name in ('BSL', 'BSR'):
        obj.update(EN=False, DN=False, ER=False, POS=0)
    else:
        obj['EN' if op.name in ('FFL', 'LFL') else 'EU'] = True
        fifo_status(obj)


def reset(memory, ref, scope):
    obj = control(memory, ref, scope)
    obj.update(dict.fromkeys(FLAGS, False));obj['POS'] = 0


def shift(memory, op, power, scope):
    a = op.args;obj = control(memory, a[1], scope)
    if not power:
        obj.update(EN=False, DN=False, ER=False, POS=0)
        return False
    if flag(obj, 'EN'):return True
    length = integer(obj, 'LEN')
    obj.update(dict.fromkeys(FLAGS, False));obj['EN'] = True
    if length < 0:
        obj['ER'] = True
        return True
    source = memory.read(a[2], scope)
    if type(source) is not bool:raise ModelError('Shift source bit is unknown or not BOOL')
    if length == 0:
        obj.update(DN=True, POS=0, UL=source)
        return True
    count = (length + 31) // 32
    key, paths, _ = array_region(memory, a[0], count, scope)
    words = [memory.read(memory.address(key, path)) for path in paths]
    if any(type(word) is not int for word in words):raise ModelError('Shift requires known DINT array words')
    bits = sum((word & 0xffffffff) << (32 * i) for i, word in enumerate(words))
    mask = (1 << length) - 1
    if op.name == 'BSL':
        unloaded = bool(bits & (1 << (length - 1)))
        selected = ((bits << 1) | int(source)) & mask
    else:
        unloaded = bool(bits & 1)
        selected = ((bits & mask) >> 1) | (int(source) << (length - 1))
    result = (bits & ~mask) | selected
    for i, path in enumerate(paths):
        word = (result >> (32 * i)) & 0xffffffff
        memory.store(key, path, word - (1 << 32) if word & (1 << 31) else word)
    obj.update(DN=True, POS=length, UL=unloaded)
    return True


def fifo(memory, op, power, scope):
    n, a = op.name, op.args;obj = control(memory, a[2], scope)
    length, position = fifo_status(obj)
    latch = 'EN' if n in ('FFL', 'LFL') else 'EU'
    if not power:
        obj[latch] = False
        return False
    if flag(obj, latch):return True
    obj[latch] = True
    if length <= 0 or position < 0:return True
    if position > length:
        raise ModelError('FIFO POS beyond LEN is outside the qualified runtime profile')
    if n in ('FFL', 'LFL') and position == length:return True
    array = a[1] if n in ('FFL', 'LFL') else a[0]
    key, paths, dtype = array_region(memory, array, length, scope)
    if n in ('FFL', 'LFL'):
        source = memory.read(a[0], scope)
        memory.store(key, paths[position], coerce(source, dtype))
        obj['POS'] += 1
    elif position == 0:
        memory.write(a[1], 0, scope)
    elif n == 'LFU':
        value = memory.read(memory.address(key, paths[position - 1]))
        memory.store(key, paths[position - 1], coerce(0, dtype))
        memory.write(a[1], value, scope)
        obj['POS'] -= 1
    else:
        values = [memory.read(memory.address(key, path)) for path in paths]
        if any(type(value) not in (int, float) for value in values):raise ModelError('FIFO array contains unknown numeric data')
        for path, value in zip(paths, values[1:] + [0]):memory.store(key, path, coerce(value, dtype))
        memory.write(a[1], values[0], scope)
        obj['POS'] -= 1
    fifo_status(obj)
    return True


def execute(memory, op, power, scope):
    validate(memory, op, scope)
    return shift(memory, op, power, scope) if op.name in ('BSL', 'BSR') else fifo(memory, op, power, scope)


def description():
    return dict(instructions=sorted(INSTRUCTIONS), language='RLL', control_fields=['LEN', 'POS', *FLAGS],
                shifts='DINT arrays, rising EN, low-to-high word order, partial last word preserved',
                fifo='Matching SINT/INT/DINT/REAL, rising EN/EU, saved LEN/POS, selected-member bounds',
                fifo_empty='Empty unload writes zero once per qualified rising edge',
                lifo='LFL writes current POS then increments; LFU pops and zeroes POS-1 without shifting other elements',
                max_elements=MAX_ELEMENTS, native_control_layout=False, native_fault_classification=False,
                remaining=['FIFO structures/strings/conversions', 'Remaining FIFO/LIFO/sequencer forms and file consumers',
                           'Indirect/alias/AOI starting arrays', 'Native invalid-state and scan parity'])
