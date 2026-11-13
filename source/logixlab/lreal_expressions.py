"""Scoped finite binary64 ladder expressions for the v35 5580 model."""
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
    if type(value) is float:
        try:return coerce(value, 'REAL')
        except (OverflowError, ValueError) as error:
            raise ModelError('Floating immediate exceeds finite REAL range') from error
    if type(value) is not int:
        raise ModelError('LREAL expressions require bounded DINT or finite REAL immediate values')
    return coerce(value, 'DINT')


def analyze(expression, memory, scope='', destination_type=None, *, consumer='CPT'):
    declared = {ref: memory.resolve(ref, scope)[2] for ref in expression.refs}
    if destination_type != 'LREAL' and 'LREAL' not in declared.values() and 'LREAL' not in expression.literal_types:
        return None
    if not available(memory.project):
        raise ModelError('LREAL expressions require the v35 ControlLogix 5580 profile')
    if consumer != 'CMP' and destination_type not in NUMERIC:
        raise ModelError(f'LREAL {consumer} requires a numeric scalar destination')
    if expression.functions - MATH:
        raise ModelError('Unsupported LREAL expression function')
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
        if kind == 'typed_literal':
            coerce(value,node[2])
            return 'number'
        if kind == 'lreal_literal':
            coerce(value,'LREAL')
            return 'number'
        if kind == 'ref':
            return types[value]
        if kind == 'call':
            if infer(node[2]) != 'number':
                raise ModelError('LREAL math functions require numeric operands')
            return 'number'
        if kind == 'unary':
            if value in ('+', '-') and node[2][0] in ('literal','typed_literal'):
                signed=node[2][1] if value == '+' else -node[2][1]
                if node[2][0]=='typed_literal':coerce(signed,node[2][2])
                else:immediate(signed)
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
    if result != ('bool' if consumer == 'CMP' else 'number'):
        raise ModelError(consumer + ' has an invalid LREAL expression result type')
    return dict(consumer=consumer, declared=declared, types=types)


def evaluate(expression, memory, scope, profile):
    def number(value):
        return coerce(value, 'LREAL')

    def visit(node):
        kind, value = node[:2]
        if kind == 'literal':
            return number(immediate(value))
        if kind == 'typed_literal':
            return number(coerce(value,node[2]))
        if kind == 'lreal_literal':
            return number(value)
        if kind == 'ref':
            result = memory.read(value, scope)
            dtype = profile['declared'][value]
            return coerce(result, 'BOOL') if dtype == 'BOOL' else number(coerce(result, dtype))
        if kind == 'unary':
            if value in ('+', '-') and node[2][0] in ('literal','typed_literal'):
                signed=node[2][1] if value == '+' else -node[2][1]
                return number(coerce(signed,node[2][2]) if node[2][0]=='typed_literal' else immediate(signed))
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
                consumers=['CPT', 'CMP', 'FAL', 'FSC'], types=sorted(NUMERIC), destination='CPT/FAL numeric scalar', destination_types=sorted(NUMERIC),
                destination_conversion='Convert once after finite binary64 evaluation; nearest-even integer results must fit; REAL rounds to finite binary32',
                selection='Any LREAL tag/literal or CPT/FAL LREAL destination selects binary64 for every numeric node',
                constants='Bounded DINT integers; decimal/radix L/U/UL constants checked at declared width then converted to binary64; unsuffixed floating literals round to finite REAL before promotion; floating L/l suffix retains finite binary64',
                typed_integer_literals=dict(types=['LINT','UDINT','ULINT'],suffixes=['L/l','U/u','UL/ul/Ul/uL'],radix_bases=[2,8,16],
                    range='Check declared integer range with its immediate unary sign before binary64 conversion',
                    selection='Requires an LREAL tag/literal or CPT/FAL LREAL destination; suffix alone retains the integer profile',
                    precision='Same binary64 conversion as integer tags; integers beyond 53 significant bits may round',
                    native_runtime_parity=False),
                radix_literals=dict(bases=[2,8,16],types=['DINT','LINT','UDINT','ULINT'],
                    interpretation='Zero-fill declared 32/64-bit words, decode signed DINT/LINT, apply immediate unary/range checks, then convert to binary64',
                    selection='Existing LREAL tag/literal or CPT/FAL LREAL destination; integer suffix alone does not select binary64',
                    precision='Same conversion as decimal integer literals/tags, including rounding beyond 53 significant bits',
                    native_runtime_parity=False),
                operators=sorted(ARITHMETIC), functions=sorted(MATH), exponent_limit=1024,
                arithmetic='Finite binary64 intermediates; REAL tags retain their stored float32 precision; integer tags convert to binary64',
                comparisons='CMP/FSC: six numeric relations, BOOL tags and eager Boolean composition',
                references='Existing structural/lazy scalar, alias, member, array and AOI bindings; full unknown destination writes',
                failures='Required unknowns, bounds, nonfinite/domain/zero/late faults roll back the modeled advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Other separators/typed forms; FRD/TOD and numeric bitwise forms',
                           'ST/FBD/SFC consumers and other controller profiles',
                           'Native numerical, status, fault, packed-layout and lifecycle parity'])
