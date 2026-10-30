"""Bounded INC iteration; hidden progress is simulator state, not a native bit."""
from . import control_operations as controls
from .model import ModelError


def identity(engine,ref,scope):
    key,parts,_=engine.memory.resolve(ref,scope)
    return key,tuple(parts)


def validate(engine,op,scope):
    key,parts=identity(engine,op.args[0],scope)
    saved=engine.project.initial[key]
    for part in parts:saved=saved[part]
    if (type(saved['POS']) is not int or saved['POS']!=0
            or any(saved[flag] is not False for flag in controls.FLAGS)):
        raise ModelError('INC requires an idle source CONTROL: POS zero and all flags false; saved hidden progress is unavailable')


def reset(engine,ref,scope):
    engine._file_incremental.discard(identity(engine,ref,scope))


def execute(engine,op,power,scope,operation,*,search=False):
    obj=controls.control(engine.memory,op.args[0],scope)
    if controls.flag(obj,'ER') or (search and controls.flag(obj,'IN')):return power
    key=identity(engine,op.args[0],scope)
    if controls.flag(obj,'DN'):
        if not power:
            obj.update(EN=False,DN=False,POS=0)
            reset(engine,op.args[0],scope)
        return power
    enabled=controls.flag(obj,'EN')
    if not power:
        obj['EN']=False
        return False
    length,position=controls.integer(obj,'LEN'),controls.integer(obj,'POS')
    if length<0 or position<0 or position>length:
        raise ModelError(op.name+' INC requires nonnegative LEN/POS with POS no greater than LEN')
    if length>controls.MAX_ELEMENTS:raise ModelError(op.name+' INC exceeds the 4096-element software limit')
    if enabled:return True
    start=position+int(key in engine._file_incremental)
    obj['EN']=True
    if search:obj['FD']=False
    if start>=length:
        obj['DN']=True
        return True
    obj['POS']=start
    engine._file_incremental.add(key)
    engine.budget-=1
    if engine.budget<0:raise ModelError(op.name+' INC instruction budget exceeded')
    result=operation()
    if search and result:obj.update(FD=True,IN=True)
    if start==length-1:obj['DN']=True
    return True


def description():
    return dict(edge='One element per observed false-to-true EN transition; held true does not iterate',
                startup='Idle source CONTROL only: POS zero and all public flags false; no saved hidden-state import',
                progress='Canonical CONTROL identity, including aliases/selected members; separate from public flags',
                lifecycle='False partial clears EN; false completed with no inhibit clears DN/POS/progress; RES clears progress',
                persistence='Transactional simulator state retained across Run entry and routine replacement; not serialized as native CONTROL bits',
                native_internal_state_parity=False)
