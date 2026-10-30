"""Bounded ST Boolean memory blocks with transactional clock/output history."""
from .integer_math import CONTROLLERS
from .model import ModelError

TYPES={'DFF':'FLIP_FLOP_D','JKFF':'FLIP_FLOP_JK','RESD':'DOMINANT_RESET','SETD':'DOMINANT_SET'}
INSTRUCTIONS=frozenset(TYPES)
SCHEMAS={
    'FLIP_FLOP_D':dict.fromkeys(('EnableIn','D','Clear','Clock','EnableOut','Q','QNot'),'BOOL'),
    'FLIP_FLOP_JK':dict.fromkeys(('EnableIn','Clear','Clock','EnableOut','Q','QNot'),'BOOL'),
    'DOMINANT_RESET':dict.fromkeys(('EnableIn','Set','Reset','EnableOut','Out','OutNot'),'BOOL'),
    'DOMINANT_SET':dict.fromkeys(('EnableIn','Set','Reset','EnableOut','Out','OutNot'),'BOOL')}


def default(dtype):
    value={name:name=='EnableIn' for name in SCHEMAS[dtype]}
    if dtype.startswith('FLIP_FLOP'):value['QNot']=True
    else:value.update(Out=dtype=='DOMINANT_SET',OutNot=dtype!='DOMINANT_SET')
    return value


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError(op.name+' requires the v35 ControlLogix 5580 software profile')
    dtype=TYPES[op.name]
    if len(op.args)!=1:raise ModelError(op.name+' requires one '+dtype+' tag')
    key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError(op.name+' requires one writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=('ST-DIGITAL',key,tuple(parts))
    state=engine.last_timer.get(identity,dict(kind=op.name,value=op.name=='SETD',clock=True))
    if state['kind']!=op.name:raise ModelError('Mixed Boolean memory instruction kinds on one record remain unqualified')
    def read(name):
        if type(obj[name]) is not bool:raise ModelError(op.name+' '+name+' is unknown or not BOOL')
        return obj[name]
    value=state['value'];clock=state['clock']
    if op.name in ('DFF','JKFF'):
        clear,clock=read('Clear'),read('Clock')
        if clear:value=False
        elif clock and not state['clock']:value=read('D') if op.name=='DFF' else not value
        obj.update(Q=value,QNot=not value)
    else:
        if op.name=='RESD':
            if read('Reset'):value=False
            elif read('Set'):value=True
        else:
            if read('Set'):value=True
            elif read('Reset'):value=False
        obj.update(Out=value,OutNot=not value)
    obj.update(EnableIn=True,EnableOut=True)
    engine.last_timer[identity]=dict(kind=op.name,value=value,clock=clock)


def description():
    return dict(profile='v35-5580-ST-Boolean-memory',language='ST',instructions=sorted(INSTRUCTIONS),records=SCHEMAS,
                startup='DFF/JKFF previous clock true and Q false; RESD initial Out false; SETD initial Out true',
                dff='Sample D only on a reached false-to-true Clock transition; Clear overrides the edge',
                jkff='Toggle on a reached rising clock; Clear overrides; v35 structure has no J/K input fields',
                latches='RESD Reset wins; SETD Set wins; neither input retains output',
                outputs='Complement recomputed on every reached call; hidden retained state is separate from visible output writes',
                sampling='Clear still samples Clock; skipped calls retain outputs/history; hidden intermediate transitions are not sampled',
                reads='Clock and Clear always required for flip-flops; D only on an uncleared rising edge; dominant latch input may bypass subordinate input',
                lifecycle='Prescan clears enables; Run resets history; first reached call applies startup then inputs; rollback/replacement preserve state',
                native_runtime_parity=False,
                remaining=['General FBD outside the qualified single-sheet profile, packed layouts and other controllers','Native startup/Run/skip/postscan and output-write qualification',
                           'Native unknown-input, lifecycle, status and fault parity'])
