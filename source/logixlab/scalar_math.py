"""Lazy scalar ladder arithmetic/bitwise rules and finite REAL remainder."""
import math
import operator

from . import time_values
from .bit_transfer import operand, unsigned
from .integer_math import CONTROLLERS, WIDE_TYPES, bit_value, bitwise_immediate_widths, profile, typed_profile, typed_integer, radix_profile, pattern
from .model import INT_BITS, UNSIGNED_BITS, ModelError, coerce, literal
from .numeric_storage import floating_math_profile, lreal_math_source, typed_literal, write_lreal_math_result
from .real_math import real

BITWISE = frozenset(('AND', 'OR', 'XOR', 'NOT'))
BITWISE_FLOATS = {'REAL': 'DINT', 'LREAL': 'LINT'}
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
            if floating_math_profile(memory,op,scope,radix=True):return True
            if radix_profile(engine,op,scope,arithmetic=True):return True
            if time_arithmetic(engine, op, scope):
                return True
            if floating_math_profile(memory, op, scope) or typed_profile(engine, op, scope, arithmetic=True):
                return True
        if op.name in BITWISE:
            bitwise_specification(engine, op, scope)
            return True
        for ref in op.args:
            value = memory.read(ref, scope)
            if isinstance(value, (list, dict, bool)):
                raise ModelError('Scalar math requires numeric scalar operands')
        memory.check_writable(op.args[-1], scope)
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
    values=[lreal_math_source(memory,ref,scope,execute=True,radix=True) for ref in op.args[:-1]]
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
    values=[real_math_source(memory,ref,scope,execute=True,radix=True) for ref in op.args[:-1]]
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
    floating = floating_math_profile(engine.memory,op,scope,radix=True)
    if floating:return floating
    radix = radix_profile(engine,op,scope,arithmetic=True)
    if radix:return radix
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
    """Select declared bit widths and the bounded floating conversion path."""
    memory = engine.memory
    widths, types, immediates = [], [], []
    typed_immediate = False
    for index, ref in enumerate(op.args):
        destination = index == len(op.args) - 1
        if not destination:
            typed = typed_literal(ref) if '#' not in ref else typed_integer(ref,radix=True)
            if typed is not None:
                dtype, _ = typed
                widths.append(INT_BITS[BITWISE_FLOATS.get(dtype, dtype)])
                types.append(dtype)
                typed_immediate = True
                continue
            try:
                literal_value = literal(ref)
            except ValueError:
                pass
            else:
                if type(literal_value) is float:
                    real(literal_value)
                    widths.append(32)
                    types.append('REAL')
                else:
                    widths.append(operand(memory, ref, scope))
                    types.append(None)
                    immediates.append(literal_value)
                continue
        key, parts, dtype = (memory.check_writable if destination else memory.resolve)(ref, scope)
        integer_type = BITWISE_FLOATS.get(dtype, dtype)
        if integer_type not in INT_BITS or isinstance(memory.at(key, parts), (list, dict)):
            raise ModelError('Bitwise operands require scalar integers, REAL or LREAL')
        widths.append(INT_BITS[integer_type])
        types.append(dtype)
    dtype = types[-1]
    if dtype in BITWISE_FLOATS and any(source in UNSIGNED_BITS for source in types[:-1]):
        raise ModelError('Floating bitwise destinations require signed or floating inputs')
    if not typed_immediate and immediates:
        widths = bitwise_immediate_widths(widths, types, immediates)
    return widths[:-1], types[:-1], dtype


