"""Typed GSV reads of explicit source settings, without scheduling side effects."""
import struct

from .integer_math import CONTROLLERS
from .model import ModelError, coerce
from .string_operations import string_operand
from .task_configuration import NAME

TASK = {'rate':(2,'DINT'), 'watchdog':(12,'DINT'), 'priority':(6,'INT'),
        'disableupdateoutputs':(18,'DINT'), 'inhibittask':(19,'DINT')}
CONTROLLER = {'timeslice':('time_slice','time_slice_defaulted','TimeSlice'),
              'shareunusedtimeslice':('share_unused_time_slice','share_unused_defaulted','ShareUnusedTimeSlice')}


def current_instance(engine, cls, instance, scope='', *, executing=False, allow_event=False):
    """Resolve THIS from a source-bound scheduled Program, never saved tag data."""
    if instance.casefold()!='this':return instance
    project=engine.project;configuration=project.task_configuration
    if (project.version!='35' or project.processor.upper() not in CONTROLLERS
            or engine.mode!='project' or scope in engine.memory.frames):
        raise ModelError('GSV THIS requires an ordinary v35 5580 project Program context; AOI/harness contexts remain unqualified')
    name=next((n for n in project.programs if n.casefold()==scope.casefold()),None)
    program=project.programs.get(name)
    if (not program or program['class']!='Standard' or program['disabled'] or program['use_as_folder']
            or not configuration.source_complete or configuration.source_sha256!=project.sha256
            or not project.program_configuration.type_attributes(name,source_sha256=project.sha256)
            or not any(project.routines[entry].program==name for entry in engine.entries if entry in project.routines)):
        raise ModelError('GSV THIS requires an eligible scheduled ordinary Standard Program and complete current source')
    owners=[task for task in project.tasks if any(p.casefold()==name.casefold() for p in task['programs'])]
    scheduler=engine._task_scheduler
    kinds=('Continuous','Periodic','Event') if allow_event else ('Continuous','Periodic')
    if (len(owners)!=1 or owners[0]['class']!='Standard' or owners[0]['type'] not in kinds
            or scheduler is None or scheduler.source!=scheduler.configuration):
        raise ModelError('GSV THIS requires one unchanged Standard Continuous/Periodic owner Task')
    owner=owners[0]['name']
    if executing and (not isinstance(engine._executing_task,str) or engine._executing_task.casefold()!=owner.casefold()):
        raise ModelError('GSV THIS has no matching active Task execution context')
    return name if cls.casefold()=='program' else owner


def source(engine, op, scope='', *, executing=False):
    if len(op.args)!=4 or any(not isinstance(a,str) for a in op.args):
        raise ModelError('GSV requires four neutral-text operands')
    project=engine.project;configuration=project.task_configuration
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:
        raise ModelError('GSV configuration requires the v35 ControlLogix 5580 software profile')
    if not configuration.source_complete or configuration.source_sha256!=project.sha256:
        raise ModelError('GSV configuration source is incomplete or unavailable')
    cls,instance,attribute,_=op.args;cls=cls.casefold();attribute=attribute.casefold()
    if cls=='controller':
        if instance:raise ModelError('GSV Controller requires an empty instance operand')
        if attribute=='name':
            name=project.source_controller_name
            if not isinstance(name,str) or not NAME.fullmatch(name):raise ModelError('GSV Controller Name is unavailable')
            return 'STRING',name
        if attribute in CONTROLLER:
            setting,defaulted,field=CONTROLLER[attribute];controller=project.controller_configuration
            value=getattr(controller,setting)
            if value is None or getattr(controller,defaulted) or field not in project.source_controller_settings:
                raise ModelError('GSV Controller setting is unavailable without an explicit source value')
            return 'INT',coerce(value,'INT')
        raise ModelError('Unsupported GSV Controller configuration attribute '+op.args[2])
    if cls!='task':raise ModelError('GSV configuration supports Task and Controller only')
    instance=current_instance(engine,cls,instance,scope,executing=executing)
    name=next((n for n in configuration.names if n.casefold()==instance.casefold()),None)
    task=next((t for t in project.tasks if name is not None and t['name']==name),None)
    if not task or task['class']!='Standard' or task['type'] not in ('Continuous','Periodic'):
        raise ModelError('GSV Task requires an explicit existing Standard Continuous/Periodic task name')
    if attribute=='name':return 'STRING',name
    if attribute not in TASK:raise ModelError('Unsupported GSV Task configuration attribute '+op.args[2])
    number,dtype=TASK[attribute]
    if attribute=='priority' and task['type']!='Periodic':
        raise ModelError('GSV Continuous Task Priority remains unqualified')
    values=project.task_timing.attributes(name,source_sha256=project.sha256)
    values.update(configuration.attributes(name,source_sha256=project.sha256))
    raw=values.get(number)
    if raw is None:raise ModelError('GSV Task attribute is unavailable from explicit source settings')
    if attribute=='inhibittask' and engine._task_scheduler is not None:
        scheduler=engine._task_scheduler
        if scheduler.source!=scheduler.configuration:raise ModelError('Task configuration changed; reload the project')
        index=next(i for i,t in enumerate(scheduler.tasks) if t.name==name)
        return dtype,int(scheduler.inhibitions[index])
    return dtype,struct.unpack('<h' if dtype=='INT' else '<i',raw)[0]


