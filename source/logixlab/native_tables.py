"""Original controller and Program Data Table identities for download checks.

Format-38 body bytes remain opaque. Their length is retained as source profile
metadata, never interpreted as saved values, storage layout or native addresses.
"""
from dataclasses import dataclass
import gzip
import io
import struct
from types import MappingProxyType
import zlib
from .model import ModelError
from .native_project import _hash,acd_stream

MAX_BYTES=128_000_000
MAX_STREAM_BYTES=16_000_000
MAX_RECORDS=200_000
MAX_TABLES=1024
MIN_BODY_BYTES=417
MAX_BODY_BYTES=416+1024*1024


@dataclass(frozen=True)
class TableIdentity:
    instance: int
    name: str
    body_bytes: int
    program_instance: int = 0

    def __post_init__(self):
        if (type(self.instance) is not int or not 1<=self.instance<65535
                or type(self.program_instance) is not int or not 0<=self.program_instance<65535
                or not isinstance(self.name,str) or not 1<=len(self.name)<=61
                or any(not 33<=ord(char)<=126 for char in self.name)
                or type(self.body_bytes) is not int or not MIN_BODY_BYTES<=self.body_bytes<=MAX_BODY_BYTES):
            raise ModelError('Unsupported source Data Table identity')

    @property
    def key(self):return (self.program_instance,self.instance) if self.program_instance else self.instance

    def manifest(self):
        row=dict(instance=self.instance,name=self.name,body_bytes=self.body_bytes)
        if self.program_instance:row['program_instance']=self.program_instance
        return row


def table_paths(data):
    """Retain bounded Table identities without collapsing their Program scopes."""
    if not isinstance(data,bytes) or not 24<=len(data)<=MAX_BYTES:raise ModelError('Invalid source Data Table database size')
    size,pos=struct.unpack_from('<II',data,8);end=size+1
    if struct.unpack_from('<I',data)[0]+1!=len(data) or not 24<=pos<=min(end,4096) or end>len(data):
        raise ModelError('Unsupported source Data Table database bounds')
    found={};names=set();records=0;collection=False;scoped_collections=set()
    while pos<end:
        records+=1
        if records>MAX_RECORDS or end-pos<6:raise ModelError('Invalid source Data Table record header')
        kind,length=struct.unpack_from('<HI',data,pos)
        if kind not in (0xFAFA,0xFDFD,0xFEFE,0xFBBF) or not 6<=length<=end-pos:
            raise ModelError('Invalid source Data Table record bounds')
        record=memoryview(data)[pos+6:pos+length];pos+=length
        if kind!=0xFAFA:continue
        if len(record)<148:raise ModelError('Truncated source Data Table component')
        used=struct.unpack_from('<I',record)[0]
        if not 148<=used<=len(record) or struct.unpack_from('<I',record,12)[0]:
            raise ModelError('Unsupported source Data Table component header')
        body=record[148:used]
        if len(body)<22:continue
        path=struct.unpack_from('<6H',body,10)
        component=struct.unpack_from('<H',record,10)[0];version=struct.unpack_from('<H',body,8)[0]
        program=0
        if path[0]==0x68 and path[2]==0x6A:
            if not 1<=path[1]<65535 or any(path[4:]):raise ModelError('Unsupported scoped Data Table path')
            program=path[1];instance=path[3]
            if not instance and component==version==0 and len(body)==74:
                if path[1] in scoped_collections:raise ModelError('Ambiguous scoped Data Table collection')
                scoped_collections.add(path[1]);continue
        elif path[0]==0x6A:
            if any(path[2:]):raise ModelError('Unsupported source Data Table child path')
            instance=path[1]
        else:continue
        if not program and instance==0 and component==version==0:
            if len(body)!=74:raise ModelError('Unsupported source Data Table collection profile')
            if collection:raise ModelError('Ambiguous source Data Table collection')
            collection=True;continue
        if component!=256 or version!=38:raise ModelError('Unsupported source Data Table body profile')
        raw=bytes(record[24:148]);stop=next((i for i in range(0,124,2) if raw[i:i+2]==bytes(2)),None)
        if stop is None:raise ModelError('Unterminated source Data Table name')
        try:name=raw[:stop].decode('utf-16le')
        except UnicodeError as error:raise ModelError('Invalid source Data Table name') from error
        row=TableIdentity(instance,name,len(body),program);name_key=(program,name.casefold())
        if row.key in found or name_key in names:raise ModelError('Ambiguous historical source Data Table identity')
        if len(found)>=MAX_TABLES:raise ModelError('Source Data Table count limit')
        found[row.key]=row;names.add(name_key)
    if not collection:raise ModelError('Explicit source Data Table collection required')
    if any(row.program_instance and row.program_instance not in scoped_collections for row in found.values()):
        raise ModelError('Explicit scoped Data Table collection required')
    return [row.manifest() for row in sorted(found.values(),key=lambda row:(row.program_instance,row.instance))]


@dataclass(frozen=True,init=False)
class NativeTables:
    source_acd_sha256: str
    source_l5x_sha256: str
    rows: tuple[TableIdentity,...]
    by_instance: object

    def __init__(self,source_acd_sha256,source_l5x_sha256,tables):
        _hash(source_acd_sha256);_hash(source_l5x_sha256)
        if not isinstance(tables,(list,tuple)) or len(tables)>MAX_TABLES:raise ModelError('Invalid source Data Table inventory')
        found={};names=set()
        for value in tables:
            if (not isinstance(value,dict) or not {'instance','name','body_bytes'}<=value.keys()
                    or value.keys()-{'instance','name','body_bytes','program_instance'}):
                raise ModelError('Invalid source Data Table manifest fields')
            row=TableIdentity(**value)
            name_key=(row.program_instance,row.name.casefold())
            if row.key in found or name_key in names:raise ModelError('Duplicate source Data Table identity')
            found[row.key]=row;names.add(name_key)
        object.__setattr__(self,'source_acd_sha256',source_acd_sha256)
        object.__setattr__(self,'source_l5x_sha256',source_l5x_sha256)
        object.__setattr__(self,'rows',tuple(sorted(found.values(),key=lambda row:(row.program_instance,row.instance))))
        object.__setattr__(self,'by_instance',MappingProxyType(dict(found)))

    @classmethod
    def from_acd(cls,path,source_l5x_sha256):
        _hash(source_l5x_sha256);digest,raw=acd_stream(path,'Comps.Dat',limit=MAX_STREAM_BYTES)
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw) as reader:
                data=reader.read(MAX_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid compressed source Data Table inventory') from error
        return cls(digest,source_l5x_sha256,table_paths(data))

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','tables'}
                or manifest['source_l5x_sha256']!=source_l5x_sha256 or not isinstance(manifest['tables'],list)):
            raise ModelError('Invalid or stale source Data Table manifest')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256,manifest['tables'])

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
                    tables=[r.manifest() for r in self.rows])

    def require_parents(self,symbols):
        if any(row.program_instance for row in self.rows):
            if (symbols is None or (symbols.source_acd_sha256,symbols.source_l5x_sha256)!=
                    (self.source_acd_sha256,self.source_l5x_sha256)
                    or any(row.program_instance and row.program_instance not in symbols.program_ids for row in self.rows)):
                raise ModelError('Scoped Data Tables require matching original Program bindings')

    def description(self):
        return dict(bound=True,tables=len(self.rows),scoped_tables=sum(bool(row.program_instance) for row in self.rows),
            source='ACD Comps.Dat Data Table format 38; identity comparison only',
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
            public_catalog_extended=False,compiled_addresses=False,storage_mapping=False,values_exposed=False,install_authority=False)
