"""Bounded 8/16/32/64-bit BCD conversions and INT/DINT byte order for v35 5580."""
from .bit_transfer import unsigned
from .integer_math import CONTROLLERS, bit_value, pattern, pattern_width, read_source
from .model import INT_BITS, ModelError

INSTRUCTIONS = frozenset(('FRD', 'TOD', 'SWPB'))
ORDERS = frozenset(('REVERSE', 'WORD', 'HIGHLOW'))
PACKED_TYPES = tuple(INT_BITS)


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
    width = pattern_width(memory, source, scope)
    if op.name == 'FRD':
        if dtype not in INT_BITS:
            raise ModelError('FRD requires an integer packed source and integer destination')
    elif dtype not in PACKED_TYPES:
        raise ModelError('TOD requires an integer source and signed/unsigned integer destination')
    return width


def preflight(memory, op, scope):
    """Check declared operands without consuming saved dynamic indices."""
    previous = memory.structural
    memory.structural = True
    try:
        return validate(memory, op, scope)
    finally:
        memory.structural = previous


def from_bcd(value, width=32):
    # Default width preserves the separate DINT FBD contract.
    value &= (1 << width) - 1
    return sum(((value >> (4 * index)) & 15) * 10 ** index for index in range(width // 4))


def to_bcd(value, dtype='DINT'):
    digits = INT_BITS[dtype] // 4
    maximum = 10 ** digits - 1
    if not 0 <= value <= maximum:
        raise ModelError(f'TOD source outside the qualified 0..{maximum} range')
    result = 0
    for index in range(digits):
        value, digit = divmod(value, 10)
        result |= digit << (4 * index)
    return bit_value(result, dtype)


def execute(memory, op, power, scope):
    if not power:
        return False
    width = validate(memory, op, scope)
    source = op.args[0]
    if op.name == 'FRD':
        # v35 explicitly defines weighted hex nibbles, including A..F.
        result = from_bcd(pattern(memory, source, scope, width), width)
    elif op.name == 'TOD':
        value = read_source(memory, source, scope)
        if type(value) is not int:
            raise ModelError('TOD source requires an integer value')
        result = to_bcd(value, scalar(memory, op.args[-1], scope))
    else:
        value = unsigned(memory, source, scope, width)
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
                bcd='RLL FRD decodes 8/16/32/64-bit patterns; TOD packs 2/4/8/16 decimal digits by destination width; shared FBD defaults remain DINT',
                rll_operands={'FRD':{'sources':list(PACKED_TYPES),'destinations':list(INT_BITS)},
                              'TOD':{'sources':list(INT_BITS),'destinations':list(PACKED_TYPES)}},
                preflight='Declared scalar types/shapes, index grammar, permissions, immediate bounds and SWPB selectors; no saved dynamic indices or tag values',
                selection='False/prescan skip live operands; true checks actual indices and required sources; full writes establish unknown results',
                frd_range='Two/four/eight/sixteen weighted nibbles including A-F; decoded value must fit the destination; range errors roll back the advance',
                tod_range='Nonnegative integer input: 0..99 (8-bit), 0..9999 (16-bit), 0..99999999 (32-bit), 0..9999999999999999 (64-bit); exact packed destination bits',
                immediates='FRD/TOD accept decimal L/U/UL integer sources alongside bounded DINT and 32-bit radix sources',
                typed_immediates='FRD decodes the declared 32/64-bit pattern; TOD packs the exact numeric value within destination capacity',
                native_runtime_parity=False,
                swpb='RLL/ST INT to INT/DINT (sign extension) or DINT to DINT tags',
                orders=sorted(ORDERS), native_math_status=False, native_fault_classification=False,
                remaining=['BCD ST expressions and remaining FBD forms',
                           'TOD saturation, math status and native fault parity'])
