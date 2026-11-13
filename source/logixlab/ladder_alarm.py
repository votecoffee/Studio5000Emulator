"""Logical digital alarms for the v35 5580 ladder runtime."""
from .integer_math import CONTROLLERS
from .model import ModelError, coerce, literal
from .wall_clock import current_value_microseconds


TYPE = 'ALARM_DIGITAL'
MAX_DINT = (1 << 31) - 1
MAX_LINT = (1 << 63) - 1
TIMESTAMPS = ('InAlarmTime', 'AckTime', 'RetToNormalTime', 'AlarmCountResetTime',
              'ShelveTime', 'UnshelveTime')
PROGRAM = ('ProgAck', 'ProgReset', 'ProgDisable', 'ProgEnable',
           'ProgSuppress', 'ProgUnsuppress', 'ProgUnshelve')
OPERATOR = ('OperAck', 'OperReset', 'OperDisable', 'OperEnable', 'AlarmCountReset',
            'OperSuppress', 'OperUnsuppress', 'OperShelve', 'OperUnshelve')
INPUTS = dict(
    EnableIn=True, In=False, InFault=False, Condition=True, AckRequired=True, Latched=False, UseProgTime=False,
    **dict.fromkeys(PROGRAM + OPERATOR, False),
    Severity=500, MinDurationPRE=0, ShelveDuration=0, MaxShelveDuration=0, ProgTime=0,
)
OUTPUTS = dict(EnableOut=False, InAlarm=False, Acked=True, InAlarmUnack=False,
               Suppressed=False, Shelved=False, Disabled=False, Commissioned=True,
               MinDurationACC=0, AlarmCount=0, Status=0, **dict.fromkeys(TIMESTAMPS, 0))
STATUS_BITS = {'instructfault': 0, 'infaulted': 1, 'severityinv': 2}
FIELDS = {name: 'BOOL' if type(value) is bool else 'DINT'
          for name, value in (INPUTS | OUTPUTS).items()}
FIELDS.update(dict.fromkeys(('ProgTime', *TIMESTAMPS), 'LINT'))


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def default():
    return INPUTS | OUTPUTS


def from_tag(element):
    return alarm_parameters(element, TYPE, 'AlarmDigitalParameters', INPUTS, FIELDS) | OUTPUTS


def alarm_parameters(element, dtype, parameter, inputs, fields):
    parameters = element.findall(f"./Data[@Format='Alarm']/{parameter}")
    if len(parameters) != 1 or len(parameters[0]):
        raise ModelError(f'{dtype} requires one {parameter} element in Alarm data')
    values = dict(inputs)
    for name, raw in parameters[0].attrib.items():
        if name not in inputs:
            raise ModelError(f'{dtype} parameter {name} is unsupported')
        value = literal(raw)
        field_type = fields[name]
        if field_type == 'BOOL' and (type(value) not in (bool, int) or value not in (0, 1)):
            raise ModelError(f'{dtype}.{name} requires a BOOL value')
        if field_type == 'REAL' and type(value) not in (int, float):
            raise ModelError(f'{dtype}.{name} requires a finite REAL value')
        if field_type in ('DINT', 'LINT') and type(value) is not int:
            raise ModelError(f'{dtype}.{name} requires an integer value')
        try:
            values[name] = coerce(value, field_type)
        except OverflowError as error:
            raise ModelError(f'{dtype}.{name} exceeds the finite {field_type} range') from error
    return values


def _record(memory, ref, scope, *, dtype=TYPE, instruction='ALMD'):
    key, parts, actual = memory.check_writable(ref, scope)
    if actual != dtype or parts:
        if scope in memory.frames:
            raise ModelError(f'{instruction} in an AOI requires an InOut parameter bound to a writable scalar {dtype} tag')
        raise ModelError(f'{instruction} requires a writable scalar {dtype} tag')
    return key, memory.at(key, parts)


def _command(memory, ref, scope, *, instruction='ALMD'):
    try:
        value = literal(ref)
    except ValueError:
        if memory.resolve(ref, scope)[2] != 'BOOL':
            raise ModelError(f'{instruction} commands require scalar BOOL tags or 0/1 immediates')
        value = memory.read(ref, scope)
        if type(value) is not bool:
            raise ModelError(f'{instruction} command requires a known scalar BOOL value')
        return value
    if type(value) not in (bool, int) or value not in (0, 1):
        raise ModelError(f'{instruction} commands require scalar BOOL tags or 0/1 immediates')
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
    if len(op.args) not in (5, 7):
        raise ModelError('ALMD requires five operands or a legacy preset and accumulator pair')
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        _record(memory, op.args[0], scope)
        for ref in op.args[1:5]:
            _command(memory, ref, scope)
        if len(op.args) == 7:
            _duration(op.args[5], MAX_DINT)
            _duration(op.args[6], 0)
    finally:
        memory.structural = previous


def prescan(engine, op, scope):
    key, obj = _record(engine.memory, op.args[0], scope)
    obj.update(dict.fromkeys(OPERATOR, False))
    obj.update(dict.fromkeys(TIMESTAMPS, 0))
    obj.update(EnableOut=False, InAlarm=False, InAlarmUnack=False, Acked=True,
               Shelved=False, MinDurationACC=0)
    engine.last_timer.pop(('ALMD', key), None)


def _shelf_deadline(now, deadline, *, minutes, cancel):
    if cancel:
        return None
    if minutes is not None:
        return now + minutes * 60_000
    return deadline if deadline is not None and now < deadline else None


def _event_time(obj, engine=None):
    stamp = obj['ProgTime'] if obj['UseProgTime'] else (engine.wall_time(current_value_microseconds) if engine is not None else current_value_microseconds())
    if type(stamp) is not int or not 0 <= stamp <= MAX_LINT:
        raise ModelError('ALMD requires a nonnegative LINT UTC timestamp from ProgTime or WallClockTime')
    return stamp


