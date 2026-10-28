"""Exact accepted edit source, detached from stale downloaded components.

Only an accepted complete Standard RLL source is retained. Compiled containers,
removed-rung metadata and native edit lifecycle semantics are not reconstructed.
"""
from dataclasses import dataclass,field
import hashlib

from . import routine_source,upload_routine_source
from .model import parse_rung

Error=routine_source.SourceError
MAX_ROUTINES=128
MAX_BYTES=8*1024*1024


@dataclass(frozen=True)
class AcceptedSource:
    key:str=field(repr=False)
    target:tuple=field(repr=False)
    source_hash:str=field(repr=False)
    revision:int
    data:bytes=field(repr=False)
    sha256:str


def records(project):
    rows=getattr(project,'runtime_native_sources',())
    if (type(rows) is not tuple or len(rows)>MAX_ROUTINES
            or any(type(r) is not AcceptedSource for r in rows)
            or any(type(r.data) is not bytes or type(r.target) is not tuple or len(r.target)!=2 for r in rows)
            or len({r.key for r in rows})!=len(rows) or len({r.target for r in rows})!=len(rows)
            or sum(len(r.data) for r in rows)>MAX_BYTES):
        raise Error('accepted_source_inventory_invalid')
    return rows


def retain(previous,project,key,source,data,target):
    """Return immutable replacement records; neither input Project is mutated."""
    rows=tuple(r for r in records(previous) if r.key!=key)
    if data is None and target is None:return rows
    if (type(data) is not bytes or not 64<=len(data)<=262144 or type(target) is not tuple or len(target)!=2
            or any(type(v) is not int or not 1<=v<=0xFFFF for v in target)
            or routine_source.decode(data)!=source or source.name.casefold()!=project.routines[key].name.casefold()
            or project.programs[project.routines[key].program]['class']!='Standard'):
        raise Error('accepted_source_complete_standard_rll_required')
    row=AcceptedSource(key,target,project.sha256,project.runtime_revision,data,hashlib.sha256(data).hexdigest())
    result=rows+(row,)
    if len(result)>MAX_ROUTINES or len({r.target for r in result})!=len(result) or sum(len(r.data) for r in result)>MAX_BYTES:
        raise Error('accepted_source_storage_limit')
    return result


def read(app,program,routine):
    """Validate retained TextIOI against the active routine on every source read."""
    engine=app.engine;project=engine.project
    rows=[r for r in records(project) if r.target==(program,routine)]
    if len(rows)!=1:raise Error('accepted_source_unavailable')
    record=rows[0];catalog=app.native_routines
    row=catalog.by_instance.get((program,routine)) if catalog is not None else None
    identity=app.native_project_identity
    if (row is None or row.type_word!=0x7FF or row.source_key is None
            or identity is None or any(c is None or c.source_acd_sha256!=identity.source_acd_sha256
                for c in (app.native_symbols,catalog,app.native_types))
            or (row.program+'/'+row.name).casefold()!=record.key
            or record.source_hash!=project.sha256 or type(record.revision) is not int
            or not 1<=record.revision<=getattr(project,'runtime_revision',0)
            or record.key not in getattr(project,'runtime_edited_routines',())
            or hashlib.sha256(record.data).hexdigest()!=record.sha256):
        raise Error('accepted_source_binding_changed')
    source=routine_source.decode(record.data)
    neutral=routine_source.resolve(source,project,app.native_symbols,catalog,app.native_types,row.program)
    active=project.routines.get(record.key)
    if (active is None or active.kind!='RLL' or active.problems
            or project.programs[row.program]['class']!='Standard' or source.name.casefold()!=row.name.casefold()
            or [parse_rung(t) for t in neutral]!=[r['nodes'] for r in active.rungs]):
        raise Error('accepted_source_active_logic_changed')
    return upload_routine_source.from_download(record.data,target_class='Standard')


def description(project):
    rows=records(project)
    return dict(retained_routines=len(rows),retained_bytes=sum(len(r.data) for r in rows),
        selectors=[3],complete_upload=False,compiled_component_readback=False,payloads_exposed=False)
