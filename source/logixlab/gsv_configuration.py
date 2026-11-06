"""Typed GSV reads of explicit settings and their bounded runtime overrides."""
from dataclasses import dataclass
import re
import struct
from uuid import uuid4

from .identity import CONTROLLOGIX_5580_PRODUCT_CODES
from .integer_math import CONTROLLERS
from .model import ModelError, coerce, dimensions
from .numeric_copy import location, prefix, static_reference
from .string_operations import string_operand
from .task_configuration import NAME

TASK = {'rate':(2,'DINT'), 'watchdog':(12,'DINT'), 'priority':(6,'INT'),
        'disableupdateoutputs':(18,'DINT'), 'inhibittask':(19,'DINT')}
DEVICE_NAME_SIZE = 33
MAJOR_FAULT_RECORD = 'major-fault-record'
MAJOR_FAULT_WORDS = 11
FAULT_RECORD_LINT = 'fault-record-lint'
FAULT_RECORD_SPLIT = 'fault-record-split'
FAULT_RECORD_TAIL = (('INT', ()), ('INT', ()), ('DINT', (8,)))
FAULT_RECORD_LAYOUTS = {
    (('LINT', ()),) + FAULT_RECORD_TAIL: FAULT_RECORD_LINT,
    (('DINT', ()), ('DINT', ())) + FAULT_RECORD_TAIL: FAULT_RECORD_SPLIT,
}
MODULE_PATH = 'module-path'
MODULE_STATUS = {'forcestatus': 9, 'ledstatus': 11}
MODULE_FAULTED = 0x1000
MODULE_RUNNING = 0x4000
MODULE_INHIBITED = 0x6000
MODULE_WAITING = 0x7000
MODULE_CONNECTION_ATTRIBUTES = {'entrystatus': 'INT', 'faultcode': 'INT', 'faultinfo': 'DINT'}
MODULE_INHIBIT_BIT = 1 << 2
MODULE_MAJOR_FAULT_BIT = 1
MODULE_MODE_MASK = MODULE_INHIBIT_BIT | MODULE_MAJOR_FAULT_BIT
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


@dataclass(frozen=True)
class ModuleConnection:
    fault_code: int = 0
    fault_info: int = 0


def _configuration_source(engine):
    project = engine.project
    configuration = project.task_configuration
    if project.version != '35' or project.processor.upper() not in CONTROLLERS:
        raise ModelError('GSV configuration requires the v35 ControlLogix 5580 software profile')
    if not configuration.source_complete or configuration.source_sha256 != project.sha256:
        raise ModelError('GSV configuration source is incomplete or unavailable')
    return project


def configure_module_connection(engine, data, *, running=False):
    project = _configuration_source(engine)
    name, state = data.get('module'), data.get('state')
    if not isinstance(name, str) or state not in ('running', 'faulted', 'clear'):
        raise ModelError('Module connection requires a module name and running, faulted or clear state')
    module = project.io_map.named_module(name)
    if module is None or module.route is None or module.inhibited is None:
        raise ModelError('Module connection requires a qualified route and an explicit Inhibited setting')
    required = {'project_generation', 'module', 'state'}
    if state == 'faulted':
        required.update(('fault_code', 'fault_info'))
    if set(data) != required:
        raise ModelError('Module connection fields do not match the requested state')
    if state == 'clear':
        engine._module_connections.pop(module.name, None)
        return {'module': module.name, 'state': state}
    code, info = data.get('fault_code', 0), data.get('fault_info', 0)
    if state == 'faulted' and (type(code) is not int or not 0 < code <= 0xffff
                               or type(info) is not int or not -(1 << 31) <= info < (1 << 31)):
        raise ModelError('Faulted module requires a nonzero 16-bit fault code and signed DINT fault info')
    connection = ModuleConnection(code, info)
    if running and engine.mode == 'project' and code:
        _apply_run_connection_fault(engine, module, connection)
    else:
        engine._module_connections[module.name] = connection
    return {'module': module.name, 'state': state, 'fault_code': code, 'fault_info': info}


def _module_mode(engine, module):
    return engine._module_modes.get(module.name, module.mode())


def _module_required(engine, module):
    return bool((_module_mode(engine, module) or 0) & MODULE_MAJOR_FAULT_BIT)


