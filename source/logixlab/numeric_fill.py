"""Numeric FLL selection and conversion for the bounded v35 5580 profile."""
from .integer_math import CONTROLLERS, bit_value
from .model import INT_BITS, ModelError, coerce, literal
from .numeric_copy import static_reference, location, prefix
from .real_math import real
from . import time_values

INTEGERS = frozenset(('SINT', 'INT', 'DINT'))
NUMERIC = INTEGERS | {'REAL'}
MAX_ELEMENTS = 100000
AGGREGATE_SCALARS = frozenset((*INT_BITS,*time_values.TYPES,'BOOL','REAL','LREAL','BIT'))


def operand_type(memory, ref, scope, *, length=False):
    try:value = literal(ref)
    except ValueError:
        key, parts, dtype = memory.resolve(ref, scope)
        if isinstance(memory.at(key, parts), (list, dict)):
            raise ModelError('Numeric FLL requires scalar source and length operands')
    else:
        dtype = 'DINT' if type(value) is int else 'REAL' if type(value) is float else 'BOOL'
        if dtype == 'DINT':coerce(value, dtype)
        elif dtype == 'REAL':real(value)
    allowed = INTEGERS if length else NUMERIC
    if dtype not in allowed:
        raise ModelError('Numeric FLL ' + ('length requires SINT/INT/DINT' if length else 'source requires SINT/INT/DINT/REAL'))
    return dtype


def converted(value, source_type, destination_type):
    if source_type in INTEGERS:
        if type(value) is not int:raise ModelError('Numeric FLL source must be a known integer')
        value = coerce(value, source_type)
        if destination_type in INTEGERS:
            return bit_value(value, destination_type)
        return real(value)
    # REAL narrowing remains a representable, nearest-even software profile.
    # Native overflow bits/status for REAL-to-integer are not inferred here.
    return coerce(real(value), destination_type)


def handle(engine, op, scope, *, execute=False):
    """Handle qualified numeric destinations; leave legacy aggregate fills alone."""
    project = engine.project
    if project.version != '35' or project.processor.upper() not in CONTROLLERS:
        return False
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        _, _, dtype = memory.check_writable(op.args[1], scope)
        if dtype not in NUMERIC:return False
        memory.region(op.args[1], 0, scope)
        source_type = operand_type(memory, op.args[0], scope)
        operand_type(memory, op.args[2], scope, length=True)
    finally:
        memory.structural = previous
    if not execute:return True

    count = memory.read(op.args[2], scope)
    if type(count) is not int or not 0 <= count <= MAX_ELEMENTS:
        raise ModelError('Numeric FLL length must be an integer in 0..100000')
    # Capture the complete target window before writing. Keep the existing
    # logical array/member boundary rather than assuming a native packed layout.
    key, paths, dtype = prefix(memory,op.args[1],scope,count,writable=True)
    memory.check_writable(op.args[1], scope)
    if count:
        value = converted(memory.read(op.args[0], scope), source_type, dtype)
        for path in paths:memory.store(key, path, value)
    return True


def write_effects(engine,op,scope):
    """Protect complete numeric/aggregate windows in existing ST FOR extensions."""
    memory=engine.memory;project=engine.project
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:return None
    previous=memory.structural;memory.structural=True
    try:
        numeric=memory.check_writable(op.args[1],scope)[2] in NUMERIC
        if not (handle if numeric else aggregate_handle)(engine,op,scope):return None
        try:count=literal(op.args[2])
        except ValueError:count=None
        if count is not None:
            if type(count) is not int or not 0<=count<=MAX_ELEMENTS:raise ModelError('Numeric FLL length must be an integer in 0..100000')
            if count==0:return []
            if static_reference(memory,op.args[1],scope):
                key,paths,_=prefix(memory,op.args[1],scope,count,writable=True)
                return [(key,path) for path in paths]
        key,parts,_,candidate=location(memory,op.args[1],scope,writable=True)
        path=candidate[0] if candidate is not None else parts
        path=path[:next((i for i,part in enumerate(path) if isinstance(part,int)),len(path))]
        return [(key,path)]
    finally:memory.structural=previous


