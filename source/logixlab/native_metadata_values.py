"""Original v35 Comments.Dat values and immutable, read-only metadata streams.

Stored target words are preserved, not resolved to executable objects. Wire
record IDs are local to this catalog; they are not copied controller MUIDs or
the opaque words returned by Program service 0x50.
"""
from dataclasses import dataclass,field
import gzip
import io
import re
import struct
import zlib

from . import metadata_query as wire
from .model import ModelError
from .native_metadata_definitions import NativeMetadataDefinitions
from .native_project import _hash,acd_stream

MAX_DATABASE_BYTES=128_000_000
MAX_DATABASE_RECORDS=200_000
LOCALES={(0,0):0x7F,(9,1):0x409,(7,1):0x407,(12,1):0x40C,(10,1):0x40A,
         (22,1):0x416,(16,1):0x410,(17,1):0x411,(18,1):0x412,(4,2):0x804}
REFERENCE_NAME=re.compile(rb'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')


def _target(raw,qualifier=b''):
    if len(raw)!=12 or not struct.unpack_from('<H',raw)[0]:raise ModelError('Invalid stored metadata target')
    return wire.Target(*struct.unpack('<HIIH',raw),qualifier)


def _path(target):return struct.pack('<HIIH',target.class_id,target.instance_word,target.context_word,target.selector_word)


def _string(raw):
    if not raw or raw[-1:]!=b'\0' or b'\0' in raw[:-1]:raise ModelError('Invalid stored metadata string extent')
    try:raw[:-1].decode('utf-8')
    except UnicodeError as error:raise ModelError('Invalid stored metadata UTF-8') from error
    if len(raw)>65536:raise ModelError('Stored metadata string exceeds wire limit')
    return raw[:-1]


def _types(rows,definitions):
    if not isinstance(definitions,NativeMetadataDefinitions) or not definitions.rows:
        raise ModelError('Original Metadata Definitions are required for values')
    ids={d.instance for d in definitions.rows}
    if max(ids)>255 or next((d.name for d in definitions.rows if d.instance==17),None)!='ValueType':
        raise ModelError('Unsupported stored metadata type schema')
    result={}
    for row in rows:
        if row.target.class_id!=0x349 or row.definition!=17:continue
        path=struct.unpack('<6H',_path(row.target));instance=path[1]
        if (path[2:]!=(0,0,0,0) or instance not in ids or row.target.qualifier or row.locale_word!=0x7F
                or row.kind!=2 or row.type_code!=0xC2 or row.elements!=1 or row.data not in (b'\0',b'\1',b'\2')
                or instance in result):raise ModelError('Invalid or duplicate stored metadata value type')
        result[instance]=row.data[0]+1
    if result.keys()!=ids:raise ModelError('Incomplete stored metadata value types')
    return result


