"""Typed CMP expressions using the same bounded parser as CPT."""
import math
import operator
from .expressions import Expression, FUNCTIONS
from .model import ModelError, coerce

RELATIONS={'=':operator.eq,'<>':operator.ne,'<':operator.lt,'<=':operator.le,'>':operator.gt,'>=':operator.ge}
LOGICAL={'&&','^^','||'}


class Condition(Expression):
    def __init__(self,text):super().__init__(text,condition=True)

    def validate(self,memory,scope=''):
        types={};real=False
        for ref in self.refs:
            dtype=memory.resolve(ref,scope)[2]
            if dtype=='BOOL':types[ref]='bool';memory.read(ref,scope)
            elif dtype in ('SINT','INT','DINT','REAL'):
                if isinstance(memory.read(ref,scope),(dict,list)):raise ModelError('CMP requires scalar numeric operands')
                types[ref]='number';real|=dtype=='REAL'
            elif memory.project.string_capacity(dtype) is not None:
                memory.string(ref,scope);types[ref]='string'
            else:raise ModelError('Unsupported CMP operand type '+dtype)
        def infer(node):
            nonlocal real
            kind,value=node[:2]
            if kind=='literal':
                real|=isinstance(value,float);return 'number'
            if kind=='ref':return types[value]
            if kind=='call':
                if infer(node[2])!='number':raise ModelError('CMP math functions require numeric operands')
                real|=value not in ('ABS','TRN','TRUNC');return 'number'
            if kind=='unary':
                operand=infer(node[2])
                if value=='!':
                    if operand!='bool':raise ModelError('CMP ! requires a BOOL expression')
                    return 'bool'
                if value=='NOT' and operand=='bool':return 'bool'
                if operand!='number':raise ModelError('CMP arithmetic requires numeric operands')
                return 'number'
            left,right=infer(node[2]),infer(node[3])
            if value in RELATIONS:
                if left!=right or (left=='bool' and value not in ('=','<>')):
                    raise ModelError('CMP comparison operand types must match')
                return 'bool'
            if value in LOGICAL:
                if left!='bool' or right!='bool':raise ModelError('CMP logical operators require BOOL expressions')
                return 'bool'
            if value in ('AND','OR','XOR') and left==right=='bool':return 'bool'
            if left!='number' or right!='number':raise ModelError('CMP arithmetic requires numeric operands')
            return 'number'
        if infer(self.tree)!='bool':raise ModelError('CMP requires a BOOL result or comparison')
        if real and self.operators & {'AND','OR','XOR','NOT'}:
            raise ModelError('Mixed REAL and bitwise CMP expressions are unsupported')
        if not real and self.operators & {'/','**'}:
            raise ModelError('Integer CMP division/power is unsupported; use a REAL operand')
        return real,types

    def evaluate(self,memory,scope=''):
        real,types=self.validate(memory,scope)
        def number(x):return coerce(x,'REAL' if real else 'DINT')
        def visit(node):
            kind,value=node[:2]
            if kind=='literal':return number(value)
            if kind=='ref':
                if types[value]=='string':return memory.string(value,scope)
                x=memory.read(value,scope);return number(x) if types[value]=='number' else bool(x)
            if kind=='call':return number(FUNCTIONS[value](visit(node[2])))
            if kind=='unary':
                x=visit(node[2])
                if value=='!' or value=='NOT' and isinstance(x,bool):return not x
                return number(x if value=='+' else -x if value=='-' else ~x)
            # Both sides are checked/evaluated. No assumed short-circuit path can
            # conceal an unknown value, out-of-bounds access or arithmetic fault.
            x,y=visit(node[2]),visit(node[3])
            if value in RELATIONS:return RELATIONS[value](x,y)
            if value in LOGICAL:return (x and y) if value=='&&' else (x or y) if value=='||' else x!=y
            if value in ('/','MOD') and not y:raise ModelError('CMP divide by zero')
            if value=='**' and abs(y)>1024:raise ModelError('CMP exponent outside modeled range')
            if value=='+':result=x+y
            elif value=='-':result=x-y
            elif value=='*':result=x*y
            elif value=='/':result=x/y
            elif value=='MOD':result=math.fmod(x,y) if real else x-(abs(x)//abs(y)*(-1 if (x<0)!=(y<0) else 1))*y
            elif value=='**':result=x**y
            elif value=='AND':result=x&y
            elif value=='OR':result=x|y
            elif value=='XOR':result=x^y
            else:raise ModelError('Unsupported CMP operator '+value)
            if isinstance(result,complex):raise ModelError('Complex CMP result')
            return result if isinstance(result,bool) else number(result)
        return bool(visit(self.tree))
