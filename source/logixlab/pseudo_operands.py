"""Seed saved ladder backing members from explicit L5X pseudo-operands."""

from collections import defaultdict, deque
import re

from .integer_math import CONTROLLERS, bit_value
from .model import ARITIES, Memory, ModelError, coerce, literal, operations, parse_rung
from .numeric_copy import static_reference


PRE_ACC = ('PRE', 'ACC')
LEN_POS = ('LEN', 'POS')
# Each record specifies its reference index, first pseudo-operand index and fields.
LAYOUTS = {
    **dict.fromkeys(('TON', 'TOF', 'RTO'), ('TIMER', ((0, 1, PRE_ACC),))),
    **dict.fromkeys(('CTU', 'CTD'), ('COUNTER', ((0, 1, PRE_ACC),))),
    **dict.fromkeys(('BSL', 'BSR'), ('CONTROL', ((1, 3, ('LEN',)),))),
    **dict.fromkeys(('FFL', 'FFU', 'LFL', 'LFU', 'SQL', 'SRT'), ('CONTROL', ((2, 3, LEN_POS),))),
    **dict.fromkeys(('SQI', 'SQO', 'AVE', 'STD'), ('CONTROL', ((3, 4, LEN_POS),))),
    **dict.fromkeys(('FAL', 'FSC'), ('CONTROL', ((0, 1, LEN_POS),))),
    **dict.fromkeys(('FBC', 'DDT'), ('CONTROL', ((3, 4, LEN_POS), (6, 7, LEN_POS)))),
}


def _literal_operands(rungs):
    for rung in rungs:
        for op in operations(rung['nodes']):
            if op.name not in LAYOUTS or len(op.args) != ARITIES[op.name]:
                continue
            dtype, records = LAYOUTS[op.name]
            for reference, first, members in records:
                fields = [(i, member) for i, member in enumerate(members, first) if op.args[i] != '?']
                if fields:
                    yield rung, op, dtype, op.args[reference], fields


def _initializer_value(token, member):
    if re.fullmatch(r'[+-]?[0-9]+', token):
        return coerce(int(token), 'DINT')
    if re.fullmatch(r'(?:2|8|16)#[0-9A-Fa-f]+(?:[ _]+[0-9A-Fa-f]+)*', token):
        try:
            value = literal(token.replace(' ', ''))
        except ValueError as error:
            raise ModelError(f'{member} radix initializer has invalid digits') from error
        if value < 1 << 32:
            return bit_value(value, 'DINT')
    raise ModelError(f'{member} initializer requires a decimal DINT, 32-bit radix pattern or ?')


def _supported(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def _backing_values(memory, routine, op, expected, reference, fields):
    program = memory.project.programs[routine.program]
    if program['class'] != 'Standard' or program['use_as_folder']:
        raise ModelError('Explicit pseudo-operands require a Standard program routine')
    if not static_reference(memory, reference, routine.program, follow_aliases=True):
        raise ModelError('Explicit pseudo-operands require a static backing tag')
    key, parts, dtype = memory.check_writable(reference, routine.program)
    if dtype != expected or not isinstance(memory.at(key, parts), dict):
        raise ModelError(f'{op.name} requires one writable {expected} record per backing tag')
    for i, member in fields:
        value = _initializer_value(op.args[i], member)
        if dtype == 'TIMER' and value < 0:
            raise ModelError(f'TIMER.{member} initializer must be nonnegative')
        yield key, (*parts, member), value


def _compile_fields(op, fields):
    if op.source_args is None:
        op.source_args = op.args.copy()
    for i, _ in fields:
        op.args[i] = '?'


def initialize_ladder_operands(project):
    if not _supported(project):
        return
    initializers = [(routine, *entry) for routine in project.routines.values()
                    if routine.kind == 'RLL' and not routine.problems for entry in _literal_operands(routine.rungs)]
    if not initializers:
        return

    memory = Memory(project)
    writes = {}
    for routine, rung, op, expected, reference, fields in initializers:
        try:
            for key, parts, value in _backing_values(memory, routine, op, expected, reference, fields):
                target = (key, parts)
                if target in writes and writes[target] != value:
                    raise ModelError(f'Conflicting {parts[-1]} initializers for {reference}')
                writes[target] = value
        except (ModelError, ValueError) as error:
            routine.problems.append(f'Rung {rung["number"]}: {error}')
            return

    # Commit seed values and compile the calls to ordinary member use together.
    # The original rung text is retained for display and export.
    for (key, parts), value in writes.items():
        memory.store(key, parts, value)
    project.initial = memory.values
    for _, _, op, _, _, fields in initializers:
        _compile_fields(op, fields)


def compile_draft_operands(project, routine, rungs):
    """Compile explicit settings that agree with the saved destination storage."""
    if not _supported(project):
        return []
    initializers = list(_literal_operands(rungs))
    if not initializers:
        return []
    saved = Memory(project)
    problems = []
    for rung, op, expected, reference, fields in initializers:
        try:
            for key, parts, value in _backing_values(saved, routine, op, expected, reference, fields):
                if saved.at(key, parts) != value:
                    raise ModelError(f'{op.name} would change imported tag initial values for {reference}.{parts[-1]}')
        except (ModelError, ValueError) as error:
            problems.append(f'Rung {rung["number"]}: {error}')
    if not problems:
        for _, op, _, _, fields in initializers:
            _compile_fields(op, fields)
    return problems


def retain_ladder_operands(previous_rungs, candidate_rungs):
    """Carry existing compiled pseudo-operands into edited surrounding logic."""
    retained = defaultdict(deque)
    for rung in previous_rungs:
        compiled = list(operations(rung['nodes']))
        if not any(op.name in LAYOUTS for op in compiled):
            continue
        authored = operations(parse_rung(rung['text']))
        for original, op in zip(authored, compiled, strict=True):
            if original.name in LAYOUTS and original.args != op.args:
                retained[original.name, tuple(original.args)].append(op.args)
    if not retained:
        return
    for rung in candidate_rungs:
        for op in operations(rung['nodes']):
            matches = retained.get((op.name, tuple(op.args)))
            if matches:
                op.source_args = op.args.copy()
                op.args = list(matches.popleft())
