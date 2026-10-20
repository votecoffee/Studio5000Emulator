"""Offline codec for observed v35 Message Router 0x36-0x39 envelopes.

Parsing establishes structure only. Verification requires the caller's 20-byte
test/session key and covers the complete CIP message before its MAC.
This module retains no keys, opens no connections and dispatches no operations.
Single, batch and transfer MACs cover the wrapper before its final 20 bytes.
Confirmation and peer authentication remain unimplemented. This codec never
dispatches requests; the optional native endpoint applies a read-only policy.
"""
from dataclasses import dataclass
import hmac
import struct


MAX_MESSAGE = 65519  # 65535-byte SendRRData body minus its 16-byte CPF overhead.
TRAILER_BYTES = 24  # Little-endian UDINT counter followed by a SHA-1 MAC.
ROUTER_PATH = b'\x20\x02\x24\x01'
CONTAINER_FORMAT = 0x301
MAX_BATCH_CHILDREN = 256  # Implementation limit, not an asserted protocol limit.
TRANSFER_CONTROL = 1  # Only the observed single-inner 0x39 container is supported.


class EnvelopeError(ValueError):
    pass


@dataclass(frozen=True)
class Envelope:
    service: int
    sequence: int
    inner: bytes
    container_format: int | None = None


@dataclass(frozen=True)
class TransferEnvelope(Envelope):
    container_control: int = TRANSFER_CONTROL


@dataclass(frozen=True)
class BatchEnvelope:
    service: int
    sequence: int
    children: tuple[bytes, ...]
    status: int | None = None


def _bounded(raw):
    if not isinstance(raw, bytes):
        raise EnvelopeError('Envelope must be immutable bytes')
    if not 4 + TRAILER_BYTES <= len(raw) <= MAX_MESSAGE:
        raise EnvelopeError('Envelope length is outside the supported bounds')


def _inner(data, service):
    if service == 0x36:
        return data, None
    if len(data) < 8:
        raise EnvelopeError('Truncated single-packet container')
    format_word, size = struct.unpack_from('<II', data)
    if format_word != CONTAINER_FORMAT:
        raise EnvelopeError('Unsupported single-packet container format')
    if service == 0x39 and size != TRANSFER_CONTROL:
        raise EnvelopeError('Unsupported transfer container control')
    if service == 0x37 and size != len(data) - 8:
        raise EnvelopeError('Single-packet container length mismatch')
    return data[8:], format_word


def _check_key(key):
    if not isinstance(key, bytes) or len(key) != 20:
        raise EnvelopeError('MAC calculation requires a 20-byte key')


def _check_inner_request(inner):
    if (not isinstance(inner, bytes) or len(inner) < 2 or inner[0] & 0x80 or
            2 + 2 * inner[1] > len(inner)):
        raise EnvelopeError('Truncated or invalid embedded CIP request')


def _check_inner_response(inner, service):
    if (len(inner) < 4 or inner[0] != (service | 0x80) or inner[1] != 0 or
            4 + 2 * inner[3] > len(inner)):
        raise EnvelopeError('Truncated or mismatched embedded CIP response')


def _batch_children(data, requests=None):
    if len(data) < 2:
        raise EnvelopeError('Truncated batch count')
    count = struct.unpack_from('<H', data)[0]
    if not 1 <= count <= MAX_BATCH_CHILDREN:
        raise EnvelopeError('Batch child count is outside the supported bounds')
    table_end = 2 + 2 * count
    if len(data) < table_end:
        raise EnvelopeError('Truncated batch offset table')
    offsets = struct.unpack_from('<' + 'H' * count, data, 2)
    if (offsets[0] != table_end or offsets[-1] >= len(data) or
            any(left >= right for left, right in zip(offsets, offsets[1:]))):
        raise EnvelopeError('Invalid batch offsets')
    if requests is not None and count != len(requests):
        raise EnvelopeError('Batch reply count does not match its request')
    children = tuple(data[start:end] for start, end in
                     zip(offsets, offsets[1:] + (len(data),)))
    for index, child in enumerate(children):
        if requests is None:
            _check_inner_request(child)
        else:
            _check_inner_response(child, requests[index][0])
    return children


def _batch_request_context(request):
    if (type(request.service) is not int or request.service != 0x38 or
            type(request.sequence) is not int or not 0 <= request.sequence <= 0xFFFFFFFF or
            request.status is not None or not isinstance(request.children, tuple) or
            not 1 <= len(request.children) <= MAX_BATCH_CHILDREN):
        raise EnvelopeError('A supported parsed batch request is required')
    for child in request.children:
        _check_inner_request(child)
    if 6 + 2 + 2 * len(request.children) + sum(map(len, request.children)) + TRAILER_BYTES > MAX_MESSAGE:
        raise EnvelopeError('Batch request context exceeds the message limit')


def _request_context(request):
    if (not isinstance(request, Envelope) or type(request.service) is not int or
            request.service not in (0x36, 0x37, 0x39) or
            type(request.sequence) is not int or not 0 <= request.sequence <= 0xFFFFFFFF or
            not isinstance(request.inner, bytes) or not 2 <= len(request.inner) <= MAX_MESSAGE or
            request.inner[0] & 0x80 or 2 + 2 * request.inner[1] > len(request.inner) or
            request.container_format != (None if request.service == 0x36 else CONTAINER_FORMAT) or
            (request.service == 0x39 and (not isinstance(request,TransferEnvelope) or
             type(request.container_control) is not int or request.container_control != TRANSFER_CONTROL)) or
            (request.service != 0x39 and isinstance(request,TransferEnvelope))):
        raise EnvelopeError('A supported parsed request is required')


