"""Scalar MOV/CLR and explicit numeric conversions for the v35 5580 model."""
import re
from . import string_operations, time_values
from .st_literals import scan as typed_integer
from .integer_math import CONTROLLERS, WIDE_TYPES, bit_value
from .model import INT_BITS, ModelError, coerce, literal
from .real_math import real

INSTRUCTIONS = frozenset(('MOV', 'CLR'))
TYPES = frozenset((*INT_BITS, 'REAL', 'LREAL'))


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def destination(memory, ref, scope, *, allow_time=False, allow_string=False):
    key, parts, dtype = memory.check_writable(ref, scope)
    if allow_string and memory.project.string_capacity(dtype) is not None:
        string_operations.string_operand(memory, ref, scope, destination=True)
        return key, parts, dtype
    if (dtype not in TYPES and not (allow_time and dtype in time_values.TYPES)
            or isinstance(memory.at(key, parts), (list, dict))):
        raise ModelError('MOV/CLR destination requires one supported scalar element')
    return key, parts, dtype


def typed_literal(ref):
    """One declared immediate; each caller selects its admitted forms."""
    text=ref.strip()
    radix=re.fullmatch(r'(2|8|16)#([0-9A-Fa-f_ ]+?)([Uu][Ll]?|[Ll])?',text)
    if radix:
        suffix=radix[3] or '';digits=radix[2]
        dtype={'':'DINT','L':'LINT','U':'UDINT','UL':'ULINT'}[suffix.upper()]
        if suffix and not re.fullmatch(r'[0-9A-Fa-f](?:[0-9A-Fa-f_ ]*[0-9A-Fa-f])?',digits):
            raise ModelError('Typed radix requires digit groups and an attached suffix')
        try:value=int(digits.replace('_','').replace(' ',''),int(radix[1]))
        except ValueError as error:raise ModelError('Radix immediate has invalid digits') from error
        bits=INT_BITS[dtype]
        if value>=1<<bits:raise ModelError(f'Radix immediate exceeds its {bits}-bit {dtype} pattern')
        return dtype,bit_value(value,dtype)
    offset=int(text[:1] in ('+','-'))
    token=typed_integer(text,offset)
    if token is not None and token[0]==len(text):
        value,dtype=token[1]
        return dtype,coerce(-value if text.startswith('-') else value,dtype)
    floating=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)[Ll]',text)
    if floating and any(c in floating[1] for c in '.eE'):
        return 'LREAL',coerce(float(floating[1]),'LREAL')
    return None


def source_type(memory, ref, scope):
    typed=typed_literal(ref)
    if typed is not None:return typed[0]
    try:value = literal(ref)
    except ValueError:
        key, parts, dtype = memory.resolve(ref, scope)
        if dtype not in TYPES or isinstance(memory.at(key, parts), (list, dict)):
            raise ModelError('MOV source requires one numeric scalar element')
        return dtype
    if type(value) is int:
        coerce(value, 'DINT');return 'DINT'
    if type(value) is float:
        real(value);return 'REAL'
    raise ModelError('MOV immediate requires bounded DINT or finite REAL')


def lreal_math_source(memory, ref, scope, *, execute=False):
    """Selected LREAL math input; keep MOV radix and other consumers separate."""
    typed=typed_literal(ref) if '#' not in ref else None
    if typed is not None:
        dtype,value=typed
    else:
        try:value=literal(ref)
        except ValueError:
            key,parts,dtype=memory.resolve(ref,scope)
            if dtype not in TYPES or isinstance(memory.at(key,parts),(list,dict)):
                raise ModelError('LREAL math source requires one numeric scalar')
            if not execute:return dtype
            value=memory.read(ref,scope)
        else:
            dtype='DINT' if type(value) is int else 'REAL' if type(value) is float else None
            if dtype is None:raise ModelError('LREAL math immediate requires a numeric literal')
    value=real(value) if dtype=='REAL' else coerce(value,dtype)
    return coerce(value,'LREAL') if execute else dtype


