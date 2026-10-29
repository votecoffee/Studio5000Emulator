"""Exact, homogeneous wide-integer ladder operations for the v35 5580 model.

Overflow remains a modeled scan fault. Mixed-type promotion and controller math
status/minor-fault behavior are deliberately separate from this numeric profile.
"""
import operator

from .model import INT_BITS, UNSIGNED_BITS, ModelError, coerce, literal

WIDE_TYPES = frozenset(('LINT', *UNSIGNED_BITS))
CONTROLLERS = frozenset(f'1756-L8{number}E' for number in range(1, 6))
COMPARISONS = {'EQU': operator.eq, 'NEQ': operator.ne, 'LES': operator.lt,
               'LEQ': operator.le, 'GRT': operator.gt, 'GEQ': operator.ge}
INSTRUCTIONS = frozenset((*COMPARISONS, 'LIM', 'MOV', 'CLR', 'ADD', 'SUB', 'MUL',
                          'DIV', 'MOD', 'NEG', 'ABS', 'AND', 'OR', 'XOR', 'NOT'))


def description(project):
    return dict(profile='v35-5580-homogeneous-integers', language='RLL',
                arithmetic_available=project.version == '35' and project.processor.upper() in CONTROLLERS,
                types=sorted(WIDE_TYPES), controllers=sorted(CONTROLLERS),
                instructions=sorted(INSTRUCTIONS), mixed_types=False,
                immediate_type='signed DINT, representable in operand type',
                division='Exact integer quotient truncated toward zero',
                overflow='Stop and roll back modeled scan; native status/fault flags not emulated')


def quotient(a, b):
    """Truncate integer division toward zero without a floating-point round trip."""
    if not b:
        raise ModelError('Integer divide by zero')
    return abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)


def profile(engine, op, scope):
    """Return the one declared wide type, or None for the existing narrow path."""
    types = []
    immediates = []
    for argument in op.args:
        try:
            value = literal(argument)
        except ValueError:
            types.append(engine.memory.resolve(argument, scope)[2])
        else:
            types.append(None)
            immediates.append(value)
    wide = set(types) & WIDE_TYPES
    if not wide:
        return None
    if len(wide) != 1 or set(types) - {None, *wide}:
        raise ModelError('Wide integer operations require matching declared operand types')
    dtype = next(iter(wide))
    if op.name not in INSTRUCTIONS:
        raise ModelError('Unsupported wide integer instruction ' + op.name)
    # Preserve previously supported same-type storage moves on older targets.
    legacy = op.name == 'CLR' or op.name == 'MOV' and not immediates
    if not legacy and (engine.project.version != '35' or engine.project.processor.upper() not in CONTROLLERS):
        raise ModelError('Wide integer execution requires the v35 ControlLogix 5580 profile')
    for value in immediates:
        if type(value) is not int or not -(1 << 31) <= value < 1 << 31:
            raise ModelError('Wide integer immediates require a signed DINT literal')
        coerce(value, dtype)
    return dtype


def bit_value(value, dtype):
    """Interpret exactly the declared number of bits, including unsigned NOT."""
    bits = INT_BITS[dtype]
    value &= (1 << bits) - 1
    if dtype not in UNSIGNED_BITS and value >= 1 << (bits - 1):
        value -= 1 << bits
    return value


def execute(engine, op, scope, dtype):
    """Execute a validated true-rung operation; return its rung-out condition."""
    memory = engine.memory
    name = op.name
    sources = op.args if name in COMPARISONS or name == 'LIM' else op.args[:-1]
    values = [memory.read(argument, scope) for argument in sources]
    if name in COMPARISONS:
        return COMPARISONS[name](*values)
    if name == 'LIM':
        low, value, high = values
        return low <= value <= high if low <= high else value >= low or value <= high
    a = values[0] if values else 0
    if name == 'CLR':
        result = 0
    elif name == 'MOV':
        result = a
    elif name == 'NEG':
        result = -a
    elif name == 'ABS':
        result = abs(a)
    elif name == 'NOT':
        result = bit_value(~a, dtype)
    else:
        b = values[1]
        if name == 'DIV':
            result = quotient(a, b)
        elif name == 'MOD':
            result = a - quotient(a, b) * b
        elif name in ('AND', 'OR', 'XOR'):
            result = bit_value({'AND': operator.and_, 'OR': operator.or_, 'XOR': operator.xor}[name](a, b), dtype)
        else:
            result = {'ADD': operator.add, 'SUB': operator.sub, 'MUL': operator.mul}[name](a, b)
    memory.write(op.args[-1], coerce(result, dtype), scope)
    return True
