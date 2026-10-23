"""Original Comps.Dat Symbol identities omitted by TagInfo, for download checks.

These records alone add no runtime tags, addresses, aliases or values. A separate
validated reference catalog may use the explicit Program/Task data names.
The supported source profile is format 63/body size 700.
"""
from dataclasses import dataclass
import gzip
import io
import re
import struct
from types import MappingProxyType
import zlib
from .model import ModelError
from .native_project import _hash,acd_stream
from .native_symbols import NativeSymbols

MAX_BYTES=128_000_000
MAX_STREAM_BYTES=16_000_000
MAX_RECORDS=200_000
MAX_AUXILIARY=1024
COMPONENT_TYPES=frozenset((256,264,1288))
REFERENCE_NAME=re.compile(r'(?:Program|Task|Routine):[A-Za-z_][A-Za-z0-9_]{0,39}\Z')


@dataclass(frozen=True)
class AuxiliarySymbol:
    program_instance: int
    instance: int
    name: str
    component_type: int
    reference_name: str | None = None

    def __post_init__(self):
        if (type(self.program_instance) is not int or not 0<=self.program_instance<65535
                or type(self.instance) is not int or not 1<=self.instance<65535
                or type(self.component_type) is not int or self.component_type not in COMPONENT_TYPES
                or not isinstance(self.name,str) or not 1<=len(self.name)<=61
                or any(not 33<=ord(char)<=126 for char in self.name)):
            raise ModelError('Unsupported auxiliary Symbol identity')
        if self.reference_name is not None and (self.component_type!=256 or
                not re.fullmatch(r'\$[0-9a-fA-F]{8}\$',self.name) or
                not isinstance(self.reference_name,str) or not REFERENCE_NAME.fullmatch(self.reference_name)
                or self.reference_name.startswith('Routine:')!=bool(self.program_instance)):
            raise ModelError('Unsupported native object reference Symbol')

    def manifest(self):
        value=dict(program_instance=self.program_instance,instance=self.instance,name=self.name,component_type=self.component_type)
        if self.reference_name is not None:value['reference_name']=self.reference_name
        return value


def symbol_paths(data,native_symbols):
    """Require all known names/paths before retaining any auxiliary identities."""
    if not isinstance(native_symbols,NativeSymbols) or native_symbols.program_inventory_error is not None:
        raise ModelError('Auxiliary Symbols require complete native Program identities')
    known={(s.program_instance,s.instance):s.name for s in native_symbols.by_key.values()}
    if not isinstance(data,bytes) or not 24<=len(data)<=MAX_BYTES:
        raise ModelError('Invalid auxiliary Symbol database size')
    size,pos=struct.unpack_from('<II',data,8);end=size+1
    if struct.unpack_from('<I',data)[0]+1!=len(data) or not 24<=pos<=min(end,4096) or end>len(data):
        raise ModelError('Unsupported auxiliary Symbol database bounds')
    found={};names=set();rows=[];records=0
    while pos<end:
        records+=1
        if records>MAX_RECORDS or end-pos<6:raise ModelError('Invalid auxiliary Symbol record header')
        kind,length=struct.unpack_from('<HI',data,pos)
        if kind not in (0xFAFA,0xFDFD,0xFEFE,0xFBBF) or not 6<=length<=end-pos:
            raise ModelError('Invalid auxiliary Symbol record bounds')
        record=memoryview(data)[pos+6:pos+length];pos+=length
        if kind!=0xFAFA:continue
        if len(record)<148:raise ModelError('Truncated auxiliary Symbol component')
        used=struct.unpack_from('<I',record)[0]
        if not 148<=used<=len(record) or struct.unpack_from('<I',record,12)[0]:
            raise ModelError('Unsupported auxiliary Symbol component header')
        body=record[148:used]
        if len(body)<22:continue
        path=struct.unpack_from('<6H',body,10)
        if path[0]==0x6B:
            if any(path[2:]):raise ModelError('Unsupported controller Symbol source path')
            parent,instance=0,path[1]
        elif path[0]==0x68 and path[2]==0x6B:
            if not path[1] or any(path[4:]) or path[1] not in native_symbols.program_ids:
                raise ModelError('Unknown or unsupported auxiliary Symbol Program parent')
            parent,instance=path[1],path[3]
        else:continue
        component=struct.unpack_from('<H',record,10)[0];version=struct.unpack_from('<H',body,8)[0]
        if instance==0 and component==version==0:continue  # Explicit collection record.
        if version!=63 or len(body)!=700:raise ModelError('Unsupported auxiliary Symbol body profile')
        raw=bytes(record[24:148]);stop=next((i for i in range(0,124,2) if raw[i:i+2]==bytes(2)),None)
        if stop is None:raise ModelError('Unterminated auxiliary Symbol name')
        try:name=raw[:stop].decode('utf-16le')
        except UnicodeError as error:raise ModelError('Invalid auxiliary Symbol name') from error
        key=(parent,instance);reference_name=None
        if (key not in known and component==256 and re.fullmatch(r'\$[0-9a-fA-F]{8}\$',name)
                and (parent==0 and (bytes(body[92:100])==b'Program:' or bytes(body[92:97])==b'Task:')
                     or parent!=0 and bytes(body[92:100])==b'Routine:')):
            size=struct.unpack_from('<H',body,90)[0]
            if not 6<=size<=48 or body[92+size]!=0:raise ModelError('Invalid native reference Symbol data name bounds')
            try:reference_name=bytes(body[92:92+size]).decode('ascii')
            except UnicodeError as error:raise ModelError('Invalid native reference Symbol data name') from error
        row=AuxiliarySymbol(parent,instance,name,component,reference_name);named=(parent,name.casefold())
        if key in found or named in names:raise ModelError('Ambiguous historical auxiliary Symbol identity')
        found[key]=name;names.add(named)
        if key in known:
            if known[key].casefold()!=name.casefold():raise ModelError('TagInfo and component Symbol names disagree')
        else:
            if len(rows)>=MAX_AUXILIARY:raise ModelError('Auxiliary Symbol count limit')
            rows.append(row.manifest())
    if not known.keys()<=found.keys():raise ModelError('Incomplete TagInfo Symbol source coverage')
    return rows


