"""Deterministic ST TONR/TOFR/RTOR using logical FBD_TIMER records."""
from .integer_math import CONTROLLERS
from .model import ModelError, coerce

INSTRUCTIONS = frozenset(('TONR','TOFR','RTOR'))
FIELDS = {'EnableIn':'BOOL','TimerEnable':'BOOL','PRE':'DINT','Reset':'BOOL',
          'EnableOut':'BOOL','ACC':'DINT','EN':'BOOL','TT':'BOOL','DN':'BOOL','Status':'DINT'}
STATUS_BITS = {'instructfault':0,'presetinv':1}


def default():
    return {name:(name=='EnableIn') if dtype=='BOOL' else 0 for name,dtype in FIELDS.items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('ST timers require the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError(op.name+' requires one FBD_TIMER tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope)
    obj=engine.memory.at(key,parts)
    if dtype!='FBD_TIMER' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError('ST timers require one writable logical FBD_TIMER record')
    if 'fbd_timer' in engine.project.udts:
        raise ModelError('Redefined FBD_TIMER structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope)
    identity=('ST-FBD-TIMER',key,tuple(parts));state=engine.last_timer.get(identity)
    if state is not None and state['kind']!=op.name:
        raise ModelError('Using different ST timer instructions on one record remains unqualified')
    state=state or dict(kind=op.name,at=engine.time_ms,started=False,active=False,armed=False)
    elapsed=engine.time_ms-state['at'] if state['active'] else 0
    if elapsed<0:raise ModelError('ST timer clock moved backwards')
    state['at']=engine.time_ms;engine.last_timer[identity]=state
    def read(name):
        value=obj[name]
        if type(value) is not (bool if FIELDS[name]=='BOOL' else int):
            raise ModelError('ST timer '+name+' is unknown or has the wrong value type')
        return value if FIELDS[name]=='BOOL' else coerce(value,'DINT')
    obj['EnableIn']=True
    preset=read('PRE')
    if preset<0:
        obj.update(EnableOut=False,Status=3);state['active']=False;return
    reset,enabled=read('Reset'),read('TimerEnable')
    obj.update(EnableOut=True,Status=0)
    if not state['started']:
        obj.update(EN=False,TT=False,DN=False)
        if op.name=='TONR':obj['ACC']=0
        state['started']=True
    if reset:
        obj.update(EN=False,TT=False,DN=False,ACC=preset if op.name=='TOFR' else 0)
        state.update(active=False,armed=False);return
    obj['EN']=enabled
    if op.name=='TOFR':
        if enabled:
            obj.update(ACC=0,TT=False,DN=True);state.update(active=False,armed=True);return
        if not state['armed']:
            obj.update(TT=False,DN=False);state['active']=False;return
        acc=read('ACC')
        if acc<0:raise ModelError('ST timer ACC must be nonnegative')
        acc=min(preset,acc+elapsed)
        obj.update(ACC=acc,TT=acc<preset,DN=acc<preset)
        state['active']=acc<preset;state['armed']=acc<preset
        return
    if not enabled:
        obj['TT']=False;state['active']=False
        if op.name=='TONR':obj.update(ACC=0,DN=False)
        return
    acc=read('ACC')
    if acc<0:raise ModelError('ST timer ACC must be nonnegative')
    acc=min(preset,acc+elapsed)
    obj.update(ACC=acc,TT=acc<preset,DN=acc>=preset);state['active']=acc<preset


def description():
    return dict(profile='v35-5580-ST-FBD_TIMER',language='ST',instructions=sorted(INSTRUCTIONS),
                record=dict(FIELDS),status_aliases={'InstructFault':'Status.0','PresetInv':'Status.1'},
                timing='Integer simulated milliseconds; elapsed time between reached calls while timing',
                st_call='Always executes; EnableIn is set regardless of its stored value',
                first_call='Clear EN/TT/DN; TONR also clears ACC, RTOR/TOFR retain represented ACC',
                prescan='Clear EnableIn/EnableOut; reset hidden elapsed-time history at Run entry',
                invalid_preset='PRE<0 sets Status=3/EnableOut=false and pauses timing; valid calls clear Status',
                rollback='Record values and elapsed-time history commit with the complete advance',
                native_runtime_parity=False,
                remaining=['General FBD outside the qualified single-sheet graph and native language forms','Native clock wrap, precision/status/fault/layout parity',
                           'Other controller profiles','Mixed timer instructions sharing one record'])
