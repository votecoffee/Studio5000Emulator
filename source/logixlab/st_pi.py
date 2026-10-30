"""Bounded PI regulator; native coefficients, rounding and lifecycle unqualified."""
import math
from .integer_math import CONTROLLERS,bit_value
from .model import ModelError,coerce
from .real_math import real

INSTRUCTIONS=frozenset(('PI',))
FIELDS={'EnableIn':'BOOL','In':'REAL','Initialize':'BOOL','InitialValue':'REAL','Kp':'REAL','Wld':'REAL',
        'HighLimit':'REAL','LowLimit':'REAL','HoldHigh':'BOOL','HoldLow':'BOOL',
        'ShapeKpPlus':'REAL','ShapeKpMinus':'REAL','KpInRange':'REAL',
        'ShapeWldPlus':'REAL','ShapeWldMinus':'REAL','WldInRange':'REAL',
        'NonLinearMode':'BOOL','ParabolicLinear':'BOOL','TimingMode':'DINT','OversampleDT':'REAL',
        'RTSTime':'DINT','RTSTimeStamp':'DINT','EnableOut':'BOOL','Out':'REAL',
        'HighAlarm':'BOOL','LowAlarm':'BOOL','DeltaT':'REAL','Status':'DINT'}
STATUS_ALIASES={'InstructFault':0,'KpInv':1,'WldInv':2,'HighLowLimsInv':3,
                'ShapeKpPlusInv':4,'ShapeKpMinusInv':5,'KpInRangeInv':6,
                'ShapeWldPlusInv':7,'ShapeWldMinusInv':8,'WldInRangeInv':9,
                'TimingModeInv':27,'RTSMissed':28,'RTSTimeInv':29,'RTSTimeStampInv':30,'DeltaTInv':31}
STATUS_BITS={name.lower():bit for name,bit in STATUS_ALIASES.items()}
MIN_GAIN=real(2**-126)
MAX_REAL=real(3.4028234663852886e38)
MAX_DT=real(4194.303)


