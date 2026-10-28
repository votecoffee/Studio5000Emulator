"""Source-bound comparison of staged native members with offline ACD metadata.

The observed offset/access dialect is accepted only when it matches this source.
This does not validate opaque trailers, native signatures or executable types.
"""
from collections import Counter
from dataclasses import asdict, dataclass
import gzip
import hashlib
import io
import json
import math
import re
import struct
import zlib

from .model import ModelError
from .native_project import _hash,acd_stream
from .native_symbols import read_tag_info
from .template_layout import decode, LayoutError

MAX_TYPES = 1024
MAX_MEMBERS = 4096
MAX_TOTAL_MEMBERS = 65536
MAX_SIZE = 1024 * 1024
MAX_DEPTH = 32
NAME = re.compile(r'[A-Za-z_][A-Za-z_0-9:]{0,253}\Z')
ATOMS = {'BOOL': (0xC1,1), 'SINT': (0xC2,1), 'INT': (0xC3,2),
         'DINT': (0xC4,4), 'LINT': (0xC5,8), 'USINT': (0xC6,1),
         'UINT': (0xC7,2), 'UDINT': (0xC8,4), 'ULINT': (0xC9,8),
         'REAL': (0xCA,4), 'LREAL': (0xCB,8)}
ACCESS = {0: 'Read/Write', 3: 'Read/Write', 10: 'Read Only', 15: 'None'}


def type_paths(data,names):
    """Read active format-177 DataType identities, never source-order IDs."""
    if not isinstance(data,bytes) or not 24<=len(data)<=128000000:raise ModelError('Invalid native type database bounds')
    size,position=struct.unpack_from('<II',data,8);end=size+1
    if struct.unpack_from('<I',data)[0]+1!=len(data) or not 24<=position<=min(end,4096) or end>len(data):
        raise ModelError('Unsupported native type database bounds')
    result={};instances=set();count=0
    while position<end:
        count+=1
        if count>200000 or end-position<6:raise ModelError('Invalid native type record header')
        kind,length=struct.unpack_from('<HI',data,position)
        if kind not in (0xFAFA,0xFDFD,0xFEFE,0xFBBF) or not 6<=length<=end-position:
            raise ModelError('Invalid native type record bounds')
        record=data[position+6:position+length];position+=length
        if kind!=0xFAFA:continue
        if len(record)<148:raise ModelError('Truncated native type component')
        used=struct.unpack_from('<I',record)[0]
        if not 148<=used<=len(record) or struct.unpack_from('<I',record,12)[0]!=0:
            raise ModelError('Unsupported native type component header')
        if struct.unpack_from('<H',record,10)[0]!=256:continue
        raw=record[24:148];stop=next((i for i in range(0,124,2) if raw[i:i+2]==b'\0\0'),None)
        if stop is None:raise ModelError('Unterminated native type name')
        try:key=raw[:stop].decode('utf-16le').casefold()
        except UnicodeError as error:raise ModelError('Invalid native type component name') from error
        if key not in names:continue
        body=record[148:used]
        if len(body)<22:raise ModelError('Truncated native type component body')
        if struct.unpack_from('<H',body,8)[0]!=177:continue
        path=struct.unpack_from('<6H',body,10)
        if path[0]!=0x6C:continue
        if not path[1] or any(path[2:]) or key in result or path[1] in instances:
            raise ModelError('Ambiguous native DataType identity')
        result[key]=path[1];instances.add(path[1])
    return result


def name(value):
    if not isinstance(value,str) or not NAME.fullmatch(value): raise ModelError('Invalid native type/member name')
    return value


def integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum: raise ModelError('Invalid native type integer')
    return value


def number(value, maximum):
    if not isinstance(value,str) or not re.fullmatch(r'0|[1-9][0-9]{0,9}',value): raise ModelError('Invalid native type XML integer')
    return integer(int(value),maximum)


@dataclass(frozen=True)
class Member:
    name: str
    dtype: str
    offset: int
    bit: int | None
    dimensions: tuple[int,...]
    access: str
    hidden: bool


@dataclass(frozen=True)
class Type:
    name: str
    size: int
    members: tuple[Member,...]


