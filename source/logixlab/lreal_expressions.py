"""Scoped binary64 and selected binary32 expressions for ladder and ST."""
import math
import operator

from .expressions import FUNCTIONS
from .integer_math import CONTROLLERS, WIDE_TYPES
from .model import INT_BITS, ModelError, coerce

NUMERIC = frozenset((*INT_BITS, 'REAL', 'LREAL'))
MATH = frozenset(FUNCTIONS) - {'SQRT', 'TRUNC'}
# Match narrow ladder math selection; SQR retains the exact integer-root path.
IMPLICIT_REAL = frozenset(FUNCTIONS) - {'ABS', 'SQR', 'TRN', 'TRUNC'}
ARITHMETIC = frozenset(('+', '-', '*', '/', 'MOD', '**'))
RELATIONS = {'=': operator.eq, '<>': operator.ne, '<': operator.lt,
             '<=': operator.le, '>': operator.gt, '>=': operator.ge}
LOGICAL = frozenset(('&&', '||', '^^', 'AND', 'OR', 'XOR'))


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def immediate(value):
    if type(value) is float:
        if not math.isfinite(value):
            raise ModelError('Floating immediate exceeds finite REAL range')
        try:return coerce(value, 'REAL')
        except (OverflowError, ValueError) as error:
            raise ModelError('Floating immediate exceeds finite REAL range') from error
    if type(value) is not int:
        raise ModelError('LREAL expressions require bounded DINT or finite REAL immediate values')
    return coerce(value, 'DINT')


def analyze(expression, memory, scope='', destination_type=None, *, consumer='CPT', precision='LREAL'):
    st = consumer in ('ST', 'CASE')
    declared = {ref: memory.resolve(ref, scope)[2] for ref in expression.refs}
    binary64 = destination_type == 'LREAL' or 'LREAL' in declared.values() or 'LREAL' in expression.literal_types
    if precision is None:
        precision = 'LREAL' if binary64 else 'REAL'
    if precision == 'REAL':
        extended = bool(expression.typed_types or expression.radix_types or destination_type in WIDE_TYPES or WIDE_TYPES.intersection(declared.values()))
        if binary64 or not extended:
            return None

        def floating_literal(node):
            return node[0] == 'literal' and type(node[1]) is float or any(floating_literal(x) for x in node[1:] if isinstance(x,tuple))
        selected = (destination_type == 'REAL' or 'REAL' in declared.values()
                    or floating_literal(expression.tree) or (not st and bool(expression.functions & IMPLICIT_REAL)))
        if not selected:
            return None
    elif precision != 'LREAL':raise ModelError('Unsupported floating expression precision')
    elif not binary64:return None
    if not available(memory.project):
        raise ModelError(precision+' expressions require the v35 ControlLogix 5580 profile')
    condition = consumer == 'CMP' or (consumer == 'ST' and destination_type in (None, 'BOOL'))
    if not condition and consumer != 'CASE' and destination_type not in NUMERIC:
        raise ModelError(f'{precision} {consumer} requires a numeric scalar destination')
    functions = frozenset(FUNCTIONS) if precision == 'REAL' else MATH
    if st:
        functions = expression.function_map.keys()
    if expression.functions - functions:
        raise ModelError('Unsupported '+precision+' expression function')
    types = {}
    for ref, dtype in declared.items():
        if consumer == 'CMP' and memory.project.string_capacity(dtype) is not None:
            memory.string(ref, scope)
            types[ref] = 'string'
            continue
        if dtype not in NUMERIC and not (condition and dtype == 'BOOL'):
            if st:
                raise ModelError(precision+' ST requires numeric scalar operands or BOOL tags in conditions')
            raise ModelError(precision+' expressions require numeric scalar operands or CMP BOOL/string tags')
        key, parts, _ = memory.resolve(ref, scope)
        if isinstance(memory.at(key, parts), (dict, list)):
            raise ModelError(precision+' expressions require scalar operands')
        types[ref] = 'bool' if dtype == 'BOOL' else 'number'

    def infer(node):
        kind, value = node[:2]
        if kind == 'literal':
            if st and type(value) is bool:
                return 'bool'
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
                raise ModelError(precision+' math functions require numeric operands')
            return 'number'
        if kind == 'unary':
            if value in ('+', '-') and node[2][0] in ('literal','typed_literal'):
                signed=node[2][1] if value == '+' else -node[2][1]
                if node[2][0]=='typed_literal':coerce(signed,node[2][2])
                else:immediate(signed)
                return 'number'
            operand = infer(node[2])
            if condition and value in ('!', 'NOT') and operand == 'bool':
                return 'bool'
            if value not in ('+', '-') or operand != 'number':
                raise ModelError('Numeric '+precision+' bitwise/unary operators remain unqualified')
            return 'number'
        if kind != 'binary':
            raise ModelError('Unsupported LREAL expression operand')
        left, right = infer(node[2]), infer(node[3])
        if condition and value in RELATIONS:
            if left != right or left == 'bool' and value not in ('=', '<>'):
                raise ModelError(f'{precision} {consumer} comparison operand types must match')
            return 'bool'
        if condition and value in LOGICAL and left == right == 'bool':
            return 'bool'
        if value not in ARITHMETIC or left != 'number' or right != 'number':
            raise ModelError(precision+' expressions require numeric arithmetic or Boolean composition')
        return 'number'

    result_type = infer(expression.tree)
    if result_type != ('bool' if condition else 'number'):
        raise ModelError(consumer+' has an invalid '+precision+' expression result type')
    result = dict(consumer=consumer, declared=declared, types=types, result_type=result_type)
    if precision == 'REAL':result['precision'] = 'REAL'
    return result


