"""Bounded ST MAVE/MSTD over finite REAL queues and logical records."""
import math
import re

from .integer_math import CONTROLLERS
from .model import ModelError,coerce
from .real_math import real

TYPES={'MAVE':'MOVING_AVERAGE','MSTD':'MOVING_STD_DEV'}
INSTRUCTIONS=frozenset(TYPES)
COMMON={'EnableIn':'BOOL','In':'REAL','InFault':'BOOL','Initialize':'BOOL',
        'SampleEnable':'BOOL','NumberOfSamples':'DINT','EnableOut':'BOOL','Out':'REAL','Status':'DINT'}
SCHEMAS={'MOVING_AVERAGE':COMMON|{'UseWeights':'BOOL'},'MOVING_STD_DEV':COMMON|{'Average':'REAL'}}
STATUS_ALIASES={'InstructFault':0,'InFaulted':1,'NumberOfSampInv':2}
STATUS_BITS={name.lower():bit for name,bit in STATUS_ALIASES.items()}
MAX_SAMPLES=4096


def default(dtype):
    return {name:(name=='EnableIn' or name=='SampleEnable' and dtype=='MOVING_AVERAGE') if kind=='BOOL'
            else 0.0 if kind=='REAL' else int(name=='NumberOfSamples') for name,kind in SCHEMAS[dtype].items()}


def array(memory,ref,scope,*,writable):
    if not re.fullmatch(r'[A-Za-z_][\w:]*(?:\.[A-Za-z_]\w*|\[\d+(?:,\d+)*\])*',ref):
        raise ModelError('Moving statistics require static whole REAL array references')
    key,parts,dtype=(memory.check_writable if writable else memory.resolve)(ref,scope)
    values=memory.at(key,parts)
    if dtype!='REAL' or not isinstance(values,list) or not 1<=len(values)<=MAX_SAMPLES or any(isinstance(v,(dict,list)) for v in values):
        raise ModelError('Moving statistics require a one-dimensional REAL array of 1..4096 elements')
    return key,parts,values


def overlap(a,b):
    return a[0]==b[0] and (a[1][:len(b[1])]==b[1] or b[1][:len(a[1])]==a[1])


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('Moving statistics require the v35 ControlLogix 5580 software profile')
    if len(op.args) not in ((2,3) if op.name=='MAVE' else (2,)):
        raise ModelError('MAVE requires record/storage/optional weights; MSTD requires record/storage')
    dtype=TYPES[op.name];key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError(op.name+' requires a writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    storage=array(engine.memory,op.args[1],scope,writable=True)
    weight=array(engine.memory,op.args[2],scope,writable=False) if len(op.args)==3 else None
    if overlap((key,parts),storage) or weight is not None and (overlap((key,parts),weight) or overlap(storage,weight)):
        raise ModelError('Moving-statistics record, storage and weight arrays must not overlap')
    return key,parts,obj,storage,weight


def prescan(engine,op,scope):
    _,_,obj,_,_=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj,storage,weight=validate(engine,op,scope);dtype=TYPES[op.name]
    identity=('ST-MOVING',key,tuple(parts));previous=engine.last_timer.get(identity)
    binding=(op.name,storage[0],tuple(storage[1]))
    if previous is not None and previous['binding']!=binding:
        raise ModelError('Moving-statistics record cannot change its storage binding during a Run')
    state={'binding':binding,'count':0} if previous is None else previous
    def read(name):
        value=obj[name];kind=SCHEMAS[dtype][name]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError(op.name+' '+name+' is unknown or has the wrong value type')
        return value if kind=='BOOL' else coerce(value,'DINT') if kind=='DINT' else real(value)
    fault,initialize,sample,length=read('InFault'),read('Initialize'),read('SampleEnable'),read('NumberOfSamples')
    weighted=read('UseWeights') if op.name=='MAVE' else False
    capacity=min(len(storage[2]),len(weight[2])) if weighted and weight is not None else len(storage[2])
    invalid=not 1<=length<=capacity
    obj.update(EnableIn=True,EnableOut=True,Status=(3 if fault else 0)|(5 if invalid else 0))
    engine.last_timer[identity]=state
    if fault or invalid:
        state['count']=0
        return
    if initialize:
        value=read('In');obj['Out']=value if op.name=='MAVE' else 0.0
        if op.name=='MSTD':obj['Average']=value
        state['count']=0
        return
    if previous is None:
        obj['Out']=0.0
        if op.name=='MSTD':obj['Average']=read('In')
    state['count']=min(state['count'],length)
    if not sample:return
    if weighted and weight is None:raise ModelError('MAVE weighted sampling requires a weight array')
    count=min(state['count']+1,length)
    engine.budget-=count
    if engine.budget<0:raise ModelError('Moving-statistics element budget exceeded')
    values=[read('In')]
    for item in storage[2][:count-1]:
        if type(item) not in (int,float):raise ModelError('Moving-statistics active sample is unknown or not REAL')
        values.append(real(item))
    total=0.0
    for i,value in enumerate(values):
        if weighted:
            w=weight[2][i]
            if type(w) not in (int,float):raise ModelError('MAVE active weight is unknown or not REAL')
            value=real(value*real(w))
        total=real(total+value)
    mean=real(total if weighted else total/count)
    result=mean
    if op.name=='MSTD':
        variance=0.0
        for value in values:
            delta=real(value-mean);variance=real(variance+real(delta*delta))
        result=real(math.sqrt(real(variance/count)));obj['Average']=mean
    obj['Out']=result
    # Only the active prefix changes. Unknown or saved unused tail values survive.
    storage[2][:count]=values;state['count']=count


def description():
    return dict(profile='v35-5580-ST-moving-statistics',language='ST',instructions=sorted(INSTRUCTIONS),
                records=SCHEMAS,status_aliases={n:'Status.'+str(b) for n,b in STATUS_ALIASES.items()},max_samples=MAX_SAMPLES,
                storage='Writable one-dimensional REAL queue; newest at index zero; only active prefix read/written',
                calculation='Float32 operands/intermediates/results; MAVE direct weighted sum or uniform mean; MSTD population deviation',
                initialization='First call starts empty; Initialize/InFault/invalid length discard active count, retaining unused storage',
                sampling='SampleEnable adds one sample per reached call; skipped calls retain state; no elapsed-time sampling',
                sizes='Runtime growth fills incrementally; shrink truncates active prefix; SampleEnable false holds outputs',
                lifecycle='Run resets per-record count; history and storage share scan rollback and detached routine replacement',
                native_runtime_parity=False,
                remaining=['FBD graphs, packed layouts and other controller profiles','Native queue order, resize/hold, first-scan and shared-storage semantics',
                           'Native precision, overflow/nonfinite/status/minor-fault and postscan parity','Changing a record storage binding within a Run'])
