"""Logical EVENT-trigger/active-overlap status, separate from native Task status."""
from .model import ModelError
from . import event_tasks
from .gsv_configuration import current_instance
from .numeric_copy import static_reference

MASK=0x5


def matches(op):
    return (len(op.args)>=3 and all(isinstance(a,str) for a in op.args[:3])
            and op.args[0].casefold()=='task' and op.args[2].casefold()=='status')


def initial(engine):
    try:event_tasks.profile(engine.project)
    except ModelError:return {}
    return {t.name.casefold():0 for t in engine._task_scheduler.tasks if t.kind=='Event'}


def target(engine,op,scope,*,executing=False):
    if len(op.args)!=4 or any(not isinstance(a,str) for a in op.args) or not matches(op):
        raise ModelError('Event Task Status requires Task, an Event task name/THIS, Status and a DINT tag')
    event_tasks.profile(engine.project)
    # Validate the actual ordinary caller, even when the target is explicitly named.
    current_instance(engine,'Program','THIS',scope,executing=executing,allow_event=True)
    name=current_instance(engine,'Task',op.args[1],scope,executing=executing,allow_event=True)
    scheduler=engine._task_scheduler
    task=next((t for t in scheduler.tasks if t.name.casefold()==name.casefold()),None)
    if task is None or task.kind!='Event':raise ModelError('Task Status requires a qualified instruction-only Event target')
    return task.name.casefold()


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


def execute(engine,op,power,scope):
    if not power:return power
    name=target(engine,op,scope,executing=True);key,parts=operand(engine,op,scope)
    state=values(engine)
    if name not in state:raise ModelError('Event Task Status is unavailable')
    if op.name=='GSV':engine.memory.store(key,parts,state[name])
    else:
        if engine._event_dispatch is None:raise ModelError('SSV Event Task Status requires an active advance')
        value=engine.memory.read(op.args[3],scope)
        if type(value) is not int:raise ModelError('SSV Event Task Status requires a known DINT')
        if value & ~MASK:raise ModelError('SSV Event Task Status supports only EVENT and active-overlap bits (0 and 2)')
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
                bits={'0':'Accepted EVENT instruction request','2':'Discarded request while target is active'},
                visibility='Live within an advance; latched until supported SSV replacement; reset/reload initializes zero',
                setters='Exact DINT source containing 0, 1, 4 or 5; source retained',
                contexts='Ordinary scheduled Programs, named Event target or THIS inside its Event task; no AOI/harness',
                duplicates='Pending requests still coalesce; they do not set the active-overlap bit',
                rollback='Status and task/data progress commit only with a successful complete advance',
                native_protocol_expanded=False,native_runtime_parity=False,
                remaining=['Timeout/external event sources and other Task status bits','Continuous/Periodic/Safety status setters',
                           'AOI/harness contexts and native pending/interrupt/status/fault/lifecycle parity'])
