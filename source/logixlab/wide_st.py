"""Shared exact wide-integer expressions for bounded ST and ladder consumers."""
from .conditions import RELATIONS
from .comparisons import ordering_type, INTEGER_RANK
from .integer_math import CONTROLLERS,WIDE_TYPES,bit_value,quotient
from .model import INT_BITS,ModelError,coerce


def analyze(expression,memory,scope='',destination_type=None,*,consumer='ST'):
    label='Wide '+consumer
    declared={ref:memory.resolve(ref,scope)[2] for ref in expression.refs}
    wide=(set(declared.values())&WIDE_TYPES)|expression.typed_types
    if destination_type in WIDE_TYPES:wide.add(destination_type)
    if not wide:return None
    if memory.project.version!='35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError(label+' requires the v35 ControlLogix 5580 profile')
    strings={ref for ref,kind in declared.items()
             if consumer=='CMP' and memory.project.string_capacity(kind) is not None}
    numeric={kind for ref,kind in declared.items() if ref not in strings}-{'BOOL'}
    mixed=consumer in ('CPT','CMP','FAL') and len(numeric)>1
    if mixed:
        dtype=ordering_type(numeric)
        if expression.typed_types - {dtype}:
            raise ModelError(label+' typed constants must match the common source tag type')
    else:
        if len(wide)!=1 or numeric-wide:
            raise ModelError(label+' numeric tag operands must have one matching declared type')
        dtype=next(iter(wide))
    if destination_type not in (None,'BOOL',dtype):
        raise ModelError(label+' numeric destination must match the expression type')
    ladder_math = consumer in ('CPT','CMP','FAL')
    bcd = {'FRD','TOD'} if expression.bcd and ladder_math and not mixed else set()
    roots = {'SQR'} if ladder_math else set()
    if expression.functions-{'ABS'}-bcd-roots or '**' in expression.operators and not ladder_math:
        raise ModelError(label+' supports ABS, homogeneous FRD/TOD and qualified integer SQR/power; other functions remain unqualified')
    types={ref:'string' if ref in strings else 'bool' if kind=='BOOL' else 'number' for ref,kind in declared.items()}
    for ref in declared:
        if ref in strings:
            memory.string(ref,scope)
            continue
        if isinstance(memory.read(ref,scope),(list,dict)):
            raise ModelError(label+' operands must be scalar values')
    def immediate(value):
        if type(value) is not int or not -(1<<31)<=value<1<<31:
            raise ModelError(label+' immediates require signed DINT integers representable in the operand type')
        coerce(value,dtype)
    origins={}
    def common_operand(node):
        key=id(node)
        if key not in origins:
            origins[key]=(node[0]=='ref' and declared[node[1]]==dtype or
                          any(common_operand(child) for child in node[2:] if isinstance(child,tuple)))
        return origins[key]
    def require_common(node):
        if not common_operand(node):
            raise ModelError('Mixed ladder arithmetic requires the common tag type in every arithmetic subexpression')
    def infer(node):
        kind,value=node[:2]
        if kind=='literal':
            if type(value) is bool:return 'bool'
            immediate(value);return 'number'
        if kind=='typed_literal':
            coerce(value,node[2]);return 'number'
        if kind=='ref':return types[value]
        if kind=='string':raise ModelError('Wide ST string forms remain unqualified')
        if kind=='unary':
            if value in ('+','-') and node[2][0] in ('literal','typed_literal') and type(node[2][1]) is int:
                signed=node[2][1] if value=='+' else -node[2][1]
                if node[2][0]=='typed_literal':coerce(signed,node[2][2])
                else:immediate(signed)
                return 'number'
            result=infer(node[2])
            if (value=='NOT' or consumer=='CMP' and value=='!') and result=='bool':return 'bool'
            if result!='number' or value=='!':raise ModelError('Invalid wide ST unary operand')
            if mixed:
                if value=='NOT':raise ModelError('Mixed numeric bitwise expressions remain unqualified')
                require_common(node)
            return 'number'
        if kind=='call':
            if infer(node[2])!='number':raise ModelError(label+' functions require a numeric operand')
            if mixed:require_common(node)
            return 'number'
        left,right=infer(node[2]),infer(node[3])
        if value in RELATIONS:
            if left!=right or left=='bool' and value not in ('=','<>'):
                raise ModelError('Wide ST comparison operand types must match')
            return 'bool'
        if consumer=='CMP' and value in ('&&','||','^^'):
            if left!=right or left!='bool':raise ModelError('Wide CMP logical operators require BOOL expressions')
            return 'bool'
        if value in ('AND','OR','XOR') and left==right=='bool':return 'bool'
        if left!='number' or right!='number':raise ModelError('Wide ST arithmetic requires numeric operands')
        if mixed:
            if value not in ('+','-','*','/','MOD','**'):raise ModelError('Mixed numeric bitwise expressions remain unqualified')
            require_common(node)
        return 'number'
    return dtype,infer(expression.tree),types


