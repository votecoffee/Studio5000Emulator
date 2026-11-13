"""Lazy numeric ladder comparisons for the bounded v35 5580 profile."""
import operator

from . import integer_math, time_values
from .bit_transfer import operand
from .model import INT_BITS, UNSIGNED_BITS, ModelError, coerce, literal
from .real_math import real
from .numeric_storage import lreal_math_source, real_math_source, typed_literal

RELATIONS = {'EQU': operator.eq, 'NEQ': operator.ne, 'LES': operator.lt,
             'LEQ': operator.le, 'GRT': operator.gt, 'GEQ': operator.ge}
INSTRUCTIONS = frozenset((*RELATIONS, 'LIM', 'MEQ'))
INTEGER_RANK = {dtype: rank for rank, dtype in enumerate(('SINT','USINT','INT','UINT','DINT','UDINT','LINT','ULINT'))}


def available(project):
    return project.version == '35' and project.processor.upper() in integer_math.CONTROLLERS


def validate(engine, op, scope):
    """Validate types and references without requiring saved comparison values."""
    if op.name not in INSTRUCTIONS or not available(engine.project):return False
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        if op.name == 'MEQ':
            masked_values(engine, op.args, scope)
        else:
            if (time_specification(memory, op, scope) or lreal_specification(memory,op.args,scope)
                    or real_specification(memory,op.args,scope)):return True
            if integer_math.typed_profile(engine,op,scope):return True
            for arg in op.args:
                value = memory.read(arg, scope)
                if isinstance(value, (list, dict, bool)):
                    raise ModelError('Numeric comparison requires scalar numeric operands')
            ordering_profile(engine, op, scope)
    finally:
        memory.structural = previous
    return True


def time_specification(memory, op, scope):
    if op.name not in RELATIONS:
        return None
    left, right = (time_values.operand_type(memory, ref, scope) for ref in op.args)
    if left is not None or right is not None:
        if not time_values.same_family(left, right):
            raise ModelError('Time/date comparisons require operands from one time family')
        return left, right
    return None


def lreal_specification(memory, args, scope):
    """Select by a declared LREAL tag or floating L/l literal, never saved values."""
    selected=False
    for ref in args:
        typed=typed_literal(ref) if '#' not in ref else None
        if typed is not None:
            selected=selected or typed[0]=='LREAL'
            continue
        try:literal(ref)
        except ValueError:selected=selected or memory.resolve(ref,scope)[2]=='LREAL'
    if not selected:return None
    for ref in args:lreal_math_source(memory,ref,scope)
    return 'LREAL'


def real_specification(memory, args, scope):
    """Select by an actual REAL tag after the separate LREAL priority check."""
    selected=False
    for ref in args:
        if '#' not in ref and typed_literal(ref) is not None:continue
        try:literal(ref)
        except ValueError:selected=selected or memory.resolve(ref,scope)[2]=='REAL'
    if not selected:return None
    for ref in args:real_math_source(memory,ref,scope)
    return 'REAL'


def ordering_profile(engine, op, scope):
    """Preserve integer ranges, or promote a tagged LREAL comparison to binary64.

    Integer-only forms do not invent a larger type or use saved values to justify signed/unsigned
    conversion. Mixed LIM constants are bounded; homogeneous/narrow forms retain
    their existing profiles.
    """
    if not available(engine.project):return integer_math.profile(engine, op, scope)
    if lreal_specification(engine.memory,op.args,scope):return 'LREAL'
    if real_specification(engine.memory,op.args,scope):return 'REAL'
    typed=integer_math.typed_profile(engine,op,scope)
    if typed:return typed
    types, constants = [], []
    for ref in op.args:
        try:value = literal(ref)
        except ValueError:types.append(engine.memory.resolve(ref, scope)[2])
        else:constants.append(value)
    if not set(types) & integer_math.WIDE_TYPES or len(set(types)) == 1:
        return integer_math.profile(engine, op, scope)
    common = ordering_type(types)
    low, high = integer_bounds(common)
    for value in constants:
        if type(value) is not int or not -(1 << 31) <= value < 1 << 31:
            raise ModelError('Mixed ordering constants require signed DINT literals')
        if not low <= value <= high:
            raise ModelError('Mixed ordering constant must fit the highest-ranked tag type')
    return common


