"""Bounded Structured Text edge pulses using logical FBD_ONESHOT records."""
from .integer_math import CONTROLLERS
from .model import ModelError

INSTRUCTIONS=frozenset(('OSRI','OSFI'))
FIELDS={name:'BOOL' for name in ('EnableIn','InputBit','EnableOut','OutputBit')}


def default():
    return {name:name=='EnableIn' for name in FIELDS}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError(op.name+' requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError(op.name+' requires one FBD_ONESHOT tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if dtype!='FBD_ONESHOT' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError(op.name+' requires one writable logical FBD_ONESHOT record')
    if 'fbd_oneshot' in engine.project.udts:raise ModelError('Redefined FBD_ONESHOT structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=(key,tuple(parts));current=obj['InputBit']
    if type(current) is not bool:raise ModelError(op.name+' InputBit is unknown or has the wrong value type')
    kind,previous=engine._st_oneshot_edges.get(identity,(op.name,op.name=='OSRI'))
    if kind!=op.name:raise ModelError('Mixed one-shot instruction kinds on one FBD_ONESHOT record remain unqualified')
    output=(current and not previous) if op.name=='OSRI' else (previous and not current)
    engine._st_oneshot_edges[identity]=(op.name,current)
    obj.update(EnableIn=True,EnableOut=True,OutputBit=output)


def description():
    return dict(profile='v35-5580-ST-ONESHOT',language='ST',instructions=sorted(INSTRUCTIONS),record=dict(FIELDS),
                calls='Reached ST calls set EnableIn/EnableOut independently of stored EnableIn',
                pulses='OSRI on sampled false-to-true; OSFI on sampled true-to-false; other reached calls clear OutputBit',
                initialization='OSRI previous input starts true; OSFI starts false; initial levels cannot generate pulses',
                skipped_calls='Retain outputs and history until next reached call; hidden intermediate pulses are not sampled',
                prescan='Clear EnableIn/EnableOut; Run entry resets history; represented InputBit/OutputBit retain until execution',
                rollback='Record and sampled-edge history commit with the complete advance',native_runtime_parity=False,
                remaining=['General FBD outside the qualified single-sheet graph and native language forms','Shared records between OSRI and OSFI','Native layout, lifecycle and fault parity',
                           'Other controller profiles'])
