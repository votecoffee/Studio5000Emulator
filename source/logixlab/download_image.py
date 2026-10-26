"""An isolated, source-bound device image prepared from native download records.

This allocates the declared temporary Data Table storage and joins its Symbol
references. It does not install an active project, interpret compiled routines,
apply initial values, or implement Resilient Transport execution/commit services.
"""
from dataclasses import dataclass
import hashlib
import re
import struct
from types import MappingProxyType

from .object_staging import NULL_REFERENCE, MAX_STORAGE_BYTES,table_key,table_instance,valid_table_key
from .download_results import ResultLedger,ResultError

MAX_READ_BYTES = 16384
SUPPORTED_OPERATIONS = frozenset(((8,0x6C),(4,0x6C),(0x4D,0x6C),(8,0x3B2),
                                 (8,0x68),(8,0x6A),(8,0x6B),(8,0x6D),
                                 (0x4B,0x74),(0x4C,0x74)))


class ImageError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)


@dataclass(frozen=True)
class Source:
    acd_sha256:str
    l5x_sha256:str

    def __post_init__(self):
        if any(not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None
               for value in (self.acd_sha256,self.l5x_sha256)):
            raise ImageError('invalid_download_image_source')


@dataclass(frozen=True)
class Region:
    instance:int
    type_code:int
    dimensions:tuple
    elements:int
    data:bytes
    program:int=0


