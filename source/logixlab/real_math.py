"""Finite REAL-result ladder math for the explicit v35 5580 profile."""
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
    if dtype != 'REAL' or isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('Standalone math currently requires a scalar REAL destination')
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


def execute(memory, op, power, scope):
    if not power:
        return False
    validate(memory, op, scope)
    values = [real(memory.read(ref, scope)) for ref in op.args[:-1]]
    try:
        result = math.pow(*values) if op.name == 'XPY' else FUNCTIONS[op.name](*values)
        result = real(result)
    except (ValueError, OverflowError) as error:
        raise ModelError(op.name + ' outside the finite REAL math profile') from error
    memory.write(op.args[-1], result, scope)
    return True


def description():
    return dict(profile='v35-5580-finite-REAL-results', language='RLL',
                instructions=sorted(INSTRUCTIONS), sources=sorted(SOURCE_TYPES), destination='REAL',
                arithmetic='Sources and results rounded to float32; host math functions, no native bit-parity claim',
                square_root='Absolute value of source before square root, including CPT/ST functions',
                trig='Radians for SIN/COS/TAN inputs and inverse-trig outputs',
                failures='Unknown values, domains and nonfinite/overflow results stop and roll back the advance',
                native_math_status=False, native_fault_classification=False,
                remaining=['Integer destinations, wide/unsigned sources and LREAL',
                           'FBD forms and native precision/status/NaN/infinity behavior'])