def evaluate(expression,memory,scope,profile):
    dtype,_,types=profile
    def number(value):return coerce(value,dtype)
    def visit(node):
        kind,value=node[:2]
        if kind=='literal':return value if type(value) is bool else number(value)
        if kind=='typed_literal':return number(value)
        if kind=='ref':
            if types[value]=='string':return memory.string(value,scope)
            item=memory.read(value,scope)
            return bool(item) if types[value]=='bool' else number(item)
        if kind=='unary':
            if value in ('+','-') and node[2][0] in ('literal','typed_literal') and type(node[2][1]) is int:
                return number(node[2][1] if value=='+' else -node[2][1])
            item=visit(node[2])
            if value in ('NOT','!') and type(item) is bool:return not item
            return number(item if value=='+' else -item if value=='-' else bit_value(~item,dtype))
        if kind=='call':
            item=visit(node[2])
            if value=='ABS':return number(abs(item))
            if value=='SQR':
                from .real_math import rounded_integer_root
                return number(rounded_integer_root(item))
            from .numeric_conversions import from_bcd,to_bcd
            return number(from_bcd(item,INT_BITS[dtype]) if value=='FRD' else to_bcd(item,dtype))
        left,right=visit(node[2]),visit(node[3])
        if value in RELATIONS:return RELATIONS[value](left,right)
        if value in ('AND','OR','XOR','&&','||','^^') and type(left) is type(right) is bool:
            return left and right if value in ('AND','&&') else left or right if value in ('OR','||') else left!=right
        if value=='+':result=left+right
        elif value=='-':result=left-right
        elif value=='*':result=left*right
        elif value=='/':result=quotient(left,right)
        elif value=='MOD':result=left-quotient(left,right)*right
        elif value=='**':
            bits=INT_BITS[dtype]
            if not 0 <= right < bits:
                raise ModelError(f'Wide integer expression exponent must be in 0..{bits-1}')
            from .real_math import integer_power_result
            result=integer_power_result(left,right,dtype)
        elif value=='AND':result=bit_value(left&right,dtype)
        elif value=='OR':result=bit_value(left|right,dtype)
        elif value=='XOR':result=bit_value(left^right,dtype)
        else:raise ModelError('Unsupported wide ST operator '+value)
        return number(result)
    return visit(expression.tree)


