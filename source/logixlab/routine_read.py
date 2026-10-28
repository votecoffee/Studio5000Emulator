"""Session-owned readback of exact source retained by an installed download.

The source and opaque component selectors use retained download bytes. No source
is invented, no opaque code executes, and edits revoke the downloaded view.
An edited routine can instead expose its exact accepted source for selector3;
untouched routines use a validated source-only snapshot from installation.
The exact downloaded selector9 profile and empty selector4 view can remain
available after source-bound routine edits; neither supplies compiled code.
"""
from dataclasses import dataclass,field
import struct

from .download_headers import HeaderBindings
from .download_image import ImageError
from .download_routines import RoutineBindings
from . import read_transport as rt,upload_routine_source


def source(app,program,routine,selector=3):
    if type(selector) is not int or selector not in (3,4,9):raise ImageError('routine_read_selector_unsupported')
    engine=app.engine;project=engine.project;installed=getattr(engine,'installed_download',None)
    if installed is None:raise ImageError('routine_read_installed_download_required')
    installed.check(app.native_project_identity,project)
    if engine.mode!='project' or engine.blockers or engine.fault or engine.calls.stack or engine.memory.frames:
        raise ImageError('routine_read_unchanged_logic_required')
    if getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',()):
        if selector!=3:
            if installed.routine_sources is None:raise ImageError('routine_read_download_snapshot_required')
            return installed.routine_sources.profile(app,program,routine,selector)
        row=app.native_routines.by_instance.get((program,routine)) if app.native_routines is not None else None
        if row is not None and (row.program+'/'+row.name).casefold() not in getattr(project,'runtime_edited_routines',()):
            if installed.routine_sources is None:raise ImageError('routine_read_download_snapshot_required')
            return installed.routine_sources.read(app,program,routine)
        from . import accepted_routine_source
        try:return accepted_routine_source.read(app,program,routine)
        except accepted_routine_source.Error as error:raise ImageError(str(error)) from error
    ns=installed.namespace;batch=ns._routine_batch
    if batch is None:raise ImageError('routine_read_download_source_required')
    headers=HeaderBindings(engine,ns,app.native_symbols,app.native_routines,app.native_auxiliary_symbols,
        app.native_tasks,app.native_tables)
    bindings=RoutineBindings(headers,app.native_types)
    raw=batch.read(program,routine,'source',bindings)
    if raw[:8]!=struct.pack('<II',1,3):raise ImageError('routine_read_source_profile_changed')
    # Revalidate the retained TextIOI against the current interpreter routine.
    # Native upload requires TargetClass, which the download XML omits. Keep
    # the retained download unchanged and convert only the served source view.
    decoded=bindings.source((program,routine),raw[8:])
    if selector==3 and not decoded.rungs:return raw[8:]
    if selector in (3,4):
        row=headers._routine(program,routine)
        if (row.type_word!=0x7FF or row.source_key is None
                or project.programs[headers._program(program)]['class']!='Standard'):
            raise ImageError('routine_read_unprotected_standard_profile_required')
    if selector==3:
        try:return upload_routine_source.from_download(raw[8:],target_class='Standard')
        except upload_routine_source.Error as error:raise ImageError(str(error)) from error
    if selector==4:
        # All 708 Program/Routine reads in the successful v35 upload reference
        # return an empty stream for this selector. Its semantic name is not
        # established; do not substitute the downloaded compiled-code bytes.
        return b''
    incremental=ns._incremental
    if incremental is None:raise ImageError('routine_read_component_required')
    incremental.verify_effects(ns._image,ns._source,app.native_metadata_values,headers)
    return incremental.read_routine_data(program,routine,ns._image,ns._source,headers,app.native_metadata_values)


@dataclass
class Stream:
    engine:object=field(repr=False)
    installed:object=field(repr=False)
    generation:int
    program:int
    routine:int
    selector:int
    data:bytes=field(repr=False)
    position:int=0
    frames:int=0

    @classmethod
    def begin(cls,app,program,routine,selector=3):
        data=source(app,program,routine,selector)
        return cls(app.engine,app.engine.installed_download,app.generation,program,routine,selector,data)

    def reply(self,app,request,key,limit):
        if (app.engine is not self.engine or app.generation!=self.generation
                or getattr(app.engine,'installed_download',None) is not self.installed):
            raise ImageError('routine_read_model_changed')
        # Checking each chunk also revokes a stream if a catalog, source body or
        # native binding changes without an Engine replacement.
        if source(app,self.program,self.routine,self.selector)!=self.data:raise ImageError('routine_read_source_changed')
        if request.position!=self.position or (request.container_format==0x101)!=(self.position==0):
            raise ImageError('routine_read_position_mismatch')
        if self.frames>=rt.MAX_FRAMES:raise ImageError('routine_read_frame_limit')
        if type(limit) is not int or limit<=36:raise ImageError('routine_read_reply_budget')
        chunk=self.data[self.position:self.position+limit-36];end=self.position+len(chunk)
        encoded=rt.encode_response(request,chunk,key,
            total_bytes=len(self.data) if request.container_format==0x101 else None,final=end==len(self.data))
        self.position=end;self.frames+=1
        return encoded,end==len(self.data)
