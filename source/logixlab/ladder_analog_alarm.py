"""Level-only ladder ALMA for the v35 ControlLogix 5580 software model."""
from .ladder_alarm import MAX_DINT, STATUS_BITS as DIGITAL_STATUS_BITS, available, alarm_parameters, _command, _record
from .model import ModelError, coerce, literal
from .real_math import SOURCE_TYPES, real

TYPE = 'ALARM_ANALOG'
LOW_LEVELS = ('LL', 'L')
HIGH_LEVELS = ('H', 'HH')
LEVELS = LOW_LEVELS + HIGH_LEVELS
ROC_LEVELS = ('ROCPos', 'ROCNeg')
PROGRAM_ACKS = tuple(level + 'ProgAck' for level in LEVELS)
SHELF_REQUESTS = ('ProgUnshelveAll',) + tuple(
    level + suffix for level in LEVELS + ROC_LEVELS for suffix in ('OperShelve', 'OperUnshelve'))
ROC_ACKS = tuple(level + suffix for level in ROC_LEVELS for suffix in ('ProgAck', 'OperAck'))
OPERATOR = ('OperAckAll', 'OperDisable', 'OperEnable', 'OperSuppress', 'OperUnsuppress',
            'AlarmCountReset') + tuple(level + 'OperAck' for level in LEVELS) + SHELF_REQUESTS[1:]
PROGRAM = ('ProgAckAll', 'ProgDisable', 'ProgEnable', 'ProgSuppress', 'ProgUnsuppress')
INPUTS = dict(EnableIn=True, In=0.0, InFault=False, AckRequired=True,
              MinDurationPRE=0, Deadband=0.0, ROCPeriod=0.0,
              ROCPosLimit=0.0, ROCNegLimit=0.0, ROCPosSeverity=500, ROCNegSeverity=500,
              ShelveDuration=0, MaxShelveDuration=0)
INPUTS.update(dict.fromkeys(OPERATOR + PROGRAM + PROGRAM_ACKS + SHELF_REQUESTS + ROC_ACKS, False))
for level in LEVELS:
    INPUTS.update({level+'Enabled': True, level+'MinDurationEnable': True,
                   level+'Limit': 0.0, level+'Severity': 500})
OUTPUTS = dict(EnableOut=False, AnyInAlarmUnack=False, Suppressed=False, Disabled=False,
               Commissioned=True, MinDurationACC=0, Status=0, ROC=0.0)
for level in LEVELS + ROC_LEVELS:
    OUTPUTS.update({level+'InAlarm': False, level+'Acked': True, level+'InAlarmUnack': False,
                    level+'Shelved': False})
OUTPUTS.update(dict.fromkeys((level + 'AlarmCount' for level in LEVELS), 0))
FIELDS = {name: {bool: 'BOOL', int: 'DINT', float: 'REAL'}[type(value)]
          for name, value in (INPUTS | OUTPUTS).items()}
STATUS_BITS = DIGITAL_STATUS_BITS | {'alarmlimitsinv': 3, 'deadbandinv': 4}


def default():
    return INPUTS | OUTPUTS


def from_tag(element):
    return alarm_parameters(element, TYPE, 'AlarmAnalogParameters', INPUTS, FIELDS) | OUTPUTS


def _input(memory, ref, scope):
    try:
        value = literal(ref)
    except ValueError:
        if memory.resolve(ref, scope)[2] not in SOURCE_TYPES:
            raise ModelError('ALMA In requires scalar REAL, SINT, INT or DINT')
        value = memory.read(ref, scope)
    else:
        if type(value) is int:
            coerce(value, 'DINT')
    return real(value)


def validate(engine, op, scope):
    if not available(engine.project):
        raise ModelError('ALMA requires the v35 ControlLogix 5580 software profile')
    if len(op.args) != 5:
        raise ModelError('ALMA requires five ladder operands')
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        _record(memory, op.args[0], scope, dtype=TYPE, instruction='ALMA')
        _input(memory, op.args[1], scope)
        for ref in op.args[2:]:
            _command(memory, ref, scope, instruction='ALMA')
    finally:
        memory.structural = previous


def prescan(engine, op, scope):
    key, obj = _record(engine.memory, op.args[0], scope, dtype=TYPE, instruction='ALMA')
    obj.update({name: value for name, value in OUTPUTS.items() if not name.endswith('AlarmCount')})
    obj.update(dict.fromkeys(OPERATOR + ('ROCPosOperAck', 'ROCNegOperAck'), False))
    obj['EnableIn'] = False
    engine.last_timer.pop(('ALMA', key), None)