def _module_inhibited(engine, module):
    override = engine._module_modes.get(module.name)
    return module.inhibited if override is None else bool(override & MODULE_INHIBIT_BIT)


def _module_connection_state(engine, module, find_parent):
    if _module_inhibited(engine, module):
        return MODULE_INHIBITED, None, None
    parent_name = module.routed_parent
    faulted_ancestor = None
    # Only follow dependencies for which the parser proved a route.
    while parent_name is not None:
        parent = find_parent(parent_name)
        if parent is None:
            break
        if _module_inhibited(engine, parent):
            return MODULE_WAITING, None, None
        upstream_connection = engine._module_connections.get(parent.name)
        if upstream_connection and upstream_connection.fault_code:
            # The fault nearest the controller is the effective blocker.
            faulted_ancestor = parent
        parent_name = parent.routed_parent
    if faulted_ancestor is not None:
        return MODULE_WAITING, None, faulted_ancestor
    connection = engine._module_connections.get(module.name)
    if connection is None:
        return None, None, None
    return (MODULE_FAULTED if connection.fault_code else MODULE_RUNNING), connection, None


def _apply_run_connection_fault(engine, module, connection):
    modules = {item.name: item for item in engine.project.io_map.module_settings}
    required_running = {
        item.name: item for item in modules.values()
        if item.name in engine._module_connections and _module_required(engine, item)
        and _module_connection_state(engine, item, modules.get)[0] == MODULE_RUNNING
    }
    engine._module_connections[module.name] = connection
    if module.name in required_running:
        _latch_module_major_fault(engine, module, connection, 16)
        return
    # Only the injected fault changed between these two effective-state reads.
    for item in required_running.values():
        if _module_connection_state(engine, item, modules.get)[0] == MODULE_WAITING:
            _latch_module_major_fault(engine, item, connection, 16, upstream=module)
            return


def _latch_module_major_fault(engine, module, connection, code, *, upstream=None):
    label = module.display_name or module.name
    reason = ('lost its simulated connection' if code == 16
              else 'could not establish its simulated connection before Run')
    diagnostic = 'module fault'
    fault = {'type': 3, 'code': code, 'module': module.name,
             'fault_code': connection.fault_code, 'fault_info': connection.fault_info, 'fault_id': uuid4().hex}
    if upstream is not None:
        fault['upstream_module'] = upstream.name
        reason += f' through {upstream.display_name or upstream.name}'
        diagnostic = 'upstream module fault'
    engine.module_major_fault = fault
    engine.fault = (f'Required module {label} {reason} '
                    f'(Type 3 Code {code}, {diagnostic} 0x{connection.fault_code:04X}, info {connection.fault_info}).')
    engine.run_module_fault_handler()


def fault_on_run_entry(engine):
    if engine.mode != 'project' or not engine._module_connections:
        return False
    modules = {module.name: module for module in engine.project.io_map.module_settings}
    upstream_failure = None
    for module in modules.values():
        if not _module_required(engine, module):
            continue
        status, connection, upstream = _module_connection_state(engine, module, modules.get)
        if status == MODULE_FAULTED:
            _latch_module_major_fault(engine, module, connection, 23)
            return True
        if upstream is not None and upstream_failure is None:
            upstream_failure = module, upstream
    if upstream_failure is None:
        return False
    module, upstream = upstream_failure
    _latch_module_major_fault(engine, module, engine._module_connections[upstream.name], 23, upstream=upstream)
    return True


def module_major_fault_state(engine):
    fault = engine.module_major_fault
    if fault is None:
        return None
    find_module = engine.project.io_map.named_module
    recovery = [fault['module']]
    if 'upstream_module' in fault:
        recovery.append(fault['upstream_module'])
    ready = all(_module_connection_state(engine, find_module(name), find_module)[0] == MODULE_RUNNING
                for name in recovery)
    return {**fault, 'clear_ready': ready}


def clear_module_major_fault(engine, fault_id):
    fault = module_major_fault_state(engine)
    if fault is None or fault_id != fault['fault_id']:
        raise ModelError('Clear requires the current I/O major fault')
    if not fault['clear_ready']:
        modules = 'the required module and its upstream module' if 'upstream_module' in fault else 'the faulted module'
        raise ModelError(f'Restore {modules} to effective Running before clearing the I/O major fault')
    engine.module_major_fault = None
    engine.fault = ''


