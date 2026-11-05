"""Typed GSV reads of explicit settings and their bounded runtime overrides."""
import re
import struct

from .identity import CONTROLLOGIX_5580_PRODUCT_CODES
from .integer_math import CONTROLLERS
from .model import ModelError, coerce
from .numeric_copy import prefix, static_reference
from .string_operations import string_operand
from .task_configuration import NAME

TASK = {'rate':(2,'DINT'), 'watchdog':(12,'DINT'), 'priority':(6,'INT'),
        'disableupdateoutputs':(18,'DINT'), 'inhibittask':(19,'DINT')}
DEVICE_NAME_SIZE = 33
CONTROLLER = {'timeslice':('time_slice','time_slice_defaulted','TimeSlice'),
              'shareunusedtimeslice':('share_unused_time_slice','share_unused_defaulted','ShareUnusedTimeSlice')}


CONTROLLER_FLAGS = {
    'canuserpifromproducer': ('DINT', 'can_use_rpi_from_producer'),
    'redundancyenabled': ('SINT', 'source_redundancy_configured'),
    'keeptesteditsonswitchover': ('SINT', 'continue_test_edits'),
    'inhibitautomaticfirmwareupdate': ('BOOL', 'automatic_firmware_update_inhibit'),
}


def current_instance(engine, cls, instance, scope='', *, executing=False, allow_event=False):
    """Resolve THIS from a source-bound scheduled Program, never saved tag data."""
    if instance.casefold()!='this':return instance
    project=engine.project;configuration=project.task_configuration
    if (project.version!='35' or project.processor.upper() not in CONTROLLERS
            or engine.mode!='project' or scope in engine.memory.frames):
        raise ModelError('GSV THIS requires an ordinary v35 5580 project Program context; AOI/harness contexts remain unqualified')
    name=next((n for n in project.programs if n.casefold()==scope.casefold()),None)
    program=project.programs.get(name)
    if (not program or program['class']!='Standard' or program['use_as_folder']
            or (program['disabled'] and name.casefold() not in engine._program_activation)
            or not configuration.source_complete or configuration.source_sha256!=project.sha256
            or not project.program_configuration.type_attributes(name,source_sha256=project.sha256)
            or not any(project.routines[entry].program==name for entry in engine.entries if entry in project.routines)):
        raise ModelError('GSV THIS requires an eligible scheduled ordinary Standard Program and complete current source')
    owners=[task for task in project.tasks if any(p.casefold()==name.casefold() for p in task['programs'])]
    scheduler=engine._task_scheduler
    kinds=('Continuous','Periodic','Event') if allow_event else ('Continuous','Periodic')
    if (len(owners)!=1 or owners[0]['class']!='Standard' or owners[0]['type'] not in kinds
            or scheduler is None or scheduler.source!=scheduler.configuration):
        raise ModelError('GSV THIS requires one unchanged eligible Standard owner Task')
    owner=owners[0]['name']
    if executing and (not isinstance(engine._executing_task,str) or engine._executing_task.casefold()!=owner.casefold()):
        raise ModelError('GSV THIS has no matching active Task execution context')
    return name if cls.casefold()=='program' else owner


def component_name(engine, cls, instance, scope, *, executing):
    owner = current_instance(engine, 'Program', 'THIS', scope, executing=executing, allow_event=True)
    project = engine.project
    catalog = project.executable_configuration
    if cls == 'program':
        if instance.casefold() == 'this':
            instance = owner
        name = next((name for name in catalog.program_names if name.casefold() == instance.casefold()), None)
        program = project.programs.get(name)
        if (catalog.source_sha256 != project.sha256 or not program or program['use_as_folder']
                or not project.program_configuration.type_attributes(name, source_sha256=project.sha256)):
            raise ModelError('GSV Program Name requires an ordinary Program in the current source')
        return name

    names = catalog.routine_names(owner, source_sha256=project.sha256)
    if not names:
        raise ModelError('GSV Routine Name requires the current Program routine inventory')
    if instance.casefold() == 'this':
        if not executing:
            return None  # Destination preflight needs the type, not an active call.
        routine = engine._executing_routine
        if routine is None or routine.program != owner:
            raise ModelError('GSV Routine THIS requires the current Program routine')
        instance = routine.name
    name = next((name for name in names if name.casefold() == instance.casefold()), None)
    bound = project.routines.get(f'{owner}/{name}'.lower()) if name is not None else None
    if bound is None or bound.program != owner or bound.name != name:
        raise ModelError('GSV Routine Name requires a Routine in the current Program')
    return name


