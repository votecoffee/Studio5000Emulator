"""Finite REAL rate of change with simulated time and transactional history."""
from .integer_math import CONTROLLERS,bit_value
from .model import ModelError,coerce
from .real_math import real

INSTRUCTIONS=frozenset(('DERV',))
FIELDS={'EnableIn':'BOOL','In':'REAL','Gain':'REAL','ByPass':'BOOL','TimingMode':'DINT',
        'OversampleDT':'REAL','RTSTime':'DINT','RTSTimeStamp':'DINT',
        'EnableOut':'BOOL','Out':'REAL','DeltaT':'REAL','Status':'DINT'}
STATUS_ALIASES={'InstructFault':0,'TimingModeInv':27,'RTSMissed':28,'RTSTimeInv':29,'RTSTimeStampInv':30,'DeltaTInv':31}
STATUS_BITS={name.lower():bit for name,bit in STATUS_ALIASES.items()}
MAX_DT=real(4194.303)


def default():
    return {name:(name=='EnableIn') if kind=='BOOL' else float(name=='Gain') if kind=='REAL'
            else int(name=='RTSTime') for name,kind in FIELDS.items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('DERV requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError('DERV requires one DERIVATIVE tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if dtype!='DERIVATIVE' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError('DERV requires one writable logical DERIVATIVE record')
    if 'derivative' in engine.project.udts:raise ModelError('Redefined DERIVATIVE structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=('ST-DERIVATIVE',key,tuple(parts))
    state=engine.last_timer.get(identity);now=engine.time_ms
    def read(name):
        value=obj[name];kind=FIELDS[name]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError('DERV '+name+' is unknown or has the wrong value type')
        return value if kind=='BOOL' else coerce(value,'DINT') if kind=='DINT' else real(value)
    mode=read('TimingMode')
    if mode==2:raise ModelError('DERV real time sampling mode remains unqualified')
    value,bypass=read('In'),read('ByPass');status=0
    if mode==0:
        scheduler=engine._task_scheduler
        task=next((t for t in scheduler.tasks if t.name==engine._executing_task),None) if scheduler else None
        elapsed=now-state['at'] if state else 0
        if elapsed<0:raise ModelError('DERV simulation clock moved backwards')
        dt=real((task.period if task is not None and task.kind=='Periodic' else elapsed)/1000)
    elif mode==1:dt=read('OversampleDT')
    else:status|=(1<<27)|1;dt=0.0
    if not 0<=dt<=MAX_DT:status|=(1<<31)|1;dt=0.0
    if bypass:out=value
    elif state is None:out=0.0
    elif dt>0:out=real(read('Gain')*(value-state['input'])/dt)
    else:out=state['out']
    obj.update(EnableIn=True,EnableOut=True,Out=out,DeltaT=dt,Status=bit_value(status,'DINT'))
    engine.last_timer[identity]=dict(at=now,input=value,out=out)


def description():
    return dict(profile='v35-5580-ST-DERV',language='ST',instructions=['DERV'],record=dict(FIELDS),
                status_aliases={name:'Status.'+str(bit) for name,bit in STATUS_ALIASES.items()},
                equation='Out = Gain * (In - previous In) / DeltaT; ByPass passes In directly',
                timing='Mode 0: Periodic task period, otherwise elapsed whole simulated milliseconds; mode 1: explicit OversampleDT',
                startup='First reached software call samples In and produces zero unless ByPass; every reached call samples In, even zero/invalid intervals or bypass',
                disabled='Zero interval holds hidden output; invalid interval/mode holds with DeltaT=0 and Status.0/.31 or .27; RTS mode 2 faults',
                reads='In/ByPass/timing must be known; Gain is read only for a non-bypassed calculation after startup with positive DeltaT',
                lifecycle='Prescan clears enables; Run resets history; skips retain; rollback and detached replacement preserve input/clock/output history',
                arithmetic='Float32 public values and history; host-double expression intermediates; nonfinite/overflow faults transactionally',
                native_runtime_parity=False,
                remaining=['Native startup, bypass/zero/invalid timing transitions, rounding/status/fault/lifecycle qualification',
                           'RTS/module timestamps, general FBD graph forms, packed layouts and other controller profiles'])
