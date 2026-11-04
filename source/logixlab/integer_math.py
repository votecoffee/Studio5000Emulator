"""Exact, homogeneous wide-integer ladder operations for the v35 5580 model.

Overflow remains a modeled scan fault. Mixed-type promotion and controller math
status/minor-fault behavior are deliberately separate from this numeric profile.
"""
import operator

from .model import INT_BITS, UNSIGNED_BITS, ModelError, coerce, literal

WIDE_TYPES = frozenset(('LINT', *UNSIGNED_BITS))
CONTROLLERS = frozenset(f'1756-L8{number}E' for number in range(1, 6))
COMPARISONS = {'EQU': operator.eq, 'NEQ': operator.ne, 'LES': operator.lt,
               'LEQ': operator.le, 'GRT': operator.gt, 'GEQ': operator.ge}
INSTRUCTIONS = frozenset((*COMPARISONS, 'LIM', 'MOV', 'CLR', 'ADD', 'SUB', 'MUL',
                          'DIV', 'MOD', 'NEG', 'ABS', 'AND', 'OR', 'XOR', 'NOT'))


def description(project):
    return dict(profile='v35-5580-homogeneous-integers', language='RLL',
                arithmetic_available=project.version == '35' and project.processor.upper() in CONTROLLERS,
                types=sorted(WIDE_TYPES), controllers=sorted(CONTROLLERS),
                instructions=sorted(INSTRUCTIONS), mixed_types=False,
                arithmetic_tags='Standalone v35 ADD/SUB/MUL/DIV/MOD/NEG/ABS also use the separate scalar_math widening tag profile',
                ordering_tags='Standalone v35 EQU/NEQ/LES/LEQ/GRT/GEQ/LIM use the separate numeric_comparisons range-preserving mixed tag/constant profile',
                storage_moves='Standalone v35 MOV/CLR use the separate numeric_storage type/conversion profile',
                bitwise_tags='Standalone v35 AND/OR/XOR/NOT tags use the scalar_math mixed-integer profile; wide immediate forms retain these homogeneous rules',
                immediate_type='signed DINT, representable in operand type',
                division='Exact integer quotient truncated toward zero',
                overflow='Stop and roll back modeled scan; native status/fault flags not emulated')


def expression_description():
    return dict(types=['SINT','INT','DINT'],intermediate_type='DINT',consumers=['ST','CPT','CMP','FAL','FSC'],
                integer='Exact quotient truncated toward zero; remainder has the dividend sign',
                cpt_real='REAL operand/function or REAL destination promotes the whole expression',
                st_real='REAL operand/function promotes expression; a REAL destination alone does not',
                cmp_real='REAL operand/function promotes the comparison expression',
                failures='Whole advance rolls back on zero divisor, required unknown data or overflow',
                ladder_selection=dict(instructions=['CPT','CMP'],controllers=sorted(CONTROLLERS),firmware='35',
                    types=[*INT_BITS,'REAL'],bool_references='CMP Boolean composition only',
                    preflight='Declared scalar types, references, index grammar, destination permissions and existing expression/literal rules without saved values or dynamic indices',
                    selection='False/prescan skip live operands; CPT retains its destination and CMP propagates false to downstream coils',
                    writes='Complete CPT writes establish unknown destinations; unwritten elements/members retain unknown values',
                    failures='Required unknowns, bad indices, arithmetic and later faults roll back runtime values, scheduler state and AOI bindings',
                    excluded='String CMP, ST/FAL/FSC/index consumers, broader type/promotion/controller rules and native fault/lifecycle parity',
                    native_runtime_parity=False),
                array_indices=dict(firmware='35',controllers=sorted(CONTROLLERS),
                    expression_types=['SINT','INT','DINT'],simple_tag_types=list(INT_BITS),
                    operators=['+','-','*','/','AND','OR','XOR','NOT'],functions=['FRD','TOD','SQR'],
                    function_profile='Checked DINT arguments/results; FRD uses eight weighted nibbles, TOD packs 0..99999999, SQR uses float32 input/result and nearest-even DINT conversion after absolute-value root',
                    arithmetic='Checked DINT intermediates; exact division toward zero; bitwise integer operations',
                    simple_tags='A single integer tag retains its full declared range without DINT or floating conversion',
                    selection='Structural preflight skips saved indices; reached indices consume all required values; bounds and faults roll back the advance',
                    excluded='Wide arithmetic subexpressions, MOD, other functions, REAL/LREAL/BOOL, typed/larger literals and native parity',
                    native_runtime_parity=False),
                bcd_cpt=dict(firmware='35',controllers=sorted(CONTROLLERS),functions=['FRD','TOD'],
                    types=['SINT','INT','DINT'],intermediate_type='DINT',
                    conversion='Promote signed narrow values before eight-nibble FRD; TOD packs 0..99999999 into a signed DINT pattern',
                    composition='Existing integer arithmetic, bitwise operations, ABS/TRN/TRUNC, nesting and supported references',
                    selection='Structural preflight; false/prescan skip live operands; reached arguments are required before full destination writes',
                    excluded='REAL/LREAL/wide/BOOL expressions, other consumers, larger/typed literals and native numerical/status/fault/lifecycle parity',
                    native_runtime_parity=False),
                bcd_cmp=dict(firmware='35',controllers=sorted(CONTROLLERS),functions=['FRD','TOD'],
                    types=['SINT','INT','DINT'],intermediate_type='DINT',boolean_composition=True,
                    conversion='Existing CPT eight-nibble FRD and bounded signed-DINT TOD patterns',
                    composition='Integer arithmetic/bitwise, six relations, Boolean tags and eager logical operands',
                    selection='Structural preflight; false/prescan skip live numeric operands; true calls consume required arguments and write downstream coils',
                    excluded='REAL/LREAL/wide/string arithmetic, BOOL numeric arguments, other consumers and native numerical/status/fault/lifecycle parity',
                    native_runtime_parity=False),
                bcd_files=dict(firmware='35',controllers=sorted(CONTROLLERS),instructions=['FAL','FSC'],
                    functions=['FRD','TOD'],types=['SINT','INT','DINT'],intermediate_type='DINT',
                    modes=['ALL','positive DINT immediate','INC'],
                    conversion='Existing CPT eight-nibble FRD and bounded signed-DINT TOD; FSC retains eager Boolean composition',
                    execution='Existing sequential FAL writes and FSC first-match inhibit/resume; numeric false continuation and observed INC edges unchanged',
                    selection='Structural expression preflight; reached iterations consume live operands; false/held/done/inhibited data-free paths retain lazy reads',
                    aoi='Existing exact InOut/local array bindings and canonical CONTROL progress',
                    excluded='Wide/REAL/string BCD mixtures, saved active INC state, other language profiles and native numerical/status/cursor/fault/lifecycle parity',
                    native_runtime_parity=False),
                native_status_parity=False,
                integer_power=dict(firmware='35',controllers=sorted(CONTROLLERS),consumers=['CPT','CMP','FAL','FSC'],
                    types=['SINT','INT','DINT'],intermediate_type='DINT',exponent_range=[0,31],
                    arithmetic='Exact checked DINT powers; zero exponent returns one including zero base; equal operators associate left to right',
                    composition='Existing integer arithmetic, bitwise operators and FRD/TOD; eager CMP/FSC Boolean operands',
                    execution='Existing lazy selection, file progress, AOI bindings and whole-advance rollback',
                    excluded='Negative/larger integer exponents, wide arithmetic, other controller profiles and native numerical/status/fault/lifecycle parity',
                    native_runtime_parity=False),
                remaining=['Complete numeric promotion/conversion matrix','Wider and negative-exponent integer powers',
                           'Remaining array subscript operand/controller and native status qualification','Native intermediate/status/fault/partial-effect parity'])


