"""Lazy scalar ladder arithmetic/bitwise rules and finite REAL remainder."""
import math
import operator

from .bit_transfer import operand, unsigned
from .integer_math import CONTROLLERS, profile
from .model import ModelError
from .real_math import real

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
        wide = profile(engine, op, scope)
        if op.name in BITWISE and wide is None:
            bitwise_widths(memory, op, scope)
    finally:
        memory.structural = previous
    return True


def bitwise_widths(memory, op, scope):
    """Declared SINT/INT/DINT widths; immediates are 32-bit patterns."""
    return [operand(memory, ref, scope, destination=index == len(op.args) - 1)
            for index, ref in enumerate(op.args)]


def execute_bitwise(memory, op, scope):
    """Zero-extend source patterns, apply the operation, keep destination bits.

    Complement after promotion so widening NOT inverts the added zero bits.
    Full writes do not require a known previous destination value.
    """
    widths = bitwise_widths(memory, op, scope)
    values = [unsigned(memory, ref, scope, width)
              for ref, width in zip(op.args[:-1], widths[:-1])]
    value = ~values[0] if op.name == 'NOT' else {
        'AND': operator.and_, 'OR': operator.or_, 'XOR': operator.xor}[op.name](*values)
    bits = widths[-1]
    value &= (1 << bits) - 1
    if value >= 1 << (bits - 1):
        value -= 1 << bits
    memory.write(op.args[-1], value, scope)
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
                arithmetic='Existing integer quotient/remainder, destination coercion and homogeneous wide-integer limits retained',
                real_remainder=dict(sources=['SINT','INT','DINT','REAL'], destinations=['SINT','INT','DINT','REAL'],
                                    selection='A REAL source or floating immediate selects float32 inputs, host fmod and float32 result',
                                    conversion='Integer results round nearest, ties to even; out-of-range results roll back',
                                    zero='Zero after float32 conversion stops and rolls back; native zero-result/minor fault is not modeled',
                                    native_precision=False),
                bitwise=dict(types=['SINT','INT','DINT'], instructions=sorted(BITWISE),
                             promotion='Zero-extend declared source patterns; NOT inverts after promotion; keep destination low bits',
                             immediates='Signed DINT decimal or complete 32-bit radix patterns',
                             destination='Reinterpret selected low bits as signed destination; full writes establish unknowns',
                             wide='Existing homogeneous wide-integer profile remains separate', native_precision=False),
                bindings='Aliases, selected elements/members and existing AOI InOut/local bindings',
                failures='Reached unknowns, invalid indices, zero divisors, excluded ranges and later faults roll back the advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Complete arithmetic promotion, wide/unsigned/REAL bitwise mixtures and wide/unsigned/LREAL remainder mixtures',
                           'Native overflow/status/fault/lifecycle/packed layout and broader controller qualification'])
