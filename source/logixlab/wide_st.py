"""Exact homogeneous wide ST expressions; no implicit numeric promotion."""
from .conditions import RELATIONS
from .integer_math import CONTROLLERS,WIDE_TYPES,bit_value,quotient
from .model import ModelError,coerce


def analyze(expression,memory,scope='',destination_type=None):
    declared={ref:memory.resolve(ref,scope)[2] for ref in expression.refs}
    wide=(set(declared.values())&WIDE_TYPES)|expression.typed_types
    if destination_type in WIDE_TYPES:wide.add(destination_type)
    if not wide:return None
    if memory.project.version!='35' or memory.project.processor.upper() not in CONTROLLERS:
        raise ModelError('Wide ST requires the v35 ControlLogix 5580 profile')
    if len(wide)!=1 or set(declared.values())-wide-{'BOOL'}:
        raise ModelError('Wide ST numeric tag operands must have one matching declared type')
    dtype=next(iter(wide))
    if destination_type not in (None,'BOOL',dtype):
        raise ModelError('Wide ST numeric destination must match the expression type')
    if expression.functions-{'ABS'} or '**' in expression.operators:
        raise ModelError('Wide ST supports ABS and basic arithmetic/bitwise operators; other functions/power remain unqualified')
    types={ref:'bool' if kind=='BOOL' else 'number' for ref,kind in declared.items()}
    for ref in declared:
        if isinstance(memory.read(ref,scope),(list,dict)):
            raise ModelError('Wide ST operands must be scalar values')
    def immediate(value):
        if type(value) is not int or not -(1<<31)<=value<1<<31:
            raise ModelError('Wide ST immediates require signed DINT integers representable in the operand type')
        coerce(value,dtype)
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
            if value=='NOT' and result=='bool':return 'bool'
            if result!='number' or value=='!':raise ModelError('Invalid wide ST unary operand')
            return 'number'
        if kind=='call':
            if infer(node[2])!='number':raise ModelError('Wide ST ABS requires a numeric operand')
            return 'number'
        left,right=infer(node[2]),infer(node[3])
        if value in RELATIONS:
            if left!=right or left=='bool' and value not in ('=','<>'):
                raise ModelError('Wide ST comparison operand types must match')
            return 'bool'
        if value in ('AND','OR','XOR') and left==right=='bool':return 'bool'
        if left!='number' or right!='number':raise ModelError('Wide ST arithmetic requires numeric operands')
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
            item=memory.read(value,scope)
            return bool(item) if types[value]=='bool' else number(item)
        if kind=='unary':
            if value in ('+','-') and node[2][0] in ('literal','typed_literal') and type(node[2][1]) is int:
                return number(node[2][1] if value=='+' else -node[2][1])
            item=visit(node[2])
            if value=='NOT' and type(item) is bool:return not item
            return number(item if value=='+' else -item if value=='-' else bit_value(~item,dtype))
        if kind=='call':return number(abs(visit(node[2])))
        left,right=visit(node[2]),visit(node[3])
        if value in RELATIONS:return RELATIONS[value](left,right)
        if value in ('AND','OR','XOR') and type(left) is type(right) is bool:
            return left and right if value=='AND' else left or right if value=='OR' else left!=right
        if value=='+':result=left+right
        elif value=='-':result=left-right
        elif value=='*':result=left*right
        elif value=='/':result=quotient(left,right)
        elif value=='MOD':result=left-quotient(left,right)*right
        elif value=='AND':result=bit_value(left&right,dtype)
        elif value=='OR':result=bit_value(left|right,dtype)
        elif value=='XOR':result=bit_value(left^right,dtype)
        else:raise ModelError('Unsupported wide ST operator '+value)
        return number(result)
    return visit(expression.tree)


def description(project):
    return dict(profile='v35-5580-homogeneous-wide-ST',types=sorted(WIDE_TYPES),
                available=project.version=='35' and project.processor.upper() in CONTROLLERS,
                operators=['+','-','*','/','MOD','AND','OR','XOR','NOT','ABS','comparisons'],
                literals='Untyped signed DINT integers or matching decimal L/U/UL literals within declared range',
                arithmetic='Exact integers, quotient toward zero; every numeric intermediate must fit its declared type',
                conditions='Wide comparisons with BOOL operands/logic; eager operand evaluation',
                mixed_numeric_types=False,native_runtime_parity=False,
                remaining=['Mixed numeric types/conversions, typed radix literals and typed instruction arguments','Power/other functions',
                           'Wide FOR/CASE/index forms','CPT/CMP/MEQ and file-expression consumers',
                           'Native math/status/fault/overflow/intermediate parity'])
