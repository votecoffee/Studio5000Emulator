"""Logical basic-record/STRING/UDT queue copies and qualified narrow numeric conversions."""
from .integer_math import CONTROLLERS, NARROW_RESULT_TYPES, dint_radix
from .model import ModelError,coerce,INT_BITS
from . import numeric_storage, time_values

NUMERIC=frozenset(('SINT','INT','DINT','REAL'))
BASIC_RECORDS=frozenset(('TIMER','COUNTER','CONTROL'))


def supported(memory,dtype):
    if dtype in NUMERIC:return True
    project=memory.project
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:return False
    return record_type(project,dtype)


def record_type(project,dtype,seen=()):
    if dtype.upper() == 'PID':return 'pid' not in project.udts
    if dtype.upper() in BASIC_RECORDS or project.string_capacity(dtype) is not None:return True
    name=dtype.casefold();definition=project.udts.get(name)
    if (name in seen or definition is None or definition.get('Class','User')!='User'
            or name in ('timer','counter','control') or any(name==item.casefold()
            for item in (*project.data_only_types,*project.aois))):return False
    return all(member.get('DataType','').upper() in (*INT_BITS,*time_values.TYPES,'BOOL','REAL','LREAL','BIT')
               or record_type(project,member.get('DataType',''),seen+(name,))
               for member in definition.findall('./Members/Member') if member.get('Hidden','false')!='true')


def aggregate(dtype):return dtype not in NUMERIC


def numeric_type(memory,ref,scope,*,destination=False):
    """Qualified narrow queue payload, independently of the array element type."""
    dtype=(numeric_storage.destination(memory,ref,scope)[2] if destination
           else numeric_storage.source_type(memory,ref,scope))
    if dtype not in NUMERIC:raise ModelError('Numeric FIFO payload requires SINT, INT, DINT or REAL')
    return dtype


def convert_numeric(value, source, dest):
    if source == 'REAL' and dest in NARROW_RESULT_TYPES:
        result, _ = numeric_storage.round_real_to_narrow_signed(coerce(value, source), dest)
        return result
    return numeric_storage.convert(value, source, dest)


def read(memory,ref,scope,dtype):
    """Capture a payload to pass to a store, which detaches logical records."""
    if not aggregate(dtype) and numeric_storage.available(memory.project):
        word = dint_radix(ref)
        if word is not None:
            return numeric_storage.convert(word, 'DINT', dtype)
        source=numeric_type(memory,ref,scope)
        return convert_numeric(memory.read(ref,scope), source, dtype)
    if not aggregate(dtype):return coerce(memory.read(ref,scope),dtype)
    value=memory.read(ref,scope,mutable=False)
    if not isinstance(value,dict):raise ModelError('FIFO requires one represented logical record')
    # Unloads capture these references before replacing whole queue slots.
    return value


def zero(memory,dtype):return memory.project.default(dtype) if aggregate(dtype) else coerce(0,dtype)


def write(memory,ref,scope,dtype,value):
    if not aggregate(dtype) and numeric_storage.available(memory.project):
        target=numeric_type(memory,ref,scope,destination=True)
        key,parts,_=memory.check_writable(ref,scope)
        memory.store(key, parts, convert_numeric(value, dtype, target))
        return
    if not aggregate(dtype):memory.write(ref,value,scope);return
    key,parts,kind=memory.check_writable(ref,scope)
    if kind!=dtype:raise ModelError('FIFO destination type changed during execution')
    memory.store(key,parts,value)
