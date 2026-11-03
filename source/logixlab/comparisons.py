"""Lazy numeric ladder comparisons for the bounded v35 5580 profile."""
import operator

from . import integer_math
from .bit_transfer import unsigned
from .model import INT_BITS, UNSIGNED_BITS, ModelError, literal

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
    conversion. Immediates, homogeneous and narrow forms retain their profiles.
    """
    if not available(engine.project):return integer_math.profile(engine, op, scope)
    types = []
    for ref in op.args:
        try:literal(ref)
        except ValueError:types.append(engine.memory.resolve(ref, scope)[2])
        else:return integer_math.profile(engine, op, scope)
    if not set(types) & integer_math.WIDE_TYPES or len(set(types)) == 1:
        return integer_math.profile(engine, op, scope)
    if any(dtype not in INT_BITS for dtype in types):
        raise ModelError('Mixed ordering comparisons require integer scalar tags')
    common = max(types, key=INTEGER_RANK.__getitem__)
    def bounds(dtype):
        bits = INT_BITS[dtype]
        return (0, (1 << bits) - 1) if dtype in UNSIGNED_BITS else (-(1 << (bits - 1)), (1 << (bits - 1)) - 1)
    low, high = bounds(common)
    if any(bounds(dtype)[0] < low or bounds(dtype)[1] > high for dtype in types):
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
    if op.name == 'LIM':
        low, value, high = values
        return low <= value <= high if low <= high else value >= low or value <= high
    return RELATIONS[op.name](*values)


def description(project):
    return dict(available=available(project), profile='v35-5580-lazy-numeric-comparisons',
                language='RLL', instructions=sorted(INSTRUCTIONS),
                selection='Structural preflight; false/prescan skip saved values and dynamic indices; true calls consume every operand',
                mixed_integer_ordering=dict(instructions=sorted((*RELATIONS,'LIM')), types=list(INTEGER_RANK),
                    operands='Tags only; highest-ranked operand type must cover every complete declared operand range',
                    promotion='Preserve numeric values and signs; no floating-point conversion and no invented wider common type',
                    selection='Read-only inputs; false/prescan skip live values and indices; true calls consume every source',
                    immediates='Retain the separate homogeneous representable signed-DINT wide rules and existing narrow rules',
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
