"""Lazy scalar ladder arithmetic/bitwise rules and finite REAL remainder."""
import math
import operator

from . import time_values
from .bit_transfer import operand, unsigned
from .integer_math import CONTROLLERS, WIDE_TYPES, bit_value, execute as execute_integer, profile, typed_profile, typed_integer, pattern_width, pattern
from .model import INT_BITS, UNSIGNED_BITS, ModelError, coerce, literal
from .numeric_storage import floating_math_profile, lreal_math_source, write_lreal_math_result
from .real_math import real

BITWISE = frozenset(('AND', 'OR', 'XOR', 'NOT'))
ARITHMETIC = frozenset(('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'NEG', 'ABS'))
INSTRUCTIONS = BITWISE | ARITHMETIC


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def validate(engine, op, scope):
    if op.name not in INSTRUCTIONS or not available(engine.project):return False
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        if op.name in ARITHMETIC:
            if time_arithmetic(engine, op, scope):
                return True
            if floating_math_profile(memory, op, scope) or typed_profile(engine, op, scope, arithmetic=True):
                return True
        if op.name in BITWISE and any(typed_integer(ref) is not None for ref in op.args[:-1]):
            bitwise_specification(engine,op,scope)
            return True
        for ref in op.args:
            value = memory.read(ref, scope)
            if isinstance(value, (list, dict, bool)):
                raise ModelError('Scalar math requires numeric scalar operands')
            if op.name in BITWISE and isinstance(value, float):
                raise ModelError('Bitwise operands require integers')
        memory.check_writable(op.args[-1], scope)
        if op.name in BITWISE:
            bitwise_specification(engine, op, scope)
        else:
            arithmetic_profile(engine, op, scope)
    finally:
        memory.structural = previous
    return True


def time_arithmetic(engine, op, scope, *, execute=False):
    """Select a typed ADD/SUB result before the general numeric profiles."""
    if op.name not in ('ADD', 'SUB'):
        return False
    memory = engine.memory
    key, parts, dtype = memory.check_writable(op.args[2], scope)
    if dtype not in time_values.TYPES:
        return False
    if isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('Time/date arithmetic requires one scalar destination')

    sources = op.args[:2]
    types = [time_values.operand_type(memory, ref, scope) for ref in sources]
    if any(source not in time_values.TYPES for source in types):
        raise ModelError('Time/date arithmetic requires time/date source operands')
    timestamps = sum(source in time_values.DATE_TYPES for source in types)
    if op.name == 'ADD' and timestamps == 2:
        raise ModelError('Time/date ADD cannot sum two timestamps')
    if (dtype in time_values.DATE_TYPES) != (timestamps == 1):
        expected = 'timestamp' if timestamps == 1 else 'duration'
        raise ModelError(f'Time/date {op.name} requires a {expected} destination')

    if execute:
        left, right = (time_values.read_operand(memory, ref, scope) * time_values.ns_per_tick(source)
                       for ref, source in zip(sources, types))
        result = left + right if op.name == 'ADD' else left - right
        ticks = time_values.exact_ticks(result, dtype, f'{op.name} to {dtype}')
        memory.store(key, parts, coerce(ticks, dtype))
    return True


def execute_lreal(engine,op,scope):
    memory=engine.memory
    values=[lreal_math_source(memory,ref,scope,execute=True) for ref in op.args[:-1]]
    a=values[0]
    if op.name in ('NEG','ABS'):result=-a if op.name=='NEG' else abs(a)
    else:
        b=values[1]
        if op.name in ('DIV','MOD') and b==0:raise ModelError(op.name+' LREAL divide by zero')
        result=({'ADD':operator.add,'SUB':operator.sub,'MUL':operator.mul,'DIV':operator.truediv,'MOD':math.fmod}[op.name])(a,b)
    write_lreal_math_result(memory, op.args[-1], result, scope)
    return True


def execute_real(engine,op,scope):
    """Calculate from finite REAL sources and round before destination conversion."""
    memory=engine.memory
    from .numeric_storage import real_math_source
    values=[real_math_source(memory,ref,scope,execute=True) for ref in op.args[:-1]]
    a=values[0]
    if op.name in ('NEG','ABS'):result=-a if op.name=='NEG' else abs(a)
    else:
        b=values[1]
        if op.name in ('DIV','MOD') and b==0:raise ModelError(op.name+' REAL divide by zero')
        result=({'ADD':operator.add,'SUB':operator.sub,'MUL':operator.mul,'DIV':operator.truediv,'MOD':math.fmod}[op.name])(a,b)
    memory.write(op.args[-1],real(result),scope)
    return True


def arithmetic_profile(engine, op, scope):
    """Mixed tag arithmetic with lossless source ranges and bounded constants.

    Keep legacy homogeneous/immediate and narrow paths separate. In particular,
    a positive saved signed value does not authorize an unsigned mixed form.
    """
    if op.name not in ARITHMETIC or not available(engine.project):
        return profile(engine, op, scope)
    floating = floating_math_profile(engine.memory, op, scope)
    if floating:
        return floating
    typed=typed_profile(engine,op,scope,arithmetic=True)
    if typed:return typed
    types, constants = [], []
    for ref in op.args:
        try:value = literal(ref)
        except ValueError:types.append(engine.memory.resolve(ref, scope)[2])
        else:types.append(None);constants.append(value)
    declared = set(types) - {None}
    if not declared & WIDE_TYPES or len(declared) == 1:
        return profile(engine, op, scope)
    if any(dtype not in INT_BITS for dtype in declared):
        raise ModelError('Mixed widening arithmetic requires integer scalar tags')
    def bounds(dtype):
        bits = INT_BITS[dtype]
        return (0, (1 << bits) - 1) if dtype in UNSIGNED_BITS else (-(1 << (bits - 1)), (1 << (bits - 1)) - 1)
    low, high = bounds(types[-1])
    if any(bounds(dtype)[0] < low or bounds(dtype)[1] > high for dtype in types[:-1] if dtype is not None):
        raise ModelError('Mixed arithmetic destination must cover every source type range')
    for value in constants:
        if type(value) is not int or not -(1 << 31) <= value < 1 << 31:
            raise ModelError('Widening arithmetic constants require signed DINT literals')
        coerce(value, types[-1])
    return types[-1]


def bitwise_specification(engine, op, scope):
    """Integer tag widths; retain the separate legacy wide-immediate rules."""
    memory = engine.memory
    if any(typed_integer(ref) is not None for ref in op.args[:-1]):
        widths=[pattern_width(memory,ref,scope) for ref in op.args[:-1]]
        key,parts,dtype=memory.check_writable(op.args[-1],scope)
        if dtype not in INT_BITS or isinstance(memory.at(key,parts),(list,dict)):
            raise ModelError('Typed bitwise result requires one scalar integer destination')
        return widths+[INT_BITS[dtype]],dtype,None
    widths, types, immediate = [], [], False
    for index, ref in enumerate(op.args):
        destination = index == len(op.args) - 1
        if not destination:
            try:
                literal(ref)
            except ValueError:
                pass
            else:
                widths.append(operand(memory, ref, scope));types.append(None)
                immediate = True
                continue
        key, parts, dtype = (memory.check_writable if destination else memory.resolve)(ref, scope)
        if dtype not in INT_BITS or isinstance(memory.at(key, parts), (list, dict)):
            raise ModelError('Bitwise tag operands require scalar signed/unsigned integers')
        widths.append(INT_BITS[dtype]);types.append(dtype)
    legacy = profile(engine, op, scope) if immediate and set(types) & WIDE_TYPES else None
    return widths, types[-1], legacy


def execute_bitwise(engine, op, scope):
    """Zero-extend declared tag patterns and keep signed/unsigned result bits."""
    memory = engine.memory
    widths, dtype, legacy = bitwise_specification(engine, op, scope)
    if legacy is not None:
        return execute_integer(engine, op, scope, legacy)
    values = [pattern(memory, ref, scope, width)
              for ref, width in zip(op.args[:-1], widths[:-1])]
    value = ~values[0] if op.name == 'NOT' else {
        'AND': operator.and_, 'OR': operator.or_, 'XOR': operator.xor}[op.name](*values)
    memory.write(op.args[-1], bit_value(value, dtype), scope)
    return True


def real_remainder(dividend, divisor):
    """Finite float32 inputs/result; fmod retains the dividend's sign.

    Avoid forming the quotient: valid tiny divisors can overflow that
    intermediate, and subtraction can lose a representable small remainder.
    Native precision, math flags and zero-divisor minor faults are unqualified.
    """
    a, b = real(dividend), real(divisor)
    if b == 0:
        raise ModelError('MOD divide by zero after REAL conversion')
    try:
        return real(math.fmod(a, b))
    except (ValueError, OverflowError) as error:
        raise ModelError('MOD outside the finite REAL remainder profile') from error


def description(project):
    return dict(available=available(project), profile='v35-5580-lazy-scalar-math',
                language='RLL', instructions=sorted(INSTRUCTIONS),
                validation='Declared scalar types, references, permissions and existing wide-profile rules; no saved values/live indices',
                selection='False/prescan skip operands; true instructions require all source values; full writes establish unknown destinations',
                arithmetic='Exact integer quotient/remainder and checked destination writes; homogeneous/immediate rules retained',
                time_date_arithmetic=dict(instructions=['ADD', 'SUB'], types=sorted(time_values.TYPES),
                    operands='Scalar time/date tags or typed literals, with a duration or timestamp result',
                    result='Two durations yield a duration. Mixed operands yield a timestamp. Timestamp subtraction yields a signed duration.',
                    precision='Calculate exact integer nanoseconds before checking destination precision and range',
                    native_runtime_parity=False),
                widening_arithmetic=dict(instructions=sorted(ARITHMETIC), types=list(INT_BITS),
                    operands='Mixed integer tags with optional signed-DINT constants; destination covers every complete source tag type range',
                    constants='Known integer literals in signed DINT range, representable in destination; larger/typed/REAL constants remain excluded',
                    conversion='Signed values retain their sign; unsigned values retain their nonnegative value; all arithmetic stays integer-exact',
                    selection='Declared-type checks even false; false/prescan skip live values and indices; true full writes establish unknowns',
                    excluded='Narrowing, mixed signed to unsigned, REAL/LREAL and larger/typed or unrepresentable constants; native overflow/status/fault parity',
                    native_runtime_parity=False),
                typed_integer_arithmetic=dict(instructions=sorted(ARITHMETIC),constant_types=['LINT','UDINT','ULINT'],
                    constants='Decimal L/U/UL integers checked at their declared source range; existing bounded DINT constants must fit the result type',
                    selection='An integer result covers every complete declared source type range; no saved value justifies narrowing or signed-to-unsigned conversion',
                    calculation='Exact integer operations; DIV truncates toward zero, MOD has the dividend sign; result overflow faults atomically',
                    scope='RLL v35 5580 only; bitwise/MEQ, floating sources, other results/consumers and native status/fault/lifecycle parity remain separate',
                    native_runtime_parity=False),
                lreal_arithmetic=dict(instructions=sorted(ARITHMETIC),types=['LREAL'],
                    operands='Scalar numeric tags, bounded DINT/finite REAL and decimal typed L/U/UL integer or floating L/l constants; no LREAL source is required when the destination is LREAL',
                    selection_by_destination='The scalar LREAL result selects binary64 inputs and calculation, including constant-only calls and NEG/ABS',
                    selection_by_source='An LREAL tag or floating L/l constant also selects binary64, including with REAL or integer results',
                    destination_types=sorted({*INT_BITS, 'REAL', 'LREAL'}),
                    result_conversion='Convert the finite binary64 result to the declared destination once; integer destinations round ties to even and require range',
                    constants='Bounded DINT, finite REAL, decimal L/U/UL integers and finite floating L/l LREAL; declared precision checked before binary64 promotion; existing radix must fit signed DINT',
                    source_types=sorted({*INT_BITS,'REAL','LREAL'}),
                    promotion='Convert every required source to binary64 before calculation; signed/unsigned values retain their numeric sign, REAL retains its stored precision',
                    calculation='Finite host binary64; MOD uses fmod with dividend sign; zero divisors and nonfinite results fault atomically',
                    selection='Structural/lazy operands, complete unknown writes and existing alias/member/AOI references',
                    native_runtime_parity=False),
                real_arithmetic=dict(instructions=sorted(ARITHMETIC),source_types=sorted({*INT_BITS,'REAL'}),
                    destination='Scalar REAL tag; no REAL source is required; constant-only calls execute',
                    integer_destinations=sorted(WIDE_TYPES),
                    selection_by_source='A REAL tag or floating immediate selects float32 for LINT and unsigned results',
                    integer_conversion='Convert the float32 result to the declared integer by nearest-even rounding with range checks',
                    constants='Bounded DINT/finite REAL and decimal L/U/UL integer constants; declared integer range checked before float32 conversion',
                    calculation='Convert every required source to finite float32 before calculation; round the result to float32; stored inputs remain unchanged',
                    boundaries='LREAL inputs select binary64 before final destination conversion',
                    native_runtime_parity=False),
                real_remainder=dict(sources=['SINT','INT','DINT','REAL'], destinations=['SINT','INT','DINT','REAL'],
                                    selection='A REAL source or floating immediate selects float32 inputs, host fmod and float32 result',
                                    conversion='Integer results round nearest, ties to even; out-of-range results roll back',
                                    zero='Zero after float32 conversion stops and rolls back; native zero-result/minor fault is not modeled',
                                    native_precision=False),
                bitwise=dict(types=list(INT_BITS), instructions=sorted(BITWISE),
                             promotion='Zero-extend declared source patterns; NOT inverts after promotion; keep destination low bits',
                             immediates='Narrow forms retain signed DINT/32-bit radix patterns; any wide operand with an immediate retains homogeneous, representable signed-DINT rules',
                             destination='Keep destination low bits and reinterpret signed/unsigned; full writes establish unknowns without floating-point conversion',
                             wide='All eight integer tag types may mix; wide immediate and arithmetic profiles remain separate', native_precision=False),
                typed_integer_bitwise=dict(instructions=sorted(BITWISE),constant_types=['LINT','UDINT','ULINT'],
                    operands='At least one decimal L/U/UL source; scalar integer tags and existing bounded DINT/32-bit radix patterns may mix',
                    conversion='Preserve each declared-width bit pattern, zero-extend before combining; NOT inverts after promotion and result keeps destination low bits',
                    range='Typed source bounds checked structurally; integer destinations may truncate/reinterpret complete bit patterns',
                    scope='RLL v35 5580 only; REAL/LREAL/BOOL, typed radix, MVM/BTD/other consumers and native status/fault/lifecycle parity remain separate',
                    native_runtime_parity=False),
                bindings='Aliases, selected elements/members and existing AOI InOut/local bindings',
                failures='Reached unknowns, invalid indices, zero divisors, excluded ranges and later faults roll back the advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Other arithmetic destination conversions/mixed signed-to-unsigned forms, larger/typed arithmetic constants, mixed-wide/typed bitwise immediates, REAL/LREAL bitwise and other wide/unsigned/LREAL remainder mixtures',
                           'Native overflow/status/fault/lifecycle/packed layout and broader controller qualification'])
