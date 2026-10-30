"""Bounded ASCII case conversion and decimal/REAL conversion in RLL/ST."""
from decimal import Decimal
import re

from .integer_math import CONTROLLERS
from .model import ModelError, coerce
from .string_operations import string_operand

INSTRUCTIONS = frozenset(('LOWER', 'UPPER', 'STOR', 'RTOS'))
DECIMAL = re.compile(r'-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)')
LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
UPPER = str.maketrans('abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')


def real_operand(memory, ref, scope, *, destination=False):
    key, parts, dtype = (memory.check_writable if destination else memory.resolve)(ref, scope)
    if dtype != 'REAL' or isinstance(memory.at(key, parts), (dict, list, bool)):
        raise ModelError('String/REAL conversion requires a scalar REAL tag')


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('String conversions require the v35 ControlLogix 5580 software profile')
    source, dest = op.args
    if op.name == 'RTOS':real_operand(memory, source, scope)
    else:string_operand(memory, source, scope)
    if op.name == 'STOR':real_operand(memory, dest, scope, destination=True)
    else:string_operand(memory, dest, scope, destination=True)


def parse_real(text):
    match = DECIMAL.search(text)
    if match is None:raise ModelError('STOR requires a decimal number in the source string')
    if re.match(r'[eE][+-]?[0-9]', text[match.end():]):
        raise ModelError('STOR scientific-notation input remains unqualified')
    if text[match.end():].startswith('.') or match.start() and text[match.start()-1] in '-.':
        raise ModelError('STOR malformed decimal/sign sequence is outside the modeled profile')
    return coerce(float(match[0]), 'REAL')


def format_real(value):
    if type(value) not in (int, float):raise ModelError('RTOS requires a known finite REAL value')
    # Nine significant digits round-trip binary32. Fixed notation avoids inventing
    # a native exponent spelling; exact native text formatting remains unverified.
    return format(Decimal(format(coerce(value, 'REAL'), '.9g')), 'f')


def execute(memory, op, scope):
    validate(memory, op, scope)
    source, dest = op.args
    if op.name == 'RTOS':memory.write_string(dest, format_real(memory.read(source, scope)), scope)
    else:
        text = memory.string(source, scope)
        if op.name == 'STOR':memory.write(dest, parse_real(text), scope)
        else:memory.write_string(dest, text.translate(LOWER if op.name == 'LOWER' else UPPER), scope)


def description():
    return dict(profile='v35-5580-string-conversions', instructions=sorted(INSTRUCTIONS), languages=['RLL','ST'],
                strings='STRING and explicit DINT LEN / SINT DATA user strings; unused destination bytes preserved',
                case='ASCII A-Z/a-z only; other single-byte characters and embedded NUL preserved',
                stor='First signed decimal run; prefix/delimiters skipped, float32 result; no-digit/malformed/exponent input blocked',
                rtos='Software fixed notation, nine significant digits, finite binary32 round-trip including signed zero',
                operands='Scalar tags, including aliases, array elements and UDT members; no immediate/expression operands',
                prescan='No initialization; false rung/skipped ST branch retains destinations',
                native_formatting_parity=False, native_math_status=False, native_fault_classification=False,
                remaining=['Native RTOS precision/trailing-zero/exponent formatting', 'STOR exponent/no-digit/malformed input parity',
                           'Wider numeric types and ST expression operands', 'Native status/fault/partial-write behavior', 'FBD execution'])
