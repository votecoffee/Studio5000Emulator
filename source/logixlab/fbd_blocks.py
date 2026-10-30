"""Qualified FBD block adapters sharing existing logical instruction models."""
from . import fbd_select,st_scale,st_signal
from .model import ModelError,Op

TYPES={**fbd_select.TYPES,'SCL':'SCALE',**st_signal.TYPES}
SCHEMAS={**fbd_select.SCHEMAS,'SCALE':st_scale.FIELDS,**st_signal.SCHEMAS}
ALIASES={
    'MULTIPLEXER':{'InstructFault':0,'SelectorInv':1},
    'SCALE':{'InstructFault':0,'InRawRangeInv':1},
    'HL_LIMIT':{'InstructFault':0,'LimitsInv':1,'SelectLimitInv':2}}
OUTPUTS={**fbd_select.OUTPUTS,
    'SCALE':('EnableOut','Out','MaxAlarm','MinAlarm','Status'),
    'HL_LIMIT':('EnableOut','Out','HighAlarm','LowAlarm','Status'),
    'SELECTABLE_NEGATE':('EnableOut','Out'),'SELECTED_SUMMER':('EnableOut','Out')}
OUTPUTS={kind:(*pins,*ALIASES.get(kind,{})) for kind,pins in OUTPUTS.items()}
PINS={kind:fields|dict.fromkeys(ALIASES.get(kind,{}),'BOOL') for kind,fields in SCHEMAS.items()}


def adapter(name):return st_scale if name=='SCL' else st_signal


def selector_description():return fbd_select.description()


def validate(engine,name,operand,scope):
    if name in fbd_select.TYPES:return fbd_select.validate(engine,name,operand,scope)
    obj=adapter(name).validate(engine,Op(name,[operand]),scope)
    key,parts,_=engine.memory.check_writable(operand,scope)
    return key,parts,obj


def prescan(engine,node,scope):
    if node['type'] in fbd_select.TYPES:fbd_select.prescan(engine,node,scope)
    else:adapter(node['type']).prescan(engine,Op(node['type'],[node['operand']]),scope)


def execute(engine,node,scope,*,wired_enable):
    name=node['type']
    if name in fbd_select.TYPES:
        fbd_select.execute(engine,node,scope,wired_enable=wired_enable);return
    _,_,obj=validate(engine,name,node['operand'],scope)
    enabled=obj['EnableIn'] if wired_enable else True
    if type(enabled) is not bool:raise ModelError(name+' EnableIn is unknown or not BOOL')
    if not enabled:
        obj.update(EnableIn=False,EnableOut=False);return
    # Reuse the numerical/status model; FBD enable gating belongs to this adapter.
    adapter(name).execute(engine,Op(name,[node['operand']]),scope)


def description():
    return dict(instructions=sorted(TYPES),records=SCHEMAS,outputs=OUTPUTS,
                status_aliases={kind:{name:'Status.'+str(bit) for name,bit in fields.items()} for kind,fields in ALIASES.items()},
                shared_models='SCL/HLL/SNEG/SSUM reuse the existing ST numerical and status profiles',
                enable='Connected EnableIn gates each block; disabled outputs/alarms/status retain; unwired enable is true',
                prescan='Clear enables only; do not copy wires or publish output references',
                unknowns='Unknown input values propagate on wires; required reads and published outputs must be known',
                native_runtime_parity=False,
                remaining=['Native first-scan/Run/postscan/disabled and simultaneous-condition qualification',
                           'Native precision/status/fault/packed-layout parity; general FBD instructions and graph forms'])
