"""Bounded dimension-wise AVE/STD with logical CONTROL and typed results."""
import math

from . import control_operations as controls
from .integer_math import CONTROLLERS
from .model import ModelError, literal
from .real_math import real

INSTRUCTIONS = frozenset(('AVE', 'STD'))


def region(memory, op, scope, count=0, *, writable=False, structural=False, references=False):
    if type(count) is not int or not 0 <= count <= controls.MAX_ELEMENTS:
        raise ModelError('Statistics exceed the 4096-element software limit')
    previous=memory.structural
    try:
        if structural:memory.structural=True
        return selected_region(memory,op,scope,count,writable=writable,references=references)
    finally:memory.structural=previous


def selected_region(memory, op, scope, count, *, writable, references):
    if references:controls.check_start_indices(memory,op.args[0],scope)
    else:controls.static_array(memory,op.args[0],scope,writable=writable)
    key, parts, dtype = (memory.check_writable if writable else memory.resolve)(op.args[0],scope)
    if dtype not in controls.NUMERIC:
        raise ModelError('Statistics sources require SINT/INT/DINT/REAL arrays')
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
    if indices[dimension] + count > shape[dimension]:
        raise ModelError('Statistics exceed the selected dimension/member boundary')
    paths = []
    for offset in range(count):
        current = list(indices);current[dimension] += offset;paths.append(prefix + current)
    return key, paths, prefix, dtype


def validate(memory, op, scope):
    previous = memory.structural
    memory.structural = True
    try:_validate(memory, op, scope)
    finally:memory.structural = previous


def _validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('Array statistics require the v35 ControlLogix 5580 software profile')
    if op.args[4:] != ['?', '?']:
        raise ModelError('Statistics LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, op.args[3], scope)
    key, _, prefix, _ = region(memory, op, scope, structural=True, references=True)
    destination(memory,op,scope,key,prefix)


def destination(memory, op, scope, key, prefix):
    dk, dp, dtype = memory.check_writable(op.args[2], scope)
    allowed = controls.NUMERIC if op.name == 'AVE' else {'REAL'}
    if dtype not in allowed or isinstance(memory.at(dk, dp), (list, dict)):
        raise ModelError(op.name + ' requires a scalar ' + ('SINT/INT/DINT/REAL' if op.name == 'AVE' else 'REAL') + ' destination')
    if dk == key and dp[:len(prefix)] == prefix:
        raise ModelError('Statistics destination must not overlap the source array')
    ck, cp, _ = memory.resolve(op.args[3], scope)
    if dk == ck and dp[:len(cp)] == cp:
        raise ModelError('Statistics destination must not overlap its CONTROL record')


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
    key, paths, prefix, _ = region(memory, op, scope, length, references=True)
    destination(memory,op,scope,key,prefix)
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
                source_types=sorted(controls.NUMERIC), destination='AVE: SINT/INT/DINT/REAL; STD: REAL',
                destinations={'AVE':sorted(controls.NUMERIC),'STD':['REAL']}, max_elements=controls.MAX_ELEMENTS,
                integer_ave='Float32 mean rounded to nearest integer, ties to even; rounded range errors roll back the advance',
                result_storage='Scalar aliases/members/AOI results disjoint from the source array and its CONTROL record',
                selection='Structural source/result/control preflight; false or EN/DN/ER-inhibited calls skip live result indices and values',
                result_writes='A fresh calculation resolves the actual result before reading samples; full writes establish unknown destinations',
                array_recovery='A cleared Type 4 Code 20 during a whole-project ladder scan skips both the result write and CONTROL update',
                control_selection='Actual CONTROL addresses remain required in prescan/runtime, with existing flag and LEN/POS reads',
                dimensions='Fully subscripted one/two/three-dimensional arrays; selected dimension varies without flattening',
                starting_references='Aliases and bounded indirect indices; no CONTROL.POS-dependent starts; false or latched EN/DN/ER calls skip live source indices and values',
                aoi='RLL bodies with exact one/two/three-dimensional numeric InOut arrays or represented saved locals; disjoint sibling results and existing copied-input/Prescan/EnableInFalse/binding rollback rules',
                calculation='Float32 inputs, accumulation and results; STD uses sample divisor N-1',
                transition='Fresh POS zero, complete operation once; held EN/DN retains result; ER inhibits',
                false_rung='STD clears EN/DN/ER/POS; AVE clears them only with DN set and ER clear',
                native_math_status=False, native_fault_classification=False,
                remaining=['Partial POS/resume and native fault side effects',
                           'Broader AOI lifecycle, wider types and additional languages', 'Native precision/layout/status parity'])
