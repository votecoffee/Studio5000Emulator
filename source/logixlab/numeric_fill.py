"""Numeric FLL selection and conversion for the bounded v35 5580 profile."""
from .integer_math import CONTROLLERS, bit_value
from .model import INT_BITS, ModelError, coerce, literal
from .numeric_copy import static_reference
from .real_math import real

INTEGERS = frozenset(('SINT', 'INT', 'DINT'))
NUMERIC = INTEGERS | {'REAL'}
MAX_ELEMENTS = 100000


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
    key, paths, dtype = memory.region(op.args[1], count, scope)
    memory.check_writable(op.args[1], scope)
    if count:
        value = converted(memory.read(op.args[0], scope), source_type, dtype)
        for path in paths:memory.store(key, path, value)
    return True


def aggregate_template(project,dtype,seen=(),*,instruction="FLL"):
    """Use declared schemas, never the Python types of unknown saved values."""
    if dtype.upper() in ('TIMER','COUNTER','CONTROL','STRING'):return project.default(dtype)
    name=dtype.lower();definition=project.udts.get(name)
    if definition is None or dtype.upper() in project.aois:
        raise ModelError('Aggregate '+instruction+' supports basic records and explicit UDTs, not operational/AOI records')
    if name in seen or len(seen)>=32:raise ModelError('Aggregate '+instruction+' schema nesting exceeds its bounded profile')
    for member in definition.findall('./Members/Member'):
        if member.get('Hidden','false').lower()=='true':continue
        kind=member.get('DataType')
        if kind not in {*INT_BITS,'BOOL','REAL','BIT'}:aggregate_template(project,kind,seen+(name,),instruction=instruction)
    return project.default(dtype)


def zero_value(value):
    if type(value) is bool:return False
    if type(value) is int:return 0
    if type(value) is float:return 0.0
    if isinstance(value,list):return [zero_value(v) for v in value]
    if isinstance(value,dict):return {k:zero_value(v) for k,v in value.items()}
    raise ModelError('Aggregate FLL cannot infer an unsupported member type')


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
        memory.region(op.args[1],0,scope)
        try:source=literal(op.args[0])
        except ValueError:
            key,parts,source_type=memory.resolve(op.args[0],scope)
            if source_type not in INTEGERS or isinstance(memory.at(key,parts),(dict,list)):
                raise ModelError('Aggregate FLL source requires scalar SINT, INT or DINT')
        else:
            if type(source) is not int or source!=0:raise ModelError('Aggregate FLL currently supports integer zero only')
        operand_type(memory,op.args[2],scope,length=True)
        try:count=literal(op.args[2])
        except ValueError:pass
        else:
            if type(count) is not int or not 0<=count<=MAX_ELEMENTS:raise ModelError('Aggregate FLL length must be an integer in 0..100000')
            if static_reference(memory,op.args[1],scope):memory.region(op.args[1],count,scope)
    finally:memory.structural=previous
    if not execute:return True
    count=memory.read(op.args[2],scope)
    if type(count) is not int or not 0<=count<=MAX_ELEMENTS:raise ModelError('Aggregate FLL length must be an integer in 0..100000')
    key,paths,_=memory.region(op.args[1],count,scope);memory.check_writable(op.args[1],scope)
    if count:
        source=memory.read(op.args[0],scope)
        if type(source) is not int or source!=0:raise ModelError('Aggregate FLL currently supports integer zero only')
        engine.budget-=len(paths)*scalar_count(pattern)
        if engine.budget<0:raise ModelError('Aggregate FLL scalar-member budget exceeded')
        for path in paths:memory.store(key,path,pattern)
    return True


def aggregate_description(project):
    return dict(available=project.version=='35' and project.processor.upper() in CONTROLLERS,language='RLL',instructions=['FLL'],
                source='Scalar SINT/INT/DINT zero or integer-zero immediate; length SINT/INT/DINT or bounded DINT immediate',
                destinations='TIMER/COUNTER/CONTROL/STRING and explicit nested basic UDTs, selected arrays, aliases and existing AOI bindings',
                zero='Typed values built from declared schema; full records establish unknowns, including BOOL/REAL members and unused string DATA',
                control='Top-level CONTROL retains its existing logical-default reset; nested CONTROL members are zeroed',
                selection='Structural preflight; false/prescan skip live operands; true captures length, complete window and zero source before stores',
                zero_length='Validate live destination, skip source value and its live index',
                work='One instruction-budget unit per scalar member filled; strict logical region bounds, no native byte clipping',
                remaining=['Nonzero/REAL/wider source patterns, operational/AOI aggregate records, packed ABI and native faults/partial effects',
                           'Native scan/lifecycle/clock/internal-history reset parity and other profiles/languages'],native_runtime_parity=False)


def description(project):
    return dict(available=project.version == '35' and project.processor.upper() in CONTROLLERS, profile='v35-5580-numeric-FLL', language='RLL', types=sorted(NUMERIC),
                integer_conversion='Preserve low destination bits when narrowing; sign-extend when widening',
                real_conversion='Finite float32; nearest-even integer results must fit the signed destination',
                operands='Scalar source; SINT/INT/DINT length; bounded DINT/finite REAL immediates',
                selection='Structural preflight; false/prescan skip live operands; true calls sample length, destination window and source before stores',
                zero_length='Validate the live destination reference without reading the source value',
                storage='Whole arrays or selected elements; row-major traversal within the logical array/member; aliases and existing AOI bindings',
                max_elements=MAX_ELEMENTS, clipping=False,
                failures='Unknown consumed values, invalid indices/lengths, REAL range errors and later faults roll back the advance',
                native_runtime_parity=False, native_math_status=False,
                remaining=['Native clipping/base-tag cross-member traversal and packed layouts',
                           'REAL overflow bits/flags, wider types and broader controller/language/lifecycle qualification',
                           'Aggregate zero fills have a separate declared-schema profile; other controller profiles retain legacy behavior'])
