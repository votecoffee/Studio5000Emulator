"""DINT explicit-target bit moves shared by ST calls and FBD Blocks."""
from . import fbd_bitwise
from .integer_math import CONTROLLERS
from .model import ModelError

TYPES={'BTDT':'FBD_BIT_FIELD_DISTRIBUTE','MVMT':'FBD_MASKED_MOVE'}
SCHEMAS={'FBD_MASKED_MOVE':fbd_bitwise.SCHEMAS['FBD_MASKED_MOVE'],
         'FBD_BIT_FIELD_DISTRIBUTE':{'EnableIn':'BOOL','Source':'DINT','SourceBit':'DINT',
             'Length':'DINT','DestBit':'DINT','Target':'DINT','EnableOut':'BOOL','Dest':'DINT'}}
INSTRUCTIONS=frozenset(TYPES)


def default(dtype):
    return {name:(name=='EnableIn') if kind=='BOOL' else 0 for name,kind in SCHEMAS[dtype].items()}


def validate(engine,op,scope):
    if op.name=='MVMT':return fbd_bitwise.validate(engine,op,scope)
    if engine.project.version!='35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('BTDT requires the v35 ControlLogix 5580 software profile')
    dtype=TYPES[op.name]
    if len(op.args)!=1:raise ModelError('BTDT requires one '+dtype+' record')
    key,parts,actual=engine.memory.check_writable(op.args[0],scope);obj=engine.memory.at(key,parts)
    if actual!=dtype or not isinstance(obj,dict) or set(obj)!=set(SCHEMAS[dtype]):
        raise ModelError('BTDT requires a writable logical '+dtype+' record')
    if dtype.lower() in engine.project.udts:raise ModelError('Redefined '+dtype+' structures remain unqualified')
    return key,parts,obj


def prescan(engine,op,scope):
    if op.name=='MVMT':fbd_bitwise.prescan(engine,op,scope);return
    _,_,obj=validate(engine,op,scope);obj.update(EnableIn=False,EnableOut=False)


def execute(engine,op,scope):
    # Reached ST calls force enables; FBD gating belongs to its graph adapter.
    if op.name=='MVMT':fbd_bitwise.execute(engine,op,scope);return
    _,_,obj=validate(engine,op,scope)
    def read(name):
        value=obj[name]
        if type(value) is not int or not -(1<<31)<=value<(1<<31):
            raise ModelError('BTDT '+name+' is unknown or not a signed DINT')
        return value
    source,target=read('Source')&0xffffffff,read('Target')&0xffffffff
    start,length,dest=read('SourceBit'),read('Length'),read('DestBit')
    if not 0<=start<=31:raise ModelError('BTDT SourceBit must be 0..31')
    if not 1<=length<=32:raise ModelError('BTDT Length must be 1..32')
    if not 0<=dest<=31:raise ModelError('BTDT DestBit must be 0..31')
    mask=(((1<<length)-1)<<dest)&0xffffffff
    result=((target&~mask)|(((source>>start)<<dest)&mask))&0xffffffff
    if result>=1<<31:result-=1<<32
    obj.update(EnableIn=True,EnableOut=True,Dest=result)


def description():
    return dict(instructions=sorted(TYPES),records=SCHEMAS,languages=['ST','FBD Block'],
                calls='One writable logical record; reached ST calls ignore stored false EnableIn and set enables',
                target='Each enabled call starts from explicit Target, never previous Dest; Source/Target unchanged',
                fields='DINT SourceBit/DestBit 0..31, Length 1..32; source excess zero-filled; destination excess discarded without wrap',
                lifecycle='Prescan clears enables and retains Dest; skipped calls retain values; no hidden state',
                failures='All required fields must be known signed DINT; invalid ranges/unknowns roll back the whole advance',
                native_runtime_parity=False,
                remaining=['Native math flags, invalid-range/fault/source-excess/lifecycle qualification',
                           'Other types/forms, packed layouts, postscan and Studio transfer/edit parity'])
