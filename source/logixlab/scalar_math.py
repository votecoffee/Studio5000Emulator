"""Lazy scalar ladder arithmetic/bitwise rules and finite REAL remainder."""
import math
import operator

from .bit_transfer import operand, unsigned
from .integer_math import CONTROLLERS, WIDE_TYPES, bit_value, execute as execute_integer, profile
from .model import INT_BITS, ModelError, literal
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
        if op.name in BITWISE:
            bitwise_specification(engine, op, scope)
        else:
            profile(engine, op, scope)
    finally:
        memory.structural = previous
    return True


def bitwise_specification(engine, op, scope):
    """Integer tag widths; retain the separate legacy wide-immediate rules."""
    memory = engine.memory
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
    values = [unsigned(memory, ref, scope, width)
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
                arithmetic='Existing integer quotient/remainder, destination coercion and homogeneous wide-integer limits retained',
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
                bindings='Aliases, selected elements/members and existing AOI InOut/local bindings',
                failures='Reached unknowns, invalid indices, zero divisors, excluded ranges and later faults roll back the advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Complete arithmetic promotion, mixed-wide/typed bitwise immediates, REAL/LREAL bitwise and wide/unsigned/LREAL remainder mixtures',
                           'Native overflow/status/fault/lifecycle/packed layout and broader controller qualification'])
