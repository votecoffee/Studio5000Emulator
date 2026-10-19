"""Opaque, source-bound comparison tokens for the modeled controller object.

Attribute widths follow the documented cache-refresh interface. These values
identify this model's source revision; they are not native firmware signatures.
"""
import hashlib
import struct
from dataclasses import dataclass
from . import __version__


ATTRIBUTE_WIDTHS = ((1, 2), (2, 2), (3, 4), (4, 4), (10, 4))


@dataclass(frozen=True)
class CatalogRevision:
    token: bytes

    @classmethod
    def from_source(cls, source_sha256):
        source_digest = bytes.fromhex(source_sha256)
        if len(source_digest) != 32: raise ValueError('A complete source SHA-256 is required')
        domain = b'LogixLab catalog revision v1\0' + __version__.encode('ascii') + b'\0'
        return cls(hashlib.sha256(domain + source_digest).digest()[:16])

    def attributes(self):
        values = struct.unpack('<HHIII', self.token)
        return {attribute: value.to_bytes(width, 'little')
                for (attribute, width), value in zip(ATTRIBUTE_WIDTHS, values)}

    def description(self):
        return {'token': self.token.hex(), 'policy': 'Source bytes and model version; stable across runtime changes',
                'native_firmware_signature': False}

    def compatibility_attributes(self):
        """Empty virtual change log with source-derived identifiers.

        Format 2 and the Logix writer marker identify the observed wire format;
        none of these generated identifiers assert native ACD correlation.
        """
        attributes=self.attributes()
        attributes.update({5:b'\0\0',6:b'\0\0',7:struct.pack('<I',2),
                           8:self.token[8:12],9:struct.pack('<HH',1,1)})
        return attributes
