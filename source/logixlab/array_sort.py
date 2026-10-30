"""Bounded dimension-wise SRT for ladder and three-operand ST calls."""
import math

from . import array_statistics as geometry, control_operations as controls
from .integer_math import CONTROLLERS
from .model import ModelError, coerce

INSTRUCTIONS = frozenset(('SRT',))


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('SRT requires the v35 ControlLogix 5580 software profile')
    if op.args[3:] != ['?', '?']:
        raise ModelError('SRT LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, op.args[2], scope)
    geometry.region(memory, op, scope, writable=True)


def write_effects(memory, op, scope):
    """Conservative whole-array effect, plus the two written CONTROL fields."""
    validate(memory, op, scope)
    key, _, prefix, _ = geometry.region(memory, op, scope, writable=True)
    ck, cp, _ = memory.resolve(op.args[2], scope)
    return [(key, prefix), (ck, cp + ['EN']), (ck, cp + ['DN'])]


def execute(memory, op, power, scope):
    validate(memory, op, scope)
    obj = controls.control(memory, op.args[2], scope)
    if not power:
        obj.update(EN=False, DN=False)
        return False
    if controls.flag(obj, 'ER') or controls.flag(obj, 'EN'):
        return True
    length, position = controls.integer(obj, 'LEN'), controls.integer(obj, 'POS')
    if position != 0 or length < 1:
        raise ModelError('SRT qualified whole-region profile requires POS zero and positive LEN')
    key, paths, _, dtype = geometry.region(memory, op, scope, length, writable=True)
    values = [memory.read(memory.address(key, path)) for path in paths]
    if any(type(value) not in (int, float) or dtype != 'REAL' and type(value) is not int
           or not math.isfinite(value) for value in values):
        raise ModelError('SRT requires known finite values of the declared numeric type')
    values = sorted(coerce(value, dtype) for value in values)
    for path, value in zip(paths, values):memory.store(key, path, value)
    # The qualified whole-region profile retains POS=0; native internal sort
    # cursor/partial-position behavior is deliberately not inferred.
    obj.update(EN=True, DN=True)
    return True


def execute_st(memory, op, scope):
    execute(memory, op, False, scope)
    return execute(memory, op, True, scope)


def description():
    return dict(profile='v35-5580-whole-region-sort', instructions=['SRT'], languages=['RLL','ST'],
                types=sorted(controls.NUMERIC), order='Ascending, integer values retain exact declared precision',
                ladder='Rising EN; held true retains array; false clears EN/DN and retains ER/POS',
                structured_text='Three operands; each executed call performs false then true',
                position='Qualified POS zero retained; positive LEN, at most 4096 values in selected dimension/member',
                prescan='No state initialization', native_math_status=False, native_fault_classification=False,
                remaining=['Native internal POS cursor and partial-state behavior', 'Native faults/side effects',
                           'Indirect/alias/AOI starting arrays and additional types'])
