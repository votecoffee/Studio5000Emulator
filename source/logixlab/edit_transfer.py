"""Temporary compiled Routine fragments, separate from download preparation.

This receives paired ELF and compressed-source containers. It never installs a routine,
resolves relocations, executes native instructions or accepts controller edits.
Validated source storage may be acknowledged; active installation is separate.
"""
import hashlib
import struct
import time
from .signed_messages import FragmentEnvelope,FRAGMENT_FORMATS,MAX_MESSAGE
from . import routine_source

MAX_BYTES=262144
MAX_FRAGMENTS=128
MAX_METADATA_RECORDS=1024
ASSEMBLY_SECONDS=30


class EditTransferError(ValueError):
    def __init__(self,status,reason):self.status=status;self.reason=reason;super().__init__(reason)


class EditTransfer:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.clear()

    def clear(self):
        self.target=None;self._data=bytearray();self.total_bytes=0
        self.fragments=0;self.complete=False;self.deadline=0
        self.kind=None;self._code=None;self.source=None
        self.translated_rungs=None;self.reference_error=None
        self.plan_validated=False;self.plan_error=None
        self._attachment=None
        self._metadata={}
        self.program_released=False;self.base_revision=None

    def expire(self):
        if self.fragments and self.clock()>=self.deadline:self.clear()

    def accept(self,envelope,*,target,prefix=None,kind='code'):
        """Retain contiguous bytes for the caller's validated source-bound target.

        The first prefix is its numeric CIP path and four setup DWORDs, already
        checked by the router. Its announced size and subsequent offsets cover
        only the remaining container bytes, as in the observed fragment dialect.
        Malformed chains discard this temporary buffer.
        """
        self.expire()
        try:
            if (not isinstance(envelope,FragmentEnvelope) or envelope.service!=0x39
                    or type(envelope.container_format) is not int or envelope.container_format not in FRAGMENT_FORMATS
                    or type(envelope.position) is not int or not 0<=envelope.position<=0xFFFFFFFF
                    or not isinstance(envelope.fragment,bytes) or not 1<=len(envelope.fragment)<=MAX_MESSAGE-38
                    or not isinstance(target,tuple) or len(target)!=2
                    or any(type(value) is not int or not 1<=value<=0xFFFFFFFF for value in target)
                    or kind not in ('code','source')):
                raise EditTransferError(3,'invalid_edit_fragment')
            data=envelope.fragment;first=envelope.container_format==0x101;last=envelope.container_format==0x201
            if first:
                if self.fragments:
                    if not (self.complete and self.kind=='code' and kind=='source' and self.target==target):
                        raise EditTransferError(0x0C,'edit_assembly_conflict')
                    self._code=bytes(self._data);self._data=bytearray();self.complete=False
                elif kind=='source':raise EditTransferError(0x0C,'edit_code_container_required')
                if (not isinstance(prefix,bytes) or not 18<=len(prefix)<=192 or not data.startswith(prefix)):
                    raise EditTransferError(3,'invalid_edit_prefix')
                data=data[len(prefix):];total=envelope.position
                if not (72 if kind=='code' else 64)<=total<=MAX_BYTES-len(self._code or b'') or not 24<=len(data)<total:
                    raise EditTransferError(3,'edit_fragment_size')
                # Bound the known container before allocating. Header flags
                # remain opaque, and ELF magic alone is no validity proof.
                if kind=='source':routine_source.source_header(data,total)
                elif (struct.unpack_from('<III',data)!=(9,0,0)
                        or struct.unpack_from('<I',data,16)[0]!=total-20 or data[20:24]!=b'\x7fELF'):
                    raise EditTransferError(0x0F,'unsupported_edit_container')
                self.target=target;self.total_bytes=total;self.kind=kind
                if not self.fragments:self.deadline=self.clock()+ASSEMBLY_SECONDS
            else:
                if prefix is not None:raise EditTransferError(3,'unexpected_edit_prefix')
                if not self.fragments or self.complete:raise EditTransferError(0x0C,'edit_assembly_required')
                if target!=self.target:raise EditTransferError(0x0C,'edit_target_changed')
                if kind!=self.kind:raise EditTransferError(0x0C,'edit_component_changed')
                if envelope.position!=len(self._data):raise EditTransferError(3,'edit_fragment_offset')
            size=len(self._data)+len(data)
            if size>self.total_bytes or (size==self.total_bytes)!=last:
                raise EditTransferError(3,'edit_fragment_size')
            if self.fragments>=MAX_FRAGMENTS:raise EditTransferError(2,'edit_fragment_limit')
            self._data.extend(data);self.fragments+=1;self.complete=last
            if self.complete and self.kind=='source':self.source=routine_source.decode(bytes(self._data))
        except routine_source.SourceError as error:
            self.clear();raise EditTransferError(3,str(error)) from error
        except EditTransferError:
            self.clear();raise

    def attach(self,data,*,target):
        """Retain the observed post-source record; its final word is opaque.

        Receipt establishes temporary storage only. It does not assign native
        identifiers, interpret metadata or accept/activate controller edits.
        """
        self.expire()
        if (not self.complete or self.kind!='source' or self.source is None
                or self.translated_rungs is None or not self.plan_validated):
            raise EditTransferError(0x0C,'validated_edit_source_required')
        if (not isinstance(target,tuple) or len(target)!=2 or any(type(value) is not int for value in target)
                or target!=self.target):raise EditTransferError(0x0C,'edit_target_changed')
        if (not isinstance(data,bytes) or len(data)!=20 or data[:16]!=struct.pack('<4I',2,5,0,1)
                or data[16:]==bytes(4)):
            raise EditTransferError(3,'unsupported_edit_post_source_record')
        if len(self._data)+len(self._code or b'')+len(data)>MAX_BYTES:
            raise EditTransferError(2,'edit_storage_limit')
        if self._attachment is not None and self._attachment!=data:
            raise EditTransferError(0x0C,'edit_post_source_record_conflict')
        self._attachment=data

    def ready(self):
        self.expire()
        return (self.complete and self.kind=='source' and self.source is not None
                and self.translated_rungs is not None and self.plan_validated and self._attachment is not None
                and type(self.base_revision) is int and self.base_revision>=0)

    def source_bytes(self):
        if not self.ready():raise EditTransferError(0x0C,'validated_edit_source_required')
        return bytes(self._data)

    def retain_metadata(self,data):
        """Retain the observed removed-rung metadata profile, without applying it.

        The region identifier and marker 4 remain opaque. Scope must match the
        complete validated candidate; a region still present in its new source
        cannot use this profile. No active metadata property is written.
        """
        if not self.ready() or self.program_released:
            raise EditTransferError(0x0C,'validated_edit_source_required')
        if not isinstance(data,bytes) or len(data)!=38:
            raise EditTransferError(3,'unsupported_edit_metadata_profile')
        version,size,pclass,program,rclass,routine,region,selector,marker,a,b,c,kind=struct.unpack('<IIHHHHIHHIIIH',data)
        if (version!=0x301 or size!=30 or (pclass,rclass)!=(0x68,0x6D) or not region
                or selector or marker!=0x7F or a or b or c or kind!=4):
            raise EditTransferError(3,'unsupported_edit_metadata_profile')
        if (program,routine)!=self.target:raise EditTransferError(0x0C,'edit_target_changed')
        if any(row.region_id==region for row in self.source.rungs):
            raise EditTransferError(0x0C,'edit_metadata_region_still_present')
        if region in self._metadata:return
        if len(self._metadata)>=MAX_METADATA_RECORDS:raise EditTransferError(2,'edit_metadata_limit')
        if len(self._data)+len(self._code or b'')+len(self._attachment or b'')+38*(len(self._metadata)+1)>MAX_BYTES:
            raise EditTransferError(2,'edit_storage_limit')
        self._metadata[region]=data

    def description(self):
        self.expire()
        return {'status':'complete' if self.complete else 'receiving' if self.fragments else 'idle',
                'source_bound':bool(self.fragments),'buffer_allocated':bool(self._data),
                'received_bytes':len(self._data),'total_bytes':self.total_bytes,'fragments':self.fragments,
                'complete':self.complete,'max_bytes':MAX_BYTES,'max_fragments':MAX_FRAGMENTS,
                'assembly_timeout_seconds':ASSEMBLY_SECONDS,
                'container_sha256':hashlib.sha256(self._data).hexdigest() if self.complete else None,
                'container_length_verified':bool(self.fragments),'elf_structural_validation':False,
                'component_kind':self.kind,'retained_bytes':len(self._data)+len(self._code or b'')+len(self._attachment or b'')+38*len(self._metadata),
                'routine_metadata':{'records':len(self._metadata),'bytes':38*len(self._metadata),'max_records':MAX_METADATA_RECORDS,
                    'sha256':hashlib.sha256(b''.join(self._metadata[key] for key in sorted(self._metadata))).hexdigest() if self._metadata else None,
                    'active_metadata_written':False,'region_semantics_verified':False,'payload_exposed':False},
                'program_released':self.program_released,'base_logic_revision':self.base_revision,
                'post_source_record':{'staged':self._attachment is not None,'bytes':len(self._attachment or b''),
                    'sha256':hashlib.sha256(self._attachment).hexdigest() if self._attachment is not None else None,
                    'interpreted':False,'payload_exposed':False},
                'code_bytes':len(self._code or (self._data if self.kind=='code' and self.complete else b'')),
                'code_sha256':hashlib.sha256(self._code or self._data).hexdigest() if self._code or self.kind=='code' and self.complete else None,
                'source_description':({**self.source.description(),
                    'operand_bindings_verified':self.translated_rungs is not None,
                    'neutral_text_available':self.translated_rungs is not None,
                    'neutral_text_sha256':hashlib.sha256('\n'.join(self.translated_rungs).encode()).hexdigest() if self.translated_rungs is not None else None,
                    'reference_error':self.reference_error,'execution_plan_validated':self.plan_validated,
                    'plan_error':self.plan_error} if self.source else None),
                'relocations_resolved':False,'instructions_executed':0,'payloads_exposed':False,
                'routine_installed':False,'accepted_edits':False,'commit':False}
