"""Private final Local Map header flag, separate from active I/O state."""
import hashlib
import struct
from .download_image import ImageError
from .download_properties import controller_profile
from .download_routines import RoutineBindings


class MapBindings:
    def __init__(self,headers,types,metadata,identity,setup):
        self.headers=headers;self.types=types;self.metadata=metadata;self.identity=identity;self.setup=setup

    def _routine_stamp(self):
        h=self.headers;ns=h.namespace;project=h.engine.project
        bindings=RoutineBindings(h,self.types)
        if ns._routine_batch is not None:
            ns._routine_batch.verify_effects(bindings)
            return 'received',id(ns._routine_batch),ns._routine_batch.record_sha256
        # Studio omits the source/code batch for an empty routine inventory.
        # Require independently complete source, original identities and image;
        # an absent batch never substitutes for existing or unreadable logic.
        config=project.executable_configuration;source=ns._source.l5x_sha256
        if (project.routines or ns._image.routines or h.routines is None or h.routines.rows
                or not config.source_complete or config.unavailable_programs
                or {name.casefold() for name in config.program_names}!={name.casefold() for name in project.programs}
                or any(config.routine_names(name,source_sha256=source)!=()
                       or not project.program_diagnostics.is_empty(name,source_sha256=source)
                       or not project.program_diagnostics.has_no_main(name,source_sha256=source)
                       for name in project.programs)):
            raise ImageError('download_map_completed_routines_required')
        return 'empty_source',bindings.stamp()

    def stamp(self):
        h=self.headers;ns=h.namespace;project=h.engine.project;source=ns._source
        profile=controller_profile(project,source)
        if ns._incremental is None:
            raise ImageError('download_map_completed_routines_required')
        ns.setup.require_complete(self.setup)
        values=h.engine.runtime_references.io_map_attributes(project,self.identity)
        if 2 not in values or 13 not in values:raise ImageError('download_map_local_identity_required')
        ns._incremental.verify_effects(ns._image,source,self.metadata,h)
        routine_stamp=self._routine_stamp()
        previous=ns._incremental.read_attribute(0x69,0,1,7,ns._image,source,self.metadata,h)
        if previous!=b'\5\0':raise ImageError('download_map_prepared_header_required')
        return hashlib.sha256(repr((profile,h.stamp(ns._image,source),values[2],values[13],
            id(ns._incremental),ns._incremental.record_sha256,routine_stamp)).encode()).hexdigest()


class DownloadMap:
    def __init__(self):self._value=None;self._binding=None;self._digest=None

    def _effect(self):return hashlib.sha256(repr((self._value,self._binding)).encode()).hexdigest()

    def validate(self,bindings):
        if self._value is None:
            if self._binding is not None or self._digest is not None:raise ImageError('download_map_effect_changed')
            return
        if bindings is None or bindings.stamp()!=self._binding:raise ImageError('download_map_binding_changed')
        if self._value!=b'\1\0' or self._effect()!=self._digest:raise ImageError('download_map_effect_changed')

    def configure(self,payload,bindings):
        self.validate(bindings);stamp=bindings.stamp()
        if type(payload) is not bytes or payload!=struct.pack('<HHH',1,7,1):raise ImageError('download_map_flag_profile')
        proposal=DownloadMap();proposal._value=payload[4:];proposal._binding=stamp;proposal._digest=proposal._effect()
        proposal.validate(bindings)
        self._value,self._binding,self._digest=proposal._value,proposal._binding,proposal._digest
        return struct.pack('<HHH',1,7,0)

    def read(self,bindings):
        self.validate(bindings)
        if self._value is None:raise ImageError('download_map_flag_unavailable')
        return self._value

    def description(self):
        return dict(configured=self._value is not None,attributes=int(self._value is not None),owner_only=True,
            private_header_only=True,flag_bits_interpreted=False,active_io_changed=False,
            active_project_changed=False,compiled_code_executed=False,commit=False,payloads_exposed=False)
