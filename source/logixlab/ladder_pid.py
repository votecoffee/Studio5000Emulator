"""Bounded ladder PID solver; native coefficients, filtering and layout unqualified."""
from .integer_math import CONTROLLERS, bit_value
from .model import ModelError, coerce, literal
from .real_math import real

INSTRUCTIONS = frozenset(('PID',))
REAL_FIELDS = ('SP KP KI KD BIAS MAXS MINS DB SO MAXO MINO UPD PV ERR OUT PVH PVL '
               'DVP DVN PVDB DVDB MAXI MINI TIE MAXCV MINCV MINTIE MAXTIE').split()
FIELDS = {'CTL': 'DINT', **dict.fromkeys(REAL_FIELDS, 'REAL'), 'DATA': 'REAL'}
BITS = dict(EN=31, CT=30, CL=29, PVT=28, DOE=27, SWM=26, CA=25, MO=24,
            PE=23, NDF=22, NOBC=21, NOZC=20, INI=15, SPOR=14, OLL=13,
            OLH=12, EWD=11, DVNA=10, DVPA=9, PVLA=8, PVHA=7)
ALIASES = {name.lower(): bit for name, bit in BITS.items()}
NUMERIC_TYPES = frozenset(('SINT', 'INT', 'DINT', 'REAL'))


def default():
    """Schema shape only; importing missing data still produces unknown values."""
    return {'CTL': 0, **dict.fromkeys(REAL_FIELDS, 0.0), 'DATA': [0.0] * 17}


def source(memory, ref, scope, *, immediate=False, role='PV'):
    try:
        value = literal(ref)
    except ValueError:
        key, parts, dtype = memory.resolve(ref, scope)
        if dtype not in NUMERIC_TYPES or isinstance(memory.at(key, parts), (list, dict)):
            raise ModelError('PID sources require scalar SINT/INT/DINT/REAL operands')
        return key, parts
    if not immediate or type(value) not in (int, float):
        raise ModelError('PID ' + role + ' requires a numeric tag' + (' or numeric immediate' if immediate else ''))
    coerce(value, 'DINT') if type(value) is int else real(value)
    return None


def validate(engine, op, scope):
    memory = engine.memory
    if engine.project.version != '35' or engine.project.processor.upper() not in CONTROLLERS:
        raise ModelError('PID requires the v35 ControlLogix 5580 software profile')
    if scope in memory.frames:
        raise ModelError('PID inside AOIs remains unqualified')
    if 'pid' in engine.project.udts:
        raise ModelError('Redefined PID records remain unqualified')
    if len(op.args) != 7 or op.args[4] != '0':
        raise ModelError('PID requires seven operands with literal 0 master operand')
    key, parts, dtype = memory.check_writable(op.args[0], scope)
    obj = memory.at(key, parts)
    if dtype != 'PID' or not isinstance(obj, dict) or set(obj) != set(FIELDS):
        raise ModelError('PID requires a writable logical PID record')
    if not isinstance(obj['DATA'], list) or len(obj['DATA']) != 17:
        raise ModelError('PID requires a seventeen-element REAL DATA array')
    pv = source(memory, op.args[1], scope)
    tieback = source(memory, op.args[2], scope, immediate=True, role='tieback')
    inhold_bit = None
    if op.args[5] != '0':
        hkey, hparts, htype = memory.resolve(op.args[5], scope)
        bit_view = hparts and isinstance(hparts[-1], tuple) and hparts[-1][0] == 'bit'
        if htype != 'BOOL' or hkey is None or not bit_view and isinstance(memory.at(hkey, hparts), (dict, list)):
            raise ModelError('PID inhold bit requires a scalar BOOL tag or literal 0')
        inhold_bit = hkey, hparts
    inhold_value = None if op.args[6] == '0' else source(memory, op.args[6], scope, role='inhold value')
    ckey, cparts, ctype = memory.check_writable(op.args[3], scope)
    if ctype not in NUMERIC_TYPES or isinstance(memory.at(ckey, cparts), (list, dict)):
        raise ModelError('PID control variable must be a writable scalar SINT/INT/DINT/REAL tag')
    for location in (pv, (ckey, cparts), tieback, inhold_bit, inhold_value):
        if location is not None and location[0] == key and location[1][:len(parts)] == parts:
            raise ModelError('PID process/control/tieback/inhold operands cannot overlap its record')
    return key, parts, obj, ctype


