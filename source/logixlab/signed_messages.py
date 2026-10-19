"""Offline codec for the observed v35 Message Router 0x36/0x37 envelopes.

Parsing establishes structure only. Verification requires the caller's 20-byte
test/session key and covers the complete CIP message before its MAC.
This module retains no keys, opens no connections and dispatches no operations.
Confirmation, peer authentication and service 0x38 remain unimplemented.
"""
from dataclasses import dataclass
import hmac
import struct


MAX_MESSAGE = 65519  # 65535-byte SendRRData body minus its 16-byte CPF overhead.
TRAILER_BYTES = 24  # Little-endian UDINT counter followed by a SHA-1 MAC.
ROUTER_PATH = b'\x20\x02\x24\x01'
CONTAINER_FORMAT = 0x301


class EnvelopeError(ValueError):
    pass


@dataclass(frozen=True)
class Envelope:
    service: int
    sequence: int
    inner: bytes
    container_format: int | None = None


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
    if size != len(data) - 8:
        raise EnvelopeError('Single-packet container length mismatch')
    return data[8:], format_word


def _check_key(key):
    if not isinstance(key, bytes) or len(key) != 20:
        raise EnvelopeError('MAC calculation requires a 20-byte key')


def _request_context(request):
    if (not isinstance(request, Envelope) or type(request.service) is not int or
            request.service not in (0x36, 0x37) or
            type(request.sequence) is not int or not 0 <= request.sequence <= 0xFFFFFFFF or
            not isinstance(request.inner, bytes) or not 2 <= len(request.inner) <= MAX_MESSAGE or
            request.inner[0] & 0x80 or 2 + 2 * request.inner[1] > len(request.inner) or
            request.container_format != (CONTAINER_FORMAT if request.service == 0x37 else None)):
        raise EnvelopeError('A supported parsed request is required')


def parse_request(raw):
    """Decode one observed envelope without asserting MAC validity."""
    _bounded(raw)
    service = raw[0]
    if service not in (0x36, 0x37):
        raise EnvelopeError('Unsupported signed request service')
    if raw[1] != 2 or raw[2:6] != ROUTER_PATH:
        raise EnvelopeError('Expected the observed Message Router instance 1 path')
    inner, format_word = _inner(raw[6:-TRAILER_BYTES], service)
    if len(inner) < 2 or inner[0] & 0x80 or 2 + 2 * inner[1] > len(inner):
        raise EnvelopeError('Truncated or invalid embedded CIP request')
    return Envelope(service, struct.unpack_from('<I', raw, len(raw)-TRAILER_BYTES)[0],
                    inner, format_word)


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
    """Decode a successful wrapper response paired with a parsed request.

    This function checks framing, embedded service and the echoed counter only.
    Use verify_response for a known-key MAC check.
    """
    _bounded(raw)
    _request_context(request)
    if raw[:4] != bytes((request.service | 0x80, 0, 0, 0)):
        raise EnvelopeError('Expected a successful corresponding wrapper response')
    inner, format_word = _inner(raw[4:-TRAILER_BYTES], request.service)
    if (len(inner) < 4 or inner[0] != (request.inner[0] | 0x80) or inner[1] != 0 or
            4 + 2 * inner[3] > len(inner)):
        raise EnvelopeError('Truncated or mismatched embedded CIP response')
    sequence = struct.unpack_from('<I', raw, len(raw)-TRAILER_BYTES)[0]
    if sequence != request.sequence:
        raise EnvelopeError('Response counter does not match its request')
    return Envelope(request.service, sequence, inner, format_word)


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
    if request.service == 0x37:
        body = struct.pack('<II', CONTAINER_FORMAT, len(inner)) + inner
    raw = bytes((request.service | 0x80, 0, 0, 0)) + body + struct.pack('<I', request.sequence)
    # Validate the same strict framing/counter/inner-header contract before
    # signing. The placeholder has the final MAC's length and is never returned.
    parse_response(raw + b'\0'*20, request)
    return raw + hmac.digest(key, raw, 'sha1')
