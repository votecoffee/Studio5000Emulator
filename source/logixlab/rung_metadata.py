"""The observed scoped, invariant Comment removal and its 23-bit RLL region."""
import struct
from . import metadata_query as mq


def target(program,routine,region):
    if any(type(v) is not int for v in (program,routine,region)) or not (1<=program<=65535 and 1<=routine<=65535 and 1<=region<=0x7FFFFF):
        raise ValueError('Unsupported RLL metadata target')
    return mq.Target(0x68,program|(0x6D<<16),routine|((0xFF80|(region>>16))<<16),region&0xFFFF,b'')


def scope(value):
    if value.class_id!=0x68 or value.instance_word>>16!=0x6D:return None
    return value.instance_word&0xFFFF,value.context_word&0xFFFF


def region(value):
    if scope(value) is None or value.qualifier or (value.context_word>>16)&0xFF80!=0xFF80:
        raise ValueError('Unsupported RLL metadata region')
    result=(((value.context_word>>16)&0x7F)<<16)|value.selector_word
    if not result or target(*scope(value),result)!=value:raise ValueError('Noncanonical RLL metadata region')
    return result


def removal(data,expected):
    if type(data) is not bytes or len(data)!=38:raise ValueError('Unsupported RLL Comment removal')
    rows=mq.download_records(data,1)
    if len(rows)!=1:raise ValueError('Unsupported RLL Comment removal')
    row=rows[0]
    if (scope(row.target)!=expected or row.locale_word!=0x7F or row.definition!=1 or row.kind!=4
            or row.data or row.references or row.elements or row.type_code is not None):
        raise ValueError('Unsupported RLL Comment removal')
    return row,region(row.target)
