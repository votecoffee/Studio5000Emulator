"""Prepare ladder drafts against a loaded source snapshot."""

import copy
from dataclasses import replace

from .model import ModelError, ascii_literal_end, ladder_operand_problem, operations, parse_rung


FIELDS = {'format', 'version', 'routine', 'source_sha256', 'base_revision', 'rungs'}
RUNG_FIELDS = {'number', 'comment', 'text'}
LAYOUT_FIELDS = {'base_index', 'comment', 'text'}


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


def _read(project, draft):
    if (type(draft) is not dict or set(draft) - {'base_logic_sha256'} != FIELDS
            or draft['format'] != 'logixlab-rll-draft'
            or type(draft['version']) is not int or draft['version'] not in (1, 2)):
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
    if type(rows) is not list or not rows or len(set(numbers)) != len(numbers):
        raise ModelError('Draft rung numbers must match the loaded routine in order')
    if draft['version'] == 1 and len(rows) != len(numbers):
        raise ModelError('Draft rung numbers must match the loaded routine in order')

    base_indices = []
    last_retained = -1
    for index, row in enumerate(rows):
        if draft['version'] == 1:
            if type(row) is not dict or set(row) != RUNG_FIELDS or any(type(value) is not str for value in row.values()):
                raise ModelError('Each draft rung must contain number, comment and text strings')
            if row['number'] != numbers[index]:
                raise ModelError('Draft rung numbers must match the loaded routine in order')
            base_indices.append(index)
        else:
            if (type(row) is not dict or set(row) != LAYOUT_FIELDS
                    or type(row['text']) is not str or type(row['comment']) is not str):
                raise ModelError('Each draft rung must contain a base index, comment and text')
            base_index = row['base_index']
            if base_index is not None:
                if type(base_index) is not int or not last_retained < base_index < len(numbers):
                    raise ModelError('Retained draft rungs must refer to unique base indices in order')
                last_retained = base_index
            base_indices.append(base_index)

    layout_changed = base_indices != list(range(len(numbers)))
    restored = []
    for index, (row, base_index) in enumerate(zip(rows, base_indices, strict=True)):
        base = routine.rungs[base_index] if base_index is not None else None
        number = str(index) if layout_changed else numbers[index]
        nodes = base['nodes'] if base is not None and row['text'] == base['text'] else _draft_nodes(row['text'], number)
        restored.append({'number': number, 'text': row['text'], 'comment': row['comment'], 'nodes': nodes})
    return routine, restored, base_indices, layout_changed


def reopen(project, draft):
    _, restored, base_indices, _ = _read(project, draft)
    if draft['version'] == 2:
        return [{**row, 'base_index': index} for row, index in zip(restored, base_indices, strict=True)]
    return restored


def _candidate_project(project, draft):
    from .pseudo_operands import retain_ladder_operands

    routine, rungs, base_indices, layout_changed = _read(project, draft)
    key = routine.key.lower()
    changed = [row for row, index in zip(rungs, base_indices, strict=True)
               if index is None or row['text'] != routine.rungs[index]['text']]
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
        return None, key, base_indices, layout_changed, diagnostics
    # Keep the source bindings, tag definitions and other routines. Engine
    # plans against its own memory, clocks, labels and execution state.
    candidate = copy.copy(project)
    candidate.routines = dict(project.routines)
    candidate.routines[key] = replace(routine, rungs=rungs)
    return candidate, key, base_indices, layout_changed, []


def validate(project, draft):
    from .runtime import Engine

    candidate, key, _, _, diagnostics = _candidate_project(project, draft)
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
    project, key, base_indices, layout_changed, diagnostics = _candidate_project(engine.project, draft)
    if diagnostics:
        raise ModelError(diagnostics[0])
    previous = engine.project
    if not layout_changed and project.routines[key].rungs == previous.routines[key].rungs:
        raise ModelError('The draft has no changes to apply')
    if key not in engine.active:
        preview = Engine(project, defer_prescan=True, include_routines=(key,))
        if preview.blockers:
            raise ModelError(preview.blockers[0])
    candidate = replacement_engine(engine, project)
    candidate.trace = [row for row in candidate.trace if row.get('routine', '').lower() != key]
    candidate.immediate_outputs = copy.deepcopy(engine.immediate_outputs)
    candidate.memory.message_cache = copy.deepcopy(engine.memory.message_cache)
    previous_origins = getattr(previous, 'runtime_rung_origins', {}).get(key)
    if previous_origins is None:
        count = len(previous.routines[key].rungs)
        previous_origins = ((None,) * count if key in getattr(previous, 'runtime_edited_routines', ())
                            else tuple(range(count)))
    origins = tuple(previous_origins[index] if index is not None else None for index in base_indices)
    record_revision(previous, project, key, draft['base_revision'], rung_origins=origins)
    project.runtime_native_sources = retain(previous, project, key, None, None, None)
    candidate.change_detection.record('routine_transaction')
    verify_working_copy(candidate)
    return candidate
