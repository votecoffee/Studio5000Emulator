"""Lazy numeric ladder comparisons for the bounded v35 5580 profile."""
import operator

from . import integer_math, scalar_math
from .bit_transfer import unsigned
from .model import INT_BITS, UNSIGNED_BITS, ModelError, coerce, literal

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
            for arg in op.args:
                value = memory.read(arg, scope)
                if isinstance(value, (list, dict, bool)):
                    raise ModelError('Numeric comparison requires scalar numeric operands')
            ordering_profile(engine, op, scope)
    finally:
        memory.structural = previous
    return True


def ordering_profile(engine, op, scope):
    """Preserve every declared tag range in the highest-ranked operand type.

    Do not invent a larger type or use saved values to justify signed/unsigned
    conversion. Mixed LIM constants are bounded; homogeneous/narrow forms retain
    their existing profiles.
    """
    if not available(engine.project):return integer_math.profile(engine, op, scope)
    types, constants = [], []
    for ref in op.args:
        try:value = literal(ref)
        except ValueError:types.append(engine.memory.resolve(ref, scope)[2])
        else:constants.append(value)
    lreal=scalar_math.lreal_profile(types,constants)
    if lreal:return lreal
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
    """Read-only tag patterns; keep the legacy immediate qualification separate."""
    memory = engine.memory
    widths = []
    immediate = False
    for ref in args:
        try:
            literal(ref)
        except ValueError:
            key, parts, dtype = memory.resolve(ref, scope)
            if dtype not in INT_BITS or isinstance(memory.at(key, parts), (list, dict)):
                raise ModelError('MEQ tag operands require scalar signed/unsigned integers')
            widths.append(INT_BITS[dtype])
        else:
            immediate = True
    if immediate:
        dtype = engine.extensions.wide_mask_profile(args, scope)
        return [engine.extensions.masked(ref, scope, dtype) for ref in args]
    # Mask each declared pattern before combining: promotion is zero fill,
    # including a negative DINT alongside LINT/ULINT. No operand is written.
    return [unsigned(memory, ref, scope, width) for ref, width in zip(args, widths)]


def execute(engine, op, power, scope):
    if not power:return False
    memory = engine.memory
    if op.name == 'MEQ':
        source, mask, compare = masked_values(engine, op.args, scope)
        return (source & mask) == (compare & mask)
    values = [memory.read(arg, scope) for arg in op.args]
    if ordering_profile(engine,op,scope)=='LREAL':values=[coerce(value,'LREAL') for value in values]
    if op.name == 'LIM':
        low, value, high = values
        return low <= value <= high if low <= high else value >= low or value <= high
    return RELATIONS[op.name](*values)


def description(project):
    return dict(available=available(project), profile='v35-5580-lazy-numeric-comparisons',
                language='RLL', instructions=sorted(INSTRUCTIONS),
                selection='Structural preflight; false/prescan skip saved values and dynamic indices; true calls consume every operand',
                mixed_integer_ordering=dict(instructions=sorted((*RELATIONS,'LIM')), types=list(INTEGER_RANK),
                    operands='Tags with optional bounded constants; highest-ranked tag type must cover every complete declared tag range',
                    promotion='Preserve numeric values and signs; no floating-point conversion and no invented wider common type',
                    selection='Read-only inputs; false/prescan skip live values and indices; true calls consume every source',
                    constants='Mixed LIM accepts signed-DINT integer literals in any operand position, representable in the highest-ranked tag type; constants do not justify tag-range conversion',
                    immediates='Homogeneous and narrow immediate rules remain separate; larger/typed/REAL mixed constants are excluded',
                    native_runtime_parity=False),
                lreal_ordering=dict(instructions=sorted((*RELATIONS,'LIM')),types=['LREAL'],
                    operands='Homogeneous scalar LREAL tags only; no mixed types or immediates',
                    calculation='Exact comparisons of stored finite binary64 values; inclusive/reversed limits; no tolerance',
                    native_runtime_parity=False),
                masked_equal='All eight integer tag types may mix; zero-extend declared patterns and consume all operands even under a zero mask',
                meq_types=list(INT_BITS), meq_mixed_integer_tags=True,
                meq_immediates='Existing narrow signed DINT/32-bit radix patterns; any wide/unsigned tag retains homogeneous representable signed-DINT rules',
                limits='Inclusive; low > high accepts values at or outside the endpoints',
                operands='Existing numeric types, immediate rules and conversion boundaries; string comparisons use their separate path',
                failures='Reached unknowns, bad indices and later faults roll back the advance and existing AOI state',
                native_runtime_parity=False,
                remaining=['Complete arithmetic promotion and mixed-wide/typed immediate qualification',
                           'Native status/fault/lifecycle parity and broader controller profiles'])
