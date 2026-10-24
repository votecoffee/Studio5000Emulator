"""Canonical saved UDT bytes at explicit source ACD member locations.

Only visible, completely supplied values are encoded. Padding and unused packed
bits must be zero in the received table. Native template verification remains a
separate prerequisite; this encoder neither allocates layouts nor executes them.
"""
from .download_image import ImageError
from .native_types import NativeTypes
from .object_staging import MAX_STORAGE_BYTES


MAX_DEPTH=8


def encode(dtype,value,types,scalar,stack=()):
    """Return a source template word and exact bytes, rejecting ambiguous storage."""
    key=dtype.casefold()
    if not isinstance(types,NativeTypes):raise ImageError('download_initial_structure_source_required')
    row=types.types.get(key);instance=types.type_ids.get(key)
    if (row is None or type(instance) is not int or not 1<=instance<=0xFFF
            or not 1<=row.size<=MAX_STORAGE_BYTES):
        raise ImageError('download_initial_structure_source_required')
    if key in stack or len(stack)>=MAX_DEPTH:raise ImageError('download_initial_structure_depth')
    visible=tuple(m for m in row.members if not m.hidden)
    if not visible or type(value) is not dict or value.keys()!={m.name for m in visible}:
        raise ImageError('download_initial_structure_fields_required')
    # Accept only explicit scalar SINT hosts for packed visible BOOL members.
    # Their unused bits stay zero; other hidden native fields remain unsupported.
    hosts=set()
    bits={m.offset+m.bit//8 for m in visible if m.dtype.upper()=='BOOL' and m.bit is not None and not m.dimensions}
    for member in row.members:
        if not member.hidden:continue
        if (member.dtype.upper()!='SINT' or member.dimensions or member.bit is not None
                or member.offset not in bits or member.offset in hosts):
            raise ImageError('download_initial_structure_hidden_layout')
        hosts.add(member.offset)
    data=bytearray(row.size);occupied=bytearray(row.size)

    def write(offset,raw,mask=None):
        if type(offset) is not int or offset<0 or offset+len(raw)>row.size:
            raise ImageError('download_initial_structure_member_extent')
        masks=bytes((mask,)) if mask is not None else bytes([255])*len(raw)
        for index,bits in enumerate(masks,offset):
            if occupied[index]&bits:raise ImageError('download_initial_structure_overlap')
            occupied[index]|=bits
        data[offset:offset+len(raw)]=bytes(a|b for a,b in zip(data[offset:offset+len(raw)],raw,strict=True))

    for member in visible:
        item=value[member.name];kind=member.dtype.upper()
        if kind=='BOOL' and member.dimensions:raise ImageError('download_initial_structure_bool_array')
        if len(member.dimensions)>1:raise ImageError('download_initial_structure_member_rank')
        if member.dimensions:
            if type(item) is not list or len(item)!=member.dimensions[0]:
                raise ImageError('download_initial_structure_member_shape')
            items=item
        else:items=(item,)
        if member.bit is not None:
            if kind!='BOOL' or type(item) is not bool:raise ImageError('download_initial_bool_required')
            bit=member.bit%8
            write(member.offset+member.bit//8,bytes((int(item)<<bit,)),1<<bit)
            continue
        for index,item in enumerate(items):
            if member.dtype.casefold() in types.types and kind not in ('TIMER','COUNTER'):
                _,raw=encode(member.dtype,item,types,scalar,(*stack,key))
            else:_,raw=scalar(kind,item,types)
            width=types.width(member.dtype)
            if len(raw)!=width:raise ImageError('download_initial_structure_member_width')
            write(member.offset+index*width,raw)
    return 0x8000|instance,bytes(data)
