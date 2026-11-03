"""Lazy numeric ladder comparisons for the bounded v35 5580 profile."""
import operator

from . import integer_math
from .bit_transfer import unsigned
from .model import INT_BITS, ModelError, literal

RELATIONS = {'EQU': operator.eq, 'NEQ': operator.ne, 'LES': operator.lt,
             'LEQ': operator.le, 'GRT': operator.gt, 'GEQ': operator.ge}
INSTRUCTIONS = frozenset((*RELATIONS, 'LIM', 'MEQ'))


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
            integer_math.profile(engine, op, scope)
    finally:
        memory.structural = previous
    return True


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
                masked_equal='All eight integer tag types may mix; zero-extend declared patterns and consume all operands even under a zero mask',
                meq_types=list(INT_BITS), meq_mixed_integer_tags=True,
                meq_immediates='Existing narrow signed DINT/32-bit radix patterns; any wide/unsigned tag retains homogeneous representable signed-DINT rules',
                limits='Inclusive; low > high accepts values at or outside the endpoints',
                operands='Existing numeric types, immediate rules and conversion boundaries; string comparisons use their separate path',
                failures='Reached unknowns, bad indices and later faults roll back the advance and existing AOI state',
                native_runtime_parity=False,
                remaining=['Complete arithmetic promotion and mixed-wide/typed immediate qualification',
                           'Native status/fault/lifecycle parity and broader controller profiles'])
