"""Structural validation for existing scalar ladder arithmetic/bitwise rules."""
from .integer_math import CONTROLLERS, profile
from .model import ModelError

BITWISE = frozenset(('AND', 'OR', 'XOR', 'NOT'))
INSTRUCTIONS = BITWISE | {'ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'NEG', 'ABS'}


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def validate(engine, op, scope):
    if op.name not in INSTRUCTIONS or not available(engine.project):return False
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        for ref in op.args:
            value = memory.read(ref, scope)
            if isinstance(value, (list, dict, bool)):
                raise ModelError('Scalar math requires numeric scalar operands')
            if op.name in BITWISE and isinstance(value, float):
                raise ModelError('Bitwise operands require integers')
        memory.check_writable(op.args[-1], scope)
        profile(engine, op, scope)
    finally:
        memory.structural = previous
    return True


def description(project):
    return dict(available=available(project), profile='v35-5580-lazy-scalar-math',
                language='RLL', instructions=sorted(INSTRUCTIONS),
                validation='Declared scalar types, references, permissions and existing wide-profile rules; no saved values/live indices',
                selection='False/prescan skip operands; true instructions require all source values; full writes establish unknown destinations',
                arithmetic='Existing calculations, integer quotient/remainder, destination coercion and homogeneous wide-integer limits retained',
                bitwise='Existing integer-only value/width rules retained; complete mixed-width promotion remains unqualified',
                bindings='Aliases, selected elements/members and existing AOI InOut/local bindings',
                failures='Reached unknowns, invalid indices, zero divisors, excluded ranges and later faults roll back the advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Complete mixed-type arithmetic/bitwise promotion, REAL MOD and additional type forms',
                           'Native overflow/status/fault/lifecycle/packed layout and broader controller qualification'])
