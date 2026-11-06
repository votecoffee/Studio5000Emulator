"""Bounded DINT ladder sequencers with canonical table references and CONTROL."""
from . import bit_transfer, control_operations as controls
from .integer_math import CONTROLLERS, bit_value
from .model import ArrayBoundsError, ModelError

INSTRUCTIONS = frozenset(('SQI', 'SQO', 'SQL'))


def starting_array(memory, ref, scope, *, writable=False, structural=False):
    previous=memory.structural
    try:
        if structural:memory.structural=True
        controls.check_start_indices(memory,ref,scope)
        key,parts,dtype=(memory.check_writable if writable else memory.resolve)(ref,scope)
        if dtype!='DINT' or any(isinstance(part,tuple) for part in parts):
            raise ModelError('Sequencer table must be a DINT array')
        value=memory.at(key,parts)
        if not isinstance(value,list) and not any(isinstance(memory.at(key,parts[:i]),list)
                                                for i,part in enumerate(parts) if isinstance(part,int)):
            raise ModelError('Sequencer table must address an array')
        if scope in memory.frames and (not parts or not isinstance(parts[-1],int) or
                len(parts)>1 and isinstance(parts[-2],int) or isinstance(value,list)):
            raise ModelError('AOI sequencers require a selected element of a one-dimensional array')
        memory.region(ref,0,scope)
        return key,parts,dtype
    finally:memory.structural=previous


def validate(memory, op, scope):
    previous = memory.structural
    memory.structural = True
    try:_validate(memory, op, scope)
    finally:memory.structural = previous


def _validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('Sequencers require the v35 ControlLogix 5580 software profile')
    a = op.args;control_index = 2 if op.name == 'SQL' else 3
    if a[control_index + 1:] != ['?', '?']:
        raise ModelError('Sequencer LEN/POS use neutral-text ?,? and saved CONTROL values')
    controls.control(memory, a[control_index], scope)
    key, parts, _ = starting_array(memory, a[0], scope, writable=op.name == 'SQL', structural=True)
    ck, cp, _ = memory.resolve(a[control_index], scope)
    if ck == key and (parts[:len(cp)] == cp or cp[:len(parts)] == parts):
        raise ModelError('Sequencer table and CONTROL cannot overlap')
    if op.name == 'SQL':
        bit_transfer.operand(memory, a[1], scope)
    else:
        bit_transfer.operand(memory, a[1], scope)
        width=bit_transfer.operand(memory,a[2],scope,destination=op.name=='SQO')
        if op.name=='SQO' and width!=32:
            raise ModelError('SQO requires a scalar writable DINT destination')
        if op.name == 'SQO':
            dk, dp, _ = memory.resolve(a[2], scope)
            if dk == key:
                boundary=parts[:-1] if parts and isinstance(parts[-1],int) else parts
                if scope not in memory.frames or dp[:len(boundary)]==boundary or boundary[:len(dp)]==dp:
                    raise ModelError('SQO destination must not share the table array storage')


def prescan(memory, op, scope):
    if op.name != 'SQI':
        controls.control(memory, op.args[2 if op.name == 'SQL' else 3], scope)['EN'] = True


def source_value(memory,ref,scope):
    """Keep signed narrow values and complete DINT immediate patterns."""
    value=memory.read(ref,scope)
    if type(value) is not int:raise ModelError('Sequencer source must be a known integer')
    return bit_value(value,'DINT')


def execute(memory, op, power, scope):
    validate(memory, op, scope)
    obj = controls.control(memory, op.args[2 if op.name == 'SQL' else 3], scope)
    previous = obj.copy()
    try:
        return _execute(memory, op, power, scope, obj)
    except ArrayBoundsError:
        obj.update(previous)
        raise