def simulated_module_connections(engine):
    try:
        project = _configuration_source(engine)
    except ModelError:
        return []
    modules = {module.name: module for module in project.io_map.module_settings}
    rows = []
    for module in modules.values():
        if module.route is None or module.inhibited is None:
            continue
        status, _, _ = _module_connection_state(engine, module, modules.get)
        connection = engine._module_connections.get(module.name)
        applied = {'state': 'clear'}
        if connection is not None:
            applied = {'state': 'faulted' if connection.fault_code else 'running',
                       'fault_code': connection.fault_code, 'fault_info': connection.fault_info}
        mode = _module_mode(engine, module)
        rows.append({'name': module.name, 'label': module.display_name or module.name,
                     'entry_status': status, 'input': applied,
                     'major_fault_on_loss': None if mode is None else bool(mode & MODULE_MAJOR_FAULT_BIT)})
    return rows


def _module_connection_attribute(engine, module, attribute, *, executing):
    dtype = MODULE_CONNECTION_ATTRIBUTES[attribute]
    if module.inhibited is None:
        raise ModelError('GSV Module connection status requires an explicit source Inhibited setting')
    if attribute != 'entrystatus' and module.route is None:
        raise ModelError('GSV Module fault diagnostics require a qualified route')
    if not executing:
        return dtype, None
    status, connection, _ = _module_connection_state(engine, module, engine.project.io_map.named_module)
    if attribute == 'entrystatus':
        if status is None:
            raise ModelError('GSV Module EntryStatus is unavailable while the module is uninhibited, no modeled parent is inhibited, and no connection state is set')
        return dtype, status
    if connection is None:
        raise ModelError('GSV Module fault diagnostics require an effective simulated connection state')
    if attribute == 'faultinfo':
        return dtype, connection.fault_info
    code = connection.fault_code
    return dtype, code if code < 0x8000 else code - 0x10000


def _module_led_status(engine):
    by_name = {module.name: module for module in engine.project.io_map.module_settings}
    states = {_module_connection_state(engine, module, by_name.get)[0] for module in by_name.values()}
    running = MODULE_RUNNING in states
    if running and states - {None, MODULE_RUNNING}:
        return 2
    if None in states:
        raise ModelError('GSV Module LEDStatus is unavailable while module states are unknown')
    return 3 if running else 1


def module_attribute(engine, instance, attribute, *, executing):
    io_map = engine.project.io_map
    if not instance and attribute == 'ledstatus' and io_map.led_inventory_complete:
        return 'INT', _module_led_status(engine) if executing else None
    if not instance and attribute in MODULE_STATUS:
        raw = io_map.attributes().get(MODULE_STATUS[attribute]) if io_map.module_status_qualified else None
        if raw is None:
            if attribute == 'ledstatus':
                raise ModelError('GSV Module LEDStatus requires a complete supported module inventory')
            raise ModelError('GSV Module status requires a complete controller-only I/O map without forces')
        return 'INT', struct.unpack('<h', raw)[0]
    if not instance or (attribute not in ('mode', 'path') and attribute not in MODULE_CONNECTION_ATTRIBUTES):
        raise ModelError('GSV Module requires a name for Mode, EntryStatus, Path or fault diagnostics, or a blank instance for ForceStatus or LEDStatus')
    module = io_map.named_module(instance)
    if module is None:
        raise ModelError('GSV Module requires an unambiguous supported named module in complete source')
    if attribute == 'path':
        if module.route is None:
            raise ModelError('GSV Module Path requires an explicit unambiguous backplane or IPv4 Ethernet route')
        return MODULE_PATH, struct.pack('<H', len(module.route)) + module.route
    if attribute in MODULE_CONNECTION_ATTRIBUTES:
        return _module_connection_attribute(engine, module, attribute, executing=executing)
    value = _module_mode(engine, module)
    if value is None:
        raise ModelError('GSV Module Mode requires explicit boolean Inhibited and MajorFault settings')
    return 'INT', value


def matches_major_fault_record(op):
    return (len(op.args) == 4 and all(isinstance(arg, str) for arg in op.args)
            and op.args[0].casefold() == 'program' and op.args[2].casefold() == 'majorfaultrecord')


