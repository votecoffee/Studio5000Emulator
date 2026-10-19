"""Observed v35 Extended Device public-key challenge, without confirmation.

This format uses a raw RSA public operation and little-endian ciphertext.
It is protocol compatibility research, not a peer-authentication mechanism.
Opaque trailing offer data is length checked but not authenticated. No private
vendor key, captured reply or session secret is retained by this implementation.
"""
from dataclasses import dataclass
import secrets
import struct


class OfferError(ValueError):
    def __init__(self, status, detail):
        self.status = status
        super().__init__(detail)


@dataclass(frozen=True)
class PublicOffer:
    exponent: int
    modulus: int
    features: tuple


def parse_offer(data):
    if len(data) < 8:
        raise OfferError(0x13, 'Truncated v35 key offer')
    boundary, word1, word2, count = struct.unpack_from('<4H', data)
    if (word1, word2) != (1, 1):
        raise OfferError(8, 'Unsupported key-offer format version')
    if not 1 <= count <= 5:
        raise OfferError(3, 'Key-offer feature count must be 1..5')
    if len(data) < 8 + 4 * count + 2:
        raise OfferError(0x13, 'Truncated key-offer feature list')
    features = tuple(struct.unpack_from('<HH', data, 8 + 4 * i) for i in range(count))
    if len({number for number, _ in features}) != count:
        raise OfferError(3, 'Duplicate key-offer feature')
    if any(number not in range(2, 7) or version != 1 for number, version in features):
        raise OfferError(8, 'Unsupported key-offer feature version')
    position = 8 + 4 * count
    if struct.unpack_from('<H', data, position)[0] != 2:
        raise OfferError(8, 'Unsupported public-key parameter count')
    position += 2
    parameters = []
    for expected_tag, width in ((0x8080, 3), (0x8081, 128)):
        if len(data) < position + 4:
            raise OfferError(0x13, 'Truncated public-key parameter')
        tag, size = struct.unpack_from('<HH', data, position)
        if (tag, size) != (expected_tag, width):
            raise OfferError(8, 'Unsupported public-key parameter layout')
        position += 4
        if len(data) < position + size:
            raise OfferError(0x13, 'Truncated public-key integer')
        parameters.append(int.from_bytes(data[position:position + size], 'big'))
        position += size
    if boundary != position:
        raise OfferError(3, 'Key-offer boundary does not match its parameters')
    # The remaining 128 bytes are opaque. Their trust/signature semantics are
    # not implemented, and the API explicitly reports peer trust as unverified.
    if len(data) < position + 128:
        raise OfferError(0x13, 'Truncated opaque key-offer data')
    if len(data) != position + 128:
        raise OfferError(0x15, 'Key offer has trailing bytes')
    exponent, modulus = parameters
    if exponent != 65537:
        raise OfferError(8, 'Only the observed public exponent is supported')
    if modulus.bit_length() != 1024 or not modulus & 1:
        raise OfferError(3, 'Public modulus must be an odd 1024-bit integer')
    return PublicOffer(exponent, modulus, features)


def challenge(data, *, nonce=None):
    offer = parse_offer(data)
    if nonce is None:
        # A nonzero high byte keeps the integer's little-endian encoding at
        # exactly 20 bytes, including for clients using minimal integer blobs.
        nonce = secrets.token_bytes(19) + bytes((secrets.randbelow(255) + 1,))
    if not isinstance(nonce, bytes) or len(nonce) != 20 or nonce[-1] == 0:
        raise ValueError('Challenge nonce must be a 20-byte unsigned integer')
    encrypted = pow(int.from_bytes(nonce, 'little'), offer.exponent, offer.modulus)
    return struct.pack('<H', 128) + encrypted.to_bytes(128, 'little')


def description(native_read_only=False):
    return {'challenge': True, 'confirmation': False, 'signed_messages': native_read_only,
            'peer_identity_verified': False, 'session_secret_retained': native_read_only}
