"""Read-only evidence of an explicitly empty Security Authority Binding catalog.

Absence in L5X or the legacy Security Code cannot establish this collection.
No authority IDs, URIs, credentials or authentication decisions are modeled.
"""
from dataclasses import dataclass
import gzip
import io
import struct
import zlib

from .model import ModelError
from .native_project import _hash,acd_stream
from .native_diagnostic_profiles import _empty_records

CLASS_ID=0x36A
MAX_BYTES=128_000_000
MAX_STREAM_BYTES=16_000_000
MAX_RECORDS=200_000
# Checked format-0 collection profile: zero fields, empty sentinels and the
# repeated class ID. Original pointer words before the path are never used.
EMPTY_TAIL=struct.pack('<13I',0,0,0,0,0,0xFFFFFFFF,0,0xFFFFFFFF,0,CLASS_ID,0,0,0xFFFFFFFF)


def empty_binding_records(data):
    return _empty_records(data,CLASS_ID,'authority binding',MAX_BYTES,MAX_RECORDS,
                          category='security',collection_tail=EMPTY_TAIL)


@dataclass(frozen=True)
class NativeSecurityBindings:
    source_acd_sha256: str
    source_l5x_sha256: str

    def __post_init__(self):
        _hash(self.source_acd_sha256);_hash(self.source_l5x_sha256)

    @classmethod
    def from_acd(cls,path,source_l5x_sha256):
        _hash(source_l5x_sha256);digest,raw=acd_stream(path,'Comps.Dat',limit=MAX_STREAM_BYTES)
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw) as reader:
                data=reader.read(MAX_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:
            raise ModelError('Invalid compressed security authority binding database') from error
        empty_binding_records(data)
        return cls(digest,source_l5x_sha256)

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        _hash(source_l5x_sha256)
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','bindings'} or
                manifest['source_l5x_sha256']!=source_l5x_sha256 or
                not isinstance(manifest['bindings'],list) or manifest['bindings']):
            raise ModelError('Invalid, nonempty or stale security authority binding manifest')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256)

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,bindings=[])

    def description(self):
        return dict(bound=True,class_id=CLASS_ID,bindings=0,explicit_empty_collection=True,
            source='Original ACD format-0/body-74 collection with no active authority bindings',
            nonempty_bindings=False,authority_configuration=False,authentication=False,authorization=False,
            legacy_security_code_used=False,configuration_writes=False,captured_bindings_replayed=False,
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256)