def integer_power(base, exponent):
    """Bounded exact DINT power; no floating conversion or negative exponent."""
    if not 0 <= exponent <= 31:
        raise ModelError('Integer expression power exponent must be in 0..31')
    return coerce(base ** exponent, 'DINT')


def quotient(a, b):
    """Truncate integer division toward zero without a floating-point round trip."""
    if not b:
        raise ModelError('Integer divide by zero')
    return abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)


def profile(engine, op, scope):
    """Return the one declared wide type, or None for the existing narrow path."""
    types = []
    immediates = []
    for argument in op.args:
        try:
            value = literal(argument)
        except ValueError:
            types.append(engine.memory.resolve(argument, scope)[2])
        else:
            types.append(None)
            immediates.append(value)
    if 'LREAL' in types:raise ModelError('LREAL requires a qualified v35 5580 storage/arithmetic/comparison profile; this instruction remains unsupported')
    wide = set(types) & WIDE_TYPES
    if not wide:
        return None
    if len(wide) != 1 or set(types) - {None, *wide}:
        raise ModelError('Wide integer operations require matching declared operand types')
    dtype = next(iter(wide))
    if op.name not in INSTRUCTIONS:
        raise ModelError('Unsupported wide integer instruction ' + op.name)
    # Preserve previously supported same-type storage moves on older targets.
    legacy = op.name == 'CLR' or op.name == 'MOV' and not immediates
    if not legacy and (engine.project.version != '35' or engine.project.processor.upper() not in CONTROLLERS):
        raise ModelError('Wide integer execution requires the v35 ControlLogix 5580 profile')
    for value in immediates:
        if type(value) is not int or not -(1 << 31) <= value < 1 << 31:
            raise ModelError('Wide integer immediates require a signed DINT literal')
        coerce(value, dtype)
    return dtype


def bit_value(value, dtype):
    """Interpret exactly the declared number of bits, including unsigned NOT."""
    bits = INT_BITS[dtype]
    value &= (1 << bits) - 1
    if dtype not in UNSIGNED_BITS and value >= 1 << (bits - 1):
        value -= 1 << bits
    return value


def execute(engine, op, scope, dtype):
    """Execute a validated true-rung operation; return its rung-out condition."""
    memory = engine.memory
    name = op.name
    sources = op.args if name in COMPARISONS or name == 'LIM' else op.args[:-1]
    values = [memory.read(argument, scope) for argument in sources]
    if name in COMPARISONS:
        return COMPARISONS[name](*values)
    if name == 'LIM':
        low, value, high = values
        return low <= value <= high if low <= high else value >= low or value <= high
    a = values[0] if values else 0
    if name == 'CLR':
        result = 0
    elif name == 'MOV':
        result = a
    elif name == 'NEG':
        result = -a
    elif name == 'ABS':
        result = abs(a)
    elif name == 'NOT':
        result = bit_value(~a, dtype)
    else:
        b = values[1]
        if name == 'DIV':
            result = quotient(a, b)
        elif name == 'MOD':
            result = a - quotient(a, b) * b
        elif name in ('AND', 'OR', 'XOR'):
            result = bit_value({'AND': operator.and_, 'OR': operator.or_, 'XOR': operator.xor}[name](a, b), dtype)
        else:
            result = {'ADD': operator.add, 'SUB': operator.sub, 'MUL': operator.mul}[name](a, b)
    memory.write(op.args[-1], coerce(result, dtype), scope)
    return True
