"""Logical digital alarms for the v35 5580 ladder runtime."""
from .integer_math import CONTROLLERS
from .model import ModelError, coerce, literal


TYPE = 'ALARM_DIGITAL'
MAX_DINT = (1 << 31) - 1
PROGRAM = ('ProgAck', 'ProgReset', 'ProgDisable', 'ProgEnable')
OPERATOR = ('OperAck', 'OperReset', 'OperDisable', 'OperEnable', 'AlarmCountReset',
            'OperSuppress', 'OperUnsuppress', 'OperShelve', 'OperUnshelve')
UNSUPPORTED_COMMANDS = ('ProgSuppress', 'ProgUnsuppress', 'ProgUnshelve',
                        'OperSuppress', 'OperUnsuppress', 'OperShelve', 'OperUnshelve',
                        'UseProgTime')
INPUTS = dict(
    EnableIn=True, In=False, InFault=False, Condition=True, AckRequired=True, Latched=False,
    **dict.fromkeys(PROGRAM + OPERATOR + UNSUPPORTED_COMMANDS, False),
    Severity=500, MinDurationPRE=0, ShelveDuration=0, MaxShelveDuration=0, ProgTime=0,
)
OUTPUTS = dict(EnableOut=False, InAlarm=False, Acked=True, InAlarmUnack=False,
               Suppressed=False, Shelved=False, Disabled=False, Commissioned=True,
               MinDurationACC=0, AlarmCount=0, Status=0)
STATUS_BITS = {'infaulted': 1}
FIELDS = {name: 'BOOL' if type(value) is bool else 'DINT'
          for name, value in (INPUTS | OUTPUTS).items()}
FIELDS['ProgTime'] = 'LINT'


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def default():
    return INPUTS | OUTPUTS


def from_tag(element):
    parameters = element.findall("./Data[@Format='Alarm']/AlarmDigitalParameters")
    if len(parameters) != 1 or len(parameters[0]):
        raise ModelError('ALARM_DIGITAL requires one AlarmDigitalParameters element in Alarm data')
    values = default()
    for name, raw in parameters[0].attrib.items():
        if name not in INPUTS:
            raise ModelError(f'ALARM_DIGITAL parameter {name} is unsupported')
        value = literal(raw)
        dtype = FIELDS[name]
        if dtype == 'BOOL' and (type(value) not in (bool, int) or value not in (0, 1)):
            raise ModelError(f'ALARM_DIGITAL.{name} requires a BOOL value')
        if dtype != 'BOOL' and type(value) is not int:
            raise ModelError(f'ALARM_DIGITAL.{name} requires an integer value')
        values[name] = coerce(value, dtype)
    return values


def _record(memory, ref, scope):
    if scope in memory.frames:
        raise ModelError('ALMD inside an AOI remains unqualified')
    key, parts, dtype = memory.check_writable(ref, scope)
    if dtype != TYPE or parts:
        raise ModelError('ALMD requires a writable scalar ALARM_DIGITAL tag')
    return key, memory.at(key, parts)


def _command(memory, ref, scope):
    try:
        value = literal(ref)
    except ValueError:
        if memory.resolve(ref, scope)[2] != 'BOOL':
            raise ModelError('ALMD commands require scalar BOOL tags or 0/1 immediates')
        value = memory.read(ref, scope)
        if type(value) is not bool:
            raise ModelError('ALMD command requires a known scalar BOOL value')
        return value
    if type(value) not in (bool, int) or value not in (0, 1):
        raise ModelError('ALMD commands require scalar BOOL tags or 0/1 immediates')
    return bool(value)


def _duration(ref, maximum):
    if ref == '?':
        return None
    try:
        value = literal(ref)
    except ValueError:
        value = None
    if type(value) is not int or not 0 <= value <= maximum:
        raise ModelError('ALMD duration requires a nonnegative DINT preset and a zero accumulator')
    return value


def validate(engine, op, scope):
    if not available(engine.project):
        raise ModelError('ALMD requires the v35 ControlLogix 5580 software profile')
    if len(op.args) != 7:
        raise ModelError('ALMD requires seven ladder operands')
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        _record(memory, op.args[0], scope)
        for ref in op.args[1:5]:
            _command(memory, ref, scope)
        _duration(op.args[5], MAX_DINT)
        _duration(op.args[6], 0)
    finally:
        memory.structural = previous


def prescan(engine, op, scope):
    key, obj = _record(engine.memory, op.args[0], scope)
    obj.update(dict.fromkeys(OPERATOR, False))
    obj.update(EnableOut=False, InAlarm=False, InAlarmUnack=False, Acked=True,
               Shelved=False, MinDurationACC=0)
    engine.last_timer.pop(('ALMD', key), None)


def execute(engine, op, power, scope):
    memory = engine.memory
    key, obj = _record(memory, op.args[0], scope)
    if any(obj[name] for name in UNSUPPORTED_COMMANDS):
        raise ModelError('ALMD suppress, shelve and program timestamps remain unqualified')
    if not 1 <= obj['Severity'] <= 1000:
        raise ModelError('ALMD severity must be 1..1000 in the software profile')
    ack, reset, disable, enable = (_command(memory, ref, scope) for ref in op.args[1:5])
    preset = _duration(op.args[5], MAX_DINT)
    if preset is None:
        preset = obj['MinDurationPRE']
    if not 0 <= preset <= MAX_DINT:
        raise ModelError('ALMD MinDurationPRE must be a nonnegative DINT')

    identity = ('ALMD', key)
    since, old_ack, old_reset = engine.last_timer.get(identity, (None, False, False))
    ack_requested = (ack and not old_ack) or obj['OperAck']
    reset_requested = (reset and not old_reset) or obj['OperReset']
    disabled = (obj['Disabled'] or disable or obj['OperDisable']) and not (enable or obj['OperEnable'])
    abnormal = power == obj['Condition']
    if disabled or not abnormal:
        since = None
    elif since is None:
        since = engine.time_ms

    old_active = obj['InAlarm']
    latched_reset = old_active and obj['Latched'] and not abnormal and reset_requested
    if disabled:
        active = False
    elif old_active:
        active = abnormal or (obj['Latched'] and not latched_reset)
    else:
        active = since is not None and engine.time_ms - since >= preset

    activated = active and not old_active
    acked = (obj['Acked'] and not activated) or not obj['AckRequired'] or ack_requested or latched_reset
    count = 0 if obj['AlarmCountReset'] else min(MAX_DINT, obj['AlarmCount'] + int(activated))
    obj.update(dict.fromkeys(OPERATOR, False))
    obj.update(EnableIn=power, EnableOut=power, In=power,
               ProgAck=ack, ProgReset=reset, ProgDisable=disable, ProgEnable=enable,
               MinDurationPRE=preset, MinDurationACC=0, Disabled=disabled,
               InAlarm=active, Acked=acked, InAlarmUnack=active and not acked,
               AlarmCount=count, Status=2 if obj['InFault'] else 0)
    engine.last_timer[identity] = (since, ack, reset)
    return power


def description(project):
    return dict(available=available(project), instruction='ALMD', language='RLL', data_type=TYPE,
                source='Scalar Alarm-format ALARM_DIGITAL tags, including program scope and aliases',
                timing='First abnormal sample starts the minimum duration; later releases use modeled milliseconds',
                state='Polarity, enable/disable, latch/reset, acknowledgment, count and InFaulted',
                false_rung_executes=True, native_runtime_parity=False,
                remaining=['Suppression, shelving and timestamps', 'Native packed layouts and alarm event services',
                           'ALMA, ASO, ST, FBD and AOI alarm execution'])
