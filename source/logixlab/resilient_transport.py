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
from .native_types import verification
from .signed_messages import FragmentEnvelope,FRAGMENT_FORMATS,MAX_MESSAGE

MAX_BUFFER_BYTES = 262144
MAX_FRAGMENTS = 128
ASSEMBLY_SECONDS = 30
DEVICE_HEADER = bytes.fromhex('5c032100120424000100000014000000')


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
        self.download_image=DownloadImage();self.image_error=None
        self.image_preparation_started=False;self._image_start_binding=None
        self.inspection={'status':'idle','expanded_bytes':0,'record_count':0,'scoped_records':0,
                         'operations':[],'execution_supported':False,'records_executed':0,
                         'payloads_exposed':False,'signature_verified':False}

    def inspect_payload(self, native_types=None):
        self.expire()
        if not self.complete:raise TransportError(0x0C,'transport_complete_payload_required')
        if self.inspection['status']=='invalid':raise TransportError(3,self.inspection['reason'])
        if self.template_error:raise TransportError(3,self.template_error)
        if self.diagnostic_error:raise TransportError(3,self.diagnostic_error)
        if self.object_error:raise TransportError(3,self.object_error)
        if self.type_error:raise TransportError(3,self.type_error)
        if self.image_error:raise TransportError(3,self.image_error)
        if self.inspection['status']=='decoded' and self._type_catalog is not native_types:
            raise TransportError(0x0C,'native_type_binding_changed')
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
        self.source_type_verification=(native_types.verify(templates.templates) if native_types is not None else
                                       verification('unavailable' if templates.templates else 'idle'))
        if self.source_type_verification['status']=='mismatch':
            self.type_error='source_type_verification_failed'
            raise TransportError(3,self.type_error)
        try:
            image=DownloadImage.prepare(batch,templates,diagnostics,objects,native_types,
                                        self.source_type_verification)
        except ImageError as error:
            self.image_error=error.reason
            raise TransportError(3,error.reason) from error
        self.templates=templates;self.diagnostics=diagnostics;self.objects=objects
        self.download_image=image
        return self.inspection

    def start_prepared_image(self):
        """Start this simulator's isolated image preparation exactly once.

        This records a completed temporary namespace transition, not firmware
        execution or active-project commit. The caller checks the current lease
        and calls inspect_payload(current_native_types) before invoking it.
        """
        self.expire()
        if not self.complete:raise TransportError(0x0C,'transport_complete_payload_required')
        if self.inspection['status']!='decoded':raise TransportError(0x0C,'device_image_inspection_required')
        if self.image_error:raise TransportError(3,self.image_error)
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
        binding=(source,image.record_sha256,image.records,id(self._type_catalog))
        if self.image_preparation_started and self._image_start_binding!=binding:
            raise TransportError(0x0C,'device_image_preparation_binding_changed')
        if (image._results.record_sha256!=image.record_sha256 or len(image._results.results)!=image.records
                or image._results.source_acd_sha256!=source.acd_sha256
                or image._results.source_l5x_sha256!=source.l5x_sha256):
            raise TransportError(0x0C,'device_image_result_binding_mismatch')
        self._image_start_binding=binding;self.image_preparation_started=True
        return {**image.description(),'preparation_started':True}

    def prepared_result_state(self,native_types):
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
        return self.start_prepared_image()

    def expire(self):
        if self.fragments and self.clock()>=self.deadline:self.clear_fragments()

    def accept(self,envelope):
        """Stage contiguous bytes only; malformed chains discard their buffer."""
        self.expire()
        try:
            if self.setup is None:raise TransportError(0x0C,'transport_setup_required')
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
                'source_type_verification':{**self.source_type_verification,
                    'errors':[dict(e) for e in self.source_type_verification['errors']]},
                'download_image':{**self.download_image.description(),'preparation_started':self.image_preparation_started,
                    **({'status':'invalid','reason':self.image_error} if self.image_error else {})},
                'template_staging':{**self.templates.description(),**({'status':'invalid','reason':self.template_error} if self.template_error else {})},
                'diagnostic_staging':{**self.diagnostics.description(),**({'status':'invalid','reason':self.diagnostic_error} if self.diagnostic_error else {})},
                'object_staging':{**self.objects.description(),**({'status':'invalid','reason':self.object_error} if self.object_error else {})},
                'configuration_exposed':False}
