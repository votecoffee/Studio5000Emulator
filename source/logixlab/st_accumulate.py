"""Finite REAL accumulation profiles; native lifecycle/rounding unqualified."""
from .integer_math import CONTROLLERS,bit_value
from .model import ModelError,coerce
from .real_math import real

TYPES={'UPDN':'UP_DOWN_ACCUM','INTG':'INTEGRATOR'}
INSTRUCTIONS=frozenset(TYPES)
SCHEMAS={
    'UP_DOWN_ACCUM':{'EnableIn':'BOOL','InPlus':'REAL','InMinus':'REAL','Initialize':'BOOL',
                     'InitialValue':'REAL','Hold':'BOOL','EnableOut':'BOOL','Out':'REAL'},
    'INTEGRATOR':{'EnableIn':'BOOL','In':'REAL','Initialize':'BOOL','InitialValue':'REAL','IGain':'REAL',
                  'HighLimit':'REAL','LowLimit':'REAL','HoldHigh':'BOOL','HoldLow':'BOOL',
                  'TimingMode':'DINT','OversampleDT':'REAL','RTSTime':'DINT','RTSTimeStamp':'DINT',
                  'EnableOut':'BOOL','Out':'REAL','HighAlarm':'BOOL','LowAlarm':'BOOL','DeltaT':'REAL','Status':'DINT'}}
STATUS_ALIASES={'InstructFault':0,'IGainInv':1,'HighLowLimsInv':2,'TimingModeInv':27,
                'RTSMissed':28,'RTSTimeInv':29,'RTSTimeStampInv':30,'DeltaTInv':31}
STATUS_BITS={name.lower():bit for name,bit in STATUS_ALIASES.items()}
MAX_DT=real(4194.303)
MAX_REAL=real(3.4028234663852886e38)


def default(dtype):
    value={name:(name=='EnableIn') if kind=='BOOL' else 0.0 if kind=='REAL' else int(name=='RTSTime')
           for name,kind in SCHEMAS[dtype].items()}
    if dtype=='INTEGRATOR':value.update(HighLimit=MAX_REAL,LowLimit=-MAX_REAL)
    return value


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
    key,parts,obj=validate(engine,op,scope);identity=('ST-ACCUMULATE',key,tuple(parts))
    state=engine.last_timer.get(identity);schema=SCHEMAS[TYPES[op.name]]
    def read(name):
        value=obj[name];kind=schema[name]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError(op.name+' '+name+' is unknown or has the wrong value type')
        return value if kind=='BOOL' else coerce(value,'DINT') if kind=='DINT' else real(value)
    previous=state['out'] if state else 0.0
    initialize=read('Initialize')
    if op.name=='UPDN':
        if initialize:out=read('InitialValue')
        elif read('Hold'):out=previous
        else:out=real(previous+read('InPlus')-read('InMinus'))
        engine.last_timer[identity]=dict(out=out)
    else:
        mode=read('TimingMode');now=engine.time_ms
        if mode==2:raise ModelError('INTG real time sampling mode remains unqualified')
        value,gain,high,low=read('In'),read('IGain'),read('HighLimit'),read('LowLimit')
        hold_high,hold_low=read('HoldHigh'),read('HoldLow')
        status=(3 if gain<0 else 0)|(5 if high<=low else 0);gain=max(0.0,gain)
        if mode==0:
            scheduler=engine._task_scheduler
            task=next((t for t in scheduler.tasks if t.name==engine._executing_task),None) if scheduler else None
            elapsed=now-state['at'] if state else 0
            if elapsed<0:raise ModelError('INTG simulation clock moved backwards')
            dt=real((task.period if task is not None and task.kind=='Periodic' else elapsed)/1000)
        elif mode==1:dt=read('OversampleDT')
        else:status|=(1<<27)|1;dt=0.0
        if not 0<=dt<=MAX_DT:status|=(1<<31)|1;dt=0.0
        prior_in=state['input'] if state else 0.0
        if initialize:out=read('InitialValue');prior_in=value
        elif high<=low:out=low
        elif status&2:out=previous
        else:
            out=previous
            # The software startup call establishes zero history; later valid
            # intervals apply the documented trapezoidal integral recurrence.
            if state is not None and dt>0:
                candidate=previous+gain*((value+prior_in)/2)*dt
                if not ((hold_high and candidate>previous) or (hold_low and candidate<previous)):out=candidate
                prior_in=value
            out=min(high,max(low,out))
        out=real(out)
        high_alarm,low_alarm=(True,True) if high<=low else (out>=high,out<=low)
        obj.update(IGain=gain,HighAlarm=high_alarm,LowAlarm=low_alarm,DeltaT=dt,Status=bit_value(status,'DINT'))
        engine.last_timer[identity]=dict(out=out,input=prior_in,at=now)
    obj.update(EnableIn=True,EnableOut=True,Out=out)


def description():
    return dict(profile='v35-5580-ST-accumulation',language='ST',instructions=sorted(INSTRUCTIONS),records=SCHEMAS,
                updn='Initialize overrides Hold; otherwise Out = previous accumulator + InPlus - InMinus; negative inputs allowed',
                intg='Out = previous Out + IGain * (In + previous In) / 2 * DeltaT, with directional holds and limits',
                timing='INTG mode 0: Periodic task period or elapsed whole simulated milliseconds; mode 1: explicit OversampleDT, zero holds',
                startup='UPDN zero accumulator then current inputs; INTG first reached call establishes zero output/input history unless Initialize',
                precedence='INTG Initialize, invalid limits, negative gain hold, then timed calculation; Initialize may exceed output limits',
                limits='Inclusive alarms; HighLimit <= LowLimit sets both alarms, Status.0/.2 and Out=LowLimit unless Initialize',
                history='Finite float32 output retained separately from visible Out; INTG input history advances on valid positive intervals, including directional holds',
                diagnostics='Negative IGain written zero with Status.0/.1; invalid mode/interval holds calculation with Status.0/.27 or .31; mode 2 faults',
                lifecycle='Prescan clears enables; Run resets histories; skipped calls retain; whole-advance rollback and detached replacement preserve state',
                arithmetic='Float32 public values and stored output/input history; host-double expression intermediates; nonfinite values fault transactionally',
                native_runtime_parity=False,
                remaining=['Native startup/input-history/Initialize/limit/hold/invalid-input precedence and rounding qualification',
                           'Module timestamps and RTS diagnostics','General FBD graph forms, packed layouts, other controller profiles and native nonfinite/status/fault parity'])