class DownloadImage:
    """Owned temporary bytes; no references to an Engine or its active tags.

    A prepared image can serve bounded readback by table or reciprocally linked
    controller Symbol ID. Program Symbols without a table remain unresolved.
    Reads require both original ACD and converted L5X hashes to match.
    """
    def __init__(self,source=None,templates=(),diagnostics=(),objects=None,records=0,
                 record_sha256=None,reason=None):
        self.source=source;self.templates=tuple(templates);self.diagnostics=tuple(diagnostics)
        self.programs=tuple(objects.programs) if objects is not None else ()
        self.routines=tuple(objects.routines) if objects is not None else ()
        self._coordination_records=objects.coordination if objects is not None else 0
        self._results=ResultLedger()
        self.records=records;self.record_sha256=record_sha256;self.reason=reason
        self._tables=MappingProxyType({t.key:t for t in objects.tables} if objects is not None else {})
        self._regions=MappingProxyType({t.key:Region(t.instance,t.type_code,t.dimensions,t.elements,
                                                        bytes(t.storage_bytes),t.program)
                                       for t in objects.tables} if objects is not None else {})
        self._symbols=MappingProxyType({(s.program,s.instance):table_key(s.program,s.table) for s in objects.symbols}
                                      if objects is not None else {})

    @classmethod
    def prepare(cls,batch,templates,diagnostics,objects,native_types,source_verification):
        """Materialize only an entirely modeled, source-verified batch.

        The caller has already built all three staging models atomically. An
        unrelated/unknown record blocks image allocation, including a service on
        a known class which a descriptor parser deliberately left uninterpreted.
        """
        if not batch:return cls(reason='empty_device_batch')
        if any((r.service,r.scopes[-1].class_id) not in SUPPORTED_OPERATIONS for r in batch):
            return cls(reason='unmodeled_device_record')
        count=templates.records+len(diagnostics.messages)+objects.records
        if count!=len(batch):return cls(reason='device_record_coverage_mismatch')
        if native_types is None:return cls(reason='native_type_source_required')
        if (source_verification.get('status')!='matched'
                or source_verification.get('types_matched')!=len(templates.templates)
                or source_verification.get('types_unavailable')!=0):
            return cls(reason='source_verified_types_required')
        source=Source(native_types.source_acd_sha256,native_types.source_l5x_sha256)
        if sum(t.storage_bytes for t in objects.tables)>MAX_STORAGE_BYTES:
            raise ImageError('download_image_storage_limit')
        digest=hashlib.sha256()
        for row in batch:digest.update(struct.pack('<I',len(row.request)));digest.update(row.request)
        image=cls(source,templates.templates,diagnostics.messages,objects,count,digest.hexdigest())
        try:image._results=ResultLedger.from_image(batch,image)
        except ResultError as error:raise ImageError(error.reason) from error
        return image

    def require_source(self,source):
        if self.source is None:raise ImageError('download_image_unavailable')
        if not isinstance(source,Source) or source!=self.source:
            raise ImageError('download_image_source_mismatch')

    def read_table(self,instance,offset,count,source):
        self.require_source(source)
        if not valid_table_key(instance) or instance not in self._regions:
            raise ImageError('download_table_unavailable')
        row=self._regions[instance]
        if (type(offset) is not int or type(count) is not int or offset<0
                or not 1<=count<=MAX_READ_BYTES or offset+count>len(row.data)):
            raise ImageError('download_table_read_range')
        return row.data[offset:offset+count]

    def read_symbol(self,program,instance,offset,count,source):
        self.require_source(source)
        if type(program) is not int or type(instance) is not int or (program,instance) not in self._symbols:
            raise ImageError('download_symbol_unavailable')
        table=self._symbols[program,instance]
        if table==NULL_REFERENCE:raise ImageError('download_symbol_storage_unresolved')
        return self.read_table(table,offset,count,source)

    def read_template(self,instance,offset,count,source):
        self.require_source(source)
        row=next((t for t in self.templates if t.instance==instance),None) if type(instance) is int else None
        if row is None:raise ImageError('download_template_unavailable')
        if (type(offset) is not int or type(count) is not int or offset<0 or not 1<=count<=MAX_READ_BYTES
                or offset+count>len(row.definition)):raise ImageError('download_template_read_range')
        return row.definition[offset:offset+count]

    def _require_results(self,source):
        self.require_source(source)
        if (self._results.record_sha256!=self.record_sha256 or len(self._results.results)!=self.records
                or self._results.source_acd_sha256!=source.acd_sha256
                or self._results.source_l5x_sha256!=source.l5x_sha256):
            raise ImageError('download_result_binding_changed')

    def preparation_results(self,offset,count,source):
        """Private, bounded ordered model results; never vendor response bytes."""
        self._require_results(source)
        try:return self._results.page(offset,count)
        except ResultError as error:raise ImageError(error.reason) from error

    def read_preparation_effect(self,ordinal,source):
        """Compare a retained result with its actual temporary resource."""
        self._require_results(source)
        try:return self._results.readback(self,ordinal)
        except ResultError as error:raise ImageError(error.reason) from error

    def attribute(self,class_id,instance,attribute,source,program=0):
        """Typed attribute bytes backed by the temporary objects only.

        Physical/compiled addresses and names are absent from this batch. This
        does not invent either; an unavailable attribute is an explicit error.
        """
        self.require_source(source)
        if any(type(v) is not int for v in (class_id,instance,attribute,program)):
            raise ImageError('invalid_download_attribute')
        if class_id==0x6B:
            if (program,instance) not in self._symbols:raise ImageError('download_symbol_unavailable')
            attrs={9:b'\0',12:struct.pack('<I',table_instance(self._symbols[program,instance]))}
        elif class_id==0x6A:
            row=self._tables.get(table_key(program,instance))
            if row is None:raise ImageError('download_table_unavailable')
            attrs={1:struct.pack('<III',*row.dimensions),2:struct.pack('<H',row.type_code),
                   6:struct.pack('<H',row.data_use),8:struct.pack('<I',row.symbol),9:b'\0\0'}
        elif class_id==0x6C and program==0:
            row=next((t for t in self.templates if t.instance==instance),None)
            if row is None:raise ImageError('download_template_unavailable')
            a=row.attributes
            attrs={1:struct.pack('<H',a.handle),2:struct.pack('<H',a.members),4:struct.pack('<I',row.words),
                   5:struct.pack('<I',a.structure_bytes),6:struct.pack('<H',a.family),8:bytes((a.recon,))}
        else:raise ImageError('download_attribute_scope_unavailable')
        if attribute not in attrs:raise ImageError('download_attribute_unavailable')
        return attrs[attribute]

    def description(self):
        return {'status':'prepared' if self.source is not None else 'blocked' if self.reason else 'idle',
                **({'reason':self.reason} if self.reason else {}),
                'source_bound':self.source is not None,'records_prepared':self.records,
                'preparation_results':self._results.description(),
                'record_sha256':self.record_sha256,'tables_allocated':len(self._regions),
                'templates_retained':len(self.templates),'diagnostics_retained':len(self.diagnostics),
                'programs_retained':len(self.programs),'routines_retained':len(self.routines),
                'storage_bytes':sum(len(r.data) for r in self._regions.values()),
                'symbols_linked':sum(t!=NULL_REFERENCE for t in self._symbols.values()),
                'symbols_unresolved':sum(t==NULL_REFERENCE for t in self._symbols.values()),
                'max_storage_bytes':MAX_STORAGE_BYTES,'max_read_bytes':MAX_READ_BYTES,
                'temporary_readback':self.source is not None,'initial_values_applied':False,
                'compiled_routines_installed':False,'active_catalog_replaced':False,
                'native_execution_supported':False,'commit':False,'values_exposed':False}
