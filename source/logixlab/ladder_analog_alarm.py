"""Ladder ALMA for the v35 ControlLogix 5580 software model."""
from typing import NamedTuple

from .ladder_alarm import MAX_DINT, STATUS_BITS as DIGITAL_STATUS_BITS, available, alarm_parameters, _command, _record
from .model import ModelError, coerce, literal
from .real_math import SOURCE_TYPES, real

TYPE = 'ALARM_ANALOG'
LOW_LEVELS = ('LL', 'L')
HIGH_LEVELS = ('H', 'HH')
LEVELS = LOW_LEVELS + HIGH_LEVELS
ROC_LEVELS = ('ROCPos', 'ROCNeg')
CONDITIONS = LEVELS + ROC_LEVELS
PROGRAM_ACKS = tuple(level + 'ProgAck' for level in CONDITIONS)
SHELF_REQUESTS = ('ProgUnshelveAll',) + tuple(
    level + suffix for level in CONDITIONS for suffix in ('OperShelve', 'OperUnshelve'))
OPERATOR = ('OperAckAll', 'OperDisable', 'OperEnable', 'OperSuppress', 'OperUnsuppress',
            'AlarmCountReset') + tuple(level + 'OperAck' for level in CONDITIONS) + SHELF_REQUESTS[1:]
PROGRAM = ('ProgAckAll', 'ProgDisable', 'ProgEnable', 'ProgSuppress', 'ProgUnsuppress')
COUNT_FIELDS = {level: level+'AlarmCount' for level in LEVELS} | {
    'ROCPos': 'ROCPosInAlarmCount', 'ROCNeg': 'ROCNegAlarmCount'}
INPUTS = dict(EnableIn=True, In=0.0, InFault=False, AckRequired=True,
              MinDurationPRE=0, Deadband=0.0, ROCPeriod=0.0,
              ROCPosLimit=0.0, ROCNegLimit=0.0, ROCPosSeverity=500, ROCNegSeverity=500,
              ShelveDuration=0, MaxShelveDuration=0)
INPUTS.update(dict.fromkeys(OPERATOR + PROGRAM + PROGRAM_ACKS + SHELF_REQUESTS, False))
for level in LEVELS:
    INPUTS.update({level+'Enabled': True, level+'MinDurationEnable': True,
                   level+'Limit': 0.0, level+'Severity': 500})
OUTPUTS = dict(EnableOut=False, AnyInAlarmUnack=False, Suppressed=False, Disabled=False,
               Commissioned=True, MinDurationACC=0, Status=0, ROC=0.0)
for level in CONDITIONS:
    OUTPUTS.update({level+'InAlarm': False, level+'Acked': True, level+'InAlarmUnack': False,
                    level+'Shelved': False})
OUTPUTS.update(dict.fromkeys(COUNT_FIELDS.values(), 0))
FIELDS = {name: {bool: 'BOOL', int: 'DINT', float: 'REAL'}[type(value)]
          for name, value in (INPUTS | OUTPUTS).items()}
STATUS_BITS = DIGITAL_STATUS_BITS | {'alarmlimitsinv': 3, 'deadbandinv': 4,
                                    'rocposlimitinv': 5, 'rocneglimitinv': 6,
                                    'rocperiodinv': 7, 'overflow': 8}


class RocSample(NamedTuple):
    period: float
    time_ms: int
    value: float
    rate: float | None


class AlarmHistory(NamedTuple):
    low_since: int | None = None
    high_since: int | None = None
    ack_all: bool = False
    level_acks: frozenset[str] = frozenset()
    roc: RocSample | None = None


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
    obj.update({name: value for name, value in OUTPUTS.items() if name not in COUNT_FIELDS.values()})
    obj.update(dict.fromkeys(OPERATOR, False))
    obj['EnableIn'] = False
    engine.last_timer.pop(('ALMA', key), None)


def _diagnostics(obj, enabled, roc_enabled):
    limits = [obj[level+'Limit'] for level in LEVELS if level in enabled]
    invalid_limits = any(a >= b for a, b in zip(limits, limits[1:]))
    high = [obj[level+'Limit'] for level in HIGH_LEVELS if level in enabled]
    low = [obj[level+'Limit'] for level in LOW_LEVELS if level in enabled]
    band = obj['Deadband']
    invalid_band = band < 0 or bool(not invalid_limits and high and low and band > 0 and band >= min(high) - max(low))
    invalid_severity = any(not 1 <= obj[level+'Severity'] <= 1000 for level in enabled | roc_enabled)
    status = 2 if obj['InFault'] else 0
    for invalid, bit in ((invalid_severity, 2), (invalid_limits, 3), (invalid_band, 4),
                         (obj['ROCPosLimit'] < 0, 5), (obj['ROCNegLimit'] < 0, 6),
                         (not 0 <= obj['ROCPeriod'] <= 32767, 7)):
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


