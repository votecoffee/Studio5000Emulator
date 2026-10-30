"""Atomic Program-mode RLL replacement in the custom execution model.

The original file hash remains the catalog binding. A separate runtime revision
and digest identify edited logic. No native ELF executes and no ACD is written.
"""
import copy
import hashlib
import json
from collections import Counter
from .model import ModelError,operations
from .routine_source import candidate_project,validate_plan,SourceError
from .runtime import Engine


def prepare(engine,source,neutral,program,base_revision,*,native_source=None,native_target=None,native_metadata=None):
    if (engine.mode!='project' or engine.blockers or engine.fault or engine.project.aois
            or engine.calls.stack or engine.memory.frames):
        raise ModelError('Routine replacement requires an executable ordinary project')
    if type(base_revision) is not int or base_revision!=getattr(engine.project,'runtime_revision',0):
        raise ModelError('Active logic changed during edit preparation')
    try:
        validate_plan(source,neutral,engine.project,program)
        project,key=candidate_project(source,neutral,engine.project,program)
    except SourceError as error:raise ModelError(str(error)) from error
    if project.routines[key].kind!='RLL':raise ModelError('Only RLL routine replacement is supported')
    # Everything below is detached. Constructor/planning/preview cannot mutate
    # active values, history, scan ownership or external-input queues.
    candidate=Engine(project,engine.mode,engine.selected,defer_prescan=True)
    if candidate.blockers:raise ModelError('Candidate routine execution is blocked')
    candidate.memory.values=copy.deepcopy(engine.memory.values)
    candidate.memory.first_scan=engine.memory.first_scan
    for name in ('scan_count','time_ms','last_timer','trace','changes','prescan_count',
                 '_initial_prescan_pending','_program_scanned','_file_incremental','_st_counter_edges','instruction_limit','budget','_program_timings','_task_measurements','_native_fault_history_uncertain'):
        setattr(candidate,name,copy.deepcopy(getattr(engine,name)))
    if candidate._task_scheduler is not None:
        candidate._task_scheduler.continue_from(engine._task_scheduler)
    candidate.change_detection=copy.deepcopy(engine.change_detection)
    candidate._apply_prescan(preview=True)
    project.instruction_counts=Counter(op.name for r in project.routines.values() for rung in r.rungs for op in operations(rung['nodes']))
    project.runtime_revision=base_revision+1
    project.runtime_edited_routines=tuple(sorted(set(getattr(engine.project,'runtime_edited_routines',()))|{key}))
    content=[(key,r.kind,[x['text'] for x in r.rungs]) for key,r in sorted(project.routines.items())]
    project.runtime_logic_sha256=hashlib.sha256(json.dumps(content,separators=(',',':')).encode()).hexdigest()
    from .accepted_routine_source import retain
    try:project.runtime_native_sources=retain(engine.project,project,key,source,native_source,native_target)
    except SourceError as error:raise ModelError(str(error)) from error
    installed=getattr(engine,'installed_download',None)
    if installed is not None:
        from .download_image import ImageError
        try:candidate.installed_download=installed.after_routine_edit(engine.project,project,
            native_source=native_source,native_target=native_target,native_metadata=native_metadata,key=key)
        except ImageError as error:raise ModelError(str(error)) from error
    return candidate,{'applied':True,'revision':project.runtime_revision,'logic_sha256':project.runtime_logic_sha256,
                      'rung_count':len(neutral),'native_code_executed':False,'file_written':False}


def description(app):
    from .accepted_routine_source import description as source_description
    project=app.engine.project if app.engine else None
    revision=getattr(project,'runtime_revision',0)
    return {'enabled':app.allow_routine_edits,'profile':'standard_rll_program_mode',
            'revision':revision,'modified':revision>0,'logic_sha256':getattr(project,'runtime_logic_sha256',None),
            'edited_routines':list(getattr(project,'runtime_edited_routines',())),
            'l5x_export_available':revision>0,
            'native_source_readback':source_description(project),
            'persistence':'memory_only','test_untest_assemble':False,'native_code_execution':False}
