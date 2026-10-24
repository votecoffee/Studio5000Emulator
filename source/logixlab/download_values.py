"""Source-equivalent initial-value preparation, without active installation.

Native table bytes are compared with explicit scalar, structure and array layouts.
Auxiliary container and Local port data remain private configuration records.
"""
from dataclasses import dataclass
import hashlib
import math
import struct
from xml.etree import ElementTree as ET

from .download_image import ImageError
from .model import ModelError
from .runtime import Engine
from .templates import ATOMS
from .object_staging import MAX_ELEMENTS,MAX_STORAGE_BYTES
from . import download_structures


def encode_value(dtype,value,native_types):
    """Only exact scalar and source-declared TIMER/COUNTER layouts are supported."""
    if dtype=='BOOL':
        if type(value) is not bool:raise ImageError('download_initial_bool_required')
        return 0xC1,bytes((value,))
    if dtype in ATOMS:
        code,fmt=ATOMS[dtype]
        if (dtype=='REAL' and (type(value) is not float or not math.isfinite(value))
                or dtype!='REAL' and type(value) is not int):raise ImageError('download_initial_scalar_required')
        try:return code,struct.pack('<'+fmt,value)
        except (OverflowError,struct.error):raise ImageError('download_initial_scalar_range') from None
    flags={'TIMER':('EN','TT','DN'),'COUNTER':('CU','CD','DN','OV','UN')}.get(dtype)
    if flags is None:return download_structures.encode(dtype,value,native_types,encode_value)
    expected=[('Control','DINT',0,None,(),True),('PRE','DINT',4,None,(),False),('ACC','DINT',8,None,(),False)]
    expected += [(name,'BOOL',0,31-i,(),False) for i,name in enumerate(flags)]
    row=native_types.types.get(dtype.casefold());instance=native_types.type_ids.get(dtype.casefold())
    if (row is None or row.size!=12 or type(instance) is not int or not 1<=instance<=0xFFF
            or [(m.name,m.dtype,m.offset,m.bit,m.dimensions,m.hidden) for m in row.members]!=expected):
        raise ImageError('download_initial_builtin_source_layout_required')
    if type(value) is not dict or value.keys()!=set(('PRE','ACC',*flags)):
        raise ImageError('download_initial_builtin_fields_required')
    if any(type(value[n]) is not bool for n in flags) or any(type(value[n]) is not int for n in ('PRE','ACC')):
        raise ImageError('download_initial_builtin_value_required')
    control=sum(int(value[n])<<(31-i) for i,n in enumerate(flags))
    try:return 0x8000|instance,struct.pack('<Iii',control,value['PRE'],value['ACC'])
    except struct.error:raise ImageError('download_initial_scalar_range') from None


def encode_initial(dtype,value,native_types):
    """Exact root Table layout; arrays use last-index-fast storage.

    Complete rectangular values already belong to the imported source model.
    Structure strides come from the source ACD. The observed root BOOL profile
    has one dimension, in complete 32-bit storage words.
    """
    if type(value) is not list:
        code,data=encode_value(dtype,value,native_types)
        return code,(0,0,0),1,data
    if dtype=='BOOL':
        if (not 32<=len(value)<=MAX_ELEMENTS or len(value)%32 or any(type(bit) is not bool for bit in value)):
            raise ImageError('download_initial_bool_array_profile')
        words=len(value)//32
        data=b''.join(struct.pack('<I',sum(int(bit)<<i for i,bit in enumerate(value[start:start+32])))
                      for start in range(0,len(value),32))
        return 0x20D3,(words,0,0),words,data
    payload=bytearray();elements=0;base_code=None
    def walk(node,depth):
        nonlocal elements,base_code
        if type(node) is list:
            if depth>=3 or not node or len(node)>MAX_ELEMENTS:
                raise ImageError('download_initial_array_extent')
            shape=None
            for item in node:
                child=walk(item,depth+1)
                if shape is None:shape=child
                elif child!=shape:raise ImageError('download_initial_array_shape')
            return (len(node),*shape)
        elements+=1
        if elements>MAX_ELEMENTS:raise ImageError('download_initial_array_extent')
        code,raw=encode_value(dtype,node,native_types)
        if base_code is None:base_code=code
        elif code!=base_code:raise ImageError('download_initial_array_type_changed')
        payload.extend(raw)
        if len(payload)>MAX_STORAGE_BYTES:raise ImageError('download_initial_array_storage_limit')
        return ()
    shape=walk(value,0)
    return base_code|(len(shape)<<13),shape+(0,)*(3-len(shape)),elements,bytes(payload)


def _tree(node,depth=0):
    if depth>3 or len(node)>4:raise ImageError('download_initial_port_xml_extent')
    if node.text and node.text.strip() or node.tail and node.tail.strip():raise ImageError('download_initial_port_xml_text')
    return node.tag,tuple(sorted(node.attrib.items())),tuple(_tree(child,depth+1) for child in node)


