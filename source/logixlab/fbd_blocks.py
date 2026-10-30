"""Qualified FBD block adapters sharing existing logical instruction models."""
from . import fbd_select,st_scale,st_signal,st_timers,st_counter,st_oneshot,st_digital,fbd_boolean
from .model import ModelError,Op

TYPES={**fbd_select.TYPES,'SCL':'SCALE',**st_signal.TYPES,
       **dict.fromkeys(st_timers.INSTRUCTIONS,'FBD_TIMER'),'CTUD':'FBD_COUNTER',
       **dict.fromkeys(st_oneshot.INSTRUCTIONS,'FBD_ONESHOT'),**st_digital.TYPES,**fbd_boolean.TYPES}
SCHEMAS={**fbd_select.SCHEMAS,'SCALE':st_scale.FIELDS,**st_signal.SCHEMAS,
         'FBD_TIMER':st_timers.FIELDS,'FBD_COUNTER':st_counter.FIELDS,'FBD_ONESHOT':st_oneshot.FIELDS,**st_digital.SCHEMAS,**fbd_boolean.SCHEMAS}
ALIASES={
    'FBD_TIMER':{'InstructFault':0,'PresetInv':1},
    'MULTIPLEXER':{'InstructFault':0,'SelectorInv':1},
    'SCALE':{'InstructFault':0,'InRawRangeInv':1},
    'HL_LIMIT':{'InstructFault':0,'LimitsInv':1,'SelectLimitInv':2}}
OUTPUTS={**fbd_select.OUTPUTS,
    'SCALE':('EnableOut','Out','MaxAlarm','MinAlarm','Status'),
    'HL_LIMIT':('EnableOut','Out','HighAlarm','LowAlarm','Status'),
    'SELECTABLE_NEGATE':('EnableOut','Out'),'SELECTED_SUMMER':('EnableOut','Out'),
    'FBD_TIMER':('EnableOut','ACC','EN','TT','DN','Status'),
    'FBD_COUNTER':('EnableOut','ACC','CU','CD','DN','OV','UN'),
    'FBD_ONESHOT':('EnableOut','OutputBit'),
    'FLIP_FLOP_D':('EnableOut','Q','QNot'),'FLIP_FLOP_JK':('EnableOut','Q','QNot'),
    'DOMINANT_RESET':('EnableOut','Out','OutNot'),'DOMINANT_SET':('EnableOut','Out','OutNot'),
    **dict.fromkeys(fbd_boolean.SCHEMAS,('EnableOut','Out'))}
OUTPUTS={kind:(*pins,*ALIASES.get(kind,{})) for kind,pins in OUTPUTS.items()}
PINS={kind:fields|dict.fromkeys(ALIASES.get(kind,{}),'BOOL') for kind,fields in SCHEMAS.items()}


ADAPTERS={'SCL':st_scale,**dict.fromkeys(st_signal.INSTRUCTIONS,st_signal),
          **dict.fromkeys(st_timers.INSTRUCTIONS,st_timers),'CTUD':st_counter,
          **dict.fromkeys(st_oneshot.INSTRUCTIONS,st_oneshot),
          **dict.fromkeys(st_digital.INSTRUCTIONS,st_digital),**dict.fromkeys(fbd_boolean.INSTRUCTIONS,fbd_boolean)}


def adapter(name):return ADAPTERS[name]


def selector_description():return fbd_select.description()


def validate(engine,name,operand,scope):
    if name in fbd_select.TYPES:return fbd_select.validate(engine,name,operand,scope)
    adapter(name).validate(engine,Op(name,[operand]),scope)
    key,parts,_=engine.memory.check_writable(operand,scope)
    return key,parts,engine.memory.at(key,parts)


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
                shared_models='Signal blocks, timers, CTUD and one-shots reuse existing ST numerical/state/status profiles',
                enable='Connected EnableIn gates each block; disabled outputs/alarms/status retain; unwired enable is true',
                prescan='Clear enables only; do not copy wires or publish output references',
                unknowns='Unknown input values propagate on wires; required reads and published outputs must be known',
                timing='Disabled FBD calls retain timer history; re-enabled active timers include elapsed simulated time since the last reached enabled call',
                timer_control='TimerEnable is separate from EnableIn: a reached false TimerEnable resets TONR or pauses RTOR; disabled EnableIn skips the algorithm',
                state='Counter and one-shot edges sample enabled reached calls only; ST/FBD sites share resolved-record history',
                boolean=fbd_boolean.description(),
                digital='DFF/JKFF/RESD/SETD share the existing sampled clock and dominant-latch history model',
                native_runtime_parity=False,
                remaining=['Native first-scan/Run/postscan/disabled and simultaneous-condition qualification',
                           'Native precision/status/fault/packed-layout parity; general FBD instructions and graph forms'])
