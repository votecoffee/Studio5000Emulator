"""Bounded little-endian numeric COP/CPS regions, without aggregate ABI guesses."""
import re
import struct
from .integer_math import CONTROLLERS
from .model import ModelError,coerce,literal
from .real_math import real

FORMATS={'SINT':'b','INT':'h','DINT':'i','LINT':'q','USINT':'B','UINT':'H','UDINT':'I','ULINT':'Q','REAL':'f'}
SIZES={name:struct.calcsize('<'+fmt) for name,fmt in FORMATS.items()}
MAX_BYTES=32768
MAX_VISITS=100000


def location(memory,ref,scope,*,writable=False):
    key,parts,dtype=(memory.check_writable if writable else memory.resolve)(ref,scope)
    if key is None or any(isinstance(p,tuple) for p in parts):raise ModelError('Numeric copy operands must be declared non-bit tags')
    value=memory.values[key];candidate=None
    for i,part in enumerate(parts):
        if isinstance(value,dict):candidate=None
        if isinstance(value,list) and candidate is None:candidate=(parts[:i],value)
        value=value[part]
    if isinstance(value,list) and candidate is None:candidate=(parts,value)
    return key,parts,dtype,candidate


def prefix(memory,ref,scope,count,*,writable=False):
    key,parts,dtype,candidate=location(memory,ref,scope,writable=writable)
    if not count:return key,[],dtype
    if candidate is None:return key,[parts],dtype
    def flatten(path,value):
        if isinstance(value,list):
            for i,item in enumerate(value):yield from flatten(path+[i],item)
        else:yield path
    result=[];started=False
    for visited,path in enumerate(flatten(*candidate),1):
        if visited>MAX_VISITS:raise ModelError('Numeric-copy region traversal limit exceeded')
        if not started and path[:len(parts)]==parts:started=True
        if started:
            result.append(path)
            if len(result)==count:break
    if not started:raise ModelError('Numeric-copy start does not address an array element')
    return key,result,dtype


def plan(engine,op,scope,count):
    memory=engine.memory;st=memory.resolve(op.args[0],scope)[2];dt=memory.check_writable(op.args[1],scope)[2]
    if st not in FORMATS or dt not in FORMATS:return None
    if memory.project.version!='35' or memory.project.processor.upper() not in CONTROLLERS:
        if st==dt:return None
        raise ModelError('Mixed numeric copies require the v35 ControlLogix 5580 software profile')
    if type(count) is not int or not 0<=count<=100000:raise ModelError('Block length must be an integer in 0..100000')
    requested=count*SIZES[dt]
    source=prefix(memory,op.args[0],scope,min((requested+SIZES[st]-1)//SIZES[st],MAX_BYTES//SIZES[st]+1))
    dest=prefix(memory,op.args[1],scope,min(count,MAX_BYTES//SIZES[dt]+1),writable=True)
    size=min(requested,len(source[1])*SIZES[st],len(dest[1])*SIZES[dt])
    if size>MAX_BYTES:raise ModelError('Numeric-copy transfer exceeds 32768 bytes')
    return source,dest,size


def encode(value,dtype):
    if dtype=='REAL':value=real(value)
    elif type(value) is not int:raise ModelError('Numeric-copy source must be a known integer')
    else:value=coerce(value,dtype)
    try:return struct.pack('<'+FORMATS[dtype],value)
    except (struct.error,OverflowError) as error:raise ModelError('Numeric-copy source value cannot be encoded') from error


def decode(raw,dtype):
    value=struct.unpack('<'+FORMATS[dtype],raw)[0]
    return real(value) if dtype=='REAL' else value


def execute(engine,specification):
    source,dest,size=specification;sk,sparts,st=source;dk,dparts,dt=dest
    engine.budget-=size
    if engine.budget<0:raise ModelError('Numeric-copy byte budget exceeded')
    memory=engine.memory
    if st==dt:
        # Retain established forward overlap propagation and unknown-value copies.
        for source_part,dest_part in zip(sparts[:size//SIZES[st]],dparts):memory.store(dk,dest_part,memory.at(sk,source_part))
        return
    raw=b''.join(encode(memory.at(sk,p),st) for p in sparts[:(size+SIZES[st]-1)//SIZES[st]])[:size]
    writes=[]
    for i,part in enumerate(dparts[:(size+SIZES[dt]-1)//SIZES[dt]]):
        chunk=raw[i*SIZES[dt]:(i+1)*SIZES[dt]]
        if len(chunk)<SIZES[dt]:
            try:chunk+=encode(memory.at(dk,part),dt)[len(chunk):]
            except ModelError as error:raise ModelError('Partial numeric-copy destination must be known and finite') from error
        writes.append((part,decode(chunk,dt)))
    for part,value in writes:memory.store(dk,part,value)


def write_effects(engine,op,scope):
    """Protect every written cell, conservatively for indirect/dynamic regions."""
    memory=engine.memory;count=engine.extensions.integer(op.args[2],scope)
    spec=plan(engine,op,scope,count)
    if spec is None:key,parts,_=memory.region(op.args[1],count,scope)
    else:
        _,(key,parts,dtype),size=spec;parts=parts[:(size+SIZES[dtype]-1)//SIZES[dtype]]
    try:literal(op.args[2]);static=True
    except ValueError:static=False
    static=static and all(re.fullmatch(r'\s*\d+\s*(?:,\s*\d+\s*)*',s) for s in re.findall(r'\[([^\]]*)\]',op.args[1]))
    if static:return [(key,p) for p in parts]
    key,parts,_,candidate=location(memory,op.args[1],scope,writable=True)
    return [(key,candidate[0] if candidate else parts)]


def description(project):
    return dict(profile='v35-5580-numeric-COP-CPS',instructions=['COP','CPS'],languages=['RLL','ST'],
                available=project.version=='35' and project.processor.upper() in CONTROLLERS,
                types=sorted(FORMATS),endianness='little',length='Destination element count; 0..100000',
                transfer='Minimum of requested bytes and remaining source/destination numeric-region bytes; at most 32768 bytes',
                partial='Preserve uncopied bytes in final destination element; its prior value must be known',
                boundaries='Scalar, member or array region; row-major multidimensional arrays and resolved member arrays; no crossing structure members',
                overlap='Same-type copies propagate forward sequentially for COP and CPS, preserving established model behavior',
                unknowns='Same-type copies retain logical unknowns; mixed-type reads require known finite source values and representable finite REAL results',
                atomicity='Both execute inside one model instruction; no native task/I/O/remote-client synchronization claim',
                budget='One budget unit per actual transferred byte; whole-advance rollback on failure',
                native_runtime_parity=False,
                remaining=['Native aggregate/BOOL/string/LREAL layouts and cross-member/base-tag copying',
                           'Nonfinite REAL payloads, native faults/partial effects, scheduling/interruption and other controller profiles'])
