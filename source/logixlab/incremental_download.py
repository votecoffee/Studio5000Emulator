"""Isolated later-batch proposals; unknown operations prevent completion.

Source metadata is preserved as typed values, not resolved to executable
objects. Whole-table writes affect private proposals, never the base image.
"""
from collections import Counter
from dataclasses import dataclass,replace
import hashlib
import json
import struct
from types import MappingProxyType

from .download_image import ImageError
from . import metadata_query
from .native_metadata_values import NativeMetadataValues,encode_records
from .download_headers import WIDTHS,path_key
from . import device_payload

MAX_METADATA_VALUES=4096
ROUTINE_DATA=b'\1'+struct.pack('<III',13,13,0)


@dataclass(frozen=True)
class UpdateResult:
    ordinal:int
    request_sha256:str
    kind:str
    key:tuple
    expected:object


def record_digest(batch):
    digest=hashlib.sha256()
    for row in batch:
        digest.update(struct.pack('<I',len(row.request)));digest.update(row.request)
    return digest.hexdigest()


def routine_data(row):
    """Unwrap only the observed Router/Routine storage profile.

    The thirteen bytes are opaque component data, not source, code, an axis
    configuration or a decoded collection. No identifier or address is used.
    """
    if len(row.scopes)!=1 or row.scopes[0]!=device_payload.Scope(2,1):
        raise ImageError('incremental_routine_router_scope')
    raw=row.request[2+2*row.request[1]:]
    if len(raw)<10:raise ImageError('incremental_routine_router_extent')
    version,size=struct.unpack_from('<II',raw);inner=raw[8:];end=2+2*inner[1]
    if version!=0x301 or size!=13 or end+21!=len(inner) or inner[0]!=0x5C:
        raise ImageError('incremental_routine_data_profile')
    try:scopes=device_payload.record_path(inner[2:end])
    except device_payload.PayloadError as error:raise ImageError('incremental_routine_data_path') from error
    nested=device_payload.Record(inner[0],scopes,inner);key=path_key(nested)
    if key[0]!=0x6D or not key[1] or inner[end:end+8]!=struct.pack('<II',1,9) or inner[end+8:]!=ROUTINE_DATA:
        raise ImageError('incremental_routine_data_profile')
    return key[1:],inner[end+8:]


def metadata_stamp(values,source):
    if (not isinstance(values,NativeMetadataValues)
            or (values.source_acd_sha256,values.source_l5x_sha256)!=(source.acd_sha256,source.l5x_sha256)):
        raise ImageError('incremental_metadata_source_required')
    try:
        if (values.definitions.source_acd_sha256,values.definitions.source_l5x_sha256)!=(source.acd_sha256,source.l5x_sha256):
            raise ImageError('incremental_metadata_source_changed')
        raw=encode_records(values.rows)
        if raw!=values.body('all-objects'):raise ImageError('incremental_metadata_source_changed')
        definitions=json.dumps(values.definitions.manifest(),sort_keys=True,separators=(',',':')).encode()
    except (ValueError,TypeError,KeyError,AttributeError,struct.error,OverflowError) as error:
        if isinstance(error,ImageError):raise
        raise ImageError('incremental_metadata_source_changed') from error
    return hashlib.sha256(raw+definitions).hexdigest()


def value_identity(row):
    # Wire record words differ between download packets and the source catalog.
    # Every actual target, locale, definition and typed value still must match.
    return (row.target,row.locale_word,row.definition,row.kind,row.data,row.type_code,row.elements,row.references)


def image_binding(image):
    return (image.record_sha256,image.records,image.templates,image.diagnostics,image.programs,image.routines,
            tuple(image._regions.items()),tuple(image._tables.items()),tuple(image._symbols.items()))