def default():
    obj={name:(name=='EnableIn') if kind=='BOOL' else 0.0 if kind=='REAL' else int(name=='RTSTime')
         for name,kind in FIELDS.items()}
    obj.update(Kp=MIN_GAIN,HighLimit=MAX_REAL,LowLimit=-MAX_REAL,KpInRange=MAX_REAL,WldInRange=MAX_REAL,
               ShapeKpPlus=1.0,ShapeKpMinus=1.0,ShapeWldPlus=1.0,ShapeWldMinus=1.0)
    return obj


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('PI requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError('PI requires one PROP_INT tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if dtype!='PROP_INT' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError('PI requires one writable logical PROP_INT record')
    if 'prop_int' in engine.project.udts:raise ModelError('Redefined PROP_INT structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=('ST-PI',key,tuple(parts))
    state=engine.last_timer.get(identity);now=engine.time_ms;status=0
    def read(name):
        value=obj[name];kind=FIELDS[name]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError('PI '+name+' is unknown or has the wrong value type')
        return value if kind=='BOOL' else coerce(value,'DINT') if kind=='DINT' else real(value)
    def bounded(name,low,high,bit):
        nonlocal status
        value=read(name)
        if not low<=value<=high:status|=1|(1<<bit)
        return min(high,max(low,value))
    mode=read('TimingMode')
    if mode==2:raise ModelError('PI real time sampling mode remains unqualified')
    if mode==0:
        scheduler=engine._task_scheduler
        task=next((t for t in scheduler.tasks if t.name==engine._executing_task),None) if scheduler else None
        elapsed=now-state['at'] if state else 0
        if elapsed<0:raise ModelError('PI simulation clock moved backwards')
        dt=real((task.period if task is not None and task.kind=='Periodic' else elapsed)/1000)
    elif mode==1:dt=read('OversampleDT')
    else:status|=(1<<27)|1;dt=0.0
    if not 0<=dt<=MAX_DT:status|=(1<<31)|1;dt=0.0
    value,initialize,high,low=read('In'),read('Initialize'),read('HighLimit'),read('LowLimit')
    hold_high,hold_low,nonlinear=read('HoldHigh'),read('HoldLow'),read('NonLinearMode')
    kp=bounded('Kp',MIN_GAIN,MAX_REAL,1);upper=0.7*math.pi/dt if dt>0 else MAX_REAL
    frequency=bounded('Wld',MIN_GAIN,upper,2);pterm=kp*value;sample=value
    if nonlinear:
        parabolic=read('ParabolicLinear')
        plus=bounded('ShapeKpPlus',0.1,10,4);minus=bounded('ShapeKpMinus',0.1,10,5)
        prange=bounded('KpInRange',MIN_GAIN,MAX_REAL,6)
        wplus=bounded('ShapeWldPlus',0,10,7);wminus=bounded('ShapeWldMinus',0,10,8)
        wrange=bounded('WldInRange',MIN_GAIN,MAX_REAL,9)
        shape=plus if value>=0 else minus;ratio=min(1,abs(value)/prange)
        # Use the displayed v35 shaping constants and outside-range P extension.
        kp*=1+(shape-1)*(ratio*ratio*0.333 if parabolic else ratio*0.5)
        signed_range=prange if value>=0 else -prange
        pterm=kp*value if abs(value)<=prange else kp*signed_range+(value-signed_range)*shape
        sample=min(wrange,max(-wrange,value));wshape=wplus if value>=0 else wminus
        ratio=min(1,abs(value)/wrange);frequency*=1+(wshape-1)*(ratio*ratio if parabolic else ratio)
        if not MIN_GAIN<=frequency<=upper:status|=5;frequency=min(upper,max(MIN_GAIN,frequency))
    old_i=state['integral'] if state else 0.0;old_sample=state['input'] if state else 0.0
    clamp=lambda v:min(high,max(low,v))
    if high<=low:
        status|=9;out=integral=low;old_sample=0.0;alarms=(True,True)
    elif initialize:
        out=integral=clamp(read('InitialValue'));old_sample=sample;alarms=(out>=high,out<=low)
    elif state is None:
        out=integral=clamp(0.0);alarms=(out>=high,out<=low)
    elif dt==0:
        out=clamp(state['out']);integral=clamp(old_i);alarms=(out>=high,out<=low)
    else:
        proposed=old_i+kp*frequency*((sample+old_sample)/2)*dt
        if (hold_high and proposed>old_i) or (hold_low and proposed<old_i):proposed=old_i
        integral=clamp(proposed);raw=pterm+integral;alarms=(raw>=high,raw<=low);out=clamp(raw)
        if any(alarms):integral=clamp(old_i)
        old_sample=sample
    out,integral=real(out),real(integral)
    obj.update(EnableIn=True,EnableOut=True,Out=out,HighAlarm=alarms[0],LowAlarm=alarms[1],DeltaT=dt,Status=bit_value(status,'DINT'))
    engine.last_timer[identity]=dict(at=now,input=old_sample,integral=integral,out=out)


def description():
    return dict(profile='v35-5580-ST-PI-software',language='ST',instructions=['PI'],record=dict(FIELDS),
                status_aliases={name:'Status.'+str(bit) for name,bit in STATUS_ALIASES.items()},
                linear='PTerm=Kp*In; ITerm=previous ITerm+Kp*Wld*(In+previous In)/2*DeltaT; Out=PTerm+ITerm',
                shaping='Linear or parabolic error-based shaping; displayed factors 0.5/0.333 for P and ratio/ratio squared for I',
                extension='Outside proportional range uses shaped Kp*signed range + (In-signed range)*selected ShapeKp, following displayed v35 equation',
                limits='Directional holds affect I only; clamp I/Out; inclusive output saturation discards proposed I; invalid limits force LowLimit and both alarms',
                initialize='Clamp InitialValue into limits and assign Out/I; captures current integral input; invalid limits take precedence',
                timing='Mode 0: Periodic configured period or elapsed whole simulated milliseconds; mode 1 explicit OversampleDT; mode 2 faults',
                parameters='Effective gains/ranges bounded internally; requests retained; minimum positive gain/range is float32 minimum normal',
                lifecycle='First reached call establishes zero I/input/output unless Initialize; prescan clears enables; Run resets; rollback/replacement preserve history',
                arithmetic='Float32 public values and stored history; host-double intermediate coefficients/products; nonlinear display-equation choices not native qualified',
                native_runtime_parity=False,
                remaining=['Native discrete coefficients, shaping constants/extension, gain thresholds, rounding and interacting-condition qualification',
                           'RTS/module timestamps, FBD graphs, packed layouts, other profiles and full native status/fault/lifecycle parity',
                           'Separate PID/PIDE execution families'])
