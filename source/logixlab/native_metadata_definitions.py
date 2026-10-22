"""Read-only original v35 Metadata Definition names and logical instance IDs."""
from dataclasses import asdict,dataclass
import gzip
import io
import re
import struct
import zlib

from .model import ModelError
from .native_project import _hash,acd_stream

CLASS_ID=0x349
MAX_BYTES=128_000_000
MAX_RECORDS=200_000
MAX_DEFINITIONS=256
NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,61}\Z')


@dataclass(frozen=True)
class Definition:
    instance:int
    name:str

    def __post_init__(self):
        if type(self.instance) is not int or not 1<=self.instance<=0xffff or not isinstance(self.name,str) or not NAME.fullmatch(self.name):
            raise ModelError('Invalid native Metadata Definition identity')

    def attributes(self):
        raw=self.name.encode('ascii')
        return {1:struct.pack('<H',len(raw))+raw}


def definition_records(data):
    if not isinstance(data,bytes) or not 24<=len(data)<=MAX_BYTES:raise ModelError('Invalid Metadata Definition database size')
    size,pos=struct.unpack_from('<II',data,8);end=size+1
    if struct.unpack_from('<I',data)[0]+1!=len(data) or not 24<=pos<=min(end,4096) or end>len(data):
        raise ModelError('Unsupported Metadata Definition database bounds')
    rows=[];collection=False;records=0
    while pos<end:
        records+=1
        if records>MAX_RECORDS or end-pos<6:raise ModelError('Invalid Metadata Definition record count or header')
        kind,length=struct.unpack_from('<HI',data,pos)
        if kind not in (0xfafa,0xfdfd,0xfefe,0xfbbf) or not 6<=length<=end-pos:
            raise ModelError('Invalid Metadata Definition record bounds')
        record=data[pos+6:pos+length];pos+=length
        if kind!=0xfafa:continue
        if len(record)<148:raise ModelError('Truncated Metadata Definition component')
        used=struct.unpack_from('<I',record)[0]
        if not 148<=used<=len(record) or struct.unpack_from('<I',record,12)[0]:
            raise ModelError('Unsupported Metadata Definition component header')
        body=record[148:used]
        if len(body)<22:continue
        path=struct.unpack_from('<6H',body,10)
        if CLASS_ID in path[2::2]:raise ModelError('Scoped Metadata Definition records are unsupported')
        if path[0]!=CLASS_ID:continue
        component_type=struct.unpack_from('<H',record,10)[0]
        if path[2:]!=(0,0,0,0) or struct.unpack_from('<H',body,8)[0]:
            raise ModelError('Unsupported Metadata Definition path or stored format')
        if not path[1]:
            if collection or component_type or len(body)!=74:raise ModelError('Invalid or duplicate Metadata Definition collection')
            collection=True;continue
        if component_type!=256 or len(body)!=216 or body[78:90]!=struct.pack('<III',1,1,130):
            raise ModelError('Unsupported stored Metadata Definition Name field')
        count=struct.unpack_from('<H',body,90)[0]
        if not 1<=count<=124 or 92+count>len(body) or any(body[92+count:]):
            raise ModelError('Invalid Metadata Definition Name extent or padding')
        try:
            name=body[92:92+count].decode('ascii')
            header=record[24:148].decode('utf-16le')
        except UnicodeError as error:raise ModelError('Invalid Metadata Definition Name encoding') from error
        expected=name+'\0'*(62-len(name))
        if len(name)>62 or header!=expected:raise ModelError('Stored Metadata Definition names disagree')
        rows.append(Definition(path[1],name))
        if len(rows)>MAX_DEFINITIONS:raise ModelError('Metadata Definition inventory limit')
    if not collection:raise ModelError('Explicit Metadata Definition collection is required')
    if len({row.instance for row in rows})!=len(rows) or len({row.name.casefold() for row in rows})!=len(rows):
        raise ModelError('Conflicting active Metadata Definition records')
    return tuple(sorted(rows,key=lambda row:row.instance))


@dataclass(frozen=True)
class NativeMetadataDefinitions:
    source_acd_sha256:str
    source_l5x_sha256:str
    rows:tuple=()

    def __post_init__(self):
        _hash(self.source_acd_sha256);_hash(self.source_l5x_sha256)
        if (not isinstance(self.rows,tuple) or len(self.rows)>MAX_DEFINITIONS or
                any(not isinstance(row,Definition) for row in self.rows) or
                len({row.instance for row in self.rows})!=len(self.rows) or
                len({row.name.casefold() for row in self.rows})!=len(self.rows)):
            raise ModelError('Conflicting native Metadata Definition inventory')
        object.__setattr__(self,'rows',tuple(sorted(self.rows,key=lambda row:row.instance)))

    @classmethod
    def from_acd(cls,path,source_l5x_sha256):
        _hash(source_l5x_sha256);digest,raw=acd_stream(path,'Comps.Dat',limit=16_000_000)
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw) as stream:
                data=stream.read(MAX_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid compressed Metadata Definition database') from error
        return cls(digest,source_l5x_sha256,definition_records(data))

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','definitions'} or
                manifest['source_l5x_sha256']!=source_l5x_sha256 or not isinstance(manifest['definitions'],list) or
                len(manifest['definitions'])>MAX_DEFINITIONS):raise ModelError('Invalid or stale Metadata Definition manifest')
        rows=[]
        for row in manifest['definitions']:
            if not isinstance(row,dict) or set(row)!={'instance','name'}:raise ModelError('Invalid Metadata Definition manifest row')
            rows.append(Definition(**row))
        return cls(manifest['source_acd_sha256'],source_l5x_sha256,tuple(rows))

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
                    definitions=[asdict(row) for row in self.rows])

    def class_attributes(self):
        return {1:struct.pack('<H',1),2:struct.pack('<I',max((r.instance for r in self.rows),default=0)),
                3:struct.pack('<I',len(self.rows))}

    def description(self):
        return dict(object_revision=1,maximum_instance=max((r.instance for r in self.rows),default=0),instance_count=len(self.rows),
            instance_list=True,name_attributes=True,metadata_services=False,native_source_bound=True,
            metadata_values=False,program_query_0x50=False,definition_writes=False,
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256)
