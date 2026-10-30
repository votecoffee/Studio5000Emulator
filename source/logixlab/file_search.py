"""Bounded ladder FSC ALL/numeric/INC search using saved CONTROL state."""
from . import control_operations as controls
from . import file_incremental as incremental
from .integer_math import CONTROLLERS
from .model import ModelError, coerce, literal

INSTRUCTIONS = frozenset(('FSC',))


def mode(text):
    if text.upper() == 'ALL':return None
    if text.upper() == 'INC':return 'INC'
    try:value = literal(text)
    except ValueError as error:raise ModelError('FSC supports ALL, INC or a positive immediate numeric mode') from error
    if type(value) is not int or value <= 0:
        raise ModelError('FSC numeric mode must be a positive DINT immediate')
    return coerce(value, 'DINT')


def validate(engine, op, scope):
    memory = engine.memory
    if engine.project.version != '35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('FSC requires the v35 ControlLogix 5580 software profile')
    if scope in memory.frames:raise ModelError('FSC execution inside AOIs remains unqualified')
    if op.args[1:3] != ['?', '?']:
        raise ModelError('FSC LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, op.args[0], scope)
    count = mode(op.args[3]);expression = engine.extensions.condition(op.args[4])
    if count=='INC':incremental.validate(engine,op,scope)
    # Type-check dynamic subscripts at a structural position, without consuming
    # unknown data or rejecting a saved final cursor before execution begins.
    previous = memory.structural
    try:
        memory.structural = True
        expression.validate(memory, scope)
    finally:memory.structural = previous
    return count, expression


def execute(engine, op, power, scope):
    count, expression = validate(engine, op, scope)
    memory = engine.memory
    if count=='INC':
        return incremental.execute(engine,op,power,scope,lambda:expression.evaluate(memory,scope),search=True)
    obj = controls.control(memory, op.args[0], scope)
    if controls.flag(obj, 'ER') or controls.flag(obj, 'IN'):return power
    if controls.flag(obj, 'DN'):
        if not power:obj.update(EN=False, DN=False, POS=0)
        return power
    enabled = controls.flag(obj, 'EN')
    if not power and (count is None or not enabled):
        if count is None:obj['EN'] = False
        return False
    length, position = controls.integer(obj, 'LEN'), controls.integer(obj, 'POS')
    if length < 0 or position < 0 or position > length:
        raise ModelError('FSC requires nonnegative LEN/POS with POS no greater than LEN')
    if length > controls.MAX_ELEMENTS:
        raise ModelError('FSC exceeds the 4096-element software limit')
    if length == 0:
        obj.update(EN=bool(power), DN=True, FD=False)
        return power
    start = position + int(enabled)
    obj.update(EN=True, FD=False)
    if start >= length:
        obj.update(EN=bool(power), DN=True)
        return power
    end = length if count is None else min(length, start + count)
    for position in range(start, end):
        engine.budget -= 1
        if engine.budget < 0:raise ModelError('FSC instruction budget exceeded')
        obj['POS'] = position
        if expression.evaluate(memory, scope):
            obj.update(FD=True, IN=True)
            if position == length - 1:obj.update(DN=True, EN=bool(power))
            return power
    if end == length:obj.update(DN=True, EN=bool(power))
    return power


def description():
    return dict(profile='v35-5580-FSC-ALL-numeric-INC', language='RLL', modes=['ALL','positive DINT immediate','INC'],
                expressions='Existing bounded CMP grammar/types; dynamic CONTROL.POS subscripts',
                found='FD/IN set and POS identifies matching element; clear IN to resume after it',
                cursor='Last compared position retained, including exhaustion; native final-cursor parity unverified',
                numeric='Active numeric searches continue on false rungs; partial EN stays set',
                completion='DN set at last element; false with IN clear resets EN/DN/POS and retains FD/ER',
                prescan='No initialization', max_elements=controls.MAX_ELEMENTS,
                native_fault_classification=False, native_cursor_parity=False,
                incremental=incremental.description(),
                remaining=['Saved active INC controls and native internal edge state', 'Additional expression types/functions',
                           'AOI execution and native faults/status/invalid-state parity'])
