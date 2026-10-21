"""Original ACD identities for the observed Program-scoped Executable format.

The owned v35 source establishes component type 256, header version 0 and
body format 54. Its six UINT16 logical words describe Program 0x68 parent
and Executable 0x6D child IDs. Nothing here reads compiled code or addresses,
generates IDs from source order, or grants native edit/execution authority.
The unprotected 371-byte body profile also retains its original Type word;
other body layouts retain identities without inventing that field.
"""
from dataclasses import dataclass
import gzip
import io
import re
import struct
from types import MappingProxyType
from typing import Mapping
import zlib

from .model import ModelError
from .native_project import _hash, acd_stream
from .native_symbols import NativeSymbols


MAX_ROUTINES = 16_384
MAX_PROGRAMS = 4096
MAX_BYTES = 128_000_000
MAX_RECORDS = 200_000
MAX_STREAM_BYTES = 16_000_000
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')


def _expected(rows):
    if not isinstance(rows,(list,tuple)) or len(rows)>MAX_ROUTINES:
        raise ModelError('Invalid or excessive expected native routine inventory')
    result={}
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'program','name'}:
            raise ModelError('Invalid expected native routine fields')
        if any(not isinstance(row[field],str) or not NAME.fullmatch(row[field]) for field in ('program','name')):
            raise ModelError('Invalid expected native routine name')
        key=(row['program'].casefold(),row['name'].casefold())
        if key in result:raise ModelError('Duplicate expected native routine name')
        result[key]=dict(row)
    if len({program for program,_ in result})>MAX_PROGRAMS:
        raise ModelError('Expected native routine program limit')
    return result


def _programs(bindings):
    if not isinstance(bindings,Mapping) or len(bindings)>MAX_PROGRAMS:
        raise ModelError('Invalid native routine Program bindings')
    result={};instances={}
    for name,instance in dict(bindings).items():
        if (not isinstance(name,str) or not NAME.fullmatch(name)
                or type(instance) is not int or not 1<=instance<=0xFFFF):
            raise ModelError('Unsupported native routine Program identity')
        key=name.casefold()
        if key in result or instance in instances:
            raise ModelError('Ambiguous native routine Program bindings')
        result[key]=instance;instances[instance]=key
    return result,instances


def routine_paths(data, expected_routines, program_ids, *, parent_class=0x68):
    """Bind explicit source names to unambiguous active format-54 child paths."""
    if type(parent_class) is not int or parent_class not in (0x68,0x338):
        raise ModelError('Unsupported native routine parent class')
    expected=_expected(expected_routines)
    programs,program_names=_programs(program_ids)
    if any(program not in programs for program,_ in expected):
        raise ModelError('Incomplete native routine Program bindings')
    names={name for _,name in expected}
    if not isinstance(data,(bytes,bytearray,memoryview)) or not 24<=len(data)<=MAX_BYTES:
        raise ModelError('Native routine database size is outside its limit')
    size,position=struct.unpack_from('<II',data,8);end=size+1
    if (struct.unpack_from('<I',data)[0]+1!=len(data)
            or not 24<=position<=min(end,4096) or end>len(data)):
        raise ModelError('Unsupported native routine database bounds')
    found={};instances=set();records=0
    while position<end:
        records+=1
        if records>MAX_RECORDS or end-position<6:
            raise ModelError('Invalid native routine record count or header')
        kind,length=struct.unpack_from('<HI',data,position)
        if kind not in (0xFAFA,0xFDFD,0xFEFE,0xFBBF) or not 6<=length<=end-position:
            raise ModelError('Invalid native routine record bounds')
        record=memoryview(data)[position+6:position+length];position+=length
        if kind!=0xFAFA:continue
        if len(record)<148:raise ModelError('Truncated native routine component header')
        used=struct.unpack_from('<I',record)[0]
        if not 148<=used<=len(record) or struct.unpack_from('<I',record,12)[0]!=0:
            raise ModelError('Unsupported native routine component header layout')
        if struct.unpack_from('<H',record,10)[0]!={0x68:256,0x338:259}[parent_class]:continue
        raw_name=bytes(record[24:148])
        stop=next((index for index in range(0,124,2) if raw_name[index:index+2]==b'\0\0'),None)
        if stop is None:raise ModelError('Unterminated native routine component name')
        try:name=raw_name[:stop].decode('utf-16le').casefold()
        except UnicodeError as error:raise ModelError('Invalid native routine component name') from error
        if name not in names:continue
        body=record[148:used]
        if len(body)<22:raise ModelError('Truncated native routine record body')
        version=struct.unpack_from('<H',body,8)[0]
        logical=struct.unpack_from('<6H',body,10)
        if logical[0]==0x6D:
            raise ModelError('Native routine requires its Program parent scope')
        if logical[0]!=parent_class or logical[2]!=0x6D:continue
        program=program_names.get(logical[1]);key=(program,name)
        if key not in expected:continue
        if version!=54:raise ModelError('Unsupported native routine body version')
        if not logical[3] or logical[4:]!=(0,0):
            raise ModelError('Unsupported native routine child path')
        if key in found:raise ModelError('Duplicate or ambiguous historical native routine records')
        pair=(logical[1],logical[3])
        if pair in instances:raise ModelError('Conflicting native routine child instances')
        type_word=None
        # The ordinary unprotected format-54/body-371 data area starts at 90.
        # Other layouts still supply identities but no guessed Type attribute.
        if (len(body)==371 and struct.unpack_from('<4I',body,74)==(297,9,1,189)):
            type_word=struct.unpack_from('<H',body,90)[0]
        found[key]=(*pair,type_word);instances.add(pair)
    if found.keys()!=expected.keys():raise ModelError('Incomplete native routine inventory')
    return [dict(expected[key],program_instance=found[key][0],instance=found[key][1],
                 **({'type_word':found[key][2]} if found[key][2] is not None else {})) for key in sorted(found)]


