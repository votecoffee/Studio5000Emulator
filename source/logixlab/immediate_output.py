"""Instruction-time samples from qualified local output tags."""
import copy
import re

from . import gsv_configuration
from .integer_math import CONTROLLERS
from .model import ModelError, dimensions

OUTPUT_NAME = re.compile(r'local:(0|[1-9][0-9]?):o', re.ASCII | re.I)
SCALARS = frozenset(('BOOL','SINT','INT','DINT','USINT','UINT','UDINT','REAL'))
MAX_CELLS = 64


def validate(engine, op, scope):
    project = engine.project
    if (engine.mode != 'project' or project.version != '35' or project.processor.upper() not in CONTROLLERS
            or scope in engine.memory.frames):
        raise ModelError('IOT requires a whole-project v35 ControlLogix 5580 ladder scan')
    ref = op.args[0]
    match = OUTPUT_NAME.fullmatch(ref)
    if not match:
        raise ModelError('IOT requires a whole Local:<slot>:O output tag')
    slot = int(match[1])
    module = next((entry for entry in project.io_map.module_settings if entry.route == bytes((1,slot))),None)
    if module is None or module.inhibited is None:
        raise ModelError('IOT output slot requires a qualified local module and explicit Inhibited setting')
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


def execute(engine, op, scope):
    key, tag, module = validate(engine,op,scope)
    status, _, _ = gsv_configuration._module_connection_state(engine,module,engine.project.io_map.named_module)
    if status != gsv_configuration.MODULE_RUNNING:
        return
    value = engine.memory.values[key]
    cells = value.values() if isinstance(value,dict) else value if isinstance(value,list) else (value,)
    if any(cell is None for cell in cells):
        raise ModelError('IOT output contains unknown data')
    pending = engine._immediate_output_advance
    previous = pending.get(key) or engine.immediate_outputs.get(key)
    sequence = previous['sequence'] + 1 if previous else 1
    pending[key] = dict(module=module.display_name or module.name,tag=tag.key,value=copy.deepcopy(value),
                        sequence=sequence,scan=engine.scan_count+1,simulation_ms=engine.time_ms)


def description():
    return dict(instruction='IOT',language='RLL',scope='v35 5580 whole-project local rack',
                connection='Requires an effective Running simulated module input',
                delivery='Latest instruction-time output per tag, published after scan commit',
                wire_packets=False,rpi_timing=False,native_runtime_parity=False)
