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
    key, parts, dtype = memory.check_writable(op.args[-1], scope)
    if dtype=='LREAL':
        if isinstance(memory.at(key,parts),(list,dict)):
            raise ModelError('LREAL math requires a scalar LREAL destination')
        if op.name=='XPY':
            # scalar_math imports real(); defer its shared profile selector.
            from .scalar_math import lreal_profile
            types,constants=[],[]
            for ref in op.args[:-1]:
                try:value=literal(ref)
                except ValueError:
                    key,parts,source_type=memory.resolve(ref,scope)
                    if isinstance(memory.at(key,parts),(list,dict)):
                        raise ModelError('LREAL power requires scalar numeric sources')
                    types.append(source_type)
                else:types.append(None);constants.append(value)
            return lreal_profile([*types,'LREAL'],constants,arithmetic=True)
        for ref in op.args[:-1]:
            try:value=literal(ref)
            except ValueError:
                key,parts,source_type=memory.resolve(ref,scope)
                if source_type not in LREAL_SOURCE_TYPES or isinstance(memory.at(key,parts),(list,dict)):
                    raise ModelError('LREAL unary math requires scalar numeric source tags')
            else:
                if type(value) is not int or not -(1 << 31) <= value < 1 << 31:
                    raise ModelError('LREAL unary constants require signed DINT integer literals')
        return 'LREAL'
    if dtype=='REAL':
        from .scalar_math import real_profile
        if isinstance(memory.at(key,parts),(list,dict)):
            raise ModelError('REAL math requires a scalar REAL destination')
        types,constants=[],[]
        for ref in op.args[:-1]:
            try:value=literal(ref)
            except ValueError:
                key,parts,source_type=memory.resolve(ref,scope)
                if isinstance(memory.at(key,parts),(list,dict)):
                    raise ModelError('REAL math requires scalar numeric sources')
                types.append(source_type)
            else:types.append(None);constants.append(value)
        return real_profile([*types,'REAL'],constants)
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
                real_destination=dict(instructions=sorted(INSTRUCTIONS),source_types=sorted({*INT_BITS,'REAL'}),
                    destination='Scalar REAL tag selects float32 sources and result, including constant-only calls',
                    constants='Signed DINT integer literals and finite REAL-convertible floating literals',
                    calculation='All required sources convert to finite float32 before the existing unary/power solver; result rounds to float32',
                    excluded='LREAL source narrowing, broader integer results/expressions and native precision/status/fault/lifecycle parity',
                    native_runtime_parity=False),
                lreal=dict(instructions=sorted(INSTRUCTIONS),sources='Scalar numeric tags for unary forms; XPY uses its separate profile',destination='Scalar LREAL tag',
                    unary=dict(instructions=sorted(FUNCTIONS),source_types=sorted(LREAL_SOURCE_TYPES),
                        constants='Signed DINT integer literals promoted exactly to binary64; floating, typed and larger literals remain excluded',
                        selection='A scalar LREAL destination selects finite binary64 input and result; sources retain their declared numeric values and stored REAL precision',
                        native_runtime_parity=False),
                    power=dict(instruction='XPY',source_types=sorted({*INT_BITS,'REAL','LREAL'}),
                        operands='Scalar numeric sources and bounded integer constants with a LREAL result; no LREAL source is required',
                        constants='Signed DINT integer literals in either source position, promoted exactly to binary64',
                        promotion='Convert all required numeric tag sources to finite binary64; stored REAL precision and wide integer rounding are retained',
                        native_runtime_parity=False),
                    arithmetic='Finite host binary64 sources/results; same math functions without a REAL intermediate',
                    selection='Structural/lazy operands, complete unknown writes and existing aliases/member/AOI references',
                    excluded='Other mixed types/immediates, floating/typed/larger constants, ST/CPT/CMP expressions, native precision/status/fault/lifecycle parity',
                    native_runtime_parity=False),
                square_root='Absolute value of source before square root, including CPT/ST functions',
                trig='Radians for SIN/COS/TAN inputs and inverse-trig outputs',
                failures='Unknown values, domains and nonfinite/overflow results stop and roll back the advance',
                native_math_status=False, native_fault_classification=False,
                remaining=['Other wide/unsigned results and operand forms',
                           'FBD Blocks share these functions; native precision/status/NaN/infinity behavior remains unqualified'])
