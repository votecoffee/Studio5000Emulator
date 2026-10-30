"""Finite REAL piecewise curves and sample-based process transport delay."""
import math
import re
from .integer_math import CONTROLLERS,bit_value
from .model import ModelError,coerce
from .real_math import real

TYPES={'FGEN':'FUNCTION_GENERATOR','DEDT':'DEADTIME'}
INSTRUCTIONS=frozenset(TYPES)
SCHEMAS={
    'FUNCTION_GENERATOR':{'EnableIn':'BOOL','In':'REAL','XY1Size':'DINT','XY2Size':'DINT','Select':'BOOL',
                          'EnableOut':'BOOL','Out':'REAL','Status':'DINT'},
    'DEADTIME':{'EnableIn':'BOOL','In':'REAL','InFault':'BOOL','Deadtime':'REAL','Gain':'REAL','Bias':'REAL',
                'TimingMode':'DINT','OversampleDT':'REAL','RTSTime':'DINT','RTSTimeStamp':'DINT',
                'EnableOut':'BOOL','Out':'REAL','DeltaT':'REAL','Status':'DINT'}}
STATUS_ALIASES={
    'FUNCTION_GENERATOR':{'InstructFault':0,'XY1SizeInv':1,'XY2SizeInv':2,'XisOutofOrder':3},
    'DEADTIME':{'InstructFault':0,'InFaulted':1,'DeadtimeInv':2,'TimingModeInv':27,
                'RTSMissed':28,'RTSTimeInv':29,'RTSTimeStampInv':30,'DeltaTInv':31}}
STATUS_BITS={dtype:{name.lower():bit for name,bit in fields.items()} for dtype,fields in STATUS_ALIASES.items()}
MAX_SAMPLES=4096
MAX_DT=real(4194.303)


def default(dtype):
    return {name:(name=='EnableIn') if kind=='BOOL' else float(name=='Gain') if kind=='REAL'
            else int(name in ('XY1Size','RTSTime')) for name,kind in SCHEMAS[dtype].items()}


def array(memory,ref,scope,*,writable):
    if not re.fullmatch(r'[A-Za-z_][\w:]*(?:\.[A-Za-z_]\w*|\[\d+(?:,\d+)*\])*',ref):
        raise ModelError('Process curves require static whole REAL array references')
    key,parts,dtype=(memory.check_writable if writable else memory.resolve)(ref,scope)
    values=memory.at(key,parts)
    if dtype!='REAL' or not isinstance(values,list) or not 1<=len(values)<=MAX_SAMPLES or any(isinstance(v,(dict,list)) for v in values):
        raise ModelError('Process curves require one-dimensional REAL arrays of 1..4096 elements')
    return key,parts,values


