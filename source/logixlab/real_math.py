"""Finite ladder math with narrow numeric results for the v35 5580 profile."""
import math

from .integer_math import CONTROLLERS
from .model import INT_BITS, ModelError, coerce, literal


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
LREAL_SOURCE_TYPES = frozenset((*INT_BITS, 'REAL', 'LREAL'))


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
    from .numeric_storage import floating_math_profile
    profile = floating_math_profile(memory, op, scope)
    if profile:
        return profile
    key, parts, dtype = memory.check_writable(op.args[-1], scope)
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
    if profile=='LREAL':
        from .numeric_storage import lreal_math_source, write_lreal_math_result
        values=[lreal_math_source(memory,ref,scope,execute=True) for ref in op.args[:-1]]
    elif profile=='REAL':
        from .numeric_storage import real_math_source
        values=[real_math_source(memory,ref,scope,execute=True) for ref in op.args[:-1]]
    else:
        values = [real(memory.read(ref, scope)) for ref in op.args[:-1]]
    try:
        result = math.pow(*values) if op.name == 'XPY' else FUNCTIONS[op.name](*values)
        if profile != 'LREAL':
            result = real(result)
    except (ValueError, OverflowError) as error:
        raise ModelError(op.name+' outside the finite '+('LREAL' if profile=='LREAL' else 'REAL')+' math profile') from error
    if profile == 'LREAL':
        write_lreal_math_result(memory, op.args[-1], result, scope)
    else:
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
                real_destination=dict(instructions=sorted(INSTRUCTIONS),source_types=sorted({*INT_BITS,'REAL'}),
                    destination='Scalar REAL tag selects float32 sources and result, including constant-only calls',
                    constants='Bounded DINT/finite REAL and decimal L/U/UL integer constants; declared range before float32 conversion',
                    calculation='All required sources convert to finite float32 before the existing unary/power solver; result rounds to float32',
                    boundaries='LREAL inputs select the binary64 path before final REAL conversion',
                    native_runtime_parity=False),
                lreal=dict(instructions=sorted(INSTRUCTIONS),sources='Scalar numeric tags for unary forms; XPY uses its separate profile',destination='Scalar LREAL tag',
                    unary=dict(instructions=sorted(FUNCTIONS),source_types=sorted(LREAL_SOURCE_TYPES),
                        constants='Bounded DINT/finite REAL and decimal L/U/UL integer or floating L/l constants; source range/precision checked before binary64 promotion',
                        selection='A scalar LREAL destination selects finite binary64 input and result; sources retain their declared numeric values and stored REAL precision',
                        native_runtime_parity=False),
                    power=dict(instruction='XPY',source_types=sorted({*INT_BITS,'REAL','LREAL'}),
                        operands='Scalar numeric sources and bounded integer constants with a LREAL result; no LREAL source is required',
                        constants='Bounded DINT/finite REAL and decimal L/U/UL integer or floating L/l constants in either source position; declared precision before binary64 promotion',
                        promotion='Convert all required numeric tag sources to finite binary64; stored REAL precision and wide integer rounding are retained',
                        native_runtime_parity=False),
                    arithmetic='Finite host binary64 sources/results; same math functions without a REAL intermediate',
                    selection_by_source='An LREAL tag or floating L/l constant selects binary64 with any scalar numeric destination',
                    destination_types=sorted({*INT_BITS, 'REAL', 'LREAL'}),
                    result_conversion='Convert the finite binary64 result once; integer destinations round ties to even and require range',
                    selection='Structural/lazy operands, complete unknown writes and existing aliases/member/AOI references',
                    excluded='Typed radix, unsuffixed integers outside DINT and radix patterns above signed DINT, other result/consumer/controller profiles and native precision/status/fault/lifecycle parity',
                    native_runtime_parity=False),
                square_root='Absolute value of source before square root, including CPT/ST functions',
                trig='Radians for SIN/COS/TAN inputs and inverse-trig outputs',
                failures='Unknown values, domains and nonfinite/overflow results stop and roll back the advance',
                native_math_status=False, native_fault_classification=False,
                remaining=['Other wide/unsigned results and operand forms',
                           'FBD Blocks share these functions; native precision/status/NaN/infinity behavior remains unqualified'])
