"""Bounded ST CTUD with logical FBD_COUNTER and per-record sampled edges."""
from .integer_math import CONTROLLERS,bit_value
from .model import ModelError,coerce

INSTRUCTIONS=frozenset(('CTUD',))
FIELDS={'EnableIn':'BOOL','CUEnable':'BOOL','CDEnable':'BOOL','PRE':'DINT','Reset':'BOOL',
        'EnableOut':'BOOL','ACC':'DINT','CU':'BOOL','CD':'BOOL','DN':'BOOL','OV':'BOOL','UN':'BOOL'}


def default():
    return {name:(name=='EnableIn') if dtype=='BOOL' else 0 for name,dtype in FIELDS.items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('CTUD requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError('CTUD requires one FBD_COUNTER tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if dtype!='FBD_COUNTER' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError('CTUD requires one writable logical FBD_COUNTER record')
    if 'fbd_counter' in engine.project.udts:raise ModelError('Redefined FBD_COUNTER structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=(key,tuple(parts))
    def read(name):
        value=obj[name]
        if type(value) is not (bool if FIELDS[name]=='BOOL' else int):
            raise ModelError('CTUD '+name+' is unknown or has the wrong value type')
        return value if FIELDS[name]=='BOOL' else coerce(value,'DINT')
    up,down,reset,preset=read('CUEnable'),read('CDEnable'),read('Reset'),read('PRE')
    previous=engine._st_counter_edges.get(identity,(up,down))
    engine._st_counter_edges[identity]=(up,down)
    obj.update(EnableIn=True,EnableOut=True,CU=up,CD=down)
    if reset:
        obj.update(ACC=0,DN=0>=preset,OV=False,UN=False);return
    acc=read('ACC')
    # The two arithmetic operations are separate: both can wrap on one call.
    if up and not previous[0]:
        if acc==2147483647:obj['OV']=True
        acc=bit_value(acc+1,'DINT')
    if down and not previous[1]:
        if acc==-2147483648:obj['UN']=True
        acc=bit_value(acc-1,'DINT')
    obj.update(ACC=acc,DN=acc>=preset)


def description():
    return dict(profile='v35-5580-ST-CTUD',language='ST',instructions=['CTUD'],record=dict(FIELDS),
                calls='Executed ST calls set EnableIn/EnableOut; CU/CD mirror current count inputs',
                edges='First reached call samples inputs without counting; later sampled false-to-true transitions count',
                ordering='Count up before count down; signed DINT wrap, OV/UN retained until Reset or explicit writes',
                done='ACC >= PRE, including zero/negative presets and Reset result',
                reset='Priority over counting; ACC=0, OV/UN=false, current input levels consumed',
                prescan='Clear EnableIn/EnableOut; Run entry clears sampled-edge history and retains represented data',
                rollback='Record and sampled-edge history commit with the complete advance',
                native_runtime_parity=False,
                remaining=['General FBD outside the qualified single-sheet graph and native language forms','Native reset/overflow/status/layout/fault parity',
                           'Other controller profiles and complete lifecycle qualification'])