def evaluate(expression, memory, scope, profile, *, allow_nonfinite_relations=False):
    precision = profile.get('precision','LREAL')
    def number(value):
        if precision == 'REAL' and type(value) is int:
            magnitude = abs(value)
            shift = magnitude.bit_length() - 24
            if shift > 0:
                # Round exact integers before Python converts them to binary64.
                # Going through a double first can move them onto a binary32 midpoint.
                significand, remainder = divmod(magnitude, 1 << shift)
                halfway = 1 << (shift - 1)
                if remainder > halfway or (remainder == halfway and significand & 1):
                    significand += 1
                magnitude = significand << shift
                value = -magnitude if value < 0 else magnitude
        return coerce(value, precision)

    def visit(node, *, relation_operand=False):
        kind, value = node[:2]
        if kind == 'literal':
            return value if type(value) is bool else number(immediate(value))
        if kind == 'typed_literal':
            return number(coerce(value,node[2]))
        if kind == 'lreal_literal':
            return number(value)
        if kind == 'ref':
            if profile['types'][value] == 'string':return memory.string(value, scope)
            result = memory.read(value, scope)
            dtype = profile['declared'][value]
            if relation_operand and dtype in ('REAL', 'LREAL') and isinstance(result, float) and not math.isfinite(result):
                return result
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
            return number(expression.function_map[value](visit(node[2])))
        # Both operands are required, including Boolean operations.
        if value in RELATIONS:
            return RELATIONS[value](visit(node[2], relation_operand=allow_nonfinite_relations),
                                    visit(node[3], relation_operand=allow_nonfinite_relations))
        x, y = visit(node[2]), visit(node[3])
        if value in LOGICAL:
            return (x and y) if value in ('&&', 'AND') else (x or y) if value in ('||', 'OR') else x != y
        if value in ('/', 'MOD') and not y:
            raise ModelError(precision+' expression divide by zero')
        if value == '**' and abs(y) > 1024:
            raise ModelError(precision+' expression exponent outside modeled range')
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
            raise ModelError('Complex '+precision+' expression result')
        return number(result)

    try:
        return visit(expression.tree)
    except OverflowError as error:
        # FAL's existing REAL overflow handler preserves completed cells and retry POS.
        if precision == 'REAL' and profile['consumer'] not in ('ST', 'CASE'):
            raise
        raise ModelError(precision+' expression arithmetic domain/range failure: '+str(error)) from error
    except (ValueError, ZeroDivisionError) as error:
        raise ModelError(precision+' expression arithmetic domain/range failure: '+str(error)) from error


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
                comparisons='CMP/FSC: six numeric or string relations, BOOL tags and eager Boolean composition',
                cmp_exceptional_relations='Direct floating tag operands may supply NaN or infinity to CMP relations.',
                strings='Built-in STRING and declared DINT LEN/SINT DATA strings; compare active bytes lexically and case-sensitively; validate LEN and required bytes; no string arithmetic/literals',
                references='Existing structural/lazy scalar, alias, member, array and AOI bindings; full unknown destination writes',
                failures='Required unknowns, bounds, nonfinite arithmetic, domain/zero and later faults roll back the modeled advance',
                structured_text=dict(numeric_tags=sorted(NUMERIC), destination='Scalar numeric or BOOL',
                    literals='Bounded DINT, finite REAL, floating L/l and decimal or radix L/U/UL integers',
                    destination_conversion='Evaluate in binary64, then convert once to a checked numeric destination',
                    native_runtime_parity=False),
                native_runtime_parity=False, native_math_status=False,
                remaining=['Other separators/typed forms; FRD/TOD and numeric bitwise forms',
                           'FBD/SFC consumers and other controller profiles',
                           'Native numerical, status, fault, packed-layout and lifecycle parity'])


