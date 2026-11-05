"""Logical EVENT, timeout and active-overlap status, separate from native Task status."""
import struct
from .model import ModelError
from . import event_tasks
from .gsv_configuration import current_instance
from .numeric_copy import static_reference

MASK=0x5


def matches(op):
    return (len(op.args)>=3 and all(isinstance(a,str) for a in op.args[:3])
            and op.args[0].casefold()=='task' and op.args[2].casefold() in ('status','overlapcount'))


def initial(engine):
    try:event_tasks.profile(engine.project)
    except ModelError:return {}
    return {t.name.casefold():0 for t in engine._task_scheduler.tasks if t.kind=='Event'}


def target(engine,op,scope,*,executing=False):
    if len(op.args)!=4 or any(not isinstance(a,str) for a in op.args) or not matches(op):
        raise ModelError('Event Task diagnostics require Task, an Event task name/THIS, Status/OverlapCount and a DINT tag')
    event_tasks.profile(engine.project)
    # Validate the actual ordinary caller, even when the target is explicitly named.
    current_instance(engine,'Program','THIS',scope,executing=executing,allow_event=True)
    name=current_instance(engine,'Task',op.args[1],scope,executing=executing,allow_event=True)
    scheduler=engine._task_scheduler
    task=next((t for t in scheduler.tasks if t.name.casefold()==name.casefold()),None)
    if task is None or task.kind!='Event':raise ModelError('Task Status requires a qualified instruction-only Event target')
    return task


def operand(engine,op,scope):
    memory=engine.memory
    key,parts,dtype=(memory.check_writable(op.args[3],scope) if op.name=='GSV' else memory.resolve(op.args[3],scope))
    if dtype!='DINT' or isinstance(memory.at(key,parts),(dict,list,bool)):
        raise ModelError('Event Task Status requires one exact scalar DINT tag')
    return key,parts


def validate(engine,op,scope):
    target(engine,op,scope);memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        key,parts=operand(engine,op,scope);return key,[parts],'DINT'
    finally:memory.structural=previous


def values(engine):
    dispatch=engine._event_dispatch
    return dispatch.status if dispatch is not None else engine._task_event_status


def overlap_counts(engine):
    scheduler=engine._task_scheduler
    if scheduler is None:return {}
    counts=engine._event_dispatch.overlap_counts if engine._event_dispatch is not None else scheduler.overlaps
    return {t.name.casefold():counts[i] for i,t in enumerate(scheduler.tasks) if t.kind=='Event'}


def execute(engine,op,power,scope):
    if not power:return power
    task=target(engine,op,scope,executing=True);name=task.name.casefold();key,parts=operand(engine,op,scope)
    if op.args[2].casefold()=='overlapcount':
        if op.name=='GSV':
            count=overlap_counts(engine)[name]
            if not 0<=count<1<<32:raise ModelError('Event Task OverlapCount word is unavailable')
            engine.memory.store(key,parts,struct.unpack('<i',struct.pack('<I',count))[0])
        else:
            dispatch=engine._event_dispatch
            if dispatch is None:raise ModelError('SSV Event Task OverlapCount requires an active advance')
            value=engine.memory.read(op.args[3],scope)
            if type(value) is not int:raise ModelError('SSV Event Task OverlapCount requires a known DINT')
            if value!=0:raise ModelError('SSV Event Task OverlapCount supports reset zero only')
            index=next(i for i,t in enumerate(engine._task_scheduler.tasks) if t.name.casefold()==name)
            dispatch.overlap_counts[index]=0
        return power
    state=values(engine)
    if name not in state:raise ModelError('Event Task Status is unavailable')
    if op.name=='GSV':engine.memory.store(key,parts,state[name])
    else:
        if engine._event_dispatch is None:raise ModelError('SSV Event Task Status requires an active advance')
        value=engine.memory.read(op.args[3],scope)
        if type(value) is not int:raise ModelError('SSV Event Task Status requires a known DINT')
        mask=MASK if task.timeout_ms is None else MASK|2
        if value & ~mask:
            raise ModelError('SSV Event Task Status supports only EVENT, qualified timeout and active-overlap bits')
        state[name]=value
    return power


def write_effects(engine,op,scope):
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        key,paths,_=validate(engine,op,scope)
        if static_reference(memory,op.args[3],scope):return [(key,p) for p in paths]
        parts=paths[0];boundary=next((i for i,p in enumerate(parts) if isinstance(p,int)),len(parts))
        return [(key,parts[:boundary])]
    finally:memory.structural=previous


def description():
    return dict(profile='v35-5580-logical-Event-Task-Status',languages=['RLL','ST'],
                attributes=['Status','OverlapCount'],
                overlap_count='Live active-request counter; exact DINT zero reset; independent of Status bits; DWORD availability without wrapping',
                overlap_lifecycle='Existing scheduler diagnostic: zero at Run entry/reset/load; detached replacement preserves committed counters',
                bits={'0':'Accepted EVENT instruction request','1':'Source-configured timeout dispatch','2':'Discarded request while target is active'},
                visibility='Live within an advance; latched until supported SSV replacement; reset/reload initializes zero',
                setters='Exact DINT replacement of modeled bits; bit 1 requires a source-enabled timeout; source retained',
                contexts='Ordinary scheduled Programs, named Event target or THIS inside its Event task; no AOI/harness',
                duplicates='Pending requests still coalesce; they do not set the active-overlap bit',
                rollback='Status and task/data progress commit only with a successful complete advance',
                native_protocol_expanded=False,native_runtime_parity=False,
                remaining=['External event sources and other Task status bits','Continuous/Periodic/Safety status setters',
                           'AOI/harness contexts and native pending/interrupt/status/fault/lifecycle parity'])
