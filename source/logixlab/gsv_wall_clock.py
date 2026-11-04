"""Typed v35 ladder/ST reads of the existing host UTC WallClockTime model."""
import struct

from .integer_math import CONTROLLERS
from .model import ModelError
from .numeric_copy import static_reference

ATTRIBUTES = {'currentvalue': (6, 2), 'datetime': (7, 7), 'localdatetime': (5, 7)}


def matches(op):
    return bool(op.args and isinstance(op.args[0],str) and op.args[0].casefold()=='wallclocktime')


def specification(engine,op):
    project=engine.project
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:
        raise ModelError('WallClockTime GSV requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=4 or any(not isinstance(a,str) for a in op.args):
        raise ModelError('WallClockTime GSV requires four neutral-text operands')
    if op.args[1]:raise ModelError('WallClockTime GSV requires an empty instance operand')
    attribute=op.args[2].casefold()
    if attribute not in ATTRIBUTES:raise ModelError('Unsupported WallClockTime GSV attribute '+op.args[2])
    if attribute=='localdatetime' and not project.wall_clock.legacy_utc:
        raise ModelError('LocalDateTime GSV requires the explicit source UTC local-time policy')
    return ATTRIBUTES[attribute]


def destination(memory,ref,scope,count):
    key,parts,dtype=memory.check_writable(ref,scope)
    value=memory.at(key,parts)
    if dtype=='LINT' and count==2 and not isinstance(value,(dict,list)):
        return key,[parts],dtype
    if dtype=='DINT':
        key,paths,dtype=memory.region(ref,count,scope)
        return key,paths,dtype
    raise ModelError('WallClockTime destination requires '+('a scalar LINT or ' if count==2 else '')+str(count)+' contiguous DINT elements')


def validate(engine,op,scope):
    _,count=specification(engine,op);memory=engine.memory;previous=memory.structural
    memory.structural=True
    try:return destination(memory,op.args[3],scope,count)
    finally:memory.structural=previous


def execute(engine,op,scope):
    number,count=specification(engine,op);memory=engine.memory
    key,paths,dtype=destination(memory,op.args[3],scope,count)
    raw=engine.project.wall_clock.attributes(read_time=True).get(number)
    if raw is None or len(raw)!=count*4:
        raise ModelError('WallClockTime GSV value is unavailable from the host UTC clock')
    values=struct.unpack('<q' if dtype=='LINT' else '<'+'i'*count,raw)
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
                attributes=['CurrentValue','DateTime','LocalDateTime (explicit UTC local policy)'],
                destinations='CurrentValue: scalar LINT or two DINT cells; calendars: seven DINT cells; complete logical member windows',
                source='Existing host time.time_ns UTC clock; independent of simulated scan time; microseconds since 1970-01-01',
                sampling='One sample per reached GSV; separate calls may differ; no scan-wide snapshot',
                selection='Structural preflight; false/prescan skip live indices and time sampling; reached full writes establish unknown cells',
                st_for_effects='Exact complete windows for direct static references; aliases/AOI/indirect references conservatively cover their enclosing array',
                local_time='Existing explicit source UTC policy only; no workstation local-zone or extended DST inference',
                failures='Required unavailable clock, invalid destinations and later faults roll back the whole modeled advance',
                native_runtime_parity=False,clock_setters=False,ptp=False,
                remaining=['DT/TIME/DATETIMESTRUCT destinations and other attributes',
                           'Non-UTC/DST policies, SSV and synchronized/CST clock state',
                           'Native sampling, interruption, scheduling, layout and fault/lifecycle parity'])
