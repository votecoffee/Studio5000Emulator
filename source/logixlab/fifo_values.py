"""Exact declared STRING/UDT FIFO payloads, separate from numeric conversions."""
import copy
from .integer_math import CONTROLLERS
from .model import ModelError,coerce,INT_BITS

NUMERIC=frozenset(('SINT','INT','DINT','REAL'))


def supported(memory,dtype):
    if dtype in NUMERIC:return True
    project=memory.project
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:return False
    return record_type(project,dtype)


def record_type(project,dtype,seen=()):
    if project.string_capacity(dtype) is not None:return True
    name=dtype.casefold();definition=project.udts.get(name)
    if (name in seen or definition is None or definition.get('Class','User')!='User'
            or name in ('timer','counter','control') or any(name==item.casefold()
            for item in (*project.data_only_types,*project.aois))):return False
    return all(member.get('DataType','').upper() in (*INT_BITS,'BOOL','REAL','BIT')
               or record_type(project,member.get('DataType',''),seen+(name,))
               for member in definition.findall('./Members/Member') if member.get('Hidden','false')!='true')


def aggregate(dtype):return dtype not in NUMERIC


def read(memory,ref,scope,dtype):
    value=memory.read(ref,scope)
    if not aggregate(dtype):return coerce(value,dtype)
    if not isinstance(value,dict):raise ModelError('FIFO requires one represented string or UDT record')
    # Typed logical copies retain all represented fields, including unknown
    # backing bytes. Moving an unknown value does not establish its contents.
    return copy.deepcopy(value)


def zero(memory,dtype):return memory.project.default(dtype) if aggregate(dtype) else coerce(0,dtype)


def write(memory,ref,scope,dtype,value):
    if not aggregate(dtype):memory.write(ref,value,scope);return
    key,parts,kind=memory.check_writable(ref,scope)
    if kind!=dtype:raise ModelError('FIFO destination type changed during execution')
    memory.store(key,parts,value)
