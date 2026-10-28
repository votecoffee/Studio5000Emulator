"""Immutable downloaded source and bounded selector9 profile after edits.

The snapshot contains validated source and opaque profile bytes, never ELF. Its
catalog identities and every resolved rung are rechecked against the live model.
"""
from dataclasses import dataclass,field
import hashlib
import struct

from . import routine_source,upload_routine_source
from .download_image import ImageError
from .download_routines import RoutineBindings,MAX_STORAGE
from .model import parse_rung
from .incremental_download import ROUTINE_DATA


def catalog_stamp(symbols,routines,types,acd,l5x):
    if any(c is None or (c.source_acd_sha256,c.source_l5x_sha256)!=(acd,l5x)
           for c in (symbols,routines,types)):
        raise ImageError('download_source_catalog_changed')
    return hashlib.sha256(repr((symbols.manifest(),routines.manifest(),types.binding_stamp())).encode()).hexdigest()


@dataclass(frozen=True)
class Source:
    key:str=field(repr=False)
    target:tuple=field(repr=False)
    data:bytes=field(repr=False)
    sha256:str
    component:bytes|None=field(default=None,repr=False)
    component_sha256:str|None=None


@dataclass(frozen=True)
class Snapshot:
    acd:str
    l5x:str
    catalog:str
    sources:tuple=field(repr=False)

    @classmethod
    def prepare(cls,headers,types,metadata=None):
        ns=headers.namespace;batch=ns._routine_batch
        if batch is None:return None
        acd,l5x=ns._source.acd_sha256,ns._source.l5x_sha256
        stamp=catalog_stamp(headers.symbols,headers.routines,types,acd,l5x)
        bindings=RoutineBindings(headers,types);sources=[]
        for target in sorted(batch._values):
            raw=batch.read(*target,'source',bindings)
            if raw[:8]!=struct.pack('<II',1,3):raise ImageError('download_source_profile_changed')
            bindings.source(target,raw[8:]);row=headers._routine(*target)
            component=None;incremental=ns._incremental
            if incremental is not None and target in incremental._routine_data:
                component=incremental.read_routine_data(*target,ns._image,ns._source,headers,metadata)
                if component!=ROUTINE_DATA:raise ImageError('download_source_component_profile_changed')
            sources.append(Source((row.program+'/'+row.name).casefold(),target,raw[8:],hashlib.sha256(raw[8:]).hexdigest(),
                component,hashlib.sha256(component).hexdigest() if component is not None else None))
        if sum(len(s.data)+len(s.component or b'') for s in sources)>MAX_STORAGE:raise ImageError('download_source_storage_limit')
        return cls(acd,l5x,stamp,tuple(sources))

    def check_catalog(self,app):
        project=app.engine.project;identity=app.native_project_identity
        if (identity is None or (identity.source_acd_sha256,project.sha256)!=(self.acd,self.l5x)
                or catalog_stamp(app.native_symbols,app.native_routines,app.native_types,self.acd,self.l5x)!=self.catalog):
            raise ImageError('download_source_catalog_changed')

    def source_key(self,app,program,routine):
        """Original opaque configuration; plain RLL replacements do not set it."""
        if type(program) is not int or type(routine) is not int:raise ImageError('download_source_key_unavailable')
        self.check_catalog(app)
        row=app.native_routines.by_instance.get((program,routine))
        if (row is None or row.type_word!=0x7FF or row.source_key is None
                or not any(s.target==(program,routine) for s in self.sources)):
            raise ImageError('download_source_key_unavailable')
        return row.source_key

    def profile(self,app,program,routine,selector):
        """Keep accepted selector9 bytes; plain RLL replacement has no setter.

        The empty selector4 view belongs to the same unprotected RLL profile.
        Neither view supplies ELF or infers new opaque component data.
        """
        if type(selector) is not int or selector not in (4,9):raise ImageError('download_source_profile_selector')
        self.source_key(app,program,routine)
        from .routine_read import source
        source(app,program,routine,3)
        installed=app.engine.installed_download
        if installed.routine_sources is not self or installed.tag_bindings is None:
            raise ImageError('download_source_profile_installation_changed')
        installed.tag_bindings.check(app,installed)
        rows=[s for s in self.sources if s.target==(program,routine)]
        if len(rows)!=1:raise ImageError('download_source_target_unavailable')
        row=app.native_routines.by_instance[(program,routine)]
        if rows[0].key!=(row.program+'/'+row.name).casefold():raise ImageError('download_source_target_unavailable')
        if selector==4:return b''
        record=rows[0]
        if (type(record.component) is not bytes or record.component!=ROUTINE_DATA
                or hashlib.sha256(record.component).hexdigest()!=record.component_sha256):
            raise ImageError('download_source_component_unavailable')
        return record.component

    def read(self,app,program,routine):
        self.check_catalog(app)
        return self._read(app,program,routine)

    def _read(self,app,program,routine):
        """Caller has checked this catalog in the same locked request."""
        if type(program) is not int or type(routine) is not int:
            raise ImageError('download_source_target_unavailable')
        project=app.engine.project
        revision=getattr(project,'runtime_revision',0);edited=getattr(project,'runtime_edited_routines',())
        if (type(revision) is not int or revision<1 or type(edited) is not tuple or not edited
                or any(key not in project.routines for key in edited)):
            raise ImageError('download_source_edit_inventory_required')
        records=[s for s in self.sources if s.target==(program,routine)]
        if len(records)!=1:raise ImageError('download_source_target_unavailable')
        record=records[0];row=app.native_routines.by_instance.get(record.target)
        if (row is None or row.type_word!=0x7FF or row.source_key is None
                or (row.program+'/'+row.name).casefold()!=record.key or record.key in edited
                or type(record.data) is not bytes or hashlib.sha256(record.data).hexdigest()!=record.sha256):
            raise ImageError('download_source_untouched_routine_required')
        active=project.routines.get(record.key)
        if (active is None or active.kind!='RLL' or active.problems
                or project.programs[row.program]['class']!='Standard'):
            raise ImageError('download_source_standard_rll_required')
        try:
            decoded=routine_source.decode_download(record.data,empty=not active.rungs)
            neutral=routine_source.resolve(decoded,project,app.native_symbols,app.native_routines,app.native_types,row.program)
            if (decoded.name.casefold()!=row.name.casefold()
                    or [parse_rung(text) for text in neutral]!=[r['nodes'] for r in active.rungs]):
                raise ImageError('download_source_active_logic_changed')
            if not decoded.rungs:return record.data
            return upload_routine_source.from_download(record.data,target_class='Standard')
        except routine_source.SourceError as error:raise ImageError(str(error)) from error
