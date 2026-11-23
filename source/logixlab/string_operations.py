"""Bounded FIND/INSERT/DELETE on represented single-byte LEN/DATA strings."""
from .model import (ModelError, StringCapacityError, StringLengthError, StringNumericRangeError,
                    StringPositionError, ascii_bytes, ascii_literal_end, coerce, literal)
from .integer_math import CONTROLLERS, dint_radix

INSTRUCTIONS = frozenset(('FIND', 'INSERT', 'DELETE'))
INTEGERS = frozenset(('SINT', 'INT', 'DINT'))
STRING_LENGTH_FAULT = 51
_SOURCE_LENGTH_FAULT_OPS = INSTRUCTIONS | {'CONCAT', 'MID', 'LOWER', 'UPPER', 'STOD', 'STOR'}
_OUTPUT_CAPACITY_CODES = {
    'CONCAT': STRING_LENGTH_FAULT, 'MID': 52, 'DELETE': 52, 'LOWER': 52, 'UPPER': 52, 'DTOS': 52, 'RTOS': 52,
}


def fault_code(opcode, error):
    """Map diagnosed string failures to the installed v35 instruction tables."""
    if isinstance(error, StringLengthError) and opcode in _SOURCE_LENGTH_FAULT_OPS:
        return STRING_LENGTH_FAULT
    if isinstance(error, StringCapacityError):
        return _OUTPUT_CAPACITY_CODES.get(opcode)
    if isinstance(error, StringNumericRangeError) and opcode in ('STOD', 'STOR'):
        return 53
    if isinstance(error, StringPositionError) and opcode in INSTRUCTIONS | {'MID'}:
        return 56
    return None


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


def position_word(memory, ref):
    project = memory.project
    if project.version == '35' and project.processor.upper() in CONTROLLERS:
        return dint_radix(ref)
    return None


def position_literal(memory, ref):
    word = position_word(memory, ref)
    return literal(ref) if word is None else word


def integer_operand(memory, ref, scope, *, destination=False):
    if not destination:
        try:
            value = position_literal(memory, ref)
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
    word = position_word(memory, ref)
    value = memory.read(ref, scope) if word is None else word
    if type(value) is not int:
        raise ModelError('String position/quantity requires an integer value')
    return coerce(value, 'DINT')


def _reports_ladder_string_faults(engine, scope):
    routine = engine._executing_routine
    return (engine.project.version == '35' and engine.project.processor.upper() in CONTROLLERS
            and routine is not None and routine.kind == 'RLL' and scope not in engine.memory.frames
            and engine._executing_program is not None and engine._program_fault is None
            and not engine.addons.prescanning)


def compare(engine, op, scope, relation):
    memory = engine.memory
    if not _reports_ladder_string_faults(engine, scope):
        values = []
        for ref in op.args:
            text = string_literal(ref)
            values.append(memory.string(ref, scope) if text is None else text)
        return relation(*values)

    literals = tuple(string_literal(ref) for ref in op.args)
    try:
        values = memory.string_pair(op.args, literals, scope, unsigned_length=op.name != 'EQU')
    except StringLengthError:
        engine._record_instruction_minor_fault(STRING_LENGTH_FAULT)
        return op.name == 'NEQ'
    return relation(*values)


def concatenate(engine, op, scope):
    memory = engine.memory
    left, right, dest = op.args
    if not _reports_ladder_string_faults(engine, scope):
        memory.write_string(dest, memory.string(left, scope) + memory.string(right, scope), scope)
        return

    capacity = string_operand(memory, dest, scope, destination=True)
    try:
        text, truncated = memory.concatenate_strings(left, right, capacity, scope)
    except StringLengthError:
        engine._record_instruction_minor_fault(STRING_LENGTH_FAULT)
        return
    memory.write_string(dest, text, scope)
    if truncated:
        engine._record_instruction_minor_fault(STRING_LENGTH_FAULT)


