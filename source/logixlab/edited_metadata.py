"""Detached current metadata for the supported native RLL Comment-removal edit."""
from dataclasses import dataclass,field
import hashlib

from . import accepted_routine_source,routine_source,rung_metadata
from .download_image import ImageError
from .native_metadata_values import encode_records


def key(row):return row.target,row.locale_word,row.definition
def digest(rows):return hashlib.sha256(repr(rows).encode()).hexdigest()


def previous_regions(installed,project,name,target):
    if name in getattr(project,'runtime_edited_routines',()):
        records=[r for r in accepted_routine_source.records(project) if r.key==name and r.target==target]
    else:
        records=[r for r in installed.routine_sources.sources if r.key==name and r.target==target]
    if len(records)!=1 or hashlib.sha256(records[0].data).hexdigest()!=records[0].sha256:
        raise ImageError('edited_metadata_previous_source_required')
    try:source=routine_source.decode_download(records[0].data,empty=not project.routines[name].rungs)
    except routine_source.SourceError as error:raise ImageError('edited_metadata_previous_source_changed') from error
    if source.name.casefold()!=project.routines[name].name.casefold():raise ImageError('edited_metadata_previous_source_changed')
    return {r.region_id for r in source.rungs}


@dataclass(frozen=True)
class View:
    original:object=field(repr=False)
    project:object=field(repr=False)
    revision:int
    rows:tuple=field(repr=False)
    original_stamp:str
    stamp:str
    data:bytes=field(repr=False)
    removals:tuple=field(repr=False)

    @classmethod
    def prepare(cls,installed,previous,project,name,target,data,packets):
        if packets is None or data is None or target is None or installed.metadata is None or installed.routine_sources is None:
            return None
        original=installed.metadata;previous_view=installed.edited_metadata
        if getattr(previous,'runtime_revision',0) and previous_view is None:return None
        if type(packets) is not tuple or len(packets)>1024:raise ImageError('edited_metadata_packet_limit')
        original.body(original.catalog,'all-objects')
        records=[s for s in installed.routine_sources.sources if s.target==target and s.key==name]
        if len(records)!=1:raise ImageError('edited_metadata_target_changed')
        if next((d.name for d in original.catalog.definitions.rows if d.instance==1),None)!='Comment':
            raise ImageError('edited_metadata_comment_definition_required')
        old_regions=previous_regions(installed,previous,name,target)
        current={r.region_id for r in routine_source.decode(data).rungs};removed=old_regions-current
        deletes=[]
        for packet in packets:
            try:row,number=rung_metadata.removal(packet,target)
            except ValueError as error:raise ImageError('edited_metadata_removal_invalid') from error
            if number not in removed:raise ImageError('edited_metadata_removal_source_mismatch')
            deletes.append(key(row))
        rows=original.rows if previous_view is None else previous_view.rows
        if previous_view is not None:
            if (previous_view.original is not original or previous_view.project is not previous
                    or previous_view.stamp!=digest(previous_view.rows)):
                raise ImageError('edited_metadata_previous_view_changed')
        result=tuple(row for row in rows if key(row) not in set(deletes))
        history=(() if previous_view is None else previous_view.removals)+tuple(deletes)
        # Unsupported/stale affected properties keep the all-object view absent.
        # They never silently disappear or become current through a source edit.
        for row in result:
            if rung_metadata.scope(row.target)==target:
                try:number=rung_metadata.region(row.target)
                except ValueError:return None
                if (number not in current or row.definition!=1 or row.kind!=1):return None
            for reference in row.references:
                if rung_metadata.scope(reference.target)==target:return None
        return cls(original,project,project.runtime_revision,result,digest(original.rows),digest(result),encode_records(result),history)

    def body(self,app,installed,identity):
        project=app.engine.project;original=installed.metadata
        if (installed.edited_metadata is not self or original is not self.original or self.project is not project
                or self.revision!=getattr(project,'runtime_revision',0) or self.stamp!=digest(self.rows)
                or self.original_stamp!=digest(original.rows) or self.data!=encode_records(self.rows)):
            raise ImageError('edited_metadata_view_changed')
        if encode_records(original.rows)!=original.body(app.native_metadata_values,'all-objects'):
            raise ImageError('edited_metadata_original_view_changed')
        original.edited_controller_body(app.native_metadata_values,project,identity)
        if installed.routine_sources is None or installed.tag_bindings is None:
            raise ImageError('edited_metadata_installation_required')
        installed.tag_bindings.check_metadata(app,installed)
        from .routine_read import edited_sources
        from .upload_routine_source import decode
        current={}
        for target,blob in edited_sources(app):
            row=app.native_routines.by_instance[target]
            name=(row.program+'/'+row.name).casefold()
            value=decode(blob) if project.routines[name].rungs else None
            current[target]=set(r.region_id for r in value.records) if value is not None else set()
        edited=set(project.runtime_edited_routines)
        for row in self.rows:
            target=rung_metadata.scope(row.target)
            if target in current:
                native=app.native_routines.by_instance[target]
                if (native.program+'/'+native.name).casefold() in edited:
                    try:number=rung_metadata.region(row.target)
                    except ValueError as error:raise ImageError('edited_metadata_region_unsupported') from error
                    if number not in current[target] or row.definition!=1 or row.kind!=1:
                        raise ImageError('edited_metadata_stale_rung_property')
            if any(rung_metadata.scope(ref.target) in current and
                    (app.native_routines.by_instance[rung_metadata.scope(ref.target)].program+'/'+
                     app.native_routines.by_instance[rung_metadata.scope(ref.target)].name).casefold() in edited for ref in row.references):
                raise ImageError('edited_metadata_rung_reference_unsupported')
        return self.data