@dataclass(frozen=True,init=False)
class NativeAuxiliarySymbols:
    source_acd_sha256: str
    source_l5x_sha256: str
    rows: tuple[AuxiliarySymbol,...]
    by_instance: object

    def __init__(self,source_acd_sha256,source_l5x_sha256,symbols):
        _hash(source_acd_sha256);_hash(source_l5x_sha256)
        if not isinstance(symbols,(list,tuple)) or len(symbols)>MAX_AUXILIARY:raise ModelError('Invalid auxiliary Symbol inventory')
        found={};names=set()
        for value in symbols:
            if (not isinstance(value,dict) or not {'program_instance','instance','name','component_type'}<=value.keys()
                    or value.keys()-{'program_instance','instance','name','component_type','reference_name'}):
                raise ModelError('Invalid auxiliary Symbol manifest fields')
            row=AuxiliarySymbol(**value);key=(row.program_instance,row.instance);named=(row.program_instance,row.name.casefold())
            if key in found or named in names:raise ModelError('Duplicate auxiliary Symbol identity')
            found[key]=row;names.add(named)
        object.__setattr__(self,'source_acd_sha256',source_acd_sha256)
        object.__setattr__(self,'source_l5x_sha256',source_l5x_sha256)
        object.__setattr__(self,'rows',tuple(found[key] for key in sorted(found)))
        object.__setattr__(self,'by_instance',MappingProxyType(dict(found)))

    def require_parents(self,native_symbols):
        if (not isinstance(native_symbols,NativeSymbols) or native_symbols.program_inventory_error is not None
                or (native_symbols.source_acd_sha256,native_symbols.source_l5x_sha256)!=(self.source_acd_sha256,self.source_l5x_sha256)):
            raise ModelError('Auxiliary Symbols require matching native Symbol bindings')
        known={(s.program_instance,s.instance) for s in native_symbols.by_key.values()}
        names={(s.program_instance,s.name.casefold()) for s in native_symbols.by_key.values()}
        if any(r.program_instance and r.program_instance not in native_symbols.program_ids for r in self.rows):
            raise ModelError('Auxiliary Symbol Program parent is unavailable')
        if known&self.by_instance.keys():raise ModelError('Auxiliary Symbol identity conflicts with TagInfo')
        if any((r.program_instance,r.name.casefold()) in names for r in self.rows):
            raise ModelError('Auxiliary Symbol name conflicts with TagInfo')

    @classmethod
    def from_acd(cls,path,source_l5x_sha256,native_symbols):
        _hash(source_l5x_sha256)
        if not isinstance(native_symbols,NativeSymbols) or native_symbols.source_l5x_sha256!=source_l5x_sha256:
            raise ModelError('Auxiliary Symbols require matching source L5X bytes')
        digest,raw=acd_stream(path,'Comps.Dat',limit=MAX_STREAM_BYTES)
        if digest!=native_symbols.source_acd_sha256:raise ModelError('Auxiliary Symbol ACD source differs')
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw) as reader:
                data=reader.read(MAX_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid compressed auxiliary Symbol inventory') from error
        result=cls(digest,source_l5x_sha256,symbol_paths(data,native_symbols));result.require_parents(native_symbols)
        return result

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','symbols'}
                or manifest['source_l5x_sha256']!=source_l5x_sha256 or not isinstance(manifest['symbols'],list)):
            raise ModelError('Invalid or stale auxiliary Symbol manifest')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256,manifest['symbols'])

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
                    symbols=[r.manifest() for r in self.rows])

    def description(self):
        return dict(bound=True,symbols=len(self.rows),source='ACD Comps.Dat Symbol format 63 identities and explicit reference data names',
            reference_data_names=sum(row.reference_name is not None for row in self.rows),
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
            runtime_tags_exposed=False,compiled_addresses=False,alias_semantics=False,values_exposed=False,install_authority=False)
