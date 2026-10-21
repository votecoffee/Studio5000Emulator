"""Absent native edit buffers and non-SFC state for guarded ordinary RLL."""


def attributes(engine,program,routine,*,source_sha256,idle,type_bound):
    project=engine.project
    if (type_bound is not True or source_sha256!=project.sha256 or engine.mode!='project' or
            engine.blockers or engine.fault or engine._native_fault_history_uncertain or
            engine.calls.stack or engine.memory.frames or
            getattr(project,'runtime_revision',0)!=0 or getattr(project,'runtime_edited_routines',()) or
            not project.program_configuration.type_attributes(program,source_sha256=source_sha256) or
            not project.program_diagnostics.edit_attributes(program,source_sha256=source_sha256,idle=idle)):
        return {}
    if not isinstance(routine,str):return {}
    target=project.routines.get((program+'/'+routine).casefold())
    if target is None or target.kind!='RLL':return {}
    # Native Code Address is null: this interpreter has no native machine-code
    # entry point. The other addresses/sizes are absent edit buffers, not the
    # active RLL body. Native Test/Untest/Assemble is not implied.
    return {2:bytes(4),**{number:bytes(4) for number in range(10,22)},23:b'\0',26:b'\0',27:b'\0'}


def description():
    return dict(attributes=[2,*range(10,22),23,26,27],scope='Source-bound ordinary Program RLL routines',
        source='Complete unprotected untested RLL source and actual clean idle simulator state',
        native_edits_idle_required=True,unmodified_logic_required=True,validated_type_profile_required=True,
        fault_history_required_clean=True,aoi_state=False,null_code_address=True,active_code_addresses=False,
        uid=False,source_keys=False,executable_flags=False,signature_types=False,
        test_untest_assemble=False,configuration_writes=False)