def execute_bitwise(engine, op, scope):
    """Combine declared integer patterns, converting floating operands numerically."""
    memory = engine.memory
    widths, source_types, dtype = bitwise_specification(engine, op, scope)
    values = []
    for ref, width, kind in zip(op.args[:-1], widths, source_types, strict=True):
        if kind in BITWISE_FLOATS:
            number = real(memory.read(ref, scope)) if kind == 'REAL' else lreal_math_source(memory, ref, scope, execute=True)
            rounded = coerce(number, BITWISE_FLOATS[kind])
            values.append(rounded & ((1 << width) - 1))
        else:
            values.append(pattern(memory, ref, scope, width, radix=True))
    value = ~values[0] if op.name == 'NOT' else {
        'AND': operator.and_, 'OR': operator.or_, 'XOR': operator.xor}[op.name](*values)
    result_type = dtype
    if dtype in BITWISE_FLOATS:
        result_type = 'LINT' if dtype == 'LREAL' or 64 in widths else 'DINT'
    memory.write(op.args[-1], bit_value(value, result_type), scope)
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
                signed_dint_radix=dict(bases=[2,8,16],bits=32,
                    interpretation='Unsuffixed full words with bit31 set are signed DINT constants; shorter words zero-fill',
                    selection='Integer-only scalar profile when a negative DINT word or typed radix selects it; existing complete tag-range and constant-fit checks',
                    scope='Ladder arithmetic and direct ordering/LIM only; default parsing, expressions, masks, BCD and call parameters remain separate',
                    native_runtime_parity=False),
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
                typed_integer_arithmetic=dict(instructions=sorted(ARITHMETIC),constant_types=['LINT','UDINT','ULINT'],radix_bases=[2,8,16],
                    constants='Decimal L/U/UL values and declared-width typed radix patterns; existing bounded DINT constants must fit the result type',
                    selection='An integer result covers every complete declared source type range; no saved value justifies narrowing or signed-to-unsigned conversion',
                    calculation='Exact integer operations; DIV truncates toward zero, MOD has the dividend sign; result overflow faults atomically',
                    scope='RLL v35 5580; typed radix selects integer-only sources/results; decimal floating priority, bitwise/MEQ and other consumers retain separate profiles; native parity remains unverified',
                    native_runtime_parity=False),
                lreal_arithmetic=dict(instructions=sorted(ARITHMETIC),types=['LREAL'],
                    operands='Scalar numeric tags, DINT radix words, bounded DINT/finite REAL and decimal/radix typed L/U/UL integer or floating L/l constants; no LREAL source is required when the destination is LREAL',
                    selection_by_destination='The scalar LREAL result selects binary64 inputs and calculation, including constant-only calls and NEG/ABS',
                    selection_by_source='An LREAL tag or floating L/l constant also selects binary64, including with REAL or integer results',
                    destination_types=sorted({*INT_BITS, 'REAL', 'LREAL'}),
                    result_conversion='Convert the finite binary64 result to the declared destination once; integer destinations round ties to even and require range',
                    constants='Bounded DINT, finite REAL, decimal/radix L/U/UL integers and finite floating L/l LREAL; radix words decode at declared width before binary64 promotion',
                    radix_sources=dict(bases=[2,8,16],types=['DINT','LINT','UDINT','ULINT'],selection='Explicit binary64 math only; default conversion helpers and other consumers remain separate',native_runtime_parity=False),
                    source_types=sorted({*INT_BITS,'REAL','LREAL'}),
                    promotion='Convert every required source to binary64 before calculation; signed/unsigned values retain their numeric sign, REAL retains its stored precision',
                    calculation='Finite host binary64; MOD uses fmod with dividend sign; zero divisors and nonfinite results fault atomically',
                    selection='Structural/lazy operands, complete unknown writes and existing alias/member/AOI references',
                    native_runtime_parity=False),
                real_arithmetic=dict(instructions=sorted(ARITHMETIC),source_types=sorted({*INT_BITS,'REAL'}),
                    destination='Scalar REAL tag; no REAL source is required; constant-only calls execute',
                    integer_destinations=sorted(INT_BITS),
                    selection_by_source='A REAL tag or floating immediate selects float32 for all signed/unsigned integer results',
                    radix_sources=dict(bases=[2,8,16],types=['DINT','LINT','UDINT','ULINT'],selection='Existing REAL calculation selectors; decode declared word before float32 conversion',native_runtime_parity=False),
                    integer_conversion='Convert the float32 result to the declared integer by nearest-even rounding with range checks',
                    constants='Bounded DINT/finite REAL and decimal/radix L/U/UL integer constants and signed DINT radix words; declared integer range checked before float32 conversion',
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
                             immediates='Unsuffixed DINT/32-bit radix patterns retain their compatibility rules; typed decimal and radix L/U/UL sources use declared widths',
                             destination='Keep destination low bits and reinterpret signed/unsigned; full writes establish unknowns without floating-point conversion',
                             wide='All eight integer tag types may mix with bounded DINT/32-bit radix or declared-width typed L/U/UL immediates', native_precision=False),
                mixed_integer_immediates=dict(instructions=sorted(BITWISE), width=32,
                    sources='Signed DINT decimal and existing 32-bit binary, octal and hexadecimal patterns with any integer tag type',
                    compatibility='Previously accepted homogeneous LINT calls retain signed DINT immediate promotion',
                    native_runtime_parity=False),
                real_bitwise=dict(instructions=sorted(BITWISE), types=['SINT','INT','DINT','REAL'],
                                  conversion='REAL sources are finite binary32, rounded to signed DINT with ties to even.',
                                  destination='Signed DINT or LINT result converted to REAL at the selected width.',
                                  native_runtime_parity=False),
                lreal_bitwise=dict(instructions=sorted(BITWISE), types=['SINT','INT','DINT','LINT','REAL','LREAL'],
                                   conversion='LREAL sources are finite binary64, rounded to signed LINT with ties to even. REAL sources retain their DINT conversion and zero extension.',
                                   destination='LREAL in the instruction selects a signed LINT bitwise result for floating destinations.',
                                   native_runtime_parity=False),
                mixed_floating_bitwise=dict(instructions=sorted(BITWISE), integer_types=list(INT_BITS),
                    inputs='REAL, LREAL and integer tags or supported immediates combine as declared-width integer bit patterns.',
                    destination='All integer types keep their low bits. Floating destinations accept signed and floating sources only.',
                    native_runtime_parity=False),
                typed_integer_bitwise=dict(instructions=sorted(BITWISE),constant_types=['LINT','UDINT','ULINT'],radix_bases=[2,8,16],
                    operands='Decimal or attached radix L/U/UL sources; integer and floating sources, and bounded DINT/32-bit radix patterns may mix',
                    conversion='Preserve each declared-width bit pattern, zero-extend before combining; NOT inverts after promotion and result keeps destination low bits',
                    range='Typed source bounds checked structurally; integer destinations may truncate or reinterpret complete bit patterns',
                    scope='RLL v35 5580 only; unsigned inputs to floating destinations, BOOL, MVM/BTD/other consumers and native status/fault/lifecycle parity remain separate',
                    native_runtime_parity=False),
                bindings='Aliases, selected elements/members and existing AOI InOut/local bindings',
                failures='Reached unknowns, invalid indices, zero divisors, excluded ranges and later faults roll back the advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Other arithmetic destination conversions/mixed signed-to-unsigned forms, larger/typed arithmetic constants, unsigned bitwise sources for floating destinations, and other wide/unsigned/LREAL remainder mixtures',
                           'Native overflow/status/fault/lifecycle/packed layout and broader controller qualification'])
