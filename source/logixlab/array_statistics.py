"""Bounded dimension-wise AVE/STD with logical CONTROL and REAL results."""
import math

from . import control_operations as controls
from .integer_math import CONTROLLERS
from .model import ModelError, literal
from .real_math import real

INSTRUCTIONS = frozenset(('AVE', 'STD'))


def region(memory, op, scope, count=0, *, writable=False):
    key, parts, dtype = controls.static_array(memory, op.args[0], scope, writable=writable)
    if not parts or not isinstance(parts[-1], int) or isinstance(memory.at(key, parts), list):
        raise ModelError('Statistics require a fully subscripted numeric array element')
    split = len(parts)
    while split and isinstance(parts[split - 1], int):split -= 1
    prefix, indices = parts[:split], parts[split:]
    shape = []
    value = memory.at(key, prefix)
    while isinstance(value, list):
        if not value:raise ModelError('Statistics require nonempty array dimensions')
        shape.append(len(value));value = value[0]
    if len(shape) != len(indices) or not 1 <= len(shape) <= 3:
        raise ModelError('Statistics require one to three explicit array subscripts')
    try:dimension = literal(op.args[1])
    except ValueError as error:raise ModelError('Statistics dimension must be immediate 0, 1 or 2') from error
    if type(dimension) is not int or not 0 <= dimension < len(shape):
        raise ModelError('Statistics dimension must select a declared array dimension')
    if not 0 <= count <= controls.MAX_ELEMENTS:
        raise ModelError('Statistics exceed the 4096-element software limit')
    if indices[dimension] + count > shape[dimension]:
        raise ModelError('Statistics exceed the selected dimension/member boundary')
    paths = []
    for offset in range(count):
        current = list(indices);current[dimension] += offset;paths.append(prefix + current)
    return key, paths, prefix, dtype


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('Array statistics require the v35 ControlLogix 5580 software profile')
    if op.args[4:] != ['?', '?']:
        raise ModelError('Statistics LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, op.args[3], scope)
    key, _, prefix, _ = region(memory, op, scope)
    dk, dp, dtype = memory.check_writable(op.args[2], scope)
    if dtype != 'REAL' or isinstance(memory.at(dk, dp), (list, dict)):
        raise ModelError('Statistics currently require a scalar REAL destination')
    if dk == key and dp[:len(prefix)] == prefix:
        raise ModelError('Statistics destination must not overlap the source array')


def prescan(memory, op, scope):
    obj = controls.control(memory, op.args[3], scope)
    obj.update(EN=False, DN=False)
    if op.name == 'STD':obj['ER'] = False
    elif not controls.flag(obj, 'ER'):obj.update(dict.fromkeys(controls.FLAGS, False))


def execute(memory, op, power, scope):
    validate(memory, op, scope)
    obj = controls.control(memory, op.args[3], scope)
    if not power:
        if op.name == 'STD' or controls.flag(obj, 'DN') and not controls.flag(obj, 'ER'):
            obj.update(EN=False, DN=False, ER=False, POS=0)
        return False
    if controls.flag(obj, 'ER') or controls.flag(obj, 'EN') or controls.flag(obj, 'DN'):
        return True
    length, position = controls.integer(obj, 'LEN'), controls.integer(obj, 'POS')
    if position != 0:
        raise ModelError('Statistics require POS zero for a fresh complete operation; resume is unqualified')
    if length < (2 if op.name == 'STD' else 1):
        raise ModelError('AVE requires at least one element; sample STD requires at least two')
    key, paths, _, _ = region(memory, op, scope, length)
    values = [real(memory.read(memory.address(key, path))) for path in paths]
    total = 0.0
    for value in values:total = real(total + value)
    mean = real(total / length)
    result = mean
    if op.name == 'STD':
        total = 0.0
        for value in values:
            delta = real(value - mean)
            total = real(total + real(delta * delta))
        result = real(math.sqrt(real(total / (length - 1))))
    memory.write(op.args[2], result, scope)
    obj.update(EN=True, DN=True, ER=False, POS=length)
    return True


def description():
    return dict(profile='v35-5580-complete-array-statistics', language='RLL', instructions=sorted(INSTRUCTIONS),
                source_types=sorted(controls.NUMERIC), destination='REAL', max_elements=controls.MAX_ELEMENTS,
                dimensions='Static fully subscripted one/two/three-dimensional arrays; selected dimension varies',
                calculation='Float32 inputs, accumulation and results; STD uses sample divisor N-1',
                transition='Fresh POS zero, complete operation once; held EN/DN retains result; ER inhibits',
                false_rung='STD clears EN/DN/ER/POS; AVE clears them only with DN set and ER clear',
                native_math_status=False, native_fault_classification=False,
                remaining=['Partial POS/resume and native fault side effects', 'Integer AVE destinations',
                           'Indirect/alias/AOI starting arrays', 'Native precision/layout/status parity'])
