"""Logical BOOL-only FBD blocks; native layouts and lifecycle unqualified."""
from .integer_math import CONTROLLERS
from .model import ModelError

TYPES={'BAND':'FBD_BOOLEAN_AND','BOR':'FBD_BOOLEAN_OR','BNOT':'FBD_BOOLEAN_NOT','BXOR':'FBD_BOOLEAN_XOR'}
INPUTS={'BAND':tuple('In'+str(i) for i in range(1,9)),
        'BOR':tuple('In'+str(i) for i in range(1,9)),'BNOT':('In',),'BXOR':('In1','In2')}
SCHEMAS={dtype:dict.fromkeys(('EnableIn',*INPUTS[name],'EnableOut','Out'),'BOOL') for name,dtype in TYPES.items()}
INSTRUCTIONS=frozenset(TYPES)


def default(dtype):
    name=next(name for name,kind in TYPES.items() if kind==dtype)
    # Declaration shapes only: omitted saved members remain unknown on import.
    values=dict.fromkeys(SCHEMAS[dtype],False);values['EnableIn']=name!='BOR'
    if name in ('BAND','BNOT'):
        for member in INPUTS[name]:values[member]=True
    return values


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError(op.name+' requires the v35 ControlLogix 5580 software profile')
    dtype=TYPES[op.name]
    if len(op.args)!=1:raise ModelError(op.name+' requires one '+dtype+' tag')
    key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError(op.name+' requires one writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    _,_,obj=validate(engine,op,scope);values=[]
    # Evaluate every declared input. Do not turn an unknown into a false value
    # through host-language Boolean coercion or short-circuit evaluation.
    for member in INPUTS[op.name]:
        value=obj[member]
        if type(value) is not bool:raise ModelError(op.name+' '+member+' is unknown or not BOOL')
        values.append(value)
    result=all(values) if op.name=='BAND' else any(values) if op.name=='BOR' else not values[0] if op.name=='BNOT' else values[0]!=values[1]
    obj.update(EnableIn=True,EnableOut=True,Out=result)


def description():
    return dict(instructions=sorted(TYPES),records=SCHEMAS,language='FBD Block',
                operands='BAND/BOR read eight BOOL members; BNOT reads In; BXOR reads In1/In2',
                unwired='Use current represented record values; removing a wire does not reset its member',
                unknowns='Every declared Boolean input must be known on an enabled call, without short-circuit inference',
                defaults='Declaration shapes follow installed v35 help; saved omissions are never replaced with shape values',
                lifecycle='Prescan clears enables only; disabled/skipped calls retain output; no hidden state',
                native_runtime_parity=False,
                remaining=['Tagless FBD Function forms and other controller profiles',
                           'Native initialization/postscan/disabled/layout/status/fault qualification'])
