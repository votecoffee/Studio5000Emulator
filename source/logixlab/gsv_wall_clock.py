"""Typed v35 ladder/ST reads of the host UTC and software coordinated clocks."""
import struct

from .integer_math import CONTROLLERS
from .model import ModelError, coerce, dimensions
from .numeric_copy import static_reference

CST_CURRENT = None  # The software CST object has no CIP attribute number.
CST_OFFSET = 3
ATTRIBUTES = {'currentvalue': (6, 2), 'datetime': (7, 7), 'localdatetime': (5, 7),
              'cstoffset': (CST_OFFSET, 2)}


def matches(op):
    return bool(op.args and isinstance(op.args[0],str) and op.args[0].casefold() in ('wallclocktime', 'cst'))


def specification(engine,op):
    project=engine.project
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:
        raise ModelError('Clock GSV requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=4 or any(not isinstance(a,str) for a in op.args):
        raise ModelError('Clock GSV requires four neutral-text operands')
    if op.args[1]:raise ModelError('Clock GSV requires an empty instance operand')
    attribute=op.args[2].casefold()
    if op.args[0].casefold() == 'cst':
        if attribute != 'currentvalue':
            raise ModelError('CST GSV supports CurrentValue')
        return CST_CURRENT, 2
    if attribute not in ATTRIBUTES:raise ModelError('Unsupported WallClockTime GSV attribute '+op.args[2])
    if attribute in ('localdatetime', 'cstoffset') and not project.wall_clock.legacy_utc:
        raise ModelError(f'{op.args[2]} GSV requires the explicit source UTC local-time policy')
    return ATTRIBUTES[attribute]


def _calendar_record_paths(memory, key, parts, count):
    parent = parts[:-1]
    _, _, dtype = memory.resolve(memory.address(key, parent))
    definition = memory.project.udts.get(dtype.lower())
    if definition is None or definition.get('Class') != 'User':
        return None
    declared = definition.findall('./Members/Member')
    members = declared[:count]
    names = [member.get('Name', '') for member in members]
    declared_names = [member.get('Name', '').casefold() for member in declared]
    if (len(names) != count or names[0] != parts[-1] or not all(names)
            or any(declared_names.count(name.casefold()) != 1 for name in names)
            or any(member.get('DataType') != 'DINT' or dimensions(member.get('Dimension', '0'))
                   or member.get('Hidden', 'false').lower() != 'false' for member in members)):
        raise ModelError('WallClockTime calendar record requires seven leading visible scalar DINTs '
                         'and the first member as destination')
    return [parent + [name] for name in names]


def destination(memory,ref,scope,count,scalar_types=('LINT','DT'),*,word_types=('DINT',)):
    key,parts,dtype=memory.check_writable(ref,scope)
    value=memory.at(key,parts)
    if count==2 and dtype in scalar_types and not isinstance(value,(dict,list)):
        return key,[parts],dtype
    if dtype in word_types:
        if count == 7 and parts and isinstance(parts[-1], str) and not isinstance(value, list):
            paths = _calendar_record_paths(memory, key, parts, count)
            if paths is not None:
                return key, paths, dtype
        key,paths,dtype=memory.region(ref,count,scope)
        return key,paths,dtype
    choices=' or '.join(('a scalar '+dtype for dtype in scalar_types))+' or ' if count==2 else ''
    words=' or '.join(word_types)
    raise ModelError('GSV destination requires '+choices+str(count)+' contiguous '+words+' elements')


def _clock_destination(memory, ref, scope, number, count):
    if number in (CST_CURRENT, CST_OFFSET):
        return destination(memory, ref, scope, count, scalar_types=('TIME',), word_types=('DINT', 'TIME32'))
    return destination(memory, ref, scope, count)


def setting_source(memory, ref, scope):
    key, parts, dtype = memory.resolve(ref, scope)
    if key is None or any(isinstance(part, tuple) for part in parts):
        raise ModelError('Clock setting requires a scalar DT/LINT tag or two DINT cells')
    value = memory.at(key, parts)
    if dtype in ('DT','LINT') and not isinstance(value, (list,dict)):
        return key, [parts], dtype
    if dtype == 'DINT':
        return memory.region(ref, 2, scope)
    raise ModelError('Clock setting requires a scalar DT/LINT tag or two DINT cells')


def setting_specification(engine, op):
    number, _ = specification(engine, op)
    if op.args[0].casefold() != 'wallclocktime' or number != 6:
        raise ModelError('Clock SSV supports only WallClockTime CurrentValue')


def validate_set(engine, op, scope):
    setting_specification(engine, op);memory=engine.memory;previous=memory.structural
    memory.structural=True
    try:return setting_source(memory,op.args[3],scope)
    finally:memory.structural=previous


def execute_set(engine, op, scope):
    setting_specification(engine, op);memory=engine.memory
    key,paths,dtype=setting_source(memory,op.args[3],scope)
    values=[memory.read(memory.address(key,path),allow_time=True) for path in paths]
    value=(coerce(values[0],dtype) if len(paths)==1 else
           struct.unpack('<q',struct.pack('<ii',*(coerce(value,'DINT') for value in values)))[0])
    engine.set_wall_clock(value)


def validate(engine,op,scope):
    number,count=specification(engine,op);memory=engine.memory;previous=memory.structural
    memory.structural=True
    try:return _clock_destination(memory,op.args[3],scope,number,count)
    finally:memory.structural=previous


def execute(engine,op,scope):
    number,count=specification(engine,op);memory=engine.memory
    key,paths,dtype=_clock_destination(memory,op.args[3],scope,number,count)
    if number is CST_CURRENT:
        ticks = engine.coordinated_clock.microseconds()
        if ticks is None:
            raise ModelError('CST CurrentValue is unavailable from the software coordinated clock')
        raw = struct.pack('<q', ticks)
    else:
        clock = engine.coordinated_clock if number == CST_OFFSET else None
        raw = engine.project.wall_clock.attributes(read_time=True, coordinated_clock=clock, clock_state=engine.wall_clock_state).get(number)
    if raw is None or len(raw)!=count*4:
        if number == CST_OFFSET:
            raise ModelError('WallClockTime CSTOffset is unavailable from the software clocks')
        raise ModelError('WallClockTime GSV value is unavailable from the host UTC clock')
    if dtype in ('DT', 'TIME'):
        values = (coerce(struct.unpack('<q' if dtype == 'DT' else '<Q', raw)[0], dtype),)
    else:
        values = struct.unpack('<q' if dtype == 'LINT' else '<' + 'i' * count, raw)
        if dtype == 'TIME32':
            values = tuple(coerce(value, dtype) for value in values)
    for path,value in zip(paths,values,strict=True):memory.store(key,path,value)


def write_effects(engine,op,scope):
    """Protect complete windows, widening aliases/indices to their enclosing array."""
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        key,paths,_=validate(engine,op,scope)
        if static_reference(memory,op.args[3],scope):return [(key,path) for path in paths]
        key,parts,_=memory.check_writable(op.args[3],scope)
        boundary=next((i for i,part in enumerate(parts) if isinstance(part,int)),len(parts))
        return [(key,parts[:boundary])]
    finally:memory.structural=previous


def description():
    return dict(profile='v35-5580-WallClockTime-GSV',languages=['RLL','ST'],
                attributes=['CurrentValue','DateTime','LocalDateTime and CSTOffset (explicit UTC local policy)'],
                destinations='CurrentValue: scalar DT, scalar LINT or two DINT cells; calendars: seven DINT array cells or the first seven DINT members of a declared UDT',
                coordinated_time='CST CurrentValue and WallClockTime CSTOffset: scalar TIME, two DINT or two TIME32 cells',
                source='Host time.time_ns UTC plus committed or pending controller adjustment; independent of simulated scan time; microseconds since 1970-01-01',
                sampling='One sample per reached GSV; separate calls may differ; no scan-wide snapshot',
                selection='Structural preflight; false/prescan skip live indices and time sampling; reached full writes establish unknown cells',
                st_for_effects='Exact complete windows for direct static references; aliases/AOI/indirect references conservatively cover their enclosing array',
                local_time='Existing explicit source UTC policy only; no workstation local-zone or extended DST inference',
                failures='Unavailable clock, out-of-range DT, invalid destinations and later faults roll back the whole modeled advance',
                native_runtime_parity=False,clock_setters=True,ptp=False,
                setting='SSV CurrentValue from scalar DT/LINT or two DINT cells; transactional controller UTC adjustment, 15-second monotonic interval, maximum 2068-12-29; no host clock write',
                remaining=['Built-in DATETIMESTRUCT layout and other attributes',
                           'Other clock SSV attributes, non-UTC/DST policies, CST status and chassis synchronization',
                           'Native sampling, interruption, scheduling, layout and fault/lifecycle parity'])
