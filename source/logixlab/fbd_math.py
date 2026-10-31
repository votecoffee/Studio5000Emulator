"""Finite REAL math Block forms; native faults, flags and layouts unqualified."""
from .integer_math import CONTROLLERS
from .model import ModelError
from .real_math import real

TYPES={**dict.fromkeys(('ADD','SUB','MUL','DIV'),'FBD_MATH'),
       **dict.fromkeys(('ABS','NEG'),'FBD_MATH_ADVANCED')}
SCHEMAS={
    'FBD_MATH':{'EnableIn':'BOOL','SourceA':'REAL','SourceB':'REAL','EnableOut':'BOOL','Dest':'REAL'},
    'FBD_MATH_ADVANCED':{'EnableIn':'BOOL','Source':'REAL','EnableOut':'BOOL','Dest':'REAL'}}
INSTRUCTIONS=frozenset(TYPES)


def default(dtype):
    # Declaration shape only; absent saved fields still import as unknown.
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
    # Installed v35 math Block tables specify N/A: retain enables and Dest.
    validate(engine,op,scope)


def execute(engine,op,scope):
    _,_,obj=validate(engine,op,scope)
    def read(name):
        value=obj[name]
        if type(value) not in (int,float):raise ModelError('FBD '+op.name+' '+name+' is unknown or not REAL')
        return real(value)
    if op.name in ('ABS','NEG'):
        value=read('Source');result=abs(value) if op.name=='ABS' else -value
    else:
        a,b=read('SourceA'),read('SourceB')
        if op.name=='DIV' and b==0:
            raise ModelError('FBD DIV zero-divisor minor-fault behavior remains outside the finite software profile')
        result=a+b if op.name=='ADD' else a-b if op.name=='SUB' else a*b if op.name=='MUL' else a/b
    obj.update(EnableIn=True,EnableOut=True,Dest=real(result))


def description():
    return dict(instructions=sorted(TYPES),records=SCHEMAS,language='FBD Block',
                arithmetic='Known finite float32 inputs/results; host-double operation then float32 result rounding',
                lifecycle='No hidden state; prescan leaves enables/Dest unchanged; disabled/skipped calls retain Dest',
                failures='Unknown/nonfinite/overflow and zero-divisor cases fail the whole advance transactionally',
                zero_divisor='Native DIV result/minor-fault handling remains unsupported; no numeric substitute is produced',
                native_runtime_parity=False,
                remaining=['Tagless Function forms, remaining math operations, wider operands and packed layouts',
                           'Native underflow/overflow/nonfinite/zero-divisor, math flags, fault and lifecycle qualification'])
