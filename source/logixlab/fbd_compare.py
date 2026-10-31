"""Finite REAL comparison/limit Block forms with BOOL results."""
import operator
from .integer_math import CONTROLLERS
from .model import ModelError
from .real_math import real

COMPARE={'EQU':operator.eq,'NEQ':operator.ne,'GRT':operator.gt,'GEQ':operator.ge,'LES':operator.lt,'LEQ':operator.le}
TYPES={**dict.fromkeys(COMPARE,'FBD_COMPARE'),'LIM':'FBD_LIMIT'}
SCHEMAS={
    'FBD_COMPARE':{'EnableIn':'BOOL','SourceA':'REAL','SourceB':'REAL','EnableOut':'BOOL','Dest':'BOOL'},
    'FBD_LIMIT':{'EnableIn':'BOOL','LowLimit':'REAL','Test':'REAL','HighLimit':'REAL','EnableOut':'BOOL','Dest':'BOOL'}}
INSTRUCTIONS=frozenset(TYPES)


def default(dtype):
    return {name:(name=='EnableIn') if kind=='BOOL' else 0.0 for name,kind in SCHEMAS[dtype].items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError(op.name+' requires the v35 ControlLogix 5580 software profile')
    dtype=TYPES[op.name]
    if len(op.args)!=1:raise ModelError('FBD '+op.name+' requires one '+dtype+' record')
    key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError('FBD '+op.name+' requires a writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    # Native v35 Block tables specify N/A; do not overwrite saved results/enables.
    validate(engine,op,scope)


def execute(engine,op,scope):
    _,_,obj=validate(engine,op,scope)
    def read(name):
        value=obj[name]
        if type(value) not in (int,float):raise ModelError('FBD '+op.name+' '+name+' is unknown or not REAL')
        return real(value)
    if op.name=='LIM':
        low,test,high=read('LowLimit'),read('Test'),read('HighLimit')
        result=low<=test<=high if low<=high else test>=low or test<=high
    else:result=COMPARE[op.name](read('SourceA'),read('SourceB'))
    obj.update(EnableIn=True,EnableOut=True,Dest=result)


def description():
    return dict(instructions=sorted(TYPES),records=SCHEMAS,language='FBD Block',
                comparison='Two known finite float32 inputs produce a BOOL result, with no tolerance comparison',
                limits='Inclusive low<=Test<=high; reversed limits accept Test>=low or Test<=high',
                lifecycle='No hidden state; prescan retains enables/Dest; disabled/skipped blocks retain Dest',
                failures='Unknown/nonfinite required inputs fail the whole advance; no fabricated FALSE or TRUE',
                native_runtime_parity=False,
                remaining=['NaN/infinity behavior, tagless Functions, strings, integer/wide operands and packed layouts',
                           'Native lifecycle/nonfinite/fault/transfer qualification and later-version mnemonic aliases'])
