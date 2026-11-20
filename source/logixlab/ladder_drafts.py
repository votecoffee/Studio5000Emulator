"""Prepare ladder drafts against a loaded source snapshot."""

import copy
from dataclasses import replace

from .model import ModelError, ascii_literal_end, ladder_operand_problem, operations, parse_rung


FIELDS = {'format', 'version', 'routine', 'source_sha256', 'base_revision', 'rungs'}
RUNG_FIELDS = {'number', 'comment', 'text'}


def _check_operand(ref):
    # Rung parsing separates operands. Check delimiter nesting within each
    # operand without requiring that a draft already has executable values.
    endings = {'(': ')', '[': ']'}
    pending = []
    index = 0
    while index < len(ref):
        char = ref[index]
        if char == "'":
            index = ascii_literal_end(ref, index)
            continue
        if char in endings:
            pending.append(endings[char])
        elif char in ')]':
            if not pending or pending.pop() != char:
                raise ModelError('Unbalanced operand delimiters')
        elif char == ';' or (char == ',' and not pending):
            raise ModelError('Unexpected operand separator')
        index += 1
    if pending:
        raise ModelError('Unbalanced operand delimiters')


def _draft_nodes(text, number):
    try:
        nodes = parse_rung(text)
        for instruction in operations(nodes):
            for ref in instruction.args:
                _check_operand(ref)
    except RecursionError as error:
        raise ModelError(f'Rung {number}: Branch nesting is too deep') from error
    except ModelError as error:
        raise ModelError(f'Rung {number}: {error}') from error
    return nodes


def reopen(project, draft):
    if (type(draft) is not dict or set(draft) - {'base_logic_sha256'} != FIELDS
            or draft['format'] != 'logixlab-rll-draft'
            or type(draft['version']) is not int or draft['version'] != 1):
        raise ModelError('Unsupported ladder draft file format')
    if draft['source_sha256'] != project.sha256:
        raise ModelError('This draft belongs to a different project source')
    revision = getattr(project, 'runtime_revision', 0)
    digest = getattr(project, 'runtime_logic_sha256', None)
    if (type(draft['base_revision']) is not int or draft['base_revision'] != revision
            or draft.get('base_logic_sha256') != digest):
        raise ModelError('This draft requires the matching base logic revision')
    key = draft['routine']
    routine = project.routines.get(key.lower()) if isinstance(key, str) else None
    if (routine is None or routine.key != key or routine.kind != 'RLL'
            or routine.problems or not routine.rungs):
        raise ModelError('The draft routine is unavailable or read-only')
    numbers = [row['number'] for row in routine.rungs]
    rows = draft['rungs']
    if (type(rows) is not list or len(rows) != len(numbers) or len(set(numbers)) != len(numbers)):
        raise ModelError('Draft rung numbers must match the loaded routine in order')

    restored = []
    for row, base in zip(rows, routine.rungs):
        if type(row) is not dict or set(row) != RUNG_FIELDS or any(type(value) is not str for value in row.values()):
            raise ModelError('Each draft rung must contain number, comment and text strings')
        if row['number'] != base['number']:
            raise ModelError('Draft rung numbers must match the loaded routine in order')
        nodes = base['nodes'] if row['text'] == base['text'] else _draft_nodes(row['text'], row['number'])
        restored.append({**row, 'nodes': nodes})
    return restored


def _candidate_project(project, draft):
    from .pseudo_operands import retain_ladder_operands

    rungs = reopen(project, draft)
    key = draft['routine'].lower()
    routine = project.routines[key]
    changed = [row for row, original in zip(rungs, routine.rungs) if row['text'] != original['text']]
    retain_ladder_operands(routine.rungs, changed)
    problems = []
    for rung in rungs:
        number = rung['number']
        if not rung['text'].strip():
            problems.append(f"Rung {number}: Empty or protected rung")
        for op in operations(rung['nodes']):
            problem = ladder_operand_problem(op, project.aois)
            if problem:
                problems.append(f'Rung {number}: {problem}')
    diagnostics = [f"{draft['routine']}: {message}" for message in problems]
    if diagnostics:
        return None, key, diagnostics
    # Keep the source bindings, tag definitions and other routines. Engine
    # plans against its own memory, clocks, labels and execution state.
    candidate = copy.copy(project)
    candidate.routines = dict(project.routines)
    candidate.routines[key] = replace(routine, rungs=rungs)
    return candidate, key, []


def validate(project, draft):
    from .runtime import Engine

    candidate, key, diagnostics = _candidate_project(project, draft)
    if candidate is not None:
        preview = Engine(candidate, defer_prescan=True, include_routines=(key,))
        diagnostics = preview.blockers
    return {'valid': not diagnostics, 'diagnostics': diagnostics}


def apply_available(engine):
    return bool(engine and engine.mode == 'project' and not engine.project.aois
                and engine.project.executable_configuration.source_complete
                and not getattr(engine, 'installed_download', None))


def prepare_apply(engine, draft):
    from .accepted_routine_source import retain
    from .logic_export import verify_working_copy
    from .routine_edits import record_revision, replacement_engine
    from .runtime import Engine

    if not apply_available(engine):
        raise ModelError('Apply draft requires a complete ordinary project in whole-project mode')
    if engine.fault or engine.module_major_fault or engine.calls.stack or engine.memory.frames:
        raise ModelError('Apply draft requires a Program-mode project without a fault or active call')
    project, key, diagnostics = _candidate_project(engine.project, draft)
    if diagnostics:
        raise ModelError(diagnostics[0])
    if project.routines[key].rungs == engine.project.routines[key].rungs:
        raise ModelError('The draft has no changes to apply')
    if key not in engine.active:
        preview = Engine(project, defer_prescan=True, include_routines=(key,))
        if preview.blockers:
            raise ModelError(preview.blockers[0])
    candidate = replacement_engine(engine, project)
    candidate.trace = [row for row in candidate.trace if row.get('routine', '').lower() != key]
    candidate.immediate_outputs = copy.deepcopy(engine.immediate_outputs)
    candidate.memory.message_cache = copy.deepcopy(engine.memory.message_cache)
    record_revision(engine.project, project, key, draft['base_revision'], offline=True)
    project.runtime_native_sources = retain(engine.project, project, key, None, None, None)
    candidate.change_detection.record('routine_transaction')
    verify_working_copy(candidate)
    return candidate