@dataclass(frozen=True)
class Routine:
    program: str
    name: str
    program_instance: int
    instance: int
    type_word: int | None = None

    def __post_init__(self):
        if any(not isinstance(value,str) or not NAME.fullmatch(value) for value in (self.program,self.name)):
            raise ModelError('Invalid native routine name')
        if any(type(value) is not int or not 1<=value<=0xFFFF for value in (self.program_instance,self.instance)):
            raise ModelError('Invalid native routine logical identity')
        if self.type_word is not None and (type(self.type_word) is not int or not 0<=self.type_word<=0xFFFF):
            raise ModelError('Invalid native routine Type word')

    def manifest(self):
        return dict(program=self.program,name=self.name,program_instance=self.program_instance,instance=self.instance,
                    **({'type_word':self.type_word} if self.type_word is not None else {}))


@dataclass(frozen=True,init=False)
class NativeRoutines:
    source_acd_sha256: str
    source_l5x_sha256: str
    rows: tuple[Routine,...]
    by_key: Mapping[tuple[str,str],Routine]
    by_instance: Mapping[tuple[int,int],Routine]

    def __init__(self, source_acd_sha256, source_l5x_sha256, routines):
        _hash(source_acd_sha256);_hash(source_l5x_sha256)
        if not isinstance(routines,(list,tuple)) or len(routines)>MAX_ROUTINES:
            raise ModelError('Invalid or excessive native routine inventory')
        names={};instances={};programs={};program_names={};rows=[]
        for row in routines:
            required={'program','name','program_instance','instance'}
            if (not isinstance(row,dict) or not required<=row.keys() or row.keys()-required-{'type_word'} or
                    'type_word' in row and type(row['type_word']) is not int):
                raise ModelError('Invalid native routine manifest fields')
            routine=Routine(**row);program=routine.program.casefold()
            key=(program,routine.name.casefold());pair=(routine.program_instance,routine.instance)
            if key in names or pair in instances:raise ModelError('Duplicate native routine name or child instance')
            if (programs.get(program,routine.program_instance)!=routine.program_instance
                    or program_names.get(routine.program_instance,program)!=program):
                raise ModelError('Conflicting native routine Program identity')
            programs[program]=routine.program_instance;program_names[routine.program_instance]=program
            names[key]=routine;instances[pair]=routine;rows.append(routine)
        if len(programs)>MAX_PROGRAMS:raise ModelError('Native routine Program count limit')
        rows.sort(key=lambda row:(row.program.casefold(),row.name.casefold()))
        for field,value in (('source_acd_sha256',source_acd_sha256),('source_l5x_sha256',source_l5x_sha256),
                ('rows',tuple(rows)),('by_key',MappingProxyType(dict(names))),('by_instance',MappingProxyType(dict(instances)))):
            object.__setattr__(self,field,value)

    @classmethod
    def from_acd(cls,path,source_l5x_sha256,expected_routines,native_symbols):
        _hash(source_l5x_sha256);_expected(expected_routines)
        if not isinstance(native_symbols,NativeSymbols) or native_symbols.source_l5x_sha256!=source_l5x_sha256:
            raise ModelError('Native routines require matching source-bound Program identities')
        digest,raw=acd_stream(path,'Comps.Dat',limit=MAX_STREAM_BYTES)
        if digest!=native_symbols.source_acd_sha256:
            raise ModelError('ACD changed or native routine Program source differs')
        try:
            reader=gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw)
            with reader:data=reader.read(MAX_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:
            raise ModelError('Invalid compressed native routine inventory') from error
        return cls(digest,source_l5x_sha256,routine_paths(data,expected_routines,native_symbols.programs))

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        _hash(source_l5x_sha256)
        if not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','routines'}:
            raise ModelError('Invalid native routine inventory manifest')
        if manifest['source_l5x_sha256']!=source_l5x_sha256:
            raise ModelError('Native routine inventory does not match the loaded L5X bytes')
        if not isinstance(manifest['routines'],list):raise ModelError('Native routine manifest requires an explicit list')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256,manifest['routines'])

    def lookup(self,program,name):
        return self.by_key.get((program.casefold(),name.casefold())) if isinstance(program,str) and isinstance(name,str) else None

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
                    routines=[row.manifest() for row in self.rows])

    def description(self):
        return dict(bound=True,complete=True,routines=len(self.rows),programs=len({row.program_instance for row in self.rows}),
                    source='ACD Comps.Dat Executable format 54 and complete source routine names',
                    source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
                    type_words_available=sum(row.type_word is not None for row in self.rows),
                    type_word_source='Original unprotected format-54/body-371 data, UINT16 at offset 90',
                    type_word_semantics_inferred=False,
                    compiled_code=False,compiled_addresses=False,native_edit_authority=False,runtime_equivalence=False)
