"""Bounded DINT ladder FBC/DDT with separate compare and result controls."""
from . import control_operations as controls
from .bit_transfer import unsigned
from .integer_math import CONTROLLERS, bit_value
from .model import ArrayBoundsError, ModelError

INSTRUCTIONS = frozenset(('FBC', 'DDT'))
MAX_BITS = 4096


def region(memory, ref, count, scope, *, writable=False, structural=False):
    if type(count) is not int or not 0 <= count <= controls.MAX_ELEMENTS:
        raise ModelError('FBC/DDT array region exceeds the 4096-element software limit')
    previous=memory.structural
    try:
        if structural:memory.structural=True
        controls.check_start_indices(memory,ref,scope)
        key,parts,dtype=(memory.check_writable if writable else memory.resolve)(ref,scope)
        if dtype!='DINT' or any(isinstance(part,tuple) for part in parts):
            raise ModelError('FBC/DDT arrays require DINT elements')
        value=memory.values[key];boundary=None
        for i,part in enumerate(parts):
            if isinstance(value,list) and (i==0 or not isinstance(parts[i-1],int)):boundary=parts[:i]
            value=value[part]
        if isinstance(value,list) and boundary is None:boundary=parts
        if boundary is None:raise ModelError('FBC/DDT operand must address an array')
        if scope in memory.frames and (not parts or not isinstance(parts[-1],int) or
                len(parts)>1 and isinstance(parts[-2],int) or isinstance(value,list)):
            raise ModelError('AOI FBC/DDT require selected elements of one-dimensional arrays')
        _,paths,_=memory.region(ref,count,scope)
        return key,paths,(key,boundary)
    finally:memory.structural=previous


def overlaps(left, right):
    return left[0]==right[0] and (left[1][:len(right[1])]==right[1] or right[1][:len(left[1])]==left[1])


def control_addresses(memory, op, scope):
    return [(key,parts) for key,parts,_ in (memory.resolve(op.args[i],scope) for i in (3,6))]


