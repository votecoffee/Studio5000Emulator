"""Load explicit ladder timer and counter PRE/ACC values into the initial image."""

import re

from .integer_math import CONTROLLERS
from .model import Memory, ModelError, coerce, operations
from .numeric_copy import static_reference


RECORD_TYPES = {'TON': 'TIMER', 'TOF': 'TIMER', 'RTO': 'TIMER',
                'CTU': 'COUNTER', 'CTD': 'COUNTER'}


def initialize_timer_counter_operands(project):
    if project.version != '35' or project.processor.upper() not in CONTROLLERS:
        return

    initializers = [
        (routine, rung, op)
        for routine in project.routines.values() if routine.kind == 'RLL'
        for rung in routine.rungs
        for op in operations(rung['nodes'])
        if op.name in RECORD_TYPES and len(op.args) == 3 and op.args[1:] != ['?', '?']
    ]
    if not initializers:
        return

    memory = Memory(project)
    writes = {}
    for routine, rung, op in initializers:
        reference, preset, accum = op.args
        try:
            program = project.programs[routine.program]
            if program['class'] != 'Standard' or program['use_as_folder']:
                raise ModelError('Explicit PRE/ACC requires a Standard program routine')
            if not static_reference(memory, reference, routine.program):
                raise ModelError('Explicit PRE/ACC requires a direct static backing tag')
            key, parts, dtype = memory.check_writable(reference, routine.program)
            if dtype != RECORD_TYPES[op.name] or not isinstance(memory.at(key, parts), dict):
                raise ModelError(f'{op.name} requires one writable {RECORD_TYPES[op.name]} record')
            for member, token in (('PRE', preset), ('ACC', accum)):
                if token == '?':
                    continue
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

    # Commit the initial values and compile these calls to ordinary PRE/ACC
    # member use together. Keep the original rung text for display and export.
    for (key, parts), value in writes.items():
        memory.store(key, parts, value)
    project.initial = memory.values
    for _, _, op in initializers:
        op.args[1:] = ['?', '?']