def math_source_type(memory, ref, scope):
    """Identify a declared math source type without consuming a tag value."""
    typed = typed_literal(ref) if '#' not in ref else None
    if typed is not None:
        return typed[0]
    try:
        value = literal(ref)
    except ValueError:
        return memory.resolve(ref, scope)[2]
    if type(value) is int:
        return 'DINT'
    return 'REAL' if type(value) is float else None


def real_math_source(memory, ref, scope, *, execute=False):
    """Selected REAL input; validate its declared type before float32 conversion."""
    dtype=lreal_math_source(memory,ref,scope)
    if dtype=='LREAL':raise ModelError('REAL math source narrowing from LREAL is not qualified')
    if not execute:return dtype
    typed=typed_literal(ref) if '#' not in ref else None
    return real(typed[1] if typed is not None else memory.read(ref,scope))


def floating_math_profile(memory, op, scope):
    """Select a ladder math calculation type from declared operands."""
    key, parts, dtype = memory.check_writable(op.args[-1], scope)
    if dtype not in TYPES:
        return None
    sources = op.args[:-1]
    source_types = () if dtype == 'LREAL' else tuple(math_source_type(memory, ref, scope) for ref in sources)
    binary64 = dtype == 'LREAL' or 'LREAL' in source_types
    single = dtype == 'REAL' or (dtype in WIDE_TYPES and 'REAL' in source_types)
    if not (binary64 or single):
        return None
    if isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('Floating math requires one scalar numeric destination')
    validate_source = lreal_math_source if binary64 else real_math_source
    for ref in sources:
        validate_source(memory, ref, scope)
    return 'LREAL' if binary64 else 'REAL'


def write_lreal_math_result(memory, ref, value, scope):
    """Validate the binary64 result before the one destination conversion."""
    value = coerce(value, 'LREAL')
    try:
        memory.write(ref, value, scope)
    except OverflowError as error:
        raise ModelError('LREAL math result exceeds finite REAL range') from error


def specification(memory, op, scope):
    previous = memory.structural
    memory.structural = True
    try:
        _, _, dtype = destination(memory, op.args[-1], scope, allow_time=True, allow_string=op.name == 'MOV')
        if op.name == 'CLR':
            return None
        ref = op.args[0]
        if memory.project.string_capacity(dtype) is not None:
            if string_operations.string_literal(ref) is None:
                string_operations.string_operand(memory, ref, scope)
            return None
        if dtype == 'LINT':
            immediate = typed_literal(ref)
            if immediate is not None:
                return immediate[0]
        if dtype in time_values.TYPES or dtype == 'LINT':
            source = time_values.operand_type(memory, ref, scope, include_lint=dtype in time_values.TYPES)
            if dtype in time_values.TYPES or source in time_values.TYPES:
                if not time_values.move_allowed(source, dtype):
                    raise ModelError('Time/date MOV requires one time family or the LINT/LDT bridge')
                return source
        return source_type(memory, op.args[0], scope)
    finally:
        memory.structural = previous


def validate(engine, op, scope):
    if op.name not in INSTRUCTIONS or not available(engine.project):return False
    specification(engine.memory, op, scope)
    return True


def convert(value, source, dest):
    if source in INT_BITS:
        if type(value) is not int:raise ModelError('MOV requires a known integer source')
        value = coerce(value, source)
        return bit_value(value, dest) if dest in INT_BITS else coerce(value, dest)
    # Keep REAL overflow results/status outside this representable profile.
    return coerce(coerce(value, source), dest)


