"""Source-bound empty Device Diagnostic Object inventories; no live diagnostics."""
from dataclasses import dataclass
import gzip
import io
import zlib

from .model import ModelError
from .native_project import _hash,acd_stream
from .native_diagnostic_profiles import _empty_records

CLASS_ID=0x3B0
MAX_BYTES=128_000_000
MAX_STREAM_BYTES=16_000_000
MAX_RECORDS=200_000


def empty_object_records(data):
    return _empty_records(data,CLASS_ID,'object',MAX_BYTES,MAX_RECORDS)


@dataclass(frozen=True)
class NativeDiagnosticObjects:
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
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid compressed diagnostic object database') from error
        empty_object_records(data)
        return cls(digest,source_l5x_sha256)

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','objects'} or
                manifest['source_l5x_sha256']!=source_l5x_sha256 or
                not isinstance(manifest['objects'],list) or manifest['objects']):
            raise ModelError('Invalid, nonempty or stale diagnostic object manifest')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256)

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,objects=[])

    def description(self):
        return dict(bound=True,class_id=CLASS_ID,objects=0,explicit_empty_collection=True,
            source='Original ACD format-0/body-74 collection with no active diagnostic objects',
            nonempty_objects=False,live_diagnostics=False,configuration_writes=False,captured_objects_replayed=False,
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256)