def _handler_fault(engine, instance, scope, *, executing):
    program_handler = engine.project.program_fault_routines.get(scope)
    if program_handler is not None:
        if instance.casefold() not in ('this', scope.casefold()):
            raise ModelError('MajorFaultRecord requires THIS or the current faulted Program')
        if not executing:
            return None
        current = engine._executing_routine
        if current is None or current.key.lower() != program_handler or engine._program_fault is None:
            raise ModelError('MajorFaultRecord requires an active Program fault in the assigned routine')
        return engine._program_fault

    routine = engine.project.routines.get(engine.project.fault_handler_routine)
    if (routine is None or scope != routine.program
            or instance.casefold() not in ('this', scope.casefold())):
        raise ModelError('MajorFaultRecord requires THIS or the current Controller Fault Handler Program')
    if not executing:
        return None
    fault = engine._program_fault if engine._program_fault is not None else engine.module_major_fault
    current = engine._executing_routine
    if current is None or current.key.lower() not in engine.project.fault_handler_routines or fault is None:
        raise ModelError('MajorFaultRecord requires an active simulated major fault in the handler')
    return fault


def _major_fault_record(engine, instance, scope, *, executing):
    fault = _handler_fault(engine, instance, scope, executing=executing)
    if fault is None:
        return MAJOR_FAULT_RECORD, None
    timestamp = fault['timestamp_us']
    time_words = (None, None) if timestamp is None else struct.unpack('<2i', struct.pack('<q', timestamp))
    type_code = 0 if engine._handler_clear_requested else (fault['code'] << 16) | fault['type']
    return MAJOR_FAULT_RECORD, (*time_words, type_code) + (None,) * 8


def _structured_fault_record(memory, key, parts):
    parent = parts[:-1]
    _, _, dtype = memory.resolve(memory.address(key, parent))
    definition = memory.project.udts.get(dtype.lower())
    if definition is None or definition.get('Class') != 'User':
        return None
    containers = definition.findall('Members')
    members = definition.findall('./Members/Member')
    names = [member.get('Name', '') for member in members]
    shape = tuple((member.get('DataType'), dimensions(member.get('Dimension', '0'))) for member in members)
    layout = FAULT_RECORD_LAYOUTS.get(shape)
    error = ('MajorFaultRecord UDT requires its first member, a LINT or two DINT timestamp words, '
             'followed by INT Type, INT Code and DINT[8] Info')
    if (layout is None or len(containers)!=1 or list(containers[0])!=members or names[0]!=parts[-1]
            or not all(names) or len({name.casefold() for name in names})!=len(names)
            or any(member.get('Hidden', 'false').casefold()!='false'
                   or 'Target' in member.attrib or 'BitNumber' in member.attrib for member in members)):
        raise ModelError(error)
    record = memory.at(key, parent)
    if (not isinstance(record, dict) or set(record)!=set(names)
            or any(isinstance(record[name], (dict, list)) for name in names[:-1])
            or not isinstance(record[names[-1]], list) or len(record[names[-1]])!=8
            or any(isinstance(item, (dict, list)) for item in record[names[-1]])):
        raise ModelError('MajorFaultRecord UDT storage does not match its declared layout')
    paths = [parent + [name] for name in names[:-1]]
    paths.extend(parent + [names[-1], index] for index in range(8))
    return key, paths, layout


def _major_fault_region(memory, ref, scope, *, writable=False):
    resolve = memory.check_writable if writable else memory.resolve
    key, parts, _ = resolve(ref, scope)
    if key is not None and parts and isinstance(parts[-1], str) and not isinstance(memory.at(key, parts), (dict, list)):
        record = _structured_fault_record(memory, key, parts)
        if record is not None:
            return record
    key, paths, kind = prefix(memory, ref, scope, MAJOR_FAULT_WORDS, writable=writable)
    if kind != 'DINT' or len(paths) != MAJOR_FAULT_WORDS:
        direction = 'writable' if writable else 'readable'
        raise ModelError(f'MajorFaultRecord requires 11 {direction} contiguous DINT elements or a supported UDT first member')
    return key, paths, kind


