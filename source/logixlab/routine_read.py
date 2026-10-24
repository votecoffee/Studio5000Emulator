"""Session-owned readback of exact source retained by an installed download.

The source and opaque component selectors use retained download bytes. No source
is invented, no opaque code executes, and edits revoke the downloaded view.
"""
from dataclasses import dataclass,field
import struct

from .download_headers import HeaderBindings
from .download_image import ImageError
from .download_routines import RoutineBindings
from . import read_transport as rt


def source(app,program,routine,selector=3):
    if type(selector) is not int or selector not in (3,9):raise ImageError('routine_read_selector_unsupported')
    engine=app.engine;project=engine.project;installed=getattr(engine,'installed_download',None)
    if installed is None:raise ImageError('routine_read_installed_download_required')
    installed.check(app.native_project_identity,project)
    if (engine.mode!='project' or engine.blockers or engine.fault or engine.calls.stack or engine.memory.frames
            or getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',())):
        raise ImageError('routine_read_unchanged_logic_required')
    ns=installed.namespace;batch=ns._routine_batch
    if batch is None:raise ImageError('routine_read_download_source_required')
    headers=HeaderBindings(engine,ns,app.native_symbols,app.native_routines,app.native_auxiliary_symbols,
        app.native_tasks,app.native_tables)
    bindings=RoutineBindings(headers,app.native_types)
    raw=batch.read(program,routine,'source',bindings)
    if raw[:8]!=struct.pack('<II',1,3):raise ImageError('routine_read_source_profile_changed')
    # Revalidate the retained TextIOI against the current interpreter routine.
    # These are the caller's exact native source bytes, without its write prefix.
    bindings.source((program,routine),raw[8:])
    if selector==3:return raw[8:]
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
