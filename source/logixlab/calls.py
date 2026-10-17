"""Conservative typed by-value JSR/SBR/RET transfers, bounded to 25 calls."""
import copy
import re
from dataclasses import dataclass
from .model import ModelError, coerce, literal, operand_problem, operations


@dataclass
class Operand:
    ref:str
    scope:str
    key:object
    parts:list
    dtype:str
    dims:tuple


def shape(value):
    result=[]
    while isinstance(value,list):
        result.append(len(value));value=value[0] if value else None
    return tuple(result)


def overlaps(a,b):
    return a.key is not None and a.key==b.key and (a.parts[:len(b.parts)]==b.parts or b.parts[:len(a.parts)]==a.parts)


class Calls:
    def __init__(self,engine):
        self.engine=engine;self.memory=engine.memory;self.stack=[];self.signatures={};self.edges={}

    def operand(self,ref,scope,writable=False):
        try:
            value=literal(ref)
            if writable:raise ModelError('Parameter destination must be a writable tag')
            dtype='BOOL' if isinstance(value,bool) else 'REAL' if isinstance(value,float) else 'DINT'
            coerce(value,dtype)
            return Operand(ref,scope,None,[],dtype,())
        except ValueError:pass
        # Native evaluation timing of aliased indirect operands is not assumed.
        for indices in re.findall(r'\[([^\]]*)\]',ref):
            if not re.fullmatch(r'\s*\d+\s*(?:,\s*\d+\s*)*',indices):raise ModelError('Routine parameters require static array indices')
        key,parts,dtype=self.memory.check_writable(ref,scope) if writable else self.memory.resolve(ref,scope)
        if key is None or any(isinstance(p,tuple) for p in parts):raise ModelError('Routine parameter system/bit selections are unsupported')
        value=self.memory.at(key,parts)
        return Operand(self.memory.address(key,parts),'',key,parts,dtype,shape(value))

    def check_pairs(self,sources,destinations):
        if len(sources)!=len(destinations):raise ModelError('Routine parameter counts must match exactly')
        for source,dest in zip(sources,destinations):
            if source.dtype!=dest.dtype or source.dims!=dest.dims:
                raise ModelError('Routine parameter data types and array dimensions must match exactly')
        for i,dest in enumerate(destinations):
            for j,source in enumerate(sources):
                if i!=j and overlaps(source,dest):raise ModelError('Cross-parameter source/destination overlap is unsupported')
            for other in destinations[:i]:
                if overlaps(dest,other):raise ModelError('Overlapping parameter destinations are unsupported')

    def signature(self,routine):
        if routine.key.lower() in self.signatures:return self.signatures[routine.key.lower()]
        ops=[op for rung in routine.rungs for op in operations(rung['nodes'])]
        headers=[op for op in ops if op.name=='SBR'];returns=[op for op in ops if op.name=='RET']
        if len(headers)>1:raise ModelError(routine.key+': only one SBR is permitted')
        first=routine.statements[0].op if routine.kind=='ST' and routine.statements and routine.statements[0].kind=='call' else None
        if headers and ((routine.kind=='ST' and first is not headers[0]) or (routine.kind!='ST' and (not routine.rungs or not routine.rungs[0]['nodes'] or routine.rungs[0]['nodes'][0] is not headers[0]))):
            raise ModelError(routine.key+': SBR must be the first unbranched instruction')
        main=self.engine.project.programs[routine.program]['main']
        if routine.name.lower()==main.lower() and returns:raise ModelError(routine.key+': RET in a main routine is invalid')
        result=(headers[0] if headers else None,returns)
        self.signatures[routine.key.lower()]=result;return result

    def validate_routine(self,routine,entry=False):
        header,returns=self.signature(routine)
        if entry and (header and header.args or any(op.args for op in returns)):
            raise ModelError('Parameterized routine requires a JSR caller; select its caller for the harness')

    def validate_operands(self,op,scope):
        problem=operand_problem(op)
        if problem:raise ModelError(problem)
        if op.name=='JSR':
            count=int(op.args[1])
            for ref in op.args[2:2+count]:self.operand(ref,scope)
            for ref in op.args[2+count:]:self.operand(ref,scope,writable=True)
        else:
            for ref in op.args:self.operand(ref,scope,writable=op.name=='SBR')

    def call_spec(self,op,scope):
        problem=operand_problem(op)
        if problem:raise ModelError(problem)
        key=(scope+'/'+op.args[0]).lower();routine=self.engine.project.routines.get(key)
        if routine is None:raise ModelError('Routine '+key+' is missing')
        if routine.name.lower()==self.engine.project.programs[scope]['main'].lower():raise ModelError('JSR cannot call a main routine')
        header,returns=self.signature(routine);count=int(op.args[1])
        sources=[self.operand(x,scope) for x in op.args[2:2+count]]
        inputs=[self.operand(x,scope,writable=True) for x in header.args] if header else []
        self.check_pairs(sources,inputs)
        destinations=[self.operand(x,scope,writable=True) for x in op.args[2+count:]]
        if destinations and not returns:raise ModelError('JSR return destinations require RET operands')
        for ret in returns:self.check_pairs([self.operand(x,scope) for x in ret.args],destinations)
        self.edges[key]={'inputs':count,'returns':len(destinations)}
        return key,sources,inputs,destinations

    def values(self,operands):
        return [coerce(self.memory.read(p.ref,p.scope),p.dtype) if p.key is None else copy.deepcopy(self.memory.read(p.ref,p.scope)) for p in operands]

    def store(self,destinations,values):
        for dest,value in zip(destinations,values):
            # Scalar coercion is unnecessary: the declared types already match.
            self.memory.check_writable(dest.ref,dest.scope)
            self.memory.store(dest.key,dest.parts,value)

    def call(self,op,scope,depth):
        if len(self.stack)>=25:raise ModelError('JSR nesting limit of 25 exceeded')
        key,sources,inputs,destinations=self.call_spec(op,scope)
        frame={'key':key,'inputs':inputs,'values':self.values(sources),'destinations':destinations,'received':False,'returned':False}
        self.stack.append(frame)
        try:
            self.engine._routine(key,depth+1)
            if destinations and not frame['returned']:raise ModelError('Subroutine ended without passing required RET values')
        finally:self.stack.pop()

    def receive(self,op,scope):
        if not self.stack:
            if op.args:raise ModelError('SBR has no JSR caller')
            return
        frame=self.stack[-1]
        if frame['received']:raise ModelError('SBR executed more than once in one call')
        destinations=[self.operand(x,scope,writable=True) for x in op.args]
        self.store(destinations,frame['values']);frame['received']=True

    def returned(self,op,scope):
        if not self.stack:
            if op.args:raise ModelError('RET has no JSR caller')
            return
        frame=self.stack[-1];sources=[self.operand(x,scope) for x in op.args]
        self.check_pairs(sources,frame['destinations'])
        self.store(frame['destinations'],self.values(sources));frame['returned']=True

    def report(self):
        return {'calls':self.edges,'nesting_limit':25,'parameters_per_direction':40,
                'contract':'Exact counts/types/dimensions; copied values; static references; cross-parameter overlap rejected; prescan does not transfer parameters'}