def write_major_fault_record(engine, op, scope, *, executing):
    _configuration_source(engine)
    _handler_fault(engine, op.args[1], scope, executing=executing)
    memory = engine.memory
    previous = memory.structural
    memory.structural = not executing
    try:
        key, paths, layout = _major_fault_region(memory, op.args[3], scope)
        if executing:
            start = 1 if layout == FAULT_RECORD_LINT else 2
            count = 1 if layout == 'DINT' else 2
            words = (memory.at(key, path) for path in paths[start:start+count])
            if any(type(word) is not int or word != 0 for word in words):
                raise ModelError('SSV MajorFaultRecord requires known zero Type and Code')
            engine._handler_clear_requested = True
    finally:
        memory.structural = previous


def source(engine, op, scope='', *, executing=False):
    if len(op.args)!=4 or any(not isinstance(a,str) for a in op.args):
        raise ModelError('GSV requires four neutral-text operands')
    project = _configuration_source(engine)
    configuration = project.task_configuration
    cls,instance,attribute,_=op.args;cls=cls.casefold();attribute=attribute.casefold()
    if cls == 'controllerdevice':
        return controller_device(engine, instance, attribute, executing=executing)
    if cls == 'module':
        if instance and scope in engine.memory.frames:
            raise ModelError('Named GSV Module requires a Program routine; AOI module references are unsupported')
        return module_attribute(engine, instance, attribute, executing=executing)
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
    if cls == 'program' and attribute == 'majorfaultrecord':
        return _major_fault_record(engine, instance, scope, executing=executing)
    if cls in ('program','routine') and attribute=='name':
        return 'STRING',component_name(engine,cls,instance,scope,executing=executing)
    if cls!='task':raise ModelError('GSV configuration supports Task/Controller settings, ControllerDevice identity, Module status and Program/Routine Name')
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


def matches_module_set(op):
    return len(op.args) == 4 and isinstance(op.args[0], str) and op.args[0].casefold() == 'module'


def validate_module_set(engine, op, scope):
    if any(not isinstance(arg, str) for arg in op.args) or op.args[2].casefold() != 'mode':
        raise ModelError('SSV Module supports Mode only')
    if engine.mode != 'project' or scope in engine.memory.frames:
        raise ModelError('SSV Module Mode requires a scheduled Program routine')
    source(engine, op, scope)
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        key, parts, dtype = memory.resolve(op.args[3], scope)
        if dtype != 'INT' or isinstance(memory.at(key, parts), (list, dict, bool)):
            raise ModelError('SSV Module Mode source requires an exact scalar INT tag')
    finally:
        memory.structural = previous


def execute_module_set(engine, op, scope):
    value = engine.memory.read(op.args[3], scope)
    if type(value) is not int or value & ~MODULE_MODE_MASK:
        raise ModelError('SSV Module Mode supports only bits 0 and 2 in a known INT')
    engine._module_modes[op.args[1].casefold()] = value


def destination(memory, ref, scope, dtype, value, *, allow_dint=False):
    if dtype == 'SINT[33]':
        key, parts, kind = prefix(memory, ref, scope, DEVICE_NAME_SIZE, writable=True)
        if kind != 'SINT' or len(parts) != DEVICE_NAME_SIZE:
            raise ModelError('GSV ControllerDevice DeviceName requires 33 writable contiguous SINT elements')
        return key, parts, kind
    if dtype == MAJOR_FAULT_RECORD:
        return _major_fault_region(memory, ref, scope, writable=True)
    if dtype == MODULE_PATH:
        key, parts, kind, region = location(memory, ref, scope, writable=True)
        size = len(value)
        error = f'GSV Module Path requires {size} writable contiguous SINT elements in a one-dimensional array'
        if kind != 'SINT' or region is None:
            raise ModelError(error)
        base, cells = region
        start = parts[-1] if parts != base else 0
        if len(cells) - start < size or isinstance(cells[0], list):
            raise ModelError(error)
        return key, [base + [i] for i in range(start, start + size)], kind
    if dtype=='STRING':
        string_operand(memory,ref,scope,destination=True)
        key,parts,kind=memory.resolve(ref,scope)
    else:
        key,parts,kind=memory.check_writable(ref,scope)
        target_types = ('INT', 'DINT') if allow_dint else (dtype,)
        error = ('GSV Module status requires a scalar INT or DINT tag' if allow_dint else
                 'GSV configuration destination must be an exact scalar '+dtype+' tag')
        if kind not in target_types or (parts and isinstance(parts[-1], tuple)):
            raise ModelError(error)
        value = memory.at(key,parts)
        if isinstance(value, (dict,list)) or (dtype != 'BOOL' and isinstance(value, bool)):
            raise ModelError(error)
    return key,[parts],kind


