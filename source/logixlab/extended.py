"""Typed data and expression instructions, with explicit supported-form checks."""
import copy
import re
from .expressions import Expression
from .conditions import Condition
from . import string_operations, string_conversions
from .model import ModelError, coerce

EXTENDED = {'COP','CPS','FLL','SIZE','CPT','CONCAT','MID','DTOS','STOD','TRN','CMP','MEQ'}
COMPARE = {'EQU','NEQ','LES','LEQ','GRT','GEQ'}


class Extensions:
    def __init__(self, engine):
        self.engine=engine
        self.memory=engine.memory
        self.expressions={}
        self.conditions={}

    def condition(self,text):
        if text not in self.conditions:self.conditions[text]=Condition(text)
        return self.conditions[text]

    def masked(self,ref,scope):
        if re.fullmatch(r'(?:2|8|16)#[0-9A-Fa-f_]+',ref):
            from .model import literal
            value=literal(ref)
            if not 0<=value<=0xffffffff:raise ModelError('MEQ immediate exceeds 32 bits')
            return value
        value=self.integer(ref,scope)
        try:dtype=self.memory.resolve(ref,scope)[2]
        except ModelError:dtype='DINT'
        # MEQ zero-extends signed SINT/INT values, unlike ordinary signed math.
        return value & ((1<<{'SINT':8,'INT':16,'DINT':32}[dtype])-1)

    def integer(self,ref,scope):
        value=self.memory.read(ref,scope)
        try:dtype=self.memory.resolve(ref,scope)[2]
        except ModelError:dtype='DINT'  # A literal already accepted by read().
        if dtype not in ('SINT','INT','DINT'):raise ModelError('This operand requires SINT, INT or DINT')
        if isinstance(value,bool) or not isinstance(value,int):raise ModelError('Integer operand required')
        coerce(value,'DINT')
        return value

    def numeric_destination(self,ref,scope,integer=False):
        _,_,dtype=self.memory.check_writable(ref,scope)
        if dtype not in (('SINT','INT','DINT') if integer else ('SINT','INT','DINT','REAL')):
            raise ModelError('Numeric scalar destination required')
        if isinstance(self.memory.read(ref,scope),(dict,list,bool)):raise ModelError('Numeric scalar destination required')
        return dtype

    def is_string(self,ref,scope):
        try:return self.memory.project.string_capacity(self.memory.resolve(ref,scope)[2]) is not None
        except ModelError:return False

    def expression(self,text):
        if text not in self.expressions:self.expressions[text]=Expression(text)
        return self.expressions[text]

    def block(self,op,scope,execute=False):
        n,a=op.name,op.args
        count=self.integer(a[2],scope)
        self.memory.check_writable(a[1],scope)
        dk,dparts,dt=self.memory.region(a[1],count,scope)
        if n in ('COP','CPS'):
            sk,sparts,st=self.memory.region(a[0],count,scope)
            if st!=dt:raise ModelError('COP/CPS currently require identical declared element types; byte reinterpretation is blocked')
            if execute:
                # Native COP supports propagation through overlapping array elements.
                for source,dest in zip(sparts,dparts):self.memory.store(dk,dest,self.memory.at(sk,source))
        else:
            value=self.memory.read(a[0],scope)
            if isinstance(value,(bool,dict,list)):raise ModelError('FLL requires a numeric scalar source')
            aggregate=dt in ('TIMER','COUNTER','CONTROL','STRING') or dt.lower() in self.memory.project.udts
            if aggregate:
                if not isinstance(value,int) or value!=0:raise ModelError('FLL of structures currently supports DINT zero only')
                def zero(obj):
                    if isinstance(obj,dict):return {k:zero(v) for k,v in obj.items()}
                    if isinstance(obj,list):return [zero(v) for v in obj]
                    return False if isinstance(obj,bool) else 0.0 if isinstance(obj,float) else 0
                if execute:
                    for dest in dparts:self.memory.store(dk,dest,self.memory.project.default(dt) if dt=='CONTROL' else zero(self.memory.at(dk,dest)))
            else:
                if dt not in ('SINT','INT','DINT','REAL'):raise ModelError('Unsupported FLL destination type')
                # Out-of-range narrowing is blocked instead of guessing native truncation.
                value=coerce(value,dt)
                if execute:
                    for dest in dparts:self.memory.store(dk,dest,value)

    def validate(self,op,scope):
        n,a=op.name,op.args
        if n in COMPARE and any(self.is_string(x,scope) for x in a):
            for arg in a:self.memory.string(arg,scope)
            return True
        if n in string_conversions.INSTRUCTIONS:
            string_conversions.validate(self.memory,op,scope);return True
        if n in string_operations.INSTRUCTIONS:
            string_operations.validate(self.memory,op,scope);return True
        if n not in EXTENDED:return False
        if n=='CMP':self.condition(a[0]).validate(self.memory,scope)
        elif n=='MEQ':
            for arg in a:self.masked(arg,scope)
        elif n in ('COP','CPS','FLL'):self.block(op,scope)
        elif n=='SIZE':
            value=self.memory.read(a[0],scope)
            dim=self.integer(a[1],scope)
            if not 0<=dim<=2:raise ModelError('SIZE dimension must be 0..2')
            for _ in range(dim):
                if not isinstance(value,list) or not value:raise ModelError('SIZE dimension exceeds array rank')
                value=value[0]
            if not isinstance(value,list):raise ModelError('SIZE source must address an array')
            self.numeric_destination(a[2],scope,integer=True)
        elif n=='CPT':
            dtype=self.numeric_destination(a[0],scope)
            self.expression(a[1]).validate(self.memory,scope,dtype)
        elif n=='TRN':
            self.numeric_destination(a[1],scope)
            value=self.memory.read(a[0],scope)
            if isinstance(value,(dict,list,bool)) or not isinstance(value,(int,float)):raise ModelError('Numeric TRN source required')
            try:dtype=self.memory.resolve(a[0],scope)[2]
            except ModelError:dtype='REAL'
            if dtype!='REAL':raise ModelError('TRN currently requires a REAL source tag or numeric immediate')
        elif n in ('CONCAT','MID'):
            sources=a[:2] if n=='CONCAT' else a[:1]
            for source in sources:self.memory.string(source,scope)
            dest=a[2] if n=='CONCAT' else a[3]
            self.memory.string(dest,scope);self.memory.check_writable(dest,scope)
            if n=='MID':
                length,start=self.integer(a[1],scope),self.integer(a[2],scope)
                if length<0 or start<1:raise ModelError('MID requires nonnegative length and a one-based start')
        elif n=='DTOS':
            self.integer(a[0],scope);self.memory.string(a[1],scope);self.memory.check_writable(a[1],scope)
        elif n=='STOD':
            self.memory.string(a[0],scope);self.numeric_destination(a[1],scope,integer=True)
        return True

    def execute(self,op,power,scope):
        n,a=op.name,op.args
        if n in COMPARE and any(self.is_string(x,scope) for x in a):
            if not power:return False
            x,y=(self.memory.string(arg,scope) for arg in a)
            return {'EQU':x==y,'NEQ':x!=y,'LES':x<y,'LEQ':x<=y,'GRT':x>y,'GEQ':x>=y}[n]
        if n in string_conversions.INSTRUCTIONS:
            if power:string_conversions.execute(self.memory,op,scope)
            return power
        if n in string_operations.INSTRUCTIONS:
            if power:string_operations.execute(self.memory,op,scope)
            return power
        if n not in EXTENDED:return None
        if not power:return power
        if n=='CMP':return self.condition(a[0]).evaluate(self.memory,scope)
        if n=='MEQ':
            source,mask,compare=(self.masked(x,scope) for x in a)
            return (source&mask)==(compare&mask)
        if n in ('COP','CPS','FLL'):self.block(op,scope,execute=True)
        elif n=='SIZE':
            value=self.memory.read(a[0],scope)
            dimension=self.integer(a[1],scope)
            if not 0<=dimension<=2:raise ModelError('SIZE dimension must be 0..2')
            for _ in range(dimension):
                if not isinstance(value,list) or not value:raise ModelError('SIZE dimension exceeds array rank')
                value=value[0]
            if not isinstance(value,list):raise ModelError('SIZE dimension exceeds array rank')
            self.memory.write(a[2],len(value),scope)
        elif n=='CPT':
            dtype=self.memory.resolve(a[0],scope)[2]
            self.memory.write(a[0],self.expression(a[1]).evaluate(self.memory,scope,dtype),scope)
        elif n=='TRN':self.memory.write(a[1],__import__('math').trunc(coerce(self.memory.read(a[0],scope),'REAL')),scope)
        elif n=='CONCAT':
            text=self.memory.string(a[0],scope)+self.memory.string(a[1],scope)
            self.memory.write_string(a[2],text,scope)
        elif n=='MID':
            source=self.memory.string(a[0],scope)
            length,start=self.integer(a[1],scope),self.integer(a[2],scope)
            if length<0 or start<1 or start>len(source)+1 or start-1+length>len(source):
                raise ModelError('MID range exceeds modeled source bounds')
            self.memory.write_string(a[3],source[start-1:start-1+length],scope)
        elif n=='DTOS':self.memory.write_string(a[1],str(self.integer(a[0],scope)),scope)
        elif n=='STOD':
            match=re.search(r'-?[0-9]+',self.memory.string(a[0],scope))
            self.memory.write(a[1],int(match[0]) if match else 0,scope)
        return power
