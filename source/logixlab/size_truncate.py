"""Structural SIZE and finite REAL truncation for the v35 5580 profile."""
import math

from .integer_math import CONTROLLERS
from .model import INT_BITS, ModelError, coerce, literal
from .real_math import real

NARROW = frozenset(('SINT', 'INT', 'DINT', 'REAL'))


def scalar(memory, ref, scope, allowed, *, destination=False):
    key, parts, dtype = (memory.check_writable if destination else memory.resolve)(ref, scope)
    if dtype not in allowed or isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('SIZE/TRN requires a supported scalar ' + ('destination' if destination else 'operand'))
    return key, parts, dtype


def shape(memory, ref, scope):
    """Find the closest logical containing array, without consuming its leaves."""
    key, parts, _ = memory.resolve(ref, scope)
    if key is None or any(isinstance(part, tuple) for part in parts):
        raise ModelError('SIZE source must address an array')
    value = memory.values[key]
    array = None
    for index, part in enumerate(parts):
        # A scalar member of an array element is not itself an array operand.
        if not isinstance(part, int):array = None
        if isinstance(value, list) and (index == 0 or not isinstance(parts[index - 1], int)):
            array = value
        value = value[part]
    if isinstance(value, list) and (not parts or not isinstance(parts[-1], int)):array = value
    if array is None:raise ModelError('SIZE source must address an array')
    dimensions = []
    while isinstance(array, list):
        dimensions.append(len(array))
        array = array[0] if array else None
    return dimensions


def handle(engine, op, scope, *, execute=False):
    project = engine.project
    if project.version != '35' or project.processor.upper() not in CONTROLLERS:
        return False
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        if op.name == 'SIZE':
            dimensions = shape(memory, op.args[0], scope)
            scalar(memory, op.args[2], scope, NARROW, destination=True)
            try:dimension = literal(op.args[1])
            except ValueError:
                scalar(memory, op.args[1], scope, {'SINT', 'INT', 'DINT'})
            else:
                if type(dimension) is not int or not 0 <= dimension <= 2:
                    raise ModelError('SIZE dimension must be 0..2')
                if dimension >= len(dimensions):raise ModelError('SIZE dimension exceeds array rank')
        else:
            scalar(memory, op.args[1], scope, {*INT_BITS, 'REAL'}, destination=True)
            try:value = literal(op.args[0])
            except ValueError:scalar(memory, op.args[0], scope, {'REAL'})
            else:
                if type(value) not in (int, float):raise ModelError('Numeric TRN source required')
                if type(value) is int:coerce(value, 'DINT')
                real(value)
    finally:
        memory.structural = previous
    if not execute:return True

    if op.name == 'SIZE':
        dimensions = shape(memory, op.args[0], scope)
        dimension = memory.read(op.args[1], scope)
        if type(dimension) is not int or not 0 <= dimension <= 2:
            raise ModelError('SIZE dimension must be 0..2')
        if dimension >= len(dimensions):raise ModelError('SIZE dimension exceeds array rank')
        key, parts, dtype = scalar(memory, op.args[2], scope, NARROW, destination=True)
        result = coerce(dimensions[dimension], dtype)
    else:
        result = math.trunc(real(memory.read(op.args[0], scope)))
        key, parts, dtype = scalar(memory, op.args[1], scope, {*INT_BITS, 'REAL'}, destination=True)
        result = coerce(result, dtype)
    memory.store(key, parts, result)
    return True


def description(project):
    return dict(available=project.version == '35' and project.processor.upper() in CONTROLLERS,
                profile='v35-5580-SIZE-TRN', size_languages=['RLL', 'ST'], trn_languages=['RLL'],
                size='Whole arrays or selected elements; closest logical member array; rank 1..3; no leaf-value reads',
                size_destinations=sorted(NARROW), trn_source='Finite REAL tag or bounded DINT/finite REAL immediate',
                trn_destinations=sorted({*INT_BITS, 'REAL'}), truncation='Float32 source, truncate toward zero, representable destination',
                selection='Structural preflight; false/prescan skip live values and dynamic indices',
                dynamic_dimension='Existing SINT/INT/DINT tag extension; native SIZE documents an immediate 0..2',
                native_runtime_parity=False, native_math_status=False,
                remaining=['LREAL source/destination; native overflow, status, fault and lifecycle parity',
                           'Packed layout, cross-member traversal and broader controller qualification'])
