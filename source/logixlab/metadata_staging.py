"""Temporary definition names and values, isolated from project metadata.

The programming lease supplies ownership, source binding and cleanup. Staging
does not install definitions, write active properties or commit a project.
"""
from dataclasses import dataclass
import re
import struct

MAX_DEFINITIONS = 256
MAX_NAME_BYTES = 128
MAX_INPUT_BYTES = 16384
MAX_FIELDS = 64
MAX_FIELD_BYTES = 1024
MAX_VALUES = 4096
MAX_VALUE_BYTES = 262144


class MetadataError(ValueError):
    def __init__(self,status,reason):
        self.status=status;self.reason=reason
        super().__init__(reason)


def parse_create(payload):
    """One Name attribute, with its UINT length and exact ASCII identifier."""
    if not isinstance(payload,bytes):raise MetadataError(3,'invalid_request')
    if len(payload)<6:raise MetadataError(0x13,'invalid_request')
    if payload[:4]!=b'\1\0\1\0':raise MetadataError(3,'invalid_request')
    size=struct.unpack_from('<H',payload,4)[0]
    if not 1<=size<=MAX_NAME_BYTES:raise MetadataError(3,'invalid_request')
    if len(payload)<6+size:raise MetadataError(0x13,'invalid_request')
    if len(payload)!=6+size:raise MetadataError(0x15,'invalid_request')
    name=payload[6:]
    if re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_]*',name) is None:raise MetadataError(3,'invalid_request')
    return name


@dataclass(frozen=True)
class Value:
    kind:int
    type_code:int|None
    elements:int
    data:bytes


class _Reader:
    def __init__(self,data):self.data=data;self.offset=0

    def take(self,size):
        if len(self.data)-self.offset<size:raise MetadataError(0x13,'invalid_request')
        result=self.data[self.offset:self.offset+size];self.offset+=size
        return result

    def unpack(self,fmt):return struct.unpack(fmt,self.take(struct.calcsize(fmt)))


def parse_values(payload,reference=0):
    """Only the observed unqualified definition target and record selectors.

    The 0x7F marker and zero selector words are retained as structural constants;
    this parser does not infer broader selector or locale semantics.
    """
    if (not isinstance(payload,bytes) or type(reference) is not int
            or not 0<=reference<=0xFFFFFFFF):raise MetadataError(3,'invalid_request')
    if len(payload)>MAX_INPUT_BYTES:raise MetadataError(2,'metadata_values_full')
    reader=_Reader(payload)
    version,size=reader.unpack('<II')
    if version!=0x301:raise MetadataError(3,'invalid_request')
    if size!=len(payload)-8:raise MetadataError(0x13 if size>len(payload)-8 else 0x15,'invalid_request')
    class_id,target,selector_a,selector_b=reader.unpack('<HIII')
    if class_id!=0x349 or selector_a or selector_b:
        raise MetadataError(0x0F,'metadata_values_not_permitted')
    count=reader.unpack('<H')[0] if not reference else 1
    if not target or not 1<=count<=MAX_FIELDS:raise MetadataError(3,'invalid_request')
    fields=[];seen=set()
    for _ in range(count):
        marker,=reader.unpack('<H')
        field=reader.unpack('<H')[0] if not reference else reference
        first,second,third=reader.unpack('<III')
        if marker!=0x7F or first or second or third:
            raise MetadataError(0x0F,'metadata_value_selector_not_permitted')
        if not field or field in seen:raise MetadataError(3,'invalid_request')
        seen.add(field)
        kind,=reader.unpack('<H')
        if kind==1:
            size,=reader.unpack('<H')
            if size>MAX_FIELD_BYTES:raise MetadataError(2,'metadata_values_full')
            data=reader.take(size)
            if any(c not in (9,10,13) and not 32<=c<127 for c in data):
                raise MetadataError(3,'invalid_request')
            value=Value(1,None,1,data)
        elif kind==2:
            code,elements=reader.unpack('<HH')
            if code not in (0xC2,0xC3):raise MetadataError(0x0F,'metadata_value_type_not_permitted')
            width=1 if code==0xC2 else 2
            if not elements or elements*width>MAX_FIELD_BYTES:raise MetadataError(3,'invalid_request')
            value=Value(2,code,elements,reader.take(elements*width))
        else:raise MetadataError(0x0F,'metadata_value_type_not_permitted')
        fields.append((field,value))
    if reader.offset!=len(payload):raise MetadataError(0x15,'invalid_request')
    return target,tuple(fields)


class MetadataStaging:
    def __init__(self):self.rows={};self.values={}

    def create(self,instance,payload):
        if type(instance) is not int or not 1<=instance<=0xFFFFFFFF:
            raise MetadataError(5,'invalid_request')
        name=parse_create(payload)
        previous=self.rows.get(instance)
        if previous is not None:
            if previous!=name:raise MetadataError(0x0C,'metadata_stage_conflict')
        else:
            if name in self.rows.values():raise MetadataError(0x0C,'metadata_stage_conflict')
            if len(self.rows)>=MAX_DEFINITIONS:raise MetadataError(2,'metadata_stage_full')
            self.rows[instance]=name
        return struct.pack('<I',instance)

    def delete(self,instance):
        if type(instance) is not int or instance not in self.rows:
            raise MetadataError(5,'metadata_stage_missing')
        del self.rows[instance]
        # Remove only staged targets and references; never touch active objects.
        self.values={target:{reference:value for reference,value in fields.items() if reference!=instance}
                     for target,fields in self.values.items() if target!=instance}
        self.values={target:fields for target,fields in self.values.items() if fields}

    def stage_values(self,payload,reference=0):
        target,fields=parse_values(payload,reference)
        if target not in self.rows or any(reference not in self.rows for reference,_ in fields):
            raise MetadataError(5,'metadata_stage_missing')
        previous=self.values.get(target,{})
        proposal=dict(previous)
        for reference,value in fields:
            if reference in proposal and proposal[reference]!=value:
                raise MetadataError(0x0C,'metadata_value_conflict')
            proposal[reference]=value
        targets=dict(self.values);targets[target]=proposal
        count=sum(map(len,targets.values()))
        size=sum(len(value.data) for row in targets.values() for value in row.values())
        if len(proposal)>MAX_FIELDS or count>MAX_VALUES or size>MAX_VALUE_BYTES:
            raise MetadataError(2,'metadata_values_full')
        self.values[target]=proposal

    def clear(self):self.rows.clear();self.values.clear()

    def description(self):
        return {'descriptor_only':False,'instances':len(self.rows),
                'name_bytes':sum(map(len,self.rows.values())),
                'max_instances':MAX_DEFINITIONS,'max_name_bytes':MAX_NAME_BYTES,
                'values_transfer':True,'values_scope':'staged_definitions','active_values_transfer':False,
                'value_targets':len(self.values),'value_count':sum(map(len,self.values.values())),
                'value_bytes':sum(len(value.data) for row in self.values.values() for value in row.values()),
                'max_packet_bytes':MAX_INPUT_BYTES,'max_field_bytes':MAX_FIELD_BYTES,
                'max_fields_per_target':MAX_FIELDS,'max_values':MAX_VALUES,'max_value_bytes':MAX_VALUE_BYTES,
                'supported_value_types':['ASCII','SINT','INT'],
                'commit':False,'names_exposed':False,'values_exposed':False}
