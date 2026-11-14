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
    r'(?:\.([0-9]{3}(?:_[0-9]{3}){1,2}|[0-9]{1,9}))?'
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


def scan(text, pos=0):
    """Return one declared temporal expression token using the storage parser."""
    prefix=re.match(r'(T32|LDT|LT|DT|T)#',text[pos:],re.ASCII|re.IGNORECASE)
    if prefix is None:return None
    dtype=PREFIXES[prefix[1].upper()];start=pos+prefix.end()
    if dtype in DATE_TYPES:
        date=DATE.match(text,start)
        if date is None:raise ValueError('Invalid '+dtype+' date literal')
        end=date.end()
    else:
        end=start
        if text[end:end+1]=='-':end+=1
        while end<len(text) and (text[end].isascii() and text[end].isalnum() or text[end]=='_'):end+=1
    if end<len(text) and (text[end].isalnum() or text[end] in '_.#'):
        raise ValueError('Invalid '+dtype+' literal boundary')
    _,ticks=literal(text[pos:end])
    return end,(ticks,dtype)


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
    return (same_family(source, dest) or source == 'LINT' and dest in DATE_TYPES
            or dest == 'LINT' and source in DATE_TYPES)


def ns_per_tick(dtype):
    return 1 if dtype in ('LTIME', 'LDT', 'LINT') else 1000


def exact_ticks(nanoseconds, dest, operation):
    ticks, remainder = divmod(nanoseconds, ns_per_tick(dest))
    if remainder:
        raise ValueError(f'{operation} would discard fractional ticks')
    return ticks


def convert_move(value, source, dest):
    # Legacy timestamp bridges retain raw ticks in the selected date precision.
    # LINT has no unit metadata: DT microseconds must not be scaled as LDT ns.
    if source == 'LINT' and dest in DATE_TYPES or dest == 'LINT' and source in DATE_TYPES:
        return value
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


def condition_profile(expression, memory, scope=''):
    """Keep default/generic condition flags outside the temporal interpreter."""
    if not (expression.allow_wide and expression.allow_lreal):return None
    return expression_profile(expression,memory,scope,consumer='CMP')


def expression_profile(expression, memory, scope='', destination_type=None, *, consumer='CMP'):
    """Qualify temporal values, arithmetic and condition composition structurally."""
    from .conditions import RELATIONS
    from .model import ModelError
    declared={ref:memory.resolve(ref,scope)[2] for ref in expression.refs}
    if destination_type not in TYPES and not TYPES.intersection(declared.values()) and not expression.temporal_types:return None
    if consumer not in ('CPT','CMP','FAL'):raise ModelError('Unsupported temporal expression consumer')
    if not available(memory.project):raise ModelError('Temporal expressions require the v35 ControlLogix 5580 profile')
    condition=consumer=='CMP'
    if not condition and destination_type not in TYPES:raise ModelError('Temporal CPT/FAL requires a temporal scalar destination')
    types={};previous=memory.structural
    try:
        memory.structural=True
        for ref,dtype in declared.items():
            if dtype in TYPES:
                operand_type(memory,ref,scope);memory.read(ref,scope,allow_time=True)
                types[ref]='date' if dtype in DATE_TYPES else 'duration'
            elif condition and dtype=='BOOL':
                if isinstance(memory.read(ref,scope),(dict,list)):raise ModelError('Temporal conditions require scalar BOOL operands')
                types[ref]='bool'
            elif condition and memory.project.string_capacity(dtype) is not None:
                memory.string(ref,scope);types[ref]='string'
            else:raise ModelError('Temporal expressions require time/date operands; conditions also allow BOOL/string tags')
    finally:memory.structural=previous
    nodes={}
    def infer(node):
        result=category(node);nodes[id(node)]=result;return result
    def category(node):
        kind,value=node[:2]
        if kind=='ref':return types[value]
        if kind=='time_literal':return 'date' if node[2] in DATE_TYPES else 'duration'
        if kind=='unary':
            operand=infer(node[2])
            if condition and value in ('!','NOT') and operand=='bool':return 'bool'
            if value in ('+','-') and operand=='duration':return 'duration'
            raise ModelError('Temporal unary operators require a duration, or condition BOOL negation')
        if kind!='binary':raise ModelError('Temporal expressions require declared temporal tags/literals; numeric constants and functions remain unqualified')
        left,right=infer(node[2]),infer(node[3])
        if condition and value in RELATIONS:
            if left!=right or left=='bool' and value not in ('=','<>'):raise ModelError('Temporal comparison families and operand categories must match')
            return 'bool'
        if condition and value in ('&&','||','^^','AND','OR','XOR') and left==right=='bool':return 'bool'
        if value=='+':
            if left==right=='duration':return 'duration'
            if (left,right) in (('date','duration'),('duration','date')):return 'date'
        elif value=='-':
            if left==right and left in ('duration','date'):return 'duration'
            if (left,right)==('date','duration'):return 'date'
        raise ModelError('Temporal arithmetic supports duration +/- duration, date +/- duration, duration + date, or date - date')
    result=infer(expression.tree)
    expected='bool' if condition else 'date' if destination_type in DATE_TYPES else 'duration'
    if result!=expected:raise ModelError(consumer+' temporal result family must match its destination')
    return dict(consumer=consumer,destination_type=destination_type,declared=declared,types=types,nodes=nodes)


