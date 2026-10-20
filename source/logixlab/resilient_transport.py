"""Lease-local setup for the observed Resilient Transport Object dialect.

The last setup word and reassembled payload are opaque. Fragments stay in a
bounded temporary buffer. No device payload is installed or project changed.
"""
import struct
import time
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
                'configuration_exposed':False}