def controller_device(engine, instance, attribute, *, executing):
    project = engine.project
    if instance:
        raise ModelError('GSV ControllerDevice requires an empty instance operand')
    fields = project.source_controller_settings
    processor = project.processor.upper()
    if not {'ProcessorType', 'MajorRev'} <= fields or processor not in CONTROLLOGIX_5580_PRODUCT_CODES:
        raise ModelError('GSV ControllerDevice requires an explicit v35 5580 processor and major revision')
    if attribute == 'status':
        status = engine._scan_controller_status
        if executing and status is None:
            raise ModelError('GSV ControllerDevice Status requires an active scan')
        return 'INT', status
    if attribute == 'devicename':
        name = processor.encode('ascii')
        return 'SINT[33]', (bytes((len(name),)) + name).ljust(DEVICE_NAME_SIZE, b'\0')
    if attribute == 'productrev':
        minor = project.minor_version
        if 'MinorRev' not in fields or not re.fullmatch(r'[0-9]{1,3}', minor) or int(minor) > 255:
            raise ModelError('GSV ControllerDevice ProductRev requires an explicit byte-sized minor revision')
        return 'INT', struct.unpack('<h', bytes((35, int(minor))))[0]
    if attribute == 'productcode':
        return 'INT', CONTROLLOGIX_5580_PRODUCT_CODES[processor]
    if attribute == 'type':
        return 'INT', 14
    if attribute == 'vendor':
        return 'INT', 1
    raise ModelError('Unsupported GSV ControllerDevice attribute ' + attribute)


def source(engine, op, scope='', *, executing=False):
    if len(op.args)!=4 or any(not isinstance(a,str) for a in op.args):
        raise ModelError('GSV requires four neutral-text operands')
    project=engine.project;configuration=project.task_configuration
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:
        raise ModelError('GSV configuration requires the v35 ControlLogix 5580 software profile')
    if not configuration.source_complete or configuration.source_sha256!=project.sha256:
        raise ModelError('GSV configuration source is incomplete or unavailable')
    cls,instance,attribute,_=op.args;cls=cls.casefold();attribute=attribute.casefold()
    if cls == 'controllerdevice':
        return controller_device(engine, instance, attribute, executing=executing)
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
        if attribute in CONTROLLER_FLAGS:
            dtype, field = CONTROLLER_FLAGS[attribute]
            controller = project.controller_configuration
            value = getattr(controller, field)
            if (value not in (0, 1) or
                    attribute == 'keeptesteditsonswitchover' and controller.source_redundancy_configured is None):
                raise ModelError('GSV Controller '+op.args[2]+' requires an unambiguous explicit 0/1 setting')
            return dtype, coerce(value, dtype)
        raise ModelError('Unsupported GSV Controller configuration attribute '+op.args[2])
    if cls in ('program','routine') and attribute=='name':
        return 'STRING',component_name(engine,cls,instance,scope,executing=executing)
    if cls!='task':raise ModelError('GSV configuration supports Task/Controller settings, ControllerDevice identity and Program/Routine Name')
    instance=current_instance(engine,cls,instance,scope,executing=executing,allow_event=True)
    name=next((n for n in configuration.names if n.casefold()==instance.casefold()),None)
    task=next((t for t in project.tasks if name is not None and t['name']==name),None)
    if not task or task['class']!='Standard' or task['type'] not in ('Continuous','Periodic','Event'):
        raise ModelError('GSV Task requires an explicit existing Standard task name')
    if task['type']=='Event':
        from .event_tasks import profile,timeout_settings
        profile(project)
        current_instance(engine,'Program','THIS',scope,executing=executing,allow_event=True)
        if attribute in ('enabletimeout','rate'):
            index=next(i for i,t in enumerate(engine._task_scheduler.tasks) if t.name==name)
            setting=timeout_settings(engine)[index]
            if attribute=='enabletimeout':return 'DINT',int(setting.enabled)
            if setting.period_ms is not None:return 'DINT',setting.period_ms*1000
            if executing and op.name=='GSV':raise ModelError('GSV Event Rate requires a defined timeout period')
            return 'DINT',None
    if attribute=='name':return 'STRING',name
    if attribute=='instance':
        scheduler=engine._task_scheduler
        slot=engine.runtime_references.task_slot(project,name)
        if scheduler is None or scheduler.source!=scheduler.configuration or slot is None:
            raise ModelError('GSV Task Instance requires an unchanged project Task registry')
        return 'DINT',slot
    if attribute not in TASK:raise ModelError('Unsupported GSV Task configuration attribute '+op.args[2])
    number,dtype=TASK[attribute]
    if attribute=='priority' and task['type'] not in ('Periodic','Event'):
        raise ModelError('GSV Continuous Task Priority remains unqualified')
    values=project.task_timing.attributes(name,source_sha256=project.sha256)
    values.update(configuration.attributes(name,source_sha256=project.sha256))
    raw=values.get(number)
    if raw is None:raise ModelError('GSV Task attribute is unavailable from explicit source settings')
    if attribute in ('inhibittask','rate','priority','watchdog') and engine._task_scheduler is not None:
        scheduler=engine._task_scheduler
        if scheduler.source!=scheduler.configuration:raise ModelError('Task configuration changed; reload the project')
        index=next(i for i,t in enumerate(scheduler.tasks) if t.name==name)
        if attribute=='inhibittask':return dtype,int(scheduler.inhibitions[index])
        if attribute=='rate':return dtype,scheduler.periods[index]*1000
        if attribute=='priority':return dtype,scheduler.priorities[index]
        if index in scheduler.watchdog_overrides:return dtype,scheduler.watchdog_overrides[index]
    return dtype,struct.unpack('<h' if dtype=='INT' else '<i',raw)[0]


