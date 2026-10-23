"""Lease-owned Symbol handles for a completed temporary download image.

Handles identify retained model objects, not physical memory. No firmware
descriptor layout, initial values or compiled code is inferred from them.
"""
from dataclasses import dataclass
import struct
from types import MappingProxyType

from .download_image import ImageError
from .download_image import MAX_READ_BYTES
from . import source_object_verification
from .download_tasks import DownloadTasks
from .download_controller import DownloadController
from .download_properties import DownloadProperties
from .download_repository import DownloadRepository
from .download_setup import DownloadSetup
from .download_map import DownloadMap
from .download_changelog import DownloadChangelog

SYMBOL_BASE=0x70000000
SYMBOL_STRIDE=32
TABLE_BASE=0x71000000
VALUE_BASE=0x72000000
ROUTINE_BASE=0x73000000
PROGRAM_BASE=0x74000000


@dataclass(frozen=True)
class SymbolHandle:
    address:int
    program:int
    instance:int
    table:int


@dataclass(frozen=True)
class TableHandle:
    address:int
    value_address:int
    instance:int


@dataclass(frozen=True)
class RoutineHandle:
    address:int
    program:int
    instance:int


@dataclass(frozen=True)
class ProgramHandle:
    address:int
    instance:int


class DownloadNamespace:
    def __init__(self,transport,native_types,**catalogs):
        transport.execution_status(native_types,**catalogs)
        if transport.source_object_verification['status']!='matched':
            raise ImageError('download_namespace_source_identities_required')
        self._image=transport.download_image
        self._incremental=None
        self._routine_batch=None
        self.tasks=DownloadTasks()
        self.controller=DownloadController()
        self.properties=DownloadProperties()
        self.repository=DownloadRepository()
        self.setup=DownloadSetup()
        self.local_map=DownloadMap()
        self.change_log=DownloadChangelog()
        self._source=self._image.source
        self._binding=(self._image.record_sha256,self._image.records)
        self._types=native_types;self._type_stamp=native_types.binding_stamp()
        self._catalog_stamp=source_object_verification.binding_stamp(
            catalogs.get('native_symbols'),catalogs.get('native_routines'),
            catalogs.get('native_auxiliary_symbols'),catalogs.get('native_tables'))
        self._symbols=tuple(SymbolHandle(SYMBOL_BASE+slot*SYMBOL_STRIDE,program,instance,table)
            for slot,((program,instance),table) in enumerate(sorted(self._image._symbols.items())))
        self._by_address=MappingProxyType({row.address:row for row in self._symbols})
        tables=[];offset=0
        for slot,instance in enumerate(sorted(self._image._tables)):
            tables.append(TableHandle(TABLE_BASE+slot*32,VALUE_BASE+offset,instance))
            offset+=(len(self._image._regions[instance].data)+7)//8*8
        self._tables=tuple(tables)
        self._table_addresses=MappingProxyType({row.address:row for row in self._tables})
        self._routines=tuple(RoutineHandle(ROUTINE_BASE+slot*32,row.program,row.instance)
            for slot,row in enumerate(sorted(self._image.routines,key=lambda r:(r.program,r.instance))))
        self._routine_addresses=MappingProxyType({row.address:row for row in self._routines})
        self._programs=tuple(ProgramHandle(PROGRAM_BASE+slot*32,instance)
            for slot,instance in enumerate(sorted(self._image.programs)))
        self._program_addresses=MappingProxyType({row.address:row for row in self._programs})

    def validate(self,source,native_types,*,native_metadata_values=None,header_bindings=None,task_bindings=None,controller_bindings=None,device_identity=None,setup_bindings=None,routine_bindings=None,map_bindings=None,changelog_bindings=None,**catalogs):
        self.validate_base(source,native_types,**catalogs)
        if self._incremental is not None:
            self._incremental.verify_effects(self._image,source,native_metadata_values,header_bindings)
        self.tasks.validate(task_bindings)
        self.controller.validate(controller_bindings)
        self.properties.validate(source,native_metadata_values,
            controller_bindings.engine.project if controller_bindings is not None else None)
        self.repository.validate(source,controller_bindings.engine.project if controller_bindings is not None else None,device_identity)
        self.setup.validate(setup_bindings)
        if self._routine_batch is not None:
            self.setup.require_complete(setup_bindings)
            self._routine_batch.verify_effects(routine_bindings)
        self.local_map.validate(map_bindings)
        self.change_log.validate(changelog_bindings)

    def retain_incremental(self,transport,source,native_metadata_values=None,header_bindings=None):
        if self._incremental is not None:raise ImageError('incremental_batch_sequence_unimplemented')
        if not transport.incremental_status_reported:raise ImageError('incremental_result_query_required')
        transport.incremental_execution_status(self._image,source,native_metadata_values,header_bindings)
        self._incremental=transport.incremental

    def retain_routines(self,transport,bindings,setup_bindings):
        if self._incremental is None:raise ImageError('completed_incremental_download_required')
        if self._routine_batch is not None:raise ImageError('download_routine_batch_already_retained')
        self.setup.require_complete(setup_bindings)
        if not transport.routine_status_reported:raise ImageError('download_routine_result_query_required')
        transport.routine_execution_status(bindings)
        self._routine_batch=transport.routine_batch

    def validate_base(self,source,native_types,**catalogs):
        self._image.require_source(source)
        try:
            if native_types is not self._types or native_types.binding_stamp()!=self._type_stamp:
                raise ImageError('download_namespace_type_binding_changed')
            stamp=source_object_verification.binding_stamp(
                catalogs.get('native_symbols'),catalogs.get('native_routines'),
                catalogs.get('native_auxiliary_symbols'),catalogs.get('native_tables'))
            if stamp!=self._catalog_stamp:raise ImageError('download_namespace_object_binding_changed')
        except (ValueError,TypeError,KeyError,AttributeError) as error:
            if isinstance(error,ImageError):raise
            raise ImageError('download_namespace_catalog_unavailable') from error
        if self._binding!=(self._image.record_sha256,self._image.records):
            raise ImageError('download_namespace_image_binding_changed')
        for ordinal in range(self._image.records):
            if not self._image.read_preparation_effect(ordinal,source).matches:
                raise ImageError('download_namespace_effect_changed')

    def symbol_page(self,program,start,budget):
        if (any(type(value) is not int for value in (program,start,budget))
                or not 0<=program<=0xFFFFFFFF or not 0<=start<=0xFFFFFFFF or budget<0):
            raise ImageError('invalid_download_symbol_page')
        if program and program not in self._image.programs:
            raise ImageError('download_symbol_program_unavailable')
        rows=[row for row in self._symbols if row.program==program and row.instance>=start]
        count=min(len(rows),budget//8)
        if rows and not count:raise ImageError('download_symbol_reply_budget')
        return count<len(rows),b''.join(struct.pack('<II',row.instance,row.address) for row in rows[:count])

    def resolve_symbol(self,address):
        """Resolve an exact handle; never interpret arbitrary memory ranges."""
        if type(address) is not int or address not in self._by_address:
            raise ImageError('download_symbol_address_unavailable')
        return self._by_address[address]

    def table_page(self,start,budget):
        if (type(start) is not int or not 0<=start<=0xFFFFFFFF
                or type(budget) is not int or budget<0):
            raise ImageError('invalid_download_table_page')
        rows=[row for row in self._tables if row.instance>=start]
        count=min(len(rows),budget//12)
        if rows and not count:raise ImageError('download_table_reply_budget')
        return count<len(rows),b''.join(struct.pack('<III',row.instance,row.address,row.value_address) for row in rows[:count])

    def resolve_table(self,address):
        if type(address) is not int or address not in self._table_addresses:
            raise ImageError('download_table_address_unavailable')
        return self._image._tables[self._table_addresses[address].instance]

    def read_values(self,address,count):
        if type(address) is not int or type(count) is not int or not 1<=count<=MAX_READ_BYTES:
            raise ImageError('invalid_download_value_range')
        for row in self._tables:
            region=self._image._regions[row.instance]
            if row.value_address<=address<row.value_address+len(region.data):
                if self._incremental is not None and row.instance in self._incremental._tables:
                    data=self._incremental._tables[row.instance].data;offset=address-row.value_address
                    if offset+count>len(data):raise ImageError('download_table_read_range')
                    return data[offset:offset+count]
                return self._image.read_table(row.instance,address-row.value_address,count,self._source)
        raise ImageError('download_value_address_unavailable')

    def routine_page(self,program,start,budget):
        if (any(type(value) is not int for value in (program,start,budget))
                or not 1<=program<=0xFFFFFFFF or not 0<=start<=0xFFFFFFFF or budget<0):
            raise ImageError('invalid_download_routine_page')
        if program not in self._image.programs:raise ImageError('download_routine_program_unavailable')
        rows=[row for row in self._routines if row.program==program and row.instance>=start]
        count=min(len(rows),budget//8)
        if rows and not count:raise ImageError('download_routine_reply_budget')
        return count<len(rows),b''.join(struct.pack('<II',row.instance,row.address) for row in rows[:count])

    def resolve_routine(self,address):
        if type(address) is not int or address not in self._routine_addresses:
            raise ImageError('download_routine_address_unavailable')
        handle=self._routine_addresses[address]
        return next(row for row in self._image.routines if (row.program,row.instance)==(handle.program,handle.instance))

    def program_page(self,start,budget):
        if type(start) is not int or not 0<=start<=0xFFFFFFFF or type(budget) is not int or budget<0:
            raise ImageError('invalid_download_program_page')
        rows=[row for row in self._programs if row.instance>=start]
        count=min(len(rows),budget//8)
        if rows and not count:raise ImageError('download_program_reply_budget')
        return count<len(rows),b''.join(struct.pack('<II',row.instance,row.address) for row in rows[:count])

    def resolve_program(self,address):
        if type(address) is not int or address not in self._program_addresses:
            raise ImageError('download_program_address_unavailable')
        return self._program_addresses[address]

    def description(self):
        return dict(status='retained',symbols=len(self._symbols),tables=len(self._tables),programs=len(self._programs),routines=len(self._routines),
            source_bound=True,owner_only=True,modeled_handles=True,physical_addresses=False,
            incremental_batches_retained=int(self._incremental is not None),
            incremental_records=self._incremental.records if self._incremental is not None else 0,
            routine_batch=self._routine_batch.description() if self._routine_batch is not None else None,
            tasks=self.tasks.description(),
            controller_configuration=self.controller.description(),
            controller_properties=self.properties.description(),
            device_repository=self.repository.description(),
            setup_configuration=self.setup.description(),
            local_map=self.local_map.description(),
            change_log=self.change_log.description(),
            descriptor_memory_reads=False,active_catalog_replaced=False,commit=False)
