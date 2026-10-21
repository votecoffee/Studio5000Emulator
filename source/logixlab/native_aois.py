"""Source-bound v35 UDI Definition IDs; no compiled AOI code or addresses."""
from dataclasses import dataclass
import gzip
import io
import re
import struct
from types import MappingProxyType
import zlib

from .model import ModelError
from .native_project import acd_stream,_hash

MAX_BYTES=128_000_000
MAX_RECORDS=200_000
MAX_DEFINITIONS=1024
NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')


def expected_names(names):
    if (not isinstance(names,(list,tuple)) or len(names)>MAX_DEFINITIONS
            or any(not isinstance(n,str) or not NAME.fullmatch(n) for n in names)):
        raise ModelError('Invalid expected AOI names')
    expected={n.casefold():n for n in names}
    if len(expected)!=len(names):raise ModelError('Duplicate expected AOI names')
    return expected


def definition_paths(data,names):
    expected=expected_names(names)
    if not isinstance(data,bytes) or not 24<=len(data)<=MAX_BYTES:raise ModelError('Invalid AOI database size')
    size,pos=struct.unpack_from('<II',data,8);end=size+1
    if struct.unpack_from('<I',data)[0]+1!=len(data) or not 24<=pos<=min(end,4096) or end>len(data):
        raise ModelError('Unsupported AOI database bounds')
    found={};records=0
    while pos<end:
        records+=1
        if records>MAX_RECORDS or end-pos<6:raise ModelError('Invalid AOI record count or header')
        kind,length=struct.unpack_from('<HI',data,pos)
        if kind not in (0xFAFA,0xFDFD,0xFEFE,0xFBBF) or not 6<=length<=end-pos:raise ModelError('Invalid AOI record bounds')
        record=memoryview(data)[pos+6:pos+length];pos+=length
        if kind!=0xFAFA:continue
        if len(record)<148:raise ModelError('Truncated AOI component header')
        used=struct.unpack_from('<I',record)[0]
        if not 148<=used<=len(record) or struct.unpack_from('<I',record,12)[0]:
            raise ModelError('Unsupported AOI component header')
        if struct.unpack_from('<H',record,10)[0]!=256:continue
        body=record[148:used]
        if len(body)<22:raise ModelError('Truncated AOI component body')
        version=struct.unpack_from('<H',body,8)[0];path=struct.unpack_from('<6H',body,10)
        if path[0]!=0x338 or path[2:]!=(0,0,0,0):continue
        raw=bytes(record[24:148]);stop=next((i for i in range(0,124,2) if raw[i:i+2]==bytes(2)),None)
        if stop is None:raise ModelError('Unterminated AOI component name')
        try:name=raw[:stop].decode('utf-16le').casefold()
        except UnicodeError as error:raise ModelError('Invalid AOI component name') from error
        if name not in expected:continue
        if version!=21 or not path[1]:raise ModelError('Unsupported AOI format or ID')
        if name in found or path[1] in found.values():raise ModelError('Ambiguous historical AOI identity')
        found[name]=path[1]
    if found.keys()!=expected.keys():raise ModelError('Incomplete AOI identities')
    return [{'name':expected[name],'instance':found[name]} for name in sorted(found)]


@dataclass(frozen=True)
class NativeAOIs:
    source_acd_sha256: str
    source_l5x_sha256: str
    definitions: object

    def __init__(self,source_acd_sha256,source_l5x_sha256,definitions):
        _hash(source_acd_sha256);_hash(source_l5x_sha256)
        if not isinstance(definitions,(list,tuple)) or len(definitions)>MAX_DEFINITIONS:raise ModelError('Invalid native AOI inventory')
        names={};ids=set()
        for row in definitions:
            if not isinstance(row,dict) or set(row)!={'name','instance'}:raise ModelError('Invalid AOI manifest fields')
            name=row['name'];instance=row['instance']
            if (not isinstance(name,str) or not NAME.fullmatch(name) or type(instance) is not int or not 1<=instance<=65535
                    or name.casefold() in names or instance in ids):raise ModelError('Invalid or repeated native AOI identity')
            names[name.casefold()]=(name,instance);ids.add(instance)
        object.__setattr__(self,'source_acd_sha256',source_acd_sha256)
        object.__setattr__(self,'source_l5x_sha256',source_l5x_sha256)
        object.__setattr__(self,'definitions',MappingProxyType(dict(names)))

    @classmethod
    def from_acd(cls,path,source_l5x_sha256,names):
        _hash(source_l5x_sha256);expected_names(names)
        digest,raw=acd_stream(path,'Comps.Dat',limit=16_000_000)
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw) as stream:
                data=stream.read(MAX_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid compressed AOI inventory') from error
        return cls(digest,source_l5x_sha256,definition_paths(data,names))

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','definitions'}
                or manifest['source_l5x_sha256']!=source_l5x_sha256 or not isinstance(manifest['definitions'],list)):
            raise ModelError('Invalid or mismatched native AOI manifest')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256,manifest['definitions'])

    def manifest(self):
        return {'source_acd_sha256':self.source_acd_sha256,'source_l5x_sha256':self.source_l5x_sha256,
                'definitions':[{'name':name,'instance':instance} for name,instance in sorted(self.definitions.values())]}

    def description(self):
        return {'bound':True,'complete':True,'definitions':len(self.definitions),
                'source':'ACD Comps.Dat UDI Definition format 21 and complete L5X AOI declarations',
                'source_acd_sha256':self.source_acd_sha256,'source_l5x_sha256':self.source_l5x_sha256,
                'compiled_addresses':False,'definition_upload':False,'native_aoi_execution':False}