def aggregate_template(project,dtype,seen=(),*,instruction="FLL"):
    """Use declared schemas, never the Python types of unknown saved values."""
    if dtype.upper() == 'PID' and instruction == 'COP/CPS':
        if 'pid' in project.udts:raise ModelError('Aggregate COP/CPS excludes redefined PID records')
        return project.default('PID')
    if dtype.upper() in ('TIMER','COUNTER','CONTROL','STRING'):return project.default(dtype)
    name=dtype.lower();definition=project.udts.get(name)
    if definition is None or dtype.upper() in project.aois:
        raise ModelError('Aggregate '+instruction+' supports basic records and explicit UDTs, not operational/AOI records')
    if name in seen or len(seen)>=32:raise ModelError('Aggregate '+instruction+' schema nesting exceeds its bounded profile')
    for member in definition.findall('./Members/Member'):
        if member.get('Hidden','false').lower()=='true':continue
        kind=member.get('DataType')
        if kind not in AGGREGATE_SCALARS:aggregate_template(project,kind,seen+(name,),instruction=instruction)
    return project.default(dtype)


def zero_value(value):
    if type(value) is bool:return False
    if type(value) is int:return 0
    if type(value) is float:return 0.0
    if isinstance(value,list):return [zero_value(v) for v in value]
    if isinstance(value,dict):return {k:zero_value(v) for k,v in value.items()}
    raise ModelError('Aggregate FLL cannot infer an unsupported member type')


def all_ones_value(project, dtype, template):
    """Represent an FF pattern only where every declared field has exact bits."""
    if isinstance(template,list):
        return [all_ones_value(project,dtype,value) for value in template]
    kind=dtype.upper()
    if kind in INT_BITS:return bit_value(-1,kind)
    if kind in ('BOOL','BIT'):return True
    if kind in ('TIMER','COUNTER','CONTROL'):
        return {name:True if type(value) is bool else -1 for name,value in template.items()}
    if kind in ('REAL','LREAL') or project.string_capacity(dtype) is not None:
        raise ModelError('All-ones FLL excludes floating-point and string members')
    if kind in time_values.TYPES:
        raise ModelError('All-ones FLL excludes time/date members')
    definition=project.udts.get(dtype.lower())
    if definition is None:raise ModelError('All-ones FLL requires a declared integral/Boolean record')
    types={member.get('Name'):member.get('DataType') for member in definition.findall('./Members/Member')}
    return {name:all_ones_value(project,types[name],value) for name,value in template.items()}


def scalar_count(value):
    if isinstance(value,dict):return sum(map(scalar_count,value.values()))
    if isinstance(value,list):return sum(map(scalar_count,value))
    return 1


def aggregate_handle(engine,op,scope,*,execute=False):
    project=engine.project
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:return False
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        _,_,dtype=memory.check_writable(op.args[1],scope)
        if dtype not in ('TIMER','COUNTER','CONTROL','STRING') and dtype.lower() not in project.udts:return False
        template=aggregate_template(project,dtype)
        pattern=template if dtype=='CONTROL' else zero_value(template)
        ones_pattern=None
        memory.region(op.args[1],0,scope)
        try:source=literal(op.args[0])
        except ValueError:
            key,parts,source_type=memory.resolve(op.args[0],scope)
            if source_type not in INTEGERS or isinstance(memory.at(key,parts),(dict,list)):
                raise ModelError('Aggregate FLL source requires scalar SINT, INT or DINT')
        else:
            if type(source) is not int or source not in (0,-1):raise ModelError('Aggregate FLL supports integer zero or -1 only')
            if source==-1:ones_pattern=all_ones_value(project,dtype,template)
        operand_type(memory,op.args[2],scope,length=True)
        try:count=literal(op.args[2])
        except ValueError:pass
        else:
            if type(count) is not int or not 0<=count<=MAX_ELEMENTS:raise ModelError('Aggregate FLL length must be an integer in 0..100000')
            if static_reference(memory,op.args[1],scope):prefix(memory,op.args[1],scope,count,writable=True)
    finally:memory.structural=previous
    if not execute:return True
    count=memory.read(op.args[2],scope)
    if type(count) is not int or not 0<=count<=MAX_ELEMENTS:raise ModelError('Aggregate FLL length must be an integer in 0..100000')
    key,paths,_=prefix(memory,op.args[1],scope,count,writable=True)
    if count:
        source=memory.read(op.args[0],scope)
        if type(source) is not int or source not in (0,-1):raise ModelError('Aggregate FLL supports integer zero or -1 only')
        if source==-1:pattern=ones_pattern if ones_pattern is not None else all_ones_value(project,dtype,template)
        engine.budget-=len(paths)*scalar_count(pattern)
        if engine.budget<0:raise ModelError('Aggregate FLL scalar-member budget exceeded')
        for path in paths:memory.store(key,path,pattern)
    return True


