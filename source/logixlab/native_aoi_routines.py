"""Source-bound AOI-scoped Executable identities; no compiled code or writes.

AOI and Program parents use separate namespaces even when their numeric IDs
coincide. The shared bounded Comps.Dat parser accepts only component type 259,
header version 0 and body format 54 for AOI parents (Program uses type 256).
"""
from dataclasses import dataclass
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

    def manifest(self):
        return dict(aoi=self.aoi,name=self.name,aoi_instance=self.aoi_instance,instance=self.instance)


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
            if not isinstance(row,dict) or set(row)!={'aoi','name','aoi_instance','instance'}:
                raise ModelError('Invalid native AOI routine fields')
            converted.append(dict(program=row['aoi'],name=row['name'],program_instance=row['aoi_instance'],instance=row['instance']))
        # Reuse immutable manifest validation, including duplicate child IDs,
        # exact hashes, bounded names/counts and conflicting parent identities.
        validated=NativeRoutines(source_acd_sha256,source_l5x_sha256,converted)
        object.__setattr__(self,'source_acd_sha256',validated.source_acd_sha256)
        object.__setattr__(self,'source_l5x_sha256',validated.source_l5x_sha256)
        object.__setattr__(self,'rows',tuple(AOIRoutine(r.program,r.name,r.program_instance,r.instance) for r in validated.rows))

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
            aoi_instance=r['program_instance'],instance=r['instance']) for r in rows])

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
            compiled_code=False,native_edit_authority=False,native_safety_execution=False)
