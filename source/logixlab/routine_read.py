"""Session-owned readback of exact source retained by an installed download.

Only the observed Routine source selector is implemented. No source is invented,
no opaque code executes, and edits revoke the original downloaded source view.
"""
from dataclasses import dataclass,field
import struct

from .download_headers import HeaderBindings
from .download_image import ImageError
from .download_routines import RoutineBindings
from . import read_transport as rt


def source(app,program,routine):
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
    return raw[8:]


@dataclass
class Stream:
    engine:object=field(repr=False)
    installed:object=field(repr=False)
    generation:int
    program:int
    routine:int
    data:bytes=field(repr=False)
    position:int=0
    frames:int=0

    @classmethod
    def begin(cls,app,program,routine):
        data=source(app,program,routine)
        return cls(app.engine,app.engine.installed_download,app.generation,program,routine,data)

    def reply(self,app,request,key,limit):
        if (app.engine is not self.engine or app.generation!=self.generation
                or getattr(app.engine,'installed_download',None) is not self.installed):
            raise ImageError('routine_read_model_changed')
        # Checking each chunk also revokes a stream if a catalog, source body or
        # native binding changes without an Engine replacement.
        if source(app,self.program,self.routine)!=self.data:raise ImageError('routine_read_source_changed')
        if request.position!=self.position or (request.container_format==0x101)!=(self.position==0):
            raise ImageError('routine_read_position_mismatch')
        if self.frames>=rt.MAX_FRAMES:raise ImageError('routine_read_frame_limit')
        if type(limit) is not int or limit<=36:raise ImageError('routine_read_reply_budget')
        chunk=self.data[self.position:self.position+limit-36];end=self.position+len(chunk)
        encoded=rt.encode_response(request,chunk,key,
            total_bytes=len(self.data) if request.container_format==0x101 else None,final=end==len(self.data))
        self.position=end;self.frames+=1
        return encoded,end==len(self.data)
