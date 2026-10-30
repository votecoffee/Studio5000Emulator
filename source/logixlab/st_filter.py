"""LPF software profile: bilinear sections, not a verified native recurrence."""
import math

from .integer_math import CONTROLLERS,bit_value
from .model import ModelError,coerce
from .real_math import real

INSTRUCTIONS=frozenset(('LPF',))
FIELDS={'EnableIn':'BOOL','In':'REAL','Initialize':'BOOL','WLag':'REAL','Order':'REAL',
        'TimingMode':'DINT','OversampleDT':'REAL','RTSTime':'DINT','RTSTimeStamp':'DINT',
        'EnableOut':'BOOL','Out':'REAL','DeltaT':'REAL','Status':'DINT'}
STATUS_ALIASES={'InstructFault':0,'WLagInv':1,'OrderInv':2,'TimingModeInv':27,
                'RTSMissed':28,'RTSTimeInv':29,'RTSTimeStampInv':30,'DeltaTInv':31}
STATUS_BITS={name.lower():bit for name,bit in STATUS_ALIASES.items()}
LOWER={1:1e-7,2:1e-5,3:0.001}
MAX_DT=real(4194.303)


def default():
    return {name:(name=='EnableIn') if kind=='BOOL' else float(name=='Order') if kind=='REAL'
            else int(name=='RTSTime') for name,kind in FIELDS.items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('LPF requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError('LPF requires one FILTER_LOW_PASS tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if dtype!='FILTER_LOW_PASS' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError('LPF requires one writable logical FILTER_LOW_PASS record')
    if 'filter_low_pass' in engine.project.udts:raise ModelError('Redefined FILTER_LOW_PASS structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def seed(order,value):
    return [[value,value]] if order==1 else [[value]*4] if order==2 else [[value,value],[value]*4]


def advance(order,r,value,sections):
    """Bilinear transform s=2/DT*(1-z^-1)/(1+z^-1); no prewarping.

    The documented analog denominators factor into a first-order section and/or
    a biquad with damping sqrt(2) (order 2) or 1 (order 3). Hidden state and
    coefficients use host doubles; only public operands/results are float32.
    """
    result=[]
    if order in (1,3):
        xp,yp=sections[0];out=((1-r)*yp+r*(value+xp))/(1+r)
        result.append([value,out]);value=out
    if order in (2,3):
        xp,xpp,yp,ypp=sections[-1];damping=math.sqrt(2) if order==2 else 1.0
        den=1+damping*r+r*r
        out=(r*r*(value+2*xp+xpp)-2*(r*r-1)*yp-(1-damping*r+r*r)*ypp)/den
        result.append([value,xp,out,yp]);value=out
    if not all(math.isfinite(v) for section in result for v in section):raise ModelError('LPF nonfinite internal state')
    return real(value),result


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=('ST-LOW-PASS',key,tuple(parts))
    state=engine.last_timer.get(identity);now=engine.time_ms
    def read(name):
        value=obj[name];kind=FIELDS[name]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError('LPF '+name+' is unknown or has the wrong value type')
        return value if kind=='BOOL' else coerce(value,'DINT') if kind=='DINT' else real(value)
    mode=read('TimingMode')
    if mode==2:raise ModelError('LPF real time sampling mode remains unqualified')
    value,initialize,requested,frequency=read('In'),read('Initialize'),read('Order'),read('WLag')
    order=int(requested) if requested in (1.0,2.0,3.0) else 1
    status=0 if requested==order else 5
    if mode==0:
        scheduler=engine._task_scheduler
        task=next((t for t in scheduler.tasks if t.name==engine._executing_task),None) if scheduler else None
        elapsed=now-state['at'] if state is not None else 0
        if elapsed<0:raise ModelError('LPF simulation clock moved backwards')
        dt=real((task.period if task is not None and task.kind=='Periodic' else elapsed)/1000)
    elif mode==1:dt=read('OversampleDT')
    else:status|=(1<<27)|1;dt=0.0
    if not 0<=dt<=MAX_DT:status|=(1<<31)|1;dt=0.0
    if dt>0:
        low,high=LOWER[order]/dt,0.7*math.pi/dt
        if not low<=frequency<=high:status|=3;frequency=min(high,max(low,frequency))
    if state is None or initialize or state['order']!=order:
        out,sections=value,seed(order,value)
    elif dt==0:out,sections=state['out'],state['sections']
    else:out,sections=advance(order,frequency*dt/2,value,state['sections'])
    obj.update(EnableIn=True,EnableOut=True,Out=out,DeltaT=dt,Status=bit_value(status,'DINT'))
    engine.last_timer[identity]=dict(at=now,order=order,out=out,sections=sections)


def description():
    return dict(profile='v35-5580-ST-LPF-bilinear-software',language='ST',instructions=['LPF'],record=dict(FIELDS),
                status_aliases={name:'Status.'+str(bit) for name,bit in STATUS_ALIASES.items()},
                solver='Explicit software approximation: bilinear first/second-order sections without prewarping; not verified native coefficients',
                orders='1: one pole; 2: Butterworth biquad; 3: one pole followed by damping-one biquad',
                arithmetic='Float32 public inputs/results; host-double coefficients and hidden section histories',
                timing='Mode 0: configured Periodic task period, otherwise elapsed whole simulated milliseconds; mode 1: OversampleDT',
                disabled='Zero interval holds history/output; invalid interval/mode holds with status; first/Initialize/order change still seeds from In',
                parameters='Order outside exact 1/2/3 uses 1 with Status.0/.2; internal cutoff clamps to order-specific bounds with Status.0/.1; inputs retained',
                lifecycle='Run clears history; first call and order changes seed from In; skipped calls retain state; rollback/replacement preserve histories',
                native_runtime_parity=False,
                remaining=['Native discrete recurrence, coefficients, precision and transitions','Real time sampling/module timestamps and RTS diagnostics',
                           'FBD graphs, packed layouts, other profiles and HPF/NTCH','Native nonfinite, overflow/status/fault, first-scan and postscan behavior'])
