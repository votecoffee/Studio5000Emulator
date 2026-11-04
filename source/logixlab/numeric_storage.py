"""Scalar MOV/CLR and explicit numeric conversions for the v35 5580 model."""
from .integer_math import CONTROLLERS, bit_value
from .model import INT_BITS, ModelError, coerce, literal
from .real_math import real

INSTRUCTIONS = frozenset(('MOV', 'CLR'))
TYPES = frozenset((*INT_BITS, 'REAL', 'LREAL'))


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def destination(memory, ref, scope):
    key, parts, dtype = memory.check_writable(ref, scope)
    if dtype not in TYPES or isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('MOV/CLR destination requires one numeric scalar element')
    return key, parts, dtype


def source_type(memory, ref, scope):
    try:value = literal(ref)
    except ValueError:
        key, parts, dtype = memory.resolve(ref, scope)
        if dtype not in TYPES or isinstance(memory.at(key, parts), (list, dict)):
            raise ModelError('MOV source requires one numeric scalar element')
        return dtype
    if type(value) is int:
        coerce(value, 'DINT');return 'DINT'
    if type(value) is float:
        real(value);return 'REAL'
    raise ModelError('MOV immediate requires bounded DINT or finite REAL')


def specification(memory, op, scope):
    previous = memory.structural
    memory.structural = True
    try:
        destination(memory, op.args[-1], scope)
        return source_type(memory, op.args[0], scope) if op.name == 'MOV' else None
    finally:
        memory.structural = previous


def validate(engine, op, scope):
    if op.name not in INSTRUCTIONS or not available(engine.project):return False
    specification(engine.memory, op, scope)
    return True


def convert(value, source, dest):
    if source in INT_BITS:
        if type(value) is not int:raise ModelError('MOV requires a known integer source')
        value = coerce(value, source)
        return bit_value(value, dest) if dest in INT_BITS else coerce(value, dest)
    # Keep REAL overflow results/status outside this representable profile.
    return coerce(coerce(value, source), dest)


def execute(engine, op, power, scope):
    if not power:return False
    memory = engine.memory
    source = specification(memory, op, scope)
    key, parts, dtype = destination(memory, op.args[-1], scope)
    value = convert(memory.read(op.args[0], scope), source, dtype) if op.name == 'MOV' else coerce(0, dtype)
    memory.store(key, parts, value)
    return True


def description(project):
    return dict(available=available(project), profile='v35-5580-numeric-storage', language='RLL',
                instructions=sorted(INSTRUCTIONS), types=sorted(TYPES),
                operands='One numeric scalar element; bounded DINT/finite REAL MOV immediates; aliases and existing AOI bindings',
                integers='Preserve low destination bits; sign-extend signed sources and zero-extend unsigned sources when widening',
                real='Finite REAL binary32 and LREAL binary64; source precision retained before destination conversion; nearest-even integer results must fit',
                lreal='Declared LREAL tags only; binary64 storage/MOV/CLR and atomic tag access; no new LREAL literals, arithmetic, ST expressions or aggregate wire layouts',
                selection='Structural preflight; false/prescan skip values and live indices; true full writes establish unknown destinations',
                clearing='CLR writes typed zero without reading the old scalar value',
                failures='Reached unknown source, invalid indices, excluded REAL ranges and later faults roll back the advance',
                native_math_status=False, native_runtime_parity=False,
                remaining=['LREAL arithmetic/expressions/AOI parameter qualification; time/date, string and aggregate forms; broader literals/controllers',
                           'REAL overflow result bits, native status/fault/lifecycle/packed layout parity'])
