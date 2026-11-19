"""Instruction-time and task-end samples from qualified simulated outputs."""
import copy
import re

from . import gsv_configuration
from .integer_math import CONTROLLERS
from .model import ModelError, dimensions

OUTPUT_NAME = re.compile(r'([a-z_][a-z0-9_]{0,39})(?::(0|[1-9][0-9]?))?:o', re.ASCII | re.I)
SCALARS = frozenset(('BOOL','SINT','INT','DINT','USINT','UINT','UDINT','REAL'))
MAX_CELLS = 64


def output_module(io_map, ref):
    match = OUTPUT_NAME.fullmatch(ref)
    if match is None:
        return None
    name, slot = match.groups()
    if slot is not None and name.casefold() == 'local':
        parent, route = None, bytes((1, int(slot)))
    else:
        module = io_map.named_module(name)
        if module is None or not module.ethernet_addressed or module.route is None:
            return None
        if slot is None:
            return module
        parent, route = module.name, module.route + bytes((1, int(slot)))
    return next((entry for entry in io_map.module_settings
                 if entry.route == route and entry.routed_parent == parent), None)


def validate(engine, op, scope):
    project = engine.project
    if (engine.mode != 'project' or project.version != '35' or project.processor.upper() not in CONTROLLERS
            or scope in engine.memory.frames):
        raise ModelError('IOT requires a whole-project v35 ControlLogix 5580 ladder scan')
    return bind(engine, op.args[0], scope)


def bind(engine, ref, scope=''):
    project = engine.project
    module = output_module(project.io_map, ref)
    if module is None or module.inhibited is None:
        raise ModelError('IOT requires a whole output tag for a qualified local slot, named IPv4 module or remote rack slot with explicit Inhibited setting')
    memory = engine.memory
    key, _, dtype = memory.resolve(ref,scope)
    tag = project.tags[key]
    if key != ref.casefold() or tag.scope or tag.alias or tag.constant or tag.tag_class != 'Standard':
        raise ModelError('IOT requires a directly represented Standard controller output tag')
    value = memory.values[key]
    if dtype in SCALARS and not isinstance(value,dict):
        if not isinstance(value,list) or (0 < len(value) <= MAX_CELLS and not any(
                isinstance(cell,(list,dict)) for cell in value)):
            return key, tag, module
    definition = project.udts.get(dtype.casefold())
    if isinstance(value,dict) and definition is not None and definition.get('Class') == 'User':
        members = definition.findall('./Members/Member')
        if (0 < len(members) <= MAX_CELLS and len(members) == len(value)
                and all(member.get('DataType') in SCALARS and not dimensions(member.get('Dimension','0'))
                        and member.get('Hidden','false').casefold() == 'false'
                        and 'Target' not in member.attrib and 'BitNumber' not in member.attrib
                        for member in members)):
            return key, tag, module
    raise ModelError('IOT requires a supported scalar, flat array or flat user record of at most 64 cells')


def capture(engine, binding, pending, committed, *, task=None):
    key, tag, module = binding
    status, _, _ = gsv_configuration._module_connection_state(engine,module,engine.project.io_map.named_module)
    if status != gsv_configuration.MODULE_RUNNING:
        return
    value = engine.memory.values[key]
    cells = value.values() if isinstance(value,dict) else value if isinstance(value,list) else (value,)
    if any(cell is None for cell in cells):
        if task is None:
            raise ModelError('IOT output contains unknown data')
        return
    previous = pending.get(key) or committed.get(key)
    sequence = previous['sequence'] + 1 if previous else 1
    pending[key] = dict(module=module.display_name or module.name,tag=tag.key,value=copy.deepcopy(value),
                        sequence=sequence,scan=engine.scan_count+1,simulation_ms=engine.time_ms)
    if task is not None:
        pending[key]['task'] = task


def execute(engine, op, scope):
    capture(engine, validate(engine, op, scope), engine._immediate_output_advance, engine.immediate_outputs)


def task_plan(engine):
    project = engine.project
    scheduler = engine._task_scheduler
    if (engine.blockers or scheduler is None or not project.io_map.module_settings
            or project.version != '35' or project.processor.upper() not in CONTROLLERS):
        return {}, ()
    # Task attribute 18 is the imported DINT DisableUpdateOutputs setting.
    tasks = {}
    for task in scheduler.tasks:
        raw = project.task_configuration.attributes(task.name, source_sha256=project.sha256).get(18)
        if raw is not None:
            tasks[task.name] = raw != bytes(4)
    targets = []
    if tasks:
        for tag in project.tags.values():
            if tag.scope or not tag.key.lower().endswith(':o'):
                continue
            try:
                targets.append(bind(engine, tag.key))
            except ModelError:
                continue  # Unsupported tags do not block ordinary task execution.
    return tasks if targets else {}, tuple(targets)


def description():
    return dict(instruction='IOT',language='RLL',scope='v35 5580 whole-project local slots, named IPv4 modules and qualified remote rack slots',
                connection='Requires an effective Running simulated module input',
                delivery='Latest instruction-time output per tag, published after scan commit',
                task_outputs='Latest task-end images for qualified running modules when the effective DisableUpdateOutputs flag is zero; unknown images are skipped',
                wire_packets=False,rpi_timing=False,native_runtime_parity=False)