def verification(status='idle', *, matched=0, members=0, failed=0, ids=0, unresolved=0, identities=False, errors=()):
    return {'status':status,'types_matched':matched,'members_matched':members,'types_unavailable':failed,
            'template_ids_matched':ids,'template_ids_unresolved':unresolved,'template_identities_verified':identities,
            'errors':[{'reason':reason,'types':count} for reason,count in errors],
            'member_locations_verified':status=='matched',
            'storage_mapping_supported':False,'signature_verified':False,
            'definitions_exposed':False,'execution_supported':False}


class NativeTypes:
    def __init__(self, source_acd_sha256, source_l5x_sha256, types, type_ids=None):
        self.source_acd_sha256=_hash(source_acd_sha256);self.source_l5x_sha256=_hash(source_l5x_sha256)
        if not isinstance(types,(list,tuple)) or len(types)>MAX_TYPES: raise ModelError('Native type count limit')
        self.types={};total=0
        for t in types:
            if not isinstance(t,Type): raise ModelError('Invalid native type')
            name(t.name);integer(t.size,MAX_SIZE)
            if not t.size or not isinstance(t.members,tuple) or not 1<=len(t.members)<=MAX_MEMBERS:
                raise ModelError('Native type size/member count limit')
            if t.name.lower() in self.types: raise ModelError('Duplicate native type')
            if t.name.upper() in ATOMS:raise ModelError('Native structure name conflicts with an atomic type')
            names=set()
            for m in t.members:
                if not isinstance(m,Member): raise ModelError('Invalid native type member')
                name(m.name);name(m.dtype);integer(m.offset,MAX_SIZE-1)
                if m.bit is not None: integer(m.bit,31)
                if (m.name.lower() in names or type(m.hidden) is not bool or m.access not in ACCESS.values()
                        or not isinstance(m.dimensions,tuple) or len(m.dimensions)>3):
                    raise ModelError('Invalid or duplicate native member')
                names.add(m.name.lower())
                for dim in m.dimensions:
                    if not integer(dim,65535): raise ModelError('Invalid native member dimension')
                if math.prod(m.dimensions)>65535: raise ModelError('Native member element limit')
                if m.dtype.upper()!='BOOL' and m.bit is not None: raise ModelError('Only BOOL has native member bit metadata')
            total+=len(t.members)
            if total>MAX_TOTAL_MEMBERS: raise ModelError('Native total member limit')
            self.types[t.name.lower()]=t
        self.member_count=total
        # Resolve every nested type and bound its source extent, without imposing
        # an invented non-overlap/alignment rule on predefined native structures.
        for t in self.types.values():
            for m in t.members:
                width=self.width(m.dtype);offset=m.offset
                if m.dtype.upper()=='BOOL' and m.bit is not None: offset+=m.bit//8
                size=(4*((math.prod(m.dimensions)+31)//32) if m.dtype.upper()=='BOOL' and m.dimensions
                      else width*math.prod(m.dimensions))
                if offset+size>t.size: raise ModelError('Native member exceeds source type size')
        depths={}
        def visit(key, stack=()):
            if key in stack or len(stack)>=MAX_DEPTH: raise ModelError('Recursive or deep native source type')
            if key in depths:return depths[key]
            depth=1+max((visit(m.dtype.lower(),stack+(key,)) for m in self.types[key].members
                         if m.dtype.upper() not in ATOMS),default=0)
            if depth>MAX_DEPTH:raise ModelError('Recursive or deep native source type')
            depths[key]=depth
            return depth
        for key in self.types:visit(key)
        self.type_ids={}
        if type_ids is not None:
            if not isinstance(type_ids,dict) or len(type_ids)>MAX_TYPES:raise ModelError('Invalid native type identity map')
            seen=set()
            for key,value in type_ids.items():
                if not isinstance(key,str) or key not in self.types or type(value) is not int or not 1<=value<=0xFFFF or value in seen:
                    raise ModelError('Invalid or duplicate native DataType identity')
                self.type_ids[key]=value;seen.add(value)

    def width(self, dtype):
        if dtype.upper() in ATOMS:return ATOMS[dtype.upper()][1]
        t=self.types.get(dtype.lower())
        if t is None:raise ModelError('Native member type reference is unavailable')
        return t.size

    @classmethod
    def from_manifest(cls, manifest, source_l5x_sha256):
        required={'source_acd_sha256','source_l5x_sha256','types'}
        if not isinstance(manifest,dict) or not required<=manifest.keys() or manifest.keys()-required-{'type_ids'}:
            raise ModelError('Invalid native type manifest')
        if manifest['source_l5x_sha256']!=source_l5x_sha256: raise ModelError('Native types do not match loaded L5X bytes')
        rows=manifest['types']
        if not isinstance(rows,list) or len(rows)>MAX_TYPES: raise ModelError('Native type count limit')
        types=[];total=0
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'name','size','members'} or not isinstance(row['members'],list):
                raise ModelError('Invalid native type fields')
            if len(row['members'])>MAX_MEMBERS:raise ModelError('Native member count limit')
            total+=len(row['members'])
            if total>MAX_TOTAL_MEMBERS:raise ModelError('Native total member limit')
            members=[]
            for m in row['members']:
                if (not isinstance(m,dict) or set(m)!={'name','dtype','offset','bit','dimensions','access','hidden'}
                        or not isinstance(m['dimensions'],list)):
                    raise ModelError('Invalid native member fields')
                members.append(Member(**{**m,'dimensions':tuple(m['dimensions'])}))
            types.append(Type(row['name'],row['size'],tuple(members)))
        return cls(manifest['source_acd_sha256'],manifest['source_l5x_sha256'],types,manifest.get('type_ids'))

    @classmethod
    def from_acd(cls, path, source_l5x_sha256):
        digest,root=read_tag_info(path)
        containers=root.findall('DataTypes')
        if len(containers)!=1 or containers[0].attrib:raise ModelError('Native type metadata is unavailable')
        types=[];total=0
        for t in containers[0]:
            if (t.tag!='DataType' or set(t.attrib)!={'Name','Size'} or len(t.findall('Members'))!=1
                    or len(t.findall('String'))>1 or any(c.tag not in ('Members','String') for c in t)):
                raise ModelError('Unsupported native type XML fields')
            if t.find('Members').attrib:raise ModelError('Unsupported native member container fields')
            marker=t.find('String')
            if marker is not None:
                if set(marker.attrib)!={'Length'} or len(marker) or not number(marker.get('Length'),65535):
                    raise ModelError('Unsupported native string metadata')
            members=[]
            for index,m in enumerate(t.find('Members')):
                required={'Name','DataType','Offset','ExtAcc','Index'}
                if (m.tag!='Member' or not required<=m.attrib.keys() or m.attrib.keys()-required-{'Bit','Hidden'}
                        or number(m.get('Index'),MAX_MEMBERS-1)!=index):raise ModelError('Unsupported native member XML fields/order')
                dims=[]
                if len(m):
                    if len(m)!=1 or m[0].tag!='Dimensions' or m[0].attrib or not 1<=len(m[0])<=3:
                        raise ModelError('Unsupported native member XML dimensions')
                    for dim in m[0]:
                        if dim.tag!='Dim' or set(dim.attrib)!={'Size'} or len(dim):raise ModelError('Unsupported native member XML dimension')
                        dims.append(number(dim.get('Size'),65535))
                if m.get('Hidden','false') not in ('true','false'):raise ModelError('Invalid native member hidden flag')
                members.append(Member(m.get('Name'),m.get('DataType'),number(m.get('Offset'),MAX_SIZE-1),
                                      number(m.get('Bit'),31) if 'Bit' in m.attrib else None,
                                      tuple(dims),m.get('ExtAcc'),m.get('Hidden','false')=='true'))
                total+=1
                if len(members)>MAX_MEMBERS or total>MAX_TOTAL_MEMBERS:raise ModelError('Native member count limit')
            types.append(Type(t.get('Name'),number(t.get('Size'),MAX_SIZE),tuple(members)))
            if len(types)>MAX_TYPES:raise ModelError('Native type count limit')
        result=cls(digest,source_l5x_sha256,types)
        try:component_digest,raw=acd_stream(path,'Comps.Dat',16000000)
        except ModelError as error:
            if str(error)!='ACD has no supported metadata stream: Comps.Dat':raise
            return result
        if component_digest!=digest:raise ModelError('ACD changed while reading native DataType identities')
        try:
            reader=gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw)
            with reader:data=reader.read(128000001)
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid native type database compression') from error
        return cls(digest,source_l5x_sha256,types,type_paths(data,result.types))

    def manifest(self):
        def member(m):
            # Validated Member fields are immutable scalars and a tuple of ints.
            # Avoid recursive deepcopy on every source/catalog binding check.
            if type(m) is not Member:return {**asdict(m),'dimensions':list(m.dimensions)}
            return {'name':m.name,'dtype':m.dtype,'offset':m.offset,'bit':m.bit,
                    'dimensions':list(m.dimensions),'access':m.access,'hidden':m.hidden}
        return {'source_acd_sha256':self.source_acd_sha256,'source_l5x_sha256':self.source_l5x_sha256,
                'type_ids':dict(self.type_ids),
                'types':[{'name':t.name,'size':t.size,'members':[member(m) for m in t.members]}
                         for t in self.types.values()]}

    def description(self):
        return {'bound':True,'source':'ACD TagInfo.XML type/member metadata','types':len(self.types),
                'members':self.member_count,'source_acd_sha256':self.source_acd_sha256,
                'native_type_ids':len(self.type_ids),
                'source_l5x_sha256':self.source_l5x_sha256,'compiled_addresses':False,'runtime_equivalence':False}

    def binding_stamp(self):
        """Pin the source pair, layouts and optional original IDs during staging."""
        raw=json.dumps(self.manifest(),sort_keys=True,separators=(',',':')).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()

    def verify(self, templates):
        definitions={};errors=Counter();matched=members=0
        for t in templates:
            try:d=decode(t.definition,t.attributes.members)
            except LayoutError:errors['template_definition_unavailable']+=1
            else:
                if t.instance in definitions:return verification('mismatch',failed=len(templates),unresolved=len(templates),errors=(('duplicate_template_id',1),))
                definitions[t.instance]=(t,d)
        names=[d.name.lower() for _,d in definitions.values()]
        if len(set(names))!=len(names):return verification('mismatch',failed=len(templates),unresolved=len(templates),errors=(('duplicate_template_name',1),))
        ids=sum(self.type_ids.get(d.name.lower())==t.instance for t,d in definitions.values())
        for t,d in definitions.values():
            reason=self._check(t,d,definitions)
            if reason:errors[reason]+=1
            else:matched+=1;members+=len(d.members)
        return verification('matched' if templates and not errors else 'mismatch' if templates else 'idle',
                            matched=matched,members=members,failed=len(templates)-matched,ids=ids,
                            unresolved=len(templates)-ids,identities=bool(templates) and ids==len(templates) and not errors,
                            errors=sorted(errors.items()))

    def _check(self,t,d,definitions):
        source=self.types.get(d.name.lower())
        if source is None:return 'source_type_unavailable'
        instance=self.type_ids.get(d.name.lower())
        if instance is not None and t.instance!=instance:return 'source_template_identity_mismatch'
        if t.attributes.structure_bytes!=source.size:return 'source_type_size_mismatch'
        if len(d.members)!=len(source.members):return 'source_member_count_mismatch'
        for m,s in zip(d.members,source.members):
            if m.name.lower()!=s.name.lower():return 'source_member_order_or_name_mismatch'
            rank=(m.type_word>>13)&3
            if len(s.dimensions)>1:return 'unsupported_member_array_rank'
            if s.dtype.upper()=='BOOL' and s.dimensions:return 'unsupported_member_bool_array'
            if rank!=len(s.dimensions) or m.type_word&0x1000:return 'source_member_type_mismatch'
            atom=ATOMS.get(s.dtype.upper())
            if atom:
                if m.type_word&0x9FFF!=atom[0]:return 'source_member_type_mismatch'
            else:
                target=definitions.get(m.type_word&0xFFF)
                if not m.type_word&0x8000 or target is None or target[1].name.lower()!=s.dtype.lower():
                    return 'source_nested_type_mismatch'
            if ACCESS.get(m.offset_word>>28)!=s.access:return 'source_member_access_mismatch'
            offset=s.offset;info=math.prod(s.dimensions) if s.dimensions else 0
            if s.dtype.upper()=='BOOL' and s.bit is not None:
                offset+=s.bit//8;info=s.bit%8
            if (m.offset_word&0x0FFFFFFF)!=offset or m.info!=info:return 'source_member_location_mismatch'
        return None