def check_roles(op, arrays, control_paths):
    if overlaps(*control_paths) or any(overlaps(control, array) for control in control_paths for array in arrays.values()):
        raise ModelError('FBC/DDT controls require distinct storage disjoint from data arrays')
    if ('result' in arrays and any(overlaps(arrays['result'],arrays[name]) for name in ('source','reference')) or
            op.name=='DDT' and overlaps(arrays['source'],arrays['reference'])):
        raise ModelError('FBC/DDT writable array roles require distinct array/member storage')


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('FBC/DDT require the v35 ControlLogix 5580 software profile')
    a = op.args
    if a[4:6] != ['?', '?'] or a[7:] != ['?', '?']:
        raise ModelError('FBC/DDT LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, a[3], scope);controls.control(memory, a[6], scope)
    arrays={name:region(memory,a[i],0,scope,writable=writable,structural=True)[2]
            for name,i,writable in (('source',0,False),('reference',1,op.name=='DDT'),('result',2,True))}
    check_roles(op,arrays,control_addresses(memory,op,scope))


def prescan(memory, op, scope):
    compare = controls.control(memory, op.args[3], scope)
    result = controls.control(memory, op.args[6], scope)
    compare.update(EN=False, FD=False)
    if controls.flag(compare, 'DN'):
        compare.update(DN=False, POS=0);result.update(DN=False, POS=0)


def execute(engine, op, power, scope):
    memory = engine.memory;validate(memory, op, scope)
    if not power:
        prescan(memory, op, scope);return False
    a = op.args;compare = controls.control(memory, a[3], scope)
    if controls.flag(compare, 'EN'):return True
    saved_controls = [(compare, compare.copy())]
    try:
        return _compare_bits(engine, op, scope, compare, saved_controls)
    except ArrayBoundsError:
        for record, previous in saved_controls:
            record.update(previous)
        raise


def _compare_bits(engine, op, scope, compare, saved_controls):
    memory, a = engine.memory, op.args
    compare['EN'] = True
    if controls.flag(compare, 'DN'):return True
    compare.update(ER=False, FD=False)
    length, position = controls.integer(compare, 'LEN'), controls.integer(compare, 'POS')
    if length <= 0 or position < 0:
        compare['ER'] = True;return True
    if length > MAX_BITS:raise ModelError('FBC/DDT exceed the 4096-bit software limit')
    words = (length + 31) // 32
    sk, sources, source_path = region(memory, a[0], words, scope)
    rk, references, reference_path = region(memory, a[1], words, scope, writable=op.name == 'DDT')
    arrays=dict(source=source_path,reference=reference_path)
    control_paths=control_addresses(memory,op,scope);check_roles(op,arrays,control_paths)
    if position >= length:
        compare.update(POS=length, DN=True);return True
    result = controls.control(memory, a[6], scope)
    saved_controls.append((result, result.copy()))
    destinations=None
    while position < length:
        engine.budget -= 1
        if engine.budget < 0:raise ModelError('FBC/DDT instruction budget exceeded')
        word, bit = divmod(position, 32)
        source = unsigned(memory, memory.address(sk, sources[word]), '', 32)
        reference = unsigned(memory, memory.address(rk, references[word]), '', 32)
        if (source ^ reference) & (1 << bit):
            compare['FD'] = True
            if controls.flag(result, 'DN'):result.update(DN=False, POS=0)
            capacity, offset = controls.integer(result, 'LEN'), controls.integer(result, 'POS')
            if capacity <= 0 or not 0 <= offset < capacity:
                raise ModelError('FBC/DDT require positive result LEN and POS within capacity; full lists require DN')
            if destinations is None:
                # Freeze the result start on the first mismatch, before DDT
                # changes reference bits or result writes can change an index.
                dk,destinations,result_path=region(memory,a[2],capacity,scope,writable=True)
                check_roles(op,dict(arrays,result=result_path),control_paths)
            if op.name == 'DDT':
                memory.store(rk, references[word], bit_value(reference ^ (1 << bit), 'DINT'))
            memory.store(dk, destinations[offset], position)
            result['POS'] = offset + 1
            if result['POS'] >= capacity:result['DN'] = True
            position += 1;compare['POS'] = position
            if controls.flag(compare, 'IN'):
                if position >= length:compare['DN'] = True
                return True
        else:
            position += 1;compare['POS'] = position
    compare['DN'] = True
    return True


def description():
    return dict(profile='v35-5580-DINT-bit-diagnostics', language='RLL', instructions=sorted(INSTRUCTIONS),
                modes='Compare.IN false: all mismatches; true: stop after one mismatch per enable edge',
                positions='Compare LEN/POS count bits; Result LEN/POS count DINT entries; LSB first',
                fbc='Record mismatching bit offsets; source and reference unchanged',
                ddt='Record offsets and update only mismatching reference bits',
                result='Append at POS; DN marks capacity, next mismatch wraps to entry zero',
                false_prescan='Clear compare EN/FD; when compare DN was set, reset both positions and done bits',
                max_bits=MAX_BITS, max_result_entries=controls.MAX_ELEMENTS,
                array_recovery='A cleared Type 4 Code 20 skips the whole-project call and restores both CONTROL records',
                invalid_state='Compare LEN<=0 or POS<0 sets ER; window/unknown/result-state failures roll back advance',
                starting_references='Aliases and bounded indirect starts; structural preflight; false/held/done/invalid compare calls skip live indices; no CONTROL.POS-dependent starts',
                sampling='Source/reference windows once per fresh comparison; result window lazily once on first mismatch, before reference/result writes',
                storage='Disjoint logical array members and distinct CONTROL records may share a base tag; writable roles cannot share an array member, even disjoint windows',
                aoi='RLL bodies with exact one-dimensional DINT InOut/local arrays and selected element starts; canonical role checks and existing lifecycle/binding rollback rules',
                native_runtime_parity=False,
                remaining=['Broader AOI shapes/lifecycle and additional languages', 'Overlapping writable roles and native address-sampling parity',
                           'Other controller profiles and complete native cursor/status/fault/partial-write parity'])
