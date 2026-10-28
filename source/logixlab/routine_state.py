"""Absent native edit buffers and non-SFC state for guarded ordinary RLL."""


def current_source(app,engine,program,routine,target):
    """Prove current source through the live view used by signed reads."""
    if (app is None or app.engine is not engine or not isinstance(program,str) or not isinstance(routine,str)
            or type(target) is not tuple or len(target)!=2
            or any(type(value) is not int for value in target)):
        return False
    catalog=app.native_routines
    row=catalog.by_instance.get(target) if catalog is not None else None
    if row is None or (row.program.casefold(),row.name.casefold())!=(program.casefold(),routine.casefold()):return False
    from . import routine_read
    from .download_image import ImageError
    try:routine_read.source(app,*target)
    except ImageError:return False
    return True


def source_key(app,program,routine):
    """Keep the original Source Key through verified plain-logic replacement.

    Caller must first establish idle state/current source with attributes().
    This additionally pins the unchanged configuration to installation catalogs.
    """
    engine=app.engine;project=engine.project;catalog=app.native_routines
    row=catalog.by_instance.get((program,routine)) if catalog is not None else None
    if row is None:return None
    if not (getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',())):return row.source_key
    installed=getattr(engine,'installed_download',None)
    if installed is None or installed.routine_sources is None:return None
    from .download_image import ImageError
    try:
        installed.check(app.native_project_identity,project)
        return installed.routine_sources.source_key(app,program,routine)
    except ImageError:return None


def attributes(engine,program,routine,*,source_sha256,idle,type_bound,app=None,native_target=None):
    project=engine.project
    if (type_bound is not True or source_sha256!=project.sha256 or engine.mode!='project' or
            engine.blockers or engine.fault or engine._native_fault_history_uncertain or
            engine.calls.stack or engine.memory.frames or
            not project.program_configuration.type_attributes(program,source_sha256=source_sha256) or
            not project.program_diagnostics.edit_attributes(program,source_sha256=source_sha256,idle=idle)):
        return {}
    if not isinstance(routine,str):return {}
    target=project.routines.get((program+'/'+routine).casefold())
    if target is None or target.kind!='RLL':return {}
    revision=getattr(project,'runtime_revision',0);edited=getattr(project,'runtime_edited_routines',())
    if revision or edited:
        if (type(revision) is not int or revision<1 or type(edited) is not tuple or not edited
                or any(key not in project.routines for key in edited)
                or not current_source(app,engine,program,routine,native_target)):
            return {}
    # Native Code Address is null: this interpreter has no native machine-code
    # entry point. The other addresses/sizes are absent edit buffers, not the
    # active RLL body. Native Test/Untest/Assemble is not implied.
    return {2:bytes(4),**{number:bytes(4) for number in range(10,22)},23:b'\0',26:b'\0',27:b'\0',
        **engine.runtime_references.routine_attributes(project,program,routine),
        **project.program_diagnostics.signature_attributes(program,source_sha256=source_sha256)}


def description():
    return dict(attributes=[2,8,*range(10,22),23,24,26,27,28],scope='Source-bound ordinary Program RLL routines',
        source='Complete unprotected untested RLL source and actual clean idle simulator state',
        native_edits_idle_required=True,unmodified_logic_required=False,validated_type_profile_required=True,
        edited_model_source_readback_required=True,
        fault_history_required_clean=True,aoi_state=False,null_code_address=True,active_code_addresses=False,
        uid=False,header_address='Live interpreter Routine reference; shared with Program main reference',
        source_keys='Pinned original opaque configuration; plain RLL edits preserve it; no decryption',executable_flags='Main=0; other ordinary RLL=2',
        signature_types='Unsigned canonical ordinary RLL only; no native signature verification',
        test_untest_assemble=False,configuration_writes=False)
