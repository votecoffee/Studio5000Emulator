"""Atomic installation of the narrow source-equivalent download profile.

The interpreter executes the validated source, never opaque native machine code.
Original ACD catalogs stay immutable; committed correlation belongs to this Engine.
"""
import copy
from dataclasses import dataclass,replace

from .download_image import ImageError
from .download_values import PreparedValues
from .download_properties import CommittedProperties


@dataclass(frozen=True)
class InstalledDownload:
    original:object
    project:object
    namespace:object
    identity:object
    header:tuple
    values:PreparedValues
    metadata:object
    routine_sources:object=None

    def check(self,original,project):
        if (original is not self.original or project is not self.project
                or project.sha256!=self.original.source_l5x_sha256):
            raise ImageError('installed_download_source_changed')

    def attributes(self,original,project):
        self.check(original,project)
        return dict(self.header)

    def metadata_body(self,original,project,catalog,selection):
        self.check(original,project)
        if self.metadata is None:raise ImageError('installed_metadata_unavailable')
        return self.metadata.body(catalog,selection)

    def after_routine_edit(self,previous,project):
        """Keep committed correlation through a validated detached logic edit.

        The original transfer remains a historical snapshot. This only binds
        its controller header to the new interpreter Project; it does not make
        the staged native code or original Routine metadata current again.
        """
        self.check(self.original,previous)
        if (project is previous or project.sha256!=previous.sha256
                or project.tags is not previous.tags or project.initial is not previous.initial
                or project.programs is not previous.programs or project.tasks is not previous.tasks
                or getattr(project,'runtime_revision',0)!=getattr(previous,'runtime_revision',0)+1):
            raise ImageError('installed_download_edit_source_changed')
        return replace(self,project=project)

    def description(self):
        revision=getattr(self.project,'runtime_revision',0)
        return dict(installed=True,source_equivalent=revision==0,routine_revision=revision,tags=len(self.values.values),
            auxiliary_tables=len(self.values.auxiliary),original_catalogs_preserved=True,
            runtime_correlation=True,saved_values_installed=True,prescan_deferred=True,
            committed_metadata=self.metadata is not None,
            retained_source_routines=0 if self.routine_sources is None else len(self.routine_sources.sources),
            added_controller_properties=0 if self.metadata is None else self.metadata.additions,
            audit_epoch_replaced=True,compiled_code_executed=False,persistent=False,
            payloads_exposed=False)


def prepare(app,changelog_bindings,native_types):
    """All work is detached. Caller serializes with app.lock and endpoint.lock."""
    headers=changelog_bindings.map.headers;ns=headers.namespace;old=app.engine
    if (headers.engine is not old or app.busy or app.running or old.mode!='project'
            or app.controller_state()['mode']!='Program'):
        raise ImageError('download_installation_program_mode_required')
    ns.change_log.require_configured(changelog_bindings)
    values=PreparedValues.prepare(headers,native_types)
    candidate=values.new_engine(headers,native_types)
    header=ns.change_log.read(changelog_bindings);original=changelog_bindings.identity
    # This source-equivalent replacement preserves backed project-object handles
    # through the owner's remaining status/read/cleanup exchanges. The registry
    # containers are independent; later allocations cannot change the old Engine.
    candidate.runtime_references=copy.copy(old.runtime_references)
    candidate.runtime_references._addresses=dict(old.runtime_references._addresses)
    candidate.runtime_references._objects=dict(old.runtime_references._objects)
    try:candidate.change_detection.prepare_download_epoch(old.change_detection)
    except ValueError:raise ImageError('download_installation_audit_source_changed') from None
    runtime=replace(original,download_uid=int.from_bytes(header[3],'little'))
    metadata=CommittedProperties.prepare(ns.properties,ns._source,changelog_bindings.map.metadata,old.project)
    from .download_source_snapshot import Snapshot
    sources=Snapshot.prepare(headers,native_types)
    installed=InstalledDownload(original,old.project,ns,runtime,tuple(sorted(header.items())),values,metadata,sources)
    candidate.installed_download=installed
    values.validate(headers,native_types);ns.change_log.require_configured(changelog_bindings)
    if app.engine is not old:raise ImageError('download_installation_engine_changed')
    return candidate,installed