def prescan(engine, op, scope):
    # An unknown word cannot safely establish the preserved configuration bits.
    validate(engine, op, scope)
    engine.memory.write(op.args[0] + '.EN', False, scope)


def execute(engine, op, power, scope):
    key, parts, obj, cvtype = validate(engine, op, scope)
    if not power:
        engine.memory.write(op.args[0] + '.EN', False, scope)
        return False
    ctl = obj['CTL']
    if type(ctl) is not int:
        raise ModelError('PID CTL is unknown or has the wrong value type')
    flags = lambda name: bool(ctl & (1 << BITS[name]))
    def read(name):
        value = obj[name]
        if type(value) not in (int, float):
            raise ModelError('PID ' + name + ' is unknown or has the wrong value type')
        return real(value)
    if any(flags(name) for name in ('CT', 'CL')):
        raise ModelError('PID cascade remains unqualified')
    inhold = False if op.args[5] == '0' else engine.memory.read(op.args[5], scope)
    if type(inhold) is not bool:
        raise ModelError('PID inhold bit must have a known BOOL value')
    hardware_manual = flags('MO') and not inhold
    manual = (hardware_manual or flags('SWM')) and not inhold
    tracking = manual or inhold
    pv_tracking = flags('PVT') and manual
    v = {name: read(name) for name in ('KP', 'KI', 'KD', 'BIAS', 'MAXS', 'MINS',
         'DB', 'MAXO', 'MINO', 'UPD', 'MAXI', 'MINI', 'MAXCV', 'MINCV', 'PVH', 'PVL',
         'DVP', 'DVN', 'PVDB', 'DVDB')}
    if v['KD'] > 0 and not flags('NDF'):
        raise ModelError('PID derivative smoothing remains unqualified; set NDF for nonzero KD')
    if min(v['KP'], v['KI'], v['KD'], v['DB']) < 0 or v['UPD'] <= 0:
        raise ModelError('PID requires nonnegative gains/deadband and positive UPD seconds')
    if v['MAXS'] <= v['MINS'] or v['MAXI'] <= v['MINI'] or v['MAXCV'] <= v['MINCV']:
        raise ModelError('PID scaling spans must be positive')
    if v['PVDB'] < 0 or v['DVDB'] < 0 or v['PVL'] > v['PVH'] or v['DVN'] > v['DVP']:
        raise ModelError('PID alarm limits/deadbands are invalid')
    low, high = v['MINO'], v['MAXO']
    if low == high:
        low, high = 0.0, 100.0
    if not 0 <= low < high <= 100:
        raise ModelError('PID automatic output limits require 0 <= MINO < MAXO <= 100')
    pv = real(v['MINS'] + (real(engine.memory.read(op.args[1], scope)) - v['MINI']) *
              (v['MAXS'] - v['MINS']) / (v['MAXI'] - v['MINI']))
    v['SP'] = pv if pv_tracking else read('SP')
    if not v['MINS'] <= v['SP'] <= v['MAXS']:
        raise ModelError('PID setpoint is outside the engineering range')
    error = real((pv - v['SP']) if flags('CA') else (v['SP'] - pv))
    percent = real(error * 100 / (v['MAXS'] - v['MINS']))
    proportional = real(v['KP'] * percent)
    ki = (v['KP'] / (60 * v['KI']) if v['KI'] else 0.0) if flags('PE') else v['KI']
    identity = ('RLL-PID', key, tuple(parts))
    previous = engine.last_timer.get(identity)
    if previous and previous['at'] == engine.time_ms:
        raise ModelError('PID requires one true execution per record per task release time')
    state = previous if flags('INI') else None
    integral = state['integral'] if state and ki else 0.0
    was_tracking = bool(state and state.get('tracking', state['manual']))
    bias = v['BIAS']
    derivative_signature = (flags('DOE'), flags('CA'), *(v[n] for n in ('MINS', 'MAXS', 'MINI', 'MAXI')))
    # Re-arm zero crossing when its configuration changes. NDF/KD/gains do
    # not affect this latch; setpoint, scaling and action changes do.
    deadband_signature = (v['DB'], flags('NOZC'), flags('CA'), v['SP'], *derivative_signature[2:])
    same_deadband = state and state['deadband_signature'] == deadband_signature and not was_tracking
    crossed = (error == 0 or same_deadband and
               (state['error'] == 0 or (error < 0) != (state['error'] < 0)))
    hold = bool(not tracking and v['DB'] > 0 and abs(error) <= v['DB'] and
                (flags('NOZC') or crossed or same_deadband and state['deadband']))
    derivative = 0.0
    if (state and not was_tracking and not tracking and not hold and v['KD'] and
            state['derivative_signature'] == derivative_signature):
        change = error - state['error'] if flags('DOE') else (pv - state['pv']) * (1 if flags('CA') else -1)
        kd = v['KP'] * 60 * v['KD'] if flags('PE') else v['KD']
        derivative = real(kd * change * 100 / (v['MAXS'] - v['MINS']) / v['UPD'])
    restart_cv = None
    if inhold:
        restart_cv = coerce(real(engine.memory.read(op.args[6], scope)), cvtype)
        if not v['MINCV'] <= restart_cv <= v['MAXCV']:
            raise ModelError('PID inhold value must be within the CV scaling span after conversion')
        out = real((restart_cv - v['MINCV']) * 100 / (v['MAXCV'] - v['MINCV']))
        if ki:
            integral = real(out - bias - proportional)
        else:
            # A restart seeds the next automatic baseline even when ordinary
            # manual bias back-calculation has been disabled through NOBC.
            bias = real(out - proportional)
        limited_low = limited_high = False
    elif manual:
        if hardware_manual:
            tieback = real(engine.memory.read(op.args[2], scope))
            mintie, maxtie = read('MINTIE'), read('MAXTIE')
            if maxtie <= mintie:
                raise ModelError('PID tieback scaling span must be positive')
            out = real(min(100.0, max(0.0, (tieback - mintie) * 100 / (maxtie - mintie))))
        else:
            out = min(100.0, max(0.0, read('SO')))
        if ki:
            integral = real(out - bias - proportional)
        elif not flags('NOBC'):
            bias = real(out - proportional)
        limited_low = limited_high = False
    elif hold:
        # Hold percent output and I; retain fresh samples so release does not
        # differentiate against the sample from before a long held interval.
        derivative = 0.0
        saved_out = state['out'] if state else read('OUT')
        out = min(high, max(low, saved_out))
        limited_low, limited_high = saved_out <= low, saved_out >= high
    else:
        # Explicit rectangular integration, with no integration on the first
        # auto call after a manual sample. This is a documented solver choice.
        delta = 0.0 if was_tracking else ki * percent * v['UPD']
        proposed = real(integral + delta)
        raw = real(bias + proportional + derivative + proposed)
        if raw > high and delta > 0:
            proposed = real(max(integral, high - bias - proportional - derivative))
        elif raw < low and delta < 0:
            proposed = real(min(integral, low - bias - proportional - derivative))
        raw = real(bias + proportional + derivative + proposed)
        integral = proposed
        out = min(high, max(low, raw))
        limited_low, limited_high = raw <= low, raw >= high
    out = real(out)
    # The v35 reference specifies zero for integer CV in the deadband. This
    # profile applies that rule throughout the automatic error band, including
    # before zero-crossing hold; manual modes bypass control deadband.
    if inhold:
        assigned_cv = restart_cv
    else:
        cv = real(v['MINCV'] + out * (v['MAXCV'] - v['MINCV']) / 100)
        assigned_cv = 0 if (cvtype != 'REAL' and not manual and v['DB'] > 0 and abs(error) <= v['DB']) else coerce(cv, cvtype)
    def alarm(name, value, limit, band, high_alarm):
        old = bool(ctl & (1 << BITS[name]))
        return (value > limit or old and value >= limit - band) if high_alarm else (
            value < limit or old and value <= limit + band)
    results = dict(EN=True, INI=True, SPOR=False, EWD=hold, OLL=limited_low, OLH=limited_high,
        PVHA=alarm('PVHA', pv, v['PVH'], v['PVDB'], True),
        PVLA=alarm('PVLA', pv, v['PVL'], v['PVDB'], False),
        DVPA=alarm('DVPA', error, v['DVP'], v['DVDB'], True),
        DVNA=alarm('DVNA', error, v['DVN'], v['DVDB'], False))
    for name, value in results.items():
        bit = 1 << BITS[name]
        ctl = (ctl | bit) if value else (ctl & ~bit)
    engine.memory.write(op.args[3], assigned_cv, scope)
    obj.update(CTL=bit_value(ctl, 'DINT'), PV=pv, ERR=error, OUT=out, BIAS=bias,
               SO=out, MINO=real(low), MAXO=real(high))
    if hardware_manual:
        obj['TIE'] = tieback
    if pv_tracking:
        obj['SP'] = v['SP']
    for i, value in ((0, integral), (2, pv), (3, error), (4, v['SP']), (14, real(assigned_cv))):
        obj['DATA'][i] = value
    engine.last_timer[identity] = dict(integral=integral, manual=manual, tracking=tracking, inhold=inhold, at=engine.time_ms,
        pv=pv, error=error, derivative=derivative, derivative_signature=derivative_signature,
        out=out, deadband=hold, deadband_signature=deadband_signature)
    return True


