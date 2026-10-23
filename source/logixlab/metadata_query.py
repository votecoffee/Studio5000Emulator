"""Bounded detached decoding of observed v35 Metadata Definition queries.

This module does not dispatch services, encode controller replies, resolve source
objects, expand string blobs, or install captured metadata in the running model.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
import struct

MAX_BYTES=8*1024*1024
MAX_FRAMES=20000
MAX_RECORDS=100000
MAX_REFERENCES=4096
NUMERIC_WIDTHS={0xC2:1,0xC3:2,0xC4:4}
_TARGET=(0xFFFF,0x8E,1,0,0,0,0)
SELECTIONS={
    'controller-all':struct.pack('<8H',1,*_TARGET),
    'controller-attribute-26':struct.pack('<9H',9,*_TARGET,26),
    'all-objects':struct.pack('<8H',1,*([0xFFFF]*7)),
}


@dataclass(frozen=True)
class Query:
    format:int
    position:int
    selection:str


@dataclass(frozen=True)
class Chunk:
    format:int
    position:int
    data:bytes


def _query(query):
    if (not isinstance(query,Query) or type(query.format) is not int or type(query.position) is not int
            or not isinstance(query.selection,str) or query.selection not in SELECTIONS):
        raise ValueError('Invalid metadata query context')
    if query.format==0x101:
        if query.position!=0:raise ValueError('Initial metadata query position must be zero')
    elif query.format==1:
        if not 0<query.position<MAX_BYTES:raise ValueError('Invalid metadata query continuation position')
    else:raise ValueError('Unsupported metadata query format')


def parse_query(payload):
    if not isinstance(payload,bytes) or len(payload) not in (24,26):
        raise ValueError('Unsupported metadata query extent')
    fmt,position=struct.unpack_from('<II',payload)
    selection=next((name for name,target in SELECTIONS.items() if payload[8:]==target),None)
    if selection is None:raise ValueError('Unsupported metadata query selection')
    result=Query(fmt,position,selection);_query(result)
    return result


def _chunk(chunk,query):
    _query(query)
    if (not isinstance(chunk,Chunk) or type(chunk.format) is not int or type(chunk.position) is not int
            or not isinstance(chunk.data,bytes) or len(chunk.data)>MAX_BYTES):
        raise ValueError('Invalid metadata query chunk context')
    allowed=(0x101,0x301) if query.format==0x101 else (1,0x201)
    if chunk.format not in allowed or chunk.position!=query.position:
        raise ValueError('Metadata query response format or position mismatch')
    if not chunk.data and chunk.format!=0x301:raise ValueError('Empty metadata query fragment')


def parse_chunk(payload,query):
    if not isinstance(payload,bytes) or not 8<=len(payload)<=MAX_BYTES+8:
        raise ValueError('Invalid metadata query chunk extent')
    fmt,position=struct.unpack_from('<II',payload)
    result=Chunk(fmt,position,payload[8:]);_chunk(result,query)
    return result


class Assembly:
    """One ordered query stream; rejected frames leave the assembly unchanged."""
    def __init__(self,*,max_bytes=MAX_BYTES,max_frames=MAX_FRAMES):
        if (type(max_bytes) is not int or not 1<=max_bytes<=MAX_BYTES or
                type(max_frames) is not int or not 1<=max_frames<=MAX_FRAMES):
            raise ValueError('Invalid metadata query assembly limits')
        self.max_bytes=max_bytes;self.max_frames=max_frames
        self.selection=None;self.complete=False;self.frames=0;self._data=bytearray()

    def accept(self,query,chunk):
        _chunk(chunk,query)
        if self.complete:raise ValueError('Metadata query stream is already complete')
        if self.selection is None:
            if query.format!=0x101:raise ValueError('Metadata query stream has no initial frame')
        elif query.format!=1 or query.selection!=self.selection or query.position!=len(self._data):
            raise ValueError('Metadata query stream selection or cursor changed')
        if self.frames>=self.max_frames or len(self._data)+len(chunk.data)>self.max_bytes:
            raise ValueError('Metadata query assembly limit')
        self.selection=query.selection;self.frames+=1;self._data.extend(chunk.data)
        self.complete=chunk.format in (0x301,0x201)

    def data(self):
        if not self.complete:raise ValueError('Metadata query stream is incomplete')
        return bytes(self._data)

    def description(self):
        return dict(selection=self.selection,complete=self.complete,frames=self.frames,bytes=len(self._data),
                    payload_sha256=hashlib.sha256(self._data).hexdigest(),payloads_exposed=False)


@dataclass(frozen=True)
class Target:
    class_id:int
    instance_word:int
    context_word:int
    selector_word:int
    qualifier:bytes


@dataclass(frozen=True)
class Reference:
    name:bytes
    target:Target


@dataclass(frozen=True)
class Record:
    target:Target
    locale_word:int
    definition:int
    record_word:int
    kind:int
    data:bytes=b''
    type_code:int|None=None
    elements:int=0
    references:tuple=()


class _Reader:
    def __init__(self,data):self.data=data;self.position=0

    def take(self,size):
        if size>len(self.data)-self.position:raise ValueError('Truncated metadata query record')
        raw=self.data[self.position:self.position+size];self.position+=size
        return raw

    def fields(self,fmt):return struct.unpack(fmt,self.take(struct.calcsize(fmt)))

    def string(self):return self.take(self.fields('<H')[0])

    def target(self):
        cls,instance,context,selector,size=self.fields('<HIIHH')
        return Target(cls,instance,context,selector,self.take(size))


def _value(reader,target,locale,definition,word):
    if reader.take(12)!=bytes(12):raise ValueError('Unsupported metadata query reserved words')
    kind,=reader.fields('<H');raw=b'';code=None;count=0;references=()
    if kind==1:raw=reader.string()
    elif kind==2:
        code,count=reader.fields('<HH')
        if code not in NUMERIC_WIDTHS or not count:raise ValueError('Unsupported metadata query numeric layout')
        raw=reader.take(NUMERIC_WIDTHS[code]*count)
    elif kind==3:
        count,=reader.fields('<H')
        if not 1<=count<=MAX_REFERENCES:raise ValueError('Metadata query reference count limit')
        references=tuple(Reference(reader.string(),reader.target()) for _ in range(count))
    elif kind!=4:raise ValueError('Unsupported metadata query value kind')
    return Record(target,locale,definition,word,kind,raw,code,count,references)


def download_records(payload,definition):
    """Decode one complete 0x4F packet, without applying its values.

    A nonzero path instance supplies the definition for one value. Instance
    zero carries a bounded list of locale/definition pairs for the same target.
    Record words are local ordinals, never native identities or returned IDs.
    """
    if (not isinstance(payload,bytes) or not 8<=len(payload)<=65519
            or type(definition) is not int or not 0<=definition<=0xFFFF):
        raise ValueError('Invalid download metadata packet')
    fmt,size=struct.unpack_from('<II',payload)
    if fmt!=0x301 or size!=len(payload)-8:raise ValueError('Invalid download metadata framing')
    reader=_Reader(payload[8:]);target=reader.target()
    count=1 if definition else reader.fields('<H')[0]
    if not 1<=count<=64:raise ValueError('Download metadata field count limit')
    result=[];seen=set()
    for word in range(1,count+1):
        locale,=reader.fields('<H')
        field=definition or reader.fields('<H')[0]
        if not field or (locale,field) in seen:raise ValueError('Invalid or duplicate download metadata field')
        result.append(_value(reader,target,locale,field,word));seen.add((locale,field))
    if reader.position!=len(reader.data):raise ValueError('Trailing download metadata bytes')
    return tuple(result)


def records(data,*,max_records=MAX_RECORDS):
    """Consume full records, preserving IDs and string blobs without interpretation.

    Three observed zero DWORDs must stay zero. Numeric widths cover the SINT,
    INT and DINT forms. References retain their own target and qualifier words.
    Unknown layouts reject the whole result rather than publishing a prefix.
    """
    if (not isinstance(data,bytes) or len(data)>MAX_BYTES or type(max_records) is not int
            or not 1<=max_records<=MAX_RECORDS):raise ValueError('Invalid metadata record input or limit')
    reader=_Reader(data);result=[];seen=set()
    while reader.position<len(data):
        if len(result)>=max_records:raise ValueError('Metadata query record limit')
        target=reader.target();locale,definition,word=reader.fields('<HHI')
        if not definition or not word or word in seen:raise ValueError('Invalid or duplicate metadata record identity')
        result.append(_value(reader,target,locale,definition,word));seen.add(word)
    return tuple(result)


def inventory(rows):
    """Aggregate detached records without names, qualifiers, IDs or values."""
    if not isinstance(rows,tuple) or len(rows)>MAX_RECORDS or any(not isinstance(r,Record) for r in rows):
        raise ValueError('Invalid metadata query inventory')
    kinds=Counter(r.kind for r in rows);codes=Counter(r.type_code for r in rows if r.type_code is not None)
    return dict(records=len(rows),definitions=len({r.definition for r in rows}),
        locales=len({r.locale_word for r in rows}),target_classes=len({r.target.class_id for r in rows}),
        value_kinds={str(k):v for k,v in sorted(kinds.items())},numeric_types={str(k):v for k,v in sorted(codes.items())},
        references=sum(len(r.references) for r in rows),string_blob_expansion=False,
        source_binding_verified=False,mac_verified=False,native_acceptance_verified=False,
        source_objects_resolved=False,program_query_0x50_resolved=False,payloads_exposed=False)
