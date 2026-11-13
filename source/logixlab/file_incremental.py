"""Bounded INC iteration; hidden progress is simulator state, not a native bit."""
from . import control_operations as controls
from .model import ModelError


def identity(engine,ref,scope):
    key,parts,_=engine.memory.resolve(ref,scope)
    return key,tuple(parts)


def source_control(engine,key):
    name,parts=key
    saved=engine.project.initial[name]
    for part in parts:saved=saved[part]
    return saved


def completed_source(saved):
    return (saved['DN'] is True and saved['ER'] is False
            and all(type(saved[flag]) is bool for flag in controls.FLAGS)
            and type(saved['LEN']) is int and type(saved['POS']) is int
            and 0 <= saved['POS'] <= saved['LEN'])


def validate(engine,op,scope):
    saved=source_control(engine,identity(engine,op.args[0],scope))
    if completed_source(saved):return
    if (type(saved['POS']) is not int or saved['POS']!=0
            or any(saved[flag] is not False for flag in controls.FLAGS)):
        raise ModelError('INC requires an idle source CONTROL or a known completed one; saved hidden progress is unavailable')


def execute(engine,op,power,scope,obj,operation,*,search=False):
    if controls.flag(obj,'ER') or (search and controls.flag(obj,'IN')):return power
    key=identity(engine,op.args[0],scope)
    if controls.flag(obj,'DN'):
        if not power:
            obj.update(EN=False,DN=False,POS=0)
            engine._file_incremental.discard(key)
            engine._file_arithmetic_retry.discard(key)
        return power
    if key not in engine._file_incremental and key not in engine._file_arithmetic_retry and completed_source(source_control(engine,key)) and controls.integer(obj,'POS') != 0:
        raise ModelError('Imported completed INC requires completed false cleanup or RES before nonzero resume; saved hidden progress is unavailable')
    enabled=controls.flag(obj,'EN')
    if not power:
        obj['EN']=False
        return False
    length,position=controls.file_cursor(obj,op.name+' INC')
    if length>controls.MAX_ELEMENTS:raise ModelError(op.name+' INC exceeds the 4096-element software limit')
    if enabled:return True
    start=position+int(key in engine._file_incremental and key not in engine._file_arithmetic_retry)
    obj['EN']=True
    if search:obj['FD']=False
    if start>=length:
        obj['DN']=True
        return True
    obj['POS']=start
    engine.budget-=1
    if engine.budget<0:raise ModelError(op.name+' INC instruction budget exceeded')
    result=operation()
    engine._file_incremental.add(key)
    engine._file_arithmetic_retry.discard(key)
    if search and result:obj.update(FD=True,IN=True)
    if start==length-1:obj['DN']=True
    return True


def description():
    return dict(edge='One element per observed false-to-true EN transition; held true does not iterate',
                startup='Idle source CONTROL or known completed DN with ER clear, known flags and 0 <= POS <= LEN; no saved partial/hidden-state import',
                progress='Canonical CONTROL identity, including aliases/selected members; separate from public flags',
                lifecycle='False partial clears EN; false completed with no inhibit clears DN/POS/progress; RES clears progress',
                persistence='Transactional simulator state retained across Run entry and routine replacement; not serialized as native CONTROL bits',
                native_internal_state_parity=False)
