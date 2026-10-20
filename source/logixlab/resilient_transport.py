"""Lease-local setup for the observed Resilient Transport Object dialect.

The last setup word is opaque. No buffer is allocated, device payload accepted
or active project changed. Segmented transport remains unsupported.
"""
import struct

MAX_BUFFER_BYTES = 262144


class TransportError(ValueError):
    def __init__(self, status, reason):
        self.status=status;self.reason=reason
        super().__init__(reason)


class ResilientTransport:
    def __init__(self):self.clear()

    def clear(self):
        self.setup=None
        self.buffer_bytes=0

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
        return {'open':self.setup is not None,'setup_only':True,
                'buffer_bytes':self.buffer_bytes,'max_buffer_bytes':MAX_BUFFER_BYTES,
                'buffer_allocated':False,'payload_transfer':False,'commit':False,
                'configuration_exposed':False}
