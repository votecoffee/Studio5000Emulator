"""Exact scalar storage and typed literals for v35 time and date operands."""
import re
from datetime import datetime
from functools import lru_cache

PREFIXES = {'T32': 'TIME32', 'T': 'TIME', 'LT': 'LTIME', 'DT': 'DT', 'LDT': 'LDT'}
TYPES = frozenset(PREFIXES.values())
DATE_TYPES = frozenset(('DT', 'LDT'))
EPOCH = datetime(1970, 1, 1)
UNITS_NS = dict(d=86_400_000_000_000, h=3_600_000_000_000, m=60_000_000_000,
                s=1_000_000_000, ms=1_000_000, us=1_000, ns=1)
MAX_DURATION_NS = (31 * 86400 + 12 * 3600 + 59 * 60 + 59) * UNITS_NS['s'] + UNITS_NS['s'] - 1
DATE_SECONDS = (datetime(2251, 1, 1) - EPOCH).days * 86400
BOUNDS = {
    'TIME32': (-2147483647, 2147483647),
    'TIME': (-(MAX_DURATION_NS // 1000), MAX_DURATION_NS // 1000),
    'LTIME': (-MAX_DURATION_NS, MAX_DURATION_NS),
    'DT': (0, DATE_SECONDS * 1_000_000 - 1),
    'LDT': (0, DATE_SECONDS * 1_000_000_000 - 1),
}
DATE = re.compile(
    r'(\d{4})-(\d{2})-(\d{2})-(\d{2}):(\d{2}):(\d{2})'
    r'(?:\.([0-9]{1,9}|[0-9]{3}(?:_[0-9]{3}){1,2}))?'
    r'(?:\s*\(UTC([+-])(\d{2}):(\d{2})\))?', re.ASCII | re.IGNORECASE)
DURATION_COMPONENT = re.compile(r'([0-9]+)(d|h|ms|us|ns|m|s)', re.IGNORECASE)


def available(project):
    from .integer_math import CONTROLLERS
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def checked(value, dtype):
    low, high = BOUNDS[dtype]
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{dtype} requires exact ticks in range {low}..{high}')
    return value


def duration(text, dtype):
    sign = -1 if text.startswith('-') else 1
    total = 0
    previous_unit = UNITS_NS['d'] + 1
    for token in text.removeprefix('-').split('_'):
        part = DURATION_COMPONENT.fullmatch(token)
        if part is None:
            raise ValueError(f'Invalid {dtype} duration literal')
        unit = UNITS_NS[part[2].lower()]
        if unit >= previous_unit or (dtype != 'LTIME' and unit == 1):
            raise ValueError(f'{dtype} duration units must descend and match its precision')
        total += int(part[1]) * unit
        previous_unit = unit
    return sign * (total if dtype == 'LTIME' else total // 1000)


def timestamp(text, dtype):
    match = DATE.fullmatch(text)
    if match is None:
        raise ValueError(f'Invalid {dtype} date literal')
    year, month, day, hour, minute, second = map(int, match.groups()[:6])
    delta = datetime(year, month, day, hour, minute, second) - EPOCH
    seconds = delta.days * 86400 + delta.seconds
    fraction = (match[7] or '').replace('_', '')
    precision = 6 if dtype == 'DT' else 9
    if len(fraction) > precision:
        raise ValueError(f'{dtype} fraction exceeds {precision} decimal places')
    if match[8]:
        offset_hour, offset_minute = int(match[9]), int(match[10])
        if offset_hour > 23 or offset_minute > 59:
            raise ValueError(f'Invalid {dtype} UTC offset')
        offset = offset_hour * 3600 + offset_minute * 60
        seconds -= offset if match[8] == '+' else -offset
    return seconds * 10 ** precision + int(fraction.ljust(precision, '0'))


def literal(ref):
    """Return the declared time/date type and exact ticks, or None for other syntax."""
    prefix, sep, value = ref.strip().partition('#')
    dtype = PREFIXES.get(prefix.upper()) if sep else None
    if dtype is None:
        return None
    ticks = timestamp(value, dtype) if dtype in DATE_TYPES else duration(value, dtype)
    return dtype, checked(ticks, dtype)


def coerce(value, dtype):
    if isinstance(value, str):
        typed = literal(value)
        if typed is not None:
            if typed[0] != dtype:
                raise ValueError(f'{dtype} requires a matching time/date literal')
            value = typed[1]
        elif re.fullmatch(r'[+-]?[0-9]+', value.strip()):
            value = int(value)
    return checked(value, dtype)


def operand_type(memory, ref, scope, *, include_lint=False):
    """Get a time/date operand's declared type without reading its saved value."""
    from .model import ModelError, literal as numeric_literal
    from .numeric_storage import typed_literal
    typed = literal(ref)
    if typed is not None:
        return typed[0]
    if '#' not in ref and typed_literal(ref) is not None:
        return None
    try:
        numeric_literal(ref)
    except ValueError:
        key, parts, dtype = memory.resolve(ref, scope)
        if dtype in TYPES or (include_lint and dtype == 'LINT'):
            if isinstance(memory.at(key, parts), (list, dict)):
                raise ModelError('Time/date operand requires one scalar element')
            return dtype
    return None


def same_family(source, dest):
    return source in TYPES and dest in TYPES and (source in DATE_TYPES) == (dest in DATE_TYPES)


def move_allowed(source, dest):
    return same_family(source, dest) or (source, dest) in (('LINT', 'LDT'), ('LDT', 'LINT'))


def ns_per_tick(dtype):
    return 1 if dtype in ('LTIME', 'LDT', 'LINT') else 1000


def exact_ticks(nanoseconds, dest, operation):
    ticks, remainder = divmod(nanoseconds, ns_per_tick(dest))
    if remainder:
        raise ValueError(f'{operation} would discard fractional ticks')
    return ticks


def convert_move(value, source, dest):
    return exact_ticks(value * ns_per_tick(source), dest, f'{source} to {dest} MOV')


@lru_cache(maxsize=512)
def display_literal(ref):
    """Parse a bounded authored operand for monitoring, including blocked rungs."""
    try:
        return literal(ref)
    except ValueError:
        return None


def read_operand(memory, ref, scope):
    typed = literal(ref)
    return typed[1] if typed is not None else memory.read(ref, scope, allow_time=True)


def display_changes(changes, tags):
    """Keep exact ticks in the browser and HTTP history as in tag snapshots."""
    if not changes:
        return changes
    names = {tag['name'] for tag in tags if tag['type'] in TYPES}
    if not names:
        return changes
    return [
        {**row, **{field: str(row[field]) if row[field] is not None else None
                  for field in ('before', 'after')}}
        if row['tag'] in names else row
        for row in changes
    ]
