"""Seed saved ladder backing members from explicit L5X pseudo-operands."""

import re

from .integer_math import CONTROLLERS
from .model import ARITIES, Memory, ModelError, coerce, operations
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


def literal_operands(project):
    for routine in project.routines.values():
        if routine.kind != 'RLL' or routine.problems:
            continue
        for rung in routine.rungs:
            for op in operations(rung['nodes']):
                if op.name not in LAYOUTS or len(op.args) != ARITIES[op.name]:
                    continue
                dtype, records = LAYOUTS[op.name]
                for reference, first, members in records:
                    fields = [(i, member) for i, member in enumerate(members, first) if op.args[i] != '?']
                    if fields:
                        yield routine, rung, op, dtype, op.args[reference], fields


def initialize_ladder_operands(project):
    if project.version != '35' or project.processor.upper() not in CONTROLLERS:
        return
    initializers = list(literal_operands(project))
    if not initializers:
        return

    memory = Memory(project)
    writes = {}
    for routine, rung, op, expected, reference, fields in initializers:
        try:
            program = project.programs[routine.program]
            if program['class'] != 'Standard' or program['use_as_folder']:
                raise ModelError('Explicit pseudo-operands require a Standard program routine')
            if not static_reference(memory, reference, routine.program, follow_aliases=True):
                raise ModelError('Explicit pseudo-operands require a static backing tag')
            key, parts, dtype = memory.check_writable(reference, routine.program)
            if dtype != expected or not isinstance(memory.at(key, parts), dict):
                raise ModelError(f'{op.name} requires one writable {expected} record per backing tag')
            for i, member in fields:
                token = op.args[i]
                if not re.fullmatch(r'[+-]?[0-9]+', token):
                    raise ModelError(f'{member} initializer requires a decimal DINT or ?')
                value = coerce(int(token), 'DINT')
                if dtype == 'TIMER' and value < 0:
                    raise ModelError(f'TIMER.{member} initializer must be nonnegative')
                target = (key, (*parts, member))
                if target in writes and writes[target] != value:
                    raise ModelError(f'Conflicting {member} initializers for {reference}')
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
        for i, _ in fields:
            op.args[i] = '?'
