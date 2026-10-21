"""Source-bound diagnostic message definitions; no live fault/event generation."""
from dataclasses import dataclass
import gzip
import io
import struct
from types import MappingProxyType
import zlib

from .model import ModelError
from .native_project import _hash,acd_stream

CLASS_ID=0x3B2
MAX_BYTES=128_000_000
MAX_STREAM_BYTES=16_000_000
MAX_RECORDS=200_000
MAX_MESSAGES=1024


def _text(value,maximum,empty=False):
    return (isinstance(value,str) and int(not empty)<=len(value)<=maximum
            and all(32<=ord(char)<=126 for char in value))


@dataclass(frozen=True)
class DiagnosticMessage:
    instance: int
    message_id: str
    message_code: str
    revision: int

    def __post_init__(self):
        if (type(self.instance) is not int or not 1<=self.instance<65535 or
                not _text(self.message_id,40) or not _text(self.message_code,128,True) or
                type(self.revision) is not int or not 0<=self.revision<=65535):
            raise ModelError('Unsupported diagnostic message definition')

    def manifest(self):return dict(instance=self.instance,message_id=self.message_id,message_code=self.message_code,revision=self.revision)

    def attributes(self):
        counted=lambda text:bytes((len(text),))+text.encode('ascii')
        return {1:counted(self.message_id),2:counted(self.message_code),3:struct.pack('<H',self.revision)}


def message_records(data):
    """Read the bounded format-0, 270-byte fixed diagnostic definition profile."""
    if not isinstance(data,bytes) or not 24<=len(data)<=MAX_BYTES:raise ModelError('Invalid diagnostic database size')
    size,pos=struct.unpack_from('<II',data,8);end=size+1
    if struct.unpack_from('<I',data)[0]+1!=len(data) or not 24<=pos<=min(end,4096) or end>len(data):
        raise ModelError('Unsupported diagnostic database bounds')
    rows=[];ids=set();names=set();collection=False;records=0
    while pos<end:
        records+=1
        if records>MAX_RECORDS or end-pos<6:raise ModelError('Invalid diagnostic record header')
        kind,length=struct.unpack_from('<HI',data,pos)
        if kind not in (0xFAFA,0xFDFD,0xFEFE,0xFBBF) or not 6<=length<=end-pos:
            raise ModelError('Invalid diagnostic record bounds')
        record=memoryview(data)[pos+6:pos+length];pos+=length
        if kind!=0xFAFA:continue
        if len(record)<148:raise ModelError('Truncated diagnostic component')
        used=struct.unpack_from('<I',record)[0]
        if not 148<=used<=len(record) or struct.unpack_from('<I',record,12)[0]:
            raise ModelError('Unsupported diagnostic component header')
        body=record[148:used]
        if len(body)<22:continue
        path=struct.unpack_from('<6H',body,10)
        if path[0]!=CLASS_ID:
            if path[2]==CLASS_ID:raise ModelError('Scoped diagnostic definitions are unsupported')
            continue
        component=struct.unpack_from('<H',record,10)[0];version=struct.unpack_from('<H',body,8)[0]
        if any(path[2:]):raise ModelError('Unsupported diagnostic child path')
        if path[1]==0 and component==version==0 and len(body)==74:
            if collection:raise ModelError('Ambiguous diagnostic collection')
            collection=True;continue
        if (component!=256 or version!=0 or len(body)!=270 or
                struct.unpack_from('<I',body,74)[0]!=0xC4 or struct.unpack_from('<I',body,86)[0]!=172):
            raise ModelError('Unsupported diagnostic definition profile')
        values=[]
        for start,width in ((90,40),(131,128)):
            count=body[start]
            if count>width or any(body[start+1+count:start+1+width]):raise ModelError('Invalid diagnostic string extent or padding')
            try:values.append(bytes(body[start+1:start+1+count]).decode('ascii'))
            except UnicodeError as error:raise ModelError('Invalid diagnostic ASCII string') from error
        raw=bytes(record[24:148]);stop=next((i for i in range(0,124,2) if raw[i:i+2]==bytes(2)),None)
        if stop is None:raise ModelError('Unterminated diagnostic component name')
        try:name=raw[:stop].decode('utf-16le')
        except UnicodeError as error:raise ModelError('Invalid diagnostic component name') from error
        if name!=values[0]:raise ModelError('Diagnostic ID differs from its component name')
        if path[1] in ids or name.casefold() in names:raise ModelError('Ambiguous diagnostic identity')
        ids.add(path[1]);names.add(name.casefold())
        if len(rows)>=MAX_MESSAGES:raise ModelError('Diagnostic definition count limit')
        rows.append(DiagnosticMessage(path[1],*values,struct.unpack_from('<H',body,260)[0]).manifest())
    if not collection:raise ModelError('Explicit diagnostic collection required')
    return rows


@dataclass(frozen=True,init=False)
class NativeDiagnostics:
    source_acd_sha256: str
    source_l5x_sha256: str
    rows: tuple[DiagnosticMessage,...]
    by_instance: object

    def __init__(self,source_acd_sha256,source_l5x_sha256,messages):
        _hash(source_acd_sha256);_hash(source_l5x_sha256)
        if not isinstance(messages,(list,tuple)) or len(messages)>MAX_MESSAGES:raise ModelError('Invalid diagnostic inventory')
        found={};names=set()
        for value in messages:
            if not isinstance(value,dict) or set(value)!={'instance','message_id','message_code','revision'}:
                raise ModelError('Invalid diagnostic manifest fields')
            row=DiagnosticMessage(**value)
            if row.instance in found or row.message_id.casefold() in names:raise ModelError('Duplicate diagnostic identity')
            found[row.instance]=row;names.add(row.message_id.casefold())
        object.__setattr__(self,'source_acd_sha256',source_acd_sha256)
        object.__setattr__(self,'source_l5x_sha256',source_l5x_sha256)
        object.__setattr__(self,'rows',tuple(found[key] for key in sorted(found)))
        object.__setattr__(self,'by_instance',MappingProxyType(dict(found)))

    @classmethod
    def from_acd(cls,path,source_l5x_sha256):
        _hash(source_l5x_sha256);digest,raw=acd_stream(path,'Comps.Dat',limit=MAX_STREAM_BYTES)
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw) as reader:
                data=reader.read(MAX_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid compressed diagnostic database') from error
        return cls(digest,source_l5x_sha256,message_records(data))

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','messages'} or
                manifest['source_l5x_sha256']!=source_l5x_sha256 or not isinstance(manifest['messages'],list)):
            raise ModelError('Invalid or stale diagnostic manifest')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256,manifest['messages'])

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,messages=[row.manifest() for row in self.rows])

    def description(self):
        return dict(bound=True,class_id=CLASS_ID,messages=len(self.rows),source='Original ACD diagnostic definitions, format 0/body 270',
            read_attributes=[1,2,3],counted_ascii_bytes=1,live_faults=False,event_generation=False,configuration_writes=False,
            captured_definitions_replayed=False,source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256)