def integer_bounds(dtype):
    bits = INT_BITS[dtype]
    return (0, (1 << bits) - 1) if dtype in UNSIGNED_BITS else (-(1 << (bits - 1)), (1 << (bits - 1)) - 1)


def ordering_type(types):
    """Choose an actual tag type that preserves every complete source range."""
    if any(dtype not in INT_BITS for dtype in types):
        raise ModelError('Mixed ordering comparisons require integer scalar tags')
    common = max(types, key=INTEGER_RANK.__getitem__)
    low, high = integer_bounds(common)
    if any(integer_bounds(dtype)[0] < low or integer_bounds(dtype)[1] > high for dtype in types):
        raise ModelError('Highest-ranked comparison type must cover every operand type range')
    return common


def masked_values(engine, args, scope):
    """Read-only integer patterns, including bounded immediates in any position."""
    memory = engine.memory
    if any(integer_math.typed_integer(ref,radix=True) is not None for ref in args):
        widths=[integer_math.pattern_width(memory,ref,scope,radix=True) for ref in args]
        return [integer_math.pattern(memory,ref,scope,width,radix=True) for ref,width in zip(args,widths)]
    widths, types, immediates = [], [], []
    for ref in args:
        try:
            value = literal(ref)
        except ValueError:
            key, parts, dtype = memory.resolve(ref, scope)
            if dtype not in INT_BITS or isinstance(memory.at(key, parts), (list, dict)):
                raise ModelError('MEQ tag operands require scalar signed/unsigned integers')
            widths.append(INT_BITS[dtype])
            types.append(dtype)
        else:
            widths.append(operand(memory, ref, scope))
            types.append(None)
            immediates.append(value)
    if immediates:
        widths = integer_math.bitwise_immediate_widths(widths, types, immediates)
    return [integer_math.pattern(memory, ref, scope, width) for ref, width in zip(args, widths, strict=True)]


def execute(engine, op, power, scope):
    if not power:return False
    memory = engine.memory
    if op.name == 'MEQ':
        source, mask, compare = masked_values(engine, op.args, scope)
        return (source & mask) == (compare & mask)
    temporal = time_specification(memory, op, scope)
    if temporal:
        ticks = [time_values.read_operand(memory, ref, scope) * time_values.ns_per_tick(dtype)
                 for ref, dtype in zip(op.args, temporal)]
        return RELATIONS[op.name](*ticks)
    profile=ordering_profile(engine,op,scope)
    if profile=='LREAL':values=[lreal_math_source(memory,arg,scope,execute=True) for arg in op.args]
    elif profile=='REAL':values=[real_math_source(memory,arg,scope,execute=True) for arg in op.args]
    else:values = [integer_math.read_source(memory,arg,scope) for arg in op.args]
    if op.name == 'LIM':
        low, value, high = values
        return low <= value <= high if low <= high else value >= low or value <= high
    return RELATIONS[op.name](*values)


