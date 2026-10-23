"""Lease-local setup for the observed Resilient Transport Object dialect.

The final setup word bounds the expected expanded size in the inspected profile.
Fragments stay in a temporary buffer. No records execute and no active project changes.
"""
import struct
import time
from . import device_payload
from .template_staging import TemplateStaging,TemplateError
from .diagnostic_staging import DiagnosticStaging,DiagnosticError
from .object_staging import ObjectStaging,ObjectError
from .download_image import DownloadImage,ImageError,Source
from .download_results import ExecutionStatus,ResultError
from .native_types import verification
from . import source_object_verification as object_verification
from .signed_messages import (FragmentEnvelope,CompactTransferEnvelope,FRAGMENT_FORMATS,MAX_MESSAGE,
                              DEVICE_TRANSFER_HEADER,validate_compact_transfer,EnvelopeError)
from .incremental_download import IncrementalDownload,record_digest
from .download_routines import RoutineBatch

MAX_BUFFER_BYTES = 262144
MAX_FRAGMENTS = 128
ASSEMBLY_SECONDS = 30
DEVICE_HEADER = DEVICE_TRANSFER_HEADER


class TransportError(ValueError):
    def __init__(self, status, reason):
        self.status=status;self.reason=reason
        super().__init__(reason)


class ResilientTransport:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.clear()

    def clear(self):
        self.setup=None
        self.buffer_bytes=0
        self.clear_fragments()

    def clear_fragments(self):
        self._data=bytearray();self.total_bytes=0;self.fragments=0;self.complete=False;self.deadline=0
        self.templates=TemplateStaging();self.template_error=None
        self.diagnostics=DiagnosticStaging();self.diagnostic_error=None
        self.objects=ObjectStaging();self.object_error=None
        self.source_type_verification=verification();self.type_error=None;self._type_catalog=None
        self._type_binding_stamp=None
        self.source_object_verification=object_verification.summary();self.source_object_error=None
        self._object_catalogs=(None,None,None,None);self._object_binding_stamp=None
        self.download_image=DownloadImage();self.image_error=None
        self.image_preparation_started=False;self._image_start_binding=None
        self.execution_status_reported=False
        self.inspection={'status':'idle','expanded_bytes':0,'record_count':0,'scoped_records':0,
                         'operations':[],'execution_supported':False,'records_executed':0,
                         'payloads_exposed':False,'signature_verified':False}
        self.incremental_inspection={**self.inspection,'operations':[]}
        self._incremental_batch=();self.incremental=IncrementalDownload();self.incremental_error=None
        self.incremental_started=False;self.incremental_status_reported=False;self._incremental_start_binding=None
        self.routine_batch=None;self.routine_error=None;self.routine_started=False;self.routine_status_reported=False
        self._routine_start_binding=None

    def start_routine_payload(self,bindings):
        self.inspect_incremental_payload()
        if self.routine_error:raise ImageError(self.routine_error)
        try:
            if self.routine_batch is None:self.routine_batch=RoutineBatch.prepare(self._incremental_batch,bindings)
            stage=self.routine_batch;stage.verify_effects(bindings)
            if (stage.records!=self.incremental_inspection['record_count'] or not stage.records
                    or stage.record_sha256!=record_digest(self._incremental_batch)):
                raise ImageError('download_routine_record_binding_changed')
            binding=(bindings.stamp(),stage.records,stage.record_sha256)
            if self.routine_started and self._routine_start_binding!=binding:
                raise ImageError('download_routine_start_binding_changed')
        except ImageError as error:
            self.routine_error=error.reason;self.routine_batch=None;raise
        self._routine_start_binding=binding;self.routine_started=True
        return {**stage.description(),'preparation_started':True,'effects_verified':stage.records}

    def routine_execution_status(self,bindings):
        self.expire()
        if not self.routine_started:raise TransportError(0x0C,'download_routine_preparation_required')
        state=self.start_routine_payload(bindings)
        expected=struct.unpack_from('<I',self.setup,12)[0]
        if self.incremental_inspection['expanded_bytes']!=expected or not expected:
            raise TransportError(0x0C,'download_routine_byte_coverage_changed')
        payload=ExecutionStatus(0,expected).encode(expected);self.routine_status_reported=True
        return payload,state

    def inspect_incremental_payload(self):
        """Inspect a later batch without treating it as a complete source image.

        The owning prepared lease checks its retained namespace before calling
        this method. Decoding never applies records or supplies execution status.
        Keep this cache separate from the first batch's source-verifying path.
        """
        self.expire()
        if not self.complete:raise TransportError(0x0C,'transport_complete_payload_required')
        if self.incremental_inspection['status']=='invalid':
            raise TransportError(3,self.incremental_inspection['reason'])
        if self.incremental_inspection['status']=='decoded':return self.incremental_inspection
        expected=struct.unpack_from('<I',self.setup,12)[0]
        try:
            batch=device_payload.decode(bytes(self._data),expected)
            self.incremental_inspection=device_payload.summary(batch,expected)
            self._incremental_batch=batch
        except device_payload.PayloadError as error:
            self.incremental_inspection={**self.incremental_inspection,'status':'invalid','reason':error.reason}
            raise TransportError(3,error.reason) from error
        return self.incremental_inspection

    def prepare_incremental_payload(self,image,source,native_metadata_values=None,header_bindings=None):
        self.inspect_incremental_payload()
        if self.incremental_error:raise ImageError(self.incremental_error)
        try:
            if self.incremental._image is None:
                self.incremental=IncrementalDownload.prepare(self._incremental_batch,image,source,native_metadata_values,header_bindings)
            else:self.incremental.validate(image,source,native_metadata_values,header_bindings)
        except ImageError as error:
            self.incremental_error=error.reason;self.incremental=IncrementalDownload();raise
        return self.incremental.description()

    def start_incremental_payload(self,image,source,native_metadata_values=None,header_bindings=None):
        self.prepare_incremental_payload(image,source,native_metadata_values,header_bindings)
        stage=self.incremental
        if stage.description()['unsupported_records']:
            raise TransportError(0x0F,'incremental_download_processing_unimplemented')
        if (stage.records!=self.incremental_inspection['record_count'] or not stage.records
                or stage.record_sha256!=record_digest(self._incremental_batch)):
            raise TransportError(0x0C,'incremental_record_binding_changed')
        stage.verify_effects(image,source,native_metadata_values,header_bindings)
        binding=(source,stage.records,stage.record_sha256)
        if self.incremental_started and self._incremental_start_binding!=binding:
            raise TransportError(0x0C,'incremental_start_binding_changed')
        self._incremental_start_binding=binding;self.incremental_started=True
        return {**stage.description(),'preparation_started':True,'effects_verified':stage.records}

    def incremental_execution_status(self,image,source,native_metadata_values=None,header_bindings=None):
        self.expire()
        if not self.incremental_started:raise TransportError(0x0C,'incremental_preparation_required')
        state=self.start_incremental_payload(image,source,native_metadata_values,header_bindings)
        expected=struct.unpack_from('<I',self.setup,12)[0]
        if self.incremental_inspection['expanded_bytes']!=expected or not expected:
            raise TransportError(0x0C,'incremental_byte_coverage_changed')
        payload=ExecutionStatus(0,expected).encode(expected)
        self.incremental_status_reported=True
        return payload,state

    def inspect_payload(self, native_types=None, *, native_symbols=None,native_routines=None,native_auxiliary_symbols=None,native_tables=None):
        self.expire()
        if not self.complete:raise TransportError(0x0C,'transport_complete_payload_required')
        if self.inspection['status']=='invalid':raise TransportError(3,self.inspection['reason'])
        if self.template_error:raise TransportError(3,self.template_error)
        if self.diagnostic_error:raise TransportError(3,self.diagnostic_error)
        if self.object_error:raise TransportError(3,self.object_error)
        if self.type_error:raise TransportError(3,self.type_error)
        if self.source_object_error:raise TransportError(3,self.source_object_error)
        if self.image_error:raise TransportError(3,self.image_error)
        if self.inspection['status']=='decoded':self.require_type_binding(native_types)
        if self.inspection['status']=='decoded':self.require_object_bindings(native_symbols,native_routines,native_auxiliary_symbols,native_tables)
        if self.inspection['status']=='decoded':return self.inspection
        expected=struct.unpack_from('<I',self.setup,12)[0]
        try:
            batch=device_payload.decode(bytes(self._data),expected)
            self.inspection=device_payload.summary(batch,expected)
        except device_payload.PayloadError as error:
            self.inspection={**self.inspection,'status':'invalid','reason':error.reason}
            raise TransportError(3,error.reason) from error
        try:
            templates=TemplateStaging.from_batch(batch)
            diagnostics=DiagnosticStaging.from_batch(batch)
            objects=ObjectStaging.from_batch(batch,templates.templates)
        except TemplateError as error:
            self.template_error=error.reason
            raise TransportError(3,error.reason) from error
        except DiagnosticError as error:
            self.diagnostic_error=error.reason
            raise TransportError(3,error.reason) from error
        except ObjectError as error:
            self.object_error=error.reason
            raise TransportError(3,error.reason) from error
        self._type_catalog=native_types
        self._type_binding_stamp=native_types.binding_stamp() if native_types is not None else None
        self.source_type_verification=(native_types.verify(templates.templates) if native_types is not None else
                                       verification('unavailable' if templates.templates else 'idle',unresolved=len(templates.templates)))
        if self.source_type_verification['status']=='mismatch':
            self.type_error='source_type_verification_failed'
            raise TransportError(3,self.type_error)
        self.require_type_binding(native_types)
        source=Source(native_types.source_acd_sha256,native_types.source_l5x_sha256) if native_types is not None else None
        self.source_object_verification=object_verification.verify(objects,source,native_symbols,native_routines,native_auxiliary_symbols,native_tables)
        if self.source_object_verification['status']=='mismatch':
            self.source_object_error='source_object_verification_failed'
            raise TransportError(3,self.source_object_error)
        self._object_catalogs=(native_symbols,native_routines,native_auxiliary_symbols,native_tables)
        self._object_binding_stamp=object_verification.binding_stamp(*self._object_catalogs)
        try:
            image=DownloadImage.prepare(batch,templates,diagnostics,objects,native_types,
                                        self.source_type_verification)
        except ImageError as error:
            self.image_error=error.reason
            raise TransportError(3,error.reason) from error
        self.require_type_binding(native_types)
        self.templates=templates;self.diagnostics=diagnostics;self.objects=objects
        self.download_image=image
        return self.inspection

    def require_type_binding(self,native_types):
        try:stamp=native_types.binding_stamp() if native_types is not None else None
        except (ValueError,TypeError,KeyError,AttributeError):raise TransportError(0x0C,'native_type_binding_changed') from None
        if native_types is not self._type_catalog or stamp!=self._type_binding_stamp:
            raise TransportError(0x0C,'native_type_binding_changed')

    def require_object_bindings(self,symbols,routines,auxiliary=None,tables=None):
        try:stamp=object_verification.binding_stamp(symbols,routines,auxiliary,tables)
        except (ValueError,TypeError,KeyError):raise TransportError(0x0C,'native_object_binding_changed') from None
        if stamp!=self._object_binding_stamp:raise TransportError(0x0C,'native_object_binding_changed')

    def start_prepared_image(self):
        """Start this simulator's isolated image preparation exactly once.

        This records a completed temporary namespace transition, not firmware
        execution or active-project commit. The caller checks the current lease
        and calls inspect_payload(current_native_types) before invoking it.
        """
        self.expire()
        if not self.complete:raise TransportError(0x0C,'transport_complete_payload_required')
        if self.inspection['status']!='decoded':raise TransportError(0x0C,'device_image_inspection_required')
        if self.source_object_error:raise TransportError(3,self.source_object_error)
        if self.image_error:raise TransportError(3,self.image_error)
        self.require_object_bindings(*self._object_catalogs)
        image=self.download_image
        if image.description()['status']!='prepared' or self._type_catalog is None:
            raise TransportError(0x0F,'source_bound_device_image_required')
        if not image.records or image.records!=self.inspection['record_count'] or not image.record_sha256:
            raise TransportError(0x0C,'device_image_record_coverage_mismatch')
        try:
            source=Source(self._type_catalog.source_acd_sha256,self._type_catalog.source_l5x_sha256)
            image.require_source(source)
        except ImageError as error:
            raise TransportError(0x0C,error.reason) from error
        self.require_type_binding(self._type_catalog)
        binding=(source,image.record_sha256,image.records,id(self._type_catalog))
        if self.image_preparation_started and self._image_start_binding!=binding:
            raise TransportError(0x0C,'device_image_preparation_binding_changed')
        if (image._results.record_sha256!=image.record_sha256 or len(image._results.results)!=image.records
                or image._results.source_acd_sha256!=source.acd_sha256
                or image._results.source_l5x_sha256!=source.l5x_sha256):
            raise TransportError(0x0C,'device_image_result_binding_mismatch')
        self._image_start_binding=binding;self.image_preparation_started=True
        return {**image.description(),'preparation_started':True}

    def prepared_result_state(self,native_types,*,native_symbols=None,native_routines=None,native_auxiliary_symbols=None,native_tables=None):
        """Recheck an already started image for result-query diagnostics only.

        This does not encode native results or start an unstarted image. The
        current catalog, result ledger and source/digest binding must still
        match the preparation that the owning client started.
        """
        self.expire()
        if not self.image_preparation_started:
            raise TransportError(0x0C,'device_image_preparation_required')
        if native_types is None or native_types is not self._type_catalog:
            raise TransportError(0x0C,'device_image_result_catalog_changed')
        self.require_object_bindings(native_symbols,native_routines,native_auxiliary_symbols,native_tables)
        return self.start_prepared_image()

    def execution_status(self,native_types,**catalogs):
        """Report completed temporary processing only after actual effect readback."""
        state=self.prepared_result_state(native_types,**catalogs)
        expected=struct.unpack_from('<I',self.setup,12)[0]
        if self.inspection['expanded_bytes']!=expected or not expected:
            raise TransportError(0x0C,'device_image_result_byte_coverage_mismatch')
        image=self.download_image
        try:
            source=Source(native_types.source_acd_sha256,native_types.source_l5x_sha256)
            for ordinal in range(image.records):
                if not image.read_preparation_effect(ordinal,source).matches:
                    raise TransportError(0x0C,'device_image_result_effect_changed')
            payload=ExecutionStatus(0,expected).encode(expected)
        except (ImageError,ResultError) as error:
            raise TransportError(0x0C,error.reason) from error
        self.execution_status_reported=True
        return payload,state

    def expire(self):
        if self.fragments and self.clock()>=self.deadline:self.clear_fragments()

    def accept(self,envelope):
        """Stage contiguous bytes only; malformed chains discard their buffer."""
        self.expire()
        try:
            if self.setup is None:raise TransportError(0x0C,'transport_setup_required')
            if isinstance(envelope,CompactTransferEnvelope):
                try:validate_compact_transfer(envelope)
                except EnvelopeError as error:raise TransportError(3,'invalid_compact_transport') from error
                if self.fragments:raise TransportError(0x0C,'transport_assembly_conflict')
                data=envelope.fragment[len(DEVICE_HEADER):]
                if len(data)>self.buffer_bytes:raise TransportError(3,'transport_fragment_size')
                self._data.extend(data);self.total_bytes=len(data);self.fragments=1;self.complete=True
                self.deadline=self.clock()+ASSEMBLY_SECONDS
                return
            if (not isinstance(envelope,FragmentEnvelope) or envelope.service!=0x39 or type(envelope.container_format) is not int
                    or envelope.container_format not in FRAGMENT_FORMATS or type(envelope.position) is not int
                    or not 0<=envelope.position<=0xFFFFFFFF or not isinstance(envelope.fragment,bytes)
                    or not 1<=len(envelope.fragment)<=MAX_MESSAGE-38):
                raise TransportError(3,'invalid_transport_fragment')
            data=envelope.fragment;first=envelope.container_format==0x101;last=envelope.container_format==0x201
            if first:
                if self.fragments:raise TransportError(0x0C,'transport_assembly_conflict')
                if not data.startswith(DEVICE_HEADER):raise TransportError(0x0F,'unsupported_device_transfer')
                data=data[len(DEVICE_HEADER):];total=envelope.position
                if not 0<len(data)<total<=self.buffer_bytes:
                    raise TransportError(3,'transport_fragment_size')
                self.total_bytes=total;self.deadline=self.clock()+ASSEMBLY_SECONDS
            else:
                if not self.fragments or self.complete:raise TransportError(0x0C,'transport_assembly_required')
                if envelope.position!=len(self._data):raise TransportError(3,'transport_fragment_offset')
            size=len(self._data)+len(data)
            if size>self.total_bytes or (size==self.total_bytes)!=last:
                raise TransportError(3,'transport_fragment_size')
            if self.fragments>=MAX_FRAGMENTS:raise TransportError(2,'transport_fragment_limit')
            self._data.extend(data);self.fragments+=1;self.complete=last
        except TransportError:
            self.clear_fragments();raise

    def open(self, payload):
        if not isinstance(payload,bytes) or len(payload)!=16:
            raise TransportError(3,'invalid_transport_setup')
        first,second,selector,buffer_bytes,_opaque=struct.unpack('<HHIII',payload)
        if (first,second,selector)!=(1,1,1):
            raise TransportError(3,'unsupported_transport_setup')
        if not 1<=buffer_bytes<=MAX_BUFFER_BYTES:
            raise TransportError(3,'transport_buffer_limit')
        if self.setup is not None and self.setup!=payload:
            raise TransportError(0x0C,'transport_setup_conflict')
        self.setup=payload;self.buffer_bytes=buffer_bytes

    def description(self):
        self.expire()
        return {'open':self.setup is not None,'setup_only':False,
                'buffer_bytes':self.buffer_bytes,'max_buffer_bytes':MAX_BUFFER_BYTES,
                'buffer_allocated':bool(self._data),'fragment_staging':True,
                'received_bytes':len(self._data),'total_bytes':self.total_bytes,'fragments':self.fragments,
                'complete':self.complete,'max_fragments':MAX_FRAGMENTS,'assembly_timeout_seconds':ASSEMBLY_SECONDS,
                'payload_transfer':False,'commit':False,
                'inspection':{**self.inspection,'operations':[dict(row) for row in self.inspection['operations']]},
                'incremental_inspection':{**self.incremental_inspection,
                    'operations':[dict(row) for row in self.incremental_inspection['operations']]},
                'incremental_staging':{**self.incremental.description(),
                    'preparation_started':self.incremental_started,'status_reported':self.incremental_status_reported,
                    **({'status':'invalid','reason':self.incremental_error} if self.incremental_error else {})},
                'routine_staging':{**(self.routine_batch.description() if self.routine_batch is not None else {}),
                    'preparation_started':self.routine_started,'status_reported':self.routine_status_reported,
                    **({'status':'invalid','reason':self.routine_error} if self.routine_error else {})},
                'source_type_verification':{**self.source_type_verification,
                    'errors':[dict(e) for e in self.source_type_verification['errors']]},
                'source_object_verification':{**self.source_object_verification,
                    'errors':list(self.source_object_verification['errors'])},
                'download_image':{**self.download_image.description(),'preparation_started':self.image_preparation_started,
                    **({'status':'invalid','reason':self.image_error} if self.image_error else {})},
                'template_staging':{**self.templates.description(),**({'status':'invalid','reason':self.template_error} if self.template_error else {})},
                'diagnostic_staging':{**self.diagnostics.description(),**({'status':'invalid','reason':self.diagnostic_error} if self.diagnostic_error else {})},
                'object_staging':{**self.objects.description(),**({'status':'invalid','reason':self.object_error} if self.object_error else {})},
                'configuration_exposed':False}
