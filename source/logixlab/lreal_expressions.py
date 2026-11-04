"""Scoped finite binary64 CPT/CMP expressions for the v35 5580 model."""
import math
import operator

from .expressions import FUNCTIONS
from .integer_math import CONTROLLERS
from .model import INT_BITS, ModelError, coerce

NUMERIC = frozenset((*INT_BITS, 'REAL', 'LREAL'))
MATH = frozenset(FUNCTIONS) - {'SQRT', 'TRUNC'}
ARITHMETIC = frozenset(('+', '-', '*', '/', 'MOD', '**'))
RELATIONS = {'=': operator.eq, '<>': operator.ne, '<': operator.lt,
             '<=': operator.le, '>': operator.gt, '>=': operator.ge}
LOGICAL = frozenset(('&&', '||', '^^', 'AND', 'OR', 'XOR'))


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def immediate(value):
    if type(value) is not int:
        raise ModelError('LREAL expressions require bounded DINT immediate values')
    return coerce(value, 'DINT')


def analyze(expression, memory, scope='', destination_type=None, *, consumer='CPT'):
    declared = {ref: memory.resolve(ref, scope)[2] for ref in expression.refs}
    if destination_type != 'LREAL' and 'LREAL' not in declared.values():
        return None
    if not available(memory.project):
        raise ModelError('LREAL expressions require the v35 ControlLogix 5580 profile')
    if consumer == 'CPT' and destination_type not in NUMERIC:
        raise ModelError('LREAL CPT requires a numeric scalar destination')
    if expression.functions - MATH or expression.typed_types:
        raise ModelError('Unsupported LREAL expression function or typed literal')
    types = {}
    for ref, dtype in declared.items():
        if dtype not in NUMERIC and not (consumer == 'CMP' and dtype == 'BOOL'):
            raise ModelError('LREAL expressions require numeric scalar operands or CMP BOOL tags')
        key, parts, _ = memory.resolve(ref, scope)
        if isinstance(memory.at(key, parts), (dict, list)):
            raise ModelError('LREAL expressions require scalar operands')
        types[ref] = 'bool' if dtype == 'BOOL' else 'number'

    def infer(node):
        kind, value = node[:2]
        if kind == 'literal':
            immediate(value)
            return 'number'
        if kind == 'ref':
            return types[value]
        if kind == 'call':
            if infer(node[2]) != 'number':
                raise ModelError('LREAL math functions require numeric operands')
            return 'number'
        if kind == 'unary':
            if value in ('+', '-') and node[2][0] == 'literal':
                immediate(node[2][1] if value == '+' else -node[2][1])
                return 'number'
            operand = infer(node[2])
            if consumer == 'CMP' and value in ('!', 'NOT') and operand == 'bool':
                return 'bool'
            if value not in ('+', '-') or operand != 'number':
                raise ModelError('Numeric LREAL bitwise/unary operators remain unqualified')
            return 'number'
        if kind != 'binary':
            raise ModelError('Unsupported LREAL expression operand')
        left, right = infer(node[2]), infer(node[3])
        if consumer == 'CMP' and value in RELATIONS:
            if left != right or left == 'bool' and value not in ('=', '<>'):
                raise ModelError('LREAL CMP comparison operand types must match')
            return 'bool'
        if consumer == 'CMP' and value in LOGICAL and left == right == 'bool':
            return 'bool'
        if value not in ARITHMETIC or left != 'number' or right != 'number':
            raise ModelError('LREAL expressions require numeric arithmetic or CMP Boolean composition')
        return 'number'

    result = infer(expression.tree)
    if result != ('number' if consumer == 'CPT' else 'bool'):
        raise ModelError(consumer + ' has an invalid LREAL expression result type')
    return dict(consumer=consumer, declared=declared, types=types)


def evaluate(expression, memory, scope, profile):
    def number(value):
        return coerce(value, 'LREAL')

    def visit(node):
        kind, value = node[:2]
        if kind == 'literal':
            return number(immediate(value))
        if kind == 'ref':
            result = memory.read(value, scope)
            dtype = profile['declared'][value]
            return coerce(result, 'BOOL') if dtype == 'BOOL' else number(coerce(result, dtype))
        if kind == 'unary':
            if value in ('+', '-') and node[2][0] == 'literal':
                return number(immediate(node[2][1] if value == '+' else -node[2][1]))
            x = visit(node[2])
            if value in ('!', 'NOT'):
                return not x
            return number(x if value == '+' else -x)
        if kind == 'call':
            return number(FUNCTIONS[value](visit(node[2])))
        # Both operands are required, including Boolean operations.
        x, y = visit(node[2]), visit(node[3])
        if value in RELATIONS:
            return RELATIONS[value](x, y)
        if value in LOGICAL:
            return (x and y) if value in ('&&', 'AND') else (x or y) if value in ('||', 'OR') else x != y
        if value in ('/', 'MOD') and not y:
            raise ModelError('LREAL expression divide by zero')
        if value == '**' and abs(y) > 1024:
            raise ModelError('LREAL expression exponent outside modeled range')
        if value == '+':
            result = x + y
        elif value == '-':
            result = x - y
        elif value == '*':
            result = x * y
        elif value == '/':
            result = x / y
        elif value == 'MOD':
            result = math.fmod(x, y)
        else:
            result = x ** y
        if isinstance(result, complex):
            raise ModelError('Complex LREAL expression result')
        return number(result)

    try:
        return visit(expression.tree)
    except (ValueError, OverflowError, ZeroDivisionError) as error:
        raise ModelError('LREAL expression arithmetic domain/range failure: ' + str(error)) from error


def description(project):
    return dict(available=available(project), profile='v35-5580-lreal-expressions',
                consumers=['CPT', 'CMP'], types=sorted(NUMERIC), destination='CPT numeric scalar', destination_types=sorted(NUMERIC),
                destination_conversion='Convert once after finite binary64 evaluation; nearest-even integer results must fit; REAL rounds to finite binary32',
                selection='Any LREAL operand or CPT LREAL destination selects binary64 for every numeric node',
                constants='Signed DINT-range integer literals promoted to binary64; no floating/typed/larger literals',
                operators=sorted(ARITHMETIC), functions=sorted(MATH), exponent_limit=1024,
                arithmetic='Finite binary64 intermediates; REAL tags retain their stored float32 precision; integer tags convert to binary64',
                comparisons='Six numeric relations, BOOL tags and eager Boolean composition',
                references='Existing structural/lazy scalar, alias, member, array and AOI bindings; full unknown destination writes',
                failures='Required unknowns, bounds, nonfinite/domain/zero/late faults roll back the modeled advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Floating/typed/larger literals; FRD/TOD and numeric bitwise forms',
                           'ST/FAL/FSC/FBD/SFC consumers and other controller profiles',
                           'Native numerical, status, fault, packed-layout and lifecycle parity'])
