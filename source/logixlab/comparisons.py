"""Lazy numeric ladder comparisons for the bounded v35 5580 profile."""
import operator

from . import integer_math
from .model import ModelError

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
            dtype = engine.extensions.wide_mask_profile(op.args, scope)
            for arg in op.args:engine.extensions.masked(arg, scope, dtype)
        else:
            for arg in op.args:
                value = memory.read(arg, scope)
                if isinstance(value, (list, dict, bool)):
                    raise ModelError('Numeric comparison requires scalar numeric operands')
            integer_math.profile(engine, op, scope)
    finally:
        memory.structural = previous
    return True


def execute(engine, op, power, scope):
    if not power:return False
    memory = engine.memory
    if op.name == 'MEQ':
        dtype = engine.extensions.wide_mask_profile(op.args, scope)
        source, mask, compare = (engine.extensions.masked(arg, scope, dtype) for arg in op.args)
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
                masked_equal='Existing narrow zero extension and homogeneous wide-integer profiles; zero mask still consumes all operands',
                limits='Inclusive; low > high accepts values at or outside the endpoints',
                operands='Existing numeric types, immediate rules and conversion boundaries; string comparisons use their separate path',
                failures='Reached unknowns, bad indices and later faults roll back the advance and existing AOI state',
                native_runtime_parity=False,
                remaining=['Complete mixed-type promotion and immediate qualification',
                           'Native status/fault/lifecycle parity and broader controller profiles'])