def description(project):
    return dict(available=available(project), profile='v35-5580-lazy-numeric-comparisons',
                language='RLL', instructions=sorted(INSTRUCTIONS),
                selection='Structural preflight; false/prescan skip saved values and dynamic indices; true calls consume every operand',
                time_date=dict(types=sorted(time_values.TYPES), instructions=sorted(RELATIONS),
                    operands='Same-family scalar tags or typed literals; exact ordering at nanosecond precision',
                    native_runtime_parity=False),
                mixed_integer_ordering=dict(instructions=sorted((*RELATIONS,'LIM')), types=list(INTEGER_RANK),
                    operands='Tags with optional bounded constants; highest-ranked tag type must cover every complete declared tag range',
                    promotion='Preserve numeric values and signs; no floating-point conversion and no invented wider common type',
                    selection='Read-only inputs; false/prescan skip live values and indices; true calls consume every source',
                    constants='Mixed LIM accepts signed-DINT integer literals in any operand position, representable in the highest-ranked tag type; constants do not justify tag-range conversion',
                    immediates='Homogeneous and narrow immediate rules remain separate; larger/typed/REAL mixed constants are excluded',
                    native_runtime_parity=False),
                typed_integer_ordering=dict(instructions=sorted((*RELATIONS,'LIM')),constant_types=['LINT','UDINT','ULINT'],
                    selection='Highest-ranked actual integer tag or typed constant must cover every complete source type range; no invented larger common type',
                    constants='Decimal L/U/UL ranges checked before exact comparison; existing bounded DINT constants must fit the selected type',
                    calculation='Exact integers without floating conversion; inclusive and reversed LIM use the same exact values',
                    scope='RLL v35 5580; REAL/LREAL priority unchanged, MEQ/bitwise/other consumers and native parity remain separate',
                    native_runtime_parity=False),
                lreal_ordering=dict(instructions=sorted((*RELATIONS,'LIM')),types=['LREAL'],
                    operands='Scalar numeric tags and constants; at least one LREAL tag or floating L/l literal selects binary64, including constant-only calls',
                    source_types=sorted({*INT_BITS,'REAL','LREAL'}),
                    constants='Bounded DINT/finite REAL and decimal L/U/UL integer or floating L/l constants; declared range/precision before binary64 promotion',
                    selection_by_literal='A floating L/l constant can select LREAL without an LREAL tag; typed integer-only forms retain their existing profile',
                    calculation='Finite host binary64, exact comparisons without tolerance; stored REAL precision retained and large integers may round',
                    limits='Inclusive normal limits; reversed limits accept values at or outside their endpoints after promotion',
                    excluded='Typed radix and radix patterns above signed DINT, unsuffixed integers outside DINT, other consumer/controller profiles and native parity',
                    native_runtime_parity=False),
                real_ordering=dict(instructions=sorted((*RELATIONS,'LIM')),source_types=sorted({*INT_BITS,'REAL'}),
                    operands='Scalar numeric tags with at least one REAL input and no LREAL input',
                    constants='Bounded DINT/finite REAL and decimal L/U/UL integer constants checked at their declared range before float32 conversion; an actual REAL tag is required',
                    calculation='Convert every required source to finite float32 before comparison; inclusive/reversed limits use converted bounds; large integers and literals may round',
                    precedence='LREAL tags or floating L/l literals retain the separate binary64 profile; integer-only comparisons retain their existing exact rules',
                    native_runtime_parity=False),
                typed_integer_masked_equal=dict(instruction='MEQ',constant_types=['LINT','UDINT','ULINT'],radix_bases=[2,8,16],
                    operands='Decimal or attached radix L/U/UL source, mask or compare; scalar integer tags and existing DINT/32-bit radix patterns may mix',
                    calculation='Zero-extend each declared pattern, then compare source AND mask with compare AND mask; no numeric signed comparison or floating conversion',
                    selection='Read-only operands; structural/lazy preflight and all required known values even for a zero mask',
                    scope='RLL v35 5580; other types/consumers and native status/fault/lifecycle parity remain separate',
                    native_runtime_parity=False),
                masked_equal='All eight integer tag types may mix; zero-extend declared patterns and consume all operands even under a zero mask',
                meq_types=list(INT_BITS), meq_mixed_integer_tags=True,
                meq_immediates='Signed DINT and 32-bit radix patterns in any position with all eight integer types; previously accepted homogeneous LINT calls keep signed DINT promotion',
                limits='Inclusive; low > high accepts values at or outside the endpoints',
                operands='Existing numeric types, immediate rules and conversion boundaries; string comparisons use their separate path',
                array_recovery='A whole-project ladder handler that clears Type 4 Code 20 skips the comparison and retains incoming rung power',
                failures='Reached unknowns, unrecovered array faults and later errors roll back the advance and existing AOI state',
                native_runtime_parity=False,
                remaining=['Complete arithmetic promotion and typed radix immediate qualification',
                           'Native status/fault/lifecycle parity and broader controller profiles'])