def ladder_description(project):
    return dict(profile='v35-5580-integer-ladder-expressions',types=list(INTEGER_RANK),
                available=project.version=='35' and project.processor.upper() in CONTROLLERS,
                instructions=['CPT','CMP','MEQ'],file_consumers=['FAL','FSC'],mixed_numeric_types=True,
                string_conditions=dict(consumers=['CMP','FSC'],
                    types='Built-in STRING and declared DINT LEN/SINT DATA strings, including different capacities',
                    comparison='Six case-sensitive lexical relations over active bytes; eager Boolean operands',
                    numeric='Exact integer source/literal selection, range checks, common-type subtrees and homogeneous BCD/bitwise/root/power rules remain',
                    selection='Structural validation; lazy false/prescan/file idle paths; unknown active bytes or invalid LEN/bounds roll back',
                    excluded='String math/literals, category mismatches, ST/CPT/FAL string operands and native numerical/status/fault/layout parity',
                    native_runtime_parity=False),
                signed_dint_radix_expressions=dict(instructions=['CPT','CMP','FAL','FSC'],bases=[2,8,16],bits=32,
                    interpretation='Unsuffixed words with bit31 set decode as signed DINT before expression unary operators',
                    arithmetic='Narrow integer or existing compatible wide profile; existing per-intermediate range checks',
                    excluded='REAL/LREAL mixtures, default/ST/index parser expansion and native parity',
                    native_runtime_parity=False),
                root_power=dict(instructions=['CPT','CMP','FAL','FSC'],types=sorted(WIDE_TYPES),
                    root='SQR of integer absolute magnitude, rounded to nearest integer without a floating conversion',
                    power='Exact nonnegative integer powers; exponent 0..width-1, with checked selected-width intermediates',
                    exponent_max={'USINT':7,'UINT':15,'UDINT':31,'LINT':63,'ULINT':63},
                    mixed_numeric_types=True,mixed_source_types=list(INTEGER_RANK),
                    common_type='Actual source type covers every full source range; each arithmetic subtree contains a source of that type',
                    mixed_exponent_max={dtype:INT_BITS[dtype]-1 for dtype in INTEGER_RANK},
                    excluded='Incompatible ranges, lower-type-only arithmetic subtrees, other functions, negative/fractional exponents, ST/index expansion and native parity',
                    native_runtime_parity=False),
                bcd=dict(instructions=['CPT','CMP','FAL','FSC'],functions=['FRD','TOD'],types=sorted(WIDE_TYPES),
                    widths={'USINT':8,'UINT':16,'UDINT':32,'LINT':64,'ULINT':64},
                    interpretation='Homogeneous selected integer width; FRD weights all nibbles including A-F; TOD packs 2/4/8/16 digits',
                    excluded='Mixed numeric tag types, REAL/LREAL, ST/index expansion and native parity',
                    native_runtime_parity=False),
                arithmetic='Exact declared-width integers; every intermediate must fit; quotient truncates toward zero',
                operators=['+','-','*','/','MOD','AND','OR','XOR','NOT','ABS','comparisons'],
                cmp_logic=['&&','||','^^','!','BOOL AND/OR/XOR/NOT'],eager_cmp=True,
                mixed_integer_comparisons=dict(instructions=['CMP'],types=list(INTEGER_RANK),
                    operands='Highest-ranked actual numeric tag type covers every complete declared numeric tag range in the expression',
                    operators='Direct numeric relations and BOOL composition, including BOOL equality, eager AND/OR/XOR/NOT and symbolic forms',
                    constants='Signed-DINT values or matching decimal L/U/UL constants representable in the actual common tag type; no invented larger type or value-based tag conversion',
                    selection='Structural preflight; false/prescan skip live values and indices; true expressions consume both logical operands',
                    arithmetic='Bounded mixed arithmetic is described in mixed_integer_arithmetic',
                    excluded='Numeric bitwise mixtures, other functions, REAL/LREAL, nonmatching typed or untyped larger constants, CPT comparison results, ST and native parity',
                    native_runtime_parity=False),
                mixed_integer_arithmetic=dict(instructions=['CPT','CMP','FAL','FSC'],types=list(INTEGER_RANK),
                    operators=['+','-','*','/','MOD','unary +','unary -','ABS','SQR','**'],
                    operands='Highest-ranked actual source tag type covers every complete numeric source range; CPT/FAL destination matches that type',
                    intermediates='Every arithmetic subexpression contains an actual source tag of the selected common type; every result must fit',
                    constants='Signed-DINT values or decimal/radix L/U/UL constants matching the actual common source type; destination and constants do not invent a wider source type',
                    typed_constants=dict(types=['LINT','UDINT','ULINT'],radix_bases=[2,8,16],matching_common_source_type=True,
                        range='Declared range checked in preflight with the immediate unary sign; exact values above 2^53',
                        no_source_promotion=True),
                    arithmetic='Exact integers; quotient toward zero; remainder has dividend sign; all required sources consumed',
                    excluded='Lower-type-only arithmetic subtrees, mixed numeric bitwise, other functions, negative/fractional powers, REAL/LREAL, nonmatching typed or untyped larger constants, ST and native parity',
                    native_runtime_parity=False),
                meq='All eight integer tag types may mix with bounded plain and typed immediates; homogeneous LINT immediate compatibility is retained',
                meq_mixed_integer_tags=True,
                literals='Signed DINT integers or matching decimal/radix L/U/UL literals within declared range in direct CPT/CMP',
                typed_integer_literals=dict(instructions=['CPT','CMP'],types=['LINT','UDINT','ULINT'],
                    suffixes=['L/l','U/u','UL/ul/Ul/uL'],radix_bases=[2,8,16],matching_numeric_types=True,
                    range='Declared literal range checked in preflight with its immediate unary sign; exact integer evaluation',
                    excluded='Other literal/tag mixtures, nonmatching radix types, other consumers, REAL/LREAL combinations and native parity',
                    native_runtime_parity=False),
                failures='Required unknown data, bounds, division and overflow faults roll back the whole advance',
                native_runtime_parity=False,
                remaining=['Other mixed arithmetic intermediates and nonmatching typed/radix literal combinations','Numeric bitwise mixtures and functions beyond ABS and qualified homogeneous FRD/TOD/SQR/power',
                           'Time/date expressions and additional file/index forms; LREAL and simple wide tag indices use separate qualified profiles','Native status/fault/intermediate/partial-effect parity'])


def description(project):
    return dict(profile='v35-5580-homogeneous-wide-ST',types=sorted(WIDE_TYPES),
                available=project.version=='35' and project.processor.upper() in CONTROLLERS,
                operators=['+','-','*','/','MOD','AND','OR','XOR','NOT','ABS','comparisons'],
                literals='Untyped signed DINT integers or matching decimal L/U/UL literals within declared range',
                arithmetic='Exact integers, quotient toward zero; every numeric intermediate must fit its declared type',
                conditions='Wide comparisons with BOOL operands/logic; eager operand evaluation',
                mixed_numeric_types=False,native_runtime_parity=False,
                remaining=['Mixed numeric types/conversions, typed radix literals and typed instruction arguments','Power/other functions',
                           'Wide FOR/CASE/index forms','File-expression consumers',
                           'Native math/status/fault/overflow/intermediate parity'])
