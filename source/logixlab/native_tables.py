"""Original controller Data Table identities for temporary download checks.

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

    def __post_init__(self):
        if (type(self.instance) is not int or not 1<=self.instance<65535
                or not isinstance(self.name,str) or not 1<=len(self.name)<=61
                or any(not 33<=ord(char)<=126 for char in self.name)
                or type(self.body_bytes) is not int or not MIN_BODY_BYTES<=self.body_bytes<=MAX_BODY_BYTES):
            raise ModelError('Unsupported source Data Table identity')

    def manifest(self):return dict(instance=self.instance,name=self.name,body_bytes=self.body_bytes)


def table_paths(data):
    """Retain a complete bounded controller Table inventory with original IDs."""
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
        if path[0]==0x68 and path[2]==0x6A:
            if path[1] and not any(path[3:]) and component==version==0 and len(body)==74:
                if path[1] in scoped_collections:raise ModelError('Ambiguous scoped Data Table collection')
                scoped_collections.add(path[1]);continue
            raise ModelError('Scoped source Data Tables are unsupported')
        if path[0]!=0x6A:continue
        if any(path[2:]):raise ModelError('Unsupported source Data Table child path')
        if path[1]==0 and component==version==0:
            if len(body)!=74:raise ModelError('Unsupported source Data Table collection profile')
            if collection:raise ModelError('Ambiguous source Data Table collection')
            collection=True;continue
        if component!=256 or version!=38:raise ModelError('Unsupported source Data Table body profile')
        raw=bytes(record[24:148]);stop=next((i for i in range(0,124,2) if raw[i:i+2]==bytes(2)),None)
        if stop is None:raise ModelError('Unterminated source Data Table name')
        try:name=raw[:stop].decode('utf-16le')
        except UnicodeError as error:raise ModelError('Invalid source Data Table name') from error
        row=TableIdentity(path[1],name,len(body))
        if row.instance in found or name.casefold() in names:raise ModelError('Ambiguous historical source Data Table identity')
        if len(found)>=MAX_TABLES:raise ModelError('Source Data Table count limit')
        found[row.instance]=row;names.add(name.casefold())
    if not collection:raise ModelError('Explicit source Data Table collection required')
    return [found[key].manifest() for key in sorted(found)]


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
            if not isinstance(value,dict) or set(value)!={'instance','name','body_bytes'}:
                raise ModelError('Invalid source Data Table manifest fields')
            row=TableIdentity(**value)
            if row.instance in found or row.name.casefold() in names:raise ModelError('Duplicate source Data Table identity')
            found[row.instance]=row;names.add(row.name.casefold())
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

    def description(self):
        return dict(bound=True,tables=len(self.rows),source='ACD Comps.Dat Data Table format 38; identity comparison only',
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
            public_catalog_extended=False,compiled_addresses=False,storage_mapping=False,values_exposed=False,install_authority=False)
