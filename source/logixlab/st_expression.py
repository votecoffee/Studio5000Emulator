"""Typed ST expression subset with ST's own operator precedence."""
import math
from .expressions import Expression
from .conditions import RELATIONS
from .model import ModelError,coerce
from . import wide_st


class STExpression(Expression):
    def __init__(self,text):
        try:super().__init__(text,condition=True,structured=True)
        except (ValueError,IndexError) as e:raise ModelError('Malformed ST expression') from e

    def analyze(self,memory,scope='',destination_type=None):
        wide=wide_st.analyze(self,memory,scope,destination_type)
        if wide is not None:return wide[1],False,wide[2]
        real=False;types={};numeric_refs={}
        for ref in self.refs:
            dtype=memory.resolve(ref,scope)[2]
            if dtype=='BOOL':types[ref]='bool'
            elif dtype in ('SINT','INT','DINT','REAL'):
                types[ref]='number';numeric_refs[ref]=dtype;real|=dtype=='REAL'
            elif memory.project.string_capacity(dtype) is not None:types[ref]='string'
            else:raise ModelError('Unsupported ST expression type '+dtype)
            value=memory.read(ref,scope)
            if isinstance(value,list):raise ModelError('ST expressions require scalar operands')
        bitwise=False
        def infer(node):
            nonlocal real,bitwise
            kind,value=node[:2]
            if kind=='literal':
                real|=isinstance(value,float);return 'bool' if isinstance(value,bool) else 'number'
            if kind=='string':return 'string'
            if kind=='ref':return types[value]
            if kind=='call':
                if infer(node[2])!='number':raise ModelError('ST math function requires a numeric operand')
                real|=value not in ('ABS','TRN','TRUNC');return 'number'
            if kind=='unary':
                t=infer(node[2])
                if value=='NOT' and t=='bool':return 'bool'
                if t!='number' or value=='!':raise ModelError('Invalid ST unary operand')
                bitwise|=value=='NOT';return 'number'
            left,right=infer(node[2]),infer(node[3])
            if value in RELATIONS:
                if left!=right or left=='bool' and value not in ('=','<>'):raise ModelError('ST comparison operand types must match')
                return 'bool'
            if value in ('AND','OR','XOR') and left==right=='bool':return 'bool'
            if left!='number' or right!='number':raise ModelError('ST arithmetic requires numeric operands')
            bitwise|=value in ('AND','OR','XOR');return 'number'
        result=infer(self.tree)
        if bitwise and (real or any(t!='DINT' for t in numeric_refs.values())):
            raise ModelError('Numeric ST bitwise expressions currently require DINT operands')
        if not real and '/' in self.operators:raise ModelError('Integer ST division is unsupported; use an explicit REAL operand')
        return result,real,types

    def evaluate(self,memory,scope='',destination_type=None):
        wide=wide_st.analyze(self,memory,scope,destination_type)
        if wide is not None:return wide_st.evaluate(self,memory,scope,wide)
        _,real,types=self.analyze(memory,scope)
        def number(x):return coerce(x,'REAL' if real else 'DINT')
        def visit(node):
            kind,value=node[:2]
            if kind=='literal':return value if isinstance(value,bool) else number(value)
            if kind=='string':return value
            if kind=='ref':
                if types[value]=='string':return memory.string(value,scope)
                x=memory.read(value,scope);return bool(x) if types[value]=='bool' else number(x)
            if kind=='call':return number(self.function_map[value](visit(node[2])))
            if kind=='unary':
                if value=='-' and node[2][0]=='literal' and type(node[2][1]) is int:return number(-node[2][1])
                x=visit(node[2])
                if value=='NOT' and isinstance(x,bool):return not x
                return number(x if value=='+' else -x if value=='-' else ~x)
            x,y=visit(node[2]),visit(node[3])
            if value in RELATIONS:return RELATIONS[value](x,y)
            if value in ('AND','OR','XOR') and isinstance(x,bool) and isinstance(y,bool):
                return x and y if value=='AND' else x or y if value=='OR' else x!=y
            if value in ('/','MOD') and not y:raise ModelError('ST divide by zero')
            if value=='**' and (abs(y)>1024 or not real and (not isinstance(y,int) or not 0<=y<=31)):
                raise ModelError('ST exponent outside modeled range')
            if value=='+':z=x+y
            elif value=='-':z=x-y
            elif value=='*':z=x*y
            elif value=='/':z=x/y
            elif value=='MOD':z=math.fmod(x,y) if real else x-(abs(x)//abs(y)*(-1 if (x<0)!=(y<0) else 1))*y
            elif value=='**':z=x**y
            elif value=='AND':z=x&y
            elif value=='OR':z=x|y
            elif value=='XOR':z=x^y
            else:raise ModelError('Unsupported ST operator '+value)
            if isinstance(z,complex):raise ModelError('Complex ST result')
            return number(z)
        return visit(self.tree)
