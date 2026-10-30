"""Bounded GSV audit values and explicit source-configuration reads."""
import struct
from .model import ModelError
from . import gsv_configuration


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
    if not legacy(op):return gsv_configuration.validate(engine,op,scope)
    source(engine,op)
    return destination(engine,op.args[3],scope)


def execute(engine,op,scope):
    # Resolve and validate the complete destination before the first write.
    # Indirect indices are re-evaluated each execution; scan rollback retains
    # the previous values if a later instruction fails.
    if not legacy(op):
        gsv_configuration.execute(engine,op,scope)
        return
    raw=source(engine,op)
    key,parts,dtype=destination(engine,op.args[3],scope)
    values=struct.unpack('<q' if dtype=='LINT' else '<ii',raw)
    for part,value in zip(parts,values,strict=True):engine.memory.store(key,part,value)


def description():
    return dict(legacy='Controller AuditValue/ChangesToDetect into LINT or two DINT elements',
                configuration=gsv_configuration.description(), ssv=False)
