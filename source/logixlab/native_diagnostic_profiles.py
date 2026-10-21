"""Original ACD evidence for an explicitly empty Device Diagnostic Profile list."""
from dataclasses import dataclass
import gzip
import io
import struct
import zlib

from .model import ModelError
from .native_project import _hash,acd_stream

CLASS_ID=0x3B1
MAX_BYTES=128_000_000
MAX_STREAM_BYTES=16_000_000
MAX_RECORDS=200_000


def empty_profile_records(data):
    """Require one active format-0 collection and no active profile definitions.

    Absence alone is not evidence. Deleted records and allocation tails are not
    active definitions; nonempty and scoped collections need a future decoder.
    """
    if not isinstance(data,bytes) or not 24<=len(data)<=MAX_BYTES:raise ModelError('Invalid diagnostic profile database size')
    size,pos=struct.unpack_from('<II',data,8);end=size+1
    if struct.unpack_from('<I',data)[0]+1!=len(data) or not 24<=pos<=min(end,4096) or end>len(data):
        raise ModelError('Unsupported diagnostic profile database bounds')
    collection=False;records=0
    while pos<end:
        records+=1
        if records>MAX_RECORDS or end-pos<6:raise ModelError('Invalid diagnostic profile record header')
        kind,length=struct.unpack_from('<HI',data,pos)
        if kind not in (0xFAFA,0xFDFD,0xFEFE,0xFBBF) or not 6<=length<=end-pos:
            raise ModelError('Invalid diagnostic profile record bounds')
        record=memoryview(data)[pos+6:pos+length];pos+=length
        if kind!=0xFAFA:continue
        if len(record)<148:raise ModelError('Truncated diagnostic profile component')
        used=struct.unpack_from('<I',record)[0]
        if not 148<=used<=len(record) or struct.unpack_from('<I',record,12)[0]:
            raise ModelError('Unsupported diagnostic profile component header')
        body=record[148:used]
        if len(body)<22:continue
        path=struct.unpack_from('<6H',body,10)
        if CLASS_ID in path[2::2]:raise ModelError('Scoped diagnostic profiles are unsupported')
        if path[0]!=CLASS_ID:continue
        if (path!=(CLASS_ID,0,0,0,0,0) or len(body)!=74 or
                struct.unpack_from('<H',record,10)[0] or struct.unpack_from('<H',body,8)[0]):
            raise ModelError('Nonempty or unsupported diagnostic profile collection')
        if collection:raise ModelError('Ambiguous diagnostic profile collection')
        collection=True
    if not collection:raise ModelError('Explicit empty diagnostic profile collection required')
    return []


@dataclass(frozen=True)
class NativeDiagnosticProfiles:
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
        except (OSError,EOFError,zlib.error) as error:raise ModelError('Invalid compressed diagnostic profile database') from error
        empty_profile_records(data)
        return cls(digest,source_l5x_sha256)

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','profiles'} or
                manifest['source_l5x_sha256']!=source_l5x_sha256 or
                not isinstance(manifest['profiles'],list) or manifest['profiles']):
            raise ModelError('Invalid, nonempty or stale diagnostic profile manifest')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256)

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,profiles=[])

    def description(self):
        return dict(bound=True,class_id=CLASS_ID,profiles=0,explicit_empty_collection=True,
            source='Original ACD format-0/body-74 collection with no active profile definitions',
            nonempty_profiles=False,configuration_writes=False,captured_definitions_replayed=False,
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256)
