"""Logical FBD selectors; native execution-order and lifecycle parity unqualified."""
from .integer_math import CONTROLLERS
from .model import ModelError,coerce
from .real_math import real

TYPES={'SEL':'SELECT','MUX':'MULTIPLEXER'}
SCHEMAS={
    'SELECT':{'EnableIn':'BOOL','In1':'REAL','In2':'REAL','SelectorIn':'BOOL','EnableOut':'BOOL','Out':'REAL'},
    'MULTIPLEXER':{'EnableIn':'BOOL',**{'In'+str(i):'REAL' for i in range(1,9)},
                   'Selector':'DINT','EnableOut':'BOOL','Out':'REAL','Status':'DINT'}}
OUTPUTS={'SELECT':('EnableOut','Out'),'MULTIPLEXER':('EnableOut','Out','Status')}
STATUS_BITS={'instructfault':0,'selectorinv':1}


def default(dtype):
    return {name:(name=='EnableIn') if kind=='BOOL' else 0.0 if kind=='REAL' else 0
            for name,kind in SCHEMAS[dtype].items()}


def validate(engine,name,operand,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('FBD selectors require the v35 ControlLogix 5580 software profile')
    dtype=TYPES[name];key,parts,actual=engine.memory.check_writable(operand,scope)
    obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError(name+' requires one writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    return key,parts,obj


def prescan(engine,node,scope):
    _,_,obj=validate(engine,node['type'],node['operand'],scope)
    obj.update(EnableIn=False,EnableOut=False)


def execute(engine,node,scope,*,wired_enable):
    name=node['type'];dtype=TYPES[name];key,parts,obj=validate(engine,name,node['operand'],scope)
    identity=('FBD-SELECTOR',key,tuple(parts));previous=engine.last_timer.get(identity,0.0)
    def read(member):
        value=obj[member];kind=SCHEMAS[dtype][member]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError(name+' '+member+' is unknown or has the wrong value type')
        return value if kind=='BOOL' else coerce(value,'DINT') if kind=='DINT' else real(value)
    enabled=read('EnableIn') if wired_enable else True
    obj.update(EnableIn=enabled,EnableOut=enabled)
    if not enabled:return
    if name=='SEL':out=read('In2' if read('SelectorIn') else 'In1')
    else:
        selector=read('Selector');valid=1<=selector<=8
        out=read('In'+str(selector)) if valid else previous
        obj['Status']=0 if valid else 3
    obj['Out']=out;engine.last_timer[identity]=out


def description():
    return dict(instructions=sorted(TYPES),records=SCHEMAS,language='FBD',
                select='SelectorIn false selects In1; true selects In2',
                multiplexer='Selector 1..8 selects In1..In8; invalid selector sets Status 3 and holds internal output',
                enable='Connected EnableIn controls execution; an unwired enable is true; disabled outputs/status retain',
                startup='First enabled invalid MUX selector returns zero; later invalid selectors use last enabled output',
                unknowns='Only consumed selector, enable and selected analog values must be known; unselected values may remain unknown',
                lifecycle='Prescan clears enables; Run clears retained output; skip retains; whole-advance rollback and detached replacement preserve history',
                native_runtime_parity=False,
                remaining=['Other FBD instructions/functions, native simultaneous-condition and startup/output-write qualification',
                           'Full FBD scheduling, feedback/connectors, packed layouts, nonfinite/status/fault parity and other controller profiles'])