def stored_records(data,definitions):
    if not isinstance(data,bytes) or not 24<=len(data)<=MAX_DATABASE_BYTES:
        raise ModelError('Invalid stored metadata database size')
    size,pos=struct.unpack_from('<II',data,8);end=size+1
    if struct.unpack_from('<I',data)[0]+1!=len(data) or not 24<=pos<=min(end,4096) or end>len(data):
        raise ModelError('Invalid stored metadata database bounds')
    pending=[];count=0;bootstrap=[]
    while pos<end:
        count+=1
        if count>MAX_DATABASE_RECORDS or end-pos<6:raise ModelError('Invalid stored metadata record header')
        kind,length=struct.unpack_from('<HI',data,pos)
        if kind not in (0xFAFA,0xFDFD,0xFEFE,0xFBBF) or not 6<=length<=end-pos:
            raise ModelError('Invalid stored metadata record bounds')
        record=data[pos+6:pos+length];pos+=length
        if kind!=0xFAFA:continue
        if len(record)<32:raise ModelError('Truncated stored metadata header')
        used,reserved,fmt,value_bytes=struct.unpack_from('<IHHH',record)
        if reserved or not 32<=used+4<=len(record) or fmt not in (1,23) or record[26]:
            raise ModelError('Unsupported stored metadata header profile')
        record=record[:used+4];offset=32;qualifier=b''
        if fmt==1:
            if record[22:27]!=bytes(5) or record[30:32]!=bytes(2):raise ModelError('Unsupported unqualified metadata target')
        else:
            if record[22:26]==bytes(4):raise ModelError('Missing stored qualifier identity')
            offset=30
            while offset+2<=len(record) and record[offset:offset+2]!=bytes(2):offset+=2
            if offset+2>len(record) or offset==30:raise ModelError('Invalid stored metadata qualifier extent')
            try:qualifier=record[30:offset].decode('utf-16le').encode('utf-8')
            except UnicodeError as error:raise ModelError('Invalid stored metadata qualifier') from error
            if len(qualifier)>65535 or b'\0' in qualifier:raise ModelError('Invalid stored metadata qualifier size')
            offset+=2
        if len(record)-offset!=value_bytes:raise ModelError('Stored metadata value extent mismatch')
        target=_target(record[10:22],qualifier);definition=record[27]
        locale=LOCALES.get(tuple(record[28:30]))
        if not definition or locale is None:raise ModelError('Unsupported stored metadata definition or locale')
        raw=record[offset:];pending.append((target,definition,locale,raw))
        if target.class_id==0x349 and definition==17:
            if len(raw)!=15 or raw[:14]!=b'\xC2\0'+bytes(12):raise ModelError('Unsupported metadata type declaration')
            bootstrap.append(wire.Record(target,locale,definition,len(pending),2,raw[14:],0xC2,1))
        if len(pending)>wire.MAX_RECORDS:raise ModelError('Stored metadata value count limit')
    types=_types(tuple(bootstrap),definitions);rows=[]
    for target,definition,locale,raw in pending:
        value_type=types.get(definition);blob=b'';code=None;elements=0;references=()
        if value_type==1:
            if raw[:12]!=bytes(12):raise ModelError('Unsupported stored metadata string header')
            blob=_string(raw[12:])
        elif value_type==2:
            if len(raw)<15 or raw[2:14]!=bytes(12):raise ModelError('Unsupported stored metadata numeric header')
            code=struct.unpack_from('<H',raw)[0];width=wire.NUMERIC_WIDTHS.get(code);blob=raw[14:]
            if width is None or not blob or len(blob)%width or len(blob)//width>65535:
                raise ModelError('Unsupported stored metadata numeric extent')
            elements=len(blob)//width
        elif value_type==3:
            if not raw or len(raw)%54 or len(raw)//54>wire.MAX_REFERENCES:raise ModelError('Unsupported stored reference extent')
            found=[]
            for offset in range(0,len(raw),54):
                name=raw[offset:offset+41];stop=name.find(b'\0')
                if (stop<1 or not REFERENCE_NAME.fullmatch(name[:stop]) or any(name[stop:]) or raw[offset+53]):
                    raise ModelError('Unsupported stored reference name or flags')
                found.append(wire.Reference(name[:stop],_target(raw[offset+41:offset+53])))
            references=tuple(found);elements=len(references)
        else:raise ModelError('Unknown stored metadata value type')
        rows.append(wire.Record(target,locale,definition,len(rows)+1,value_type,blob,code,elements,references))
    return tuple(rows)


def encode_records(rows):
    data=bytearray()
    def text(raw):return struct.pack('<H',len(raw))+raw
    def target(row):return _path(row)+text(row.qualifier)
    for row in rows:
        data.extend(target(row.target));data.extend(struct.pack('<HHI',row.locale_word,row.definition,row.record_word)+bytes(12))
        data.extend(struct.pack('<H',row.kind))
        if row.kind==1:data.extend(text(row.data))
        elif row.kind==2:data.extend(struct.pack('<HH',row.type_code,row.elements)+row.data)
        elif row.kind==3:
            data.extend(struct.pack('<H',len(row.references)))
            for ref in row.references:data.extend(text(ref.name)+target(ref.target))
        else:raise ModelError('Unsupported original metadata value kind')
        if len(data)>wire.MAX_BYTES:raise ModelError('Metadata value stream exceeds limit')
    return bytes(data)