def execute(engine, op, power, scope):
    if not power:return False
    memory = engine.memory
    source = specification(memory, op, scope)
    key, parts, dtype = destination(memory, op.args[-1], scope, allow_time=True, allow_string=op.name == 'MOV')
    capacity = memory.project.string_capacity(dtype)
    if capacity is not None:
        ref = op.args[0]
        text = string_operations.string_literal(ref)
        value = memory.string(ref, scope, limit=capacity) if text is None else text[:capacity]
        memory.write_string(op.args[-1], value, scope)
        return True
    if dtype in time_values.TYPES or source in time_values.TYPES:
        value = 0
        if source is not None:
            ticks = time_values.read_operand(memory, op.args[0], scope)
            value = time_values.convert_move(ticks, source, dtype)
        memory.store(key, parts, coerce(value, dtype))
        return True
    typed=typed_literal(op.args[0]) if op.name=='MOV' else None
    value = convert(typed[1] if typed is not None else memory.read(op.args[0], scope), source, dtype) if op.name == 'MOV' else coerce(0, dtype)
    memory.store(key, parts, value)
    return True


def description(project):
    return dict(available=available(project), profile='v35-5580-numeric-storage', language='RLL',
                instructions=sorted(INSTRUCTIONS), types=sorted(TYPES),
                operands='One numeric scalar element; bounded DINT/finite REAL or typed L/U/UL integer and floating L/l MOV immediates; aliases and existing AOI bindings',
                time_date=dict(types=sorted(time_values.TYPES), instructions=['MOV', 'CLR'],
                    operands='Same-family scalar tags or typed literals, plus LINT/LDT tag bridge; CLR writes zero ticks',
                    conversion='Exact tick scaling; reject fractional destination ticks or out-of-range results; LINT/LDT copies nanosecond ticks',
                    representation='Exact decimal ticks in the declared microsecond or nanosecond unit',
                    native_runtime_parity=False),
                typed_mov_literals=dict(integer_types=['LINT','UDINT','ULINT'],floating_type='LREAL',
                    range='Declared source range and precision checked structurally, before existing destination conversion',
                    conversion='Same integer pattern, floating precision and checked nearest-even conversion as a source tag',
                    scope='MOV source only; decimal typed forms and radix L/U/UL bit patterns; no expressions, other arguments/consumers or native parity',
                    native_runtime_parity=False),
                radix_mov_literals=dict(bases=[2,8,16],source_type='DINT',bits=32,
                    interpretation='Zero-fill unspecified bits; unsuffixed bit 31 is signed DINT before existing MOV conversion',
                    typed_suffixes=dict(L=dict(source_type='LINT',bits=64,signed=True),
                        U=dict(source_type='UDINT',bits=32,signed=False),UL=dict(source_type='ULINT',bits=64,signed=False)),
                    typed_interpretation='Attached case-insensitive L/U/UL selects declared width; signed LINT bit 63 is the sign bit; exact integral source before conversion',
                    grouping='Interior spaces or underscores; case-insensitive hexadecimal digits',
                    scope='MOV source only; base fields describe unsuffixed DINT, typed_suffixes describes attached typed forms; no explicit sign, other consumers or native parity',
                    native_runtime_parity=False),
                integers='Preserve low destination bits; sign-extend signed sources and zero-extend unsigned sources when widening',
                real='Finite REAL binary32 and LREAL binary64; source precision retained before destination conversion; nearest-even integer results must fit',
                lreal='Declared LREAL tags and finite floating L/l MOV literals; binary64 storage/conversion, CLR and atomic tag access; expression and wire-layout profiles remain separate',
                selection='Structural preflight; false/prescan skip values and live indices; true full writes establish unknown destinations',
                clearing='CLR writes typed zero without reading the old scalar value',
                failures='Reached unknown source, invalid indices, excluded REAL ranges and later faults roll back the advance',
                native_math_status=False, native_runtime_parity=False,
                remaining=['Lossy or cross-family time/date conversion, string CLR and non-string aggregate MOV/CLR; typed radix in other consumers/controllers',
                           'REAL overflow result bits, native status/fault/lifecycle/packed layout parity'])