def execute(memory, op, scope):
    validate(memory, op, scope)
    a = op.args
    capacity = string_operand(memory, a[0], scope)
    start = integer_value(memory, a[2], scope)
    if not 1 <= start <= capacity:
        raise StringPositionError(f'{op.name} start must be 1..source DATA capacity')
    if op.name == 'DELETE':
        quantity = integer_value(memory, a[1], scope)
        result = memory.string_without(a[0], start, quantity, scope)
        memory.write_string(a[3], result, scope)
        return
    if op.name == 'FIND':
        result = memory.string_find(a[0], a[1], start, scope)
        memory.write(a[3], result, scope)
        return
    source = memory.string(a[0], scope)
    if start > len(source) + 1:
        raise ModelError(f'{op.name} start exceeds the modeled active string boundary')
    addition = memory.string(a[1], scope)
    result = source[:start - 1] + addition + source[start - 1:]
    memory.write_string(a[3], result, scope)


def description():
    return dict(instructions=sorted(INSTRUCTIONS), languages=['RLL', 'ST'], encoding='single-byte Latin-1 storage',
                strings='STRING and explicit DINT LEN / one-dimensional SINT DATA user strings',
                positions='One-based SINT/INT/DINT tag or bounded DINT immediate; no expression operands',
                position_radix=dict(languages=['RLL', 'ST'], firmware='35', controllers=sorted(CONTROLLERS),
                    instructions=['FIND', 'INSERT', 'MID', 'DELETE'],
                    operands='Start and Quantity accept grouped unsuffixed binary, octal and hexadecimal DINT words',
                    native_runtime_parity=False),
                search='Case-sensitive; first match at/after Start, zero when absent',
                mid='Start within declared DATA; exact window within LEN; only selected DATA bytes are consumed',
                find=dict(languages=['RLL','ST'],
                    selection='Known nonempty source/search LEN; Start within source DATA capacity',
                    reads='Capture all active source DATA at/after Start and all active search DATA; earlier source and inactive bytes may remain unknown',
                    result='First one-based position in the original source, or zero when absent; valid Start beyond LEN consumes no source DATA',
                    excluded='Empty source/search, unknown consumed bytes, invalid LEN/Start and result-type overflow retain existing guards',
                    native_runtime_parity=False),
                delete=dict(languages=['RLL','ST'],
                    selection='Known LEN, Start and positive Qty; deletion window within active source and Start within DATA capacity',
                    reads='Only retained prefix/suffix bytes; removed and inactive DATA may remain unknown',
                    writes='Capture retained text before writing LEN and active result; preserve unused destination bytes',
                    native_runtime_parity=False),
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
                    oversized_length='Scheduled ladder reports Type 4 Code 51; NEQ returns true and the other five relations return false.',
                    native_runtime_parity=False),
                operand_selection=dict(language='RLL',firmware='35',controllers=sorted(CONTROLLERS),
                    instructions=['CONCAT','MID','DTOS','STOD','FIND','INSERT','DELETE','LOWER','UPPER','STOR','RTOS','EQU','NEQ','LES','LEQ','GRT','GEQ','CMP'],
                    preflight='Declared string/scalar shapes, index grammar, permissions and existing literal bounds without saved values or dynamic indices',
                    selection='False/prescan skip live operands; enabled calls retain runtime address, active-LEN/DATA, range and capacity checks',
                    writes='Complete logical string writes establish unknown LEN/active DATA while preserving unused bytes and other elements',
                    array_recovery='A cleared Type 4 Code 20 during a whole-project ladder scan skips the instruction result write',
                    capacity_diagnostics='Qualified ladder CONCAT continues with Type 4 Code 51 on invalid oversized LEN or output clipping. Other modeled capacity faults roll back the advance.',
                    position_diagnostics='Ladder FIND, INSERT, MID and DELETE report Type 4 Code 56 for documented invalid ranges and roll back the advance',
                    comparisons='Required source strings and both CMP logical operands are consumed; no value or identity folding',
                    excluded='New algorithms, empty-search/zero-delete edge behavior, broader types/encoding/controller rules and native status/fault/lifecycle parity',
                    native_runtime_parity=False),
                remaining=['Empty FIND search', 'Zero-quantity DELETE', 'INSERT beyond active text plus one',
                           'Native minor faults and math/status parity', 'FBD execution'])