@dataclass(frozen=True)
class NativeMetadataValues:
    source_acd_sha256:str
    source_l5x_sha256:str
    definitions:NativeMetadataDefinitions=field(repr=False)
    rows:tuple=field(repr=False)
    _all:bytes=field(init=False,repr=False)
    _controller:bytes=field(init=False,repr=False)

    def __post_init__(self):
        _hash(self.source_acd_sha256);_hash(self.source_l5x_sha256)
        if (not isinstance(self.definitions,NativeMetadataDefinitions) or
                (self.source_acd_sha256,self.source_l5x_sha256)!=(self.definitions.source_acd_sha256,self.definitions.source_l5x_sha256)
                or not isinstance(self.rows,tuple) or not 1<=len(self.rows)<=wire.MAX_RECORDS):
            raise ModelError('Invalid or unbound original metadata values')
        try:
            for row in self.rows:
                if (not isinstance(row,wire.Record) or any(type(getattr(row,key)) is not int for key in
                        ('locale_word','definition','record_word','kind','elements')) or not isinstance(row.data,bytes)
                        or not isinstance(row.references,tuple) or not isinstance(row.target,wire.Target)):
                    raise ValueError('Invalid metadata value field types')
                if any(not isinstance(ref,wire.Reference) or not isinstance(ref.name,bytes) or not isinstance(ref.target,wire.Target)
                        for ref in row.references):raise ValueError('Invalid metadata reference fields')
                for target in (row.target,*(ref.target for ref in row.references)):
                    if not isinstance(target.qualifier,bytes):raise ValueError('Invalid metadata qualifier field')
                    if any(type(getattr(target,key)) is not int for key in ('class_id','instance_word','context_word','selector_word')):
                        raise ValueError('Invalid metadata target words')
                    _target(_path(target));target.qualifier.decode('utf-8')
                    if b'\0' in target.qualifier:raise ValueError('Invalid metadata target qualifier')
                if row.kind==1:
                    row.data.decode('utf-8')
                    if b'\0' in row.data:raise ValueError('Invalid stored metadata text')
                if row.kind==2 and type(row.type_code) is not int:raise ValueError('Invalid metadata numeric type')
                if any(not REFERENCE_NAME.fullmatch(ref.name) or ref.target.qualifier for ref in row.references):
                    raise ValueError('Unsupported stored metadata reference')
            raw=encode_records(self.rows)
            if wire.records(raw)!=self.rows:raise ValueError('Noncanonical metadata records')
            types=_types(self.rows,self.definitions);keys=set()
            for index,row in enumerate(self.rows,1):
                key=(row.target,row.definition,row.locale_word)
                if (row.record_word!=index or row.kind!=types.get(row.definition) or key in keys
                        or row.locale_word not in LOCALES.values()):raise ValueError('Conflicting metadata record')
                keys.add(key)
        except (ValueError,TypeError,struct.error,AttributeError,OverflowError) as error:
            raise ModelError('Invalid original metadata value records') from error
        object.__setattr__(self,'_all',raw)
        selected=tuple(row for row in self.rows if _path(row.target)==struct.pack('<6H',0x8E,1,0,0,0,0))
        object.__setattr__(self,'_controller',encode_records(selected))

    @classmethod
    def from_acd(cls,path,source_l5x_sha256,definitions):
        _hash(source_l5x_sha256);digest,raw=acd_stream(path,'Comments.Dat',limit=16_000_000)
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw) as stream:
                data=stream.read(MAX_DATABASE_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid compressed metadata values') from error
        return cls(digest,source_l5x_sha256,definitions,stored_records(data,definitions))

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256,definitions):
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','values_hex'} or
                manifest['source_l5x_sha256']!=source_l5x_sha256 or not isinstance(manifest['values_hex'],str) or
                not 2<=len(manifest['values_hex'])<=2*wire.MAX_BYTES):raise ModelError('Invalid or stale metadata value manifest')
        try:rows=wire.records(bytes.fromhex(manifest['values_hex']))
        except ValueError as error:raise ModelError('Invalid encoded metadata value manifest') from error
        return cls(manifest['source_acd_sha256'],source_l5x_sha256,definitions,rows)

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,values_hex=self._all.hex())

    def body(self,selection):
        if selection=='all-objects':return self._all
        if selection=='controller-all':return self._controller
        if selection=='controller-attribute-26':return b'' # Existing exact empty compatibility selection.
        raise ModelError('Unsupported metadata value selection')

    def description(self):
        return dict(available=True,read_only=True,records=len(self.rows),bytes=len(self._all),
            definitions=len(self.definitions.rows),locales=len({r.locale_word for r in self.rows}),
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
            record_ids='simulator_local',source_targets_resolved=False,program_query_0x50=False,
            original_source_only=True,metadata_writes=False,values_exposed=False)
