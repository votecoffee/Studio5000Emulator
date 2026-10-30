"""Bounded ESEL selection and transactional Program/Operator arbitration."""
from .integer_math import CONTROLLERS
from .model import ModelError,coerce
from .real_math import real

INSTRUCTIONS=frozenset(('ESEL',))
FIELDS={'EnableIn':'BOOL',**{'In'+str(i):'REAL' for i in range(1,7)},
        **{'In'+str(i)+'Fault':'BOOL' for i in range(1,7)},
        'InsUsed':'DINT','SelectorMode':'DINT','ProgSelector':'DINT','OperSelector':'DINT',
        **dict.fromkeys(('ProgProgReq','ProgOperReq','ProgOverrideReq','OperProgReq','OperOperReq','ProgValueReset'),'BOOL'),
        'EnableOut':'BOOL','Out':'REAL','SelectedIn':'DINT','ProgOper':'BOOL','Override':'BOOL','Status':'DINT'}
STATUS_ALIASES={'InstructFault':0,'InsFaulted':1,'InsUsedInv':2,'SelectorModeInv':3,'ProgSelectorInv':4,'OperSelectorInv':5}
STATUS_BITS={name.lower():bit for name,bit in STATUS_ALIASES.items()}


def default():
    return {name:(name=='EnableIn') if kind=='BOOL' else 0.0 if kind=='REAL' else int(name=='InsUsed')
            for name,kind in FIELDS.items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('ESEL requires the v35 ControlLogix 5580 software profile')
    if len(op.args)!=1:raise ModelError('ESEL requires one SELECT_ENHANCED tag')
    key,parts,dtype=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if dtype!='SELECT_ENHANCED' or not isinstance(obj,dict) or set(obj)!=set(FIELDS):
        raise ModelError('ESEL requires one writable logical SELECT_ENHANCED record')
    if 'select_enhanced' in engine.project.udts:raise ModelError('Redefined SELECT_ENHANCED structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    key,parts,obj=validate(engine,op,scope);identity=('ST-ENHANCED-SELECT',key,tuple(parts))
    def read(name):
        value=obj[name];kind=FIELDS[name]
        expected=(bool,) if kind=='BOOL' else (int,) if kind=='DINT' else (int,float)
        if type(value) not in expected:raise ModelError('ESEL '+name+' is unknown or has the wrong value type')
        return value if kind=='BOOL' else coerce(value,'DINT') if kind=='DINT' else real(value)
    program=engine.last_timer.get(identity,False)
    prog,oper,override,op_prog,op_oper,reset=(read(name) for name in
        ('ProgProgReq','ProgOperReq','ProgOverrideReq','OperProgReq','OperOperReq','ProgValueReset'))
    if oper:program=False
    elif prog:program=True
    elif program and op_oper:program=False
    elif not program and op_prog:program=True
    used,mode,pick_prog,pick_oper=(read(name) for name in ('InsUsed','SelectorMode','ProgSelector','OperSelector'))
    status=(5 if not 1<=used<=6 else 0)|(9 if not 0<=mode<=4 else 0)
    if not 0<=pick_prog<=6:status|=17
    if not 0<=pick_oper<=6:status|=33
    selected=None;out=None
    if 0<=mode<=4:
        if mode==0 or override:
            pick=pick_prog if program else pick_oper
            if 1<=pick<=6:selected=pick;out=read('In'+str(pick))
        elif 1<=used<=6:
            values=[(i,read('In'+str(i))) for i in range(1,used+1) if not read('In'+str(i)+'Fault')]
            if not values:status|=3
            elif mode==4:selected=0;out=real(sum(v for _,v in values)/len(values))
            elif mode in (1,2):selected,out=(max if mode==1 else min)(values,key=lambda row:row[1])
            else:
                ordered=sorted(v for _,v in values);middle={ordered[(len(ordered)-1)//2],ordered[len(ordered)//2]}
                selected,out=next(row for row in values if row[1] in middle)
    if selected is not None:obj.update(Out=out,SelectedIn=selected)
    obj.update(EnableIn=True,EnableOut=True,ProgOper=program,Override=override,Status=status,
               OperProgReq=False,OperOperReq=False)
    if reset:obj.update(ProgProgReq=False,ProgOperReq=False,ProgOverrideReq=False)
    engine.last_timer[identity]=program


def description():
    return dict(profile='v35-5580-ST-ESEL',language='ST',instructions=['ESEL'],record=dict(FIELDS),
                status_aliases={name:'Status.'+str(bit) for name,bit in STATUS_ALIASES.items()},
                modes='0 manual; 1 high; 2 low; 3 median; 4 average; automatic modes use good-health inputs in prefix InsUsed',
                ties='First input index wins high/low ties; even median chooses first original input equal to either middle value',
                control='First reached call starts Operator, then applies requests; ProgOperReq wins, then ProgProgReq, then the request to leave current control',
                manual='Active Program/Operator selector 1..6 selects that input independently of InsUsed/health; selector 0 holds Out and SelectedIn',
                override='ProgOverrideReq is level-sensitive manual selection; invalid SelectorMode still prevents an output update',
                requests='Clear Operator requests after each reached call; ProgValueReset clears Program requests after using them',
                diagnostics='Recompute selector/count diagnostics every call; invalid automatic count/mode and all-used-inputs-faulted hold visible Out/SelectedIn',
                reads='Required controls/selectors must be known; automatic modes read used health flags and only healthy values; manual reads selected value only',
                lifecycle='Prescan clears enables; Run clears control history; skips retain; whole-advance rollback and detached replacement preserve control',
                native_runtime_parity=False,
                remaining=['Native startup, simultaneous requests, reset/override/health/status precedence and median qualification',
                           'FBD graphs, packed layouts, other controller profiles and native precision/lifecycle/nonfinite/fault parity'])
