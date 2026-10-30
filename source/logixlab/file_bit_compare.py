"""Bounded DINT ladder FBC/DDT with separate compare and result controls."""
from . import control_operations as controls
from .bit_transfer import unsigned
from .integer_math import CONTROLLERS, bit_value
from .model import ModelError

INSTRUCTIONS = frozenset(('FBC', 'DDT'))
MAX_BITS = 4096


def region(memory, ref, count, scope, *, writable=False):
    key, paths, dtype = controls.array_region(memory, ref, count, scope, writable=writable)
    if dtype != 'DINT':raise ModelError('FBC/DDT arrays require DINT elements')
    return key, paths


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('FBC/DDT require the v35 ControlLogix 5580 software profile')
    a = op.args
    if a[4:6] != ['?', '?'] or a[7:] != ['?', '?']:
        raise ModelError('FBC/DDT LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, a[3], scope);controls.control(memory, a[6], scope)
    source, _ = region(memory, a[0], 0, scope)
    reference, _ = region(memory, a[1], 0, scope, writable=op.name == 'DDT')
    result, _ = region(memory, a[2], 0, scope, writable=True)
    compare = memory.resolve(a[3], scope)[0];output = memory.resolve(a[6], scope)[0]
    if compare == output or {compare, output} & {source, reference, result}:
        raise ModelError('FBC/DDT controls require separate base tags from each other and data arrays')
    if result in (source, reference) or op.name == 'DDT' and source == reference:
        raise ModelError('FBC/DDT writable array roles require separate base tags')


def prescan(memory, op, scope):
    compare = controls.control(memory, op.args[3], scope)
    result = controls.control(memory, op.args[6], scope)
    compare.update(EN=False, FD=False)
    if controls.flag(compare, 'DN'):
        compare.update(DN=False, POS=0);result.update(DN=False, POS=0)


def execute(engine, op, power, scope):
    memory = engine.memory;validate(memory, op, scope)
    if not power:
        prescan(memory, op, scope);return False
    a = op.args;compare = controls.control(memory, a[3], scope)
    if controls.flag(compare, 'EN'):return True
    compare['EN'] = True
    if controls.flag(compare, 'DN'):return True
    compare.update(ER=False, FD=False)
    length, position = controls.integer(compare, 'LEN'), controls.integer(compare, 'POS')
    if length <= 0 or position < 0:
        compare['ER'] = True;return True
    if length > MAX_BITS:raise ModelError('FBC/DDT exceed the 4096-bit software limit')
    words = (length + 31) // 32
    sk, sources = region(memory, a[0], words, scope)
    rk, references = region(memory, a[1], words, scope, writable=op.name == 'DDT')
    if position >= length:
        compare.update(POS=length, DN=True);return True
    result = controls.control(memory, a[6], scope)
    while position < length:
        engine.budget -= 1
        if engine.budget < 0:raise ModelError('FBC/DDT instruction budget exceeded')
        word, bit = divmod(position, 32)
        source = unsigned(memory, memory.address(sk, sources[word]), '', 32)
        reference = unsigned(memory, memory.address(rk, references[word]), '', 32)
        if (source ^ reference) & (1 << bit):
            compare['FD'] = True
            if op.name == 'DDT':
                memory.store(rk, references[word], bit_value(reference ^ (1 << bit), 'DINT'))
            if controls.flag(result, 'DN'):result.update(DN=False, POS=0)
            capacity, offset = controls.integer(result, 'LEN'), controls.integer(result, 'POS')
            if capacity <= 0 or not 0 <= offset < capacity:
                raise ModelError('FBC/DDT require positive result LEN and POS within capacity; full lists require DN')
            dk, destinations = region(memory, a[2], capacity, scope, writable=True)
            memory.store(dk, destinations[offset], position)
            result['POS'] = offset + 1
            if result['POS'] >= capacity:result['DN'] = True
            position += 1;compare['POS'] = position
            if controls.flag(compare, 'IN'):
                if position >= length:compare['DN'] = True
                return True
        else:
            position += 1;compare['POS'] = position
    compare['DN'] = True
    return True


def description():
    return dict(profile='v35-5580-DINT-bit-diagnostics', language='RLL', instructions=sorted(INSTRUCTIONS),
                modes='Compare.IN false: all mismatches; true: stop after one mismatch per enable edge',
                positions='Compare LEN/POS count bits; Result LEN/POS count DINT entries; LSB first',
                fbc='Record mismatching bit offsets; source and reference unchanged',
                ddt='Record offsets and update only mismatching reference bits',
                result='Append at POS; DN marks capacity, next mismatch wraps to entry zero',
                false_prescan='Clear compare EN/FD; when compare DN was set, reset both positions and done bits',
                max_bits=MAX_BITS, max_result_entries=controls.MAX_ELEMENTS,
                invalid_state='Compare LEN<=0 or POS<0 sets ER; bounds/unknown/result-state failures roll back advance',
                native_runtime_parity=False,
                remaining=['AOIs and alias/indirect array starts', 'Overlapping writable roles and shared base controls',
                           'Other controller profiles and complete native cursor/status/fault/partial-write parity'])