def parse_request(raw):
    """Decode one observed envelope without asserting MAC validity."""
    _bounded(raw)
    service = raw[0]
    if service not in (0x36, 0x37, 0x38, 0x39):
        raise EnvelopeError('Unsupported signed request service')
    if raw[1] != 2 or raw[2:6] != ROUTER_PATH:
        raise EnvelopeError('Expected the observed Message Router instance 1 path')
    sequence = struct.unpack_from('<I', raw, len(raw)-TRAILER_BYTES)[0]
    if service == 0x38:
        return BatchEnvelope(service, sequence, _batch_children(raw[6:-TRAILER_BYTES]))
    inner, format_word = _inner(raw[6:-TRAILER_BYTES], service)
    _check_inner_request(inner)
    kind = TransferEnvelope if service == 0x39 else Envelope
    return kind(service, sequence, inner, format_word)


def verify_request(raw, key, *, expected_sequence):
    """Verify a known key and exact counter; callers own replay/session state.

    A valid MAC proves possession of the supplied key, not vendor identity or
    permission to execute the embedded operation. No session is advanced here.
    """
    _check_key(key)
    if type(expected_sequence) is not int or not 0 <= expected_sequence <= 0xFFFFFFFF:
        raise EnvelopeError('Expected sequence must be a UDINT')
    envelope = parse_request(raw)
    if not hmac.compare_digest(hmac.digest(key, raw[:-20], 'sha1'), raw[-20:]):
        raise EnvelopeError('Request MAC verification failed')
    if envelope.sequence != expected_sequence:
        raise EnvelopeError('Request sequence does not match the expected counter')
    return envelope


def parse_response(raw, request):
    """Decode a corresponding wrapper response paired with a parsed request.

    This function checks framing, embedded service and the echoed counter only.
    Use verify_response for a known-key MAC check.
    """
    _bounded(raw)
    if isinstance(request, BatchEnvelope):
        _batch_request_context(request)
        if (raw[0] != 0xB8 or raw[1] != 0 or raw[2] not in (0, 0x1E) or raw[3] != 0):
            raise EnvelopeError('Unsupported batch response header')
        children = _batch_children(raw[4:-TRAILER_BYTES], request.children)
        sequence = struct.unpack_from('<I', raw, len(raw)-TRAILER_BYTES)[0]
        if sequence != request.sequence:
            raise EnvelopeError('Response counter does not match its request')
        return BatchEnvelope(request.service, sequence, children, raw[2])
    _request_context(request)
    if raw[:4] != bytes((request.service | 0x80, 0, 0, 0)):
        raise EnvelopeError('Expected a successful corresponding wrapper response')
    inner, format_word = _inner(raw[4:-TRAILER_BYTES], request.service)
    _check_inner_response(inner, request.inner[0])
    sequence = struct.unpack_from('<I', raw, len(raw)-TRAILER_BYTES)[0]
    if sequence != request.sequence:
        raise EnvelopeError('Response counter does not match its request')
    kind = TransferEnvelope if request.service == 0x39 else Envelope
    return kind(request.service, sequence, inner, format_word)


def verify_response(raw, key, *, request):
    """Authenticate a reply against its parsed request and supplied session key.

    As with request verification, the caller owns session identity and replay
    state. An authenticated embedded CIP error remains an error.
    """
    _check_key(key)
    envelope = parse_response(raw, request)
    if not hmac.compare_digest(hmac.digest(key, raw[:-20], 'sha1'), raw[-20:]):
        raise EnvelopeError('Response MAC verification failed')
    return envelope


def encode_response(request, inner, key):
    """Frame and sign supplied CIP reply bytes without executing any operation."""
    _check_key(key)
    _request_context(request)
    if not isinstance(inner, bytes) or len(inner) > MAX_MESSAGE:
        raise EnvelopeError('Embedded reply must be bounded immutable bytes')
    body = inner
    if request.service in (0x37,0x39):
        control = TRANSFER_CONTROL if request.service == 0x39 else len(inner)
        body = struct.pack('<II', CONTAINER_FORMAT, control) + inner
    raw = bytes((request.service | 0x80, 0, 0, 0)) + body + struct.pack('<I', request.sequence)
    # Validate the same strict framing/counter/inner-header contract before
    # signing. The placeholder has the final MAC's length and is never returned.
    parse_response(raw + b'\0'*20, request)
    return raw + hmac.digest(key, raw, 'sha1')


def encode_batch_response(request, children, key):
    """Sign ordered child replies, preserving each child's service and error."""
    _check_key(key)
    _batch_request_context(request)
    if not isinstance(children, tuple) or len(children) != len(request.children):
        raise EnvelopeError('Batch replies must be an immutable matching tuple')
    offset = 2 + 2 * len(children); offsets = []
    for child, original in zip(children, request.children):
        if not isinstance(child, bytes): raise EnvelopeError('Batch replies must be immutable bytes')
        _check_inner_response(child, original[0])
        offsets.append(offset); offset += len(child)
    if 4 + offset + TRAILER_BYTES > MAX_MESSAGE:
        raise EnvelopeError('Batch reply exceeds the message limit')
    body = struct.pack('<H', len(children)) + struct.pack('<'+'H'*len(offsets), *offsets) + b''.join(children)
    status = 0x1E if any(child[2] for child in children) else 0
    raw = bytes((0xB8, 0, status, 0)) + body + struct.pack('<I', request.sequence)
    parse_response(raw + b'\0'*20, request)
    return raw + hmac.digest(key, raw, 'sha1')