def overlaps(a,b):return a[0]==b[0] and (a[1][:len(b[1])]==b[1] or b[1][:len(a[1])]==a[1])


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError(op.name+' requires the v35 ControlLogix 5580 software profile')
    if len(op.args) not in ((3,5) if op.name=='FGEN' else (2,)):
        raise ModelError('FGEN requires record/X1/Y1/optional X2/Y2; DEDT requires record/storage')
    dtype=TYPES[op.name];key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError(op.name+' requires one writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    arrays=[array(engine.memory,ref,scope,writable=op.name=='DEDT') for ref in op.args[1:]]
    if any(overlaps((key,parts),a) for a in arrays):raise ModelError('Process record and array operands must not overlap')
    return key,parts,obj,arrays


def prescan(engine,op,scope):
    _,_,obj,_=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def finite(value):
    if type(value) not in (int,float):raise ModelError('Process curve active array value is unknown or not REAL')
    return real(value)


def execute(engine,op,scope):
    key,parts,obj,arrays=validate(engine,op,scope);dtype=TYPES[op.name]
    def read(name):
        value=obj[name];kind=SCHEMAS[dtype][name]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError(op.name+' '+name+' is unknown or has the wrong value type')
        return value if kind=='BOOL' else coerce(value,'DINT') if kind=='DINT' else real(value)
    obj.update(EnableIn=True,EnableOut=True)
    if op.name=='FGEN':
        second=read('Select');count=read('XY2Size' if second else 'XY1Size');pair=arrays[2:] if second else arrays[:2]
        status=5 if second else 3
        if len(pair)!=2 or not 1<=count<=min(len(a[2]) for a in pair):obj['Status']=status;return
        engine.budget-=count
        if engine.budget<0:raise ModelError('FGEN point budget exceeded')
        x=[finite(v) for v in pair[0][2][:count]]
        if any(a>=b for a,b in zip(x,x[1:])):obj['Status']=9;return
        y=pair[1][2]
        if count==1:out=finite(y[0])
        else:
            value=read('In')
            if value<=x[0]:out=finite(y[0])
            elif value>=x[-1]:out=finite(y[count-1])
            else:
                index=next(i for i in range(1,count) if value<=x[i]);lo,hi=finite(y[index-1]),finite(y[index])
                out=real(lo+(hi-lo)*((value-x[index-1])/(x[index]-x[index-1])))
        obj.update(Out=out,Status=0);return
    identity=('ST-DEADTIME',key,tuple(parts));previous=engine.last_timer.get(identity)
    storage=arrays[0];binding=(storage[0],tuple(storage[1]));now=engine.time_ms
    if previous is not None and previous['binding']!=binding:raise ModelError('DEDT cannot change its storage binding during a Run')
    if any(k!=identity and isinstance(k,tuple) and k[0]=='ST-DEADTIME' and overlaps(binding,v['binding']) for k,v in engine.last_timer.items()):
        raise ModelError('DEDT records cannot share overlapping storage during a Run')
    state=dict(binding=binding,at=now,length=None,faulted=False) if previous is None else dict(previous)
    mode,fault,delay=read('TimingMode'),read('InFault'),read('Deadtime')
    if mode==2:raise ModelError('DEDT real time sampling mode remains unqualified')
    status=3 if fault else 0
    if mode==0:
        scheduler=engine._task_scheduler
        task=next((t for t in scheduler.tasks if t.name==engine._executing_task),None) if scheduler else None
        elapsed=now-state['at']
        if elapsed<0:raise ModelError('DEDT simulation clock moved backwards')
        dt=real((task.period if task is not None and task.kind=='Periodic' else elapsed)/1000)
    elif mode==1:dt=read('OversampleDT')
    else:status|=(1<<27)|1;dt=0.0
    if not 0<=dt<=MAX_DT:status|=(1<<31)|1;dt=0.0
    invalid=delay<0 or dt>0 and delay>len(storage[2])*dt
    if invalid:status|=5
    value=None if fault else real(read('In')*read('Gain')+read('Bias'))
    state['at']=now
    if fault:state['faulted']=True
    elif previous is not None and dt>0:
        count=0 if invalid else int(math.floor(delay/dt+0.5))
        engine.budget-=count
        if engine.budget<0:raise ModelError('DEDT sample budget exceeded')
        if count:
            if state['faulted']:values=[value]*count
            elif state['length'] is None:values=[finite(v) for v in storage[2][:count]]
            else:
                keep=min(count,state['length']);values=[finite(v) for v in storage[2][:keep]]
                values.extend([values[-1] if values else value]*(count-keep))
            obj['Out']=values[-1];storage[2][:count]=[value]+values[:-1]
        else:obj['Out']=value
        state.update(length=count,faulted=False)
    obj.update(DeltaT=dt,Status=bit_value(status,'DINT'));engine.last_timer[identity]=state


def description():
    return dict(profile='v35-5580-ST-curves-delay',language='ST',instructions=sorted(INSTRUCTIONS),records=SCHEMAS,
                status_aliases={dtype:{name:'Status.'+str(bit) for name,bit in fields.items()} for dtype,fields in STATUS_ALIASES.items()},
                arrays='Static 1D REAL arrays of 1..4096 elements; FGEN tables read-only, DEDT storage writable; active prefixes only',
                fgen='3 or 5 operands; selected table only, strictly increasing active X, linear interpolation, endpoint clamp and single-point constant',
                fgen_diagnostics='Invalid selected size/missing second pair or unordered X holds visible Out with status; inactive table values/count ignored',
                dedt='First reached call validates without moving output/buffer; positive intervals shift scaled In*Gain+Bias through rounded sample delay',
                delay_rounding='Nearest interval, halves upward; invalid delay uses zero with Status.0/.2; request retained',
                resize='Grow active delay with oldest retained sample; shrink discards oldest samples; grow from zero uses current scaled input',
                health='Bad health holds visible Out/buffer; recovery seeds active buffer from current scaled input, deferred through disabled timing',
                timing='DEDT mode 0 Periodic configured period or elapsed whole milliseconds; mode 1 explicit OversampleDT; zero holds; RTS mode 2 faults',
                storage='Initial active delay uses saved array values; per-record binding fixed during Run; overlapping DEDT storage rejected',
                lifecycle='Run clears delay history; prescan clears enables; skipped calls retain; values/storage/history/scheduler roll back together',
                native_runtime_parity=False,
                remaining=['Native selected-table diagnostics/read/precision and deadtime startup/resize/recovery/timing/status qualification',
                           'RTS/module timestamps, FBD graphs, packed layouts, other profiles and complete native nonfinite/fault/lifecycle parity'])