def destination(memory, ref, scope, dtype):
    if dtype == 'SINT[33]':
        key, parts, kind = prefix(memory, ref, scope, DEVICE_NAME_SIZE, writable=True)
        if kind != 'SINT' or len(parts) != DEVICE_NAME_SIZE:
            raise ModelError('GSV ControllerDevice DeviceName requires 33 writable contiguous SINT elements')
        return key, parts, kind
    if dtype=='STRING':
        string_operand(memory,ref,scope,destination=True)
        key,parts,kind=memory.resolve(ref,scope)
    else:
        key,parts,kind=memory.check_writable(ref,scope)
        error = 'GSV configuration destination must be an exact scalar '+dtype+' tag'
        if kind != dtype or (parts and isinstance(parts[-1], tuple)):
            raise ModelError(error)
        value = memory.at(key,parts)
        if isinstance(value, (dict,list)) or (dtype != 'BOOL' and isinstance(value, bool)):
            raise ModelError(error)
    return key,[parts],kind


def validate(engine, op, scope):
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        dtype,_=source(engine,op,scope)
        return destination(memory,op.args[3],scope,dtype)
    finally:memory.structural=previous


def execute(engine, op, scope):
    dtype,value=source(engine,op,scope,executing=True);memory=engine.memory
    key,paths,_=destination(memory,op.args[3],scope,dtype)
    if dtype == 'SINT[33]':
        for path, byte in zip(paths, value, strict=True):
            memory.store(key, path, byte)
    elif dtype=='STRING':memory.write_string(op.args[3],value,scope)
    else:memory.write(op.args[3],value,scope)



def write_effects(engine,op,scope):
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        key,paths,_=validate(engine,op,scope)
        if static_reference(memory,op.args[3],scope):return [(key,path) for path in paths]
        parts=paths[0];boundary=next((i for i,part in enumerate(parts) if isinstance(part,int)),len(parts))
        return [(key,parts[:boundary])]
    finally:memory.structural=previous


def description():
    return dict(profile='v35-5580-explicit-GSV-configuration', languages=['RLL','ST'],
                task=['Name','Instance','Rate (Periodic or Event timeout)','EnableTimeOut (Event)','Watchdog','Priority (Periodic/Event)','InhibitTask','DisableUpdateOutputs'],
                controller=['Name','TimeSlice (explicit)','ShareUnusedTimeSlice (explicit)',
                            'CanUseRPIFromProducer','RedundancyEnabled','KeepTestEditsOnSwitchover','InhibitAutomaticFirmwareUpdate'],
                controller_flags='Read-only explicit project flags. No producer negotiation, redundancy switchover or firmware service.',
                program=['Name'],routine=['Name'],
                controller_device=['DeviceName','ProductCode','ProductRev','Type','Vendor','Status'],
                controller_device_source='v35 5580 project processor and firmware revision, plus modeled controller mode at scan entry.',
                controller_device_status='Remote keyswitch; Program 0x3070, Run 0x3060, software fault 0x3450 at retry entry.',
                task_instance='Zero-based slot in the current emulator Task registry, independent of native CIP instance IDs.',
                component_names='Named Program or THIS and Program-scoped Routine or THIS in ordinary scheduled project logic.',
                destinations='Exact BOOL/SINT/INT/DINT scalars, represented LEN/DATA strings, or a 33-cell SINT window for DeviceName; no cross-type byte copies',
                times='Microseconds from exact milliseconds; no inferred defaults',
                state='Source configuration with live Task InhibitTask, Watchdog, Periodic Rate and Periodic/Event Priority in project mode',
                selection='Structural destination validation without saved dynamic indices; false/prescan skip outputs; full writes establish unknown cells',
                st_for_effects='Complete static destinations; aliases/AOI/changing selections conservatively cover enclosing arrays',
                native_runtime_equivalence=False, ssv=True,
                current_instance='Task, Program and Routine THIS in ordinary scheduled Continuous/Periodic/qualified Event Program routines. AOI/harness THIS unqualified.',
                remaining=['Empty instance, native instance IDs and AOI/harness THIS contexts','Continuous priority/rate and zero-watchdog defaults',
                           'Scan-time/interval/status/fault attributes','Other classes/attributes and broader SSV'])
