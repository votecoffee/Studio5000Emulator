"""Source-bound AOI-scoped Executable identities; no compiled code or writes.

AOI and Program parents use separate namespaces even when their numeric IDs
coincide. The shared bounded Comps.Dat parser accepts only component type 259,
header version 0 and body format 54 for AOI parents. Program records use type
256 or the separately checked ordinary saved-download type-259 profile.
"""
from dataclasses import dataclass,field
import gzip
import io
import zlib
from .model import ModelError
from .native_aois import NativeAOIs
from .native_project import _hash,acd_stream
from .native_routines import NativeRoutines,routine_paths,MAX_BYTES,MAX_STREAM_BYTES,MAX_ROUTINES


@dataclass(frozen=True)
class AOIRoutine:
    aoi: str
    name: str
    aoi_instance: int
    instance: int
    type_word: int | None = None
    source_key: bytes | None = field(default=None,repr=False)

    def manifest(self):
        return dict(aoi=self.aoi,name=self.name,aoi_instance=self.aoi_instance,instance=self.instance,
                    **({'type_word':self.type_word} if self.type_word is not None else {}),
                    **({'source_key_hex':self.source_key.hex()} if self.source_key is not None else {}))


@dataclass(frozen=True,init=False)
class NativeAOIRoutines:
    source_acd_sha256: str
    source_l5x_sha256: str
    rows: tuple[AOIRoutine,...]

    def __init__(self,source_acd_sha256,source_l5x_sha256,routines):
        if not isinstance(routines,(list,tuple)) or len(routines)>MAX_ROUTINES:
            raise ModelError('Native AOI routines require an explicit inventory')
        converted=[]
        for row in routines:
            required={'aoi','name','aoi_instance','instance'}
            if not isinstance(row,dict) or not required<=row.keys() or row.keys()-required-{'type_word','source_key_hex'}:
                raise ModelError('Invalid native AOI routine fields')
            converted.append(dict(program=row['aoi'],name=row['name'],program_instance=row['aoi_instance'],instance=row['instance'],
                                  **({'type_word':row['type_word']} if 'type_word' in row else {}),
                                  **({'source_key_hex':row['source_key_hex']} if 'source_key_hex' in row else {})))
        # Reuse immutable manifest validation, including duplicate child IDs,
        # exact hashes, bounded names/counts and conflicting parent identities.
        validated=NativeRoutines(source_acd_sha256,source_l5x_sha256,converted)
        object.__setattr__(self,'source_acd_sha256',validated.source_acd_sha256)
        object.__setattr__(self,'source_l5x_sha256',validated.source_l5x_sha256)
        object.__setattr__(self,'rows',tuple(AOIRoutine(r.program,r.name,r.program_instance,r.instance,r.type_word,r.source_key) for r in validated.rows))

    @classmethod
    def from_acd(cls,path,source_l5x_sha256,expected_routines,native_aois):
        _hash(source_l5x_sha256)
        if not isinstance(native_aois,NativeAOIs) or native_aois.source_l5x_sha256!=source_l5x_sha256:
            raise ModelError('AOI routines require matching source-bound AOI identities')
        if not isinstance(expected_routines,(list,tuple)) or len(expected_routines)>MAX_ROUTINES or any(not isinstance(row,dict)
                or set(row)!={'aoi','name'} for row in expected_routines):
            raise ModelError('Invalid expected AOI routine inventory')
        expected=[dict(program=row['aoi'],name=row['name']) for row in expected_routines]
        digest,raw=acd_stream(path,'Comps.Dat',limit=MAX_STREAM_BYTES)
        if digest!=native_aois.source_acd_sha256:raise ModelError('AOI routine ACD source differs')
        try:
            reader=gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2]==b'\x1f\x8b' else io.BytesIO(raw)
            with reader:data=reader.read(MAX_BYTES+1)
        except (OSError,EOFError,zlib.error) as error:
            raise ModelError('Invalid compressed native AOI routine inventory') from error
        rows=routine_paths(data,expected,{name:pair[1] for name,pair in native_aois.definitions.items()},parent_class=0x338)
        return cls(digest,source_l5x_sha256,[dict(aoi=r['program'],name=r['name'],
            aoi_instance=r['program_instance'],instance=r['instance'],
            **({'type_word':r['type_word']} if 'type_word' in r else {}),
            **({'source_key_hex':r['source_key_hex']} if 'source_key_hex' in r else {})) for r in rows])

    @classmethod
    def from_manifest(cls,manifest,source_l5x_sha256):
        _hash(source_l5x_sha256)
        if (not isinstance(manifest,dict) or set(manifest)!={'source_acd_sha256','source_l5x_sha256','routines'}
                or manifest['source_l5x_sha256']!=source_l5x_sha256 or not isinstance(manifest['routines'],list)):
            raise ModelError('Invalid or stale native AOI routine manifest')
        return cls(manifest['source_acd_sha256'],source_l5x_sha256,manifest['routines'])

    def lookup(self,aoi,name):
        return next((r for r in self.rows if r.aoi.casefold()==aoi.casefold() and r.name.casefold()==name.casefold()),None)

    def manifest(self):
        return dict(source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
                    routines=[r.manifest() for r in self.rows])

    def description(self):
        return dict(bound=True,routines=len(self.rows),aois=len({r.aoi_instance for r in self.rows}),
            source='ACD Comps.Dat AOI-scoped Executable format 54 and explicit readable source routines',
            source_acd_sha256=self.source_acd_sha256,source_l5x_sha256=self.source_l5x_sha256,
            type_words_available=sum(row.type_word is not None for row in self.rows),type_word_semantics_inferred=False,
            source_key_metadata_available=sum(row.source_key is not None for row in self.rows),source_keys_decrypted=False,
            compiled_code=False,native_edit_authority=False,native_safety_execution=False)
