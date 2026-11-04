"""Scalar MOV/CLR and explicit numeric conversions for the v35 5580 model."""
import re
from .st_literals import scan as typed_integer
from .integer_math import CONTROLLERS, bit_value
from .model import INT_BITS, ModelError, coerce, literal
from .real_math import real

INSTRUCTIONS = frozenset(('MOV', 'CLR'))
TYPES = frozenset((*INT_BITS, 'REAL', 'LREAL'))


def available(project):
    return project.version == '35' and project.processor.upper() in CONTROLLERS


def destination(memory, ref, scope):
    key, parts, dtype = memory.check_writable(ref, scope)
    if dtype not in TYPES or isinstance(memory.at(key, parts), (list, dict)):
        raise ModelError('MOV/CLR destination requires one numeric scalar element')
    return key, parts, dtype


def typed_literal(ref):
    """One MOV immediate; never widen general memory/expression parsing."""
    text=ref.strip()
    radix=re.fullmatch(r'(2|8|16)#([0-9A-Fa-f_ ]+)',text)
    if radix:
        try:value=int(radix[2].replace('_','').replace(' ',''),int(radix[1]))
        except ValueError as error:raise ModelError('MOV radix immediate has invalid digits') from error
        if value>=1<<32:raise ModelError('MOV radix immediate exceeds its 32-bit DINT pattern')
        return 'DINT',bit_value(value,'DINT')
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


def lreal_math_sources(memory, op, scope):
    """Preflight scalar LREAL-result math without consuming saved source values."""
    if destination(memory,op.args[-1],scope)[2]!='LREAL':
        raise ModelError('LREAL math requires a scalar LREAL destination')
    for ref in op.args[:-1]:lreal_math_source(memory,ref,scope)
    return 'LREAL'


def specification(memory, op, scope):
    previous = memory.structural
    memory.structural = True
    try:
        destination(memory, op.args[-1], scope)
        return source_type(memory, op.args[0], scope) if op.name == 'MOV' else None
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
    key, parts, dtype = destination(memory, op.args[-1], scope)
    typed=typed_literal(op.args[0]) if op.name=='MOV' else None
    value = convert(typed[1] if typed is not None else memory.read(op.args[0], scope), source, dtype) if op.name == 'MOV' else coerce(0, dtype)
    memory.store(key, parts, value)
    return True


def description(project):
    return dict(available=available(project), profile='v35-5580-numeric-storage', language='RLL',
                instructions=sorted(INSTRUCTIONS), types=sorted(TYPES),
                operands='One numeric scalar element; bounded DINT/finite REAL or typed L/U/UL integer and floating L/l MOV immediates; aliases and existing AOI bindings',
                typed_mov_literals=dict(integer_types=['LINT','UDINT','ULINT'],floating_type='LREAL',
                    range='Declared source range and precision checked structurally, before existing destination conversion',
                    conversion='Same integer pattern, floating precision and checked nearest-even conversion as a source tag',
                    scope='MOV source only; decimal typed forms and separate unsuffixed DINT radix patterns; no typed radix, expressions, other arguments/consumers or native parity',
                    native_runtime_parity=False),
                radix_mov_literals=dict(bases=[2,8,16],source_type='DINT',bits=32,
                    interpretation='Zero-fill unspecified bits; reinterpret bit 31 as the signed DINT top bit before existing MOV conversion',
                    grouping='Interior spaces or underscores; case-insensitive hexadecimal digits',
                    scope='Unsuffixed nonnegative radix MOV source only; other consumers retain their contracts',
                    native_runtime_parity=False),
                integers='Preserve low destination bits; sign-extend signed sources and zero-extend unsigned sources when widening',
                real='Finite REAL binary32 and LREAL binary64; source precision retained before destination conversion; nearest-even integer results must fit',
                lreal='Declared LREAL tags and finite floating L/l MOV literals; binary64 storage/conversion, CLR and atomic tag access; expression and wire-layout profiles remain separate',
                selection='Structural preflight; false/prescan skip values and live indices; true full writes establish unknown destinations',
                clearing='CLR writes typed zero without reading the old scalar value',
                failures='Reached unknown source, invalid indices, excluded REAL ranges and later faults roll back the advance',
                native_math_status=False, native_runtime_parity=False,
                remaining=['Time/date, string and aggregate MOV/CLR forms; typed radix/other consumers/controllers',
                           'REAL overflow result bits, native status/fault/lifecycle/packed layout parity'])