def destination(memory, ref, scope, dtype):
    if dtype=='STRING':
        string_operand(memory,ref,scope,destination=True)
        key,parts,kind=memory.resolve(ref,scope)
    else:
        key,parts,kind=memory.check_writable(ref,scope)
        if kind!=dtype or isinstance(memory.at(key,parts),(dict,list,bool)):
            raise ModelError('GSV configuration destination must be an exact scalar '+dtype+' tag')
    return key,[parts],kind


def validate(engine, op, scope):
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        dtype,_=source(engine,op,scope)
        return destination(memory,op.args[3],scope,dtype)
    finally:memory.structural=previous


def execute(engine, op, scope):
    dtype,value=source(engine,op,scope,executing=True);memory=engine.memory
    destination(memory,op.args[3],scope,dtype)
    if dtype=='STRING':memory.write_string(op.args[3],value,scope)
    else:memory.write(op.args[3],value,scope)



def write_effects(engine,op,scope):
    from .numeric_copy import static_reference
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        key,paths,_=validate(engine,op,scope)
        if static_reference(memory,op.args[3],scope):return [(key,path) for path in paths]
        parts=paths[0];boundary=next((i for i,part in enumerate(parts) if isinstance(part,int)),len(parts))
        return [(key,parts[:boundary])]
    finally:memory.structural=previous


def description():
    return dict(profile='v35-5580-explicit-GSV-configuration', languages=['RLL','ST'],
                task=['Name','Rate (Periodic)','Watchdog','Priority (Periodic)','InhibitTask','DisableUpdateOutputs'],
                controller=['Name','TimeSlice (explicit)','ShareUnusedTimeSlice (explicit)'],
                destinations='Exact INT/DINT scalars or represented LEN/DATA strings; no cross-type byte copies',
                times='Microseconds from exact source milliseconds; no inferred defaults',
                state='Source configuration; Task InhibitTask reads live runtime inhibition in project mode',
                selection='Structural destination validation without saved dynamic indices; false/prescan skip outputs; full writes establish unknown cells',
                st_for_effects='Complete static destinations; aliases/AOI/changing selections conservatively cover enclosing arrays',
                native_runtime_equivalence=False, ssv=True,
                current_instance='Task THIS in ordinary scheduled Continuous/Periodic Program routines; named reads unchanged; AOI/harness THIS unqualified',
                remaining=['Empty instance, native instance IDs and AOI/harness/Event THIS contexts','Continuous priority/rate and zero-watchdog defaults',
                           'Scan-time/interval/status/fault attributes','Other classes/attributes and broader SSV'])