def real_description(project):
    return dict(available=available(project),profile='v35-5580-real-extended-expressions',
                consumers=['CPT','CMP','FAL','FSC'],types=sorted(NUMERIC-{'LREAL'}),
                selection='A REAL tag, unsuffixed floating literal, implicit REAL math function or CPT/FAL REAL destination; at least one wide integer source/result tag, typed integer literal or signed DINT radix word',
                implicit_real_functions=sorted(IMPLICIT_REAL),
                integer_functions='ABS/SQR/TRN/TRUNC do not select REAL by themselves; exact integer forms retain their existing qualification',
                priority='LREAL selection first; narrow REAL, exact integer, string-only and generic/index consumers retain their existing paths',
                structured_text=dict(selection='REAL tag, untyped floating literal or REAL destination with a wide integer tag or typed integer literal',
                    operators='Existing ST arithmetic/functions, Boolean conditions, checked numeric assignments and numeric CASE; pure integer roots stay exact',
                    native_runtime_parity=False),
                constants='Bounded DINT/finite REAL; declared decimal/radix L/U/UL words, signed DINT words and immediate unary range checks before float32 conversion',
                arithmetic='Finite float32 sources and every numeric intermediate; existing unary math, arithmetic and bounded power',
                operators=sorted(ARITHMETIC),functions=sorted(FUNCTIONS),exponent_limit=1024,
                comparisons='CMP/FSC numeric or string relations, BOOL tags and eager Boolean composition; numeric bitwise and FRD/TOD excluded',
                cmp_exceptional_relations='Direct REAL tag operands may supply NaN or infinity to CMP relations.',
                strings='Built-in STRING and declared DINT LEN/SINT DATA strings; compare active bytes lexically and case-sensitively; validate LEN and required bytes; no string arithmetic/literals',
                destination_types=sorted(NUMERIC-{'LREAL'}),destination_conversion='Nearest-even integer conversion with range checks; REAL results retain float32 precision',
                cpt_signed_narrowing=dict(destinations=['SINT','INT'],
                    result='A rounded DINT-range REAL result stores its low destination bits',
                    status='The stored result sets S:N and S:Z, with S:V set on narrowing',
                    native_runtime_parity=False),
                failures='Unknowns, bounds, domains, integer ranges and later failures roll back; FAL REAL calculation overflow retains the existing ER/POS/prefix/retry behavior',
                native_runtime_parity=False,native_math_status=False)
