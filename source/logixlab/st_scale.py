"""Bounded finite-REAL ST scaling with logical SCALE records."""
from .integer_math import CONTROLLERS
from .model import ModelError
from .real_math import real

INSTRUCTIONS=frozenset(('SCL',))
FIELDS={'EnableIn':'BOOL','In':'REAL','InRawMax':'REAL','InRawMin':'REAL',
        'InEUMax':'REAL','InEUMin':'REAL','Limiting':'BOOL','EnableOut':'BOOL',
        'Out':'REAL','MaxAlarm':'BOOL','MinAlarm':'BOOL','Status':'DINT'}
STATUS_BITS={'instructfault':0,'inrawrangeinv':1}


def default():
    return {name:(name=='EnableIn') if dtype=='BOOL' else 0.0 if dtype=='REAL' else 0 for name,dtype in FIELDS.items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('SCL requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError('SCL requires one SCALE tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if dtype!='SCALE' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError('SCL requires one writable logical SCALE record')
    if 'scale' in engine.project.udts:raise ModelError('Redefined SCALE structures remain unqualified')
    return obj


def prescan(engine,op,scope):
    validate(engine,op,scope).update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    obj=validate(engine,op,scope)
    def read(name):
        value=obj[name]
        if type(value) not in (int,float):raise ModelError('SCL '+name+' is unknown or has the wrong value type')
        try:return real(value)
        except ModelError as error:raise ModelError('SCL '+name+' is outside the finite REAL profile') from error
    minimum,maximum=read('InRawMin'),read('InRawMax')
    if minimum>=maximum:
        obj.update(EnableIn=True,EnableOut=True,Status=3);return
    value,eu_min,eu_max=read('In'),read('InEUMin'),read('InEUMax')
    limiting=obj['Limiting']
    if type(limiting) is not bool:raise ModelError('SCL Limiting is unknown or has the wrong value type')
    high,low=value>maximum,value<minimum
    result=(value-minimum)*((eu_max-eu_min)/(maximum-minimum))+eu_min
    if limiting:
        if high:result=eu_max
        elif low:result=eu_min
    try:result=real(result)
    except ModelError as error:raise ModelError('SCL result is outside the finite REAL profile') from error
    obj.update(EnableIn=True,EnableOut=True,Out=result,MaxAlarm=high,MinAlarm=low,Status=0)


def description():
    return dict(profile='v35-5580-ST-SCALE',language='ST',instructions=['SCL'],record=dict(FIELDS),
                status_aliases={'InstructFault':'Status.0','InRawRangeInv':'Status.1'},
                calls='Reached ST calls set EnableIn/EnableOut regardless of stored EnableIn; skipped calls retain values',
                arithmetic='Float32 inputs and final result; host double intermediates in the documented slope formula',
                limiting='Raw inputs above/below range map to the corresponding EU endpoint before final float32 coercion',
                alarms='Strict raw-range comparisons; independent of limiting and EU range direction',
                invalid_range='InRawMin >= InRawMax sets Status=3; Out and alarm values retain; valid recovery sets Status=0',
                prescan='Clear EnableIn/EnableOut; no hidden execution history',
                failures='Unknown required inputs or nonfinite/unrepresentable results stop and roll back the whole advance',
                native_runtime_parity=False,
                remaining=['General FBD outside the qualified single-sheet typed graph','Native intermediate rounding, overflow/limiting order and nonfinite values',
                           'Complete native status, lifecycle, fault and packed-layout parity','Other controller profiles'])
