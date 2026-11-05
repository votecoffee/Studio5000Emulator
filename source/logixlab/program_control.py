"""Program DisableFlag instructions for an ordinary scheduled Program."""
from dataclasses import dataclass

from .gsv_configuration import current_instance
from .integer_math import CONTROLLERS
from .model import ModelError, operations
from .numeric_copy import static_reference
from .program_configuration import ATTRIBUTE


@dataclass
class Advance:
    """Program flags and first-scan history staged for one advance."""

    disabled: set[str]
    scanned: set[str]
    pending_prescan: set[str]

    def set_disabled(self, name, value):
        if value:
            self.disabled.add(name)
        elif name in self.disabled:
            self.disabled.remove(name)
            self.scanned.discard(name)


def matches(op):
    return (len(op.args) >= 3
            and all(isinstance(value, str) for value in op.args[:3])
            and op.args[0].casefold() == 'program'
            and op.args[2].casefold() == 'disableflag')


def source_flag(project, name):
    program = project.programs.get(name)
    if (not program or program['class'] != 'Standard' or program['use_as_folder']
            or not program['main'] or f"{name}/{program['main']}".lower() not in project.routines):
        return None
    disabled = project.program_configuration.execution_disabled(name, source_sha256=project.sha256)
    return disabled if disabled is program['disabled'] else None


def activation_routines(project):
    """Collect dormant Programs referenced by named writes in the runnable graph."""
    if project.version != '35' or project.processor.upper() not in CONTROLLERS:
        return {}
    scheduled = {name for task in project.tasks for name in task['programs'] if name in project.programs}
    dormant = {name.casefold(): name for name in scheduled
               if project.programs[name]['disabled'] and source_flag(project, name) is True}
    if not dormant:
        return {}
    routines = {}
    for key, routine in project.routines.items():
        if routine.program in scheduled:
            routines.setdefault(routine.program, []).append(key)
    pending = [name for name in scheduled if not project.programs[name]['disabled']]
    result = {}
    while pending:
        for key in routines.get(pending.pop(), ()):
            for rung in project.routines[key].rungs:
                for op in operations(rung['nodes']):
                    if op.name != 'SSV' or len(op.args) != 4 or not matches(op):
                        continue
                    target = op.args[1].casefold()
                    if target != 'this' and target in dormant and target not in result:
                        name = dormant[target]
                        result[target] = tuple(sorted(routines[name]))
                        pending.append(name)
    return result


def target(engine, op, scope, *, executing=False):
    if len(op.args) != 4 or any(not isinstance(value, str) for value in op.args):
        raise ModelError('Program DisableFlag requires four neutral-text operands')
    caller = current_instance(engine, 'Program', 'THIS', scope, executing=executing, allow_event=True)
    instance = op.args[1]
    key = (caller if instance.casefold() == 'this' else instance).casefold()
    project = engine.project
    name = next((name for name in project.programs if name.casefold() == key), None)
    disabled = source_flag(project, name)
    if disabled is not None:
        entry = f"{name}/{project.programs[name]['main']}".lower()
        if entry in engine.entries:
            return key, disabled
        if op.name == 'GSV' and disabled and any(name in task['programs'] for task in project.tasks):
            return key, True
    raise ModelError('Program DisableFlag requires a scheduled ordinary Standard Program with a main routine and a canonical or omitted Disabled flag')


def operand(memory, op, scope):
    reading = op.name == 'GSV'
    resolve = memory.check_writable if reading else memory.resolve
    key, parts, dtype = resolve(op.args[3], scope)
    kinds = ('SINT', 'DINT') if reading else ('SINT',)
    if dtype not in kinds or isinstance(memory.at(key, parts), (dict, list)):
        raise ModelError('GSV Program DisableFlag requires one scalar SINT or DINT destination' if reading
                         else 'SSV Program DisableFlag requires one scalar SINT source')
    return key, parts


def validate(engine, op, scope):
    target(engine, op, scope)
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        return operand(memory, op, scope)
    finally:
        memory.structural = previous


def execute(engine, op, scope):
    name, source_disabled = target(engine, op, scope, executing=True)
    memory = engine.memory
    key, parts = operand(memory, op, scope)
    advance = engine._program_advance
    if advance is None:
        raise ModelError('Program DisableFlag requires an active advance')
    if op.name == 'GSV':
        inactive_source = source_disabled and name not in engine._program_activation
        memory.store(key, parts, int(inactive_source or name in advance.disabled))
        return
    value = memory.at(key, parts)
    if type(value) is not int:
        raise ModelError('SSV Program DisableFlag requires a known SINT')
    advance.set_disabled(name, value != 0)


def write_effects(engine, op, scope):
    key, parts = validate(engine, op, scope)
    if static_reference(engine.memory, op.args[3], scope):
        return [(key, parts)]
    boundary = next((i for i, part in enumerate(parts) if isinstance(part, int)), len(parts))
    return [(key, parts[:boundary])]


def attributes(engine, name, *, source_sha256):
    """Expose the committed override on the existing read-only Program byte."""
    values = engine.project.program_configuration.attributes(name, source_sha256=source_sha256)
    if not engine.blockers and ATTRIBUTE in values:
        key = name.casefold()
        if key in engine._program_activation or (values[ATTRIBUTE] == b'\0' and key in engine._disabled_programs):
            values[ATTRIBUTE] = bytes((int(key in engine._disabled_programs),))
    return values


def description(engine):
    return dict(
        disabled_programs=[name for name in engine.project.programs if name.casefold() in engine._disabled_programs],
        activatable_imported_programs=[name for name in engine.project.programs if name.casefold() in engine._program_activation],
        languages=['RLL', 'ST'],
        source='Scheduled ordinary Standard Program with a main. An omitted Disabled flag starts enabled in the emulator. Named SSV plans imported-disabled targets.',
        activation='Imported-disabled Programs remain dormant until enabled. Prescan precedes their first permitted execution in the Run cycle.',
        operand='SSV SINT: zero enables, nonzero disables. GSV SINT/DINT returns 0 or 1.',
        effect='Active invocation completes. Later entries check the live flag. Re-enable marks the next invocation first-scan.',
        lifecycle='Run entry and detached routine replacement retain the flag. Reset and reload restore source.',
        native_attribute=ATTRIBUTE, native_attribute_requires_explicit_source=True,
        native_writes=False, native_runtime_parity=False,
    )
