"""Bounded structural inspection of the observed compressed device batch.

No network access, record dispatch, model writes or signature verification.
Only the observed definite-length CMS/zlib profile is supported.
"""
from collections import Counter
from dataclasses import dataclass
import re
import struct
import zlib

MAX_ENCODED_BYTES=262144
MAX_EXPANDED_BYTES=2*1024*1024
MAX_RECORDS=4096
MAX_RECORD_BYTES=65519
MAX_SCOPES=16
COMPRESSED_OID=bytes.fromhex('2a864886f70d0109100109')
ZLIB_OID=bytes.fromhex('2a864886f70d0109100308')
CONTENT_OID=bytes.fromhex('2a864886f70d0109100110')


class PayloadError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)


class _DER:
    def __init__(self,data):self.data=memoryview(data);self.offset=0

    def take(self,tag):
        data=self.data;offset=self.offset
        if offset+2>len(data) or data[offset]!=tag:raise PayloadError('invalid_container')
        size=data[offset+1];offset+=2
        if size&0x80:
            count=size&0x7F
            if not 1<=count<=3 or offset+count>len(data) or data[offset]==0:raise PayloadError('invalid_container_length')
            size=int.from_bytes(data[offset:offset+count],'big');offset+=count
            if size<128:raise PayloadError('invalid_container_length')
        if offset+size>len(data):raise PayloadError('truncated_container')
        self.offset=offset+size
        return data[offset:self.offset]

    def child(self,tag):return _DER(self.take(tag))

    def expect(self,tag,value):
        if self.take(tag)!=value:raise PayloadError('unsupported_container_profile')

    def end(self):
        if self.offset!=len(self.data):raise PayloadError('trailing_container_data')


@dataclass(frozen=True)
class Scope:
    class_id:int
    instance:int
    attribute:int|None=None
    symbolic:bool=False


@dataclass(frozen=True)
class Record:
    service:int
    scopes:tuple[Scope,...]
    request:bytes


def record_path(raw):
    """Preserve arbitrary object parents for inspection, never live routing."""
    offset=0;scopes=[];cls=instance=attribute=None;symbolic=False
    while offset<len(raw):
        code=raw[offset];offset+=1
        if code==0x91:
            if cls is None or instance is None or offset>=len(raw):raise PayloadError('invalid_record_path')
            size=raw[offset];offset+=1
            if offset+size+size%2>len(raw):raise PayloadError('invalid_record_path')
            try:name=raw[offset:offset+size].decode('ascii')
            except UnicodeDecodeError:raise PayloadError('invalid_record_path') from None
            if not re.fullmatch(r'[A-Za-z_][\w:]*',name) or size%2 and raw[offset+size]!=0:raise PayloadError('invalid_record_path')
            offset+=size+size%2;symbolic=True;continue
        if code not in (0x20,0x21,0x22,0x24,0x25,0x26,0x28,0x29,0x2A,0x30,0x31,0x32):raise PayloadError('unsupported_record_path')
        width=(1,2,4)[code&3]
        if width>1:
            if offset>=len(raw) or raw[offset]!=0:raise PayloadError('invalid_record_path')
            offset+=1
        if offset+width>len(raw):raise PayloadError('invalid_record_path')
        value=int.from_bytes(raw[offset:offset+width],'little');offset+=width;kind=code&0xFC
        if kind==0x20:
            if cls is not None:
                if instance is None or attribute is not None or symbolic:raise PayloadError('invalid_parent_scope')
                scopes.append(Scope(cls,instance))
            if len(scopes)>=MAX_SCOPES:raise PayloadError('record_scope_limit')
            cls=value;instance=attribute=None;symbolic=False
        elif kind==0x24:
            if cls is None or instance is not None or symbolic or attribute is not None:raise PayloadError('invalid_record_path')
            instance=value
        elif kind==0x30:
            if cls is None or instance is None or attribute is not None or symbolic:raise PayloadError('invalid_record_path')
            attribute=value
        else:
            if cls is None or instance is None:raise PayloadError('invalid_record_path')
            symbolic=True
    if cls is None or instance is None:raise PayloadError('invalid_record_path')
    scopes.append(Scope(cls,instance,attribute,symbolic))
    return tuple(scopes)


def records(raw):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_EXPANDED_BYTES:raise PayloadError('expanded_size_limit')
    result=[];offset=0
    while offset<len(raw):
        if len(result)>=MAX_RECORDS:raise PayloadError('record_count_limit')
        if offset+4>len(raw):raise PayloadError('truncated_record_length')
        size=struct.unpack_from('<I',raw,offset)[0];offset+=4
        if not 2<=size<=MAX_RECORD_BYTES or offset+size>len(raw):raise PayloadError('invalid_record_length')
        request=raw[offset:offset+size];offset+=size;end=2+2*request[1]
        if not 1<=request[0]<=0x7F or end>len(request):raise PayloadError('invalid_record_header')
        result.append(Record(request[0],record_path(request[2:end]),request))
    return tuple(result)


def decode(raw,expected_bytes):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_ENCODED_BYTES:raise PayloadError('encoded_size_limit')
    if type(expected_bytes) is not int or not 1<=expected_bytes<=MAX_EXPANDED_BYTES:raise PayloadError('expanded_size_limit')
    root=_DER(raw);outer=root.child(0x30);root.end();outer.expect(6,COMPRESSED_OID)
    explicit=outer.child(0xA0);outer.end();body=explicit.child(0x30);explicit.end();body.expect(2,b'\0')
    algorithm=body.child(0x30);algorithm.expect(6,ZLIB_OID)
    if algorithm.offset<len(algorithm.data):algorithm.expect(5,b'')
    algorithm.end();content=body.child(0x30);body.end();content.expect(6,CONTENT_OID)
    explicit=content.child(0xA0);content.end();compressed=explicit.take(4);explicit.end()
    try:
        decoder=zlib.decompressobj();expanded=decoder.decompress(compressed,expected_bytes+1)
    except zlib.error:raise PayloadError('invalid_compressed_stream') from None
    if len(expanded)!=expected_bytes:raise PayloadError('expanded_size_mismatch')
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:raise PayloadError('incomplete_or_trailing_stream')
    return records(expanded)


def summary(batch,expanded_bytes):
    counts=Counter((r.service,r.scopes[-1].class_id) for r in batch)
    return {'status':'decoded','expanded_bytes':expanded_bytes,'record_count':len(batch),
            'scoped_records':sum(len(r.scopes)>1 for r in batch),
            'operations':[{'service':s,'class_id':c,'count':n} for (s,c),n in sorted(counts.items())],
            'execution_supported':False,'records_executed':0,'payloads_exposed':False,
            'signature_verified':False}