def _sample_roc(previous, period, sample, now):
    if not period:
        return None
    if previous is None or previous.period != period:
        return RocSample(period, now, sample, 0.0)
    # Compare seconds in REAL so a configured 0.1 s expires at 100 ms.
    if coerce((now - previous.time_ms) / 1000, 'REAL') < period:
        return previous
    try:
        rate = coerce((sample - previous.value) / period, 'REAL')
    except (OverflowError, ModelError):
        rate = None
    return RocSample(period, now, sample, rate)


def execute(engine, op, power, scope):
    memory = engine.memory
    key, obj = _record(memory, op.args[0], scope, dtype=TYPE, instruction='ALMA')
    identity = ('ALMA', key)
    history = engine.last_timer.get(identity, AlarmHistory())
    if not power:
        obj.update(EnableIn=False, EnableOut=False)
        if history.roc is not None:
            engine.last_timer[identity] = history._replace(roc=None)
        return False

    if any(obj[name] for name in SHELF_REQUESTS):
        raise ModelError('ALMA shelving remains unqualified')
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
    period = obj['ROCPeriod'] if 0 < obj['ROCPeriod'] <= 32767 else 0.0
    roc_enabled = {level for level in ROC_LEVELS if period and obj[level+'Limit'] > 0}
    status, invalid_limits, band = _diagnostics(obj, enabled, roc_enabled)
    detected = set() if disabled or invalid_limits else enabled

    now = engine.time_ms
    low, low_since = _direction(obj, LOW_LEVELS, detected, sample, band, history.low_since, now, preset, False)
    high, high_since = _direction(obj, HIGH_LEVELS, detected, sample, band, history.high_since, now, preset, True)
    roc = _sample_roc(history.roc, 0.0 if disabled else period, sample, now)
    rate = roc.rate if roc is not None else 0.0
    if rate is None:
        status |= (1 << STATUS_BITS['overflow']) | 1
        rate = 0.0
    active = low | high | {
        'ROCPos': 'ROCPos' in roc_enabled and rate >= obj['ROCPosLimit'],
        'ROCNeg': 'ROCNeg' in roc_enabled and rate <= -obj['ROCNegLimit'],
    }

    global_ack = (ack_all and not history.ack_all) or obj['OperAckAll']
    level_acks = frozenset(level for level in CONDITIONS if obj[level+'ProgAck'])
    count_reset = obj['AlarmCountReset']
    any_unack = False
    for level, in_alarm in active.items():
        activated = in_alarm and not obj[level+'InAlarm']
        rearm = in_alarm and not suppressed and (activated or was_suppressed)
        ack_requested = global_ack or (level in level_acks and level not in history.level_acks) or obj[level+'OperAck']
        acked = (obj[level+'Acked'] and not rearm) or not obj['AckRequired'] or ack_requested
        unack = in_alarm and not acked
        any_unack |= unack
        count_field = COUNT_FIELDS[level]
        count = 0 if count_reset else min(MAX_DINT, obj[count_field] + int(activated))
        obj.update({level+'InAlarm': in_alarm, level+'Acked': acked, level+'InAlarmUnack': unack,
                    count_field: count})
    obj.update(dict.fromkeys(OPERATOR, False))
    obj.update(EnableIn=True, EnableOut=True, In=sample, ProgAckAll=ack_all,
               ProgDisable=disable, ProgEnable=enable, Suppressed=suppressed, Disabled=disabled,
               AnyInAlarmUnack=any_unack, MinDurationACC=0, ROC=rate, Status=status)
    engine.last_timer[identity] = AlarmHistory(low_since, high_since, ack_all, level_acks, roc)
    return True


def description(project):
    return dict(available=available(project), instruction='ALMA', language='RLL', data_type=TYPE,
                levels=['LL', 'L', 'H', 'HH'], timing='Shared qualification time per direction; inclusive pickup and deadband release',
                rate_of_change='Sampled positive and negative conditions using the configured period',
                remaining=['Shelving, timestamps, ST and FBD', 'Native layout and alarm event services'],
                native_runtime_parity=False)