def aggregate_description(project):
    return dict(available=project.version=='35' and project.processor.upper() in CONTROLLERS,language='RLL',instructions=['FLL'],
                source='Scalar SINT/INT/DINT zero or -1, or matching immediate; length SINT/INT/DINT or bounded DINT immediate',
                destinations='TIMER/COUNTER/CONTROL/STRING and explicit nested basic UDTs, selected arrays, aliases and existing AOI bindings',
                zero='Typed values built from declared schema; full records establish unknowns, including BOOL/REAL/LREAL/time/date members and unused string DATA',
                udt_scalar_fields=sorted(AGGREGATE_SCALARS-{'BIT'}),
                all_ones='-1 fills exact signed/unsigned integer and Boolean fields, arrays, TIMER/COUNTER/CONTROL and nested integral UDTs; floating/time/date/string members excluded',
                control='Top-level CONTROL zero retains its existing logical-default reset; nested zero CONTROL members are zeroed; -1 sets flags and signed fields to all ones',
                selection='Structural preflight; false/prescan skip live operands; true captures length, complete window and source pattern before stores',
                zero_length='Validate live destination, skip source value and its live index',
                clipping=True,clipping_boundary='Selected logical array/member or scalar; no crossing sibling members',
                st_for_effects='Complete clipped static windows; changing/alias/AOI selections conservatively cover the enclosing array',
                work='One instruction-budget unit per actual scalar member filled; logical clipping, no native byte clipping',
                remaining=['Other nonzero/REAL/wider source patterns, all-ones floating/time/date/string fields, operational/AOI aggregate records, packed ABI and native faults/partial effects',
                           'Native scan/lifecycle/clock/internal-history reset parity and other profiles/languages'],native_runtime_parity=False)


def description(project):
    return dict(available=project.version == '35' and project.processor.upper() in CONTROLLERS, profile='v35-5580-numeric-FLL', language='RLL', types=sorted(NUMERIC),
                integer_conversion='Preserve low destination bits when narrowing; sign-extend when widening',
                real_conversion='Finite float32; nearest-even integer results must fit the signed destination',
                operands='Scalar source; SINT/INT/DINT length; bounded DINT/finite REAL immediates',
                selection='Structural preflight; false/prescan skip live operands; true calls sample length, destination window and source before stores',
                zero_length='Validate the live destination reference without reading the source value',
                storage='Whole arrays or selected elements; row-major traversal within the logical array/member; aliases and existing AOI bindings',
                max_elements=MAX_ELEMENTS, clipping=True,
                clipping_boundary='Selected logical numeric array/member or scalar; requests stop at its end, without crossing sibling members',
                st_for_effects='Complete clipped static window; dynamic/alias selections conservatively cover the member and enclosing parent arrays',
                failures='Unknown consumed values, invalid indices/lengths, REAL range errors and later faults roll back the advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Native clipping/base-tag cross-member traversal and packed layouts',
                           'REAL overflow bits/flags, wider types and native/controller/language/lifecycle qualification',
                           'Aggregate zero fills have a separate declared-schema profile; other controller profiles retain legacy behavior'])
