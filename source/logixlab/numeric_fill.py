"""Numeric FLL selection and conversion for the bounded v35 5580 profile."""
from .integer_math import CONTROLLERS, bit_value
from .model import ModelError, coerce, literal
from .real_math import real

INTEGERS = frozenset(('SINT', 'INT', 'DINT'))
NUMERIC = INTEGERS | {'REAL'}
MAX_ELEMENTS = 100000


def operand_type(memory, ref, scope, *, length=False):
    try:value = literal(ref)
    except ValueError:
        key, parts, dtype = memory.resolve(ref, scope)
        if isinstance(memory.at(key, parts), (list, dict)):
            raise ModelError('Numeric FLL requires scalar source and length operands')
    else:
        dtype = 'DINT' if type(value) is int else 'REAL' if type(value) is float else 'BOOL'
        if dtype == 'DINT':coerce(value, dtype)
        elif dtype == 'REAL':real(value)
    allowed = INTEGERS if length else NUMERIC
    if dtype not in allowed:
        raise ModelError('Numeric FLL ' + ('length requires SINT/INT/DINT' if length else 'source requires SINT/INT/DINT/REAL'))
    return dtype


def converted(value, source_type, destination_type):
    if source_type in INTEGERS:
        if type(value) is not int:raise ModelError('Numeric FLL source must be a known integer')
        value = coerce(value, source_type)
        if destination_type in INTEGERS:
            return bit_value(value, destination_type)
        return real(value)
    # REAL narrowing remains a representable, nearest-even software profile.
    # Native overflow bits/status for REAL-to-integer are not inferred here.
    return coerce(real(value), destination_type)


def handle(engine, op, scope, *, execute=False):
    """Handle qualified numeric destinations; leave legacy aggregate fills alone."""
    project = engine.project
    if project.version != '35' or project.processor.upper() not in CONTROLLERS:
        return False
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        _, _, dtype = memory.check_writable(op.args[1], scope)
        if dtype not in NUMERIC:return False
        memory.region(op.args[1], 0, scope)
        source_type = operand_type(memory, op.args[0], scope)
        operand_type(memory, op.args[2], scope, length=True)
    finally:
        memory.structural = previous
    if not execute:return True

    count = memory.read(op.args[2], scope)
    if type(count) is not int or not 0 <= count <= MAX_ELEMENTS:
        raise ModelError('Numeric FLL length must be an integer in 0..100000')
    # Capture the complete target window before writing. Keep the existing
    # logical array/member boundary rather than assuming a native packed layout.
    key, paths, dtype = memory.region(op.args[1], count, scope)
    memory.check_writable(op.args[1], scope)
    if count:
        value = converted(memory.read(op.args[0], scope), source_type, dtype)
        for path in paths:memory.store(key, path, value)
    return True


def description(project):
    return dict(available=project.version == '35' and project.processor.upper() in CONTROLLERS, profile='v35-5580-numeric-FLL', language='RLL', types=sorted(NUMERIC),
                integer_conversion='Preserve low destination bits when narrowing; sign-extend when widening',
                real_conversion='Finite float32; nearest-even integer results must fit the signed destination',
                operands='Scalar source; SINT/INT/DINT length; bounded DINT/finite REAL immediates',
                selection='Structural preflight; false/prescan skip live operands; true calls sample length, destination window and source before stores',
                zero_length='Validate the live destination reference without reading the source value',
                storage='Whole arrays or selected elements; row-major traversal within the logical array/member; aliases and existing AOI bindings',
                max_elements=MAX_ELEMENTS, clipping=False,
                failures='Unknown consumed values, invalid indices/lengths, REAL range errors and later faults roll back the advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Native clipping/base-tag cross-member traversal and packed layouts',
                           'REAL overflow bits/flags, wider types and broader controller/language/lifecycle qualification',
                           'Aggregate zero fills and other controller profiles retain their separate legacy contract'])
