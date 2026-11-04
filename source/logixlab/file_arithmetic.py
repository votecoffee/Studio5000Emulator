"""Bounded ladder FAL ALL/numeric/INC iteration with existing CPT expressions."""
from . import control_operations as controls
from . import file_incremental as incremental
from .integer_math import CONTROLLERS, WIDE_TYPES
from . import wide_st
from .model import ModelError, coerce, literal

INSTRUCTIONS = frozenset(('FAL',))
NUMERIC = controls.NUMERIC | WIDE_TYPES


def mode(text):
    if text.upper() == 'ALL':return None
    if text.upper() == 'INC':return 'INC'
    try:value = literal(text)
    except ValueError as error:raise ModelError('FAL supports ALL, INC or a positive immediate numeric mode') from error
    if type(value) is not int or value <= 0:
        raise ModelError('FAL numeric mode must be a positive DINT immediate')
    return coerce(value, 'DINT')


def destination(memory, op, scope):
    key, parts, dtype = memory.check_writable(op.args[4], scope)
    if dtype not in NUMERIC or isinstance(memory.at(key, parts), (list, dict, bool)):
        raise ModelError('FAL requires a writable supported integer or REAL scalar destination')
    ck, cp, _ = memory.resolve(op.args[0], scope)
    if key == ck and parts[:len(cp)] == cp:
        raise ModelError('FAL destination must not overlap its CONTROL record')
    return dtype


def calculate(engine,expression,scope,dtype,*,execute=False):
    profile=wide_st.analyze(expression,engine.memory,scope,dtype,consumer='FAL')
    if profile is not None:
        if profile[1]!='number':raise ModelError('FAL requires a numeric expression result')
        if execute:return wide_st.evaluate(expression,engine.memory,scope,profile)
    elif execute:return expression.evaluate(engine.memory,scope,dtype)
    else:expression.validate(engine.memory,scope,dtype)


def validate(engine, op, scope):
    memory = engine.memory
    if engine.project.version != '35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('FAL requires the v35 ControlLogix 5580 software profile')
    if op.args[1:3] != ['?', '?']:
        raise ModelError('FAL LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, op.args[0], scope)
    count = mode(op.args[3]);expression = engine.extensions.expression(op.args[5])
    if count=='INC':incremental.validate(engine,op,scope)
    previous = memory.structural
    try:
        memory.structural = True
        calculate(engine,expression,scope,destination(memory,op,scope))
    finally:memory.structural = previous
    return count, expression


def execute(engine, op, power, scope):
    count, expression = validate(engine, op, scope)
    memory = engine.memory
    if count=='INC':
        def operation():
            dtype=destination(memory,op,scope)
            memory.write(op.args[4],calculate(engine,expression,scope,dtype,execute=True),scope)
        return incremental.execute(engine,op,power,scope,operation)
    obj = controls.control(memory, op.args[0], scope)
    if controls.flag(obj, 'ER'):return power
    if controls.flag(obj, 'DN'):
        if not power:obj.update(EN=False, DN=False, ER=False, POS=0)
        return power
    enabled = controls.flag(obj, 'EN')
    if not power and (count is None or not enabled):
        if count is None:obj['EN'] = False
        return False
    length, position = controls.integer(obj, 'LEN'), controls.integer(obj, 'POS')
    if length < 0 or position < 0 or position > length:
        raise ModelError('FAL requires nonnegative LEN/POS with POS no greater than LEN')
    if length > controls.MAX_ELEMENTS:
        raise ModelError('FAL exceeds the 4096-element software limit')
    start = position + int(enabled)
    obj['EN'] = True
    if start >= length:
        obj.update(EN=bool(power), DN=True)
        return power
    end = length if count is None else min(length, start + count)
    for position in range(start, end):
        engine.budget -= 1
        if engine.budget < 0:raise ModelError('FAL instruction budget exceeded')
        obj['POS'] = position
        dtype = destination(memory, op, scope)
        memory.write(op.args[4], calculate(engine,expression,scope,dtype,execute=True), scope)
    if end == length:obj.update(EN=bool(power), DN=True)
    return power


def description():
    return dict(profile='v35-5580-FAL-ALL-numeric-INC', language='RLL', modes=['ALL','positive DINT immediate','INC'],
                types=sorted(NUMERIC), exact_integer_types=sorted(WIDE_TYPES),
                wide_expressions='Matching declared numeric tag/result type; exact intermediates, ABS/basic arithmetic/bitwise and representable signed-DINT literals', expressions='Existing bounded CPT grammar, destination-indexed per iteration',
                cursor='Last computed position retained, including exhaustion; native final-cursor parity unverified',
                numeric='Active numeric work continues on false rungs; partial EN stays set',
                completion='DN set at last element; false completed call clears EN/DN/POS; ER inhibits',
                writes='Sequential live reads/writes; source/destination array overlap can propagate',
                prescan='No initialization', max_elements=controls.MAX_ELEMENTS,
                aoi='RLL exact-type/dimension InOut and represented local operands; frame-scoped indices and canonical per-CONTROL progress',
                native_fault_classification=False, native_cursor_parity=False, native_math_status=False,
                incremental=incremental.description(),
                remaining=['Saved active INC controls and native internal edge state', 'Mixed FAL numeric promotion, LREAL and additional expression functions',
                           'Broader AOI lifecycle/schema and native overflow/fault/status/partial-write parity'])