def validate(engine, op, scope):
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        dtype,value=source(engine,op,scope)
        return destination(memory,op.args[3],scope,dtype,value,allow_dint=dtype=='INT' and op.args[0].casefold()=='module')
    finally:memory.structural=previous


def _structured_fault_values(words, layout):
    low, high, packed, *info = words
    type_code = struct.unpack('<2h', struct.pack('<i', packed))
    if layout == FAULT_RECORD_LINT:
        timestamp = None if low is None else struct.unpack('<q', struct.pack('<2i', low, high))[0]
        return (timestamp, *type_code, *info)
    return (low, high, *type_code, *info)


def execute(engine, op, scope):
    dtype,value=source(engine,op,scope,executing=True);memory=engine.memory
    key,paths,kind=destination(memory,op.args[3],scope,dtype,value,allow_dint=dtype=='INT' and op.args[0].casefold()=='module')
    if dtype == MAJOR_FAULT_RECORD and kind != 'DINT':
        value = _structured_fault_values(value, kind)
    if dtype in ('SINT[33]', MODULE_PATH, MAJOR_FAULT_RECORD):
        for path, item in zip(paths, value, strict=True):
            memory.store(key, path, item)
    elif dtype=='STRING':memory.write_string(op.args[3],value,scope)
    elif kind != dtype:
        old = memory.at(key, paths[0])
        if type(old) is not int:
            raise ModelError('GSV Module status requires a known DINT to preserve its upper word')
        memory.store(key, paths[0], (old & ~0xFFFF) | (value & 0xFFFF))
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
                module=['ForceStatus','LEDStatus','Mode','EntryStatus','FaultCode','FaultInfo','Path'],
                module_path='Counted CIP route for a local slot, an explicit IPv4 device, or a slot under a qualified remote EN2T/EN2TR.',
                named_module_settings='Explicit local and qualified routed source settings with live Mode overrides. EntryStatus models Inhibited, Waiting, and explicit simulated Running or Faulted states.',
                module_mode_ssv={'source':'Exact scalar INT with bits 0 and 2 only',
                                 'visibility':'Immediate within an advance; rolled back on fault',
                                 'lifecycle':'Retained across Run entry and routine replacement; reset/reload restores source settings',
                                 'connection_model':False},
                module_connection_input='Explicit project-bound API state, applied between scans. Fault diagnostics reflect only an effective simulated connection.',
                module_status='INT or DINT low word; preserve a known DINT upper word.',
                module_led_status='Empty controller-only map or aggregate of a complete simulated module inventory.',
                module_force_status='Controller-only I/O map.',
                major_fault_record='Active ladder fault routine; DINT[11] or first member of a supported fault-record UDT.',
                controller_device=['DeviceName','ProductCode','ProductRev','Type','Vendor','Status'],
                controller_device_source='v35 5580 project processor and firmware revision, plus modeled controller mode at scan entry.',
                controller_device_status='Remote keyswitch; Program 0x3070, Run 0x3060, software fault 0x3450 at retry entry.',
                task_instance='Zero-based slot in the current emulator Task registry, independent of native CIP instance IDs.',
                component_names='Named Program or THIS and Program-scoped Routine or THIS in ordinary scheduled project logic.',
                destinations='Exact BOOL/SINT/INT/DINT scalars, LEN/DATA strings, or a 33-cell SINT window for DeviceName; Module status also accepts the low word of a DINT',
                times='Microseconds from exact milliseconds; no inferred defaults',
                state='Source configuration with live Task InhibitTask, Watchdog, Periodic Rate and Periodic/Event Priority in project mode',
                selection='Structural destination validation without saved dynamic indices; false/prescan skip outputs; full writes establish unknown cells',
                st_for_effects='Complete static destinations; aliases/AOI/changing selections conservatively cover enclosing arrays',
                native_runtime_equivalence=False, ssv=True,
                current_instance='Task, Program and Routine THIS in ordinary scheduled Continuous/Periodic/qualified Event Program routines. AOI/harness THIS unqualified.',
                remaining=['Empty instance, native instance IDs and AOI/harness THIS contexts','Continuous priority/rate and zero-watchdog defaults',
                           'Scan-time/interval/status/fault attributes','Other classes/attributes and broader SSV'])
