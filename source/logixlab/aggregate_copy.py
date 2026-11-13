"""Matching basic-record COP/CPS with structural, lazy operand selection."""
from .integer_math import CONTROLLERS
from .model import ModelError, literal
from .numeric_copy import prefix, static_reference
from .numeric_fill import aggregate_template, scalar_count, MAX_ELEMENTS, AGGREGATE_SCALARS


def handle(engine, op, scope, *, execute=False):
    project = engine.project
    if project.version != '35' or project.processor.upper() not in CONTROLLERS:
        return False
    memory = engine.memory
    previous = memory.structural
    memory.structural = True
    try:
        source_type = memory.resolve(op.args[0], scope)[2]
        dest_type = memory.check_writable(op.args[1], scope)[2]
        if not any(t in ('TIMER', 'COUNTER', 'CONTROL', 'STRING', 'PID') or t.lower() in project.udts
                   for t in (source_type, dest_type)):
            return False
        if source_type != dest_type:
            raise ModelError('Aggregate COP/CPS require identical declared element types')
        template = aggregate_template(project, dest_type, instruction='COP/CPS')
        for ref in op.args[:2]:memory.region(ref, 0, scope)
        try:count = literal(op.args[2])
        except ValueError:
            key, parts, dtype = memory.resolve(op.args[2], scope)
            if dtype not in ('SINT', 'INT', 'DINT') or isinstance(memory.at(key, parts), (dict, list)):
                raise ModelError('Aggregate COP/CPS length requires scalar SINT, INT or DINT')
        else:
            if type(count) is not int or not 0 <= count <= MAX_ELEMENTS:
                raise ModelError('Aggregate COP/CPS length must be an integer in 0..100000')
            for ref in op.args[:2]:
                if static_reference(memory, ref, scope):prefix(memory, ref, scope, count)
    finally:memory.structural = previous
    if not execute:return True

    count = memory.read(op.args[2], scope)
    if type(count) is not int or not 0 <= count <= MAX_ELEMENTS:
        raise ModelError('Aggregate COP/CPS length must be an integer in 0..100000')
    # Capture all addresses before writing, including indices/lengths stored
    # inside the copied records. Values retain sequential overlap propagation.
    sk, sources, _ = prefix(memory, op.args[0], scope, count)
    dk, destinations, _ = prefix(memory, op.args[1], scope, count, writable=True)
    size = min(len(sources), len(destinations))
    sources, destinations = sources[:size], destinations[:size]
    engine.budget -= len(destinations) * scalar_count(template)
    if engine.budget < 0:raise ModelError('Aggregate COP/CPS scalar-member budget exceeded')
    for source, dest in zip(sources, destinations):
        memory.store(dk, dest, memory.at(sk, source))
    return True


def write_effects(engine,op,scope):
    """Track complete clipped records, conservatively for changing selections."""
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        if not handle(engine,op,scope):return None
        try:count=literal(op.args[2])
        except ValueError:count=None
        if count==0:return []
        if count is not None and all(static_reference(memory,ref,scope) for ref in op.args[:2]):
            _,sources,_=prefix(memory,op.args[0],scope,count)
            key,paths,_=prefix(memory,op.args[1],scope,count,writable=True)
            return [(key,path) for path in paths[:len(sources)]]
        key,parts,_=memory.check_writable(op.args[1],scope)
        boundary=next((i for i,part in enumerate(parts) if isinstance(part,int)),len(parts))
        return [(key,parts[:boundary])]
    finally:memory.structural=previous


def description(project):
    return dict(available=project.version == '35' and project.processor.upper() in CONTROLLERS,
                instructions=['COP', 'CPS'], languages=['RLL', 'ST'],
                types='Identical TIMER/COUNTER/CONTROL/STRING/PID or explicit nested qualified UDT element types',
                pid='Copy represented CTL/REAL fields and DATA[17]; preserve each destination solver history until its ordinary INI/Run lifecycle resets it',
                udt_scalar_fields=sorted(AGGREGATE_SCALARS-{'BIT'}),
                selection='Structural preflight; false/prescan skip saved lengths, values and dynamic indices',
                execution='Capture length and clipped source/destination windows before sequential stores; copy the minimum remaining element count',
                clipping=True,clipping_boundary='Selected logical array/member or scalar; no crossing sibling members',
                st_for_effects='Complete clipped static windows; changing/alias/AOI selections conservatively cover the enclosing array',
                zero_length='Resolve both live addresses without reading record values',
                unknowns='Copy logical unknowns, full records and all string DATA; each destination owns independent storage',
                overlap='Forward sequential propagation for both instructions, retaining existing logical-copy behavior',
                work='One budget unit per actual scalar member copied; logical clipping and whole-advance rollback',
                remaining=['Packed layouts, mixed aggregate types, native byte clipping and cross-member/base-tag traversal',
                           'Other operational/AOI aggregate schemas, private instruction-history transfer and native synchronization/fault/lifecycle parity'],
                native_runtime_parity=False)