def _local_ports(project,data):
    """Compare the bounded observed ICP/Ethernet port profile with original L5X."""
    if not project.io_map.empty or project.io_map.root_link_port!=1 or not 1<len(data)<=32768 or data[-1:]!=b'\0':
        raise ImageError('download_initial_port_profile_required')
    try:
        if project.path.stat().st_size>150_000_000:raise ImageError('download_initial_source_file_changed')
        raw=project.path.read_bytes()
    except OSError:raise ImageError('download_initial_source_file_unavailable') from None
    if hashlib.sha256(raw).hexdigest()!=project.sha256:raise ImageError('download_initial_source_file_changed')
    if b'<!' in data.upper():raise ImageError('download_initial_port_xml_invalid')
    try:
        root=ET.fromstring(raw);observed=ET.fromstring(data[:-1])
    except ET.ParseError:raise ImageError('download_initial_port_xml_invalid') from None
    modules=root.findall('./Controller/Modules/Module')
    if len(modules)!=1 or modules[0].get('Name')!='Local':raise ImageError('download_initial_port_source_required')
    ports=modules[0].findall('Ports')
    if len(ports)!=1 or not 1<=len(ports[0])<=2:raise ImageError('download_initial_port_source_required')
    expected=ET.Element('in');ids=set()
    for port in ports[0]:
        kind={'ICP':'ICP','Ethernet':'EN'}.get(port.get('Type'));ident=port.get('Id');up=port.get('Upstream')
        if (port.tag!='Port' or port.attrib.keys()-{'Id','Type','Address','Upstream'} or kind is None
                or ident not in ('1','2') or ident in ids or up not in ('true','false')):
            raise ImageError('download_initial_port_source_required')
        ids.add(ident);values={'Id':ident,'Type':kind,'Ups':up.title()}
        if 'Address' in port.attrib:values['Addr']=port.get('Address')
        node=ET.SubElement(expected,'Port',values)
        if len(port)>1:raise ImageError('download_initial_port_source_required')
        for bus in port:
            if bus.tag!='Bus' or len(bus) or bus.attrib.keys()-{'Size'}:
                raise ImageError('download_initial_port_source_required')
            if bus.attrib:
                size=bus.get('Size')
                if not size.isascii() or not size.isdecimal() or not 1<=int(size)<=256:
                    raise ImageError('download_initial_port_source_required')
                ET.SubElement(node,'Bus',{'Max':size,'Size':size})
    if _tree(observed)!=_tree(expected):raise ImageError('download_initial_port_source_mismatch')


@dataclass(frozen=True)
class PreparedValues:
    binding:str
    values:tuple
    auxiliary:tuple

    @classmethod
    def prepare(cls,headers,native_types):
        ns=headers.namespace;project=headers._project();image=ns._image
        if ns._incremental is None:raise ImageError('download_initial_incremental_required')
        stamp=headers.stamp(image,ns._source)
        symbols=headers.symbols
        if symbols is None or set(symbols.by_key)!=set(project.tags) or set(project.initial)!=set(project.tags):
            raise ImageError('download_initial_complete_tag_source_required')
        tables={};values=[];auxiliary=[]
        for key,symbol in sorted(symbols.by_key.items()):
            tag=project.tags[key]
            if tag.alias or tag.problem or tag.tag_class!='Standard':raise ImageError('download_initial_tag_profile_required')
            target=(symbol.program_instance,symbol.instance);table=image._symbols.get(target)
            if table is None or table not in image._regions or table in tables:
                raise ImageError('download_initial_tag_table_required')
            region=ns._incremental._tables.get(table,image._regions[table])
            code,dimensions,elements,data=encode_initial(tag.dtype.upper(),project.initial[key],native_types)
            if region.dimensions!=dimensions or region.elements!=elements or region.type_code!=code or region.data!=data:
                raise ImageError('download_initial_source_value_mismatch')
            tables[table]=key;values.append((key,table,code,data))
        for table,original in sorted(image._regions.items()):
            if table in tables:continue
            region=ns._incremental._tables.get(table,original)
            targets=[target for target,t in image._symbols.items() if t==table]
            extra=headers.auxiliary.by_instance.get(targets[0]) if headers.auxiliary and len(targets)==1 else None
            if (extra is not None and extra.program_instance==0 and extra.name=='__CONTAINER'
                    and extra.component_type==264 and region.type_code==0xC4 and region.dimensions==(0,0,0)
                    and region.elements==1 and region.data==bytes(4)):
                kind='opaque_container_zero'
            elif (not targets and region.type_code==0x20C2 and region.elements==len(region.data)
                    and region.dimensions==(len(region.data),0,0)):
                _local_ports(project,region.data);kind='source_local_ports'
            else:raise ImageError('download_initial_auxiliary_table_unimplemented')
            auxiliary.append((table,kind,region.type_code,region.dimensions,region.data))
        return cls(stamp,tuple(values),tuple(auxiliary))

    def validate(self,headers,native_types):
        if self!=self.prepare(headers,native_types):raise ImageError('download_initial_preparation_changed')

    def new_engine(self,headers,native_types):
        self.validate(headers,native_types)
        try:candidate=Engine(headers.engine.project,defer_prescan=True)
        except ModelError:raise ImageError('download_initial_execution_plan_unavailable') from None
        if candidate.blockers or candidate.fault or candidate.memory.values!=candidate.project.initial:
            raise ImageError('download_initial_execution_plan_unavailable')
        self.validate(headers,native_types)
        return candidate

    def description(self):
        return dict(prepared=True,tags=len(self.values),tag_bytes=sum(len(r[3]) for r in self.values),
            auxiliary_tables=len(self.auxiliary),all_tables_accounted=True,source_values_matched=True,
            scalar_and_builtin_layouts=True,
            atomic_arrays=True,array_rank_limit=3,array_element_limit=MAX_ELEMENTS,
            packed_bool_arrays=True,bool_array_rank_limit=1,bool_storage_word_bits=32,
            source_structures=True,structure_arrays=True,structure_padding='zero_required',
            active_values_changed=False,compiled_code_executed=False,commit=False,payloads_exposed=False)
