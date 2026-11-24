"""Width-aware SINT/INT/DINT ladder MVM and BTD; no native fault flags."""
import re

from .integer_math import CONTROLLERS, dint_radix
from .model import ModelError, literal

INSTRUCTIONS = frozenset(('MVM', 'BTD'))
WIDTHS = {'SINT': 8, 'INT': 16, 'DINT': 32}


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def operand(memory, ref, scope, *, destination=False, radix=False):
    """Validate scalar shape and return width without inventing unknown data."""
    if not destination:
        if radix and dint_radix(ref) is not None:
            return 32
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


def field_literal(ref, low, high, name, *, radix=False):
    try:
        word = dint_radix(ref) if radix else None
        value = literal(ref) if word is None else word
    except ValueError as error:
        raise ModelError('BTD ' + name + ' must be an immediate integer') from error
    if type(value) is not int or not low <= value <= high:
        raise ModelError(f'BTD {name} must be {low}..{high}')
    return value


def specification(memory, op, scope):
    radix = available(memory.project)
    source_width = operand(memory, op.args[0], scope, radix=radix)
    if op.name == 'MVM':
        mask_width = operand(memory, op.args[1], scope, radix=radix)
        dest_width = operand(memory, op.args[2], scope, destination=True)
        return source_width, mask_width, dest_width
    source_bit = field_literal(op.args[1], 0, source_width - 1, 'source bit', radix=radix)
    dest_width = operand(memory, op.args[2], scope, destination=True)
    dest_bit = field_literal(op.args[3], 0, dest_width - 1, 'destination bit', radix=radix)
    length = field_literal(op.args[4], 1, 32, 'length', radix=radix)
    return source_width, source_bit, dest_width, dest_bit, length


def preflight(memory, op, scope):
    """Structurally check v35 5580 references; retain older validation paths."""
    if not available(memory.project):
        return specification(memory, op, scope)
    previous = memory.structural
    memory.structural = True
    try:
        return specification(memory, op, scope)
    finally:
        memory.structural = previous


def unsigned(memory, ref, scope, width, *, radix=False):
    word = dint_radix(ref) if radix else None
    value = memory.read(ref, scope) if word is None else word
    if type(value) is not int:
        raise ModelError('Bit-transfer operand requires an integer value')
    return value & ((1 << width) - 1)


def execute(memory, op, power, scope):
    if not power:
        return False
    spec = specification(memory, op, scope)
    radix = available(memory.project)
    if op.name == 'MVM':
        source_width, mask_width, dest_width = spec
        mask = unsigned(memory, op.args[1], scope, mask_width, radix=radix) & ((1 << dest_width) - 1)
        source_bit = dest_bit = 0
    else:
        source_width, source_bit, dest_width, dest_bit, length = spec
        mask = (((1 << length) - 1) << dest_bit) & ((1 << dest_width) - 1)
    # A zero mask is a true no-op; a full replacement needs no old destination.
    if not mask:
        return True
    # MVM zero-fills selected bits above the source width on the qualified profile.
    source_mask = mask
    if radix and op.name == 'MVM':
        source_mask &= (1 << source_width) - 1
    source = unsigned(memory, op.args[0], scope, source_width, radix=radix) if source_mask else 0
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
                dint_radix='v35 5580: unsuffixed 32-bit binary/octal/hex with grouped digits for sources, MVM masks and BTD fields',
                mixed_widths='Zero-fill; preserve destination bits outside the selected mask/field',
                preflight='v35 ControlLogix 5580 checks declared scalar types/shapes, index grammar, permissions and immediate bounds without saved dynamic indices',
                selection='False/prescan skip values/indices; enabled calls check addresses first. A zero MVM mask skips values, and v35 5580 MVM can write zero-filled bits without reading the narrower source. Full writes establish unknowns; partial writes require old bits.',
                btd_fields='Immediate source/destination bit within declared width; length 1..32',
                btd_excess='Source high bits zero-filled; destination excess discarded without array wrap',
                native_math_status=False, native_fault_classification=False)
