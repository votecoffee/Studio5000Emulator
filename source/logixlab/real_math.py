"""Finite ladder math with narrow numeric results for the v35 5580 profile."""
import math

from .integer_math import CONTROLLERS
from .model import ModelError, coerce, literal


def square_root(value):
    # Installed v35 SQR/SQRT specifies absolute-value handling, also in expressions.
    return math.sqrt(abs(value))


FUNCTIONS = {'SQR': square_root, 'LN': math.log, 'LOG': math.log10,
             'DEG': math.degrees, 'RAD': math.radians,
             'SIN': math.sin, 'COS': math.cos, 'TAN': math.tan,
             'ASN': math.asin, 'ACS': math.acos, 'ATN': math.atan}
INSTRUCTIONS = frozenset((*FUNCTIONS, 'XPY'))
SOURCE_TYPES = frozenset(('SINT', 'INT', 'DINT', 'REAL'))
DESTINATION_TYPES = SOURCE_TYPES


def real(value):
    if type(value) not in (int, float):
        raise ModelError('Math source must be a known numeric scalar')
    try:
        return coerce(value, 'REAL')
    except (OverflowError, ValueError) as error:
        raise ModelError('Math value exceeds finite REAL range') from error


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('Standalone math requires the v35 ControlLogix 5580 software profile')
    key, parts, dtype = memory.check_writable(op.args[-1], scope)
    if dtype=='LREAL':
        if isinstance(memory.at(key,parts),(list,dict)):
            raise ModelError('LREAL math requires a scalar LREAL destination')
        for ref in op.args[:-1]:
            try:literal(ref)
            except ValueError:
                key,parts,source_type=memory.resolve(ref,scope)
                if source_type!='LREAL' or isinstance(memory.at(key,parts),(list,dict)):
                    raise ModelError('LREAL math requires matching scalar LREAL tags; mixed types remain unqualified')
            else:raise ModelError('LREAL math requires tagged sources; immediates remain unqualified')
        return 'LREAL'
    if dtype not in DESTINATION_TYPES or isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('Standalone math requires a scalar SINT/INT/DINT/REAL destination')
    for ref in op.args[:-1]:
        try:
            value = literal(ref)
        except ValueError:
            key, parts, dtype = memory.resolve(ref, scope)
            if dtype not in SOURCE_TYPES or isinstance(memory.at(key, parts), (list, dict)):
                raise ModelError('Math source requires scalar SINT/INT/DINT/REAL')
        else:
            if type(value) is int:coerce(value, 'DINT')
            real(value)


def preflight(memory, op, scope):
    """Check declared operands without consuming saved dynamic indices."""
    previous = memory.structural
    memory.structural = True
    try:
        validate(memory, op, scope)
    finally:
        memory.structural = previous


def execute(memory, op, power, scope):
    if not power:
        return False
    profile=validate(memory,op,scope)
    convert=(lambda value:coerce(value,'LREAL')) if profile=='LREAL' else real
    values = [convert(memory.read(ref, scope)) for ref in op.args[:-1]]
    try:
        result = math.pow(*values) if op.name == 'XPY' else FUNCTIONS[op.name](*values)
        result = convert(result)
    except (ValueError, OverflowError) as error:
        raise ModelError(op.name+' outside the finite '+('LREAL' if profile=='LREAL' else 'REAL')+' math profile') from error
    memory.write(op.args[-1], result, scope)
    return True


def description():
    return dict(profile='v35-5580-finite-math-narrow-results', language='RLL',
                instructions=sorted(INSTRUCTIONS), sources=sorted(SOURCE_TYPES), destination='SINT/INT/DINT/REAL',
                destinations=sorted(DESTINATION_TYPES),
                validation='Declared scalar types, shapes, index grammar, permissions and literal bounds; no live indices or saved tag values',
                selection='False/prescan skip operands; true checks actual indices and all required source values; full writes establish unknown results',
                integer_conversion='Round the float32 result to nearest integer, ties to even; reject rounded out-of-range values with whole-advance rollback',
                arithmetic='Sources and results rounded to float32; host math functions, no native bit-parity claim',
                lreal=dict(instructions=sorted(INSTRUCTIONS),sources='Matching scalar LREAL tags',destination='Scalar LREAL tag',
                    arithmetic='Finite host binary64 sources/results; same math functions without a REAL intermediate',
                    selection='Structural/lazy operands, complete unknown writes and existing aliases/member/AOI references',
                    excluded='Mixed types, immediates, ST/CPT/CMP expressions, native precision/status/fault/lifecycle parity',
                    native_runtime_parity=False),
                square_root='Absolute value of source before square root, including CPT/ST functions',
                trig='Radians for SIN/COS/TAN inputs and inverse-trig outputs',
                failures='Unknown values, domains and nonfinite/overflow results stop and roll back the advance',
                native_math_status=False, native_fault_classification=False,
                remaining=['Wide/unsigned sources or destinations and mixed LREAL forms',
                           'FBD Blocks share these functions; native precision/status/NaN/infinity behavior remains unqualified'])
