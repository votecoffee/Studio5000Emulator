"""Finite REAL maximum/minimum capture with transactional retained extrema."""
from .integer_math import CONTROLLERS
from .model import ModelError
from .real_math import real

TYPES={'MAXC':'MAXIMUM_CAPTURE','MINC':'MINIMUM_CAPTURE'}
INSTRUCTIONS=frozenset(TYPES)
FIELDS={'EnableIn':'BOOL','In':'REAL','Reset':'BOOL','ResetValue':'REAL','EnableOut':'BOOL','Out':'REAL'}


def default():
    return {name:(name=='EnableIn') if kind=='BOOL' else 0.0 for name,kind in FIELDS.items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError(op.name+' requires the v35 ControlLogix 5580 software profile')
    dtype=TYPES[op.name]
    if len(op.args)!=1:raise ModelError(op.name+' requires one '+dtype+' tag')
    key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError(op.name+' requires one writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=('ST-CAPTURE',key,tuple(parts))
    reset=obj['Reset']
    if type(reset) is not bool:raise ModelError(op.name+' Reset is unknown or not BOOL')
    name='ResetValue' if reset else 'In';value=obj[name]
    if type(value) not in (int,float):raise ModelError(op.name+' '+name+' is unknown or not REAL')
    value=real(value);previous=engine.last_timer.get(identity)
    if reset or previous is None:result=value
    elif (value>previous if op.name=='MAXC' else value<previous):result=value
    else:result=previous
    obj.update(EnableIn=True,EnableOut=True,Out=result)
    engine.last_timer[identity]=result


def description():
    return dict(profile='v35-5580-ST-capture',language='ST',instructions=sorted(INSTRUCTIONS),
                records={dtype:dict(FIELDS) for dtype in TYPES.values()},
                sampling='Each reached ST call forces enable bits and compares its finite REAL input; skipped calls retain values',
                initialization='First non-reset call seeds the retained extremum from In; Reset takes priority and seeds ResetValue',
                reset='While Reset is true, each call copies ResetValue and replaces the retained baseline',
                history='Per resolved record, separate from Out; explicit Out writes do not replace the extremum',
                ties='Strict comparison preserves the previous value, including its signed zero',
                lifecycle='Prescan clears enable bits; Run entry resets history; supported detached routine replacement preserves it',
                failures='Unknown required inputs, nonfinite/overflow or a later fault roll back outputs, history and the whole advance',
                native_runtime_parity=False,
                remaining=['General FBD graph forms, packed layouts and other controller profiles','Native initialization/reset priority, skipped-call and postscan behavior',
                           'Native nonfinite, precision, signed-zero, status and fault parity'])
