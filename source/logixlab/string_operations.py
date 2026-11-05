"""Bounded FIND/INSERT/DELETE on represented single-byte LEN/DATA strings."""
from .model import ModelError, ascii_bytes, ascii_literal_end, coerce, literal
from .integer_math import CONTROLLERS

INSTRUCTIONS = frozenset(('FIND', 'INSERT', 'DELETE'))
INTEGERS = frozenset(('SINT', 'INT', 'DINT'))


def string_operand(memory, ref, scope, *, destination=False):
    key, parts, dtype = (memory.check_writable if destination else memory.resolve)(ref, scope)
    capacity = memory.project.string_capacity(dtype)
    if capacity is None:
        raise ModelError('String operation requires a scalar LEN/DATA string tag')
    obj = memory.at(key, parts)
    if not isinstance(obj, dict) or set(obj) != {'LEN', 'DATA'}:
        raise ModelError('String operation requires a scalar LEN/DATA string tag')
    if not isinstance(obj['DATA'], list) or len(obj['DATA']) != capacity:
        raise ModelError('String DATA shape differs from its declared capacity')
    return capacity


def string_literal(ref):
    if not ref.startswith("'"):
        return None
    if ascii_literal_end(ref, 0) != len(ref):
        raise ModelError('Expected one single-quoted string literal')
    return bytes(value & 255 for value in ascii_bytes(ref)).decode('latin-1')


def integer_operand(memory, ref, scope, *, destination=False):
    if not destination:
        try:
            value = literal(ref)
        except ValueError:
            pass
        else:
            if type(value) is not int:
                raise ModelError('String position/quantity requires an integer operand')
            coerce(value, 'DINT')
            return
    key, parts, dtype = (memory.check_writable if destination else memory.resolve)(ref, scope)
    if dtype not in INTEGERS:
        raise ModelError('String position/quantity/result requires scalar SINT, INT or DINT')
    if isinstance(memory.at(key, parts), (dict, list)):
        raise ModelError('String position/quantity/result requires scalar SINT, INT or DINT')


def validate(memory, op, scope):
    """Check types and writable shapes without reading placeholder ST values."""
    a = op.args
    string_operand(memory, a[0], scope)
    if op.name in ('FIND', 'INSERT'):
        string_operand(memory, a[1], scope)
        integer_operand(memory, a[2], scope)
    else:
        integer_operand(memory, a[1], scope)
        integer_operand(memory, a[2], scope)
    if op.name == 'FIND':
        integer_operand(memory, a[3], scope, destination=True)
    else:
        string_operand(memory, a[3], scope, destination=True)


def integer_value(memory, ref, scope):
    value = memory.read(ref, scope)
    if type(value) is not int:
        raise ModelError('String position/quantity requires an integer value')
    return coerce(value, 'DINT')


def execute(memory, op, scope):
    validate(memory, op, scope)
    a = op.args
    source = memory.string(a[0], scope)
    capacity = string_operand(memory, a[0], scope)
    start = integer_value(memory, a[2], scope)
    if not 1 <= start <= capacity:
        raise ModelError(f'{op.name} start must be 1..source DATA capacity')
    if op.name == 'FIND':
        search = memory.string(a[1], scope)
        if not source or not search:
            raise ModelError('FIND requires nonempty source and search strings in this model')
        result = source.find(search, start - 1) + 1
        memory.write(a[3], result, scope)
        return
    if start > len(source) + 1:
        raise ModelError(f'{op.name} start exceeds the modeled active string boundary')
    if op.name == 'INSERT':
        addition = memory.string(a[1], scope)
        result = source[:start - 1] + addition + source[start - 1:]
    else:
        quantity = integer_value(memory, a[1], scope)
        if quantity < 1 or start - 1 + quantity > len(source):
            raise ModelError('DELETE requires positive quantity within the active source string')
        result = source[:start - 1] + source[start - 1 + quantity:]
    memory.write_string(a[3], result, scope)


def description():
    return dict(instructions=sorted(INSTRUCTIONS), languages=['RLL', 'ST'], encoding='single-byte Latin-1 storage',
                strings='STRING and explicit DINT LEN / one-dimensional SINT DATA user strings',
                positions='One-based SINT/INT/DINT tag or bounded DINT immediate; no expression operands',
                search='Case-sensitive; first match at/after Start, zero when absent',
                mov=dict(language='RLL', firmware='35', controllers=sorted(CONTROLLERS),
                    sources='Scalar STRING or user string tag, or one single-quoted byte literal',
                    selection='Validate shape and literal syntax structurally; false/prescan skip live indices, LEN and DATA',
                    result='Copy the active prefix up to destination capacity, update LEN, retain unused DATA',
                    native_math_status=False, native_runtime_parity=False),
                comparison_literals=dict(language='RLL', firmware='35', controllers=sorted(CONTROLLERS),
                    instructions=['EQU','NEQ','LES','LEQ','GRT','GEQ'],
                    operands='Either side may be a scalar STRING/user-string tag or single-quoted byte literal',
                    comparison='Case-sensitive unsigned byte ordering; shorter equal prefixes sort first',
                    selection='Validate literal syntax and string tag shape structurally; read active bytes only on a true rung',
                    native_runtime_parity=False),
                operand_selection=dict(language='RLL',firmware='35',controllers=sorted(CONTROLLERS),
                    instructions=['CONCAT','MID','DTOS','STOD','FIND','INSERT','DELETE','LOWER','UPPER','STOR','RTOS','EQU','NEQ','LES','LEQ','GRT','GEQ','CMP'],
                    preflight='Declared string/scalar shapes, index grammar, permissions and existing literal bounds without saved values or dynamic indices',
                    selection='False/prescan skip live operands; enabled calls retain runtime address, active-LEN/DATA, range and capacity checks',
                    writes='Complete logical string writes establish unknown LEN/active DATA while preserving unused bytes and other elements',
                    comparisons='Required source strings and both CMP logical operands are consumed; no value or identity folding',
                    excluded='New algorithms, empty-search/zero-delete edge behavior, broader types/encoding/controller rules and native status/fault/lifecycle parity',
                    native_runtime_parity=False),
                remaining=['Empty FIND search', 'Zero-quantity DELETE', 'INSERT beyond active text plus one',
                           'Native minor faults and math/status parity', 'FBD execution'])