def description():
    return dict(profile='v35-5580-RLL-PID-software', language='RLL', instructions=['PID'],
        record=dict(FIELDS), data_elements=17, ctl_aliases=dict(BITS),
        operands='PID record, scalar SINT/INT/DINT/REAL PV, numeric tieback tag or DINT/REAL immediate, writable SINT/INT/DINT/REAL CV, 0, BOOL inhold tag or 0, numeric readback tag or 0; outside AOIs',
        conversions='PV/tieback promote to finite REAL; integer CV uses ties-to-even with range faults; automatic integer CV is zero throughout a positive deadband; DATA14 mirrors assigned CV',
        equation='Percent error=100*(SP-PV)/(MAXS-MINS), sign reversed for CA; P=KP*error%; independent I+=KI*error%*UPD; dependent I+=KP*error%*UPD/(60*KI)',
        solver='Rectangular I per reached true call using UPD, not elapsed time; clip outward I to automatic headroom, freeze if already beyond the limit',
        derivative='NDF required for KD>0; independent D=KD*d(error%)/UPD or signed KD*d(PV%)/UPD; dependent coefficient=KP*60*KD; first/reinitialized/manual-transfer/config-change sample gives zero D',
        deadband='DB>0: inclusive engineering error band; NOZC holds immediately, otherwise hold after zero/sign crossing; EWD means active hold; hold percent output and I, refresh samples; manual overrides',
        manual='MO overrides SWM: numeric tieback scaled MINTIE..MAXTIE into 0..100, raw input mirrored in TIE; SWM uses SO; I tracks output-P-BIAS or BIAS tracks with zero KI unless NOBC; first auto sample holds I',
        pv_tracking='PVT copies scaled PV to SP during controlling MO/SWM only; unknown old SP may be established; resulting SP must fit the engineering range; inactive auto and inhold retain SP',
        inhold='True BOOL overrides manual/deadband; readback copied into CV after conversion, must fit MINCV..MAXCV; inverse OUT seeds I or BIAS regardless NOBC; release primes auto; external module/acknowledgement/timing not modeled',
        lifecycle='Prescan/false clear EN only; skipped calls retain history; first call or INI=false starts zero I; Run resets hidden state; whole-advance rollback',
        data='DATA[0,2,3,4,14] mirror I,PV,error,SP,CV; other entries retained, not interpreted as native coefficients',
        native_runtime_parity=False, packed_layout=False,
        remaining=['Derivative smoothing/filter coefficients, cascade and analog module restart/acknowledgement',
                   'ST/AOI forms, further optional-operand variants and saved active solver state',
                   'Native coefficients, anti-windup/bumpless/initialization/alarm boundaries, minor faults, rounding and DATA/layout parity'])
