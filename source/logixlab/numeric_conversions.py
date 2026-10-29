"""DINT BCD conversions and INT/DINT byte order for the v35 5580 model."""
from .bit_transfer import operand, unsigned
from .integer_math import CONTROLLERS, bit_value
from .model import ModelError

INSTRUCTIONS = frozenset(('FRD', 'TOD', 'SWPB'))
ORDERS = frozenset(('REVERSE', 'WORD', 'HIGHLOW'))


def scalar(memory, ref, scope, *, destination=False):
    key, parts, dtype = (memory.check_writable if destination else memory.resolve)(ref, scope)
    if isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('Conversion requires one scalar element')
    return dtype


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('Conversions require the v35 ControlLogix 5580 software profile')
    source, dest = op.args[0], op.args[-1]
    dtype = scalar(memory, dest, scope, destination=True)
    if op.name == 'SWPB':
        stype = scalar(memory, source, scope)
        if stype not in ('INT', 'DINT') or dtype not in (('INT', 'DINT') if stype == 'INT' else ('DINT',)):
            raise ModelError('SWPB requires INT to INT/DINT or DINT to DINT tags')
        if op.args[1].upper() not in ORDERS:
            raise ModelError('SWPB order must be REVERSE, WORD or HIGHLOW')
        return 16 if stype == 'INT' else 32
    if dtype != 'DINT' or operand(memory, source, scope) != 32:
        raise ModelError('FRD/TOD currently require a DINT source/immediate and DINT destination')
    # operand() permits only SINT/INT/DINT or bounded DINT immediates.
    return 32


def execute(memory, op, power, scope):
    if not power:
        return False
    width = validate(memory, op, scope)
    value = unsigned(memory, op.args[0], scope, width)
    if op.name == 'FRD':
        # v35 explicitly defines weighted hex nibbles, including A..F.
        result = sum(((value >> (4 * index)) & 15) * 10 ** index for index in range(8))
    elif op.name == 'TOD':
        value = memory.read(op.args[0], scope)
        if not 0 <= value <= 99999999:
            raise ModelError('TOD source outside the qualified 0..99999999 range')
        result = 0
        for index in range(8):
            value, digit = divmod(value, 10)
            result |= digit << (4 * index)
        result = bit_value(result, 'DINT')
    else:
        order = op.args[1].upper()
        if width == 16:
            # Every order swaps a two-byte source. INT->DINT sign-extends.
            result = bit_value(((value & 255) << 8) | (value >> 8), 'INT')
        elif order == 'REVERSE':
            result = bit_value(int.from_bytes(value.to_bytes(4, 'little'), 'big'), 'DINT')
        elif order == 'WORD':
            result = bit_value((value << 16) | (value >> 16), 'DINT')
        else:
            result = bit_value(((value & 0x00ff00ff) << 8) | ((value & 0xff00ff00) >> 8), 'DINT')
    memory.write(op.args[-1], result, scope)
    return True


def description():
    return dict(profile='v35-5580-conversions', instructions=sorted(INSTRUCTIONS),
                bcd='RLL DINT source/immediate and DINT destination; eight weighted nibbles for FRD',
                tod_range='0..99999999; packed signed DINT bit pattern',
                swpb='RLL/ST INT to INT/DINT (sign extension) or DINT to DINT tags',
                orders=sorted(ORDERS), native_math_status=False, native_fault_classification=False,
                remaining=['Other BCD types and mixed conversions', 'BCD expression/FBD forms',
                           'TOD saturation, math status and native fault parity'])
