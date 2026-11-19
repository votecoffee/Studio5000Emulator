"""Reopen and validate ladder drafts against a loaded source snapshot."""

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


def validate(project, draft):
    from .runtime import Engine

    rungs = reopen(project, draft)
    key = draft['routine'].lower()
    problems = []
    for rung in rungs:
        number = rung['number']
        if not rung['text'].strip():
            problems.append(f"Rung {number}: Empty or protected rung")
        for op in operations(rung['nodes']):
            problem = ladder_operand_problem(op, project.aois)
            if problem:
                problems.append(f'Rung {number}: {problem}')
    if problems:
        return {'valid': False, 'diagnostics': [f"{draft['routine']}: {message}" for message in problems]}
    # Keep the source bindings, tag definitions and other routines. Engine
    # plans against its own memory, clocks, labels and execution state.
    candidate = copy.copy(project)
    candidate.routines = dict(project.routines)
    candidate.routines[key] = replace(project.routines[key], rungs=rungs)
    preview = Engine(candidate, defer_prescan=True, include_routines=(key,))
    return {'valid': not preview.blockers, 'diagnostics': preview.blockers}