def _diagnostics(obj, enabled):
    limits = [obj[level+'Limit'] for level in LEVELS if level in enabled]
    invalid_limits = any(a >= b for a, b in zip(limits, limits[1:]))
    high = [obj[level+'Limit'] for level in HIGH_LEVELS if level in enabled]
    low = [obj[level+'Limit'] for level in LOW_LEVELS if level in enabled]
    band = obj['Deadband']
    invalid_band = band < 0 or bool(not invalid_limits and high and low and band > 0 and band >= min(high) - max(low))
    invalid_severity = any(not 1 <= obj[level+'Severity'] <= 1000 for level in enabled)
    status = 2 if obj['InFault'] else 0
    for invalid, bit in ((invalid_severity, 2), (invalid_limits, 3), (invalid_band, 4)):
        if invalid:
            status |= 1 | (1 << bit)
    return status, invalid_limits, 0.0 if invalid_band else band


def _direction(obj, levels, enabled, sample, band, since, now, preset, high):
    tripped = {}
    retained = {}
    for level in levels:
        limit = obj[level+'Limit']
        tripped[level] = level in enabled and (sample >= limit if high else sample <= limit)
        retained[level] = level in enabled and obj[level+'InAlarm'] and (
            sample >= limit - band if high else sample <= limit + band)
    if not any(tripped.values()) and not any(retained.values()):
        return dict.fromkeys(levels, False), None
    if since is None:
        since = now
    elapsed = now - since >= preset
    active = {level: retained[level] or
              (tripped[level] and (elapsed or not obj[level+'MinDurationEnable'])) for level in levels}
    return active, since


def execute(engine, op, power, scope):
    memory = engine.memory
    key, obj = _record(memory, op.args[0], scope, dtype=TYPE, instruction='ALMA')
    if not power:
        obj.update(EnableIn=False, EnableOut=False)
        return False

    if obj['ROCPeriod'] != 0.0 or any(obj[name] for name in ROC_ACKS + SHELF_REQUESTS):
        raise ModelError('ALMA rate-of-change and shelving remain unqualified')
    preset = obj['MinDurationPRE']
    if not 0 <= preset <= MAX_DINT:
        raise ModelError('ALMA MinDurationPRE must be a nonnegative DINT')
    sample = _input(memory, op.args[1], scope)
    ack_all, disable, enable = (_command(memory, ref, scope, instruction='ALMA') for ref in op.args[2:])
    disabled = (obj['Disabled'] or disable or obj['OperDisable']) and not (enable or obj['OperEnable'])
    was_suppressed = obj['Suppressed']
    suppressed = (was_suppressed or obj['ProgSuppress'] or obj['OperSuppress']) and not (
        obj['ProgUnsuppress'] or obj['OperUnsuppress'])
    enabled = {level for level in LEVELS if obj[level+'Enabled']}
    status, invalid_limits, band = _diagnostics(obj, enabled)
    detected = set() if disabled or invalid_limits else enabled

    identity = ('ALMA', key)
    low_since, high_since, old_ack_all, old_level_acks = engine.last_timer.get(
        identity, (None, None, False, frozenset()))
    low, low_since = _direction(obj, LOW_LEVELS, detected, sample, band, low_since, engine.time_ms, preset, False)
    high, high_since = _direction(obj, HIGH_LEVELS, detected, sample, band, high_since, engine.time_ms, preset, True)
    active = low | high

    global_ack = (ack_all and not old_ack_all) or obj['OperAckAll']
    level_acks = frozenset(level for level in LEVELS if obj[level+'ProgAck'])
    count_reset = obj['AlarmCountReset']
    any_unack = False
    for level, in_alarm in active.items():
        activated = in_alarm and not obj[level+'InAlarm']
        rearm = in_alarm and not suppressed and (activated or was_suppressed)
        ack_requested = global_ack or (level in level_acks and level not in old_level_acks) or obj[level+'OperAck']
        acked = (obj[level+'Acked'] and not rearm) or not obj['AckRequired'] or ack_requested
        unack = in_alarm and not acked
        any_unack |= unack
        count = 0 if count_reset else min(MAX_DINT, obj[level+'AlarmCount'] + int(activated))
        obj.update({level+'InAlarm': in_alarm, level+'Acked': acked, level+'InAlarmUnack': unack,
                    level+'AlarmCount': count})
    obj.update(dict.fromkeys(OPERATOR, False))
    obj.update(EnableIn=True, EnableOut=True, In=sample, ProgAckAll=ack_all,
               ProgDisable=disable, ProgEnable=enable, Suppressed=suppressed, Disabled=disabled,
               AnyInAlarmUnack=any_unack, MinDurationACC=0, Status=status)
    engine.last_timer[identity] = (low_since, high_since, ack_all, level_acks)
    return True


def description(project):
    return dict(available=available(project), instruction='ALMA', language='RLL', data_type=TYPE,
                levels=['LL', 'L', 'H', 'HH'], timing='Shared qualification time per direction; inclusive pickup and deadband release',
                remaining=['Rate-of-change, shelving, timestamps, ST and FBD', 'Native layout and alarm event services'],
                native_runtime_parity=False)
