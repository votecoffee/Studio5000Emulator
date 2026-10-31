"""Bounded RLIM with simulated periodic/elapsed time and explicit oversampling."""
from .integer_math import CONTROLLERS,bit_value
from .model import ModelError,coerce
from .real_math import real

INSTRUCTIONS=frozenset(('RLIM',))
FIELDS={'EnableIn':'BOOL','In':'REAL','IncRate':'REAL','DecRate':'REAL','ByPass':'BOOL',
        'TimingMode':'DINT','OversampleDT':'REAL','RTSTime':'DINT','RTSTimeStamp':'DINT',
        'EnableOut':'BOOL','Out':'REAL','DeltaT':'REAL','Status':'DINT'}
STATUS_ALIASES={'InstructFault':0,'IncRateInv':1,'DecRateInv':2,'TimingModeInv':27,
                'RTSMissed':28,'RTSTimeInv':29,'RTSTimeStampInv':30,'DeltaTInv':31}
STATUS_BITS={name.lower():bit for name,bit in STATUS_ALIASES.items()}
MAX_DT=real(4194.303)


def default():
    return {name:(name=='EnableIn') if dtype=='BOOL' else 0.0 if dtype=='REAL' else int(name=='RTSTime')
            for name,dtype in FIELDS.items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('RLIM requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError('RLIM requires one RATE_LIMITER tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if dtype!='RATE_LIMITER' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError('RLIM requires one writable logical RATE_LIMITER record')
    if 'rate_limiter' in engine.project.udts:raise ModelError('Redefined RATE_LIMITER structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=('ST-RATE-LIMITER',key,tuple(parts))
    state=engine.last_timer.get(identity);now=engine.time_ms
    def read(name):
        value=obj[name];dtype=FIELDS[name]
        expected=(bool,) if dtype=='BOOL' else (int,) if dtype=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError('RLIM '+name+' is unknown or has the wrong value type')
        if dtype=='BOOL':return value
        if dtype=='DINT':return coerce(value,'DINT')
        try:return real(value)
        except ModelError as error:raise ModelError('RLIM '+name+' is outside the finite REAL profile') from error
    mode=read('TimingMode')
    if mode==2:raise ModelError('RLIM real time sampling mode remains unqualified')
    value,inc,dec,bypass=read('In'),read('IncRate'),read('DecRate'),read('ByPass')
    status=(3 if inc<0 else 0)|(5 if dec<0 else 0);inc=max(0.0,inc);dec=max(0.0,dec)
    if mode==0:
        scheduler=engine._task_scheduler
        task=next((t for t in scheduler.tasks if t.name==engine._executing_task),None) if scheduler is not None else None
        elapsed=now-state['at'] if state is not None else 0
        if elapsed<0:raise ModelError('RLIM simulation clock moved backwards')
        dt=real((task.period if task is not None and task.kind=='Periodic' else elapsed)/1000)
    elif mode==1:
        dt=read('OversampleDT')
        if not 0<dt<=MAX_DT:status|=(1<<31)|1;dt=0.0
    else:
        status|=(1<<27)|1;dt=0.0
    previous=state['previous'] if state is not None else value
    if bypass or state is None:result=value
    elif dt<=0:result=previous
    elif value>=previous:result=min(value,previous+inc*dt)
    else:result=max(value,previous-dec*dt)
    result=real(result)
    obj.update(EnableIn=True,EnableOut=True,IncRate=inc,DecRate=dec,Out=result,DeltaT=dt,Status=bit_value(status,'DINT'))
    engine.last_timer[identity]=dict(at=now,previous=result)


def description():
    return dict(profile='v35-5580-ST-RATE-LIMITER',language='ST',instructions=['RLIM'],record=dict(FIELDS),
                status_aliases={name:('Status.'+str(bit)) for name,bit in STATUS_ALIASES.items()},
                timing='Mode 0: configured period for Periodic tasks, otherwise elapsed simulated milliseconds between reached calls',
                oversampling='Mode 1: each call uses its explicit positive finite OversampleDT, at most float32(4194.303) seconds',
                initialization='First reached call and ByPass set Out and hidden previous output to In',
                calls='ST calls force EnableIn/EnableOut; skipped calls retain values; periodic/oversample repeats can advance at one timestamp',
                history='Hidden per-record previous output and clock; explicit Out writes do not replace this history',
                invalid_inputs='Negative rates written as zero with Status.0/.1/.2; invalid oversample holds with DeltaT=0 and Status.0/.31',
                invalid_mode='Values outside 0..2 hold with DeltaT=0 and Status.0/.27; mode 2 faults as unsupported',
                prescan='Clear enable pair; Run entry resets history, then first call initializes from In',
                rollback='Values and history commit with the whole advance; no native precision/status/fault/layout parity claim',
                native_runtime_parity=False,
                remaining=['Module timestamp/real time sampling mode and RTS status behavior','General FBD graph forms and other controller profiles',
                           'Native skipped-call, timing transitions, invalid-input, precision, overflow and lifecycle qualification'])
