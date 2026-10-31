"""DINT bitwise/masked Block forms; native flags and packed layouts unqualified."""
from .integer_math import CONTROLLERS
from .model import ModelError

TYPES={**dict.fromkeys(('AND','OR','XOR'),'FBD_LOGICAL'),'NOT':'FBD_CONVERT',
       'MEQ':'FBD_MASK_EQUAL','MVMT':'FBD_MASKED_MOVE'}
SCHEMAS={
    'FBD_LOGICAL':{'EnableIn':'BOOL','SourceA':'DINT','SourceB':'DINT','EnableOut':'BOOL','Dest':'DINT'},
    'FBD_CONVERT':{'EnableIn':'BOOL','Source':'DINT','EnableOut':'BOOL','Dest':'DINT'},
    'FBD_MASK_EQUAL':{'EnableIn':'BOOL','Source':'DINT','Mask':'DINT','Compare':'DINT','EnableOut':'BOOL','Dest':'BOOL'},
    'FBD_MASKED_MOVE':{'EnableIn':'BOOL','Source':'DINT','Mask':'DINT','Target':'DINT','EnableOut':'BOOL','Dest':'DINT'}}
INSTRUCTIONS=frozenset(TYPES)


def default(dtype):
    return {name:(name=='EnableIn') if kind=='BOOL' else 0 for name,kind in SCHEMAS[dtype].items()}


def validate(engine,op,scope):
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError(op.name+' requires the v35 ControlLogix 5580 software profile')
    dtype=TYPES[op.name]
    if len(op.args)!=1:raise ModelError('FBD '+op.name+' requires one '+dtype+' record')
    key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError('FBD '+op.name+' requires a writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    _,_,obj=validate(engine,op,scope)
    # MVMT clears enables; the other five v35 Block tables specify N/A.
    if op.name=='MVMT':obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    _,_,obj=validate(engine,op,scope)
    def read(name):
        value=obj[name]
        if type(value) is not int or not -(1<<31)<=value<(1<<31):
            raise ModelError('FBD '+op.name+' '+name+' is unknown or not a signed DINT')
        return value & 0xffffffff
    if op.name in ('AND','OR','XOR'):
        a,b=read('SourceA'),read('SourceB')
        result=a&b if op.name=='AND' else a|b if op.name=='OR' else a^b
    elif op.name=='NOT':result=read('Source')^0xffffffff
    else:
        source,mask=read('Source'),read('Mask')
        if op.name=='MEQ':result=(source&mask)==(read('Compare')&mask)
        else:result=(source&mask)|(read('Target')&(~mask&0xffffffff))
    if type(result) is int and result>=1<<31:result-=1<<32
    obj.update(EnableIn=True,EnableOut=True,Dest=result)


def description():
    return dict(instructions=sorted(TYPES),records=SCHEMAS,language='FBD Block',
                bitwise='Exact 32-bit patterns; signed DINT outputs; MEQ returns BOOL',
                masked_equal='Compare Source & Mask with Compare & Mask',
                masked_move='Replace selected Target bits with Source bits; never read previous Dest',
                lifecycle='No hidden state; MVMT prescan clears enables; other five retain enables/Dest; all retain Dest on disabled/skipped calls',
                failures='All required operands must be known signed DINT values, including zero/full masks; failures roll back the whole advance',
                native_runtime_parity=False,
                remaining=['ST MVMT call, tagless Functions, other FBD_CONVERT operations, wider/mixed types and packed layouts',
                           'Native math flags, fault, lifecycle, transfer/edit and controller qualification'])
