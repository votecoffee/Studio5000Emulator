"""Qualified FBD block adapters sharing existing logical instruction models."""
from . import fbd_select,st_scale,st_signal,st_timers,st_counter,st_oneshot,st_digital,fbd_boolean,st_rate,st_capture,st_accumulate,st_select,st_derivative,fbd_math,fbd_compare
from .model import ModelError,Op

TYPES={**fbd_select.TYPES,'SCL':'SCALE',**st_signal.TYPES,
       **dict.fromkeys(st_timers.INSTRUCTIONS,'FBD_TIMER'),'CTUD':'FBD_COUNTER',
       **dict.fromkeys(st_oneshot.INSTRUCTIONS,'FBD_ONESHOT'),**st_digital.TYPES,**fbd_boolean.TYPES,
       'RLIM':'RATE_LIMITER',**st_capture.TYPES,**st_accumulate.TYPES,
       'ESEL':'SELECT_ENHANCED','DERV':'DERIVATIVE',**fbd_math.TYPES,**fbd_compare.TYPES}
SCHEMAS={**fbd_select.SCHEMAS,'SCALE':st_scale.FIELDS,**st_signal.SCHEMAS,
         'FBD_TIMER':st_timers.FIELDS,'FBD_COUNTER':st_counter.FIELDS,'FBD_ONESHOT':st_oneshot.FIELDS,**st_digital.SCHEMAS,**fbd_boolean.SCHEMAS,
         'RATE_LIMITER':st_rate.FIELDS,**dict.fromkeys(st_capture.TYPES.values(),st_capture.FIELDS),
         **st_accumulate.SCHEMAS,'SELECT_ENHANCED':st_select.FIELDS,'DERIVATIVE':st_derivative.FIELDS,**fbd_math.SCHEMAS,**fbd_compare.SCHEMAS}
ALIASES={
    'SELECT_ENHANCED':st_select.STATUS_ALIASES,'DERIVATIVE':st_derivative.STATUS_ALIASES,
    'INTEGRATOR':st_accumulate.STATUS_ALIASES,
    'RATE_LIMITER':st_rate.STATUS_ALIASES,
    'FBD_TIMER':{'InstructFault':0,'PresetInv':1},
    'MULTIPLEXER':{'InstructFault':0,'SelectorInv':1},
    'SCALE':{'InstructFault':0,'InRawRangeInv':1},
    'HL_LIMIT':{'InstructFault':0,'LimitsInv':1,'SelectLimitInv':2}}
OUTPUTS={**fbd_select.OUTPUTS,**dict.fromkeys(fbd_compare.SCHEMAS,('EnableOut','Dest')),**dict.fromkeys(fbd_math.SCHEMAS,('EnableOut','Dest')),
    'SELECT_ENHANCED':('EnableOut','Out','SelectedIn','ProgOper','Override','Status'),
    'DERIVATIVE':('EnableOut','Out','DeltaT','Status'),
    'UP_DOWN_ACCUM':('EnableOut','Out'),
    'INTEGRATOR':('EnableOut','Out','HighAlarm','LowAlarm','DeltaT','Status'),
    'RATE_LIMITER':('EnableOut','Out','DeltaT','Status'),
    **dict.fromkeys(st_capture.TYPES.values(),('EnableOut','Out')),
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
          **dict.fromkeys(st_digital.INSTRUCTIONS,st_digital),**dict.fromkeys(fbd_boolean.INSTRUCTIONS,fbd_boolean),
          'RLIM':st_rate,**dict.fromkeys(st_capture.INSTRUCTIONS,st_capture),
          **dict.fromkeys(st_accumulate.INSTRUCTIONS,st_accumulate),'ESEL':st_select,'DERV':st_derivative,**dict.fromkeys(fbd_math.INSTRUCTIONS,fbd_math),**dict.fromkeys(fbd_compare.INSTRUCTIONS,fbd_compare)}


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
                shared_models='Signal blocks, timers, counters, one-shots, digital memory, rate limiting, captures, accumulation, enhanced selection and derivatives share existing ST profiles',
                enable='Connected EnableIn gates each block; disabled outputs/alarms/status retain; unwired enable is true',
                prescan='Math/comparison blocks retain enables/Dest; other qualified blocks clear enables; do not copy wires or publish references',
                unknowns='Unknown input values propagate on wires; required reads and published outputs must be known',
                timing='Disabled FBD calls retain timer history; re-enabled active timers include elapsed simulated time since the last reached enabled call',
                timer_control='TimerEnable is separate from EnableIn: a reached false TimerEnable resets TONR or pauses RTOR; disabled EnableIn skips the algorithm',
                state='Counter and one-shot edges sample enabled reached calls only; ST/FBD sites share resolved-record history',
                rate_capture='RLIM shares timing and previous-output history; MAXC/MINC share retained extrema and level-sensitive reset baselines',
                accumulation='UPDN shares its per-call total; INTG shares trapezoidal integral, input sample and timing history with ST',
                process='ESEL shares Program/Operator arbitration; DERV shares reached input, output and simulated clock history with ST',
                requests='Wired request inputs are reapplied before every reached block; internal request resets do not clear their source tags',
                comparison=fbd_compare.description(),
                math=fbd_math.description(),
                boolean=fbd_boolean.description(),
                digital='DFF/JKFF/RESD/SETD share the existing sampled clock and dominant-latch history model',
                native_runtime_parity=False,
                remaining=['Native first-scan/Run/postscan/disabled and simultaneous-condition qualification',
                           'Native precision/status/fault/packed-layout parity; general FBD instructions and graph forms'])