def _execute(memory, op, power, scope, obj):
    a = op.args;n = op.name
    if not power:
        if n != 'SQI':obj['EN'] = False
        return False
    length, position = controls.integer(obj, 'LEN'), controls.integer(obj, 'POS')
    if n == 'SQI':
        obj['ER'] = False
        if length <= 0 or not 0 <= position <= length:
            obj['ER'] = True
            return False
    else:
        obj['DN'] = False
        if length <= 0 or position < 0:
            obj.update(EN=True, ER=True, DN=position == length)
            return True
        if not controls.flag(obj, 'EN'):
            obj.update(EN=True, ER=False)
            position = position + 1 if position < length else 1
            obj['POS'] = position
        obj['DN'] = position == length
        if position > length:
            obj['ER'] = True
            return True
    # LEN counts cyclic rows 1..LEN; row zero is retained for startup. The
    # bounded profile qualifies the whole configured table including row zero.
    if length + 1 > controls.MAX_ELEMENTS:
        raise ModelError('Sequencer table exceeds the 4096-element software limit')
    # Only reached data operations consume the live starting subscript. A bad
    # start faults; the existing SQI/SQO ER policy still covers a valid start
    # whose configured LEN+1 window runs beyond its array/member boundary.
    starting_array(memory,a[0],scope,writable=n=='SQL')
    try:
        key, paths, _ = memory.region(a[0], length + 1, scope)
    except ArrayBoundsError:
        raise
    except ModelError:
        if n == 'SQL':raise
        obj['ER'] = True
        return False if n == 'SQI' else True
    if n == 'SQL':
        memory.store(key, paths[position], source_value(memory,a[1],scope))
        return True
    width = bit_transfer.operand(memory, a[1], scope)
    mask = bit_transfer.unsigned(memory, a[1], scope, width)
    if not mask:return True
    source = memory.read(memory.address(key, paths[position]))
    if type(source) is not int:raise ModelError('Sequencer table row is unknown or not DINT')
    if n == 'SQI':
        value = source_value(memory,a[2],scope)
        return (source & mask) == (value & mask)
    old = 0 if mask == 0xffffffff else memory.read(a[2], scope)
    memory.write(a[2], bit_value((old & ~mask) | (source & mask), 'DINT'), scope)
    return True


def description():
    return dict(instructions=sorted(INSTRUCTIONS), language='RLL', profile='v35-5580-DINT-tables',
                rows='Startup row zero; edge advances through 1..LEN then wraps to one',
                held_true='SQO rewrites masked output; SQL reloads current row; SQI compares without advancing',
                masks='SINT/INT/DINT zero-filled patterns and 32-bit radix immediates',
                source_types=['SINT','INT','DINT'],destination_type='SQO requires DINT',
                sources='SQL/SQI scalar narrow integer tags, signed DINT literals or full 32-bit radix patterns; no FIFO REAL conversions',
                source_conversion='Preserve signed narrow numeric values in DINT; full radix patterns retain all bits; SQI retains signed-source masked comparison and masks retain declared zero-fill widths',
                source_selection='Structural types/shapes and immediate bounds; false/invalid-state paths skip live sources; SQI zero mask skips compared-source references',
                bounds='Selected array/member region including LEN+1 rows, maximum 4096 elements; live starts consumed on reached data operations, including held calls',
                starting_references='Aliases and bounded indirect starts; no CONTROL.POS-dependent subscripts; false/invalid CONTROL calls do not consume live table indices',
                selection='Structural preflight for table, mask and payload references; false/invalid-state paths skip live mask/source/destination indices',
                zero_mask='Full table window checked first; zero mask skips row values and live compared-source/output references',
                control_selection='Actual CONTROL address still required at runtime; SQO/SQL prescan sets actual EN; held true calls consume live data without advancing again',
                aoi='RLL bodies with exact one-dimensional InOut/local DINT arrays and selected element starts; disjoint instance members allowed; existing Prescan/EnableInFalse/binding rollback rules',
                array_recovery='Cleared Type 4 Code 20 skips a whole-project call and restores its original CONTROL fields',
                invalid_state='ER with data retained for modeled SQI/SQO cases; SQL window overruns stop and roll back',
                native_scan_parity=False, native_control_layout=False,
                remaining=['Wide/unsigned/floating payloads and broader table/result types', 'Broader AOI shapes/lifecycle and additional languages',
                           'Native faults/invalid-state parity and broader controller profiles'])
