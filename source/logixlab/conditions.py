"""Typed CMP expressions using the same bounded parser as CPT."""
import math
from .integer_math import CONTROLLERS, quotient, integer_power
import operator
from .expressions import Expression, FUNCTIONS, BCD_FUNCTIONS, index_function
from .model import ModelError, coerce

RELATIONS={'=':operator.eq,'<>':operator.ne,'<':operator.lt,'<=':operator.le,'>':operator.gt,'>=':operator.ge}
LOGICAL={'&&','^^','||'}


class Condition(Expression):
    def __init__(self,text,*,allow_wide=False,bcd=False,lreal=False,integer_literals=False):
        super().__init__(text,condition=True,bcd=bcd,floating_literals=lreal,integer_literals=lreal or integer_literals)
        self.allow_wide=allow_wide
        self.allow_lreal=lreal

    def floating_profile(self,memory,scope):
        if not self.allow_lreal:return None
        from . import lreal_expressions, comparisons
        previous=memory.structural
        if comparisons.available(memory.project):memory.structural=True
        try:return lreal_expressions.analyze(self,memory,scope,consumer='CMP')
        finally:memory.structural=previous

    def wide_profile(self,memory,scope):
        if not self.allow_wide:return None
        from . import wide_st, comparisons
        previous=memory.structural
        if comparisons.available(memory.project):memory.structural=True
        try:profile=wide_st.analyze(self,memory,scope,consumer='CMP')
        finally:memory.structural=previous
        if profile is not None and profile[1]!='bool':raise ModelError('CMP requires a BOOL result or comparison')
        return profile

    def validate(self,memory,scope=''):
        floating=self.floating_profile(memory,scope)
        if floating is not None:return True,floating['types']
        wide=self.wide_profile(memory,scope)
        if wide is not None:return False,wide[2]
        if self.typed_types:raise ModelError('Typed integer literals require the qualified integer expression profile')
        types={};real=False
        integer_root = memory.project.version == '35' and memory.project.processor.upper() in CONTROLLERS
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
                real|=value not in {'ABS','TRN','TRUNC',*BCD_FUNCTIONS} and not (integer_root and value=='SQR');return 'number'
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
        if self.functions & BCD_FUNCTIONS:
            if memory.project.version!='35' or memory.project.processor.upper() not in CONTROLLERS:
                raise ModelError('BCD conditions require the v35 ControlLogix 5580 profile')
            if real or 'string' in types.values():
                raise ModelError('BCD conditions require narrow integer arithmetic and Boolean composition')
        if real and self.operators & {'AND','OR','XOR','NOT'}:
            raise ModelError('Mixed REAL and bitwise CMP expressions are unsupported')
        if not real and '**' in self.operators:
            if memory.project.version != '35' or memory.project.processor.upper() not in CONTROLLERS:
                raise ModelError('Integer expression power requires the v35 ControlLogix 5580 profile')
        return real,types

    def evaluate(self,memory,scope=''):
        floating=self.floating_profile(memory,scope)
        if floating is not None:
            from . import lreal_expressions
            return bool(lreal_expressions.evaluate(self,memory,scope,floating))
        wide=self.wide_profile(memory,scope)
        if wide is not None:
            from . import wide_st
            return bool(wide_st.evaluate(self,memory,scope,wide))
        real,types=self.validate(memory,scope)
        def number(x):return coerce(x,'REAL' if real else 'DINT')
        def visit(node):
            kind,value=node[:2]
            if kind=='literal':return number(value)
            if kind=='ref':
                if types[value]=='string':return memory.string(value,scope)
                x=memory.read(value,scope);return number(x) if types[value]=='number' else bool(x)
            if kind=='call':
                x=visit(node[2]);return number(index_function(value,x) if value in BCD_FUNCTIONS or not real and value=='SQR' else FUNCTIONS[value](x))
            if kind=='unary':
                if value=='-' and node[2][0]=='literal' and type(node[2][1]) is int:return number(-node[2][1])
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
            elif value=='/':result=x/y if real else quotient(x,y)
            elif value=='MOD':result=math.fmod(x,y) if real else x-quotient(x,y)*y
            elif value=='**':result=x**y if real else integer_power(x,y)
            elif value=='AND':result=x&y
            elif value=='OR':result=x|y
            elif value=='XOR':result=x^y
            else:raise ModelError('Unsupported CMP operator '+value)
            if isinstance(result,complex):raise ModelError('Complex CMP result')
            return result if isinstance(result,bool) else number(result)
        return bool(visit(self.tree))