def evaluate_condition(expression, memory, scope, profile):
    return evaluate_expression(expression,memory,scope,profile)


def evaluate_expression(expression, memory, scope, profile):
    """Use bounded canonical nanoseconds, then require exact destination ticks."""
    from .conditions import RELATIONS
    from .model import ModelError,coerce
    def bounded(value,category):return coerce(value,'LDT' if category=='date' else 'LTIME')
    def visit(node):
        kind,value=node[:2];category=profile['nodes'][id(node)]
        if kind=='time_literal':return bounded(value*ns_per_tick(node[2]),category)
        if kind=='ref':
            dtype=profile['declared'][value]
            if category in ('date','duration'):return bounded(read_operand(memory,value,scope)*ns_per_tick(dtype),category)
            if category=='string':return memory.string(value,scope)
            return coerce(memory.read(value,scope),'BOOL')
        if kind=='unary':
            item=visit(node[2])
            if value in ('!','NOT'):return not item
            return bounded(item if value=='+' else -item,category)
        left,right=visit(node[2]),visit(node[3])
        if value in RELATIONS:return RELATIONS[value](left,right)
        if value in ('&&','AND'):return left and right
        if value in ('||','OR'):return left or right
        if value in ('^^','XOR'):return left!=right
        return bounded(left+right if value=='+' else left-right,category)
    result=visit(expression.tree)
    if profile['consumer']=='CMP':return result
    dtype=profile['destination_type']
    try:ticks=exact_ticks(result,dtype,profile['consumer']+' temporal result')
    except ValueError as error:raise ModelError(str(error)) from error
    return coerce(ticks,dtype)


def expression_description(project):
    return dict(available=available(project),consumers=['CPT','CMP','FAL','FSC'],types=sorted(TYPES),
                operators=['+','-'],unary='Duration + and -; condition BOOL negation',
                arithmetic='Exact nanoseconds; each duration/date node fits canonical LTIME/LDT bounds',
                families='Duration +/- duration; date +/- duration; duration + date; date - date',
                destination='CPT/FAL temporal scalar of the result family; exact tick precision and declared range required',
                conditions='Same-family relations, BOOL/string comparisons and eager Boolean composition',
                failures='Unknowns, bounds, fractional ticks, range and later faults roll back the advance; FAL temporal errors do not use REAL ER/prefix retry',
                excluded='Numeric mixtures, multiplication/division/functions, date + date, duration - date, ST/FBD/SFC and native numerical/status/fault/layout parity',
                native_runtime_parity=False)
