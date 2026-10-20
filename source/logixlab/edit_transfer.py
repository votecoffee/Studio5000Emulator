"""Temporary compiled Routine fragments, separate from download preparation.

This receives one observed opaque ELF container. It never installs a routine,
resolves relocations, executes native instructions or accepts controller edits.
The endpoint rejects installation after the final fragment has been retained.
"""
import hashlib
import struct
import time
from .signed_messages import FragmentEnvelope,FRAGMENT_FORMATS,MAX_MESSAGE

MAX_BYTES=262144
MAX_FRAGMENTS=128
ASSEMBLY_SECONDS=30


class EditTransferError(ValueError):
    def __init__(self,status,reason):self.status=status;self.reason=reason;super().__init__(reason)


class EditTransfer:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.clear()

    def clear(self):
        self.target=None;self._data=bytearray();self.total_bytes=0
        self.fragments=0;self.complete=False;self.deadline=0

    def expire(self):
        if self.fragments and self.clock()>=self.deadline:self.clear()

    def accept(self,envelope,*,target,prefix=None):
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
                    or any(type(value) is not int or not 1<=value<=0xFFFFFFFF for value in target)):
                raise EditTransferError(3,'invalid_edit_fragment')
            data=envelope.fragment;first=envelope.container_format==0x101;last=envelope.container_format==0x201
            if first:
                if self.fragments:raise EditTransferError(0x0C,'edit_assembly_conflict')
                if (not isinstance(prefix,bytes) or not 18<=len(prefix)<=192 or not data.startswith(prefix)):
                    raise EditTransferError(3,'invalid_edit_prefix')
                data=data[len(prefix):];total=envelope.position
                if not 72<=total<=MAX_BYTES or not 24<=len(data)<total:
                    raise EditTransferError(3,'edit_fragment_size')
                # Bound the known container before allocating. Header flags
                # remain opaque, and ELF magic alone is no validity proof.
                if (struct.unpack_from('<III',data)!=(9,0,0)
                        or struct.unpack_from('<I',data,16)[0]!=total-20 or data[20:24]!=b'\x7fELF'):
                    raise EditTransferError(0x0F,'unsupported_edit_container')
                self.target=target;self.total_bytes=total;self.deadline=self.clock()+ASSEMBLY_SECONDS
            else:
                if prefix is not None:raise EditTransferError(3,'unexpected_edit_prefix')
                if not self.fragments or self.complete:raise EditTransferError(0x0C,'edit_assembly_required')
                if target!=self.target:raise EditTransferError(0x0C,'edit_target_changed')
                if envelope.position!=len(self._data):raise EditTransferError(3,'edit_fragment_offset')
            size=len(self._data)+len(data)
            if size>self.total_bytes or (size==self.total_bytes)!=last:
                raise EditTransferError(3,'edit_fragment_size')
            if self.fragments>=MAX_FRAGMENTS:raise EditTransferError(2,'edit_fragment_limit')
            self._data.extend(data);self.fragments+=1;self.complete=last
        except EditTransferError:
            self.clear();raise

    def description(self):
        self.expire()
        return {'status':'complete' if self.complete else 'receiving' if self.fragments else 'idle',
                'source_bound':bool(self.fragments),'buffer_allocated':bool(self._data),
                'received_bytes':len(self._data),'total_bytes':self.total_bytes,'fragments':self.fragments,
                'complete':self.complete,'max_bytes':MAX_BYTES,'max_fragments':MAX_FRAGMENTS,
                'assembly_timeout_seconds':ASSEMBLY_SECONDS,
                'container_sha256':hashlib.sha256(self._data).hexdigest() if self.complete else None,
                'container_length_verified':bool(self.fragments),'elf_structural_validation':False,
                'relocations_resolved':False,'instructions_executed':0,'payloads_exposed':False,
                'routine_installed':False,'accepted_edits':False,'commit':False}
