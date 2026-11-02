"""Bounded FBD REAL truncation and DINT BCD conversions."""
import math
from .fbd_bitwise import SCHEMAS as BITWISE_SCHEMAS
from .integer_math import CONTROLLERS
from .model import ModelError
from .numeric_conversions import from_bcd,to_bcd
from .real_math import real

TYPES={'FRD':'FBD_CONVERT','TOD':'FBD_CONVERT','TRN':'FBD_TRUNCATE'}
SCHEMAS={'FBD_CONVERT':BITWISE_SCHEMAS['FBD_CONVERT'],
         'FBD_TRUNCATE':{'EnableIn':'BOOL','Source':'REAL','EnableOut':'BOOL','Dest':'DINT'}}
INSTRUCTIONS=frozenset(TYPES)


def default(dtype):
    return {name:(name=='EnableIn') if kind=='BOOL' else 0.0 if kind=='REAL' else 0 for name,kind in SCHEMAS[dtype].items()}


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
    # All three v35 Block execution tables specify N/A.
    validate(engine,op,scope)


def execute(engine,op,scope):
    _,_,obj=validate(engine,op,scope);value=obj['Source']
    if op.name=='TRN':
        if type(value) not in (int,float):raise ModelError('FBD TRN Source is unknown or not REAL')
        result=math.trunc(real(value))
        if not -(1<<31)<=result<(1<<31):raise ModelError('FBD TRN result outside the signed DINT profile')
    else:
        if type(value) is not int or not -(1<<31)<=value<(1<<31):raise ModelError('FBD '+op.name+' Source is unknown or not a signed DINT')
        result=from_bcd(value) if op.name=='FRD' else to_bcd(value)
    obj.update(EnableIn=True,EnableOut=True,Dest=result)


def description():
    return dict(instructions=sorted(TYPES),records=SCHEMAS,language='FBD Block',
                truncation='Known finite float32 source truncated toward zero into signed DINT; overflow rejected',
                bcd='Shared ladder DINT conversions: eight weighted nibbles for FRD, including A..F; TOD accepts 0..99999999',
                lifecycle='No hidden state; prescan retains enables/Dest; disabled/skipped calls retain Dest',
                failures='Required unknowns, nonfinite/overflow and excluded TOD ranges fail the whole advance',
                native_runtime_parity=False,
                remaining=['Native TOD saturation/minor faults, TRN overflow results, math flags and lifecycle/fault qualification',
                           'Other types/forms, implicit wire conversions, packed layouts and Studio transfer/edit parity'])
