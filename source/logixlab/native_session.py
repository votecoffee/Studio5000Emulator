"""Anonymous, read-only Studio compatibility sessions for the software model.

The opaque 0x4C proof is acknowledged, not verified. Subsequent messages must
prove possession of our fresh challenge key through their MAC and counter.
No vendor identity, operator permissions or safety authority is established.
"""
import hashlib
import secrets
import struct
import time

from . import key_exchange, signed_messages


class NativeError(ValueError):
    def __init__(self, status, detail):
        self.status = status
        super().__init__(detail)


class NativeSession:
    def __init__(self):
        self.close()

    def close(self):
        self.key = None
        self.stage = 'closed'
        self.sequence = None
        self.context = None
        self.operator_digest = None
        self.deadline = 0
        self.metadata_query = None
        self.read_stream = None

    def begin(self, offer, *, nonce=None):
        self.close()
        parsed = key_exchange.parse_offer(offer)
        nonce = nonce if nonce is not None else secrets.token_bytes(19) + bytes((secrets.randbelow(255) + 1,))
        result = key_exchange.challenge(offer, nonce=nonce)
        self.key = nonce
        self.features = parsed.features
        self.stage = 'challenge'
        self.deadline = time.monotonic() + 300
        return result

    def check_live(self):
        if self.key is None or time.monotonic() >= self.deadline:
            self.close()
            raise NativeError(0x0F, 'Native compatibility session expired; reconnect')

    def acknowledge(self, data):
        self.check_live()
        if self.stage != 'challenge' or len(data) != 22 or data[:2] != b'\x14\0':
            self.close()
            raise NativeError(0x0F, 'Expected one bounded compatibility acknowledgement')
        # This acknowledgement is deliberately not called authentication.
        self.stage = 'acknowledged'
        self.sequence = 1
        return struct.pack('<H', len(self.features)) + b''.join(
            struct.pack('<HI', number, 1) for number, _ in self.features)

    def consume(self, raw):
        self.check_live()
        if self.sequence is None:
            raise NativeError(0x0F, 'Compatibility acknowledgement required')
        try:
            envelope = signed_messages.verify_request(raw, self.key, expected_sequence=self.sequence)
        except signed_messages.EnvelopeError as error:
            self.close()
            raise NativeError(0x0F, 'Native request MAC, framing or counter rejected') from error
        self.sequence += 1
        self.deadline = time.monotonic() + 300
        return envelope

    def registration(self, service, path, payload):
        """Maintain an anonymous model context; retain no operator payload."""
        if self.stage == 'bound':
            return None
        if path.attribute is not None or path.symbols or path.instance != 1:
            raise NativeError(0x0F, 'Anonymous context setup required')
        if self.stage == 'acknowledged' and (service, path.class_id) == (0x5C, 0x8E) and 1 <= len(payload) <= 2048:
            self.operator_digest = hashlib.sha256(payload).digest()
            self.stage = 'operator'
            return b''
        if self.stage == 'operator' and (service, path.class_id) == (0x4B, 0x378) and 8 <= len(payload) <= 2048:
            self.context = struct.pack('<I', secrets.randbelow(0xFFFFFFFF) + 1)
            self.stage = 'context'
            return self.context
        if self.stage == 'context' and (service, path.class_id) == (0x63, 0x8E) and payload == self.context:
            self.stage = 'bound'
            return b''
        raise NativeError(0x0F, 'Unexpected anonymous context operation')


def clear(session):
    native = getattr(session, 'native', None)
    if native is not None:
        native.close()
        del session.native


def acknowledge_existing_timeline(data, current_uid):
    """Acknowledge the observed initializer while retaining a bound source UID.

    Successful v35 reference exchanges retain the controller's existing nonzero
    Timeline UID after different proposals. This implements that already-set
    case only; it never initializes an unset UID or replaces source metadata.
    """
    if (not isinstance(data,bytes) or len(data)!=8 or data[:4]!=b'\1\0\x0A\0'
            or data[4:]==bytes(4)):
        raise NativeError(3,'Expected one nonzero Timeline UID proposal')
    if type(current_uid) is not int or not 1<=current_uid<=0xFFFFFFFF:
        raise NativeError(0x0C,'An existing source Timeline UID is required')
    return b'\1\0\x0A\0\0\0'


def description(enabled):
    return {'enabled': enabled, 'anonymous': True, 'read_only': True,
            'confirmation_proof_verified': False, 'peer_identity_verified': False,
            'operator_authorization': False, 'signed_batches': enabled,
            'signed_transfer_container':enabled,
            'signed_fragment_staging':enabled,
            'signed_routine_source_readback':enabled,
            'routine_read_selectors':[3,9] if enabled else [],
            'routine_source_read_scope':'Unedited source-equivalent installed downloads only',
            'timeline_acknowledgement':'Existing nonzero source UID retained',
            'timeline_initialization':False, 'timeline_replacement':False,
            'controller_mode': 'Program' if enabled else None,
            'idle_timeout_seconds': 300 if enabled else 0}
