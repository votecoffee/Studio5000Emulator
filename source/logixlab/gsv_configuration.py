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


def source(engine, op):
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
    dtype,_=source(engine,op)
    return destination(engine.memory,op.args[3],scope,dtype)


def execute(engine, op, scope):
    dtype,value=source(engine,op);memory=engine.memory
    destination(memory,op.args[3],scope,dtype)
    if dtype=='STRING':memory.write_string(op.args[3],value,scope)
    else:memory.write(op.args[3],value,scope)


def description():
    return dict(profile='v35-5580-explicit-GSV-configuration', languages=['RLL','ST'],
                task=['Name','Rate (Periodic)','Watchdog','Priority (Periodic)','InhibitTask','DisableUpdateOutputs'],
                controller=['Name','TimeSlice (explicit)','ShareUnusedTimeSlice (explicit)'],
                destinations='Exact INT/DINT scalars or represented LEN/DATA strings; no cross-type byte copies',
                times='Microseconds from exact source milliseconds; no inferred defaults',
                state='Configuration reads only; no task, watchdog, I/O or CPU timeslice side effects',
                native_runtime_equivalence=False, ssv=False,
                remaining=['Task current/THIS/empty instance and native instance IDs','Continuous priority/rate and zero-watchdog defaults',
                           'Scan-time/interval/status/fault attributes','Other classes/attributes and SSV'])
