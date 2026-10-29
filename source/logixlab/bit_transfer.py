"""Width-aware SINT/INT/DINT ladder MVM and BTD; no native fault flags."""
import re

from .model import ModelError, literal

INSTRUCTIONS = frozenset(('MVM', 'BTD'))
WIDTHS = {'SINT': 8, 'INT': 16, 'DINT': 32}


def operand(memory, ref, scope, *, destination=False):
    """Validate scalar shape and return width without inventing unknown data."""
    if not destination:
        try:
            value = literal(ref)
        except ValueError:
            pass
        else:
            radix = re.fullmatch(r'(?:2|8|16)#[0-9A-Fa-f_]+', ref.strip())
            if type(value) is not int or not (0 <= value <= 0xffffffff if radix else -(1 << 31) <= value < 1 << 31):
                raise ModelError('Bit-transfer immediate requires a signed DINT or 32-bit radix pattern')
            return 32
    key, parts, dtype = (memory.check_writable if destination else memory.resolve)(ref, scope)
    if dtype not in WIDTHS:
        raise ModelError('Bit-transfer operand requires SINT, INT or DINT')
    if isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('Bit-transfer operand requires one scalar element')
    return WIDTHS[dtype]


def field_literal(ref, low, high, name):
    try:
        value = literal(ref)
    except ValueError as error:
        raise ModelError('BTD ' + name + ' must be an immediate integer') from error
    if type(value) is not int or not low <= value <= high:
        raise ModelError(f'BTD {name} must be {low}..{high}')
    return value


def specification(memory, op, scope):
    source_width = operand(memory, op.args[0], scope)
    if op.name == 'MVM':
        mask_width = operand(memory, op.args[1], scope)
        dest_width = operand(memory, op.args[2], scope, destination=True)
        return source_width, mask_width, dest_width
    source_bit = field_literal(op.args[1], 0, source_width - 1, 'source bit')
    dest_width = operand(memory, op.args[2], scope, destination=True)
    dest_bit = field_literal(op.args[3], 0, dest_width - 1, 'destination bit')
    length = field_literal(op.args[4], 1, 32, 'length')
    return source_width, source_bit, dest_width, dest_bit, length


def unsigned(memory, ref, scope, width):
    value = memory.read(ref, scope)
    if type(value) is not int:
        raise ModelError('Bit-transfer operand requires an integer value')
    return value & ((1 << width) - 1)


def execute(memory, op, power, scope):
    if not power:
        return False
    spec = specification(memory, op, scope)
    if op.name == 'MVM':
        source_width, mask_width, dest_width = spec
        mask = unsigned(memory, op.args[1], scope, mask_width) & ((1 << dest_width) - 1)
        source_bit = dest_bit = 0
    else:
        source_width, source_bit, dest_width, dest_bit, length = spec
        mask = (((1 << length) - 1) << dest_bit) & ((1 << dest_width) - 1)
    # A zero mask is a true no-op; a full replacement needs no old destination.
    if not mask:
        return True
    source = unsigned(memory, op.args[0], scope, source_width)
    bits = (source >> source_bit) << dest_bit
    full = (1 << dest_width) - 1
    dest = 0 if mask == full else unsigned(memory, op.args[2], scope, dest_width)
    result = ((dest & ~mask) | (bits & mask)) & full
    if result >= 1 << (dest_width - 1):
        result -= 1 << dest_width
    memory.write(op.args[2], result, scope)
    return True


def description():
    return dict(language='RLL', instructions=sorted(INSTRUCTIONS), types=list(WIDTHS),
                mixed_widths='Zero-fill; preserve destination bits outside the selected mask/field',
                btd_fields='Immediate source/destination bit within declared width; length 1..32',
                btd_excess='Source high bits zero-filled; destination excess discarded without array wrap',
                native_math_status=False, native_fault_classification=False)
