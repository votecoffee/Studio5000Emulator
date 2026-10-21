"""Observed signed Message Router 0x3A reads and bounded detached assembly.

Replies contain stream chunks, not embedded CIP replies. No operation is
dispatched, no controller is contacted, and assembled bytes never execute.
"""
from dataclasses import dataclass
import hmac
import struct
from . import signed_messages as sm

MAX_STREAM_BYTES=8*1024*1024
MAX_FRAMES=4096
Error=sm.EnvelopeError


@dataclass(frozen=True)
class ReadRequest:
    sequence: int
    container_format: int
    position: int
    inner: bytes = b''
    service: int = 0x3A


@dataclass(frozen=True)
class ReadChunk:
    sequence: int
    container_format: int
    position: int
    data: bytes
    service: int = 0x3A


def _request(request):
    if (not isinstance(request,ReadRequest) or type(request.service) is not int or request.service!=0x3A or
            type(request.sequence) is not int or not 0<=request.sequence<=0xffffffff or
            type(request.container_format) is not int or type(request.position) is not int or
            not isinstance(request.inner,bytes)):
        raise Error('Invalid read request context')
    if request.container_format==0x101:
        if request.position!=0:raise Error('Initial read position must be zero')
        sm._check_inner_request(request.inner)
    elif request.container_format==1:
        if request.inner or not 1<=request.position<=MAX_STREAM_BYTES:raise Error('Invalid read continuation')
    else:raise Error('Unsupported read request format')
    if 38+len(request.inner)>sm.MAX_MESSAGE:raise Error('Read request exceeds message limit')


def parse_request(raw):
    sm._bounded(raw)
    if raw[:6]!=b'\x3a\2'+sm.ROUTER_PATH or len(raw)<38:raise Error('Invalid read wrapper or header')
    fmt,position=struct.unpack_from('<II',raw,6)
    result=ReadRequest(struct.unpack_from('<I',raw,len(raw)-24)[0],fmt,position,raw[14:-24])
    _request(result)
    return result


def parse_response(raw,request):
    _request(request);sm._bounded(raw)
    if raw[:4]!=b'\xba\0\0\0' or len(raw)<36:raise Error('Invalid successful read response header')
    fmt,position=struct.unpack_from('<II',raw,4);data=raw[12:-24]
    sequence=struct.unpack_from('<I',raw,len(raw)-24)[0]
    if sequence!=request.sequence:raise Error('Read response counter mismatch')
    if request.container_format==0x101:
        if fmt==0x301:
            if position!=len(data):raise Error('Complete read byte count mismatch')
        elif fmt==0x101:
            if not 0<len(data)<position<=MAX_STREAM_BYTES:raise Error('Invalid initial read size')
        else:raise Error('Unsupported initial read response format')
    elif fmt not in (1,0x201) or position!=request.position or not data:
        raise Error('Invalid continuation read response')
    if len(data)>MAX_STREAM_BYTES:raise Error('Read chunk exceeds stream limit')
    return ReadChunk(sequence,fmt,position,data)


def verify_request(raw,key,*,expected_sequence=None):
    sm._check_key(key);request=parse_request(raw)
    if expected_sequence is not None and (type(expected_sequence) is not int or not 0<=expected_sequence<=0xffffffff):
        raise Error('Expected read counter must be a UDINT')
    if not hmac.compare_digest(hmac.digest(key,raw[:-20],'sha1'),raw[-20:]):raise Error('Read request MAC rejected')
    if expected_sequence is not None and request.sequence!=expected_sequence:raise Error('Read request counter rejected')
    return request


def verify_response(raw,key,*,request):
    sm._check_key(key);response=parse_response(raw,request)
    if not hmac.compare_digest(hmac.digest(key,raw[:-20],'sha1'),raw[-20:]):raise Error('Read response MAC rejected')
    return response


def encode_request(request,key):
    _request(request);sm._check_key(key)
    raw=b'\x3a\2'+sm.ROUTER_PATH+struct.pack('<II',request.container_format,request.position)+request.inner+struct.pack('<I',request.sequence)
    return raw+hmac.digest(key,raw,'sha1')


def encode_response(request,data,key,*,total_bytes=None,final=True):
    _request(request);sm._check_key(key)
    if not isinstance(data,bytes) or type(final) is not bool:raise Error('Invalid read response data')
    if request.container_format==0x101:
        if type(total_bytes) is not int or not 0<=total_bytes<=MAX_STREAM_BYTES:raise Error('Initial read requires a bounded total size')
        fmt=0x301 if final else 0x101;position=total_bytes
    else:
        if total_bytes is not None:raise Error('Continuation read has no new total size')
        fmt=0x201 if final else 1;position=request.position
    raw=b'\xba\0\0\0'+struct.pack('<II',fmt,position)+data+struct.pack('<I',request.sequence)
    parse_response(raw+bytes(20),request)
    return raw+hmac.digest(key,raw,'sha1')


class Assembly:
    """One ordered stream in caller-owned session context; keys stay outside."""
    def __init__(self,*,max_bytes=MAX_STREAM_BYTES,max_frames=MAX_FRAMES):
        if (type(max_bytes) is not int or not 1<=max_bytes<=MAX_STREAM_BYTES or
                type(max_frames) is not int or not 1<=max_frames<=MAX_FRAMES):raise Error('Invalid read assembly bounds')
        self.max_bytes=max_bytes;self.max_frames=max_frames
        self.clear()

    def clear(self):
        self.inner=None;self.total_bytes=None;self._data=bytearray();self.frames=0;self.sequence=None;self.complete=False

    def accept(self,request,response):
        _request(request)
        if (not isinstance(response,ReadChunk) or type(response.service) is not int or response.service!=0x3A or
                type(response.sequence) is not int or response.sequence!=request.sequence or
                type(response.container_format) is not int or type(response.position) is not int or
                not 0<=response.container_format<=0xffffffff or not 0<=response.position<=0xffffffff or
                not isinstance(response.data,bytes)):raise Error('Invalid read chunk context')
        # Use the same structural validation for parsed and caller-built frames.
        raw=b'\xba\0\0\0'+struct.pack('<II',response.container_format,response.position)+response.data+struct.pack('<I',response.sequence)+bytes(20)
        parse_response(raw,request)
        if self.complete:raise Error('Read assembly already complete')
        if self.frames>=self.max_frames:raise Error('Read frame count limit')
        if self.sequence is not None and request.sequence<=self.sequence:raise Error('Read sequence is stale or reversed')
        if request.container_format==0x101:
            if self.inner is not None:raise Error('A read stream is already pending')
            total=response.position
            if total>self.max_bytes:raise Error('Read stream exceeds assembly limit')
        else:
            if self.inner is None or request.position!=len(self._data):raise Error('Read continuation gap, overlap or missing start')
            total=self.total_bytes
        length=len(self._data)+len(response.data)
        final=response.container_format in (0x301,0x201)
        if length>total or final and length!=total or not final and length>=total:
            raise Error('Read chunk conflicts with declared total or completion')
        if request.container_format==0x101:self.inner=request.inner;self.total_bytes=total
        self._data.extend(response.data);self.frames+=1;self.sequence=request.sequence;self.complete=final
        return self.complete

    def value(self):
        if not self.complete:raise Error('Read stream is incomplete')
        return bytes(self._data)

    def routine_source(self):
        """Inspect a complete scoped source read using its separate upload profile."""
        from .upload_routine_source import decode_assembly
        return decode_assembly(self)
