"""DINT ladder DTR, including reference updates on false scans and prescan."""
from .bit_transfer import operand, unsigned
from .integer_math import CONTROLLERS, bit_value
from .model import ModelError


def validate(memory, op, scope):
    if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('DTR requires the v35 ControlLogix 5580 software profile')
    for index, ref in enumerate(op.args):
        if operand(memory, ref, scope, destination=index == 2) != 32:
            raise ModelError('DTR requires DINT scalar source, mask and writable reference')


def execute(memory, op, power, scope):
    validate(memory, op, scope)
    source, mask, reference = op.args
    # Read all required values before writing, including aliased operands.
    masked = unsigned(memory, source, scope, 32) & unsigned(memory, mask, scope, 32)
    changed = power and masked != unsigned(memory, reference, scope, 32)
    if not power or changed:
        memory.write(reference, bit_value(masked, 'DINT'), scope)
    return bool(changed)


def description():
    return dict(profile='v35-5580-DTR', language='RLL', instructions=['DTR'],
                operands='DINT source/mask tags or bounded immediates; writable DINT scalar reference',
                comparison='Masked source compared against the complete prior reference',
                true_scan='Changed comparison energizes rung-out and replaces reference with masked source',
                false_scan='Replace reference with masked source; rung-out remains false',
                prescan='Replace reference with masked source, including lexically prescanned routines',
                unknowns='Required unknown source/mask/reference reads fault; false/prescan can establish reference',
                native_runtime_parity=False,
                remaining=['Other controller profiles', 'Complete native operand, status and fault parity'])
