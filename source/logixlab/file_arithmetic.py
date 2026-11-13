"""Bounded ladder FAL ALL/numeric/INC iteration with existing CPT expressions."""
from . import control_operations as controls
from . import file_incremental as incremental
from .integer_math import CONTROLLERS, WIDE_TYPES
from . import lreal_expressions, wide_st
from .model import ArrayBoundsError, ModelError, coerce, literal

INSTRUCTIONS = frozenset(('FAL',))


class RealCalculationOverflow(OverflowError):
    """A reached FAL calculation or completed result cannot fit finite REAL."""


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
    if dtype not in lreal_expressions.NUMERIC or isinstance(memory.at(key, parts), (list, dict, bool)):
        raise ModelError('FAL requires a writable numeric scalar destination')
    ck, cp, _ = memory.resolve(op.args[0], scope)
    if key == ck and parts[:len(cp)] == cp:
        raise ModelError('FAL destination must not overlap its CONTROL record')
    return key, parts, dtype


def calculate(engine,expression,scope,dtype,*,execute=False):
    memory = engine.memory
    floating = lreal_expressions.analyze(expression, memory, scope, dtype, consumer='FAL')
    if floating is not None:
        return lreal_expressions.evaluate(expression, memory, scope, floating) if execute else None
    profile = wide_st.analyze(expression, memory, scope, dtype, consumer='FAL')
    if profile is not None:
        if profile[1] != 'number':
            raise ModelError('FAL requires a numeric expression result')
        if execute:
            return wide_st.evaluate(expression, memory, scope, profile)
    elif execute:
        return expression.evaluate(memory, scope, dtype)
    else:
        expression.validate(memory, scope, dtype)


def validate(engine, op, scope):
    memory = engine.memory
    if engine.project.version != '35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('FAL requires the v35 ControlLogix 5580 software profile')
    if op.args[1:3] != ['?', '?']:
        raise ModelError('FAL LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, op.args[0], scope)
    count = mode(op.args[3])
    expression = engine.extensions.expression(op.args[5], bcd=True, floating_literals=True, integer_literals=True)
    if count=='INC':incremental.validate(engine,op,scope)
    previous = memory.structural
    try:
        memory.structural = True
        calculate(engine,expression,scope,destination(memory,op,scope)[2])
    finally:memory.structural = previous
    return count, expression


def execute(engine, op, power, scope):
    count, expression = validate(engine, op, scope)
    memory = engine.memory
    obj = controls.control(memory, op.args[0], scope)
    previous = obj.copy()
    control_id = incremental.identity(engine,op.args[0],scope)
    previous_retry = control_id in engine._file_arithmetic_retry
    writes = {}

    def write_element():
        key, parts, dtype = destination(memory, op, scope)
        try:
            value = calculate(engine, expression, scope, dtype, execute=True)
        except OverflowError as error:
            # Binary64 evaluation already reports its own ModelError. Keep
            # integer, domain, unknown-value and reference failures separate.
            if dtype != 'REAL':raise
            raise RealCalculationOverflow from error
        # An address can be written repeatedly in one call. Retain its first
        # value, including an unknown value, for recovery of that call.
        writes.setdefault((key, tuple(parts)), memory.at(key, parts))
        try:
            memory.write(op.args[4], value, scope)
        except OverflowError as error:
            # A finite binary64 result can overflow only at REAL storage.
            # Memory coerces before storing, so the failing cell is intact.
            if dtype != 'REAL':raise
            raise RealCalculationOverflow from error
        engine._file_arithmetic_retry.discard(control_id)

    try:
        if count == 'INC':
            return incremental.execute(engine, op, power, scope, obj, write_element)
        return _execute(engine, power, obj, count, write_element, control_id)
    except RealCalculationOverflow:
        obj.update(ER=True, DN=False)
        engine._file_arithmetic_retry.add(control_id)
        return power
    except ArrayBoundsError:
        for (key, parts), value in writes.items():
            memory.store(key, parts, value)
        obj.update(previous)
        if previous_retry:engine._file_arithmetic_retry.add(control_id)
        else:engine._file_arithmetic_retry.discard(control_id)
        raise


def _execute(engine, power, obj, count, write_element, control_id):
    if controls.flag(obj, 'ER'):return power
    if controls.flag(obj, 'DN'):
        if not power:
            obj.update(EN=False, DN=False, ER=False, POS=0)
            engine._file_arithmetic_retry.discard(control_id)
        return power
    enabled = controls.flag(obj, 'EN')
    if not power and (count is None or not enabled):
        if count is None:obj['EN'] = False
        return False
    length, position = controls.file_cursor(obj, 'FAL')
    if length > controls.MAX_ELEMENTS:
        raise ModelError('FAL exceeds the 4096-element software limit')
    start = position + int(enabled and control_id not in engine._file_arithmetic_retry)
    obj['EN'] = True
    if start >= length:
        obj.update(EN=bool(power), DN=True)
        return power
    end = length if count is None else min(length, start + count)
    for position in range(start, end):
        engine.budget -= 1
        if engine.budget < 0:raise ModelError('FAL instruction budget exceeded')
        obj['POS'] = position
        write_element()
    if end == length:obj.update(EN=bool(power), DN=True)
    return power


def description():
    return dict(profile='v35-5580-FAL-ALL-numeric-INC', language='RLL', modes=['ALL','positive DINT immediate','INC'],
                types=sorted(lreal_expressions.NUMERIC), exact_integer_types=sorted(WIDE_TYPES),
                binary64=dict(selection='LREAL source, destination or floating L/l literal',
                    destination_types=sorted(lreal_expressions.NUMERIC),
                    modes=['ALL','positive DINT immediate','INC'],
                    calculation='Use the bounded binary64 ladder evaluator per reached iteration; convert only the completed result to the destination type',
                    native_runtime_parity=False),
                wide_expressions='Matching declared numeric tag/result type; exact intermediates, ABS/basic arithmetic/bitwise, representable signed-DINT or matching decimal L/U/UL literals', expressions='Existing bounded CPT grammar including qualified narrow FRD/TOD, destination-indexed per iteration',
                typed_integer_literals=dict(types=['LINT','UDINT','ULINT'],suffixes=['L/l','U/u','UL/ul/Ul/uL'],
                    range='Matching numeric tag/literal/result type; check declared literal range with its unary sign before execution',
                    precision='Exact integers at declared width; every numeric intermediate must fit',
                    excluded='Mixed typed/tag types, floating/typed radix forms, other arguments and native parity',
                    native_runtime_parity=False),
                cursor='Last computed position retained, including exhaustion; native final-cursor parity unverified',
                real_overflow='Reached float32 calculation or finite binary64-to-REAL store overflow latches ER at the attempted POS, preserves completed writes and retries that position after repair; RES clears pending retry',
                numeric='Active numeric work continues on false rungs; partial EN stays set',
                completion='DN set at last element; false completed call clears EN/DN/POS; ER inhibits',
                writes='Sequential live reads/writes; source/destination array overlap can propagate',
                array_recovery='Type 4 Code 20 restores CONTROL and destination values from before the current whole-project call',
                prescan='No initialization', max_elements=controls.MAX_ELEMENTS,
                aoi='RLL exact-type/dimension InOut and represented local operands; frame-scoped indices and canonical per-CONTROL progress',
                native_fault_classification=False, native_cursor_parity=False, native_math_status=False,
                incremental=incremental.description(),
                remaining=['Saved active INC controls and native internal edge state', 'Other mixed FAL numeric promotion, numeric LREAL bitwise/BCD and additional functions',
                           'Broader AOI lifecycle/schema and native overflow/fault/status/partial-write parity'])