def execute(engine, op, power, scope):
    memory = engine.memory
    key, obj = _record(memory, op.args[0], scope)
    severity_invalid = not 1 <= obj['Severity'] <= 1000
    status = (0b101 if severity_invalid else 0) | (0b010 if obj['InFault'] else 0)
    ack, reset, disable, enable = (_command(memory, ref, scope) for ref in op.args[1:5])
    preset = _duration(op.args[5], MAX_DINT) if len(op.args) == 7 else None
    if preset is None:
        preset = obj['MinDurationPRE']
    if not 0 <= preset <= MAX_DINT:
        raise ModelError('ALMD MinDurationPRE must be a nonnegative DINT')

    identity = ('ALMD', key)
    since, old_ack, old_reset, shelf_until, old_shelve, detected_at = engine.last_timer.get(
        identity, (None, False, False, None, False, None))
    now = engine.time_ms
    shelve_request = obj['OperShelve']
    was_shelved = shelf_until is not None
    unshelve_requested = obj['ProgUnshelve'] or obj['OperUnshelve']
    shelf_started = shelve_request and not old_shelve and not unshelve_requested
    minutes = obj['ShelveDuration'] if shelf_started else None
    if minutes is not None and not 1 <= minutes <= obj['MaxShelveDuration']:
        raise ModelError('ALMD shelve duration must be 1..MaxShelveDuration minutes')
    shelf_until = _shelf_deadline(now, shelf_until, minutes=minutes, cancel=unshelve_requested)
    shelved = shelf_until is not None
    ack_requested = (ack and not old_ack) or obj['OperAck']
    reset_requested = (reset and not old_reset) or obj['OperReset']
    disabled = (obj['Disabled'] or disable or obj['OperDisable']) and not (enable or obj['OperEnable'])
    was_suppressed = obj['Suppressed']
    unsuppress = obj['ProgUnsuppress'] or obj['OperUnsuppress']
    suppressed = (was_suppressed or obj['ProgSuppress'] or obj['OperSuppress']) and not unsuppress
    abnormal = power == obj['Condition']
    if disabled or not abnormal:
        since = None
        detected_at = None
    elif since is None:
        since = now

    old_active = obj['InAlarm']
    detecting = since is not None and not old_active and detected_at is None
    latched_reset = old_active and obj['Latched'] and not abnormal and reset_requested
    if disabled:
        active = False
    elif old_active:
        active = abnormal or (obj['Latched'] and not latched_reset)
    else:
        active = since is not None and now - since >= preset

    activated = active and not old_active
    rearm_ack = active and not (suppressed or shelved) and (activated or was_suppressed or was_shelved)
    acked = (obj['Acked'] and not rearm_ack) or not obj['AckRequired'] or ack_requested or latched_reset
    count_reset = obj['AlarmCountReset']
    count = 0 if count_reset else min(MAX_DINT, obj['AlarmCount'] + int(activated))

    auto_ack = activated and not obj['AckRequired']
    acknowledged = acked and (not obj['Acked'] or (rearm_ack and ack_requested))
    events = [('AckTime', acknowledged and not auto_ack),
              ('RetToNormalTime', old_active and not active),
              ('AlarmCountResetTime', count_reset),
              ('ShelveTime', shelf_started),
              ('UnshelveTime', was_shelved and unshelve_requested)]
    changed = [field for field, reached in events if reached]
    timestamps = {}
    if detecting or changed:
        stamp = _event_time(obj, engine)
        timestamps = dict.fromkeys(changed, stamp)
        if detecting:
            detected_at = stamp
        if shelf_started:
            timestamps['UnshelveTime'] = coerce(stamp + (shelf_until - now) * 1000, 'LINT')
    if activated:
        timestamps['InAlarmTime'] = detected_at
        if auto_ack:
            timestamps['AckTime'] = detected_at

    obj.update(timestamps)
    obj.update(dict.fromkeys(OPERATOR, False))
    obj.update(EnableIn=power, EnableOut=power, In=power,
               ProgAck=ack, ProgReset=reset, ProgDisable=disable, ProgEnable=enable,
               MinDurationPRE=preset, MinDurationACC=0, Disabled=disabled, Suppressed=suppressed,
               Shelved=shelved, InAlarm=active, Acked=acked, InAlarmUnack=active and not acked,
               AlarmCount=count, Status=status)
    engine.last_timer[identity] = (since, ack, reset, shelf_until, shelve_request, detected_at)
    return power


def description(project):
    return dict(available=available(project), instruction='ALMD', language='RLL', data_type=TYPE,
                source='Scalar Alarm-format ALARM_DIGITAL tags, including program scope and aliases',
                timing='First abnormal sample starts the minimum duration; later releases use modeled milliseconds',
                state='Polarity, enable/disable, suppression, shelving, latch/reset, acknowledgment and count',
                diagnostics='Status.0 InstructFault and Status.2 SeverityInv indicate invalid severity. Status.1 InFaulted indicates bad input quality. Alarm evaluation continues.',
                suppression='Suppress retains detection, delay and count. Unsuppress wins and rearms acknowledgment for an active, unshelved alarm.',
                shelving='A sampled rising edge shelves or reshelves for configured minutes. Unshelve wins. Expiration uses modeled time.',
                timestamps='UTC microseconds as LINT. Reached events use WallClockTime or ProgTime; InAlarmTime retains initial detection.',
                false_rung_executes=True, native_runtime_parity=False,
                aoi='Ladder AOIs with an exact scalar ALARM_DIGITAL InOut binding',
                remaining=['Native packed layouts and alarm event services', 'ASO, ST and FBD'])