class IncrementalDownload:
    def __init__(self):
        self._image=None;self._binding=None;self._source=None;self._metadata_stamp=None
        self._metadata=();self._tables=MappingProxyType({});self._diagnostics=();self._coordination=()
        self.records=0;self.metadata_packets=0;self._unsupported=()
        self._headers=MappingProxyType({});self._header_stamp=None
        self._routine_data=MappingProxyType({});self._effects=();self.record_sha256=None;self._effect_stamp=None;self._ledger_binding=None

    @classmethod
    def prepare(cls,batch,image,source,native_metadata_values=None,header_bindings=None):
        image.require_source(source)
        proposal=cls();metadata=[];tables={};diagnostics=[];coordination=[];held=set();seen=set()
        original=None;stamp=None;unsupported=Counter();modeled=packets=0
        headers={};header_stamp=None;components={};effects=[]
        def effect(row,kind,key,expected):
            effects.append(UpdateResult(len(effects),hashlib.sha256(row.request).hexdigest(),kind,key,expected))
        for row in batch:
            leaf=row.scopes[-1];operation=(row.service,leaf.class_id)
            if operation==(0x33,2):
                key,data=routine_data(row)
                if key[0] not in held:raise ImageError('incremental_routine_program_reservation_required')
                if header_bindings is None:raise ImageError('incremental_routine_source_required')
                if header_stamp is None:header_stamp=header_bindings.stamp(image,source)
                header_bindings.expected(0x6D,*key)
                if key in components:raise ImageError('incremental_duplicate_routine_data')
                components[key]=data;effect(row,'routine',key,data);modeled+=1;continue
            if row.service==4 and leaf.class_id in WIDTHS and header_bindings is not None:
                if header_stamp is None:header_stamp=header_bindings.stamp(image,source)
                key=path_key(row)
                if key[1] and key[1] not in held:raise ImageError('incremental_header_program_reservation_required')
                key,values=header_bindings.check(row)
                if key in headers:raise ImageError('incremental_duplicate_header_update')
                headers[key]=values;effect(row,'header',key,values);modeled+=1;continue
            if operation not in ((0x4F,0x349),(0x50,0x6A),(4,0x3B2),(0x4B,0x74),(0x4C,0x74)):
                unsupported[operation]+=1;effects.append(None);continue
            if any(s.attribute is not None or s.symbolic or type(s.instance) is not int
                   or not (0 if s is leaf and operation==(0x4F,0x349) else 1)<=s.instance<=0xFFFFFFFF
                   for s in row.scopes):
                raise ImageError('incremental_object_path_unsupported')
            payload=row.request[2+2*row.request[1]:]
            if leaf.class_id==0x74:
                if (len(row.scopes)!=2 or row.scopes[0].class_id!=0x68 or leaf.instance!=1
                        or row.scopes[0].instance not in image.programs):
                    raise ImageError('incremental_program_scope_required')
                program=row.scopes[0].instance;before=program in held
                if row.service==0x4B:
                    if payload!=b'\1' or before:raise ImageError('incremental_program_acquire_invalid')
                    held.add(program)
                else:
                    if payload or not before:raise ImageError('incremental_program_release_invalid')
                    held.remove(program)
                coordination.append((program,before,program in held))
                effect(row,'coordination',(len(coordination)-1,),coordination[-1])
            else:
                if len(row.scopes)!=1:raise ImageError('incremental_global_scope_required')
                if leaf.class_id==0x3B2:
                    if payload!=b'\0\0':raise ImageError('incremental_diagnostic_attributes_unsupported')
                    if not any(d.instance==leaf.instance for d in image.diagnostics):
                        raise ImageError('incremental_diagnostic_missing')
                    diagnostics.append(leaf.instance)
                    effect(row,'diagnostic',(len(diagnostics)-1,),leaf.instance)
                elif leaf.class_id==0x6A:
                    region=image._regions.get(leaf.instance)
                    if region is None:raise ImageError('incremental_table_missing')
                    if len(payload)<7:raise ImageError('incremental_table_write_extent')
                    offset,selector,size=struct.unpack_from('<IBH',payload)
                    if offset or selector:raise ImageError('incremental_table_write_profile')
                    if not size or size!=len(region.data) or len(payload)!=size+7:
                        raise ImageError('incremental_table_write_extent')
                    if leaf.instance in tables:raise ImageError('incremental_duplicate_table_write')
                    tables[leaf.instance]=replace(region,data=payload[7:])
                    effect(row,'table',(leaf.instance,),payload[7:])
                else:
                    if original is None:
                        stamp=metadata_stamp(native_metadata_values,source)
                        original={value_identity(value) for value in native_metadata_values.rows}
                    try:values=metadata_query.download_records(payload,leaf.instance)
                    except ValueError as error:raise ImageError('incremental_metadata_packet_invalid') from error
                    start=len(metadata)
                    for value in values:
                        if value_identity(value) not in original:raise ImageError('incremental_metadata_value_mismatch')
                        key=(value.target,value.locale_word,value.definition)
                        if key in seen:raise ImageError('incremental_duplicate_metadata_value')
                        if len(metadata)>=MAX_METADATA_VALUES:raise ImageError('incremental_metadata_value_limit')
                        seen.add(key);metadata.append(value)
                    packets+=1
                    effect(row,'metadata',(start,len(metadata)),tuple(metadata[start:]))
            modeled+=1
        if held:raise ImageError('incremental_program_coordination_incomplete')
        if stamp is not None and metadata_stamp(native_metadata_values,source)!=stamp:
            raise ImageError('incremental_metadata_source_changed')
        if header_stamp is not None and header_bindings.stamp(image,source)!=header_stamp:
            raise ImageError('incremental_header_source_changed')
        proposal._image=image;proposal._binding=image_binding(image);proposal._source=source;proposal._metadata_stamp=stamp
        proposal._metadata=tuple(metadata);proposal._tables=MappingProxyType(tables)
        proposal._diagnostics=tuple(diagnostics);proposal._coordination=tuple(coordination)
        proposal.records=modeled;proposal.metadata_packets=packets
        proposal._headers=MappingProxyType(headers);proposal._header_stamp=header_stamp
        proposal._routine_data=MappingProxyType(components);proposal._effects=tuple(effects)
        proposal.record_sha256=record_digest(batch)
        proposal._effect_stamp=hashlib.sha256(repr(proposal._effects).encode()).hexdigest()
        proposal._ledger_binding=(proposal.record_sha256,len(proposal._effects),proposal.records,proposal._effect_stamp)
        proposal._unsupported=tuple((service,cls,count) for (service,cls),count in sorted(unsupported.items()))
        return proposal

    def validate(self,image,source,native_metadata_values=None,header_bindings=None):
        image.require_source(source)
        if image is not self._image or source!=self._source or image_binding(image)!=self._binding:
            raise ImageError('incremental_base_image_changed')
        if self._ledger_binding!=(self.record_sha256,len(self._effects),self.records,self._effect_stamp):
            raise ImageError('incremental_result_binding_changed')
        if self._metadata_stamp is not None and metadata_stamp(native_metadata_values,source)!=self._metadata_stamp:
            raise ImageError('incremental_metadata_source_changed')
        if self._header_stamp is not None and (header_bindings is None or header_bindings.stamp(image,source)!=self._header_stamp):
            raise ImageError('incremental_header_source_changed')

    def verify_effects(self,image,source,native_metadata_values=None,header_bindings=None):
        self.validate(image,source,native_metadata_values,header_bindings)
        if self._unsupported or not self.records or len(self._effects)!=self.records:
            raise ImageError('incremental_record_coverage_incomplete')
        if hashlib.sha256(repr(self._effects).encode()).hexdigest()!=self._effect_stamp:
            raise ImageError('incremental_effect_ledger_changed')
        for ordinal,result in enumerate(self._effects):
            if result is None or result.ordinal!=ordinal:raise ImageError('incremental_effect_ledger_changed')
            key=result.key
            if result.kind=='header':observed=self._headers.get(key)
            elif result.kind=='routine':observed=self._routine_data.get(key)
            elif result.kind=='table':observed=self._tables[key[0]].data if key[0] in self._tables else None
            elif result.kind=='metadata':observed=self._metadata[key[0]:key[1]]
            elif result.kind=='diagnostic':observed=self._diagnostics[key[0]] if key[0]<len(self._diagnostics) else None
            elif result.kind=='coordination':observed=self._coordination[key[0]] if key[0]<len(self._coordination) else None
            else:raise ImageError('incremental_effect_kind_unavailable')
            if observed!=result.expected:raise ImageError('incremental_effect_readback_mismatch')

    def read_routine_data(self,program,instance,image,source,header_bindings,native_metadata_values=None):
        self.validate(image,source,native_metadata_values,header_bindings)
        if any(type(v) is not int for v in (program,instance)) or (program,instance) not in self._routine_data:
            raise ImageError('incremental_routine_data_unavailable')
        return self._routine_data[program,instance]

    def read_metadata(self,ordinal,image,source,native_metadata_values,header_bindings=None):
        self.validate(image,source,native_metadata_values,header_bindings)
        if type(ordinal) is not int or not 0<=ordinal<len(self._metadata):raise ImageError('incremental_metadata_read_range')
        return self._metadata[ordinal]

    def read_table(self,instance,image,source,native_metadata_values=None,header_bindings=None):
        self.validate(image,source,native_metadata_values,header_bindings)
        if type(instance) is not int or instance not in self._tables:raise ImageError('incremental_table_read_unavailable')
        return self._tables[instance].data

    def read_attribute(self,class_id,program,instance,number,image,source,native_metadata_values=None,header_bindings=None):
        self.validate(image,source,native_metadata_values,header_bindings)
        if any(type(v) is not int for v in (class_id,program,instance,number)):
            raise ImageError('incremental_header_read_invalid')
        row=dict(self._headers.get((class_id,program,instance),()))
        if number not in row:raise ImageError('incremental_header_read_unavailable')
        return row[number]

    def description(self):
        return dict(status='partial' if self._unsupported else 'modeled' if self._image is not None else 'idle',
            records_modeled=self.records,unsupported_records=sum(n for _,_,n in self._unsupported),
            unsupported_operations=[dict(service=s,class_id=c,count=n) for s,c,n in self._unsupported],
            metadata_packets=self.metadata_packets,metadata_values=len(self._metadata),
            max_metadata_values=MAX_METADATA_VALUES,
            source_metadata_verified=self._metadata_stamp is not None,metadata_targets_resolved=False,
            table_writes=len(self._tables),table_bytes=sum(len(t.data) for t in self._tables.values()),
            diagnostic_empty_updates=len(self._diagnostics),coordination_records=len(self._coordination),
            header_updates=len(self._headers),header_attributes=sum(len(v) for v in self._headers.values()),
            routine_data_records=len(self._routine_data),routine_data_bytes=sum(map(len,self._routine_data.values())),
            routine_data_interpreted=False,result_records=sum(e is not None for e in self._effects),
            opaque_symbol_controls=sum(k[0]==0x6B for k in self._headers),symbol_control_bits_interpreted=False,
            open_coordination=0,base_image_modified=False,active_catalog_replaced=False,
            execution_supported=False,completion_supported=False,commit=False,payloads_exposed=False)
