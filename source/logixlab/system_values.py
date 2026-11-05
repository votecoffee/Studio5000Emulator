"""Bounded GSV audit values and explicit source-configuration reads."""
import struct
from .model import ModelError
from . import event_status, gsv_configuration, gsv_timing, gsv_wall_clock, program_control, task_inhibit


def source(engine,op):
    if (len(op.args)!=4 or any(not isinstance(a,str) for a in op.args)
            or op.args[0].casefold()!='controller' or op.args[1]!=''):
        raise ModelError('GSV supports Controller with an empty instance operand')
    attribute=op.args[2].casefold()
    if attribute=='auditvalue':
        raw=engine.change_detection.attributes(engine.project.sha256).get(27)
    elif attribute=='changestodetect':
        raw=engine.project.controller_configuration.attributes().get(28)
    else:raise ModelError('GSV supports Controller AuditValue and ChangesToDetect only')
    if raw is None:raise ModelError('GSV Controller change-detection value is unavailable')
    return raw


def destination(engine,ref,scope):
    memory=engine.memory
    key,parts,dtype=memory.check_writable(ref,scope)
    if dtype=='LINT' and type(memory.at(key,parts)) is int:
        return key,[parts],'LINT'
    if dtype=='DINT':
        key,parts,dtype=memory.region(ref,2,scope)
        return key,parts,dtype
    raise ModelError('GSV destination requires a LINT scalar or two contiguous DINT elements')


def legacy(op):
    return (len(op.args)==4 and all(isinstance(a,str) for a in op.args)
            and op.args[0].casefold()=='controller'
            and op.args[2].casefold() in ('auditvalue','changestodetect'))


def validate(engine,op,scope):
    if program_control.matches(op):return program_control.validate(engine,op,scope)
    if event_status.matches(op):return event_status.validate(engine,op,scope)
    if gsv_timing.matches(op):return gsv_timing.validate(engine,op,scope)
    if gsv_wall_clock.matches(op):return gsv_wall_clock.validate(engine,op,scope)
    if not legacy(op):return gsv_configuration.validate(engine,op,scope)
    source(engine,op)
    return destination(engine,op.args[3],scope)


def execute(engine,op,scope):
    if program_control.matches(op):return program_control.execute(engine,op,scope)
    if event_status.matches(op):
        event_status.execute(engine,op,True,scope);return
    # Resolve and validate the complete destination before the first write.
    # Indirect indices are re-evaluated each execution; scan rollback retains
    # the previous values if a later instruction fails.
    if gsv_timing.matches(op):
        gsv_timing.execute(engine,op,scope)
        return
    if gsv_wall_clock.matches(op):
        gsv_wall_clock.execute(engine,op,scope)
        return
    if not legacy(op):
        gsv_configuration.execute(engine,op,scope)
        return
    raw=source(engine,op)
    key,parts,dtype=destination(engine,op.args[3],scope)
    values=struct.unpack('<q' if dtype=='LINT' else '<ii',raw)
    for part,value in zip(parts,values,strict=True):engine.memory.store(key,part,value)


def write_effects(engine,op,scope):
    if program_control.matches(op):return program_control.write_effects(engine,op,scope)
    if event_status.matches(op):return event_status.write_effects(engine,op,scope)
    if gsv_timing.matches(op):return gsv_timing.write_effects(engine,op,scope)
    if gsv_wall_clock.matches(op):return gsv_wall_clock.write_effects(engine,op,scope)
    if not legacy(op):return gsv_configuration.write_effects(engine,op,scope)
    key,parts,_=validate(engine,op,scope)
    return [(key,part) for part in parts]


def validate_set(engine, op, scope):
    if program_control.matches(op):return program_control.validate(engine,op,scope)
    if gsv_timing.matches(op):return gsv_timing.validate_reset(engine,op,scope)
    if event_status.matches(op):return event_status.validate(engine,op,scope)
    return task_inhibit.validate(engine,op,scope)


def execute_set(engine, op, power, scope):
    if not power:return power
    if program_control.matches(op):
        program_control.execute(engine,op,scope)
        return power
    if gsv_timing.matches(op):
        gsv_timing.execute_reset(engine,op,scope)
        return power
    if event_status.matches(op):return event_status.execute(engine,op,power,scope)
    return task_inhibit.execute(engine,op,power,scope)


def description():
    return dict(legacy='Controller AuditValue/ChangesToDetect into LINT or two DINT elements',
                configuration=gsv_configuration.description(), wall_clock=gsv_wall_clock.description(),
                timing=gsv_timing.description(), event_status=event_status.description(),
                ssv=True, task_inhibition=task_inhibit.description(), task_rate=task_inhibit.rate_description(),
                task_priority=task_inhibit.priority_description(),
                task_watchdog=task_inhibit.watchdog_description())
