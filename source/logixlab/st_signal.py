"""Bounded ST HLL, SNEG and SSUM over logical signal-conditioning records."""
from .integer_math import CONTROLLERS
from .model import ModelError,coerce
from .real_math import real

TYPES={'HLL':'HL_LIMIT','SNEG':'SELECTABLE_NEGATE','SSUM':'SELECTED_SUMMER'}
INSTRUCTIONS=frozenset(TYPES)
SCHEMAS={
    'HL_LIMIT':{'EnableIn':'BOOL','In':'REAL','HighLimit':'REAL','LowLimit':'REAL','SelectLimit':'DINT',
                'EnableOut':'BOOL','Out':'REAL','HighAlarm':'BOOL','LowAlarm':'BOOL','Status':'DINT'},
    'SELECTABLE_NEGATE':{'EnableIn':'BOOL','In':'REAL','NegateEnable':'BOOL','EnableOut':'BOOL','Out':'REAL'},
    'SELECTED_SUMMER':{'EnableIn':'BOOL',**{name+str(i):dtype for i in range(1,9)
                        for name,dtype in (('In','REAL'),('Gain','REAL'),('Select','BOOL'))},
                       'Bias':'REAL','EnableOut':'BOOL','Out':'REAL'}}
STATUS_BITS={'instructfault':0,'limitsinv':1,'selectlimitinv':2}


def default(dtype):
    return {name:(name in ('EnableIn','NegateEnable')) if kind=='BOOL'
            else (1.0 if name.startswith('Gain') else 0.0) if kind=='REAL' else 0
            for name,kind in SCHEMAS[dtype].items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError(op.name+' requires the v35 ControlLogix 5580 software profile')
    dtype=TYPES[op.name]
    if len(op.args)!=1:raise ModelError(op.name+' requires one '+dtype+' tag')
    key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError(op.name+' requires one writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    return obj


def prescan(engine,op,scope):
    validate(engine,op,scope).update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    obj=validate(engine,op,scope);schema=SCHEMAS[TYPES[op.name]]
    def read(name):
        value=obj[name];kind=schema[name]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError(op.name+' '+name+' is unknown or has the wrong value type')
        if kind=='BOOL':return value
        if kind=='DINT':return coerce(value,'DINT')
        try:return real(value)
        except ModelError as error:raise ModelError(op.name+' '+name+' is outside the finite REAL profile') from error
    if op.name=='SNEG':
        value=read('In');result=-value if read('NegateEnable') else value
    elif op.name=='SSUM':
        result=0.0
        for i in range(1,9):
            if read('Select'+str(i)):result+=read('In'+str(i))*read('Gain'+str(i))
        result+=read('Bias')
    else:
        selected=read('SelectLimit');invalid_selector=selected not in (0,1,2)
        mode=0 if invalid_selector else selected;status=5 if invalid_selector else 0
        value=read('In');high=read('HighLimit') if mode!=2 else None;low=read('LowLimit') if mode!=1 else None
        invalid_limits=mode==0 and high<=low
        if invalid_limits:result=low;status|=3
        elif mode==1:result=min(value,high)
        elif mode==2:result=max(value,low)
        else:result=max(low,min(value,high))
        obj.update(Status=status,HighAlarm=mode!=2 and value>=high,LowAlarm=mode!=1 and value<=low)
    try:result=real(result)
    except ModelError as error:raise ModelError(op.name+' result is outside the finite REAL profile') from error
    obj.update(EnableIn=True,EnableOut=True,Out=result)


def description():
    return dict(profile='v35-5580-ST-SIGNALS',language='ST',instructions=sorted(INSTRUCTIONS),records={k:dict(v) for k,v in SCHEMAS.items()},
                calls='Reached ST calls set EnableIn/EnableOut independently of stored EnableIn; skipped calls retain values',
                hll='Modes 0=both, 1=high, 2=low; inclusive active alarms; inactive limit/alarm is ignored/false',
                hll_status='Invalid selector assumes mode 0 with Status.0/.2; invalid both-limit range uses LowLimit with Status.0/.1',
                status_aliases={'HL_LIMIT':{'InstructFault':'Status.0','LimitsInv':'Status.1','SelectLimitInv':'Status.2'}},
                sneg='NegateEnable selects -In or In; signed zero retained by float32 coercion',
                ssum='Selected In1..In8 times gains, summed in index order, then Bias; no selections returns Bias',
                required_inputs='HLL reads active limits; SSUM reads all selectors but only selected signal/gain pairs and Bias',
                arithmetic='Finite float32 inputs/results; host double weighted products and sum, no intermediate native parity claim',
                prescan='Clear EnableIn/EnableOut only; no hidden execution history',
                failures='Unknown required inputs and nonfinite/overflow results stop and roll back the whole advance',
                native_runtime_parity=False,
                remaining=['FBD graph execution','Native precision/intermediate overflow/nonfinite/status/fault/lifecycle/layout parity',
                           'Other controller profiles','SEL/MUX language qualification and remaining select/limit instructions'])
